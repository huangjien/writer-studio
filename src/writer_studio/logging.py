import logging
import os
from typing import Optional

DEFAULT_LEVEL = os.getenv("NOVEL_EVAL_LOG_LEVEL", "INFO").upper()

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def parse_level(level: Optional[str]) -> int:
    if level is None:
        level = DEFAULT_LEVEL
    lvl = str(level).upper()
    return _LEVELS.get(lvl, logging.INFO)


def init_logging(level: Optional[str] = None) -> None:
    """Initialize root logging configuration.

    - Level comes from `level` or env `NOVEL_EVAL_LOG_LEVEL`.
    - Uses a concise format with time, level, logger name, and message.
    - If logging already configured, only updates the level.
    """
    lvl = parse_level(level)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=lvl,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        root.setLevel(lvl)


def get_logger(name: str) -> logging.Logger:
    """Return a module-specific logger, ensuring initialization has occurred."""
    if not logging.getLogger().handlers:
        init_logging(DEFAULT_LEVEL)
    return logging.getLogger(name)
