from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Callable

from .schemas import ContextFrame
from .storage import JSONStore
from .coordinates import grid_coordinates, resolve_spreadsheet, validate_grid_ranges


_WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def tokenize(text: str) -> list[str]:
    return [match.group(0).casefold() for match in _WORD_RE.finditer(text)]


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    stop_words = {
        "the", "and", "for", "that", "with", "this", "from", "are", "was",
        "were", "have", "has", "had", "not", "but", "you", "your", "into",
        "about", "which", "will", "would", "can", "could", "should", "their",
        "they", "them", "then", "than", "its", "our", "out", "all", "any",
        "use", "using", "used", "when", "where", "what", "how", "why", "who",
        "also", "more", "most", "such", "only", "each", "other", "some",
        "been", "being", "between", "through", "over", "under", "after",
        "before", "same",
    }
    counts: dict[str, int] = {}
    for word in tokenize(text):
        if len(word) < 3 or word in stop_words:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [
        word
        for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
            :limit
        ]
    ]


def summarize(text: str, max_chars: int = 280) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    clipped = clean[:max_chars].rsplit(" ", 1)[0]
    return clipped + "..."


def _parse_paragraphs(
    text: str, initial_location: str | None = None
) -> list[tuple[int, str, str]]:
    sections: list[tuple[int, str, str]] = []
    heading_stack: list[tuple[int, str]] = []
    if initial_location and initial_location != "Document":
        heading_stack = [(1, part) for part in initial_location.split(" / ")]
    buffer: list[str] = []

    def flush() -> None:
        content = "\n".join(buffer).strip()
        if content:
            location = " / ".join(title for _, title in heading_stack) or "Document"
            sections.append((len(sections) + 1, content, location))
        buffer.clear()

    for line in text.splitlines():
        stripped = line.strip()
        match = _HEADING_RE.match(stripped)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip().rstrip(":")
            heading_stack = [item for item in heading_stack if item[0] < level]
            heading_stack.append((level, title))
        elif re.match(r"^(?:[-*•]|\d+[.)])\s+", stripped):
            flush()
            buffer.append(line.rstrip())
            flush()
        elif not stripped:
            flush()
        else:
            buffer.append(line.rstrip())
    flush()

    if not sections and text.strip():
        location = initial_location or "Document"
        sections.append((1, text.strip(), location))
    return sections


