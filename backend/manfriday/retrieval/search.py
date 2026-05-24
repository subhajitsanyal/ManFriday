import re
from collections import Counter
from dataclasses import dataclass
from math import log

from manfriday.retrieval.models import ChunkMetadata, RankedChunk, SourceMetadata

TOKEN_RE = re.compile(r"[a-z0-9]+")
SOURCE_TYPE_PRIORITY = {"local_file": 0, "configured_url": 1, "web": 2}


@dataclass(frozen=True)
class KeywordIndex:
    chunks: tuple[ChunkMetadata, ...]
    sources_by_id: dict[str, SourceMetadata]
    k1: float = 1.5
    b: float = 0.75
    manual_boost: float = 0.15

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_document_terms",
            tuple(_tokens(_searchable_text(chunk)) for chunk in self.chunks),
        )
        object.__setattr__(
            self,
            "_term_counts",
            tuple(Counter(terms) for terms in self._document_terms),
        )
        object.__setattr__(
            self,
            "_document_lengths",
            tuple(len(terms) for terms in self._document_terms),
        )
        avg_len = (
            sum(self._document_lengths) / len(self._document_lengths)
            if self._document_lengths
            else 0.0
        )
        object.__setattr__(self, "_average_document_length", avg_len)
        document_frequency: Counter[str] = Counter()
        for terms in self._document_terms:
            document_frequency.update(set(terms))
        object.__setattr__(self, "_document_frequency", document_frequency)

    def query(self, query: str, *, limit: int = 5) -> tuple[RankedChunk, ...]:
        query_terms = tuple(_tokens(query))
        if not query_terms or limit <= 0:
            return ()

        ranked: list[RankedChunk] = []
        for index, chunk in enumerate(self.chunks):
            source = self.sources_by_id.get(chunk.source_id)
            if source is None:
                continue
            bm25_score = self._bm25_score(index, query_terms)
            keyword_score = self._keyword_score(index, query_terms)
            manual_boost = (
                self.manual_boost
                if source.manufacturer_or_manual and keyword_score > 0
                else 0.0
            )
            score = bm25_score + keyword_score + manual_boost
            if score <= 0:
                continue
            ranked.append(
                RankedChunk(
                    chunk=chunk,
                    source=source,
                    score=round(score, 6),
                    bm25_score=round(bm25_score, 6),
                    keyword_score=round(keyword_score, 6),
                    manual_boost=manual_boost,
                ),
            )

        return tuple(
            sorted(ranked, key=_rank_sort_key)[:limit],
        )

    def _bm25_score(self, document_index: int, query_terms: tuple[str, ...]) -> float:
        if self._average_document_length <= 0:
            return 0.0
        term_counts = self._term_counts[document_index]
        document_length = self._document_lengths[document_index]
        score = 0.0
        total_documents = len(self.chunks)
        for term in set(query_terms):
            frequency = term_counts[term]
            if frequency <= 0:
                continue
            document_frequency = self._document_frequency[term]
            idf = log(1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5))
            denominator = frequency + self.k1 * (
                1 - self.b + self.b * document_length / self._average_document_length
            )
            score += idf * (frequency * (self.k1 + 1)) / denominator
        return score

    def _keyword_score(self, document_index: int, query_terms: tuple[str, ...]) -> float:
        term_counts = self._term_counts[document_index]
        matches = sum(1 for term in query_terms if term_counts[term] > 0)
        if matches == 0:
            return 0.0
        return matches / len(query_terms)


@dataclass(frozen=True)
class VectorEntry:
    chunk_id: str
    source_id: str
    content_hash: str | None
    weights: dict[str, float]
    norm: float


@dataclass(frozen=True)
class VectorIndex:
    entries_by_chunk_id: dict[str, VectorEntry]

    def query(self, query: str) -> dict[str, float]:
        query_vector, query_norm = _term_vector(_tokens(query))
        if query_norm <= 0:
            return {}

        scores: dict[str, float] = {}
        for chunk_id, entry in self.entries_by_chunk_id.items():
            if entry.norm <= 0:
                continue
            dot_product = sum(
                weight * entry.weights.get(term, 0.0)
                for term, weight in query_vector.items()
            )
            if dot_product <= 0:
                continue
            scores[chunk_id] = round(dot_product / (query_norm * entry.norm), 6)
        return scores


