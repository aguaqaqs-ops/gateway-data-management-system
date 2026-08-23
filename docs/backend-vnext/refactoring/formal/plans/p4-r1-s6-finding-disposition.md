# P4/R1-S6 Finding Disposition

状态：**DISPOSITION RECORDED; REMEDIATION PENDING AUTHORIZATION**

日期：2026-08-23

Owner：Operation Runtime (`gateway_backend.operations`)

上游：[P4/R1-S6 Independent Review](p4-r1-s6-independent-review.md)、[P4/R1-S5 Handoff](p4-r1-s5-handoff.md)、[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)、[Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)

```yaml
step_id: P4-R1-S6-FINDING-DISPOSITION
input_head_sha: 03774b313697f564afe450d9a6890b6c1857aa0f
reviewed_candidate_sha: 1243b1cdf736a1c8f3b10446d33753fce9cb9d40
review_record: p4-r1-s6-independent-review.md
result: rework_required_remediation_pending
scope: docs_only
production_tests_modified: false
public_surface_changed: false
persisted_keys_changed: false
status_matrix_changed: false
manual_recovery_semantics_changed: false
next_step: conditional remediation after explicit authorization
next_step_authorized: false
container_gate: not_applicable_r1_no_runtime_boundary_change
benchmark: not_applicable_contract_state_only
```

## 1. Disposition decision

S6-F1、S6-F2、S6-F3 均保留为 `rework_required`，本记录只完成 owning Contract disposition，
不宣称 production/test remediation 已完成。S7 与 R2 仍未授权。

F1 采用“现有 guard 负责”路径：`validate_operation_transition` /
`validate_step_transition` 既是 status matrix owner，也是候选 record mutation 的关系校验
owner。非终态、非 `MANUAL_RECOVERY_REQUIRED` 的 same-status heartbeat、checkpoint 和
cancel-intent mutation 通过现有 guard 后返回 `APPLY`；`APPLY` 代表 mutation validation
通过，不代表新增 status self-loop 或 status matrix edge。

R2 是首个持久化 consumer，必须在数据库 CAS 前组合调用相应 transition guard 与
`validate_write_precondition`。最终终态的 same-status publication 只有完整 record 相等时
返回 `IDEMPOTENT`；`MANUAL_RECOVERY_REQUIRED` 禁止原地 same-status mutation。该决定不新增
guard、签名、status、persisted key 或 public symbol。

## 2. Finding-scoped remediation matrix

| Finding | Owner | Disposition and authorized future path | Regression proof | Focused rerun | Closure condition | Reopen condition |
| --- | --- | --- | --- | --- | --- | --- |
| S6-F1 P2: non-final same-status guard conflict | `contracts.py` / `state.py`; normative owner is Operation Lifecycle | Keep existing guard behavior; synchronize the lifecycle Contract and §2.7 plan language; future R2 CAS composition must call transition guard plus write precondition. | Shared state parameter tables distinguish accepted non-final same-status `APPLY`, final exact-record `IDEMPOTENT`, conflicting terminal duplicate, and MANUAL barrier; assert identity, append-only, cancel monotonic, timestamp, lease and version checks. | Backend unit state/contract/architecture gate plus independent S6 rerun after remediation. | Contract, implementation and tests all describe `APPLY` as mutation validation without changing the status matrix; no unresolved owner contradiction. | Any new public guard/signature, changed status matrix or MANUAL semantics, or R2 composition that bypasses the existing guard. |
| S6-F2 P2: finite binary64 payload rejected | `contracts.py`; numeric semantics remain Shared Kernel-owned | Accept finite Python binary64 values supported by Shared Kernel JCS/I-JSON; reject non-finite/out-of-contract numbers with `ValueError`; retain opaque payload semantics and existing budgets. | Shared payload table covers finite values through parser, direct record construction and canonical round-trip; non-finite values and numeric boundary failures remain negative cases. | Backend unit contract/state/architecture gate plus five-package static checks; independent S6 rerun. | `{"value": 1.5}` and equivalent finite binary64 values canonicalize and round-trip; NaN/Infinity/out-of-contract values fail closed; no payload version/digest/business interpretation added. | Any change to Shared Kernel numeric contract, payload wire shape, semantic interpretation, digest/version axis or resource budgets. |
| S6-F3 P3: precondition identity bounds missing | `state.py`; existing opaque-ID validator remains owner-local | Reuse the existing package-private opaque-ID validator for `WritePrecondition` worker/lease IDs and current scalar values; preserve exact bool/int checks and `ValueError`. | Shared identity boundary table covers valid 1/255-byte IDs, empty, 256-byte, control-character and Unix/Windows host-path values for constructor and guard inputs. | Backend unit contract/state/architecture gate plus five-package static checks; independent S6 rerun. | Constructor and guard reject every out-of-contract worker/lease identity while valid `StepRecord` and precondition paths remain accepted; no new identity type or error taxonomy. | Any new identity type/security principal, public helper, changed precondition signature, or cross-package/deployment boundary. |

## 3. Scope and sequencing

This disposition commit is docs-only and may modify only formal Contract/plan records. It does not
modify `contracts.py`, `state.py`, `test_operation_contracts.py` or `test_operation_state.py`.

After a separate remediation authorization, the implementation sequence is:

1. Update finite-float validation and shared payload regression tables for S6-F2.
2. Reuse the existing opaque-ID validator in `state.py` and add shared precondition boundary cases
   for S6-F3.
3. Preserve and, if needed, clarify the existing same-status state parameter tables for S6-F1;
   do not add a guard or alter the status matrix.
4. Commit the clean code/test candidate and rerun the focused backend tests/ruff/mypy gates.
5. Run `ruff check . && mypy` in all five Python packages and `git diff --check`.
6. Create the final S6 remediation handoff only after the independent review confirms all three
   findings are closed. After that handoff, do not modify S5/S6 production/tests.

## 4. Verification applicability

The current disposition changes only formal documentation. No Dockerfile, dependency, Compose,
entrypoint, filesystem/UID boundary, worker, HTTP, SQLite, Repository or P5 path is touched;
container rebuild is therefore `not_applicable`. R1 has no throughput or latency claim, so the
benchmark is also `not_applicable`.

The eventual remediation remains pure in-process contract/state logic and must not introduce Dolt,
network, process, thread, serial-timeout or external-effect fixtures.

## 5. Exit and authorization

Current exit is `rework_required`: this record makes the owner decision unambiguous but does not
close the findings. Closure requires code/test remediation, focused and five-package static gates,
`git diff --check`, and an independent review rerun with no open P1/P2 finding.

S7 and R2 remain unauthorized. Any implementation that changes public symbols/signatures, persisted
keys/wire shape, status matrix, MANUAL semantics, Shared Kernel numeric semantics or the R1 boundary
must stop and reopen the owning Contract before further work.
