import sqlite3
import writer_studio.persistence.db as db


def test_save_evaluation_without_embeddings_table(tmp_path, monkeypatch):
    db_file = tmp_path / "db_eval_no_vec.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))

    # Patch sqlite3.connect to ensure no eval_embeddings table exists
    orig_connect = sqlite3.connect

    def connect_plain(path):
        con = orig_connect(path)
        # Do NOT create eval_embeddings; also ensure distance is absent
        return con

    monkeypatch.setattr(sqlite3, "connect", connect_plain)

    db.init_db()

    # Saving evaluation should hit the try/except and log skip
    eid = db.save_evaluation(
        provider="local",
        model="m",
        lang="en",
        rounds=1,
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        chapter_text="no vec table",
        final_text="ok",
        final_json={"ok": True},
    )
    assert isinstance(eid, int) and eid > 0