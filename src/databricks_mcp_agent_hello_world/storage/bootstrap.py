from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from . import schema
from .spark import get_spark_session
from .write import EVENTS_JSONL_FILE_NAME


@dataclass(frozen=True, slots=True)
class InitStorageReport:
    exit_code: int
    messages: list[str] = field(default_factory=list)
    changed: bool = False


@dataclass(frozen=True, slots=True)
class StorageTableName:
    catalog: str
    schema: str
    table: str

    @property
    def full_name(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.table}"

    @property
    def schema_name(self) -> str:
        return f"{self.catalog}.{self.schema}"


def init_storage(
    settings: Settings,
) -> InitStorageReport:
    spark = get_spark_session()
    if spark is None:
        local_data_dir = Path(settings.storage.local_data_dir).expanduser()
        created_dir = ensure_local_storage_dir(local_data_dir)
        return InitStorageReport(
            exit_code=0,
            messages=[
                (
                    f"Local storage directory created at {settings.storage.local_data_dir}"
                    if created_dir
                    else (
                        "Local storage directory already available at "
                        f"{settings.storage.local_data_dir}"
                    )
                )
            ],
            changed=created_dir,
        )

    table_name = (settings.storage.agent_events_table or "").strip()
    if not table_name:
        raise ValueError("storage.agent_events_table must be configured when Spark is available.")

    target = parse_table_name(table_name)
    messages: list[str] = []
    changed = False

    if not catalog_exists(spark, target.catalog):
        raise ValueError(f"Catalog {target.catalog} does not exist")

    if not schema_exists(spark, target):
        create_schema(spark, target)
        changed = True
        messages.append(f"Schema {target.schema_name} created")

    if not table_exists(spark, target):
        create_table(spark, target)
        changed = True
        messages.append(f"Table {target.full_name} created")
        return InitStorageReport(exit_code=0, messages=messages, changed=changed)

    schema_diff = compare_table_schema(spark, target)
    if schema_diff is None:
        messages.append(f"Table {target.full_name} already exists and matches expected schema")
        return InitStorageReport(exit_code=0, messages=messages, changed=changed)

    messages.append(f"Table {target.full_name} schema mismatch detected")
    messages.extend(schema_diff)
    messages.append("Refusing to modify an existing table automatically.")
    return InitStorageReport(exit_code=1, messages=messages, changed=changed)


def parse_table_name(table_name: str) -> StorageTableName:
    parts = [part.strip() for part in table_name.split(".")]
    if len(parts) != 3 or any(not part for part in parts):
        raise ValueError(
            "storage.agent_events_table must be a fully qualified 3-part name: "
            "catalog.schema.table"
        )
    return StorageTableName(catalog=parts[0], schema=parts[1], table=parts[2])


def ensure_local_storage_dir(local_data_dir: Path) -> bool:
    created = not local_data_dir.exists()
    local_data_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = local_data_dir / EVENTS_JSONL_FILE_NAME
    if jsonl_path.exists() and jsonl_path.is_dir():
        raise ValueError(f"Expected JSONL path to be a file, found directory: {jsonl_path}")
    return created


def catalog_exists(spark: Any, catalog_name: str) -> bool:
    rows = spark.sql(f"SHOW CATALOGS LIKE '{sql_literal(catalog_name)}'").collect()
    return any(_row_first_value(row) == catalog_name for row in rows)


def schema_exists(spark: Any, target: StorageTableName) -> bool:
    rows = spark.sql(
        f"SHOW SCHEMAS IN {quote_name(target.catalog)} LIKE '{sql_literal(target.schema)}'"
    ).collect()
    return any(_row_first_value(row) == target.schema for row in rows)


def create_schema(spark: Any, target: StorageTableName) -> None:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {qualified_schema_name(target)}")


def table_exists(spark: Any, target: StorageTableName) -> bool:
    rows = spark.sql(
        f"SHOW TABLES IN {qualified_schema_name(target)} LIKE '{sql_literal(target.table)}'"
    ).collect()
    return any(getattr(row, "tableName", None) == target.table for row in rows)


def compare_table_schema(spark: Any, target: StorageTableName) -> list[str] | None:
    expected_schema = expected_table_schema_fields(spark)
    actual_schema = actual_table_schema_fields(spark, target)
    if actual_schema == expected_schema:
        return None
    return format_schema_diff(expected_schema, actual_schema)


def expected_table_schema_fields(spark: Any) -> list[schema.SchemaFieldSpec]:
    del spark
    return schema.arrow_schema_to_field_specs(schema.EVENT_SCHEMA)


def actual_table_schema_fields(
    spark: Any, target: StorageTableName
) -> list[schema.SchemaFieldSpec]:
    schema = spark.table(qualified_table_name(target)).schema
    return spark_schema_to_field_specs(schema)


def create_table(spark: Any, target: StorageTableName) -> None:
    columns_sql = schema.arrow_schema_to_sql_columns(
        schema.EVENT_SCHEMA
    ).replace("\n", "\n    ")
    spark.sql(
        "\n".join(
            (
                f"CREATE TABLE {qualified_table_name(target)} (",
                f"    {columns_sql}",
                ")",
                "USING DELTA",
            )
        )
    )


def format_schema_diff(
    expected_schema: list[schema.SchemaFieldSpec], actual_schema: list[schema.SchemaFieldSpec]
) -> list[str]:
    return [
        "Expected schema:",
        *[f"  - {line}" for line in describe_schema(expected_schema)],
        "Actual schema:",
        *[f"  - {line}" for line in describe_schema(actual_schema)],
    ]


def describe_schema(schema_fields: list[schema.SchemaFieldSpec]) -> list[str]:
    return [
        f"{field.name}: {field.data_type} (nullable={field.nullable})"
        for field in schema_fields
    ]


def spark_schema_to_field_specs(schema_obj: Any) -> list[schema.SchemaFieldSpec]:
    return [
        schema.SchemaFieldSpec(
            name=field.name,
            data_type=field.dataType.simpleString(),
            nullable=field.nullable,
        )
        for field in schema_obj.fields
    ]


def qualified_schema_name(target: StorageTableName) -> str:
    return ".".join((quote_name(target.catalog), quote_name(target.schema)))


def qualified_table_name(target: StorageTableName) -> str:
    return ".".join(
        (quote_name(target.catalog), quote_name(target.schema), quote_name(target.table))
    )


def quote_name(name: str) -> str:
    escaped = name.replace("`", "``")
    return f"`{escaped}`"


def sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _row_first_value(row: Any) -> Any:
    if isinstance(row, dict):
        values = list(row.values())
        if values:
            return values[0]
    if hasattr(row, "asDict"):
        values = list(row.asDict().values())
        if values:
            return values[0]
    return row[0]
