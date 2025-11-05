from types import SimpleNamespace
from fastapi.testclient import TestClient

import writer_studio.persistence.db as db
from writer_studio.api.server import app
import writer_studio.api.server as server_mod


def _setup_tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "api_eval_persist.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


def test_evaluate_error_returns_500(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    async def _raise_eval(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(server_mod, "a_evaluate_chapter", _raise_eval)

    with TestClient(app) as client:
        r = client.post(
            "/evaluate",
            json={"chapter_text": "Hi", "persist": False},
        )
        assert r.status_code == 500


def test_evaluate_persist_then_get_and_search(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    # Stub evaluation result with two messages, final JSON content
    messages = [
        SimpleNamespace(name="Critic", content="Interim content"),
        SimpleNamespace(name="Summarizer", content='{"score": 7}'),
    ]

    async def _stub_eval(**kwargs):
        return SimpleNamespace(messages=messages)

    monkeypatch.setattr(server_mod, "a_evaluate_chapter", _stub_eval)

    with TestClient(app) as client:
        # Persist evaluation
        r = client.post(
            "/evaluate",
            json={"chapter_text": "Mystery story", "persist": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["id"], int) and body["id"] > 0
        eid = body["id"]

        # Fetch evaluation by id
        r2 = client.get(f"/evaluations/{eid}")
        assert r2.status_code == 200
        data = r2.json()
        assert data["final_json"] == {"score": 7}
        assert "chapter_text" in data

        # Search evaluations via API search endpoint (LIKE fallback)
        r3 = client.get("/search", params={"q": "Mystery", "top_k": 5})
        assert r3.status_code == 200
        results = r3.json()["results"]
        assert any(item["id"] == eid for item in results)