# P3-R6-S0 Entry, Applicability and Budget Freeze

状态：S0 complete；implementation authorization pending

日期：2026-08-22

Owner：Backend vNext Capability Architecture / R6 Owners

设计基线：[P3-R6 Risk, Surface and Bundle Design Baseline](p3-r6-risk-surface-bundle-design.md)

上游 handoff：[P3-R5 Comparison Handoff](p3-r5-comparison-handoff.md)

本文冻结 R6 的入口事实、适用性、owner、bounded budgets、failure matrix、fixtures、review focus 和实现授权前置条件。数值是 fail-closed resource caps，不是 latency SLO 或 performance gate。

## 1. Entry facts

```yaml
handoff_kind: p3_r6_s0_entry_and_budget_freeze
p3_r5_exit: pass
p3_r6_ready: yes
p3_r6_design: p3-r6-risk-surface-bundle-design.md
p3_r6_detail_plan: p3-r6-risk-surface-bundle-execution-plan.md
p3_r6_s0_exit: pass
p3_r6_implementation_authorized: no
validated_r5_code_sha: 7cb90e6f3e3707de856da0aabb43f7d519b9f1f3
r5_handoff_documentation_sha: 500ca11
s0_review_head: 500ca1138d9054e3add04409f039578bb308b7695
s0_execution_date: 2026-08-22
s0_worktree: docs_dirty_no_code_changes
container_gate: inherited_required_deferred
benchmark: measurement_only_no_gate
```

R5 source/module gate 已通过；R5 inherited Docker/Cargo image gate 仍须在最终 candidate 前关闭。R6 只新增 Python capability/docs/tests 时不因 R6 本身要求 image rebuild；若触碰 Rust、依赖、Dockerfile 或 runtime boundary，按 AGENTS 规则重建。

## 2. Applicability and owner DAG

```text
R5 ComparisonFacts / RecordsClosure
  -> R6 RiskEvaluation
       -> R6 SurfaceAssembly
            -> R6 BundleAssembly / final closure
```

| Object | Owner | R6 treatment |
| --- | --- | --- |
| `ComparisonFacts`, records closure | R5 comparison | immutable input; no semantic rewrite |
| `RiskRulesetSnapshot` activation/version/digest | Table Rules / Risk Policy | frozen input; R6 cannot mutate |
| Risk evaluation/annotation | risk evaluation | R6-owned immutable intermediate |
| Comparison surface | surface assembly | R6-owned thin result |
| Bundle manifest/closure | bundle assembly | R6-owned final closure |
| confirmation persistence/revocation | future flow/application | digest only; no R6 state machine |
| static risk | future capability | seam only; out of R6 input |

## 3. Frozen resource caps

| Budget | Frozen limit | Exceedance |
| --- | ---: | --- |
| `max_risk_tables_per_pair` | 4,096 | pair `FAILED` before evaluation |
| `max_annotations_per_table` | 2,000,000 | table `DEGRADED`; discard partial annotation artifact |
| `max_annotations_per_pair` | 4,000,000 | pair `DEGRADED`; no partial annotation closure |
| `max_annotation_artifact_bytes_per_table` | 512 MiB | table `DEGRADED`; discard partial artifact |
| `max_risk_evaluation_json_bytes` | 16 MiB | pair `FAILED`; no risk closure |
| `max_risk_report_json_bytes` | 16 MiB | pair `FAILED`; no risk closure |
| `max_surface_json_bytes` | 16 MiB | pair `FAILED`; no surface publication |
| `max_bundle_manifest_json_bytes` | 16 MiB | bundle `FAILED` |
| `max_bundle_closure_json_bytes` | 16 MiB | bundle `FAILED` |
| `max_diagnostics_per_table` | 4,096 | table `DEGRADED`; bounded truncation diagnostic |
| `max_diagnostics_bytes_per_table` | 4 MiB | table `DEGRADED`; bounded truncation diagnostic |
| `max_risk_table_wall_time_seconds` | 120 s | table `DEGRADED`; discard partial artifact |
| `max_risk_pair_wall_time_seconds` | 900 s | pair `CANCELLED`; no facts/risk READY |
| `max_surface_pair_wall_time_seconds` | 120 s | surface `FAILED` |
| `max_bundle_wall_time_seconds` | 300 s | bundle `FAILED` |
| `max_pair_concurrency` | 8 | caller must bound queue |
| `cancellation_observation_seconds` | 5 s | diagnostic; no READY publication |

R5 input/table/records caps remain owned by R2/R3/R5 and are not copied into a second parser budget table. R6 caps only bound risk, surface and bundle work.

## 4. Failure matrix and publication

