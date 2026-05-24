from pathlib import Path

from manfriday.retrieval.index import load_retrieval_index
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


def load_index_or_ingest_retrieval_sources(
    *,
    local_docs_dir: Path,
    online_sources_path: Path | None,
    index_dir: Path,
) -> IngestionSummary:
    return load_retrieval_index(index_dir) or ingest_retrieval_sources(
        local_docs_dir=local_docs_dir,
        online_sources_path=online_sources_path,
    )
