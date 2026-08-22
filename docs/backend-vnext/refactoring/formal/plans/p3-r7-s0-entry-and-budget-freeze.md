# P3-R7-S0 Entry, Applicability and Budget Freeze

状态：S0 complete/pass；implementation authorization pending

日期：2026-08-22

Owner：Backend vNext Canonical Storage / Mutation Planner / External Target Sync

设计基线：[P3-R7 Mutation and Target Closure Design Baseline](p3-r7-mutation-target-closure-design.md)

执行计划：[P3-R7 Mutation and Target Closure Execution Plan](p3-r7-mutation-target-closure-execution-plan.md)

上游 handoff：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)、[P3-R6 Risk, Surface and Bundle Handoff](p3-r6-risk-surface-bundle-handoff.md)

本文冻结 R7 的入口事实、owner DAG、public input boundary、mutation policy、failure semantics、
resource caps、fixtures、review boundary 和实现授权前置条件。数值是 fail-closed caps，不是
latency SLO 或 performance gate。

## 1. Entry facts

```yaml
handoff_kind: p3_r7_s0_entry_and_budget_freeze
p3_r4_exit: pass
p3_r6_exit: pass
p3_r7_ready: yes
p3_r7_design: p3-r7-mutation-target-closure-design.md
p3_r7_detail_plan: p3-r7-mutation-target-closure-execution-plan.md
p3_r7_s0_exit: pass
p3_r7_implementation_authorized: no
p3_implementation_authorized: no
container_gate: inherited_required_deferred
benchmark: measurement_only_no_gate
legacy_oracle_gap: closed_at_r7_s7
```

R7 只接受 R4 immutable `CanonicalizationManifest`、`RepositoryImportArtifactInput` 及其 digest/ref。
R6 Surface/Bundle 只可作为 provenance reference，不能作为 mutation authority。

## 2. Applicability and owner DAG

```text
R4 canonical before/after storage projection
  -> R7 StorageMutationPlan
       -> R7 ChangeSetArtifact
            -> Dolt renderer / external reference executor
```

| Object | Owner | R7 treatment |
| --- | --- | --- |
| canonical projection and manifest | R4 storage projection | immutable authoritative input |
| mutation plan and ChangeSet | R7 mutation planner | immutable R7 output |
| replay SQL | R7 Dolt renderer | derived artifact; no execution |
| reference apply state | R7 executor | in-memory test/reference state only |
| confirmation and durable operation state | P5B/P4/P5 | outside R7 |
| external target sync package | R7 external target sync | separate capability owner; public ChangeSet input only |

## 3. Frozen policy and caps

| Budget/policy | Frozen value | Exceedance or mismatch |
| --- | --- | --- |
| default planner policy | `REBUILD_ALWAYS` | no implicit adaptive behavior |
| patch row count | `<= 1,000` | table is rebuild or ineligible |
| patch change ratio | `<= 5%` | table is rebuild or ineligible |
| rendered replay artifact | `<= 200 MiB` | direct rejection; no split/fallback |
| manifest/closure/artifact caps | inherit R4/R5 existing caps | fail closed at owning artifact boundary |
| empty before + non-empty after | rebuild only | patch forbidden |
| non-empty before + empty after | destructive plan | confirmation required before effect |
| both empty | `NOOP` | no transaction/empty commit |
| schema/key/projection change | rebuild | unsupported renderer -> `TARGET_CAPABILITY_UNSUPPORTED` |

No new quota, helper, broker, service, security principal or automatic fallback is introduced by S0.

## 4. Failure and publication matrix

| Fault | Result | Publication |
| --- | --- | --- |
| malformed input/manifest/digest | `FAILED` | no plan or ChangeSet ref |
| unsupported schema/key/type/renderer capability | `TARGET_CAPABILITY_UNSUPPORTED` | no effect artifact |
| missing destructive confirmation | `CONFIRMATION_REQUIRED` | plan may be diagnostic only; no effect artifact |
| before-image/affected-row mismatch | `DRIFT_DETECTED` | whole transaction fails closed |
| duplicate identity with equal fingerprint | idempotent reuse | existing result only |
| duplicate identity with different fingerprint | `IDEMPOTENCY_CONFLICT` | no new effect |
| render size/resource cap exceeded | `RESOURCE_EXCEEDED` | no partial replay artifact |
| executor crash before evidence | `UNKNOWN_OUTCOME` | reconcile before retry |
| readback mismatch | `READBACK_MISMATCH` | no success; full resync required |
| both baselines empty | `NOOP` | no transaction or empty commit |

One ChangeSet maps to one atomic renderer transaction. Partial table effects are never published as
success. Unknown outcome cannot be blind-replayed or assigned a new idempotency identity.

## 5. Fixture and review freeze

Required semantic fixture groups:

```text
R7_MUTATION_BASELINE_CASES
R7_REBUILD_PATCH_NOOP_CASES
R7_SCHEMA_KEY_PROJECTION_CHANGE_CASES
R7_DESTRUCTIVE_CONFIRMATION_CASES
R7_THRESHOLD_BOUNDARY_CASES
R7_CHANGESET_IDENTITY_CASES
R7_RENDERER_GOLDEN_CASES
R7_RENDERER_CAPABILITY_FAILURES
R7_EXECUTOR_ROLLBACK_AND_DRIFT_CASES
R7_UNKNOWN_OUTCOME_RECONCILIATION_CASES
R7_RESOURCE_AND_REPLAY_SIZE_CASES
```

Focused review covers owner/import graph, canonical digest identity, destructive boundary, resource
admission, deterministic ordering, SQL/parameter safety, atomic publication and recovery. Independent
review receives only committed public contracts, exact commands and deferred register.

## 6. S0 exit checklist

- [x] R4 and R6 handoffs accepted as immutable upstream inputs;
- [x] R7 owner DAG and forbidden integration boundary accepted;
- [x] `REBUILD_ALWAYS` default and explicit `ADAPTIVE_PATCH` eligibility accepted;
- [x] initial/empty baseline, table transition and destructive confirmation semantics accepted;
- [x] ChangeSet identity, atomic transaction and unknown-outcome rules accepted;
- [x] separate `external_target_sync` owner and three-format artifact boundary accepted;
- [x] exact R7 caps, fixture groups, review isolation and deferred register recorded;
- [x] R7 implementation authorization remains `no`; global authorization remains `no`.

S1 may begin only in a new conversation and may implement the frozen public contracts.

## 7. Verification record

Executed 2026-08-22 as a documentation-only entry review. No source, tests, dependencies, image,
deployment or runtime boundary changed.

| Check | Result |
| --- | --- |
| R4/R6 handoff applicability | **PASS**; both upstream exits are `pass` |
| R7 design/plan/contract links | **PASS**; all referenced files resolve |
| owner, policy, failure and cap matrix | **PASS**; no unresolved architecture blocker |
| fixture, marker and benchmark policy | **PASS**; pure logic remains unit; timing tests serial |
| forbidden flow/Repository/P5 integration | **PASS**; explicitly out of scope |
| implementation authorization | **PASS**; remains disabled |
| container/image gate | **DEFERRED / NOT APPLICABLE**; docs-only S0; inherited gate remains final-candidate work |

S0 decision: **PASS / complete**.
