from __future__ import annotations

import hashlib

from .data import DEMO_CUSTOMERS

# TEMPLATE_CUSTOMIZE_HERE
# Replace these example app tools with your real project tools and keep behavior
# aligned with your domain.


def lookup_customer(customer_id: str) -> dict[str, object]:
    """Fetch demo customer details by customer_id."""

    try:
        customer = DEMO_CUSTOMERS[customer_id]
    except KeyError as exc:
        raise ValueError(f"unknown customer_id: {customer_id}") from exc
    return dict(customer)


def create_support_ticket(summary: str, severity: str = "low") -> dict[str, object]:
    """Return a deterministic fake support ticket payload."""

    if not summary.strip():
        raise ValueError("summary must not be empty")
    if severity not in {"low", "medium", "high"}:
        raise ValueError("invalid severity")

    ticket_hash = hashlib.sha256(summary.encode()).hexdigest()[:8].upper()
    return {
        "ticket_id": f"TICK-{ticket_hash}",
        "status": "created",
        "severity": severity,
    }
