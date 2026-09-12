## Operation worker

The process-local operation worker is started from the source-based backend image with:

```bash
GATEWAY_BACKEND_OPERATION_WORKER_CONTROL_DB_PATH=/var/lib/gateway/control/control.sqlite3 \
GATEWAY_BACKEND_OPERATION_WORKER_ARTIFACT_ROOT=/var/lib/gateway/artifacts \
GATEWAY_BACKEND_OPERATION_WORKER_REPOSITORY_BASE_URL=http://repository-service:8000 \
GATEWAY_BACKEND_OPERATION_WORKER_REPOSITORY_BEARER_TOKEN_FILE=/run/secrets/repository-bearer-token \
python -m gateway_backend.bootstrap.operation_worker
```

`CONTROL_DB_PATH` and `ARTIFACT_ROOT` must be absolute. The worker creates the control DB
parent directory, verifies SQLite integrity, and requires the artifact root to already exist.
`SIGTERM` and `SIGINT` request a graceful drain. An empty database loads the frozen preview
JobDefinition registry, reaches readiness, remains idle, and exits cleanly after the signal.

HTTP backend settings use the `GATEWAY_BACKEND_` prefix for the same control DB, artifact root,
and repository read values. `/healthz` is liveness only; `/readyz` stays false until settings,
SQLite integrity, artifact root, and the preview registry are valid. Logs and health responses
must not include bearer tokens or host paths.
