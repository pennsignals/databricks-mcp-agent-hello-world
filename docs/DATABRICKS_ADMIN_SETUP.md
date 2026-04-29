# Databricks Admin Setup for GitHub OIDC Bundle CD

[Back to README](../README.md)
[Reference: CD deployment](./CD_DEPLOYMENT.md)

This document describes the Databricks administrator setup required for a project that deploys Databricks Asset Bundles from GitHub Actions using GitHub OIDC and a dedicated Databricks service principal.

The happy path is:

```text
GitHub Actions -> GitHub OIDC token -> Databricks service principal -> Databricks Asset Bundle deploy
```

The project repository owns the bundle configuration and GitHub workflow. The Databricks administrator owns the Databricks identity, workspace access, federation policy, endpoint permissions, and Unity Catalog grants.

## Inputs needed from the project team

Before setup, collect:

```text
GitHub organization: <github-org>
GitHub repository:   <github-repo>
GitHub environment:  <github-environment>   # usually dev
Target workspace:    <workspace-url>
Bundle target:       <bundle-target>        # usually dev
LLM endpoint:        <serving-endpoint-name>
Events table:        <catalog>.<schema>.<table>
```

The GitHub OIDC subject should use this shape:

```text
repo:<github-org>/<github-repo>:environment:<github-environment>
```

## 1. Create a dedicated Databricks service principal

Create one Databricks service principal for the project and environment.

Example display name:

```text
<team>_<project>_Deployments_Dev
```

