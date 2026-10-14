from __future__ import annotations

from .frames import tokenize
from .schemas import ContextFrame


class SimpleRetriever:
    """Transparent lexical candidate narrowing, never final Context Formation."""

    def score(self, query: str, frame: ContextFrame) -> float:
        q = set(tokenize(query))
        if not q:
            return 0.0

        location_tokens = set(tokenize(frame.structural_location))
        keyword_tokens = set(k.lower() for k in frame.keywords)
        summary_tokens = set(tokenize(frame.summary))

        location_overlap = len(q & location_tokens) / len(q)
        keyword_overlap = len(q & keyword_tokens) / len(q)
        summary_overlap = len(q & summary_tokens) / len(q)

        return round(
            (0.55 * location_overlap) +
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
        if asset_ids is not None:
            allowed = set(asset_ids)
            candidates = [f for f in frames if f.source_id in allowed]

        scored = []
        for frame in candidates:
            score = self.score(query, frame)
            copy = ContextFrame.from_dict(frame.to_dict())
            copy.score = score
            if copy.is_current:
                scored.append(copy)

        scored.sort(key=lambda f: (f.score or 0.0), reverse=True)
        by_id = {frame.frame_id: frame for frame in scored}
        result: list[ContextFrame] = []
        included: set[str] = set()
        limit = max(1, top_k)
        for frame in scored:
            chain = [frame]
            seen = {frame.frame_id}
            parent = by_id.get(frame.parent_frame_id)
            while parent and parent.frame_id not in seen:
                chain.insert(0, parent)
                seen.add(parent.frame_id)
                parent = by_id.get(parent.parent_frame_id)
            for item in chain:
                if item.frame_id not in included:
                    if len(result) >= limit:
                        return result
                    result.append(item)
                    included.add(item.frame_id)
        return result
