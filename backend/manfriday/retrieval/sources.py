from pathlib import Path

from manfriday.retrieval.ingestion import ingest_local_documents, merge_ingestion_summaries
from manfriday.retrieval.models import IngestionSummary
from manfriday.retrieval.url_ingestion import ingest_configured_urls


def ingest_retrieval_sources(
    *,
    local_docs_dir: Path,
    online_sources_path: Path | None,
) -> IngestionSummary:
    configured_url_summary = (
        ingest_configured_urls(online_sources_path)
        if online_sources_path is not None
        else IngestionSummary(status="completed")
    )
    return merge_ingestion_summaries(
        ingest_local_documents(local_docs_dir),
        configured_url_summary,
    )
