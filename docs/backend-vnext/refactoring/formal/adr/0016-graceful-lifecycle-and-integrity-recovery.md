# ADR 0016: Graceful Lifecycle and Integrity Recovery

状态：Accepted

日期：2026-08-18

决策 owner：Backend vNext Operation Runtime and Repository Integrity

关联阶段：Phase 3 error boundary、Phase 4 runtime、Phase 5 deployment integration

## Context

规则变更、容器维护和 repository/external target 故障都可能发生在 Preview 或 Submit 中间。
业务数据重新上传成本较低，但 repository commit 和 target 状态是不可逆或需要保护的事实。
普通日志不足以持续提示用户或阻止自动 cleanup。

## Decision

安全关停与安全重启共用 graceful lifecycle。`DRAINING` 关闭新业务 admission，保留已有
operation、checkpoint 和 durable takeover；首版 timeout 为 deployment/runtime 配置默认
`180s`，超时进入 `DRAINING_TIMEOUT`，不自动强杀。restart 是 graceful shutdown 后的
startup recovery 和 health check。

临时 artifact 或未产生 repository effect 的流程允许丢弃并重新上传，新 attempt 通过
`recovery_of` 关联旧 attempt。Dolt commit 已完成后，重新上传不得替代或覆盖原 commit；
external target 必须针对原 canonical commit resync。

Repository/content readback mismatch、CAS ambiguity 等权威事实问题创建 durable
`RepositoryIntegrityIncident`，经稳定错误码、结构化持久日志、metrics/alert 和 admin
readback 暴露，至少保留到 acknowledge、resolution 和显式 archive。普通 artifact cleanup
不得删除未解决 incident。

## Alternatives

- 关停时强制 kill 所有 worker：拒绝，丢失 durable handoff 并扩大未知结果。
- 只依赖进程内 active counter：拒绝，无法覆盖异步 operation 和 restart takeover。
- 通过重新上传修正已完成 commit：拒绝，掩盖权威事实并可能产生分叉。
- 为 incident 引入独立 broker/sidecar：拒绝，现有 control metadata 和日志足够支持首版。

## Consequences

P4 需要 durable lifecycle/operation state 和 takeover；P5 需要 readiness、signal 和
container wiring。用户可以得到明确的 `REUPLOAD_REQUIRED`、`FULL_RESYNC_REQUIRED` 或
`OPERATOR_REVIEW_REQUIRED` 提示，运维也能持续发现未解决 repository 问题。

## Required Verification

- drain、quiescence、180s timeout、restart takeover 和 readiness；
- crash/unknown outcome、external reconcile 和 artifact fallback；
- incident persistence、acknowledge/archive boundary 和 cleanup exclusion；
- re-upload 不复用旧 attempt id，已完成 commit 不被覆盖。
