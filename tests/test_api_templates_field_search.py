from fastapi.testclient import TestClient

import writer_studio.persistence.db as db
from writer_studio.api.server import app


def _setup_tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "api_tmpl_field.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


def test_templates_search_by_json_field(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    # Seed a template with nested relationships
    tid = db.save_character_template(
        "en",
        "Sherlock JSONField",
        {
            "role": "Detective",
            "relationships": {"allies": ["Watson", "Lestrade"]},
        },
        source="Fiction",
    )
    assert isinstance(tid, int) and tid > 0

    with TestClient(app) as client:
        r = client.get(
            "/templates/search",
            params={
                "language": "en",
                "field": "relationships.allies",
                "value": "Watson",
            },
        )
        assert r.status_code == 200
        names = [it["name"] for it in r.json()["results"]]
        assert any("Sherlock" in n for n in names)

        # Negative case: value not present
        r2 = client.get(
            "/templates/search",
            params={
                "language": "en",
                "field": "relationships.allies",
                "value": "Irene",
            },
        )
        assert r2.status_code == 200
        assert all("Irene" not in it["name"] for it in r2.json()["results"])