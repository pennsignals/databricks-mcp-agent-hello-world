from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import databricks_mcp_agent_hello_world as package_root
from databricks_mcp_agent_hello_world import llm_client, logging_utils
from databricks_mcp_agent_hello_world.app import registry, tools
from databricks_mcp_agent_hello_world.clients import databricks as db_clients
from databricks_mcp_agent_hello_world.commands import (
    _agent_run_exit_code,
    _build_agent_task_request,
    _load_settings_for_command,
    _load_task_payload,
    run_discover_tools_command,
    run_evals_command,
    run_init_storage_command,
    run_preflight_command,
)
from databricks_mcp_agent_hello_world.evals.harness import EvalSetupError
from databricks_mcp_agent_hello_world.models import EvalRunReport, ToolCall
from databricks_mcp_agent_hello_world.providers import base, factory, managed_mcp
from databricks_mcp_agent_hello_world.providers.local_python import LocalPythonToolProvider
from databricks_mcp_agent_hello_world.runner.agent_runner import AgentRunner
from databricks_mcp_agent_hello_world.storage import bootstrap, spark, write
from tests.helpers import make_settings


def test_app_registry_and_tool_errors() -> None:
    assert registry.get_tool_function("get_user_profile") is tools.get_user_profile
    assert len(registry.list_authored_tools()) == len(registry.TOOL_DEFINITIONS)

    with pytest.raises(ValueError, match="unknown setting key"):
        tools.get_workspace_setting("missing")
    with pytest.raises(ValueError, match="summary must not be empty"):
        tools.create_support_ticket("   ")
    with pytest.raises(ValueError, match="invalid severity"):
        tools.create_support_ticket("need help", severity="urgent")
    with pytest.raises(TypeError, match="ranked result score"):
        tools._ranked_result_sort_key({"score": object(), "title": "Demo"})

    assert package_root.__all__ == ["__version__", "run_agent_task", "run_init_storage"]


def test_databricks_client_helpers_cover_all_configuration_paths(monkeypatch) -> None:
    db_clients._cached_config.cache_clear()
    db_clients._cached_workspace_client.cache_clear()
    db_clients._cached_openai_client.cache_clear()

    captured_config_calls: list[dict[str, str]] = []
    captured_workspace_client_configs: list[object] = []
    captured_openai_workspace_clients: list[object] = []

    class FakeConfig:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.host = kwargs.get("host")
            captured_config_calls.append(kwargs)

    class FakeWorkspaceClient:
        def __init__(self, *, config) -> None:
            self.config = config
            captured_workspace_client_configs.append(config)

    class FakeDatabricksOpenAI:
        def __init__(self, *, workspace_client) -> None:
            self.workspace_client = workspace_client
            captured_openai_workspace_clients.append(workspace_client)

    sdk_module = ModuleType("databricks.sdk")
    sdk_module.WorkspaceClient = FakeWorkspaceClient
    sdk_config_module = ModuleType("databricks.sdk.config")
    sdk_config_module.Config = FakeConfig
    openai_module = ModuleType("databricks_openai")
    openai_module.DatabricksOpenAI = FakeDatabricksOpenAI

    monkeypatch.setitem(sys.modules, "databricks.sdk", sdk_module)
    monkeypatch.setitem(sys.modules, "databricks.sdk.config", sdk_config_module)
    monkeypatch.setitem(sys.modules, "databricks_openai", openai_module)

    no_profile_or_host = make_settings(databricks_config_profile=None, workspace_host=None)
    profile_only = make_settings(databricks_config_profile="DEFAULT", workspace_host=None)
    host_only = make_settings(databricks_config_profile=None, workspace_host="https://example.com")
    both = make_settings(databricks_config_profile="DEFAULT", workspace_host="https://example.com")

    assert db_clients._workspace_client_config_kwargs(no_profile_or_host) == {}
    assert db_clients._workspace_client_config_kwargs(profile_only) == {"profile": "DEFAULT"}
    assert db_clients._workspace_client_config_kwargs(host_only) == {"host": "https://example.com"}
    assert db_clients._workspace_client_config_kwargs(both) == {
        "profile": "DEFAULT",
        "host": "https://example.com",
    }

    assert db_clients.get_workspace_client(no_profile_or_host).config.kwargs == {}
    assert db_clients.get_workspace_client(profile_only).config.kwargs == {"profile": "DEFAULT"}
    assert db_clients.get_workspace_client(host_only).config.kwargs == {
        "host": "https://example.com"
    }
    assert db_clients.get_workspace_client(both).config.kwargs == {
        "profile": "DEFAULT",
        "host": "https://example.com",
    }
    assert db_clients.get_openai_client(both).workspace_client.config.kwargs == {
        "profile": "DEFAULT",
        "host": "https://example.com",
    }
    assert len(captured_workspace_client_configs) == 4
    assert captured_openai_workspace_clients


