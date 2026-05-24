from datetime import datetime

from manfriday.retrieval.models import IngestionSummary, SourceMetadata


def ingestion_summary_to_dict(summary: IngestionSummary) -> dict:
    return {
        "status": summary.status,
        "local_files_indexed": summary.local_files_indexed,
        "urls_indexed": summary.urls_indexed,
        "source_count": len(summary.sources),
        "chunk_count": len(summary.chunks),
        "skipped": [
            {"source": item.source, "reason": item.reason}
            for item in summary.skipped
        ],
        "failed": [
            {"source": item.source, "reason": item.reason}
            for item in summary.failed
        ],
        "sources": [
            {
                "source_id": source.source_id,
                "type": source.type,
                "title": source.title,
                "uri": source.uri,
                "chunk_count": _chunk_count(summary, source),
                "content_hash": source.content_hash,
                "manufacturer_or_manual": source.manufacturer_or_manual,
                "retrieved_at": _iso_or_none(source.retrieved_at),
            }
            for source in summary.sources
        ],
    }


def _chunk_count(summary: IngestionSummary, source: SourceMetadata) -> int:
    return sum(1 for chunk in summary.chunks if chunk.source_id == source.source_id)


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")
