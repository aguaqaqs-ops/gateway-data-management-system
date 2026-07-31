# Architecture Simplification Execution Plan

状态：Active / Design Before Combined Code Cleanup

日期：2026-07-31

适用范围：WP1-R1 checkpoint、Phase 0–2简化设计与联合代码清理

正式决策：
[ADR 0009](../formal/adr/0009-proportional-assurance-and-trusted-internal-repository.md)

本文只记录执行顺序、状态和checkpoint，不拥有public/persisted/wire语义。任务完成
后删除本文，Git历史作为执行记录。

## 1. Objective

在不改变Phase 0–1 canonical业务结果的前提下，删除缺少现实威胁、业务损失或
consumer依据的security/evidence/recovery复杂度。先闭合Phase 0–2整体简化设计，
再分批清理共享代码，避免Phase 2 contract与Phase 0–1 artifact owner反复返工。

## 2. Confirmed baseline

| Area | Baseline |
| --- | --- |
| 目标 | 业务优先、适度保障、需要驱动 |
| 使用场景 | 少量协作者；Backend通过内网Repository Service保存Versioned tables |
| Repository范围 | Dolt Versioned-only；Current等待真实consumer |
| 认证 | 一个global bearer；deployment TLS；无per-repository ACL |
| Create | 同步幂等；initial empty commit和main |
| Upload | 同步one-shot streaming；size/raw SHA；package临时 |
| Import | 唯一异步业务Operation；expected commit同时作为parent和CAS预期 |
| Verification | committed table/schema/row count；无FULL row rehash |
| Operation | QUEUED/RUNNING/SUCCEEDED/FAILED；一次恢复；矛盾人工处理 |
| Ref | import内嵌CAS；无standalone CAS/LWW/force |
| Read | explicit CommitId；raw Arrow IPC |
| 负载 | 10–100 MB通常、约200 MB极端；10–200次/天、1,000次极端 |
| 并发 | 跨Repository有限并行；单Repository通常一周一次写入 |
| Retention | commit永久；success package删除；orphan/普通失败TTL |
| Backup | 上游备份package；部署层snapshot durable root；无public backup API |
| Compatibility | T2/T3无承诺；真实route从`/v1/`激活 |
| Phase 0–1 KEEP | canonical bytes、Python/Rust核心和少量业务golden |

## 3. Revised sequence

```text
T0  Proportional-assurance decision
  -> T1  WP1-R1 legacy checkpoint
  -> D2  Phase 2 simplification design
  -> D01 Phase 0–1 simplification design
  -> DX  Cross-phase interface reconciliation
  -> C02 Phase 0–2 combined code simplification
  -> P2  Revised Versioned Repository feature delivery
```

`C02`是同一执行阶段，不是单一commit。至少拆成delivery-control、Phase 0–1外围、
Repository contracts、dependency/reference cleanup和联合回归五批。

## 4. Completed stages

### T0 — Decision contract

状态：COMPLETE

- ADR 0009接受适度保障、可信内网和Versioned-only。
- 总体Architecture加入全局原则和重新进入条件。
- 旧ADR 0008只保留WP1-R1历史意义。

### T1 — WP1-R1 legacy checkpoint

状态：COMPLETE

- Implementation closure：`361a56a`
- Verified checkpoint：`ed8a69c`
- 未发布package或wire，不产生兼容义务。

### D2 — Phase 2 simplification design

状态：COMPLETE

- Repository Service Contract已破坏性改写为精简baseline。
- Phase 2 plan已改写为design-before-code和最小Versioned纵切。
- T2 implementation checklist已生成。
- `$grill-me`已确认负载、同步/异步边界、CAS、artifact和灾难恢复。

## 5. D01 — Phase 0–1 simplification design

状态：READY

设计必须按同一原则审查：

### KEEP

