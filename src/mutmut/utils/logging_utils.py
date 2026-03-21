import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mutmut.configuration import config


def get_logger(name: str) -> logging.Logger:
    """Get the logger for the logging_utils module."""
    return logging.getLogger(name if name.startswith("mutmut.") else f"mutmut.{name}")


logger = get_logger(__name__)


_file_handler: logging.Handler | None = None


def setup_file_logging(log_file: str = "mutants/mutmut-debug.log", level: int = logging.DEBUG) -> None:
    """Set up file-based logging for debugging.

    Creates a rotating log file at the specified path. Useful for debugging
    child processes which can't easily log to the console.

    Args:
        log_file: Path to the log file (default: 'mutants/mutmut-debug.log')
        level: Logging level (default: DEBUG)
    """
    global _file_handler

    if _file_handler is not None:
        return

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
    )
    _file_handler.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(process)d] %(name)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    _file_handler.setFormatter(formatter)

    # Add handler to mutmut logger - file only, no stdout
    root_logger = logging.getLogger("mutmut")
    root_logger.addHandler(_file_handler)
    root_logger.setLevel(level)
    root_logger.propagate = False  # Don't propagate to root logger (avoids stdout)

    logger.debug(f"File logging initialized: {log_path}")


def get_log_file_path() -> Path:
    """Get the path to the debug log file.

    Args:
        log_dir: Directory where log files are stored

    Returns:
        Path to the debug log file
    """
    return Path(config().log_file_path)
