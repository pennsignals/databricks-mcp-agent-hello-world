from __future__ import annotations


def get_spark_session():
    try:
        from pyspark.sql import SparkSession
    except ImportError:
        return None

    try:
        return SparkSession.getActiveSession()
    except Exception:
        return None


def require_spark_session():
    spark = get_spark_session()
    if spark is None:
        raise RuntimeError(
            "Spark is required because storage.agent_events_table is configured, "
            "but no active Spark session is available."
        )
    return spark
