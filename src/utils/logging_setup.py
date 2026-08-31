from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import (
    APPLICATION_LOG,
    CAMERA_LOG,
    DETECTION_LOG,
    LOG_BACKUP_COUNT,
    LOG_LEVEL,
    LOG_MAX_BYTES,
)


def _file_handler(path: Path, level: str, max_bytes: int, backup_count: int):
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level.upper())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


def _configure(name: str, path: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL.upper())
    logger.propagate = False

    # Avoid duplicate handlers if setup is called more than once.
    if not logger.handlers:
        logger.addHandler(
            _file_handler(path, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT)
        )

    return logger


def setup_logging() -> dict:
    """
    Configure the three dedicated log files and return the loggers.

    Returns:
        Dict with keys ``app`` (application.log), ``camera`` (camera.log) and
        ``detection`` (detection.log).
    """
    return {
        "app": _configure("application", APPLICATION_LOG),
        "camera": _configure("camera", CAMERA_LOG),
        "detection": _configure("detection", DETECTION_LOG),
    }


def get_logger(name: str) -> logging.Logger:
    """Return an existing configured logger (no-op if not yet configured)."""
    return logging.getLogger(name)