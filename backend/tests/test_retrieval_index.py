from pathlib import Path

from manfriday.retrieval import (
    ingest_retrieval_sources,
    load_index_or_ingest_retrieval_sources,
    load_retrieval_index,
    write_retrieval_index,
)

FIXTURES = Path(__file__).parent / "fixtures" / "retrieval"


def test_retrieval_index_round_trips_source_and_chunk_metadata(tmp_path: Path) -> None:
    summary = ingest_retrieval_sources(local_docs_dir=FIXTURES, online_sources_path=None)

    path = write_retrieval_index(summary, tmp_path)
    loaded = load_retrieval_index(tmp_path)

    assert path.exists()
    assert loaded is not None
    assert [source.uri for source in loaded.sources] == [
        "notes.txt",
        "workbench_manual.md",
    ]
    assert [chunk.chunk_id for chunk in loaded.chunks] == [
        chunk.chunk_id for chunk in summary.chunks
    ]
    assert loaded.source_results[0].source.source_id == loaded.sources[0].source_id


def test_load_index_or_ingest_prefers_existing_stale_index(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    first_root.mkdir()
    (first_root / "stale.txt").write_text("stale indexed clamp text", encoding="utf-8")
    summary = ingest_retrieval_sources(local_docs_dir=first_root, online_sources_path=None)
    write_retrieval_index(summary, tmp_path / "index")
    second_root = tmp_path / "second"
    second_root.mkdir()
    (second_root / "fresh.txt").write_text("fresh live text", encoding="utf-8")

    loaded = load_index_or_ingest_retrieval_sources(
        local_docs_dir=second_root,
        online_sources_path=None,
        index_dir=tmp_path / "index",
    )

    assert [source.uri for source in loaded.sources] == ["stale.txt"]
    assert "stale indexed" in loaded.chunks[0].text


def test_load_index_or_ingest_falls_back_when_index_missing(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "fresh.txt").write_text("fresh live text", encoding="utf-8")

    loaded = load_index_or_ingest_retrieval_sources(
        local_docs_dir=root,
        online_sources_path=None,
        index_dir=tmp_path / "missing-index",
    )

    assert [source.uri for source in loaded.sources] == ["fresh.txt"]


def test_load_index_or_ingest_falls_back_when_index_is_unreadable(tmp_path: Path) -> None:
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "index.json").write_text("{not json", encoding="utf-8")
    root = tmp_path / "docs"
    root.mkdir()
    (root / "fresh.txt").write_text("fresh live text", encoding="utf-8")

    loaded = load_index_or_ingest_retrieval_sources(
        local_docs_dir=root,
        online_sources_path=None,
        index_dir=index_dir,
    )

    assert [source.uri for source in loaded.sources] == ["fresh.txt"]
