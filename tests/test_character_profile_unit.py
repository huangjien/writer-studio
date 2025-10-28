from pathlib import Path

from writer_studio.cli import character_profile as cp_cli


def test_load_template_fallback_to_en(monkeypatch):
    # Use repo tasks path; ask for a non-existent lang to trigger fallback

    tasks_dir = Path(__file__).resolve().parents[1] / "tasks" / "character_profile"
    monkeypatch.setenv("CHAR_TASKS_DIR", str(tasks_dir))
    tmpl = cp_cli._load_template("xx")
    assert isinstance(tmpl, dict)
    # Expect known top-level keys from en.yaml template structure
    assert "character_profile" in tmpl or len(tmpl) > 0


def test_ask_scalar_with_default(monkeypatch):
    # empty input returns the default
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: "")
    val = cp_cli._ask_scalar("prompt", default="DEF")
    assert val == "DEF"

    # non-empty input overrides default
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: "NEW")
    val = cp_cli._ask_scalar("prompt", default="DEF")
    assert val == "NEW"


def test_ask_scalar_no_default(monkeypatch):
    # First empty, then non-empty
    seq = iter(["", "VALUE"])

    def _inp(*_a, **_k):
        return next(seq)

    monkeypatch.setattr("builtins.input", _inp)
    val = cp_cli._ask_scalar("prompt")
    assert val == "VALUE"


def test_ask_list_with_default(monkeypatch, capsys):
    # Blank input with default present returns default immediately
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "")
    res = cp_cli._ask_list("items", min_items=0, default=["a", "b"])
    assert res == ["a", "b"]


def test_walk_and_fill_nested_defaults(monkeypatch):
    # Template with nested dict and empty list; defaults provided
    obj = {"backstory": {"origin": ""}, "traits": []}
    defaults = {"backstory": {"origin": "old"}, "traits": ["cool"]}

    # Always return empty so scalar keeps default; list with min_items=0 keeps default
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "")
    out = cp_cli._walk_and_fill(obj, defaults)
    assert out["backstory"]["origin"] == "old"
    assert out["traits"] == ["cool"]


def test_fill_sections_edit_only_specified(monkeypatch):
    template_root = {
        "backstory": "",
        "relationships": {"allies": []},
        "traits": [""],
    }
    defaults = {
        "backstory": "old-story",
        "relationships": {"allies": ["Alice"]},
        "traits": ["brave"],
    }
    sections = ["backstory", "relationships"]

    # Patch helpers
    monkeypatch.setattr(cp_cli, "_walk_and_fill", lambda obj, d: {"x": 1})
    monkeypatch.setattr(cp_cli, "_ask_scalar", lambda p, default=None: "NEW-STORY")
    # _ask_list should not be called for non-edited 'traits'
    out = cp_cli._fill_sections(template_root, defaults, sections)
    assert out["backstory"] == "NEW-STORY"
    assert out["relationships"] == {"x": 1}
    # Non-edited key should keep default
    assert out["traits"] == ["brave"]


# EOF
