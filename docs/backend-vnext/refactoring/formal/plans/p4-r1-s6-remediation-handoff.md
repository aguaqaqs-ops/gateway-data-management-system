# P4/R1-S6 Remediation Handoff

状态：**PASS**（S6-F2/F3 remediation and independent re-review）

日期：2026-08-23

Owner：Operation Runtime (`gateway_backend.operations`)

上游：[P4/R1-S6 Finding Disposition](p4-r1-s6-finding-disposition.md)、[P4/R1-S7 Runtime Contract and State Handoff](p4-r1-runtime-contract-state-handoff.md)

```yaml
step_id: P4-R1-S6-REMEDIATION
input_handoff_sha: 6d227e786c3cd908563b69a206960f015cd814b6
reviewed_candidate_sha: e2703407a1c80d31f6888ce86c0ab9b125464ad5
validated_code_sha: e2703407a1c80d31f6888ce86c0ab9b125464ad5
candidate_worktree_at_review: clean
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/contracts.py
  - vnext/backend/src/gateway_backend/operations/state.py
  - vnext/backend/tests/test_operation_contracts.py
  - vnext/backend/tests/test_operation_state.py
focused_tests: pass
five_package_static: pass
independent_review: pass
container_gate: not_applicable_r1_no_runtime_boundary_change
benchmark: not_applicable_contract_state_only
findings: []
deferred_items:
  - SQLite/WAL atomic CAS remains R2-owned and is not implemented in R1.
  - External-effect cancel/fail/supersede authorization remains R5/JobDefinition-owned.
  - Worker lifecycle, deployment wiring and real Repository effects remain outside R1.
reopen_conditions:
  - Any change to the public surface, persisted keys, status matrix or MANUAL attention semantics.
  - Any change to Shared Kernel numeric semantics, payload wire shape or a new digest/version axis.
  - Any new identity type/security principal or cross-package/deployment boundary.
next_step: P4-R1-S7 final handoff
next_step_authorized: yes
```

## 1. Finding closure

S6-F2 is closed. Inline payload validation now accepts every finite Python binary64 value accepted
by Shared Kernel JCS/I-JSON, while rejecting NaN and both infinities. Parser admission, direct
record construction, canonical bytes and record-document round trips share the same bounded path;
the payload remains opaque and no business interpretation or new version/digest axis was added.

S6-F3 is closed. `WritePrecondition` construction and `validate_write_precondition` now reuse the
existing Operations opaque-ID validator for worker and lease identities. The shared boundary cases
cover valid 1-byte and 255-byte identities plus empty, 256-byte, control-character and Unix/Windows
host-path values for both constructor and current-scalar guard inputs.

F1 remains closed by the preceding docs-only disposition: existing transition guards own same-status
mutation validation without adding a status-matrix self-loop.

## 2. Verification

| Check | Result |
| --- | --- |
| focused R1 unit gate on clean candidate | **PASS**; 398 passed in 2.39s |
| backend unit gate on clean candidate | **PASS**; 1226 passed, 1 Starlette deprecation warning in 48.30s |
| backend `uv run ruff check .` / `uv run mypy` | **PASS**; mypy checked 193 source files |
| shared_kernel ruff/mypy | **PASS**; mypy checked 34 source files |
| repository_contracts ruff/mypy | **PASS**; mypy checked 15 source files |
| repository_client ruff/mypy | **PASS**; mypy checked 26 source files |
| repository_service ruff/mypy | **PASS**; mypy checked 195 source files |
| independent F2/F3 boundary probes | **PASS** |
| `git diff --check` | **PASS** |

The independent probes separately exercised finite `1.5`, negative zero and a small finite value;
NaN/Infinity rejection; valid 1-byte/255-byte identities; and rejection of empty, 256-byte,
control-character and Unix/Windows path identities in both constructor and guard paths.

The candidate changes only the four allowed Operations source/test paths. No Dolt, subprocess,
network, thread, fixed-timeout or serial fixture was introduced. Container rebuild and benchmark
remain not applicable under the R1 boundary.

## 3. Authorization

All S6 findings are closed. This handoff authorizes the final R1 S7 handoff refresh and R2-S0 entry
acceptance discussion only. It does not authorize SQLite/WAL implementation, worker lifecycle,
Repository effects, P5 or deployment work.
