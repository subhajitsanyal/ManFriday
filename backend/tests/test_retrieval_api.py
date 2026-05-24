import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from manfriday.api.app import create_app
from manfriday.cli import main as cli_main
from manfriday.config.settings import Settings
from manfriday.retrieval import write_retrieval_index
from manfriday.retrieval.ingestion import LocalDocumentIngestor
from tests.test_retrieval_url_ingestion import _fixture_server

FIXTURES = Path(__file__).parent / "fixtures" / "retrieval"
PDF_FIXTURES = Path(__file__).parent / "fixtures" / "retrieval_pdf"


def test_retrieval_ingest_requires_bearer_auth() -> None:
    client = TestClient(create_app(_settings()))

    assert client.post("/retrieval/ingest").status_code == 401


def test_retrieval_query_requires_bearer_auth() -> None:
    client = TestClient(create_app(_settings()))

    assert client.post("/retrieval/query", json={"query": "hex key"}).status_code == 401


def test_retrieval_ingest_returns_per_source_summary() -> None:
    client = TestClient(create_app(_settings()))

    response = client.post("/retrieval/ingest", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["local_files_indexed"] == 2
    assert body["urls_indexed"] == 0
    assert body["source_count"] == 2
    assert body["chunk_count"] == 4
    assert body["failed"] == []
    assert body["skipped"] == [{"source": "ignore.bin", "reason": "unsupported_file_type"}]
    assert [source["uri"] for source in body["sources"]] == [
        "notes.txt",
        "workbench_manual.md",
    ]
    manual = next(source for source in body["sources"] if source["uri"] == "workbench_manual.md")
    assert manual["title"] == "Workbench Safety Manual"
    assert manual["chunk_count"] == 3
    assert manual["manufacturer_or_manual"] is True
    assert manual["content_hash"]
    assert manual["retrieved_at"].endswith("Z")


def test_retrieval_ingest_writes_persisted_index(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(RETRIEVAL_INDEX_DIR=tmp_path / "index")))

    response = client.post("/retrieval/ingest", headers=_headers())

    assert response.status_code == 200
    assert (tmp_path / "index" / "index.json").exists()


