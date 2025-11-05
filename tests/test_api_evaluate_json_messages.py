from types import SimpleNamespace
from fastapi.testclient import TestClient

from writer_studio.api.server import app
import writer_studio.api.server as server_mod


class DummyResult:
    def __init__(self, messages):
        self.messages = messages


def test_evaluate_parses_final_json_and_returns_messages(monkeypatch):
    # Stub a_evaluate_chapter to return a JSON string in the final message
    messages = [
        SimpleNamespace(name="Critic", content="Interim"),
        SimpleNamespace(name="Summarizer", content='{"score": 5, "notes": "ok"}'),
    ]

    async def _stub_eval(**kwargs):
        return DummyResult(messages)

    monkeypatch.setattr(server_mod, "a_evaluate_chapter", _stub_eval)

    with TestClient(app) as client:
        r = client.post(
            "/evaluate",
            json={
                "chapter_text": "Hello",
                "persist": False,
                "return_messages": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["final_json"]["score"] == 5
        assert isinstance(body.get("messages"), list) and len(body["messages"]) == 2
        assert body["messages"][-1]["name"] == "Summarizer"


def test_evaluate_handles_plain_text_final_message(monkeypatch):
    # Stub a_evaluate_chapter to return a plain text in the final message
    messages = [
        SimpleNamespace(name="Summarizer", content="final plain text"),
    ]

    async def _stub_eval(**kwargs):
        return DummyResult(messages)

    monkeypatch.setattr(server_mod, "a_evaluate_chapter", _stub_eval)

    with TestClient(app) as client:
        r = client.post(
            "/evaluate",
            json={
                "chapter_text": "Hi",
                "persist": False,
                "return_messages": False,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["final_text"] == "final plain text"
        assert body.get("final_json") is None