- JCS、typed scalar、identifier、row/collection framing的canonical bytes；
- canonical row hash和业务content equality；
- Python/Rust核心实现；
- 少量跨语言golden；
- Backend compute、artifact round-trip和container smoke。

### REVIEW FOR SIMPLIFY/REMOVE

- fixture/scenario closure digest和self-verifying manifest；
- run evidence、gate closure和phase-exit identity；
- exact-commit bundle、frozen-path protection和immutable attempt；
- 重复schema/runtime validator和大规模negative evidence matrix；
- ArtifactRef中的通用content/access/retention字段；
- 普通读取时的重复全量hash；
- 已失去consumer的conformance profile、script和临时sign-off材料。

### Required output

- Phase 0–1 KEEP/SIMPLIFY/REMOVE清单；
- 每个保留digest的业务owner和使用者；
- 最小ArtifactRef与canonical import package边界；
- 保留的普通CI命令和golden集合；
- 删除依赖图和分批代码计划；
- canonical bytes不变的验收方法。

## 6. DX — Cross-phase reconciliation

状态：PENDING / requires D01

只核对共享接口：

1. ArtifactRef字段、raw SHA和生命周期；
2. Storage Projection业务digest与Repository structural verification；
3. `manifest.json + replay.sql`字段owner；
4. shared-kernel/canonical vectors的保留consumer；
5. conformance package、scripts和CI删除边界；
6. Backend → contracts/client依赖。

如果D01发现Artifact字段需要调整，允许在代码开始前一次性修订D2 contract；不得
重新引入ACL、FULL verification、custom wire或exact evidence。

## 7. C02 — Combined code simplification

状态：BLOCKED / requires D01 + DX

执行批次：

```text
C0 baseline and retained-test inventory
C1 remove Phase 2 delivery-control/traceability
C2 simplify Phase 0–1 evidence/conformance shell
C3 replace Repository contracts
C4 clean dependencies, locks, scripts and references
C5 joint regression and deletion proof
```

控制：

- 每批独立commit；
- 不混入新Repository业务feature；
- 不修改canonical bytes；
- 不删除没有被D01明确裁决的Phase 0–1代码；
- 不继续使用已删除的closure作为新验收authority；
- ordinary tests失败时修复代码或明确调整设计，不生成waiver evidence。

## 8. C02 exit

- 正式文档只有一套有效Phase 0–2语义；
- 旧141项traceability、router、closure和attempt不再存在；
- Phase 0–1 canonical bytes和核心golden不变；
- Repository contracts只剩薄Pydantic DTO；
- contracts/client/service和保留的Backend/shared-kernel tests通过；
- 尚未实现的business route不advertise；
- 可以按修订后的P2-R1开始真实feature delivery。

## 9. Risks

| Risk | Control |
| --- | --- |
| 联合清理范围过大 | 同一计划、独立commits、每批保留测试 |
| D01推翻D2接口 | DX只允许代码前一次协调修订 |
| 旧gate阻止新设计 | 旧gate只证明checkpoint，不再拥有新authority |
| canonical结果被误删 | bytes/golden为硬验收，外围evidence与业务digest分开 |
| Dolt去重低于预期 | P2真实数据测量，不提前承诺比率 |
| 极端峰值积压 | configurable worker/admission；按测量调整 |
| snapshot后CommitId变化 | 接受人工重放与引用修正；需要更高保障时重开ADR |

## 10. Status

| Stage | Status | Evidence |
| --- | --- | --- |
| T0 Decision | COMPLETE | ADR 0009 |
| T1 WP1-R1 checkpoint | COMPLETE | `361a56a`; `ed8a69c` |
| D2 Phase 2 design | COMPLETE | simplified contract/plan + T2 checklist |
| D01 Phase 0–1 design | READY | next stage |
| DX Cross-phase reconciliation | PENDING | requires D01 |
| C02 Combined code simplification | BLOCKED | requires D01 + DX |
| P2 Revised feature delivery | PENDING | requires C02 |
