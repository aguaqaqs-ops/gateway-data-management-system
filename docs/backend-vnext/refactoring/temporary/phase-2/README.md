# Phase 2 Interactive Design — Working Index

状态：**Historical after WP1-R1 checkpoint / Superseded by ADR 0009**

本文件只提供 Phase 2 交互设计的导航、阶段性一致性视图和恢复入口，不复制
Decision Ledger 正文，也不是正式 contract。正式 Authority 顺序、访谈协议和
Session State 以
[interactive-design-session-guide.md](interactive-design-session-guide.md)
为准。

2026-07-31过渡：本目录的旧设计只继续支持正在进行的WP1-R1 checkpoint。WP1-R1
完成后，安全、恢复、scope和交付规则由
[ADR 0009](../../formal/adr/0009-proportional-assurance-and-trusted-internal-repository.md)
替代；不得从本目录启动旧计划WP1-R2+。执行顺序见
[Architecture Simplification Execution Plan](../architecture-simplification-execution-plan.md)。

## Document map

| 文档 | 职责 |
| --- | --- |
| [interactive-design-session-guide.md](interactive-design-session-guide.md) | Authority 阅读要求、交互协议、Session State、round scope |
| [decision-ledger-round-0-to-3.md](decision-ledger-round-0-to-3.md) | Round 0–3 decision authority：`58 total / 51 ACCEPTED / 7 SUPERSEDED` |
| [decision-ledger-round-4-to-7.md](decision-ledger-round-4-to-7.md) | Round 4–7 decision authority；当前 `32 total / 32 ACCEPTED` |
| [decision-ledger-round-8-to-11.md](decision-ledger-round-8-to-11.md) | Round 8–11 decision authority；当前 `58 total / 58 ACCEPTED` |
| [caller-responsibility-scan-round-0-to-6.md](caller-responsibility-scan-round-0-to-6.md) | Round 0–6严格性分类、候选amendment与OPEN架构问题；不拥有decision语义 |
| [round-11-convergence-readiness-scan.md](round-11-convergence-readiness-scan.md) | Round 11 ledger/WP/gate/formal-conflict readiness证据；不拥有decision语义 |
| [consolidated-design-review.md](consolidated-design-review.md) | Round 0–11整体一致性review、追踪摘要与pre-formalization blocking register |
| [bounded-phase-3-consumer-adequacy-check.md](bounded-phase-3-consumer-adequacy-check.md) | Phase 3已知import/readback consumer覆盖矩阵、F0 obligations与reopen检查 |

聚合状态：`148 total / 141 ACCEPTED / 7 SUPERSEDED`。Round 0–11已全部明确
确认；WP0–WP9与exact-commit exit主线已收敛，Consolidated Design Review已由
用户确认；bounded Phase 3 consumer-adequacy check也已确认PASS。用户已明确授权
formalize；F0 Formal closure已PASS，formal blocking register为空，具备开始WP0-R1
的设计条件。

## Round 4–7 consistency map

下表只描述依赖关系；具体语义、理由、被拒方案和 reopen condition 必须回到
owning decision 阅读。

| 设计链 | Owning decisions | 当前一致性结论 |
| --- | --- | --- |
| Canonical import provider → Dolt runtime ownership | `P2-R4-D01`、`P2-R4-D02` | Canonical SQL replay 只在 repository-scoped bounded runtime 内执行；active sql-server 与 offline CLI 不并发拥有同一 repository。 |
| Durable root → registry/control/current topology | `P2-R4-D03`、`P2-R4-D04` | 单 trust-domain root 内按 repository aggregate 隔离；global registry、per-repository control 与 current transaction authority 不互相冒充。 |
| Provision/restart → backup boundary | `P2-R4-D05`、`P2-R4-D06`、`P2-R6-D08` | Registry-authoritative provisioning 与 repository-aggregate restore一致；partial/mismatched state fail closed。 |
| Journal → idempotency → writer ownership | `P2-R5-D01`、`P2-R5-D02`、`P2-R5-D03` | Accepted request、effect attempt、effect evidence和fencing均durable；timeout/lease expiry不触发blind replay。 |
| Ref/Current mutation → store-specific recovery | `P2-R5-D04`、`P2-R5-D05`、`P2-R6-D11`、`P2-R6-D12` | Mutable write由caller显式选择checked或LWW；内容verification可分级；ref仍以journal/publication evidence恢复，Current仍以SQLite transaction-local marker恢复。 |
| Failure representation → crash classification | `P2-R6-D01`、`P2-R6-D02`、`P2-R6-D15` | Operation status、journal phase、effect classification和FailureDescriptor分离；普通verification mismatch与authority corruption分开处理。 |
| Reconciliation → cancellation/repair | `P2-R6-D03`、`P2-R6-D04` | Repository Service拥有T2 reconciliation；UNKNOWN阻塞对应store mutation lane；caller取消不取消accepted effect。 |
| Cleanup → attribution → authority integrity | `P2-R6-D05`、`P2-R6-D06`、`P2-R6-D07` | Recovery evidence先于cleanup；deterministic private operation ref归因Dolt effect；journal/store矛盾时quarantine而非选边覆盖。 |
| Retention → GC → aggregate lifecycle | `P2-R7-D01`～`P2-R7-D06` | Reachability与分级retention形成GC root；exact-plan quiescent GC、manifested restore和planned deletion共享repository maintenance边界；restore以public incarnation阻止旧caller静默重放。 |

