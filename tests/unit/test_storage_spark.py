from __future__ import annotations

import builtins
import sys
from types import ModuleType, SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.storage import spark


def test_get_spark_session_returns_active_session(monkeypatch) -> None:
    monkeypatch.setattr(spark, "_logged_local_fallback", False)
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(getActiveSession=lambda: "active")
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)

    assert spark.get_spark_session() == "active"


def test_get_spark_session_creates_session_inside_databricks_runtime(monkeypatch) -> None:
    builder_calls = []
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(
        getActiveSession=lambda: None,
        builder=SimpleNamespace(getOrCreate=lambda: builder_calls.append(True) or "created"),
    )
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "14.x")

    assert spark.get_spark_session() == "created"
    assert builder_calls == [True]


def test_require_spark_session_returns_active_session(monkeypatch) -> None:
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(getActiveSession=lambda: "required-active")
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)

    assert spark.require_spark_session() == "required-active"


def test_require_spark_session_creates_session_when_none_is_active(monkeypatch) -> None:
    required_builder_calls = []
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(
        getActiveSession=lambda: None,
        builder=SimpleNamespace(
            getOrCreate=lambda: required_builder_calls.append(True) or "required-created"
        ),
    )
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)

    assert spark.require_spark_session() == "required-created"
    assert required_builder_calls == [True]


def test_get_spark_session_logs_local_fallback_once(monkeypatch, caplog) -> None:
    monkeypatch.setattr(spark, "_logged_local_fallback", False)
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(
        getActiveSession=lambda: (_ for _ in ()).throw(RuntimeError("spark unavailable"))
    )
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)

    with caplog.at_level("INFO"):
        assert spark.get_spark_session() is None
        assert spark.get_spark_session() is None

    assert len([message for message in caplog.messages if "Local mode" in message]) == 1


def test_require_spark_session_chains_spark_initialization_error(monkeypatch) -> None:
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
    pyspark_sql = ModuleType("pyspark.sql")
    pyspark_sql.SparkSession = SimpleNamespace(
        getActiveSession=lambda: (_ for _ in ()).throw(RuntimeError("spark unavailable"))
    )
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql)

    with pytest.raises(RuntimeError, match="Spark session initialization failed") as exc_info:
        spark.require_spark_session()

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_require_spark_session_rejects_missing_pyspark(monkeypatch) -> None:
    real_import = builtins.__import__

    def _raise_for_pyspark_sql(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pyspark.sql":
            raise ImportError("no pyspark")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _raise_for_pyspark_sql)

    with pytest.raises(RuntimeError, match="Refusing to fall back to local JSONL"):
        spark.require_spark_session()
