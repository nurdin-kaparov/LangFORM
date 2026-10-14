import gzip
import io
import json

import pytest
import requests
from urllib3.response import HTTPResponse

from langform.bridge import ollama_report
from langform.models import (
    OLLAMA_INVENTORY_MAX_BYTES,
    ModelError,
    OllamaResponseTooLargeError,
    OllamaSLM,
    OllamaUnavailableError,
)
import socket
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from langform.models import ModelError, OllamaSLM, OllamaUnavailableError


def test_installed_model_with_ollama_stopped_is_not_missing(monkeypatch):
    def stopped(self):
        raise RuntimeError("http://user:private-token@localhost:11434?secret=value")
    monkeypatch.setattr("langform.bridge.OllamaSLM.list_models", stopped)
    report = ollama_report("http://localhost:11434", ["qwen3:4b"])
    assert report == {"ollamaStatus": "unreachable", "models": ["qwen3:4b"]}
    assert "private-token" not in str(report)
    assert ollama_report("http://localhost:11434", [])["ollamaStatus"] == "unreachable"


def test_reachable_server_with_missing_model_and_recovery(monkeypatch):
    def probe(self):
        assert self.timeout == 5
        return []
    monkeypatch.setattr("langform.bridge.OllamaSLM.list_models", probe)
    assert ollama_report("http://localhost:11434", ["qwen3:4b"]) == {
        "ollamaStatus": "reachable", "models": []}
    monkeypatch.setattr("langform.bridge.OllamaSLM.list_models", lambda self: [{"name": "qwen3:4b"}])
    assert ollama_report("http://localhost:11434", [])["models"] == ["qwen3:4b"]


def test_health_inventory_is_bounded(monkeypatch):
    monkeypatch.setattr("langform.bridge.OllamaSLM.list_models",
                        lambda self: [{"name": "x" * 151}, {}, {"name": None}] + [{"name": "qwen3:4b"}] * 200)
    report = ollama_report("http://localhost:11434", [])
    assert report["ollamaStatus"] == "reachable"
    assert len(report["models"]) == 128

def test_http_connection_refusal_preserves_inventory_and_recovers(loopback_ollama):
    server = loopback_ollama
    previous = ["qwen3:4b"] * 130
    original = previous.copy()
    adapter = OllamaSLM(base_url=server.url, timeout=1)
    with pytest.raises(OllamaUnavailableError) as error:
        adapter.list_models()
    assert isinstance(error.value.__cause__, requests.ConnectionError)
    assert ollama_report(server.url, previous) == {
        "ollamaStatus": "unreachable", "models": previous[:128],
    }
    assert previous == original
    assert server.requests == []

    # The same address recovers without re-pairing or restarting the adapter.
    server.start()
    server.reply(b'{"models": [{"name": "phi4-mini:3.8b"}]}')
    assert adapter.list_models() == [{"name": "phi4-mini:3.8b"}]
    assert ollama_report(server.url, previous) == {
        "ollamaStatus": "reachable", "models": ["phi4-mini:3.8b"],
    }


