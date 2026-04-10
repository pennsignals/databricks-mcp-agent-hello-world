from pathlib import Path

import pytest

from databricks_mcp_agent_hello_world.config import load_settings


def test_load_settings_reads_prompt_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yml"
    filter_prompt = tmp_path / "filter.txt"
    audit_prompt = tmp_path / "audit.txt"
    agent_prompt = tmp_path / "agent.txt"
    filter_prompt.write_text("filter prompt", encoding="utf-8")
    audit_prompt.write_text("audit prompt", encoding="utf-8")
    agent_prompt.write_text("agent prompt", encoding="utf-8")
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "active_profile_name: prod-profile",
                f"tool_filter_prompt_path: {filter_prompt}",
                f"tool_audit_prompt_path: {audit_prompt}",
                f"agent_system_prompt_path: {agent_prompt}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("LLM_ENDPOINT_NAME", raising=False)

    settings = load_settings(str(config_path))

    assert settings.active_profile_name == "prod-profile"
    assert settings.prompts.filter_prompt == "filter prompt"
    assert settings.prompts.audit_prompt == "audit prompt"
    assert settings.prompts.agent_system_prompt == "agent prompt"


def test_load_settings_requires_llm_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text("tool_provider_type: local_python\n", encoding="utf-8")
    monkeypatch.delenv("LLM_ENDPOINT_NAME", raising=False)

    with pytest.raises(ValueError, match="LLM_ENDPOINT_NAME"):
        load_settings(str(config_path))


def test_load_settings_reads_dotenv_before_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yml"
    dotenv_path = tmp_path / ".env"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: yaml-endpoint",
                "tool_provider_type: local_python",
                "active_profile_name: yaml-profile",
            ]
        ),
        encoding="utf-8",
    )
    dotenv_path.write_text(
        "\n".join(
            [
                "LLM_ENDPOINT_NAME=dotenv-endpoint",
                "ACTIVE_PROFILE_NAME=dotenv-profile",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("LLM_ENDPOINT_NAME", raising=False)
    monkeypatch.delenv("ACTIVE_PROFILE_NAME", raising=False)

    settings = load_settings(str(config_path))

    assert settings.llm_endpoint_name == "dotenv-endpoint"
    assert settings.active_profile_name == "dotenv-profile"


def test_load_settings_prefers_real_env_over_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yml"
    dotenv_path = tmp_path / ".env"
    config_path.write_text("tool_provider_type: local_python\n", encoding="utf-8")
    dotenv_path.write_text("LLM_ENDPOINT_NAME=dotenv-endpoint\n", encoding="utf-8")
    monkeypatch.setenv("LLM_ENDPOINT_NAME", "env-endpoint")

    settings = load_settings(str(config_path))

    assert settings.llm_endpoint_name == "env-endpoint"
