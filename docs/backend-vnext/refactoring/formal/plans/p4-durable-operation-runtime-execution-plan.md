# P4 Durable Operation Runtime Execution Plan

状态：**Initial staged execution plan; implementation not yet authorized**

日期：2026-08-23

Owner：Backend vNext Operation Runtime

设计基线：[P4 Durable Operation Runtime Design Baseline](p4-durable-operation-runtime-design.md)

默认入口：[P4 Active Context Index](p4-active-context-index.md)

## 1. Planning rule

P4 沿用 P3 的 staged execution、focused review、风险驱动 independent review、module gate
和 handoff 方式，但不复用 P3 的 capability module boundary。每个 R 只在上一个 handoff
稳定后，依据实际 contract、风险和上下文规模细化其 S steps；不提前创建空抽象或未使用的 provider。

标准 S-step：

| Step | 目的 | 结果 |
|---|---|---|
| S0 | entry、scope freeze、owner/reopen review | accepted step brief |
| S1 | contract、schema、port 或最小 walking skeleton | importable boundary |
| S2 | 单一主责实现 | focused code + unit tests |
| S3 | conformance、failure、round-trip、fault tests | validation evidence |
| S4 | focused review | findings register |
| S5 | remediation、regression、retest | closed findings or reopen |
| S6 | risk-based independent review | independent review result |
| S7 | module gate、docs、handoff | tested tip + exit record |

这张表是**可裁剪模板，不是固定工序**：

- `S0` 和模块 gate/handoff 是每个 R 的最小要求；
- `S1-S3` 按是否引入 contract、代码和独立验证需求适用；纯文档/边界收敛可以合并；
- `S4` 需要 focused review；没有 finding 时不强制产生独立 remediation step；
- `S5` 仅在存在 finding 或需要 regression 修复时启用；
- `S6` 按风险触发，不是每个 R 的默认必需步骤；
- 一个步骤如果跨越多个 owner、独立 contract 或无法在有限上下文中解释，必须拆成
  `S2a/S2b`、`S3a/S3b` 等实际步骤；低风险步骤可以合并，但必须在 handoff 中记录适用性裁定。

每个 R 的 S-step 数量、名称和顺序由该 R 的 S0 entry brief 冻结。模块 handoff 必须记录
`applicable_steps`、合并/拆分理由、未执行步骤及其风险依据；不能只写“按 S0-S7 完成”。

任何 P1/P2 finding、contract ambiguity、跨 owner 事务漏洞、stale worker 写入漏洞、未知
外部 effect replay 路径或资源上限绕过，必须在下一模块前关闭或 reopen owning contract。

## 2. Module roadmap

| Module | Scope | Dependencies | Handoff |
|---|---|---|---|
| P4-R1 Runtime Contract & State | Operation/Step status、envelope、version、error、cancel/supersede | P4 design + existing contracts | accepted state/DTO/error matrix |
| P4-R2 Durable Store & Atomic Transition | SQLite/WAL schema、migration、transactions、CAS、claim/lease | R1 | store port + transaction evidence |
| P4-R3 Worker & Lifecycle | worker entrypoint、bounded scheduler、heartbeat、drain、startup recovery | R1/R2 | runnable worker + lifecycle handoff |
| P4-R4 JobDefinition & Checkpoint | registry、versioned payload、artifact/checkpoint refs、READY closure | R1/R2/R3 | two registered synthetic jobs |
| P4-R5 Retry, Takeover & Effect Recovery | retry/backoff、takeover、unknown outcome、Repository stub reconcile | R2/R3/R4 | recovery state machine + fault evidence |
| P4-R6 Acceptance & Integration Gate | crash/duplicate/cancel/container gate、docs/provenance、independent acceptance | R1–R5 | P4 exit handoff and implementation authorization decision |

R1–R5 默认串行。R 内只有不共享未稳定 contract、不会改变 owner 语义的实际 steps 允许并行。

## 3. R1 — Runtime Contract & State

目标：冻结 Operations owner 的最小通用语义，不解释业务 payload。物理落点为
`vnext/backend/src/gateway_backend/operations/`；逻辑架构名称仍为 `backend_vnext`。

逐 step 的权威 context package、命令、review 和 handoff 见
[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)。

- S0：核对 Operation Lifecycle、External Effect、Contract Taxonomy 和 P4 design 的 owner seam；
  盘点当前 `gateway_backend` 落点，并冻结不迁移旧顶层 package 的裁定。
