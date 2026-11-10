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


### 正常 drain 的纯重算让出（DC88）

S2b D 对已注册 `PURE_RECOMPUTE` 且未跨外部 effect 的阶段，允许在尚未写出本次新 checkpoint 时协作让出。应用/registry owner 判能力；LeaseSession 在原 mutation lock 下重读 fresh records，以有效 lease/CAS 及真实 drain 为前置，按既有 `RUNNING → RETRY_WAIT` 清 worker/token/lease并立即可重领。保留旧 checkpoint（可为空）、prior outputs 与业务保护，不制造 checkpoint、发布未完成结果或更换冻结来源。

cancel 优先走原业务取消，lease_lost/expired/stale CAS 不得写入。独立 drain 诊断使下次 claim 保持既有 attempt_count，operator recovery session 身份也保留；正常停机不耗失败恢复次数，也不重置已经消耗的次数。真实失败/crash/失租仍沿原 R5。外部 effect 后不适用本让出，不复用 Repository healthy-wait 诊断或更改其截止预算。

这是现有 LeaseSession/R5 的有限协作扩展，不是新的 durable 状态或租约协议。定向验证租约/取消/事务屏障、checkpoint/保护、claim 计数与实际 worker drain/reclaim；180 秒排空上限和无自动强杀不变。决议与范围见 [DC88](../plans/p6-s0-owner-decisions.md#dc88-纯重算阶段的正常-drain-交接)。

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
- `RETRY_WAIT` 上的既有 diagnostic 标记控制下一次 claim 的恢复会话计数：
  `R5.HEALTHY_WAIT_HANDOFF` 表示已确认的健康等待让出，claim 保持 `attempt_count`；
  `R5.HEALTHY_WAIT_HANDOFF_OPERATOR` 表示 operator 授权会话中的健康等待让出，claim 同样保持
  `attempt_count` 并恢复 `R5.OPERATOR_RECOVERY_SESSION`；`R5.RECOVERY_AUTHORIZED` 表示 operator 命令
  已授权一个新恢复会话，claim 恰好增加一次 `attempt_count` 并转为
  `R5.OPERATOR_RECOVERY_SESSION`。这些标记复用现有 diagnostic 字段，不增加状态或 durable 字段。
- RUNNING Step 的 `diagnostic` 通常为 null；仅 operator 已授权并由 worker claim 的会话可使用
  `R5.OPERATOR_RECOVERY_SESSION`。该既有诊断标记保留到该会话终止、失败或健康让出，不改变 lease、
  status 或 optimistic-version 规则；其他 RUNNING Step diagnostic 仍拒绝。
- `SUCCEEDED | FAILED | CANCELLED | SUPERSEDED` 为 final terminal。
  `MANUAL_RECOVERY_REQUIRED` 为 attention state：不可自动 claim，不释放业务占用；仅
  authorized recovery 可将 Step 置为现有可领取的 `RETRY_WAIT` 并将 Operation 恢复为
  `RUNNING`，或产生允许的终局；实际 lease 仅由 worker claim 授予。
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

### History metadata checkpoint 与计算缓存（S5）

History `materialize_inputs` 保存完整 exact-commit 描述、descriptor、ordered provenance、
存储事实与冻结 ruleset/节点绑定，不要求预读整表或保留可重建 canonical 文件。side 载荷为
`history-compare/materialize-side/v5`，封装文档为 `materialized-sides/v2`；旧载荷拒绝，不双读。
assemble 恢复重新核当前 scope 下相同 exact-commit authority/catalog 与冻结描述，重新查
单表 diff 和独立 Parquet 导出，再按同一 Comparison planner 的真实 reader 需求合并读行。
失效缓存只能从该 exact commit 补行，不能读 main 或把 cache hit hint 当恢复事实。
当前记录闭包、风险、surface 与完整 bundle 仍经原三 step 发布；内部缓存没有进入 READY
闭包，所有 lease/consumer 关闭后、READY 前及异常 finally 释放本 operation 的 cache intent，
不覆盖原 workflow/source/checkpoint/result 保护。

### Submit finalize与可选计算缓存（S5）

原MatchingFinalizeFacts通过后，T3按Attempt.preview_result_id解析真实Preview producer，
核workspace/repository和已冻结configuration facts绑定，再在原Submission/Attempt/
occupancy/ReviewSeed事务中触达至多64个未过期且当前manifest匹配的cache uses及成员TTL。
不读文件、调用Repository或运行比较，不推进业务BaselineHead；Head CAS仍只归Archive。
T1已冻结Attempt，不把临时Preview存在性新增为T3强前提：缺行仅跳过不可定位的可选触达；
不猜producer、不回填。存在行解码失败、scope或冻结facts矛盾沿原绑定失败传播。

可选维护使用窄SAVEPOINT；只允许已知typed坏cache payload在SAVEPOINT回滚成功、外层事务
仍active后脱敏记录并继续。未知SQLite错误（含未精确证明为cache自身的约束失败）、
IOERR/CORRUPT/FULL/BUSY、CAS、scope错误或外层事务丢失不能吞掉。之后的权威写入失败
仍回滚全部T3及本次TTL。合法FINALIZED replay先核原业务闭合后早返回，不重复触达TTL；
response loss沿原事务/recovery处理，不增加journal、重试状态或跨服务原子事务。
T1即PREPARED但不代表已有包，prepare checkpoint前后的冻结恢复界限仍由
[Canonical Storage §5](canonical-storage-and-repository-boundary.md#5-artifact-lifecycle)拥有。

<a id="p7-s1a-目标补充资源和跨-root-closure待实现"></a>

## P7-S1a 生效补充：资源和跨 root closure（已生效）

状态：S1a 资源与跨 root closure 接线已实现，operation-runtime/v2 不变；证据与适用边界见 [S1a 总结](../plans/p7-s1a-summary.md)。[A 入口](../plans/p7-s1a-a-entry-and-contract.md)保留当时仅固定目标的历史事实，[S1a 执行方案 §3](../plans/p7-s1a-execution-plan.md#3-编码输入定稿)继续约束配置与资源接线。本步单环境/组、W=K=1，不修订多 worker startup/recovery 或队列状态机。

`storage-layout.json` 与 `resource-profile.json` 是位置与资源的各自唯一来源，公共 schema_version/environment_id/group_id 必须匹配。入口为 GATEWAY_STORAGE_LAYOUT_FILE / GATEWAY_RESOURCE_PROFILE_FILE，替代旧 root 与重复 N/M/E 环境入口，不保 alias。N为1–256；M为显式正整数bytes且≤40GiB；8GiB≤reserve<E≤48GiB且M≤E−reserve；W=K=1。JSON拒绝bool/小数冒充整数、NaN/Infinity、重复/未知key及不支持版本。N不得超过有效CPU quota整数部分或cpuset，容器实际memory.max=E且祖先限制足够；M是kernel预算，不能用RSS代替。整机同时计worker、backend、RS/Dolt与共享余量，不重复算page cache或Dolt。scratch/staging cap是必填正整数，资源变化只在排空/重启生效。

角色预检实际挂载来源/marker/权限/身份与cgroup后才允许ready/claim；不以渲染成功代替实际核验。HTTP新工作因基础存储不可用/低水位沿503 SERVICE_NOT_READY，接收后的I/O失败沿原operation恢复，effect UNKNOWN仍先核原结果。readiness与liveness不混用，不新增公共failure code。

checkpoint、请求快照、READY与canonical table-set closure在durable，成员保留自身类别。所有成员完成且受保护后，仍由既有lease/DB publication屏障发表完整closure；跨root不增加联合事务。scratch只有operation/step/attempt或HTTP接收上下文的临时owner，禁止唯一恢复事实存入scratch。新ID同步用于record refs、bare closure/checkpoint ID与严格decoder；不能仅改通用ArtifactRef而漏job/nominal载荷。prepare checkpoint及固定package/key恢复边界保持原§6与Canonical Storage §5。

D 实施接口（阶段组合验收仍归 G）：scratch capability 在 HTTP multipart 解析之前以 upload
owner 创建；其他发布请求使用 request owner，worker 每次实际执行使用真实 operation owner。
一个 owner 的所有同时存活 temporary 文件共用 `scratch_max_bytes_per_attempt`，每次增长前
检查累计 logical payload bytes 与 producer 原有单文件上限；关闭 writer 不释放额度，移除该文件
后才释放。预算不把 filesystem 元数据、分配块或 native 子进程容量冒称精确预留。
服务内部 writer 使用受控文件接口，禁止默认系统 temp、ambient TMPDIR 与传 pathname 绕过计数。
owner 目录持独占 flock，成功、失败、取消或 close/ENOSPC 失败均在释放 owner 前收尾；scratch
不保存恢复权威。接收取消继续等待正在读取上传的 acceptance 线程结束后再删除输入。


F 接线细节：标准 Compose override 从两文档生成 long-syntax bind（禁止自动创建 source）、
role memory/CPU/swap 和 replicas，基础 YAML 不提供可写存储默认值。host `check-host` 先核
实际 mountpoint/source 和宿主/祖先规划预算；显式 `init-layout` 只为已存在空 root 写固定
marker，已有 marker 必须精确匹配。服务只核本角色 roots；backend HTTP admission/readiness、
worker 写 UoW/claim 及 RS readiness/import claim 在实际观察成功后继续。挂载身份失效锁存，
重启预检前不接受替代 root。显式 host 调试记录无硬 envelope，不能在容器中绕过限制。
固定 slot/filesystem 与单对象 fd stat 仅为 S1b 的 bounded adapter 输入；不在本步写统计 DB。


F 的 deployment 准入进一步约束：仅 backend 显式启动可在已验证 metadata root 发布可重建的配置摘要记录；worker startup、claim 与写事务必须读取同组、同规范化摘要，缺损/变化拒绝且不自建 DB 或重写记录。通用 readiness/请求不更新记录，安全离线维护与低水位清理不依赖记录；它不增加 operation 状态、lease、epoch 或业务成功证据。运行期 root 身份失效锁存到重启；临时容量拒绝可在安全回收后恢复。
