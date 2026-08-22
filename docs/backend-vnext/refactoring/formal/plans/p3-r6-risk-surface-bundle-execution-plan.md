# P3-R6 Risk, Surface and Bundle Execution Plan

状态：S0 complete；S1 complete/pass；S2 complete/pass；S3 complete/pass；S4 complete/pass；S5 complete/pass；S6 complete/pass；S7 complete/pass；R6 module gate pass；handoff: [p3-r6-risk-surface-bundle-handoff.md](p3-r6-risk-surface-bundle-handoff.md)；global implementation authorization remains disabled

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

S1 status: **complete/pass** in the current worktree. This was an S1-only Risk contract
authorization; the global `p3_implementation_authorized` value remains `no`. The v1 snapshot was
amended during S2 to add the explicitly required `UNKNOWN_CHANGE_TARGET` rule/reason, and the
combined S1/S2 focused gate revalidated the amended snapshot.

S1 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/contracts.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/__init__.py
vnext/backend/tests/test_risk_contracts.py
```

The implementation freezes Risk v1 levels, target/scope enums, rule IDs, reason codes and the
eleven default rule specifications. `RiskRulesetSnapshot` uses strict canonical document parsing and
JCS/raw SHA-256 digest verification. `RiskEvaluationInput` consumes only public R5
`ComparisonFacts` plus the read-only `RiskRecordsAccess` protocol; artifact refs and diagnostics are
excluded from table/evaluation semantic digests. No provider, mutable registry, artifact writer,
surface/bundle import or flow state was added.

#### S1 verification record

Executed on 2026-08-22 against base source HEAD
`6b9525e0e8acd40d50dad540c0129b842abec746`; S1 source/test changes remain uncommitted in the
current worktree. The focused gate is pure Python and does not create Dolt repositories.

| Check | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit tests/test_risk_contracts.py tests/test_architecture.py` | **28 passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **passed** |
| `git diff --check` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; Python contracts/tests/docs only; inherited R5 image gate remains a final-candidate prerequisite |

S1 decision: **PASS / complete**. S2 may consume the committed public contract once this worktree
is sealed; no Risk engine or annotation publication behavior is claimed by this record.

### S2 — Risk evaluation, annotations and immutable closure

Objective: implement bounded Python reference facts extraction, rule evaluation, aggregation, annotation artifacts, degraded no-record entries and risk closure validation.

Conversation: `same conversation as S1`.

Tests: structural/row/schema/degraded/ordered-unsupported/composite cases, unknown target behavior, resource caps, cancellation, manifest/content digest and no partial publication.

Exit: stable `RiskEvaluation`/`RiskReport` digests and complete risk closure for valid results.

S2 status: **complete/pass**. S2 implementation authorization is limited to the Risk capability;
the global `p3_r6_implementation_authorized` and `p3_implementation_authorized` values remain
`no`. S3 review, S4 surface and S5 bundle remain unauthorized.

S2 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/contracts.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/__init__.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_facts.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_rules.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_engine.py
vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_artifacts.py
vnext/backend/tests/test_risk_contracts.py
vnext/backend/tests/test_risk_evaluation.py
docs/backend-vnext/contracts/risk.md
docs/backend-vnext/capabilities/risk-evaluation.md
docs/backend-vnext/refactoring/formal/plans/p3-r6-risk-surface-bundle-execution-plan.md
```

S2 implements the injected frozen v1 ruleset evaluator, S0 execution budgets, cancellation and
deadline handling, stable aggregation, canonical annotation content/manifest artifacts and
replay-validated risk annotation closure. It does not add a registry, provider fallback, static-risk,
flow, surface or bundle integration.

#### S2 verification record

Executed on 2026-08-22 against source HEAD
`6b9525e0e8acd40d50dad540c0129b842abec746`; S1/S2 source, tests and docs remain uncommitted in the
current worktree. No Dolt repository or external runtime was used.

| Check | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit tests/test_risk_contracts.py tests/test_risk_evaluation.py tests/test_architecture.py` | **41 passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **passed** |
| `git diff --check` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; Python contracts/engine/tests/docs only; inherited R5 image gate remains a final-candidate prerequisite |

