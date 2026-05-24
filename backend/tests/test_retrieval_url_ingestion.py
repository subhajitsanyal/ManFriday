from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from manfriday.retrieval import ConfiguredUrlIngestor, parse_configured_url_sources


def test_parse_configured_url_sources_yaml() -> None:
    sources = parse_configured_url_sources(
        """
        sources:
          - title: Manufacturer Torque Guide
            url: http://127.0.0.1:8000/guide.md
            tags: [manufacturer, torque]
            manufacturer_or_manual: true
        """,
    )

    assert sources[0].title == "Manufacturer Torque Guide"
    assert sources[0].url == "http://127.0.0.1:8000/guide.md"
    assert sources[0].tags == ("manufacturer", "torque")
    assert sources[0].manufacturer_or_manual is True


def test_configured_url_ingestion_indexes_trusted_text_source(tmp_path: Path) -> None:
    with _fixture_server() as server:
        sources_path = tmp_path / "sources.yaml"
        sources_path.write_text(
            f"""
            sources:
              - title: Manufacturer Torque Guide
                url: {server.url('/guide.md')}
                tags: [manufacturer, torque]
                manufacturer_or_manual: true
            """,
            encoding="utf-8",
        )

        summary = ConfiguredUrlIngestor().ingest_sources_path(sources_path)

    assert summary.status == "completed"
    assert summary.urls_indexed == 1
    assert summary.failed == ()
    source = summary.sources[0]
    assert source.type == "configured_url"
    assert source.title == "Manufacturer Torque Guide"
    assert source.uri.endswith("/guide.md")
    assert source.tags == ("manufacturer", "torque")
    assert source.manufacturer_or_manual is True
    assert source.content_hash
    assert summary.chunks[0].text == (
        "Set the torque wrench to 4 Nm before tightening the camera mount."
    )


def test_configured_url_ingestion_reports_per_source_failures(tmp_path: Path) -> None:
    with _fixture_server() as server:
        sources_path = tmp_path / "sources.yaml"
        sources_path.write_text(
            f"""
            sources:
              - title: Missing Guide
                url: {server.url('/missing.md')}
              - title: Binary Guide
                url: {server.url('/binary.bin')}
            """,
            encoding="utf-8",
        )

        summary = ConfiguredUrlIngestor().ingest_sources_path(sources_path)

    assert summary.status == "completed_with_errors"
    assert summary.urls_indexed == 0
    assert {failure.reason for failure in summary.failed} == {
        "http_404",
        "unsupported_content_type",
    }


class _FixtureServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_FixtureServer":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def url(self, path: str) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}{path}"


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/guide.md":
            self._send(
                status=200,
                content_type="text/markdown",
                body=b"Set the torque wrench to 4 Nm before tightening the camera mount.",
            )
        elif self.path == "/binary.bin":
            self._send(status=200, content_type="application/octet-stream", body=b"\x00\x01")
        else:
            self._send(status=404, content_type="text/plain", body=b"missing")

    def log_message(self, format: str, *args) -> None:
        return

    def _send(self, *, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _fixture_server() -> _FixtureServer:
    return _FixtureServer()
