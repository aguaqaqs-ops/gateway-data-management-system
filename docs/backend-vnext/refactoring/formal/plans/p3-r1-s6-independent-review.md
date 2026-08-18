# P3-R1-S6 Independent Review

状态：S6 complete；无未处理 P1/P2 finding；S7 module gate complete / R1 gate pass

日期：2026-08-19

Reviewed source tip：`fc51595` (`phase1/gate-ownership-repair`)

Review baseline：`d432073`（S0 entry）至 `fc51595`（当前 R1 candidate）

本审核与实现、S4 focused review 和 S5 remediation 对话隔离。结论只依据最终累计
diff、S0 inventory、S4 finding record、formal contract/ADR 以及本文件列出的可重现命令；
不采用实现者口头解释作为 evidence。

## 1. Review input and changed surface

Normative references:

```text
docs/backend-vnext/refactoring/formal/plans/p3-r1-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r1-s0-asset-inventory.md
docs/backend-vnext/refactoring/formal/plans/p3-r1-s4-focused-review.md
docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md
docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md
docs/backend-vnext/refactoring/formal/contracts/canonical-row-hash-compute-boundary.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/adr/0010-minimal-golden-and-ordinary-ci.md
docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md
```

Changed implementation/test surface in `d432073..fc51595`:

```text
vnext/backend/src/gateway_backend/capabilities/
vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py
vnext/backend/src/gateway_backend/infrastructure/artifact_store/local_store.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_artifact_boundary.py
vnext/backend/tests/test_artifact_ref_conformance.py
vnext/backend/tests/support/artifact_staging.py
vnext/backend/tests/test_artifact_staging_conformance.py
vnext/shared_kernel/tests/conftest.py
docs/backend-vnext/refactoring/formal/plans/p3-*.md
```

The implementation surface remains limited to capability ownership skeletons, the existing
canonical-row-hash owner move, and local/test artifact conformance. No parser, source
materialization, storage projection, comparison, risk, mutation planner, application flow,
HTTP, Workspace, Submit, Operation Runtime, retention policy, or new security principal was
introduced.

## 2. Independent checks

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **81 passed** |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_artifact_boundary.py tests/test_artifact_ref_conformance.py tests/test_artifact_staging_conformance.py` | **62 passed** |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**; no issues in 55 source files |
| `cd vnext/shared_kernel && uv run pytest -m unit` | **242 passed** |
| `cd vnext/rust && cargo test -p gateway-shared-kernel --locked` | **passed**; Rust lib 82, vector conformance 3, SQL ENUM/SET 3 |
| `git diff --check d432073..fc51595` | **passed** |

No check used Dolt, Repository Service, HTTP, Workspace, Submit, an operation runtime, or an
external process. The tests use in-memory/local stores and `tmp_path`; no container rebuild is
required because this candidate changes no image, deployment, or container-only runtime
boundary. The current source tip, rather than an older image, is the tested evidence.

Container decision:

```yaml
reviewed_source_tip: fc5159576b30de5bd8c1428446537aa92a23642b
container_rebuild: no
container_rebuild_reason: S6 review/doc changes do not touch image, deployment, or container-only runtime boundaries
last_validated_image_revision: none; source-tree validation is the authoritative evidence
container_validation_deferred_to: S7 final candidate if an image/deployment/container boundary is introduced
```

## 3. Minimum boundary review

| Area | Result | Evidence / disposition |
| --- | --- | --- |
| Contract owner | **Pass** | Concrete capability packages own their public `contracts.py`; canonical row-hash content metadata is no longer a backend-root contract. Backend `artifacts` retains only the four-field nominal envelope. |
| Dependency graph | **Pass** | Architecture tests enumerate the owner set, permitted downstream-to-upstream edges, contracts-only cross-capability imports, and importability. No cycle, `_internal`, provider, planner, builder, cache, or forbidden application/repository import is present. |
| Shared primitive reuse | **Pass** | Python and Rust continue to consume `gateway_shared_kernel` primitives and repository-level vectors. No backend digest, encoding, scalar, or generic failure primitive was added. |
| Artifact boundary | **Pass** | `ArtifactRef` remains `artifact_id/media_type/size_bytes/raw_sha256`; capability semantic/schema digests stay owner-local. Tests verify ref round-trip, no host path, raw/content digest separation, and fresh-store reopen. |
| Partial/corrupt/missing handling | **Pass for R1 staging** | Conformance matrix covers missing bytes, missing sidecar, size/digest corruption, malformed sidecar, and sidecar-replace failure. Failures are fail-closed at the existing store boundary. Durable takeover/recovery is outside R1. |
| Cleanup boundary | **Pass for R1 test staging; production deferred** | `tmp_path` cleanup is isolated from a sibling durable integrity incident. Production retention/cleanup remains the later lifecycle owner under ADR 0012 (`F-004`). |
| Scope and non-goals | **Pass** | Cumulative diff contains only S0-S4 foundation evidence and tests; no R2 parser or downstream capability behavior is pre-implemented. |
| R2 entry handoff | **Conditionally ready** | R2 may consume the public owner/import checks and staging helper after S7 records the R1 module gate. R2 must re-read its parser contracts and must not infer parser semantics from this skeleton. |

## 4. Finding closure

S4 findings `S4-001` through `S4-004`, `S4-006` through `S4-008` remain closed with no
regression in the final candidate. `S4-005` remains an accepted non-blocking limitation:
`LocalArtifactStore` has a process-local ref cache, but it is not a coordination or recovery
mechanism and fresh-store conformance tests verify on-disk identity after reopen. S5 was recorded
as not required, so there are no unverified remediation claims.

The inventory's deferred `F-002` (R4 manifest policy) and `F-004` (production artifact
retention/cleanup) remain outside R1. Neither is a blocker for the R1 test foundation. No new
P1/P2 finding, contract ambiguity, digest/storage boundary violation, capability cycle, or test
classification blocker was found.

## 5. Independent review decision

**S6 PASS.** The final R1 candidate satisfies the S6 minimum checks and has no blocking finding.
It may proceed to S7 module gate/handoff. This is not an R1 gate, does not authorize R2
implementation by itself, and does not authorize SQL/XML parser or downstream P3 capability
implementation.

S7 must record the tested source tip, exact changed paths, commands/results, inventory and
decision register, formal contract/ADR/fixture references, limitations/deferred work, R2 entry
prerequisites, and the implementation-authorization status. The status remains:
`p3_implementation_authorized: no`.

## 6. Carry-forward constraints

- Preserve the capability DAG and contracts-only imports as R2 begins.
- Keep Backend and Repository artifact refs nominally separate.
- Keep semantic/content metadata with its concrete capability owner.
- Treat the local-store cache as process-local adapter state only.
- Keep production retention/cleanup, operation takeover, and durable lifecycle behavior outside
  R1 unless their owning contract/ADR is explicitly reopened.
