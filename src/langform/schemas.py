from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


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
        return cls(**data)


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextFrame":
        return cls(**data)


@dataclass
class MemoryItem:
    role: str
    content: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        return cls(**data)


@dataclass
class ContextPackage:
    status: str
    user_query: str
    context_frames: list[ContextFrame]
    memory: list[MemoryItem] = field(default_factory=list)
    session_id: str | None = None
    request: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "session_id": self.session_id,
            "user_query": self.user_query,
            "context_frames": [f.to_dict() for f in self.context_frames],
            "memory": [m.to_dict() for m in self.memory],
            "request": self.request,
        }
