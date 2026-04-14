# databricks-mcp-agent-hello-world

`databricks-mcp-agent-hello-world` is a bundle-based, Python-wheel Databricks Job template for a non-interactive, tool-using agent workflow. It is a Databricks Job template, not a Databricks App, and it is meant to be run locally first and then deployed as a bundle.

The starter uses a local-first development flow, deploys as Python wheel Jobs on Databricks, and uses serverless compute as the default deployed compute path for MVP.

For MVP, `local_python` is the only working runtime backend. `managed_mcp` is reserved for a future extension path.

## Required edits before your first run

- [ ] Replace the placeholder workspace host in `databricks.yml` before you run `databricks bundle validate` or `databricks bundle deploy`.
  - Placeholder:
    ```yaml
    targets:
      dev:
        workspace:
          host: https://your-workspace.cloud.databricks.com
      prod:
        workspace:
          host: https://your-workspace.cloud.databricks.com
    ```
  - Intended pattern:
    ```yaml
    targets:
      dev:
        workspace:
          host: https://<your-workspace-host>
      prod:
        workspace:
          host: https://<your-workspace-host>
    ```
- [ ] Create a real repo-root `workspace-config.yml` by copying `workspace-config.example.yml`.
- [ ] Keep `workspace-config.yml` in the repo root for local runs.
- [ ] Make sure the deployed job YAML uses this exact config path syntax:
  ```yaml
  config_path: ${workspace.file_path}/workspace-config.yml
  ```

## Quickstart

Use one path only: CLI profile auth, repo-root `workspace-config.yml`, then local checks in the order below.

The quickstart assumes the default deployed compute path: serverless Databricks Jobs. There is no alternate compute branch in the first-run setup.

1. `uv sync`
2. `databricks auth login`
   If you are not using the `DEFAULT` profile, pass `--profile <name>` and use the same profile name in `DATABRICKS_CONFIG_PROFILE`.
3. copy `.env.example` and `workspace-config.example.yml`
4. `uv run preflight --config-path workspace-config.yml`
5. `uv run discover-tools --config-path workspace-config.yml`
6. `uv run compile-tool-profile --config-path workspace-config.yml`
7. `uv run run-agent-task --config-path workspace-config.yml --task-input-json '{"task_name":"hello_world_demo"}'`
8. `uv run pytest`
9. `uv run run-evals --config-path workspace-config.yml`

## Testing levels

### Unit tests

Command:

```bash
uv run pytest
```

Definition:

- local
- fast
- no live LLM call required
- no token usage expected

### Live integration evals

Command:

```bash
uv run run-evals --config-path workspace-config.yml
```

Definition:

- uses configured Databricks-hosted LLM endpoint
- requires valid auth
- consumes tokens
- may vary slightly between runs

Live integration evals call the configured Databricks-hosted LLM endpoint and may consume tokens.
Use them after local setup and basic hello-world verification succeed. Normal success means the
agent uses only allowlisted tools, explicitly excluded tools stay out of execution, and blocked
tool attempts are not expected during normal live runs.

### Hello-world demo run

Command:

```bash
uv run run-agent-task --config-path workspace-config.yml --task-input-json '{"task_name":"hello_world_demo"}'
```

Definition:

- demonstrates the actual end-to-end hello-world workflow
- not a test harness
- should be used after preflight and profile compilation

## Deployment

Deploy to Databricks after the local flow is green.

The bundled Jobs use serverless compute by default. That is the recommended MVP path because it removes the most common first-run blocker: permission to create a classic jobs cluster. Local commands still run entirely from your machine and do not require Databricks compute.

```bash
databricks bundle validate --target dev
databricks bundle deploy --target dev
databricks bundle run --target dev compile_tool_profile_job
databricks bundle run --target dev run_agent_task_job
```

Success:
- `bundle validate` passes after the placeholder host has been replaced.
- `bundle deploy --target dev` succeeds.
- `compile_tool_profile_job` runs successfully and compiles the active profile in the workspace.
- `run_agent_task_job` runs successfully and returns the hello-world result on Databricks.

If a downstream project needs a different compute model, edit [resources/databricks_mcp_agent_hello_world_job.yml](/Users/mbecker/git/databricks-mcp-agent-hello-world/resources/databricks_mcp_agent_hello_world_job.yml) and replace the serverless task environment configuration with the compute configuration your workspace requires. That is a downstream customization and does not change the local CLI workflow or the Job-first architecture of this starter.

## Compute defaults

This starter defaults bundled Databricks Jobs to serverless compute.

Why this is the MVP default:

- it avoids the common first-run failure where a user can deploy the bundle but cannot create a classic jobs cluster
- it reduces manual compute setup for new users
- it keeps the template focused on the agent workflow instead of cluster provisioning
- it preserves one obvious path: configure locally, verify locally, deploy, then run the Job

What this means in practice:

- local development does not depend on Databricks compute
- deployed `compile_tool_profile_job` and `run_agent_task_job` use serverless by default
- if your workspace does not support serverless for this pattern, you can intentionally change the job resource later

To change compute mode later in a downstream project:

1. Edit [resources/databricks_mcp_agent_hello_world_job.yml](/Users/mbecker/git/databricks-mcp-agent-hello-world/resources/databricks_mcp_agent_hello_world_job.yml).
2. Replace each task's `environment_key` plus job-level `environments` block with the compute configuration your workspace requires, such as a classic `new_cluster`, a shared existing cluster, or another approved job compute pattern.
3. Keep the Python wheel task shape and keep `config_path: ${workspace.file_path}/workspace-config.yml` unchanged so the local and deployed flows stay aligned.

This documentation is here to show where the compute decision lives. It is not a second recommended quickstart.

## Troubleshooting

1. `databricks bundle validate` fails with the placeholder host

   Symptom: validation errors reference `https://your-workspace.cloud.databricks.com`.

   Fix: update `targets.<target>.workspace.host` in `databricks.yml`.

2. `preflight` or runtime cannot find `workspace-config.yml`

   Symptom: the command fails because the config file is missing.

   Fix: copy `workspace-config.example.yml` to `workspace-config.yml` and keep it in the repo root.

3. `LLM_ENDPOINT_NAME` is missing or invalid

   Symptom: local validation fails or the agent cannot start with the configured endpoint.

   Fix: update `.env` or `workspace-config.yml` with the correct Databricks-hosted endpoint name.

4. Local logs say Spark is unavailable

   Symptom: local runs print a message about Spark not being present.

   Fix: that is expected in local mode. Local fallback persistence is normal off-cluster.

5. `databricks bundle deploy` fails before the Jobs are created

   Symptom: deployment fails while validating or creating bundle-managed resources.

   Fix: treat this as a bundle deployment problem first. Re-check `databricks.yml`, authentication, target workspace access, and any workspace-level bundle restrictions.

6. `databricks bundle run` fails because serverless is unavailable or unsupported

   Symptom: deployment succeeded, but a bundled Job run fails during compute provisioning before your wheel entry point starts.

   Fix: this usually means the configured job compute mode is incompatible with the target workspace's capabilities, policies, or permissions. The Python wheel Job model is still correct; the compute configuration is the mismatch. If the workspace does not support the default serverless path, update [resources/databricks_mcp_agent_hello_world_job.yml](/Users/mbecker/git/databricks-mcp-agent-hello-world/resources/databricks_mcp_agent_hello_world_job.yml) to use the compute model your environment allows.

7. Job runtime cannot find the config path

   Symptom: the Databricks job cannot load `workspace-config.yml`.

   Fix: confirm `config_path` in the job YAML matches the deployed workspace file path and that `workspace-config.yml` is part of the deployed project.
