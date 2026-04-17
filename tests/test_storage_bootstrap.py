from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.storage import bootstrap


@dataclass(frozen=True)
class FakeDataType:
    value: str

    def simpleString(self) -> str:
        return self.value


@dataclass(frozen=True)
class FakeField:
    name: str
    dataType: FakeDataType
    nullable: bool


@dataclass(frozen=True)
class FakeSchema:
    fields: tuple[FakeField, ...]


class FakeSqlResult:
    def __init__(self, rows):
        self._rows = rows

    def collect(self):
        return self._rows


class FakeCatalogApi:
    def __init__(self, spark: "FakeSpark") -> None:
        self.spark = spark

    def tableExists(self, table_name: str) -> bool:
        return table_name in self.spark.tables


class FakeDataFrameWriter:
    def __init__(self, spark: "FakeSpark", schema: FakeSchema) -> None:
        self.spark = spark
        self.schema = schema
        self.format_name = None
        self.mode_name = None

    def format(self, format_name: str):
        self.format_name = format_name
        return self

    def mode(self, mode_name: str):
        self.mode_name = mode_name
        return self

    def saveAsTable(self, table_name: str) -> None:
        normalized_name = ".".join(_unquote_qualified_name(table_name))
        self.spark.saved_tables.append(normalized_name)
        self.spark.tables[normalized_name] = self.schema


class FakeDataFrame:
    def __init__(self, spark: "FakeSpark", schema: FakeSchema) -> None:
        self.spark = spark
        self.schema = schema
        self.write = FakeDataFrameWriter(spark, schema)


class FakeSpark:
    def __init__(
        self,
        *,
        expected_schema: FakeSchema,
        catalogs: set[str] | None = None,
        schemas: set[tuple[str, str]] | None = None,
        tables: dict[str, FakeSchema] | None = None,
    ) -> None:
        self.expected_schema = expected_schema
        self.catalogs = set(catalogs or set())
        self.schemas = set(schemas or set())
        self.tables = dict(tables or {})
        self.catalog = FakeCatalogApi(self)
        self.sql_calls: list[str] = []
        self.saved_tables: list[str] = []
        self.dropped_tables: list[str] = []
        self.arrow_tables = []

    def sql(self, query: str) -> FakeSqlResult:
        self.sql_calls.append(query)
        if query.startswith("SHOW CATALOGS LIKE "):
            catalog_name = query.split("'")[1]
            rows = [{"catalog": catalog_name}] if catalog_name in self.catalogs else []
            return FakeSqlResult(rows)
        if query.startswith("SHOW SCHEMAS IN "):
            catalog_name = query.split("`")[1]
            schema_name = query.split("'")[1]
            return FakeSqlResult(
                [{"namespace": schema_name}]
                if (catalog_name, schema_name) in self.schemas
                else []
            )
        if query.startswith("SHOW TABLES IN "):
            schema_name = ".".join(
                _unquote_qualified_name(query.split(" LIKE ")[0].removeprefix("SHOW TABLES IN "))
            )
            table_name = query.split("'")[1]
            qualified_name = f"{schema_name}.{table_name}"
            return FakeSqlResult(
                [SimpleNamespace(tableName=table_name)] if qualified_name in self.tables else []
            )
        if query.startswith("CREATE SCHEMA IF NOT EXISTS "):
            catalog_name, schema_name = _unquote_qualified_name(
                query.removeprefix("CREATE SCHEMA IF NOT EXISTS ")
            )
            self.schemas.add((catalog_name, schema_name))
            return FakeSqlResult([])
        if query.startswith("DROP TABLE "):
            table_name = ".".join(_unquote_qualified_name(query.removeprefix("DROP TABLE ")))
            self.dropped_tables.append(table_name)
            self.tables.pop(table_name, None)
            return FakeSqlResult([])
        raise AssertionError(f"Unexpected SQL query: {query}")

    def createDataFrame(self, arrow_table) -> FakeDataFrame:
        self.arrow_tables.append(arrow_table)
        return FakeDataFrame(self, self.expected_schema)

    def table(self, table_name: str):
        normalized_name = ".".join(_unquote_qualified_name(table_name))
        return SimpleNamespace(schema=self.tables[normalized_name])


def _unquote_qualified_name(name: str) -> tuple[str, ...]:
    return tuple(part.strip("`") for part in name.split("."))


def _settings(tmp_path: Path, *, table_name: str = "main.agent_demo.agent_events"):
    return SimpleNamespace(
        storage=SimpleNamespace(
            local_data_dir=str(tmp_path / ".local_state"),
            agent_events_table=table_name,
        )
    )


def _schema(*names: str) -> FakeSchema:
    return FakeSchema(
        tuple(
            FakeField(
                name=name,
                dataType=FakeDataType("string"),
                nullable=False,
            )
            for name in names
        )
    )


