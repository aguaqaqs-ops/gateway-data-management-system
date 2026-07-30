# Phase 2 Repository Service Foundation — Interactive Design Session Guide

状态：**Resolved / Formalized**

适用阶段：Backend vNext Phase 2 — Repository Service Foundation

用途：为跨对话、多轮的 Phase 2 正式设计提供持久化工作协议，避免因上下文压缩或
新建对话丢失约束、已确认决定和设计进度。

本文件是临时设计指导与讨论载体，不是 Repository Service 的正式 contract。
最终规则必须按 semantic ownership 写入 `formal/`。只有整体设计完成一致性复审并
得到用户明确确认后，本文件才能标记为 `Resolved`。

---

## 1. 工作方式

本任务采用：

> 仓库审计 → 分轮交互设计 → Decision Ledger → 整体一致性复审 →
> 用户整体确认 → formalization → 文档验证

不得在第一轮直接生成完整最终设计。每轮只处理当前 design package，并在用户
明确确认本轮后进入下一轮。

本任务默认：

- 只进行设计和设计文档修改；
- 不实现 production code；
- 不修改 Phase 1 的 source/runtime/image identity；
- 不 commit、push、部署或发布；
- 不自动 bless vector、golden 或 scenario；
- 不清理或覆盖不属于本任务的用户变更。

如果用户后续明确授权其中某项动作，以最新授权为准。

### 1.1 Caller-owned rigor 与 Repository Service 最小责任

Phase 2 的总设计原则是：

> Repository Service 提供通用、可观测、可恢复的表数据存储机制和 effect
> evidence；外部调用方显式选择其业务所需的结果可靠性、freshness、并发覆盖和
> retention 强度，并对该选择的业务后果负责。

因此，内容或业务结果严谨度不得在 Repository Service 内形成隐藏默认、统一最高
成本路径或追溯修改其他 operation 的二次状态机。Verification level、
mutable-resource concurrency mode、read binding、artifact retention 及其他同类
policy 应由 caller 显式选择；Repository Service 记录 requested/completed policy
和对应 evidence，但不判断该强度是否足以支持 caller 的业务 finalize。

该原则不允许 caller 关闭 Repository Service 解释自身行为所需的最小责任：

- authentication/authorization、input/path/resource safety；
- idempotency、request/effect identity、journal、atomic publication evidence；
- writer ownership/fencing、unknown-effect reconciliation；
- provider/storage/control authority 的内部一致性；
- transport、stream 和已发布 artifact 的完整性。

后续设计若拟强制 full content scan、CAS、跨 store 一致性、长期数据保留或额外
业务审批，必须先证明它属于上述服务自身安全闭包；否则应改为 caller-explicit
policy、由上层业务 owner 承担，或延后到有真实 consumer evidence 时再增加。
不得为“绝对可靠”建立没有明确 owner 的 overlay、补偿状态机或后台纠错系统。

---

## 2. 冻结基线

开始或恢复设计时必须独立复核：

| 项 | 预期值 |
| --- | --- |
| Repository | `/root/gateway-data-management-system` |
| Branch | `main` |
| Phase 1 exit source | `7702d2127712193a8a88e66ba614dc073922ac15` |
| Phase 1 closure commit | `9b4adbcb27b322c625f14f628ed80450826b7c0d` |
| Phase 1 gates | `PR-CORRECTNESS`、`PR-NATIVE`、`PHASE-EXIT-CONTAINER` 全部 PASS |
| Phase 1 blocking register | empty |

Phase 1 source、runtime、image、locks、vectors、golden 和 formal scenario
identity 已冻结。Phase 2 设计不得重写或冒充这些 identity。

当前已知但仍须核实的仓库事实：

- `vnext/repository_service` 只是最小 bootstrap；
- 当前能力主要是 settings、Dockerfile 和 normative vector consumer；
- Dolt 预期固定为 2.1.11；
- Remote Repository transport 尚无正式裁决。

每次新对话开始时记录：

1. branch、HEAD、Phase 1 closure ancestor；
2. `git status --short`；
3. Repository Service、deploy、client、contracts、tests、fixtures、locks 清单；
4. 当前实现能力与结构性缺口；
5. 本文件 §5 的 session state。

---

## 3. Authority 与阅读要求

开始 Round 0 前必须完整阅读：

