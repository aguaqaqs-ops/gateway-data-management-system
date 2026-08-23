# P3→P4 Context and Code Consolidation — C4 Consumer Audit

状态：`complete`（`c4_continue_plan: yes`；`approved_code_change_bundles: 0`；`c5_status: not_applicable`）

日期：2026-08-23

本记录完成 C4 的只读 consumer audit。没有修改 `vnext/**`、Dockerfile、Compose、依赖或测试，
也没有批准以“清理”为理由改变 P3 contract、fixture oracle、reference deliverable 或
P2-R1 harness。权威计划：[P3→P4 Context and Code Consolidation Execution Plan](p3-p4-context-and-code-consolidation-execution-plan.md) §10。

## Audit identity

```yaml
baseline_sha: 31409c8e0c37d8c12a323269ddeefebdb9927955
pre_cleanup_tag: docs/p3-p4-cleanup-pre-20260823
audited_candidate_sha: 80eb14e6dd38bcc99a0597e62b459686fb740a4c
worktree_at_audit: clean
public_semantics_changed: false
audited_paths: 13
audited_bundles: 7
approved_code_change_bundles: 0
deferred_bundles: 4
kept_bundles: 3
c5_status: not_applicable
```

The candidate SHA is the clean post-C3 tree. A later C2/C3 documentation change does not authorize
code removal; any code implementation must use a new candidate and repeat the applicable gates.

## Evidence method

The following checks were run against the audited candidate:

| Check | Result | Evidence |
| --- | --- | --- |
| Public package exports and `__all__` | pass | `gateway_backend.__init__` exports only `create_app`; `gateway_shared_kernel.testing` is not re-exported from the package root; external-target reference executor remains test/reference-owned. |
| Python imports and dynamic module strings | pass | `rg` found direct test, worker, matrix, script and Compose consumers; no unlisted dynamic import or package entrypoint consumer was found. |
| Package scripts and runtime entrypoints | pass | Backend entrypoint is `gateway_backend:main`; Repository production entrypoint is `gateway_repository_service.app`; `target_gate` is the explicit `repository-probe` command; no candidate is a production script entrypoint except that profile gate. |
| Docker/Compose/profile/runbook | pass | `vnext/deploy/compose.yaml`, `vnext/repository_service/README.md`, `vnext/deploy/p2r1-cache/README.md`, and the Compose integration test still describe/use P2-R1 matrix/target-gate behavior. |
| Tests/fixtures/oracle tooling | pass | Candidate-specific unit, architecture, shared-kernel corpus, provenance, Compose, and corrective audit tests directly import or assert these paths. |
| Owner/recovery value | pass | W2/S6 evidence, P3 reference conformance, P2-R1 provenance, cgroup authorization, workflow isolation, and worker publication remain recoverable or normative evidence. |

Commands used:

```text
rg -n --hidden --glob '!*.pyc' 'synthetic_w2|run_r6_s6_evidence|gateway_shared_kernel\.testing|gateway_repository_service\.(matrix|workflow|workflow_worker|target_gate)|target_gate|repository-probe|test_p2_r1_audit_corrective' vnext docs README.md
rg -n 'importlib|__import__|entry_points|gateway_backend|gateway_shared_kernel|gateway_repository_service' vnext --glob 'Dockerfile*' --glob '*.yaml' --glob '*.yml' --glob '*.sh'
sha256sum \
  vnext/backend/benchmarks/p3_capability_diagnostics.py \
  vnext/backend/src/gateway_backend/capabilities/external_target_sync/_reference_executor.py \
  vnext/backend/src/gateway_backend/synthetic_w2.py \
  vnext/scripts/run_r6_s6_evidence.py \
  vnext/shared_kernel/src/gateway_shared_kernel/testing/__init__.py \
  vnext/shared_kernel/src/gateway_shared_kernel/testing/codec.py \
  vnext/shared_kernel/src/gateway_shared_kernel/testing/dispatch.py \
  vnext/shared_kernel/src/gateway_shared_kernel/testing/validate_frame.py \
  vnext/repository_service/src/gateway_repository_service/matrix.py \
  vnext/repository_service/src/gateway_repository_service/workflow.py \
  vnext/repository_service/src/gateway_repository_service/workflow_worker.py \
  vnext/repository_service/src/gateway_repository_service/target_gate.py \
  vnext/repository_service/tests/test_p2_r1_audit_corrective.py
git status --short --branch && git rev-parse HEAD
```

The audited source hashes are retained in the C1 inventory and the pre-cleanup tag. The current
hashes at C4 are listed below for the code paths whose disposition is not `KEEP` by default:

```text
vnext/backend/src/gateway_backend/synthetic_w2.py                         2baab12901cf0a80673310b7cfe55cce06a68c1111cd011d98dbc58cf8af162d
vnext/scripts/run_r6_s6_evidence.py                                      768c7b148ee342ba8566ec6ed2d7029c73f2ad835497b7dca309de0f004dae65
vnext/shared_kernel/src/gateway_shared_kernel/testing/__init__.py         f7e4e382cab2888e113f0bd9893ba3c1ec074ceb61c6486e976d779f597512ff
vnext/shared_kernel/src/gateway_shared_kernel/testing/codec.py             ea79d8f091321f850cc0754c142027f96db9e39476a26596167bd80308391182
vnext/shared_kernel/src/gateway_shared_kernel/testing/dispatch.py           27a0f0721bdcbdb8e842466c9de0f7a3c906b6cacff0746ed036513bfaf164c0
vnext/shared_kernel/src/gateway_shared_kernel/testing/validate_frame.py     ee54cec7aa4940441e48df2d376fd3b0ca46126c43fabb3d36085cf6292291b3
vnext/repository_service/src/gateway_repository_service/matrix.py          a13401f2638c0d9399b83a1e54be44aba8bd68a1b93ac1e6a46581cebdc98700
vnext/repository_service/src/gateway_repository_service/workflow.py        eccecb13dae48991fa843632ed4e8c074e9904f6b38e6b2bfa5128d84f021c0b
vnext/repository_service/src/gateway_repository_service/workflow_worker.py 7f045bd8702aa4ce833e541649809b8818fc8ebd7730bf3e7eb541b3447e874b
vnext/repository_service/src/gateway_repository_service/target_gate.py     7e84f780d074c1848b8f8712406f9ef52eb391268d93204ca2055252842eb62b
```

