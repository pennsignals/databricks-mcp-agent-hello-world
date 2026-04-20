from __future__ import annotations

import hashlib

from .data import (
    DEMO_ONBOARDING_DOCS,
    DEMO_RECENT_JOB_RUNS,
    DEMO_USERS,
    DEMO_WORKSPACE_SETTINGS,
)

# TEMPLATE_CUSTOMIZE_HERE
# Replace these example app tools with your real project tools and keep behavior
# aligned with your domain.


def get_user_profile(user_id: str) -> dict[str, object]:
    """Fetch demo user details by user_id."""

    try:
        profile = DEMO_USERS[user_id]
    except KeyError as exc:
        raise ValueError(f"unknown user_id: {user_id}") from exc
    return {key: value for key, value in profile.items()}


def search_onboarding_docs(query: str, max_results: int = 3) -> dict[str, object]:
    """Search demo onboarding docs with deterministic keyword scoring."""

    if not query.strip():
        raise ValueError("query must not be empty")
    if max_results < 1:
        raise ValueError("max_results must be >= 1")

    lowered_query = query.lower()
    query_tokens = set(lowered_query.split())
    ranked_results: list[dict[str, object]] = []

    for doc in DEMO_ONBOARDING_DOCS:
        haystack = f"{doc['title']} {doc['content']}".lower()
        score = sum(1 for token in query_tokens if token in haystack)
        if score == 0:
            continue
        ranked_results.append(
            {
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "path": doc["path"],
                "snippet": doc["content"][:160],
                "score": score,
            }
        )

    ranked_results.sort(key=_ranked_result_sort_key)
    return {
        "query": query,
        "results": ranked_results[:max_results],
    }


def get_workspace_setting(key: str) -> dict[str, object]:
    """Fetch one demo workspace setting by key."""

    if key not in DEMO_WORKSPACE_SETTINGS:
        raise ValueError(f"unknown setting key: {key}")
    return {"key": key, "value": DEMO_WORKSPACE_SETTINGS[key]}


def list_recent_job_runs(limit: int = 5) -> dict[str, object]:
    """List recent demo job runs in newest-first order."""

    if limit < 1:
        raise ValueError("limit must be >= 1")
    return {"runs": DEMO_RECENT_JOB_RUNS[:limit]}


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


def _ranked_result_sort_key(item: dict[str, object]) -> tuple[int, str]:
    score_value = item["score"]
    if not isinstance(score_value, (int, str, float)):
        raise TypeError(f"ranked result score must be int, str, or float; got {type(score_value)}")
    return (-int(score_value), str(item["title"]))
