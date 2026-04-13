from __future__ import annotations

from typing import Any


DEMO_HANDBOOK_ENTRIES = [
    {
        "title": "Local authentication",
        "snippet": "Authenticate locally with databricks auth login.",
    },
    {
        "title": "Workspace config",
        "snippet": "Set llm_endpoint_name in workspace-config.yml.",
    },
    {
        "title": "Preflight check",
        "snippet": "Run preflight before running the hello-world demo.",
    },
]

DEMO_SETTINGS = {
    "runtime_target": "Databricks Job (Python wheel task)",
    "local_auth_method": "Databricks CLI profile",
    "tool_backend": "local_python",
}


def greet_user(name: str) -> dict[str, str]:
    cleaned_name = name.strip()
    greeting = f"Hello, {cleaned_name}!" if cleaned_name else "Hello!"
    return {"greeting": greeting}


def search_demo_handbook(query: str, max_results: int = 1) -> dict[str, Any]:
    cleaned_query = query.strip().lower()
    tokens = [token for token in cleaned_query.split() if token]
    ranked_entries: list[tuple[int, int, dict[str, str]]] = []
    for index, entry in enumerate(DEMO_HANDBOOK_ENTRIES):
        haystack = f"{entry['title']} {entry['snippet']}".lower()
        score = sum(1 for token in tokens if token in haystack)
        ranked_entries.append((score, index, entry))

    ranked_entries.sort(key=lambda item: (-item[0], item[1]))
    selected = [entry for score, _, entry in ranked_entries if score > 0]
    if not selected:
        selected = list(DEMO_HANDBOOK_ENTRIES)
    return {"results": selected[: max(0, max_results)]}


def get_demo_setting(key: str) -> dict[str, str]:
    cleaned_key = key.strip()
    return {"key": cleaned_key, "value": DEMO_SETTINGS.get(cleaned_key, "")}


def tell_demo_joke(topic: str) -> dict[str, str]:
    cleaned_topic = topic.strip()
    joke = "Why did the notebook bring a ladder? To reach its highest note."
    if cleaned_topic:
        joke = f"{joke} It had nothing to do with {cleaned_topic}, which is the point."
    return {"joke": joke}
