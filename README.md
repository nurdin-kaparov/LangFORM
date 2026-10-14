# LangFORM 0.3.0

A local-first Python package for organizing approved sources into source-grounded Context Packages for an external agent.

LangFORM registers local Assets, extracts supported document structure, uses an Ollama-hosted local SLM to form and select semantic Context Frames, maintains an index, and retrieves original evidence for a question. The consuming application remains responsible for its own tools, planning, and final answer.

## Requirements

- Python 3.11 or later
- Ollama and a supported model installed locally for semantic formation and context selection
- Model weights are not included or downloaded automatically

## Install from this repository

```bash
git clone https://github.com/nurdin-kaparov/LangFORM.git
cd LangFORM
python -m venv .venv
# Activate .venv, then:
python -m pip install -e ".[all]"
```

The `all` extra installs document readers, the Ollama client, and MCP support. Install only the extras your integration needs by consulting `pyproject.toml`.

## Python usage

```python
from langform import ContextSubagent

context = ContextSubagent(workspace=".langform")
context.select_model("<an installed supported Ollama model tag>")

# Register only a file the user has approved for this workspace.
asset = context.register_asset("./knowledge.md")
context.analyze_asset(asset.asset_id)

package = context.prepare_context(
    "What evidence supports the proposed deadline?",
    top_k=5,
    asset_ids=[asset.asset_id],
)

if package.status != "context_ready":
    raise RuntimeError(f"Context is not ready: {package.status}")

print(package.to_dict())  # original evidence, coordinates, and selection details
```

Check the returned Package status and original source evidence before using it. Generated summaries and Frame descriptions guide retrieval; they are not substitutes for source content. Changed or unavailable sources and unavailable models must be reported explicitly, not silently replaced with outside information.

## MCP and command line

Install the MCP extra, then configure the consuming application to launch `langform-mcp` over stdio. Set `LANGFORM_WORKSPACE` to a private local workspace. MCP entry points are called by the external application; they are not autonomous tools given to the Context SLM.

The `langform` command provides local setup, model, Asset, analysis, and Package operations. Run `langform --help` or `langform <command> --help` to inspect the installed command options.

## Scope and privacy

- The Context SLM reads supplied, approved sources; it does not search the internet or discover additional sources.
- Source registration does not authorize arbitrary local paths. Grant access only to files the owner approves.
- Keep `.langform` workspaces and returned Packages private; they may contain source metadata and original excerpts.
- The Python package, local workspace, hosted project, and any external agent are separate components. Their credentials, scope, and records are not interchangeable.

## Test

```bash
python -m pytest
```

## Windows companion

Packaging source is in `local-setup/`. Build the Windows executable on a Windows x64 machine with Python 3.11 using `local-setup/build-windows.ps1`. The executable is not included in this source update; do not treat packaging sources as a built or signed installer.

MIT License.
