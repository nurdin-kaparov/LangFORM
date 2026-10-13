# LangFORM — Context Intelligence

LangFORM supplies source-grounded context to external agents from owner-approved
local Assets. A local SLM reads and summarizes the collection, creates hierarchical
Context Frames, and maintains a compact index. Requests select relevant original
evidence rather than requiring a consuming agent to reread every complete source.
Efficiency depends on the device, model, and collection; evidence coverage still
needs verification.

The public **`/read-me`** is the external-agent integration guide: delegation
boundaries, local MCP and Python usage, authenticated project API requests,
asynchronous completion, Package contracts, and safe evidence consumption.
Setup and internal workflow details are available as secondary reference.

**Version 0.3.0 · MIT · Python 3.11+**

## Projects and direct Context SLM interaction

Use **Local Connections → Download setup** for guided local installation and
pairing without a repository checkout. See [local setup details](docs/LOCAL_SETUP.md).

The active interface is **Projects**, not a test console. Set up your local SLM
first, then select an available SLM from your connected laptop while creating a
project. Projects let you evaluate the Context Subagent and create reusable Context
Packages. Inspect processing and selection, then use **Download Package (JSON)**
on a completed evidence Package to save its original content and source references.
Interact directly with that Context SLM. Every prompt first reaches the SLM
for an intent decision: **Context Processing** or **Context Packaging**. Processing
reads approved sources, forms semantic Frames, generates source summaries and
updates the master index; packaging selects existing source-grounded context.
There is no internal hosted master model, search, or cloud-model fallback.

Local file selection grants access through the workstation bridge, not browser
file uploads. Explicit HTTPS URLs are source inputs, not search requests.
Summaries, Frames, progress and returned package evidence are stored in the
authenticated hosted application; originals remain local and unchanged.
Update your local LangFORM source and restart the bridge for the new objectives.
See [Projects architecture and API](docs/PROJECTS.md) and `/read-me` for setup and
limitations. Historical records are preserved outside the new conversation.

### Current orchestration

1. Set up Ollama and an installed supported SLM, run the guided local launcher,
   and approve pairing. Folder access is optional and explicitly granted.
2. Create a project using an available SLM reported by the connected laptop.
3. The hosted application checks ownership, local health, and model availability;
   prompt execution also requires affirmative bridge protocol compatibility.
4. Every prompt first invokes the local SLM to decide **processing** or
   **packaging**, including prompts with standardized intent hints.
5. Processing resolves explicitly approved sources, registers scoped Assets,
   forms validated semantic Frames, produces local source summaries, and returns
   the scoped master index. Packaging selects existing Frames and returns their
   original evidence plus a grounded local reply; it does not discover sources.
6. The bridge polls outbound jobs and reports real progress. The hosted app
   persists operations, returned metadata, and evidence views for inspection.
   Cached completed jobs retry delivery without repeating completed local work.

The master index is data, not a master LLM. External consuming agents may request
Packages through the API or MCP; there is no internal hosted model fallback or
search tool. Cancellation and failure are not whole-project rollback guarantees.
For responsibilities, phase order, readiness, privacy, recovery, and examples,
use the expanded `/read-me`. The guided launcher still requires Python 3.11+ and
does not start a background service.

Windows executable packaging is available separately: see
[Windows executable build and runtime guidance](docs/WINDOWS_EXECUTABLE.md).
It bundles Python into `LangFORM.exe`; a successful Windows build is required
before distributing it. The existing website setup download remains the Python
launcher until a verified executable is connected to its download channel.

## Hierarchical Context Frame Index

Context Frames can overlap and nest: a broad parent remains retrievable alongside independently useful children. Semantic parent links are separate from revision lineage. A project's **Frames and index** tab shows its hierarchy; the core `/api/frames/index` endpoint returns compact metadata without original source content.

