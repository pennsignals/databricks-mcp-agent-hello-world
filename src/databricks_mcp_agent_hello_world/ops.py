from __future__ import annotations

import logging
from pathlib import Path

from databricks.sdk.config import Config

from .clients.databricks import DatabricksWorkspaceGateway
from .config import Settings
from .models import DiscoveryReport, PreflightCheck, PreflightReport
from .profiles.repository import ToolProfileRepository
from .providers.local_python import LocalPythonToolProvider
from .tooling.runtime import set_runtime_settings

logger = logging.getLogger(__name__)


def run_preflight(settings: Settings) -> PreflightReport:
    checks: list[PreflightCheck] = []
    provider = LocalPythonToolProvider()
    set_runtime_settings(settings)

    checks.append(
        PreflightCheck(
            name="config_load",
            status="pass",
            message="Configuration loaded successfully.",
            details={"config_path": settings.config_path, "dotenv_path": settings.dotenv_path},
        )
    )

    checks.append(_check_auth_mode(settings))
    checks.append(_check_prompt_files(settings))
    checks.append(_check_tool_registry(provider))
    checks.append(_check_persistence_targets(settings))
    checks.append(_check_active_profile(settings))
    checks.append(_check_databricks_endpoint(settings))

    overall = "fail" if any(check.status == "fail" for check in checks) else "pass"
    return PreflightReport(
        overall_status=overall,
        checks=checks,
        settings_summary={
            "provider_type": settings.provider_type,
            "llm_endpoint_name": settings.llm_endpoint_name,
            "active_profile_name": settings.active_profile_name,
            "auth_mode": settings.auth_mode,
            "tool_backend_mode": settings.sql.backend_mode,
            "dotenv_path": settings.dotenv_path,
        },
    )


def discover_tools(settings: Settings, include_profile: bool = True) -> DiscoveryReport:
    provider = LocalPythonToolProvider()
    tools = provider.list_tools()
    active_profile = ToolProfileRepository(settings).load_active() if include_profile else None
    return DiscoveryReport(
        provider_type=provider.provider_type,
        provider_id=provider.provider_id,
        inventory_hash=provider.inventory_hash(),
        tools=tools,
        active_profile=active_profile,
    )


def _check_auth_mode(settings: Settings) -> PreflightCheck:
    details = {
        "auth_mode": settings.auth_mode,
        "profile": settings.databricks_cli_profile,
        "workspace_host": settings.workspace_host,
    }
    try:
        kwargs = {}
        if settings.databricks_cli_profile:
            kwargs["profile"] = settings.databricks_cli_profile
        if settings.workspace_host:
            kwargs["host"] = settings.workspace_host
        Config(**kwargs)
        return PreflightCheck(
            name="auth_mode",
            status="pass",
            message="Databricks auth configuration is coherent.",
            details=details,
        )
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="auth_mode",
            status="fail",
            message=str(exc),
            details=details,
        )


def _check_prompt_files(settings: Settings) -> PreflightCheck:
    prompt_paths = [
        settings.prompts.filter_prompt_path,
        settings.prompts.audit_prompt_path,
        settings.prompts.agent_system_prompt_path,
    ]
    missing = [path for path in prompt_paths if not Path(path).exists()]
    if missing:
        return PreflightCheck(
            name="prompt_files",
            status="fail",
            message="One or more prompt files are missing.",
            details={"missing": missing},
        )
    return PreflightCheck(
        name="prompt_files",
        status="pass",
        message="Prompt files are present.",
        details={"paths": prompt_paths},
    )


def _check_tool_registry(provider: LocalPythonToolProvider) -> PreflightCheck:
    try:
        tools = provider.list_tools()
        if not tools:
            raise ValueError("No tools were discovered.")
        return PreflightCheck(
            name="tool_registry",
            status="pass",
            message="Local tool registry loaded successfully.",
            details={
                "tool_count": len(tools),
                "inventory_hash": provider.inventory_hash(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="tool_registry",
            status="fail",
            message=str(exc),
        )


def _check_persistence_targets(settings: Settings) -> PreflightCheck:
    missing = []
    if not settings.storage.tool_profiles_table:
        missing.append("TOOL_PROFILE_TABLE")
    if not settings.storage.agent_runs_table:
        missing.append("AGENT_RUNS_TABLE")
    if not settings.storage.agent_outputs_table:
        missing.append("AGENT_OUTPUT_TABLE")
    status = "pass" if not missing else "fail"
    return PreflightCheck(
        name="persistence_targets",
        status=status,
        message=(
            "Persistence targets are configured."
            if not missing
            else "Missing persistence target settings."
        ),
        details={"missing": missing},
    )


def _check_active_profile(settings: Settings) -> PreflightCheck:
    repo = ToolProfileRepository(settings)
    active = repo.load_active()
    if active:
        return PreflightCheck(
            name="active_profile",
            status="pass",
            message="Active tool profile exists.",
            details={
                "profile_name": active.profile_name,
                "profile_version": active.profile_version,
            },
        )
    return PreflightCheck(
        name="active_profile",
        status="warn",
        message="No active tool profile found; compile_tool_profile can be run.",
        details={"profile_name": settings.active_profile_name},
    )


def _check_databricks_endpoint(settings: Settings) -> PreflightCheck:
    try:
        gateway = DatabricksWorkspaceGateway(settings)
        endpoint = gateway.get_serving_endpoint()
        return PreflightCheck(
            name="llm_endpoint",
            status="pass",
            message="Configured LLM endpoint is reachable.",
            details={"endpoint": endpoint.get("name", settings.llm_endpoint_name)},
        )
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="llm_endpoint",
            status="fail",
            message=str(exc),
            details={"endpoint_name": settings.llm_endpoint_name},
        )


def print_json_report(payload) -> None:
    print(payload.model_dump_json(indent=2))


def print_preflight_summary(report: PreflightReport) -> None:
    for check in report.checks:
        logger.info(
            "preflight check=%s status=%s message=%s",
            check.name,
            check.status,
            check.message,
        )
    print_json_report(report)


def print_discovery_report(report: DiscoveryReport) -> None:
    logger.info(
        "tool discovery provider=%s tool_count=%s inventory_hash=%s",
        report.provider_type,
        len(report.tools),
        report.inventory_hash,
    )
    print(report.model_dump_json(indent=2))
