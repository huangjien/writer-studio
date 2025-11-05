import builtins
from pathlib import Path

from writer_studio.cli import character_profile as cli


def test_ask_list_keep_default(monkeypatch, capsys):
    inputs = iter([""])
    monkeypatch.setattr(builtins, "input", lambda _: next(inputs))
    res = cli._ask_list("traits", default=["a", "b"])
    assert res == ["a", "b"]
    out = capsys.readouterr().out
    assert "Current: a, b" in out


def test_ask_list_min_items_enforced(monkeypatch, capsys):
    inputs = iter(["", "A", "", "B", ""])  # require at least 2
    monkeypatch.setattr(builtins, "input", lambda _: next(inputs))
    res = cli._ask_list("skills", min_items=2)
    assert res == ["A", "B"]
    out = capsys.readouterr().out
    assert "Please add at least 2 item(s)." in out


def test_walk_and_fill_with_defaults(monkeypatch):
    # Return blank to accept defaults; ensure list min_items satisfied by defaults
    monkeypatch.setattr(builtins, "input", lambda _: "")
    tmpl = {"name": "", "traits": [""], "bio": {"age": ""}}
    defaults = {"name": "Alice", "traits": ["curious"], "bio": {"age": "20"}}
    res = cli._walk_and_fill(tmpl, defaults)
    assert res["name"] == "Alice"
    assert res["traits"] == ["curious"]
    assert res["bio"]["age"] == "20"


def test_fill_sections_edit_selective(monkeypatch):
    inputs = iter([""] * 5)
    monkeypatch.setattr(builtins, "input", lambda _: next(inputs))
    tmpl = {"relationships": [""], "backstory": {"note": ""}, "name": ""}
    defaults = {"relationships": ["friend"], "backstory": {"note": "old"}, "name": "Bob"}
    res = cli._fill_sections(tmpl, defaults, sections_to_edit=["relationships"])
    assert res["relationships"] == ["friend"]
    # backstory kept from defaults
    assert res["backstory"]["note"] == "old"
    # name kept from defaults
    assert res["name"] == "Bob"