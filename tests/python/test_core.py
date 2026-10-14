import json
from pathlib import Path

import pytest

from langform import ContextSubagent, LangFORM, ModelManager
from langform.frames import FrameBuilder
from langform.storage import JSONStore
from langform.retrieval import SimpleRetriever


def prepared(tmp_path: Path) -> tuple[ContextSubagent, str]:
    sample = tmp_path / "sample.md"
    sample.write_text(
        "# Retrieval\n\nContext Frames preserve original evidence.\n\n"
        "Retrieval selects relevant context for language models.", encoding="utf-8"
    )
    service = LangFORM(workspace=tmp_path / ".langform")
    asset = service.register_asset(str(sample))
    service.analyze_asset(asset.asset_id)
    return service, asset.asset_id


def configure_stub_model(service, monkeypatch, choice=None):
    service.settings.save({"selected_model_id": "qwen3:4b"})
    monkeypatch.setattr(service.models, "select", lambda model_id: model_id)

    def generate(prompt, system=None):
        if "Candidate frames:" in prompt:
            candidates = json.loads(prompt.split("Candidate frames:\n", 1)[1])
            request_id = prompt.split("Request ID: ", 1)[1].split("\n", 1)[0]
            return {"request_id": request_id, "selected_frames": choice if choice is not None else [
                {"context_frame_id": candidates[0]["context_frame_id"], "reason": "Direct source evidence.",
                 "include_mode": "full_frame", "priority": 1}
            ]}
        if "non-empty string field named summary" in prompt:
            return {"summary": "Retrieval selects Context Frames containing original evidence."}
        return {"ranges": [{"key": "root", "start": 1, "end": 2, "parentKey": None, "reason": "One coherent retrieval concept."}]}

    monkeypatch.setattr(service.models.adapter, "generate_json", generate)


def test_no_model_never_substitutes_keyword_results(tmp_path):
    service, asset_id = prepared(tmp_path)
    package = service.prepare_context("retrieval context")
    assert package.status == "model_required"
    assert package.frames == []
    assert service.get_package(package.package_id)["frames"] == []
    assert service.list_frames(asset_id)[0].provenance["formation_method"] == "structural_draft"
    assert not hasattr(service, "memory")
    assert not hasattr(service, "add_memory")


def test_original_evidence_and_persistence(tmp_path, monkeypatch):
    service, asset_id = prepared(tmp_path)
    configure_stub_model(service, monkeypatch)
    service.analyze_asset(asset_id)
    package = service.prepare_context("retrieval context")
    assert package.status == "context_ready"
    assert len(package.frames) == 1
    frame = package.frames[0]
    assert frame.content == (
        "Context Frames preserve original evidence.\n\n"
        "Retrieval selects relevant context for language models."
    )
    assert (frame.start_paragraph, frame.end_paragraph) == (1, 2)
    assert frame.selection_reason == "Direct source evidence."
    assert service.get_package(package.package_id)["frames"][0]["content"] == frame.content
    assert ContextSubagent(service.workspace).get_package(package.package_id)["status"] == "context_ready"


def test_revision_history_and_exact_parent_range(tmp_path, monkeypatch):
    service, asset_id = prepared(tmp_path)
    configure_stub_model(service, monkeypatch)
    service.analyze_asset(asset_id)
    parent = service.list_frames(asset_id)[0]
    children = service.refine_frame(parent.frame_id, "Researcher requested a boundary review.")
    assert children[0].content == parent.content
    assert children[0].revision_parent_frame_id == parent.frame_id
    assert children[0].parent_frame_id is None
    assert children[0].version == parent.version + 1
    assert not service.get_frame(parent.frame_id).is_current
    assert len(service.list_frames(asset_id, include_history=True)) == 3
    with pytest.raises(ValueError):
        service.refine_frame(parent.frame_id, "Try a stale parent")


def test_unlisted_model_selection_is_not_evidence(tmp_path, monkeypatch):
    service, _ = prepared(tmp_path)
    configure_stub_model(service, monkeypatch, [{"context_frame_id": "invented-id", "reason": "Unknown", "include_mode": "full_frame", "priority": 1}])
    package = service.prepare_context("retrieval context")
    assert package.status == "error"
    assert not package.frames


def test_explicit_empty_asset_scope(tmp_path):
    service, _ = prepared(tmp_path)
    package = service.prepare_context("retrieval context", asset_ids=[])
    assert package.status == "no_evidence"


