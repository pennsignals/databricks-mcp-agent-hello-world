# App Customization Guide

Start here when adapting this template.

This package is the intended app-specific editing surface. Keep changes small at
first, and leave the runtime framework in place.

## What to edit

For local customization, edit app tools, registry, sample task, and evals.

- `tools.py`: replace demo tool implementations with your project tools.
- `registry.py`: register project tools and model-visible tool descriptions.
- repo-root `examples/demo_run_task.json`: update the default local/deployed task.
- repo-root `evals/sample_scenarios.json`: update smoke evals for the new task.

Before shared-workspace deployment:

- repo-root `databricks.yml`: review or adjust the bundle name.
- repo-root `resources/jobs.yml`: review or adjust job display names.

Run the repo-root package customization script once, immediately after forking
and before editing app code. The main README keeps that first-run flow
canonical.

Tool descriptions are visible to the LLM. State clearly what each tool does and
when it should be used so the model can choose from the available inventory.

The starter app intentionally includes one relevant read-style tool
(`lookup_customer`) and one irrelevant write-like tool
(`create_support_ticket`). The default task should lead the LLM to select only
the relevant tool, demonstrating tool sub-selection from the available inventory.
`create_support_ticket` exists to demonstrate that the model can ignore
irrelevant tools. A separate eval shows that the write-like demo tool is
available when explicitly requested. The write-like tool is harmless and
local/demo-only.

Prompt instructions are not a runtime safety gate. If you add real
side-effecting tools, add domain-specific safeguards appropriate for your use
case.

Optional customization includes the system prompt, MCP tool-source config,
storage route, and endpoint/profile/workspace settings.

## What usually does not need editing

You usually do not need to edit runner, provider, storage, client, or lower-level
tool-conversion internals unless you are extending the template framework itself.
Local tools should normally be customized only through `app/tools.py` and
`app/registry.py`.
