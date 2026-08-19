from __future__ import annotations

import re
import uuid
from pathlib import Path

from .schemas import ContextFrame
from .storage import JSONStore


_WORD_RE = re.compile(r"[A-Za-z0-9_'-]+")


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    stop = {
        "the","and","for","that","with","this","from","are","was","were","have","has","had",
        "not","but","you","your","into","about","which","will","would","can","could","should",
        "their","they","them","then","than","its","our","out","all","any","use","using","used",
        "when","where","what","how","why","who","also","more","most","such","only","each","other",
        "some","been","being","between","through","over","under","after","before","same"
    }
    counts = {}
    for w in tokenize(text):
        if len(w) < 3 or w in stop:
            continue
        counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def summarize(text: str, max_chars: int = 280) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    clipped = clean[:max_chars].rsplit(" ", 1)[0]
    return clipped + "..."


class FrameStore:
    def __init__(self, workspace: str | Path):
        self.store = JSONStore(Path(workspace) / "frames" / "frames.json", [])

    def list(self) -> list[ContextFrame]:
        return [ContextFrame.from_dict(x) for x in self.store.load()]

    def replace_for_asset(self, asset_id: str, frames: list[ContextFrame]) -> None:
        remaining = [f for f in self.list() if f.source_id != asset_id]
        self.store.save([f.to_dict() for f in remaining + frames])


class FrameBuilder:
    """Creates semantic-ish frames using document structure and paragraph boundaries."""

    def build(self, asset_id: str, text: str, source_location: str) -> list[ContextFrame]:
        sections = self._sections(text)
        frames = []
        for section_title, content in sections:
            if not content.strip():
                continue
            for part in self._split_long_section(content):
                keywords = extract_keywords(part)
                frames.append(
                    ContextFrame(
                        frame_id=f"frame_{uuid.uuid4().hex[:12]}",
                        source_id=asset_id,
                        section=section_title,
                        content=part.strip(),
                        summary=summarize(part),
                        keywords=keywords,
                        topics=keywords[:5],
                        provenance={
                            "source": source_location,
                            "section": section_title,
                        },
                    )
                )
        return frames

    def _sections(self, text: str) -> list[tuple[str | None, str]]:
        lines = text.splitlines()
        sections = []
        title = None
        buffer = []

        def flush():
            nonlocal buffer
            content = "\n".join(buffer).strip()
            if content:
                sections.append((title, content))
            buffer = []

        for line in lines:
            stripped = line.strip()
            is_heading = (
                stripped.startswith("#")
                or (0 < len(stripped) <= 90 and stripped.endswith(":"))
            )
            if is_heading:
                flush()
                title = stripped.lstrip("#").strip().rstrip(":")
            else:
                buffer.append(line)
        flush()

        if not sections and text.strip():
            sections.append((None, text.strip()))
        return sections

    def _split_long_section(self, text: str, target_chars: int = 1800) -> list[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return [text]
        parts, current = [], []
        size = 0
        for p in paragraphs:
            if current and size + len(p) > target_chars:
                parts.append("\n\n".join(current))
                current, size = [], 0
            current.append(p)
            size += len(p)
        if current:
            parts.append("\n\n".join(current))
        return parts
