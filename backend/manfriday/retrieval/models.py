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
