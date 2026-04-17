from __future__ import annotations

from pathlib import Path

from .clients.databricks import get_workspace_client
from .config import (
    Settings,
    build_settings,
    collect_config_warnings,
    collect_dotenv_warnings,
    load_dotenv_values,
    load_yaml_config,
    resolve_deprecated_config_aliases,
)
from .models import PreflightCheck, PreflightReport
from .providers.factory import get_tool_provider
from .storage.spark import get_spark_session


def run_preflight(config_path: str) -> PreflightReport:
    checks: list[PreflightCheck] = []

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
                message="Optional .env parsed successfully."
                if dotenv_path
                else "No .env file present.",
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

    config_warnings = collect_config_warnings(raw_config) + collect_dotenv_warnings(dotenv_values)
    if config_warnings:
        checks.append(
            PreflightCheck(
                name="config_warnings",
                status="warn",
                message="Config contains deprecated or unused keys.",
                details={"warnings": config_warnings},
            )
        )

    settings = build_settings(
        resolve_deprecated_config_aliases(raw_config),
        config_path=config_path,
        dotenv_path=dotenv_path,
        dotenv_values=dotenv_values,
    )

    checks.append(_check_databricks_client(settings))
    checks.append(_check_llm_endpoint_name(settings))
    provider_check, provider = _check_provider_factory(settings)
    checks.append(provider_check)
    tool_check, _ = _check_tool_registry_nonempty(provider)
    checks.append(tool_check)
    checks.append(_check_persistence_target_names(settings))
    checks.append(_check_persistence_reachability(settings))

    return _finalize_preflight_report(checks, settings)


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
            message=(
                "Unable to initialize Databricks client. For local development, the "
                "recommended path is Databricks CLI auth with "
                "`DATABRICKS_CONFIG_PROFILE` pointing to a valid profile in "
                "`~/.databrickscfg`."
            ),
            details={"error": str(exc)},
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


def _check_persistence_target_names(settings: Settings) -> PreflightCheck:
    local_data_dir = (settings.storage.local_data_dir or "").strip()
    if not local_data_dir:
        return PreflightCheck(
            name="persistence_targets",
            status="fail",
            message="Local persistence configuration is missing.",
            details={"missing": ["local_data_dir"]},
        )

    spark = get_spark_session()
    agent_events_table = (settings.storage.agent_events_table or "").strip()
    if spark is not None and not agent_events_table:
        return PreflightCheck(
            name="persistence_targets",
            status="fail",
            message="agent_events_table is required when Spark is available.",
            details={"missing": ["agent_events_table"], "local_data_dir": local_data_dir},
        )

    return PreflightCheck(
        name="persistence_targets",
        status="pass",
        message="Persistence targets are configured for the active runtime.",
        details={
            "agent_events_table": agent_events_table or None,
            "local_data_dir": local_data_dir,
            "spark_available": spark is not None,
        },
    )


def _check_persistence_reachability(settings: Settings) -> PreflightCheck:
    spark = get_spark_session()
    if spark is None:
        local_data_dir = Path(settings.storage.local_data_dir).expanduser()
        return PreflightCheck(
            name="persistence_reachability",
            status="pass",
            message="Spark is unavailable, so local JSONL event-log storage would be used.",
            details={"local_data_dir": str(local_data_dir)},
        )
    try:
        table_name = (settings.storage.agent_events_table or "").strip()
        if not table_name:
            raise ValueError("agent_events_table is missing.")
        spark.table(table_name).limit(0).collect()
        return PreflightCheck(
            name="persistence_reachability",
            status="pass",
            message="Configured Delta event store is reachable in read-only mode.",
            details={"agent_events_table": table_name},
        )
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="persistence_reachability",
            status="fail",
            message=(
                "Unable to read the configured Delta event store. "
                f"Check storage.agent_events_table and schema access: {exc}"
            ),
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
            "dotenv_path": settings.dotenv_path,
        }
    return PreflightReport(
        overall_status=overall,
        checks=checks,
        settings_summary=settings_summary,
    )
