from __future__ import annotations

from types import SimpleNamespace

from databricks_mcp_agent_hello_world import preflight
from databricks_mcp_agent_hello_world.models import PreflightCheck
from tests.helpers import make_settings


def test_preflight_direct_helper_branches(monkeypatch, tmp_path: Path) -> None:
    settings = make_settings(storage={"local_data_dir": str(tmp_path), "agent_events_table": "main.demo.events"})
    assert preflight._check_llm_endpoint_name(make_settings(llm_endpoint_name="  ")).status == "fail"

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda actual_settings: (_ for _ in ()).throw(RuntimeError("auth failed")),
    )
    failed_client = preflight._check_databricks_client(settings)
    assert failed_client.status == "fail"
    assert failed_client.details["error"] == "auth failed"

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_tool_provider",
        lambda actual_settings: (_ for _ in ()).throw(RuntimeError("bad provider")),
    )
    provider_check, provider = preflight._check_provider_factory(settings)
    assert provider is None
    assert provider_check.status == "fail"

    empty_tool_check, tool_count = preflight._check_tool_registry_nonempty(SimpleNamespace(list_tools=lambda: []))
    assert tool_count == 0
    assert empty_tool_check.status == "fail"
    none_provider_check, tool_count = preflight._check_tool_registry_nonempty(None)
    assert tool_count == 0
    assert none_provider_check.status == "fail"

    exploding_tool_check, tool_count = preflight._check_tool_registry_nonempty(
        SimpleNamespace(list_tools=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    )
    assert tool_count == 0
    assert exploding_tool_check.status == "fail"

    monkeypatch.setattr("databricks_mcp_agent_hello_world.preflight.get_spark_session", lambda: None)
    missing_local_dir = preflight._check_persistence_target_names(
        make_settings(storage={"local_data_dir": "   ", "agent_events_table": "main.demo.events"})
    )
    assert missing_local_dir.status == "fail"

    spark = SimpleNamespace(
        table=lambda name: SimpleNamespace(limit=lambda n: SimpleNamespace(collect=lambda: []))
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.preflight.get_spark_session", lambda: spark)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.storage_table_exists",
        lambda actual_spark, table_name: True,
    )
    reachable = preflight._check_persistence_reachability(settings)
    assert reachable.status == "pass"

    missing_table = preflight._check_persistence_reachability(
        make_settings(storage={"local_data_dir": str(tmp_path), "agent_events_table": "   "})
    )
    assert missing_table.status == "fail"

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.storage_table_exists",
        lambda actual_spark, table_name: (_ for _ in ()).throw(RuntimeError("catalog denied")),
    )
    failed_reachability = preflight._check_persistence_reachability(settings)
    assert failed_reachability.status == "fail"
    assert "catalog denied" in failed_reachability.message

    report = preflight._finalize_preflight_report([PreflightCheck(name="config", status="pass", message="ok")])
    assert report.overall_status == "pass"
    assert report.settings_summary == {}
