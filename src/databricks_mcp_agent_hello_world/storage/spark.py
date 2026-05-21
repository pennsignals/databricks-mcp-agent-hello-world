from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
_logged_local_fallback = False
NO_SPARK_REQUIRED_MESSAGE = (
    "Spark is required by storage.require_spark=true, but no Spark session is available. "
    "Refusing to fall back to local JSONL."
)
SPARK_INIT_FAILED_REQUIRED_MESSAGE = (
    "Spark is required by storage.require_spark=true, but Spark session initialization failed."
)


def get_spark_session():
    global _logged_local_fallback
    try:
        from pyspark.sql import SparkSession

        active = SparkSession.getActiveSession()
        if active:
            return active
        if os.getenv("DATABRICKS_RUNTIME_VERSION"):
            return SparkSession.builder.getOrCreate()
    except Exception:
        pass
    if not _logged_local_fallback:
        logger.info(
            "Local mode: no active Spark session detected; using local fallback persistence."
        )
        _logged_local_fallback = True
    return None


def require_spark_session():
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise RuntimeError(NO_SPARK_REQUIRED_MESSAGE) from exc

    try:
        active = SparkSession.getActiveSession()
        if active:
            return active
        return SparkSession.builder.getOrCreate()
    except Exception as exc:
        raise RuntimeError(SPARK_INIT_FAILED_REQUIRED_MESSAGE) from exc
