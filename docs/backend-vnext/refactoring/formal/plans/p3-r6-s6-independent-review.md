# P3-R6-S6 Independent Owner, Import, Digest and Recovery Review

状态：**S6 complete；无未处理 P1/P2 finding；S7 未执行**

日期：2026-08-22

Reviewed source tip：`931f9c3ba76b3dcb8847a84f12b79f9073bed287` plus the uncommitted S6
Bundle recovery remediation and regression test. The review was isolated from the S1-S5
implementation conversations and relies only on the public contracts, cumulative source tree,
tests and commands recorded here.

## 1. Review boundary

The independent review covered:

- Risk, Surface and Bundle public owner DAGs and forbidden HTTP/application, flow, Repository/Dolt,
  legacy, private-provider and test-support imports;
- comparison/risk separation, frozen ruleset identity, semantic digest inputs and exclusion of
  refs, operation state, host paths and diagnostics from semantic digests;
- READY/DEGRADED/FAILED/CANCELLED precedence, degraded no-record entries, cancellation/deadline
  checkpoints and table/pair/manifest/closure/JSON resource caps;
- annotation, surface and bundle artifact integrity, nested ref rewriting, cross-pair snapshot
  sharing, logical-path scope and host/cache/repository ref rejection;
- recovery replay of manifest and closure metadata, destination-write failure, missing/tampered
  source artifacts, and absence of partial public publication;
- unit marker classification and absence of Dolt, process, network or fixed-timeout fixtures.

Out of scope: static-risk providers, comparison algorithm/R5 facts, cache/GC and retention,
P5 flow integration, Rust risk parity, production Repository/Dolt adapters and the inherited R5
image gate.

## 2. Independent evidence

| Check | Result |
| --- | --- |
| focused R6 Risk/Surface/Bundle/architecture unit gate | **PASS**; 73 passed |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit --ignore tests/test_table_rules_resolver.py` | **PASS**; 632 passed, 1 existing Starlette deprecation warning |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **PASS** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **PASS**; 171 source files |
| `git diff --check` | **PASS** |

The focused gate was:

```text
tests/test_bundle_assembly.py tests/test_bundle_contracts.py
tests/test_surface_assembly.py tests/test_risk_evaluation.py tests/test_architecture.py
```

All tests use in-memory stores or `tmp_path`; no Dolt repository, Repository process, shell/SQL,
network, integration fixture or fixed-timeout serial test was introduced. No Docker/container
rebuild is triggered: S6 changed Python Bundle recovery validation, tests and documentation only;
the inherited R5 image gate remains a final-candidate prerequisite.

## 3. Findings register

| ID | Area / disposition | Evidence |
| --- | --- | --- |
| `S6-001` | Bundle recovery semantic binding and schema / **P2 closed** | `validate_bundle()` previously checked closure entries and `bundle_digest` but did not bind manifest semantic fields or `closure.bundle_manifest_digest` to the in-memory bundle, and recovery JSON accepted unknown manifest/closure/entry fields. It now recomputes the expected manifest semantic payload and digest and enforces exact recovery schemas. `test_recovery_rejects_manifest_and_closure_semantic_metadata_tampering` passes. |
| `S6-002` | Artifact orphan lifecycle / **accepted defer** | A later destination-store write can leave opaque artifacts unreachable because `ArtifactStorePort` has no delete/transaction primitive. No manifest, closure or public Bundle result is returned on failure. Reclamation remains ADR 0012 lifecycle work and the inherited R5 deferred register. |
| `S6-003` | Owner/import boundary / **pass** | Architecture owner set, allowed DAG and forbidden import scan pass. Risk imports only public Comparison/artifact/shared-kernel ports; Surface consumes public Comparison/Risk contracts; Bundle consumes public Surface/artifact/shared-kernel ports. No flow, Repository/Dolt, legacy, static provider or test-support import is present. |

No additional P1/P2 finding, contract ambiguity, digest owner collision, resource-cap bypass,
partial READY publication, unsafe logical path, cross-pair scope leak, automatic provider fallback
or incorrect test marker was found.

## 4. Boundary dispositions

| Area | Result | Evidence / disposition |
| --- | --- | --- |
| Status and failure precedence | **Pass** | Contract result types reject outputs for FAILED/CANCELLED; Surface rejects failed/cancelled ComparisonFacts; Bundle required-pair failure is FAILED and optional-pair failure is DEGRADED. |
| Digest ownership and replay | **Pass after S6-001** | Risk, Surface and Bundle semantic digests exclude runtime refs/diagnostics as specified. Bundle recovery now binds both manifest semantic payload and closure-to-manifest digest, and rejects unknown recovery fields, before accepting replay. |
| Closure atomicity | **Pass with deferred lifecycle** | Source readback and every destination write are integrity-checked before final Bundle validation; failure returns no public refs. Opaque orphan reclamation remains deferred under ADR 0012. |
| Resource and cancellation bounds | **Pass** | Risk table/pair and artifact/JSON budgets, Surface JSON/wall-time budgets and Bundle manifest/closure/wall-time checkpoints are covered by focused tests. |
| Ref/path and sharing safety | **Pass** | Host-path and reserved cache/repository/flow prefixes are rejected; cross-pair snapshot artifacts are canonicalized to shared paths and duplicate logical paths fail closed. |

## 5. Deferred and reopen register

Carry forward: static-risk rules/provider, unified static/diff aggregation, Rust risk kernels and
differential tests, risk/surface/bundle cache, artifact GC/retention, P5 flow integration, the R5
legacy table-rules oracle gap and the inherited image gate.

Reopen R6 if a capability imports a forbidden owner, risk rules alter comparison semantics, static
risk enters the R6 DTO, a partial artifact becomes publicly visible, degraded tables lose terminal
closure entries, confirmation persistence enters R6, a resource cap is bypassed, automatic provider
fallback is introduced or a new security principal/helper/service is proposed.

## 6. Decision

**S6 PASS.** The independent review has no open P1/P2 finding. S7 may perform the module gate and
handoff in a new conversation. This record does not claim S7, the R6 module gate, production
integration, container validation or global implementation authorization.

```yaml
p3_r6_s6: completed
p3_r6_s6_exit: pass
p3_r6_s6_reviewed_source_sha: 931f9c3ba76b3dcb8847a84f12b79f9073bed287
p3_r6_s6_worktree: dirty_s6_bundle_recovery_remediation_tests_and_review_doc
p3_r6_s6_remediation: bundle_manifest_semantic_binding_and_closure_manifest_digest_closed
p3_r6_s6_deferred: orphan_reclamation_under_adr_0012;legacy_table_rules_oracle_gap;inherited_image_gate
p3_r6_implementation_authorized: no
p3_implementation_authorized: no
```
