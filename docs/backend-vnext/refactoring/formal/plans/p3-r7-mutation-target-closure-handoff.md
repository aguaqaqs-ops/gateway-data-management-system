# P3-R7 Mutation and Target Closure Handoff

状态：`pass`（R7 module gate；P4/P5 entry boundary。不是 Phase 3 全部实现授权，不含 flow/production
integration、真实 Repository/Dolt effect 或 durable operation state）

日期：2026-08-22

Owner：Backend vNext Canonical Storage / Mutation Planner / External Target Sync

本文封存 R7 的 source/module gate、公开 mutation/change-set/renderer/executor seam、独立 review
closure、已知 deferred items 和 P4/P5 prerequisites。R7 只交付 target-neutral
`StorageMutationPlan`、`ChangeSetArtifact`、deterministic replay SQL 和 in-memory reference
executor；`p3_implementation_authorized` 仍为 `no`。

设计基线：[P3-R7 Mutation and Target Closure Design Baseline](p3-r7-mutation-target-closure-design.md)

过程证据：R7 执行计划、S0 freeze 与 S6 review 已归档；恢复见 tag
`docs/p3-p4-cleanup-pre-20260823` 与 [p3-p4-cleanup-manifest.yaml](p3-p4-cleanup-manifest.yaml)。

上游 handoff：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)、[P3-R6 Risk, Surface and Bundle Handoff](p3-r6-risk-surface-bundle-handoff.md)

```yaml
handoff_kind: p3_r7_mutation_target_closure
round: P3-R7-S7
p3_r7_exit: pass
p3_implementation_authorized: no
worktree_at_validated_tip: clean_committed_on_b0261cb
validated_code_sha: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
s0_entry_sha: e09ff32cc3562b744ff5718357a529c7b8ce3e6f
s6_reviewed_tip: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
s7_tests_rerun: yes
container_gate: inherited_required_deferred_docker_daemon_unavailable
benchmark: measurement_only_no_gate
legacy_oracle_gap: inherited_known_external_fixture_gap
upstream_applicability_re_attested_sha: f2d48d876c40dd918878a6e5215c57daf7920766
r7_rework_required: no
handoff_documentation_sha: pending_handoff_documentation_commit
```

`validated_code_sha` 是 S7 运行 gates 的 source tip。S7 acceptance record 和本 handoff 是随后
新增的文档变化，未改变该 source candidate；`handoff_documentation_sha` 在本次文档修正提交完成
后再回填。`p3_r7_exit: pass` 表示 R7 source/module gate 的 staged implementation surface 通过；
inherited R5 Rust/Cargo backend image/container gate 仍是必须执行的 deferred gate，不被该 pass
隐式关闭。

## 1. Gate identity

```yaml
branch: phase1/gate-ownership-repair
s0_record: sealed_in_this_handoff; archived_basename p3-r7-s0-entry-and-budget-freeze.md
s3_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r7-mutation-target-closure-execution-plan.md
s6_review_record: archived; recovery_tag docs/p3-p4-cleanup-pre-20260823; basename p3-r7-s6-independent-review.md
s7_record: p3-r7-mutation-target-closure-handoff.md
container_rebuild_reason: R7 is pure Python capability logic; no Dockerfile, lockfile or runtime-boundary change in the R7 lineage
last_validated_image_revision: none
container_validation_deferred_to: inherited R5 image gate and the P3 final candidate gate
benchmark_reason: R7 freezes measurement-only profiles but has no independent benchmark runner in this candidate
```

```text
Current sealed source candidate: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
Worktree at S7 rerun: clean
Container rebuild required for R7 itself: no
Inherited R5 image gate: required/deferred
Container result: deferred; no image revision is claimed for this R7 candidate
Deferred gate owner/action: backend image owner must rebuild vnext/backend/Dockerfile from the final candidate and rerun container gates before any image/release claim
```

## 2. Commit lineage

核对命令：

```bash
git log --reverse --format='%H %s' e09ff32^..b0261cb669fedc07173a31cd55ce83ef19b0c6ad
```

```yaml
commit_lineage_count: 2
commit_lineage:
  s1_s5_implementation:
    reviewed_tip: e09ff32cc3562b744ff5718357a529c7b8ce3e6f
    subject: "feat(backend): implement P3-R7 mutation closure, renderer and executor"
    stage_exit: pass
    note: contracts, planner/closure, Dolt renderer, reference executor, golden fixtures and unit tests
  post_r7_tip:
    reviewed_tip: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
    subject: "independent review record"
    stage_exit: pass
    note: subsequent R6 remediation on top of the R7 implementation tip; S7 gates rerun at this HEAD
  s7:
    reviewed_tip: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
    stage_exit: pass
    note: this handoff documentation follows the sealed source candidate and is not this SHA
```

