from __future__ import annotations

from pathlib import Path

from .clients.databricks import get_workspace_client
from .config import (
    Settings,
    enabled_tool_sources,
    load_settings,
)
from .models import PreflightCheck, PreflightReport
from .providers.factory import get_tool_provider
from .storage.bootstrap import storage_table_exists
from .storage.spark import require_spark_session


def run_preflight(config_path: str) -> PreflightReport:
    try:
        settings = load_settings(config_path)
    except Exception as exc:
        return build_preflight_config_error_report(config_path, exc)

    return run_preflight_loaded(config_path, settings)


def build_preflight_config_error_report(
    config_path: str,
    exc: Exception,
) -> PreflightReport:
    return _finalize_preflight_report(
        [
            PreflightCheck(
                name="config",
                status="fail",
                message=str(exc),
                details={"config_path": str(Path(config_path))},
            )
        ]
    )


def run_preflight_loaded(config_path: str, settings: Settings) -> PreflightReport:
    checks: list[PreflightCheck] = []

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
            message="Databricks client configuration can be constructed locally.",
            details={"host": getattr(client.config, "host", None)},
        )
    except Exception as exc:
        return PreflightCheck(
            name="databricks_client",
            status="fail",
            message=(
                "Unable to construct Databricks client configuration. For local development, "
                "the recommended path is Databricks CLI auth with "
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
            message=(
                "llm_endpoint_name is configured. Preflight does not verify that this "
                "endpoint exists or that you have serving permissions."
            ),
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
                message="Tool provider can be constructed from local configuration.",
                details={"enabled_tool_sources": enabled_tool_sources(settings)},
            ),
            provider,
        )
    except Exception as exc:
        return (
            PreflightCheck(
                name="provider_factory",
                status="fail",
                message=str(exc),
                details={"enabled_tool_sources": enabled_tool_sources(settings)},
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
                message="At least one tool is discoverable from the configured provider.",
                details={"tool_count": len(tools)},
            ),
            len(tools),
        )
    except Exception as exc:
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

    agent_events_table = (settings.storage.agent_events_table or "").strip()
    storage_mode = "spark_table" if agent_events_table else "local_jsonl"

    return PreflightCheck(
        name="persistence_targets",
        status="pass",
        message=f"Storage mode: {storage_mode}.",
        details={
            "agent_events_table": agent_events_table or None,
            "local_data_dir": local_data_dir,
            "storage_mode": storage_mode,
        },
    )


def _check_persistence_reachability(settings: Settings) -> PreflightCheck:
    table_name = (settings.storage.agent_events_table or "").strip()
    if not table_name:
        local_data_dir = Path(settings.storage.local_data_dir).expanduser()
        return PreflightCheck(
            name="persistence_reachability",
            status="pass",
            message="Storage mode: local_jsonl.",
            details={"local_data_dir": str(local_data_dir), "storage_mode": "local_jsonl"},
        )
    try:
        spark = require_spark_session()
        if not storage_table_exists(spark, table_name):
            return PreflightCheck(
                name="persistence_reachability",
                status="fail",
                message=(
                    "Storage mode: spark_table. The configured Delta event store is not "
                    "initialized yet. "
                    "Run init_storage_job before the first Spark-backed workload run."
                ),
                details={
                    "agent_events_table": table_name,
                    "storage_mode": "spark_table",
                    "next_step": "init_storage_job",
                },
            )
        spark.table(table_name).limit(0).collect()
        return PreflightCheck(
            name="persistence_reachability",
            status="pass",
            message="Storage mode: spark_table. The configured Delta event store is readable.",
            details={"agent_events_table": table_name, "storage_mode": "spark_table"},
        )
    except Exception as exc:
        return PreflightCheck(
            name="persistence_reachability",
            status="fail",
            message=(
                "Unable to read the configured Delta event store. "
                f"Check storage.agent_events_table and schema access: {exc}"
            ),
            details={
                "agent_events_table": table_name,
                "storage_mode": "spark_table",
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
            "enabled_tool_sources": enabled_tool_sources(settings),
            "llm_endpoint_name": settings.llm_endpoint_name,
            "dotenv_path": settings.dotenv_path,
        }
    return PreflightReport(
        overall_status=overall,
        checks=checks,
        settings_summary=settings_summary,
    )
