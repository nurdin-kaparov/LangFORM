from __future__ import annotations

from dataclasses import dataclass


class ModelError(RuntimeError):
    pass


@dataclass
class OllamaSLM:
    model: str = "gemma3:4b"
    base_url: str = "http://127.0.0.1:11434"
    timeout: int = 120

    def generate(self, prompt: str, system: str | None = None) -> str:
        try:
            import requests
        except ImportError as e:
            raise ModelError(
                "Ollama adapter requires requests. Install with: pip install -e \".[ollama]\""
            ) from e

        full_prompt = prompt if not system else f"SYSTEM:\n{system}\n\nUSER:\n{prompt}"
        try:
            response = requests.post(
                f"{self.base_url.rstrip('/')}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise ModelError(f"Ollama request failed: {e}") from e

        data = response.json()
        return data.get("response", "")

    def health(self) -> bool:
        try:
            import requests
        except ImportError as e:
            raise ModelError(
                "Ollama adapter requires requests. Install with: pip install -e \".[ollama]\""
            ) from e

        try:
            response = requests.get(f"{self.base_url.rstrip('/')}/api/tags", timeout=min(self.timeout, 10))
            response.raise_for_status()
        except requests.RequestException as e:
            raise ModelError(f"Ollama health check failed: {e}") from e

        models = response.json().get("models", [])
        return any(model.get("name") == self.model for model in models)
