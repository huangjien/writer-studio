import os
import sys
from pathlib import Path

import writer_studio.persistence.db as db
from writer_studio.cli import character_profile as cli


def _setup_db(tmp_path, monkeypatch):
    db_file = tmp_path / "cli_profiles.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    db.init_db()
    return db_file


def test_cli_search_no_matches(tmp_path, monkeypatch, capsys):
    _setup_db(tmp_path, monkeypatch)
    sys.argv = ["prog", "search", "--language", "en", "--q", "zzz", "--limit", "3"]
    cli.main()
    out = capsys.readouterr().out
    assert "No matches." in out


def test_cli_collect_warns_and_persists_unnamed(tmp_path, monkeypatch, capsys):
    _setup_db(tmp_path, monkeypatch)
    # Avoid interactive input by stubbing template and walk
    monkeypatch.setattr(cli, "_load_template", lambda lang: {"character_profile": {"name": ""}})
    monkeypatch.setattr(cli, "_walk_and_fill", lambda root, defaults=None: {"name": ""})
    sys.argv = ["prog", "collect", "--language", "en"]
    cli.main()
    out = capsys.readouterr().out
    assert "Warning: name is empty; saving under '(unnamed)'." in out


def test_cli_use_template_writes_outputs(tmp_path, monkeypatch, capsys):
    _setup_db(tmp_path, monkeypatch)
    # Seed a template directly into DB
    tid = db.save_character_template("en", "T1", {"name": "T1", "backstory": {}, "relationships": []}, source="UnitTest")
    # Stub interactive functions
    monkeypatch.setattr(cli, "_ask_scalar", lambda prompt, default=None: "NewName")
    monkeypatch.setattr(cli, "_fill_sections", lambda tmpl, defaults, sections_to_edit: {"name": "NewName", "backstory": {}, "relationships": []})
    json_path = tmp_path / "out.json"
    yaml_path = tmp_path / "out.yaml"
    sys.argv = ["prog", "use_template", "--id", str(tid), "--language", "en", "--json-out", str(json_path), "--yaml-out", str(yaml_path)]
    cli.main()
    out = capsys.readouterr().out
    assert "Wrote JSON to:" in out and "Wrote YAML to:" in out
    assert json_path.exists()
    assert yaml_path.exists()
    assert "character_profile" in json_path.read_text(encoding="utf-8")