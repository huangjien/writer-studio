from fastapi.testclient import TestClient

import writer_studio.persistence.db as db
from writer_studio.api.server import app


def _setup_tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "api_templates_create.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


def test_create_template_and_list(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    with TestClient(app) as client:
        r = client.post(
            "/templates",
            json={
                "lang": "en",
                "name": "CreateList",
                "source": "Fiction",
                "template": {"role": "Hero"},
            },
        )
        assert r.status_code == 200
        tid = r.json()["id"]
        assert isinstance(tid, int) and tid > 0

        r2 = client.get("/templates", params={"language": "en"})
        assert r2.status_code == 200
        assert any(it["name"] == "CreateList" for it in r2.json()["results"])