def test_databricks_llm_validates_endpoint_and_passes_optional_tool_choice(monkeypatch) -> None:
    with pytest.raises(ValueError, match="llm_endpoint_name must be configured"):
        llm_client.DatabricksLLM(make_settings(llm_endpoint_name="   "))

    create_calls: list[dict[str, object]] = []

    class FakeChatCompletions:
        def create(self, **kwargs):
            create_calls.append(kwargs)
            return {"ok": True}

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions()))
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.clients.databricks.get_openai_client",
        lambda settings: fake_client,
    )
    llm = llm_client.DatabricksLLM(make_settings(llm_endpoint_name="endpoint-a"))

    assert llm.tool_step([], []) == {"ok": True}
    assert "tool_choice" not in create_calls[0]
    assert llm.tool_step([], [], tool_choice="auto") == {"ok": True}
    assert create_calls[1]["tool_choice"] == "auto"


def test_logging_utils_sets_level_with_and_without_existing_handlers(monkeypatch) -> None:
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    try:
        root_logger.handlers = [logging.StreamHandler()]
        logging_utils.configure_logging("debug")
        assert root_logger.level == logging.DEBUG

        root_logger.handlers = []
        basic_config_calls: list[dict[str, object]] = []
        monkeypatch.setattr(
            logging,
            "basicConfig",
            lambda **kwargs: basic_config_calls.append(kwargs),
        )
        monkeypatch.setenv("LOG_LEVEL", "warning")
        logging_utils.configure_logging()
        assert basic_config_calls[0]["level"] == logging.WARNING
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)


def test_commands_additional_branches(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "workspace-config.yml"
    task_file = tmp_path / "task.json"
    task_file.write_text('{"task_name":"demo","instructions":"hi","payload":{}}', encoding="utf-8")

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_preflight",
        lambda path: SimpleNamespace(overall_status="fail"),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands._load_settings_for_command",
        lambda config_path, command_name, next_step=None: "settings",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.discover_tools",
        lambda settings: {"settings": settings},
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.load_settings",
        lambda path: "settings",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.init_storage",
        lambda settings: SimpleNamespace(exit_code=0, messages=["done"]),
    )

    assert run_preflight_command(str(config_path)).exit_code == 1
    assert run_discover_tools_command(str(config_path)).payload == {"settings": "settings"}
    assert run_init_storage_command(str(config_path)).payload.messages == ["done"]
    assert (
        _load_task_payload(
            task_input_json=None,
            task_input_file=str(task_file),
        )["task_name"]
        == "demo"
    )
    assert (
        _build_agent_task_request(
            {
                "task_name": "demo",
                "instructions": "hi",
                "payload": {},
                "run_id": "run-123",
            },
            command_name="run-agent-task",
        ).run_id
        == "run-123"
    )

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.load_settings",
        lambda path: (_ for _ in ()).throw(FileNotFoundError(path)),
    )
    with pytest.raises(
        RuntimeError,
        match="Create workspace-config.yml and rerun run_agent_task_job",
    ):
        _load_settings_for_command(
            str(config_path),
            "run-agent-task",
            next_step="run_agent_task_job",
        )
    with pytest.raises(RuntimeError, match="Missing config file"):
        _load_settings_for_command(str(config_path), "discover-tools")

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.load_settings",
        lambda path: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(EvalSetupError, match="Unable to load config"):
        run_evals_command(str(config_path))

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.load_settings",
        lambda path: "settings",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_evals",
        lambda settings, scenario_file: (_ for _ in ()).throw(RuntimeError("eval boom")),
    )
    with pytest.raises(EvalSetupError, match="eval boom"):
        run_evals_command(str(config_path))

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.commands.run_evals",
        lambda settings, scenario_file: (_ for _ in ()).throw(EvalSetupError("already wrapped")),
    )
    with pytest.raises(EvalSetupError, match="already wrapped"):
        run_evals_command(str(config_path))

    assert _agent_run_exit_code(SimpleNamespace(status="success")) == 0
    with pytest.raises(ValueError, match="Unsupported agent run status"):
        _agent_run_exit_code(SimpleNamespace(status="blocked"))