- S1a：创建 `gateway_backend/operations/__init__.py` 与 `contracts.py` 的 public skeleton，
  冻结 `OPERATION_RUNTIME_CONTRACT_VERSION = "backend-vnext/operation-runtime/v1"`、
  `(job_kind, step_name)` registry key 和受控 exports。
- S1b：定义 closed envelope document、status enum 的 document encoding、diagnostic code、
  `to_document/from_document` 规则；采用 JCS canonical JSON，不允许任意 context dict。
- S2a：实现 frozen Operation/Step record、opaque IDs、version 和 Step lease fields、payload/ref
  validation；不接 SQLite、worker、Repository 或业务 entity。
- S2b：实现纯逻辑 state transition guard、terminal idempotency、cancel/supersede guard、
  stale-write precondition guard；CAS 的数据库实现留给 R2。
- S3a：完成并强化 `tests/test_operation_contracts.py`，覆盖 canonical round-trip、unknown field/
  version、malformed shape、payload size/type 和 public export boundary。
- S3b：完成并强化 `tests/test_operation_state.py`，覆盖合法/非法转移、terminal duplicate、
  cancel safety boundary、unknown outcome、`MANUAL_RECOVERY_REQUIRED` 和 stale-write guard。
- S4：审查业务语义泄漏、generic evidence 扩张、未版本化 context dict、`operation_kind`
  别名回流和 Repository authority 越界。
- S5：仅在 S4 finding 或 regression 需要时启用；修复后只重跑受影响 focused tests。
- S6：若 S4 无法独立证明恢复/跨 owner 屏障，则触发 independent contract review；否则记录
  `not_required` 及理由。
- S7：handoff state/DTO/error matrix、tested tip、applicable steps、deferred/reopen register；
  后续模块不得自行扩展状态或重新引入 `operation_kind`。

禁止：Workspace/Submission/Archive 字段进入通用 record；以 Operation terminal status 表达业务 finalize；
禁止在 `gateway_backend` 外再创建 `backend_vnext` 的并行 R1 实现。

## 4. R2 — Durable Store & Atomic Transition

目标：在同一 SQLite/WAL control DB 中提供 operation/step/outbox 所需的最小持久化能力。

- S0：冻结表 owner、migration、事务边界和并发/锁预算。
- S1：定义 schema、indexes、optimistic version、claim/lease CAS 和 transaction port。
- S2：实现创建、claim、heartbeat、checkpoint、terminal publish、cancel request 和 readback。
- S3：覆盖重复 claim、stale worker、rollback、crash 前后事务可见性和 migration round-trip。
- S4–S6：审查跨表原子性、迟到写入、锁等待、诊断大小和 cleanup 边界。
- S7：handoff store port、migration evidence、事务不变量和已知容量限制。

禁止：跨库 two-phase commit；Repository marker/ref/CAS 写入；把业务 entity 直接作为 persistence record。

## 5. R3 — Worker & Lifecycle

目标：提供独立 worker entrypoint、顺序 step 执行和 graceful lifecycle。

- S0：冻结启动参数、worker identity、bounded concurrency 和 signal/readiness 责任。
- S1：定义 scheduler/handler port、claim loop、heartbeat loop、drain barrier 和 startup recovery hook。
- S2：实现单 worker、`max_in_flight=1`、顺序 step 和 checkpoint-aware shutdown。
- S3：覆盖 drain、quiescence、restart recovery、lease expiry、heartbeat loss 和 worker crash。
- S4–S6：审查 busy loop、无界线程、强杀丢 checkpoint、readiness 过早开放和信号竞态。
- S7：handoff runnable entrypoint、生命周期证据和容器改动清单。

首版不启用内部 fan-out；不得把 capability 内部表级并行自动转成 operation step。

## 6. R4 — JobDefinition & Checkpoint

目标：让任何 worker 仅凭 durable record、prior outputs 和 artifact refs 恢复执行。

- S0：冻结 JobDefinition owner/application registration 与 payload versioning 规则。
- S1：定义 registry lookup、handler signature、checkpoint/artifact ref 和 READY closure port。
- S2：实现两个 synthetic jobs：幂等纯 compute、external-effect stub。
- S3：覆盖 payload reload、artifact missing/corrupt、checkpoint round-trip、duplicate delivery 和 READY gating。
- S4–S6：审查 closure 捕获、超大 inline payload、artifact cleanup 越权和 job-specific policy 泄漏。
- S7：handoff registry、synthetic job contract、fixtures 和 reload evidence。