## Disposition

| Bundle / paths | Consumer graph and owner evidence | C4 decision | C5 authorization |
| --- | --- | --- | --- |
| `KEEP_EVIDENCE_TOOL` — `benchmarks/p3_capability_diagnostics.py` | P3 final handoff, final benchmark JSON, and capability execution plan are source/evidence pointers. | `KEEP` | none |
| `KEEP_P3_REFERENCE` — `external_target_sync/_reference_executor.py` | External-target tests and support oracle consume it; the capability package owns the reference conformance role. | `KEEP` | none; deletion requires R7 reopen |
| `MOVE_REMOVE_CANDIDATE` — `synthetic_w2.py`, `run_r6_s6_evidence.py` | Unit tests import the module; backend architecture tests explicitly classify the import as forbidden for production capability code; the script imports the module and drives Stage-I evidence. No release entrypoint was found, but owner disposition for relocation/removal is absent. | `DEFER` | not authorized; retain until an owner-approved test-support/evidence migration plan exists |
| `MOVE_CANDIDATE` — `gateway_shared_kernel.testing/*` | Shared-kernel corpus tests and backend architecture tests import/assert the namespace. It is test-only by intent, but currently lives in the production source/package-build tree and relocation changes cross-package test imports. | `DEFER` | not authorized; require package/install and fixture-path proof plus owner approval |
| `RETIRE_DECISION_REQUIRED` — `matrix.py`, `workflow.py`, `workflow_worker.py` | `target_gate` execs `matrix`; `matrix` imports workflow; workflow execs `workflow_worker`; corrective and provenance tests import symbols; Repository README documents matrix commands and W2/W8 gates. | `DEFER` | no change authorized; an explicit P2-R1 harness/profile decision is required before KEEP/RETIRE |
| `KEEP_UNTIL_PROFILE_RETIRED` — `target_gate.py` | Compose `repository-probe` profile invokes it; Compose integration and corrective tests assert the command and verified cgroup handoff. | `KEEP` | none; profile retirement must precede any bundle change |
| `FOLLOW_HARNESS_DECISION` — `test_p2_r1_audit_corrective.py` | `run-tests.sh` and testing conventions include the test suite; it owns assertions for matrix/workflow/target-gate safety and provenance. | `DEFER` | no change authorized; follow the harness decision, do not delete independently |

No bundle has a closed consumer graph that supports `REMOVE` or `MOVE` during this cleanup. The
absence of a production import is insufficient where a test oracle, evidence record, release/profile
command, or recovery procedure is still authoritative.

## Verification

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -q tests/test_synthetic_w2.py tests/test_architecture.py` | 25 passed |
| `cd vnext/shared_kernel && uv run pytest -q tests/test_canonical_cases.py tests/test_validate_scalar_frame.py tests/test_sql_enum_set_values.py tests/test_testing_exports.py` | 145 passed |
| `cd vnext/repository_service && uv run pytest -q -m unit tests/test_p2r1_runtime_provenance.py tests/test_p2_r2_compose_integration.py` | 48 passed |
| `git diff --check` and manifest/record structural checks | pass |

Container rebuild: `not_applicable`. C4 made no Dockerfile, Compose, entrypoint, deployment,
dependency, or container-only runtime change. The existing `repository-probe` profile is a reason to
retain the harness, not evidence that a new image has been validated.

## Gate and reopen decisions

- No code, test, package, deployment, or container change is authorized by C4.
- C5 is `not_applicable`; C6 must carry this record and the zero-approved-bundle result into the
  implementer handoff.
- A future `MOVE` of shared-kernel testing helpers requires package build/install evidence, updated
  imports, architecture-boundary test coverage, and five-package static checks.
- A future synthetic-W2 removal requires an owner decision on historical S6 evidence retention and
  deletion/migration of its mechanism-only tests as one bundle.
- A future Repository harness retirement requires a new decision covering Compose profile, target
  launcher, matrix/workflow/worker, README/runbook, provenance tests, and the applicable container gate.
- Any proposed change to the external-target reference executor reopens P3-R7; any proposed change
  to P2-R1 matrix/provenance semantics reopens the owning P2 handoff.

## C4 exit

```yaml
c4_exit: pass
c4_continue_plan: yes
consumer_graphs_closed_for_remove_or_move: false
approved_code_change_bundles: []
deferred_bundles:
  - MOVE_REMOVE_CANDIDATE
  - MOVE_CANDIDATE
  - RETIRE_DECISION_REQUIRED
  - FOLLOW_HARNESS_DECISION
kept_bundles:
  - KEEP_EVIDENCE_TOOL
  - KEEP_P3_REFERENCE
  - KEEP_UNTIL_PROFILE_RETIRED
c5_status: not_applicable
p3_exit: pass
p4_ready: yes
p4_implementation_authorized: no_until_p4_entry_acceptance
```
