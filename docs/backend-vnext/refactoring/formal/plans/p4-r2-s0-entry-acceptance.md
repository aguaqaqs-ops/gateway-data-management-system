# P4/R2-S0 Independent Entry Acceptance

状态：**PASS — DESIGN ACCEPTED; S1a IMPLEMENTATION NOT AUTHORIZED**

日期：2026-08-23

Owner：Backend vNext Architecture Acceptance（independent acceptance context）

上游：[P4/R1 Runtime Contract and State Handoff](p4-r1-runtime-contract-state-handoff.md)、
[P4-R2-S0 Entry Brief](p4-r2-s0-entry-brief.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
acceptance_kind: p4_r2_s0
input_handoff_sha: 1c492b3aad6ff577e2966cc083b14a24337c4f50
input_validated_code_sha: e2703407a1c80d31f6888ce86c0ab9b125464ad5
reviewed_base_sha: 1c492b3aad6ff577e2966cc083b14a24337c4f50
reviewed_candidate_document_set_sha256: da07ad1e34846cac0736f4fbaaca4c95428386ec2e39471d9582b940ec8fe635
candidate_acceptance_record_excluded_from_hash: true
candidate_worktree: documentation_only_candidate_on_clean_reviewed_base
source_code_changed: false
tests_changed: false
dependencies_changed: false
deployment_changed: false
p4_r1_exit: pass
p4_r2_s0: accepted
p4_r2_design: accepted
p4_r2_s1a_authorized: no
p4_r2_authorized: no
accepted_store_topology: same_host_shared_local_sqlite_wal
accepted_transaction_owner: infrastructure_control_db_uow_with_owner_scoped_participants
accepted_step_model: only_runnable_steps_materialized_one_nonfinal_step_per_operation_v1
accepted_takeover_boundary: no_running_token_swap_recovery_policy_precedes_reclaim
accepted_schema_shape: normalized_scalars_plus_canonical_composite_blobs
accepted_migration: stdlib_sqlite_forward_component_v1
accepted_sqlite_profile: wal_foreign_keys_full_immediate_busy_5s
accepted_lease_profile: lease_30s_r3_heartbeat_10s_max_in_flight_1
open_findings: []
deferred_items:
  - production outbox and business T1/T3 remain P5-owned
  - worker/settings/volume/readiness remain R3-owned
  - JobDefinition and successor/checkpoint policy remain R4-owned
  - retry/backoff/effect-aware takeover remain R5-owned
  - retention, backup and real capacity baseline remain deferred to real consumers
next_step: P4-R2-S1a
next_step_authorized: no
next_input_sha: pending_s0_documentation_commit
```

## 1. Candidate identity

本次independent pass从clean committed R1 handoff base `1c492b3`开始，只审查R2 design/S0
documentation candidate及必要的default-context/status修正。`e270340`仍是当前HEAD的ancestor，
从该validated R1 code tip到reviewed base的`vnext/`差异为空；本候选没有修改source、tests、
dependency或deployment。

候选摘要按以下固定顺序计算，明确排除本acceptance record以避免自引用：

```bash
sha256sum \
  docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md \
  docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md \
  docs/backend-vnext/refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md \
  docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-design.md \
  docs/backend-vnext/refactoring/formal/plans/p4-durable-operation-runtime-execution-plan.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r1-runtime-contract-state-handoff.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r2-s0-entry-brief.md \
  docs/backend-vnext/refactoring/formal/plans/p4-r2-durable-store-atomic-transition-execution-plan.md \
  docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md \
  docs/backend-vnext/refactoring/formal/plans/implementation-stages.md \
  | sha256sum
```

复算结果为`da07ad1e...e635`。P4 Active Context和README只负责检索/状态接线，不拥有本文
接受的schema、transaction或CAS语义，因此不进入candidate semantic document set。

## 2. Independent acceptance decisions

### 2.1 Owner and transaction seam — PASS

Operations只拥有Operation/Step port、store outcomes和guarded persistence composition；concrete
SQLite connection、migration和Unit of Work属于`infrastructure.control_db`。future P5 concrete
Unit of Work可以在同一connection中组合business/outbox participant，而R2不预建business table、
production outbox或generic repository framework。

### 2.2 Schema and migration — PASS

schema v1只保存R1 semantic fields和有当前claim consumer的`eligible_at_us` storage metadata。
标量column与canonical composite BLOB不形成full-document双份权威；readback必须重新经过R1
parser。stdlib SQLite component migration是forward-only、transactional且拒绝未来版本；没有
legacy import、downgrade、checksum evidence或automatic repair framework。

### 2.3 Atomicity and stale-writer barrier — PASS

create、first claim、terminal+successor/final、cancel intent都拥有明确cross-row transaction
barrier。每次update组合R1 transition guard、write precondition和SQL CAS；leased write还检查
current lease未过期。direct `RUNNING -> RUNNING` token replacement被禁止，expired step的retry/
attention decision保留给R5/JobDefinition owner，因而没有blind replay或effect authority泄漏。

### 2.4 Bounded operation and assurance — PASS

首版`max_in_flight=1`、claim limit 1、30秒lease、R3建议10秒heartbeat、5秒busy timeout；所有
query有hard limit和stable ordering。测试策略区分pure/in-memory unit、on-disk WAL integration与
真正fixed-time/process serial；backend不增加xdist。R2不依赖Dolt，不穷举SQLite内部schedule，
不创建durable rejection/audit state。

### 2.5 Deployment and security boundary — PASS

accepted deployment是同主机backend/worker共享可靠local volume；settings、Compose、mount、
entrypoint和readiness仍属R3。R2没有新service、UID/helper、broker、sidecar、custom IPC、NFS/HA
claim或Repository authority。日志明确排除payload、lease token、artifact bytes、SQL和absolute
DB path。

## 3. Acceptance checklist

| Gate | Result | Evidence / condition |
| --- | --- | --- |
| R1 handoff identity | PASS | input `1c492b3`; validated code `e270340` remains ancestor |
| R1 source/test drift | PASS | reviewed-base diff from validated tip contains no `vnext/` changes after R1 remediation seal |
| R2 scope and non-goals | PASS | S0 brief §2–4/§9; no business, Repository, worker or deployment ownership |
| Store/UoW owner | PASS | Operations port vs infrastructure concrete transaction direction is singular |
| Schema/index consumer basis | PASS | only claim/admin/identity/FK consumers; no speculative ref/job-kind indexes |
| Migration and compatibility | PASS | stdlib, forward v1, transactional startup race handling, newer-version rejection |
| Atomicity matrix | PASS | create/claim/publish/cancel and synthetic co-transaction proof are explicit |
| Lease/takeover compatibility | PASS | no direct RUNNING lease swap; R1/R5 boundaries preserved |
| Integrity/recovery proportionality | PASS | active corruption blocks readiness seam; no automatic repair/quarantine journal |
| Test classification | PASS | unit/integration/serial split follows backend marker and no-xdist rules |
| Container/dependency applicability | N/A | documentation-only candidate; no image/dependency/runtime boundary change |
| Default-context consistency | PASS | stale SQLite-store and positive `operation_kind` descriptions corrected |
| Open P1/P2 or contract ambiguity | PASS | none |
| S1a implementation authorization | NO | explicit new user authorization and committed S0 documentation identity required |

## 4. Decision and next prerequisites

`p4_r2_s0: accepted`表示R2详细设计已经收敛，可以作为后续实施authority；它不表示SQLite
schema、port、migration或tests已实现。`p4_r2_s1a_authorized: no`保持不变。

开始S1a前必须：

1. 将本S0 documentation candidate作为docs-only revision封存，S1a handoff记录实际input SHA；
2. 获得明确的`P4-R2-S1a` implementation authorization；
3. 重新检查worktree、input ancestry与R1 Operations source/test tree；
4. 只执行detailed plan §5允许的port/error/architecture paths，不提前进入SQLite adapter。

若candidate摘要、accepted owner/schema/atomicity/takeover边界在封存前变化，必须重新复算并
re-review，不能沿用本PASS。
