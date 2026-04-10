from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pydantic import ValidationError

from ..config import Settings
from ..llm_client import DatabricksLLM
from ..models import FilterDecision, ToolProfile, ToolSpec
from ..providers.local_python import LocalPythonToolProvider
from .repository import ToolProfileRepository

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
SELECTION_POLICY = (
    "Prefer the smallest useful allowlist for a formulaic, "
    "non-interactive Databricks batch workflow."
)


class ToolProfileCompiler:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = LocalPythonToolProvider()
        self.llm = DatabricksLLM(settings)
        self.repo = ToolProfileRepository(settings)

    def compile(self) -> ToolProfile:
        tools = self.provider.list_tools()
        inventory_hash = self.provider.inventory_hash()
        logger.info("Profile compilation starting with %s discovered tools", len(tools))
        logger.info("Discovered tool inventory hash %s", inventory_hash)
        decision = self._filter_tools(tools)
        self._validate_decision(tools, decision)
        audit_report = self._build_audit_report(tools, decision)
        profile = ToolProfile(
            profile_name=self.settings.active_profile_name,
            profile_version=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            inventory_hash=inventory_hash,
            provider_type=self.settings.provider_type,
            provider_id=self.provider.provider_id,
            llm_endpoint_name=self.settings.llm_endpoint_name,
            prompt_version=PROMPT_VERSION,
            discovered_tools=tools,
            allowed_tools=decision.allowed_tools,
            disallowed_tools=decision.disallowed_tools,
            justifications=decision.tool_justifications,
            audit_report_text=audit_report,
            selection_policy=SELECTION_POLICY,
            is_active=True,
        )
        self.repo.save(profile)
        logger.info(
            "Compiled tool profile %s with %s allowed tools.",
            profile.profile_version,
            len(profile.allowed_tools),
        )
        return profile

    def _filter_tools(self, tools: list[ToolSpec]) -> FilterDecision:
        tool_payload = [tool.model_dump() for tool in tools]
        user_prompt = (
            "Mission: compile a governed allowlist for a formulaic "
            "non-interactive Databricks batch agent.\n"
            f"Maximum allowed tools: {self.settings.max_allowed_tools}\n"
            f"Selection policy: {SELECTION_POLICY}\n"
            "Return strict JSON with keys allowed_tools, disallowed_tools, "
            "tool_justifications, summary_reasoning.\n"
            f"Tools:\n{json.dumps(tool_payload, indent=2)}"
        )
        raw = self.llm.complete_json(self.settings.prompts.filter_prompt, user_prompt)
        try:
            return FilterDecision.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"Invalid filter decision from model: {exc}") from exc

    def _validate_decision(self, tools: list[ToolSpec], decision: FilterDecision) -> None:
        discovered_list = [tool.tool_name for tool in tools]
        discovered = set(discovered_list)
        allowed = set(decision.allowed_tools)
        disallowed = set(decision.disallowed_tools)
        if len(allowed) > self.settings.max_allowed_tools:
            raise ValueError("LLM returned more allowed tools than MAX_ALLOWED_TOOLS.")
        if allowed & disallowed:
            raise ValueError("A tool cannot be both allowed and disallowed.")
        if len(decision.allowed_tools) != len(allowed) or len(decision.disallowed_tools) != len(
            disallowed
        ):
            raise ValueError("Duplicate tool names are not allowed in filter decisions.")
        if allowed - discovered or disallowed - discovered:
            raise ValueError("Filter decision returned unknown tool names.")
        if allowed | disallowed != discovered:
            raise ValueError(
                "Every discovered tool must appear exactly once in the allow/disallow lists."
            )
        if set(decision.tool_justifications) != discovered:
            raise ValueError("Every discovered tool must have a justification.")
        for tool_name, reason in decision.tool_justifications.items():
            if not reason.strip():
                raise ValueError(f"Tool {tool_name} is missing a non-empty justification.")

    def _build_audit_report(self, tools: list[ToolSpec], decision: FilterDecision) -> str:
        payload = {
            "profile_name": self.settings.active_profile_name,
            "discovered_tools": [tool.model_dump() for tool in tools],
            "allowed_tools": decision.allowed_tools,
            "disallowed_tools": decision.disallowed_tools,
            "tool_justifications": decision.tool_justifications,
            "summary_reasoning": decision.summary_reasoning,
            "llm_endpoint_name": self.settings.llm_endpoint_name,
        }
        user_prompt = (
            "Group the tools into exactly two lists: allowed and not allowed. "
            "Explain why each tool belongs in its group.\n"
            f"Payload:\n{json.dumps(payload, indent=2)}"
        )
        try:
            return self.llm.complete_text(self.settings.prompts.audit_prompt, user_prompt)
        except Exception:  # noqa: BLE001
            logger.exception("Falling back to deterministic local audit report generation.")
            lines = [
                f"Profile: {self.settings.active_profile_name}",
                f"LLM endpoint: {self.settings.llm_endpoint_name}",
                "",
                "Allowed",
            ]
            for tool_name in decision.allowed_tools:
                lines.append(f"- {tool_name}: {decision.tool_justifications[tool_name]}")
            lines.extend(["", "Not Allowed"])
            for tool_name in decision.disallowed_tools:
                lines.append(f"- {tool_name}: {decision.tool_justifications[tool_name]}")
            return "\n".join(lines)
