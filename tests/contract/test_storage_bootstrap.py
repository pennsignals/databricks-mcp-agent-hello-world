from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.storage import bootstrap
from tests.helpers import make_settings


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


class FakeSpark:
    def __init__(
        self,
        *,
        created_table_schema: FakeSchema | None = None,
        catalogs: set[str] | None = None,
        schemas: set[tuple[str, str]] | None = None,
        tables: dict[str, FakeSchema] | None = None,
    ) -> None:
        self.created_table_schema = created_table_schema or _schema("schema_version")
        self.catalogs = set(catalogs or set())
        self.schemas = set(schemas or set())
        self.tables = dict(tables or {})
        self.catalog = FakeCatalogApi(self)
        self.created_tables: list[str] = []
        self.create_table_sql: list[str] = []

    def sql(self, query: str) -> FakeSqlResult:
        if query.startswith("SHOW CATALOGS LIKE "):
            catalog_name = query.split("'")[1]
            rows = [{"catalog": catalog_name}] if catalog_name in self.catalogs else []
            return FakeSqlResult(rows)
        if query.startswith("SHOW SCHEMAS IN "):
            catalog_name = query.split("`")[1]
            schema_name = query.split("'")[1]
            rows = (
                [{"namespace": schema_name}]
                if (catalog_name, schema_name) in self.schemas
                else []
            )
            return FakeSqlResult(rows)
        if query.startswith("SHOW TABLES IN "):
            schema_name = ".".join(
                _unquote_qualified_name(
                    query.split(" LIKE ")[0].removeprefix("SHOW TABLES IN ")
                )
            )
            table_name = query.split("'")[1]
            qualified_name = f"{schema_name}.{table_name}"
            rows = (
                [SimpleNamespace(tableName=table_name)]
                if qualified_name in self.tables
                else []
            )
            return FakeSqlResult(rows)
        if query.startswith("CREATE SCHEMA IF NOT EXISTS "):
            catalog_name, schema_name = _unquote_qualified_name(
                query.removeprefix("CREATE SCHEMA IF NOT EXISTS ")
            )
            self.schemas.add((catalog_name, schema_name))
            return FakeSqlResult([])
        if query.startswith("CREATE TABLE "):
            table_name = ".".join(
                _unquote_qualified_name(
                    query.split("(", 1)[0].removeprefix("CREATE TABLE ").strip()
                )
            )
            self.create_table_sql.append(query)
            self.created_tables.append(table_name)
            self.tables[table_name] = self.created_table_schema
            return FakeSqlResult([])
        raise AssertionError(f"Unexpected SQL query: {query}")

    def table(self, table_name: str):
        normalized_name = ".".join(_unquote_qualified_name(table_name))
        return SimpleNamespace(schema=self.tables[normalized_name])


def _unquote_qualified_name(name: str) -> tuple[str, ...]:
    return tuple(part.strip("`") for part in name.split("."))


def _settings(tmp_path: Path, *, table_name: str = "main.agent_demo.agent_events"):
    return make_settings(
        storage={
            "local_data_dir": str(tmp_path / ".local_state"),
            "agent_events_table": table_name,
        }
    )


def _schema(*names: str) -> FakeSchema:
    return FakeSchema(
        tuple(
            FakeField(name=name, dataType=FakeDataType("string"), nullable=False)
            for name in names
        )
    )


def test_init_storage_local_mode_creates_directory_without_jsonl(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: None,
    )

    report = bootstrap.init_storage(settings)

    assert report.exit_code == 0
    assert Path(settings.storage.local_data_dir).exists()
    assert not (Path(settings.storage.local_data_dir) / "agent_events.jsonl").exists()


def test_init_storage_creates_missing_remote_schema_and_table(tmp_path: Path, monkeypatch) -> None:
    spark = FakeSpark(catalogs={"main"})
    monkeypatch.setattr(
        bootstrap.schema,
        "arrow_schema_to_sql_columns",
        lambda schema: "`schema_version` STRING NOT NULL",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )

    report = bootstrap.init_storage(_settings(tmp_path))

    assert report.exit_code == 0
    assert report.messages == [
        "Schema main.agent_demo created",
        "Table main.agent_demo.agent_events created",
    ]
    assert spark.created_tables == ["main.agent_demo.agent_events"]


def test_init_storage_fails_when_remote_catalog_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: FakeSpark(),
    )

    with pytest.raises(ValueError, match="Catalog main does not exist"):
        bootstrap.init_storage(_settings(tmp_path))


def test_init_storage_reports_schema_mismatch_without_modifying_existing_table(
    tmp_path: Path,
    monkeypatch,
) -> None:
    spark = FakeSpark(
        catalogs={"main"},
        schemas={("main", "agent_demo")},
        tables={"main.agent_demo.agent_events": _schema("wrong_field")},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )

    report = bootstrap.init_storage(_settings(tmp_path))

    assert report.exit_code == 1
    assert (
        report.messages[0]
        == "Table main.agent_demo.agent_events schema mismatch detected"
    )
    assert report.messages[-1] == "Refusing to modify an existing table automatically."
