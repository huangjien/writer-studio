import argparse
import json
import os
import sys
from pathlib import Path

from writer_studio.logging import get_logger, init_logging
from writer_studio.teams.novel_eval_team import evaluate_chapter


def _safe_token_count(text: str, model_name: str) -> int:
    try:
        import tiktoken  # type: ignore

        try:
            enc = tiktoken.encoding_for_model(model_name)
        except Exception:
            # Fallbacks for common OpenAI model families
            if "gpt-4o" in model_name or "-o" in model_name:
                enc = tiktoken.get_encoding("o200k_base")
            else:
                enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text or ""))
    except Exception:
        # Very rough fallback: count words as proxy
        return len((text or "").split())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="novel-eval",
        description=(
            "Evaluate a novel chapter using an Autogen " "RoundRobinGroupChat team."
        ),
    )
    parser.add_argument("chapter", help="Path to a text file containing the chapter.")
    parser.add_argument(
        "--model",
        default=os.getenv("NOVEL_EVAL_MODEL", "gpt-4o-mini"),
        help=(
            "Model name, e.g. gpt-4o-mini, deepseek-r1, "
            "gemini-1.5-flash, or an Ollama model."
        ),
    )
    parser.add_argument(
        "--provider",
        default=os.getenv("NOVEL_EVAL_PROVIDER", "openai"),
        choices=["openai", "deepseek", "gemini", "ollama"],
        help="LLM provider to use (default from NOVEL_EVAL_PROVIDER).",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the final JSON summary if available.",
    )
    parser.add_argument(
        "--lang",
        default=os.getenv("NOVEL_EVAL_LANG", "zh-CN"),
        help="Answer language (default: zh-CN).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("NOVEL_EVAL_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    args = parser.parse_args()

    init_logging(args.log_level)
    log = get_logger("novel_eval.cli")

    chapter_path = Path(args.chapter)
    if not chapter_path.exists():
        raise SystemExit(f"File not found: {chapter_path}")

    log.info(
        "Starting evaluation: provider=%s model=%s lang=%s file=%s",
        args.provider,
        args.model,
        args.lang,
        chapter_path,
    )

    text = chapter_path.read_text(encoding="utf-8")
    log.debug("Loaded chapter text: %d chars", len(text))

    result = evaluate_chapter(
        text,
        model=args.model,
        answer_language=args.lang,
        provider=args.provider,
    )
    log.info(
        "Team run completed; messages=%d",
        len(result.messages) if getattr(result, "messages", None) else 0,
    )

    # Print all messages for transparency
    if not args.json:
        print("=== Team Messages ===")
        for msg in result.messages:
            # Each message is a BaseChatMessage; print role and content
            # if present
            name = (
                getattr(msg, "source", None) or getattr(msg, "name", None) or "message"
            )
            content = (
                getattr(msg, "content", None) or getattr(msg, "text", None) or str(msg)
            )
            print(f"\n[{name}]\n{content}")

    # Attempt to locate the summarizer's JSON output in the last message
    final_text = None
    if result.messages:
        last_msg = result.messages[-1]
        final_text = getattr(last_msg, "content", None) or getattr(
            last_msg, "text", None
        )

    if args.json and final_text:
        try:
            parsed = json.loads(final_text)
            print(json.dumps(parsed, indent=2))
        except Exception:
            # If not valid JSON, print raw content
            log.warning("Final message is not valid JSON; printing raw content")
            print(final_text)
    elif args.json:
        print("{}")

    # Token usage (estimated)
    input_tokens = _safe_token_count(text, args.model)
    output_tokens = 0
    for msg in result.messages:
        content = getattr(msg, "content", None) or getattr(msg, "text", None)
        if content:
            output_tokens += _safe_token_count(content, args.model)

    total_tokens = input_tokens + output_tokens

    # Respect --json: keep stdout clean; write metrics to stderr
    lines = [
        "=== Token Usage (estimated) ===",
        f"provider: {args.provider}",
        f"model: {args.model}",
        f"input_tokens: {input_tokens}",
        f"output_tokens: {output_tokens}",
        f"total_tokens: {total_tokens}",
    ]
    log.debug(
        "Token usage: input=%d output=%d total=%d",
        input_tokens,
        output_tokens,
        total_tokens,
    )
    if args.json:
        sys.stderr.write("\n" + "\n".join(lines) + "\n")
    else:
        print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
