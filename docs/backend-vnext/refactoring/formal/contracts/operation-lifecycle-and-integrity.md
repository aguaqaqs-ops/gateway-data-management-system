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