### S3 — Risk focused contract/resource/security review

Objective: independently check risk owner/import boundary, ruleset drift, failure lattice, resource enforcement, artifact closure and diagnostic leakage.

Conversation: `new conversation`; reviewer receives S0/S1/S2 committed artifacts and exact commands only.

Outputs: findings register, exact rerun list, remediation authorization and S4 entry decision.

Exit: no unclosed P1/P2 or contract ambiguity; any accepted deferred item is explicit.

#### S3 verification record

Executed on 2026-08-22 as an independent focused review against source tip
`fd2d2f99f19039abd4262990ccf013ff43f55979` (S1/S2 risk contracts, engine, artifacts and tests).
The review did not rely on implementer explanations or private mutable state. Three P2 and one P1
findings were returned to the Risk owner in the same implementation boundary; the remediation and
confirmatory rerun are included below.

Review boundary:

- public owner/import DAG and forbidden flow, repository, source-materialization, legacy and test
  dependencies;
- frozen ruleset identity and complete-v1 validation, canonical semantic digest inputs and ref/
  diagnostic exclusion;
- READY/DEGRADED/FAILED/CANCELLED precedence, cancellation/deadline checkpoints and pair/table
  resource caps;
- annotation content/manifest/closure digest binding, no-record entries, tamper/readback checks and
  no public output on pair failure;
- host-path identity rejection, bounded diagnostics/evidence and absence of full records in reports;
- test marker classification and whether the focused gate introduces Dolt, process, network or
  container dependencies.

| Finding | Area / disposition | Evidence |
| --- | --- | --- |
| `S3-F001` | Pair annotation cap / **P1 closed** | Initial review found all table annotations were materialized before the pair cap was checked. Admission now receives the remaining pair budget and stops before exceeding it; the pair-cap regression remains in the focused suite. |
| `S3-F002` | Publication cancellation boundary / **P2 closed** | Initial review found cancellation was checked after publication. The evaluator now checks immediately before the publication commit boundary and never converts a committed result back to `CANCELLED`; no public ref is returned on pre-commit cancellation. |
| `S3-F003` | `COUNTS_ONLY` closure semantics / **P2 closed** | Count-only mode no longer emits an artifact-budget diagnostic or no-record closure entry; a regression test covers the intentional suppression path. |
| `S3-F004` | Annotation artifact schema / **P2 closed** | Closure replay now parses every annotation, target and reason shape in addition to digest/manifest checks; malformed canonical records fail closed. |
| `S3-001` | Multi-artifact orphan lifecycle / **accepted defer** | A later artifact-store failure can leave opaque content/manifest/closure objects unreachable in the store. The result returns no public ref; `ArtifactStorePort` has no delete/transaction primitive. Reclamation remains ADR 0012 lifecycle work and inherited R5-D05, so this is not a partial public closure or a new security boundary. |
| `S3-002` | Ruleset drift / **pass** | `validate_risk_ruleset()` rejects non-v1 id/version/model, incomplete rule sets and frozen rule identity changes; canonical ruleset document and digest round-trip tests pass. |
| `S3-003` | Failure lattice / **pass after remediation** | Contract construction rejects outputs for `FAILED`/`CANCELLED`; cancellation is checked before the publication commit boundary, and pair/table cap, missing-closure and cancellation tests pass. Degraded tables retain explicit no-record closure entries. |
| `S3-004` | Resource enforcement / **pass after remediation** | Pair annotation admission is incremental and stops before materializing beyond the remaining pair cap; row matching no longer copies the full record tuple. Table/pair counts, artifact/JSON/diagnostic byte limits and wall-time checkpoints are covered by the focused gate. |
| `S3-005` | Closure and diagnostic leakage / **pass after remediation** | Closure replay rechecks raw/content/manifest digests, canonical payloads and every annotation record shape; refs and diagnostics are excluded from semantic digests. Artifact identities and risk evidence reject host-path-shaped values, and reports do not inline records. |
| `S3-006` | Owner/import and runtime boundary / **pass** | Architecture DAG allows Risk only the public Comparison contracts and artifact/shared-kernel ports; no HTTP, flow, Workspace, Submit, Repository/Dolt, legacy, private provider or test-support import is present. |

