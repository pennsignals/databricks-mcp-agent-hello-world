from pathlib import Path
from types import SimpleNamespace

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
    newer = _profile("v2", "2026-04-13T11:00:00+00:00")
    older = _profile("v1", "2026-04-13T10:00:00+00:00")

    class FakeRow:
        def __init__(self, payload):
            self.payload = payload

        def asDict(self, recursive=True):
            return self.payload

    class FakeFrame:
        def __init__(self, rows):
            self.rows = rows

        def where(self, *args, **kwargs):
            return self

        def orderBy(self, *args, **kwargs):
            self.rows = sorted(self.rows, key=lambda row: row["created_at"], reverse=True)
            return self

        def limit(self, n):
            self.rows = self.rows[:n]
            return self

        def collect(self):
            return [FakeRow(row) for row in self.rows]

    class FakeSpark:
        def __init__(self, rows):
            self.rows = rows

        def table(self, table_name):
            return FakeFrame(self.rows)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.profiles.repository.get_spark_session",
        lambda: FakeSpark(
            [
                ToolProfileRepository._to_persisted_row(older),
                ToolProfileRepository._to_persisted_row(newer),
            ]
        ),
    )
    repo = ToolProfileRepository(_settings(tmp_path))

    loaded = repo.load_active("default")

    assert loaded.profile_version == "v2"
    assert loaded.created_at == newer.created_at


def test_profile_repository_does_not_silently_fall_back_to_local_when_spark_exists(
    tmp_path: Path, monkeypatch
) -> None:
    local_profile = _profile("local-v1", "2026-04-13T10:00:00+00:00")
    local_path = tmp_path / "active_tool_profile.json"
    local_path.write_text(local_profile.model_dump_json(), encoding="utf-8")

    class FakeFrame:
        def where(self, *args, **kwargs):
            return self

        def orderBy(self, *args, **kwargs):
            return self

        def limit(self, n):
            return self

        def collect(self):
            return []

    class FakeSpark:
        def table(self, table_name):
            return FakeFrame()

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.profiles.repository.get_spark_session",
        lambda: FakeSpark(),
    )
    repo = ToolProfileRepository(_settings(tmp_path))

    assert repo.load_active("default") is None
