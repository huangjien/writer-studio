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
novel-eval path/to/chapter.txt --model gpt-4o --lang zh-CN
```

Flags:
- `--model`: OpenAI model (default: `gpt-4o-mini`).
- `--provider`: LLM provider (openai, deepseek, gemini, ollama). Defaults from `NOVEL_EVAL_PROVIDER`.
- `--json`: Print only the final JSON summary if available.
- `--lang`: Answer language (default: `zh-CN`). All agents respond in this language.

The maximum number of rounds is now configured in the language-specific YAML files (default: 4).

Example:

```
novel-eval samples/chapter1.txt --json --lang zh-CN
```

### Programmatic Usage

```python
from writer_studio.teams.novel_eval_team import a_evaluate_chapter

chapter_text = "..."
result = await a_evaluate_chapter(chapter_text, model="gpt-4o", answer_language="zh-CN")
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
  max_rounds: 4
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

## REST API

A lightweight FastAPI service exposes the chapter evaluator via REST.

- Start locally:
  - `make serve-api` then open `http://localhost:8000/docs`
- Endpoint:
  - `POST /evaluate`
  - Request body:
    ```json
    {
      "chapter_text": "...",
      "model": "qwen:8b",
      "provider": "ollama",
      "answer_language": "zh-CN",
      "return_messages": true
    }
    ```
  - Response body:
    ```json
    {
      "final_text": "...",            // last agent message
      "final_json": { /* parsed */ },   // summarizer JSON if valid
      "messages": [                     // included when return_messages=true
        {"name": "LiteraryCritic", "content": "..."}
      ]
    }
    ```

### Docker + Nginx

- Build and run with reverse proxy:
  - `docker compose up --build`
- Services:
  - `api`: FastAPI at `http://localhost:8000`
  - `nginx`: Front at `http://localhost:8080` (proxies to API)
- External resource:
  - `ollama`: External LLM runtime reachable at `OLLAMA_HOST` (default `http://localhost:11434`). Not included in Compose.
- Environment overrides:
  - `NOVEL_EVAL_PROVIDER`, `NOVEL_EVAL_MODEL`, `NOVEL_EVAL_LANG`, `NOVEL_EVAL_LOG_LEVEL`, `OLLAMA_HOST`, `NOVEL_EVAL_DB_PATH`
- Data persistence:
  - Compose mounts `./data` to `/data` in the API container; SQLite DB at `/data/evals.db`.
- Nginx config: `nginx.conf`

This API uses the existing team orchestration in `writer_studio.teams.novel_eval_team` and returns the Summarizer's JSON when available. To ensure the Summarizer is the final speaker, configure `max_rounds` in the language YAML files to be divisible by 4.

## Production (GCP) Deployment

For GCP deployment with 443-only external access:

- Use the production compose file: `docker-compose.prod.yml`.
  - Only Nginx exposes `443:443`.
  - The API service does NOT publish any host ports; it is reachable only via Nginx.
  - Ollama service does NOT publish `11434` in production.
- SSL termination in Nginx:
  - Provide certificates under `./certs` on the host:
    - `./certs/fullchain.pem` and `./certs/privkey.pem`
  - The file `nginx-ssl.conf` configures HTTPS and proxies to `api:8000`.
- Start services:
  - `docker compose -f docker-compose.prod.yml up -d --build`
- GCP firewall (Compute Engine):
  - Allow inbound TCP `443` to the VM.
  - Deny/block inbound `80`, `8000`, `11434`, and any other ports.
  - Optionally, restrict source ranges to your allowed CIDRs.
- Alternative: GCP HTTPS Load Balancer
  - If terminating TLS at the load balancer, you can keep Nginx on port 80 behind the LB.
  - In that case, expose only 80 internally and allow only LB health-check CIDRs; external traffic still enters via port 443 at the LB.

## Persistence & Search

The API persists evaluations to SQLite and (when available) indexes vectors with the `sqlite-vec` plugin.

- DB path: `NOVEL_EVAL_DB_PATH` (default `/data/evals.db`)
- Table: `evaluations`
  - `id`, `created_at`, `provider`, `model`, `lang`, `rounds`, `input_tokens`, `output_tokens`, `total_tokens`, `chapter_text`, `final_text`, `final_json`
- Virtual table: `eval_embeddings` (vec0) with dimension `NOVEL_EVAL_EMBED_DIM` (default 384)
- Endpoints:
  - `GET /evaluations/{id}` → fetch a stored evaluation
  - `GET /search?q=...&top_k=5` → vector similarity search (falls back to LIKE if vec0 not loaded)
- Persisting during evaluation:
  - `POST /evaluate` accepts `persist` (default `true`). When enabled, it saves the run and adds a vector row.

Note: Embeddings are deterministic, local pseudo-vectors (no network calls). If `sqlite-vec` fails to load, the API continues with basic LIKE search fallback.

  ```

**Logging**
- Control verbosity with `--log-level` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). Default is `INFO`.
- Or set environment variable `NOVEL_EVAL_LOG_LEVEL` to override globally.
- Example:
  - `novel-eval samples/chapter1.txt --model gpt-4o-mini --lang en --log-level DEBUG`
  - `export NOVEL_EVAL_LOG_LEVEL=WARNING && novel-eval samples/ch1.txt --lang fr`
- Logs include:
  - Startup configuration (model, language, file)
  - Task config loading and fallbacks
  - Team run lifecycle and message counts
  - JSON parsing warnings (if final message isn’t valid JSON)
  - Debug token usage summary

### LLM Providers and Models

Supported providers: `openai`, `deepseek`, `gemini`, `ollama`. You can set a global default via environment or override per run via CLI. Agents can also specify their own provider/model in YAML.

**Environment (.env)**

```
# Core provider and model
NOVEL_EVAL_PROVIDER=ollama                # openai | deepseek | gemini | ollama
NOVEL_EVAL_MODEL=qwen3:8b                 # e.g. gpt-4o-mini, deepseek-r1, gemini-1.5-flash, or Ollama tag
NOVEL_EVAL_LANG=zh-CN
NOVEL_EVAL_LOG_LEVEL=INFO

