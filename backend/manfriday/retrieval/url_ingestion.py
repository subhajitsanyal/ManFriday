from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from manfriday.retrieval.ingestion import _chunks_for, _looks_like_manual
from manfriday.retrieval.models import (
    ChunkMetadata,
    IngestionFailure,
    IngestionSummary,
    SourceIngestionResult,
    SourceMetadata,
)

SUPPORTED_CONTENT_TYPES = (
    "text/plain",
    "text/markdown",
    "text/html",
    "application/xhtml+xml",
)


@dataclass(frozen=True)
class ConfiguredUrlSource:
    title: str
    url: str
    tags: tuple[str, ...] = ()
    manufacturer_or_manual: bool = False


@dataclass(frozen=True)
class ConfiguredUrlIngestor:
    max_bytes: int = 2_000_000
    max_chunk_chars: int = 1_200
    timeout_seconds: float = 10.0
    now_fn: Callable[[], datetime] | None = None

    def ingest_sources_path(self, path: Path) -> IngestionSummary:
        if not path.exists():
            return IngestionSummary(status="completed")
        try:
            sources = parse_configured_url_sources(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            return IngestionSummary(
                status="completed_with_errors",
                failed=(IngestionFailure(source=str(path), reason=str(exc)),),
            )
        return self.ingest_sources(sources)

    def ingest_sources(self, sources: tuple[ConfiguredUrlSource, ...]) -> IngestionSummary:
        results: list[SourceIngestionResult] = []
        failed: list[IngestionFailure] = []
        for source in sources:
            try:
                results.append(self.ingest_source(source))
            except ConfiguredUrlIngestionError as exc:
                failed.append(IngestionFailure(source=source.url, reason=exc.reason))
        return IngestionSummary(
            status="completed" if not failed else "completed_with_errors",
            urls_indexed=len(results),
            failed=tuple(failed),
            sources=tuple(result.source for result in results),
            chunks=tuple(chunk for result in results for chunk in result.chunks),
            source_results=tuple(results),
        )

    def ingest_source(self, source_config: ConfiguredUrlSource) -> SourceIngestionResult:
        parsed = urlparse(source_config.url)
        if parsed.scheme not in {"http", "https"}:
            raise ConfiguredUrlIngestionError("unsupported_url_scheme")
        fetched = self._fetch(source_config.url)
        text = _text_from_response(fetched.body, fetched.content_type)
        timestamp = self._now()
        content_hash = sha256(fetched.body).hexdigest()
        source = SourceMetadata(
            source_id=_configured_url_source_id(source_config.url),
            type="configured_url",
            title=source_config.title,
            uri=source_config.url,
            tags=source_config.tags,
            retrieved_at=timestamp,
            manufacturer_or_manual=source_config.manufacturer_or_manual
            or _looks_like_manual(source_config.url, text),
            content_hash=content_hash,
            size_bytes=len(fetched.body),
            created_at=timestamp,
            updated_at=timestamp,
        )
        chunks = tuple(
            ChunkMetadata(
                chunk_id=_configured_url_chunk_id(source.source_id, index, chunk_text),
                source_id=source.source_id,
                text=chunk_text,
                chunk_index=index,
                section=section,
                token_count=len(chunk_text.split()),
                content_hash=sha256(chunk_text.encode("utf-8")).hexdigest(),
                created_at=timestamp,
                updated_at=timestamp,
            )
            for index, (section, chunk_text) in enumerate(
                _chunks_for(text, max_chunk_chars=self.max_chunk_chars),
            )
        )
        return SourceIngestionResult(source=source, chunks=chunks)

    def _fetch(self, url: str) -> "FetchedUrl":
        request = Request(url, headers={"User-Agent": "ManFriday/0.1 retrieval"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                if content_type not in SUPPORTED_CONTENT_TYPES:
                    raise ConfiguredUrlIngestionError("unsupported_content_type")
                body = response.read(self.max_bytes + 1)
        except HTTPError as exc:
            raise ConfiguredUrlIngestionError(f"http_{exc.code}") from exc
        except URLError as exc:
            raise ConfiguredUrlIngestionError("request_failed") from exc
        if len(body) > self.max_bytes:
            raise ConfiguredUrlIngestionError("response_too_large")
        return FetchedUrl(body=body, content_type=content_type)

    def _now(self) -> datetime:
        now = self.now_fn() if self.now_fn is not None else datetime.now(UTC)
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now


@dataclass(frozen=True)
class FetchedUrl:
    body: bytes
    content_type: str


class ConfiguredUrlIngestionError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def ingest_configured_urls(path: Path) -> IngestionSummary:
    return ConfiguredUrlIngestor().ingest_sources_path(path)


def parse_configured_url_sources(text: str) -> tuple[ConfiguredUrlSource, ...]:
    sources: list[ConfiguredUrlSource] = []
    current: dict[str, object] | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped or stripped == "sources:":
            continue
        if stripped.startswith("- "):
            if current is not None:
                sources.append(_source_from_mapping(current))
            current = {}
            key_value = stripped[2:].strip()
            if key_value:
                _assign_yaml_value(current, key_value)
            continue
        if current is None:
            raise ValueError("invalid_sources_yaml")
        _assign_yaml_value(current, stripped)
    if current is not None:
        sources.append(_source_from_mapping(current))
    return tuple(sources)


def _assign_yaml_value(target: dict[str, object], key_value: str) -> None:
    key, separator, value = key_value.partition(":")
    if not separator:
        raise ValueError("invalid_sources_yaml")
    target[key.strip()] = _parse_yaml_scalar(value.strip())


def _parse_yaml_scalar(value: str) -> object:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        return tuple(
            item.strip().strip("'\"")
            for item in value[1:-1].split(",")
            if item.strip()
        )
    return value.strip("'\"")


def _source_from_mapping(mapping: dict[str, object]) -> ConfiguredUrlSource:
    title = str(mapping.get("title", "")).strip()
    url = str(mapping.get("url", "")).strip()
    if not title or not url:
        raise ValueError("configured_url_missing_title_or_url")
    tags = mapping.get("tags", ())
    if isinstance(tags, str):
        tags = (tags,)
    manufacturer_or_manual = mapping.get("manufacturer_or_manual", False)
    return ConfiguredUrlSource(
        title=title,
        url=url,
        tags=tuple(str(tag) for tag in tags),
        manufacturer_or_manual=bool(manufacturer_or_manual),
    )


def _text_from_response(body: bytes, content_type: str) -> str:
    text = body.decode("utf-8")
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _TextExtractor()
        parser.feed(text)
        return parser.text()
    return text


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"p", "br", "li", "h1", "h2", "h3"}:
            self._parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)

    def text(self) -> str:
        return " ".join(self._parts).replace("\n ", "\n").strip()


def _configured_url_source_id(url: str) -> str:
    return f"url_{sha256(url.encode('utf-8')).hexdigest()[:16]}"


def _configured_url_chunk_id(source_id: str, chunk_index: int, text: str) -> str:
    text_hash = sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{source_id}_chunk_{chunk_index:04d}_{text_hash}"
