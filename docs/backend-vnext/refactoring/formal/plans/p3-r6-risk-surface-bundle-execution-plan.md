# P3-R6 Risk, Surface and Bundle Execution Plan

状态：S0 complete；S1-S7 staged planning；implementation authorization pending

日期：2026-08-22

Owner：Backend vNext Capability Architecture

设计基线：[P3-R6 Risk, Surface and Bundle Design Baseline](p3-r6-risk-surface-bundle-design.md)

入口冻结：[P3-R6-S0 Entry, Applicability and Budget Freeze](p3-r6-s0-entry-and-budget-freeze.md)

上游 handoff：[P3-R5 Comparison Handoff](p3-r5-comparison-handoff.md)

本文将 R6 拆为可独立验证的 risk、surface、bundle steps。每一步明确上下文策略：`new conversation` 用于隔离入口或审核判断；`same conversation` 仅用于同一 owner 的连续实现，且不得跨越独立 review。

## 1. Objective and exit

R6 交付 flow-neutral `RiskEvaluation`、`ComparisonSurface` 和 `ComparisonBundle`，其 digests、artifact closure、resource limits、failure semantics 和 forbidden-import boundary 可独立验证。

R6 exit requires：

- R6 public contracts each have one owner and no unresolved architecture blocker；
- Python reference risk provider、surface 和 bundle golden/contract tests pass；
- failure precedence、degraded no-record entries、closure atomicity and refs are tested；
- benchmark evidence is recorded as measurement-only；
- focused and independent reviews have no open P1/P2 finding；
- R5 inherited image gate/deferred register is carried forward；
- handoff records tested source SHA, exact commands, deferred register and R7 prerequisites；
- global `p3_implementation_authorized` remains `no`。

## 2. Conversation and review policy

| Step | Topic | Conversation policy | Review isolation |
| --- | --- | --- | --- |
| S0 | entry, applicability, budgets and freeze | `new conversation` | architecture/owner decisions only |
| S1 | risk contracts and ruleset snapshot | `new conversation` after S0 | implementation authorization scoped to Risk |
| S2 | risk engine, annotations and risk closure | `same conversation as S1` | no reviewer role; implementation only |
| S3 | risk focused review | `new conversation` | reviewer must not rely on S1/S2 explanations |
| S4 | surface contracts and assembly | `new conversation` after S3 | consumes only public R5/R6 risk boundary |
| S5 | bundle assembly and final closure | `same conversation as S4` | implementation only |
| S6 | independent R6 review | `new conversation` | independent owner/import/digest/recovery review |
| S7 | module gate and R6 handoff | `new conversation` | acceptance/documentation only; no implementation |

Do not carry implementer scratch state, mutable objects, private module assumptions or unfinished findings across a `new conversation`. The handoff between conversations is the committed public contract, test evidence and deferred register.

## 3. Scope and dependency boundary

```text
R5 ComparisonFacts / RecordsClosure
  -> S1/S2 RiskEvaluation
  -> S4/S5 SurfaceAssembly
  -> S5 BundleAssembly + final closure
```

Allowed production imports:

```text
gateway_backend.artifacts public ports
gateway_backend.capabilities.comparison public contracts
gateway_backend.capabilities.risk_evaluation public contracts
gateway_backend.capabilities.surface_assembly public contracts
gateway_backend.capabilities.bundle_assembly public contracts
shared canonical encoding public primitives
```

Forbidden: HTTP/application/Workspace/Submit/Archive/Operation Runtime, Repository/Dolt, source materialization private modules, legacy business modules, host-path helpers, test support, static-risk provider implementation, new service/helper/security principal and automatic provider fallback.

## 4. Staged steps

### S0 — Entry, applicability and budget freeze

Objective: accept the R5 handoff, freeze R6 scope, owner DAG, status lattice, closure topology, ruleset authority, exact caps, fixtures, review boundaries and authorization procedure.

Outputs: S0 freeze record, accepted design baseline, this plan, owner/deferred table and S1 entry package.

Verification: document cross-reference scan, YAML/status consistency, budget/failure matrix review, no code changes.

Exit: `p3_r6_s0 = completed`; implementation still unauthorized.

#### S0 verification record

Executed on 2026-08-22 as a documentation-only entry review against inherited R5 candidate
`7cb90e6f3e3707de856da0aabb43f7d519b9f1f3` and current documentation HEAD
`500ca1138d9054e3add04409f039578bb308b7695`. No `vnext/` source, tests, dependencies, image,
deployment or runtime-boundary files changed.

| Check | Result |
| --- | --- |
| R5 handoff applicability | **PASS**; `p3_r5_exit: pass`, `p3_r6_ready: yes` |
| R6 baseline/plan/contract links | **PASS**; all normative references resolve |
| owner DAG, status precedence, closure topology | **PASS**; R5 facts/closure remain immutable input and final publication is bundle-owned |
| exact caps, failure matrix and fixture groups | **PASS**; freeze record is internally consistent and fail-closed |
| review/conversation and authorization boundary | **PASS**; S0 is architecture-only, S1 starts in a new conversation, global authorization remains `no` |
| `git diff --check` and whitespace scan | **PASS** |
| image/container verification | **DEFERRED / NOT APPLICABLE**; docs-only S0, inherited R5 image gate remains a final-candidate prerequisite |

