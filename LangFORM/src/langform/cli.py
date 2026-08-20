from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .core import LangFORM
from .bridge import serve_bridge


def _print(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def run_demo() -> int:
    with tempfile.TemporaryDirectory(prefix="langform_demo_") as td:
        root = Path(td)
        sample = root / "sample.txt"
        sample.write_text(
            "LangFORM manages context for LLM applications.\n\n"
            "Context Frames represent coherent units of meaning.\n\n"
            "Retrieval selects relevant frames instead of sending every available file.",
            encoding="utf-8",
        )

        lf = LangFORM(workspace=root / ".langform")
        asset = lf.register_asset(str(sample))
        lf.analyze_asset(asset.asset_id)
        lf.add_memory("user", "I am interested in how LangFORM handles retrieval.")
        package = lf.prepare_context("How does LangFORM use Context Frames for retrieval?", top_k=3)

        print("LangFORM demo completed successfully.\n")
        _print(package.to_dict())
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="langform", description="LangFORM CLI")
    parser.add_argument("--workspace", default=".langform", help="LangFORM workspace directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="Run a self-contained LangFORM demo")

    p_bridge = sub.add_parser("bridge", help="Run the local Ollama/Gemma bridge")
    p_bridge.add_argument("--host", default=None)
    p_bridge.add_argument("--port", type=int, default=8765)
    p_bridge.add_argument("--model", default=None)
    p_bridge.add_argument("--ollama-url", default=None)
    p_bridge.add_argument("--token", default=None)
    p_bridge.add_argument("--allowed-origin", default=None)

    p_reg = sub.add_parser("register", help="Register an asset")
    p_reg.add_argument("reference")
    p_reg.add_argument("--uploaded", action="store_true")

    p_an = sub.add_parser("analyze", help="Register and analyze a local file")
    p_an.add_argument("path")
    p_an.add_argument("--uploaded", action="store_true")

    p_q = sub.add_parser("query", help="Retrieve Context Frames for a query")
    p_q.add_argument("query")
    p_q.add_argument("--top-k", type=int, default=5)

    p_assets = sub.add_parser("assets", help="List registered assets")

    p_mem = sub.add_parser("memory-add", help="Add conversation memory")
    p_mem.add_argument("role", choices=["user", "assistant", "system"])
    p_mem.add_argument("content")

    sub.add_parser("memory-clear", help="Clear conversation memory")

    args = parser.parse_args(argv)

    if args.command == "demo":
        return run_demo()

    if args.command == "bridge":
        serve_bridge(
            host=args.host,
            port=args.port,
            model=args.model,
            ollama_url=args.ollama_url,
            token=args.token,
            allowed_origin=args.allowed_origin,
        )
        return 0

    lf = LangFORM(workspace=args.workspace)

    if args.command == "register":
        asset = lf.register_asset(args.reference, uploaded=args.uploaded)
        _print(asset.to_dict())
        return 0

    if args.command == "analyze":
        asset = lf.register_asset(args.path, uploaded=args.uploaded)
        asset = lf.analyze_asset(asset.asset_id)
        _print(asset.to_dict())
        return 0

    if args.command == "query":
        package = lf.prepare_context(args.query, top_k=args.top_k)
        _print(package.to_dict())
        return 0

    if args.command == "assets":
        _print([a.to_dict() for a in lf.list_assets()])
        return 0

    if args.command == "memory-add":
        _print(lf.add_memory(args.role, args.content).to_dict())
        return 0

    if args.command == "memory-clear":
        lf.clear_memory()
        print("Conversation memory cleared.")
        return 0

    return 1
