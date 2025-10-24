import os
import json
import sqlite3
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from writer_studio.logging import get_logger

log = get_logger("novel_eval.db")

DB_PATH = os.getenv("NOVEL_EVAL_DB_PATH", "/data/evals.db")
EMBED_DIM = int(os.getenv("NOVEL_EVAL_EMBED_DIM", "384"))


def _ensure_dir() -> None:
    base = os.path.dirname(DB_PATH)
    if base and not os.path.exists(base):
        os.makedirs(base, exist_ok=True)


def _pseudo_embed(text: str, dim: int = EMBED_DIM) -> List[float]:
    """
    Deterministic, fast pseudo-embedding for local vector search without external calls.
    Based on SHA256 seed -> PRNG in [0,1), centered to [-0.5, 0.5].
    """
    h = hashlib.sha256((text or "").encode("utf-8")).digest()
    seed = int.from_bytes(h[:8], "big")
    rng = (seed * 6364136223846793005 + 1) % (1 << 64)
    vec: List[float] = []
    for _ in range(dim):
        rng = (rng * 2862933555777941757 + 3037000493) % (1 << 64)
        # map to [0,1)
        val = (rng / float(1 << 64))
        vec.append(val - 0.5)
    return vec


def _serialize_vec(vec: List[float]) -> bytes:
    # sqlite-vec expects float32 packed bytes; do local packing
    import struct

    return struct.pack(f"<{len(vec)}f", *vec)


def init_db() -> None:
    """
    Initialize SQLite DB and attempt to load sqlite-vec (vec0) extension.
    Creates base tables and virtual table for embeddings.
    """
    _ensure_dir()
    con = sqlite3.connect(DB_PATH)
    try:
        con.enable_load_extension(True)
        try:
            import sqlite_vec  # type: ignore

            sqlite_vec.load(con)
            log.info("sqlite-vec extension loaded successfully")
        except Exception as e:
            log.warning("sqlite-vec not available; vector search will be disabled: %s", e)
        # Base table
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              provider TEXT,
              model TEXT,
              lang TEXT,
              rounds INTEGER,
              input_tokens INTEGER,
              output_tokens INTEGER,
              total_tokens INTEGER,
              chapter_text TEXT,
              final_text TEXT,
              final_json TEXT
            )
            """
        )
        # Virtual table for embeddings (vec0); only works if extension loaded
        try:
            con.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS eval_embeddings USING vec0(embedding float[{EMBED_DIM}])"
            )
            log.info("Created eval_embeddings virtual table with dim=%d", EMBED_DIM)
        except Exception as e:
            log.warning("Could not create eval_embeddings vec0 table: %s", e)
    finally:
        con.close()


def save_evaluation(
    provider: Optional[str],
    model: Optional[str],
    lang: Optional[str],
    rounds: int,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    chapter_text: str,
    final_text: Optional[str],
    final_json: Optional[Dict[str, Any]],
) -> int:
    _ensure_dir()
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO evaluations(provider, model, lang, rounds, input_tokens, output_tokens, total_tokens, chapter_text, final_text, final_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider,
                model,
                lang,
                rounds,
                input_tokens,
                output_tokens,
                total_tokens,
                chapter_text,
                final_text,
                json.dumps(final_json) if final_json is not None else None,
            ),
        )
        eval_id = cur.lastrowid
        # Try to insert embedding row with rowid=eval_id
        try:
            vec = _pseudo_embed(chapter_text, EMBED_DIM)
            blob = _serialize_vec(vec)
            cur.execute("INSERT INTO eval_embeddings(rowid, embedding) VALUES (?, ?)", (eval_id, blob))
        except Exception as e:
            log.warning("Skipping embedding insert (vec0 unavailable?): %s", e)
        con.commit()
        return eval_id
    finally:
        con.close()


def get_evaluation(eval_id: int) -> Optional[Dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        row = cur.execute(
            "SELECT id, created_at, provider, model, lang, rounds, input_tokens, output_tokens, total_tokens, chapter_text, final_text, final_json FROM evaluations WHERE id = ?",
            (eval_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "created_at": row[1],
            "provider": row[2],
            "model": row[3],
            "lang": row[4],
            "rounds": row[5],
            "input_tokens": row[6],
            "output_tokens": row[7],
            "total_tokens": row[8],
            "chapter_text": row[9],
            "final_text": row[10],
            "final_json": json.loads(row[11]) if row[11] else None,
        }
    finally:
        con.close()


def search_evaluations(query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Vector search via vec0 if available; fallback to LIKE search otherwise."""
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        results: List[Dict[str, Any]] = []
        try:
            vec = _pseudo_embed(query_text, EMBED_DIM)
            blob = _serialize_vec(vec)
            rows = cur.execute(
                "SELECT rowid, distance(embedding, ?) AS dist FROM eval_embeddings ORDER BY dist LIMIT ?",
                (blob, top_k),
            ).fetchall()
            ids = [r[0] for r in rows]
            if ids:
                placeholders = ",".join(["?"] * len(ids))
                eval_rows = cur.execute(
                    f"SELECT id, created_at, provider, model, lang, rounds, final_text, final_json FROM evaluations WHERE id IN ({placeholders})",
                    ids,
                ).fetchall()
                # Preserve order by distance
                order_map = {rid: i for i, rid in enumerate(ids)}
                for erow in sorted(eval_rows, key=lambda x: order_map.get(x[0], 9999)):
                    results.append({
                        "id": erow[0],
                        "created_at": erow[1],
                        "provider": erow[2],
                        "model": erow[3],
                        "lang": erow[4],
                        "rounds": erow[5],
                        "final_text": erow[6],
                        "final_json": json.loads(erow[7]) if erow[7] else None,
                    })
                return results
        except Exception as e:
            log.warning("Vector search unavailable; falling back to LIKE: %s", e)
        # Fallback LIKE search
        rows = cur.execute(
            "SELECT id, created_at, provider, model, lang, rounds, final_text, final_json FROM evaluations WHERE chapter_text LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query_text}%", top_k),
        ).fetchall()
        for r in rows:
            results.append({
                "id": r[0],
                "created_at": r[1],
                "provider": r[2],
                "model": r[3],
                "lang": r[4],
                "rounds": r[5],
                "final_text": r[6],
                "final_json": json.loads(r[7]) if r[7] else None,
            })
        return results
    finally:
        con.close()