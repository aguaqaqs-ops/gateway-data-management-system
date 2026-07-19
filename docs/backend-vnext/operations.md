# Operations

formal upload 在 snapshot materialization 后先执行逐 pair project identity assessment。`DIFFERENT_PROJECT` 选择 `DATASET_REPLACEMENT`，不调度 detailed comparison/cache completion；埋点和确认语义见 `capabilities/project-identity-and-dataset-replacement.md`。

本文描述 backend vNext 的执行编排、异步边界、step 状态和诊断。业务流程见 `flows.md`，能力 contract 见 `capabilities/`。

## Operation 原则

1. Operation 表达执行进度，不表达业务事实。
2. Flow 创建 operation，operation 调用 capability。
3. 重负载 repository write 不进入直接反馈路径。
4. Cache warmup、comparison core cache completion、shadow benchmark 和 cleanup 都是异步优化，不是业务成功条件；其中 upload preview 产生的 comparison core cache 只属于 provisional candidate，只有 submit finalize 成功验证后才会被 promotion / rekey 为 canonical cache。
5. Cleanup 只回收临时资源，不删除已提交 repository refs、repository_path 或 READY 所需 artifact closure。
6. Operation READY 前必须闭合对外可读 artifact closure。
7. Benchmark 默认以 flow 级端到端旅程为主，必要时再下钻到 operation / capability 级别定位问题；repo-backed history compare 作为独立 benchmark track 观察 compare / native / cache 行为，不再引入 benchmark-facing 的兼容开关。
8. 如果需要模拟真实业务链路，benchmark 可以把 `upload -> submit -> approve -> archive -> history compare` 组织成 ladder 形式，但每个节点仍然是正式 flow / operation，不在 runtime 里新增特殊 benchmark 语义。

## 并行与异步

当前 flow / operation 设计可以支持部分环节的多 worker 异步执行，但前提是执行运行时显式实现 step 认领、幂等和依赖控制，而不是靠状态机自动推导。

第一版实现建议仍以串行为默认路径，把并行作为可选 policy / feature flag，而不是先做一套通用 DAG 调度器；只有在 benchmark 证明收益后，再把默认策略逐步放开。

建议边界：

- 不同 operation 之间可以并行，只要它们不共享同一组业务事实写入边界。
- 同一 operation 内只有在 step 之间无数据依赖、且 step 认领是原子的情况下，才允许由不同 worker 并行处理。
- 只读类步骤可以按表、按 pair 或按独立 artifact 并行拆分。
- 写入类步骤必须受 writer lease、generation gate 或等价互斥保护，不能和同一目标上的其他写入并发。
- worker 崩溃后，其他 worker 可以接管未完成 step，但不能重放已经确认提交的写入。
- retry / cancel / supersede 都应由 runtime 统一裁决，worker 只负责执行和上报 step 结果。

如果第一版并行只考虑“双份业务数据上传”或“两个 pair 比较”这类固定双任务场景，可以进一步收敛成固定双槽 fan-out / fan-in：

- 单份业务数据保持完全串行，不引入并行调度。
- 双份业务数据时只分裂成两个子任务，分别由两个 worker 处理。
- 两个 pair 比较时只分裂成两个子任务，分别由两个 worker 处理。
- runtime 不需要通用 DAG，只需要 parent + two child slots。
- 任一子任务失败时，parent 统一决定整体失败、重试或回退串行。
- 子任务之间没有依赖时，才能使用固定双槽并行；一旦出现共享写入边界或交叉依赖，立即退回串行。

## 最小 Runtime 草案

如果先追求最小可落地版本，建议把 runtime 收敛为“单 operation 认领 + 顺序 step 执行 + 失效后接管”，先不做通用 DAG 调度。

### 1. 认领模型

- 同一时刻一个 operation 只允许一个 worker 持有有效 lease。
- worker 通过原子 claim 把 operation 从 `QUEUED` 推进到 `RUNNING`。
- claim 记录最少包含 `worker_id`、`claim_token`、`lease_expires_at` 和 `claimed_at`。
- lease 过期后，其他 worker 可以接管，但必须重新读取 operation / step 状态。

### 2. Step 模型

- 每个 operation 预先定义固定顺序的 step 列表。
- step 只需要 `PENDING`、`RUNNING`、`SUCCEEDED`、`FAILED_RETRYABLE`、`FAILED_FINAL`、`CANCELLED` 这几类状态。
- runtime 只负责把“下一个可执行 step”从 `PENDING` 认领为 `RUNNING`。
- step 完成后再推进下一个 step，不要求 runtime 维护完整 DAG。
- 如果某个 capability 内部要做表级并行，可以先放在 capability / provider 内部，不放进 runtime 第一版。

### 3. 提交模型

