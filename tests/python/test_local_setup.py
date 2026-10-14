import base64
import importlib.util
import json
from pathlib import Path
import zlib

import pytest
from langform.bridge import pairing_url
from langform.bridge_local import LocalBridge

spec = importlib.util.spec_from_file_location("local_setup", Path(__file__).parents[2] / "local-setup/launcher.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def payload(files):
    return base64.b64encode(zlib.compress(json.dumps(files).encode())).decode()


def test_setup_origin_rejects_insecure_or_credential_bearing_addresses():
    assert setup.validate_server("https://app.example/") == "https://app.example"
    assert setup.validate_server("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    for url in ["http://app.example", "https://user:secret@app.example", "https://app.example/?token=value",
                "https://app.example/#token", "https://app.example/path", "file:///tmp/app"]:
        with pytest.raises(ValueError):
            setup.validate_server(url)


def test_bundle_unpack_stays_inside_destination(tmp_path):
    setup.unpack_package(tmp_path, payload({"src/langform/example.py": "pass\n"}))
    assert (tmp_path / "src/langform/example.py").read_text() == "pass\n"
    for name in ["../outside.py", "/outside.py", "..\\outside.py"]:
        with pytest.raises(ValueError):
            setup.unpack_package(tmp_path, payload({name: "not permitted"}))


def test_connect_without_grants_never_discovers_local_files(tmp_path):
    source = tmp_path / "private-notes.txt"
    source.write_text("No permission to read this")
    bridge = LocalBridge(tmp_path / "workspace", [])
    assert not bridge.approved(source)
    assert bridge.execute("list_sources", {"_actor": "researcher"})["sources"] == []
    with pytest.raises(PermissionError):
        bridge.register(source)


def test_browser_pairing_code_is_only_a_fragment():
    assert pairing_url("https://app.example", "abcdef123456") == "https://app.example/connections#pair=abcdef123456"
    assert pairing_url("https://app.example") == "https://app.example/connections"


def test_cancel_setup_does_not_write_or_install(monkeypatch, tmp_path):
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(setup, "APP_SERVER", "https://app.example")
    monkeypatch.setattr(setup, "ask", lambda _question: False)
    monkeypatch.setattr(setup, "unpack_package", lambda *_: pytest.fail("Cancelled setup wrote package files"))
    monkeypatch.setattr(setup.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("Cancelled setup installed packages"))
    assert setup.main() == 0


def test_reconnect_reuses_approved_setup_without_installation(monkeypatch, tmp_path):
    import hashlib
    home = tmp_path / ".langform"
    python = home / "companion-python" / ("Scripts/python.exe" if setup.os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    settings = {"server": "https://app.example", "packageHash": hashlib.sha256(setup.PACKAGE.encode()).hexdigest(), "folder": None}
    (home / "companion-settings.json").write_text(json.dumps(settings))
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(setup, "APP_SERVER", settings["server"])
    monkeypatch.setattr(setup, "ollama_reachable", lambda: True)
    monkeypatch.setattr(setup, "ask", lambda *_: pytest.fail("Unchanged approved setup asked for installation"))
    monkeypatch.setattr(setup, "choose_folder", lambda: pytest.fail("Reconnect changed existing folder approval"))
    monkeypatch.setattr(setup, "unpack_package", lambda *_: pytest.fail("Reconnect wrote source"))
    monkeypatch.setattr(setup.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("Reconnect reinstalled packages"))
    commands = []
    monkeypatch.setattr(setup.subprocess, "call", lambda args: commands.append(args) or 0)
    assert setup.main() == 0
    assert "--open-browser" in commands[0]
    assert "--allow" not in commands[0]


def test_launcher_reopens_unfinished_pairing_without_new_device(monkeypatch, tmp_path):
    import types
    import langform.bridge as cli
    from langform.storage import JSONStore
    workspace = tmp_path / "private"
    store = JSONStore(workspace / "bridge/device.json", {})
    store.save({"server": "https://app.example", "deviceToken": "fixture-not-a-real-token",
                "bridgeId": "fixture-device", "pairingCode": "abcdef123456"})
    browser_urls = []

    class FakeTransport:
        def __init__(self, server):
            self.server, self.token = server, None

        def call(self, path, body=None):
            if path == "heartbeat":
                assert body["supportedObjectives"] == ["processing", "packaging"]
                return {"paired": False}
            if path == "register":
                pytest.fail("An unfinished valid pairing should not create another device")
            if path == "jobs":
                raise KeyboardInterrupt()
            pytest.fail(f"Unexpected operation: {path}")

    monkeypatch.setattr(cli, "Transport", FakeTransport)
    monkeypatch.setattr(cli, "ollama_report", lambda *_: {"models": [], "ollamaStatus": "reachable"})
    monkeypatch.setattr(cli.threading, "Thread", lambda **_: types.SimpleNamespace(start=lambda: None))
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: browser_urls.append(url) or True)
    assert cli.main(["--server", "https://app.example", "--workspace", str(workspace), "--open-browser"]) == 0
    assert browser_urls == ["https://app.example/connections#pair=abcdef123456"]
    assert store.load()["bridgeId"] == "fixture-device"
