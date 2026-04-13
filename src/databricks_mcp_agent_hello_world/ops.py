from __future__ import annotations

from pathlib import Path
from typing import Any

from .clients.databricks import get_workspace_client
from .config import (
    Settings,
    build_settings,
    load_dotenv_values,
    load_yaml_config,
)
from .models import DiscoveryReport, PreflightCheck, PreflightReport
from .profiles.compiler import ToolProfileCompiler, build_hello_world_demo_task
from .runner.agent_runner import AgentRunner
from .providers.local_python import LocalPythonToolProvider
from .tooling.runtime import set_runtime_settings


def run_preflight(config_path: str) -> PreflightReport:
    checks: list[PreflightCheck] = []
    raw_config: dict[str, Any] | None = None
    dotenv_values: dict[str, str] = {}
    dotenv_path: str | None = None
    settings: Settings | None = None

    try:
        raw_config = load_yaml_config(config_path)
        checks.append(
            PreflightCheck(
                name="config_file",
                status="pass",
                message="Config file exists and parsed successfully.",
                details={"config_path": str(Path(config_path))},
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            PreflightCheck(
                name="config_file",
                status="fail",
                message=str(exc),
                details={"config_path": str(Path(config_path))},
            )
        )
        return _finalize_preflight_report(checks)

    try:
        dotenv_path, dotenv_values = load_dotenv_values(config_path)
        checks.append(
            PreflightCheck(
                name="dotenv",
                status="pass",
                message=(
                    "Optional .env parsed successfully."
                    if dotenv_path
                    else "No .env file present."
                ),
                details={"dotenv_path": dotenv_path},
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            PreflightCheck(
                name="dotenv",
                status="fail",
                message=str(exc),
                details={"dotenv_path": str(Path(config_path).resolve().parent / ".env")},
            )
        )
        return _finalize_preflight_report(checks)

    settings = build_settings(
        raw_config,
        config_path=config_path,
        dotenv_path=dotenv_path,
        dotenv_values=dotenv_values,
    )
    set_runtime_settings(settings)

    checks.append(_check_databricks_profile(settings))
    checks.append(_check_databricks_client(settings))
    checks.append(_check_llm_endpoint_name(settings))
    checks.append(_check_tool_registry_import())
    checks.append(_check_tool_registry_nonempty())
    checks.append(_check_tool_provider_type(settings))
    checks.append(_check_persistence_targets(settings))

    return _finalize_preflight_report(checks, settings)


def discover_tools(settings: Settings) -> DiscoveryReport:
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()
    return DiscoveryReport(
        provider_type=provider.provider_type,
        tool_count=len(tools),
        provider_id=provider.provider_id,
        inventory_hash=provider.inventory_hash(),
        tools=tools,
        active_profile=None,
    )


def run_hello_world_demo(settings: Settings):
    set_runtime_settings(settings)
    discover_tools(settings)
    compiler = ToolProfileCompiler(settings)
    compiler.compile(build_hello_world_demo_task())
    runner = AgentRunner(settings)
    return runner.run(build_hello_world_demo_task())


def print_json_report(payload: Any) -> None:
    print(payload.model_dump_json(indent=2))


def print_preflight_summary(report: PreflightReport) -> None:
    print(f"Preflight: {report.overall_status}")
    for check in report.checks:
        print(f"- {check.name}: {check.status} - {check.message}")


def print_discovery_report(report: DiscoveryReport) -> None:
    print(f"Provider type: {report.provider_type}")
    print(f"Total tools: {report.tool_count}")
    for tool in report.tools:
        summary = _summarize_input_schema(tool.input_schema)
        print(f"- {tool.tool_name}: {tool.description}")
        print(f"  Input schema: {summary}")


def _check_databricks_profile(settings: Settings) -> PreflightCheck:
    profile = (settings.databricks_cli_profile or "").strip()
    if profile:
        return PreflightCheck(
            name="databricks_profile",
            status="pass",
            message="DATABRICKS_CONFIG_PROFILE resolved successfully.",
            details={"profile": profile},
        )
    return PreflightCheck(
        name="databricks_profile",
        status="fail",
        message="DATABRICKS_CONFIG_PROFILE must be set in workspace-config.yml or .env.",
        details={"profile": settings.databricks_cli_profile},
    )


def _check_databricks_client(settings: Settings) -> PreflightCheck:
    try:
        client = get_workspace_client(settings)
        return PreflightCheck(
            name="databricks_client",
            status="pass",
            message="Databricks client initialized successfully.",
            details={"host": getattr(client.config, "host", None)},
        )
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="databricks_client",
            status="fail",
            message=str(exc),
            details={"profile": settings.databricks_cli_profile},
        )


def _check_llm_endpoint_name(settings: Settings) -> PreflightCheck:
    endpoint_name = settings.llm_endpoint_name.strip()
    if endpoint_name:
        return PreflightCheck(
            name="llm_endpoint_name",
            status="pass",
            message="llm_endpoint_name is present.",
            details={"llm_endpoint_name": endpoint_name},
        )
    return PreflightCheck(
        name="llm_endpoint_name",
        status="fail",
        message="llm_endpoint_name is required.",
    )


def _check_tool_registry_import() -> PreflightCheck:
    try:
        provider = LocalPythonToolProvider()
        return PreflightCheck(
            name="tool_registry_import",
            status="pass",
            message="Local tool registry imported successfully.",
            details={"provider_type": provider.provider_type},
        )
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="tool_registry_import",
            status="fail",
            message=str(exc),
        )


