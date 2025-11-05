import writer_studio.persistence.db as db


def _set_db(tmp_path, monkeypatch):
    db_file = tmp_path / "db_list_missing.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    return db_file


def test_list_filters_and_get_template_missing(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    db.init_db()

    # Seed profiles across languages
    db.save_character_profile("en", "Alpha", {"name": "Alpha"})
    db.save_character_profile("fr", "Bravo", {"name": "Bravo"})

    # Seed templates across languages
    db.save_character_template("en", "Sherlock", {"role": "Detective"})
    db.save_character_template("fr", "Dupin", {"role": "Detective"})

    # List profiles filtered by language
    en_profiles = db.list_character_profiles(lang="en", limit=10)
    assert any(p["name"] == "Alpha" for p in en_profiles)
    assert all(p["lang"] == "en" for p in en_profiles)

    # List templates filtered by language
    fr_templates = db.list_character_templates(lang="fr", limit=10)
    assert any(t["name"] == "Dupin" for t in fr_templates)
    assert all(t["lang"] == "fr" for t in fr_templates)

    # Missing template id should return None
    assert db.get_character_template_by_id(999999) is None