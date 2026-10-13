from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .core import LangFORM


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
        package = lf.prepare_context("How does LangFORM use Context Frames for retrieval?", top_k=3)

        print("Local extraction demo completed. Context selection requires an installed model.\n")
        _print(package.to_dict())
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="langform", description="LangFORM CLI")
    parser.add_argument("--workspace", default=".langform", help="LangFORM workspace directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="Run a self-contained LangFORM demo")

    p_reg = sub.add_parser("register", help="Register an asset")
    p_reg.add_argument("reference")
    p_reg.add_argument("--uploaded", action="store_true")

    p_an = sub.add_parser("analyze", help="Register and analyze a local file")
    p_an.add_argument("path")
    p_an.add_argument("--uploaded", action="store_true")

    p_q = sub.add_parser("query", help="Retrieve Context Frames for a query")
    p_q.add_argument("query")
    p_q.add_argument("--top-k", type=int, default=5)

    sub.add_parser("assets", help="List registered Assets")
    p_frames = sub.add_parser("frames", help="List Context Frames")
    p_frames.add_argument("--asset-id")
    p_frames.add_argument("--history", action="store_true")
    sub.add_parser("models", help="Show actual local model availability")
    p_install = sub.add_parser("model-install", help="Download a supported model via Ollama")
    p_install.add_argument("model_id")
    p_select = sub.add_parser("model-select", help="Select an installed local model")
    p_select.add_argument("model_id")
    p_refine = sub.add_parser("refine", help="Create a purposeful frame revision")
    p_refine.add_argument("frame_id")
    p_refine.add_argument("--note", required=True)
    sub.add_parser("packages", help="List saved Context Packages")
    sub.add_parser("mcp", help="Serve the local MCP interface over stdio")

    args = parser.parse_args(argv)

    if args.command == "demo":
        return run_demo()

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

    if args.command == "frames":
        _print([frame.to_dict() for frame in lf.list_frames(args.asset_id, args.history)])
        return 0
    if args.command == "models":
        _print(lf.model_status())
        return 0
    if args.command == "model-install":
        lf.install_model(args.model_id, on_progress=_print)
        return 0
    if args.command == "model-select":
        _print({"selected_model_id": lf.select_model(args.model_id)})
        return 0
    if args.command == "refine":
        _print([frame.to_dict() for frame in lf.refine_frame(args.frame_id, args.note)])
        return 0
    if args.command == "packages":
        _print(lf.list_packages())
        return 0
    if args.command == "mcp":
        import os
        os.environ["LANGFORM_WORKSPACE"] = args.workspace
        from .mcp_server import main as serve
        serve()
        return 0

    return 1
