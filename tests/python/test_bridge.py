from pathlib import Path
import pytest
from langform.bridge_local import LocalBridge
from langform.bridge import Transport


def setup_bridge(tmp_path):
    sources = tmp_path / "approved"
    sources.mkdir()
    source = sources / "notes.md"
    source.write_text("# Evidence\n\nFirst exact paragraph.\n\nSecond exact paragraph.\n\nThird exact paragraph.", encoding="utf8")
    bridge = LocalBridge(tmp_path / "private-workspace", [sources])
    asset = bridge.register(source)
    bridge.service.analyze_asset(asset.asset_id)  # Honest structural draft, no model.
    args = {"_actor": "researcher", "asset_ids": [asset.asset_id], "context_model": "qwen3:4b"}
    return bridge, asset, args


def test_grants_exclude_unapproved_sources_symlinks_and_private_workspace(tmp_path):
    bridge, asset, args = setup_bridge(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("not approved")
    (bridge.grants[0] / "link.txt").symlink_to(outside)
    (bridge.grants[0] / ".env.json").write_text('{"secret":true}')
    assert not bridge.approved(outside)
    assert not bridge.approved(bridge.grants[0] / ".env.json")
    assert bridge.workspace.stat().st_mode & 0o777 == 0o700
    assert not bridge.approved(bridge.workspace / "bridge" / "device.json")
    assert [source["name"] for source in bridge.execute("list_sources", args)["sources"]] == ["notes.md"]
    with pytest.raises(PermissionError):
        bridge.register(outside)


def test_main_agent_cannot_discover_or_read_unscoped_assets(tmp_path):
    bridge, asset, _ = setup_bridge(tmp_path)
    args = {"_actor": "main_agent", "asset_ids": []}
    assert bridge.execute("list_assets", args)["assets"] == []
    assert bridge.execute("frame_index", args)["frames"] == []
    with pytest.raises(PermissionError):
        bridge.execute("inspect_frame", {**args, "frame_id": bridge.service.list_frames(asset.asset_id)[0].frame_id})
    with pytest.raises(PermissionError):
        bridge.execute("list_sources", args)


def test_metadata_edit_is_revision_not_evidence_rewrite_and_lock_prevents_rebuild(tmp_path):
    bridge, asset, args = setup_bridge(tmp_path)
    old = bridge.service.list_frames(asset.asset_id)[0]
    edited = bridge.execute("edit_frame", {**args, "frame_id": old.frame_id, "summary": "Researcher label.", "importance": "high"})["frame"]
    assert edited["content"] == old.content
    assert edited["revision_parent_frame_id"] == old.frame_id
    assert edited["provenance"]["research_override"] is True
    assert bridge.service.get_frame(old.frame_id).is_current is False
    locked = bridge.execute("lock_frame", {**args, "frame_id": edited["frame_id"], "locked": True})["frame"]
    index = bridge.execute("frame_index", args)["frames"]
    assert index[0]["locked"] is True
    with pytest.raises(ValueError, match="Unlock"):
        bridge.service.frames.replace_for_asset(asset.asset_id, [])
    bridge.execute("lock_frame", {**args, "frame_id": locked["frame_id"], "locked": False})
    assert bridge.execute("frame_index", args)["frames"][0]["locked"] is False


def test_manual_split_merge_preserves_exact_paragraphs(tmp_path):
    bridge, asset, args = setup_bridge(tmp_path)
    original = bridge.service.list_frames(asset.asset_id)[0]
    bridge.execute("split_frame", {**args, "frame_id": original.frame_id, "split_at": 1})
    leaves = [frame for frame in bridge.service.list_frames(asset.asset_id) if not frame.child_frame_ids]
    assert len(leaves) == 2
    for leaf in leaves:
        assert leaf.coordinates() == {"type": "paragraph", "start_paragraph": leaf.start_paragraph,
                                      "end_paragraph": leaf.end_paragraph}
        assert leaf.source_version == original.source_version
        assert bridge.service._resolve_frame(leaf).content == leaf.content
    merged = bridge.execute("merge_frames", {**args, "frame_ids": [frame.frame_id for frame in leaves]})["frames"][0]
    assert merged["content"] == original.content
    assert (merged["start_paragraph"], merged["end_paragraph"]) == (1, 3)
    assert merged["source_coordinates"] == original.coordinates()
    assert merged["source_version"] == original.source_version
    reloaded = bridge.service.get_frame(merged["frame_id"])
    assert bridge.service._resolve_frame(reloaded).content == original.content
    assert reloaded.index_entry()["research_override"] is True


def test_baseline_and_long_context_are_separate_from_semantic_frames(tmp_path):
    bridge, asset, args = setup_bridge(tmp_path)
    before = bridge.service.list_frame_index()
    common = {**args, "_actor": "main_agent", "query": "exact paragraph"}
    baseline = bridge.execute("baseline_context", common)
    assert baseline["model_usage"] == []
    assert "not vector RAG" in baseline["baseline_method"]
    assert baseline["package"]["frames"][0]["formation_method"] == "baseline_context"
    long_context = bridge.execute("long_context", common)
    assert "First exact paragraph." in long_context["package"]["frames"][0]["content"]
    assert bridge.service.list_frame_index() == before


def test_bridge_transport_requires_secure_origin_without_embedded_credentials():
    for server in ["http://example.com", "https://user:password@example.com", "https://example.com/?token=bad"]:
        with pytest.raises(ValueError):
            Transport(server)
    assert Transport("http://127.0.0.1:8080").server == "http://127.0.0.1:8080"
