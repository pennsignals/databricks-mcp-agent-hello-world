from __future__ import annotations

from pathlib import Path
from typing import Any

from .clients.databricks import get_workspace_client
from .config import Settings, build_settings, load_dotenv_values, load_yaml_config, parse_task_input_file
from .models import AgentTaskRequest, DiscoveryReport, PreflightCheck, PreflightReport
from .profiles.compiler import ToolProfileCompiler
from .profiles.repository import ToolProfileRepository
from .providers.factory import get_tool_provider
from .runner.agent_runner import AgentRunner
from .storage.spark_utils import get_spark_session
from .tooling.runtime import set_runtime_settings


def run_preflight(config_path: str) -> PreflightReport:
    checks: list[PreflightCheck] = []
    raw_config: dict[str, Any] | None = None
    dotenv_values: dict[str, str] = {}
    dotenv_path: str | None = None
    settings: Settings | None = None
    has_active_profile = False
    can_compile_profile = False

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
    provider_check, provider = _check_provider_factory(settings)
    checks.append(provider_check)
    tool_check, tool_count = _check_tool_registry_nonempty(provider)
    checks.append(tool_check)
    checks.append(_check_sql_config(settings))
    checks.append(_check_persistence_target_names(settings))
    checks.append(_check_persistence_reachability(settings))

    repo = ToolProfileRepository(settings)
    active_profile_check, has_active_profile = _check_active_profile(repo, settings)
    checks.append(active_profile_check)

    can_compile_profile = (
        provider is not None
        and tool_count > 0
        and not any(
            check.name in {"llm_endpoint_name", "provider_factory", "persistence_targets", "persistence_reachability"}
            and check.status == "fail"
            for check in checks
        )
    )
    checks.append(
        PreflightCheck(
            name="compile_capability",
            status="pass" if can_compile_profile else "warn",
            message=(
                "Profile compilation is available."
                if can_compile_profile
                else "Profile compilation is not currently available."
            ),
            details={"can_compile_profile": can_compile_profile},
        )
    )

    return _finalize_preflight_report(
        checks,
        settings,
        has_active_profile=has_active_profile,
        can_compile_profile=can_compile_profile,
    )


def discover_tools(settings: Settings) -> DiscoveryReport:
    provider = get_tool_provider(settings)
    tools = provider.list_tools()
    return DiscoveryReport(
        provider_type=provider.provider_type,
        tool_count=len(tools),
        provider_id=provider.provider_id,
        inventory_hash=provider.inventory_hash(),
        tools=tools,
        active_profile=None,
    )


def run_example_task(settings: Settings, task_input_file: str) -> Any:
    set_runtime_settings(settings)
    discover_tools(settings)
    runner = AgentRunner(settings)
    task_input = parse_task_input_file(task_input_file)
    return runner.run(
        AgentTaskRequest(
            task_name=task_input.get("task_name", "example_task"),
            instructions=task_input.get("instructions", "Complete the requested task."),
            payload=task_input.get("payload", task_input),
        )
    )


def print_json_report(payload: Any) -> None:
    print(payload.model_dump_json(indent=2))


def print_preflight_summary(report: PreflightReport) -> None:
    print(f"Preflight: {report.overall_status}")
    print(f"has_active_profile: {report.has_active_profile}")
    print(f"can_compile_profile: {report.can_compile_profile}")
    for check in report.checks:
        print(f"- {check.name}: {check.status} - {check.message}")


def print_discovery_report(report: DiscoveryReport) -> None:
    print(f"Provider type: {report.provider_type}")
    print(f"Total tools: {report.tool_count}")
    for tool in report.tools:
        summary = _summarize_input_schema(tool.input_schema)
        capability_tags = ", ".join(tool.capability_tags) or "-"
        data_domains = ", ".join(tool.data_domains) or "-"
        print(f"- {tool.tool_name}: {tool.description}")
        print(f"  Input schema: {summary}")
        print(f"  Side effect level: {tool.side_effect_level}")
        print(f"  Tags: {capability_tags}")
        print(f"  Domains: {data_domains}")


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


