from databricks_mcp_agent_hello_world.tools.registry import TOOL_DEFINITIONS, list_tool_specs


def test_every_registered_tool_declares_explicit_metadata() -> None:
    for definition in TOOL_DEFINITIONS.values():
        spec = definition.spec
        assert spec.capability_tags
        assert spec.data_domains
        assert spec.side_effect_level in {"read_only", "write"}


def test_registry_metadata_is_normalized_and_descriptions_are_neutral() -> None:
    for spec in list_tool_specs():
        assert spec.capability_tags == sorted(spec.capability_tags)
        assert spec.data_domains == sorted(spec.data_domains)
        assert "intentionally not useful" not in spec.description.lower()
