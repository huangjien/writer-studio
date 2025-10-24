import asyncio
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

DEFAULT_MODEL = os.getenv("NOVEL_EVAL_MODEL", "gpt-4o-mini")
DEFAULT_ANSWER_LANGUAGE = os.getenv("NOVEL_EVAL_LANG", "zh-CN")
DEFAULT_PROVIDER = os.getenv("NOVEL_EVAL_PROVIDER", "openai").lower()
log = get_logger("novel_eval.team")


def _build_model_client(model: Optional[str] = None, provider: Optional[str] = None):
    """Create a model client for the requested provider.

    Supported providers: openai, deepseek, gemini, ollama.
    - openai: requires `OPENAI_API_KEY` in env (or keyless if default SDK finds it)
    - deepseek: requires `DEEPSEEK_API_KEY`; uses OpenAI-compatible endpoint
    - gemini: requires `GEMINI_API_KEY`; uses OpenAI-compatible endpoint
    - ollama: requires local Ollama; optional `OLLAMA_HOST` (default http://localhost:11434)
    """
    chosen_model = model or DEFAULT_MODEL
    chosen_provider = (provider or DEFAULT_PROVIDER).lower()
    log.debug("Building model client: provider=%s model=%s", chosen_provider, chosen_model)

    if chosen_provider == "openai":
        return OpenAIChatCompletionClient(model=chosen_model)

    if chosen_provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set in environment")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        # For non-OpenAI endpoints, supply model_info capabilities.
        model_info = {
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "R1" if "reasoner" in chosen_model else "unknown",
            "structured_output": True,
        }
        return OpenAIChatCompletionClient(
            model=chosen_model,
            api_key=api_key,
            base_url=base_url,
            model_info=model_info,
        )

    if chosen_provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in environment")
        base_url = os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        model_info = {
            "vision": True,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
            "structured_output": True,
        }
        return OpenAIChatCompletionClient(
            model=chosen_model,
            api_key=api_key,
            base_url=base_url,
            model_info=model_info,
        )

    if chosen_provider == "ollama":
        try:
            from autogen_ext.models.ollama import OllamaChatCompletionClient  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "Ollama client not available. Install autogen-ext[ollama] and ensure Ollama is running."
            ) from e
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        # autogen Ollama client takes `host` without /v1 suffix
        return OllamaChatCompletionClient(model=chosen_model, host=host)

    raise ValueError(f"Unsupported provider: {chosen_provider}")


def _load_task_config(answer_language: str) -> dict:
    # Allow override via env var; otherwise use repo-root/tasks/novel_eval
    base_dir_env = os.getenv("NOVEL_EVAL_TASKS_DIR")
    if base_dir_env:
        base_dir = Path(base_dir_env)
    else:
        base_dir = Path(__file__).resolve().parents[3] / "tasks" / "novel_eval"
    lang_code = answer_language
    candidate = base_dir / f"{lang_code}.yaml"
    if not candidate.exists():
        log.warning(
            "Task config for lang=%s not found at %s; falling back to en.yaml", lang_code, candidate
        )
        candidate = base_dir / "en.yaml"
    try:
        with candidate.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                data = {}
            log.info("Loaded task config: %s", candidate)
            return data
    except Exception as e:
        log.error("Failed to load task config from %s: %s", candidate, e)
        return {}


