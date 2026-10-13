from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal, TypedDict


class ParagraphCoordinates(TypedDict):
    type: Literal["paragraph"]
    start_paragraph: int
    end_paragraph: int


class GridCoordinates(TypedDict):
    type: Literal["xlsx", "csv"]
    sheet: str | None
    start_row: int
    end_row: int
    start_column: int
    end_column: int
    column_ids: list[str]


SourceCoordinates = ParagraphCoordinates | GridCoordinates


def _known_fields(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    names = {item.name for item in fields(cls)}
    return {key: value for key, value in data.items() if key in names}


@dataclass
class AssetRecord:
    asset_id: str
    reference_type: str
    location: str
    name: str
    file_type: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None
    modified_at: str | None = None
    sha256: str | None = None
    status: str = "registered"
    summary: str | None = None
    document_type: str | None = None
    topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    frame_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetRecord":
        return cls(**_known_fields(cls, data))


@dataclass
class ContextFrame:
    frame_id: str
    source_id: str
    content: str
    summary: str
    section: str | None = None
    topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    start_paragraph: int = 1
    end_paragraph: int = 1
    structural_location: str = "Document"
    model_id: str | None = None
    version: int = 1
    is_current: bool = True
    parent_frame_id: str | None = None
    revision_parent_frame_id: str | None = None
    child_frame_ids: list[str] = field(default_factory=list)
    sibling_frame_ids: list[str] = field(default_factory=list)
    ancestor_frame_ids: list[str] = field(default_factory=list)
    depth_level: int = 0
    frame_type: str = "semantic_range"
    importance: str = "normal"
    include_mode: str | None = None
    priority: int | None = None
    duplicate_of_frame_id: str | None = None
    revision_note: str | None = None
    selection_reason: str | None = None
    source_coordinates: SourceCoordinates | None = None
    source_version: str | None = None

    def coordinates(self) -> SourceCoordinates:
        return self.source_coordinates or {"type": "paragraph", "start_paragraph": self.start_paragraph,
                                           "end_paragraph": self.end_paragraph}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextFrame":
        compatible = dict(data)
        # Earlier stores used parent_frame_id exclusively for revision lineage.
        if "depth_level" not in compatible and "revision_parent_frame_id" not in compatible:
            compatible["revision_parent_frame_id"] = compatible.pop("parent_frame_id", None)
        provenance = compatible.get("provenance") or {}
        compatible.setdefault("start_paragraph", provenance.get("start_paragraph", 1))
        compatible.setdefault("end_paragraph", provenance.get("end_paragraph", 1))
        compatible.setdefault(
            "structural_location",
            provenance.get("structural_location") or compatible.get("section") or "Document",
        )
        return cls(**_known_fields(cls, compatible))

    def index_entry(self) -> dict[str, Any]:
        return {
            "context_frame_id": self.frame_id, "asset_id": self.source_id,
            "asset_name": self.provenance.get("asset_name", self.source_id),
            "asset_type": self.provenance.get("asset_type", "text"),
            "source_location": self.provenance.get("source"),
            "description": self.summary, "structural_location": self.structural_location,
            "start_paragraph": self.start_paragraph, "end_paragraph": self.end_paragraph,
            "source_coordinates": self.coordinates(), "source_version": self.source_version,
            "parent_frame_id": self.parent_frame_id, "child_frame_ids": self.child_frame_ids,
            "ancestor_frame_ids": self.ancestor_frame_ids, "sibling_frame_ids": self.sibling_frame_ids,
            "depth_level": self.depth_level, "frame_type": self.frame_type,
            "importance": self.importance, "topics": self.topics, "keywords": self.keywords,
            "version": self.version, "is_current": self.is_current,
            "revision_parent_frame_id": self.revision_parent_frame_id,
            "locked": bool(self.provenance.get("locked")),
            "research_override": bool(self.provenance.get("research_override")),
        }

    @classmethod
    def from_index(cls, entry: dict[str, Any]) -> "ContextFrame":
        return cls(
            frame_id=entry["context_frame_id"], source_id=entry["asset_id"], content="",
            summary=entry["description"], structural_location=entry["structural_location"],
            start_paragraph=entry["start_paragraph"], end_paragraph=entry["end_paragraph"],
            parent_frame_id=entry.get("parent_frame_id"), depth_level=entry.get("depth_level", 0),
            frame_type=entry.get("frame_type", "semantic_range"), importance=entry.get("importance", "normal"),
            child_frame_ids=entry.get("child_frame_ids", []), ancestor_frame_ids=entry.get("ancestor_frame_ids", []),
            sibling_frame_ids=entry.get("sibling_frame_ids", []), topics=entry.get("topics", []),
            keywords=entry.get("keywords", []), version=entry.get("version", 1),
            is_current=entry.get("is_current", True),
            source_coordinates=entry.get("source_coordinates"), source_version=entry.get("source_version"),
            provenance={"source": entry.get("source_location"), "asset_name": entry.get("asset_name"),
                "asset_type": entry.get("asset_type"), "locked": bool(entry.get("locked")),
                "research_override": bool(entry.get("research_override"))},
        )


@dataclass
class ContextPackage:
    status: str
    user_query: str
    frames: list[ContextFrame]
    assets_used: list[str] = field(default_factory=list)
    model_id: str | None = None
    latency_ms: int = 0
    package_id: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "status": self.status,
            "user_query": self.user_query,
            "frames": [frame.to_dict() for frame in self.frames],
            "assets_used": self.assets_used,
            "model_id": self.model_id,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
        }
