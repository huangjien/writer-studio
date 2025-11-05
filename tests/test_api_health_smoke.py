from fastapi.testclient import TestClient

from writer_studio.api.server import app


def test_health_endpoint_smoke():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"