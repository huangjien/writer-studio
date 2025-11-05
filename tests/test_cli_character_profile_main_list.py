import sys

import writer_studio.persistence.db as db
from writer_studio.cli import character_profile as cli


def test_cli_list_prints_items(tmp_path, monkeypatch, capsys):
    db_file = tmp_path / "cli_list.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    db.init_db()
    # Seed profiles
    p1 = db.save_character_profile("en", "Alice", {"name": "Alice"})
    p2 = db.save_character_profile("en", "Bob", {"name": "Bob"})
    assert p1 and p2

    sys.argv = ["prog", "list", "--language", "en"]
    cli.main()
    out = capsys.readouterr().out
    assert "Alice" in out and "Bob" in out