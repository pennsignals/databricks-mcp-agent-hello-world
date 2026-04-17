from databricks_mcp_agent_hello_world.app.data import (
    DEMO_ONBOARDING_DOCS,
    DEMO_RECENT_JOB_RUNS,
    DEMO_USERS,
    DEMO_WORKSPACE_SETTINGS,
)


def test_demo_data_constants_match_expected_contract() -> None:
    assert set(DEMO_USERS) == {"usr_ada_01", "usr_grace_01"}
    assert len(DEMO_ONBOARDING_DOCS) == 3
    assert DEMO_WORKSPACE_SETTINGS["runtime_target"] == "Databricks Serverless Jobs"
    assert (
        DEMO_RECENT_JOB_RUNS[0]["summary_note"]
        == "Nightly feature refresh completed successfully in 18 minutes."
    )
