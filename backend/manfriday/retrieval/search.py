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


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _searchable_text(chunk: ChunkMetadata) -> str:
    parts = [chunk.text]
    if chunk.section:
        parts.append(chunk.section)
    return "\n".join(parts)


def _rank_sort_key(result: RankedChunk) -> tuple:
    return (
        -result.score,
        SOURCE_TYPE_PRIORITY.get(result.source.type, 99),
        -int(result.source.manufacturer_or_manual),
        result.source.uri,
        result.chunk.chunk_index,
        result.chunk.chunk_id,
    )