Python exposes `service.list_frame_index()` and the MCP `list_frame_index` tool. Its persistent index is separate from source evidence. The SLM selects existing IDs, include modes and priorities through strict JSON; an algorithm resolves their typed source coordinates afterward. Changed sources fail explicitly. A child already covered by a selected parent retains its semantic guidance without repeating that evidence.


### Native spreadsheet evidence

XLSX frames use exact worksheet names and inclusive cell rectangles; CSV frames use inclusive logical record and positional column ranges. Coordinates are one-based, with stable column letters (`A`, `B`, …), so duplicate or empty headers are unambiguous. Quoted CSV newlines stay in their original record. Empty cells, formulas, rich text and merged-cell references remain original evidence; formulas are not recalculated by LangFORM.

The semantic model can choose useful broad table parents and narrower row **and column** children. Without a configured model, Python creates explicit whole-sheet structural drafts, not fixed row chunks. The metadata-only index includes `source_coordinates` / `sourceCoordinates` and `source_version` / `sourceVersion`. Spreadsheet versions are SHA-256 hashes of original file bytes. Retrieval and refinement reject changed bytes, invalid ranges, unknown frame IDs and cross-sheet parent relationships. Legacy paragraph frames remain readable; paragraph fields on native frames are compatibility aliases, not cell coordinates.

Evidence packages retain native coordinates, source versions and original cell values. Project conversations show returned evidence and selection traces; Python's `ContextPackage.to_dict()` and CLI/MCP outputs include the same provenance. Legacy package export endpoints remain available. Covered duplicate ranges point to one containing evidence frame instead of repeating its content. Legacy uploaded evidence requires both the authenticated Asset owner and a matching private storage owner. Spreadsheet processing is limited to 50 MB and 250,000 rectangular cells per source, with explicit errors above those limits.

LangFORM is a local-first **Context Subagent**. It indexes authorized **Assets**, represents their meaning with source-linked **Context Frames**, and forms evidence-only **Context Packages** for a separate main agent.

The core Context Subagent does not plan tasks or execute general tools. The
project interface saves interactions and presents local SLM replies grounded in
the selected context. It is not a general-purpose assistant; an external master
agent can use its context packages for broader reasoning.

## What is implemented

- A Python package and CLI with local Asset registration, document extraction, persistent frame revisions, Ollama model management, Context Formation, and MCP stdio tools.
- An authenticated research dashboard with Assets, source structures, paragraphs, semantic frames, purposeful refinement, Context Requests, package inspectors, model status, activity, configurable selection budgets, and a separate fixed-character retrieval baseline.
- An Express REST API with a versioned OpenAPI contract and generated clients.
- Private uploaded files in App Storage; queryable metadata and immutable package snapshots in PostgreSQL.
- Public dashboard `/read-me` documentation.

The Context Intelligence foundation now includes a separate multistep **Main Agent Test Harness**, paired local Context SLM bridge, saved operational replay, and experiment exports. See [Test Harness setup](docs/TEST-HARNESS.md) and [research scope](docs/RESEARCH.md) for measurement boundaries and remaining limitations.

## Local Python quick start

```bash
pip install -e ".[ollama,documents,mcp,dev]"
ollama serve
langform model-install qwen3:4b
langform model-select qwen3:4b
langform analyze ./knowledge.md
langform frames
langform query "Find evidence about the retrieval architecture."
langform packages
```

Each CLI invocation uses `.langform` unless `--workspace /path/to/workspace` is specified before the command. Do not commit that directory: it contains local source metadata and evidence.

```python
from langform import ContextSubagent

context = ContextSubagent(workspace=".langform")
context.select_model("qwen3:4b")  # verifies an installed Ollama model
asset = context.register_asset("./knowledge.md")
context.analyze_asset(asset.asset_id)
package = context.prepare_context(
    "Find evidence describing deterministic retrieval.",
    top_k=5,
    asset_ids=[asset.asset_id],
)
print(package.to_dict())  # source excerpts, coordinates, summaries, selection reasons
```

