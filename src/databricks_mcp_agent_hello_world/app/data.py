DEMO_USERS = {
    "usr_ada_01": {
        "user_id": "usr_ada_01",
        "display_name": "Ada Lovelace",
        "team": "Data Platform",
        "role": "ML Engineer",
        "preferred_os": "macOS",
    },
    "usr_grace_01": {
        "user_id": "usr_grace_01",
        "display_name": "Grace Hopper",
        "team": "ML Infrastructure",
        "role": "Data Scientist",
        "preferred_os": "Linux",
    },
}

DEMO_ONBOARDING_DOCS = [
    {
        "doc_id": "doc_local_dev_setup",
        "title": "Local Development Setup",
        "path": "/docs/onboarding/local-development.md",
        "content": (
            "For local development, create an isolated environment with python3.12 -m venv "
            'and install the project with python -m pip install -e ".[dev]", '
            "run the test suite before opening a PR, and use the shared lint config."
        ),
    },
    {
        "doc_id": "doc_repo_workflow",
        "title": "Repository Workflow",
        "path": "/docs/onboarding/repository-workflow.md",
        "content": (
            "Use short-lived branches, keep commits focused, and open pull requests "
            "with a concise summary of changes and validation steps."
        ),
    },
    {
        "doc_id": "doc_compute_overview",
        "title": "Compute Target Overview",
        "path": "/docs/platform/compute-targets.md",
        "content": (
            "Batch agent jobs default to Databricks Serverless Jobs unless a task "
            "explicitly opts into a different execution target."
        ),
    },
]

DEMO_WORKSPACE_SETTINGS = {
    "runtime_target": "Databricks Serverless Jobs",
    "artifact_storage": "Unity Catalog volumes",
    "workspace_region": "us-west-2",
    "support_channel": "#agent-support",
}

DEMO_RECENT_JOB_RUNS = [
    {
        "job_name": "nightly_feature_refresh",
        "started_at": "2026-01-14T02:00:00Z",
        "status": "success",
        "summary_note": "Nightly feature refresh completed successfully in 18 minutes.",
    },
    {
        "job_name": "onboarding_index_refresh",
        "started_at": "2026-01-13T18:30:00Z",
        "status": "success",
        "summary_note": "Onboarding search index refresh completed successfully.",
    },
    {
        "job_name": "quality_signal_rollup",
        "started_at": "2026-01-13T09:10:00Z",
        "status": "success",
        "summary_note": "Quality signal rollup completed with one transient retry.",
    },
]
