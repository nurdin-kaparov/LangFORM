import re
from langform.core import ContextSubagent


def test_coarse_navigation_and_frame_selection_use_metadata_before_exact_evidence(tmp_path, monkeypatch):
    service = ContextSubagent(tmp_path / "workspace")
    assets = []
    for name in ["irrelevant", "target"]:
        path = tmp_path / f"{name}.md"
        path.write_text(f"# {name}\n\nExact {name} evidence.")
        asset = service.register_asset(str(path))
        service.analyze_asset(asset.asset_id)
        assets.append(asset)
    target = service.list_frames(assets[1].asset_id)[0]
    config = service.settings.load()
    config.update({"selected_model_id": "qwen3:4b", "preferred_candidate_frames": 1,
                   "soft_max_candidate_frames": 1, "hard_max_candidate_frames": 2})
    service.settings.save(config)
    monkeypatch.setattr(service.models, "select", lambda model: None)
    def respond(prompt, system):
        if "Asset metadata:" in prompt:
            assert '"content":' not in prompt
            return {"request_id": re.search(r"Request ID: ([^\n]+)", prompt)[1],
                    "selected_asset_ids": [assets[1].asset_id]}
        return {"request_id": service.last_selection_trace["request_id"], "selected_frames": [
            {"context_frame_id": target.frame_id, "include_mode": "full_frame", "priority": 1}
        ]}
    monkeypatch.setattr(service.models.adapter, "generate_json", respond)
    package = service.prepare_context("target", asset_ids=[asset.asset_id for asset in assets])
    assert package.status == "context_ready"
    assert package.frames[0].source_id == assets[1].asset_id
    assert package.frames[0].content == target.content
    assert len(service.asset_selection_traces) == 1