1. `docs/backend-vnext/refactoring/formal/README.md`
2. `docs/backend-vnext/refactoring/formal/architecture/architecture-and-refactoring-plan.md`
3. `docs/backend-vnext/refactoring/formal/plans/implementation-stages.md`
4. `docs/backend-vnext/refactoring/formal/contracts/contract-taxonomy-and-ownership.md`
5. `docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md`
6. `docs/backend-vnext/refactoring/formal/contracts/external-effect-and-recovery.md`
7. `docs/backend-vnext/refactoring/formal/contracts/performance-measurement-and-baseline.md`
8. `docs/backend-vnext/refactoring/formal/contracts/business-lifecycle-and-state.md`
9. `docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md`
10. `docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md`
11. `docs/backend-vnext/refactoring/formal/policies/rust-safety-and-performance-policy.md`
12. `docs/backend-vnext/refactoring/formal/adr/0002-minimal-persisted-business-state.md`
13. `docs/backend-vnext/refactoring/formal/adr/0003-external-effect-reconciliation.md`
14. `docs/backend-vnext/refactoring/formal/adr/0004-raw-source-artifact-and-canonical-dolt-storage.md`
15. `docs/backend-vnext/refactoring/formal/adr/0007-vnext-performance-baseline-authority.md`
16. `docs/backend-vnext/refactoring/temporary/project-environment-preparation.md`
17. `docs/backend-vnext/refactoring/temporary/phase-1/phase-1-closure-signoff.md`
18. 当前 `vnext/repository_service`、`vnext/deploy`、相关 tests、Docker 和 lock
    文件。

Authority 顺序：

```text
accepted formal contract / architecture / policy
  > accepted ADR
  > accepted evidence / closure
  > implementation / tests
  > temporary history
  > legacy
```

如果正式文档之间存在实质冲突：

1. 暂停受影响设计；
2. 指出冲突规则和 downstream impact；
3. 识别 semantic owner；
4. 提出 formal contract 或 ADR 的收口方案；
5. 得到用户确认后再继续。

不得用实现兼容两套正式语义。Legacy 只用于行为或 fixture 发现，不拥有 vNext
contract、接口或架构。

---

## 4. `$grill-me` 使用约束

如果新对话中提供 `$grill-me`，可以用它执行深入访谈，但必须受本文件约束。
如果不可用，则由主 agent 手动执行相同流程，不得因此跳过交互确认。

`$grill-me` 不得变成无边界需求访谈：

- 先读仓库和 authority，再提问；
- 严格按 §7 的 Round 顺序；
- 每轮只讨论当前 design package；
- 每轮提出 2～5 个会实质改变 contract、架构、数据、一致性、恢复、部署、
  安全或验收的高价值问题；
- 每个问题必须提供推荐方案、备选方案、主要取舍和 downstream impact；
- 能从仓库确认的事实不得询问用户；
- 命名、日志格式等低影响事项不得阻塞设计；
- 当前轮未确认前不得进入下一轮；
- 新冲突只重开受影响的决定，不从头重做全部设计；
- 全部 Round 完成后停止访谈，进入整体一致性复审；
- 未得到“整体设计确认，可以 formalize”前不得写正式结论。

本设计不使用 `$design-readiness` 的“五个问题上限”作为完整访谈流程。
`design-readiness` 只适合轻量开工检查，不能替代下述多轮设计。

---

## 5. Session State

每轮确认和每次对话结束前必须更新本节。

| 字段 | 当前值 |
| --- | --- |
| Design status | `RESOLVED` |
| Current round | `F0 Formal closure — PASS / ready for WP0-R1` |
| Last confirmed round | `Round 11 implementation plan` |
| Accepted decision count | `141` |
| Open blockers | `None` |
| Deferred decisions | `Non-blocking items remain assigned to later phases or evidence-driven reopen conditions` |
| Consolidated review | `Confirmed by user / 2026-07-30` |
| Formalization authorized | `Yes / explicitly authorized by user / 2026-07-30` |
| F0 result | `PASS / formal blocking register empty / ready for WP0-R1` |

允许的 Design status：

```text
NOT_STARTED
AUDITING
INTERVIEWING
CONSOLIDATING
AWAITING_OVERALL_APPROVAL
FORMALIZING
VALIDATING
RESOLVED
BLOCKED
```

恢复对话时先读取本节和 §6 索引列出的全部 Decision Ledger，不得重新询问已经
Accepted 的问题。

---

## 6. Decision Ledger Index

