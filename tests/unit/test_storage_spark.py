from __future__ import annotations

import builtins
import sys
from types import ModuleType, SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.storage import spark


def test_get_spark_session_returns_active_session(monkeypatch) -> None:
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(getActiveSession=lambda: "active")
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)

    assert spark.get_spark_session() == "active"


def test_get_spark_session_returns_none_when_pyspark_is_missing(monkeypatch) -> None:
    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "pyspark.sql":
            raise ImportError("missing pyspark")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)

    assert spark.get_spark_session() is None


def test_get_spark_session_does_not_create_session_inside_databricks_runtime(monkeypatch) -> None:
    builder_calls = []
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(
        getActiveSession=lambda: None,
        builder=SimpleNamespace(getOrCreate=lambda: builder_calls.append(True) or "created"),
    )
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "14.x")

    assert spark.get_spark_session() is None
    assert builder_calls == []


def test_get_spark_session_returns_none_when_active_session_has_runtime_error(
    monkeypatch,
) -> None:
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(
        getActiveSession=lambda: (_ for _ in ()).throw(RuntimeError("spark unavailable"))
    )
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)

    assert spark.get_spark_session() is None


def test_get_spark_session_surfaces_unexpected_active_session_errors(monkeypatch) -> None:
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(
        getActiveSession=lambda: (_ for _ in ()).throw(ValueError("spark bug"))
    )
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)

    with pytest.raises(ValueError, match="spark bug"):
        spark.get_spark_session()


def test_require_spark_session_raises_clear_error_when_no_session(monkeypatch) -> None:
    monkeypatch.setattr(spark, "get_spark_session", lambda: None)

    with pytest.raises(RuntimeError, match="storage\\.agent_events_table is configured"):
        spark.require_spark_session()


def test_require_spark_session_returns_active_session(monkeypatch) -> None:
    monkeypatch.setattr(spark, "get_spark_session", lambda: "active")

    assert spark.require_spark_session() == "active"