class StreamingInventory:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = False
        self.read_count = 0

    def raise_for_status(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def iter_content(self, chunk_size):
        assert chunk_size == 8192
        for chunk in self.chunks:
            self.read_count += 1
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def json(self):
        pytest.fail("Inventory must not use unbounded response.json()")


def mock_inventory(monkeypatch, chunks, timeout=120):
    response = StreamingInventory(chunks)

    def request(method, url, **kwargs):
        assert method == "GET"
        assert url == "http://127.0.0.1:11434/api/tags"
        assert kwargs == {"timeout": timeout, "stream": True}
        return response

    monkeypatch.setattr(requests, "request", request)
    return response


def test_streamed_inventory_and_inference_timeout_unchanged(monkeypatch):
    body = json.dumps({"models": [{"name": "qwen3:4b"}, None]}).encode()
    response = mock_inventory(monkeypatch, [body[:7], b"", body[7:]])
    adapter = OllamaSLM()
    assert adapter.list_models() == [{"name": "qwen3:4b"}]
    assert adapter.timeout == 120
    assert response.closed


def test_inventory_at_byte_budget_is_accepted(monkeypatch):
    body = b'{"models":[]}'
    body += b" " * (OLLAMA_INVENTORY_MAX_BYTES - len(body))
    response = mock_inventory(monkeypatch, [
        body[offset:offset + 8192] for offset in range(0, len(body), 8192)
    ])
    assert OllamaSLM().list_models() == []
    assert response.closed


def test_oversized_inventory_stops_reading_and_closes(monkeypatch):
    chunks = [b" " * 8192] * (OLLAMA_INVENTORY_MAX_BYTES // 8192)
    response = mock_inventory(monkeypatch, chunks + [b"x", b"must not be read"])
    with pytest.raises(OllamaResponseTooLargeError, match="byte budget"):
        OllamaSLM().list_models()
    assert response.read_count == len(chunks) + 1
    assert response.closed


def test_oversized_probe_preserves_inventory_and_recovers(monkeypatch):
    previous = ["qwen3:4b"]
    response = mock_inventory(monkeypatch, [b"x" * 8192] * (
        OLLAMA_INVENTORY_MAX_BYTES // 8192 + 1
    ), timeout=5)
    assert ollama_report("http://127.0.0.1:11434", previous) == {
        "ollamaStatus": "unreachable", "models": previous,
    }
    assert previous == ["qwen3:4b"]
    assert response.closed
    mock_inventory(monkeypatch, [b'{"models":[{"name":"phi4-mini:3.8b"}]}'], timeout=5)
    assert ollama_report("http://127.0.0.1:11434", previous) == {
        "ollamaStatus": "reachable", "models": ["phi4-mini:3.8b"],
    }


@pytest.mark.parametrize("body", [b"{", b"\xff", b"[]", b'{"models":{}}'])
def test_invalid_inventory_closes_response(monkeypatch, body):
    response = mock_inventory(monkeypatch, [body])
    with pytest.raises(ModelError):
        OllamaSLM().list_models()
    assert response.closed


def test_stream_read_failure_is_unavailable_and_private(monkeypatch):
    response = mock_inventory(monkeypatch, [
        b'{"models":',
        requests.exceptions.ChunkedEncodingError("private-token"),
    ])
    with pytest.raises(OllamaUnavailableError) as error:
        OllamaSLM().list_models()
    assert "private-token" not in str(error.value)
    assert response.closed
    response = mock_inventory(monkeypatch, [
        requests.exceptions.ReadTimeout("http://user:private-token@localhost"),
    ], timeout=5)
    report = ollama_report("http://127.0.0.1:11434", ["qwen3:4b"])
    assert report == {"ollamaStatus": "unreachable", "models": ["qwen3:4b"]}
    assert response.closed


def test_http_error_closes_streamed_response(monkeypatch):
    response = mock_inventory(monkeypatch, [])

    def failed_status():
        raise requests.exceptions.HTTPError("service unavailable")

    monkeypatch.setattr(response, "raise_for_status", failed_status)
    with pytest.raises(OllamaUnavailableError):
        OllamaSLM().list_models()
    assert response.closed


@pytest.mark.parametrize("compressed", [False, True])
def test_real_response_stream_enforces_decoded_byte_budget(monkeypatch, compressed):
    body = b'{"models":[]}' + b" " * OLLAMA_INVENTORY_MAX_BYTES
    wire_body = gzip.compress(body) if compressed else body
    headers = {"Content-Encoding": "gzip"} if compressed else {}
    # No Content-Length: the limit must follow actual bytes, not trust headers.
    raw = HTTPResponse(body=io.BytesIO(wire_body), headers=headers, preload_content=False)
    response = requests.Response()
    response.status_code = 200
    response.raw = raw
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    with pytest.raises(OllamaResponseTooLargeError):
        OllamaSLM().list_models()
    assert raw.closed

@dataclass
class InventoryResponse:
    body: bytes = b'{"models": [{"name": "qwen3:4b"}]}'
    delay_at: str | None = None
    gate: threading.Event | None = None
    disconnect: bool = False

def test_http_dropped_connection_preserves_inventory_and_recovers(loopback_ollama):
    server = loopback_ollama
    server.start()
    healthy = ollama_report(server.url, [])
    assert healthy == {"ollamaStatus": "reachable", "models": ["qwen3:4b"]}
    server.reply(disconnect=True)
    adapter = OllamaSLM(base_url=server.url, timeout=1)
    with pytest.raises(OllamaUnavailableError) as error:
        adapter.list_models()
    assert isinstance(error.value.__cause__, requests.ConnectionError)
    report = ollama_report(server.url, healthy["models"])
    assert report == {"ollamaStatus": "unreachable", "models": ["qwen3:4b"]}
    server.reply()
    assert ollama_report(server.url, report["models"]) == healthy

@pytest.fixture
def loopback_ollama(monkeypatch):
    # Do not let workstation proxy settings route these probes off loopback.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    fixture = LoopbackOllama()
    try:
        yield fixture
    finally:
        fixture.close()
        assert all(request == ("GET", "/api/tags") for request in fixture.requests)

@pytest.mark.parametrize("delay_at", ["headers", "body"])
def test_http_timeout_preserves_inventory_and_recovers(loopback_ollama, delay_at):
    server = loopback_ollama
    server.start()
    healthy = ollama_report(server.url, [])
    assert healthy == {"ollamaStatus": "reachable", "models": ["qwen3:4b"]}
    server.reply(delay_at=delay_at)

    # Exercise exception translation with a short real socket timeout. Requests
    # wraps a timeout while reading a body as ConnectionError, not ReadTimeout.
    adapter = OllamaSLM(base_url=server.url, timeout=0.1)
    with pytest.raises(OllamaUnavailableError) as error:
        adapter.list_models()
    assert isinstance(error.value.__cause__, requests.RequestException)

    started = time.monotonic()
    report = ollama_report(server.url, healthy["models"])
    elapsed = time.monotonic() - started
    assert report == {"ollamaStatus": "unreachable", "models": ["qwen3:4b"]}
    # No mocked request or shortened bridge timeout: verify its actual 5s budget.
    assert 4.5 <= elapsed < 9
    server.response.gate.set()
    server.reply(b'{"models": [{"name": "gemma3:4b"}]}')
    assert ollama_report(server.url, report["models"]) == {
        "ollamaStatus": "reachable", "models": ["gemma3:4b"],
    }
    assert len(server.requests) == 4

@pytest.mark.parametrize(
    ("body", "exception"),
    [
        (b'{"models": [private-response', ModelError),
        (b'null', ModelError),
        (b'[]', ModelError),
        (b'{"models": null}', ModelError),
        (b'{"models": {"name": "qwen3:4b"}}', ModelError),
    ],
    ids=["invalid-json", "null-root", "array-root", "null-models", "object-models"],
)
def test_http_malformed_inventory_preserves_inventory_and_recovers(
    loopback_ollama, body, exception,
):
    server = loopback_ollama
    server.start()
    server.reply(body)
    with pytest.raises(exception):
        OllamaSLM(base_url=server.url).list_models()
    report = ollama_report(server.url, ["qwen3:4b"])
    assert report == {"ollamaStatus": "unreachable", "models": ["qwen3:4b"]}
    assert "private-response" not in json.dumps(report)
    assert server.url not in json.dumps(report)

    # Valid empty inventory is reachable, unlike a decoding failure. Successful
    # probes replace stale inventory even when no models are installed.
    server.reply(b'{"models": []}')
    recovered = ollama_report(server.url, report["models"])
    assert recovered == {"ollamaStatus": "reachable", "models": []}
    server.reply()
    assert ollama_report(server.url, recovered["models"]) == {
        "ollamaStatus": "reachable", "models": ["qwen3:4b"],
    }

class LoopbackOllama:
    """Only serves inventory; never invokes Ollama or a model download."""

    def __init__(self):
        self.response = InventoryResponse()
        self.requests = []
        self.gates = []
        self.thread = None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.requests.append(("GET", self.path))
                if self.path != "/api/tags":
                    self.send_error(404)
                    return
                response = fixture.response
                if response.disconnect:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection = True
                    return
                try:
                    if response.delay_at == "headers":
                        response.gate.wait(10)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response.body)))
                    self.end_headers()
                    if response.delay_at == "body":
                        self.wfile.flush()
                        response.gate.wait(10)
                    self.wfile.write(response.body)
                except (BrokenPipeError, ConnectionResetError):
                    # Expected when a timed-out client closes its socket.
                    pass

            def do_POST(self):
                fixture.requests.append(("POST", self.path))
                self.send_error(405)

            def log_message(self, format, *args):
                pass

        self.handler = Handler
        # Reserve an ephemeral port without listening: refusal is real and the
        # port cannot accidentally be claimed by another service.
        self.server = self._bind(0)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def _bind(self, port):
        server = ThreadingHTTPServer(
            ("127.0.0.1", port), self.handler, bind_and_activate=False
        )
        # Join handlers during teardown after releasing any delayed responses.
        server.daemon_threads = False
        server.server_bind()
        return server

    def start(self):
        self.server.server_activate()
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()

    def reply(self, body=None, *, delay_at=None, disconnect=False):
        gate = threading.Event() if delay_at else None
        if gate:
            self.gates.append(gate)
        self.response = InventoryResponse(
            body=body if body is not None else InventoryResponse().body,
            delay_at=delay_at, gate=gate, disconnect=disconnect,
        )

    def close(self):
        for gate in self.gates:
            gate.set()
        if self.thread:
            self.server.shutdown()
            self.thread.join(timeout=2)
            assert not self.thread.is_alive()
        self.server.server_close()