Decision 正文按已稳定的 Round 分组保存在 companion ledger 中；本指南只保存
流程、当前状态和索引，禁止复制 decision 正文形成第二 authority。
Round 4–6 的阶段性依赖图、OPEN 项和恢复入口见
[README.md](README.md)，该索引不拥有 decision 语义。

| Round | Ledger | 当前记录 |
| --- | --- | --- |
| Round 0–3 | [decision-ledger-round-0-to-3.md](decision-ledger-round-0-to-3.md) | `58 total / 51 ACCEPTED / 7 SUPERSEDED` |
| Round 4–7 | [decision-ledger-round-4-to-7.md](decision-ledger-round-4-to-7.md) | `32 total / 32 ACCEPTED` |
| Round 8–11 | [decision-ledger-round-8-to-11.md](decision-ledger-round-8-to-11.md) | `58 total / 58 ACCEPTED` |

后续 ledger 在首个对应 decision 被用户确认时创建；不得提前写入未确认决定。
Decision ID、状态、必需字段、supersession 和 reopen 规则由各 ledger 开头的
governance 说明约束。§5 的 Accepted decision count 是所有 ledger 的聚合计数。

---

## 7. 交互协议

### 7.1 每轮输出模板

每轮必须按以下顺序：

1. **Authority facts**：仓库和正式文档已确定什么；
2. **Decision boundary**：本轮必须决定什么、明确不决定什么；
3. **Options**：方案 A/B/C；
4. **Recommendation**：推荐默认值及理由；
5. **Impact**：对 API、数据、一致性、恢复、部署、安全、测试和后续阶段的影响；
6. **Questions**：2～5 个问题；
7. **Reply format**：方便用户逐项回答或选择“全部按推荐”。

用户回答后：

1. 复述本轮最终决定；
2. 更新 §6 索引指向的 owning Decision Ledger；
3. 标明 Accepted、Rejected、Deferred、Open；
4. 指出 downstream constraints；
5. 更新 §5 Session State；
6. 询问用户是否“确认本轮并进入下一轮”。

只有用户明确确认后才能进入下一轮。

### 7.2 三个强制停止点

1. **Round stop**：每轮必须确认。
2. **Overall stop**：全部轮次完成后必须进行 Consolidated Design Review。
3. **Formalization stop**：只有用户明确回复“整体设计确认，可以 formalize”
   后才能生成正式设计文档。

---

## 8. 设计轮次

### Round 0：设计章程与 Decision Map

只确认：

- Phase 2 系统边界；
- accepted formal 已固定的规则；
- Phase 2 non-goals；
- 设计包及依赖；
- 用户必须确认的事项；
- 可采用工程默认值的事项；
- 后续轮次与预计决策数量。

本轮不做 transport 等具体技术裁决。交付 Phase 2 Design Decision Map。

### Round 1：服务边界、部署假设与 transport

确认：

- Repository Service 信任边界；
- REST、gRPC、Arrow Flight 或组合；
- control plane / bulk data plane；
- wire serialization；
- API versioning；
- Local/Remote client 边界；
- 单机部署及未来多节点兼容边界；
- 第一版是否引入真实外部对象存储。

必须给出明确推荐方案。

### Round 2：Identity、资源模型与公共 API

确认：

- Repository ID、ref、immutable ref、commit、artifact、operation、idempotency key；
- opaque identifier 规则和生命周期；
- request/response envelope；
- pagination、stream、deadline、cancellation；
- error envelope 与兼容策略。

API 至少覆盖：

```text
CreateRepository
GetRepository
ResolveRef
GetCommit
GetCatalog
StreamTableRows
ExportTable
DiffRefs
SubmitImport
GetOperation
CreateRef
CreateImmutableRef
CompareAndSetRef
DeleteRef
PlanGarbageCollection
ExecuteGarbageCollection
```

外部 contract 不得返回 server path、run directory、Dolt directory 或内部对象。

### Round 3：读侧一致性与大数据传输

确认：

- immutable commit 一致性边界；
- `open_ref()` resolve + pin；
- catalog、rows、diff、export；
- schema/order/digest binding；
- pagination/chunk envelope；
- streaming/backpressure/cancellation/deadline；
- artifact reference；
- 大数据传输组合；
- 客户端断连 cleanup。

### Round 4：Dolt ownership、registry 与 storage layout

确认：

