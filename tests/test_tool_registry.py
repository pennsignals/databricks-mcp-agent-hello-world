from databricks_mcp_agent_hello_world.app.registry import TOOL_DEFINITIONS, list_authored_tools


def test_every_registered_tool_declares_explicit_metadata() -> None:
    for definition in TOOL_DEFINITIONS.values():
        assert definition.capability_tags
        assert definition.data_domains
        assert definition.example_uses
        assert definition.side_effect_level in {"read_only", "write"}


def test_registry_metadata_is_normalized_and_descriptions_are_neutral() -> None:
    for definition in list_authored_tools():
        assert definition.capability_tags == sorted(definition.capability_tags)
        assert definition.data_domains == sorted(definition.data_domains)
        assert "unserious" not in definition.description.lower()


def test_registry_entries_do_not_author_provider_metadata() -> None:
    for definition in list_authored_tools():
        assert not hasattr(definition, "provider_type")
        assert not hasattr(definition, "provider_id")
