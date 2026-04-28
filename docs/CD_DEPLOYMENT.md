# CD deployment with GitHub Actions and OIDC

This template supports local/manual deployment and tag-driven CD deployment, but they serve different jobs. Use the `local` target first to validate auth, config, and runtime behavior. Use GitHub Actions CD for repeatable shared `dev` deployments once the local flow is green.

The template now requires Python 3.12+ in its wheel metadata and intentionally no longer supports older Databricks runtimes that are still on Python 3.11. This keeps the template aligned with the latest Databricks serverless environment and current modern Databricks runtimes, so use Python 3.12 for local build tooling, validation, and release automation as well.

This template includes `local`, `dev`, and `prod` bundle targets, but only `dev` CD deployment is implemented today. Production deployment automation is future work for either this template or downstream projects built from it.

## When to use local deployment vs CD deployment

| Topic | Local deployment | CD dev deployment |
| --- | --- | --- |
| Target | `local` | `dev` |
| Deployer | Human developer | Databricks service principal |
| Auth | Databricks CLI profile/local auth | GitHub OIDC |
| Root path | User-scoped `~/.bundle/...` | Shared `/Shared/.bundle/.../dev` |
| Intended use | Debugging and manual smoke testing | Repeatable shared non-prod deployment |
| Which config file is used | `workspace-config.yml` that you manage locally | Generated `workspace-config.yml` rendered from `workspace-config.deploy.template.yml.j2` |
| Where Databricks values are stored | Local `.env`, local CLI profile, and local config files | GitHub environment secrets in the `dev` environment |

Local/manual deployment remains the best path for initial debugging. CD deployment is the recommended repeatable deployment path for shared `dev` environments. Local users should deploy `local`, while GitHub Actions should deploy `dev`.

## Security model

- The workflow uses GitHub OIDC and a Databricks service principal. No PATs are used.
- All Databricks-specific values are stored as GitHub environment secrets.
- This repository is public, so the Databricks workspace URL is treated as sensitive and is not committed to `databricks.yml`.
- The workflow intentionally does not expose an environment URL in GitHub.
- The workflow uses the `dev` GitHub environment so environment protections such as required reviewers can be applied.

## One-time setup in Databricks

Create one Databricks service principal for `dev` CD, assign it to the `dev` workspace, and grant the minimum capabilities it needs to deploy bundle-managed jobs, own and update those jobs, use the configured serving endpoint, create and write to the configured Delta table target, and access the required Unity Catalog catalog and schema.

The first successful `dev` deployment should be run by the service principal. If `dev` resources were previously created by a human user, delete those old jobs before switching CD ownership to the service principal. After that, GitHub CD should create and own the shared dev jobs.

Create the GitHub OIDC federation policy with this exact command template:

```bash
databricks account service-principal-federation-policy create <SERVICE_PRINCIPAL_NUMERIC_ID> \
  --policy-id github-actions-dev \
  --description "GitHub Actions dev deploys for <ORG>/<REPO>" \
  --json '{
    "oidc_policy": {
      "issuer": "https://token.actions.githubusercontent.com",
      "subject": "repo:<ORG>/<REPO>:environment:dev"
    }
  }'
```

Replace:

- `<SERVICE_PRINCIPAL_NUMERIC_ID>` with the Databricks account-level numeric service principal ID
- `<ORG>` with the GitHub org or user
- `<REPO>` with the GitHub repository name

## One-time setup in GitHub

1. Open the repository in GitHub.
2. Go to `Settings` -> `Environments`.
3. Create an environment named `dev`.
4. Add these exact environment secrets:
   - `DATABRICKS_HOST`
   - `DATABRICKS_CLIENT_ID`
   - `DEV_LLM_ENDPOINT_NAME`
   - `DEV_AGENT_EVENTS_TABLE`
5. Add required reviewers for the `dev` environment.
6. Optionally enable prevent self-review.
7. Do not set an environment URL.

## How tag-based deployment works

1. A tag matching `vX.Y.Z` is pushed.
2. The workflow verifies that the tagged commit is on `main`.
3. The workflow renders deployment config into `workspace-config.yml`.
4. The workflow validates the bundle.
5. The workflow deploys the `dev` bundle.
6. The bundle build step runs `scripts/build_wheel.py`, which resolves the SCM version and builds the wheel into `dist/`.
7. The deployed jobs install that built wheel from `../dist/*.whl`.
8. The workflow runs `init_storage_job`.
9. The workflow runs `run_agent_task_job`.

The deployment command order is intentionally fixed:

```bash
databricks current-user me
databricks bundle validate --target dev
databricks bundle deploy --target dev
databricks bundle run --target dev init_storage_job
databricks bundle run --target dev run_agent_task_job
```

`pyproject.toml` now uses dynamic VCS versioning through `hatch-vcs`, so CD does not rewrite the file. Tagged releases resolve directly from the pushed tag, and the bundle deploy builds and deploys the resulting wheel artifact without a separate filename sync step.

## Troubleshooting

### OIDC auth failure

Check that the GitHub job is running in the `dev` environment, `permissions.id-token` is set to `write`, the Databricks service principal is assigned to the workspace, and the federation policy subject matches `repo:<ORG>/<REPO>:environment:dev`.

### Missing GitHub environment secret

If `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DEV_LLM_ENDPOINT_NAME`, or `DEV_AGENT_EVENTS_TABLE` is missing from the `dev` GitHub environment, config rendering or authentication will fail. Add the missing secret to the environment rather than to repository variables.

### Schema mismatch in `init_storage_job`

`init_storage_job` intentionally fails on schema mismatch. CD does not perform schema migrations. Inspect the reported schema difference, then migrate the table manually, replace it intentionally, or point `DEV_AGENT_EVENTS_TABLE` at a fresh target.

### Dev workspace permission failure

If deployment or job execution fails with permission errors, verify that the Databricks service principal can deploy bundle-managed jobs, use the serving endpoint, and access the configured Unity Catalog objects and Delta table target.

### Bundle validate uses the wrong workspace

The bundle does not store workspace hosts in `databricks.yml`. Local validation uses local Databricks auth, and GitHub CD uses the `dev` environment secrets plus OIDC.

The current CD flow does not handle schema migrations, prod deployment, rollback, or compute model changes away from the current serverless pattern.

## Future work: prod deployment

The `prod` target already exists in the template, but this PR does not implement prod deployment. Downstream teams or future template work can add a `prod` GitHub environment, a `prod` OIDC federation policy using subject `repo:<ORG>/<REPO>:environment:prod`, and a separate gated workflow or gated workflow job later.
