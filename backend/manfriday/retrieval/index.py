import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from manfriday.retrieval.models import (
    ChunkMetadata,
    IngestionSummary,
    SourceIngestionResult,
    SourceMetadata,
)

INDEX_FILENAME = "index.json"
INDEX_VERSION = 1


def write_retrieval_index(summary: IngestionSummary, index_dir: Path) -> Path:
    index_dir.mkdir(parents=True, exist_ok=True)
    path = retrieval_index_path(index_dir)
    path.write_text(json.dumps(_summary_to_index(summary), indent=2), encoding="utf-8")
    return path


def load_retrieval_index(index_dir: Path) -> IngestionSummary | None:
    path = retrieval_index_path(index_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != INDEX_VERSION:
            return None
        sources = tuple(_source_from_dict(item) for item in payload.get("sources", []))
        chunks = tuple(_chunk_from_dict(item) for item in payload.get("chunks", []))
        if not sources and not chunks:
            return None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return IngestionSummary(
        status="completed",
        local_files_indexed=int(payload.get("local_files_indexed", 0)),
        urls_indexed=int(payload.get("urls_indexed", 0)),
        sources=sources,
        chunks=chunks,
        source_results=tuple(
            SourceIngestionResult(
                source=source,
                chunks=tuple(chunk for chunk in chunks if chunk.source_id == source.source_id),
            )
            for source in sources
        ),
    )


def retrieval_index_path(index_dir: Path) -> Path:
    return index_dir / INDEX_FILENAME


def _summary_to_index(summary: IngestionSummary) -> dict:
    return {
        "version": INDEX_VERSION,
        "written_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "local_files_indexed": summary.local_files_indexed,
        "urls_indexed": summary.urls_indexed,
        "sources": [_metadata_to_dict(source) for source in summary.sources],
        "chunks": [_metadata_to_dict(chunk) for chunk in summary.chunks],
    }


def _metadata_to_dict(value) -> dict:
    result = asdict(value)
    for key, item in result.items():
        if isinstance(item, datetime):
            result[key] = item.isoformat().replace("+00:00", "Z")
    return result


def _source_from_dict(value: dict) -> SourceMetadata:
    return SourceMetadata(
        source_id=value["source_id"],
        type=value["type"],
        title=value["title"],
        uri=value["uri"],
        tags=tuple(value.get("tags", ())),
        retrieved_at=_datetime_or_none(value.get("retrieved_at")),
        manufacturer_or_manual=bool(value.get("manufacturer_or_manual", False)),
        content_hash=value.get("content_hash"),
        size_bytes=value.get("size_bytes"),
        created_at=_datetime_or_none(value.get("created_at")),
        updated_at=_datetime_or_none(value.get("updated_at")),
    )


def _chunk_from_dict(value: dict) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=value["chunk_id"],
        source_id=value["source_id"],
        text=value["text"],
        chunk_index=int(value["chunk_index"]),
        page=value.get("page"),
        section=value.get("section"),
        token_count=int(value.get("token_count", 0)),
        content_hash=value.get("content_hash"),
        created_at=_datetime_or_none(value.get("created_at")),
        updated_at=_datetime_or_none(value.get("updated_at")),
        bm25_score=value.get("bm25_score"),
        vector_score=value.get("vector_score"),
        combined_score=value.get("combined_score"),
    )


def _datetime_or_none(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
