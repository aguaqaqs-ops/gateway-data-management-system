# Internal Build Environment Stabilization Handoff

状态：**PASS**

日期：2026-09-13

```yaml
internal_build_environment: pass
canonical_lock_identity: unchanged
dependency_versions_changed: no
p5_5b_semantics_changed: no
p5_5b_implementation_authorized: no
next_step: explicit_P5-5B-S1_implementation_authorization
new_explicit_authorization_required: yes
independent_review: pass
deferred: canonical_registry_migration_if_internal_index_changes_lock_source
```

## Entry freeze

| Item | Value |
| --- | --- |
| entry HEAD | `583e567397f9673624df885b2485c7ae4afc58a3` |
| tested implementation SHA | `c394db28fd43ab3aeabab7eda2d010df0dc3b3fb` |
| handoff documentation SHA | `996ab6c33a1152a14f91b23cbd8e7333c56f8248` |
| clean gate worktree | `/tmp/internal-build-gate.kuvoN8` (detached at implementation SHA) |

### Lockfile SHA256 (unchanged vs entry HEAD)

| Package | sha256 |
| --- | --- |
| backend | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| shared_kernel | `7be9e482910c3ede1c0a7f33d1eb08e9fc183468fca8570cf04bf023fb898` |
| repository_contracts | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| repository_client | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| repository_service | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |

## Environment audit (read-only)

| Variable | Entry state |
| --- | --- |
| `UV_DEFAULT_INDEX` / `UV_INDEX_URL` / `UV_INSECURE_HOST` | set (host provisioning only) |
| `PIP_INDEX_URL` / `PIP_TRUSTED_HOST` | set |
| `GATEWAY_DOCKER_BUILD_NETWORK` | unset (defaults: compose bridge / build-script host) |
| `GATEWAY_P2R1_CACHE_URL` | unset; default probe `172.17.0.1:18080` unreachable in gate env |
| P2R1 retained cache | unreachable; compose e2e uses build harness + dependency-base path |

Tools: uv 0.12.5, Python 3.13.5, Docker 26.1.5.

## Changed paths (implementation commit)

- `vnext/scripts/lib/gateway-index-env.sh` (new)
- `vnext/scripts/prepare-dev-dependencies.sh` (new)
- `vnext/scripts/run-tests.sh`
- `vnext/scripts/build-repository-service-image.sh`
- `vnext/backend/Dockerfile`
- `vnext/deploy/compose.yaml`
- `vnext/repository_service/tests/test_prepare_dev_dependencies_script.py` (new)
- `vnext/repository_service/tests/test_build_repository_service_image_script.py`
- `vnext/repository_service/tests/test_p2_r2_compose_integration.py`
- `vnext/repository_service/tests/test_distribution_boundaries.py`
- `vnext/backend/tests/test_backend_dockerfile_contract.py` (new)

## Path authority

| Path | Role | May change lock? |
| --- | --- | --- |
| `prepare-dev-dependencies.sh` | host `uv sync --locked` | no (post assert) |
| `run-tests.sh` | authoritative pytest | no (index stripped) |
| `build-repository-service-image.sh` | repository-service image | no |
| `deploy/compose.yaml` build args | backend/worker/rs bootstrap | no |
| Compose e2e harness | test client + rs image | no |

## Verification (clean worktree at `c394db28`)

### Focused / static

Five-package ruff/mypy with index isolation: **pass**.

### Authoritative `./vnext/scripts/run-tests.sh`

**Exit 0** | **4301 passed**, 1 skipped

| Phase | Passed |
| --- | ---: |
| shared_kernel | 242 |
| repository_contracts | 152 |
| repository_client | 154 |
| backend | 1894 |
| repository_service (parallel) | 1658 |
| repository_service (serial, incl. 8 Compose owners) | 201 |

`git diff --exit-code HEAD -- vnext/*/uv.lock` after run: **pass**.

### Docker (current-HEAD build)

`docker compose build backend worker` at implementation SHA: **pass**

| Image | ID |
| --- | --- |
| `deploy-backend:latest` | `sha256:ddd73f5c2d28...` |
| `deploy-worker:latest` | `sha256:ccad2ae3f6cf...` |

Manual `compose up` smoke with `chmod 0400` secret file failed (`PermissionError` on
`/run/secrets/repository-bearer-token`); **non-binding**. Compose e2e owners in authoritative
runner provide binding container evidence (8/8 in serial phase).

## Independent review

Bugbot findings-first review on implementation diff: **pass** (no bugs; no lock/registry
rewrite; no production runtime index leakage).

## Known prerequisites

- Gitignored `legacy/` must be present for backend parity tests in detached worktrees.
- `GATEWAY_DEV_DEPENDENCY_MODE=internal` requires explicit `UV_INDEX_URL` or
  `UV_DEFAULT_INDEX`; never automate internal sync without lockfile assert.
- Backend builder installs uv via astral.sh curl (rust base has no pip); runtime stage uses
  `UV_BOOTSTRAP_*` pip bootstrap (build-time only).
- Running `uv sync` in project dirs without stripping machine index can rewrite lock
  registry URLs — `test_distribution_boundaries` probe now strips index env.

## Cleanup

Gate worktree and temp secrets removed after docs commit.
