import writer_studio.persistence.db as db


def test_save_get_and_search_evaluations(tmp_path, monkeypatch):
    db_file = tmp_path / "db_eval.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))

    db.init_db()

    # Save an evaluation (exercise embed insert try/except)
    eid = db.save_evaluation(
        provider="local",
        model="unknown",
        lang="en",
        rounds=1,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        chapter_text="Mystery tale",
        final_text="{\"score\": 8}",
        final_json={"score": 8},
    )
    assert isinstance(eid, int) and eid > 0

    # Get evaluation by id
    data = db.get_evaluation(eid)
    assert data and data["id"] == eid
    assert data["final_json"] == {"score": 8}

    # Search evaluations (vector try -> fallback LIKE)
    res = db.search_evaluations("Mystery", top_k=5)
    assert any(item["id"] == eid for item in res)