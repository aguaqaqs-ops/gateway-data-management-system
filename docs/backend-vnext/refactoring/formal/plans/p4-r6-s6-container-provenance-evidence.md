# P4-R6-S6 Container and Provenance Evidence

状态：**PASS — current-HEAD candidate 镜像重建、smoke、source 对照与八项 Compose owners 均通过**

日期：2026-09-13

Owner：Backend vNext Architecture Acceptance

上游：[P4-R6-S4 Independent Review](p4-r6-s4-independent-review.md)、
[P4-R6-S0 Independent Entry Acceptance](p4-r6-s0-independent-entry-acceptance.md)

```yaml
step_id: P4-R6-S6
tested_candidate_sha: 7fbddc731d304be719fb980d6c538a6b9cf6910f
gate_worktree: /tmp/p4-r6-gate.TTdACz
gate_worktree_clean: yes
source_test_digest: sha256:5f49d396981f1b75f43b092c71979c3f56ea8742e639db717316a5992028f941
source_test_file_count: 308
backend_src_image_file_count: 178
decision: pass
container_gate: pass
compose_eight_nodeids: pass_8_of_8
p4_r6_s4_f1: closed
```

## 1. Pre-build identity

| Item | Value |
| --- | --- |
| Candidate SHA | `7fbddc731d304be719fb980d6c538a6b9cf6910f` |
| Gate worktree porcelain | **empty** |
| `backend/uv.lock` | `sha256:21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| `repository_service/uv.lock` | `sha256:6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| `backend/Dockerfile` | `sha256:0ec5408bfef751ab1d6b0c478781b92c32b534c31e6ab7e3147b914d7671d74f` |
| `deploy/compose.yaml` | `sha256:113224e1ba968ed2ce588640d7fb07c7f8f2bb10ce136dd444f314dbe6591c81` |
| Source/test tree digest (git ls-files method) | `sha256:5f49d396981f1b75f43b092c71979c3f56ea8742e639db717316a5992028f941` (308 files) |

Bearer token 通过仓库外 `${P4_R6_SECRET_DIR}/repository-bearer-token` 注入；未写入仓库、未提交。

## 2. Image build

```bash
cd "${P4_R6_GATE_DIR}/vnext/deploy"
export GATEWAY_P2R2_BEARER_TOKEN_FILE="${P4_R6_SECRET_DIR}/repository-bearer-token"
export GATEWAY_BACKEND_SESSION_FILE="${P4_R6_GATE_DIR}/vnext/deploy/config/session.json"
docker compose build backend worker
```

| Image | ID |
| --- | --- |
| `deploy-backend:latest` | `sha256:90cb348c524d5969d8e4475a7738e897eebdfa994dfc6d94ae7cd26b1e2513cf` |
| `deploy-worker:latest` | `sha256:99c8f93a38c8646866c7da643be027949add83ee7047c58ea8b04bf46568edb4` |
| `gateway-repository-service:local` (Compose owners) | `sha256:e274d5628c904c99eae1624caf622d969d3560b0b3a3415d5742d4d3a9c49357` |

**Build exit code:** 0

## 3. Image vs host source consistency

Normalized per-file SHA-256 over sorted `**/*.py` under `vnext/backend/src` on host vs
`/app/backend/src` in backend and worker images: **178 files, zero mismatches**.

## 4. Smoke (backend + worker + repository-service)

```bash
docker compose up -d repository-service backend worker
docker compose stop -t 180 worker
docker inspect "${WORKER_CONTAINER}" --format '{{.State.Status}} {{.State.ExitCode}}'
docker compose down
```

| Check | Result |
| --- | --- |
| `healthz` / `readyz` | 200 / 200 |
| Worker `ExitCode` (inspected, not inferred) | **0** |
| Log sequence | `worker_ready` → `drain_started` → `worker_exited` |
| Redaction (host path, bearer, session, payload, SQL, lease) | **0 hits** |
| Control DB `PRAGMA quick_check` | `ok` |
| Operations migration/schema rows | present |

**C4 exit code:** 0

## 5. Eight Compose owner nodeids

```bash
cd "${P4_R6_GATE_DIR}/vnext/repository_service"
env -u UV_DEFAULT_INDEX ... uv run --locked pytest -q -n 0 <eight nodeids>
```

| # | Node ID | Result |
| ---: | --- | --- |
| 1 | `test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | pass |
| 2 | `test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | pass |
| 3 | `test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | pass |
| 4 | `test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | pass |
| 5 | `test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up` | pass |
| 6 | `test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up` | pass |
| 7 | `test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up` | pass |
| 8 | `test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up` | pass |

**Result:** 8 passed in 153.50s; pytest exit 0.

## 6. Historical diagnostics (non-binding)

| Event | Cause | Binding? |
| --- | --- | --- |
| First authoritative runner (uncommitted worktree) | `ProvenanceError: worktree is dirty` on 8 Compose owners | no — superseded by sealed commit + clean worktree |
| First smoke attempt | Missing `GATEWAY_P2R2_BEARER_TOKEN_FILE` | no — superseded by repo-external secret wiring |
| Gate worktree first `run-tests.sh` | Missing gitignored `legacy/` oracle | no — environment sync before rerun |

## 7. Environment note

Gate worktree at sealed candidate does not include gitignored `/legacy/`. Authoritative
`backend` parity tests require syncing `legacy/` from the development tree before
`run-tests.sh`. This does not affect `git status --porcelain` or Compose image provenance.
