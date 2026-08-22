# P3-R7-S6 Independent Owner, Import, Digest and Recovery Review

状态：**S6 independent review complete；无未处理 P1/P2 finding**

日期：2026-08-22

本记录对 R7 mutation planner、Dolt renderer 和 external reference executor 执行独立复核。
复核只依赖公开 contracts、已提交 source tree、tests 和下列命令，不依赖 S1-S5 implementer
explanations。当前候选为 clean committed source tip：

```yaml
reviewed_source_sha: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
worktree: clean_committed_source_before_s7_acceptance_docs
```

## 1. Review boundary

独立复核覆盖：

- `mutation_planning` 与 `external_target_sync` owner DAG，以及 forbidden
  HTTP/application、flow、Repository/Dolt、R6 private、legacy、provider implementation、
  test-support imports；
- plan identity binding（source/base/projection/renderer/policy/threshold/encoding digests）、
  canonical table/key/operation ordering、mixed `REBUILD_TABLE` / `PATCH_DML` / `NOOP` plans；
- initial/empty baselines、table add/remove、schema/key/projection transitions、destructive
  confirmation、threshold boundaries、unsupported canonical values；
- ChangeSet closure manifest/digest binding、SQL/checkpoint exclusion、canonical JSON parsing、
  no partial public closure publication；
- Dolt renderer identifier/value encoding、deterministic `replay.sql`、replay-size admission、
  renderer capability declaration；
- reference executor `PREPARE -> APPLYING -> VERIFYING -> SUCCEEDED | FAILED | UNKNOWN_OUTCOME`
  state machine、transaction rollback、exact affected-row checks、ledger/readback reconciliation
  and idempotent retry；
- unit marker 分类及 Dolt/process/network/fixed-timeout absence。

Out of scope：真实 Repository/Dolt execution、P5B confirmation/finalize、P4 durable operation
state、production external adapters、cache/retention/GC、Rust renderer/provider optimization、
benchmark numeric gates and inherited image gate。

## 2. Independent findings register

| ID | Severity / disposition | Evidence |
| --- | --- | --- |
| `S3-F001` | Unsupported canonical key values / **P2 closed in S3** | Planner preflight checks both key and image cells and returns `TARGET_CAPABILITY_UNSUPPORTED` before closure construction. |
| `S3-F002` | Mixed-plan closure summary / **P2 closed in S3** | Closure construction retains every per-table summary, including `NOOP`. |
| `S3-F003` | Closure parser malformed column entries / **P2 closed in S3** | Parser rejects every non-object entry explicitly. |
| `S3-001` | Artifact-store orphan reclamation / **accepted defer** | `ArtifactStorePort` has no delete/transaction primitive. A later store failure may leave opaque unreachable bytes, but no public closure ref is returned. Reclamation remains ADR 0012 lifecycle work. |
| `S6-001` | Owner/import boundary / **pass** | Architecture DAG passes. `mutation_planning` imports only `storage_projection` public contracts plus artifact ports. `external_target_sync` imports only public `mutation_planning` contracts; no planner-private modules, flow, Repository/Dolt, legacy or test-support edge was added. |
| `S6-002` | Plan identity and closure digest binding / **pass** | `test_mutation_planning.py` covers mixed plans, threshold boundaries, destructive confirmation, idempotency conflict, closure digest stability and malformed closure rejection. |
| `S6-003` | Renderer safety and replay admission / **pass** | `test_dolt_renderer.py` covers golden SQL fixtures, capability failures, source-literal anomaly and replay-size rejection. Renderer uses controlled identifier quoting and canonical value encoding; no shell interpolation. |
| `S6-004` | Executor rollback, unknown outcome and reconcile / **pass** | `test_external_target_executor.py` covers rollback on drift, `UNKNOWN_OUTCOME`, reconcile-then-retry, idempotent reuse and readback mismatch. Checkpoint export/import remains test-only JSON. |
| `S6-005` | Forbidden P4/P5 integration / **pass** | No HTTP/Workspace/Submit/Operation Runtime import, no durable checkpoint/confirmation persistence and no Repository/Dolt execution adapter in R7 capabilities. |

