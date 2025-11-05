import sys

import pytest

from writer_studio.cli import character_profile as cp_cli
from writer_studio.persistence.db import (
    init_db,
    save_character_profile,
    save_character_template,
)


def _set_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "evals.db"
    monkeypatch.setenv("NOVEL_EVAL_DB_PATH", str(db_file))
    init_db()
    return db_file


def test_cli_list_and_show_profiles(tmp_path, monkeypatch, capsys):
    _set_db_path(tmp_path, monkeypatch)

    # Seed one profile
    save_character_profile("en", "John Doe", {"backstory": "Test", "relationships": {}})

    # Run: list
    monkeypatch.setattr(sys, "argv", ["character-profile", "list", "--language", "en"])
    cp_cli.main()
    out = capsys.readouterr().out
    assert "John Doe" in out

    # Run: show by name
    monkeypatch.setattr(
        sys,
        "argv",
        ["character-profile", "show", "--language", "en", "--name", "John Doe"],
    )
    cp_cli.main()
    out = capsys.readouterr().out
    assert "John Doe" in out


def test_cli_search_profiles(tmp_path, monkeypatch, capsys):
    _set_db_path(tmp_path, monkeypatch)

    save_character_profile(
        "en", "Jane Detective", {"backstory": "Detective", "relationships": {}}
    )
    # Text search
    monkeypatch.setattr(
        sys,
        "argv",
        ["character-profile", "search", "--language", "en", "--q", "Detective"],
    )
    cp_cli.main()
    out = capsys.readouterr().out
    assert "Jane Detective" in out


def test_cli_template_list_and_show(tmp_path, monkeypatch, capsys):
    _set_db_path(tmp_path, monkeypatch)

    # Seed one template
    tpl_id = save_character_template(
        "en",
        "Sherlock Holmes",
        {"backstory": "Consulting detective", "relationships": {"allies": ["Watson"]}},
        source="Fiction",
    )
    assert tpl_id > 0

    # tlist
    monkeypatch.setattr(sys, "argv", ["character-profile", "tlist", "--language", "en"])
    cp_cli.main()
    out = capsys.readouterr().out
    assert "Sherlock Holmes" in out

    # tshow
    monkeypatch.setattr(
        sys, "argv", ["character-profile", "tshow", "--id", str(tpl_id)]
    )
    cp_cli.main()
    out = capsys.readouterr().out
    assert "Sherlock Holmes" in out

    # Skip interactive "use_template" in this non-interactive test


def test_cli_use_template_noninteractive(monkeypatch, capsys):
    # Avoid DB/file IO by stubbing dependencies
    from writer_studio.cli import character_profile as cp

    # Provide a fake template row
    monkeypatch.setattr(
        cp,
        "get_character_template_by_id",
        lambda _id: {
            "id": 1,
            "lang": "zh-CN",
            "name": "TemplateName",
            "template": {
                "role": "Mage",
                "backstory": "Old tale",
                "relationships": ["R1"],
            },
        },
    )
    # Minimal template structure for language
    monkeypatch.setattr(
        cp,
        "_load_template",
        lambda lang: {
            "character_profile": {
                "name": "",
                "role": "",
                "backstory": "",
                "relationships": [],
            }
        },
    )
    # Make scalar prompts return defaults deterministically
    monkeypatch.setattr(cp, "_ask_scalar", lambda prompt, default=None: default or "X")
    # Avoid stdin reads for list prompts
    monkeypatch.setattr(
        cp,
        "_ask_list",
        lambda prompt, min_items=0, default=None: list(default or []),
    )

    saved = {}

    def fake_save(lang, name, profile):
        saved["lang"] = lang
        saved["name"] = name
        saved["profile"] = profile
        return 99

    monkeypatch.setattr(cp, "save_character_profile", fake_save)
    # Ensure init_db is a no-op
    monkeypatch.setattr(cp, "init_db", lambda: None)

    # Invoke CLI
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "character-profile",
            "use_template",
            "--id",
            "1",
            "--name",
            "NewGuy",
            "--language",
            "en",
        ],
    )
    cp.main()
    out = capsys.readouterr().out
    assert "Create Character From Template" in out
    expected = "Saved to SQLite: id=99 lang=en name=NewGuy"
    assert expected in out
    # Validate that defaults were applied and name set
    assert saved["name"] == "NewGuy"
    assert saved["lang"] == "en"
    # Role preserved from template defaults
    # backstory/relationships editable section updated
    assert saved["profile"]["role"] == "Mage"


def test_cli_collect_persist_empty_name_warning(monkeypatch, capsys):
    from writer_studio.cli import character_profile as cp

    # Stub template and collection to avoid stdin
    monkeypatch.setattr(cp, "_load_template", lambda lang: {"character_profile": {}})
    monkeypatch.setattr(
        cp,
        "_walk_and_fill",
        lambda root, defaults=None: {
            "name": "",
            "role": "R",
            "backstory": "B",
            "relationships": [],
        },
    )

    calls = {}
    monkeypatch.setattr(
        cp,
        "save_character_profile",
        lambda lang, name, profile: calls.setdefault("args", (lang, name, profile))
        or 123,
    )
    monkeypatch.setattr(cp, "init_db", lambda: None)

    monkeypatch.setattr(
        sys, "argv", ["character-profile", "collect", "--language", "en"]
    )
    cp.main()
    out = capsys.readouterr().out
    assert "Warning: name is empty" in out
    assert "Saved to SQLite" in out
    lang, name, profile = calls["args"]
    assert lang == "en"
    assert name == "(unnamed)"
    assert profile["role"] == "R"


