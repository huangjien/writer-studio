import json
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from writer_studio.logging import get_logger, init_logging
from writer_studio.persistence.db import (  # Character profiles; Character templates
    get_character_profile,
    get_character_profile_by_id,
    get_character_template_by_id,
    get_evaluation,
    init_db,
    list_character_profiles,
    list_character_templates,
    save_character_profile,
    save_character_template,
    save_evaluation,
    search_character_profiles,
    search_character_templates,
    search_evaluations,
    update_character_profile,
)
from writer_studio.teams.novel_eval_team import a_evaluate_chapter

init_logging(None)
log = get_logger("novel_eval.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB and vector search on startup
    init_db()
    yield


app = FastAPI(title="Writer Studio Novel Eval API", version="0.1.2", lifespan=lifespan)


class EvaluateRequest(BaseModel):
    chapter_text: str = Field(..., description="Raw chapter text to evaluate")
    model: Optional[str] = Field(None, description="LLM model name; defaults via env")
    provider: Optional[str] = Field(None, description="LLM provider; defaults via env")
    answer_language: Optional[str] = Field(
        None, description="Answer language code like zh-CN; defaults via env"
    )
    return_messages: bool = Field(
        False,
        description="Include all agent messages in response for transparency",
    )
    persist: bool = Field(
        True, description="Persist evaluation to SQLite with vector index"
    )


class AgentMessage(BaseModel):
    name: str
    content: str


class EvaluateResponse(BaseModel):
    id: Optional[int]
    final_text: Optional[str]
    final_json: Optional[Dict[str, Any]]
    messages: Optional[List[AgentMessage]]


# === Character Profiles & Templates API Models ===


class ProfileCreate(BaseModel):
    lang: str
    name: str
    profile: Dict[str, Any]


class ProfileUpdate(BaseModel):
    lang: Optional[str] = None
    name: Optional[str] = None
    profile: Dict[str, Any]


class TemplateCreate(BaseModel):
    lang: str
    name: str
    source: Optional[str] = None
    template: Dict[str, Any]


class UseTemplateRequest(BaseModel):
    name: str = Field(..., description="New character name")
    language: Optional[str] = Field(
        None, description="Override language; defaults to template lang or CHAR_LANG"
    )
    backstory: Optional[Any] = Field(
        None, description="Override backstory section for the new profile"
    )
    relationships: Optional[Any] = Field(
        None, description="Override relationships section for the new profile"
    )
    persist: bool = Field(True, description="Persist the new profile to SQLite")


# Startup handled via lifespan above


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/evaluations/{eval_id}")
async def get_eval(eval_id: int) -> Dict[str, Any]:
    data = await run_in_threadpool(get_evaluation, eval_id)
    if not data:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return data


@app.get("/search")
async def search(
    q: str = Query(..., min_length=1), top_k: int = Query(5, ge=1, le=50)
) -> Dict[str, Any]:
    results = await run_in_threadpool(search_evaluations, q, top_k)
    return {"results": results}


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(payload: EvaluateRequest) -> EvaluateResponse:
    try:
        log.info(
            "API evaluate: provider=%s model=%s lang=%s",
            payload.provider,
            payload.model,
            payload.answer_language,
        )
        result = await a_evaluate_chapter(
            chapter_text=payload.chapter_text,
            model=payload.model,
            answer_language=(
                payload.answer_language if payload.answer_language else None
            ),
            provider=payload.provider,
        )
    except Exception as e:
        log.error("Evaluation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # Collect final message content
    final_text: Optional[str] = None
    if getattr(result, "messages", None):
        last_msg = result.messages[-1]
        final_text = getattr(last_msg, "content", None) or getattr(
            last_msg, "text", None
        )

    # Attempt to parse final JSON (Summarizer output)
    final_json: Optional[Dict[str, Any]] = None
    if final_text:
        try:
            final_json = json.loads(final_text)
        except Exception:
            final_json = None

    messages: Optional[List[AgentMessage]] = None
    if payload.return_messages and getattr(result, "messages", None):
        messages = []
        for msg in result.messages:
            name = (
                getattr(msg, "source", None) or getattr(msg, "name", None) or "message"
            )
            content = (
                getattr(msg, "content", None) or getattr(msg, "text", None) or str(msg)
            )
            messages.append(AgentMessage(name=name, content=content))

    # Persist
    eval_id: Optional[int] = None
    if payload.persist:
        # Estimate tokens roughly (same heuristic as CLI)
        def _safe_token_count(text: str, model_name: str) -> int:
            try:
                import tiktoken  # type: ignore

                try:
                    enc = tiktoken.encoding_for_model(model_name)
                except Exception:
                    if "gpt-4o" in (model_name or "") or "-o" in (model_name or ""):
                        enc = tiktoken.get_encoding("o200k_base")
                    else:
                        enc = tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(text or ""))
            except Exception:
                return len((text or "").split())

        input_tokens = _safe_token_count(
            payload.chapter_text, payload.model or "unknown"
        )
        output_tokens = 0
        for msg in getattr(result, "messages", []) or []:
            content = getattr(msg, "content", None) or getattr(msg, "text", None)
            if content:
                output_tokens += _safe_token_count(content, payload.model or "unknown")
        total_tokens = input_tokens + output_tokens

        # Calculate actual rounds used (4 agents per round)
        actual_rounds = len(result.messages) // 4 if result.messages else 0

        eval_id = await run_in_threadpool(
            save_evaluation,
            payload.provider,
            payload.model,
            payload.answer_language,
            actual_rounds,
            input_tokens,
            output_tokens,
            total_tokens,
            payload.chapter_text,
            final_text,
            final_json,
        )

    return EvaluateResponse(
        id=eval_id,
        final_text=final_text,
        final_json=final_json,
        messages=messages,
    )


# === Character Profiles REST ===


@app.get("/profiles")
async def list_profiles(
    language: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=1000)
) -> Dict[str, Any]:
    items = await run_in_threadpool(list_character_profiles, language, limit)
    return {"results": items}