禁止：动态闭包作为恢复入口；把 renderer replay bytes 当作已执行 Repository effect。

## 7. R5 — Retry, Takeover & Effect Recovery

目标：实现有限重试、接管和 evidence-first 外部 effect 编排，不接管 Repository authority。

- S0：冻结 retryable failure owner、backoff/attempt policy、takeover matrix 和 stub boundary。
- S1：定义 retry decision、reconcile port、unknown outcome 和 `MANUAL_RECOVERY_REQUIRED` guard。
- S2：实现纯 compute retry、lease takeover、原 operation identity poll/reconcile 和 cancel boundary。
- S3：覆盖 request-sent crash、effect-confirmed crash、poll timeout、duplicate delivery、普通失败和人工恢复。
- S4–S6：审查新 key 生成、blind replay、occupancy 提前释放、错误终态伪造和 Repository contract 越界。
- S7：handoff recovery matrix、fault evidence、stub contract 和未决参数清单。

禁止：业务 T3 finalize；自行判断 Repository commit/ref 是否存在；创建 generic external-effect journal。

## 8. R6 — Acceptance & Integration Gate

目标：汇总当前 HEAD 的 P4 runtime 证据并决定实现授权/阶段退出。

- S0：entry acceptance checklist、测试分类、container applicability 和 provenance freeze。
- S1：组装 synthetic worker harness、crash harness、Repository stub 和 admin readback。
- S2：运行 focused/unit/serial/integration 测试及 ruff/mypy；按风险补齐 regression fixtures。
- S3：执行 process crash、lease takeover、duplicate delivery、cancel、drain/restart 和 checkpoint corruption matrix。
- S4：独立审查 contract owner、事务/CAS、恢复边界、测试 owner 和 deferred register。
- S5：修复并复测；任何 P1/P2 或 contract ambiguity 必须关闭或 reopen。
- S6：按 worker entrypoint/lifecycle 改动重建当前 HEAD image，执行 container gate。
- S7：签发 P4 handoff，记录 tested tip、image revision、命令结果、限制和下一阶段 prerequisites。

## 9. 测试与验证策略

- 纯状态、payload、校验和 transition 测试不得创建 Dolt。
- 固定时间预算的 drain、heartbeat、lease 和 crash/recovery 测试标记 `serial`，必要时 `-n 0`。
- 真实 Repository/Dolt 交互属于独立 integration；stub 不能被表述为 production validation。
- 五个 Python 包执行各自 `ruff check .` 与 `mypy`；repository_service 继续遵守既有 unit/integration/serial 入口。
- P4 final candidate 若触碰 worker entrypoint、Compose、health/readiness 或 container runtime，必须重建当前 HEAD 镜像。

## 10. Exit criteria

P4 只有同时满足以下条件才可关闭：

- Operation/Step contract、schema/migration 和 JobDefinition registry 有唯一 owner；
- claim/lease/heartbeat/takeover 的 CAS 不变量通过测试；
- 纯 compute 与 external-effect stub 在 crash、duplicate、cancel、drain/restart 下通过；
- unknown outcome 无 blind replay，Repository operation identity 不漂移；
- worker 可从最小 checkpoint 恢复，READY artifact 可读且闭合；
- runtime 不依赖业务模型或 capability 私有实现；
- focused、unit、serial、integration、ruff、mypy 和适用的 container gate 通过；
- handoff 记录 tested tip、image provenance、deferred/reopen register 和 P5 entry prerequisites。

## 11. Deferred register

| Item | Owner / timing |
|---|---|
| lease/retry/poll 数值 | R2/R5 详细设计，按测试预算冻结 |
| terminal operation retention/GC | P5/Operations，基于真实容量 |
| 真实 Repository/Dolt Submit/Finalize | P5B |
| production external target / multi-target schema | future external-sync owner |
| 多实例 HA / 外部 durable DB | 出现真实部署 consumer 后 reopen |
| global fan-out、cache、并发优化 | P7 |
| formal end-to-end performance baseline | 首个 P5 production journey 后 |

当前状态：设计基线已接受；本计划仍不授予 P4 implementation，必须先完成 R6 entry acceptance。