### 2.1 Upstream applicability re-attestation

After R6 independent S7 revalidated the clean current candidate
`f2d48d876c40dd918878a6e5215c57daf7920766`, R7 re-attested the R4/R6 input boundary. The diff
from sealed R7 source tip `b0261cb669fedc07173a31cd55ce83ef19b0c6ad` to that candidate contains
formal R7 documentation/review records only and no production, test, contract, dependency or
runtime-boundary change. The sealed R7 source tip already includes the R6 S6 remediation, and the
public authority split remains unchanged: R4 canonical projection is mutation authority; R6
Surface/Bundle is provenance only.

No R7 implementation or contract rework is required. The current acceptance refreshes the upstream
evidence chain and this handoff only; it does not enter or authorize P4. Current backend evidence is
also consistent with that disposition: the R6 focused gate passed 90 tests, and the backend unit
gate excluding the inherited legacy oracle passed 714 tests. The unfiltered unit run's 58 failures
remain confined to `tests/test_table_rules_resolver.py` and do not identify an R7 regression.

## 3. Changed-path inventory

R7 source/test capability surface：

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

R7 contract/formal records：

```text
docs/backend-vnext/refactoring/formal/plans/p3-r7-mutation-target-closure-design.md
# archived: p3-r7-s0-entry-and-budget-freeze.md, p3-r7-mutation-target-closure-execution-plan.md,
#   p3-r7-s6-independent-review.md (tag docs/p3-p4-cleanup-pre-20260823)
docs/backend-vnext/refactoring/formal/plans/p3-r7-mutation-target-closure-handoff.md
```

No R7 change touched dependencies, lockfiles, Dockerfile, Compose, entrypoint, deployment wiring,
Rust/Cargo files or runtime boundaries.

## 4. Public boundary handed to P4/P5

R7 exposes only the following flow-neutral, immutable/public seams:

- R4 `CanonicalizationManifest` and `RepositoryImportArtifactInput` remain the sole authoritative
  storage projection inputs. R6 Surface/Bundle artifacts may be used only as provenance reference,
  never as mutation authority.
- `mutation_planning` owns `StorageMutationPlan`, `ChangeSetArtifact`, closure digest and atomic
  publication of the canonical JSON closure. Planner policy defaults to `REBUILD_ALWAYS`; patch
  eligibility is explicit and bounded.
- Dolt renderer produces deterministic bounded `replay.sql` bytes from public ChangeSet contracts.
  It does not execute SQL or accept caller-provided SQL text.
- `external_target_sync` owns the public apply contract and in-memory reference executor state
  machine. Checkpoint export/import is test-only JSON fixture data, not durable production state.
- Confirmation, durable operation state, lease/takeover and production external adapters remain
  outside R7.

The allowed dependency direction is:

```text
R4 canonical storage projection
  -> R7 StorageMutationPlan / ChangeSetArtifact
       -> Dolt renderer replay.sql
       -> external reference executor
```

The R7 capabilities do not import HTTP/application/Workspace/Submit/Archive/Operation Runtime,
Repository/Dolt execution adapters, R6 private modules, legacy business modules, host-path
helpers, test support or new helper/service/security principals.

## 5. Sealed R7 module gate evidence

All Python commands used the backend package virtualenv. The focused command was:

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_mutation_contracts.py tests/test_mutation_planning.py \
  tests/test_dolt_renderer.py tests/test_external_target_contracts.py \
  tests/test_external_target_executor.py tests/test_architecture.py
