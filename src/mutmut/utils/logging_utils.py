"""File-based logging helpers, used mainly by the hot-fork orchestrator.

Child/orchestrator processes cannot easily log to the console without
corrupting the interactive terminal output, so mutmut logs to a rotating file
instead. Logging is opt-in (``log_to_file``/``debug`` config) and off by default.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mutmut.configuration import config

# Without a handler, logging falls back to lastResort, which writes WARNING+ to
# stderr and corrupts the interactive terminal. Keep mutmut's logs silent unless
# file logging is explicitly enabled.
logging.getLogger("mutmut").addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``mutmut.`` namespace."""
    return logging.getLogger(name if name.startswith("mutmut.") else f"mutmut.{name}")


logger = get_logger(__name__)


_file_handler: logging.Handler | None = None


def setup_file_logging(log_file: str | None = None, level: int = logging.DEBUG) -> None:
    """Attach a rotating file handler to the ``mutmut`` logger (idempotent).

    Useful for debugging child processes which cannot log to the console.

    Args:
        log_file: Path to the log file (defaults to ``config().log_file_path``).
        level: Logging level (default: DEBUG).
    """
    global _file_handler

    if _file_handler is not None:
        return

    log_path = Path(log_file if log_file is not None else config().log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
    )
    _file_handler.setLevel(level)
    _file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s.%(msecs)03d [%(process)d] %(name)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # File only - do not propagate to the root logger (which would hit stdout).
    root_logger = logging.getLogger("mutmut")
    root_logger.addHandler(_file_handler)
    root_logger.setLevel(level)
    root_logger.propagate = False

    logger.debug(f"File logging initialized: {log_path}")


def get_log_file_path() -> Path:
    """Return the configured debug-log file path."""
    return Path(config().log_file_path)
