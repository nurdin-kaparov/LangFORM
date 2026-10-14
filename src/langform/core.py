from __future__ import annotations

import json
import hashlib
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .assets import AssetRegistry
from .frames import FrameBuilder, FrameStore, extract_keywords, summarize, _parse_paragraphs
from .models import ModelError, ModelManager
from .readers import read_text
from .retrieval import SimpleRetriever
from .schemas import AssetRecord, ContextFrame, ContextPackage
from .storage import JSONStore
from .coordinates import read_spreadsheet, grid_coordinates, resolve_spreadsheet, contains


class ContextSubagent:
    """Local-first Context Formation over user-authorized Assets.

    This class indexes sources, builds versioned Context Frames, and assembles
    evidence-only Context Packages. It does not answer questions, plan work,
    maintain conversation memory, or execute tools.
    """

    def __init__(
        self,
        workspace: str | Path = ".langform",
        *,
        ollama_url: str | None = None,
        timeout: int = 120,
    ):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.assets = AssetRegistry(self.workspace)
        self.frames = FrameStore(self.workspace)
        self.frame_builder = FrameBuilder()
        self.retriever = SimpleRetriever()
        self.models = ModelManager(base_url=ollama_url, timeout=timeout)
        self.selection_traces: list[dict[str, Any]] = []
        self.asset_selection_traces: list[dict[str, Any]] = []
        self.last_selection_trace: dict[str, Any] = {}
        self.settings = JSONStore(
            self.workspace / "registry" / "settings.json",
            {
                "selected_model_id": None,
                "preferred_candidate_frames": 30,
                "soft_max_candidate_frames": 60,
                "hard_max_candidate_frames": 100,
            },
        )
        self.packages = JSONStore(
            self.workspace / "packages" / "context-packages.json", []
        )

    def register_asset(self, reference: str, uploaded: bool = False) -> AssetRecord:
        return self.assets.register(reference, copy_uploaded=uploaded)

    def list_assets(self) -> list[AssetRecord]:
        return self.assets.list()

    def list_frames(
        self, asset_id: str | None = None, include_history: bool = False
    ) -> list[ContextFrame]:
        frames = self.frames.list(include_history=include_history)
        return [frame for frame in frames if asset_id is None or frame.source_id == asset_id]

    def get_frame(self, frame_id: str) -> ContextFrame:
        return self.frames.get(frame_id)

    def list_frame_index(
        self, asset_id: str | None = None, parent_frame_id: str | None = None,
        roots_only: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            entry for entry in self.frames.index()
            if (asset_id is None or entry["asset_id"] == asset_id)
            and (parent_frame_id is None or entry.get("parent_frame_id") == parent_frame_id)
            and (not roots_only or entry.get("parent_frame_id") is None)
        ]

    def model_status(self) -> dict[str, Any]:
        try:
            installed = self.models.installed_models()
            installed_tags = {
                str(item.get("name") or item.get("model") or "") for item in installed
            }
            return {
                "status": "ready",
                "provider": "ollama",
                "base_url": self.models.adapter.base_url,
                "selected_model_id": self._selected_model_id(),
                "models": [
                    {
                        **definition,
                        "installed": definition["ollama_tag"] in installed_tags,
                    }
                    for definition in self.models.catalog()
                ],
            }
        except ModelError as exc:
            return {
                "status": "unavailable",
                "provider": "ollama",
                "base_url": self.models.adapter.base_url,
                "selected_model_id": self._selected_model_id(),
                "models": self.models.catalog(),
                "error": str(exc),
            }

    def install_model(self, model_id: str, on_progress=None) -> None:
        self.models.install(model_id, on_progress=on_progress)

    def select_model(self, model_id: str) -> str:
        selected = self.models.select(model_id)
        config = self.settings.load()
        config["selected_model_id"] = selected
        self.settings.save(config)
        return selected

    def configure_frame_budget(self, preferred: int = 30, soft: int = 60, hard: int = 100) -> None:
        if not all(type(value) is int for value in (preferred, soft, hard)) or not 1 <= preferred <= soft <= hard <= 500:
            raise ValueError("Frame budgets must satisfy 1 ≤ preferred ≤ soft ≤ hard ≤ 500.")
        config = self.settings.load()
        config.update(
            preferred_candidate_frames=preferred,
            soft_max_candidate_frames=soft,
            hard_max_candidate_frames=hard,
        )
        self.settings.save(config)

    def analyze_asset(
        self,
        asset_id: str,
        *,
        model_id: str | None = None,
        revision_note: str | None = None,
    ) -> AssetRecord:
        asset = self.assets.get(asset_id)
        if asset.reference_type == "web_url":
            raise ValueError(
                "The local Python package does not fetch webpages. Use the hosted "
                "Assets interface for public HTTPS pages."
            )

        source = read_spreadsheet(asset.location)
        text = ("\n\n".join(resolve_spreadsheet(source, grid_coordinates(source, grid), source["version"])
                            for grid in source["grids"] if grid["rows"] and grid["columns"])
                if source else read_text(asset.location))
        selected_model_id = model_id or self._selected_model_id()
        summarizer = None
        if selected_model_id:
            self.models.select(selected_model_id)
            summarizer = self._frame_summarizer(selected_model_id)

        built_frames = self.frame_builder.build_spreadsheet(
            asset.asset_id, source, asset.location, model_id=selected_model_id, summarizer=summarizer,
            planner=self._spreadsheet_planner if selected_model_id else None,
        ) if source else self.frame_builder.build(
            asset.asset_id,
            text,
            asset.location,
            model_id=selected_model_id,
            summarizer=summarizer,
            planner=self._boundary_planner if selected_model_id else None,
        )
        for frame in built_frames:
            frame.provenance.update(asset_name=asset.name, asset_type=asset.file_type or "text")
            if not source:
                frame.source_coordinates = frame.coordinates()
                frame.source_version = hashlib.sha256(Path(asset.location).read_bytes()).hexdigest()
        if source and read_spreadsheet(asset.location)["version"] != source["version"]:
            raise ValueError("Source changed during formation. Analyze the Asset again.")
        JSONStore(self.workspace / "sources" / f"{asset.asset_id}.json", {}).save({
            "source_location": asset.location,
            "paragraphs": [{"sequence": number, "text": content, "location": location}
                for number, content, location in _parse_paragraphs(text)],
        })
        self.frames.replace_for_asset(
            asset.asset_id, built_frames, revision_note=revision_note
        )

        asset.summary = summarize(text, max_chars=500)
        asset.keywords = extract_keywords(text, limit=16)
        asset.topics = asset.keywords[:8]
        asset.frame_ids = [
            frame.frame_id for frame in self.frames.current_for_asset(asset.asset_id)
        ]
        asset.status = "ready"
        self.assets.save_asset(asset)
        return asset

    def refine_frame(self, frame_id: str, note: str) -> list[ContextFrame]:
        parent = self.frames.get(frame_id)
        if not parent.is_current:
            raise ValueError("Only a current Context Frame can be refined.")
        selected_model_id = self._selected_model_id()
        if not selected_model_id:
            raise ModelError("Select an installed local model before refining a frame.")
        self.models.select(selected_model_id)

        resolved = self._resolve_frame(parent)
        asset = self.assets.get(parent.source_id)
        source = read_spreadsheet(asset.location)
        children = self.frame_builder.build_spreadsheet(
            parent.source_id, source, asset.location, model_id=selected_model_id,
            summarizer=self._frame_summarizer(selected_model_id), planner=self._spreadsheet_planner,
            scope=parent.coordinates(),
        ) if source and parent.coordinates()["type"] != "paragraph" else self.frame_builder.build(
            parent.source_id,
            resolved.content,
            str(parent.provenance.get("source", "local source")),
            model_id=selected_model_id,
            summarizer=self._frame_summarizer(selected_model_id),
            planner=self._boundary_planner,
            start_paragraph=parent.start_paragraph,
            initial_location=parent.structural_location,
        )
        if not children:
            raise ValueError("The Context Frame contains no source text to refine.")
        for child in children:
            child.source_version = parent.source_version
            if child.source_coordinates is None:
                child.source_coordinates = child.coordinates()
        self._resolve_frame(parent)
        self.frames.refine(parent.frame_id, children, note.strip() or "Refined frame range.")

        asset = self.assets.get(parent.source_id)
        asset.frame_ids = [
            frame.frame_id for frame in self.frames.current_for_asset(parent.source_id)
        ]
        self.assets.save_asset(asset)
        return [
            frame
            for frame in self.frames.list(include_history=False)
            if frame.revision_parent_frame_id == parent.frame_id or
            frame.frame_id in {item.frame_id for item in children}
        ]

    def prepare_context(
        self,
        user_query: str,
        top_k: int = 5,
        asset_ids: list[str] | None = None,
    ) -> ContextPackage:
        started = time.perf_counter()
        self.last_selection_trace = None
        self.selection_traces = []
        self.asset_selection_traces = []
        query = user_query.strip()
        if not query:
            raise ValueError("A context request must include a non-empty query.")

        config = self.settings.load()
        preferred = config.get("preferred_candidate_frames", 30)
        soft = config.get("soft_max_candidate_frames", 60)
        hard = config.get("hard_max_candidate_frames", 100)
        if any(type(value) is not int for value in (preferred, soft, hard)) or not 1 <= preferred <= soft <= hard <= 500:
            raise ValueError("Candidate budgets must satisfy 1 <= preferred <= soft <= hard <= 500.")
        index = [ContextFrame.from_index(entry) for entry in self.list_frame_index()]
        if asset_ids is not None:
            index = [frame for frame in index if frame.source_id in set(asset_ids)]
        candidates = self.retriever.retrieve(
            query, index,
            top_k=hard,
            asset_ids=asset_ids,
        )
        selected_model_id = self._selected_model_id()
        status = "context_ready"
        selected: list[ContextFrame] = []

        if not candidates:
            status = "no_evidence"
        elif not selected_model_id:
            status = "model_required"
        else:
            try:
                self.models.select(selected_model_id)
                if len(index) > preferred and len({frame.source_id for frame in index}) > 1:
                    relevant_assets = self._select_assets(query, index)
                    candidates = self.retriever.retrieve(query, index, top_k=hard, asset_ids=relevant_assets)
                for budget in sorted({preferred, soft, hard}):
                    if not candidates:
                        break
                    selected = self._select_frames(query, candidates[:budget], top_k, selected_model_id)
                    if selected or budget >= len(candidates):
                        break
                status = "context_ready" if selected else "no_evidence"
            except ModelError:
                status = "model_required"
            except (ValueError, TypeError, KeyError, OSError):
                status = "error"

        package = ContextPackage(
            package_id=f"package_{uuid.uuid4().hex[:12]}",
            status=status,
            user_query=query,
            frames=selected,
            assets_used=sorted({frame.source_id for frame in selected}),
            model_id=selected_model_id,
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        saved = self.packages.load()
        saved.append(package.to_dict())
        self.packages.save(saved)
        return package

    def list_packages(self) -> list[dict[str, Any]]:
        return list(reversed(self.packages.load()))

    def get_package(self, package_id: str) -> dict[str, Any]:
        for package in self.packages.load():
            if package.get("package_id") == package_id:
                return package
        raise KeyError(f"Context Package not found: {package_id}")

    def _selected_model_id(self) -> str | None:
        selected = self.settings.load().get("selected_model_id")
        return selected if isinstance(selected, str) and selected else None

    def _frame_summarizer(self, model_id: str):
        self.models.adapter.model = model_id

        def summarize_range(content: str, location: str) -> str:
            result = self.models.adapter.generate_json(
                "Summarize this source range in one or two factual sentences. "
                "Return JSON with a non-empty string field named summary. "
                "Do not add facts that are not in the source.\n\n"
                f"Structural location: {location}\n\nSource:\n{content}",
                "You produce source-grounded Context Frame summaries. Return only JSON.",
            )
            summary = result.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                raise ModelError("The selected model returned an invalid frame summary.")
            return summary.strip()

        return summarize_range

    def _boundary_planner(
        self, paragraphs: list[tuple[int, str, str]]
    ) -> list[dict[str, Any]]:
        """Two bounded passes: propose semantic depth, then review split/merge utility."""
        batches: list[list[tuple[int, str, str]]] = []
        current: list[tuple[int, str, str]] = []
        size = 0
        for paragraph in paragraphs:
            if current and size + len(paragraph[1]) > 24000:
                batches.append(current)
                current, size = [], 0
            current.append(paragraph)
            size += len(paragraph[1])
        if current:
            batches.append(current)

        ranges: list[dict[str, Any]] = []
        system = (
            "You form hierarchical Context Frames, not mutually exclusive chunks. Keep useful "
            "broad parent frames while adding selected independently meaningful children. "
            "Balance semantic precision against manageable frame count. Return only JSON."
        )
        for batch in batches:
            result = self.models.adapter.generate_json(
                "Propose nested semantic source ranges representing every numbered paragraph at least once. "
                "Depth depends on meaning, density, structure, and future retrieval utility, "
                'not length. Return {"ranges":[{"key":"unique-key","start":1,"end":2,'
                '"parentKey":null,"frameType":"chapter","importance":"high","reason":"..."}]}.\n'
                + "\n\n".join(f"P{number} [{location}]\n{text}" for number, text, location in batch),
                system,
            )
            proposed = result.get("ranges")
            if not isinstance(proposed, list) or not proposed:
                raise ModelError("Local model returned no semantic ranges.")
            ranges.extend(proposed)

        review = self.models.adapter.generate_json(
            "Review these proposed nested ranges. Keep useful broad parents and selected children. "
            "Overlap is allowed. Repair duplicate keys and parent containment. Avoid unnecessary "
            "fragmentation. This is the final review: stop after this pass. Represent P1 through "
            f"P{len(paragraphs)} at least once. Use the same JSON schema.\n"
            f"Ranges: {json.dumps(ranges, ensure_ascii=False)}\n"
            "Source overview:\n"
            + "\n".join(f"P{number} [{location}]: {text[:200]}" for number, text, location in paragraphs),
            system,
        )
        final_ranges = review.get("ranges")
        if not isinstance(final_ranges, list):
            raise ModelError("Local model returned an invalid boundary review.")
        return final_ranges

    def _select_assets(self, query: str, index: list[ContextFrame]) -> list[str]:
        """Coarse semantic navigation over Asset metadata, never original content."""
        descriptors = []
        for asset in self.assets.list():
            frames = [frame for frame in index if frame.source_id == asset.asset_id]
            if not frames:
                continue
            ranked = sorted(frames, key=lambda frame: self.retriever.score(query, frame), reverse=True)
            roots = [frame for frame in frames if frame.parent_frame_id is None]
            descriptions = list(dict.fromkeys(frame.summary[:200] for frame in roots[:2] + ranked[:2]))
            descriptors.append({"asset_id": asset.asset_id, "name": asset.name,
                "summary": (asset.summary or "")[:400], "type": asset.file_type,
                "frame_descriptions": descriptions, "frame_count": len(frames)})
        selected: list[str] = []
        for start in range(0, len(descriptors), 16):
            batch = descriptors[start:start + 16]
            request_id = f"assets_{uuid.uuid4().hex[:12]}"
            response = self.models.adapter.generate_json(
                "Select the Assets that could provide evidence for the request, including broad or comparative tasks. "
                "Use only the supplied IDs. Return JSON with exactly request_id and selected_asset_ids.\n"
                f"Request ID: {request_id}\nRequest: {query}\nAsset metadata:\n{json.dumps(batch, ensure_ascii=False)}",
                "You are LangFORM's Context Subagent. Navigate metadata only. Do not answer or invent source evidence.",
            )
            trace = {"request_id": request_id, "asset_metadata": batch, "selection": response}
            self.asset_selection_traces.append(trace)
            ids = response.get("selected_asset_ids")
            allowed = {entry["asset_id"] for entry in batch}
            if (set(response) != {"request_id", "selected_asset_ids"} or response.get("request_id") != request_id
                or not isinstance(ids, list) or any(not isinstance(value, str) or value not in allowed for value in ids)
                or len(ids) != len(set(ids))):
                raise ValueError("Invalid Asset metadata selection.")
            trace["validation_status"] = "validated"
            selected.extend(ids)
        return selected

    def _select_frames(
        self,
        query: str,
        candidates: list[ContextFrame],
        top_k: int,
        model_id: str,
    ) -> list[ContextFrame]:
        self.models.adapter.model = model_id
        candidate_data = [frame.index_entry() for frame in candidates]
        visible_ids = {frame.frame_id for frame in candidates}
        for entry in candidate_data:
            # Siblings can be inferred from parent IDs; do not repeat an
            # all-to-all sibling list in every model-input record.
            entry["indexed_sibling_count"] = len(entry.pop("sibling_frame_ids", []))
            entry["indexed_child_count"] = len(entry["child_frame_ids"])
            entry["child_frame_ids"] = [item for item in entry["child_frame_ids"] if item in visible_ids]
            entry["ancestor_frame_ids"] = [item for item in entry["ancestor_frame_ids"] if item in visible_ids]
        request_id = f"request_{uuid.uuid4().hex[:12]}"
        self.last_selection_trace = {"request_id": request_id, "candidate_index": candidate_data}
        self.selection_traces.append(self.last_selection_trace)
        response = self.models.adapter.generate_json(
            f"Select at most {max(1, min(top_k, 20))} Context Frames that directly help with "
            "the request. Choose sufficient granularity: parents, children, siblings, or both. "
            "Do not always choose the smallest frame. Use only supplied IDs and no source content. "
            'Return {"request_id":"' + request_id + '","selected_frames":[{"context_frame_id":"...",'
            '"include_mode":"full_frame","priority":1,"reason":"..."}]}.\n\n'
            f"Request ID: {request_id}\n"
            f"Request:\n{query}\n\nCandidate frames:\n{json.dumps(candidate_data, ensure_ascii=False)}",
            "You are LangFORM's Context Subagent. Select source-grounded evidence only. "
            "Do not answer, plan, invent evidence, or select an unlisted ID. Return only JSON.",
        )
        choices = response.get("selected_frames")
        self.last_selection_trace["selection"] = {
            "request_id": response.get("request_id"), "selected_frames": choices,
        }
        if (set(response) - {"request_id", "selected_frames"} or response.get("request_id") != request_id
            or not isinstance(choices, list) or len(choices) > max(1, min(top_k, 20))):
            raise ValueError("Invalid model selection request ID or frame count.")

        by_id = {frame.frame_id: frame for frame in candidates}
        seen: set[str] = set()
        selected: list[ContextFrame] = []
        for choice in choices:
            if not isinstance(choice, dict):
                raise ValueError("Model frame selections must be JSON objects.")
            frame_id = choice.get("context_frame_id")
            reason = choice.get("reason")
            if (set(choice) - {"context_frame_id", "include_mode", "priority", "reason"}
                or not isinstance(frame_id, str) or frame_id not in by_id or frame_id in seen
                or choice.get("include_mode") not in {"full_frame", "parent_frame", "child_frame"}
                or type(choice.get("priority")) is not int or choice["priority"] < 1
                or (reason is not None and not isinstance(reason, str))):
                raise ValueError("Unknown frame, duplicate selection, invalid mode, or invalid priority.")
            seen.add(frame_id)
        self.last_selection_trace["validation_status"] = "validated"
        # Validate the entire selection before touching any original source.
        for choice in choices:
            frame = self._resolve_frame(by_id[choice["context_frame_id"]])
            reason = choice.get("reason")
            frame.selection_reason = (reason or "Selected at sufficient semantic granularity.")[:500]
            frame.include_mode = choice["include_mode"]
            frame.priority = choice["priority"]
            selected.append(frame)
        for frame in selected:
            covers = [item for item in selected if item.source_id == frame.source_id
                and item.source_version == frame.source_version and item.frame_id != frame.frame_id
                and contains(item.coordinates(), frame.coordinates()) and
                (not contains(frame.coordinates(), item.coordinates()) or selected.index(item) < selected.index(frame))]
            covering = next((item for item in covers if not any(
                outer.frame_id != item.frame_id and contains(outer.coordinates(), item.coordinates())
                and (not contains(item.coordinates(), outer.coordinates()) or selected.index(outer) < selected.index(item))
                for outer in covers)), None)
            if covering:
                frame.duplicate_of_frame_id = covering.frame_id
                frame.content = ""
        return sorted(selected, key=lambda frame: frame.priority)

    def _resolve_frame(self, indexed: ContextFrame) -> ContextFrame:
        """Resolve coordinates algorithmically; no model call reads or generates evidence."""
        frame = self.frames.get(indexed.frame_id)
        if not frame.is_current or frame.source_id != indexed.source_id or frame.coordinates() != indexed.coordinates() or frame.source_version != indexed.source_version:
            raise ValueError("Selected frame is no longer current or changed during selection.")
        source = JSONStore(self.workspace / "sources" / f"{frame.source_id}.json", {}).load()
        asset = self.assets.get(frame.source_id)
        coordinates = frame.coordinates()
        if coordinates["type"] != "paragraph":
            original = read_spreadsheet(asset.location)
            if original is None:
                raise ValueError("Native source format no longer matches the frame.")
            content = resolve_spreadsheet(original, coordinates, frame.source_version)
            if content != frame.content:
                raise ValueError("Selected evidence no longer matches the indexed source.")
            frame.content = content
            frame.score = indexed.score
            return frame
        if frame.source_version and hashlib.sha256(Path(asset.location).read_bytes()).hexdigest() != frame.source_version:
            raise ValueError("Source changed after indexing. Analyze the Asset again.")
        start, end = coordinates["start_paragraph"], coordinates["end_paragraph"]
        if (type(start) is not int or type(end) is not int or start < 1 or end < start):
            raise ValueError("Invalid paragraph coordinates.")
        current = [{"sequence": number, "text": text, "location": location}
            for number, text, location in _parse_paragraphs(read_text(asset.location))]
        if source.get("paragraphs") != current:
            raise ValueError("Source changed after indexing. Analyze the Asset again.")
        paragraphs = [item["text"] for item in current if start <= item["sequence"] <= end]
        if len(paragraphs) != end - start + 1:
            raise ValueError("Selected coordinates do not resolve to complete evidence.")
        content = "\n\n".join(paragraphs)
        if content != frame.content:
            raise ValueError("Selected evidence no longer matches its indexed source range.")
        frame.content = content
        frame.score = indexed.score
        return frame

    def _spreadsheet_planner(self, source: dict, scope: dict | None = None) -> list[dict]:
        proposals = []
        bounds = [scope] if scope else [grid_coordinates(source, grid) for grid in source["grids"]
                                       if grid["rows"] and grid["columns"]]
        schema = ('{"ranges":[{"key":"unique","parentKey":null,"coordinates":{"type":"xlsx or csv",'
                  '"sheet":"exact sheet name or null","start_row":1,"end_row":2,'
                  '"start_column":1,"end_column":3},"reason":"observable utility","frameType":"table"}]}')
        system = "Form useful nested semantic cell ranges, not fixed row chunks. Never generate evidence values. Return JSON."
        for bound in bounds:
            evidence = resolve_spreadsheet(source, bound, source["version"])
            for start in range(0, len(evidence), 24000):
                result = self.models.adapter.generate_json(
                    "Propose useful table parents and independently meaningful row AND column children. "
                    f"Return {schema}. Bounds: {json.dumps(bound)}\nCells:\n{evidence[start:start + 24000]}", system)
                if not isinstance(result.get("ranges"), list):
                    raise ValueError("Invalid native formation response.")
                proposals.extend(result["ranges"])
        review = self.models.adapter.generate_json(
            "Review proposals once. Repair duplicate keys, parent containment and full coverage of source bounds. "
            "Avoid fragmentation; keep useful broad parents. Children must lie strictly inside parents on the same sheet. "
            f"Return {schema}.\nBounds: {json.dumps(bounds)}\nProposals: {json.dumps(proposals)}", system)
        return review.get("ranges")


# Keep the established public entry point while making the product boundary explicit.
LangFORM = ContextSubagent
