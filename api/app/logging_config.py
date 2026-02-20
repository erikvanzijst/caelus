from __future__ import annotations

import logging
import os
import sys

_DEFAULT_LOG_LEVEL = "INFO"
_RESET = "\x1b[0m"
_LEVEL_COLORS = {
    "DEBUG": "\x1b[36m",
    "INFO": "\x1b[32m",
    "WARNING": "\x1b[33m",
    "ERROR": "\x1b[31m",
    "CRITICAL": "\x1b[1;31m",
}


class _ColorFormatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: str, *, use_color: bool) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        original = record.levelname
        if self._use_color:
            color = _LEVEL_COLORS.get(original, "")
            record.levelname = f"{color}{original}{_RESET}" if color else original
        try:
            return super().format(record)
        finally:
            record.levelname = original


def _should_use_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def _resolve_level(level: str | int | None) -> int:
    if isinstance(level, int):
        return level
    candidate = (level or os.getenv("CAELUS_LOG_LEVEL", _DEFAULT_LOG_LEVEL)).upper()
    resolved = logging.getLevelName(candidate)
    if isinstance(resolved, int):
        return resolved
    return logging.INFO


def configure_logging(*, level: str | int | None = None, force: bool = False) -> None:
    root = logging.getLogger()
    resolved_level = _resolve_level(level)
    root.setLevel(resolved_level)

    if root.handlers and not force:
        for handler in root.handlers:
            handler.setLevel(resolved_level)
        return

    handler = logging.StreamHandler()
    handler.setLevel(resolved_level)
    handler.setFormatter(
        _ColorFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            use_color=_should_use_color(),
        )
    )
    root.handlers.clear()
    root.addHandler(handler)
