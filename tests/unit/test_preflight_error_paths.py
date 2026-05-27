from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world import preflight
from databricks_mcp_agent_hello_world.models import PreflightCheck
from tests.helpers import make_settings


def test_preflight_direct_helper_branches(monkeypatch, tmp_path: Path) -> None:
    settings = make_settings(
        storage={
            "local_data_dir": str(tmp_path),
            "agent_events_table": "main.demo.events",
        }
    )
    assert (
        preflight._check_llm_endpoint_name(make_settings(llm_endpoint_name="  ")).status == "fail"
    )
    endpoint_check = preflight._check_llm_endpoint_name(make_settings(llm_endpoint_name="demo"))
    assert endpoint_check.status == "pass"
    assert "configured" in endpoint_check.message
    assert "does not verify" in endpoint_check.message

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda actual_settings: (_ for _ in ()).throw(RuntimeError("auth failed")),
    )
    failed_client = preflight._check_databricks_client(settings)
    assert failed_client.status == "fail"
    assert "construct Databricks client configuration" in failed_client.message
    assert failed_client.details["error"] == "auth failed"

    workspace_client_settings = []
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda actual_settings: (
            workspace_client_settings.append(actual_settings)
            or SimpleNamespace(config=SimpleNamespace(host="https://example.com"))
        ),
    )
    client_check = preflight._check_databricks_client(settings)
    assert client_check.status == "pass"
    assert "can be constructed locally" in client_check.message
    assert workspace_client_settings == [settings]

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_tool_provider",
        lambda actual_settings: (_ for _ in ()).throw(RuntimeError("bad provider")),
    )
    provider_check, provider = preflight._check_provider_factory(settings)
    assert provider is None
    assert provider_check.status == "fail"

    empty_tool_check, tool_count = preflight._check_tool_registry_nonempty(
        SimpleNamespace(list_tools=list)
    )
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

    missing_local_dir = preflight._check_persistence_target_names(
        make_settings(storage={"local_data_dir": "   ", "agent_events_table": "main.demo.events"})
    )
    assert missing_local_dir.status == "fail"

    spark = SimpleNamespace(
        table=lambda name: SimpleNamespace(limit=lambda n: SimpleNamespace(collect=list))
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.require_spark_session",
        lambda: spark,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.storage_table_exists",
        lambda actual_spark, table_name: True,
    )
    reachable = preflight._check_persistence_reachability(settings)
    assert reachable.status == "pass"

    local_reachability = preflight._check_persistence_reachability(
        make_settings(storage={"local_data_dir": str(tmp_path), "agent_events_table": "   "})
    )
    assert local_reachability.status == "pass"
    assert local_reachability.details["storage_mode"] == "local_jsonl"

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.storage_table_exists",
        lambda actual_spark, table_name: (_ for _ in ()).throw(RuntimeError("catalog denied")),
    )
    failed_reachability = preflight._check_persistence_reachability(settings)
    assert failed_reachability.status == "fail"
    assert "catalog denied" in failed_reachability.message

    report = preflight._finalize_preflight_report(
        [PreflightCheck(name="config", status="pass", message="ok")]
    )
    assert report.overall_status == "pass"
    assert report.settings_summary == {}