def test_retrieval_ingest_includes_configured_url_sources(tmp_path: Path) -> None:
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
        client = TestClient(create_app(_settings(RETRIEVAL_ONLINE_SOURCES_PATH=sources_path)))

        response = client.post("/retrieval/ingest", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["local_files_indexed"] == 2
    assert body["urls_indexed"] == 1
    assert body["source_count"] == 3
    source = next(source for source in body["sources"] if source["type"] == "configured_url")
    assert source["title"] == "Manufacturer Torque Guide"
    assert source["manufacturer_or_manual"] is True


def test_retrieval_ingest_reports_missing_directory() -> None:
    client = TestClient(create_app(_settings(RETRIEVAL_LOCAL_DOCS_DIR=FIXTURES / "missing")))

    response = client.post("/retrieval/ingest", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["local_files_indexed"] == 0
    assert body["source_count"] == 0
    assert body["chunk_count"] == 0
    assert body["failed"][0]["reason"] == "directory_not_found"


def test_retrieval_query_returns_ranked_chunks() -> None:
    client = TestClient(create_app(_settings()))

    response = client.post(
        "/retrieval/query",
        headers=_headers(),
        json={"query": "hex key", "limit": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "hex key"
    assert body["source_count"] == 2
    assert body["chunk_count"] == 4
    assert body["result_count"] == 1
    result = body["results"][0]
    assert result["source_uri"] == "notes.txt"
    assert result["source_type"] == "local_file"
    assert result["text"] == (
        "Use the blue bin for spare clamps.\n\n"
        "The small hex key belongs with the camera mount."
    )
    assert result["score"] > 0
    assert result["bm25_score"] > 0
    assert result["keyword_score"] > 0


def test_retrieval_query_prefers_persisted_index_when_available(tmp_path: Path) -> None:
    index_dir = tmp_path / "index"
    index_root = tmp_path / "indexed"
    index_root.mkdir()
    (index_root / "indexed.txt").write_text("indexed-only calibration token", encoding="utf-8")
    summary = LocalDocumentIngestor().ingest_directory(index_root)
    write_retrieval_index(summary, index_dir)
    live_root = tmp_path / "live"
    live_root.mkdir()
    (live_root / "live.txt").write_text("live-only calibration token", encoding="utf-8")
    client = TestClient(
        create_app(
            _settings(
                RETRIEVAL_LOCAL_DOCS_DIR=live_root,
                RETRIEVAL_INDEX_DIR=index_dir,
            ),
        ),
    )

    response = client.post(
        "/retrieval/query",
        headers=_headers(),
        json={"query": "indexed-only", "limit": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_count"] == 1
    assert body["results"][0]["source_uri"] == "indexed.txt"
    assert body["results"][0]["vector_score"] > 0
    assert body["results"][0]["combined_score"] == body["results"][0]["score"]


def test_retrieval_query_falls_back_when_persisted_index_is_missing(tmp_path: Path) -> None:
    live_root = tmp_path / "live"
    live_root.mkdir()
    (live_root / "live.txt").write_text("live-only calibration token", encoding="utf-8")
    client = TestClient(
        create_app(
            _settings(
                RETRIEVAL_LOCAL_DOCS_DIR=live_root,
                RETRIEVAL_INDEX_DIR=tmp_path / "missing-index",
            ),
        ),
    )

    response = client.post(
        "/retrieval/query",
        headers=_headers(),
        json={"query": "live-only", "limit": 3},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["source_uri"] == "live.txt"
    assert response.json()["results"][0]["vector_score"] == 0.0


def test_retrieval_query_returns_stable_ordering_and_manual_preference() -> None:
    client = TestClient(create_app(_settings()))

    first = client.post(
        "/retrieval/query",
        headers=_headers(),
        json={"query": "camera mount", "limit": 10},
    ).json()
    second = client.post(
        "/retrieval/query",
        headers=_headers(),
        json={"query": "camera mount", "limit": 10},
    ).json()

    assert [result["chunk_id"] for result in first["results"]] == [
        result["chunk_id"] for result in second["results"]
    ]
    assert first["results"][0]["source_uri"] == "workbench_manual.md"
    assert first["results"][0]["manufacturer_or_manual"] is True


def test_retrieval_query_handles_missing_directory() -> None:
    client = TestClient(create_app(_settings(RETRIEVAL_LOCAL_DOCS_DIR=FIXTURES / "missing")))

    response = client.post(
        "/retrieval/query",
        headers=_headers(),
        json={"query": "camera"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_count"] == 0
    assert body["chunk_count"] == 0
    assert body["result_count"] == 0
    assert body["results"] == []


def test_retrieval_query_returns_configured_url_chunks(tmp_path: Path) -> None:
    with _fixture_server() as server:
        sources_path = tmp_path / "sources.yaml"
        sources_path.write_text(
            f"""
            sources:
              - title: Manufacturer Torque Guide
                url: {server.url('/guide.md')}
                manufacturer_or_manual: true
            """,
            encoding="utf-8",
        )
        client = TestClient(create_app(_settings(RETRIEVAL_ONLINE_SOURCES_PATH=sources_path)))

        response = client.post(
            "/retrieval/query",
            headers=_headers(),
            json={"query": "torque wrench", "limit": 3},
        )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["source_type"] == "configured_url"
    assert result["source_title"] == "Manufacturer Torque Guide"
    assert "4 Nm" in result["text"]


def test_retrieval_query_returns_pdf_page_metadata() -> None:
    client = TestClient(create_app(_settings(RETRIEVAL_LOCAL_DOCS_DIR=PDF_FIXTURES)))

    response = client.post(
        "/retrieval/query",
        headers=_headers(),
        json={"query": "4 Nm", "limit": 3},
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["source_uri"] == "camera_mount_manual.pdf"
    assert result["page"] == 2
    assert result["text"] == "Tighten the mount screw to 4 Nm on page two"


def test_manfriday_ingest_cli_outputs_summary(capsys, monkeypatch) -> None:
    monkeypatch.setenv("MANFRIDAY_LOCAL_SECRET", "test-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["manfriday", "ingest", "--local-docs-dir", str(FIXTURES)],
    )

    cli_main()

    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "completed"
    assert body["local_files_indexed"] == 2
    assert body["source_count"] == 2
    assert body["chunk_count"] == 4


def test_manfriday_ingest_cli_writes_persisted_index(capsys, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MANFRIDAY_LOCAL_SECRET", "test-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "manfriday",
            "ingest",
            "--local-docs-dir",
            str(FIXTURES),
            "--index-dir",
            str(tmp_path / "index"),
        ],
    )

    cli_main()

    body = json.loads(capsys.readouterr().out)
    assert body["source_count"] == 2
    assert (tmp_path / "index" / "index.json").exists()


def test_manfriday_ingest_cli_includes_configured_urls(capsys, monkeypatch, tmp_path: Path) -> None:
    with _fixture_server() as server:
        sources_path = tmp_path / "sources.yaml"
        sources_path.write_text(
            f"""
            sources:
              - title: Manufacturer Torque Guide
                url: {server.url('/guide.md')}
            """,
            encoding="utf-8",
        )
        monkeypatch.setenv("MANFRIDAY_LOCAL_SECRET", "test-secret")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "manfriday",
                "ingest",
                "--local-docs-dir",
                str(FIXTURES),
                "--online-sources-path",
                str(sources_path),
            ],
        )

        cli_main()

    body = json.loads(capsys.readouterr().out)
    assert body["local_files_indexed"] == 2
    assert body["urls_indexed"] == 1
    assert body["source_count"] == 3


def _settings(**overrides) -> Settings:
    values = {
        "MANFRIDAY_LOCAL_SECRET": "test-secret",
        "MODEL_PROVIDER": "mock",
        "RETRIEVAL_LOCAL_DOCS_DIR": FIXTURES,
    }
    values.update(overrides)
    return Settings(
        **values,
    )


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-secret"}
