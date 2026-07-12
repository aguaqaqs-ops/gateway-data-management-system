# Flows

本文描述 backend vNext 的业务流程如何调用能力层。能力层保持 flow-neutral；业务状态和执行状态在本层与 `operations.md` 中表达。

## 调用者类型

| 调用者类型 | 典型流程 | Repository import |
| --- | --- | --- |
| `DIRECT_RESPONSE_CALLER` | Upload preview | 不执行 |
| `READ_ONLY_CALLER` | History compare、archive diagnostics read-only | 不执行 |
| `WARMUP_CALLER` | Upload 后 precommit warmup | 可选，仅产生候选结果 |
| `FINALIZE_WRITE_CALLER` | Submit/commit finalize、archive/promote write | 执行，必须校验 |

## Capability Policy 映射

能力层保持 flow-neutral。业务流程只通过显式 policy 调用 capability，不要求 capability 理解 upload、submit 或 history compare。

| 调用者类型 | `cache_policy` | `cache_lookup_policy` | `validation_status_policy` | `artifact_policy` |
| --- | --- | --- | --- | --- |
| `DIRECT_RESPONSE_CALLER` | `DISABLED` 或 `READ_ONLY` | `READ_COMMIT_VALIDATED_ONLY` | `NO_CACHE_WRITE` | 按响应需要生成 caller-local artifact |
| `READ_ONLY_CALLER` | `READ_ONLY` | `READ_COMMIT_VALIDATED_ONLY` | `NO_CACHE_WRITE` | `CALLER_LOCAL_REQUIRED` |
| `WARMUP_CALLER` | `WRITE_THROUGH` | `READ_ANY_WITH_REVALIDATION` | `PROVISIONAL_ONLY` | `CACHE_ARTIFACT_ALLOWED` |
| `FINALIZE_WRITE_CALLER` | `WRITE_THROUGH` | `READ_PROVISIONAL_WITH_REVALIDATION` | `PROMOTE_AFTER_AUTHORITY_VALIDATION` | `CALLER_LOCAL_REQUIRED` |

规则：

- 流程状态、权限和 UI 反馈变化时，应优先调整 flow/operation 层，不修改 capability。
- 只有 capability 的输入、输出、artifact、cache 或 validation 需求变化时，才修改 capability contract。
- 任何读取 `PROVISIONAL` candidate 的流程都必须从 durable source/ref 重新校验，并具备 fallback recompute 路径。
- upload preview 期间的 comparison core cache 只能作为 provisional candidate；它在 `SUBMIT_FINALIZE` 拿到最终 repository-backed commit / ref 后，要被 promotion / rekey 成 canonical compare-core cache，供后续只读流程复用。
- 该 provisional candidate 在提交 finalize 完成前不应被 history compare 直接消费；只读流程只能看 canonical 身份。
- cache 的实际查询和复用应由 flow / operation / capability 内部完成；调用方只决定是否注入 cache 句柄或禁用 cache，不手动拼接 cache key 或直接查询 cache entry。

## Upload Preview

目标：

- 快速反馈给前端展示。
- 不创建不可逆业务事实。
- 不执行重负载 Dolt import。

同步主路径：

```text
receive preview package
  -> source_package_staging optional
  -> sql_dump_source_resolution
  -> snapshot_materialization
  -> comparison / risk / surface
  -> preview/workbench response
  -> PreviewInputBinding
```

规则：

- 不等待 cache warmup 或 comparison core cache completion。
- 不创建 immutable repository ref。
- 不推进 Submission 状态。
- 同步结果只证明 preview 可展示，不证明数据已进入 Dolt。

响应后可启动异步 comparison core cache completion；upload 后也可再启动额外 warmup，见 `operations.md`。

## Upload Precommit Warmup

目标：

- 利用用户检查期间的时间，为后续 submit/commit 加速。
- 生成候选 cache 或 shadow benchmark 结果。

异步路径：

```text
preview accepted
  -> optional snapshot/table/projection cache warmup
  -> optional repository import shadow/precommit operation
  -> diagnostics
```

规则：

- warmup 结果不得作为 preview ready 条件。
- warmup 失败不得改变 workspace preview 业务状态。
- upload 阶段产生的 cache 只能是 `PROVISIONAL` candidate。
- 后续 finalize 必须从 durable submit/source 和 binding 重新校验。

## Submit Acceptance

目标：

- 同步接收 submit full package。
- 完成轻量、确定性的拒绝条件检查。

同步路径：

```text
receive SubmitSourcePackage
  -> durable L1 source artifact
  -> PreviewInputBinding validation
  -> generation / permission / state check
  -> create SubmitOperation
  -> return ACCEPTED or rejected
```

规则：

- `ACCEPTED` 不表示 Dolt commit 成功。
- `ACCEPTED` 不表示 Submission 已进入审核状态。
- 重负载 repository import 进入异步 finalize。
- 第 10 步第一版只把 `PreviewInputBinding` 与 `SubmitSourcePackage` 的 required entry digest / parser version / table ruleset version 硬校验收口，并创建一个后续由 finalize worker 接管的 `OperationKind.SUBMIT_FINALIZE` queued operation record。
- `submission_id` 在 submit acceptance 阶段分配，并随 accepted response / operation request payload 一起传递到后续 finalize。
- `SubmitAccepted.status = ACCEPTED` 是同步接收响应状态；运行时持久化记录仍使用通用 `OperationStatus.QUEUED`，后续由 finalize worker 推进。
- workspace generation gate、permission gate 和更细的业务准入，在 API / workspace 层补齐后再接入，不放进这一步的最小 acceptance seam。
- 初版建议把这条入口收敛到 `backend_vnext/workspaces/` 薄层，由它承接 preview binding 比对、`PREVIEW_READY` gate、`active_submit_operation_id` 乐观写入和失败回滚，再调用 submit acceptance flow。