@app.get("/profiles/by_name")
async def get_profile_by_name(
    language: str = Query(...), name: str = Query(...)
) -> Dict[str, Any]:
    data = await run_in_threadpool(get_character_profile, language, name)
    if not data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return data


@app.post("/profiles")
async def create_profile(payload: ProfileCreate) -> Dict[str, Any]:
    row_id = await run_in_threadpool(
        save_character_profile, payload.lang, payload.name, payload.profile
    )
    return {"id": row_id}


@app.put("/profiles/{profile_id}")
async def update_profile(profile_id: int, payload: ProfileUpdate) -> Dict[str, Any]:
    ok = await run_in_threadpool(
        update_character_profile,
        profile_id,
        payload.profile,
        payload.name,
        payload.lang,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Profile not found or not updated")
    return {"updated": True}


@app.get("/profiles/search")
async def search_profiles(
    language: Optional[str] = Query(None),
    name_like: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    field: Optional[str] = Query(None),
    value: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
) -> Dict[str, Any]:
    items = await run_in_threadpool(
        search_character_profiles,
        language,
        name_like,
        q,
        field,
        value,
        limit,
    )
    return {"results": items}


@app.get("/profiles/{profile_id}")
async def get_profile(profile_id: int) -> Dict[str, Any]:
    data = await run_in_threadpool(get_character_profile_by_id, profile_id)
    if not data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return data


# === Character Templates REST ===


@app.post("/templates")
async def create_template(payload: TemplateCreate) -> Dict[str, Any]:
    row_id = await run_in_threadpool(
        save_character_template,
        payload.lang,
        payload.name,
        payload.template,
        payload.source,
    )
    return {"id": row_id}


@app.get("/templates")
async def list_templates(
    language: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=1000)
) -> Dict[str, Any]:
    items = await run_in_threadpool(list_character_templates, language, limit)
    return {"results": items}


@app.get("/templates/search")
async def search_templates(
    language: Optional[str] = Query(None),
    name_like: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    field: Optional[str] = Query(None),
    value: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
) -> Dict[str, Any]:
    items = await run_in_threadpool(
        search_character_templates,
        language,
        name_like,
        q,
        field,
        value,
        limit,
    )
    return {"results": items}


@app.get("/templates/{template_id}")
async def get_template(template_id: int) -> Dict[str, Any]:
    t = await run_in_threadpool(get_character_template_by_id, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@app.post("/templates/{template_id}/use")
async def use_template(template_id: int, payload: UseTemplateRequest) -> Dict[str, Any]:
    t = await run_in_threadpool(get_character_template_by_id, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    template_lang = t.get("lang")
    language = payload.language or template_lang or os.getenv("CHAR_LANG", "zh-CN")
    defaults: Dict[str, Any] = t.get("template") or {}
    # Build new profile from template defaults with optional overrides
    new_profile: Dict[str, Any] = dict(defaults)
    if payload.backstory is not None:
        new_profile["backstory"] = payload.backstory
    if payload.relationships is not None:
        rel = payload.relationships
        try:
            # Normalize relationships: if dict with 'allies', flatten to list
            if (
                isinstance(rel, dict)
                and "allies" in rel
                and isinstance(rel["allies"], list)
            ):
                new_profile["relationships"] = rel["allies"]
            elif isinstance(rel, list):
                new_profile["relationships"] = rel
            else:
                new_profile["relationships"] = rel
        except Exception:
            new_profile["relationships"] = rel
    new_profile["name"] = payload.name

    row_id: Optional[int] = None
    if payload.persist:
        row_id = await run_in_threadpool(
            save_character_profile, language, payload.name, new_profile
        )
    return {
        "id": row_id,
        "lang": language,
        "name": payload.name,
        "profile": new_profile,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
