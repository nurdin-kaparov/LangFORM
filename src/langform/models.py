from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable


class ModelError(RuntimeError):
    """Raised when the configured local model cannot complete an operation."""


class OllamaUnavailableError(ModelError):
    """Raised when no Ollama service responds at the configured local address."""


class OllamaResponseTooLargeError(ModelError):
    """Raised when an Ollama inventory response exceeds the local byte budget."""


OLLAMA_INVENTORY_MAX_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ModelDefinition:
    model_id: str
    display_name: str
    ollama_tag: str
    parameter_count: str
    license_name: str
    license_url: str
    estimated_system_ram_gb: int
    notes: str


MODEL_CATALOG = (
    ModelDefinition(
        "qwen3:1.7b",
        "Qwen3 1.7B",
        "qwen3:1.7b",
        "1.7B",
        "Apache-2.0",
        "https://huggingface.co/Qwen/Qwen3-1.7B",
        3,
        "Lower-memory option; context capacity depends on runtime settings.",
    ),
    ModelDefinition(
        "qwen3:4b",
        "Qwen3 4B",
        "qwen3:4b",
        "4B",
        "Apache-2.0",
        "https://huggingface.co/Qwen/Qwen3-4B",
        6,
        "Balanced default candidate for local Context Formation.",
    ),
    ModelDefinition(
        "phi4-mini:3.8b",
        "Phi-4 Mini 3.8B",
        "phi4-mini:3.8b",
        "3.8B",
        "MIT",
        "https://huggingface.co/microsoft/Phi-4-mini-instruct",
        6,
        "Long-context model; the published window is not a promise of local RAM fit.",
    ),
    ModelDefinition(
        "gemma3:4b",
        "Gemma 3 4B",
        "gemma3:4b",
        "4B",
        "Gemma Terms of Use",
        "https://ai.google.dev/gemma/terms",
        8,
        "Review Gemma's terms before use; runtime and context settings affect memory.",
    ),
)


def _requests():
    try:
        import requests
    except ImportError as exc:
        raise ModelError(
            'Ollama support requires requests. Install with: pip install -e ".[ollama]"'
        ) from exc
    return requests


