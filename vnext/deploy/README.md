# Gateway vNext Deploy Configuration

This directory contains Compose and example configuration for local and staged
verification. Example files document shape and field semantics only; they do not
automatically grant production permissions to real users.

## Session permissions

Backend HTTP authorization uses `session.json` entries mounted at
`GATEWAY_BACKEND_SESSION_FILE`. Each session carries an explicit `permissions`
array. Permission checks are exact string matches with no inheritance.

| Permission | Purpose |
| --- | --- |
| `workspace_read` | Read workspaces, operations, and submission reads |
| `upload_submit_workspace` | Upload revisions and accept submit attempts |
| `preview_workspace` | Start preview operations |
| `review_submission` | Apply review events |
| `archive_submission` | List candidates, preview plans, append audit facts, and start archives |
| `read_project_history` | Read project history nodes and start history compares |

`archive_submission` is independent from upload, preview, and review. Grant it
only to actors that should perform Archive commands for a device/project scope.

`read_project_history` is independent from workspace, upload, preview, review,
and archive permissions. Permission checks are exact string matches with no
inheritance; granting `archive_submission` does not imply history read access.

## Provisioned mapping and initial seed

`provisioned-mapping.json` binds `gateway_device_external_key` and
`business_project_id` to one `repository_id` and an initial baseline identity.

- `baseline_head_version` in the mapping file is the **initial seed input only**.
- First repository seed must use `baseline_head_version = 0`.
- Startup creates the INITIAL baseline node/head once and never rewrites Head on
  later restarts from mapping alone.
- After Archive advances Head, re-reading mapping must not move Head backward.

Do not run mixed v4/v5 control DB writers. Upgrade flow:

1. Stop admission and drain HTTP/worker processes sharing the control DB.
2. Take a consistent SQLite backup.
3. Start upgraded processes against the migrated database.
4. Verify `/readyz` and scope-specific smoke journeys before reopening traffic.

## Required secret file paths

Compose and production startup require these host files (see `compose.yaml`):

- `GATEWAY_P2R2_BEARER_TOKEN_FILE` — Repository Service bearer token
- `GATEWAY_BACKEND_SESSION_FILE` — session permissions document
- `GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE` — internal recovery bearer

Files should be readable only by the service user/group configured for the
container runtime.

## Compose services

- `backend` — HTTP API, control DB, artifact root, session, and mapping mounts
- `worker` — operation worker sharing backend control DB and artifacts
- `repository-service` — isolated repository volume; not mounted into backend

Archive uses the shared control DB only. It does not add Repository mounts,
worker jobs, or extra services.
