# Convert This Template to a Real App

[Back to README](../README.md)
[Architecture](./ARCHITECTURE.md)

Use this checklist after forking. Before app edits or the normal quickstart,
run `python scripts/customize_template.py my_agent_app` once, use lowercase
snake_case, and commit the rename as its own first commit.

For local customization, edit app tools, registry, sample task, and evals.
Before shared-workspace deployment, review or adjust the Databricks bundle/job
identity.

## Customization model

Required for a real project:

- `src/databricks_tool_agent_template/app/tools.py`
- `src/databricks_tool_agent_template/app/registry.py`
- `examples/demo_run_task.json`
- `evals/sample_scenarios.json`

Before shared-workspace deployment:

- `databricks.yml`
- `resources/jobs.yml`

Review or adjust the bundle name in `databricks.yml` and job display names in
`resources/jobs.yml` before shared-workspace deployment.

Usually unchanged:

- `runner/`
- `providers/`
- `storage/`
- `clients/`
- `tools/`

Optional:

- system prompt
- MCP tool-source config
- storage route
- endpoint/profile/workspace settings

## 1. Replace the demo app behavior

Edit [app/tools.py](../src/databricks_tool_agent_template/app/tools.py) to
replace the demo tool implementations.

Edit [app/registry.py](../src/databricks_tool_agent_template/app/registry.py)
to register project tools and update model-visible tool descriptions.

Tool descriptions are visible to the model. State what each tool does and when
it should be used so the model can choose between the full discovered inventory.

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

Before shared-workspace deployment, review or adjust the Databricks bundle name in
[databricks.yml](../databricks.yml) and job display names in
[resources/jobs.yml](../resources/jobs.yml).

You do not need to rename the Python package to start using this template.

## 4. Configure workspace settings

Copy [workspace-config.example.yml](../workspace-config.example.yml) to
`workspace-config.yml`, then set workspace-specific values such as the serving
endpoint, auth profile, tool source settings, and storage route.

Keep real workspace hosts, endpoint names, table names, MCP URLs, and
credentials out of public committed config.

| Need | File | What to change |
|---|---|---|
| Serving endpoint | `workspace-config.yml` | `llm_endpoint_name` |
| Workspace/auth | `workspace-config.yml` | `workspace_host`, `databricks_config_profile` |
| Local tools | `app/tools.py`, `app/registry.py` | implementations, schemas, descriptions |
| MCP tools | `workspace-config.yml` | `tools.databricks_mcp` settings |
| Local event files | `workspace-config.yml` | `storage.local_data_dir` |
| Table persistence | `workspace-config.yml` | `storage.agent_events_table` |
| Bundle identity | `databricks.yml` | bundle name |
| Job identity | `resources/jobs.yml` | job display names |

For runtime details, see [Architecture](./ARCHITECTURE.md).

## 5. Optional changes

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

## Update app-specific tests

When replacing the demo app, update app-specific tests that assert demo tool
names, sample task names, sample eval scenarios, or model-visible tool
descriptions.

Framework tests should continue to pass without requiring changes to runner,
provider, storage, client, or lower-level tool internals.

## 6. Files you usually should not edit

These runtime internals usually do not need editing unless you are extending the
template framework:

- `runner/`
- `providers/`
- `storage/`
- `clients/`
- `tools/`