- Dolt binary/process ownership；
- process lifecycle；
- repository registry 持久化；
- repository/staging/volume layout；
- command/SQL boundary；
- canonical import projection；
- committed readback；
- process crash/restart；
- registry/disk reconciliation；
- fresh repository；
- backup/restore boundary。

Public contract 不得感知本地 repository path。

### Round 5：写侧 journal、幂等、lease 与 CAS

确认：

- PREPARED/APPLIED/VERIFIED journal；
- T1/T2/T3 effect boundary；
- journal persistence；
- idempotency scope、request digest、collision、retention；
- writer lease acquire/renew/fencing/release/crash recovery；
- concurrent writers；
- `CompareAndSetRef`；
- immutable ref；
- delete semantics。

Normal write 只有 full committed-ref `SnapshotManifest` readback 匹配后才能
进入 `VERIFIED`。

### Round 6：Failure、unknown outcome 与 reconciliation

确认：

- typed failure taxonomy；
- retryability 与 effect classification；
- unknown outcome；
- evidence-first recovery；
- journal crash matrix；
- timeout/cancel/disconnect；
- service/Dolt crash；
- stale journal/lease/staging；
- readback mismatch；
- cleanup precedence；
- reconciliation ownership；
- audit evidence 和可观察状态。

Restart/reconciliation 必须先读 evidence，不得盲目重做可能已产生 effect 的请求。

### Round 7：GC、retention 与 backup/restore

确认：

- generations、artifacts、journal、idempotency retention；
- Plan/Execute GC 分离；
- stale plan、checkpoint、interruption、concurrency；
- backup contents；
- restore validation；
- restored environment identity。

### Round 8：安全与资源治理

确认：

- authentication/authorization；
- repository access；
- secret；
- path concealment；
- SSRF/artifact URL；
- upload/download/decompression/input limits；
- malformed/oversized input；
- isolation；
- audit/redaction；
- stream/resource/DoS limits。

如果 Phase 2 不实现完整认证，仍须定义可信部署边界与未来接入点。

### Round 9：可观测性、measurement 与运维

确认：

- logs/traces/metrics；
- typed spans/counters；
- correlation IDs；
- environment fingerprint；
- readiness/liveness；
- graceful/non-graceful restart；
- persistent volume；
- image/Dolt/Python/uv/locks/source identity；
- runbook；
- production-client-only benchmark boundary。

不得声明 numeric 性能收益。

### Round 10：测试、gate 与 exit matrix

定义可执行验证：

- schema/wire contract；
- Fake/Local/Remote contract suite；
- Local/Remote fixture 等价；
- immutable pinned reads；
- stream/backpressure/cancel/deadline；
- idempotency、CAS、lease；
- journal crash/recovery；
- unknown outcome；
- readback mismatch；
- service/Dolt restart；
- stale state；
- GC、backup/restore；
- security negatives；
- container/persistent volume；
- exact identity；
- Phase 1 regressions。

设计唯一、fail-closed 的 gate classes。Required lanes 不允许 skip、xfail、
`UNSUPPORTED`、advisory-only 或 retry 掩盖。

### Round 11：实施计划

将设计拆为可审核、可回滚的 WP/R。每批包含：

- goal、scope、non-goals；
- prerequisites；
- contract/schema/API changes；
- files/modules；
- fixtures/tests；
- required gates；
- evidence；
- rollback；
- entry/exit；
- 禁止混入内容。

交付推荐顺序、依赖图、关键路径、有限并行边界和 exact-commit exit 流程。

---

## 9. Phase 2 固定边界

Phase 2 目标是独立、通用、容器化的 Repository Service，使业务系统不依赖
Dolt CLI 或 repository local path。

Repository wire 必须移除 Workspace、Submission、Preview、Archive、Baseline、
History 等业务语义。“业务主线晋升”必须表达为业务校验加通用
`CompareAndSetRef`。

Phase 2 不做：

- SnapshotSummary、Comparison、Risk 或业务 hidden-table 解释；
- candidate selection 或 archive gate；
- 完整 Submit/Review/Archive 流程；
- Phase 3 capability framework；
- Phase 4 workflow/operation runtime；
- Phase 5 业务纵切；
- 多节点共享 writer；
- 通用 DAG/plugin/provider framework；
- 无 consumer 的空抽象；
- Shared Kernel 算法复制；
- Phase 1 vectors/golden/scenario 修改；
- local path public contract；
- 大文件普通 JSON；
- nightly、first-party unsafe、SIMD、custom allocator；
- numeric 性能收益声明。

