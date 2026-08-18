# P3-R1-S4 Architecture/Import and Focused Contract Review

状态：S4 complete；无未处理 P1/P2 finding；S5 remediation not required（R1 implementation authorization remains pending）

日期：2026-08-19

Reviewed source tip：`e3542ecac3076ae25a51d65f029fb6b852e88665`

Review scope：P3-R1 execution plan、S0 inventory、S1/S2/S3 cumulative diff、formal
contracts/ADR，以及当前 backend architecture/import、artifact boundary 和 staging
conformance evidence。审核只依据仓库 evidence，不采用实现者口头解释。

## 1. Evidence

Changed implementation/test surface reviewed:

```text
vnext/backend/src/gateway_backend/capabilities/
vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py
vnext/backend/src/gateway_backend/infrastructure/artifact_store/local_store.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_artifact_boundary.py
vnext/backend/tests/test_artifact_ref_conformance.py
vnext/backend/tests/support/artifact_staging.py
vnext/backend/tests/test_artifact_staging_conformance.py
```

Normative references reviewed:

```text
docs/backend-vnext/refactoring/formal/plans/p3-r1-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md
docs/backend-vnext/refactoring/formal/contracts/canonical-row-hash-compute-boundary.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/adr/0010-minimal-golden-and-ordinary-ci.md
docs/backend-vnext/refactoring/formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md
```

Verification evidence:

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit` | **81 passed** |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_artifact_boundary.py tests/test_artifact_ref_conformance.py tests/test_artifact_staging_conformance.py` | **62 passed** |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**; mypy reports no issues in 55 source files |
| `git diff --check d432073..e3542ec` | **passed** |

No command in this review used Dolt, Repository Service, HTTP, Workspace, Submit, or an
operation runtime.

Container/image decision for this review:

```yaml
reviewed_implementation_tip: e3542ec
review_record_commit: metadata-only commit containing this review record
container_rebuild: no
container_rebuild_reason: docs-only S4 review record; no image, deployment, or container-runtime boundary changed
last_validated_image_revision: none for S4; source-tree evidence is e3542ec
container_validation_deferred_to: S7 final candidate if an image/deployment boundary is touched
```

The implementation tip predates this documentation-only record commit; no production Python or
test behavior changed in the record commit.

## 2. Focused checks and findings

| ID | Review area | Result | Evidence / disposition |
| --- | --- | --- | --- |
| `S4-001` | Shared-kernel duplication | **No finding** | Capability metadata reuses `gateway_shared_kernel.DigestRef`; raw SHA and canonical bytes remain owned by Shared Kernel. No backend digest/encoding copy was added. |
| `S4-002` | Generic-common drift | **No finding** | The owner set contains only concrete capability packages. No `capabilities/common`, `capabilities/utils`, generic provider base, or compatibility alias exists. |
| `S4-003` | Nominal `ArtifactRef` boundary | **No finding** | S3 uses only Backend `ArtifactRef` and the four-field envelope. Content/schema digests remain capability-owned metadata; no Repository ref or shared serialization type was introduced. |
| `S4-004` | Capability cycle/private import | **No finding** | `test_capability_modules_respect_import_dag` checks the declared downstream-to-upstream DAG and contracts-only cross-capability imports. Importability checks pass for every owner. |
| `S4-005` | Hidden mutable state | **Accepted non-blocking limitation** | `LocalArtifactStore` retains a process-local ref cache, already recorded in S0 as non-coordinating adapter state. S3 reopens a fresh store before missing/corrupt sidecar checks; no durable cache or capability state crosses the boundary. Production lifecycle/takeover remains deferred. |
| `S4-006` | Dolt/test dependency | **No finding** | Focused contract, architecture, and staging tests use local/in-memory stores and `tmp_path`; no Dolt fixture, Repository runtime, or external process is created. |
| `S4-007` | Error mapping overreach | **No finding** | Malformed sidecar JCS errors are mapped at the existing `LocalArtifactStore` adapter boundary to `ManifestVerificationError`; the conformance matrix verifies fail-closed behavior. No capability-specific failure registry was added. |
| `S4-008` | Scope expansion | **No finding** | The diff adds only owner skeleton/import checks and artifact test staging conformance. It does not add parser, projection, planner, HTTP, Workspace, operation, retention, or a new security principal. |

The accepted `S4-005` limitation does not reopen an ADR: it is the process-local cache behavior
already bounded by the artifact-store contract and ADR 0012's single-trust-domain scope. It must
not be converted into a broker, sidecar state machine, or production retention mechanism in R1.

## 3. Review decision

S4 focused review **passes**. There are no P1/P2 findings, contract ambiguities, import cycles,
artifact identity violations, or test-classification blockers requiring S5 remediation. S5 is
therefore recorded as not required for this review tip; S6 remains the next independent review
step before any R1 module gate.

This result does not authorize parser or other P3 capability implementation. R1 remains
implementation-authorized: **no**. R1 gate and R2 entry still require the S6/S7 evidence and
handoff conditions in the execution plan.

## 4. R2/S6 carry-forward conditions

- Preserve the capability DAG and contracts-only downstream imports as implementation begins.
- Keep Backend and Repository artifact refs nominally separate; do not move content metadata into
  the generic artifact envelope.
- Treat the local-store ref cache as process-local adapter state, not a coordination or recovery
  mechanism.
- Keep production retention/cleanup, operation takeover, and durable lifecycle behavior outside R1.
- Re-run the focused architecture/import and artifact conformance checks against the final R1 tip.
