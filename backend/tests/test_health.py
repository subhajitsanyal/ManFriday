from fastapi.testclient import TestClient

from manfriday.api.app import create_app
from manfriday.config.settings import Settings


def test_health_is_unauthenticated() -> None:
    app = create_app(Settings(MANFRIDAY_LOCAL_SECRET="test-secret"))
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "manfriday-backend"
    assert response.json()["version"] == "0.1.0"
    assert response.json()["time"].endswith("Z")
