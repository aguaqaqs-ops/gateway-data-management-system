## Operation worker

The process-local operation worker is started from the source-based backend image with:

```bash
GATEWAY_BACKEND_OPERATION_WORKER_CONTROL_DB_PATH=/var/lib/gateway/control/control.sqlite3 \
python -m gateway_backend.bootstrap.operation_worker
```

`CONTROL_DB_PATH` must be an absolute path. The worker creates its parent directory and
initializes the local SQLite/WAL control database. `SIGTERM` and `SIGINT` request a graceful
drain; an empty database reaches readiness, remains idle, and exits cleanly after the signal.

R3 intentionally composes an immutable empty registry. Runnable records fail closed until a
future R4 job registry is installed; this entrypoint does not claim that production jobs or
external effects are executable.
