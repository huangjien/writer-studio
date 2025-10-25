from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

from writer_studio.teams.novel_eval_team import (
    _build_model_client,
    create_novel_eval_team,
)


def test_build_model_client_openai(monkeypatch):
    monkeypatch.setenv("NOVEL_EVAL_PROVIDER", "openai")
    client = _build_model_client(model="gpt-4o-mini", provider="openai")
    assert isinstance(client, OpenAIChatCompletionClient)


def test_build_model_client_deepseek(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = _build_model_client(model="deepseek-r1", provider="deepseek")
    assert isinstance(client, OpenAIChatCompletionClient)


def test_build_model_client_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = _build_model_client(model="gemini-1.5-flash", provider="gemini")
    assert isinstance(client, OpenAIChatCompletionClient)


def test_create_team_fallback_language(monkeypatch):
    # Use a language code that does not exist to trigger fallback to en.yaml
    team = create_novel_eval_team(
        model="gpt-4o-mini", provider="openai", answer_language="xx-YY"
    )
    assert isinstance(team, RoundRobinGroupChat)


def test_agents_use_fallback_provider_openai(monkeypatch):
    # Ensure env defaults are openai
    monkeypatch.setenv("NOVEL_EVAL_PROVIDER", "openai")
    team = create_novel_eval_team(
        model="gpt-4o-mini", provider="openai", answer_language="en"
    )
    assert isinstance(team, RoundRobinGroupChat)


def test_per_agent_yaml_override(monkeypatch, tmp_path):
    # Create a temporary tasks directory with per-agent provider/model
    # overrides
    tasks_dir = tmp_path
    yaml_text = (
        "language: test\n\n"
        "agents:\n"
        "  LiteraryCritic:\n"
        "    provider: openai\n"
        "    model: gpt-4o-mini\n"
        "    system_message: |\n"
        "      Critic role. Respond in test.\n"
        "  CopyEditor:\n"
        "    provider: deepseek\n"
        "    model: deepseek-r1\n"
        "    system_message: |\n"
        "      Copy role. Respond in test.\n"
        "  ContinuityChecker:\n"
        "    provider: gemini\n"
        "    model: gemini-1.5-flash\n"
        "    system_message: |\n"
        "      Continuity role. Respond in test.\n"
        "  Summarizer:\n"
        "    provider: openai\n"
        "    model: gpt-4o-mini\n"
        "    system_message: |\n"
        "      Summarizer outputs JSON only. Respond in test.\n"
    )
    (tasks_dir / "test.yaml").write_text(yaml_text, encoding="utf-8")

    # Set required keys for deepseek and gemini client construction
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    # Point loader to our temporary tasks directory
    monkeypatch.setenv("NOVEL_EVAL_TASKS_DIR", str(tasks_dir))

    team = create_novel_eval_team(
        model="gpt-4o-mini", provider="openai", answer_language="test"
    )
    assert isinstance(team, RoundRobinGroupChat)
