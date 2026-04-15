from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from pydantic import ValidationError

from ..config import Settings
from ..llm_client import DatabricksLLM
from ..models import (
    AgentTaskRequest,
    CompileToolProfileResult,
    FilterDecision,
    ToolProfile,
    ToolSpec,
)
from ..providers.factory import get_tool_provider
from .repository import ToolProfileRepository

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
SELECTION_POLICY = (
    "Prefer the smallest useful allowlist for the supplied task in a "
    "non-interactive Databricks batch workflow."
)


class ToolProfileCompiler:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = get_tool_provider(settings)
        self.llm = DatabricksLLM(settings)
        self.repo = ToolProfileRepository(settings)

    def compile(
        self,
        task: AgentTaskRequest,
        *,
        force_refresh: bool = False,
    ) -> CompileToolProfileResult:
        tools = self.provider.list_tools()
        inventory_hash = self.provider.inventory_hash()
        compile_task_hash = self._compile_task_hash(task)
        compile_task_summary = self._compile_task_summary(task)
        try:
            active_profile = self.repo.load_active(self.settings.active_profile_name)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Unable to load active tool profile for profile {self.settings.active_profile_name!r}: {exc}"
            ) from exc
        logger.info("Profile compilation starting with %s discovered tools", len(tools))
        logger.info("Discovered tool inventory hash %s", inventory_hash)
        if (
            active_profile
            and active_profile.profile_name == self.settings.active_profile_name
            and active_profile.inventory_hash == inventory_hash
            and active_profile.compile_task_hash == compile_task_hash
            and active_profile.prompt_version == PROMPT_VERSION
            and not force_refresh
        ):
            logger.info(
                "Reusing active tool profile %s version %s",
                active_profile.profile_name,
                active_profile.profile_version,
            )
            return CompileToolProfileResult(profile=active_profile, reused_existing=True)

        decision = self._filter_tools(task, tools)
        self._validate_decision(tools, decision)
        audit_report = self._build_audit_report(
            task,
            tools,
            decision,
            compile_task_hash=compile_task_hash,
            compile_task_summary=compile_task_summary,
        )
        profile = ToolProfile(
            profile_name=self.settings.active_profile_name,
            profile_version=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"),
            inventory_hash=inventory_hash,
            provider_type=self.settings.provider_type,
            llm_endpoint_name=self.settings.llm_endpoint_name,
            prompt_version=PROMPT_VERSION,
            compile_task_name=task.task_name,
            compile_task_hash=compile_task_hash,
            compile_task_summary=compile_task_summary,
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
        return CompileToolProfileResult(profile=profile, reused_existing=False)

    def _filter_tools(self, task: AgentTaskRequest, tools: list[ToolSpec]) -> FilterDecision:
        """Delegate tool subset selection to the LLM and validate structure only.

        Python assembles task context, tool schemas, and descriptive metadata.
        The model alone chooses allowed_tools and disallowed_tools. Python does
        not prefilter, score, or rank tools before or after the model call.
        """

        user_prompt = json.dumps(
            {
                "task_name": task.task_name,
                "instructions": task.instructions,
                "payload": task.payload,
                "max_allowed_tools": self.settings.max_allowed_tools,
                "selection_policy": SELECTION_POLICY,
                "discovered_tools": [self._tool_prompt_payload(tool) for tool in tools],
            },
            indent=2,
            sort_keys=True,
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

    def _build_audit_report(
        self,
        task: AgentTaskRequest,
        tools: list[ToolSpec],
        decision: FilterDecision,
        *,
        compile_task_hash: str,
        compile_task_summary: str,
    ) -> str:
        payload = {
            "profile_name": self.settings.active_profile_name,
            "task_name": task.task_name,
            "instructions": task.instructions,
            "payload": task.payload,
            "compile_task_name": task.task_name,
            "compile_task_hash": compile_task_hash,
            "compile_task_summary": compile_task_summary,
            "discovered_tools": [self._tool_prompt_payload(tool) for tool in tools],
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
                f"Compile task: {task.task_name}",
                f"Compile task hash: {compile_task_hash}",
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

    @staticmethod
    def _tool_prompt_payload(tool: ToolSpec) -> dict[str, object]:
        return {
            "tool_name": tool.tool_name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "capability_tags": list(tool.capability_tags),
            "side_effect_level": tool.side_effect_level,
            "data_domains": list(tool.data_domains),
            "example_uses": list(tool.example_uses),
        }

    @staticmethod
    def _compile_task_hash(task: AgentTaskRequest) -> str:
        semantic_task = {
            "task_name": task.task_name,
            "instructions": task.instructions,
            "payload": task.payload,
        }
        canonical_json = json.dumps(
            semantic_task,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @staticmethod
    def _compile_task_summary(task: AgentTaskRequest) -> str:
        return f"{task.task_name}: {task.instructions}"[:240]