No additional P1/P2 finding, digest owner collision, resource-cap bypass, partial success
publication, blind unknown-outcome replay, unsupported value stringification, automatic provider
fallback or incorrect marker remains.

## 3. Gate evidence

| Check | Result |
| --- | --- |
| focused R7 mutation/renderer/executor/architecture unit gate | **PASS**；98 passed |
| `cd vnext/backend && uv run pytest -q -m unit` | **PASS**；848 passed，1 existing Starlette deprecation warning |
| `cd vnext/backend && uv run ruff check .` | **PASS** |
| `cd vnext/backend && uv run mypy` | **PASS**；188 source files |
| other four Python packages `uv run ruff check .` / `uv run mypy` | **PASS**；mypy 26 / 15 / 195 / 34 source files |
| `git diff --check` | **PASS** |

Focused command：

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_mutation_contracts.py tests/test_mutation_planning.py \
  tests/test_dolt_renderer.py tests/test_external_target_contracts.py \
  tests/test_external_target_executor.py tests/test_architecture.py
```

所有 R7 测试使用 in-memory store 或 fixture bytes；未创建 Dolt repository，未启动 process、
shell/SQL execution、网络或 fixed-timeout fixture，因此不需要 `integration` 或 `serial -n 0`
rerun。S6 未触碰依赖、Dockerfile、Compose、deployment 或 container-only runtime boundary。

## 4. Boundary dispositions

| Area | Result | Evidence / disposition |
| --- | --- | --- |
| Planner eligibility and publication | **Pass** | Threshold, destructive confirmation, unsupported canonical values and resource caps fail closed before public closure publication. |
| Closure identity and atomicity | **Pass with deferred lifecycle** | One ChangeSet maps to one atomic renderer transaction; no partial table success is published. Opaque orphan reclamation remains ADR 0012 deferred work. |
| Renderer determinism and safety | **Pass** | Golden SQL fixtures and capability-failure cases prove deterministic replay generation and bounded admission. |
| Executor recovery | **Pass** | Unknown outcome requires reconcile before retry; duplicate identity with equal fingerprint reuses existing result. |
| Owner/import graph | **Pass** | `mutation_planning -> storage_projection`; `external_target_sync -> mutation_planning` public contracts only. |

## 5. Deferred and reopen register

Carry forward：真实 Repository/Dolt execution、P5B confirmation/finalize、P4/P5 durable operation
state、production external adapters、multi-target persistence、cache/retention/GC、orphan
reclamation under ADR 0012、Rust renderer/provider optimization、benchmark numeric gates and
inherited R5 Rust/Cargo backend image gate。

Reopen R7 if forbidden imports appear, presentation artifacts become mutation authority, plan
identity can drift, partial effects publish, unknown outcomes blind-replay, unsupported values
stringify, a new service/helper/security principal is introduced or durable P4/P5 state enters
the R7 capability.

## 6. Tested source inventory

```text
vnext/backend/src/gateway_backend/capabilities/mutation_planning/
vnext/backend/src/gateway_backend/capabilities/external_target_sync/
vnext/backend/tests/test_mutation_contracts.py
vnext/backend/tests/test_mutation_planning.py
vnext/backend/tests/test_dolt_renderer.py
vnext/backend/tests/test_external_target_contracts.py
vnext/backend/tests/test_external_target_executor.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/support/mutation_contracts.py
vnext/backend/tests/support/mutation_renderer_fixtures.py
vnext/backend/tests/support/external_target_executor.py
vnext/fixtures/golden/mutation/
```

## 7. Decision

**S6 PASS.** 当前候选无 open P1/P2；S3 planner findings 保持关闭，`S3-001` 明确 accepted
defer。S7 可在新 conversation 对同一 sealed source candidate 重跑 module gate 并刷新 handoff；
本记录不宣称已通过 container gate 或 production gate，也不改变全局实现授权。

```yaml
p3_r7_s6: completed
p3_r7_s6_exit: pass
p3_r7_s6_reviewed_source_sha: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
p3_r7_s6_worktree: clean_committed_source_before_s7_acceptance_docs
p3_r7_s6_deferred: orphan_reclamation_under_adr_0012;inherited_image_gate
p3_r7_implementation_authorized: no
p3_implementation_authorized: no
```
