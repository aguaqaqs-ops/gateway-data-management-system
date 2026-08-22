# P3-R6 Risk, Surface and Bundle Handoff

状态：`pass`（R6 module gate；R7 entry。不是 Phase 3 全部实现授权，不含 flow/production
integration、cache/GC 或 Rust risk provider）

日期：2026-08-22

Owner：Backend vNext Capability Architecture

本文是 P3-R7 的默认 R6 入口。它封存 R6 的 source/module gate、公开 capability seam、独立
review closure、已知 deferred items 和 R7 prerequisites。R6 只交付 flow-neutral Risk、Surface
和 Bundle capability；`p3_implementation_authorized` 仍为 `no`。

上级计划：[P3-R6 Risk, Surface and Bundle Execution Plan](p3-r6-risk-surface-bundle-execution-plan.md)

设计基线：[P3-R6 Risk, Surface and Bundle Design Baseline](p3-r6-risk-surface-bundle-design.md)

入口冻结：[P3-R6-S0 Entry, Applicability and Budget Freeze](p3-r6-s0-entry-and-budget-freeze.md)

独立 review：[P3-R6-S6 Independent Owner, Import, Digest and Recovery Review](p3-r6-s6-independent-review.md)

## 1. Gate identity

```yaml
handoff_kind: p3_r6_risk_surface_bundle
round: P3-R6-S7
branch: phase1/gate-ownership-repair
p3_r6_exit: pass
p3_r7_ready: yes
p3_r6_s6_review: pass
p3_r6_s7_gate: pass
validated_code_sha: f2d48d876c40dd918878a6e5215c57daf7920766
source_worktree_at_gate: clean_committed_current_candidate_before_acceptance_docs
container_gate: inherited_required_deferred_docker_daemon_unavailable
benchmark: measurement_only_no_gate_runner_absent
p3_r6_implementation_authorized: no
p3_implementation_authorized: no
```

`validated_code_sha` 是独立 S7 acceptance owner 运行 current-candidate gates 的干净 committed
HEAD。随后仅修复本 execution/handoff/index 状态链，未修改生产代码；本文件不伪造尚未产生的
documentation commit SHA，也不授权进入 P4。

## 2. Changed-path inventory

R6 source/test capability surface：

```text
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/
vnext/backend/src/gateway_backend/capabilities/surface_assembly/
vnext/backend/src/gateway_backend/capabilities/bundle_assembly/
vnext/backend/tests/test_risk_contracts.py
vnext/backend/tests/test_risk_evaluation.py
vnext/backend/tests/test_surface_contracts.py
vnext/backend/tests/test_surface_assembly.py
vnext/backend/tests/test_bundle_contracts.py
vnext/backend/tests/test_bundle_assembly.py
vnext/backend/tests/test_architecture.py
```

R6 contract/capability/formal records：

```text
docs/backend-vnext/contracts/risk.md
docs/backend-vnext/contracts/comparison-surface.md
docs/backend-vnext/contracts/comparison-bundle.md
docs/backend-vnext/capabilities/risk-evaluation.md
docs/backend-vnext/capabilities/surface-assembly.md
docs/backend-vnext/capabilities/bundle-assembly.md
docs/backend-vnext/refactoring/formal/plans/p3-r6-risk-surface-bundle-design.md
docs/backend-vnext/refactoring/formal/plans/p3-r6-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r6-s6-independent-review.md
docs/backend-vnext/refactoring/formal/plans/p3-r6-risk-surface-bundle-execution-plan.md
```

No R6 change touched dependencies, lockfiles, Dockerfile, Compose, entrypoint, deployment wiring,
Rust/Cargo files or runtime boundaries.

## 3. Public boundary handed to R7

R6 exposes only the following flow-neutral, immutable/public seams:

- R5 `ComparisonFacts` and optional `ComparisonRecordsClosure` remain comparison-owned authority;
  R6 does not recompute or mutate comparison semantics.
