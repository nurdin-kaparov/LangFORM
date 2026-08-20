from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .models import ModelError, OllamaSLM


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class LangFORMBridgeHandler(BaseHTTPRequestHandler):
    """Small local HTTP bridge between a browser/host app and Ollama."""

    server_version = "LangFORMBridge/0.2.0"

    def _config(self) -> dict[str, str]:
        return {
            "token": getattr(self.server, "bridge_token", ""),
            "allowed_origin": getattr(self.server, "allowed_origin", ""),
            "model": getattr(self.server, "model", "gemma3:4b"),
            "ollama_url": getattr(self.server, "ollama_url", "http://127.0.0.1:11434"),
        }

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = _json_bytes(payload)
        origin = self.headers.get("Origin", "")
        allowed_origin = self._config()["allowed_origin"]
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if allowed_origin and origin == allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = self._config()["token"]
        if not expected:
            return False
        provided = self.headers.get("Authorization", "")
        actual = provided.removeprefix("Bearer ").strip()
        return hmac.compare_digest(actual, expected)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 2_000_000:
            raise ValueError("Request body must be between 1 byte and 2 MB")
        body = self.rfile.read(length)
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object")
        return value

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin", "")
        allowed_origin = self._config()["allowed_origin"]
        if not allowed_origin or origin != allowed_origin:
            self.send_error(403, "Origin is not allowed")
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != "/health":
            self._send_json(404, {"status": "error", "message": "Not found"})
            return
        if not self._authorized():
            self._send_json(401, {"status": "error", "message": "Authorization required"})
            return

        config = self._config()
        slm = OllamaSLM(model=config["model"], base_url=config["ollama_url"])
        try:
            available = slm.health()
            self._send_json(
                200,
                {
                    "status": "ready" if available else "unavailable",
                    "provider": "ollama",
                    "model": config["model"],
                    "ollama_url": config["ollama_url"],
                },
            )
        except ModelError as exc:
            self._send_json(
                503,
                {
                    "status": "unavailable",
                    "provider": "ollama",
                    "model": config["model"],
                    "message": str(exc),
                },
            )

    def do_POST(self) -> None:
        if self.path != "/v1/generate":
            self._send_json(404, {"status": "error", "message": "Not found"})
            return
        if not self._authorized():
            self._send_json(401, {"status": "error", "message": "Authorization required"})
            return

        try:
            payload = self._read_json()
            prompt = payload.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError("prompt is required")
            config = self._config()
            model = payload.get("model") or config["model"]
            slm = OllamaSLM(model=model, base_url=config["ollama_url"])
            response = slm.generate(prompt, system=payload.get("system"))
            self._send_json(
                200,
                {
                    "status": "completed",
                    "model": model,
                    "response": response,
                },
            )
        except (ValueError, ModelError, TypeError) as exc:
            self._send_json(400 if isinstance(exc, ValueError) else 502, {"status": "error", "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the bridge quiet by default; callers can wrap the server if they
        # need structured access logs.
        return


def serve_bridge(
    *,
    host: str | None = None,
    port: int = 8765,
    model: str | None = None,
    ollama_url: str | None = None,
    token: str | None = None,
    allowed_origin: str | None = None,
) -> None:
    bridge_token = token or os.getenv("LANGFORM_BRIDGE_TOKEN", "")
    if not bridge_token:
        raise ValueError("LANGFORM_BRIDGE_TOKEN is required before starting the bridge")

    server = ThreadingHTTPServer((host or os.getenv("LANGFORM_BRIDGE_HOST", "127.0.0.1"), port), LangFORMBridgeHandler)
    server.bridge_token = bridge_token
    server.model = model or os.getenv("LANGFORM_OLLAMA_MODEL", "gemma3:4b")
    server.ollama_url = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    server.allowed_origin = allowed_origin or os.getenv(
        "LANGFORM_ALLOWED_ORIGIN",
        "https://agentic-workspace-flow--nurdin.replit.app",
    )
    print(f"LangFORM bridge listening on http://{server.server_address[0]}:{server.server_address[1]}")
    print(f"Model: {server.model}; Ollama: {server.ollama_url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()