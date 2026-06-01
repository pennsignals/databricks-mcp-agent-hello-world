from __future__ import annotations

from types import SimpleNamespace

import pytest

from databricks_tool_agent_template.storage import bootstrap, write


def test_parse_table_name_normalizes_three_part_table_name() -> None:
    target = bootstrap.parse_table_name(" main . demo . events ")

    assert target.full_name == "main.demo.events"
    assert target.schema_name == "main.demo"


def test_parse_table_name_rejects_non_three_part_table_name() -> None:
    with pytest.raises(ValueError, match="fully qualified 3-part name"):
        bootstrap.parse_table_name("main.demo")


def test_ensure_local_storage_dir_creates_directory_once(tmp_path) -> None:
    local_dir = tmp_path / "state"

    assert bootstrap.ensure_local_storage_dir(local_dir) is True
    assert bootstrap.ensure_local_storage_dir(local_dir) is False


def test_ensure_local_storage_dir_rejects_jsonl_directory(tmp_path) -> None:
    local_dir = tmp_path / "state"
    local_dir.mkdir()
    (local_dir / write.EVENTS_JSONL_FILE_NAME).mkdir()

    with pytest.raises(ValueError, match="Expected JSONL path to be a file"):
        bootstrap.ensure_local_storage_dir(local_dir)


@pytest.mark.parametrize(
    ("helper", "value", "expected"),
    [
        pytest.param(bootstrap.quote_name, "a`b", "`a``b`", id="quote-name"),
        pytest.param(bootstrap.sql_literal, "O'Hare", "O''Hare", id="sql-literal"),
    ],
)
def test_sql_text_helpers_escape_special_characters(helper, value: str, expected: str) -> None:
    assert helper(value) == expected


def test_describe_schema_returns_empty_list_for_empty_schema() -> None:
    assert bootstrap.describe_schema([]) == []


def test_compare_table_schema_returns_none_when_expected_and_actual_match(monkeypatch) -> None:
    matching_spark = SimpleNamespace(
        table=lambda name: SimpleNamespace(schema=SimpleNamespace(fields=[]))
    )
    monkeypatch.setattr(
        bootstrap.schema,
        "arrow_schema_to_field_specs",
        lambda event_schema: [],
    )

    assert (
        bootstrap.compare_table_schema(
            matching_spark,
            bootstrap.StorageTableName("main", "demo", "events"),
        )
        is None
    )
