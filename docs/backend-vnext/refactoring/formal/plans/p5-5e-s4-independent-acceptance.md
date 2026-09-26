# P5-5E-S4 Independent Slice Exit Acceptance Record

状态：**PASS — `p5_5e_slice_exit: pass`（independent acceptance context，2026-09-26）**

日期：2026-09-26

本记录绑定 S4 最终候选 `217236980350d523101936af5464fbbd9ad66f88` 上的门禁证据；
delivery handoff 见 [p5-5e-s4-handoff.md](p5-5e-s4-handoff.md)。

上游：[Execution Plan §S4](p5-5e-history-compare-execution-plan.md)、
[S3 Stage Exit Acceptance](p5-5e-s3-stage-exit-acceptance.md)。

```yaml
record_kind: p5_5e_slice_exit_acceptance_evidence
acceptance_kind: p5_5e_slice_exit
acceptance_authority: independent_acceptance_context_after_gate_reproduction
candidate_head: 217236980350d523101936af5464fbbd9ad66f88
gate_tested_head: 217236980350d523101936af5464fbbd9ad66f88
decision: pass
findings_closed: [S3-deferred-full-runner, S4-fresh-compose-conjunction]
review_findings_open: []
p5_5e_s1_stage_exit: pass
p5_5e_s2_stage_exit: pass
p5_5e_s3_stage_exit: pass
p5_5e_slice_exit: pass
production_deployment_authorized: no
new_repository_effect_authorized: no
delivery_recommendation: pass_recommended
handoff: docs/backend-vnext/refactoring/formal/plans/p5-5e-s4-handoff.md
compose_gate_provenance: docs/backend-vnext/refactoring/formal/plans/p5-5e-s4-compose-gate-provenance.json
exit_record: docs/backend-vnext/refactoring/formal/plans/p5-5e-slice-exit-final.md
```

## T1 — Five-package static

见 [S4 Handoff Phase 1](p5-5e-s4-handoff.md)；五包 ruff/mypy `--no-incremental` 均 exit 0。

## T2 — Authoritative runner

`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` exit **0**。

| Package | Result |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend | 2702 passed |
| repository_service (parallel) | 1678 passed, 1 skipped |
| repository_service (serial) | 205 passed |

五锁 SHA 与 `compose.yaml` SHA 与 provenance JSON 一致；worktree clean。

**注记**：`repository_service` parallel 1 skipped 沿用 P5-5D S4R2 环境先例；S4 要求的 backend compose 并合为 0 skipped。

## T3 — Fresh build

`build-repository-service-image.sh` 与 `docker compose … build backend worker` exit 0。
repository-service OCI revision = `217236980350d523101936af5464fbbd9ad66f88`；
gate running backend `src` digest = 本地 `0fa5063d2b241ba9e208aa79ac526e2e2b5060856b01e4d2552cd06b322a689f`。

## T4 — Conjunction

`GATEWAY_COMPOSE_GATE_PREBUILT=0`，project `gateway-p5-5e-s4-gate`：**9 passed, 0 skipped**（1070.00s）。
nodeid 列表见 handoff Phase 4。

## Evidence chain

| Stage | Authority |
| --- | --- |
| S0 docs | [p5-5e-s0-independent-docs-acceptance.md](p5-5e-s0-independent-docs-acceptance.md) |
| S1 | [p5-5e-s1-stage-exit-acceptance.md](p5-5e-s1-stage-exit-acceptance.md) |
| S2 | [p5-5e-s2-stage-exit-acceptance.md](p5-5e-s2-stage-exit-acceptance.md) |
| S3 | [p5-5e-s3-stage-exit-acceptance.md](p5-5e-s3-stage-exit-acceptance.md) |
| S4 | 本记录 + [p5-5e-s4-compose-gate-provenance.json](p5-5e-s4-compose-gate-provenance.json) |

## Scope boundary

- **不** 授权 production deployment 或新 Repository effect。
- **不** 与 P5 整体架构/性能收口合并签署；P5 架构集中修复在 5E slice exit 之后进行。
