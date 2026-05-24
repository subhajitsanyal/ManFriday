from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from manfriday.retrieval.index import load_vector_index
from manfriday.retrieval.models import IngestionSummary, RetrievalContext
from manfriday.retrieval.search import build_merged_retriever
from manfriday.retrieval.sources import load_index_or_ingest_retrieval_sources


def _load_or_ingest_sources(
    local_docs_dir: Path,
    online_sources_path: Path | None,
    index_dir: Path,
) -> IngestionSummary:
    return load_index_or_ingest_retrieval_sources(
        local_docs_dir=local_docs_dir,
        online_sources_path=online_sources_path,
        index_dir=index_dir,
    )


@dataclass(frozen=True)
class RetrievalContextBuilder:
    local_docs_dir: Path
    online_sources_path: Path | None = None
    index_dir: Path = Path(".state/retrieval")
    limit: int = 3
    ingest_fn: Callable[[Path, Path | None, Path], IngestionSummary] = _load_or_ingest_sources

    def build(self, query: str) -> RetrievalContext:
        summary = self.ingest_fn(self.local_docs_dir, self.online_sources_path, self.index_dir)
        retriever = build_merged_retriever(
            sources=summary.sources,
            chunks=summary.chunks,
            vector_index=load_vector_index(self.index_dir, summary.chunks),
        )
        return RetrievalContext(query=query, chunks=retriever.query(query, limit=self.limit))


def build_retrieval_context(
    *,
    query: str,
    local_docs_dir: Path,
    online_sources_path: Path | None = None,
    index_dir: Path = Path(".state/retrieval"),
    limit: int = 3,
) -> RetrievalContext:
    return RetrievalContextBuilder(
        local_docs_dir=local_docs_dir,
        online_sources_path=online_sources_path,
        index_dir=index_dir,
        limit=limit,
    ).build(query)
