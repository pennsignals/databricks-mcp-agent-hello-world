from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import Settings
from ..models import ToolProfile, ToolProfileRecord, ToolSpec
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
            try:
                append_delta_table_record(self.spark, table_name, row)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Failed to write tool profile "
                    f"{profile.profile_name!r} version {profile.profile_version!r} "
                    f"to Delta table {table_name!r}: {exc}"
                ) from exc
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
            try:
                frame = self.spark.table(table_name)
            except Exception as exc:  # noqa: BLE001
                if self._is_missing_table_error(exc):
                    return None
                raise RuntimeError(
                    f"Unable to read active tool profile from Delta table {table_name!r}: {exc}"
                ) from exc
            try:
                rows = (
                    frame.where(f"profile_name = '{self._escape_sql_literal(requested_profile)}'")
                    .where("is_active = true")
                    .orderBy("created_at", "profile_version", ascending=False)
                    .limit(1)
                    .collect()
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Delta tool profile table "
                    f"{table_name!r} has an invalid schema or cannot be queried: {exc}"
                ) from exc
            if not rows:
                return None
            try:
                return self._from_persisted_row(rows[0].asDict(recursive=True))
            except ValueError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Delta table {table_name!r} does not match the expected tool profile schema: {exc}"
                ) from exc

        if self.active_profile_path.exists():
            try:
                profile = ToolProfile.model_validate_json(
                    self.active_profile_path.read_text(encoding="utf-8")
                )
            except ValidationError as exc:
                raise ValueError(
                    f"Invalid local tool profile cache at {self.active_profile_path}: {exc}"
                ) from exc
            if profile.profile_name == requested_profile and profile.is_active:
                return profile
        return None

    def is_table_reachable(self) -> bool:
        if self.spark is None:
            return False
        table_name = (self.settings.storage.tool_profile_table or "").strip()
        if not table_name:
            raise ValueError("storage.tool_profile_table must be configured when Spark is available.")
        try:
            self.spark.table(table_name).limit(0).collect()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Unable to read Delta table {table_name!r}: {exc}") from exc
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
        try:
            persisted = ToolProfileRecord.model_validate(row)
        except ValidationError as exc:
            raise ValueError(
                "Delta tool profile table does not match the expected schema. "
                "Required columns include profile_name, profile_version, inventory_hash, "
                "provider_type, llm_endpoint_name, prompt_version, is_active, created_at, "
                "selection_policy, audit_report_text, discovered_tools_json, "
                "allowed_tools_json, disallowed_tools_json, and justifications_json."
            ) from exc

        try:
            discovered_tools = [
                ToolSpec.model_validate(tool)
                for tool in json.loads(persisted.discovered_tools_json)
            ]
            allowed_tools = list(json.loads(persisted.allowed_tools_json))
            disallowed_tools = list(json.loads(persisted.disallowed_tools_json))
            justifications = dict(json.loads(persisted.justifications_json))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Delta tool profile row contains invalid serialized tool metadata "
                f"for profile {persisted.profile_name!r} version {persisted.profile_version!r}."
            ) from exc

        return ToolProfile(
            profile_name=persisted.profile_name,
            profile_version=persisted.profile_version,
            created_at=persisted.created_at,
            inventory_hash=persisted.inventory_hash,
            provider_type=persisted.provider_type,
            llm_endpoint_name=persisted.llm_endpoint_name,
            prompt_version=persisted.prompt_version,
            is_active=bool(persisted.is_active),
            discovered_tools=discovered_tools,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
            justifications=justifications,
            audit_report_text=persisted.audit_report_text,
            selection_policy=persisted.selection_policy,
        )

    @staticmethod
    def _escape_sql_literal(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _is_missing_table_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "table or view not found" in message or "not found" in message
