# App Customization Guide

Start here when adapting this template.

This package is the intended app-specific editing surface. Keep changes small at
first, and leave the runtime framework in place.

## What to edit

- `tools.py`: replace demo tool implementations with your project tools.
- `registry.py`: register project tools and model-visible tool descriptions.
- repo-root `examples/demo_run_task.json`: update the default local/deployed task.
- repo-root `evals/sample_scenarios.json`: update smoke evals for the new task.

Tool descriptions are visible to the LLM. State clearly what each tool does and
when it should be used so the model can choose from the available inventory.
Local tools are customized through `app/tools.py` and `app/registry.py`;
`LocalPythonToolProvider` is framework internals and should not be edited for
normal app customization.

The starter app intentionally includes one relevant read-style tool
(`lookup_customer`) and one irrelevant write-like tool
(`create_support_ticket`). The default task should lead the LLM to select only
the relevant tool, demonstrating tool sub-selection from the available inventory.

## What usually does not need editing

You usually do not need to edit runner, provider, storage, or client internals
unless you are extending the template framework itself.
Lower-level local tool conversion helpers are implementation details, not the
recommended extension path.
