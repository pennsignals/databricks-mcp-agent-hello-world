from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_spark_session():
    try:
        from pyspark.sql import SparkSession

        active = SparkSession.getActiveSession()
        if active:
            return active
        if os.getenv("DATABRICKS_RUNTIME_VERSION"):
            return SparkSession.builder.getOrCreate()
    except Exception:  # noqa: BLE001
        pass
    logger.info("Spark session unavailable; falling back to local persistence.")
    return None
