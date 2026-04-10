from __future__ import annotations

import logging
from pathlib import Path

from ..config import Settings
from ..models import ToolProfile
from ..storage.result_repository import DeltaOrLocalRepository
from ..storage.spark_utils import get_spark_session

logger = logging.getLogger(__name__)


class ToolProfileRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.spark = get_spark_session()
        self.repo = DeltaOrLocalRepository(self.spark, settings.storage.local_data_dir)
        base_dir = Path(settings.storage.local_data_dir)
        self.active_profile_path = base_dir / "active_tool_profile.json"
        self.profile_versions_dir = base_dir / "profiles"

    def save(self, profile: ToolProfile) -> None:
        self.repo.append(self.settings.storage.tool_profiles_table, "tool_profiles", profile)
        self.active_profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_versions_dir.mkdir(parents=True, exist_ok=True)
        self.active_profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        version_path = (
            self.profile_versions_dir / f"{profile.profile_name}_{profile.profile_version}.json"
        )
        version_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        logger.info(
            "Saved tool profile %s version %s",
            profile.profile_name,
            profile.profile_version,
        )

    def load_active(self) -> ToolProfile | None:
        if self.active_profile_path.exists():
            return ToolProfile.model_validate_json(
                self.active_profile_path.read_text(encoding="utf-8")
            )
        return None
