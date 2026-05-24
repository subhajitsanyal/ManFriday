from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from manfriday.retrieval.models import IngestionSummary, RetrievalContext
from manfriday.retrieval.search import build_keyword_index
from manfriday.retrieval.sources import ingest_retrieval_sources


def _ingest_sources(local_docs_dir: Path, online_sources_path: Path | None) -> IngestionSummary:
    return ingest_retrieval_sources(
        local_docs_dir=local_docs_dir,
        online_sources_path=online_sources_path,
    )


@dataclass(frozen=True)
class RetrievalContextBuilder:
    local_docs_dir: Path
    online_sources_path: Path | None = None
    limit: int = 3
    ingest_fn: Callable[[Path, Path | None], IngestionSummary] = _ingest_sources

    def build(self, query: str) -> RetrievalContext:
        summary = self.ingest_fn(self.local_docs_dir, self.online_sources_path)
        index = build_keyword_index(sources=summary.sources, chunks=summary.chunks)
        return RetrievalContext(query=query, chunks=index.query(query, limit=self.limit))


def build_retrieval_context(
    *,
    query: str,
    local_docs_dir: Path,
    online_sources_path: Path | None = None,
    limit: int = 3,
) -> RetrievalContext:
    return RetrievalContextBuilder(
        local_docs_dir=local_docs_dir,
        online_sources_path=online_sources_path,
        limit=limit,
    ).build(query)