Exact rerun evidence:

| Check | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit tests/test_risk_contracts.py tests/test_risk_evaluation.py tests/test_architecture.py` | **42 passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit` | **722 passed**, 1 existing Starlette deprecation warning |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **passed**; 161 source files |
| `git diff --check` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; S3 changed only this documentation record; Risk is pure Python and no image, lockfile, deployment or runtime boundary changed. Inherited R5 image gate remains a final-candidate prerequisite. |

No fixed-timeout, Dolt, process, network or integration fixture was introduced, so no
`integration` or `serial -n 0` rerun is required. Benchmark evidence remains measurement-only and
was not used as an S3 gate.

Remediation authorization: **scoped Risk remediation completed** for the pair-cap admission,
publication commit boundary, count-only closure semantics and annotation record validation. `S3-001`
is explicitly accepted deferred lifecycle work; no P1/P2 finding or contract ambiguity remains open.
S4 entry decision: **APPROVED AFTER SEAL** to begin surface contracts/assembly in a new conversation
once the tested Risk remediation is sealed as the S3 handoff. The next conversation may consume only
that committed public R5/R6 Risk boundary. `p3_r6_implementation_authorized` and global
`p3_implementation_authorized` remain `no`.

### S4 — Surface contracts and deterministic assembly

Objective: implement thin `ComparisonSurface`, table projection, risk refs, ordered unsupported presentation, diagnostic refs, logical ref validation and surface digest.

Conversation: `new conversation` after S3.

Tests: table mapping, summary-only/degraded/replacement modes, missing required records, forbidden refs, digest stability and closure ref rewrite.

Exit: surface can consume R5 facts and optional risk result without reading full rows or flow state.

S4 status: **complete/pass**. S4 implementation is scoped to the Surface Assembly capability and
does not authorize Bundle Assembly, flow integration or global P3 implementation.

S4 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/surface_assembly/contracts.py
vnext/backend/src/gateway_backend/capabilities/surface_assembly/__init__.py
vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py
vnext/backend/src/gateway_backend/capabilities/surface_assembly/_digest.py
vnext/backend/src/gateway_backend/capabilities/surface_assembly/_refs.py
vnext/backend/tests/test_surface_contracts.py
vnext/backend/tests/test_surface_assembly.py
docs/backend-vnext/contracts/comparison-surface.md
docs/backend-vnext/capabilities/surface-assembly.md
```

The reference implementation fixes `backend-vnext/comparison-surface/v2`, immutable public
contracts, canonical table ordering, descriptor-only projection, records/risk closure binding,
replacement side-by-side presentation, ordered-unsupported degradation, opaque ref validation and
ref rewriting, semantic digest exclusion of runtime refs/diagnostics, and the 16 MiB surface JSON
cap. Failed, cancelled, over-budget or closure-invalid inputs never return a partial Surface.

#### S4 verification record

Executed on 2026-08-22 against committed source HEAD
`250f1d0d751590ed9c370986a92838309da30f14` plus the uncommitted S4 worktree. No dependency,
Dockerfile, deployment, Rust or runtime-boundary files changed.

| Check | Result |
| --- | --- |
| focused Surface/architecture unit gate | **PASS**; 38 passed |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **PASS** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **PASS**; 166 source files |
| full backend `pytest -q -m unit` | **PASS for S4 scope / pre-existing external-oracle gap remains**; 684 passed, 58 failures in `tests/test_table_rules_resolver.py` because the absent/incompatible `legacy/backend_vnext` oracle cannot load |
| full unit excluding known legacy oracle | **PASS**; 608 passed, 1 existing Starlette deprecation warning; executed with `--ignore tests/test_table_rules_resolver.py` |
| `git diff --check` | **PASS** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; Python-only Surface contracts, assembly, tests and docs; inherited R5 image gate remains a final-candidate prerequisite |

No Dolt, process, network, integration or fixed-timeout serial fixture was introduced. S5 remains
the next implementation step and is not included in this authorization or verification record.

### S5 — Bundle assembly and final closure

Objective: implement single/multi-pair bundle assembly, bundle-relative ref rewrite, shared snapshot artifact handling, manifest/closure validation and atomic final publication.

Conversation: `same conversation as S4`.

Tests: single/multi-pair, shared artifacts, missing/tampered/duplicate refs, closure size caps, digest stability, degraded no-record entries and failure cleanup.

Exit: valid bundle is replayable from its final closure; invalid or partial bundle cannot be READY.

S5 status: **complete/pass**. S5 implementation is scoped to Bundle Assembly and does not authorize
flow integration, bundle cache/GC or global P3 implementation.

S5 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/bundle_assembly/contracts.py
vnext/backend/src/gateway_backend/capabilities/bundle_assembly/__init__.py
vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py
vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_digest.py
vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_refs.py
vnext/backend/tests/test_bundle_contracts.py
vnext/backend/tests/test_bundle_assembly.py
vnext/backend/tests/test_architecture.py
docs/backend-vnext/contracts/comparison-bundle.md
docs/backend-vnext/capabilities/bundle-assembly.md
```

