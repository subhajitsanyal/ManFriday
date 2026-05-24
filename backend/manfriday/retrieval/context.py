from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from manfriday.retrieval.ingestion import ingest_local_documents
from manfriday.retrieval.models import IngestionSummary, RetrievalContext
from manfriday.retrieval.search import build_keyword_index


@dataclass(frozen=True)
class RetrievalContextBuilder:
    local_docs_dir: Path
    limit: int = 3
    ingest_fn: Callable[[Path], IngestionSummary] = ingest_local_documents

    def build(self, query: str) -> RetrievalContext:
        summary = self.ingest_fn(self.local_docs_dir)
        index = build_keyword_index(sources=summary.sources, chunks=summary.chunks)
        return RetrievalContext(query=query, chunks=index.query(query, limit=self.limit))


def build_retrieval_context(
    *,
    query: str,
    local_docs_dir: Path,
    limit: int = 3,
) -> RetrievalContext:
    return RetrievalContextBuilder(local_docs_dir=local_docs_dir, limit=limit).build(query)
