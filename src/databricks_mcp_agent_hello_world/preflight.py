from __future__ import annotations

from pathlib import Path

from .clients.databricks import get_workspace_client
from .config import (
    Settings,
    load_settings_bundle,
)
from .models import PreflightCheck, PreflightReport
from .providers.factory import get_tool_provider
from .storage.bootstrap import storage_table_exists
from .storage.spark import get_spark_session


def run_preflight(config_path: str) -> PreflightReport:
    checks: list[PreflightCheck] = []

    try:
        loaded = load_settings_bundle(config_path)
    except Exception as exc:  # noqa: BLE001
        checks.append(
            PreflightCheck(
                name="config",
                status="fail",
                message=str(exc),
                details={"config_path": str(Path(config_path))},
            )
        )
        return _finalize_preflight_report(checks)

    settings = loaded.settings

    checks.append(
        PreflightCheck(
            name="config",
            status="pass",
            message="Config loaded successfully through the shared runtime validation path.",
            details={
                "config_path": str(Path(settings.config_path or config_path)),
                "dotenv_path": settings.dotenv_path,
            },
        )
    )

    if loaded.warnings:
        checks.append(
            PreflightCheck(
                name="config_warnings",
                status="warn",
                message="Config contains deprecated or unused keys.",
                details={"warnings": loaded.warnings},
            )
        )

    checks.append(_check_databricks_client(settings))
    checks.append(_check_llm_endpoint_name(settings))
    provider_check, provider = _check_provider_factory(settings)
    checks.append(provider_check)
    provider_runtime_status_check = _check_provider_runtime_status(settings)
    if provider_runtime_status_check is not None:
        checks.append(provider_runtime_status_check)
        return _finalize_preflight_report(checks, settings)
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


def _check_provider_runtime_status(settings: Settings) -> PreflightCheck | None:
    if settings.tool_provider_type != "managed_mcp":
        return None
    return PreflightCheck(
        name="provider_runtime_status",
        status="fail",
        message="Configured provider 'managed_mcp' is a placeholder and is not implemented yet.",
        details={
            "tool_provider_type": "managed_mcp",
            "next_step": "Implement managed_mcp or switch to local_python.",
        },
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
        if not storage_table_exists(spark, table_name):
            return PreflightCheck(
                name="persistence_reachability",
                status="fail",
                message=(
                    "Configured Delta event store is not initialized yet. "
                    "Run init_storage_job before the first Spark-backed workload run."
                ),
                details={
                    "agent_events_table": table_name,
                    "next_step": "init_storage_job",
                },
            )
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
