import builtins

import pytest

from writer_studio.teams.novel_eval_team import (
    _build_model_client,
    _load_task_config,
    a_evaluate_chapter,
    evaluate_chapter,
)


def test_build_model_client_missing_api_keys(monkeypatch):
    # DeepSeek missing key
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        _build_model_client(model="deepseek-r1", provider="deepseek")

    # Gemini missing key
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        _build_model_client(model="gemini-1.5-flash", provider="gemini")


def test_build_model_client_unsupported_provider():
    with pytest.raises(ValueError):
        _build_model_client(model="gpt-4o-mini", provider="unknownprov")


def test_build_model_client_ollama_import_failure(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "autogen_ext.models.ollama" or name.startswith(
            "autogen_ext.models.ollama"
        ):
            raise ImportError("forced failure for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError):
        _build_model_client(model="qwen3:8b", provider="ollama")


def test_load_task_config_invalid_yaml(monkeypatch, tmp_path):
    tasks_dir = tmp_path
    bad_yaml = ":- bad"
    (tasks_dir / "bad.yaml").write_text(bad_yaml, encoding="utf-8")
    monkeypatch.setenv("NOVEL_EVAL_TASKS_DIR", str(tasks_dir))
    data = _load_task_config("bad")
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_a_evaluate_chapter_runs_with_stub(monkeypatch, tmp_path):
    # Provide a tasks file with schema so the function appends it
    tasks_dir = tmp_path
    yaml_text = (
        "language: test2\n\n"
        "task:\n"
        "  preamble: |\n"
        "    Preamble text.\n"
        "  schema: |\n"
        '    {"type": "object"}\n'
    )
    (tasks_dir / "test2.yaml").write_text(yaml_text, encoding="utf-8")
    monkeypatch.setenv("NOVEL_EVAL_TASKS_DIR", str(tasks_dir))

    # Stub RoundRobinGroupChat to avoid external dependencies
    class FakeResult:
        def __init__(self):
            self.messages = []

    class FakeTeam:
        def __init__(self, agents, termination_condition=None):
            self.agents = agents
            self.termination_condition = termination_condition

        async def run(self, task: str):
            assert "CHAPTER:" in task
            assert "Schema:" in task
            return FakeResult()

    import writer_studio.teams.novel_eval_team as mod

    monkeypatch.setattr(mod, "RoundRobinGroupChat", FakeTeam)

    res = await a_evaluate_chapter(
        chapter_text="Some text",
        model="gpt-4o-mini",
        answer_language="test2",
        provider="openai",
    )
    assert hasattr(res, "messages")


def test_evaluate_chapter_sync_wrapper(monkeypatch, tmp_path):
    # Reuse the stub team for the sync wrapper
    tasks_dir = tmp_path
    yaml_text = "language: en\n"
    (tasks_dir / "en.yaml").write_text(yaml_text, encoding="utf-8")
    monkeypatch.setenv("NOVEL_EVAL_TASKS_DIR", str(tasks_dir))

    class FakeResult:
        def __init__(self):
            self.messages = ["ok"]

    class FakeTeam:
        def __init__(self, agents, termination_condition=None):
            self.agents = agents
            self.termination_condition = termination_condition

        async def run(self, task: str):
            return FakeResult()

    import writer_studio.teams.novel_eval_team as mod

    monkeypatch.setattr(mod, "RoundRobinGroupChat", FakeTeam)

    res = evaluate_chapter(
        chapter_text="Sync text",
        model="gpt-4o-mini",
        answer_language="en",
        provider="openai",
    )
    assert hasattr(res, "messages") and res.messages == ["ok"]
