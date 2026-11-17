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

The P2-R1 probe launcher, systemd runner units, and `repository-probe` Compose service have been removed. Only the retained dependency cache and `Dockerfile.dependency-base` remain active.

## Remote development host (container gate)

Verified development host: `10.10.60.4` (SSH user `tmpuser`).

Prior provenance records are superseded. Current gate evidence:

```text
test: tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
result: PASSED (27.44s)
directed_probe: v15 leftover/FIFO/symlink/receipt + owner/mode + restart
compose_project: gateway-p2r9-e-1c12969750e6
cache: remote http://172.17.0.1:18080 (HTTP 200); image loaded locally
validated_code_sha: e78b564a112b2a040740e3e07d7e6f04329d06e9
container_validated_code_sha: e78b564a112b2a040740e3e07d7e6f04329d06e9
build_input_revision: e78b564a112b2a040740e3e07d7e6f04329d06e9
source_tree_sha256: sha256:2cc377e74be2ab342ee09028ce54ff77a4690c5a5f12ce633959bfe6643172a2
image_id: sha256:87e4e908bfa63370033256b380c6582c39fb6888749131633d5e856ae649a007
image_label gateway.p2r1.source-tree-sha256: sha256:2cc377e74be2ab342ee09028ce54ff77a4690c5a5f12ce633959bfe6643172a2
image_label org.opencontainers.image.revision: e78b564a112b2a040740e3e07d7e6f04329d06e9
S3 ready: yes
full_record: docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md
```

Superseded runs:

```text
validated_code_sha: 13ec2137d7ed8f3da406bf550da68647d2536c77
compose_project: gateway-p2r4-s10-e1333a00185a
reason: superseded_by_e78b564_step_e
validated_code_sha: cb1ef42db7dd4957d20cdc4ce3b61cb35c7b9596
compose_project: gateway-p2r4-s10-7720cf769b61
reason: commit_b_touched_repository_service_readme; build context drift from HEAD
compose_project: gateway-p2r4-s10-7da182fe355e
reason: build_input_revision a748818 not locally resolvable; source_tree mismatch
compose_project: gateway-p2r4-s10-39dfebc86b19
reason: provenance_unresolved
```

Provenance documentation commits must not modify `vnext/repository_service/**` or
`vnext/repository_contracts/**`; those paths are included in the build-context
digest and will invalidate recorded image provenance.

### Candidate sealing and SHA-writing rules

Treat the code candidate and the commit that records its provenance as two different
objects:

1. Finish every build-input change first, including tests and README files under
   `vnext/repository_service/` or `vnext/repository_contracts/`, and commit them as the
   candidate.
2. Capture the candidate SHA outside the candidate's tracked build-input files. A
   commit cannot contain its own final SHA; do not add a literal SHA to a build-input
   README after the gate and continue calling the old image current.
3. Do not amend, rebase, squash, or otherwise replace the candidate after image build
   or gate execution. Any new build-input commit invalidates the previous provenance.
4. Run the remote gate from a new detached worktree at the literal candidate SHA. Do
   not force-checkout over an active development worktree and do not fetch into a
   branch that is currently checked out.
5. After the gate passes, write the literal candidate SHA, digests, image ID and result
   only to a provenance path outside the build-context digest. Record that later
   documentation commit separately as `provenance_documentation_sha` in the external
   handoff, review record, or a tag created after the commit. The provenance commit
   cannot contain its own final SHA either; do not create another commit merely to
   backfill the previous documentation commit's SHA.

The expected history is therefore:

```text
candidate commit (validated_code_sha == container_validated_code_sha)
  -> image build and container gate at that exact SHA
  -> provenance-only commit outside repository_service/** and repository_contracts/**
```

Local gate hosts that cannot reach `172.17.0.1:18080` should treat container gate
reruns as remote-only; the failure mode is infrastructure (cache unreachable), not
application regression.

### Syncing source to the remote host

Do **not** sync the entire repository or full `vnext/` tree. `vnext/rust/` is about
24 GB and is not required for repository-service Compose gates.

**Authoritative path: git bundle + exact SHA checkout**

Formal container gate provenance requires a remote Git checkout at the candidate
SHA. File-only sync cannot produce a matching `build_input_revision`.

