from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from manfriday.retrieval.models import (
    ChunkMetadata,
    IngestionFailure,
    IngestionSkipped,
    IngestionSummary,
    SourceIngestionResult,
    SourceMetadata,
)

SUPPORTED_LOCAL_EXTENSIONS = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class LocalDocumentIngestor:
    max_file_size_bytes: int = 2_000_000
    max_chunk_chars: int = 1_200
    now_fn: Callable[[], datetime] | None = None

    def ingest_directory(self, root: Path) -> IngestionSummary:
        root = root.resolve()
        if not root.exists():
            return IngestionSummary(
                status="completed",
                failed=(IngestionFailure(source=str(root), reason="directory_not_found"),),
            )
        results: list[SourceIngestionResult] = []
        skipped: list[IngestionSkipped] = []
        failed: list[IngestionFailure] = []
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            relative_path = path.relative_to(root).as_posix()
            if path.suffix.lower() not in SUPPORTED_LOCAL_EXTENSIONS:
                skipped.append(
                    IngestionSkipped(source=relative_path, reason="unsupported_file_type"),
                )
                continue
            size_bytes = path.stat().st_size
            if size_bytes > self.max_file_size_bytes:
                skipped.append(IngestionSkipped(source=relative_path, reason="file_too_large"))
                continue
            try:
                results.append(self.ingest_file(path=path, root=root))
            except UnicodeDecodeError:
                failed.append(IngestionFailure(source=relative_path, reason="decode_failed"))
        sources = tuple(result.source for result in results)
        chunks = tuple(chunk for result in results for chunk in result.chunks)
        return IngestionSummary(
            status="completed" if not failed else "completed_with_errors",
            local_files_indexed=len(results),
            skipped=tuple(skipped),
            failed=tuple(failed),
            sources=sources,
            chunks=chunks,
            source_results=tuple(results),
        )

    def ingest_file(self, *, path: Path, root: Path) -> SourceIngestionResult:
        content = path.read_bytes()
        text = content.decode("utf-8")
        relative_path = path.relative_to(root).as_posix()
        content_hash = sha256(content).hexdigest()
        timestamp = self._now()
        source = SourceMetadata(
            source_id=_source_id(relative_path),
            type="local_file",
            title=_title_for(path, text),
            uri=relative_path,
            retrieved_at=timestamp,
            manufacturer_or_manual=_looks_like_manual(relative_path, text),
            content_hash=content_hash,
            size_bytes=len(content),
            created_at=timestamp,
            updated_at=timestamp,
        )
        chunks = tuple(
            _chunk_metadata(
                source=source,
                text=chunk_text,
                chunk_index=index,
                section=section,
                timestamp=timestamp,
            )
            for index, (section, chunk_text) in enumerate(
                _chunks_for(text, max_chunk_chars=self.max_chunk_chars),
            )
        )
        return SourceIngestionResult(source=source, chunks=chunks)

    def _now(self) -> datetime:
        now = self.now_fn() if self.now_fn is not None else datetime.now(UTC)
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now


def ingest_local_documents(root: Path) -> IngestionSummary:
    return LocalDocumentIngestor().ingest_directory(root)


def merge_ingestion_summaries(*summaries: IngestionSummary) -> IngestionSummary:
    failed = tuple(item for summary in summaries for item in summary.failed)
    skipped = tuple(item for summary in summaries for item in summary.skipped)
    sources = tuple(source for summary in summaries for source in summary.sources)
    chunks = tuple(chunk for summary in summaries for chunk in summary.chunks)
    source_results = tuple(result for summary in summaries for result in summary.source_results)
    return IngestionSummary(
        status=(
            "completed_with_errors"
            if any(summary.status == "completed_with_errors" for summary in summaries)
            else "completed"
        ),
        local_files_indexed=sum(summary.local_files_indexed for summary in summaries),
        urls_indexed=sum(summary.urls_indexed for summary in summaries),
        skipped=skipped,
        failed=failed,
        sources=sources,
        chunks=chunks,
        source_results=source_results,
    )


def _source_id(relative_path: str) -> str:
    return f"local_{sha256(relative_path.encode('utf-8')).hexdigest()[:16]}"


def _chunk_id(source_id: str, chunk_index: int, text: str) -> str:
    text_hash = sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{source_id}_chunk_{chunk_index:04d}_{text_hash}"


def _chunk_metadata(
    *,
    source: SourceMetadata,
    text: str,
    chunk_index: int,
    section: str | None,
    timestamp: datetime,
) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=_chunk_id(source.source_id, chunk_index, text),
        source_id=source.source_id,
        text=text,
        chunk_index=chunk_index,
        page=None,
        section=section,
        token_count=len(text.split()),
        content_hash=sha256(text.encode("utf-8")).hexdigest(),
        created_at=timestamp,
        updated_at=timestamp,
    )


def _title_for(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def _looks_like_manual(relative_path: str, text: str) -> bool:
    sample = f"{relative_path}\n{text[:500]}".lower()
    return "manual" in sample or "manufacturer" in sample


def _chunks_for(text: str, *, max_chunk_chars: int) -> list[tuple[str | None, str]]:
    chunks: list[tuple[str | None, str]] = []
    section: str | None = None
    current: list[str] = []
    current_size = 0
    for block in _blocks(text):
        if block.startswith("#"):
            if current:
                chunks.append((section, "\n\n".join(current)))
                current = []
                current_size = 0
            section = block.lstrip("#").strip() or section
            continue
        if current and current_size + len(block) + 2 > max_chunk_chars:
            chunks.append((section, "\n\n".join(current)))
            current = []
            current_size = 0
        current.append(block)
        current_size += len(block) + 2
    if current:
        chunks.append((section, "\n\n".join(current)))
    return chunks


def _blocks(text: str) -> list[str]:
    return [block.strip() for block in text.replace("\r\n", "\n").split("\n\n") if block.strip()]
