from fastapi.testclient import TestClient

import writer_studio.persistence.db as db
from writer_studio.api.server import app


def _setup_tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "api_use_tmpl.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


def test_use_template_language_override_and_list_relationships(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    tid = db.save_character_template(
        "en",
        "Sherlock Variant",
        {"backstory": "B", "relationships": {"allies": ["Watson"]}},
        source="Fiction",
    )
    assert tid > 0

    with TestClient(app) as client:
        r = client.post(
            f"/templates/{tid}/use",
            json={
                "name": "NewHero",
                "language": "fr",
                "relationships": ["Lestrade", "Watson"],
                "persist": False,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["lang"] == "fr"  # override language
        assert body["profile"]["relationships"] == ["Lestrade", "Watson"]


def test_use_template_relationships_scalar(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    tid = db.save_character_template(
        "en",
        "Scalar Rel",
        {"backstory": "B", "relationships": {"allies": ["Ally"]}},
        source="Fiction",
    )
    assert tid > 0

    with TestClient(app) as client:
        r = client.post(
            f"/templates/{tid}/use",
            json={"name": "Solo", "relationships": "Friend", "persist": False},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["profile"]["relationships"] == "Friend"