The implementation fixes `backend-vnext/comparison-bundle/v2`, immutable Bundle contracts,
single/multi-pair organization, optional-pair degradation, bundle-relative logical paths,
content/integrity based final refs, nested JSON ref rewriting, shared snapshot deduplication,
manifest/closure validation, 16 MiB manifest/closure caps, cancellation/deadline boundaries and
publication only after final artifact readback. Bundle imports only Surface public API/contracts,
artifact ports and shared kernel; it does not import comparison, risk, Repository, flow or runtime.
Artifact-store orphan reclamation remains deferred under ADR 0012 because the existing port has no
delete/transaction primitive.

#### S5 verification record

Executed on 2026-08-22 against committed source HEAD
`250f1d0d751590ed9c370986a92838309da30f14` plus the uncommitted S4/S5 worktree. No dependency,
Dockerfile, deployment, Rust or runtime-boundary files changed.

| Check | Result |
| --- | --- |
| focused Bundle/Surface/architecture unit gate | **PASS**; 61 passed |
| full backend unit excluding known legacy oracle | **PASS**; 631 passed, 1 existing Starlette deprecation warning; `--ignore tests/test_table_rules_resolver.py` |
| full backend `pytest -q -m unit` | **PASS for S5 scope / pre-existing external-oracle gap remains**; 707 passed, 58 failures in `tests/test_table_rules_resolver.py` |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **PASS** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **PASS**; 171 source files |
| `git diff --check` | **PASS** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; Python-only Bundle contracts/assembly/tests/docs; inherited R5 image gate remains a final-candidate prerequisite |

The 58 full-unit failures are the inherited `table_rules_legacy_oracle` gap: missing or incompatible
`legacy/backend_vnext` files and registry API. No Dolt, process, network, integration or fixed-timeout
serial fixture was introduced. S6 is the next prerequisite and must independently review the complete
R6 owner/import/digest/recovery boundary.

### S6 — Independent R6 owner/import/digest/recovery review

Objective: review the complete R6 surface without relying on implementer explanations.

Conversation: `new conversation`.

Review focus: public owner graph, forbidden imports, ruleset/comparison separation, status precedence, artifact atomicity, resource caps, cancellation, ref/path safety, cross-pair sharing and no static-risk/flow leakage.

Exit: no open P1/P2; remediation rerun records identify tested tip and exact nodeids.

#### S6 independent review record

S6 is **complete/pass**. The independent record is [P3-R6-S6 Independent Owner, Import, Digest
and Recovery Review](p3-r6-s6-independent-review.md). It reviewed the cumulative Risk, Surface
and Bundle boundary without relying on implementer explanations.