| Fault | Scope/result | Publication |
| --- | --- | --- |
| invalid ruleset snapshot/version/digest | pair `FAILED` | no risk result |
| unknown change target with valid facts | table `UNKNOWN` annotation | continue other tables |
| one table risk rule/resource failure | table `DEGRADED` | explicit no-record risk closure entry |
| risk artifact/manifest/digest failure | pair `FAILED` | no risk closure |
| missing records closure when facts require it | pair `FAILED` | no surface/bundle READY |
| surface ref/path/closure validation failure | surface `FAILED` | no surface publication |
| missing referenced artifact at bundle assembly | bundle `FAILED` | no bundle READY |
| optional baseline pair failure | overall at most `DEGRADED` | primary pair may continue |
| primary pair failure | overall `FAILED` | no final bundle READY |
| cancellation/deadline | terminal `CANCELLED` | no facts/risk/surface/bundle READY |

Every terminal path closes readers, writers and temporary stores before publishing status. Partial annotation, surface or bundle artifacts are discarded and never appear in the final closure.

## 5. Ruleset and fixture freeze

R6 v1 ruleset snapshot is `RISK_ONLY`; rule id, rule version, severity policy, params, contract version and digest are canonicalized before evaluation. Required semantic fixture groups:

```text
RISK_STRUCTURAL_CASES
RISK_STANDARD_ROW_CASES
RISK_SCHEMA_CASES
RISK_DEGRADED_CASES
RISK_ORDERED_UNSUPPORTED_CASES
RISK_COMPOSITE_SIGNAL_CASES
RISK_RULESET_DIGEST_CASES
RISK_ANNOTATION_BOUNDARY_CASES
SURFACE_TABLE_PROJECTION_CASES
SURFACE_REF_VALIDATION_CASES
BUNDLE_SINGLE_PAIR_CASES
BUNDLE_MULTI_PAIR_SHARED_ARTIFACT_CASES
BUNDLE_CLOSURE_FAULTS
R6_RESOURCE_BOUNDARY_CASES
```

Pure contract/risk/digest/artifact checks are `unit`. No R6 test creates Dolt. Fixed event/join/stream cancellation timing tests, if introduced, are `serial` and run with `-n 0`; no manual Dolt `skipif` is permitted.

## 6. Benchmark disposition

Profiles: `r6_tiny`, `r6_small`, `r6_medium`, `r6_large`; multi-pair factors `1/2/4/8`. Each correctness-passed run records dataset revision, ruleset digest, provider, cold/cache mode, wall time, CPU, RSS, queue wait, annotation count/bytes, bundle bytes and cancellation latency. No result changes budgets or authorizes implementation.

## 7. S0 exit checklist and S1 prerequisites

S0 exit evidence is recorded in the execution plan §4. The following decisions are frozen:

- [x] R6 design baseline and detail plan accepted;
- [x] owner DAG, public input/output contracts and failure precedence accepted;
- [x] exact caps table and fixture groups recorded;
- [x] Python reference provider and no-Rust-differential boundary recorded;
- [x] focused/independent review scopes and new-vs-same conversation policy recorded;
- [x] R5 deferred container/fixture items have owners and final-candidate close points;
- [x] R6-specific implementation authorization remains separate; global `p3_implementation_authorized` remains `no`.

S1 may consume only the immutable R5 public boundary and this freeze. It may not add static-risk inputs, flow state or comparison semantic changes.

## 8. Verification record

S0 was executed as a documentation-only entry review on 2026-08-22. No production source, test,
dependency, image or deployment path changed. The current source candidate is the inherited R5
validated SHA; the R6 documents are the only new/untracked paths in this worktree.

| Check | Result |
| --- | --- |
| R5 handoff applicability and `p3_r5_exit` | **PASS**; `p3_r5_exit: pass`, `p3_r6_ready: yes`, validated code SHA `7cb90e6f3e3707de856da0aabb43f7d519b9f1f3` |
| R6 design/plan/contract cross-reference | **PASS**; baseline, execution plan, Risk, Comparison Surface and Comparison Bundle contracts resolve |
| owner, failure and budget matrix review | **PASS**; owners, terminal publication rules and all 17 R6 caps are consistent |
| fixture, marker and benchmark policy review | **PASS**; fixture groups are named, pure checks are `unit`, timing checks are `serial`, benchmarks are measurement-only |
| architecture/reopen review | **PASS**; no flow/repository/private import, static-risk input, fallback provider or new principal is authorized |
| `git rev-parse HEAD` | **PASS**; `500ca1138d9054e3add04409f039578bb308b7695` |
| `git diff --check` | **PASS**; no whitespace errors in tracked changes; R6 files have no trailing whitespace |
| code/container gate | **NOT APPLICABLE** for S0; docs-only change, inherited R5 image gate remains deferred to final candidate |

S0 decision: **PASS / complete**. S1 may begin only in a new conversation and may implement the
frozen Risk public contracts; this record does not authorize R6 implementation globally or in any
later step.