- Risk owns `RiskRulesetSnapshot`, `RiskEvaluation`, `RiskReport`, annotation artifacts and the
  replay-validated risk closure. The bounded Python reference evaluator is the R6 candidate path;
  there is no automatic provider fallback.
- Surface owns `ComparisonSurface`, table projection, validated logical refs and `surface_digest`.
  It consumes descriptor/fact data and does not read full rows or flow state.
- Bundle owns single/multi-pair organization, bundle-relative ref rewrite, shared snapshot
  artifact deduplication, manifest/closure validation and `bundle_digest`.
- Artifact storage is accessed through public ports. Runtime refs, host paths, diagnostics and
  operation metadata are excluded from semantic digests as required by the contracts.

The allowed dependency direction is:

```text
R5 ComparisonFacts / RecordsClosure
  -> RiskEvaluation
  -> SurfaceAssembly
  -> BundleAssembly + final closure
```

The R6 capabilities do not import HTTP/application/Workspace/Submit/Archive/Operation Runtime,
Repository/Dolt, source-materialization private modules, legacy business modules, host-path
helpers, test support or static-risk provider implementation. R7 must not treat a Surface or
Bundle presentation artifact as mutation authority; mutation authority remains canonical storage
projection and the R7-owned target-neutral ChangeSet contract.

## 4. Module gate evidence

The focused command was:

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_bundle_assembly.py tests/test_bundle_contracts.py \
  tests/test_surface_assembly.py tests/test_surface_contracts.py \
  tests/test_risk_evaluation.py tests/test_risk_contracts.py tests/test_architecture.py