def test_cli_collect_update_profile(monkeypatch, capsys):
    from writer_studio.cli import character_profile as cp

    # Existing profile returned by id
    monkeypatch.setattr(
        cp,
        "get_character_profile_by_id",
        lambda _id: {
            "id": _id,
            "lang": "en",
            "name": "Existing",
            "profile": {"role": "Old"},
        },
    )
    # New fill keeps same name to exercise None name/lang update
    monkeypatch.setattr(cp, "_load_template", lambda lang: {"character_profile": {}})
    monkeypatch.setattr(
        cp,
        "_walk_and_fill",
        lambda root, defaults=None: {"name": "Existing", "role": "New"},
    )

    captured = {}

    def fake_update(row_id, filled, name=None, lang=None):
        captured["row_id"] = row_id
        captured["filled"] = filled
        captured["name"] = name
        captured["lang"] = lang
        return True

    monkeypatch.setattr(cp, "update_character_profile", fake_update)
    monkeypatch.setattr(cp, "init_db", lambda: None)

    monkeypatch.setattr(
        sys,
        "argv",
        ["character-profile", "collect", "--update", "--id", "1", "--language", "en"],
    )
    cp.main()
    out = capsys.readouterr().out
    assert "Updated SQLite: id=1" in out
    assert captured["row_id"] == 1
    assert captured["filled"]["role"] == "New"
    # Unchanged name/lang should pass None
    assert captured["name"] is None
    assert captured["lang"] is None


def test_cli_tcollect_persist_and_outputs(tmp_path, monkeypatch, capsys):
    from writer_studio.cli import character_profile as cp

    monkeypatch.setattr(cp, "_load_template", lambda lang: {"character_profile": {}})
    monkeypatch.setattr(
        cp, "_walk_and_fill", lambda root, defaults=None: {"name": "Templ", "role": "R"}
    )

    saved = {}
    monkeypatch.setattr(
        cp,
        "save_character_template",
        lambda lang, name, tpl, source=None: saved.update(
            {"lang": lang, "name": name, "tpl": tpl, "source": source}
        )
        or 77,
    )
    monkeypatch.setattr(cp, "init_db", lambda: None)

    json_path = tmp_path / "t.json"
    yaml_path = tmp_path / "t.yaml"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "character-profile",
            "tcollect",
            "--language",
            "en",
            "--json-out",
            str(json_path),
            "--yaml-out",
            str(yaml_path),
            "--source",
            "Book",
        ],
    )
    cp.main()
    out = capsys.readouterr().out
    assert "Completed Template (JSON)" in out
    assert json_path.read_text(encoding="utf-8").strip().startswith("{")
    assert "character_profile" in json_path.read_text(encoding="utf-8")
    assert (
        yaml_path.read_text(encoding="utf-8").strip().startswith("character_profile:")
    )
    assert saved["name"] == "Templ"
    assert saved["lang"] == "en"
    assert saved["source"] == "Book"


def test_cli_use_template_outputs_and_env_fallback(tmp_path, monkeypatch, capsys):
    from writer_studio.cli import character_profile as cp

    # Template has no lang -> env fallback
    monkeypatch.setenv("CHAR_LANG", "fr")
    monkeypatch.setattr(
        cp,
        "get_character_template_by_id",
        lambda _id: {
            "id": 1,
            "lang": None,
            "name": "T",
            "template": {"role": "Knight", "backstory": "Legend", "relationships": []},
        },
    )
    monkeypatch.setattr(
        cp,
        "_load_template",
        lambda lang: {
            "character_profile": {
                "name": "",
                "role": "",
                "backstory": "",
                "relationships": [],
            }
        },
    )
    monkeypatch.setattr(cp, "_ask_scalar", lambda prompt, default=None: default or "X")
    monkeypatch.setattr(
        cp, "_ask_list", lambda prompt, min_items=0, default=None: list(default or [])
    )

    saved = {}
    monkeypatch.setattr(
        cp,
        "save_character_profile",
        lambda lang, name, profile: saved.update(
            {"lang": lang, "name": name, "profile": profile}
        )
        or 88,
    )
    monkeypatch.setattr(cp, "init_db", lambda: None)

    j = tmp_path / "c.json"
    y = tmp_path / "c.yaml"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "character-profile",
            "use_template",
            "--id",
            "1",
            "--name",
            "Hero",
            "--json-out",
            str(j),
            "--yaml-out",
            str(y),
        ],
    )
    cp.main()
    out = capsys.readouterr().out
    assert "Wrote JSON" in out
    assert "Wrote YAML" in out
    assert saved["lang"] == "fr"
    assert saved["name"] == "Hero"
    assert "character_profile" in j.read_text(encoding="utf-8")
    assert "character_profile" in y.read_text(encoding="utf-8")


def test_cli_errors(monkeypatch):
    from writer_studio.cli import character_profile as cp

    # Missing template id
    monkeypatch.setattr(cp, "get_character_template_by_id", lambda _id: None)
    monkeypatch.setattr(
        sys, "argv", ["character-profile", "use_template", "--id", "999"]
    )
    with pytest.raises(SystemExit) as ei:
        cp.main()
    assert "Template id not found" in str(ei.value)

    # Missing character_profile root in template
    monkeypatch.setattr(cp, "_load_template", lambda lang: {})
    monkeypatch.setattr(
        sys, "argv", ["character-profile", "collect", "--language", "en"]
    )
    with pytest.raises(SystemExit) as ei2:
        cp.main()
    assert "Template missing 'character_profile' root" in str(ei2.value)


# EOF