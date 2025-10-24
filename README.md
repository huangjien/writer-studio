# Writer Studio

Writer Studio is a platform for writing and editing documents.

## Novel Chapter Evaluation (Autogen RoundRobinGroupChat)

This repo includes a multi-agent evaluation team powered by AutoGen (`autogen-agentchat` + `autogen-ext`).
It accepts a chapter of a novel and produces structured feedback and a JSON summary.

### Install

- Ensure Python `>=3.13`.
- Set your OpenAI API key: `export OPENAI_API_KEY=...`.
- Install with the Autogen extras:

```
pip install -e .[autogen-stable]
```

### CLI Usage

```
novel-eval path/to/chapter.txt --model gpt-4o --rounds 4 --lang zh-CN
```

Flags:
- `--model`: OpenAI model (default: `gpt-4o-mini`).
- `--rounds`: Max round-robin turns (default: 4). With four agents, each speaks once.
- `--json`: Print only the final JSON summary if available.
- `--lang`: Answer language (default: `zh-CN`). All agents respond in this language.

Example:

```
novel-eval samples/chapter1.txt --json --lang zh-CN
```

### Programmatic Usage

```python
from writer_studio.teams.novel_eval_team import a_evaluate_chapter

chapter_text = "..."
result = await a_evaluate_chapter(chapter_text, model="gpt-4o", max_rounds=4, answer_language="zh-CN")
print(result.messages[-1].content)  # JSON summary from Summarizer
```

### Notes

- Models are configured via `autogen_ext.models.openai.OpenAIChatCompletionClient` and use `OPENAI_API_KEY`.
- Agents: `LiteraryCritic`, `CopyEditor`, `ContinuityChecker`, `Summarizer` (round-robin sequence).
- The Summarizer outputs a compact JSON with per-category scores, overall score, strengths, weaknesses, and action items.
- Default language can be overridden via `--lang` or env `NOVEL_EVAL_LANG`.

**Language Tasks**
- Stores per-language evaluation tasks in `tasks/novel_eval/` as YAML: `en.yaml`, `zh-CN.yaml`, `zh-TW.yaml`, `fr.yaml`, `de.yaml`, `it.yaml`, `es.yaml`, `ru.yaml`, `ko.yaml`, `jp.yaml`.
- The team loads `preamble` and agent `system_message` from the selected language file at startup. If the file is missing, it falls back to `en.yaml` and then built-in defaults.
- Override the tasks directory with `NOVEL_EVAL_TASKS_DIR` to point to an external path if needed.
- Example YAML:
  
  ```yaml
  language: en
  task:
    preamble: |
      Evaluate a novel chapter. Respond strictly in en. Summarizer outputs JSON only per the schema.
    schema: |
      {
        "overall_score": number,
        "strengths": [string],
        "weaknesses": [string],
        "continuity_issues": [string],
        "editing_suggestions": [string],
        "key_themes": [string],
        "action_items": [string]
      }
  agents:
    LiteraryCritic:
      system_message: |
        Act as a seasoned literary critic... Respond in en.
    CopyEditor:
      system_message: |
        Act as a professional copy editor... Respond in en.
    ContinuityChecker:
      system_message: |
        Act as a continuity checker... Respond in en.
    Summarizer:
      system_message: |
        Output only valid JSON per schema... Respond in en.
  ```

**Logging**
- Control verbosity with `--log-level` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). Default is `INFO`.
- Or set environment variable `NOVEL_EVAL_LOG_LEVEL` to override globally.
- Example:
  - `novel-eval samples/chapter1.txt --model gpt-4o-mini --rounds 3 --lang en --log-level DEBUG`
  - `export NOVEL_EVAL_LOG_LEVEL=WARNING && novel-eval samples/ch1.txt --lang fr`
- Logs include:
  - Startup configuration (model, rounds, language, file)
  - Task config loading and fallbacks
  - Team run lifecycle and message counts
  - JSON parsing warnings (if final message isn’t valid JSON)
  - Debug token usage summary