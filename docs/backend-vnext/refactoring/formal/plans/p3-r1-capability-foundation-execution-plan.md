# P3-R1 Capability Foundation Execution Plan

状态：正式执行计划（Accepted）

日期：2026-08-18

阶段：P3-R1 detail plan；implementation authorization pending

Owner：Backend vNext Capability Architecture

上级计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)

## 1. Scope

P3-R1 只建立 capability contract/test foundation，不实现 SQL/XML parser、source
materialization、storage projection、comparison、risk、mutation planner 或 application
flow。

R1 必须先盘点并复用 Phase 1 已有资产：

```text
vnext/shared_kernel
vnext/backend/src/gateway_backend/artifacts
vnext/backend/src/gateway_backend/infrastructure/artifact_store
vnext/backend/src/gateway_backend/canonicalization_*
vnext/backend/tests/test_architecture.py
vnext/fixtures/golden
vnext/fixtures/vectors
```

R1 不是对既有设计的无条件继承。Phase 1 代码、contract、测试和文档只是 evidence；若
复用会违反当前 P3 owning contract、digest/artifact boundary、依赖规则、容量/并发目标
或恢复语义，必须暂停相关实现并 reopen owning contract/ADR。

## 2. R1 outcomes

R1 完成后必须具备：

- 已审查的 shared primitive、artifact、fixture 和 architecture asset inventory；
- 明确的 KEEP/EXTEND/MOVE/DEFER/REMOVE 结论；
- capability owner、public contract 和依赖方向的静态边界；
- 仅在盘点证明必要时新增或修订 shared primitive；
- 可在 `tmp_path`/local ArtifactStore 中创建、读取、验证和清理测试 artifact；
- capability contract/fixture/import checks；
- 没有 `capabilities/common`、`capabilities/utils` 或万能 provider base class；
- R1 handoff，可作为 R2 entry，但不包含 R2 parser 实现。

## 3. Global invariants

- `gateway_shared_kernel` 继续拥有跨语言 canonical primitive；backend 不复制 digest、
  identifier、scalar 或 encoding。
- `gateway_backend.artifacts` 继续拥有 Backend artifact envelope/store；R1 不定义新的
  ArtifactRef nominal type，不拥有 production retention/cleanup。
- capability contract 就近放在具体 capability package；不创建 generic common package。
- provider identity、线程数、调度顺序不进入 semantic digest。
- capability 之间只传 public contract 或 immutable artifact/ref，不传 mutable Python object、
  provider-private object、builder、planner 或 cache layout。
- 纯 contract、parser、type mapping、projection、comparison、risk 和 planner 测试不得
  创建 Dolt；真实 Repository/readback 只在独立 integration 层验证。
- 未发布项目不为错误设计保留兼容 alias；legacy 只作为 reference oracle。

## 4. Conversation and evidence policy

| Step | Conversation | Required context |
| --- | --- | --- |
| S0 entry/inventory | 新开执行对话 | 本文、P3 contracts/ADR、现有资产路径、当前 git status |
| S1 contract/skeleton | 与 S0 同一对话 | S0 inventory、decision register、owner graph |
| S2 implementation | 新开实现对话 | 本文、S1 handoff、允许路径、测试命令 |
| S3 conformance/tests | 与 S2 同一对话 | changed diff、S2 output、fixture contract |
| S4 focused review | 新开审核对话 | 本文、diff、测试结果、S3 evidence；不依赖实现者叙述 |
| S5 remediation/retest | 新开修复对话 | S4 findings、原始 diff、reopen conditions |
| S6 independent review | 新开独立审核对话 | 本文、最终 diff、findings closure、测试/静态结果 |
| S7 module gate/handoff | 新开验收/文档对话 | 全部 evidence、review closure、next-R entry checklist |

任务提示词只推动当前步骤，不复制设计细节。若对话上下文与本文或 owning contract
冲突，以 owning contract、本文和最新 handoff 为准。

## 5. Step execution plan

### S0 — Existing asset inventory and applicability review

**目标**：证明现有资产能否作为 P3-R1 foundation 使用，并识别必须修订的 contract、owner、
依赖或测试边界。

**只读范围**：

- `docs/backend-vnext/refactoring/formal/architecture/`；
- `docs/backend-vnext/refactoring/formal/contracts/`；
- `docs/backend-vnext/refactoring/formal/adr/0001-python-rust-hybrid-compute-strategy.md`；
- `vnext/shared_kernel/`；
- `vnext/backend/src/gateway_backend/artifacts/`；
- `vnext/backend/src/gateway_backend/infrastructure/artifact_store/`；
- `vnext/backend/src/gateway_backend/canonicalization_*`；
- `vnext/backend/tests/test_architecture.py` 和直接相关 unit tests；
- `vnext/fixtures/golden/`、`vnext/fixtures/vectors/`。

**盘点字段**：

```text
asset/path
current owner
contract authority
current consumers
KEEP/EXTEND/MOVE/DEFER/REMOVE
P3 semantic fit
dependency direction
test evidence
capacity/concurrency concern
artifact/digest concern
failure/recovery concern
required decision or follow-up
```

**必须暂停的 finding**：shared primitive 语义冲突、artifact boundary 无法表达 immutable
handoff、实际 capability cycle、digest/sort/scalar 不一致、关键失败/恢复没有可执行证明，
或复用会违反已接受安全/容量边界。

**输出**：[S0 inventory and applicability review](p3-r1-s0-asset-inventory.md)、
dependency/owner graph、compatibility matrix、issue register、R1-S0 recommendation。
S0 不修改业务代码；如需修订正式 contract/ADR，先记录并等待 decision。

