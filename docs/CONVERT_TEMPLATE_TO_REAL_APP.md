# Convert This Template to a Real App

[Back to README](../README.md)
[Architecture](./ARCHITECTURE.md)

Use this checklist after the README quickstart works.

The Python package name can remain unchanged for initial adoption. Rename the
Databricks bundle/job identity for your project first. Rename the Python package
only if your team requires project-specific import/package names.

## 1. Replace the demo app behavior

Edit [app/tools.py](../src/databricks_mcp_agent_hello_world/app/tools.py) to
replace the demo tool implementations.

Edit [app/registry.py](../src/databricks_mcp_agent_hello_world/app/registry.py)
to register project tools and update model-visible tool descriptions.

Tool descriptions are visible to the model. State what each tool does and when
it should be used so the model can choose between the full discovered inventory.

The starter app intentionally includes one relevant read-style tool
(`lookup_customer`) and one irrelevant write-like tool
(`create_support_ticket`). The default task should lead the LLM to select only
the relevant tool, demonstrating tool sub-selection from the available inventory.

## 2. Update the sample task and evals

Edit [examples/demo_run_task.json](../examples/demo_run_task.json) for the
default local and deployed task.

Edit [evals/sample_scenarios.json](../evals/sample_scenarios.json) for smoke
evals that match the new task.

Evals verify run status, expected tool use, and required output text. Supported
scenario assertion fields are:

- `expected_status`
- `required_executed_tools`
- `forbidden_executed_tools`
- `required_output_substrings`

Eval summary reports are written locally under `storage.local_data_dir`; agent
execution events still follow the configured storage route.

## 3. Configure the deployment identity

Rename the Databricks bundle/job identity in [databricks.yml](../databricks.yml)
for your project.

If desired, also update display names in [resources/jobs.yml](../resources/jobs.yml).

You do not need to rename the Python package to start using this template.

## 4. Configure workspace settings

Copy [workspace-config.example.yml](../workspace-config.example.yml) to
`workspace-config.yml`, then set workspace-specific values such as the serving
endpoint, auth profile, tool source settings, and storage route.

Keep real workspace hosts, endpoint names, table names, MCP URLs, and
credentials out of public committed config.

## 5. Optional changes

Package renaming is optional and advanced, not part of the default path. Rename
the Python package only if your team requires project-specific import/package
names.

You can also replace the default system prompt if your domain needs different
general behavior. Keep local console commands and Databricks wheel task
arguments aligned around the same config and task files unless your app
intentionally needs separate task inputs.

After editing, validate the template still works:

```bash
preflight --config-path workspace-config.yml
discover-tools --config-path workspace-config.yml
run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json
python -m nox -s tests
```

Before using real data, review persisted event payloads. They can include task
inputs, prompt messages, tool arguments, tool results, model responses, errors,
and final outputs.

## 6. Files you usually should not edit

These runtime internals usually do not need editing unless you are extending the
template framework:

- `runner/`
- `providers/`
- `storage/`
- `clients/`
- `tools/`