```

Results:

| Check | Result |
| --- | --- |
| focused Risk/Surface/Bundle/architecture gate | **PASS**; 90 passed in 1.29s |
| `cd vnext/backend && uv run pytest -q -m unit` | **KNOWN EXTERNAL FIXTURE GAP**; 790 passed, 58 failed, 1 warning in 46.89s |
| `cd vnext/backend && uv run pytest -q -m unit --ignore tests/test_table_rules_resolver.py` | **PASS**; 714 passed, 1 existing Starlette deprecation warning in 50.49s |
| `cd vnext/backend && uv run ruff check .` / `uv run mypy` | **PASS**; 188 source files |
| `repository_client` / `repository_contracts` / `repository_service` / `shared_kernel` `uv run ruff check .` / `uv run mypy` | **PASS**; mypy checked 26 / 15 / 195 / 34 source files |
| `git diff --check` | **PASS** |

The 58 full-unit failures are confined to `tests/test_table_rules_resolver.py`: its test support
loads absent or incompatible `legacy/backend_vnext` files and registry symbols. The R6 gate does
not own that external oracle, and the unit run excluding that file passes.

No R6 test creates Dolt, starts a Repository process, invokes a shell/SQL parser, uses network
I/O or depends on a fixed-timeout serial fixture. No `integration` or `serial -n 0` rerun is
required for this R6 candidate.

## 5. Review closure

The S3 focused Risk review and S6 independent cumulative review both pass with no open P1/P2
finding or contract ambiguity.

| Review item | Disposition |
| --- | --- |
| S3 pair annotation admission cap | **Closed**; admission is incremental and bounded before materialization |
| S3 publication cancellation boundary | **Closed**; cancellation is checked before publication commit |
| S3 count-only closure semantics | **Closed**; no spurious artifact-budget/no-record entry is emitted |
| S3 annotation record schema | **Closed**; closure replay validates every canonical record shape |
| S6 bundle manifest/closure semantic binding | **Closed**; recovery recomputes manifest binding and exact schemas reject unknown fields |
| S6 redundant closure semantic entries | **Closed**; Bundle recovery binds the redundant semantic entries |
| S6 surface role digest binding | **Closed**; before/current/records/risk semantic roles are bound while raw refs remain excluded |
| S6 pair-cap degraded risk | **Closed**; degraded pairs retain explicit `UNKNOWN` table risk state |
| S6 typed risk artifact conformance | **Closed**; Bundle publication validates canonical annotation content/manifest shape through the public Surface seam |
| artifact orphan reclamation | **Accepted deferred** under ADR 0012; the current artifact port has no delete/transaction primitive and no public orphan ref is returned |

The S6 regression owner is
`test_recovery_rejects_manifest_and_closure_semantic_metadata_tampering`. Degraded tables retain
terminal no-record closure entries; failed/cancelled or closure-invalid results do not publish
READY refs; bundle validation covers nested refs, shared artifacts, manifest and closure digests.

## 6. Deferred and reopen register

| Item | Status and owner/action |
| --- | --- |
| static-risk provider/rules and unified static/diff aggregation | **Deferred**; future capability/risk owner |
| Rust risk kernel and cross-language differential | **Deferred**; P6/native provider owner; no R6 parity claim |
| Risk/Surface/Bundle cache, retention and artifact GC | **Deferred**; future lifecycle/cache owner; orphan reclamation remains ADR 0012 work |
| P5 flow/application integration and confirmation persistence | **Deferred**; flow/application owner |
| R5 legacy table-rules oracle gap | **Known external fixture gap**; restore compatible `legacy/backend_vnext` oracle or retain explicit exclusion |
| inherited R5 Rust/Cargo backend image gate | **Required/deferred**; rebuild current `vnext/backend/Dockerfile` and run container gates when Docker daemon is available |

Reopen R6 or its owning contract if a capability imports a forbidden owner, risk changes comparison
semantics, static risk enters the R6 risk DTO, partial artifacts become publicly visible, degraded
tables lose terminal closure entries, a resource cap is bypassed, automatic provider fallback is
introduced or a new helper/service/security principal is proposed.

## 7. Benchmark and container disposition

The exact discovery command

```text
rg --files vnext | rg -i '(^|/)(bench|benchmark)([^/]*|/)'
```

returned no R6 benchmark runner or workload generator. R6 therefore records no duration, CPU, RSS,
queue, spill, artifact-byte or cancellation-latency number. Benchmark remains measurement-only and
has no effect on `p3_r6_exit`.

The exact container check was:

```text
docker info
```

The Docker 29.7.2 client reported that `/var/run/docker.sock` does not exist and it could not connect
to the daemon. The current HEAD image was not built, no image revision is claimed, and the mandatory
inherited R5 image gate is carried forward. When Docker is available, the image owner must rebuild
from the then-current final candidate (the revalidated source tip here is
`f2d48d876c40dd918878a6e5215c57daf7920766`) and run the relevant container gates before any
final image/release/production-candidate claim.

## 8. R7 entry prerequisites

R7 is `ready` to begin its own entry/design conversation after accepting this handoff. Before R7
implementation authorization, its S0 must freeze at least:

- `StorageMutationPlan`, `ChangeSetArtifact`, `ADAPTIVE_PATCH` and target-neutral mutation ownership;
- canonical before/after storage snapshot and manifest inputs from R4, without importing R6 private
  modules or treating preview-facing Surface/Bundle data as storage truth;
- deterministic Dolt renderer and reference external executor boundaries, including parameterized
  execution and no shell interpolation;
- key guards, exact affected-row checks, before/after digest binding, readback and atomic/fail-closed
  publication semantics;
- mutation, artifact, archive/path, cancellation, resource and recovery caps plus the owner DAG;
- R7-specific focused/independent review boundaries and the inherited image/legacy deferred register.

R7 may consume R6 as an immutable preview/result closure reference where needed, but R6 does not
authorize Repository/Dolt writes, target application, SQL generation, flow integration or any
production cutover.

```yaml
p3_r6_exit: pass
p3_r7_ready: yes
p3_r6_validated_code_sha: f2d48d876c40dd918878a6e5215c57daf7920766
p3_r6_container_gate: inherited_required_deferred_docker_daemon_unavailable
p3_r6_benchmark: measurement_only_no_gate
p3_r6_implementation_authorized: no
p3_implementation_authorized: no
```
