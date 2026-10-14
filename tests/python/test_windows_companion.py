import importlib.util
import json
from pathlib import Path
import sys

import pytest

SETUP = Path(__file__).parents[2] / "local-setup"
sys.path.insert(0, str(SETUP))
spec = importlib.util.spec_from_file_location("windows_companion", SETUP / "windows-companion.py")
companion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(companion)


def test_config_is_adjacent_to_executable_not_extraction_directory(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(SETUP / "LangFORM.exe"))
    assert companion.configuration_path() == SETUP / "langform-connection.json"


def test_server_config_and_explicit_override(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"server": "https://app.example/"}))
    assert companion.resolve_server(None, config) == "https://app.example"
    assert companion.resolve_server("https://other.example", config) == "https://other.example"
    for value in ["http://app.example", "https://name:password@app.example", "https://app.example/?token=x"]:
        config.write_text(json.dumps({"server": value}))
        with pytest.raises(ValueError):
            companion.resolve_server(None, config)


def configure(monkeypatch, tmp_path, *, settings=None, approval=True, folder=None):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(companion.launcher, "ask", lambda _: approval)
    monkeypatch.setattr(companion.launcher, "choose_folder", lambda: folder)
    monkeypatch.setattr(companion.launcher, "ollama_reachable", lambda: True)
    seen = []
    monkeypatch.setattr(companion, "bridge_main", lambda args: seen.append(args) or 0)
    if settings is not None:
        home = tmp_path / ".langform"
        home.mkdir()
        (home / "windows-companion-settings.json").write_text(json.dumps(settings))
    return seen


def test_declined_connection_never_pairs_or_creates_settings(monkeypatch, tmp_path):
    seen = configure(monkeypatch, tmp_path, approval=False)
    assert companion.main(["--server", "https://app.example"]) == 0
    assert not seen
    assert not (tmp_path / ".langform").exists()


def test_models_only_connection_calls_bundled_bridge_without_python_or_pip(monkeypatch, tmp_path):
    seen = configure(monkeypatch, tmp_path)
    monkeypatch.setattr(companion.subprocess, "Popen", lambda *a, **k: pytest.fail("Unexpected subprocess"))
    assert companion.main(["--server", "https://app.example"]) == 0
    assert "--allow" not in seen[0]
    assert "--open-browser" in seen[0]
    assert str(tmp_path / ".langform/companion-workspace") in seen[0]
    settings = json.loads((tmp_path / ".langform/windows-companion-settings.json").read_text())
    assert settings == {"server": "https://app.example", "folder": None}


def test_reuses_only_same_server_approved_folder(monkeypatch, tmp_path):
    folder = tmp_path / "approved"
    folder.mkdir()
    seen = configure(monkeypatch, tmp_path, settings={"server": "https://app.example", "folder": str(folder)})
    monkeypatch.setattr(companion.launcher, "ask", lambda _: pytest.fail("Unexpected approval"))
    monkeypatch.setattr(companion.launcher, "choose_folder", lambda: pytest.fail("Unexpected folder picker"))
    companion.main(["--server", "https://app.example", "--re-pair"])
    assert seen[0][-3:] == ["--allow", str(folder), "--re-pair"]


def test_change_folder_can_remove_grant(monkeypatch, tmp_path):
    seen = configure(monkeypatch, tmp_path, settings={"server": "https://app.example", "folder": str(tmp_path)})
    companion.main(["--server", "https://app.example", "--change-folder"])
    assert "--allow" not in seen[0]


def test_changed_server_does_not_inherit_old_folder(monkeypatch, tmp_path):
    seen = configure(monkeypatch, tmp_path, settings={"server": "https://old.example", "folder": str(tmp_path)})
    companion.main(["--server", "https://app.example"])
    assert "--allow" not in seen[0]


def test_invalid_saved_settings_fail_explicitly(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[]")
    with pytest.raises(ValueError):
        companion.read_settings(path)


def test_smoke_test_never_connects(monkeypatch):
    monkeypatch.setattr(companion, "smoke_test", lambda: 0)
    monkeypatch.setattr(companion, "resolve_server", lambda *args: pytest.fail("Unexpected server access"))
    monkeypatch.setattr(companion, "bridge_main", lambda *args: pytest.fail("Unexpected pairing"))
    assert companion.main(["--smoke-test"]) == 0
