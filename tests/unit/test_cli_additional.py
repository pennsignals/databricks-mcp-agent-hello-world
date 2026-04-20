from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from databricks_mcp_agent_hello_world import cli
from databricks_mcp_agent_hello_world.commands import CommandResult
from databricks_mcp_agent_hello_world.models import EvalRunReport, EvalScenarioResult


@pytest.mark.parametrize(
    ("entrypoint_name", "command_name"),
    [
        ("preflight_entrypoint", "preflight"),
        ("discover_tools_entrypoint", "discover-tools"),
        ("run_agent_task_entrypoint", "run-agent-task"),
        ("run_evals_entrypoint", "run-evals"),
    ],
)
def test_entrypoints_raise_system_exit_with_command_code(
    monkeypatch,
    entrypoint_name: str,
    command_name: str,
) -> None:
    monkeypatch.setattr(cli, "run_named_command", lambda actual: 7 if actual == command_name else 0)

    with pytest.raises(SystemExit) as excinfo:
        getattr(cli, entrypoint_name)()

    assert excinfo.value.code == 7


def test_main_rejects_missing_command(capsys) -> None:
    assert cli.main([]) == 2
    assert "Usage: python -m databricks_mcp_agent_hello_world.cli" in capsys.readouterr().err


def test_main_uses_sys_argv_when_no_explicit_argv(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["python", "preflight", "--config-path", "demo.yml"])
    monkeypatch.setattr(cli, "run_named_command", lambda name, argv=None, prog=None: 0)

    assert cli.main() == 0


def test_run_named_command_returns_parse_error_code_for_invalid_flags() -> None:
    assert cli.run_named_command("run-agent-task", ["--config-path", "demo.yml"]) == 2


def test_run_named_command_handles_non_integer_system_exit(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "run_discover_tools_command",
        lambda config_path: (_ for _ in ()).throw(SystemExit("bad")),
    )

    assert cli.run_named_command("discover-tools", ["--config-path", "demo.yml"]) == 2


def test_build_parser_allows_commands_without_extra_output_flags() -> None:
    args = cli.build_parser("custom-command", prog="custom-command").parse_args([])
    assert args.config_path == "workspace-config.yml"


def test_print_run_summary_omits_final_answer_block_when_empty(capsys) -> None:
    record = SimpleNamespace(
        status="success",
        run_id="run-123",
        task_name="task-a",
        tools_called=[],
        result={"final_response": ""},
    )

    cli.print_run_summary(record)

    output = capsys.readouterr().out
    assert "Final answer:" not in output


def test_print_eval_summary_renders_remaining_failure_modes(capsys) -> None:
    summary = EvalRunReport(
        scenario_file="evals/sample_scenarios.json",
        total_scenarios=1,
        passed_scenarios=0,
        failed_scenarios=1,
        all_passed=False,
        results=[
            EvalScenarioResult(
                scenario_id="failure-matrix",
                passed=False,
                failed_checks=[
                    "forbidden_output_substrings_present",
                    "missing_required_available_tools",
                    "forbidden_available_tools_present",
                    "forbidden_executed_tools_present",
                    "below_min_tool_calls",
                    "above_max_tool_calls",
                    "scenario_execution_error",
                ],
                expected_status="success",
                actual_status=None,
                available_tools=[],
                executed_tools=[],
                tool_call_count=0,
                final_response_excerpt="forbidden output",
                task_name="workspace_onboarding_brief",
                found_forbidden_output_substrings=["secret"],
                missing_required_available_tools=["get_user_profile"],
                present_forbidden_available_tools=["delete_everything"],
                present_forbidden_executed_tools=["delete_everything"],
                expected_min_tool_calls=1,
                expected_max_tool_calls=0,
                scenario_execution_error_message="runner crashed",
            )
        ],
    )

    cli._print_eval_summary(summary)
    output = capsys.readouterr().out

    assert "Forbidden output substrings found: secret" in output
    assert "Missing available tools: get_user_profile" in output
    assert "Available tools: -" in output
    assert "Forbidden available tools present: delete_everything" in output
    assert "Forbidden executed tools present: delete_everything" in output
    assert "Executed tools: -" in output
    assert "Expected minimum tool calls: 1" in output
    assert "Expected maximum tool calls: 0" in output
    assert "Scenario execution failed before scoring." in output
    assert "Error: runner crashed" in output


