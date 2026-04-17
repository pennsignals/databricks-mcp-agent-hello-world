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
        self.sql_calls: list[str] = []
        self.created_tables: list[str] = []
        self.create_table_sql: list[str] = []
        self.dropped_tables: list[str] = []

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
        if query.startswith("CREATE TABLE "):
            table_name = ".".join(
                _unquote_qualified_name(query.split("(", 1)[0].removeprefix("CREATE TABLE ").strip())
            )
            self.create_table_sql.append(query)
            self.created_tables.append(table_name)
            self.tables[table_name] = self.created_table_schema
            return FakeSqlResult([])
        if query.startswith("DROP TABLE "):
            table_name = ".".join(_unquote_qualified_name(query.removeprefix("DROP TABLE ")))
            self.dropped_tables.append(table_name)
            self.tables.pop(table_name, None)
            return FakeSqlResult([])
        raise AssertionError(f"Unexpected SQL query: {query}")

    def createDataFrame(self, *_args, **_kwargs):
        raise AssertionError("bootstrap should not call createDataFrame")

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


def _field_specs(*names: str) -> list[bootstrap.SchemaFieldSpec]:
    return [
        bootstrap.SchemaFieldSpec(
            name=name,
            data_type="string",
            nullable=False,
        )
        for name in names
    ]


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
    assert report.messages == [
        f"Local storage directory created at {settings.storage.local_data_dir}"
    ]
    assert local_data_dir.exists()
    assert not (local_data_dir / "agent_events.jsonl").exists()


def test_init_storage_local_mode_noops_when_directory_already_exists(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    Path(settings.storage.local_data_dir).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: None,
    )

    report = bootstrap.init_storage(settings)

    assert report.exit_code == 0
    assert report.changed is False
    assert report.messages == [
        f"Local storage directory already available at {settings.storage.local_data_dir}"
    ]


def test_init_storage_fails_when_catalog_is_missing(tmp_path: Path, monkeypatch) -> None:
    spark = FakeSpark()
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )

    with pytest.raises(ValueError, match="Catalog main does not exist"):
        bootstrap.init_storage(_settings(tmp_path))


