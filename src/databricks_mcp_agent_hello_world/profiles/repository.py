from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import ToolProfile, ToolSpec
from ..storage.result_repository import append_delta_table_record
from ..storage.spark_utils import get_spark_session

logger = logging.getLogger(__name__)


class ToolProfileRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.spark = get_spark_session()
        base_dir = Path(settings.storage.local_data_dir)
        self.active_profile_path = base_dir / "active_tool_profile.json"
        self.profile_versions_dir = base_dir / "profiles"

    def save(self, profile: ToolProfile) -> None:
        row = self._to_persisted_row(profile)
        if self.spark is not None:
            table_name = (self.settings.storage.tool_profile_table or "").strip()
            if not table_name:
                raise ValueError("storage.tool_profile_table must be configured when Spark is available.")
            append_delta_table_record(self.spark, table_name, row)
            logger.info(
                "Saved tool profile %s version %s to Delta table %s",
                profile.profile_name,
                profile.profile_version,
                table_name,
            )
            return

        self.active_profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_versions_dir.mkdir(parents=True, exist_ok=True)
        self.active_profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        version_path = self.profile_versions_dir / (
            f"{profile.profile_name}_{profile.profile_version}.json"
        )
        version_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        logger.info(
            "Saved tool profile %s version %s to local fallback storage",
            profile.profile_name,
            profile.profile_version,
        )

    def load_active(self, profile_name: str | None = None) -> ToolProfile | None:
        requested_profile = profile_name or self.settings.active_profile_name
        if self.spark is not None:
            table_name = (self.settings.storage.tool_profile_table or "").strip()
            if not table_name:
                raise ValueError("storage.tool_profile_table must be configured when Spark is available.")
            rows = (
                self.spark.table(table_name)
                .where(f"profile_name = '{requested_profile}'")
                .where("is_active = true")
                .orderBy("created_at", ascending=False)
                .limit(1)
                .collect()
            )
            if not rows:
                return None
            return self._from_persisted_row(rows[0].asDict(recursive=True))

        if self.active_profile_path.exists():
            profile = ToolProfile.model_validate_json(
                self.active_profile_path.read_text(encoding="utf-8")
            )
            if profile.profile_name == requested_profile and profile.is_active:
                return profile
        return None

    def is_table_reachable(self) -> bool:
        if self.spark is None:
            return False
        table_name = (self.settings.storage.tool_profile_table or "").strip()
        if not table_name:
            raise ValueError("storage.tool_profile_table must be configured when Spark is available.")
        self.spark.table(table_name).limit(0).collect()
        return True

    @staticmethod
    def _to_persisted_row(profile: ToolProfile) -> dict[str, Any]:
        return {
            "profile_name": profile.profile_name,
            "profile_version": profile.profile_version,
            "created_at": profile.created_at,
            "inventory_hash": profile.inventory_hash,
            "provider_type": profile.provider_type,
            "llm_endpoint_name": profile.llm_endpoint_name,
            "prompt_version": profile.prompt_version,
            "is_active": profile.is_active,
            "discovered_tools_json": json.dumps(
                [tool.model_dump() for tool in profile.discovered_tools],
                sort_keys=True,
            ),
            "allowed_tools_json": json.dumps(profile.allowed_tools, sort_keys=True),
            "disallowed_tools_json": json.dumps(profile.disallowed_tools, sort_keys=True),
            "justifications_json": json.dumps(profile.justifications, sort_keys=True),
            "audit_report_text": profile.audit_report_text,
            "selection_policy": profile.selection_policy,
        }

    @staticmethod
    def _from_persisted_row(row: dict[str, Any]) -> ToolProfile:
        return ToolProfile(
            profile_name=row["profile_name"],
            profile_version=row["profile_version"],
            created_at=row["created_at"],
            inventory_hash=row["inventory_hash"],
            provider_type=row["provider_type"],
            llm_endpoint_name=row["llm_endpoint_name"],
            prompt_version=row["prompt_version"],
            is_active=bool(row["is_active"]),
            discovered_tools=[
                ToolSpec.model_validate(tool) for tool in json.loads(row["discovered_tools_json"])
            ],
            allowed_tools=list(json.loads(row["allowed_tools_json"])),
            disallowed_tools=list(json.loads(row["disallowed_tools_json"])),
            justifications=dict(json.loads(row["justifications_json"])),
            audit_report_text=row["audit_report_text"],
            selection_policy=row.get("selection_policy", ""),
        )
