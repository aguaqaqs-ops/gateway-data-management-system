# Phase 3 Final Closure and P4/P5 Handoff Execution Plan

状态：F0 entry complete/pass；F1 evidence reconciliation complete/pass；F2 diagnostic benchmark
runner/evidence provisional pass；F3 applicable source gate complete/pass；F4 current-candidate container gate
deferred to the sealed-candidate implementer；F5 independent acceptance and handoff pending；`p3_exit: pending`

日期：2026-08-22

Owner：Backend vNext Architecture Acceptance

上游 handoff：[P3-R7 Mutation and Target Closure Handoff](p3-r7-mutation-target-closure-handoff.md)

Phase exit 基线：[P3 Capability Foundation Design](p3-capability-foundation-design.md#7-phase-3-exit-criteria)

本文是 P3-R1 至 P3-R7 之后唯一的 Phase 3 最终闭合入口。它不是新的 capability module，
因此不编号为 P3-R8。若后续发现必须新增 capability contract 或 production mechanism，必须
reopen 对应 R/Contract，而不是把实现扩入本闭合轮次。

## 1. Objective and exit

本轮只完成 phase-level evidence reconciliation、诊断性 benchmark、最终 candidate gate、
container gate 和 P4/P5 entry handoff。

Phase 3 只有在以下条件同时满足后才可记录 `p3_exit: pass`：

- R1-R7 handoff 对最终 candidate 仍适用，且没有 open P1/P2 或 contract ambiguity；
- 被测试的 source candidate 是一个 clean committed SHA，source/test patch identity 不再代替
  commit；其后的 evidence/handoff record commit 只允许改变 formal records 和 raw measurement
  evidence，并必须同时记录两个 SHA；
- 五个 Python package 的适用测试、ruff 和 mypy 通过；任何外部 fixture 排除必须精确到
  nodeid、说明 owner/reopen condition，且不得写成“已关闭”；
- measurement-only P3 concurrency/cancellation evidence 已保存，包含 revision、dataset、
  provider、环境、wall/CPU/RSS/queue wait、bytes、cancellation latency 和限制；
- 当前最终 candidate 的 backend image 完成 rebuild，release wheel/native import、health
  smoke 和 Compose config 通过；
- final handoff 明确 `p3_exit`、`p4_ready`、tested SHA、image identity、deferred register 和
  P4/P5 ownership，不把 module gate 当作 production integration authorization。

## 2. Scope and non-goals

### 2.1 In scope

- reconcile R6/R7/current-index 中互相矛盾的 test、legacy oracle、Docker 和 authorization 状态；
- 增加最小、可重复、非 SLO 化的 P3 diagnostic benchmark runner 和 raw evidence；
- 运行 source、static、container 和 smoke gates；
- 冻结 durable state、lease/takeover、checkpoint、Repository operation reconciliation 与
  P4/P5 的 owner seam；
- 发布 P3 phase-exit handoff，或在硬门禁失败时保留明确的 `pending/blocked` 状态。

### 2.2 Out of scope

- durable Operation Store、worker、lease、heartbeat、takeover 或 drain 实现；
- Workspace/HTTP/PreviewResult、Submit/finalize、confirmation 或 business persistence；
- 真实 Repository/Dolt effect 接线、production external target adapter 或 multi-target state；
- 新 cache/GC/evidence service、helper/security principal 或 performance SLO；
- 修改 R1-R7 已封存的 capability semantic contract 来规避 gate。

## 3. Entry decision

F0 entry 审查结论为 **PASS**：

- R1-R7 均有 module exit/handoff，R7 `p3_r7_exit: pass`；
- R7 public output 已覆盖 Phase 3 最后一个 planned capability dependency；
- 当前工作开始前 HEAD `3ad7afa3d938011d01685de3fd732af68e891e66` clean；
- 未发现要求在 P3 新增 durable runtime 或 business flow 的 architecture blocker；
- 剩余问题都属于 phase evidence/gate/handoff，适合在本轮闭合。

这只授权 final-closure runner、tests 和 formal records；不授权 P4/P5 implementation。

历史状态键 `p3_implementation_authorized: no` 在本轮收敛解释为“P3 capability 不得接入
production application/HTTP 主路径”。它不否认 R1-R7 已按各 step scoped authorization
完成的 module implementation。后续 handoff 使用无歧义的
`p3_capability_modules_complete` 与 `p3_production_integration_authorized`，旧键仅作兼容别名。

## 4. Durable and reconciliation ownership freeze

| Fact/state | Authority | Final-closure rule |
| --- | --- | --- |
| R4 canonical projection、R7 mutation plan/ChangeSet | owning capability | immutable input/output；不得由 Operation checkpoint 或 R6 presentation 重定义 |
| operation/step status、optimistic version、claim、lease、heartbeat、attempt、retry/cancel、generic checkpoint envelope | P4 Operation Runtime | durable execution mechanism；不取得业务或 Repository effect 所有权 |
| checkpoint payload schema、`operation_kind + step_name`、READY/final-failure business rule | P5 application `JobDefinition` | 使用稳定 DTO、business ID、artifact/digest/ref 和 Repository operation ID；不得使用进程闭包 |
| SubmitAttempt/ArchiveExecution、confirmation、occupancy、T1/T3、Submission/Baseline facts | P5 application/domain | business authority；Operation terminal status不能单独 finalize/abort或释放occupancy |
| Repository import request fingerprint、operation、marker/private ref/main CAS、result、recovery audit | Repository Service | effect/evidence authority；Repository V1保持single-root lock，不引入P4 lease/takeover |
| target-specific ledger/readback/reconcile algorithm | Repository Service or future target adapter | P4只调用并保存稳定结果引用，不自行推断effect |

### 4.1 Lease and takeover

P4 takeover 只接管 application step 的执行权。新 worker 必须加载 versioned checkpoint，
并以既有 immutable request/idempotency identity 和 Repository operation ID 继续查询。
如果 request 可能已送达但 operation ID 响应丢失，只允许以完全相同的 key/fingerprint 重取
Repository 原 operation ID；禁止生成新 key、blind replay 或直接检查 Dolt 推断结果。

Repository Service 内部 startup reconciliation 继续由其 control DB、marker、private ref、
main CAS 和 artifact evidence 决定；P4 lease expiry 不改变 Repository operation 状态。

### 4.2 Checkpoint

P4 只拥有 generic、optimistically-versioned checkpoint envelope。P5 `JobDefinition` 拥有每个
step 的 versioned payload schema。对跨 Repository effect 的 step，最小 payload 包含：

```text
business execution/attempt ID
immutable artifact/ref/digest binding
repository ID + target ref + expected commit
idempotency key reference/request fingerprint
requested verification and unknown-type policy
repository operation ID when known
last observed repository status/result binding
next legal action
```

不得把 full Comparison/Risk/Surface rows、Repository marker/ref evidence副本或可由 owning
authority 重读的状态复制进 checkpoint。

### 4.3 Repository operation reconciliation

```text
P5 T1 transaction
  -> persist business attempt + P4 operation/outbox + immutable request checkpoint
P4 worker
  -> submit/recover original Repository operation identity
  -> poll the original operation; timeout/disconnect remains pending
Repository Service
  -> reconcile marker/private ref/main/artifact and publish authoritative result
P4 worker
  -> persist matching result reference and invoke owner handler
P5 T3 transaction
  -> validate every T1 binding, then finalize or allowed stable-not-published abort
```

`MANUAL_RECOVERY_REQUIRED`、连接失败、poll timeout、worker crash 和 lease expiry 都不得
释放 business occupancy。Production external-target adapter 没有已确认首版 consumer，继续
defer；本轮不为它建立 multi-target durable schema。

## 5. Closure steps

| Step | Scope | Exit |
| --- | --- | --- |
| F0 | entry/applicability/non-goal freeze | **complete/pass** |
| F1 | reconcile R6/R7/index evidence and legacy-oracle disposition | **complete/pass**; current authority uses exact external-fixture disposition |
| F2 | diagnostic runner + raw measurement evidence | runner smoke/ruff pass；final candidate rerun recorded |
| F3 | authoritative tests, exact external-fixture exclusion, five-package ruff/mypy | **complete/pass for current dirty candidate**; sealed-candidate rerun remains F5 |
| F4 | backend image rebuild, native/wheel/health/Compose smoke | current final candidate image identity and commands recorded |
| F5 | independent phase acceptance and P3→P4/P5 handoff | clean committed SHA；`p3_exit: pass` / `p4_ready: yes` |

F5 必须在新 acceptance context 中执行，不依赖本轮 implementer 对未提交工作树的解释。

### 5.1 Candidate and record sealing protocol

为避免 tracked benchmark/handoff evidence 对 Git revision 形成自引用，封版使用两个明确身份：

1. `tested_candidate_sha`：包含 runner、production source、tests 和 pending-status plans 的 clean
   commit；所有 source/static/benchmark/container gates 都针对它执行；
2. `handoff_record_sha`：只加入 raw evidence、实测结果和 final handoff/status 的后继 commit；
   `tested_candidate_sha..handoff_record_sha` 不得包含 production source、test 或 build/deployment
   input 变化。

若 evidence record 需要改变 runner、测试、Dockerfile、Compose、依赖或 production source，原
candidate 立即失效，必须形成新的 `tested_candidate_sha` 并重跑适用门禁。Independent
acceptance 同时核对两个 SHA 和允许的 diff；不得把 handoff record SHA 冒充实际 tested SHA。

## 6. Current evidence

### 6.1 Source gate

`./vnext/scripts/run-tests.sh` 在 base HEAD `3ad7afa3d938011d01685de3fd732af68e891e66`
执行。shared-kernel、repository-contracts、repository-client 分别 **242 / 152 / 154 passed**；
backend 为 **790 passed、58 failed、1 warning**。58 项全部属于：

```text
tests/test_table_rules_resolver.py::test_legacy_oracle_matches_parity_cases
```

失败原因是 `legacy/backend_vnext` 文件缺失或 registry API 不兼容。该失败发生后权威脚本按
fail-fast 停止，不能把本次运行描述成五包全量 pass。

本轮随后执行精确排除，不忽略 `test_table_rules_resolver.py` 中其余 tests：

```text
cd vnext/backend && uv run pytest -q -m unit \
  --deselect 'tests/test_table_rules_resolver.py::test_legacy_oracle_matches_parity_cases'
```

结果为 **790 passed、58 deselected、1 warning**。Repository Service 的 `not serial` 与
`serial -n 0` gates 分别为 **1356 passed / 283 skipped** 和
**92 passed / 113 skipped / 1639 deselected**。五个 Python packages 的 `ruff check .` 与
`mypy` 全部通过，mypy 分别检查 backend/repository-client/repository-contracts/
repository-service/shared-kernel **188 / 26 / 15 / 195 / 34** 个 source files。

F3 对当前 dirty candidate 的 applicable source gate 为 **PASS**。F5 仍须在 sealed candidate
重跑；原 `run-tests.sh` 的 unfiltered external-oracle failure 不得改写为全量 pass。

### 6.2 Legacy oracle disposition

该 oracle 是 test-support discovery evidence，不是 vNext runtime dependency 或正式 semantic
owner。P3 final closure 采用 **known external fixture / exact exclusion**，不采用“gap closed”：

- 保留同文件中由 module-level frozen parity matrix 驱动的 vNext resolver contract tests；
- 只排除上述 external-oracle parameterized nodeid，不忽略整个文件；
- 不从网络或历史 tag 静默恢复 legacy code；
- 若 table-rule parity matrix、owner contract 或 migration/cutover 要求改变，则 reopen R4 和
  fixture owner，并在可复验 legacy source 上重跑 oracle。

这项 disposition 不阻塞 P3 capability exit，但必须进入 handoff deferred/reopen register。

### 6.3 Diagnostic benchmark

Runner：`vnext/backend/benchmarks/p3_capability_diagnostics.py`。

Raw evidence：[p3-final-closure-benchmark.json](p3-final-closure-benchmark.json)。当前记录基于
base revision `3ad7afa3d938011d01685de3fd732af68e891e66` 加本轮未提交 runner，属于 provisional
evidence；F5 前必须在 sealed final candidate 重跑并更新 revision。

该 runner 使用 100,000 rows/pair、4,096 rows/batch、`1/2/4/8` pair、每组 3 次观测，记录
wall、CPU、Linux `ru_maxrss`、queue wait、execution time 和 Arrow bytes；另以 200,000 SQL
statements 测量真实 parser cooperative cancellation。结果只证明 runner/metrics 可用，不
建立性能阈值、不选择 production provider，也不声称是 P5 end-to-end workload。

### 6.4 Container gate

默认 `/var/run/docker.sock` 不存在。本轮曾使用 isolated temporary root/socket 启动本地
Docker daemon，并从当前 worktree 开始 rebuild `vnext/backend/Dockerfile`；构建在 dependency
sync 阶段按任务 owner 的安排主动停止，临时 daemon/root 已清理，未形成可接受的 image
identity 或 smoke 结论。F4 现明确 deferred 给 sealed-candidate implementer；其必须在 clean
committed SHA 上重新完整 build，并完成 native import、health 和 Compose smoke。此前未完成的
临时构建不能作为通过证据。

## 7. Current status

```yaml
current_module: P3-FINAL
p3_final_closure_entry: pass
p3_final_closure_authorized: yes
p3_final_closure_f0: completed
p3_final_closure_f1: completed_pass
p3_final_closure_f2: provisional_pass_requires_sealed_candidate_rerun
p3_final_closure_f3: completed_pass_dirty_candidate_requires_f5_rerun
p3_final_closure_f4: deferred_to_sealed_candidate_implementer
p3_final_closure_f5: pending
p3_final_closure_base_sha: 3ad7afa3d938011d01685de3fd732af68e891e66
p3_capability_modules_complete: yes
p3_production_integration_authorized: no
p3_implementation_authorized: no
p3_legacy_oracle_disposition: known_external_fixture_exact_nodeid_exclusion
p3_benchmark: provisional_measurement_only_evidence_recorded
p3_container_gate: pending_clean_sha_rebuild_and_smoke
p3_exit: pending
p4_design_conversation_ready: yes
p4_ready: no_until_p3_final_handoff
p4_implementation_authorized: no
p5_implementation_authorized: no
```

## 8. Reopen and stop conditions

停止 F5 并 reopen owner，如果发现 R1-R7 public contract/digest 不适用、production provider
golden/differential mismatch、artifact partial publication、unknown-outcome blind replay、
Repository result binding不足、owner cycle、资源上限绕过或任何 open P1/P2。

Docker build/smoke、sealed-candidate tests、`tested_candidate_sha` / `handoff_record_sha` identity
或二者间 evidence-only diff 证明缺失时保持
`p3_exit: pending`，不得用 docs-only acceptance 改写为 pass。

## 9. Normative references

- [P3 Capability Foundation Design](p3-capability-foundation-design.md)
- [P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)
- [P3 Active Context Index](p3-active-context-index.md)
- [P3-R7 Mutation and Target Closure Handoff](p3-r7-mutation-target-closure-handoff.md)
- [Implementation Stages](implementation-stages.md)
- [Operation Lifecycle and Repository Integrity](../contracts/operation-lifecycle-and-integrity.md)
- [External Effect and Recovery](../contracts/external-effect-and-recovery.md)
- [Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)
- [Repository Service](../contracts/repository-service.md)
- [Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)
