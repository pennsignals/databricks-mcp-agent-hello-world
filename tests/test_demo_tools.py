import pytest

from databricks_mcp_agent_hello_world.app.tools import (
    create_support_ticket,
    get_user_profile,
    get_workspace_setting,
    list_recent_job_runs,
    search_onboarding_docs,
)


def test_get_user_profile_returns_expected_user() -> None:
    user_details = get_user_profile("usr_ada_01")

    assert user_details["display_name"] == "Ada Lovelace"


def test_get_user_profile_raises_for_unknown_user() -> None:
    with pytest.raises(ValueError, match="unknown user_id"):
        get_user_profile("missing")


def test_search_onboarding_docs_ranks_local_development_first() -> None:
    result = search_onboarding_docs("local development")

    assert result["results"][0]["doc_id"] == "doc_local_dev_setup"


def test_search_onboarding_docs_returns_runtime_target_doc() -> None:
    result = search_onboarding_docs("runtime target")

    assert "doc_compute_overview" in [item["doc_id"] for item in result["results"]]


def test_search_onboarding_docs_validates_inputs() -> None:
    with pytest.raises(ValueError, match="query must not be empty"):
        search_onboarding_docs("   ")
    with pytest.raises(ValueError, match="max_results must be >= 1"):
        search_onboarding_docs("local development", max_results=0)


def test_get_workspace_setting_returns_runtime_target() -> None:
    result = get_workspace_setting("runtime_target")

    assert result["value"] == "Databricks Serverless Jobs"


def test_get_workspace_setting_raises_for_unknown_key() -> None:
    with pytest.raises(ValueError, match="unknown setting key"):
        get_workspace_setting("missing")


def test_list_recent_job_runs_handles_limits() -> None:
    assert len(list_recent_job_runs()["runs"]) == 3
    assert len(list_recent_job_runs(limit=1)["runs"]) == 1
    with pytest.raises(ValueError, match="limit must be >= 1"):
        list_recent_job_runs(limit=0)


def test_create_support_ticket_is_deterministic() -> None:
    result = create_support_ticket("Need help with onboarding", severity="medium")

    assert result == {
        "ticket_id": "TICK-1B3A5FF8",
        "status": "created",
        "severity": "medium",
    }


def test_create_support_ticket_validates_inputs() -> None:
    with pytest.raises(ValueError, match="summary must not be empty"):
        create_support_ticket("   ")
    with pytest.raises(ValueError, match="invalid severity"):
        create_support_ticket("Need help", severity="urgent")
