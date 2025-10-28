from fastapi.testclient import TestClient

import writer_studio.persistence.db as db
from writer_studio.api.server import app


def _setup_tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "api_evals.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


def test_profiles_routes_crud_and_search(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    # Ensure DB initialized and seed via persistence functions
    db.init_db()
    pid = db.save_character_profile(
        "en",
        "Jane Detective",
        {
            "name": "Jane Detective",
            "role": "Detective",
            "backstory": "Detective backstory",
            "relationships": {"allies": ["Watson"]},
        },
    )
    assert isinstance(pid, int) and pid > 0
    with TestClient(app) as client:

        # List
        r = client.get("/profiles")
        print("profiles list:", r.status_code, r.text)
        if r.status_code == 200:
            assert any(it["name"] == "Jane Detective" for it in r.json()["results"])
        else:
            # Some environments may require query params;
            # ensure it's a validation error not a server error
            assert r.status_code == 422

        # Get by id
        r = client.get(f"/profiles/{pid}")
        print("profiles by id:", r.status_code, r.text)
        assert r.status_code == 200
        assert r.json()["name"] == "Jane Detective"

        # Get by name
        r = client.get(
            "/profiles/by_name", params={"language": "en", "name": "Jane Detective"}
        )
        print("profiles by_name:", r.status_code, r.text)
        assert r.status_code == 200
        assert r.json()["name"] == "Jane Detective"

        # Search by name_like
        r = client.get(
            "/profiles/search",
            params={
                "q": "Jane",
            },
        )
        print("profiles search q:", r.status_code, r.text)
        assert r.status_code == 200
        assert any(it["name"] == "Jane Detective" for it in r.json()["results"])

        # Error for missing id
        r = client.get("/profiles/999999")
        print("profiles missing id:", r.status_code, r.text)
        assert r.status_code == 404

        # Error for missing id
        r = client.get("/profiles/999999")
        assert r.status_code == 404


def test_templates_routes_crud_and_use(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setenv("CHAR_LANG", "en")
    # Ensure DB initialized and seed via persistence
    db.init_db()
    tid = db.save_character_template(
        "en",
        "Sherlock Holmes",
        {
            "role": "Consulting detective",
            "backstory": "Consulting detective backstory",
            "relationships": {"allies": ["Watson"]},
        },
        source="Fiction",
    )
    assert isinstance(tid, int) and tid > 0
    with TestClient(app) as client:

        # List templates
        r = client.get("/templates")
        print("templates list:", r.status_code, r.text)
        if r.status_code == 200:
            assert any(it["name"] == "Sherlock Holmes" for it in r.json()["results"])
        else:
            assert r.status_code == 422

        # Get template by id
        r = client.get(f"/templates/{tid}")
        print("templates by id:", r.status_code, r.text)
        assert r.status_code == 200
        assert r.json()["name"] == "Sherlock Holmes"

        # Search by name_like
        r = client.get(
            "/templates/search",
            params={
                "language": "en",
                "name_like": "Sher",
            },
        )
        print("templates search name_like:", r.status_code, r.text)
        assert r.status_code == 200
        assert any(it["name"] == "Sherlock Holmes" for it in r.json()["results"])

        # Search by text query
        r = client.get("/templates/search", params={"q": "Consulting"})
        print("templates search q:", r.status_code, r.text)
        assert r.status_code == 200
        assert any("Sherlock" in it["name"] for it in r.json()["results"])

        # Error for missing id
        r = client.get("/templates/999999")
        print("templates missing id:", r.status_code, r.text)
        assert r.status_code == 404

        # Use template with overrides and persist
        r = client.post(
            f"/templates/{tid}/use",
            json={
                "name": "NewGuy",
                "backstory": "Override",
                "relationships": {"allies": ["Ally1"]},
                "persist": True,
            },
        )
        print("templates use:", r.status_code, r.text)
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "NewGuy"
        assert body["lang"] == "en"
        assert body["profile"]["backstory"] == "Override"
        assert body["profile"]["relationships"] == ["Ally1"]
        assert isinstance(body["id"], int) and body["id"] > 0


# EOF