发现必须改变 accepted semantic contract 时，先报告、确认和 formalize，不得
顺手修改或实现。

---

## 10. Consolidated Design Review

Round 0～11 全部确认后，先输出完整但仍可修改的整体设计，至少检查：

1. Accepted decisions 是否互相兼容；
2. API、identity 和数据模型是否闭合；
3. read/write/recovery 是否使用一致 identity；
4. journal、lease、idempotency、CAS 是否存在竞态或空窗；
5. Local/Remote 是否 contract-equivalent；
6. public contract 是否泄露 path 或业务语义；
7. container/restart 是否满足 recovery contract；
8. tests/gates 是否证明所有 exit conditions；
9. 是否越界进入 Phase 3/4/5；
10. 是否存在重复 owner、formal 冲突或无 owner 规则；
11. Deferred 是否确属 non-blocking；
12. blocking register 是否允许开始实现。

然后等待用户选择：

- 整体确认并 formalize；
- 重开指定 Round；
- 暂停并保留 Draft。

---

## 11. Formalization

仅在用户明确回复“整体设计确认，可以 formalize”后：

1. 把本文件补全并标记 `Resolved`；
2. 创建
   `docs/backend-vnext/refactoring/formal/plans/phase-2-implementation-design-and-delivery-plan.md`；
3. 更新 `docs/backend-vnext/refactoring/formal/README.md`；
4. 必要时更新 `implementation-stages.md`；
5. 只有确有 owner 缺口时才修改 owning contract 或新增 ADR；
6. 不在 phase plan 中复制其他 owner 的完整规范；
7. 建立 requirement → decision → formal owner → WP → gate → evidence
   追踪矩阵；
8. 建立最终 blocking register；
9. 判断是否具备开始 WP0/WP1 的条件。

正式设计必须覆盖：

- component/dependency topology；
- public client/API/wire；
- data model 与 state machines；
- read consistency 与 data plane；
- journal/idempotency/lease/CAS；
- effect/recovery；
- Dolt/registry/staging/artifact ownership；
- GC/backup/restore；
- security/resource limits；
- deployment/observability/measurement；
- Local/Remote conformance；
- gates、WP/R 和 Phase 2 exit matrix。

---

## 12. 文档验证与最终报告

Formalize 后至少执行：

- `git diff --check`
- 相对链接和索引检查
- authority/owner 重复定义检查
- Decision Ledger 与 formal 文档一致性检查
- requirements traceability 检查
- Phase 2 exit conditions 可验证性检查
- blocking register 检查
- 确认未修改 Phase 1 identity、locks、vectors、golden、scenario
- 必要的轻量 architecture/document tests

最终报告：

1. 整体架构；
2. Accepted decisions；
3. Rejected alternatives；
4. Deferred/non-goals；
5. API、data model、state machines；
6. recovery、安全、部署；
7. WP/R、依赖、关键路径；
8. gates 和 exit matrix；
9. 文档变更；
10. 验证结果；
11. blocking register；
12. 是否具备开始 WP0/WP1 的条件。

完成文档不等于完成设计。只有各轮经用户确认、整体一致性复审通过并正式落盘后，
才能宣布 Phase 2 完整设计完成。

---

## 13. Resolution record

Phase 2完整设计已于2026-07-30完成以下停止点：

1. Round 0–11全部确认；
2. Consolidated Design Review确认；
3. bounded Phase 3 consumer-adequacy check确认PASS；
4. 用户明确授权formalize；
5. F0 formal closure、formal supersession、traceability和validation PASS。

正式实现authority：

- [Repository Service Contract](../../formal/contracts/repository-service.md)
- [Phase 2 Implementation Design and Delivery Plan](../../formal/plans/phase-2-implementation-design-and-delivery-plan.md)
- [Phase 2 Requirement Traceability](../../formal/plans/phase-2-requirement-traceability.yaml)
- [Phase 2 F0 Validation Report](../../formal/plans/phase-2-f0-validation-report.md)
- [ADR 0008](../../formal/adr/0008-generic-dual-store-and-caller-selected-rigor.md)

本目录继续作为decision history，不再拥有implementation authority。若后续consumer、
provider或platform evidence命中某项reopen condition，只重开对应formal owner和
Decision，不修改历史记录冒充原决定。
