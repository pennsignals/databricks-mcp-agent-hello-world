from __future__ import annotations

from types import SimpleNamespace

from databricks_mcp_agent_hello_world.cli import (
    _print_eval_summary,
    build_parser,
    print_run_summary,
    run_named_command,
)
from databricks_mcp_agent_hello_world.commands import CommandResult
from databricks_mcp_agent_hello_world.evals.harness import EvalSetupError
from databricks_mcp_agent_hello_world.models import (
    DiscoveryReport,
    EvalRunReport,
    EvalScenarioResult,
    PreflightReport,
)


def test_parsers_accept_supported_flags() -> None:
    preflight_args = build_parser("preflight", prog="preflight").parse_args([])
    discover_args = build_parser("discover-tools", prog="discover-tools").parse_args([])
    run_task_args = build_parser("run-agent-task", prog="run-agent-task").parse_args(
        ["--task-input-json", "{}"]
    )
    run_evals_args = build_parser("run-evals", prog="run-evals").parse_args([])

    assert preflight_args.config_path == "workspace-config.yml"
    assert discover_args.output == "text"
    assert run_task_args.task_input_json == "{}"
    assert run_evals_args.scenario_file == "evals/sample_scenarios.json"


def test_main_rejects_unknown_command(capsys) -> None:
    from databricks_mcp_agent_hello_world.cli import main

    exit_code = main(["not-a-real-command"])
    output = capsys.readouterr().err

    assert exit_code == 2
    assert "not-a-real-command" in output
    assert "Expected one of" in output


def test_run_named_command_renders_text_summary_for_preflight(monkeypatch) -> None:
    recorded: dict[str, object] = {}
    payload = PreflightReport(overall_status="pass", checks=[], settings_summary={})

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_preflight_command",
        lambda config_path: (
            recorded.update({"config_path": config_path})
            or CommandResult(exit_code=0, payload=payload)
        ),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.print_preflight_summary",
        lambda report: recorded.update({"rendered": report}),
    )

    exit_code = run_named_command("preflight", ["--config-path", "custom.yml"])

    assert exit_code == 0
    assert recorded == {"config_path": "custom.yml", "rendered": payload}


def test_run_named_command_renders_json_for_discovery(monkeypatch, capsys) -> None:
    payload = DiscoveryReport(
        provider_type="local_python",
        tool_count=0,
        provider_id="builtin_tools",
        inventory_hash="hash",
        tools=[],
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_discover_tools_command",
        lambda config_path: CommandResult(exit_code=0, payload=payload),
    )

    exit_code = run_named_command(
        "discover-tools",
        ["--config-path", "custom.yml", "--output", "json"],
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"provider_type": "local_python"' in output
    assert '"tool_count": 0' in output


def test_run_named_command_maps_eval_setup_error_to_stderr(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_evals_command",
        lambda config_path, *, scenario_file="evals/sample_scenarios.json": (_ for _ in ()).throw(
            EvalSetupError("auth failed")
        ),
    )

    exit_code = run_named_command("run-evals", ["--config-path", "custom.yml"])

    assert exit_code == 1
    assert "auth failed" in capsys.readouterr().err


def test_run_named_command_maps_generic_exception_to_stderr(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_discover_tools_command",
        lambda config_path: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    exit_code = run_named_command("discover-tools", ["--config-path", "custom.yml"])

    assert exit_code == 1
    assert "boom" in capsys.readouterr().err


def test_print_run_summary_prints_status_and_final_answer(capsys) -> None:
    record = SimpleNamespace(
        status="success",
        run_id="run-123",
        task_name="task-a",
        tools_called=[{"tool_name": "alpha"}],
        result={"final_response": "All set"},
    )

    print_run_summary(record)
    output = capsys.readouterr().out

    assert "Run status: success" in output
    assert "Tools called: 1" in output
    assert "Final answer:" in output
    assert "All set" in output


def test_print_eval_summary_renders_detailed_failure_block(capsys) -> None:
    summary = EvalRunReport(
        scenario_file="evals/sample_scenarios.json",
        total_scenarios=1,
        passed_scenarios=0,
        failed_scenarios=1,
        all_passed=False,
        results=[
            EvalScenarioResult(
                scenario_id="onboarding_happy_path",
                passed=False,
                failed_checks=[
                    "missing_required_output_substrings",
                    "missing_required_executed_tools",
                    "status_mismatch",
                    "missing_required_result_keys",
                ],
                expected_status="success",
                actual_status="error",
                available_tools=["get_user_profile", "search_onboarding_docs"],
                executed_tools=["get_user_profile"],
                tool_call_count=1,
                final_response_excerpt="Grace Hopper uses python3.12 -m venv plus pip.",
                task_name="workspace_onboarding_brief",
                run_record_id="run-123",
                missing_required_output_substrings=["Ada Lovelace"],
                missing_required_executed_tools=["list_recent_job_runs"],
                missing_required_result_keys=["summary_markdown"],
                actual_result_keys=["available_tools", "final_response", "tool_calls"],
            )
        ],
    )

    _print_eval_summary(summary)
    output = capsys.readouterr().out

    assert "FAIL onboarding_happy_path" in output
    assert (
        "Checks failed: missing_required_output_substrings, "
        "missing_required_executed_tools, status_mismatch, "
        "missing_required_result_keys" in output
    )
    assert "Task name: workspace_onboarding_brief" in output
    assert "Run id: run-123" in output
    assert "Expected status: success" in output
    assert "Actual status: error" in output
    assert "Missing output substrings: Ada Lovelace" in output
    assert "Missing executed tools: list_recent_job_runs" in output
    assert "Executed tools: get_user_profile" in output
    assert "Missing result keys: summary_markdown" in output
    assert "Actual result keys: available_tools, final_response, tool_calls" in output
    assert "Final response excerpt: Grace Hopper uses python3.12 -m venv plus pip." in output
    assert "Passed 0/1 scenarios" in output


def test_print_eval_summary_keeps_pass_output_concise(capsys) -> None:
    summary = EvalRunReport(
        scenario_file="evals/sample_scenarios.json",
        total_scenarios=1,
        passed_scenarios=1,
        failed_scenarios=0,
        all_passed=True,
        results=[
            EvalScenarioResult(
                scenario_id="happy",
                passed=True,
                failed_checks=[],
                expected_status="success",
                task_name="workspace_onboarding_brief",
            )
        ],
    )

    _print_eval_summary(summary)
    output = capsys.readouterr().out

    assert output == "PASS happy\nPassed 1/1 scenarios\n"