def _check_tool_registry_nonempty() -> PreflightCheck:
    try:
        tools = LocalPythonToolProvider().list_tools()
        if not tools:
            raise ValueError("No tools are registered.")
        return PreflightCheck(
            name="tool_registry_nonempty",
            status="pass",
            message="At least one tool is registered.",
            details={"tool_count": len(tools)},
        )
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="tool_registry_nonempty",
            status="fail",
            message=str(exc),
        )


def _check_tool_provider_type(settings: Settings) -> PreflightCheck:
    if settings.tool_provider_type == "local_python":
        return PreflightCheck(
            name="tool_provider_type",
            status="pass",
            message="tool_provider_type is recognized.",
            details={"tool_provider_type": settings.tool_provider_type},
        )
    return PreflightCheck(
        name="tool_provider_type",
        status="fail",
        message=f"Unsupported tool_provider_type: {settings.tool_provider_type}",
        details={"tool_provider_type": settings.tool_provider_type},
    )


def _check_persistence_targets(settings: Settings) -> PreflightCheck:
    missing = []
    if not (settings.storage.tool_profile_table or "").strip():
        missing.append("tool_profile_table")
    if not (settings.storage.agent_runs_table or "").strip():
        missing.append("agent_runs_table")
    if not (settings.storage.agent_output_table or "").strip():
        missing.append("agent_output_table")

    if missing:
        return PreflightCheck(
            name="persistence_targets",
            status="fail",
            message="Persistence target names are missing.",
            details={"missing": missing},
        )
    return PreflightCheck(
        name="persistence_targets",
        status="pass",
        message="Persistence target names are present.",
        details={
            "tool_profile_table": settings.storage.tool_profile_table,
            "agent_runs_table": settings.storage.agent_runs_table,
            "agent_output_table": settings.storage.agent_output_table,
        },
    )


def _finalize_preflight_report(
    checks: list[PreflightCheck],
    settings: Settings | None = None,
) -> PreflightReport:
    overall = "fail" if any(check.status == "fail" for check in checks) else "pass"
    settings_summary = {}
    if settings is not None:
        settings_summary = {
            "tool_provider_type": settings.tool_provider_type,
            "llm_endpoint_name": settings.llm_endpoint_name,
            "active_profile_name": settings.active_profile_name,
            "databricks_config_profile": settings.databricks_cli_profile,
            "dotenv_path": settings.dotenv_path,
        }
    return PreflightReport(
        overall_status=overall,
        checks=checks,
        settings_summary=settings_summary,
    )


def _summarize_input_schema(schema: dict[str, Any]) -> str:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or not properties:
        return "no parameters"
    required = set(schema.get("required", []))
    parts = []
    for name, value in properties.items():
        value_type = value.get("type", "any") if isinstance(value, dict) else "any"
        suffix = "required" if name in required else "optional"
        parts.append(f"{name}:{value_type} ({suffix})")
    return ", ".join(parts)
