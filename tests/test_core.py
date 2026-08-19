from pathlib import Path

from langform import LangFORM


def test_end_to_end(tmp_path: Path):
    sample = tmp_path / "sample.txt"
    sample.write_text(
        "LangFORM creates Context Frames.\n\n"
        "Retrieval selects relevant context for language models.",
        encoding="utf-8",
    )

    lf = LangFORM(workspace=tmp_path / ".langform")
    asset = lf.register_asset(str(sample))
    analyzed = lf.analyze_asset(asset.asset_id)

    assert analyzed.status == "analyzed"
    assert analyzed.frame_ids

    package = lf.prepare_context("How does retrieval select context?")
    assert package.status == "context_ready"
    assert package.context_frames


def test_memory(tmp_path: Path):
    lf = LangFORM(workspace=tmp_path / ".langform")
    lf.add_memory("user", "Remember this.")
    assert lf.memory.recent(1)[0].content == "Remember this."
    lf.clear_memory()
    assert lf.memory.list() == []