**退出条件**：每个盘点资产有结论；blocking finding 已关闭或正式 reopen；S1 的 owner 和
允许路径明确。

### S1 — Ownership, dependency and public boundary skeleton

**目标**：将 S0 结论变成可检查的 capability package/public contract 边界。

**允许范围**：capability package skeleton、public `contracts.py`/ports、architecture/import
checks、必要的 formal plan/contract cross-reference。不得实现 capability 算法。

**必须验证**：

- 不创建 `capabilities/common` 或 `capabilities/utils`；
- 每个 contract 只有一个 owner；
- capability 只能依赖上游 public contract；
- 不可 import `_internal`、provider selection、planner、builder 或 cache layout；
- Backend foundation 不引入 HTTP、Workspace、Submit、Operation Runtime 或 Repository
  business semantics。

**输出**：可导入的 package skeleton、architecture/import tests、更新后的 owner/decision
register。

### S2 — Proven shared primitive gap decision

**目标**：只处理 S0 证明存在的 shared primitive 缺口。

**默认行为**：如果现有 `gateway_shared_kernel` 或 `gateway_backend.artifacts` 已满足要求，
S2 只增加 conformance tests，不新增抽象。

若确有缺口，必须先说明：至少两个独立 consumer、flow-neutral、稳定命名/语义、可独立测试，
并更新 owning contract/ADR。禁止为了未来可能使用而预建版本、digest、generic failure
registry 或万能 provider interface。

**测试**：跨 Python/Rust 的 canonical fixtures、invalid cases、bytes/digest exact compare、
artifact ref round-trip；不创建 Dolt。

### S3 — Artifact and staging test conformance

**目标**：验证各 capability 后续可以使用统一的测试 artifact/staging 方式。

**实现边界**：复用现有 local ArtifactStore 和 `tmp_path`；增加最小测试 helper 或 fixture
adapter 时，必须保持 artifact content schema 由 capability owner 拥有。

**必须验证**：

- manifest/schema/raw/content digest 校验；
- immutable write/read/reopen；
- partial/corrupt/missing artifact 失败；
- workspace path 不进入 artifact ref；
- 测试结束 cleanup 不影响 durable integrity incident；
- 无永久工作区 staging 依赖。

**输出**：可被 R2-R7 复用的测试 helper contract、round-trip fixtures 和 cleanup tests。

### S4 — Architecture/import and focused contract review

**目标**：在 R1 进入 remediation 前，独立验证设计边界和当前 diff。

**审核重点**：shared-kernel duplication、generic-common drift、nominal ArtifactRef 混用、
capability cycle、隐藏 mutable state、测试依赖 Dolt、错误映射越权、scope expansion。

**对话要求**：新开 focused review 对话。审核者只依赖本文、formal contracts/ADR、diff 和
测试结果，不把实现者口头解释当作 evidence。

### S5 — Remediation and retest

**目标**：逐条关闭 S4 findings，保持 R1 scope 不扩张。

**规则**：

- contract/ADR finding 不能只靠代码 workaround 关闭；
- 每个修复必须新增或更新 regression test；
- 修复后重新运行受影响的 unit/conformance/static checks；
- 新发现的 P1/P2、digest/storage/recovery 或跨语言问题必须 reopen owner；
- 若 remediation 改变 S1/S2 decision，回到对应 step 并重新审核。

### S6 — Independent review

**目标**：对 R1 最终 candidate 做与实现对话隔离的独立审核。

**输入**：最终 diff、S0 inventory、S4 findings、S5 closure、测试/静态检查结果、artifact
round-trip evidence。

**最低检查**：contract owner、依赖图、shared primitive reuse、artifact boundary、cleanup
边界、scope/non-goal、R2 entry handoff。发现 blocking finding 时不得进入 S7。

### S7 — R1 module gate and handoff

**目标**：形成可供 R2 使用的稳定 handoff。

**必须记录**：

- tested source tip；
- changed paths；
- commands/counts/results；
- inventory 和 decision register；
- contract/ADR/fixture references；
- known limitations 和 deferred items；
- R2 entry prerequisites；
- implementation authorization status。

R1 gate 通过不代表 Phase 3 implementation 全部授权；只表示 R1 foundation 可以作为后续
R2 entry 使用。

## 6. Test and command policy

具体命令以实际 package/changed paths 为准，默认至少包含：

```text
owner package unit/conformance tests
ruff check
mypy
architecture/import checks
artifact round-trip and cleanup tests
git diff --check
```

纯 Python/internal logic 不引入真实 Dolt fixture；若使用 subprocess、durable on-disk state
或 real Dolt，按仓库 AGENTS 规则标记 integration/serial。

## 7. Handoff to P3-R2

R2 只有在 R1-S7 handoff 后再创建详细计划。R2 entry 必须拿到：

- stable public boundary and import checks；
- accepted shared primitive inventory；
- artifact/staging helper contract；
- no-open-blocker statement；
- R2-specific parser questions重新从 P3 contracts 读取，而不是从 R1 内部实现猜测。

## 8. Reopen conditions

- 发现 R1 复用资产与正式 contract/ADR 冲突；
- 新增 shared primitive 但无法证明两个独立 consumer；
- 任何 capability import `_internal` 或形成 cycle；
- artifact raw/content digest 或 nominal ref 边界混用；
- 纯 capability 测试开始依赖 Dolt；
- R1 需要引入 Operation Runtime、HTTP、Workspace、Submit 或新的安全主体；
- 实现者无法在当前 step context 中解释完整的输入、输出、不变量和测试证据。