Use a service principal rather than a human user for CI/CD. Databricks describes service principals as specialized identities for automation, scripts, jobs, and CI/CD systems because they are not tied to an individual user. See [Databricks service principals](https://docs.databricks.com/aws/en/admin/users-groups/service-principals).

For production, create a separate production service principal instead of reusing the dev identity.

## 2. Add the service principal to the target workspace

Add the service principal to the target workspace.

Return both identifiers to the project team:

```text
Service principal numeric/internal ID: <numeric-id>
Service principal UUID/application/client ID: <uuid>
```

Use them differently:

```text
Numeric/internal ID:
  Used by Databricks account-level federation policy commands.

UUID/application/client ID:
  Used by GitHub Actions as DATABRICKS_CLIENT_ID.
```

Databricks GitHub OIDC setup uses `DATABRICKS_CLIENT_ID` for the service principal application ID. See [Databricks GitHub OIDC documentation](https://docs.databricks.com/aws/en/dev-tools/auth/provider-github).

## 3. Confirm workspace capabilities

Confirm the service principal can access the target workspace.

Confirm the workspace supports the compute mode required by the bundle. This template uses serverless job compute, and Databricks documents Unity Catalog as a requirement for serverless jobs. See [serverless jobs requirements](https://docs.databricks.com/aws/en/jobs/run-serverless-jobs).

The service principal should be able to:

```text
Authenticate to the workspace through GitHub OIDC
Deploy Databricks Asset Bundles
Create and update bundle-managed jobs
Upload bundle files and artifacts under the bundle workspace root
Run the bundle-created jobs
Use serverless jobs compute
Query the required model serving endpoint
Read/write required Unity Catalog objects
```

Avoid making the service principal a workspace admin unless that is the organization's chosen operating model.

## 4. Create the GitHub OIDC federation policy

Create a service-principal federation policy for the GitHub repository and GitHub environment.

Policy values:

```text
Issuer:   https://token.actions.githubusercontent.com
Audience: <Databricks account ID>
Subject:  repo:<github-org>/<github-repo>:environment:<github-environment>
```

Example subject:

```text
repo:my-org/my-agent-project:environment:dev
```

Run the federation policy command from an account-authenticated Databricks CLI session.

Example command shape:

```bash
databricks account service-principal-federation-policy create <SERVICE_PRINCIPAL_NUMERIC_ID> \
  --json '{
    "oidc_policy": {
      "issuer": "https://token.actions.githubusercontent.com",
      "audiences": ["<DATABRICKS_ACCOUNT_ID>"],
      "subject": "repo:<github-org>/<github-repo>:environment:<github-environment>"
    }
  }'
```

Databricks documents GitHub OIDC setup as creating a federation policy and configuring the GitHub Actions workflow. The documented policy values include the GitHub issuer, an environment-based subject, and the Databricks account ID as the recommended audience. See [Databricks GitHub OIDC documentation](https://docs.databricks.com/aws/en/dev-tools/auth/provider-github) and the [service principal federation policy API](https://docs.databricks.com/api/account/serviceprincipalfederationpolicy).

## 5. Confirm expected GitHub configuration

The project team configures GitHub, but the Databricks administrator should confirm the expected values.

GitHub workflow job:

```yaml
environment: <github-environment>

permissions:
  contents: read
  id-token: write
```

GitHub environment secrets:

```text
DATABRICKS_HOST
DATABRICKS_CLIENT_ID
DEV_LLM_ENDPOINT_NAME
DEV_AGENT_EVENTS_TABLE
```

Expected values:

```text
DATABRICKS_HOST:
  Full workspace URL, for example https://adb-...azuredatabricks.net

DATABRICKS_CLIENT_ID:
  Service principal UUID/application/client ID

DEV_LLM_ENDPOINT_NAME:
  Name of the Databricks serving endpoint

DEV_AGENT_EVENTS_TABLE:
  Fully qualified Unity Catalog table name
```

The workflow should set:

```yaml
env:
  DATABRICKS_AUTH_TYPE: github-oidc
  DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
  DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}
```

Databricks GitHub OIDC exchanges a GitHub workload identity token for a Databricks OAuth token, so GitHub does not need a Databricks PAT or client secret. See [Databricks GitHub OIDC documentation](https://docs.databricks.com/aws/en/dev-tools/auth/provider-github).

## 6. Grant model serving endpoint access

Grant the service principal query access to the required model serving endpoint.

Required permission:

```text
CAN_QUERY / Query
```

Endpoint:

```text
<serving-endpoint-name>
```

The endpoint should match the project's GitHub environment secret, for example:

```text
DEV_LLM_ENDPOINT_NAME
```

Databricks model serving docs state that a service principal needs Query permission on the endpoint before it can query the endpoint. See [Databricks model serving endpoint permissions](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-route-optimization).

## 7. Grant Unity Catalog privileges

Grant the service principal the Unity Catalog privileges required by the project.

Typical minimum for an existing events table:

```sql
GRANT USE CATALOG ON CATALOG <catalog>
TO `<service-principal-uuid>`;

GRANT USE SCHEMA ON SCHEMA <catalog>.<schema>
TO `<service-principal-uuid>`;

GRANT SELECT, MODIFY ON TABLE <catalog>.<schema>.<table>
TO `<service-principal-uuid>`;
```

Use the service principal UUID/application/client ID in backticks if SQL does not resolve the service principal display name.

If the project is expected to create tables or other Unity Catalog objects, grant the required create privileges at the schema or catalog level according to the organization's governance model. Databricks documents Unity Catalog access control through standard SQL grants and securable-object privileges. See [Unity Catalog overview](https://docs.databricks.com/aws/en/data-governance/unity-catalog).

## 8. Let GitHub CD create the shared bundle resources

Do not pre-create the shared bundle jobs as a human user.

The first deployment for a shared target such as `dev` should be run by GitHub Actions as the service principal. This lets the service principal create and own the bundle-managed jobs from the beginning.

The bundle may create jobs such as:

```text
dev_init_storage_job
dev_run_agent_task_job
```

The exact names depend on the bundle target and configured name prefixes.

Using the service principal as the initial creator avoids ownership mismatches between human-created jobs and service-principal-managed bundle deployments. Databricks job permissions distinguish view, run-management, manage, and owner privileges. See [Databricks job permissions](https://docs.databricks.com/aws/en/jobs/privileges).

## 9. Understand bundle resource visibility

This template may grant the workspace `users` group read-only visibility on bundle-managed shared resources, for example:

```yaml
permissions:
  - group_name: users
    level: CAN_VIEW
```

This allows workspace users to observe shared jobs and runs without granting deployment control.

Databricks Asset Bundle permissions support principals such as `user_name`, `group_name`, and `service_principal_name`, and top-level bundle permission levels include `CAN_VIEW`, `CAN_MANAGE`, and `CAN_RUN`. See [Databricks Asset Bundle permissions](https://docs.databricks.com/aws/en/dev-tools/bundles/permissions).

The template intentionally does not hardcode a deployment user, service principal UUID, or organization-specific deployer group. In some local validation contexts, Databricks may recommend explicitly adding the current deployer identity with `CAN_MANAGE`. That recommendation is expected for a generic template. Downstream private repos can add their own deployer identity or deployer group if they want fully explicit bundle-managed permissions.

## 10. Optional: grant project maintainers access to the service principal

This is optional and depends on the organization's operating model.

If desired, grant appropriate administrative access to selected project maintainers so they can inspect or manage the service principal.

Keep this separate from GitHub CD itself. GitHub CD authenticates directly as the service principal through OIDC and does not require a human user to run as the service principal.

## Final admin handoff checklist

```text
[ ] Create a dedicated Databricks service principal for the project/environment.
[ ] Add the service principal to the target workspace.
[ ] Confirm the service principal can access the workspace.
[ ] Confirm the workspace supports Unity Catalog and serverless jobs if required.
[ ] Return the service principal numeric/internal ID to the project team.
[ ] Return the service principal UUID/application/client ID to the project team.
[ ] Create the GitHub OIDC service-principal federation policy.
[ ] Use issuer: https://token.actions.githubusercontent.com.
[ ] Use audience: Databricks account ID.
[ ] Use subject: repo:<github-org>/<github-repo>:environment:<github-environment>.
[ ] Confirm GitHub will use environment: <github-environment>.
[ ] Confirm GitHub will use permissions: contents: read and id-token: write.
[ ] Confirm GitHub DATABRICKS_HOST will be the full workspace URL.
[ ] Confirm GitHub DATABRICKS_CLIENT_ID will be the service principal UUID/application/client ID.
[ ] Grant the service principal CAN_QUERY / Query access to the serving endpoint.
[ ] Grant the required Unity Catalog privileges.
[ ] Confirm the first shared bundle deployment will be run by GitHub CD as the service principal.
[ ] Optional: grant selected maintainers access to manage or inspect the service principal.
```

## Notes for project teams

After the Databricks administrator completes setup, configure the GitHub environment secrets:

```text
DATABRICKS_HOST
DATABRICKS_CLIENT_ID
DEV_LLM_ENDPOINT_NAME
DEV_AGENT_EVENTS_TABLE
```

Then run the CD workflow manually once to validate the setup.

If the manual CD run succeeds, tag-based releases can deploy through the normal release flow.