```

Results:

| Check | Result |
| --- | --- |
| focused R7 mutation/renderer/executor/architecture gate | **PASS**; 98 passed in 46.74s |
| `cd vnext/backend && uv run pytest -q -m unit` | **PASS**; 848 passed, 1 existing Starlette deprecation warning |
| `cd vnext/backend && uv run ruff check .` | **PASS** |
| `cd vnext/backend && uv run mypy` | **PASS**; 188 source files |
| other four Python packages `uv run ruff check .` / `uv run mypy` | **PASS**; mypy 26 / 15 / 195 / 34 source files |
| `git diff --check` | **PASS** |

No R7 test creates Dolt, starts a Repository process, invokes a shell/SQL parser, uses network
I/O or depends on a fixed-timeout serial fixture. No `integration` or `serial -n 0` rerun is
required for this R7 candidate.

## 6. Review closure

The S3 planner focused review and S6 independent cumulative review both pass with no open P1/P2
finding or contract ambiguity.

| Review item | Disposition |
| --- | --- |
| S3 unsupported canonical key/image preflight | **Closed**; planner returns `TARGET_CAPABILITY_UNSUPPORTED` before closure construction |
| S3 mixed-plan closure summary | **Closed**; every per-table summary, including `NOOP`, is retained |
| S3 malformed closure column entries | **Closed**; parser rejects non-object entries explicitly |
| S6 owner/import boundary | **Closed**; architecture DAG and forbidden-import scans pass |
| S6 renderer safety and replay admission | **Closed**; golden SQL and capability-failure fixtures pass |
| S6 executor rollback/unknown/reconcile | **Closed**; rollback, reconcile-then-retry and idempotent reuse tests pass |
| artifact orphan reclamation | **Accepted deferred** under ADR 0012; artifact port has no delete/transaction primitive and no public orphan ref is returned |

## 7. Deferred and reopen register

| Item | Status and owner/action |
| --- | --- |
| real Repository/Dolt execution and readback | **Deferred**; Repository service / P5B owner |
| P5B confirmation/finalize and durable operation state | **Deferred**; flow/application owner |
| P4 durable operation, drain, checkpoint and takeover | **Deferred**; operation lifecycle owner |
| production external target adapters and multi-target persistence | **Deferred**; future external-sync owner |
| cache/retention/GC and orphan reclamation | **Deferred**; ADR 0012 lifecycle owner |
| Rust renderer/provider optimization | **Deferred**; native provider owner |
| benchmark numeric gates | **Deferred**; no R7 benchmark runner exists |
| R5 legacy table-rules oracle gap | **Known external fixture gap**; current unfiltered backend unit has 58 failures confined to `tests/test_table_rules_resolver.py`; restore a compatible `legacy/backend_vnext` oracle or retain the explicit exclusion |
| inherited R5 Rust/Cargo backend image gate | **Required/deferred**; rebuild current `vnext/backend/Dockerfile` and run container gates before any final image/release claim |

Reopen R7 or its owning contract if a capability imports a forbidden owner, presentation artifacts
become mutation authority, plan identity can drift, partial effects publish, unknown outcomes are
blindly replayed, unsupported values stringify, a resource cap is bypassed or a new
helper/service/security principal is proposed.

## 8. Benchmark and container disposition

The exact discovery command

```text
rg --files vnext | rg -i '(^|/)(bench|benchmark)([^/]*|/)'
```

returned no R7 benchmark runner or workload generator. R7 therefore records no duration, CPU, RSS,
queue, spill, artifact-byte or cancellation-latency number. Benchmark remains measurement-only and
has no effect on `p3_r7_exit`.

The exact container check was:

```text
docker info
```

The Docker 29.7.2 client is available, but `/var/run/docker.sock` does not exist and the daemon is
unavailable. R7 itself introduced no image boundary change. No current-HEAD backend image was built,
no image revision is claimed, and the mandatory inherited R5 image gate is carried forward to the
P3 final candidate gate.

## 9. P4/P5 entry prerequisites

P4 and P5 may begin their own entry/design conversations after accepting this handoff. Before any
production integration authorization, later phases must freeze at least:

- durable operation state, drain, checkpoint and takeover semantics owned by P4;
- Workspace/HTTP/PreviewResult wiring and artifact retention owned by P5A;
- Submit/finalize, destructive confirmation persistence, real Dolt effect and external ChangeSet
  wiring owned by P5B;
- explicit separation between R7 immutable ChangeSet authority and any preview-facing R6
  presentation artifacts;
- inherited backend image/container gate closure on the final candidate HEAD.

P4/P5 must not import R7 planner-private modules or treat renderer replay bytes as executed
Repository effects. R7 does not authorize flow wiring, HTTP routes, Repository/Dolt writes or
global Phase 3 implementation.

```yaml
p3_r7_exit: pass
p3_r7_validated_code_sha: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
p3_r7_upstream_applicability_re_attested_sha: f2d48d876c40dd918878a6e5215c57daf7920766
p3_r7_rework_required: no
p3_r7_container_gate: inherited_required_deferred_docker_daemon_unavailable
p3_r7_benchmark: measurement_only_no_gate
p3_r7_implementation_authorized: no
p3_implementation_authorized: no
```
