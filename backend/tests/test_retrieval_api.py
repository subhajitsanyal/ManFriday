import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from manfriday.api.app import create_app
from manfriday.cli import main as cli_main
from manfriday.config.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "retrieval"


def test_retrieval_ingest_requires_bearer_auth() -> None:
    client = TestClient(create_app(_settings()))

    assert client.post("/retrieval/ingest").status_code == 401


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