def test_eval_harness_additional_branches(tmp_path: Path, monkeypatch) -> None:
    missing_path = tmp_path / "missing.json"

    from databricks_mcp_agent_hello_world.evals import harness

    with pytest.raises(EvalSetupError, match="Scenario file not found"):
        harness.load_eval_scenarios(str(missing_path))

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(EvalSetupError, match="Invalid scenario JSON"):
        harness.load_eval_scenarios(str(invalid_json))

    not_list = tmp_path / "not-list.json"
    not_list.write_text("{}", encoding="utf-8")
    with pytest.raises(EvalSetupError, match="top-level JSON list"):
        harness.load_eval_scenarios(str(not_list))

    invalid_scenario = tmp_path / "invalid-scenario.json"
    invalid_scenario.write_text('[{"scenario_id":"a","description":"x"}]', encoding="utf-8")
    with pytest.raises(EvalSetupError, match="Invalid scenario file"):
        harness.load_eval_scenarios(str(invalid_scenario))

    scenario_dir = tmp_path / "evals"
    scenario_dir.mkdir()
    bad_task = tmp_path / "task.json"
    bad_task.write_text("{", encoding="utf-8")
    scenario_file = scenario_dir / "scenario.json"
    scenario_file.write_text(
        '[{"scenario_id":"a","description":"x","task_input_file":"../task.json"}]',
        encoding="utf-8",
    )
    with pytest.raises(EvalSetupError, match="Invalid task input JSON"):
        harness.load_eval_scenarios(str(scenario_file))

    missing_task_ref = scenario_dir / "missing-task.json"
    missing_task_ref.write_text(
        '[{"scenario_id":"a","description":"x","task_input_file":"../missing-task-input.json"}]',
        encoding="utf-8",
    )
    with pytest.raises(EvalSetupError, match="Task input file not found"):
        harness.load_eval_scenarios(str(missing_task_ref))

    scenario = harness.EvalScenario(
        scenario_id="score",
        description="x",
        task_input=harness.AgentTaskRequest(task_name="demo", instructions="hi"),
        max_tool_calls=0,
        forbidden_output_substrings=["forbidden"],
    )
    run_record = harness.AgentRunRecord(
        run_id="run-1",
        task_name="demo",
        status="success",
        result={
            "final_response": "forbidden output",
            "available_tools": ["tool-a"],
            "tool_calls": [{"tool_name": "tool-a", "status": "ok"}],
        },
    )
    scored = harness._score_scenario(scenario, run_record)
    assert "above_max_tool_calls" in scored.failed_checks
    assert "forbidden_output_substrings_present" in scored.failed_checks

    assert harness._as_string_list("not-a-list") == []
    assert harness._as_trace_list("not-a-list") == []
    assert harness._ordered_unique_tools(
        [
            {"tool_name": "a", "status": "ok"},
            {"tool_name": "a", "status": "ok"},
            {"tool_name": "b", "status": "skipped"},
            {"tool_name": 5, "status": "ok"},
        ],
        statuses={"ok"},
    ) == ["a"]

    scenario = harness.EvalScenario(
        scenario_id="missing-task",
        description="x",
        task_input=harness.AgentTaskRequest(task_name="demo", instructions="hi"),
    )
    scenario = scenario.model_copy(update={"task_input": None, "task_input_file": None})
    with pytest.raises(EvalSetupError, match="missing task_input"):
        harness._require_task_input(scenario)

    report = EvalRunReport(
        scenario_file="scenario.json",
        total_scenarios=0,
        passed_scenarios=0,
        failed_scenarios=0,
        all_passed=True,
        results=[],
    )
    harness._write_latest_eval_report(
        make_settings(storage={"local_data_dir": str(tmp_path)}),
        report,
    )
    saved_report = tmp_path / "evals" / "latest_eval_report.json"
    assert saved_report.exists()


