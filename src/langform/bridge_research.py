"""Explicit researcher overrides, preserving original evidence and revision history."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from .schemas import ContextFrame


def research_edit(bridge, operation: str, args: dict) -> dict:
    ids = args.get("frame_ids", []) if operation == "merge_frames" else [args.get("frame_id")]
    if not isinstance(ids, list) or not 1 <= len(ids) <= 20 or len(set(ids)) != len(ids):
        raise ValueError("Select 1–20 distinct Frame IDs.")
    frames = [bridge.frame(frame_id, args) for frame_id in ids]
    if any(not frame.is_current for frame in frames):
        raise ValueError("Research edits require current Frames.")
    if operation != "lock_frame" and any(frame.provenance.get("locked") for frame in frames):
        raise PermissionError("Unlock selected Frames before editing them.")
    if operation in {"split_frame", "merge_frames"}:
        if any(frame.coordinates()["type"] != "paragraph" for frame in frames):
            raise ValueError("Manual split/merge currently supports paragraph ranges only; native-coordinate edits must use the appropriate source adapter.")
        return edit_ranges(bridge, operation, args, frames)
    original = frames[0]
    current = ContextFrame.from_dict(original.to_dict())
    current.frame_id = f"frame_{uuid.uuid4().hex[:12]}"
    current.version += 1
    current.provenance["research_edited_at"] = datetime.now(timezone.utc).isoformat()
    current.revision_parent_frame_id = original.frame_id
    current.provenance = {**original.provenance, "research_override": True, "edit_origin": "researcher"}
    if operation == "lock_frame":
        if type(args.get("locked")) is not bool:
            raise ValueError("Lock state must be a boolean.")
        current.provenance["locked"] = args["locked"]
        current.revision_note = "Researcher changed experiment lock state."
    else:
        summary = args.get("summary", original.summary)
        topics = args.get("topics", original.topics)
        importance = args.get("importance", original.importance)
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 1200:
            raise ValueError("Summary must be 1–1200 characters.")
        if not isinstance(topics, list) or len(topics) > 16 or any(not isinstance(topic, str) or len(topic) > 80 for topic in topics):
            raise ValueError("Topics must be up to sixteen short labels.")
        if importance not in {"high", "normal", "low"}:
            raise ValueError("Importance must be high, normal, or low.")
        current.summary, current.topics, current.importance = summary.strip(), topics, importance
        current.revision_note = "Researcher metadata override; original evidence unchanged."
    saved = bridge.service.frames.list()
    for frame in saved:
        if frame.frame_id == original.frame_id:
            frame.is_current = False
        if frame.is_current and frame.parent_frame_id == original.frame_id:
            frame.parent_frame_id = current.frame_id
    saved.append(current)
    bridge.service.frames._save(saved)
    asset = bridge.service.assets.get(original.source_id)
    asset.frame_ids = [frame.frame_id for frame in bridge.service.frames.current_for_asset(asset.asset_id)]
    bridge.service.assets.save_asset(asset)
    return {"frame": bridge.service.get_frame(current.frame_id).to_dict(), "edit_origin": "researcher"}


def edit_ranges(bridge, operation: str, args: dict, frames: list[ContextFrame]) -> dict:
    parent = frames[0]
    for frame in frames:
        bridge.service._resolve_frame(frame)  # Reject any changed source.
    if operation == "split_frame":
        split = args.get("split_at")
        if type(split) is not int or not parent.start_paragraph <= split < parent.end_paragraph:
            raise ValueError("Split after a paragraph inside this Frame.")
        text = parent.content
        ranges = [
            {"key": "root", "start": parent.start_paragraph, "end": parent.end_paragraph, "parentKey": None},
            {"key": "left", "start": parent.start_paragraph, "end": split, "parentKey": "root"},
            {"key": "right", "start": split + 1, "end": parent.end_paragraph, "parentKey": "root"},
        ]
        built = bridge.service.frame_builder.build(parent.source_id, text, parent.provenance.get("source", ""),
            planner=lambda _: ranges, summarizer=lambda content, location: parent.summary,
            start_paragraph=parent.start_paragraph, initial_location=parent.structural_location, model_id="researcher_override")
        for frame in built:
            frame.source_coordinates = frame.coordinates()
            frame.source_version = parent.source_version
            frame.provenance.update({**parent.provenance, "research_override": True, "edit_origin": "researcher"})
        bridge.service.frames.refine(parent.frame_id, built, "Researcher split; original evidence unchanged.")
    else:
        if len(frames) < 2 or any(frame.source_id != parent.source_id or frame.parent_frame_id != parent.parent_frame_id for frame in frames):
            raise ValueError("Merge at least two sibling Frames from the same Asset.")
        if any(frame.child_frame_ids for frame in frames):
            raise ValueError("Merge leaf siblings only; preserve their parent hierarchy.")
        start, end = min(frame.start_paragraph for frame in frames), max(frame.end_paragraph for frame in frames)
        snapshot = bridge.service.workspace / "sources" / f"{parent.source_id}.json"
        import json
        source = json.loads(snapshot.read_text(encoding="utf-8"))
        paragraphs = source["paragraphs"]
        content = "\n\n".join(item["text"] for item in paragraphs if start <= item["sequence"] <= end)
        summary = args.get("summary") or parent.summary
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 1200:
            raise ValueError("Summary must be 1–1200 characters.")
        merged = ContextFrame.from_dict(parent.to_dict())
        merged.frame_id = f"frame_{uuid.uuid4().hex[:12]}"
        merged.content, merged.summary = content, summary
        merged.start_paragraph, merged.end_paragraph = start, end
        merged.source_coordinates = {"type": "paragraph", "start_paragraph": start, "end_paragraph": end}
        merged.version += 1
        merged.provenance["research_edited_at"] = datetime.now(timezone.utc).isoformat()
        merged.revision_parent_frame_id = parent.frame_id
        merged.provenance = {**parent.provenance, "research_override": True,
            "merged_frame_ids": [frame.frame_id for frame in frames], "edit_origin": "researcher"}
        merged.revision_note = "Researcher merged leaf siblings; includes exact intervening paragraphs."
        merged.model_id = "researcher_override"
        saved = bridge.service.frames.list()
        retired = {frame.frame_id for frame in frames}
        semantic_parent = next((frame for frame in saved if frame.frame_id == parent.parent_frame_id), None)
        if semantic_parent and (start, end) == (semantic_parent.start_paragraph, semantic_parent.end_paragraph):
            # A merged range equal to its parent replaces that parent; it must
            # not become an invalid equal-range semantic child.
            retired.add(semantic_parent.frame_id)
            merged.parent_frame_id = semantic_parent.parent_frame_id
            merged.depth_level = semantic_parent.depth_level
            merged.revision_parent_frame_id = semantic_parent.frame_id
            merged.version = semantic_parent.version + 1
            for frame in saved:
                if frame.is_current and frame.parent_frame_id == semantic_parent.frame_id and frame.frame_id not in retired:
                    frame.parent_frame_id = merged.frame_id
        for frame in saved:
            if frame.frame_id in retired:
                frame.is_current = False
        saved.append(merged)
        bridge.service.frames._save(saved)
        built = [merged]
    asset = bridge.service.assets.get(parent.source_id)
    asset.frame_ids = [frame.frame_id for frame in bridge.service.frames.current_for_asset(parent.source_id)]
    bridge.service.assets.save_asset(asset)
    return {"frames": [frame.to_dict() for frame in built], "edit_origin": "researcher"}
