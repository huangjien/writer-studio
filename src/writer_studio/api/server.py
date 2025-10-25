import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from writer_studio.logging import get_logger, init_logging
from writer_studio.persistence.db import (
    get_evaluation,
    init_db,
    save_evaluation,
    search_evaluations,
)
from writer_studio.teams.novel_eval_team import a_evaluate_chapter

init_logging(None)
log = get_logger("novel_eval.api")
app = FastAPI(title="Writer Studio Novel Eval API", version="0.1.2")


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


@app.on_event("startup")
def _startup() -> None:
    # Initialize DB and vector search
    init_db()


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
