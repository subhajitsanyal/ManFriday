from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

SourceType = Literal["local_file", "configured_url", "web"]


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    type: SourceType
    title: str
    uri: str
    tags: tuple[str, ...] = ()
    retrieved_at: datetime | None = None
    manufacturer_or_manual: bool = False
    content_hash: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ChunkMetadata:
    chunk_id: str
    source_id: str
    text: str
    chunk_index: int
    page: int | None = None
    section: str | None = None
    token_count: int = 0
    content_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    bm25_score: float | None = None
    vector_score: float | None = None
    combined_score: float | None = None


@dataclass(frozen=True)
class RankedChunk:
    chunk: ChunkMetadata
    source: SourceMetadata
    score: float
    bm25_score: float
    keyword_score: float
    manual_boost: float = 0.0
    vector_score: float = 0.0
    combined_score: float | None = None


@dataclass(frozen=True)
class Citation:
    citation_id: str
    source_id: str
    chunk_id: str
    source_title: str
    source_uri: str
    source_type: SourceType
    section: str | None
    score: float


@dataclass(frozen=True)
class RetrievalContext:
    query: str
    chunks: tuple[RankedChunk, ...] = ()

    @property
    def citations(self) -> tuple[Citation, ...]:
        return tuple(
            Citation(
                citation_id=f"cite_{index + 1}",
                source_id=result.source.source_id,
                chunk_id=result.chunk.chunk_id,
                source_title=result.source.title,
                source_uri=result.source.uri,
                source_type=result.source.type,
                section=result.chunk.section,
                score=result.score,
            )
            for index, result in enumerate(self.chunks)
        )


@dataclass(frozen=True)
class SourceIngestionResult:
    source: SourceMetadata
    chunks: tuple[ChunkMetadata, ...]


@dataclass(frozen=True)
class IngestionSkipped:
    source: str
    reason: str


@dataclass(frozen=True)
class IngestionFailure:
    source: str
    reason: str


@dataclass(frozen=True)
class IngestionSummary:
    status: str
    local_files_indexed: int = 0
    urls_indexed: int = 0
    skipped: tuple[IngestionSkipped, ...] = ()
    failed: tuple[IngestionFailure, ...] = ()
    sources: tuple[SourceMetadata, ...] = ()
    chunks: tuple[ChunkMetadata, ...] = ()
    source_results: tuple[SourceIngestionResult, ...] = field(default=(), repr=False)