def _check_provider_factory(settings: Settings):
    try:
        provider = get_tool_provider(settings)
        return (
            PreflightCheck(
                name="provider_factory",
                status="pass",
                message="Provider factory resolved successfully.",
                details={"tool_provider_type": settings.tool_provider_type},
            ),
            provider,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            PreflightCheck(
                name="provider_factory",
                status="fail",
                message=str(exc),
                details={"tool_provider_type": settings.tool_provider_type},
            ),
            None,
        )


def _resolve_tool_provider(settings: Settings):
    return get_tool_provider(settings)


def _check_tool_registry_nonempty(provider) -> tuple[PreflightCheck, int]:
    if provider is None:
        return (
            PreflightCheck(
                name="tool_registry_nonempty",
                status="fail",
                message="Tool discovery cannot run because the provider factory failed.",
            ),
            0,
        )
    try:
        tools = provider.list_tools()
        if not tools:
            raise ValueError("No tools are registered.")
        return (
            PreflightCheck(
                name="tool_registry_nonempty",
                status="pass",
                message="At least one tool is registered.",
                details={"tool_count": len(tools)},
            ),
            len(tools),
        )
    except Exception as exc:  # noqa: BLE001
        return (
            PreflightCheck(
                name="tool_registry_nonempty",
                status="fail",
                message=str(exc),
            ),
            0,
        )


def _check_sql_config(settings: Settings) -> PreflightCheck:
    if not settings.sql_config_required:
        return PreflightCheck(
            name="sql_config",
            status="pass",
            message=(
                "Skipped - SQL config is not required for local_python hello-world flow."
            ),
            details={
                "sql_config_required": False,
                "tool_provider_type": settings.tool_provider_type,
            },
        )

    missing = []
    if not (settings.sql.warehouse_id or "").strip():
        missing.append("sql.warehouse_id")
    if not (settings.sql.catalog or "").strip():
        missing.append("sql.catalog")
    if not (settings.sql.schema or "").strip():
        missing.append("sql.schema")
    if missing:
        return PreflightCheck(
            name="sql_config",
            status="fail",
            message="SQL config is required for this provider.",
            details={"missing": missing, "tool_provider_type": settings.tool_provider_type},
        )

    return PreflightCheck(
        name="sql_config",
        status="pass",
        message="SQL config is present.",
        details={
            "sql_config_required": True,
            "tool_provider_type": settings.tool_provider_type,
            "warehouse_id": settings.sql.warehouse_id,
            "catalog": settings.sql.catalog,
            "schema": settings.sql.schema,
        },
    )


def _check_persistence_target_names(settings: Settings) -> PreflightCheck:
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


def _check_persistence_reachability(settings: Settings) -> PreflightCheck:
    spark = get_spark_session()
    if spark is None:
        return PreflightCheck(
            name="persistence_reachability",
            status="pass",
            message="Spark is unavailable, so local fallback storage would be used.",
        )
    try:
        for table_name in (
            settings.storage.tool_profile_table,
            settings.storage.agent_runs_table,
            settings.storage.agent_output_table,
        ):
            if not table_name:
                continue
            spark.table(table_name).limit(0).collect()
        return PreflightCheck(
            name="persistence_reachability",
            status="pass",
            message="Configured Delta persistence targets are reachable in read-only mode.",
        )
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="persistence_reachability",
            status="fail",
            message=(
                "Unable to read one of the configured Delta persistence targets. "
                f"Check the table names and schema: {exc}"
            ),
        )


def _check_active_profile(
    repo: ToolProfileRepository,
    settings: Settings,
) -> tuple[PreflightCheck, bool]:
    try:
        active_profile = repo.load_active(settings.active_profile_name)
        has_active_profile = active_profile is not None
        return (
            PreflightCheck(
                name="active_profile",
                status="pass",
                message=(
                    "An active profile is available."
                    if has_active_profile
                    else "No active profile exists yet. Run compile_tool_profile_job first."
                ),
                details={"has_active_profile": has_active_profile},
            ),
            has_active_profile,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            PreflightCheck(
                name="active_profile",
                status="fail",
                message=str(exc),
            ),
            False,
        )


def _finalize_preflight_report(
    checks: list[PreflightCheck],
    settings: Settings | None = None,
    *,
    has_active_profile: bool = False,
    can_compile_profile: bool = False,
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
        has_active_profile=has_active_profile,
        can_compile_profile=can_compile_profile,
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
