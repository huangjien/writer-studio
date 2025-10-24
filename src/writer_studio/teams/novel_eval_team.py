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
log = get_logger("novel_eval.team")


def _build_model_client(model: Optional[str] = None) -> OpenAIChatCompletionClient:
    """Create the OpenAI model client using environment configuration.

    Requires `OPENAI_API_KEY` to be set in the environment.
    """
    chosen_model = model or DEFAULT_MODEL
    log.debug("Building model client: model=%s", chosen_model)
    return OpenAIChatCompletionClient(model=chosen_model)


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
            log.info("Loaded task config: %s", candidate)
            return data
    except Exception as e:
        log.error("Failed to load task config from %s: %s", candidate, e)
        return {}


def create_novel_eval_team(
    model: Optional[str] = None,
    max_rounds: int = 4,
    answer_language: str = DEFAULT_ANSWER_LANGUAGE,
) -> RoundRobinGroupChat:
    """Construct a RoundRobinGroupChat team for chapter evaluation.

    Agents:
    - LiteraryCritic: theme, pacing, voice; 0–10 score.
    - CopyEditor: grammar, clarity, readability; 0–10 score.
    - ContinuityChecker: plot logic, consistency; 0–10 score.
    - Summarizer: aggregate scores and produce final JSON summary.

    All agents must respond in the specified `answer_language`.
    """
    log.info(
        "Creating team: model=%s max_rounds=%d lang=%s",
        model or DEFAULT_MODEL,
        max_rounds,
        answer_language,
    )
    model_client = _build_model_client(model)

    cfg = _load_task_config(answer_language)
    agents_cfg = cfg.get("agents", {})

    critic_msg = agents_cfg.get("LiteraryCritic", {}).get(
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

    critic = AssistantAgent(
        name="LiteraryCritic",
        model_client=model_client,
        system_message=critic_msg,
    )

    copy_msg = agents_cfg.get("CopyEditor", {}).get(
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

    copy_editor = AssistantAgent(
        name="CopyEditor",
        model_client=model_client,
        system_message=copy_msg,
    )

    continuity_msg = agents_cfg.get("ContinuityChecker", {}).get(
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

    continuity = AssistantAgent(
        name="ContinuityChecker",
        model_client=model_client,
        system_message=continuity_msg,
    )

    summarizer_msg = agents_cfg.get("Summarizer", {}).get(
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

    summarizer = AssistantAgent(
        name="Summarizer",
        model_client=model_client,
        system_message=summarizer_msg,
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
) -> TaskResult:
    """Async: Run the evaluation team on the provided chapter text and return the TaskResult."""
    team = create_novel_eval_team(
        model=model, max_rounds=max_rounds, answer_language=answer_language
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
) -> TaskResult:
    """Sync wrapper around a_evaluate_chapter for convenience in CLI usage."""
    return asyncio.run(
        a_evaluate_chapter(
            chapter_text,
            model=model,
            max_rounds=max_rounds,
            answer_language=answer_language,
        )
    )
