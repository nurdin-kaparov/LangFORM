from __future__ import annotations

from .frames import tokenize
from .schemas import ContextFrame


class SimpleRetriever:
    """Dependency-free baseline retriever using weighted token overlap."""

    def score(self, query: str, frame: ContextFrame) -> float:
        q = set(tokenize(query))
        if not q:
            return 0.0

        content_tokens = set(tokenize(frame.content))
        keyword_tokens = set(k.lower() for k in frame.keywords)
        summary_tokens = set(tokenize(frame.summary))

        content_overlap = len(q & content_tokens) / len(q)
        keyword_overlap = len(q & keyword_tokens) / len(q)
        summary_overlap = len(q & summary_tokens) / len(q)

        return round(
            (0.55 * content_overlap) +
            (0.30 * keyword_overlap) +
            (0.15 * summary_overlap),
            6
        )

    def retrieve(
        self,
        query: str,
        frames: list[ContextFrame],
        top_k: int = 5,
        asset_ids: list[str] | None = None,
    ) -> list[ContextFrame]:
        candidates = frames
        if asset_ids:
            allowed = set(asset_ids)
            candidates = [f for f in frames if f.source_id in allowed]

        scored = []
        for frame in candidates:
            score = self.score(query, frame)
            copy = ContextFrame.from_dict(frame.to_dict())
            copy.score = score
            scored.append(copy)

        scored.sort(key=lambda f: (f.score or 0.0), reverse=True)
        return scored[:max(1, top_k)]
