from databricks_mcp_agent_hello_world.demo.registry import TOOL_DEFINITIONS


def test_demo_registry_contains_exact_tool_set() -> None:
    assert list(TOOL_DEFINITIONS) == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]


def test_demo_registry_side_effect_levels_and_metadata_are_present() -> None:
    assert TOOL_DEFINITIONS["create_support_ticket"].spec.side_effect_level == "write"
    for tool_name in [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
    ]:
        assert TOOL_DEFINITIONS[tool_name].spec.side_effect_level == "read_only"

    for definition in TOOL_DEFINITIONS.values():
        assert definition.spec.capability_tags
        assert definition.spec.data_domains
        assert definition.spec.example_uses
