from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "ClipMind AI API is running"}
