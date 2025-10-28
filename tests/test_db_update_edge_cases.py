import writer_studio.persistence.db as db


def test_update_profile_returns_false_for_missing_id(tmp_path, monkeypatch):
    db_file = tmp_path / "db_edges.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))

    db.init_db()

    # Seed one profile to ensure DB is usable
    pid = db.save_character_profile("en", "Seed", {"name": "Seed"})
    assert pid > 0

    # Update non-existent id should return False
    ok = db.update_character_profile(999999, {"name": "X"}, name=None, lang=None)
    assert ok is False


def test_search_filters_name_like_and_q(tmp_path, monkeypatch):
    db_file = tmp_path / "db_search.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))

    db.init_db()

    suffix = "Edge"
    db.save_character_profile("en", f"John_{suffix}", {"name": "John", "role": "Mage"})
    db.save_character_profile(
        "en", f"Johnny_{suffix}", {"name": "Johnny", "role": "Knight"}
    )

    # name_like filter
    res1 = db.search_character_profiles(lang="en", name_like=f"John_{suffix}"[:5])
    names1 = {r["name"] for r in res1}
    assert any(n.startswith("John_") for n in names1)

    # q free-text in name
    res2 = db.search_character_profiles(lang="en", q="Knight")
    assert any("Johnny_" in r["name"] for r in res2)


# EOF
