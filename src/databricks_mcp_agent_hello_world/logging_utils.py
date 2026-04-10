from __future__ import annotations

import logging
import os


def configure_logging(level: str | None = None) -> None:
    log_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(getattr(logging, log_level, logging.INFO))
        return
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