## Submission Review

目标：

- 提供 submit 后的薄 review state machine。
- 让 approve / reject / withdraw 保持正式业务语义，但不把 archive 语义塞进 review 本体。

规则：

- `START_REVIEW` 只把 submission 推进到 review 中间态，不改变 archive 归档结果。
- `APPROVE` 只改变 review 语义，不触发 archive，也不隐式推进 mainline。
- `REJECT` / `WITHDRAW` 允许把 workspace 重新开放，并释放对应 mutable ref。
- review flow 不重建 submit / import / compare 的事实，只消费已存在的 submission 和 workspace 记录。

## Submit / Commit Finalize

目标：

- 将已接收 submit 输入固化为 repository commit/ref。
- 校验导入后的 repository state 与 source Snapshot 一致。
- 成功后创建或推进 L2 业务事实。

异步路径：

```text
SubmitSourcePackage durable
  -> binding validation / replay validation
  -> sql_dump_source_resolution
  -> snapshot_materialization
  -> repository_import as FINALIZE_WRITE_CALLER
  -> readback validation
  -> hidden summary table write / validation
  -> promote validated cache candidates
  -> immutable ref / Submission L2 state
```

规则：

- 可以读取 upload warmup 的 `PROVISIONAL` cache candidate 加速。
- provisional candidate 校验失败时回退到 `SubmitSourcePackage` 重算。
- repository import/readback validation 成功后才可以 promote cache 为 `COMMIT_VALIDATED`，其中包括把 upload preview 期间的 comparison core cache provisional candidate rekey / promotion 成 canonical repository-backed entry。
- submit finalize 成功后，FINAL SnapshotSummary 通过 repository commit/ref 内的 hidden summary table 持久化；history compare 只读读取这份事实，不再自行重建摘要。
- validation mismatch 是最终失败。
- `SUBMIT_FINALIZE` 第一版固定为 `SQL_DUMP_REPLAY` replay-only：正式提交只消费重建后的 `replay.sql`，不要求 CSV/TSV staging。
- provider 切换能力继续保留在 repository import capability / benchmark 低层；如果后续确有需要让 submit finalize 走其它 provider，再单独调整这条 flow contract。
- finalize worker 只接管 acceptance 已经创建好的 `OperationKind.SUBMIT_FINALIZE` operation，不在 finalize 阶段重新创建 operation。
- submit finalize 成功后，workspace 状态推进应通过 `backend_vnext/workspaces/` 薄层完成，而不是在 finalize flow 里直接耦合业务仓库实现。
- submit finalize 的 cleanup 只回收临时资源；`repository_path`、`run_dir` 和 commit/ref 属于正式结果或诊断依据，默认保留，不由 flow 内部自动删除。

## History Compare

目标：

- 对历史 repository refs 生成只读 comparison/surface/bundle。
- 不改变 workspace、submission、archive 或 repository write state。

只读路径：

```text
repository refs
  -> hidden summary table readback
  -> table artifact cache lookup
  -> comparison / risk / surface / bundle
```

规则：

- 不执行 repository import。
- 不读取 upload provisional cache。
- 只读取 `COMMIT_VALIDATED` / repository readback 产生的 cache，以及 submit finalize 已 promotion / rekey 到 canonical 身份的 comparison core cache。
- hidden summary table 缺失、损坏或版本不匹配应视为完整性错误，不应回退到重新生成 summary。
- READY 前必须闭合 operation artifact closure。
- 真实 benchmark 可以把这一条 flow 组织成 2-node compare 或 3-node dual-pair compare 的 ladder，但那只是 benchmark-local 编排，不是新的 public flow contract。

## Archive / Promote Mainline

目标：

- 将已审核且满足归档前置条件的 immutable candidate 推进为 mainline。
- 在异常场景下，必须通过显式的异常确认、候选选择与可追溯的保护引用后，才允许推进。
- 正式代码入口位于 `backend_vnext/flows/archive.py`。

规则：

- Archive 是 batch-scoped write flow，不能只看单个 submission 的状态就直接推进。
- 在执行 mainline write 之前，flow 必须完成只读预检，并确认以下条件：
  - batch 处于可归档且未冻结的状态。
  - 所有 active workspace 均已确认。
  - candidate set 与预期哈希一致。
  - 恰好一个 `MAINLINE_MODIFIED` 候选被选中。
  - 所有被选中的 `BASELINE_INITIAL_HISTORY` 候选都存在对应的 anomaly resolution。
  - 非 `APPROVED_SUBMISSION` 来源的 mainline candidate 已提供 override reason，且 candidate 仍然受保护于 immutable ref。
- `Open Ref` / repository ref materialization 只在 archive 的所有验证、selection 和 promote 完成后的最后收尾步骤执行，用来做只读回读闭合；它不能取代业务判定，也不能把 mutable preview 视为业务事实。
- Diagnostics、dry-run 和 eligibility 预检可以使用 read-only capabilities；正式 mainline write 仍属于 write/finalize caller，并且必须受 repository writer lease 保护。
- 归档成功后，flow 必须回写 candidate、submission 和 workspace 的归档状态，并关闭 batch。
