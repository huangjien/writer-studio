import logging
import os

from writer_studio.logging import get_logger, init_logging, parse_level


def test_parse_level_default_env(monkeypatch):
    monkeypatch.setenv("NOVEL_EVAL_LOG_LEVEL", "WARNING")
    assert parse_level(None) == logging.WARNING


def test_parse_level_unknown_value():
    # Unknown string should default to INFO
    assert parse_level("notalevel") == logging.INFO


def test_init_logging_configures_handlers_when_none():
    root = logging.getLogger()
    # Clear existing handlers to simulate fresh start
    for h in list(root.handlers):
        root.removeHandler(h)
    init_logging("DEBUG")
    assert root.handlers, "init_logging should configure at least one handler"
    assert root.level == logging.DEBUG


def test_get_logger_initializes_if_needed(monkeypatch):
    # Ensure no handlers so get_logger triggers init
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    # Default env level is INFO if NOVEL_EVAL_LOG_LEVEL not set
    monkeypatch.delenv("NOVEL_EVAL_LOG_LEVEL", raising=False)
    logger = get_logger("unit.test")
    assert logger.name == "unit.test"
    assert logging.getLogger().handlers, "get_logger should initialize logging"