# LangFORM

**Version:** v0.0.2-2026.08.18

LangFORM is an open-source context, memory, retrieval, and orchestration framework for LLM and agentic AI applications.

Its purpose is simple:

> Give models the right context, not all available context.

LangFORM can register user-authorized assets, extract text, create semantically useful Context Frames, store metadata, retrieve relevant frames for a user query, maintain lightweight conversation memory, and prepare a structured Context Package for a Main LLM or surrounding agent application.

## What Works in v0.0.2

This version includes working Python code for:

- Asset registration
- Local-file references
- Uploaded-asset registration
- Technical and semantic metadata
- Text extraction from TXT, MD, JSON, and CSV files
- Optional PDF, DOCX, and XLSX extraction when the related packages are installed
- Context Frame creation
- Context Frame persistence
- Simple relevance retrieval
- Conversation memory
- Context Package creation
- JSON-based registries
- Optional local SLM communication through Ollama
- Command-line interface
- Basic tests

The framework is intentionally UI-independent. A developer can use LangFORM underneath a web app, desktop app, API, CLI, or another agent runtime.

## Installation

Clone the repository:

```bash
git clone https://github.com/nurdin-kaparov/LangFORM.git
cd LangFORM
```

Create and activate a virtual environment if desired, then install:

```bash
pip install -e .
```

Optional file-reader support:

```bash
pip install -e ".[documents]"
```

Optional Ollama support:

```bash
pip install -e ".[ollama]"
```

Install everything:

```bash
pip install -e ".[all]"
```

## Quick Test

After installation:

```bash
langform demo
```

or:

```bash
python -m langform demo
```

This runs a self-contained demo without requiring an external LLM.

## Analyze a File

```bash
langform analyze path/to/file.txt
```

LangFORM will:

1. register the file as an Asset,
2. extract its text,
3. generate metadata,
4. create Context Frames,
5. store the records locally.

## Ask for Context

```bash
langform query "What does the document say about memory?"
```

LangFORM searches stored Context Frames and returns a Context Package as JSON.

## Python Example

```python
from langform import LangFORM

lf = LangFORM(workspace=".langform")

asset = lf.register_asset("notes.txt")
lf.analyze_asset(asset.asset_id)

package = lf.prepare_context(
    "What does the file say about retrieval?",
    top_k=5,
)

print(package.to_dict())
```

## Optional Ollama Local SLM

If Ollama is running locally:

```python
from langform.models import OllamaSLM

slm = OllamaSLM(model="gemma3:4b")
print(slm.generate("Summarize this sentence: LangFORM manages context."))
```

The core LangFORM package does not require Ollama to run.

## Asset Handling

LangFORM distinguishes among:

- `local_path`: the original file remains where the user keeps it.
- `uploaded_file`: the application may copy the uploaded file into LangFORM's managed `uploaded_assets` folder.
- `web_url`: registered as a reference in v0.0.2. Automatic downloading is intentionally not performed by the core.

## Workspace

Runtime data is stored separately from source code:

```text
.langform/
├── registry/
│   └── assets.json
├── frames/
│   └── frames.json
├── memory/
│   └── conversation.json
└── uploaded_assets/
```

The workspace can be changed when creating `LangFORM`.

## Current Retrieval Method

v0.0.2 uses a transparent keyword-overlap scoring method. It is deliberately simple and dependency-free.

Later versions can add embedding-based retrieval, hybrid retrieval, reranking, and more advanced semantic orchestration without changing the basic Context Frame interface.

## Important Boundary

LangFORM focuses on context intelligence.

The surrounding platform or agent runtime remains responsible for general-purpose actions such as:

- web search
- Python execution
- shell execution
- browser actions
- email
- external API calls

LangFORM can receive results from those tools and convert useful information into context.

## Core Files

- `Terminologies.md`
- `System_Instructions.md`
- `Orchestration_Protocol.md`

These files define LangFORM's shared language, local SLM role, and structured communication principles.

## License

MIT License.
