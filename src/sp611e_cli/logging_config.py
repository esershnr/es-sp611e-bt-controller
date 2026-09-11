"""Logging configuration for SP611E CLI and Web Server."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from sp611e_cli.config import CONFIG_DIR

LOG_FILE: Path = CONFIG_DIR / "sp611e.log"


def get_log_path() -> Path:
    """Return the absolute path to the log file."""
    return LOG_FILE


def setup_logging(verbose: bool = False) -> None:
    """Configure file and console logging.

    Args:
        verbose: If True, set console logging level to DEBUG instead of WARNING.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Root logger for sp611e package
    pkg_logger = logging.getLogger("sp611e_cli")
    pkg_logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers if setup_logging is called multiple times
    if pkg_logger.handlers:
        return

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler (max 2 MB per file, keeps 3 backups)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    pkg_logger.addHandler(file_handler)

    # Console handler
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        pkg_logger.addHandler(console_handler)
