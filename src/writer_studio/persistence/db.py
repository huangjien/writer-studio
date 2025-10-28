import hashlib
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from writer_studio.logging import get_logger

log = get_logger("novel_eval.db")

DB_PATH = os.getenv("NOVEL_EVAL_DB_PATH", "/data/evals.db")
EMBED_DIM = int(os.getenv("NOVEL_EVAL_EMBED_DIM", "384"))


def _ensure_dir() -> None:
    """
    Ensure the directory for the SQLite DB exists. If the configured
    directory is not writable (e.g., /data on local dev), fall back
    to a project-local ./data directory and update DB_PATH accordingly.
    """
    global DB_PATH
    base = os.path.dirname(DB_PATH)
    if base and not os.path.exists(base):
        try:
            os.makedirs(base, exist_ok=True)
        except OSError as e:
            # Fall back to a local writable directory
            log.warning(
                "DB base dir %s not writable; falling back to ./data (err=%s)",
                base,
                e,
            )
            fallback_dir = os.path.abspath("./data")
            os.makedirs(fallback_dir, exist_ok=True)
            # Preserve DB filename when falling back
            filename = os.path.basename(DB_PATH) or "evals.db"
            DB_PATH = os.path.join(fallback_dir, filename)


def _pseudo_embed(text: str, dim: int = EMBED_DIM) -> List[float]:
    """
    Deterministic, fast pseudo-embedding for local vector search
    without external calls. Based on SHA256 seed -> PRNG in [0,1),
    centered to [-0.5, 0.5].
    """
    h = hashlib.sha256((text or "").encode("utf-8")).digest()
    seed = int.from_bytes(h[:8], "big")
    rng = (seed * 6364136223846793005 + 1) % (1 << 64)
    vec: List[float] = []
    for _ in range(dim):
        rng = (rng * 2862933555777941757 + 3037000493) % (1 << 64)
        # map to [0,1)
        val = rng / float(1 << 64)
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
            log.warning(
                "sqlite-vec not available; vector search will be disabled: %s",
                e,
            )
        # Base table: novel chapter evaluations
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
        # Character profiles table
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS character_profiles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              lang TEXT,
              name TEXT,
              profile_json TEXT,
              UNIQUE(lang, name)
            )
            """
        )
        # Character templates table (for historical/fictional references)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS character_templates (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              lang TEXT,
              name TEXT,
              source TEXT,
              template_json TEXT,
              UNIQUE(lang, name)
            )
            """
        )
        # Virtual table for embeddings (vec0); only works if extension loaded
        try:
            con.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS eval_embeddings "
                f"USING vec0(embedding float[{EMBED_DIM}])"
            )
            log.info("Created eval_embeddings virtual table with dim=%d", EMBED_DIM)
        except Exception as e:
            log.warning("Could not create eval_embeddings vec0 table: %s", e)
    finally:
        con.close()


def save_character_profile(lang: str, name: str, profile_json: Dict[str, Any]) -> int:
    """Insert or update a character profile. Returns the row id.

    If a profile with the same (lang, name) exists, it is updated in place via
    an UPSERT. The `updated_at` timestamp is refreshed.
    """
    _ensure_dir()
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO character_profiles(lang, name, profile_json)
            VALUES (?, ?, ?)
            ON CONFLICT(lang, name) DO UPDATE SET
              profile_json=excluded.profile_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (lang, name, json.dumps(profile_json, ensure_ascii=False)),
        )
        # Retrieve the id (rowid) for the upserted/inserted row
        row = cur.execute(
            "SELECT id FROM character_profiles WHERE lang = ? AND name = ?",
            (lang, name),
        ).fetchone()
        con.commit()
        return int(row[0]) if row else -1
    finally:
        con.close()


