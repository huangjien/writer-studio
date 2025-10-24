import json
import sys

import pytest

import writer_studio.cli.evaluate_chapter as cli


class FakeMsg:
    def __init__(self, source="Agent", content=""):
        self.source = source
        self.content = content


class FakeResult:
    def __init__(self, messages):
        self.messages = messages


def test_cli_missing_file_exits(monkeypatch, capsys, tmp_path):
    missing = tmp_path / "missing.txt"
    argv = ["novel-eval", str(missing), "--provider", "openai", "--model", "gpt-4o-mini"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "File not found" in str(exc.value)


def test_cli_json_output_parses_valid_json(monkeypatch, capsys, tmp_path):
    chapter = tmp_path / "chapter.txt"
    chapter.write_text("Hello world", encoding="utf-8")

    fake_json = {"ok": True, "scores": {"a": 1}}
    messages = [FakeMsg(source="Summarizer", content=json.dumps(fake_json))]
    fake_res = FakeResult(messages)

    # Stub the imported symbol inside CLI module to avoid real execution
    monkeypatch.setattr(cli, "evaluate_chapter", lambda *a, **k: fake_res)

    argv = [
        "novel-eval",
        str(chapter),
        "--provider",
        "openai",
        "--model",
        "gpt-4o-mini",
        "--json",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    cli.main()
    out = capsys.readouterr()
    # Valid JSON printed to stdout
    parsed = json.loads(out.out)
    assert parsed["ok"] is True
    # Token metrics printed to stderr in --json mode
    assert "Token Usage" in out.err


def test_cli_prints_messages_when_not_json(monkeypatch, capsys, tmp_path):
    chapter = tmp_path / "chapter.txt"
    chapter.write_text("Hello again", encoding="utf-8")

    messages = [
        FakeMsg(source="LiteraryCritic", content="Critique text"),
        FakeMsg(source="Summarizer", content="Not JSON here"),
    ]
    fake_res = FakeResult(messages)

    # Stub the imported symbol inside CLI module
    monkeypatch.setattr(cli, "evaluate_chapter", lambda *a, **k: fake_res)

    argv = [
        "novel-eval",
        str(chapter),
        "--provider",
        "openai",
        "--model",
        "gpt-4o-mini",
        # no --json
    ]
    monkeypatch.setattr(sys, "argv", argv)

    cli.main()
    out = capsys.readouterr()
    assert "=== Team Messages ===" in out.out
    assert "[LiteraryCritic]" in out.out
    assert "Critique text" in out.out
    # Token metrics go to stdout in non-json mode
    assert "Token Usage" in out.out


def test_cli_json_invalid_final_text(monkeypatch, capsys, tmp_path):
    chapter = tmp_path / "chapter.txt"
    chapter.write_text("Hello", encoding="utf-8")

    messages = [FakeMsg(source="Summarizer", content="not a json string")]
    fake_res = FakeResult(messages)
    monkeypatch.setattr(cli, "evaluate_chapter", lambda *a, **k: fake_res)

    argv = ["novel-eval", str(chapter), "--provider", "openai", "--model", "gpt-4o-mini", "--json"]
    monkeypatch.setattr(sys, "argv", argv)

    cli.main()
    out = capsys.readouterr()
    assert "not a json string" in out.out
    assert "Token Usage" in out.err


def test_cli_json_no_final_text(monkeypatch, capsys, tmp_path):
    chapter = tmp_path / "chapter.txt"
    chapter.write_text("Hello", encoding="utf-8")

    messages = []
    fake_res = FakeResult(messages)
    monkeypatch.setattr(cli, "evaluate_chapter", lambda *a, **k: fake_res)

    argv = ["novel-eval", str(chapter), "--provider", "openai", "--model", "gpt-4o-mini", "--json"]
    monkeypatch.setattr(sys, "argv", argv)

    cli.main()
    out = capsys.readouterr()
    assert out.out.strip() == "{}"
    assert "Token Usage" in out.err


def test_safe_token_count_with_fake_tiktoken_o200k(monkeypatch):
    class FakeEnc:
        def encode(self, text):
            return list(text)

    class FakeTikToken:
        def encoding_for_model(self, model):
            raise RuntimeError("force fallback")

        def get_encoding(self, name):
            assert name == "o200k_base"
            return FakeEnc()

    monkeypatch.setitem(sys.modules, "tiktoken", FakeTikToken())
    count = cli._safe_token_count("abc", "gpt-4o-mini")
    assert count == 3


def test_safe_token_count_with_fake_tiktoken_cl100k(monkeypatch):
    class FakeEnc:
        def encode(self, text):
            return list(text)

    class FakeTikToken:
        def encoding_for_model(self, model):
            raise RuntimeError("force fallback")

        def get_encoding(self, name):
            assert name == "cl100k_base"
            return FakeEnc()

    monkeypatch.setitem(sys.modules, "tiktoken", FakeTikToken())
    count = cli._safe_token_count("abcd", "unknown-model")
    assert count == 4