Authoritative record: [P3-R6-S0 Entry, Applicability and Budget Freeze](p3-r6-s0-entry-and-budget-freeze.md#8-verification-record).
Decision: **S0 pass**; `p3_r6_s0 = completed`, `p3_r6_s0_exit = pass`, and no implementation is authorized.

### S1 — Risk contracts and frozen ruleset snapshot

Objective: define public risk input/output types, `RiskRulesetSnapshot`, rule IDs/versions/severity/reason codes, canonical digest inputs and records access protocol.

Conversation: `new conversation`; scoped Risk implementation authorization may be granted only after S0 exit.

Tests: ruleset digest stability, risk contract serialization, forbidden imports, malformed snapshot matrix, R5 facts compatibility.

Exit: public risk contracts committed; no engine or surface/bundle implementation assumptions leak into the contract.

### S2 — Risk evaluation, annotations and immutable closure

Objective: implement bounded Python reference facts extraction, rule evaluation, aggregation, annotation artifacts, degraded no-record entries and risk closure validation.

Conversation: `same conversation as S1`.

Tests: structural/row/schema/degraded/ordered-unsupported/composite cases, unknown target behavior, resource caps, cancellation, manifest/content digest and no partial publication.

Exit: stable `RiskEvaluation`/`RiskReport` digests and complete risk closure for valid results.

### S3 — Risk focused contract/resource/security review

Objective: independently check risk owner/import boundary, ruleset drift, failure lattice, resource enforcement, artifact closure and diagnostic leakage.

Conversation: `new conversation`; reviewer receives S0/S1/S2 committed artifacts and exact commands only.

Outputs: findings register, exact rerun list, remediation authorization and S4 entry decision.

Exit: no unclosed P1/P2 or contract ambiguity; any accepted deferred item is explicit.

### S4 — Surface contracts and deterministic assembly

Objective: implement thin `ComparisonSurface`, table projection, risk refs, ordered unsupported presentation, diagnostic refs, logical ref validation and surface digest.

Conversation: `new conversation` after S3.

Tests: table mapping, summary-only/degraded/replacement modes, missing required records, forbidden refs, digest stability and closure ref rewrite.

Exit: surface can consume R5 facts and optional risk result without reading full rows or flow state.

### S5 — Bundle assembly and final closure

Objective: implement single/multi-pair bundle assembly, bundle-relative ref rewrite, shared snapshot artifact handling, manifest/closure validation and atomic final publication.

Conversation: `same conversation as S4`.

Tests: single/multi-pair, shared artifacts, missing/tampered/duplicate refs, closure size caps, digest stability, degraded no-record entries and failure cleanup.

Exit: valid bundle is replayable from its final closure; invalid or partial bundle cannot be READY.

### S6 — Independent R6 owner/import/digest/recovery review

Objective: review the complete R6 surface without relying on implementer explanations.

Conversation: `new conversation`.

Review focus: public owner graph, forbidden imports, ruleset/comparison separation, status precedence, artifact atomicity, resource caps, cancellation, ref/path safety, cross-pair sharing and no static-risk/flow leakage.

Exit: no open P1/P2; remediation rerun records identify tested tip and exact nodeids.

### S7 — R6 module gate and handoff

Objective: seal the tested source SHA, summarize focused/independent review, record exact unit/lint/type/benchmark commands, carry deferred items and establish R7 entry prerequisites.

Conversation: `new conversation`; acceptance/documentation only.

Exit: `p3_r6_exit = pass`, `p3_r7_ready = yes` only if all gate evidence is present. This does not authorize P3 production integration or change global implementation authorization.

## 5. Verification policy

R6 pure Python contracts, risk, surface, bundle, digest and artifact tests are `unit`. R6 does not create Dolt repositories. Any fixed timeout/cancellation timing test is `serial` and runs with `-n 0`. Each package runs its mandated ruff and mypy commands. Benchmark runs are measurement-only and must identify dataset/ruleset/provider/revision and raw resource metrics.

Container rebuild is not required for Python-only R6 changes. It becomes mandatory if R6 changes Rust/Cargo, lockfiles, Dockerfile, entrypoint, Compose, environment wiring or runtime boundaries. The inherited R5 image gate remains a final-candidate prerequisite.

## 6. Deferred register and reopen conditions

Deferred: static-risk provider/rules, unified static/diff aggregation, Rust risk kernels/differential, risk/surface/bundle cache, artifact GC/retention, P5 flow integration, R5 legacy fixture gap and inherited image gate.

Reopen R6 if a capability imports forbidden flow/repository/private modules, risk rules modify comparison semantics, static-risk input enters R6 risk DTO, partial artifacts publish, degraded tables lose terminal closure entries, confirmation persistence enters R6, resource caps are bypassed, automatic provider fallback is introduced or a new security principal/helper/service is proposed.

## 7. Current status

```yaml
current_module: P3-R6
p3_r6_design: accepted
p3_r6_detail_plan: accepted_for_staged_planning
p3_r6_s0: completed
p3_r6_s0_exit: pass
p3_r6_implementation_authorized: no
p3_implementation_authorized: no
p3_r5_exit: pass
p3_r5_validated_code_sha: 7cb90e6f3e3707de856da0aabb43f7d519b9f1f3
container_gate: inherited_required_deferred
benchmark: measurement_only_no_gate
```

## 8. Normative references

- [P3 Capability Foundation Design](p3-capability-foundation-design.md)
- [P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)
- [P3-R5 Comparison Handoff](p3-r5-comparison-handoff.md)
- [P3-R6 Risk, Surface and Bundle Design Baseline](p3-r6-risk-surface-bundle-design.md)
- [P3-R6-S0 Entry, Applicability and Budget Freeze](p3-r6-s0-entry-and-budget-freeze.md)
- [Risk Contract](../../../contracts/risk.md)
- [Comparison Surface Contract](../../../contracts/comparison-surface.md)
- [Comparison Bundle Contract](../../../contracts/comparison-bundle.md)
- [Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)
