# P5 架构收口 S0 Entry Brief

- 状态：**DRAFT — 待独立文档审核；实现未授权**
- 日期：2026-09-25
- Owner：Backend vNext Architecture（收口牵头）；独立审核由未参与本轮起草的 reviewer 承担
- 审核顺序：本文件 → [详细设计](p5-arch-closure-design.md) → [执行计划](p5-arch-closure-execution-plan.md)
  → ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
  [0019](../adr/0019-commit-canonical-metadata-authority.md)、
  [0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
  [0021](../adr/0021-flow-neutral-comparison-entry.md)

## 1. 权威与基线

```yaml
entry_kind: p5_arch_closure_s0_docs_only
status: draft; independent docs review pending
docs_branch: p5-arch-closure-docs
docs_worktree: /home/dev/gdds-p5-arch-closure-docs
code_inspection_base: 2172369803          # 5E-S3 exit + 架构门禁基线 + S4 预算例外记录
main_line_at_start: phase1/gate-ownership-repair @ 2172369803
p5_5e_s3_stage_exit: pass
p5_5e_s4: not_started_at_draft            # S4 期间本分支不合入主线
p5_5e_slice_exit: not_evaluated
closure_docs_authorized: yes              # repository owner，2026-09-25
closure_implementation_authorized: no
new_repository_effect_authorized: no
production_deployment_authorized: no
```

本轮全部源码核查与实验都在 `2172369803` 上进行；主工作区未改动。5E-S4 期间主线可能出现回修提交，
这些提交不属于本文基线，由 S1 kickoff 复核（执行计划 §2）。

权威输入：

- `AGENTS.md`、[testing-conventions](../../../testing-conventions.md)、
  [纵切指南](../guides/slice-design-execution-and-review-guide.md)
- [P5 设计 §2A、§2A.4.1、§6、§9](p5-business-vertical-slices-design.md)
- [Architecture](../architecture/architecture-and-refactoring-plan.md) §4、§7、§13
- [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md) §4.4、§5、§8
- [Business Lifecycle 3.0.0](../contracts/business-lifecycle-and-state.md) §2–§6
- [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md) §3
- [P3 能力设计](p3-capability-foundation-design.md) §4.2、[R4 设计](p3-r4-storage-projection-design.md) §4、
  [R5 设计](p3-r5-comparison-design.md) §5、[R6 设计](p3-r6-risk-surface-bundle-design.md)
- [5E 设计](p5-5e-history-compare-design.md) §5、§6.6
- 旧设计 oracle：`docs/backend-vnext/capabilities/project-identity-and-dataset-replacement.md`（仅行为追溯）

## 2. 由实际代码得出的 readiness

| 事实（E） | 证据 | 对本收口的意义 |
| --- | --- | --- |
| 导入门禁已冻结 54 条违例、8 个运行时环、16 个不可达模块 | `T/architecture_baseline.py`、`T/support/import_rules.py` | S1–S5 的机械工作清单 |
| Preview 原始域与规范域比较不一致 | 本轮实验：`com_cfg` 同内容两侧 `DEGRADED` | S2 的阶段门槛测试 |
| 规则集 52 条：显式键 19、带忽略列 13、SKIP 8、BROWSE_ONLY 13、UPDATE_ONLY 11、ORDERED 9 | `migrated_table_ruleset_snapshot()` | 规则视图必须覆盖的角色 |
| Submission 已持久化 `canonicalization_manifest_ref/digest` | `B/domain/submission/models.py` | commit 规范元数据无需新存储 |
| Archive 已有带审计的确认与异常处置事件机制 | `B/domain/archive/models.py`、`B/application/archive/queries.py` | 身份异常处置可复用 |
| surface 已实现替换展示；comparison 替换模式无 facts；risk 无处理 | `B/capabilities/surface_assembly/_assembly.py`、`B/capabilities/comparison/pair_planning.py` | 身份工作量评估 |
| `logics.xml` 被暂存但未解析 | `B/capabilities/source_package_staging/contracts.py`、`B/application/preview_jobs.py` | S3 接入点 |
| composite 派生表主键含 `TEXT` 列 | `B/capabilities/snapshot_materialization/compose.py` | S3 停止条件 |

## 3. 范围、风险与信任假设

- 范围：设计 §1 的目标；不包括 5E slice 内容、Phase 6 实现与部署。
- 主要风险：
  - 规范快照同一性依赖 SQL 与 Arrow 两条编码路径一致；
  - S2 一次性改变 Preview 与 History 的结果语义；
  - S4 新增用户确认交互与 A 类持久事实。
- 信任假设沿用 P5 §3：同机 Backend 与 worker 属于单一信任域；外部 HTTP 输入、artifact 内容、scope 与路径仍不可信。
- 身份确认的 actor 与时间只来自 session 与服务端时钟；理由内容视为不可信输入并受长度约束。

## 4. 交付物与审核边界

本轮交付（全部为文档）：

1. 本 Entry Brief；
2. [详细设计](p5-arch-closure-design.md)（含附录 A：Business Lifecycle 3.1.0 候选）；
3. [执行计划](p5-arch-closure-execution-plan.md)；
4. ADR 0018–0021（状态 Proposed）；
5. [P5 §2A.4.1](p5-business-vertical-slices-design.md#p5-architecture-review-20260925) 第二轮复核补充。

审核结论按纵切指南 §6 给出（通过 / 定向修订 / 整体返工）。审核应重点确认：

- 设计 §4.1 规范快照同一性是否足以支撑 R1、R3 的修复；
- §5.5 删除 5E integrity 机制的依据是否成立；
- §7.2 初始空基线 `NOT_APPLICABLE` 的规定；
- §8 对 P5 §6.1 “XML 增强可降级”的修订；
- 执行计划阶段顺序与 S1“行为不变”约束是否可兑现。

## 5. 通过后的事件（互相独立，不自动推导）

- 文档审核通过：ADR 0018–0021 状态改为 Accepted；Business Lifecycle 按附录 A 升至 3.1.0；
  P5 §2A.2 按 ADR 0021 修订。
- 实现授权：由 repository owner 另行给出，最早在 P5-5E slice exit 之后。
- 本分支合入主线：5E slice exit 之后。

## 6. 验证与镜像决策

docs-only：检查链接、锚点与源码路径；不运行实现测试，不构建镜像。本轮引用的实验脚本与规则统计
为只读核查，结果记录在设计 §2.1 与本文 §2。
