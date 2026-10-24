# Operation Lifecycle and Repository Integrity Contract

状态：正式设计基线（Accepted）

阶段：Phase 3 capability/error boundary；Phase 4 runtime；Phase 5 deployment integration

Contract ID：`gateway-vnext.operation-lifecycle-and-integrity`

Owner：Operation Runtime and Repository Integrity

## 1. Graceful lifecycle

安全关停和安全重启共用同一合同：

```text
SERVING -> DRAINING -> QUIESCED -> CHECKPOINTED -> STOPPING -> EXITED
```

restart 是 graceful shutdown 后的正常 startup recovery、health check 和 re-entry。
首版 deployment/runtime graceful drain timeout 为 `180s`，不属于 capability contract。
超时进入 `DRAINING_TIMEOUT`，不自动强杀；强制终止必须由授权管理员明确执行并记录原因。

进入 `DRAINING` 后 readiness=false，拒绝新的 Preview、Submit、history compare 和会
创建 artifact/cache/external ChangeSet 的请求；允许 liveness、metrics、admin readback
和已有 operation 状态查询。已有 operation 继续执行或 checkpoint 后由 durable runtime
接管。

## 2. Quiescence and recovery

`QUIESCED` 必须同时确认 active Preview、Submit/finalize、Repository effect、external
sync 和不可恢复 pending promotion/readback 均为零。startup 在 readiness=true 前执行：

```text
load durable state
  -> reconcile operations/artifacts/unknown outcomes
  -> validate active ruleset
  -> restore workers
  -> health check
  -> readiness=true
```

external target 局部恢复失败时，repository/read-only 可以 degraded-ready，但相关 target
同步必须被拒绝并标记 `FULL_RESYNC_REQUIRED`。

## 3. Re-upload boundary

重新上传只恢复 provisional 或尚未产生 authoritative repository effect 的流程：

- Preview artifact、provisional cache、未提交 plan 损坏：丢弃并新建 upload/attempt；
- Submit effect 前 source fallback 不可用：要求新 upload；
- Dolt commit 已完成：禁止用新 upload 替代、覆盖或回滚原 commit；
- external target 失败：针对原 canonical commit full resync；
- repository content/readback mismatch：先处理 integrity incident。

每次重新上传都创建新的 attempt id，并通过 `recovery_of` 与旧 attempt、failure code、
base commit 和 ruleset snapshot 建立关联。

## 4. Integrity incident

权威事实问题必须创建 durable `RepositoryIntegrityIncident`（或等价 control record），
至少保存：

```text
incident_id
repository_id / operation_id / commit/ref
failure_class
expected_digest / observed_digest
affected_tables
recommended_action
first_seen_at / last_seen_at
acknowledgement_status
resolution_reference
```

权威事实问题指：Repository 返回值与 Backend 持有的期望值相矛盾（例如 T3 回显的 manifest digest、expected
parent 或 commit），或 CAS/结果歧义。以下情形不创建 incident，按普通稳定失败处理，附诊断、结构化日志与
指标：未与 Backend 期望值比较的 Repository 读取不一致（如 catalog 行数与读取行数不一致）；Backend artifact
store 的读回校验失败（如 manifest artifact 的 digest 与 Submission 记录不符）（2026-09-27，
[ADR 0019](../adr/0019-commit-canonical-metadata-authority.md)；5E 的 History compare integrity incident 在
P5 架构收口 S2b 删除前仍按原实现运行）。

incident 通过 stable operation/user code、结构化持久日志、metrics/alert 和 admin readback
暴露。integrity incident 不进入普通 artifact cleanup，至少保留到显式 acknowledge、
resolution 记录和 operator archive。只保存身份、digest、状态和诊断引用，不保存大量
业务 row payload 或 secret。

Repository health 至少区分：

```text
HEALTHY | DEGRADED | REUPLOAD_REQUIRED | FULL_RESYNC_REQUIRED | BLOCKED
```

## 5. Phase ownership

Phase 3 只定义 cancellation/checkpoint/error boundary；durable operation、drain、takeover、
signal handling 和 container wiring 属于 Phase 4/5。不得为了该 contract 新增 broker、
sidecar 或独立 evidence 服务。

P4-R3 拥有 operation-worker 进程内的 signal installation、worker-local lifecycle、
`READY_TO_CLAIM` 和 drain/checkpoint handoff 机制。这些进程内事实不等于本
Contract 的全局 `SERVING` / `DRAINING` / `QUIESCED`。P5 拥有 deployment/container
signal 接线、backend HTTP readiness/admission，以及对 Preview、Submit/finalize、
Repository effect 和 external sync 的全局 quiescence 汇总。该 owner 拆分不改变
`180s` timeout、`DRAINING_TIMEOUT` 或管理员显式强制终止语义。

## 6. Phase 4 operation runtime contract snapshot

自 P4-R1-S1b 起，durable Operation/Step persisted semantics 由
`gateway_backend.operations` 实现，并由本 section 与
[P4-R1 Runtime Contract and State Detailed Execution Plan](../plans/p4-r1-runtime-contract-state-execution-plan.md)
的 step/handoff 编排共同约束。实现不得与本文冲突；冲突必须 reopen owning contract。

### 6.1 Package and publication

- 唯一物理 package：`gateway_backend.operations`；registry identity 使用
  `(job_kind, step_name)`；禁止 `operation_kind` 字段、alias 或兼容 shim。
