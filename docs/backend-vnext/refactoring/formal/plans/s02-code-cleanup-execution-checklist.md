# S02 Code Cleanup Execution Checklist

状态：Accepted Execution Checklist

日期：2026-07-31

Owner：Backend vNext Architecture（执行顺序与跨对话交接）

Authority ancestor：`fc6a0c9`

权威设计：
[DX Cross-Phase Interface Reconciliation](dx-cross-phase-interface-reconciliation.md)

本文只把DX的`S02-C1..C5`转换为五轮执行清单，不重新定义contract。字段或行为冲突
时停止实现，以ADR 0009、ADR 0010、DX及其链接的owning contract为准。

## 1. 使用方式

每轮使用独立对话，只执行一个`C`项：

```text
确认clean start SHA和本轮scope
  -> 实现/删除/迁移
  -> 定向验证
  -> rg旧引用
  -> review diff
  -> 独立commit
  -> clean worktree
  -> 输出handoff
```

共同规则：

- 当前HEAD必须包含`fc6a0c9`和本清单，且开始时工作区干净；
- 严格按`C1 -> C2 -> C3 -> C4 -> C5`执行；
- 每轮开始SHA是上一轮结束SHA，不跨轮预改；
- 保留canonical bytes、128 cases、Python/Rust核心和mixed-scalar golden；
- 不实现P2 feature、不注册stub route、不保留旧compatibility adapter；
- 每轮定向验证失败必须在本轮修复；未green不提交、不进入下一轮；
- 若本轮仍过大，可拆为多个同scope green commits，但不得混入下一轮；
- 每轮结束报告实际命令、结果、commit SHA、残留项和下一轮是否ready。

## 2. C1 — Delivery-control removal

范围：

- 删除`vnext/conformance/phase2/`的router、gate、closure、affected-scope、
  phase protection、attempt/closure schema及其测试；
- 删除Phase 2专用命令、脚本和CI入口；
- 清除对已删除traceability/F0 formal文件的代码与temporary链接；
- 恢复普通package test入口。

验证：

- 受影响Python package执行ruff、strict mypy、pytest；
- `rg`确认不存在仍可执行的Phase 2 gate/closure/traceability引用；
- review删除清单，确认未触及canonical corpus/core。

退出：

- 普通package命令不再生成attempt、closure或exact-commit evidence；
- 工作区clean并形成独立green commit。

建议commit：

```text
refactor(vnext): remove legacy delivery control
```

## 3. C2 — Canonical test simplification

范围：

- Python/Rust各自薄loader直接消费保留的128 cases并zero skip；
- 删除vector-set manifest/schema、closure validator、candidate/bless generator；
- 删除Repository vector consumer和Shared Kernel `conformance` optional extra；
- 把mixed-scalar golden迁回Backend/Rust owner tests；
- 确认保留测试迁移完成后删除generic `gateway-conformance` distribution。

验证：

- Shared Kernel：ruff、strict mypy、pytest；
- Rust：fmt、clippy、test、release build；
- Python/Rust case ID集合exact一致、128 cases zero skip；
- mixed-scalar expected result未改变；
- `rg`确认Repository/Shared Kernel不再依赖generic conformance。

退出：

- canonical bytes、digest、error classification不变；
- owner tests独立green并形成独立commit。

建议commit：

```text
refactor(vnext): simplify canonical test ownership
```

## 4. C3 — Compute and Backend artifact boundary

范围：

- 切换Canonical Row Hash boundary v1；
- request/result/failure收缩到owning contract字段；
- 用minimal `BackendArtifactRef`替换旧generic envelope；
- 删除generic ArtifactManifest、ContentContract、ContractBinding及ref中的
  semantic/retention/access字段；
- semantic metadata回到capability result/owner manifest；
- ordinary reopen只验证raw integrity、Arrow parse和fixed schema。

验证：

- Backend：ruff、strict mypy、pytest；
- native：installed release wheel、compute、GIL progress；
- Arrow/artifact round-trip及corrupt/truncated/schema negative tests；
- Python/Rust mixed-scalar result一致；
- `rg`确认production ref没有旧generic字段或host path。

退出：

- boundary v1无fallback，minimal ref唯一；
- Backend/native定向验证green并形成独立commit。

建议commit：

```text
refactor(vnext): minimize compute artifact boundary
```

## 5. C4 — Thin Repository packages

范围：

- 用Pydantic/stdlib Versioned DTO、普通UUID、bounded opaque string和simple error
  替换strict/JCS/problem/custom stream体系；
- 删除FailureDescriptor、StoreKind、Current identities、handwritten schemas和
  schema snapshots；
- 建立独立`RepositoryArtifactRef`，不复用Backend class或artifact ID；
- 删除contracts/client/service对Shared Kernel、Backend、Rust compute和
  conformance的依赖并更新lockfiles；
- 不激活业务route或stub OpenAPI。

验证：

- contracts/client/service分别执行ruff、strict mypy、pytest；
- distribution/import boundary tests；
- `rg`确认无Shared Kernel/conformance反向依赖和旧wire类型；
- package/lock diff只保留实际direct dependencies。

退出：

- 三个Repository distributions独立green；
- 没有激活虚假feature，形成独立commit。

建议commit：

```text
refactor(vnext): replace repository contracts with thin v1 DTOs
```

## 6. C5 — Cross-phase regression

范围：

- 不再新增设计或功能，只修复C1–C4暴露的集成问题；
- 清理最后的旧authority、schema、script、dependency和CI引用；
- 记录尚未实现的P2 feature入口。

验证：

- Shared Kernel ruff/mypy/pytest；
- Rust fmt/clippy/test/release build；
- Backend ruff/mypy/pytest；
- Repository contracts/client/service ruff/mypy/pytest；
- installed release wheel import/compute/GIL smoke；
- Backend artifact round-trip；
- 一个Compose health/native smoke；
- canonical 128 cases zero skip、mixed-scalar结果不变；
- 全仓`rg`旧runner/evidence/vector manifest/gate/traceability/custom wire引用；
- `git diff --check`和clean worktree。

退出：

- 所有当前可用ordinary checks green；
- 未实现P2能力明确标记为not implemented，不伪装为pass；
- 形成最终回归commit，S02结束后才可进入P2-R1。

建议commit：

```text
test(vnext): close cross-phase simplification regression
```

## 7. 每轮新对话提示模板

```text
执行S02-C<N>，只完成本轮实现、定向验证和提交。

开始前：
- 确认HEAD包含authority commit fc6a0c9及上一轮handoff commit；
- 确认工作区干净；
- 完整读取formal/plans/s02-code-cleanup-execution-checklist.md对应章节和其引用的
  DX/owning contracts。

执行时：
- 不跨入下一轮，不实现P2 feature，不保留旧compatibility adapter；
- 删除前用rg确认consumer；
- 每轮失败在本轮修复；
- 允许在本轮内进一步拆分green commits。

结束时报告：
- start SHA与commit SHA；
- 修改/删除范围；
- 所有验证命令及结果；
- 旧引用搜索结果；
- 已知限制；
- 下一轮ready：yes/no。
```

## 8. Handoff格式

```text
round:
start_sha:
end_sha:
commits:
changed_or_deleted:
verification:
reference_search:
known_limits:
worktree_clean:
next_round_ready:
```