```sh
# Local: seal and bundle the candidate branch tip
CANDIDATE_SHA=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"
test "$(git rev-parse phase1/gate-ownership-repair)" = "$CANDIDATE_SHA"
git bundle create /tmp/gate-candidate.bundle phase1/gate-ownership-repair
git bundle verify /tmp/gate-candidate.bundle
scp /tmp/gate-candidate.bundle tmpuser@10.10.60.4:/tmp/gate-candidate.bundle

# Remote: fetch into a dedicated ref and create a new detached gate worktree.
# Replace the value below with the literal local CANDIDATE_SHA.
ssh -t tmpuser@10.10.60.4
cd /home/tmpuser/gateway-data-management-system
CANDIDATE_SHA='<candidate-sha>'
CANDIDATE_SHORT=$(git rev-parse --short=12 "$CANDIDATE_SHA")
GATE_WORKTREE="/home/tmpuser/gateway-gate-${CANDIDATE_SHORT}"
git fetch /tmp/gate-candidate.bundle \
  +refs/heads/phase1/gate-ownership-repair:refs/gate/candidate
test "$(git rev-parse refs/gate/candidate)" = "$CANDIDATE_SHA"
test ! -e "$GATE_WORKTREE"
git worktree add --detach "$GATE_WORKTREE" "$CANDIDATE_SHA"
cd "$GATE_WORKTREE"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
test -z "$(git status --porcelain)"
```

When a shared remote is available, `git push` + `git fetch origin` is equivalent to
the bundle fetch above. Do not use ad-hoc `git init` plus tar/rsync overlay as the
gate source of truth.

One-time remote setup when the directory is not yet a clone:

```sh
ssh -t tmpuser@10.10.60.4
sudo pacman -S --needed git
git clone <origin-url> /home/tmpuser/gateway-data-management-system
```

**Never include `vnext/rust`** in any sync.

Before running the gate, compare the versioned identity JSON on local and remote.
Abort if any field differs:

```sh
python3 vnext/repository_service/tests/support/build_context_digest.py identity
```

Diagnostic-only file sync (non-provenance): `rsync` may help inspect files on the
remote host, but it must not be used to produce formal container gate evidence.
Only a Git checkout at `<candidate-sha>` satisfies `build_input_revision`.

Additional remote prerequisites:

- **Git metadata**: `compose_build_harness` resolves `build-input-revision` via
  `git log`. The remote checkout must be a normal clone/checkout at the candidate
  SHA.
- **S10 e2e chown**: the Compose harness resolves the image `gateway` UID/GID and, when a
  development user in an unprivileged LXC cannot perform the host-side `chown`, uses a
  short-lived root helper container against only the token-file parent directory. The
  runner therefore only needs access to the Docker daemon; it does not need interactive
  `sudo` for this step.

For other operator-only procedures that genuinely require root, use an interactive sudo prompt
only. Do not pipe passwords through `ssh`, shell history, documentation, or passwordless sudo
grants for pytest; the current S10 Compose harness does not require sudo.

```sh
ssh -t tmpuser@10.10.60.4
cd /home/tmpuser/gateway-data-management-system/vnext/repository_service
uv sync
sudo uv run pytest tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay \
  -m serial -n 0 -v
```

When the gate runs as root via `sudo`, configure Git safe-directory once on the
remote host:

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

Formal image production uses `vnext/scripts/build-repository-service-image.sh`, which
calls the canonical helper once and passes three independent build args. Diagnostic
`docker build` must consume the same helper; do not use `git archive HEAD` or a
single `BUILD_REVISION` for both candidate and build-input:

```sh
IDENTITY_JSON="$(python3 repository_service/tests/support/build_context_digest.py identity)"
CANDIDATE_SHA="$(printf '%s' "$IDENTITY_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["candidate_sha"])')"
BUILD_INPUT_REVISION="$(printf '%s' "$IDENTITY_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["build_input_revision"])')"
SOURCE_TREE_SHA256="$(printf '%s' "$IDENTITY_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["source_tree_sha256"])')"

docker build \
  --network=host \
  --build-arg DOLT_DOWNLOAD_URL=http://172.17.0.1:18080/dolt/2.1.11/dolt-linux-amd64.tar.gz \
  --build-arg UV_BOOTSTRAP_INDEX_URL=http://172.17.0.1:18080/uv/simple \
  --build-arg UV_BOOTSTRAP_TRUSTED_HOST=172.17.0.1 \
  --build-arg HTTP_PROXY \
  --build-arg HTTPS_PROXY \
  --build-arg NO_PROXY=172.17.0.1,localhost,127.0.0.1 \
  --build-arg CANDIDATE_SHA="$CANDIDATE_SHA" \
  --build-arg BUILD_INPUT_REVISION="$BUILD_INPUT_REVISION" \
  --build-arg SOURCE_TREE_SHA256="$SOURCE_TREE_SHA256" \
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
  --build-arg CANDIDATE_SHA="$CANDIDATE_SHA" \
  --build-arg BUILD_INPUT_REVISION="$BUILD_INPUT_REVISION" \
  --build-arg SOURCE_TREE_SHA256="$SOURCE_TREE_SHA256" \
  --build-arg MYSQL_CONNECTOR_VERSION=9.7.0 \
  --build-arg PYARROW_VERSION=25.0.0 \
  --tag gateway-p2r1-repository:dev \
  --file repository_service/Dockerfile .
```