def test_semantic_ranges_not_fixed_paragraph_count():
    text = "\n\n".join(f"Dataset description number {number}." for number in range(80))
    frames = FrameBuilder().build(
        "asset", text, "dataset.txt",
        planner=lambda paragraphs: [(1, len(paragraphs))],
        summarizer=lambda source, location: "One coherent dataset.",
        model_id="test-model",
    )
    assert len(frames) == 1
    assert frames[0].end_paragraph == 80
    assert frames[0].content == text


@pytest.mark.parametrize("ranges", [[(1, 1)], [(2, 2)], [(1, 3)],
    [{"key": "child", "start": 1, "end": 2, "parentKey": "missing"}]])
def test_invalid_model_boundaries_are_rejected(ranges):
    with pytest.raises(ValueError):
        FrameBuilder().build("asset", "First.\n\nSecond.", "source.txt", planner=lambda _: ranges)


def test_model_manager_checks_installed_catalog(monkeypatch):
    manager = ModelManager()
    monkeypatch.setattr(manager, "installed_models", lambda: [{"name": "qwen3:4b"}])
    assert manager.select("qwen3:4b") == "qwen3:4b"
    from langform.models import ModelError
    with pytest.raises(ModelError):
        manager.select("qwen3:1.7b")
    with pytest.raises(ModelError):
        manager.select("not-a-supported-model")


def test_corrupt_store_never_silently_resets(tmp_path):
    store = JSONStore(tmp_path / "registry.json", [])
    store.path.write_text("{bad json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        store.load()


def test_nested_frames_and_persistent_compact_index(tmp_path):
    from langform.frames import FrameStore
    frames = FrameBuilder().build("asset", "First.\n\nSecond.\n\nThird.", "source.txt",
        planner=lambda _: [
            {"key": "chapter", "start": 1, "end": 3, "parentKey": None},
            {"key": "detail", "start": 2, "end": 2, "parentKey": "chapter"},
        ], summarizer=lambda content, location: "Concise semantic description.", model_id="test")
    assert frames[1].parent_frame_id == frames[0].frame_id
    assert frames[1].depth_level == 1
    assert frames[0].content == "First.\n\nSecond.\n\nThird."
    store = FrameStore(tmp_path)
    store.replace_for_asset("asset", frames)
    entries = FrameStore(tmp_path).index()
    assert entries[0]["child_frame_ids"] == [frames[1].frame_id]
    assert entries[1]["ancestor_frame_ids"] == [frames[0].frame_id]
    assert all("content" not in entry and "original_content" not in entry for entry in entries)


def test_changed_source_never_returns_stale_evidence(tmp_path, monkeypatch):
    service, asset_id = prepared(tmp_path)
    configure_stub_model(service, monkeypatch)
    service.analyze_asset(asset_id)
    Path(service.assets.get(asset_id).location).write_text("Changed source.", encoding="utf-8")
    package = service.prepare_context("retrieval context")
    assert package.status == "error"
    assert package.frames == []


def test_parent_child_package_avoids_duplicate_evidence(tmp_path, monkeypatch):
    service, asset_id = prepared(tmp_path)
    frames = FrameBuilder().build(asset_id,
        "Context Frames preserve original evidence.\n\nRetrieval selects relevant context for language models.",
        service.assets.get(asset_id).location,
        planner=lambda _: [
            {"key": "parent", "start": 1, "end": 2, "parentKey": None},
            {"key": "child", "start": 2, "end": 2, "parentKey": "parent"},
        ], summarizer=lambda content, location: "Retrieval context.", model_id="test")
    service.frames.replace_for_asset(asset_id, frames)
    configure_stub_model(service, monkeypatch, [
        {"context_frame_id": frames[0].frame_id, "include_mode": "parent_frame", "priority": 1},
        {"context_frame_id": frames[1].frame_id, "include_mode": "child_frame", "priority": 2},
    ])
    package = service.prepare_context("retrieval")
    assert package.status == "context_ready"
    assert package.frames[0].content == frames[0].content
    assert package.frames[1].content == ""
    assert package.frames[1].duplicate_of_frame_id == frames[0].frame_id


def test_candidate_budget_keeps_broad_parent_available():
    frames = FrameBuilder().build(
        "asset", "Overview.\n\nSpecific retrieval details.", "sample.txt",
        planner=lambda _: [
            {"key": "parent", "start": 1, "end": 2, "parentKey": None},
            {"key": "child", "start": 2, "end": 2, "parentKey": "parent"},
        ], summarizer=lambda content, location: content, model_id="test",
    )
    candidates = SimpleRetriever().retrieve("specific retrieval details", frames, top_k=1)
    assert [frame.frame_id for frame in candidates] == [frames[0].frame_id]
