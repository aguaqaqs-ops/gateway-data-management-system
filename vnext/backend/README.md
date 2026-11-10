## Backend and operation worker

Production deployment requires `GATEWAY_STORAGE_LAYOUT_FILE` and
`GATEWAY_RESOURCE_PROFILE_FILE`, mounted read-only. The two strict JSON files
own all ten storage locations and worker/service resources. Backend and worker
share the six BE roots; the DB is always `be-metadata/control.sqlite3`.

Prepare the actual mounts/directories, run explicit host `check-host`,
`init-layout`, `check-layout`, and render the Compose override as described in
[the deployment runbook](../deploy/README.md#storage-and-resource-configuration-p7-s1a).
The base Compose file has no usable default storage. Missing mounts, wrong
markers, permissions or actual cgroup limits refuse startup before DB writes,
readiness and claims. Runtime identity loss blocks new work until restart.

The worker command remains `python -m gateway_backend.bootstrap.operation_worker`.
Repository URL, bearer token file and provisioned mapping settings keep the
`GATEWAY_BACKEND_OPERATION_WORKER_` prefix. N/M/E/reserve/W/K come exclusively
from the resource JSON; old root, DB-path and repeated resource environment
settings have no runtime entrypoints. Existing roots must already exist.
`SIGTERM` and `SIGINT` request a graceful drain. `/healthz` is liveness only;
`/readyz` also checks the current storage/resource boundary. Logs exclude tokens
and host source paths.
