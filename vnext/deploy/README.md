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
kernel allocation budget, not RSS or the cgroup hard limit. Fixed W=K is enforced.

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
role-specific memory/CPU/swap and one replica per fixed service. It neither checks a remote host nor
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

## Statistics (P7-S1b)

Backend and worker write the independent `be-metadata/telemetry/statistics.sqlite3`
using separate bounded buffers/connections. Repository Service keeps a disposable
ring; backend polls its authenticated internal feed every 5 seconds. Collection
starts/stops with the existing processes; it does not participate in business
readiness, transactions, recovery or cleanup decisions. No new volume or service
is required. Ordinary session permission `statistics_read_group` grants group
health/capacity only; repository/operation APIs still require their existing scope
permissions. Never grant the recovery bearer for statistics display.

Compose forwards the same restart-scoped `GATEWAY_STATISTICS_ENABLED` (default
`true`), `SAMPLE_INTERVAL_SECONDS` (`1`), `FILESYSTEM_INTERVAL_SECONDS` (`60`) and
`STORAGE_REFRESH_SECONDS` (`600`) to all three roles. These names share the
`GATEWAY_STATISTICS_` prefix. Backend/worker also receive `TOTAL_BUDGET_BYTES`
(default `4294967296`, 4 GiB per group, including WAL/maintenance). Direct process
settings expose the other finite defaults in their statistics config; a Compose
override can explicitly pass additional settings. Keep the current sample period
identical across roles: queries use it to recognize gaps; historical period
changes cannot be reconstructed. Changing settings requires restarting the roles.

The budget was calibrated on 06 against the actual schema/indexes: 30,000 resource
rows averaged 475.82 indexed bytes, 10,000 occupancy rows 554.19 bytes, 1,000
10-table execution summaries 4,612.10 bytes and 1,000 writes 593.92 bytes. The
42,000-row run used 25,124,864 DB bytes, 1,466,752 WAL bytes and 32,768 SHM bytes.
A sizing example of three 1-second processes for 7 days, ten repositories with five
600-second categories plus one public category for 90 days, two filesystem feed
records every 60 seconds, and 500 execution/write pairs per day for 90 days needs
about 1.61 GB indexed main storage (2.01 GB with 25% allowance). The 4 GiB budget
has a 2 GiB main-file cap; the original 2 GiB total/1 GiB main cap would retain
about 2.67 curve days under that example after projected summaries/trends. This
is a capacity example, not a guarantee: more devices, attempts, process instances,
filesystem identities or larger bounded metrics shorten coverage. Actual curves,
summary coverage, nulls, truncation and drop counters are the authority; 7/90 days
are targets. No exact physical allocation or reclaimed-byte promise is made.

Every batch respects the loaded metadata filesystem byte/fraction/inode low-water
policy plus finite batch headroom. Pressure pauses statistics and retries at the
maintenance interval (60 seconds), dropping buffered input; old curves are the
first pressure-cleanup candidate. Statistics never removes business data or runs
VACUUM. Schema/identity mismatch or corruption disables statistics until an
operator repairs it while stopped and restarts. For this undeployed project,
explicitly recreating only the disposable telemetry DB/WAL/SHM loses historical
statistics; it cannot reconstruct previous resource/write windows. Never delete
or recreate the control DB to repair telemetry. Queries do not trigger scans or
configuration changes. Group health remains readable when the statistics DB is
unavailable; device/operation statistics return `STATISTICS_UNAVAILABLE`.

Capacity/debug originals and sizing assumptions are retained at
`/home/dev/gdds-stage-exchange/p7-s1b/e/`; the accepted capacity log is
`capacity-bddf517966-r2.log`. This was a host filesystem calibration and focused
lifecycle check, not a current-image container gate or formal performance result.
The final stage gate binds container lifecycle/deployment evidence to the final
candidate.


Worker resources use a fixed `count == active_limit` in 1..32. All workers use
one resource specification; the host planning check includes every worker plus
backend, Repository Service and shared reserves. The default remains W1/N1 with
32 GiB envelope, 8 GiB reserve and 24 GiB kernel budget. Input limits do not claim
validated capacity. Each worker requires
`GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX` in 1..count. Its stable identity
is scoped to environment/group and its numbered metadata flock remains held until
the process exits, including when executor threads outlive the main run function.
Never unlink or replace `.gateway-worker-<index>.lock` during metadata maintenance.
Replacement containers require confirmation that the old container and all its
execution processes have exited; lease expiry alone does not establish that fact.


The renderer keeps `worker` as instance 1 and emits `worker-2` through `worker-W`.
Additional services extend the absolute base Compose file, sharing the worker
image `${COMPOSE_PROJECT_NAME:-gateway}-worker`, environment and secrets. Set an
explicit `COMPOSE_PROJECT_NAME` for every deployment and use that same project
for every command. Every service has one replica, its own strict instance index
and the same limits. Start all rendered services with `up -d`; an explicit
`up backend worker` starts only instance 1. Never use `--scale` or manually run
additional worker containers. The lifecycle flock rejects a duplicate index,
while actual process count and resource allocation still require inspection.
Workers use `restart: no`; after verifying the original container and its
execution processes have exited, start the original fixed service explicitly.
Do not recreate a replacement while the previous container is still alive.

After all workers report ready, verify the actual project containers:

```bash
python3 vnext/scripts/render-runtime-config.py \
  --storage-layout /etc/gateway/storage-layout.json \
  --resource-profile /etc/gateway/resource-profile.json check-workers \
  --project "$COMPOSE_PROJECT_NAME"
```

This rejects missing/stopped services, duplicate replicas or indices, differing
worker images, automatic restart, and Docker memory/swap/CPU limits that differ
from the profile. Runtime preflight also checks each process's actual cgroups.
The approved small-input W2 correctness profile uses N1, each worker E16 GiB,
reserve8 GiB/M8 GiB/CPU2/swap0, backend2 GiB/CPU1, RS4 GiB/CPU2 and shared host
reserve8 GiB/CPU2: 46 GiB/CPU9 in total. It does not change the W1 default or
establish production/t4 capacity. The Compose test fixture selects this profile
explicitly for its two-worker journey.
