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
| `review_submission` | Read scoped reviews and apply APPROVE/REJECT/WITHDRAW |
| `withdraw_own_submission` | Read own reviews and WITHDRAW own PENDING submissions |
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

The control DB has one baseline schema (`infrastructure/control_db/schema.py`) and
no in-place upgrade. Backend and worker check the schema when they start: a database
whose schema differs from the running build is refused before any write, and the
error names only the mismatched objects. To move a local development environment to
a new baseline, stop backend and worker, delete the local control DB file together
with its `-wal` and `-shm` sidecar files, and start again; the control DB is then
recreated from the baseline. Backend and worker that share one control DB must run
the same build. After a restart, confirm `/readyz` and the scope-specific smoke
journeys before reopening traffic.

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


## Storage and resource configuration (P7 S1a)

Two explicit documents are the only sources of locations and resources:
`storage-layout.json` and `resource-profile.json`. The ten slot names, strict
format and fixed relative paths are specified in the
[S1a design](../../docs/backend-vnext/refactoring/formal/plans/p7-s1a-execution-plan.md#31-配置文档与作用域).
There is no old DATA_ROOT/artifact-root/absolute control-DB/N/M/E alias.
Backend and worker derive `be-metadata/control.sqlite3`; RS owns its four roots
and derives `rs-metadata/service-state/repository-service.sqlite3`.

`examples/storage-layout.same-disk.json` is a complete development example for
06's observed ext4 source `/dev/mapper/pve-vm--107--disk--0` mounted at `/`.
It must be edited for another deployment. `storage-layout.split-disk.json` is a
shape template requiring ten explicitly mounted local filesystems, not a claim
that those devices exist. Several slots may share one declared filesystem and
one consistent watermark. All source and container root paths remain distinct
and non-nested; source prefixes, roots and marker files must not be symlinks.
The standard deployment supports long-syntax bind mounts only.

The development resource profile uses N1/M24 GiB/E32 GiB/reserve8 GiB/W1/K1,
backend2 GiB/1 CPU, RS4 GiB/2 CPU and worker2 CPU, with host48 GiB/8 CPU planning
budget including shared8 GiB/2 CPU reserve. These are explicit conservative
correctness inputs, not a measured production capacity default. They fit 06's
observed 32 vCPU/64 GiB configuration; actual host/ancestor capacity is checked
again at execution. Swap is explicitly zero. `memory.max` equals the role's
configured envelope, `memory.swap.max` equals the additional swap allowance,
and effective CPU quota/cpuset and visible ancestors must cover the role.
The host formula counts W×E + backend + RS/Dolt + shared reserve once; M is a
kernel allocation budget, not RSS or the cgroup hard limit. W=K=1 is enforced.

Use Python 3.12+ on the actual deployment host. The renderer and host preflight
use only the standard library; they do not install dependencies or create mount
sources. Prepare actual mounts and empty source directories explicitly first.
Give RS root directories traversal/read/write access for the image's `gateway`
UID/GID; the entrypoint verifies mounts before preparing known owned components
and dropping privileges. It does not recursively repair unknown trees. Backend
and worker currently run as the image's root user and only mount the six BE
roots. RS receives only the four RS roots. Secrets remain separate files.

```bash
python3 vnext/scripts/render-runtime-config.py \
  --storage-layout /etc/gateway/storage-layout.json \
  --resource-profile /etc/gateway/resource-profile.json check-host
python3 vnext/scripts/render-runtime-config.py \
  --storage-layout /etc/gateway/storage-layout.json \
  --resource-profile /etc/gateway/resource-profile.json init-layout
python3 vnext/scripts/render-runtime-config.py \
  --storage-layout /etc/gateway/storage-layout.json \
  --resource-profile /etc/gateway/resource-profile.json check-layout
python3 vnext/scripts/render-runtime-config.py \
  --storage-layout /etc/gateway/storage-layout.json \
  --resource-profile /etc/gateway/resource-profile.json render \
  --output /run/gateway-compose-runtime.json
docker compose -f vnext/deploy/compose.yaml \
  -f /run/gateway-compose-runtime.json up -d
```

`check-host` validates actual host mountpoints/sources, no nested source mount,
free bytes/inodes and physical/ancestor resource capacity; it may precede marker
initialization. `init-layout` validates all ten existing empty roots before
writing the first marker. Existing matching markers make it idempotent; any
nonempty unmarked root or mismatched marker is refused without deletion.
`check-layout` additionally verifies all markers. Marker identity is exactly
schema_version/environment_id/group_id/slot/storage_id. The backend maintenance
CLI exposes the same explicit `init-layout` and `check-layout` host operations.

`render` validates document structure and writes a new external Compose JSON
override, which supplies every root/config bind with `create_host_path: false`,
role-specific memory/CPU/swap and replicas. It neither checks a remote host nor
initializes state. Always use the override, including `config`, `build`, `up`,
`exec` and `down`; the base YAML has no usable storage default. Both documents
are mounted read-only. Changing their values requires drain/restart and a new
render. Compose uses the host cgroup namespace so the runtime can inspect its
actual child and visible ancestor limits; it does not mount the Docker socket
or make cgroup controls writable.

Every service repeats bounded mount/marker/cgroup checks and an effective-role
create/write/fsync/unlink probe before opening its DB. Capacity must pass before
publishing ready or claiming work; RS may first run its existing safe bounded
startup reclaim under a valid root identity. Backend runtime
checks also gate HTTP admission and every worker write UoW; RS checks readiness,
import claims and cleaner identity. A lost root identity remains refused until
restart/preflight. Missing/wrong/readonly/inaccessible roots never produce a
replacement directory or system-disk fallback. Existing liveness remains
separate. Post-admission ENOSPC/EDQUOT/I/O errors keep existing failure/recovery
semantics, including unknown-effect reconciliation.
A temporary low-water observation refuses admission without latching identity
failure. RS cleaner checks identity with capacity admission disabled, so it can
reclaim eligible data and restore readiness. It does not delete protected data.
The true cgroup v2 hierarchy root has no local memory/CPU limit files; only a
verified hierarchy root is treated as unlimited at that level. Missing leaf or
delegated-controller files still fail closed, and stricter ancestors still apply.

Backend explicit startup atomically publishes the derived ordinary file
`be-metadata/.gateway-runtime-configuration.json` after root/marker/euid probes.
It contains environment/group and normalized digests of both documents. Worker
requires a matching bounded no-follow record before startup and claim; Compose
starts it after backend is healthy. Runtime readiness/admission only compares,
and never repairs it. Stopped-service backend restart may replace a missing,
stale or malformed ordinary record; symlinks, directories and submounts are
refused. This file is not a lease or business authority. Cleanup and offline
maintenance do not require it.

Both Compose harnesses and the frontend real-backend script prepare explicit
isolated runtime roots through the same renderer. Their external directories
carry an exact owner/inode record. Successful teardown removes only that run's
roots; failure retains owned diagnostics. RS named-volume backing is explicitly
labelled, checked for container references, and removed separately after Compose
down because bind mounts do not make it a Compose-managed volume. Failed volume
contents are preserved while stopped before removing that owned volume.


Explicit host debugging may select backend `runtime_mode=host` (the corresponding
HTTP/worker setting prefix applies); it verifies role-local marker/identity and
watermarks but records `hard_envelope=false`. This mode is refused inside a
Docker/Podman container and is not container-isolation evidence. RS host probes
use explicit typed roots with a non-production profile; production requires both
canonical documents and cannot override them with probe roots.

The adapters expose fixed-count slot/filesystem observations with environment,
group and existing JCS configuration digests. Same-device free/inode samples are
reported once. One-object BE/RS adapters provide bounded fd-based logical and
allocated-byte observations, inode/device and observation time. These do not
scan roots, provide a statistics API, infer device ownership or measure exclusive
thin/reflink allocation. Statistics collection and persistence remain S1b.

## Changing a mount safely

Stop acceptance and delivery, drain worker/RS writes and active transfers, and
resolve unknown effects using the existing recovery path. Stop backend, worker,
RS and maintenance; obtain the existing exclusive service locks. Record both
configs/build identity. Copy each complete selected root while stopped,
including DB and present WAL/SHM as one consistent set, preserving markers,
permissions, IDs and refs. Never live-copy SQLite/Dolt or start both copies as
writers. Validate file counts/bytes/digests with ordinary copy tools.

Verify new actual mount sources, capacity, permissions and markers; update the
single layout and regenerate the override for all roles. Keep the old copies
read-only until validation finishes. Run host checks, start RS/control plane and
perform recovery, then start worker/acceptance. Check protected objects, Head,
fixed packages, mixed-root download and bounded cleanup. A failure leaves the
deployment stopped for diagnosis. Once the new copy has accepted writes, simply
switching back to the old copy is unsafe. No online migration, automatic disk
selection, old path alias or automatic DB deletion is provided.
