import errno
import os
from pathlib import Path

from writer_studio.persistence import db as pdb


def test_db_path_fallback_and_crud(tmp_path, monkeypatch):
    # Simulate read-only base dir by raising EROFS on makedirs
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", "/data/evals.db")

    def ro_makedirs(path, exist_ok=False):
        raise OSError(errno.EROFS, "Read-only file system")

    monkeypatch.setattr(os, "makedirs", ro_makedirs)

    # init should warn and fall back to ./data
    pdb.init_db()

    # Perform writes to ensure DB gets created in ./data
    pdb.save_character_profile(
        "en", "Fallback Tester", {"backstory": "B", "relationships": {}}
    )
    tpl_id = pdb.save_character_template(
        "en", "Tpl", {"backstory": "TB", "relationships": {}}, source="Test"
    )
    assert tpl_id > 0

    # Validate file exists in ./data
    assert (Path("data") / "evals.db").exists()

    # Basic reads
    prof = pdb.get_character_profile("en", "Fallback Tester")
    assert prof is not None
    listed = pdb.list_character_profiles("en", limit=10)
    assert any(p["name"] == "Fallback Tester" for p in listed)

    # Searches
    search = pdb.search_character_profiles("en", q="Fallback", limit=10)
    assert any("Fallback" in p["name"] for p in search)
    tpls = pdb.list_character_templates("en")
    assert any(t["name"] == "Tpl" for t in tpls)
    ts = pdb.search_character_templates("en", q="Tpl")
    assert any(t["name"] == "Tpl" for t in ts)
