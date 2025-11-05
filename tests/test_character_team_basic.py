from pathlib import Path

import pytest

from writer_studio.teams.character_team import _build_model_client, _load_task_config


def test_load_task_config_default_en(tmp_path, monkeypatch):
    # Point CHAR_TASKS_DIR to the repo tasks to ensure file exists
    base_tasks = Path(__file__).resolve().parents[1] / "tasks" / "character_profile"
    monkeypatch.setenv("CHAR_TASKS_DIR", str(base_tasks))
    cfg = _load_task_config("en")
    assert isinstance(cfg, dict)
    assert "task" in cfg
    assert "template" in cfg["task"]


def test_build_model_client_openai(monkeypatch):
    # character_team supports only openai provider
    client = _build_model_client(model="gpt-4o-mini", provider="openai")
    # The specific type isn’t strictly required; ensure object returned
    assert client is not None


def test_build_model_client_unsupported_provider():
    with pytest.raises(ValueError):
        _build_model_client(model="any", provider="ollama")


# EOF