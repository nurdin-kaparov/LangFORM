from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .schemas import MemoryItem
from .storage import JSONStore


class ConversationMemory:
    def __init__(self, workspace: str | Path):
        self.store = JSONStore(Path(workspace) / "memory" / "conversation.json", [])

    def add(self, role: str, content: str) -> MemoryItem:
        item = MemoryItem(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        items = self.list()
        items.append(item)
        self.store.save([x.to_dict() for x in items])
        return item

    def list(self) -> list[MemoryItem]:
        return [MemoryItem.from_dict(x) for x in self.store.load()]

    def recent(self, limit: int = 8) -> list[MemoryItem]:
        return self.list()[-limit:]

    def clear(self) -> None:
        self.store.save([])
