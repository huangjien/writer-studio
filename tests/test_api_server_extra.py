from types import SimpleNamespace

from fastapi.testclient import TestClient

import writer_studio.api.server as api_server
import writer_studio.persistence.db as db
from writer_studio.api.server import app


def _setup_tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "api_extra.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


def test_update_profile_and_search_field(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    pid = db.save_character_profile(
        "en",
        "Bob Mage",
        {
            "name": "Bob Mage",
            "role": "Mage",
            "backstory": "Arcane",
            "relationships": {"allies": ["Friend"]},
        },
    )
    assert isinstance(pid, int) and pid > 0

    with TestClient(app) as client:
        # Update profile: change role, name, and lang
        r = client.put(
            f"/profiles/{pid}",
            json={
                "profile": {
                    "name": "Bob Mage",
                    "role": "Wizard",
                    "relationships": {"allies": ["Friend"]},
                },
                "name": "Bob W",
                "lang": "fr",
            },
        )
        assert r.status_code == 200
        assert r.json()["updated"] is True

        # Verify updates
        r2 = client.get(f"/profiles/{pid}")
        assert r2.status_code == 200
        body = r2.json()
        assert body["name"] == "Bob W"
        assert body["lang"] == "fr"
        assert body["profile"]["role"] == "Wizard"

        # Search by JSON field
        r3 = client.get(
            "/profiles/search",
            params={"field": "relationships.allies", "value": "Friend"},
        )
        assert r3.status_code == 200
        names = [it["name"] for it in r3.json()["results"]]
        assert any("Bob" in n for n in names)


def test_update_profile_not_found(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()
    with TestClient(app) as client:
        r = client.put(
            "/profiles/999999",
            json={"profile": {"name": "X"}},
        )
        assert r.status_code == 404


def test_evaluate_flow_parsing_and_persist(tmp_path, monkeypatch):
    _setup_tmp_db(tmp_path, monkeypatch)
    db.init_db()

    class Msg(SimpleNamespace):
        pass

    # Stub out team run and persistence
    async def fake_run(
        chapter_text: str, model=None, answer_language=None, provider=None
    ):
        messages = [
            Msg(source="Planner", content="plan"),
            Msg(source="Critic", content="crit"),
            Msg(source="Summarizer", content='{"score": 7, "notes": "ok"}'),
        ]
        return SimpleNamespace(messages=messages)

    captured = {}

    def fake_save_eval(
        provider,
        model,
        lang,
        rounds,
        in_toks,
        out_toks,
        total_toks,
        input_text,
        final_text,
        final_json,
    ):
        captured.update(
            {
                "provider": provider,
                "model": model,
                "lang": lang,
                "rounds": rounds,
                "in": in_toks,
                "out": out_toks,
                "total": total_toks,
                "final_text": final_text,
                "final_json": final_json,
            }
        )
        return 42

    monkeypatch.setattr(api_server, "a_evaluate_chapter", fake_run)
    monkeypatch.setattr(api_server, "save_evaluation", fake_save_eval)

    with TestClient(app) as client:
        r = client.post(
            "/evaluate",
            json={
                "chapter_text": "hello world",
                "model": "gpt-4o-mini",
                "provider": "openai",
                "answer_language": "en",
                "return_messages": True,
                "persist": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == 42
        assert body["final_json"]["score"] == 7
        assert isinstance(body.get("messages"), list) and len(body["messages"]) == 3
        # Token counts captured
        assert captured["total"] >= captured["in"]


# EOF