Without a selected model, Python extraction creates explicitly labeled **structural drafts**, not SLM-formed semantic frames. Context selection returns `model_required` instead of presenting lexical matches as model decisions. `python -m langform demo` demonstrates this boundary without downloading model weights.

### Local model catalog

| Ollama tag | License | Estimated practical system RAM |
|---|---|---:|
| `qwen3:1.7b` | Apache-2.0 | 3 GB |
| `qwen3:4b` | Apache-2.0 | 6 GB |
| `phi4-mini:3.8b` | MIT | 6 GB |
| `gemma3:4b` | Gemma Terms of Use | 8 GB |

These are estimates, not guarantees. Quantization, concurrent requests, and context length affect memory. Review each model's linked license in the Model Manager. Models are not bundled or claimed installed: availability is checked against Ollama.

## Adaptive Context Frames

Frame depth is semantic, not a fixed token, row, line, or paragraph count. A frame may represent one independent requirement, several related paragraphs, a complete section, or one coherent dataset.

The local model proposes source ranges, then reviews them for useful splits or merges. Initial formation stops after two bounded passes. Large model-input batches are transport limits, **not** frame boundaries. Ranges must cover source coordinates without gaps; useful nested or overlapping ranges are permitted. Summaries never replace original evidence.

Later refinement requires an explicit purpose and preserves the prior frame, its parent relationship, and version. It is not continuous background fragmentation.

The dashboard uses hierarchical Asset → structural region → frame-description selection. Candidate budgets are configurable: preferred 30, soft maximum 60, hard maximum 100 by default. The Python package currently uses transparent lexical candidate narrowing before mandatory local-model selection.

## MCP

```bash
LANGFORM_WORKSPACE=/absolute/path/.langform langform-mcp
```

Tools expose model management, authorized Asset registration, analysis, frame inspection/refinement, context requests, and saved packages. There are no shell, planning, conversation-memory, or arbitrary action tools. See [integration examples](docs/INTEGRATION.md).

## Dashboard development

```bash
pnpm install
pnpm --filter @workspace/db run push       # development database only
pnpm --filter @workspace/api-server run dev
pnpm --filter @workspace/langform-dashboard run dev
```

Replit runs the registered workflows with managed ports and artifact routing. The hosted API's Ollama address refers to **the API server's machine**, not the user's browser. No local model service is assumed available in a hosted deployment.

Uploaded files, text, and public HTTPS pages can be processed by the dashboard. Arbitrary workstation paths are intentionally rejected by the hosted API; use the local Python package instead. Python URL registration is metadata-only; Python webpage extraction is not implemented.

## Verify

```bash
python -m pytest
pnpm --filter @workspace/api-spec run codegen
pnpm --filter @workspace/api-server run typecheck
pnpm --filter @workspace/langform-dashboard run typecheck
PORT=5173 BASE_PATH=/ pnpm --filter @workspace/langform-dashboard run build
```

Model tests use explicit test doubles and do not claim live-model accuracy. The MCP test uses the official SDK's in-memory client.

## Repository organization and history

`src/langform/` is the canonical Python package. The previous root package and duplicate nested `LangFORM/` tree were imported from the existing `nurdin-kaparov/LangFORM` repository through a history-linked Git subtree. The duplicate is not an active second package; historical source remains in Git history. Earlier architectural documents are retained in `docs/archive/v0.0.2/` as historical material, not current product instructions.

- `artifacts/langform-dashboard/` — dashboard
- `artifacts/api-server/` — REST API and Ollama adapter
- `lib/api-spec/openapi.yaml` — API contract
- `lib/db/src/schema/` — PostgreSQL schema
- `src/langform/` — local Python package and MCP server
- `tests/python/` — package and protocol tests
- `docs/` — architecture, integration, and research boundaries

The working feature branch is `feat/langform-context-intelligence`; main is not replaced. Versioning follows semantic versioning. No PyPI release is implied by this workspace build.