def create_novel_eval_team(
    model: Optional[str] = None,
    max_rounds: int = 4,
    answer_language: str = DEFAULT_ANSWER_LANGUAGE,
    provider: Optional[str] = None,
) -> RoundRobinGroupChat:
    """Construct a RoundRobinGroupChat team for chapter evaluation.

    Agents:
    - LiteraryCritic: theme, pacing, voice; 0–10 score.
    - CopyEditor: grammar, clarity, readability; 0–10 score.
    - ContinuityChecker: plot logic, consistency; 0–10 score.
    - Summarizer: aggregate scores and produce final JSON summary.

    All agents must respond in the specified `answer_language`.
    """
    fallback_model = model or DEFAULT_MODEL
    fallback_provider = (provider or DEFAULT_PROVIDER).lower()
    log.info(
        "Creating team: default_model=%s provider=%s max_rounds=%d lang=%s",
        fallback_model,
        fallback_provider,
        max_rounds,
        answer_language,
    )

    cfg = _load_task_config(answer_language)
    agents_cfg = cfg.get("agents", {})

    critic_cfg = agents_cfg.get("LiteraryCritic", {})
    critic_msg = critic_cfg.get(
        "system_message",
        (
            f"""
            You are a seasoned literary critic.
            Analyze theme, character development, pacing, and narrative voice.
            Output:
            - Strengths (bulleted)
            - Weaknesses (bulleted)
            - Suggestions (short)
            End with 'Score: <number>' for 'literary_quality'.
            Respond in language: {answer_language}
            """
        ),
    )
    critic_model = critic_cfg.get("model", fallback_model)
    critic_provider = critic_cfg.get("provider", fallback_provider)

    critic = AssistantAgent(
        name="LiteraryCritic",
        model_client=_build_model_client(critic_model, critic_provider),
        system_message=critic_msg,
    )

    copy_cfg = agents_cfg.get("CopyEditor", {})
    copy_msg = copy_cfg.get(
        "system_message",
        (
            f"""
            You are a copy editor.
            Evaluate grammar, clarity, and readability.
            Provide concise edits (quote short spans only).
            End with 'Score: <number>' for 'readability_quality'.
            Respond in language: {answer_language}
            """
        ),
    )
    copy_model = copy_cfg.get("model", fallback_model)
    copy_provider = copy_cfg.get("provider", fallback_provider)

    copy_editor = AssistantAgent(
        name="CopyEditor",
        model_client=_build_model_client(copy_model, copy_provider),
        system_message=copy_msg,
    )

    continuity_cfg = agents_cfg.get("ContinuityChecker", {})
    continuity_msg = continuity_cfg.get(
        "system_message",
        (
            f"""
            You are a continuity checker.
            Identify plot holes, contradictions, timeline or POV issues.
            Mark issues with short references.
            End with 'Score: <number>' for 'continuity_quality'.
            Respond in language: {answer_language}
            """
        ),
    )
    continuity_model = continuity_cfg.get("model", fallback_model)
    continuity_provider = continuity_cfg.get("provider", fallback_provider)

    continuity = AssistantAgent(
        name="ContinuityChecker",
        model_client=_build_model_client(continuity_model, continuity_provider),
        system_message=continuity_msg,
    )

    summarizer_cfg = agents_cfg.get("Summarizer", {})
    summarizer_msg = summarizer_cfg.get(
        "system_message",
        (
            f"""
            You aggregate prior agents' findings into a concise JSON.
            Parse their 'Score: <number>' lines.
            Output ONLY valid JSON with keys:
            {{
              "scores": {{
                "literary_quality": <0-10>,
                "readability_quality": <0-10>,
                "continuity_quality": <0-10>
              }},
              "overall_score": <0-10 average>,
              "strengths": ["Summarize 3-5 bullets"],
              "weaknesses": ["Summarize 3-5 bullets"],
              "action_items": ["Concrete edits the author can make"],
              "notes": "One short paragraph"
            }}
            All natural-language fields MUST be written in: {answer_language}
            """
        ),
    )
    summarizer_model = summarizer_cfg.get("model", fallback_model)
    summarizer_provider = summarizer_cfg.get("provider", fallback_provider)

    summarizer = AssistantAgent(
        name="Summarizer",
        model_client=_build_model_client(summarizer_model, summarizer_provider),
        system_message=summarizer_msg,
    )

    log.debug(
        "Agent models/providers: critic=%s/%s copy_editor=%s/%s continuity=%s/%s summarizer=%s/%s",
        critic_model,
        critic_provider,
        copy_model,
        copy_provider,
        continuity_model,
        continuity_provider,
        summarizer_model,
        summarizer_provider,
    )

    termination = MaxMessageTermination(max_rounds)
    team = RoundRobinGroupChat(
        [critic, copy_editor, continuity, summarizer], termination_condition=termination
    )
    return team


async def a_evaluate_chapter(
    chapter_text: str,
    model: Optional[str] = None,
    max_rounds: int = 4,
    answer_language: str = DEFAULT_ANSWER_LANGUAGE,
    provider: Optional[str] = None,
) -> TaskResult:
    """Async: Run the evaluation team on the provided chapter text and return the TaskResult."""
    team = create_novel_eval_team(
        model=model, max_rounds=max_rounds, answer_language=answer_language, provider=provider
    )

    cfg = _load_task_config(answer_language)
    preamble = cfg.get("task", {}).get(
        "preamble",
        (
            f"All agents must answer in {answer_language}. Keep outputs concise and follow your role rules.\n\n"
            "Evaluate the following novel chapter. Each agent speaks once, stays concise, and follows their output rules.\n\n"
        ),
    )
    schema = cfg.get("task", {}).get("schema")

    task_parts = [preamble]
    if schema:
        task_parts.append("Schema:\n" + schema)
    task_parts.append(f"CHAPTER:\n\n{chapter_text}\n")
    task = "\n\n".join(task_parts)

    log.info("Running team: rounds=%d lang=%s", max_rounds, answer_language)
    result = await team.run(task=task)
    log.info(
        "Team finished. Messages=%d",
        len(result.messages) if getattr(result, "messages", None) else 0,
    )
    return result


def evaluate_chapter(
    chapter_text: str,
    model: Optional[str] = None,
    max_rounds: int = 4,
    answer_language: str = DEFAULT_ANSWER_LANGUAGE,
    provider: Optional[str] = None,
) -> TaskResult:
    """Sync wrapper around a_evaluate_chapter for convenience in CLI usage."""
    return asyncio.run(
        a_evaluate_chapter(
            chapter_text,
            model=model,
            max_rounds=max_rounds,
            answer_language=answer_language,
            provider=provider,
        )
    )
