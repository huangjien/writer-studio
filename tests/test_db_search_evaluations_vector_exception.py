import sqlite3
import writer_studio.persistence.db as db


def test_search_evaluations_logs_vector_exception_and_falls_back(tmp_path, monkeypatch):
    db_file = tmp_path / "db_eval_vec_fail.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    db.init_db()

    # Seed an evaluation so LIKE fallback can find it
    eid = db.save_evaluation(
        provider="local",
        model="m",
        lang="en",
        rounds=1,
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        chapter_text="vector fallback case",
        final_text="ok",
        final_json=None,
    )
    assert isinstance(eid, int)

    # Force an exception inside the vector try-block
    def boom(_: bytes) -> bytes:  # wrong signature on purpose
        raise RuntimeError("boom")

    monkeypatch.setattr(db, "_serialize_vec", boom)

    res = db.search_evaluations("fallback", top_k=3)
    assert any(r["id"] == eid for r in res)