def test_init_storage_creates_missing_schema_automatically(tmp_path: Path, monkeypatch) -> None:
    spark = FakeSpark(catalogs={"main"})
    monkeypatch.setattr(
        bootstrap.persistence_schema,
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
    assert ("main", "agent_demo") in spark.schemas
    assert spark.created_tables == ["main.agent_demo.agent_events"]
    assert spark.create_table_sql == [
        "CREATE TABLE `main`.`agent_demo`.`agent_events` (\n"
        "    `schema_version` STRING NOT NULL\n"
        ")\n"
        "USING DELTA"
    ]


def test_init_storage_creates_missing_table_without_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    spark = FakeSpark(
        catalogs={"main"},
        schemas={("main", "agent_demo")},
    )
    monkeypatch.setattr(
        bootstrap.persistence_schema,
        "arrow_schema_to_sql_columns",
        lambda schema: "`schema_version` STRING NOT NULL",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )
    report = bootstrap.init_storage(_settings(tmp_path))

    assert report.exit_code == 0
    assert report.messages == ["Table main.agent_demo.agent_events created"]
    assert spark.created_tables == ["main.agent_demo.agent_events"]
    assert spark.create_table_sql == [
        "CREATE TABLE `main`.`agent_demo`.`agent_events` (\n"
        "    `schema_version` STRING NOT NULL\n"
        ")\n"
        "USING DELTA"
    ]


def test_init_storage_noops_when_existing_table_matches_expected_schema(
    tmp_path: Path, monkeypatch
) -> None:
    expected_schema = _schema("schema_version")
    expected_field_specs = _field_specs("schema_version")
    spark = FakeSpark(
        catalogs={"main"},
        schemas={("main", "agent_demo")},
        tables={"main.agent_demo.agent_events": expected_schema},
    )
    monkeypatch.setattr(
        bootstrap.persistence_schema,
        "arrow_schema_to_field_specs",
        lambda schema: expected_field_specs,
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
    assert spark.created_tables == []
    assert spark.dropped_tables == []


def test_init_storage_returns_error_when_schema_mismatches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        bootstrap.persistence_schema,
        "arrow_schema_to_field_specs",
        lambda schema: _field_specs("schema_version"),
    )
    spark = FakeSpark(
        catalogs={"main"},
        schemas={("main", "agent_demo")},
        tables={"main.agent_demo.agent_events": _schema("event_id")},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: spark,
    )
    report = bootstrap.init_storage(_settings(tmp_path))

    assert report.exit_code == 1
    assert report.messages[0] == "Table main.agent_demo.agent_events schema mismatch detected"
    assert "Expected schema:" in report.messages
    assert "Actual schema:" in report.messages
    assert report.messages[-1] == "Refusing to modify an existing table automatically."
    assert spark.created_tables == []
    assert spark.dropped_tables == []


def test_init_storage_yes_flag_does_not_change_non_destructive_behavior(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        bootstrap.persistence_schema,
        "arrow_schema_to_field_specs",
        lambda schema: _field_specs("schema_version"),
    )
    mismatching_spark = FakeSpark(
        catalogs={"main"},
        schemas={("main", "agent_demo")},
        tables={"main.agent_demo.agent_events": _schema("event_id")},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: mismatching_spark,
    )

    report = bootstrap.init_storage(_settings(tmp_path), assume_yes=True)

    assert report.exit_code == 1
    assert report.messages[-1] == "Refusing to modify an existing table automatically."
    assert mismatching_spark.dropped_tables == []
    assert mismatching_spark.created_tables == []


def test_init_storage_yes_flag_still_allows_automatic_create_paths(
    tmp_path: Path, monkeypatch
) -> None:
    spark = FakeSpark(catalogs={"main"})
    monkeypatch.setattr(
        bootstrap.persistence_schema,
        "arrow_schema_to_sql_columns",
        lambda schema: "`schema_version` STRING NOT NULL",
    )
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


def test_expected_table_schema_fields_uses_arrow_schema_helper(monkeypatch) -> None:
    sentinel_spark = object()
    expected = [
        bootstrap.SchemaFieldSpec(name="schema_version", data_type="string", nullable=False),
        bootstrap.SchemaFieldSpec(name="payload_json", data_type="string", nullable=False),
    ]
    calls: list[object] = []

    monkeypatch.setattr(
        bootstrap.persistence_schema,
        "arrow_schema_to_field_specs",
        lambda schema: calls.append(schema) or expected,
    )

    assert bootstrap.expected_table_schema_fields(sentinel_spark) == expected
    assert calls == [bootstrap.persistence_schema.EVENT_SCHEMA]


def test_create_table_uses_generated_delta_ddl(monkeypatch) -> None:
    spark = FakeSpark(catalogs={"main"}, schemas={("main", "agent_demo")})
    target = bootstrap.parse_table_name("main.agent_demo.agent_events")

    monkeypatch.setattr(
        bootstrap.persistence_schema,
        "arrow_schema_to_sql_columns",
        lambda schema: (
            "`event_index` BIGINT NOT NULL,\n"
            "`payload_json` STRING NOT NULL,\n"
            "`error_message` STRING"
        ),
    )

    bootstrap.create_table(spark, target)

    assert spark.created_tables == ["main.agent_demo.agent_events"]
    assert spark.create_table_sql == [
        "CREATE TABLE `main`.`agent_demo`.`agent_events` (\n"
        "    `event_index` BIGINT NOT NULL,\n"
        "    `payload_json` STRING NOT NULL,\n"
        "    `error_message` STRING\n"
        ")\n"
        "USING DELTA"
    ]
