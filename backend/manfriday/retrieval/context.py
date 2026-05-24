import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from manfriday.retrieval.index import load_vector_index
from manfriday.retrieval.models import (
    IngestionSummary,
    RankedChunk,
    RetrievalContext,
    RetrievalSafetyPolicy,
)
from manfriday.retrieval.search import build_merged_retriever
from manfriday.retrieval.sources import load_index_or_ingest_retrieval_sources

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "do",
    "for",
    "how",
    "i",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "what",
    "where",
}


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
    min_supported_score: float = 0.2
    ingest_fn: Callable[[Path, Path | None, Path], IngestionSummary] = _load_or_ingest_sources

    def build(self, query: str) -> RetrievalContext:
        summary = self.ingest_fn(self.local_docs_dir, self.online_sources_path, self.index_dir)
        vector_index = load_vector_index(self.index_dir, summary.chunks)
        retriever = build_merged_retriever(
            sources=summary.sources,
            chunks=summary.chunks,
            vector_index=vector_index,
        )
        chunks = retriever.query(query, limit=self.limit)
        return RetrievalContext(
            query=query,
            chunks=chunks,
            safety_policy=_safety_policy(
                query,
                chunks,
                vector_index_present=vector_index is not None,
                min_supported_score=self.min_supported_score,
            ),
        )


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


def _safety_policy(
    query: str,
    chunks: tuple[RankedChunk, ...],
    *,
    vector_index_present: bool,
    min_supported_score: float = 0.2,
) -> RetrievalSafetyPolicy:
    if not chunks:
        return RetrievalSafetyPolicy(
            confidence="low_confidence",
            fallback_reason="no_matching_chunks",
            instruction=(
                "No trusted retrieval chunks matched the question. Do not invent procedural, "
                "tool, safety, setup, torque, installation, or repair instructions; ask for "
                "the relevant manual/source or more context."
            ),
        )
    if not _has_meaningful_query_overlap(query, chunks):
        return RetrievalSafetyPolicy(
            confidence="low_confidence",
            fallback_reason="no_meaningful_query_overlap",
            instruction=(
                "Retrieved chunks only matched generic words. Do not invent procedural, "
                "tool, safety, setup, torque, installation, or repair instructions; ask for "
                "the relevant manual/source or more context."
            ),
        )
    if chunks[0].score < min_supported_score:
        return RetrievalSafetyPolicy(
            confidence="low_confidence",
            fallback_reason="top_score_below_threshold",
            instruction=(
                "Retrieved chunks scored below the support threshold. State the uncertainty "
                "and ask for the relevant manual/source before giving procedural instructions."
            ),
        )
    fallback_reason = "merged_keyword_vector" if vector_index_present else "keyword_only"
    return RetrievalSafetyPolicy(
        confidence="supported",
        fallback_reason=fallback_reason,
        instruction=(
            "Use the retrieved chunks as supporting context. Cite sources when the answer "
            "depends on them."
        ),
    )


def _has_meaningful_query_overlap(query: str, chunks: tuple[RankedChunk, ...]) -> bool:
    query_terms = {
        token for token in TOKEN_RE.findall(query.lower())
        if token not in STOPWORDS and len(token) > 2
    }
    if not query_terms:
        return False
    selected_text = "\n".join(
        f"{result.chunk.text}\n{result.chunk.section or ''}".lower()
        for result in chunks
    )
    return any(term in selected_text for term in query_terms)