def test_print_eval_summary_skips_optional_error_and_excerpt_lines_when_absent(capsys) -> None:
    summary = EvalRunReport(
        scenario_file="evals/sample_scenarios.json",
        total_scenarios=1,
        passed_scenarios=0,
        failed_scenarios=1,
        all_passed=False,
        results=[
            EvalScenarioResult(
                scenario_id="scenario-error",
                passed=False,
                failed_checks=["scenario_execution_error"],
                expected_status="success",
                actual_status=None,
                available_tools=[],
                executed_tools=[],
                tool_call_count=0,
                final_response_excerpt="",
                task_name="workspace_onboarding_brief",
                scenario_execution_error_message=None,
            )
        ],
    )

    cli._print_eval_summary(summary)
    output = capsys.readouterr().out

    assert "Scenario execution failed before scoring." in output
    assert "Error:" not in output
    assert "Final response excerpt:" not in output


def test_print_json_report_serializes_model(capsys) -> None:
    cli.print_json_report(
        EvalRunReport(
            scenario_file="evals/sample_scenarios.json",
            total_scenarios=0,
            passed_scenarios=0,
            failed_scenarios=0,
            all_passed=True,
            results=[],
        )
    )

    assert '"all_passed": true' in capsys.readouterr().out


def test_print_discovery_report_and_schema_summary(capsys) -> None:
    report = SimpleNamespace(
        provider_type="local_python",
        tool_count=1,
        tools=[
            SimpleNamespace(
                tool_name="get_user_profile",
                description="Fetch a user",
                input_schema={"type": "object", "properties": {}, "required": []},
                side_effect_level="read_only",
                capability_tags=[],
                data_domains=[],
            )
        ],
    )

    cli.print_discovery_report(report)
    output = capsys.readouterr().out

    assert "Provider type: local_python" in output
    assert "Input schema: no parameters" in output
    assert (
        cli._summarize_input_schema(
            {
                "properties": {
                    "query": {"type": "string"},
                    "limit": "not-a-dict",
                },
                "required": ["query"],
            }
        )
        == "query:string (required), limit:any (optional)"
    )


def test_run_command_helpers_delegate_to_command_layer(monkeypatch) -> None:
    args = SimpleNamespace(
        config_path="demo.yml",
        task_input_json="{}",
        task_input_file=None,
        scenario_file="evals/custom.json",
    )
    preflight_result = CommandResult(exit_code=0, payload={})
    discover_result = CommandResult(exit_code=0, payload={})
    run_task_result = CommandResult(exit_code=0, payload={})
    evals_result = CommandResult(exit_code=0, payload={})

    monkeypatch.setattr(
        cli,
        "run_preflight_command",
        lambda path: preflight_result if path == "demo.yml" else None,
    )
    monkeypatch.setattr(
        cli,
        "run_discover_tools_command",
        lambda path: discover_result if path == "demo.yml" else None,
    )
    monkeypatch.setattr(
        cli,
        "run_agent_task_command",
        lambda path, *, task_input_json, task_input_file: (
            run_task_result
            if (path, task_input_json, task_input_file) == ("demo.yml", "{}", None)
            else None
        ),
    )
    monkeypatch.setattr(
        cli,
        "run_evals_command",
        lambda path, *, scenario_file: (
            evals_result if (path, scenario_file) == ("demo.yml", "evals/custom.json") else None
        ),
    )

    assert cli._run_preflight(args) is preflight_result
    assert cli._run_discover_tools(args) is discover_result
    assert cli._run_agent_task(args) is run_task_result
    assert cli._run_evals(args) is evals_result