- Public surface 分阶段发布：S1a 导出 contract version、status enums、`JobStepKey`；
  S1b 增加 `BusinessReference`、`OperationRecord`、`StepRecord`、`OperationDiagnostic` 与
  `operation_record_from_document` / `step_record_from_document`；S2b 增加
  `WritePrecondition`、`TransitionDisposition` 与 transition/write guards。
- Runtime contract version：`backend-vnext/operation-runtime/v2`；与 job payload contract
  version 分开版本化。Operations 不重新导出 `ArtifactRef`。

### 6.2 Closed persisted documents

Operation 与 Step persisted document 均为 closed object；`to_document()` 发出全部 keys
（不适用值为 `null`）；parser 要求 exact key set 并拒绝 unknown field/version/type。
`diagnostic` 内未提供的可选明细字段会省略，不写成空数组或 `null`。

- `document_type` 分别为 `operation` / `step`，作为 serializer/parser discriminator，不作为
  record field。
- `business_refs` item 为 `{"kind","value"}`；没有结构化明细时 `diagnostic` 为
  `{"code","message"}`。包含明细时还带 `details` 与 `omitted_count`；每项为
  `{"code","side","table_name","column_name"}`，`side` 为 `INITIAL` 或 `MODIFIED`，
  `column_name` 可为 `null`。投影级诊断没有对应表时 `table_name` 可为 `null`。
  artifact/checkpoint/ref item 复用 artifact owner 的 `ArtifactRef` document shape。
- Diagnostic 明细最多 100 项，按 `(side, table_name, column_name, code)` 稳定排序；空字段先于
  有值字段。`omitted_count` 记录未列出的总项数，仅当已列明细达到 100 项时可大于零；未省略时
  为 `0`。无明细时不输出 `details` 或 `omitted_count`。
- `job_payload` 与 `job_payload_ref` 恰有一个非 null；inline payload root 必须是 JSON object，
  空 payload 使用 `{}`；record 内 inline payload 保存 canonical JCS `bytes`。
- Timestamp 仅接受 canonical UTC `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`；tuple 输出保持 semantic
  order；要求 identity 唯一的 artifact refs 拒绝重复。

### 6.3 Status semantics

- Operation：`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `SUPERSEDED`,
  `MANUAL_RECOVERY_REQUIRED`。
- Step：`PENDING`, `RUNNING`, `RETRY_WAIT`, `SUCCEEDED`, `FAILED`, `CANCELLED`,
  `MANUAL_RECOVERY_REQUIRED`。
- `SUCCEEDED | FAILED | CANCELLED | SUPERSEDED` 为 final terminal。
  `MANUAL_RECOVERY_REQUIRED` 为 attention state：不可自动 claim，不释放业务占用；仅
  authorized recovery 可产生允许的 `RUNNING` 或终局。
- 结构状态矩阵、lease identity、diagnostic/completion/timestamp 交叉字段规则与 stale-write
  precondition 由 `gateway_backend.operations` 在 R1-S2a/S2b 证明；R2 负责数据库原子 CAS，
  不得把先读后验当作持久化实现。
- `validate_operation_transition` / `validate_step_transition` 同时是候选 record mutation
  的关系校验 owner：非终态、非 attention state 的 same-status heartbeat、checkpoint 和
  cancel-intent mutation 也必须通过现有 guard，并返回 `APPLY`。这里的 `APPLY` 表示
  mutation validation 通过，不增加 status matrix edge，也不把 mutation 解释为 status
  self-loop。
- R2 在 CAS 前必须组合执行相应 transition guard 与
  `validate_write_precondition`；final terminal same-status 只有完整 record 相等时返回
  `IDEMPOTENT`，`MANUAL_RECOVERY_REQUIRED` 禁止原地 same-status mutation。

### 6.4 Bounded validation

保守默认预算包括：opaque ID 1..255 UTF-8 bytes；`job_kind` / `step_name` 1..128 ASCII
`[A-Za-z0-9._:/-]`；
inline payload 最大 64 KiB；JSON depth 32、aggregate 4096、key 128 UTF-8 bytes、string 16 KiB；
business/artifact refs 每 tuple 最多 64、单 record 内 ArtifactRef 合计最多 64；optimistic
version / attempt count 与 diagnostic `omitted_count` 为非负 I-JSON safe integer。Diagnostic
code 为 1..128 个匹配诊断码 pattern 的 ASCII 字符；明细最多 100 项；`table_name` / `column_name` 为 `null` 或
1..255 UTF-8 bytes。Runtime 只验证 JSON/I-JSON shape 与资源预算，不解释 job payload 业务字段。

2026-09-13 P4-R6-S0 bounded amendment：`/` 是已确认 P5 `backend-vnext/preview`
consumer 需要的 opaque namespace 字符。它不表示文件系统路径、URL 或层级，runtime 不得将
registry name 拼接为 host path。该扩展不拒绝任何原先合法值，不改 persisted key、
schema、status/CAS 语义或当时的 `backend-vnext/operation-runtime/v1` version。`BusinessReference.kind`
复用同一 pattern。精确 disposition 与回归要求见
[P4-R6/R1 Registry-Name Contract Reopen](../plans/p4-r6-r1-registry-name-contract-reopen.md)。

P5 EXIT-F1 增加了 persisted diagnostic 明细字段，Operation/Step closed document 的运行时
Contract 从 `backend-vnext/operation-runtime/v1` 提升为 `backend-vnext/operation-runtime/v2`；
不读取旧版本记录，也不改 control DB schema。
