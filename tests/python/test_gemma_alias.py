import json
import ast
from pathlib import Path

import pytest

from langform.bridge import ollama_report
from langform.models import ModelError, ModelManager, OllamaSLM

METADATA = json.loads((Path(__file__).parents[1] / "fixtures/gemma-model-metadata.json").read_text())


def test_ollama_adapter_methods_are_not_duplicated():
    import inspect
    module = ast.parse(inspect.getsource(OllamaSLM))
    methods = [node.name for node in module.body[0].body if isinstance(node, ast.FunctionDef)]
    assert len(methods) == len(set(methods)), "Merged adapter methods must not silently override one another"


@pytest.mark.parametrize("fixture,status,model", [
    ("supported4b", "supported", "gemma3:4b"),
    ("unsupported12b", "unsupported", None),
    ("unavailable", "unknown", None),
    ("incomplete", "unknown", None),
])
def test_alias_mapping_and_runtime(monkeypatch, fixture, status, model):
    monkeypatch.setattr(OllamaSLM, "list_models", lambda self: [{"name": "gemma3:latest"}])
    calls = []

    def metadata(self, method, path, **kwargs):
        assert self.timeout <= 2
        assert path == "/api/show"
        assert kwargs["json"] == {"model": "gemma3:latest", "verbose": False}
        calls.append(path)
        return {"model_info": METADATA[fixture]}

    monkeypatch.setattr(OllamaSLM, "inventory_json", metadata)
    report = ollama_report("http://localhost:11434", [])
    assert report["ollamaStatus"] == "reachable"
    assert report["models"] == ["gemma3:latest"]
    assert report["modelMappings"] == [{"runtimeTag": "gemma3:latest", "modelId": model, "status": status}]
    manager = ModelManager()
    monkeypatch.setattr(manager.adapter, "install", lambda *a, **kw: pytest.fail("Unexpected weights download"))
    if model:
        assert manager.select("gemma3:4b") == "gemma3:latest"
        assert manager.adapter.model == "gemma3:latest"
        manager.install("gemma3:4b")
        sent = []
        class Response:
            def json(self):
                return {"message": {"content": "local response"}}
        monkeypatch.setattr(manager.adapter, "_request", lambda *a, **kw: sent.append(kw["json"]) or Response())
        assert manager.adapter.generate("test") == "local response"
        assert sent[0]["model"] == "gemma3:latest"
    else:
        with pytest.raises(ModelError):
            manager.select("gemma3:4b")
    assert calls


def test_unreachable_does_not_reuse_alias_readiness(monkeypatch):
    monkeypatch.setattr(OllamaSLM, "list_models", lambda self: (_ for _ in ()).throw(ModelError("private URL")))
    assert ollama_report("http://localhost:11434", ["gemma3:latest"]) == {
        "ollamaStatus": "unreachable", "models": ["gemma3:latest"]}


def test_metadata_request_failure_is_unknown_not_unreachable(monkeypatch):
    monkeypatch.setattr(OllamaSLM, "list_models", lambda self: [{"name": "gemma3:latest"}])
    monkeypatch.setattr(OllamaSLM, "inventory_json", lambda *a, **kw: (_ for _ in ()).throw(ModelError("private URL")))
    report = ollama_report("http://localhost:11434", [])
    assert report["ollamaStatus"] == "reachable"
    assert report["modelMappings"][0]["status"] == "unknown"
    assert "private" not in str(report)


def test_inventory_response_is_byte_bounded_and_closed(monkeypatch):
    class Response:
        closed = False
        def iter_content(self, size):
            yield b"x" * 33
        def close(self):
            self.closed = True
    response = Response()
    adapter = OllamaSLM()
    monkeypatch.setattr(adapter, "_request", lambda *a, **kw: response)
    with pytest.raises(ModelError):
        adapter.inventory_json("GET", "/api/tags", limit=32)
    assert response.closed
