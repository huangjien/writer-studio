from fastapi.testclient import TestClient

import writer_studio.persistence.db as db
from writer_studio.api.server import app


def _setup_tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "api_profiles_create.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


def test_create_profile_and_by_name_not_found(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    with TestClient(app) as client:
        r = client.post(
            "/profiles",
            json={"lang": "en", "name": "Alice", "profile": {"role": "Mage"}},
        )
        assert r.status_code == 200
        assert isinstance(r.json()["id"], int)

        r2 = client.get(
            "/profiles/by_name", params={"language": "en", "name": "Missing"}
        )
        assert r2.status_code == 404