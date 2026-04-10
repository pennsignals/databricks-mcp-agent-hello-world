from __future__ import annotations

from typing import Any

MOCK_INCIDENT_DOCS = [
    {
        "id": "inc-001",
        "title": "Billing timeout regression",
        "text": "Timeout spikes were caused by a downstream cache stampede in billing-api.",
        "tags": ["billing", "timeouts", "cache"],
    },
    {
        "id": "inc-002",
        "title": "Auth service retry storm",
        "text": (
            "Retry amplification in auth-service created elevated latency "
            "and intermittent 503s."
        ),
        "tags": ["auth", "latency", "retries"],
    },
    {
        "id": "inc-003",
        "title": "Runbook for incident triage",
        "text": (
            "Use the runbook to validate dependency health, confirm feature "
            "flags, and inspect recent deploys."
        ),
        "tags": ["runbook", "triage", "ops"],
    },
]

MOCK_CUSTOMERS = {
    "CUST-12345": {
        "customer_id": "CUST-12345",
        "plan": "enterprise",
        "health_score": 92,
        "open_tickets": 1,
        "last_invoice_amount": 18450.22,
    },
    "CUST-99999": {
        "customer_id": "CUST-99999",
        "plan": "growth",
        "health_score": 68,
        "open_tickets": 4,
        "last_invoice_amount": 2199.00,
    },
}

MOCK_SERVICES = {
    "billing-api": [
        {
            "incident_id": "SEV-101",
            "status": "OPEN",
            "severity": "high",
            "summary": "Elevated tail latency",
        },
        {
            "incident_id": "SEV-102",
            "status": "MONITORING",
            "severity": "medium",
            "summary": "Cache miss rate elevated",
        },
    ],
    "auth-service": [
        {"incident_id": "SEV-201", "status": "OPEN", "severity": "high", "summary": "Retry storm"},
    ],
}


def search_incident_kb(query: str, max_results: int = 3) -> dict[str, Any]:
    q = query.lower().strip()
    scored = []
    for row in MOCK_INCIDENT_DOCS:
        haystack = f"{row['title']} {row['text']} {' '.join(row['tags'])}".lower()
        score = sum(1 for token in q.split() if token in haystack)
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [row for score, row in scored if score > 0][:max_results]
    return {"query": query, "results": results}


def search_runbook_sections(service_name: str, symptom: str | None = None) -> dict[str, Any]:
    sections = [
        {
            "section_id": "rb-001",
            "service_name": service_name,
            "title": "Validate dependency health",
            "content": (
                f"Check {service_name} dependencies, recent deploys, "
                "and feature flags before escalating."
            ),
        },
        {
            "section_id": "rb-002",
            "service_name": service_name,
            "title": "Containment checklist",
            "content": (
                "Review active incidents, identify retry storms, "
                "and confirm fallback paths are healthy."
            ),
        },
    ]
    if symptom:
        sections = [
            section for section in sections if symptom.lower() in section["content"].lower()
        ] or sections
    return {"service_name": service_name, "symptom": symptom, "sections": sections}


def lookup_customer_summary(customer_id: str) -> dict[str, Any]:
    summary = MOCK_CUSTOMERS.get(customer_id)
    if not summary:
        return {"customer_id": customer_id, "found": False}
    return {"customer_id": customer_id, "found": True, "summary": summary}


def get_open_incidents_for_service(service_name: str) -> dict[str, Any]:
    incidents = MOCK_SERVICES.get(service_name, [])
    return {"service_name": service_name, "incidents": incidents, "count": len(incidents)}


def lookup_service_dependencies(service_name: str) -> dict[str, Any]:
    dependencies = {
        "billing-api": ["postgres-primary", "pricing-service", "redis-cache"],
        "auth-service": ["identity-provider", "session-store", "rate-limiter"],
    }
    return {
        "service_name": service_name,
        "dependencies": dependencies.get(service_name, []),
        "count": len(dependencies.get(service_name, [])),
    }
