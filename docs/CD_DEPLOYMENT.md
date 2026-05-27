# CD Deployment

[Back to README](../README.md)

This repo includes a small GitHub Actions workflow for tag-driven deployment to the `dev` Databricks Asset Bundle target.

## What It Does

`.github/workflows/cd-dev-on-tag.yml` runs CI, renders `workspace-config.yml` from protected GitHub environment values, validates and deploys the bundle to `dev`, initializes storage, and runs the demo job as a smoke check.

It does not deploy a production target.

## When It Runs

The workflow runs on:

- manual `workflow_dispatch`
- pushed tags that match `v*.*.*`

Release tags should point at commits reachable from `main`.

## Required GitHub Configuration

Use the GitHub environment named `dev`.

Required environment secrets:

- `DATABRICKS_HOST`
- `DATABRICKS_CLIENT_ID`
- `DEV_LLM_ENDPOINT_NAME`
- `DEV_AGENT_EVENTS_TABLE`

The workflow sets `DATABRICKS_AUTH_TYPE=github-oidc`.

## Required Databricks Setup

At a high level, the Databricks workspace must allow the GitHub OIDC identity to:

- authenticate as the service principal identified by `DATABRICKS_CLIENT_ID`
- deploy Databricks Asset Bundles
- query the configured model serving endpoint
- create or write the configured event table
- run the bundle jobs

The deployed bundle path is owned by the authenticated Databricks identity.

## Command Sequence

The workflow executes this Databricks sequence:

```bash
databricks current-user me
databricks bundle validate --target dev
databricks bundle deploy --target dev
databricks bundle run --target dev init_storage_job
databricks bundle run --target dev run_agent_task_job
```

Databricks job output is intentionally suppressed in GitHub logs to reduce the chance of leaking task data.

## When It Fails

Check:

- the CI job result
- GitHub environment secret names and values
- Databricks OIDC/service-principal setup
- serving endpoint query permissions
- Unity Catalog permissions for `DEV_AGENT_EVENTS_TABLE`
- the Databricks job run output in the workspace
