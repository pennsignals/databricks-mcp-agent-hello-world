import pytest

from databricks_tool_agent_template.app.tools import (
    create_support_ticket,
    lookup_customer,
)


def test_lookup_customer_returns_expected_customer() -> None:
    assert lookup_customer("cust_acme")["name"] == "Acme Co"


def test_lookup_customer_raises_for_unknown_customer() -> None:
    with pytest.raises(ValueError, match="unknown customer_id"):
        lookup_customer("missing")


def test_create_support_ticket_is_deterministic() -> None:
    assert create_support_ticket("Need help with onboarding", severity="medium") == {
        "ticket_id": "TICK-1B3A5FF8",
        "status": "created",
        "severity": "medium",
    }


@pytest.mark.parametrize(
    ("summary", "severity", "message"),
    [
        pytest.param("   ", "low", "summary must not be empty", id="blank-summary"),
        pytest.param("need help", "urgent", "invalid severity", id="invalid-severity"),
    ],
)
def test_create_support_ticket_rejects_invalid_inputs(
    summary: str,
    severity: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        create_support_ticket(summary, severity=severity)
