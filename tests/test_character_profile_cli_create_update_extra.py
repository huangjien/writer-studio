import sys

import pytest


def test_cli_collect_create_noninteractive(tmp_path, monkeypatch, capsys):
    from writer_studio.cli import character_profile as cp

    # Bypass interactive prompts
    monkeypatch.setattr(
        cp,
        "_load_template",
        lambda lang: {"character_profile": {"name": "", "role": "", "backstory": ""}},
    )
    monkeypatch.setattr(
        cp,
        "_walk_and_fill",
        lambda root, defaults=None: {
            "name": "Hero",
            "role": "Knight",
            "backstory": "Legend",
        },
    )
    saved = {}
    monkeypatch.setattr(
        cp,
        "save_character_profile",
        lambda lang, name, profile: saved.update(
            {"lang": lang, "name": name, "profile": profile}
        )
        or 99,
    )
    monkeypatch.setattr(cp, "init_db", lambda: None)

    j = tmp_path / "hero.json"
    y = tmp_path / "hero.yaml"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "character-profile",
            "collect",
            "--language",
            "en",
            "--json-out",
            str(j),
            "--yaml-out",
            str(y),
        ],
    )
    cp.main()
    out = capsys.readouterr().out
    assert "Completed Character Profile (JSON)" in out
    assert "Saved to SQLite" in out
    assert saved["lang"] == "en"
    assert saved["name"] == "Hero"
    assert saved["profile"]["role"] == "Knight"
    assert "character_profile" in j.read_text(encoding="utf-8")
    assert "character_profile" in y.read_text(encoding="utf-8")


def test_cli_collect_update_missing_id_error(monkeypatch):
    from writer_studio.cli import character_profile as cp

    monkeypatch.setattr(cp, "init_db", lambda: None)
    # Trigger missing id with --update
    monkeypatch.setattr(sys, "argv", ["character-profile", "collect", "--update"])
    with pytest.raises(SystemExit) as ei:
        cp.main()
    assert "requires --id" in str(ei.value)


# EOF
