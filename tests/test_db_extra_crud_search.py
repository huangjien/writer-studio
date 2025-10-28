import os
import uuid
from pathlib import Path

import writer_studio.persistence.db as db


def test_db_readonly_fallback_and_crud_json_search(tmp_path, monkeypatch):
    # Force a non-writable base to trigger fallback to ./data
    # Use a unique filename to avoid collisions with other tests

    unique = uuid.uuid4().hex
    forced = f"/root/nonwritable/{unique}.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", forced)
    monkeypatch.setattr(db, "DB_PATH", forced)

    # Initialize; expect fallback and db file under ./data
    db.init_db()
    # After fallback, DB_PATH should point to project-local ./data/forced.db
    # Ensure fallback took effect and DB_PATH points to the forced basename
    assert os.path.basename(db.DB_PATH) == os.path.basename(forced)
    assert Path(db.DB_PATH).parent.name == "data"

    # Seed profiles
    suffix = unique
    pid1 = db.save_character_profile(
        "en",
        f"John_{suffix}",
        {
            "name": "John",
            "role": "Mage",
            "backstory": "Arcane",
            "relationships": {"allies": ["A", "B"]},
        },
    )
    pid2 = db.save_character_profile(
        "en",
        f"Alice_{suffix}",
        {
            "name": "Alice",
            "role": "Detective",
            "backstory": "Investigate",
            "relationships": {"allies": ["Watson"]},
        },
    )
    assert pid1 > 0 and pid2 > 0

    # Getters
    p1 = db.get_character_profile_by_id(pid1)
    assert p1 and p1["name"] == f"John_{suffix}"
    assert p1["profile"]["name"] == "John"
    p2 = db.get_character_profile("en", f"Alice_{suffix}")
    assert p2 and p2["name"] == f"Alice_{suffix}"
    assert p2["profile"]["name"] == "Alice"

    # JSON field search (nested list)
    res = db.search_character_profiles(
        lang="en", field="relationships.allies", value_like="Watson"
    )
    assert any(r["name"] == f"Alice_{suffix}" for r in res)

    # Update profile with name/lang changes
    ok = db.update_character_profile(
        pid1, {"name": "John", "role": "Wizard"}, name=f"JohnX_{suffix}", lang="fr"
    )
    assert ok is True
    p1u = db.get_character_profile_by_id(pid1)
    assert p1u["name"] == f"JohnX_{suffix}"
    assert p1u["lang"] == "fr"
    assert p1u["profile"]["role"] == "Wizard"

    # Templates: seed and search
    tid = db.save_character_template(
        "en",
        f"Sherlock_{suffix}",
        {
            "role": "Consulting detective",
            "backstory": "Consulting",
            "relationships": {"allies": ["Watson"]},
        },
        source="Fiction",
    )
    assert tid > 0
    t = db.get_character_template_by_id(tid)
    assert t and t["name"] == f"Sherlock_{suffix}"

    # JSON field search in templates
    tres = db.search_character_templates(
        lang="en", field="relationships.allies", value_like="Watson"
    )
    assert any(r["name"] == f"Sherlock_{suffix}" for r in tres)


# EOF