@dataclass(frozen=True)
class MergedRetriever:
    keyword_index: KeywordIndex
    vector_index: VectorIndex | None = None
    keyword_weight: float = 0.8
    vector_weight: float = 0.2

    def query(self, query: str, *, limit: int = 5) -> tuple[RankedChunk, ...]:
        keyword_results = self.keyword_index.query(
            query,
            limit=max(limit, len(self.keyword_index.chunks)),
        )
        if not keyword_results or limit <= 0:
            return ()

        vector_scores = self.vector_index.query(query) if self.vector_index is not None else {}
        best_keyword_score = max(result.score for result in keyword_results) or 1.0
        merged: list[RankedChunk] = []
        for result in keyword_results:
            normalized_keyword = result.score / best_keyword_score
            vector_score = vector_scores.get(result.chunk.chunk_id, 0.0)
            if vector_scores:
                combined_score = (
                    self.keyword_weight * normalized_keyword
                    + self.vector_weight * vector_score
                    + result.manual_boost
                )
            else:
                combined_score = result.score
            merged.append(
                RankedChunk(
                    chunk=result.chunk,
                    source=result.source,
                    score=round(combined_score, 6),
                    bm25_score=result.bm25_score,
                    keyword_score=result.keyword_score,
                    manual_boost=result.manual_boost,
                    vector_score=round(vector_score, 6),
                    combined_score=round(combined_score, 6),
                ),
            )

        return tuple(sorted(merged, key=_rank_sort_key)[:limit])


def build_keyword_index(
    *,
    sources: tuple[SourceMetadata, ...],
    chunks: tuple[ChunkMetadata, ...],
) -> KeywordIndex:
    return KeywordIndex(
        chunks=tuple(
            sorted(
                chunks,
                key=lambda chunk: (chunk.source_id, chunk.chunk_index, chunk.chunk_id),
            ),
        ),
        sources_by_id={source.source_id: source for source in sources},
    )


def build_vector_index(
    *,
    chunks: tuple[ChunkMetadata, ...],
) -> VectorIndex:
    return VectorIndex(
        entries_by_chunk_id={
            chunk.chunk_id: _vector_entry(chunk)
            for chunk in chunks
        },
    )


def build_merged_retriever(
    *,
    sources: tuple[SourceMetadata, ...],
    chunks: tuple[ChunkMetadata, ...],
    vector_index: VectorIndex | None = None,
) -> MergedRetriever:
    return MergedRetriever(
        keyword_index=build_keyword_index(sources=sources, chunks=chunks),
        vector_index=vector_index,
    )


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _searchable_text(chunk: ChunkMetadata) -> str:
    parts = [chunk.text]
    if chunk.section:
        parts.append(chunk.section)
    return "\n".join(parts)


def _vector_entry(chunk: ChunkMetadata) -> VectorEntry:
    vector, norm = _term_vector(_tokens(_searchable_text(chunk)))
    return VectorEntry(
        chunk_id=chunk.chunk_id,
        source_id=chunk.source_id,
        content_hash=chunk.content_hash,
        weights=vector,
        norm=norm,
    )


def _term_vector(tokens: list[str] | tuple[str, ...]) -> tuple[dict[str, float], float]:
    counts = Counter(tokens)
    if not counts:
        return {}, 0.0
    weights = {term: 1.0 + log(count) for term, count in counts.items()}
    norm = sum(weight * weight for weight in weights.values()) ** 0.5
    return weights, norm


def _rank_sort_key(result: RankedChunk) -> tuple:
    return (
        -result.score,
        SOURCE_TYPE_PRIORITY.get(result.source.type, 99),
        -int(result.source.manufacturer_or_manual),
        result.source.uri,
        result.chunk.chunk_index,
        result.chunk.chunk_id,
    )
