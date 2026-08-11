# P2-R1 persistent dependency cache

This is a development-host cache for the repository-service target image. It
is intentionally outside Docker images, containers, and named volumes so that
matrix cleanup does not remove it. The cache is served only on the Docker
bridge gateway (`172.17.0.1:18080`) by
`gateway-p2r1-dependency-cache.service`.

The current pinned artifact is:

```text
/dolt/2.1.11/dolt-linux-amd64.tar.gz
```

The source Dockerfile verifies the downloaded Dolt archive with the pinned
SHA-256 before extraction and verifies the repository-service lockfile. The
dependency-base Dockerfile additionally requires `DOLT_BINARY_SHA256` for the
preloaded binary, verifies the cached uv wheel and lockfile, checks exact Dolt
and uv versions, and runs `uv pip check` plus package imports. Obtain the
binary checksum from the retained cache with `sha256sum offline-assets/dolt`
and pass it explicitly when rebuilding that base image.

The remote development host also retains a dependency-base image containing
the lock-resolved Python 3.14 environment, Dolt 2.1.11 and uv 0.11.28. It is a
build accelerator, not a production release image; keep it when cleaning probe
containers and named volumes.

The verified retained image tags from the 2026-08-02 build are:

```text
gateway-p2r1-repository:dependency-base-python3.14-dolt2.1.11-uv0.11.28
gateway-p2r1-repository:20260802-cached
```

The cache also retains the exact uv 0.11.28 wheel under both its versioned
artifact path and the small PEP 503 bootstrap index at `/uv/simple/uv/`.

The service and cache directory are persistent across Docker restarts and host
reboots. Do not remove them as part of probe cleanup. Add a new versioned
artifact directory for dependency updates; retain old versions until no active
build references them.

The formal probe's test named volume, matrix container and temporary build
contexts may be removed after results are copied. The two image tags above and
the versioned cache artifacts must remain available for subsequent source-only
rebuilds.

Probe/matrix cleanup must not remove the retained cache artifacts or dependency-base
image tags documented above. P2-R4 S10 Compose import/restart gate reuses the same cache
contract through `vnext/scripts/build-repository-service-image.sh`; do not run uncached
`docker compose build` on network-constrained hosts.

## Delegated cgroup setup

The target image does not create host cgroups and does not run privileged. The
authoritative path is an installed systemd service. `Delegate=yes` is on the
service, never on the `.slice`; the launcher obtains the slice's actual
`ControlGroup` dynamically and does not derive a path from the unit name.

```sh
sudo install -m 0644 gateway-p2r1.slice gateway-p2r1-runner@.service \
  /etc/systemd/system/
sudo install -m 0755 p2r1-target-launcher.sh \
  /usr/local/libexec/gateway-p2r1-target-launcher.sh
sudo systemctl daemon-reload
```

The service uses `DelegateSubgroup=supervisor` for its own supervisor process.
Docker's systemd driver receives only the valid per-run slice unit name as
`cgroup_parent`; it cannot receive a service `ControlGroup` filesystem path.
The launcher obtains both the service and per-run slice `ControlGroup` values
for ancestry evidence, then requires the Docker scope to be a sibling of the
runner service under that per-run slice. A container placed inside the runner
service subtree or under another slice is rejected.

The launcher starts one gated target container, resolves its real PID and
exact Docker cgroup, then creates this topology inside that cgroup before
releasing the gate:

```text
container delegated root (empty, memory+pids enabled)
├── supervisor (target gate/matrix PID)
└── samples (empty, memory+pids enabled)
    └── gateway-p2r1-<sample> (worker PID)
```

The complete verified ancestry is:

```text
gateway-p2r1.slice
└── gateway-p2r1-<run>.slice
    ├── gateway-p2r1-runner@<run>.service
    └── docker-<id>.scope
        ├── supervisor
        └── samples
```

All direct container PIDs are moved to `supervisor` before either the
delegated root or `samples` enables controllers. The target receives the
launcher-written, read-only `cgroup-layout.json`; formal matrix code uses its
`samples` path and never infers a sample root from the current supervisor
process. The target gate propagates the verified supervisor ControlGroup to
the matrix process. Any topology, permission, migration or cleanup failure
stops the run.

The Compose profile uses `cgroup: host`, the dynamic per-run slice name as
`cgroup_parent`, and a read-write bind mount of the resolved per-run slice at
`/sys/fs/cgroup/gateway-p2r1`.
The provenance manifest and target gate are separate read-only/controlled
mounts. `cgroup: private`, a static bind mount, or a direct `docker compose`
invocation is not formal delegation evidence.

The launcher is the authoritative target-container path. Each invocation gets
a validated unique Compose project name (`gateway-p2r1-<run-id>`); every
`up`, `ps`, `logs`, and `down` command carries that project name, so cleanup
cannot stop `backend`, `worker`, another project, or a concurrent probe:

```sh
cd /root/gateway-data-management-system
vnext/deploy/p2r1-cache/p2r1-target-launcher.sh \
  --output /var/lib/gateway/repository/audit-rerun/p2-r1.jsonl \
  --image-digest sha256:<image-id> \
  --build-revision <source-revision> \
  --cache-condition retained-dependency-cache
```

The launcher obtains the immutable image ID and labels from Docker, requires a
clean worktree, creates a read-only provenance manifest, and passes verified
metadata into the container. It rejects dirty source, stale labels, missing
source-tree/lock/version labels, missing manifest, and non-systemd Docker.
Do not replace a failed preflight with `privileged` or a host-wide cgroup mount.

The matrix writes its output inside the probe container/volume using the
absolute `--output` path. The launcher first stops and reaps the target, then
copies the raw JSONL, summary JSON and Markdown report to the same host
destination using no-replace publication and fsync barriers. Exported raw
JSONL is parsed line-by-line and failed targets must end with an
`incomplete/no-go` terminal record. Only after all three artifacts pass size,
digest and publication checks does cleanup run `down -v` for the unique
project. If the target or export fails, cleanup omits `-v` and retains the
source volume plus its staging path for recovery. Cache images and dependency
artifacts are not removed.

Failed runs are an explicit recovery quarantine, not a successful cleanup. The
launcher prints the exact Compose project, retained volume ID(s), and staging
path. After copying or otherwise recovering the evidence, remove only that
project's retained volume and verify its container, network, volume, and cgroup
objects are gone; do not use a shared-project `down --remove-orphans` command.

## Remote development host (container gate)

Verified development host: `10.10.60.4` (SSH user `tmpuser`).

P2-R4 S10 Compose import/restart gate passed on 2026-08-11 with full provenance:

```text
test: tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
result: PASSED (63s)
compose_project: gateway-p2r4-s10-7da182fe355e
cache: http://172.17.0.1:18080 (HTTP 200)
validated_code_sha: closure commit on phase1/gate-ownership-repair (see git rev-parse HEAD)
container_validated_code_sha: a74881839be7d83aff36878ca8cba39ad56b29b3
build_input_revision: a74881839be7d83aff36878ca8cba39ad56b29b3
source_tree_sha256: sha256:253746e0344fe08782ab9b9b5db383fa40f9590be8d81b91a179848652bcb750
image_id: sha256:8ece8d619091689cfa8d371483098a6952076d36e84ff4783e317ceb30aad671
image_label gateway.p2r1.source-tree-sha256: sha256:253746e0344fe08782ab9b9b5db383fa40f9590be8d81b91a179848652bcb750
image_label org.opencontainers.image.revision: a74881839be7d83aff36878ca8cba39ad56b29b3
```

Superseded prior remote run `gateway-p2r4-s10-39dfebc86b19` (provenance_unresolved: missing
`validated_code_sha`, `build_input_revision`, `source_tree_sha256`, and `image_id`).

Local gate hosts that cannot reach `172.17.0.1:18080` should treat container gate
reruns as remote-only; the failure mode is infrastructure (cache unreachable), not
application regression.

### Syncing source to the remote host

Do **not** sync the entire repository or full `vnext/` tree. `vnext/rust/` is about
24 GB and is not required for repository-service Compose gates. Copying it over SSH
stalls for many minutes and provides no gate value.

Sync only the packages and paths required for repository-service gates. Prefer
`rsync --delete` over tar overlay so removed local files do not linger on the remote
host:

```sh
rsync -az --delete \
  --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
  --exclude='.mypy_cache' --exclude='.ruff_cache' \
  --exclude='vnext/rust' \
  vnext/repository_service \
  vnext/repository_contracts \
  vnext/shared_kernel \
  vnext/repository_client \
  vnext/deploy \
  vnext/scripts \
  vnext/fixtures \
  AGENTS.md \
  tmpuser@10.10.60.4:/home/tmpuser/gateway-data-management-system/
```

**Never include `vnext/rust`** in tar or rsync.

Before running the gate, compare the Docker build-input digest on local and remote.
Both hosts must report the same value:

```sh
uv run python vnext/repository_service/tests/support/build_context_digest.py source-tree-sha256
```

Use delete-replace sync (not tar overlay) so removed local files do not linger remotely.
When `rsync` is unavailable, extract into a staging directory and `mv` each synced path
over the remote destination after `rm -rf` of the previous copy.

Additional remote prerequisites:

- **Git metadata**: `compose_build_harness` resolves `build-input-revision` via
  `git log`. The remote checkout must be a normal clone/checkout at the candidate
  SHA. Do not use ad-hoc `git init` overlays on top of rsynced trees.
- **S10 e2e chown**: `test_import_compose_e2e` calls `os.chown(token, gateway_uid,
  gateway_gid)`; run the pytest node with `sudo` on the remote host.

Default path: use an interactive sudo prompt. Do not pipe passwords through `ssh`,
shell history, or documentation examples.

```sh
ssh -t tmpuser@10.10.60.4
cd /home/tmpuser/gateway-data-management-system/vnext/repository_service
uv sync
sudo uv run pytest tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay \
  -m serial -n 0 -v
```