The review found one P2 recovery gap: Bundle validation did not bind manifest semantic fields or
the closure's `bundle_manifest_digest` to the in-memory bundle, and recovery JSON accepted unknown
manifest/closure/entry fields. Bundle recovery now recomputes both bindings and enforces exact
schemas; `test_recovery_rejects_manifest_and_closure_semantic_metadata_tampering` is the
regression owner. Artifact orphan reclamation remains an explicit ADR 0012 defer because
`ArtifactStorePort` has no delete/transaction primitive.

S6 evidence:

| Check | Result |
| --- | --- |
| focused Risk/Surface/Bundle/architecture unit gate | **PASS**; 73 passed |
| backend unit excluding inherited legacy oracle | **PASS**; 632 passed, 1 existing Starlette deprecation warning |
| backend `ruff check .` | **PASS** |
| backend `mypy` | **PASS**; 171 source files |
| `git diff --check` | **PASS** |

Reviewed source tip: `931f9c3ba76b3dcb8847a84f12b79f9073bed287` plus uncommitted S6 Bundle
remediation/tests and review documentation. No Docker/container rebuild is triggered; only Python
capability logic/tests/docs changed, and the inherited R5 image gate remains a final-candidate
prerequisite. S7 may now perform the module gate and handoff in a new conversation.

### S7 — R6 module gate and handoff

Objective: seal the tested source SHA, summarize focused/independent review, record exact unit/lint/type/benchmark commands, carry deferred items and establish R7 entry prerequisites.

Conversation: `new conversation`; acceptance/documentation only.

Exit: `p3_r6_exit = pass`, `p3_r7_ready = yes` only if all gate evidence is present. This does not authorize P3 production integration or change global implementation authorization.

#### S7 verification and handoff record

S7 is **complete/pass**. The tested source candidate is the clean committed source tip
`9739bf03443df37c826e2a73934513524e7e2674`, immediately before adding this acceptance record and
the handoff document. The detailed handoff is [P3-R6 Risk, Surface and Bundle Handoff](p3-r6-risk-surface-bundle-handoff.md).
This is a source/module gate only: it does not authorize P3 production integration, flow wiring,
cache/GC, a Rust risk provider or the global implementation flag.

| Check | Result |
| --- | --- |
| focused R6 Risk/Surface/Bundle/architecture unit gate | **PASS**; 86 passed |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit --ignore tests/test_table_rules_resolver.py` | **PASS**; 632 passed, 1 existing Starlette deprecation warning |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit` | **KNOWN EXTERNAL FIXTURE GAP**; 708 passed, 58 failed, 1 warning; all failures are confined to `tests/test_table_rules_resolver.py` loading the absent/incompatible `legacy/backend_vnext` oracle |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **PASS** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **PASS**; 171 source files |
| `git diff --check` | **PASS** |
| benchmark runner discovery | **NOT APPLICABLE**; exact command and empty result are recorded in the handoff; no numeric result is used as a gate |
| `docker info` | **DEFERRED**; Docker client is present but the daemon is unavailable at `/var/run/docker.sock`, so no image revision or container pass is claimed |

The focused gate covers Risk contract/evaluation/closure, Surface contract/assembly, Bundle
contract/assembly/recovery, and the architecture owner/import graph. The independent S6 review is
closed with no P1/P2 finding; the S3 Risk review is also closed with only ADR 0012 orphan
reclamation accepted as deferred lifecycle work. The known full-unit failures are inherited from
the missing/incompatible legacy oracle and are outside R6 ownership.

The inherited R5 Rust/Cargo backend image gate remains mandatory and deferred. Because this is a
stage exit, the repository container rule also requires rebuilding the current HEAD when Docker is
available; the failed `docker info` check is the evidence for the deferral. No R6 Dockerfile,
dependency, deployment or runtime-boundary change was introduced.

S7 decision: **PASS**; `p3_r6_exit = pass`, `p3_r7_ready = yes`, and
`p3_r6_implementation_authorized = no` / `p3_implementation_authorized = no` remain unchanged.

