"""Isolated contract tests with explicit model fixtures, not live SLM inference."""
import json
from pathlib import Path

import pytest

from langform.bridge_local import LocalBridge
from langform.bridge_urls import fetch_source_url, public_address


@pytest.fixture
def local(tmp_path, monkeypatch):
    sources = tmp_path / "approved"
    sources.mkdir()
    (sources / "notes.md").write_text("First paragraph.\n\nSecond paragraph.", encoding="utf-8")
    (sources / "other.md").write_text("Other project's source.", encoding="utf-8")
    bridge = LocalBridge(tmp_path / "private", [sources])
    execute = bridge.execute
    monkeypatch.setattr(bridge, "execute", lambda op, args: execute(op, {"context_model": "qwen3:4b", **args}))
    return bridge


def fixture_model(monkeypatch, bridge, response):
    calls = []
    monkeypatch.setattr(bridge, "select_model", lambda args: None)
    def generate(prompt, system=None):
        calls.append(prompt)
        return response
    monkeypatch.setattr(bridge.service.models.adapter, "generate", generate)
    return calls


def test_standardized_objective_still_goes_through_slm(local, monkeypatch):
    calls = fixture_model(monkeypatch, local, '{"intent":"processing","reason":"Selected local source"}')
    result = local.execute("classify_project_prompt", {
        "prompt": "Read the chosen file", "requested_intent": "processing", "source_keys": ["abc"]})
    assert result["intent"] == "processing"
    assert len(calls) == 1 and '"selected_file_count": 1' in calls[0]


@pytest.mark.parametrize("response", ["not JSON", '{"intent":"search","reason":"Internet"}', '{"intent":"chat"}'])
def test_invalid_classification_has_no_heuristic_fallback(local, monkeypatch, response):
    fixture_model(monkeypatch, local, response)
    with pytest.raises(ValueError):
        local.execute("classify_project_prompt", {"prompt": "process .md"})


def test_slm_cannot_silently_override_standardized_objective(local, monkeypatch):
    fixture_model(monkeypatch, local, '{"intent":"packaging","reason":"Question"}')
    with pytest.raises(ValueError):
        local.execute("classify_project_prompt", {"prompt": "Read sources", "requested_intent": "processing"})


def test_file_selection_registers_access_not_file_bytes(local):
    selected = local.execute("list_sources", {"_actor": "researcher"})["sources"][0]
    result = local.execute("resolve_project_sources", {"_actor": "researcher", "_project_scope": True,
        "prompt": "Process selected sources", "source_keys": [selected["id"]], "asset_ids": []})
    assert len(result["asset_ids"]) == 1
    assert "content" not in result["assets"][0]
    asset = local.service.assets.get(result["asset_ids"][0])
    assert Path(asset.location).read_text() in {"First paragraph.\n\nSecond paragraph.", "Other project's source."}


def test_unknown_grant_key_fails_without_registering_sources(local):
    with pytest.raises(PermissionError):
        local.execute("resolve_project_sources", {"_actor": "researcher",
            "prompt": "Read file", "source_keys": ["0" * 24]})
    assert not local.service.assets.list()


def test_extension_input_resolves_only_approved_matching_files(local):
    result = local.execute("resolve_project_sources", {"_actor": "researcher", "prompt": "Process .md files"})
    assert sorted(asset["name"] for asset in result["assets"]) == ["notes.md", "other.md"]


def test_missing_filename_does_not_silently_process_previous_scope(local):
    asset = local.register(next(path for path in local.sources().values() if path.name == "notes.md"))
    with pytest.raises(ValueError, match="named file"):
        local.execute("resolve_project_sources", {"_actor": "researcher", "asset_ids": [asset.asset_id],
            "prompt": "Process missing.md"})


def test_project_index_and_inspection_do_not_expand_into_other_projects(local):
    assets = [local.register(path) for path in local.sources().values()]
    for asset in assets:
        local.service.analyze_asset(asset.asset_id)
    args = {"_actor": "researcher", "_project_scope": True, "asset_ids": [assets[0].asset_id]}
    index = local.execute("frame_index", args)["frames"]
    assert index and {frame["asset_id"] for frame in index} == {assets[0].asset_id}
    foreign = local.service.list_frames(assets[1].asset_id)[0]
    with pytest.raises(PermissionError, match="project"):
        local.execute("inspect_frame", {**args, "frame_id": foreign.frame_id})
    assert len(local.execute("list_assets", args)["assets"]) == 2  # explicit configuration chooser


def test_packaging_requires_semantic_processing_not_structural_drafts(local, monkeypatch):
    asset = local.register(next(iter(local.sources().values())))
    local.service.analyze_asset(asset.asset_id)  # no model: explicitly structural draft
    fixture_model(monkeypatch, local, "Fixture response must not be used")
    with pytest.raises(ValueError, match="Context Processing"):
        local.execute("package_project_context", {"_actor": "researcher", "_project_scope": True,
            "asset_ids": [asset.asset_id], "prompt": "What is in the document?"})


def test_processed_source_summary_uses_slm_and_persists_metadata(local, monkeypatch):
    asset = local.register(next(iter(local.sources().values())))
    # Explicit semantic-result fixture isolates post-formation persistence.
    def formed(asset_id, args):
        local.service.analyze_asset(asset_id)
        frames = local.service.frames.list()
        for frame in frames:
            frame.model_id = "fixture:model"
        local.service.frames._save(frames)
        local.metrics.save({asset_id: {"formation_passes": 2}})
    monkeypatch.setattr(local, "analyze", formed)
    calls = fixture_model(monkeypatch, local, "Fixture source summary from Frame metadata.")
    result = local.execute("process_project_asset", {"_actor": "researcher", "_project_scope": True,
        "asset_id": asset.asset_id, "asset_ids": [asset.asset_id]})
    assert result["frames"] and result["formation_trace"]["formation_passes"] == 2
    assert result["asset"]["summary"] == "Fixture source summary from Frame metadata."
    assert '"context_frame_id"' in calls[0] and '"content":' not in calls[0]
    assert local.service.assets.get(asset.asset_id).summary == result["asset"]["summary"]
    assert local._processing_phase == "summarizing_source"
    combined = local.execute("summarize_project", {"_actor": "researcher", "_project_scope": True,
        "asset_ids": [asset.asset_id]})
    assert combined["frame_index"] and combined["reply"] == combined["summary"]


def test_explicit_url_is_registered_in_local_cache_without_following_links(local, monkeypatch):
    monkeypatch.setattr("langform.bridge_projects.fetch_source_url", lambda url: "Readable approved page.")
    url = "https://example.org/document"
    result = local.execute("resolve_project_sources", {"_actor": "researcher", "prompt": f"Process {url}"})
    asset = local.service.assets.get(result["asset_ids"][0])
    assert Path(asset.location).is_relative_to(local.imports)
    assert asset.name == url and local.source_urls.load()[asset.asset_id] == url
    assert Path(asset.location).read_text() == "Readable approved page."


@pytest.mark.parametrize("url", ["http://example.org", "https://user:password@example.org", "https://example.org:8080"])
def test_url_reader_rejects_unapproved_transport_and_credentials(url):
    with pytest.raises(ValueError):
        fetch_source_url(url)


def test_url_reader_rejects_private_hosts():
    with pytest.raises(ValueError):
        public_address("localhost")
