from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from langform.bridge import LangFORMBridgeHandler
from langform.models import OllamaSLM


def _start_bridge(monkeypatch):
    monkeypatch.setattr(OllamaSLM, "health", lambda self: True)
    monkeypatch.setattr(OllamaSLM, "generate", lambda self, prompt, system=None: f"local:{prompt}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), LangFORMBridgeHandler)
    server.bridge_token = "test-token"
    server.allowed_origin = "https://example.test"
    server.model = "gemma3:4b"
    server.ollama_url = "http://127.0.0.1:11434"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _request(server, path, *, method="GET", payload=None, token="test-token"):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Origin": "https://example.test",
        },
    )
    return urllib.request.urlopen(request)


def test_bridge_health_and_generation(monkeypatch):
    server = _start_bridge(monkeypatch)
    try:
        with _request(server, "/health") as response:
            health = json.load(response)
        assert health["status"] == "ready"
        assert health["model"] == "gemma3:4b"

        with _request(
            server,
            "/v1/generate",
            method="POST",
            payload={"prompt": "Summarize this locally"},
        ) as response:
            generated = json.load(response)
        assert generated == {
            "status": "completed",
            "model": "gemma3:4b",
            "response": "local:Summarize this locally",
        }
    finally:
        server.shutdown()
        server.server_close()


def test_bridge_rejects_missing_token(monkeypatch):
    server = _start_bridge(monkeypatch)
    try:
        try:
            _request(server, "/health", token="wrong-token")
        except urllib.error.HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError("Expected the bridge to reject an invalid token")
    finally:
        server.shutdown()
        server.server_close()