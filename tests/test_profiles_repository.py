from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world.models import ToolProfile, ToolSpec
from databricks_mcp_agent_hello_world.profiles.repository import ToolProfileRepository


def _settings(tmp_path: Path):
    return SimpleNamespace(
        active_profile_name="default",
        storage=SimpleNamespace(
            local_data_dir=str(tmp_path),
            tool_profile_table="main.agent.tool_profiles",
        ),
    )


def _tool(name: str) -> ToolSpec:
    return ToolSpec(
        tool_name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}, "required": []},
        provider_type="local_python",
        provider_id="builtin_tools",
    )


def _profile(version: str, created_at: str) -> ToolProfile:
    return ToolProfile(
        profile_name="default",
        profile_version=version,
        created_at=created_at,
        inventory_hash="hash-1",
        provider_type="local_python",
        llm_endpoint_name="endpoint-a",
        prompt_version="v1",
        discovered_tools=[_tool("greet_user")],
        allowed_tools=["greet_user"],
        disallowed_tools=[],
        justifications={"greet_user": "needed"},
        audit_report_text="audit",
        selection_policy="small allowlist",
    )


class FakeRow:
    def __init__(self, payload):
        self.payload = payload

    def asDict(self, recursive=True):  # noqa: ARG002
        return self.payload


class FakeFrame:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters: list[str] = []
        self.orderings: list[tuple[tuple[str, ...], object]] = []

    def where(self, expression):
        self.filters.append(expression)
        if expression == "is_active = true":
            self.rows = [row for row in self.rows if row["is_active"]]
        elif expression.startswith("profile_name = '") and expression.endswith("'"):
            profile_name = expression[len("profile_name = '") : -1].replace("''", "'")
            self.rows = [row for row in self.rows if row["profile_name"] == profile_name]
        return self

    def orderBy(self, *columns, **kwargs):
        ascending = kwargs.get("ascending", True)
        if isinstance(ascending, (list, tuple)):
            flags = list(ascending)
        else:
            flags = [ascending] * len(columns)
        self.orderings.append((columns, ascending))
        for column, is_ascending in reversed(list(zip(columns, flags))):
            self.rows.sort(key=lambda row, col=column: row[col], reverse=not is_ascending)
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def collect(self):
        return [FakeRow(row) for row in self.rows]


class FakeSpark:
    def __init__(self, rows=None, table_error=None):
        self.rows = list(rows or [])
        self.table_error = table_error
        self.table_names: list[str] = []
        self.last_frame: FakeFrame | None = None

    def table(self, table_name):
        self.table_names.append(table_name)
        if self.table_error is not None:
            raise self.table_error
        self.last_frame = FakeFrame(self.rows)
        return self.last_frame


def test_profile_repository_uses_local_fallback_when_spark_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.profiles.repository.get_spark_session",
        lambda: None,
    )
    repo = ToolProfileRepository(_settings(tmp_path))
    profile = _profile("v1", "2026-04-13T10:00:00+00:00")

    repo.save(profile)

    loaded = repo.load_active("default")
    assert loaded == profile


def test_profile_repository_loads_latest_active_profile_from_delta(
    tmp_path: Path, monkeypatch
) -> None:
    older = ToolProfileRepository._to_persisted_row(
        _profile("v1", "2026-04-13T10:00:00+00:00")
    )
    newer_same_created_at = ToolProfileRepository._to_persisted_row(
        _profile("v2", "2026-04-13T10:00:00+00:00")
    )
    inactive_latest = ToolProfileRepository._to_persisted_row(
        _profile("v3", "2026-04-13T12:00:00+00:00")
    )
    inactive_latest["is_active"] = False
    other_profile = ToolProfileRepository._to_persisted_row(
        ToolProfile(
            profile_name="other",
            profile_version="v9",
            created_at="2026-04-13T13:00:00+00:00",
            inventory_hash="hash-1",
            provider_type="local_python",
            llm_endpoint_name="endpoint-a",
            prompt_version="v1",
            discovered_tools=[_tool("greet_user")],
            allowed_tools=["greet_user"],
            disallowed_tools=[],
            justifications={"greet_user": "needed"},
            audit_report_text="audit",
            selection_policy="small allowlist",
        )
    )

    spark = FakeSpark(
        [
            older,
            newer_same_created_at,
            inactive_latest,
            other_profile,
        ]
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.profiles.repository.get_spark_session",
        lambda: spark,
    )
    repo = ToolProfileRepository(_settings(tmp_path))

    loaded = repo.load_active("default")

    assert loaded.profile_version == "v2"
    assert loaded.created_at == "2026-04-13T10:00:00+00:00"
    assert loaded.profile_name == "default"
    assert spark.table_names == ["main.agent.tool_profiles"]
    assert spark.last_frame is not None
    assert spark.last_frame.filters == [
        "profile_name = 'default'",
        "is_active = true",
    ]


def test_profile_repository_returns_none_when_delta_table_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.profiles.repository.get_spark_session",
        lambda: FakeSpark(table_error=RuntimeError("Table or view not found: main.agent.tool_profiles")),
    )
    repo = ToolProfileRepository(_settings(tmp_path))

    assert repo.load_active("default") is None


def test_profile_repository_raises_clear_error_for_invalid_delta_schema(
    tmp_path: Path, monkeypatch
) -> None:
    broken_row = ToolProfileRepository._to_persisted_row(
        _profile("v1", "2026-04-13T10:00:00+00:00")
    )
    broken_row.pop("allowed_tools_json")
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.profiles.repository.get_spark_session",
        lambda: FakeSpark([broken_row]),
    )
    repo = ToolProfileRepository(_settings(tmp_path))

    with pytest.raises(ValueError, match="expected schema"):
        repo.load_active("default")


def test_profile_repository_wraps_delta_write_failures(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.profiles.repository.get_spark_session",
        lambda: FakeSpark(),
    )

    def _fail(*args, **kwargs):  # noqa: ANN001, ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.profiles.repository.append_delta_table_record",
        _fail,
    )
    repo = ToolProfileRepository(_settings(tmp_path))

    with pytest.raises(RuntimeError, match="Failed to write tool profile"):
        repo.save(_profile("v1", "2026-04-13T10:00:00+00:00"))
