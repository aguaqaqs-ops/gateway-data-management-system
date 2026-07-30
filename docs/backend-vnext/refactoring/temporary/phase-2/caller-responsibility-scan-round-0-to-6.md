# Phase 2 Caller-Responsibility Scan — Round 0–6

状态：**Resolved / Review Complete**

本文件记录 `P2-R6-D09` 之后对 Round 0–6 的阶段性扫描。它只做分类、指出
候选 amendment 和恢复访谈上下文，不拥有 decision 语义。最终选择必须写回
owning Decision Ledger；formal contract 只在整体设计获准 formalize 后修改。

## Accepted principle

Repository Service 提供通用机制、明确 evidence 和可选择的policy；caller为自己
选择的业务严谨度负责。该原则不意味着caller可以关闭服务维持自身正确运行所需
的安全边界。

当前分类：

| 类型 | Owner | 是否可由 caller 降级 |
| --- | --- | --- |
| 业务/内容严谨度 | Caller | 可以显式选择 |
| Freshness、lost-update policy、结果完整度 | 待本轮确认 | 可以设计为显式选择 |
| Effect identity、accepted-request recovery | Repository Service | 建议不可关闭 |
| Authentication、path/input/resource safety | Repository Service/deployment | 不可由普通请求关闭 |
| Provider/storage内部一致性 | Repository Service | 不可由普通请求关闭 |
| Transport framing/completeness | Repository Service/client contract | 不可关闭 |

## Already caller-owned

以下 Accepted decisions 已符合该原则，无需重开：

| 能力 | Decisions | 说明 |
| --- | --- | --- |
| Versioned/Current store选择 | `P2-R0-D06`、`P2-R2-D06` | Caller保存persistence policy；服务不判断authority。 |
| Cross-store一致性 | `P2-R0-D07`、`P2-R2-D09`、`P2-R2-D22` | Caller独立编排，不提供dual-write或unified snapshot保证。 |
| 同名表关系 | `P2-R2-D07` | 服务不推断两侧同步或等价。 |
| 小型同步/大型异步Current mutation | `P2-R2-D20` | Caller通过显式operation选择completion model。 |
| Query order与resume | `P2-R3-D03` | 未请求order时不承诺顺序；需要resume的caller显式提供total order。 |
| Stream或artifact delivery | `P2-R3-D04` | Diff caller显式选择delivery form。 |
| Import verification level | `P2-R6-D09` | Caller显式选择NONE/STRUCTURAL/FULL并承担内容验证强度。 |

## Strictness retained as service safety

扫描建议以下规则不要解释为“过度保证业务结果”，也不要下放给普通caller：

| 规则 | Decisions | 保留理由 |
| --- | --- | --- |
| Thin auth、repository/action isolation | `P2-R1-D01`、`D02`、`D13` | 防止越权，不是内容质量偏好。 |
| Opaque path/identity与受限input grammar | `P2-R2-D01`、`D02`、`D03`、`D08` | 防止path/provider泄漏与任意执行。 |
| Journal、effect attribution、fencing、UNKNOWN reconciliation | `P2-R5-D01`、`D03`、`P2-R6-D02`、`D03`、`D06` | 保证服务能解释自己是否执行过请求；关闭后连caller也无法可靠承担风险。 |
| Control/store corruption fail closed | `P2-R4-D05`、`P2-R6-D07` | 防止在未知内部状态上继续覆盖数据。 |
| Stream/artifact completeness与hash | `P2-R3-D02`、`D04`、`D05`、`D10` | 防止截断bytes被误当完整响应；不是业务内容验证。 |
| Closed type/SQL boundary | `P2-R2-D03`、`D08`、`D15`、`P2-R3-D07` | 保持通用typed contract与安全边界；caller可在调用前自行转换数据。 |
| Immutable/protected ref语义 | `P2-R2-D02`、`P2-R5-D04` | Caller已通过ref kind选择mutable或immutable；选择immutable后语义必须稳定。 |

## Resolved architecture candidates

### C1 — Effect-safety opt-out boundary

`P2-R5-D02` 当前要求所有mutation使用idempotency key，journal/fencing也不可选。
最终由`P2-R6-D10`确认：caller-responsibility只覆盖结果/并发/freshness policy；
idempotency、journal、fencing和effect reconciliation保持强制，不提供
fire-and-forget mutation。

### C2 — Caller-selected lost-update policy

`P2-R6-D11`已确认mutable write显式选择：

```text
concurrency_mode = CHECK_EXPECTED | LAST_WRITE_WINS
```

Immutable/protected refs、operation ref和internal metadata不受该选择影响。

### C3 — Current bulk verification level

`P2-R6-D12`已确认async Current table-content write复用
`NONE | STRUCTURAL | FULL`；SQLite transaction/generation/effect marker始终
强制。小型同步row mutation继续使用transaction-local evidence，不做全表scan。

### C4 — Exact snapshot versus latest-at-start read

`P2-R6-D13`已确认catalog、stream和export显式选择：

```text
read_binding = EXACT(binding) | LATEST_AT_START
```

LATEST_AT_START在真正打开provider snapshot时解析并返回resolved binding；它不
提供跨请求repeatable read。

### C5 — Atomic batch versus partial success

`P2-R6-D14`确认继续采用TableMutationBatch all-or-nothing，不增加BEST_EFFORT。
Caller需要独立失败域时拆分batch，或使用现有UpsertRow等明确variant。

## Reviewed but not reopened

- `P2-R2-D14/D16/D17` 的closed mutation vocabulary减少歧义；增加generic SQL或
  arbitrary patch不会简化整体contract。
- `P2-R3-D07` 的exact logical type mapping防止silent precision loss；caller可在
  Repository边界前选择自己的coercion。
- `P2-R3-D08` 已允许不同table分别`COMPLETE/UNSUPPORTED`，只禁止无法证明的
  partial records，caller已有stream-two-commits fallback。
- `P2-R6-D04` 禁止accepted effect随transport cancel，是effect uncertainty规则，
  不是替caller决定业务可靠性。
- `P2-R4-D06` 的quiescent backup和`P2-R2-D23`的repository deletion属于Round 7；
  后续设计可继续应用caller-selected policy，但当前不提前裁决。

## Formalization warning

`P2-R6-D09` 与当前Accepted formal full-readback规则冲突；`P2-R6-D11`和
`P2-R6-D13`也扩展了当前formal/temporary surface。整体formalization必须一次性
更新semantic owner和ADR，不得让实现依赖本扫描文件推断contract。

## Convergence result

Round 0–6复扫后没有剩余会改变Repository Service核心架构的阻塞问题。其余事项
已明确归属Round 7 retention/GC/backup/delete、Round 8 security/resource limits、
Round 9 observability/operations或Round 10 conformance，不在本轮提前裁决。
`P2-R6-D15`另完成了最后的派生收口：requested verification mismatch是普通
operation failure，只有authority contradiction或真实storage corruption才触发
quarantine。
