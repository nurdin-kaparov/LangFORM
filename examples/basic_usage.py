from pathlib import Path
from tempfile import TemporaryDirectory

from langform import LangFORM


with TemporaryDirectory() as td:
    td = Path(td)
    note = td / "notes.txt"
    note.write_text(
        "LangFORM prepares Context Frames for model interactions.\n\n"
        "Its retrieval layer selects relevant information for a query.",
        encoding="utf-8",
    )

    lf = LangFORM(workspace=td / ".langform")
    asset = lf.register_asset(str(note))
    lf.analyze_asset(asset.asset_id)

    package = lf.prepare_context("What does LangFORM retrieval do?")
    print(package.to_dict())
