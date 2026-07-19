# ADR 0003: Evidence-First External Effect Reconciliation

状态：Accepted

日期：2026-07-19

决策 owner：Backend vNext Application and Repository Architecture

关联阶段：Phase 2、Phase 4、Slice 5B/5D

## Context

业务数据库与独立 Repository Service 之间没有分布式事务。请求发送后的 timeout、worker crash 或 lease takeover 无法证明 Repository 未接受请求。把 `RUNNING` step 整体重做可能重复 commit/CAS；把 Operation failure 当作业务终局又可能错误释放占用。

## Decision

SubmitAttempt 与 ArchiveExecution 各自使用 `PREPARED/EFFECT_PENDING/FINALIZED/ABORTED` 四态，并以 T1 验收、T2 外部 effect、T3 业务 finalize 划分事务。Repository Service journal 和 full readback evidence 是 effect authority；恢复只按 `NOT_APPLIED/UNKNOWN/APPLIED` 分类推进。

请求可能已被接受后必须先 reconcile，并复用原 operation、idempotency key、request/artifact digest；只有权威 `NOT_APPLIED` 才能重放原请求或 abort。Outbox record 与业务 finalize 同事务，delivery 独立。精确规则由 [External Effect and Recovery Contract](../contracts/external-effect-and-recovery.md) 唯一规定。

## Alternatives

- 业务数据库与 Repository Service 使用分布式事务：拒绝，增加协调依赖且不能消除 Dolt 进程级故障边界。
- 超时后以新 key 重试整个 step：拒绝，可能重复外部 effect。
- Operation terminal status 直接决定业务 unlock：拒绝，执行证据不等于 effect certainty。
- 为每个证据阶段增加业务状态：拒绝；journal/evidence 与 typed failure 已足够。

## Consequences

重复投递、进程重启和网络不确定性可恢复到唯一业务终局，但需要持久 Repository journal、immutable artifact checkpoint、reconciler 和故障注入测试。`EFFECT_PENDING` 可能长时间占用资源，运维必须提供 attention/repair，而不能以 blind replay 快速解锁。

## Required Verification

- 每个 request-acceptance 前后注入点的 restart/takeover tests。
- `UNKNOWN/APPLIED` 不重发、不解锁；explicit `NOT_APPLIED` 才允许原 key replay。
- Journal APPLIED/VERIFIED、T3 和 outbox delivery 之间 crash 后恰好一次业务结果。
- Readback mismatch 保持 effect evidence 和占用。
