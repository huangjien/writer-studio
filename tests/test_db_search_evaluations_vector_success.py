import sqlite3
import writer_studio.persistence.db as db


def test_search_evaluations_vector_success_with_user_distance(tmp_path, monkeypatch):
    db_file = tmp_path / "db_eval_vec_ok.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))

    # Patch sqlite3.connect to auto-register a mock distance() function
    orig_connect = sqlite3.connect

    def connect_with_distance(path):
        con = orig_connect(path)
        con.create_function("distance", 2, lambda a, b: 0.0)
        return con

    monkeypatch.setattr(sqlite3, "connect", connect_with_distance)

    db.init_db()

    # Create a plain table to stand in for the vec0 virtual table
    con = sqlite3.connect(db.DB_PATH)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS eval_embeddings (rowid INTEGER PRIMARY KEY, embedding BLOB)")
        con.commit()
    finally:
        con.close()

    # Save an evaluation; embedding insert should now succeed
    eid = db.save_evaluation(
        provider="local",
        model="m",
        lang="en",
        rounds=1,
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        chapter_text="vector success case",
        final_text="ok",
        final_json=None,
    )
    assert isinstance(eid, int)

    res = db.search_evaluations("vector", top_k=5)
    # Ensure the vector-path returns ordered results including our id
    assert any(r["id"] == eid for r in res)