## 5. Verification policy

R6 pure Python contracts, risk, surface, bundle, digest and artifact tests are `unit`. R6 does not create Dolt repositories. Any fixed timeout/cancellation timing test is `serial` and runs with `-n 0`. Each package runs its mandated ruff and mypy commands. Benchmark runs are measurement-only and must identify dataset/ruleset/provider/revision and raw resource metrics.

Pure Python R6 changes introduce no additional image boundary. However, the repository stage-exit
rule still requires a current-HEAD container rebuild at S7; this gate is deferred when Docker is
unavailable. The inherited R5 image gate remains a final-candidate prerequisite.

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
p3_r6_s1: completed
p3_r6_s1_exit: pass
p3_r6_s1_implementation_authorized: yes
p3_r6_s1_tested_source_sha: 6b9525e0e8acd40d50dad540c0129b842abec746
p3_r6_s1_worktree: dirty_uncommitted_contract_implementation
p3_r6_s2: completed
p3_r6_s2_exit: pass
p3_r6_s2_implementation_authorized: yes
p3_r6_s2_tested_source_sha: 6b9525e0e8acd40d50dad540c0129b842abec746
p3_r6_s2_worktree: dirty_uncommitted_s1_s2_contract_engine_tests_docs
p3_r6_s3: completed
p3_r6_s3_exit: pass
p3_r6_s3_initial_reviewed_source_sha: fd2d2f99f19039abd4262990ccf013ff43f55979
p3_r6_s3_tested_source: fd2d2f99f19039abd4262990ccf013ff43f55979_plus_uncommitted_risk_remediation
p3_r6_s3_worktree: dirty_risk_remediation_and_review_record
p3_r6_s3_remediation: pair_cap_commit_boundary_count_only_and_annotation_schema_closed; orphan_reclamation_deferred_under_adr_0012
p3_r6_s4: completed
p3_r6_s4_exit: pass
p3_r6_s4_tested_source_sha: 250f1d0d751590ed9c370986a92838309da30f14_plus_uncommitted_surface_changes
p3_r6_s4_worktree: dirty_surface_contract_assembly_tests_and_docs
p3_r6_s5: completed
p3_r6_s5_exit: pass
p3_r6_s5_tested_source_sha: 250f1d0d751590ed9c370986a92838309da30f14_plus_uncommitted_surface_bundle_changes
p3_r6_s5_worktree: dirty_surface_bundle_contract_assembly_tests_and_docs
p3_r6_s5_deferred: orphan_reclamation_under_adr_0012;legacy_table_rules_oracle_gap;inherited_image_gate
p3_r6_s6: completed
p3_r6_s6_exit: pass
p3_r6_s6_reviewed_source_sha: 931f9c3ba76b3dcb8847a84f12b79f9073bed287
p3_r6_s6_worktree: dirty_s6_bundle_recovery_remediation_tests_and_review_doc
p3_r6_s6_remediation: bundle_manifest_semantic_binding_and_closure_manifest_digest_closed
p3_r6_s6_deferred: orphan_reclamation_under_adr_0012;legacy_table_rules_oracle_gap;inherited_image_gate
p3_r6_s7: completed
p3_r6_s7_exit: pass
p3_r6_s7_tested_source_sha: 9739bf03443df37c826e2a73934513524e7e2674
p3_r6_s7_worktree: clean_source_at_gate_then_acceptance_docs_added
p3_r6_s7_deferred: orphan_reclamation_under_adr_0012;legacy_table_rules_oracle_gap;inherited_image_gate
p3_r6_exit: pass
p3_r7_ready: yes
p3_r6_handoff: p3-r6-risk-surface-bundle-handoff.md
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
- [P3-R6-S6 Independent Owner, Import, Digest and Recovery Review](p3-r6-s6-independent-review.md)
- [P3-R6 Risk, Surface and Bundle Handoff](p3-r6-risk-surface-bundle-handoff.md)
- [Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)