Optional: install the minimal NOPASSWD rule in
[`sudoers-compose-e2e.example`](sudoers-compose-e2e.example) with `visudo`, verify
with `sudo -n`, and then run the same pytest command without a password prompt.
Never embed credentials in scripts, logs, or runbooks.

When `sudo` is required and the gate runs as root, configure Git safe-directory once on
the remote host:

```sh
sudo git config --global --add safe.directory /home/tmpuser/gateway-data-management-system
```

## Remote host setup

Run as root on the development host:

```sh
install -d -o gateway-p2r1-cache -g gateway-p2r1-cache \
  /var/lib/gateway/p2r1-dependency-cache/dolt/2.1.11
install -m 0644 dolt-linux-amd64.tar.gz \
  /var/lib/gateway/p2r1-dependency-cache/dolt/2.1.11/dolt-linux-amd64.tar.gz
install -m 0644 gateway-p2r1-dependency-cache.service \
  /etc/systemd/system/gateway-p2r1-dependency-cache.service
systemctl daemon-reload
systemctl enable --now gateway-p2r1-dependency-cache.service
```

The `gateway-p2r1-cache` system user must own the cache directory. The service
is read-only and has no write access outside that directory.

## Cached build

From the `vnext` Docker build context, pass the cache URL and preserve the
Docker service proxy for PyPI/uv dependencies:

```sh
docker build \
  --network=host \
  --build-arg DOLT_DOWNLOAD_URL=http://172.17.0.1:18080/dolt/2.1.11/dolt-linux-amd64.tar.gz \
  --build-arg UV_BOOTSTRAP_INDEX_URL=http://172.17.0.1:18080/uv/simple \
  --build-arg UV_BOOTSTRAP_TRUSTED_HOST=172.17.0.1 \
  --build-arg HTTP_PROXY \
  --build-arg HTTPS_PROXY \
  --build-arg NO_PROXY=172.17.0.1,localhost,127.0.0.1 \
  --build-arg BUILD_REVISION="$(git rev-parse HEAD)" \
  --build-arg SOURCE_TREE_SHA256="sha256:$(git archive HEAD | sha256sum | cut -d' ' -f1)" \
  --build-arg MYSQL_CONNECTOR_VERSION=9.7.0 \
  --build-arg PYARROW_VERSION=25.0.0 \
  --tag gateway-p2r1-repository:dev \
  --file repository_service/Dockerfile .
```

`UV_BOOTSTRAP_INDEX_URL` remains public by default and only controls installing
the pinned uv bootstrap wheel. The Docker layer created by
`uv sync --frozen` is retained by Docker for source-only rebuilds. A future
full Python package mirror can be wired to uv separately without changing the
artifact-cache contract. When the persistent dependency-base image is
available, the formal Dockerfile can reuse it without network downloads:

```sh
docker build --network=host \
  --build-arg BASE_IMAGE=gateway-p2r1-repository:dependency-base-python3.14-dolt2.1.11-uv0.11.28 \
  --build-arg USE_PRELOADED_DEPENDENCIES=1 \
  --build-arg BUILD_REVISION="$(git rev-parse HEAD)" \
  --build-arg SOURCE_TREE_SHA256="sha256:$(git archive HEAD | sha256sum | cut -d' ' -f1)" \
  --build-arg MYSQL_CONNECTOR_VERSION=9.7.0 \
  --build-arg PYARROW_VERSION=25.0.0 \
  --tag gateway-p2r1-repository:dev \
  --file repository_service/Dockerfile .
```

## Probe commands

Local source checks must use an explicit diagnostic subset:

```sh
uv run --offline --no-sync python -m gateway_repository_service.matrix \
  --diagnostic --workloads W0 \
  --output /tmp/p2-r1-diagnostic-w0.jsonl
```

The v7 historical formal entry point produced 132 records and remains frozen.
The current formal entry point is the explicit v8 A-only command below: it
produces 66 records (30 normal + 36 scaling), requires the delegated cgroup and
verified image/build metadata, and must use a new `audit-rerun` path without
overwriting historical artifacts:

```sh
vnext/deploy/p2r1-cache/p2r1-target-launcher.sh \
  --output /var/lib/gateway/repository/audit-rerun/p2-r1.jsonl \
  --v8-formal \
  --runs 5
```

Candidate B is reserved in v8 and may only be exercised through the separate
diagnostic-only `--reserved-b-w0-smoke` entry point; it is not part of the 66
records and cannot select a provider.

Before formal review, Candidate A can be exercised through the matching
diagnostic-only v8 smoke. It uses the v8 1 MiB batch bound and 8 GiB sample
ceiling, writes one W0 record, and cannot select a provider:

```sh
vnext/deploy/p2r1-cache/p2r1-target-launcher.sh \
  --output /var/lib/gateway/repository/v8-smoke/a-w0.jsonl \
  --v8-a-w0-smoke
```