def save_character_template(
    lang: str, name: str, template_json: Dict[str, Any], source: Optional[str] = None
) -> int:
    """Insert or update a character template. Returns the row id.

    Templates represent real historical or fictional persons to be adapted.
    """
    _ensure_dir()
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO character_templates(lang, name, source, template_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(lang, name) DO UPDATE SET
              source=excluded.source,
              template_json=excluded.template_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (lang, name, source, json.dumps(template_json, ensure_ascii=False)),
        )
        row = cur.execute(
            "SELECT id FROM character_templates WHERE lang = ? AND name = ?",
            (lang, name),
        ).fetchone()
        con.commit()
        return int(row[0]) if row else -1
    finally:
        con.close()


def get_character_template_by_id(template_id: int) -> Optional[Dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        row = cur.execute(
            """
            SELECT id, created_at, updated_at, lang, name, source, template_json
            FROM character_templates
            WHERE id = ?
            """,
            (template_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "created_at": row[1],
            "updated_at": row[2],
            "lang": row[3],
            "name": row[4],
            "source": row[5],
            "template": json.loads(row[6]) if row[6] else None,
        }
    finally:
        con.close()


def list_character_templates(
    lang: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        if lang:
            rows = cur.execute(
                """
                SELECT id, created_at, updated_at, lang, name, source
                FROM character_templates
                WHERE lang = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (lang, limit),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT id, created_at, updated_at, lang, name, source
                FROM character_templates
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "updated_at": r[2],
                "lang": r[3],
                "name": r[4],
                "source": r[5],
            }
            for r in rows
        ]
    finally:
        con.close()


def search_character_templates(
    lang: Optional[str] = None,
    name_like: Optional[str] = None,
    q: Optional[str] = None,
    field: Optional[str] = None,
    value_like: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        where: List[str] = []
        params: List[Any] = []
        if lang:
            where.append("lang = ?")
            params.append(lang)
        if name_like:
            where.append("name LIKE ?")
            params.append(f"%{name_like}%")
        if q:
            where.append("(name LIKE ? OR template_json LIKE ? OR source LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        if field and value_like:
            json_path = f"$.{field}"
            where.append("json_extract(template_json, ?) LIKE ?")
            params.extend([json_path, f"%{value_like}%"])
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = (
            "SELECT id, created_at, updated_at, lang, name, source "
            "FROM character_templates "
            f"{where_clause} "
            "ORDER BY updated_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = cur.execute(sql, tuple(params)).fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "updated_at": r[2],
                "lang": r[3],
                "name": r[4],
                "source": r[5],
            }
            for r in rows
        ]
    finally:
        con.close()


def get_character_profile_by_id(profile_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single character profile by its integer id."""
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        row = cur.execute(
            """
            SELECT id, created_at, updated_at, lang, name, profile_json
            FROM character_profiles
            WHERE id = ?
            """,
            (profile_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "created_at": row[1],
            "updated_at": row[2],
            "lang": row[3],
            "name": row[4],
            "profile": json.loads(row[5]) if row[5] else None,
        }
    finally:
        con.close()


def update_character_profile(
    profile_id: int,
    profile_json: Dict[str, Any],
    name: Optional[str] = None,
    lang: Optional[str] = None,
) -> bool:
    """Update an existing profile by id. Optionally update name/lang.

    Returns True if a row was updated.
    """
    _ensure_dir()
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        # Build dynamic update SET clause
        set_parts = ["profile_json = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: List[Any] = [json.dumps(profile_json, ensure_ascii=False)]
        if name is not None:
            set_parts.append("name = ?")
            params.append(name)
        if lang is not None:
            set_parts.append("lang = ?")
            params.append(lang)
        params.append(profile_id)
        sql = f"UPDATE character_profiles SET {', '.join(set_parts)} WHERE id = ?"
        cur.execute(sql, tuple(params))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def get_character_profile(lang: str, name: str) -> Optional[Dict[str, Any]]:
    """Fetch a single character profile by language and name."""
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        row = cur.execute(
            """
            SELECT id, created_at, updated_at, lang, name, profile_json
            FROM character_profiles
            WHERE lang = ? AND name = ?
            """,
            (lang, name),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "created_at": row[1],
            "updated_at": row[2],
            "lang": row[3],
            "name": row[4],
            "profile": json.loads(row[5]) if row[5] else None,
        }
    finally:
        con.close()


def list_character_profiles(
    lang: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """List recent character profiles, optionally filtered by language."""
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        if lang:
            rows = cur.execute(
                """
                SELECT id, created_at, updated_at, lang, name
                FROM character_profiles
                WHERE lang = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (lang, limit),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT id, created_at, updated_at, lang, name
                FROM character_profiles
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "updated_at": r[2],
                "lang": r[3],
                "name": r[4],
            }
            for r in rows
        ]
    finally:
        con.close()


def search_character_profiles(
    lang: Optional[str] = None,
    name_like: Optional[str] = None,
    q: Optional[str] = None,
    field: Optional[str] = None,
    value_like: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Search profiles by partial name, language, or JSON field/value.

    - If `q` is provided, searches in `name` and raw `profile_json` text.
    - If `field` and `value_like` are provided, matches using JSON1 `json_extract`.
    """
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        where: List[str] = []
        params: List[Any] = []
        if lang:
            where.append("lang = ?")
            params.append(lang)
        if name_like:
            where.append("name LIKE ?")
            params.append(f"%{name_like}%")
        if q:
            where.append("(name LIKE ? OR profile_json LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])
        if field and value_like:
            json_path = f"$.{field}"
            where.append("json_extract(profile_json, ?) LIKE ?")
            params.extend([json_path, f"%{value_like}%"])
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = (
            "SELECT id, created_at, updated_at, lang, name "
            "FROM character_profiles "
            f"{where_clause} "
            "ORDER BY updated_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = cur.execute(sql, tuple(params)).fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "updated_at": r[2],
                "lang": r[3],
                "name": r[4],
            }
            for r in rows
        ]
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
            INSERT INTO evaluations(provider, model, lang, rounds,
            input_tokens, output_tokens, total_tokens, chapter_text,
            final_text, final_json)
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
            cur.execute(
                "INSERT INTO eval_embeddings(rowid, embedding) VALUES (?, ?)",
                (eval_id, blob),
            )
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
            "SELECT id, created_at, provider, model, lang, rounds, "
            "input_tokens, output_tokens, total_tokens, chapter_text, "
            "final_text, final_json FROM evaluations WHERE id = ?",
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
                "SELECT rowid, distance(embedding, ?) AS dist "
                "FROM eval_embeddings ORDER BY dist LIMIT ?",
                (blob, top_k),
            ).fetchall()
            ids = [r[0] for r in rows]
            if ids:
                placeholders = ",".join(["?"] * len(ids))
                eval_rows = cur.execute(
                    f"SELECT id, created_at, provider, model, lang, "
                    f"rounds, final_text, final_json FROM evaluations "
                    f"WHERE id IN ({placeholders})",
                    ids,
                ).fetchall()
                # Preserve order by distance
                order_map = {rid: i for i, rid in enumerate(ids)}
                for erow in sorted(eval_rows, key=lambda x: order_map.get(x[0], 9999)):
                    results.append(
                        {
                            "id": erow[0],
                            "created_at": erow[1],
                            "provider": erow[2],
                            "model": erow[3],
                            "lang": erow[4],
                            "rounds": erow[5],
                            "final_text": erow[6],
                            "final_json": (json.loads(erow[7]) if erow[7] else None),
                        }
                    )
                return results
        except Exception as e:
            log.warning("Vector search unavailable; falling back to LIKE: %s", e)
        # Fallback LIKE search
        rows = cur.execute(
            "SELECT id, created_at, provider, model, lang, rounds, "
            "final_text, final_json FROM evaluations WHERE "
            "chapter_text LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query_text}%", top_k),
        ).fetchall()
        for r in rows:
            results.append(
                {
                    "id": r[0],
                    "created_at": r[1],
                    "provider": r[2],
                    "model": r[3],
                    "lang": r[4],
                    "rounds": r[5],
                    "final_text": r[6],
                    "final_json": json.loads(r[7]) if r[7] else None,
                }
            )
        return results
    finally:
        con.close()
