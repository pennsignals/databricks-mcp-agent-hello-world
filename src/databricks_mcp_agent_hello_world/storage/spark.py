from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)
_logged_local_fallback = False


def get_spark_session():
    global _logged_local_fallback
    try:
        from pyspark.sql import SparkSession

        active = SparkSession.getActiveSession()
        if active:
            return active
        if os.getenv("DATABRICKS_RUNTIME_VERSION"):
            return SparkSession.builder.getOrCreate()
    except Exception:  # noqa: BLE001
        pass
    if not _logged_local_fallback:
        logger.info(
            "Local mode: no active Spark session detected; using local fallback persistence."
        )
        _logged_local_fallback = True
    return None


def is_spark_available(spark: Any | None = None) -> bool:
    return (spark or get_spark_session()) is not None
