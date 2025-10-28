from types import SimpleNamespace

from writer_studio.teams import character_team as ct


class FakeTeam:
    def __init__(self):
        self.calls = []

    def run(self, task, termination_condition=None):
        # Capture the task and return a simple TaskResult-like object
        self.calls.append(task)
        return SimpleNamespace(messages=[{"role": "assistant", "content": "ok"}])


def test_review_character_uses_team_run(monkeypatch):
    fake = FakeTeam()
    monkeypatch.setattr(ct, "create_character_review_team", lambda **kwargs: fake)
    res = ct.review_character("Chapter text", '{"name": "A"}')
    assert hasattr(res, "messages")
    assert len(res.messages) == 1
    assert "Chapter text" in fake.calls[0]
    assert "Character Profile" in fake.calls[0]


def test_create_team_fallback_language(monkeypatch):
    # Use non-existent language to hit fallback en.yaml path
    class DummyGroup:
        def __init__(self, agents=None):
            self.agents = agents or []

    monkeypatch.setattr(ct, "RoundRobinGroupChat", DummyGroup)
    team = ct.create_character_review_team(answer_language="xx-YY")
    assert isinstance(team, DummyGroup)
    assert len(team.agents) == 4
