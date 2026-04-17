import pyarrow as pa

from databricks_mcp_agent_hello_world.storage import bootstrap
from databricks_mcp_agent_hello_world.storage import persistence_schema


def test_arrow_field_to_spark_sql_type_maps_supported_demo_types() -> None:
    assert (
        persistence_schema.arrow_field_to_spark_sql_type(pa.field("event_id", pa.string()))
        == "STRING"
    )
    assert (
        persistence_schema.arrow_field_to_spark_sql_type(
            pa.field("payload_json", pa.large_string())
        )
        == "STRING"
    )
    assert (
        persistence_schema.arrow_field_to_spark_sql_type(pa.field("event_index", pa.int64()))
        == "BIGINT"
    )


def test_arrow_schema_to_sql_columns_renders_current_types_and_not_null() -> None:
    schema = pa.schema(
        [
            pa.field("event_index", pa.int64(), nullable=False),
            pa.field("payload_json", pa.large_string(), nullable=False),
            pa.field("error_message", pa.string(), nullable=True),
        ]
    )

    assert persistence_schema.arrow_schema_to_sql_columns(schema) == (
        "`event_index` BIGINT NOT NULL,\n"
        "`payload_json` STRING NOT NULL,\n"
        "`error_message` STRING"
    )


def test_arrow_schema_to_field_specs_derives_spark_comparison_fields() -> None:
    schema = pa.schema(
        [
            pa.field("event_index", pa.int64(), nullable=False),
            pa.field("payload_json", pa.large_string(), nullable=False),
            pa.field("error_message", pa.string(), nullable=True),
        ]
    )

    assert persistence_schema.arrow_schema_to_field_specs(schema) == [
        bootstrap.SchemaFieldSpec(name="event_index", data_type="bigint", nullable=False),
        bootstrap.SchemaFieldSpec(name="payload_json", data_type="string", nullable=False),
        bootstrap.SchemaFieldSpec(name="error_message", data_type="string", nullable=True),
    ]