- worker 结束一个 step 时，必须把 step 结果、诊断和必要的 artifact closure 一起写回。
- 只有当所有必须 step 都成功，且 READY 所需 artifact closure 完整时，operation 才能对外 `READY`。
- `READY` 之后允许后台 cleanup、cache register 或统计上报继续跑，但不再改变对外可读结果。

### 4. 接管模型

- worker 崩溃或 lease 失效后，新的 worker 只接管未完成的 `PENDING` / `RUNNING` step。
- 已成功提交的 step 不重放，除非显式 retry 且该 step 被标记为 `retryable`。
- `RUNNING` step 是否可重跑，取决于该 step 是否具备幂等 checkpoint；第一版可以先保守处理为“超时后重做整个 step”。

### 5. 并行策略

- 第一版只保证 operation 之间可以并行。
- 同一 operation 内的并行先不纳入 runtime 协议，避免过早引入通用调度器。
- 如果后续 benchmark 证明某些步骤值得并行，再把这些步骤提升为可选 fan-out policy。

### 6. 最小字段

```text
operation:
  operation_id
  operation_kind
  caller_type
  status
  generation optional
  retry_of optional
  superseded_by optional
  worker_id optional
  claim_token optional
  lease_expires_at optional
  failure_summary optional
  ready_closure_digest optional

step:
  operation_id
  step_name
  step_sequence
  status
  worker_id optional
  claim_token optional
  lease_expires_at optional
  started_at optional
  finished_at optional
  diagnostics optional
```

这个草案的目标不是一次性覆盖所有并发形态，而是先把“能异步、能接管、能诊断、能 READY”做扎实；并行只保留后续扩展口。

## Operation 类型

| Operation | 调用者类型 | 说明 |
| --- | --- | --- |
| `UploadPreviewOperation` | `DIRECT_RESPONSE_CALLER` | 快速构建 preview/surface，并在响应后异步补齐 comparison core cache。 |
| `PrecommitWarmupOperation` | `WARMUP_CALLER` | upload 后异步 warmup cache 或 shadow import benchmark。 |
| `SubmissionReviewOperation` | `FINALIZE_WRITE_CALLER` | submit 后的 review/approve/reject/withdraw 薄流转。 |
| `SubmitFinalizeOperation` | `FINALIZE_WRITE_CALLER` | submit acceptance 后异步导入 repository 并固化业务事实。 |
| `HistoryCompareOperation` | `READ_ONLY_CALLER` | 只读历史比较，生成 surface/bundle。 |
| `ArchivePromoteOperation` | `FINALIZE_WRITE_CALLER` | 归档或推进 mainline 的正式写操作，包含批次级预检、异常确认、候选选择与最终 promote。 |

## Upload Preview Operation

目标：

- 快速构建 preview / surface。
- 响应后异步补齐 comparison core cache candidate。

典型步骤：

```text
load input
compute analytics
assemble surface
publish result
async comparison core cache completion
cleanup
```

规则：

- compare / risk / surface 属于同步主路径，不等待 cache completion。
- preview ready 必须在 cache completion 之前可发布。
- comparison core cache completion 失败不应破坏前面的 preview 结果。
- upload preview 写入的 comparison core cache 视为 `PROVISIONAL` candidate。
- 该 `PROVISIONAL` candidate 不对 history compare 直接开放，只能在 submit finalize 的验证通过后 promotion / rekey 为 canonical 身份。

## Precommit Warmup Operation

目标：

- 生成后续 finalize 可复用的候选 cache。
- 可执行 repository import provider shadow benchmark。
- benchmark 建议先记录正式路径 baseline，再在相同 flow 旅程上观察额外的 cache / async / materialization 开销；两轮都应尽量复用同一条 flow 旅程。

典型步骤：

```text
load preview source/binding
snapshot_materialization
write source/table/projection cache as PROVISIONAL
optional repository import shadow benchmark
write diagnostics
cleanup expired provisional artifacts
```

规则：

- 不改变 Workspace preview ready 状态。
- 不创建 immutable repository ref。
- 不创建 Submission。
- 失败通常不影响用户主流程，可记录为 diagnostics。

## Submit Finalize Operation

目标：

- 从 durable submit input 固化 repository commit/ref。
- 推进 submission/review 前置业务事实。

典型步骤：

```text
load SubmitSourcePackage
load accepted SubmitOperation / submission_id
validate PreviewInputBinding
snapshot_materialization
lookup provisional cache candidates
repository_import with writer lease
readback validation
write / validate hidden summary table
promote cache candidates to COMMIT_VALIDATED
create immutable ref / Submission L2 state
write audit and diagnostics
```

失败策略：

