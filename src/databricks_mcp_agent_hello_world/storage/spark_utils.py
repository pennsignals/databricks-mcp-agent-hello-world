from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_spark_session():
    try:
        from pyspark.sql import SparkSession

        return SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    except Exception:  # noqa: BLE001
        logger.info("Spark session unavailable; falling back to local persistence.")
        return None