def _cohesion(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class FrameStore:
    """JSON persistence with append-only frame revisions."""

    def __init__(self, workspace: str | Path):
        self.store = JSONStore(Path(workspace) / "frames" / "frames.json", [])
        self.index_store = JSONStore(Path(workspace) / "frames" / "frame-index.json", [])

    def _save(self, frames: list[ContextFrame]) -> None:
        for frame in frames:
            related = [item for item in frames if item.source_id == frame.source_id and item.is_current == frame.is_current]
            by_id = {item.frame_id: item for item in related}
            frame.child_frame_ids = [item.frame_id for item in related if item.parent_frame_id == frame.frame_id]
            frame.sibling_frame_ids = [item.frame_id for item in related if item.frame_id != frame.frame_id and item.parent_frame_id == frame.parent_frame_id]
            frame.ancestor_frame_ids = []
            parent = by_id.get(frame.parent_frame_id)
            while parent and parent.frame_id not in frame.ancestor_frame_ids:
                frame.ancestor_frame_ids.append(parent.frame_id)
                parent = by_id.get(parent.parent_frame_id)
        self.store.save([frame.to_dict() for frame in frames])
        self.index_store.save([frame.index_entry() for frame in frames])

    def index(self, include_history: bool = False) -> list[dict]:
        if not self.index_store.path.exists() and self.store.path.exists():
            self._save(self.list())
        entries = self.index_store.load()
        return entries if include_history else [entry for entry in entries if entry.get("is_current", True)]

    def list(self, include_history: bool = True) -> list[ContextFrame]:
        frames = [ContextFrame.from_dict(item) for item in self.store.load()]
        return frames if include_history else [frame for frame in frames if frame.is_current]

    def get(self, frame_id: str) -> ContextFrame:
        for frame in self.list():
            if frame.frame_id == frame_id:
                return frame
        raise KeyError(f"Context Frame not found: {frame_id}")

    def current_for_asset(self, asset_id: str) -> list[ContextFrame]:
        return [
            frame
            for frame in self.list(include_history=False)
            if frame.source_id == asset_id
        ]

    def replace_for_asset(
        self, asset_id: str, frames: list[ContextFrame], revision_note: str | None = None
    ) -> None:
        all_frames = self.list()
        current = [
            frame for frame in all_frames if frame.source_id == asset_id and frame.is_current
        ]
        if any(frame.provenance.get("locked") for frame in current):
            raise ValueError("Unlock research Frames before rebuilding this Asset.")
        for old in current:
            old.is_current = False
        for new_frame in frames:
            parent = next(
                (
                    old
                    for old in current
                    if old.start_paragraph == new_frame.start_paragraph
                    and old.end_paragraph == new_frame.end_paragraph
                    and old.coordinates() == new_frame.coordinates()
                ),
                None,
            )
            new_frame.version = parent.version + 1 if parent else 1
            new_frame.revision_parent_frame_id = parent.frame_id if parent else None
            new_frame.revision_note = revision_note
        self._save(all_frames + frames)

    def refine(self, parent_id: str, frames: list[ContextFrame], note: str) -> None:
        all_frames = self.list()
        parent = next((frame for frame in all_frames if frame.frame_id == parent_id), None)
        if parent is None:
            raise KeyError(f"Context Frame not found: {parent_id}")
        if not parent.is_current:
            raise ValueError("Only a current Context Frame can be refined.")
        retired = {parent.frame_id}
        while True:
            descendants = {item.frame_id for item in all_frames if item.is_current and item.parent_frame_id in retired}
            if descendants.issubset(retired):
                break
            retired.update(descendants)
        if any(item.frame_id in retired and item.provenance.get("locked") for item in all_frames):
            raise ValueError("Unlock the Frame and its locked descendants before refinement.")
        for item in all_frames:
            if item.frame_id in retired:
                item.is_current = False
        root = next((item for item in frames if item.coordinates() == parent.coordinates()), None)
        if root is None:
            root = ContextFrame.from_dict(parent.to_dict())
            root.frame_id = f"frame_{uuid.uuid4().hex[:12]}"
            root.depth_level = 0
            frames.insert(0, root)
            for item in frames[1:]:
                if item.parent_frame_id is None:
                    item.parent_frame_id = root.frame_id
                item.depth_level += 1
        root.parent_frame_id = parent.parent_frame_id
        for frame in frames:
            frame.source_id = parent.source_id
            previous = next((item for item in all_frames if item.frame_id in retired and item.coordinates() == frame.coordinates()), None)
            frame.version = previous.version + 1 if previous else 1
            frame.is_current = True
            frame.revision_parent_frame_id = previous.frame_id if previous else None
            frame.depth_level += parent.depth_level
            frame.revision_note = note
        self._save(all_frames + frames)


class FrameBuilder:
    """Materializes semantic ranges; transport batching never defines frame depth."""

    def build_spreadsheet(self, asset_id: str, source: dict, source_location: str, *,
                          model_id=None, summarizer=None, planner=None, scope=None) -> list[ContextFrame]:
        if planner:
            ranges = planner(source, scope)
        else:
            ranges = [{"key": str(i), "parentKey": None, "coordinates": grid_coordinates(source, grid),
                       "reason": "Explicit worksheet structural draft.", "frameType": "table"}
                      for i, grid in enumerate(source["grids"]) if grid["rows"] and grid["columns"]
                      and (scope is None or grid["sheet"] == scope["sheet"])]
        ranges = validate_grid_ranges(source, ranges, scope)
        ids = {item["key"]: f"frame_{uuid.uuid4().hex[:12]}" for item in ranges}
        result = []
        for item in ranges:
            c = item["coordinates"]
            content = resolve_spreadsheet(source, c, source["version"])
            location = f'{c["sheet"] or Path(source_location).name} / {c["column_ids"][0]}{c["start_row"]}:{c["column_ids"][-1]}{c["end_row"]}'
            summary = summarizer(content, location).strip() if summarizer else summarize(content)
            if not summary:
                raise ValueError("A Context Frame summary cannot be empty.")
            keywords = extract_keywords(content)
            result.append(ContextFrame(
                frame_id=ids[item["key"]], source_id=asset_id, content=content, summary=summary,
                section=location, structural_location=location, source_coordinates=c, source_version=source["version"],
                start_paragraph=c["start_row"], end_paragraph=c["end_row"], model_id=model_id,
                parent_frame_id=ids.get(item.get("parentKey")), depth_level=item["depth"],
                frame_type=item.get("frameType", "table_range"), importance=item.get("importance", "normal"),
                topics=keywords[:8], keywords=keywords,
                provenance={"source": source_location, "source_coordinates": c, "source_version": source["version"],
                            "formation_method": "semantic_model" if planner else "structural_draft",
                            "formation_passes": 2 if planner else 0, "depth_reason": item["reason"]},
            ))
        return result

    def build(
        self,
        asset_id: str,
        text: str,
        source_location: str,
        *,
        model_id: str | None = None,
        summarizer: Callable[[str, str], str] | None = None,
        planner: Callable[[list[tuple[int, str, str]]], list] | None = None,
        start_paragraph: int = 1,
        initial_location: str | None = None,
    ) -> list[ContextFrame]:
        parsed = _parse_paragraphs(text, initial_location)
        if not parsed:
            return []
        groups: list[list[tuple[int, str, str]]] = []
        current: list[tuple[int, str, str]] = []
        current_size = 0
        current_terms: set[str] = set()

        def flush() -> None:
            nonlocal current, current_size, current_terms
            if current:
                groups.append(current)
            current = []
            current_size = 0
            current_terms = set()

        if planner:
            ranges = planner(parsed)
            ranges = validate_ranges(ranges, len(parsed))
            groups = [parsed[item["start"] - 1:item["end"]] for item in ranges]
        else:
            # Explicit structural drafts when no local model is configured.
            # No fixed row, token, line, or paragraph count determines depth.
            for paragraph in parsed:
                if current and current[-1][2] != paragraph[2]:
                    flush()
                current.append(paragraph)
            flush()
            ranges = [{"key": str(index), "parentKey": None, "depth": 0} for index in range(len(groups))]

        result: list[ContextFrame] = []
        ids = {item["key"]: f"frame_{uuid.uuid4().hex[:12]}" for item in ranges}
        for group, metadata in zip(groups, ranges):
            source_content = "\n\n".join(item[1] for item in group).strip()
            location = group[0][2]
            summary = (
                summarizer(source_content, location).strip()
                if summarizer
                else summarize(source_content)
            )
            if not summary:
                raise ValueError("A Context Frame summary cannot be empty.")
            start = start_paragraph + group[0][0] - 1
            end = start_paragraph + group[-1][0] - 1
            keywords = extract_keywords(source_content)
            result.append(
                ContextFrame(
                    frame_id=ids[metadata["key"]],
                    source_id=asset_id,
                    content=source_content,
                    summary=summary,
                    section=location,
                    topics=keywords[:8],
                    keywords=keywords,
                    provenance={
                        "source": source_location,
                        "structural_location": location,
                        "start_paragraph": start,
                        "end_paragraph": end,
                        "summary_method": "local_model" if summarizer else "extractive",
                        "formation_method": "semantic_model" if planner else "structural_draft",
                        "formation_passes": 2 if planner else 0,
                        "depth_reason": metadata.get("reason"),
                    },
                    start_paragraph=start,
                    end_paragraph=end,
                    structural_location=location,
                    model_id=model_id if summarizer else None,
                    parent_frame_id=ids.get(metadata.get("parentKey")),
                    depth_level=metadata.get("depth", 0),
                    frame_type=metadata.get("frameType", "semantic_range"),
                    importance=metadata.get("importance", "normal"),
                )
            )
        return result


def validate_ranges(ranges: list, paragraph_count: int) -> list[dict]:
    """Validate coverage and parent containment, without requiring disjoint ranges."""
    normalized = []
    for index, item in enumerate(ranges):
        if isinstance(item, tuple):
            item = {"key": str(index), "start": item[0], "end": item[1], "parentKey": None}
        if not isinstance(item, dict):
            raise ValueError("A semantic range must be an object.")
        start, end = item.get("start"), item.get("end")
        if type(start) is not int or type(end) is not int or start < 1 or end < start or end > paragraph_count:
            raise ValueError("Invalid frame source coordinates.")
        normalized.append(dict(item))
    by_key = {}
    for item in normalized:
        key = item.get("key")
        if not isinstance(key, str) or not key or key in by_key:
            raise ValueError("Semantic frame keys must be unique strings.")
        by_key[key] = item
    def depth(item, seen):
        key = item["key"]
        if key in seen:
            raise ValueError("Frame hierarchy contains a cycle.")
        parent_key = item.get("parentKey")
        if parent_key is None:
            return 0
        parent = by_key.get(parent_key)
        if not parent or parent["start"] > item["start"] or parent["end"] < item["end"] or (parent["start"], parent["end"]) == (item["start"], item["end"]):
            raise ValueError("Child coordinates must lie strictly within their parent.")
        return 1 + depth(parent, seen | {key})
    for item in normalized:
        item["depth"] = depth(item, set())
    if not normalized or any(not any(item["start"] <= sequence <= item["end"] for item in normalized) for sequence in range(1, paragraph_count + 1)):
        raise ValueError("Semantic frames must represent the complete source.")
    return normalized