- binding/digest mismatch：`FAILED_FINAL`。
- repository validation mismatch：`FAILED_FINAL`。
- temporary Dolt IO/server failure：`FAILED_RETRYABLE`。
- cache warmup/promotion failure：不应导致 repository commit rollback；记录 diagnostics 并允许后续重建 cache。
- 这里的 cache warmup/promotion 包括 comparison core cache 的 provisional candidate rekey / promotion；只有 repository import 与 readback validation 成功后，这类 cache 才能进入 canonical 身份。
- hidden summary table 是 submit finalize 的正式产物之一；它和 immutable ref 一样属于 finalize 成功后应保留的事实，不是可被 cleanup 自动删掉的临时态。
- `submission_id` 必须复用 submit acceptance 阶段已经分配的稳定业务 ID，不在 finalize 阶段重新生成。
- finalize worker 只 resume acceptance 已创建好的 `OperationKind.SUBMIT_FINALIZE` operation，不在 finalize 阶段重新创建 operation。
- finalize 阶段的 cleanup 只负责释放临时资源；当前实现会保留 `repository_path` 和 `run_dir` 供诊断、open-ref 和后续复盘使用，不能把它们理解为自动清空的临时目录。

## History Compare Operation

目标：

- 对 immutable repository refs 生成只读 comparison result。

典型步骤：

```text
resolve comparable refs
load hidden SnapshotSummary / canonical cache metadata
selective baseline row materialization
current ref materialization
comparison / risk / surface
bundle assembly
publish download metadata
async comparison core cache completion
cleanup
```

规则：

- 不执行 repository import。
- 不读取 `PROVISIONAL` cache。
- 只读取 `COMMIT_VALIDATED` / repository readback 产生的 cache，以及 submit finalize 已 promotion / rekey 到 canonical 身份的 comparison core cache。
- hidden summary table 缺失、损坏或版本不匹配应视为完整性错误，不应回退到重新生成 summary。
- comparison core cache completion 是可选后置阶段，失败不应破坏前面的 compare 结果。
- READY 前 operation artifact closure 必须完整。

## Archive Promote Operation

目标：

- 在批次级前置校验、异常确认和候选选择完成后，将选定的 immutable candidate 晋升为 mainline。
- 该 operation 由 `backend_vnext/flows/archive.py` 作为正式 flow adapter 驱动。

典型步骤：

```text
load batch / confirmations / anomaly resolutions / candidates
load summaries as needed
batch graph and integrity precheck
selection validation
dry-run promote check
mainline promotion
status propagation
open ref closeout
write audit and diagnostics
cleanup
```

规则：

- 这是 batch-scoped write operation，不能把单个 submission 的 review 状态当成归档完成。
- 执行前必须校验 batch 仍处于可归档状态，且不存在进行中的归档或冻结状态。
- 所有 active workspace 必须已经确认；缺失确认时不得继续推进。
- selected mainline candidate 必须存在、必须唯一，且若来源不是 `APPROVED_SUBMISSION`，则必须带有显式 override reason 和保护性 immutable ref。
- 所有被选中的 `BASELINE_INITIAL_HISTORY` 候选都必须存在对应 anomaly resolution，且该 resolution 必须覆盖目标 submission。
- `Open Ref` 作为 archive execute 的最后收尾步骤执行，只用于最终只读回读闭合；归档资格不能只靠 open ref 或 cache 命中判断，必须以 batch graph、summary、confirmation 和 anomaly resolution 一起决定。
- execute 必须在写入前再次校验 expected base hash、workspace confirmation set hash、candidate set hash 和 selected candidates。
- promote 成功后，需要回写 candidate / submission / workspace 的归档状态，并关闭 batch。
- 失败时必须保留 diagnostics，不能静默降级为“已归档但未晋升”的假成功。

## Step Diagnostics

每个 step 应记录：

```text
operation_id
step_name
status
started_at
finished_at
duration_ms
provider
cache_layer optional
cache_key_digest optional
cache_validation_status optional
input_digest_summary
artifact_count optional
table_count optional
failure_code optional
failure_phase optional
retryable optional
```

诊断不得包含 host path、完整 SQL payload 或敏感 cache key payload。

## Cache 状态转换

```text
PROVISIONAL
  -> CONTENT_VERIFIED optional
  -> COMMIT_VALIDATED
```

规则：

- `PROVISIONAL` 通常由 warmup operation 写入。
- `COMMIT_VALIDATED` 只能由 finalize/write operation 或 repository readback validation 后产生。
- Read-only operation 只能读取 `COMMIT_VALIDATED` cache。

## Retry 与取消

规则：

- Retry 不能跳过 digest/binding validation。
- 被 supersede 的 upload generation 相关 warmup operation 应取消或自然过期。
- Writer lease 获取失败或 Dolt server temporary failure 可 retry。
- Final failure 需要用户重新提交或修正输入。
