import os
from pathlib import Path
from typing import Optional

import yaml
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

from writer_studio.logging import get_logger

DEFAULT_MODEL = os.getenv("CHAR_TEAM_MODEL", "gpt-4o-mini")
DEFAULT_ANSWER_LANGUAGE = os.getenv("CHAR_TEAM_LANG", "zh-CN")
DEFAULT_PROVIDER = os.getenv("CHAR_TEAM_PROVIDER", "openai").lower()
log = get_logger("character_review.team")


def _build_model_client(model: Optional[str] = None, provider: Optional[str] = None):
    use_model = model or DEFAULT_MODEL
    use_provider = (provider or DEFAULT_PROVIDER).lower()
    if use_provider != "openai":
        raise ValueError(f"Unsupported provider for character team: {use_provider}")
    return OpenAIChatCompletionClient(model=use_model)


def _load_task_config(answer_language: str) -> dict:
    base_dir_env = os.getenv("CHAR_TASKS_DIR")
    base_dir = (
        Path(base_dir_env)
        if base_dir_env
        else Path(__file__).resolve().parents[3] / "tasks" / "character_profile"
    )
    candidate = base_dir / f"{answer_language}.yaml"
    if not candidate.exists():
        log.warning(
            "Character task config for lang=%s not found at %s; "
            "falling back to en.yaml",
            answer_language,
            candidate,
        )
        candidate = base_dir / "en.yaml"
    with candidate.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_character_review_team(
    model: Optional[str] = None,
    answer_language: str = DEFAULT_ANSWER_LANGUAGE,
    provider: Optional[str] = None,
) -> RoundRobinGroupChat:
    cfg = _load_task_config(answer_language)
    agents_cfg = cfg.get("agents", {})
    fallback_model = model or DEFAULT_MODEL
    fallback_provider = provider or DEFAULT_PROVIDER

    # Define agents
    critic_cfg = agents_cfg.get("LiteraryPsychologist", {})
    critic_msg = critic_cfg.get("system_message", "Analyze identity and psychology.")
    critic_model = critic_cfg.get("model", fallback_model)
    critic_provider = critic_cfg.get("provider", fallback_provider)
    critic = AssistantAgent(
        name="LiteraryPsychologist",
        model_client=_build_model_client(critic_model, critic_provider),
        system_message=critic_msg,
    )

    role_cfg = agents_cfg.get("NarrativeRoleAnalyst", {})
    role_msg = role_cfg.get("system_message", "Analyze role, symbolism, and function.")
    role_model = role_cfg.get("model", fallback_model)
    role_provider = role_cfg.get("provider", fallback_provider)
    role_analyst = AssistantAgent(
        name="NarrativeRoleAnalyst",
        model_client=_build_model_client(role_model, role_provider),
        system_message=role_msg,
    )

    continuity_cfg = agents_cfg.get("ContinuityReviewer", {})
    cont_msg = continuity_cfg.get(
        "system_message", "Check continuity and relationships."
    )
    cont_model = continuity_cfg.get("model", fallback_model)
    cont_provider = continuity_cfg.get("provider", fallback_provider)
    continuity = AssistantAgent(
        name="ContinuityReviewer",
        model_client=_build_model_client(cont_model, cont_provider),
        system_message=cont_msg,
    )

    summarizer_cfg = agents_cfg.get("Summarizer", {})
    sum_msg = summarizer_cfg.get(
        "system_message", "Output a single JSON matching the template keys."
    )
    sum_model = summarizer_cfg.get("model", fallback_model)
    sum_provider = summarizer_cfg.get("provider", fallback_provider)
    summarizer = AssistantAgent(
        name="Summarizer",
        model_client=_build_model_client(sum_model, sum_provider),
        system_message=sum_msg,
    )

    chat = RoundRobinGroupChat(agents=[critic, role_analyst, continuity, summarizer])
    return chat


def review_character(
    chapter_text: str,
    character_profile_json: str,
    model: Optional[str] = None,
    answer_language: str = DEFAULT_ANSWER_LANGUAGE,
    provider: Optional[str] = None,
) -> TaskResult:
    team = create_character_review_team(
        model=model, answer_language=answer_language, provider=provider
    )

    cfg = _load_task_config(answer_language)
    max_rounds = cfg.get("max_rounds", 4)
    preamble = cfg.get("task", {}).get(
        "preamble",
        (
            "Discuss character based on the chapter and provided profile; "
            "summarizer outputs JSON."
        ),
    )

    task = (
        f"{preamble}\n\n"
        "Chapter:\n" + chapter_text + "\n\n"
        "Character Profile (JSON):\n" + character_profile_json + "\n"
    )

    log.debug(
        "Character review: lang=%s model=%s provider=%s",
        answer_language,
        model or DEFAULT_MODEL,
        provider or DEFAULT_PROVIDER,
    )
    result = team.run(
        task,
        termination_condition=MaxMessageTermination(max_messages=max_rounds),
    )
    return result