Round 6 已通过 `P2-R6-D09` 接受caller-selected verification；Round 0–6已按
“Repository Service提供机制和证据、caller选择所需严谨度”完成扫描，并确认
不得降低effect safety、authorization、input safety或durable recovery。

## Round 10 exit coverage map

| Guide obligation | Owning decisions |
| --- | --- |
| Schema/wire、compatibility、stale state | `P2-R10-D01`、`D02`、`D06` |
| Fake/Local/Remote与Local/Remote等价 | `P2-R10-D02` |
| Pinned read、stream、backpressure、cancel/deadline | `P2-R10-D07` |
| Idempotency、CAS/LWW、lease、verification | `P2-R10-D04`、`D09` |
| Journal crash、UNKNOWN、restart、GC/backup/restore | `P2-R10-D03`、`D09` |
| Security/resource/container/TLS/platform | `P2-R10-D05`、`D08`、`D11`、`D12` |
| Gate result、immutable evidence、Phase 1 regression | `P2-R10-D01`、`D05`、`D10`、`D13` |

## Formalization gap

当前 Accepted formal contract 仍包含以下旧规则：

- Normal versioned write 必须从 committed ref 流式读取全部 required
  canonical/protected tables，生成并匹配 versioned `SnapshotManifest` 后才可
  `VERIFIED`。
- Provider/import success、commit hash、input digest、hidden summary、schema 或
  row count 单独都不能替代上述 full committed-ref readback。
- `UNKNOWN/APPLIED` 不得 blind replay 或释放业务/Repository serialization
  occupancy。
- Archive/ref CAS 复用已验证 commit 的内容 evidence，不重复全表扫描。

Legacy 曾支持 `DISABLED`、row-count、schema/row-count、hidden-summary/catalog
和 table-digest 等 validation policy；默认 plan 使用 schema/row-count，旧
formal submit 使用 hidden-summary/catalog。它们是 implementation evidence，
不是当前 formal `VERIFIED` authority。

`P2-R6-D09` 已确认目标语义与上述 formal 规则不同：caller必须显式选择
`NONE | STRUCTURAL | FULL`，三者完成requested policy后均可VERIFIED并正常
推进；后验检查是独立VerifyCommit。该冲突必须在整体设计获准formalize后通过
formal contract和superseding ADR一次性消除，不能让实现同时支持两套
VERIFIED含义。

## Accepted readback tiers

Formalization必须同步修改：

1. `canonical-storage-and-repository-boundary.md`；
2. `external-effect-and-recovery.md`；
3. architecture 与 implementation stages；
4. performance baseline authority；
5. Phase 2 exit criteria、recovery fixtures 和 downstream T3 finalize contract。

Verification level只影响内容/结构检查，不能关闭journal、idempotency、CAS、
fencing、effect attribution和reconciliation。完整decision见`P2-R6-D09`。

## Remaining ownership

| Round | Current/deferred topics |
| --- | --- |
| Round 9 | 9项observability、identity、readiness/restart、reconciliation、capacity、measurement与runbook decision已确认 |
| Round 10 | 13项conformance、failure/security/container gate与Phase 2 exit matrix decision已确认 |
| Round 11 | 26项WP/R、依赖、rollback、有限并行与exact-commit exit decision已确认 |

## Resume rule

恢复会话时依次读取：

1. Guide §5 Session State；
2. 三个 Decision Ledger；
3. 本文件的 OPEN 项；
4. 对应 formal owners。

已经 `ACCEPTED` 的 decision 不重复访谈；要改变时必须按 ledger 的 reopen
condition 保留原记录并显式 supersede。
