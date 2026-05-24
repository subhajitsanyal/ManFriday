from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from manfriday.retrieval import LocalDocumentIngestor, SourceMetadata, ingest_local_documents

FIXTURES = Path(__file__).parent / "fixtures" / "retrieval"
PDF_FIXTURES = Path(__file__).parent / "fixtures" / "retrieval_pdf"
NOW = datetime(2026, 5, 24, 3, 0, tzinfo=UTC)


def test_local_markdown_and_text_ingestion_returns_source_and_chunk_metadata() -> None:
    summary = LocalDocumentIngestor(now_fn=lambda: NOW).ingest_directory(FIXTURES)

    assert summary.status == "completed"
    assert summary.local_files_indexed == 2
    assert summary.urls_indexed == 0
    assert summary.failed == ()
    assert [(item.source, item.reason) for item in summary.skipped] == [
        ("ignore.bin", "unsupported_file_type"),
    ]
    assert [source.uri for source in summary.sources] == ["notes.txt", "workbench_manual.md"]
    assert all(isinstance(source, SourceMetadata) for source in summary.sources)
    assert {chunk.source_id for chunk in summary.chunks} == {
        source.source_id for source in summary.sources
    }
    assert all(chunk.chunk_id.startswith(f"{chunk.source_id}_chunk_") for chunk in summary.chunks)
    assert all(chunk.token_count > 0 for chunk in summary.chunks)
    assert all(chunk.created_at == NOW and chunk.updated_at == NOW for chunk in summary.chunks)


def test_markdown_ingestion_extracts_title_sections_hash_and_manual_flag() -> None:
    summary = LocalDocumentIngestor(now_fn=lambda: NOW).ingest_directory(FIXTURES)
    source = next(source for source in summary.sources if source.uri == "workbench_manual.md")
    chunks = [chunk for chunk in summary.chunks if chunk.source_id == source.source_id]

    assert source.source_id == _source_id("workbench_manual.md")
    assert source.title == "Workbench Safety Manual"
    assert source.type == "local_file"
    assert source.manufacturer_or_manual is True
    assert source.retrieved_at == NOW
    expected_hash = sha256((FIXTURES / "workbench_manual.md").read_bytes()).hexdigest()
    assert source.content_hash == expected_hash
    assert [chunk.section for chunk in chunks] == [
        "Workbench Safety Manual",
        "Clamp Setup",
        "Battery Notes",
    ]
    assert chunks[0].text == "Manufacturer guidance for using the bench camera and power tools."
    assert chunks[1].chunk_index == 1
    assert chunks[1].page is None
    assert chunks[1].bm25_score is None
    assert chunks[1].vector_score is None
    assert chunks[1].combined_score is None


def test_text_ingestion_uses_stem_title_and_stable_ids() -> None:
    first = LocalDocumentIngestor(now_fn=lambda: NOW).ingest_directory(FIXTURES)
    second = LocalDocumentIngestor(now_fn=lambda: NOW).ingest_directory(FIXTURES)
    source = next(source for source in first.sources if source.uri == "notes.txt")
    chunks = [chunk for chunk in first.chunks if chunk.source_id == source.source_id]

    assert source.source_id == _source_id("notes.txt")
    assert source.title == "notes"
    assert source.manufacturer_or_manual is False
    assert [source.source_id for source in first.sources] == [
        source.source_id for source in second.sources
    ]
    assert [chunk.chunk_id for chunk in first.chunks] == [chunk.chunk_id for chunk in second.chunks]
    assert chunks[0].text == (
        "Use the blue bin for spare clamps.\n\n"
        "The small hex key belongs with the camera mount."
    )


def test_ingestion_skips_file_that_exceeds_size_limit() -> None:
    summary = LocalDocumentIngestor(max_file_size_bytes=10, now_fn=lambda: NOW).ingest_directory(
        FIXTURES,
    )

    assert summary.local_files_indexed == 0
    assert ("notes.txt", "file_too_large") in {
        (item.source, item.reason) for item in summary.skipped
    }
    assert ("workbench_manual.md", "file_too_large") in {
        (item.source, item.reason) for item in summary.skipped
    }


def test_pdf_ingestion_extracts_page_text_and_page_metadata() -> None:
    summary = LocalDocumentIngestor(now_fn=lambda: NOW).ingest_directory(PDF_FIXTURES)

    assert summary.status == "completed"
    assert summary.local_files_indexed == 1
    assert summary.failed == ()
    source = summary.sources[0]
    assert source.title == "camera mount manual"
    assert source.uri == "camera_mount_manual.pdf"
    assert source.manufacturer_or_manual is True
    assert [chunk.page for chunk in summary.chunks] == [1, 2]
    assert summary.chunks[0].text == "PDF camera mount manual page one"
    assert summary.chunks[1].text == "Tighten the mount screw to 4 Nm on page two"


def test_pdf_ingestion_skips_pdf_that_exceeds_page_limit() -> None:
    summary = LocalDocumentIngestor(max_pdf_pages=1, now_fn=lambda: NOW).ingest_directory(
        PDF_FIXTURES,
    )

    assert summary.local_files_indexed == 0
    assert [(item.source, item.reason) for item in summary.skipped] == [
        ("camera_mount_manual.pdf", "pdf_page_limit_exceeded"),
    ]


def test_pdf_ingestion_skips_pdf_that_exceeds_size_limit() -> None:
    summary = LocalDocumentIngestor(max_file_size_bytes=10, now_fn=lambda: NOW).ingest_directory(
        PDF_FIXTURES,
    )

    assert summary.local_files_indexed == 0
    assert [(item.source, item.reason) for item in summary.skipped] == [
        ("camera_mount_manual.pdf", "file_too_large"),
    ]


def test_pdf_ingestion_reports_extraction_failure(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj\n")

    summary = LocalDocumentIngestor(now_fn=lambda: NOW).ingest_directory(tmp_path)

    assert summary.status == "completed_with_errors"
    assert summary.local_files_indexed == 0
    assert [(item.source, item.reason) for item in summary.failed] == [
        ("broken.pdf", "pdf_extract_failed"),
    ]


def test_ingest_local_documents_helper_uses_default_ingestor() -> None:
    summary = ingest_local_documents(FIXTURES)

    assert summary.status == "completed"
    assert summary.local_files_indexed == 2


def _source_id(relative_path: str) -> str:
    return f"local_{sha256(relative_path.encode('utf-8')).hexdigest()[:16]}"