# OpenAI
OPENAI_API_KEY=

# DeepSeek (OpenAI-compatible)
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# Gemini (OpenAI-compatible endpoint)
GEMINI_API_KEY=
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

# Ollama (local)
OLLAMA_HOST=http://localhost:11434
```

- For `ollama`, pull the model locally first: `ollama pull qwen3:8b` and ensure the daemon is running.
- For `deepseek` and `gemini`, set the respective API keys; their endpoints are OpenAI-compatible.

**CLI Examples**

```
# Use env defaults (source .env first)
novel-eval samples/chapter1.txt

# Explicit provider + model override
novel-eval samples/chapter1.txt --provider ollama --model qwen3:8b --lang zh-CN
novel-eval samples/chapter1.txt --provider deepseek --model deepseek-r1
novel-eval samples/chapter1.txt --provider gemini --model gemini-1.5-flash
```

**Per-Agent YAML Overrides**

Add `provider` and `model` under specific agents to mix providers in one team:

```yaml
language: es
agents:
  LiteraryCritic:
    provider: ollama
    model: qwen3:8b
    system_message: |
      Crítico literario... Responder en es.
  CopyEditor:
    provider: openai
    model: gpt-4o-mini
    system_message: |
      Corrector de estilo... Responder en es.
  ContinuityChecker:
    provider: deepseek
    model: deepseek-r1
    system_message: |
      Comprobador de continuidad... Responder en es.
  Summarizer:
    provider: gemini
    model: gemini-1.5-flash
    system_message: |
      Salida solo JSON conforme al esquema... Responder en es.
```

**Notes**
- `OLLAMA_HOST` should be a base URL (no `/v1` suffix), e.g. `http://localhost:11434`.
- Gemini’s OpenAI-compatible endpoint supports a subset of features; structured output and tool calling may be limited.
- If an agent omits `provider`/`model` in YAML, it falls back to `NOVEL_EVAL_PROVIDER`/`NOVEL_EVAL_MODEL` or CLI arguments.

## Character Profiles & Templates

An interactive CLI to collect, save, search, and reuse character profiles. Profiles are structured per language-specific YAML templates in `tasks/character_profile/` (`en.yaml`, `zh-CN.yaml`). You can also create reusable templates based on historical or fictional persons and adapt them when creating new characters.

### CLI Commands

```
# Collect a character profile interactively (defaults to zh-CN)
character-profile collect --language zh-CN

# Save outputs
character-profile collect --language zh-CN \
  --json-out profile.json --yaml-out profile.yaml --persist

# Edit an existing profile by id (prefilled prompts)
character-profile collect --update --id 12

# Show/List
character-profile show --language zh-CN --name "李青"
character-profile list --language zh-CN

# Search by free text or JSON field value
character-profile search --language zh-CN --q 侦探
character-profile search --field relationships.allies --value 张三 --limit 100

# Collect a reusable template (history/fiction/person)
character-profile tcollect --language en --source "Fiction: Sherlock Holmes"

# List/Show templates
character-profile tlist --language en
character-profile tshow --id 5

# Use a template to create a new character (edit only backstory & relationships)
character-profile use_template --id 5 --name "Adrian Wu" --language en \
  --json-out profile.json --yaml-out profile.yaml --persist
```

### What Gets Saved

- `character_profiles` table: `id`, `created_at`, `updated_at`, `lang`, `name`, `profile_json`
- `character_templates` table: `id`, `created_at`, `updated_at`, `lang`, `name`, `source`, `template_json`
- DB path: `NOVEL_EVAL_DB_PATH` (default `/data/evals.db`).

### Template Sources and Reuse

- Templates can reference real historical figures or fictional characters via `--source` (e.g., `"History: 李白"`, `"Fiction: Holmes"`).
- `use_template` loads by `--id`, keeps most sections from the template, and prompts only `backstory` and `relationships` (plus `name`).
- The new character profile is saved to `character_profiles` and can be shown, listed, or searched.

### Search Behavior

- `--q` matches `%q%` in `name` or raw JSON text.
- `--field` + `--value` uses SQLite JSON1: `json_extract(<json>, '$.<field>') LIKE '%<value>%'`.
- `--language` filters results; combine with `--q` or `--field/--value`.

### Configuration

- `CHAR_LANG`: default language for the CLI (e.g., `zh-CN`, `en`).
- `CHAR_TASKS_DIR`: override the path to `tasks/character_profile/` YAMLs.
- When a language YAML is missing, the CLI falls back to `en.yaml`.

### Notes

- Prompts accept defaults when editing (`--update`); press Enter to keep current values.
- Lists show current items; pressing Enter immediately keeps the list.
- All outputs (`--json-out`, `--yaml-out`) are optional; saving to SQLite is controlled by `--persist` (default: true).