@dataclass
class OllamaSLM:
    model: str = "qwen3:4b"
    base_url: str = "http://127.0.0.1:11434"
    timeout: int = 120

    def _request(self, method: str, path: str, **kwargs: Any):
        requests = _requests()
        try:
            response = requests.request(
                method,
                f"{self.base_url.rstrip('/')}{path}",
                timeout=kwargs.pop("timeout", self.timeout),
                **kwargs,
            )
            try:
                response.raise_for_status()
            except requests.RequestException:
                response.close()
                raise
            return response
        except requests.RequestException as exc:
            raise OllamaUnavailableError(f"Ollama request failed: {exc}") from exc

    def list_models(self) -> list[dict[str, Any]]:
        requests = _requests()
        body = bytearray()
        try:
            with self._request("GET", "/api/tags", stream=True) as response:
                # iter_content counts decoded bytes, including compressed responses.
                # Never access response.content/json(), which buffer without a limit.
                for chunk in response.iter_content(chunk_size=8192):
                    if len(body) + len(chunk) > OLLAMA_INVENTORY_MAX_BYTES:
                        raise OllamaResponseTooLargeError(
                            "Ollama inventory response exceeds the one-mebibyte byte budget."
                        )
                    body.extend(chunk)
        except requests.RequestException as exc:
            raise OllamaUnavailableError("Ollama inventory response could not be read.") from exc
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise ModelError("Ollama returned invalid inventory JSON.") from exc
        if not isinstance(payload, dict):
            raise ModelError("Ollama returned an invalid model list.")
        models = payload.get("models", [])
        if not isinstance(models, list):
            raise ModelError("Ollama returned an invalid model list.")
        return [model for model in models if isinstance(model, dict)]

    def install(
        self,
        model: str,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        requests = _requests()
        try:
            response = requests.post(
                f"{self.base_url.rstrip('/')}/api/pull",
                json={"name": model, "stream": True},
                timeout=self.timeout,
                stream=True,
            )
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    progress = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ModelError("Ollama returned invalid model-download progress.") from exc
                if on_progress:
                    on_progress(progress)
                if progress.get("error"):
                    raise ModelError(str(progress["error"]))
        except requests.RequestException as exc:
            raise OllamaUnavailableError(f"Ollama model download failed: {exc}") from exc

    def generate(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = self._request(
            "POST",
            "/api/chat",
            json={"model": self.model, "messages": messages, "stream": False,
                "options": {"num_ctx": 16384}},
        ).json()
        self.last_usage = {
            "input_tokens": payload.get("prompt_eval_count"),
            "output_tokens": payload.get("eval_count"),
            "duration_ns": payload.get("total_duration"),
        }
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ModelError("Ollama returned an empty model response.")
        return content.strip()

    def inventory_json(self, method: str, path: str, limit: int = 256 * 1024, **kwargs: Any) -> dict:
        """Inventory responses have a separate byte and elapsed-time budget."""
        budget = min(5, self.timeout)
        response = self._request(method, path, stream=True, timeout=budget, **kwargs)
        deadline = time.monotonic() + budget
        content = bytearray()
        try:
            # A small read also checks the deadline during slow trickle responses,
            # rather than waiting indefinitely to fill a large chunk.
            for chunk in response.iter_content(1):
                if time.monotonic() > deadline:
                    raise ModelError("Ollama metadata response exceeded its time budget.")
                if len(content) + len(chunk) > limit:
                    raise OllamaResponseTooLargeError("Ollama metadata response exceeds its byte budget.")
                content.extend(chunk)
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ModelError("Ollama inventory must be an object.")
            return payload
        finally:
            response.close()

    def model_mappings(self, installed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mappings = []
        deadline = time.monotonic() + 5
        probes = 0
        for item in installed[:128]:
            tag = item.get("name")
            if not isinstance(tag, str) or not 0 < len(tag) <= 150:
                continue
            model_id = next((m.model_id for m in MODEL_CATALOG
                             if tag == m.model_id or tag.startswith(m.model_id + "-")), None)
            status = "supported" if model_id else "unsupported"
            if not model_id and (tag == "gemma3" or tag.startswith("gemma3:")):
                status = "unknown"
                if probes < 8 and time.monotonic() < deadline:
                    probes += 1
                    probe = OllamaSLM(base_url=self.base_url, timeout=max(0.1, min(2, deadline - time.monotonic())))
                    try:
                        metadata = probe.inventory_json("POST", "/api/show", json={"model": tag, "verbose": False})
                        info = metadata.get("model_info", {})
                        if isinstance(info, dict) and info.get("general.architecture") == "gemma3":
                            # Published Gemma 3 4B text architecture, not a rounded parameter-size guess.
                            signature = (info.get("gemma3.block_count"), info.get("gemma3.embedding_length"),
                                         info.get("gemma3.attention.head_count"), info.get("gemma3.attention.head_count_kv"))
                            if signature == (34, 2560, 8, 4):
                                model_id, status = "gemma3:4b", "supported"
                            elif all(isinstance(v, int) and v > 0 for v in signature):
                                status = "unsupported"
                        elif isinstance(info, dict) and info.get("general.architecture"):
                            status = "unsupported"
                    except Exception:
                        pass  # Metadata failure is unknown, not absence or a health failure.
            mappings.append({"runtimeTag": tag, "modelId": model_id, "status": status})
        return mappings

    def generate_json(self, prompt: str, system: str | None = None) -> dict[str, Any]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = self._request(
            "POST",
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": "json",
            },
        ).json()
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str):
            raise ModelError("Ollama returned a non-text JSON response.")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelError("Ollama returned invalid JSON.") from exc
        if not isinstance(result, dict):
            raise ModelError("Ollama JSON response must be an object.")
        return result

    def health(self) -> bool:
        return any(
            model.get("name") == self.model or model.get("model") == self.model
            for model in self.list_models()
        )


class ModelManager:
    """Discovers, installs, and selects local Ollama models without cloud fallback."""

    def __init__(self, base_url: str | None = None, timeout: int = 120):
        self.adapter = OllamaSLM(
            base_url=base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            timeout=timeout,
        )

    @staticmethod
    def catalog() -> list[dict[str, Any]]:
        return [asdict(definition) for definition in MODEL_CATALOG]

    def installed_models(self) -> list[dict[str, Any]]:
        return self.adapter.list_models()

    def available_models(self) -> list[dict[str, Any]]:
        installed = self.installed_models()
        mappings = self.adapter.model_mappings(installed)
        return [
            {
                **asdict(definition),
                "installed": any(m["modelId"] == definition.model_id for m in mappings),
            }
            for definition in MODEL_CATALOG
        ]

    def install(
        self,
        model_id: str,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        definition = next(
            (item for item in MODEL_CATALOG if item.model_id == model_id), None
        )
        if definition is None:
            raise ModelError(f"Model is not in the supported local catalog: {model_id}")
        if any(m["modelId"] == model_id and m["status"] == "supported"
               for m in self.adapter.model_mappings(self.installed_models())):
            return
        self.adapter.install(definition.ollama_tag, on_progress=on_progress)

    def select(self, model_id: str) -> str:
        definition = next(
            (item for item in MODEL_CATALOG if item.model_id == model_id), None
        )
        if definition is None:
            raise ModelError(f"Model is not in the supported local catalog: {model_id}")
        mappings = self.adapter.model_mappings(self.installed_models())
        runtime = next((m["runtimeTag"] for m in mappings if m["modelId"] == model_id and m["status"] == "supported"), None)
        if runtime is None:
            raise ModelError(f"Local model is not installed: {definition.ollama_tag}")
        self.adapter.model = runtime
        return runtime
