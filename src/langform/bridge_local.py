"""Scoped local operations for the Test Harness; never a general filesystem tool."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from .core import ContextSubagent
from .readers import read_text
from .storage import JSONStore
from .frames import tokenize
from .bridge_research import research_edit
from . import bridge_projects

SUPPORTED = {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".pdf", ".docx", ".xlsx"}
EXCLUDED = {"node_modules", "__pycache__", "generated-artifacts", "dist"}


class LocalBridge:
    def __init__(self, workspace: Path, grants: list[Path], ollama_url: str | None = None):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.grants = [path.expanduser().resolve(strict=True) for path in grants]
        self.imports = self.workspace / "bridge" / "imports"
        self.imports.mkdir(parents=True, exist_ok=True)
        self.service = ContextSubagent(self.workspace, ollama_url=ollama_url)
        self.metrics = JSONStore(self.workspace / "bridge" / "asset-metrics.json", {})
        self.source_urls = JSONStore(self.workspace / "bridge" / "source-urls.json", {})
        self._usage: list[dict[str, Any]] = []
        self.on_progress = None
        self._operation = ""
        self._call_index = 0
        self._processing_phase = ""
        original_generate = self.service.models.adapter.generate

        def measured_generate(prompt, system=None):
            self._call_index += 1
            call_index = self._call_index
            if self.on_progress:
                self.on_progress({"stage": "slm_started", "callIndex": call_index,
                                  "phase": self._processing_phase,
                                  "model": self.service.models.adapter.model})
            started = time.perf_counter()
            result = original_generate(prompt, system)
            self._usage.append({
                **getattr(self.service.models.adapter, "last_usage", {}),
                "model_id": self.service.models.adapter.model,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            })
            if self.on_progress:
                self.on_progress({"stage": "slm_completed", "callIndex": call_index,
                                  "phase": self._processing_phase,
                                  "model": self.service.models.adapter.model})
            return result

        self.service.models.adapter.generate = measured_generate

    def approved(self, path: Path) -> bool:
        resolved = path.expanduser().resolve()
        if resolved.is_relative_to(self.imports.resolve()):
            return resolved.suffix == ".md"
        # Private bridge credentials, cached Packages and Frame stores must
        # never become Assets, even if a user grants a broad parent folder.
        if resolved.is_relative_to(self.workspace):
            return False
        for grant in self.grants:
            if grant.is_file() and resolved == grant:
                return resolved.suffix.lower() in SUPPORTED
            if grant.is_dir() and resolved.is_relative_to(grant):
                relative = resolved.relative_to(grant)
                if (resolved.suffix.lower() in SUPPORTED
                    and not any(part.startswith(".") or part in EXCLUDED for part in relative.parts)):
                    return True
        return False

    def asset(self, asset_id: str, args: dict):
        asset = self.service.assets.get(asset_id)
        if not self.approved(Path(asset.location)):
            raise PermissionError("Asset is outside the explicitly granted local paths.")
        if (args.get("_actor") != "researcher" or args.get("_project_scope")) and asset_id not in args.get("asset_ids", []):
            raise PermissionError("Asset is outside this project's scope.")
        return asset

    def frame(self, frame_id: str, args: dict):
        frame = self.service.get_frame(frame_id)
        self.asset(frame.source_id, args)
        return frame

    def select_model(self, model: str):
        # Selection checks installation. Never download a model on behalf of a job.
        self.service.models.select(model)
        settings = self.service.settings.load()
        settings["selected_model_id"] = model
        self.service.settings.save(settings)

    def sources(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for grant in self.grants:
            paths = grant.rglob("*") if grant.is_dir() else [grant]
            for path in paths:
                relative = path.relative_to(grant) if grant.is_dir() else Path(path.name)
                if any(part.startswith(".") or part in EXCLUDED for part in relative.parts):
                    continue
                if path.is_file() and not path.is_symlink() and path.suffix.lower() in SUPPORTED and self.approved(path):
                    key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]
                    result[key] = path.resolve()
                if len(result) >= 2000:
                    return result
        return result

    def register(self, path: Path):
        if not self.approved(path):
            raise PermissionError("File is outside granted paths.")
        existing = next((asset for asset in self.service.list_assets() if asset.location == str(path.resolve())), None)
        return existing or self.service.register_asset(str(path.resolve()))

    def analyze(self, asset_id: str, args: dict):
        asset = self.asset(asset_id, args)
        if any(frame.provenance.get("locked") for frame in self.service.list_frames(asset_id)):
            raise PermissionError("This Asset contains locked research Frames. Unlock them before rebuilding.")
        text = read_text(asset.location)
        started = time.perf_counter()
        self.service.analyze_asset(asset_id)
        source_url = self.source_urls.load().get(asset_id)
        if source_url:
            saved = self.service.frames.list()
            for frame in saved:
                if frame.source_id == asset_id and frame.is_current:
                    frame.provenance["source_url"] = source_url
            self.service.frames._save(saved)
        values = self.metrics.load()
        values[asset_id] = {
            "source_characters": len(text), "latency_ms": round((time.perf_counter() - started) * 1000),
            "model_id": args["context_model"], "formation_passes": 2,
            "frame_count": len(self.service.list_frames(asset_id)),
        }
        self.metrics.save(values)
        return self.service.assets.get(asset_id)

    def scoped_assets(self, args: dict, discovery: bool = False):
        assets = []
        for asset in self.service.list_assets():
            if not self.approved(Path(asset.location)):
                continue
            if (discovery and args.get("_actor") == "researcher"
                and (not args.get("_project_scope") or self._operation == "list_assets")) or asset.asset_id in args.get("asset_ids", []):
                assets.append(asset)
        return assets

    def execute(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        self._usage = []
        self._operation = operation
        self._call_index = 0
        self._processing_phase = operation
        started = time.perf_counter()
        researcher = args.get("_actor") == "researcher"
        if not researcher:
            for asset_id in args.get("asset_ids", []):
                self.asset(asset_id, args)
        budgets = args.get("candidate_budgets")
        if budgets is not None:
            values = [budgets.get(key) for key in ["preferred", "soft", "hard"]]
            if any(type(value) is not int for value in values) or not 1 <= values[0] <= values[1] <= values[2] <= 500:
                raise ValueError("Invalid candidate budgets.")
            settings = self.service.settings.load()
            settings.update(dict(zip(["preferred_candidate_frames", "soft_max_candidate_frames", "hard_max_candidate_frames"], values)))
            self.service.settings.save(settings)
        if operation in {"list_sources", "register_sources", "import_assets", "edit_frame", "split_frame", "merge_frames", "lock_frame"} and not researcher:
            raise PermissionError("This operation requires an explicit researcher action.")
        result: dict[str, Any]
        if operation == "classify_project_prompt":
            result = bridge_projects.classify(self, args)
        elif operation == "resolve_project_sources":
            if not researcher:
                raise PermissionError("Source access requires an explicit project user request.")
            result = bridge_projects.resolve_sources(self, args)
        elif operation == "summarize_project":
            result = bridge_projects.processing_summary(self, args)
        elif operation == "process_project_asset":
            result = bridge_projects.process_asset(self, args)
        elif operation == "package_project_context":
            result = bridge_projects.package_reply(self, args)
        elif operation == "list_sources":
            result = {"sources": [{"id": key, "name": path.name, "size_bytes": path.stat().st_size, "file_type": path.suffix}
                for key, path in self.sources().items()]}
        elif operation == "register_sources":
            ids = args.get("source_ids", [])
            if not isinstance(ids, list) or not 1 <= len(ids) <= 100:
                raise ValueError("Select 1–100 granted files.")
            sources = self.sources()
            if any(key not in sources for key in ids):
                raise PermissionError("A file is no longer present or is outside the grants.")
            result = {"assets": [self.register(sources[key]).to_dict() for key in ids]}
        elif operation == "import_assets":
            sources = args.get("sources", [])
            if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
                raise ValueError("Select 1–20 hosted Assets.")
            assets = []
            for source in sources:
                import uuid
                key = str(uuid.UUID(source["id"]))
                text = source["text"]
                if not isinstance(text, str) or len(text) > 250_000:
                    raise ValueError("Imported canonical text exceeds its size budget.")
                path = self.imports / f"{key}.md"
                if path.is_symlink():
                    raise PermissionError("Import destination cannot be a symbolic link.")
                path.write_text(text, encoding="utf-8")
                asset = self.register(path)
                asset.name = str(source["name"])[:200]
                asset.document_type = "imported_canonical_text"
                self.service.assets.save_asset(asset)
                assets.append(asset.to_dict())
            result = {"assets": assets, "source_representation": "canonical extracted text, not original file bytes"}
        elif operation == "list_assets":
            result = {"assets": [asset.to_dict() for asset in self.scoped_assets(args, discovery=True)]}
        elif operation == "analyze_asset":
            self.select_model(args["context_model"])
            asset = self.analyze(args["asset_id"], args)
            result = {"asset": asset.to_dict(), "formation_trace": self.metrics.load().get(asset.asset_id)}
        elif operation in {"frame_index", "asset_structure"}:
            assets = self.scoped_assets(args, discovery=True)
            allowed = {asset.asset_id for asset in assets}
            if args.get("asset_id"):
                self.asset(args["asset_id"], args)
                allowed = {args["asset_id"]}
            entries = [entry for entry in self.service.list_frame_index() if entry["asset_id"] in allowed]
            result = {"frames": entries}
        elif operation == "inspect_frame":
            frame = self.frame(args["frame_id"], args)
            if frame.is_current:
                frame = self.service._resolve_frame(frame)
            elif not researcher:
                raise ValueError("Main Agent cannot retrieve a retired Frame as current evidence.")
            result = {"frame": frame.to_dict(), "historical_snapshot": not frame.is_current}
        elif operation == "refine_frame":
            frame = self.frame(args["frame_id"], args)
            if frame.provenance.get("locked"):
                raise PermissionError("Frame is locked. Unlock it before refinement.")
            self.select_model(args["context_model"])
            frames = self.service.refine_frame(frame.frame_id, str(args.get("note", "")))
            result = {"frames": [frame.to_dict() for frame in frames], "edit_origin": args.get("_actor", "main_agent")}
        elif operation in {"edit_frame", "split_frame", "merge_frames", "lock_frame"}:
            result = research_edit(self, operation, args)
        elif operation == "get_package":
            package = self.service.get_package(args["package_id"])
            for asset_id in package.get("assets_used", []):
                self.asset(asset_id, args)
            result = {"package": package}
        elif operation == "prepare_context":
            for asset_id in args.get("asset_ids", []):
                self.asset(asset_id, args)
            self.select_model(args["context_model"])
            formation = []
            for asset in self.scoped_assets(args):
                if not self.service.list_frames(asset.asset_id):
                    self.analyze(asset.asset_id, args)
                    formation.append({"asset_id": asset.asset_id, **self.metrics.load()[asset.asset_id]})
            package = self.service.prepare_context(args["query"], asset_ids=args.get("asset_ids", []))
            meta = self.metrics.load()
            counts = [meta.get(asset_id, {}).get("source_characters") for asset_id in args.get("asset_ids", [])]
            result = {"package": package.to_dict(), "selection_trace": {
                "asset_navigation": getattr(self.service, "asset_selection_traces", []),
                "frame_selection_attempts": getattr(self.service, "selection_traces", [])},
                "formation_trace": formation,
                "source_characters": sum(counts) if all(isinstance(count, int) for count in counts) else None,
                "package_characters": sum(len(frame.content) for frame in package.frames)}
        elif operation in {"baseline_context", "long_context"}:
            import uuid
            query = set(tokenize(str(args.get("query", ""))))
            chunks, source_size = [], 0
            for asset in self.scoped_assets(args):
                text = read_text(self.asset(asset.asset_id, args).location)
                source_size += len(text)
                for start in range(0, len(text), 800 if operation == "baseline_context" else max(1, len(text))):
                    content = text[start:start + 900] if operation == "baseline_context" else text
                    chunks.append({"frame_id": f"baseline_{uuid.uuid4().hex[:12]}", "source_id": asset.asset_id,
                        "summary": asset.name, "content": content, "start_character": start, "end_character": start + len(content),
                        "score": len(query & set(tokenize(content))), "formation_method": operation})
            if operation == "baseline_context":
                chunks.sort(key=lambda chunk: chunk["score"], reverse=True)
                chunks = chunks[:5]
            result = {"package": {"package_id": f"package_{uuid.uuid4().hex[:12]}",
                "status": "context_ready" if chunks else "no_evidence", "frames": chunks,
                "assets_used": sorted({chunk["source_id"] for chunk in chunks}), "model_id": None},
                "source_characters": source_size, "package_characters": sum(len(chunk["content"]) for chunk in chunks),
                "baseline_method": "fixed-character chunks with lexical retrieval; not vector RAG" if operation == "baseline_context" else "all selected canonical source text"}
        else:
            raise ValueError("Unknown bridge operation.")
        result["model_usage"] = list(self._usage)
        result["operation_latency_ms"] = round((time.perf_counter() - started) * 1000)
        return result
