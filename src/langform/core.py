from __future__ import annotations

from pathlib import Path
from typing import Any

from .assets import AssetRegistry
from .frames import FrameBuilder, FrameStore, extract_keywords, summarize
from .memory import ConversationMemory
from .readers import read_text
from .retrieval import SimpleRetriever
from .schemas import AssetRecord, ContextPackage


class LangFORM:
    def __init__(self, workspace: str | Path = ".langform"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.assets = AssetRegistry(self.workspace)
        self.frames = FrameStore(self.workspace)
        self.memory = ConversationMemory(self.workspace)
        self.frame_builder = FrameBuilder()
        self.retriever = SimpleRetriever()

    def register_asset(self, reference: str, uploaded: bool = False) -> AssetRecord:
        return self.assets.register(reference, copy_uploaded=uploaded)

    def list_assets(self) -> list[AssetRecord]:
        return self.assets.list()

    def analyze_asset(self, asset_id: str) -> AssetRecord:
        asset = self.assets.get(asset_id)
        if asset.reference_type == "web_url":
            raise ValueError(
                "v0.0.2 registers web URLs as references but does not download them automatically."
            )

        text = read_text(asset.location)
        built_frames = self.frame_builder.build(asset.asset_id, text, asset.location)
        self.frames.replace_for_asset(asset.asset_id, built_frames)

        asset.summary = summarize(text, max_chars=500)
        asset.keywords = extract_keywords(text, limit=16)
        asset.topics = asset.keywords[:8]
        asset.frame_ids = [f.frame_id for f in built_frames]
        asset.status = "analyzed"
        self.assets.save_asset(asset)
        return asset

    def prepare_context(
        self,
        user_query: str,
        top_k: int = 5,
        asset_ids: list[str] | None = None,
        session_id: str | None = None,
        memory_limit: int = 6,
    ) -> ContextPackage:
        selected = self.retriever.retrieve(
            user_query,
            self.frames.list(),
            top_k=top_k,
            asset_ids=asset_ids,
        )
        memory = self.memory.recent(memory_limit)
        status = "context_ready" if selected or memory else "more_context_required"
        request = None
        if status == "more_context_required":
            request = {
                "type": "retrieve_context",
                "information_need": user_query,
            }

        return ContextPackage(
            status=status,
            session_id=session_id,
            user_query=user_query,
            context_frames=selected,
            memory=memory,
            request=request,
        )

    def add_memory(self, role: str, content: str):
        return self.memory.add(role, content)

    def ingest_external_result(
        self,
        result_text: str,
        label: str = "external_result",
    ) -> list[dict[str, Any]]:
        temp_asset_id = f"external:{label}"
        frames = self.frame_builder.build(temp_asset_id, result_text, label)
        existing = self.frames.list()
        self.frames.store.save([f.to_dict() for f in existing + frames])
        return [f.to_dict() for f in frames]

    def clear_memory(self) -> None:
        self.memory.clear()