def test_parse_table_name_requires_three_parts() -> None:
    with pytest.raises(ValueError, match="3-part name"):
        bootstrap.parse_table_name("main.agent_events")


def test_confirm_defaults_to_no(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert bootstrap.prompt_yes_no("Create it?") is False

    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert bootstrap.prompt_yes_no("Create it?") is True


def test_init_storage_local_mode_creates_directory_without_jsonl(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: None,
    )

    report = bootstrap.init_storage(settings)

    local_data_dir = Path(settings.storage.local_data_dir)
    assert report.exit_code == 0
    assert report.messages == [f"Local storage ready at {settings.storage.local_data_dir}"]
    assert local_data_dir.exists()
    assert not (local_data_dir / "agent_events.jsonl").exists()


def test_init_storage_fails_when_catalog_is_missing(tmp_path: Path, monkeypatch) -> None:
    spark = FakeSpark(expected_schema=_schema("schema_version"))
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )

    with pytest.raises(ValueError, match="Catalog main does not exist"):
        bootstrap.init_storage(_settings(tmp_path))


def test_init_storage_creates_missing_schema_after_confirmation(
    tmp_path: Path, monkeypatch
) -> None:
    spark = FakeSpark(expected_schema=_schema("schema_version"), catalogs={"main"})
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )
    report = bootstrap.init_storage(_settings(tmp_path), prompt_fn=lambda prompt: "y")

    assert report.exit_code == 0
    assert report.messages == [
        "Schema main.agent_demo created",
        "Table main.agent_demo.agent_events created",
    ]
    assert ("main", "agent_demo") in spark.schemas
    assert spark.saved_tables == ["main.agent_demo.agent_events"]


def test_init_storage_creates_missing_table_without_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    spark = FakeSpark(
        expected_schema=_schema("schema_version"),
        catalogs={"main"},
        schemas={("main", "agent_demo")},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )
    report = bootstrap.init_storage(_settings(tmp_path))

    assert report.exit_code == 0
    assert report.messages == ["Table main.agent_demo.agent_events created"]
    assert spark.saved_tables == ["main.agent_demo.agent_events"]


def test_init_storage_noops_when_existing_table_matches_expected_schema(
    tmp_path: Path, monkeypatch
) -> None:
    expected_schema = _schema("schema_version")
    spark = FakeSpark(
        expected_schema=expected_schema,
        catalogs={"main"},
        schemas={("main", "agent_demo")},
        tables={"main.agent_demo.agent_events": expected_schema},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )

    report = bootstrap.init_storage(_settings(tmp_path))

    assert report.exit_code == 0
    assert report.messages == [
        "Table main.agent_demo.agent_events already exists and matches expected schema"
    ]
    assert spark.saved_tables == []
    assert spark.dropped_tables == []


def test_init_storage_returns_error_when_mismatch_is_declined(
    tmp_path: Path, monkeypatch
) -> None:
    spark = FakeSpark(
        expected_schema=_schema("schema_version"),
        catalogs={"main"},
        schemas={("main", "agent_demo")},
        tables={"main.agent_demo.agent_events": _schema("event_id")},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )
    report = bootstrap.init_storage(_settings(tmp_path), prompt_fn=lambda prompt: "n")

    assert report.exit_code == 1
    assert report.messages[0] == "Table main.agent_demo.agent_events schema mismatch detected"
    assert "Expected schema:" in report.messages
    assert "Actual schema:" in report.messages
    assert report.messages[-1] == "No changes were made."
    assert spark.saved_tables == []
    assert spark.dropped_tables == []


def test_init_storage_recreates_table_when_mismatch_is_confirmed(
    tmp_path: Path, monkeypatch
) -> None:
    spark = FakeSpark(
        expected_schema=_schema("schema_version"),
        catalogs={"main"},
        schemas={("main", "agent_demo")},
        tables={"main.agent_demo.agent_events": _schema("event_id")},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )
    report = bootstrap.init_storage(_settings(tmp_path), prompt_fn=lambda prompt: "yes")

    assert report.exit_code == 0
    assert report.messages[-1] == "Table main.agent_demo.agent_events dropped and recreated"
    assert spark.dropped_tables == ["main.agent_demo.agent_events"]
    assert spark.saved_tables == ["main.agent_demo.agent_events"]


def test_init_storage_yes_auto_approves_without_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    spark = FakeSpark(expected_schema=_schema("schema_version"), catalogs={"main"})
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )
    report = bootstrap.init_storage(_settings(tmp_path), assume_yes=True)

    assert report.exit_code == 0
    assert report.messages == [
        "Schema main.agent_demo created",
        "Table main.agent_demo.agent_events created",
    ]
