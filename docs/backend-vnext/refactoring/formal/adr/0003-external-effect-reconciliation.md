# ADR 0003: Evidence-First External Effect Reconciliation

状态：Accepted

日期：2026-07-19

决策 owner：Backend vNext Application and Repository Architecture

关联阶段：Phase 2、Phase 4、Slice 5B/5D

2026-08-02 amendment：T1/T2/T3业务事务边界继续有效；Repository Service内部
journal/effect classification与FULL evidence已由ADR 0009替代为四态Operation、
caller-selected NONE/STRUCTURAL/FULL_SCAN、matching commit marker、stable未发布
failure code和人工恢复分支。

## Context

业务数据库与独立 Repository Service 之间没有分布式事务。请求发送后的 timeout、worker crash 或 lease takeover 无法证明 Repository 未接受请求。把 `RUNNING` step 整体重做可能重复 commit/CAS；把 Operation failure 当作业务终局又可能错误释放占用。

## Decision

SubmitAttempt与ArchiveExecution各自使用
`PREPARED/EFFECT_PENDING/FINALIZED/ABORTED`四态，并以T1验收、T2外部effect、T3
业务finalize划分事务。Repository Service的SUCCEEDED operation、matching CommitId
和target ref是effect result；业务content/digest facts仍由业务owner检查。Repository
内部恢复使用matching commit marker，矛盾状态显式进入MANUAL_RECOVERY_REQUIRED。

请求可能已被接受后必须先reconcile，并复用原operation、idempotency key、
request/artifact digest；只有Repository matching SUCCEEDED或普通未发布stable failure才
允许业务finalize/abort，MANUAL_RECOVERY_REQUIRED继续占用。Repository自身仅在无
matching commit且artifact完整时以原key自动重放一次。Outbox record与业务finalize
同事务，delivery独立。精确规则由
[External Effect and Recovery Contract](../contracts/external-effect-and-recovery.md)唯一规定。

## Alternatives

- 业务数据库与 Repository Service 使用分布式事务：拒绝，增加协调依赖且不能消除 Dolt 进程级故障边界。
- 超时后以新 key 重试整个 step：拒绝，可能重复外部 effect。
- Operation terminal status 直接决定业务 unlock：拒绝，执行证据不等于 effect certainty。
- 为每个证据阶段增加业务状态：拒绝；journal/evidence 与 typed failure 已足够。

## Consequences

重复投递、进程重启和网络不确定性可恢复到唯一业务终局，但需要durable Repository
operation、immutable artifact checkpoint、reconciler和故障注入测试。
`EFFECT_PENDING`可能长时间占用资源，运维必须提供attention/repair，而不能以blind
replay快速解锁。

## Required Verification

- 每个 request-acceptance 前后注入点的 restart/takeover tests。
- 已知Repository operation不blind replay；业务worker只查询原operation。
- Repository SUCCEEDED result、T3和outbox delivery之间crash后恰好一次业务结果。
- MANUAL_RECOVERY_REQUIRED不自动释放业务occupancy，由operator处理。
