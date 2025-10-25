from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .infra.settings import SettingsLoader


def configure_logging() -> None:
    """Configure project-wide logging with rotating file and console output.

    Uses SettingsLoader for file path, level, and rotation settings. Idempotent:
    subsequent calls won't duplicate handlers.
    """
    settings = SettingsLoader()
    log_file = Path(settings.get("log_file"))
    level_name = str(settings.get("log_level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("valutatrade")
    if logger.handlers:
        # Already configured
        logger.setLevel(level)
        return

    handler = RotatingFileHandler(
        log_file,
        maxBytes=int(settings.get("log_rotation_bytes", 1_048_576)),
        backupCount=int(settings.get("log_backup_count", 5)),
        encoding="utf-8",
    )
    fmt = logging.Formatter(
        fmt=(
            "%(levelname)s %(asctime)s %(message)s"
        ),
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(fmt)

    logger.setLevel(level)
    logger.addHandler(handler)
    # Also echo to console at INFO level
    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(fmt)
    logger.addHandler(stream)