def test_provider_storage_and_runner_support_branches(tmp_path: Path, monkeypatch, caplog) -> None:
    provider = LocalPythonToolProvider(make_settings())
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.providers.local_python.get_tool_function",
        lambda name: (_ for _ in ()).throw(RuntimeError(f"boom: {name}")),
    )
    result = provider.call_tool(
        ToolCall(
            tool_name="get_user_profile",
            arguments={},
            request_id="req-1",
        )
    )
    assert result.status == "error"
    assert result.error == "boom: get_user_profile"

    with pytest.raises(ValueError, match="Unsupported tool_provider_type"):
        factory.get_tool_provider(make_settings(tool_provider_type="something-else"))

    managed_provider = managed_mcp.ManagedMCPToolProvider()
    for method in (
        managed_provider.list_tools,
        managed_provider.inventory_hash,
        lambda: managed_provider.call_tool(ToolCall(tool_name="demo")),
    ):
        with pytest.raises(NotImplementedError, match="not implemented yet"):
            method()

    class DummyProvider(base.ToolProvider):
        provider_type = "dummy"
        provider_id = "dummy"

        def list_tools(self):
            return super().list_tools()

        def inventory_hash(self):
            return super().inventory_hash()

        def call_tool(self, tool_call):
            return super().call_tool(tool_call)

    dummy = DummyProvider()
    with pytest.raises(NotImplementedError):
        dummy.list_tools()
    with pytest.raises(NotImplementedError):
        dummy.inventory_hash()
    with pytest.raises(NotImplementedError):
        dummy.call_tool(ToolCall(tool_name="demo"))

    target = bootstrap.parse_table_name(" main . demo . events ")
    assert target.full_name == "main.demo.events"
    assert target.schema_name == "main.demo"
    with pytest.raises(ValueError, match="fully qualified 3-part name"):
        bootstrap.parse_table_name("main.demo")

    local_dir = tmp_path / "state"
    assert bootstrap.ensure_local_storage_dir(local_dir) is True
    assert bootstrap.ensure_local_storage_dir(local_dir) is False
    (local_dir / write.EVENTS_JSONL_FILE_NAME).mkdir()
    with pytest.raises(ValueError, match="Expected JSONL path to be a file"):
        bootstrap.ensure_local_storage_dir(local_dir)

    assert bootstrap._row_first_value({"catalog": "main"}) == "main"
    with pytest.raises(KeyError):
        bootstrap._row_first_value({})
    assert bootstrap._row_first_value(SimpleNamespace(asDict=lambda: {"schema": "demo"})) == "demo"

    class EmptyMappingRow:
        def asDict(self):
            return {}

        def __getitem__(self, index):
            return "fallback"

    assert bootstrap._row_first_value(EmptyMappingRow()) == "fallback"
    assert bootstrap._row_first_value(("fallback",)) == "fallback"
    assert bootstrap._row_as_dict({}) == {}
    assert bootstrap._row_as_dict(SimpleNamespace(asDict=lambda: ["not", "dict"])) is None
    assert bootstrap.quote_name("a`b") == "`a``b`"
    assert bootstrap.sql_literal("O'Hare") == "O''Hare"
    assert bootstrap.describe_schema([]) == []

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
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: object(),
    )
    with pytest.raises(ValueError, match="storage.agent_events_table must be configured"):
        bootstrap.init_storage(
            make_settings(
                storage={
                    "agent_events_table": "   ",
                    "local_data_dir": str(tmp_path),
                }
            )
        )
    same_schema_spark = SimpleNamespace(
        sql=lambda query: SimpleNamespace(
            collect=lambda: (
                [SimpleNamespace(tableName="events")]
                if query.startswith("SHOW TABLES")
                else [SimpleNamespace()]
            )
        ),
        table=lambda name: SimpleNamespace(schema=SimpleNamespace(fields=[])),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.catalog_exists",
        lambda spark_obj, name: True,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.schema_exists",
        lambda spark_obj, target_obj: True,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.table_exists",
        lambda spark_obj, target_obj: True,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.compare_table_schema",
        lambda spark_obj, target_obj: None,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.get_spark_session",
        lambda: same_schema_spark,
    )
    matched = bootstrap.init_storage(
        make_settings(
            storage={
                "agent_events_table": "main.demo.events",
                "local_data_dir": str(tmp_path),
            }
        )
    )
    assert matched.exit_code == 0
    assert matched.messages == ["Table main.demo.events already exists and matches expected schema"]
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.bootstrap.table_exists",
        lambda spark_obj, target_obj: True,
    )
    assert bootstrap.storage_table_exists(object(), "main.demo.events") is True

    spark._logged_local_fallback = False
    monkeypatch.setitem(sys.modules, "pyspark.sql", ModuleType("pyspark.sql"))
    sys.modules["pyspark.sql"].SparkSession = SimpleNamespace(getActiveSession=lambda: "active")
    assert spark.get_spark_session() == "active"

    builder_calls = []
    sys.modules["pyspark.sql"].SparkSession = SimpleNamespace(
        getActiveSession=lambda: None,
        builder=SimpleNamespace(getOrCreate=lambda: builder_calls.append(True) or "created"),
    )
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "14.x")
    assert spark.get_spark_session() == "created"
    assert builder_calls == [True]

    spark._logged_local_fallback = False
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)
    sys.modules["pyspark.sql"].SparkSession = SimpleNamespace(
        getActiveSession=lambda: (_ for _ in ()).throw(RuntimeError("spark unavailable"))
    )
    with caplog.at_level("INFO"):
        assert spark.get_spark_session() is None
        assert spark.get_spark_session() is None
    assert len([message for message in caplog.messages if "Local mode" in message]) == 1

    assert write._event_rows_jsonl_path(str(tmp_path)).name == "agent_events.jsonl"
    assert (
        write.write_event_rows(
            make_settings(storage={"local_data_dir": str(tmp_path)}),
            [],
        )
        is None
    )

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.write.get_spark_session",
        lambda: object(),
    )
    with pytest.raises(ValueError, match="storage.agent_events_table must be configured"):
        write.write_event_rows(
            make_settings(storage={"agent_events_table": "   ", "local_data_dir": str(tmp_path)}),
            [{"schema_version": "1"}],
        )

    save_calls: list[str] = []

    class FakeWriter:
        def mode(self, value):
            assert value == "append"
            return self

        def saveAsTable(self, table_name):
            save_calls.append(table_name)

    class FakeDataFrame:
        write = FakeWriter()

    class FakeSpark:
        def createDataFrame(self, arrow_table):
            return FakeDataFrame()

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.storage.write.validate_event_rows",
        lambda rows: "arrow-table",
    )
    write._append_delta_event_rows(FakeSpark(), "main.demo.events", [{"schema_version": "1"}])
    assert save_calls == ["main.demo.events"]

    runner = AgentRunner.__new__(AgentRunner)
    runner.provider = SimpleNamespace(
        call_tool=lambda tool_call: {"tool_name": tool_call.tool_name}
    )
    assert AgentRunner._parse_tool_arguments({}) == ({}, None)
    assert AgentRunner._parse_tool_arguments({"a": 1}) == ({"a": 1}, None)
    assert AgentRunner._parse_tool_arguments(5)[1] is not None
    assert AgentRunner._parse_tool_arguments("[]") == (
        {},
        "Tool call arguments must decode to a JSON object.",
    )
    assert AgentRunner._build_result_payload(
        final_response="done",
        discovered_tools=[],
        tool_calls=[],
    ) == {
        "final_response": "done",
        "available_tools": [],
        "available_tools_count": 0,
        "tool_calls": [],
    }
    assert AgentRunner._truncate_excerpt("x" * 600) == "x" * 500
