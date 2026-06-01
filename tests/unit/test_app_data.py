from databricks_tool_agent_template.app.data import DEMO_CUSTOMERS


def test_app_data_matches_current_example_contract() -> None:
    assert set(DEMO_CUSTOMERS) == {"cust_acme", "cust_globex"}
    assert DEMO_CUSTOMERS["cust_acme"] == {
        "customer_id": "cust_acme",
        "name": "Acme Co",
        "tier": "enterprise",
        "region": "us-west",
    }
    assert DEMO_CUSTOMERS["cust_globex"] == {
        "customer_id": "cust_globex",
        "name": "Globex",
        "tier": "startup",
        "region": "us-east",
    }
