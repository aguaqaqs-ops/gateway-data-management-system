# P5 架构收口 S0 Entry Brief

- 状态：**DRAFT r3 — 已按 S0 独立审核（F1–F11）、owner 决议（DC10–DC27）与两份 r2 独立复审修订，待独立复审（可只核对 r3 差异）；实现未授权**
- 日期：2026-09-26（r2、r3）；r1 为 2026-09-25
- Owner：Backend vNext Architecture（收口牵头）
- 修订与复审：r2、r3 由 S0 审核者应 repository owner 要求执行修订。r2 经两份独立复审，结论均为定向修订；r3 按两份复审的
  findings 与 DC23–DC27 修订。r3 的复审须由未参与 r3 修订的 reviewer 承担，可只核对 r3 差异；修订者的自查不构成独立复审。
- 复审顺序：[修订处置表](p5-arch-closure-s0-revision-disposition.md)（§8 为 r3 部分）→ 本文件 → [详细设计](p5-arch-closure-design.md)
  → [执行计划](p5-arch-closure-execution-plan.md)
  → ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
  [0019](../adr/0019-commit-canonical-metadata-authority.md)、
  [0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
  [0021](../adr/0021-flow-neutral-comparison-entry.md)
- 审核与决议依据：[S0 独立审核报告](p5-arch-closure-s0-independent-docs-review.md)、r2 独立复审
  （[第一份](p5-arch-closure-s0-independent-rereview.md)、[第二份](p5-arch-closure-s0-independent-rereview-2.md)）、
  [S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md)

## 1. 权威与基线

```yaml
entry_kind: p5_arch_closure_s0_docs_only
status: draft r3; independent re-review of r3 pending
docs_branch: p5-arch-closure-docs
docs_worktree: /home/dev/gdds-p5-arch-closure-docs
code_inspection_base: 2172369803          # 5E-S3 exit + 架构门禁基线 + S4 预算例外记录
main_line_at_start: phase1/gate-ownership-repair @ 2172369803
r1_reviewed_commit: 3e5d5807e5
s0_review_verdict: targeted_revision      # 审核报告 @ 89668aaf56（含 2026-09-26 补充）
r2_reviewed_commit: 5858eaaa08
r2_rereview_verdicts: [targeted_revision, targeted_revision]   # @ 34ff1827cf、ca6502d8a4
owner_decisions: DC1-DC27                 # DC10–DC22 @ 3f3b1de192；DC23–DC27 @ f984381ab3
p5_5e_status_source: main_line_5e_records # 本文不判定 5E 状态
p5_5e_slice_exit_required_before_s1: yes  # 本分支在 5E slice exit 前不合入主线
closure_docs_authorized: yes              # repository owner，2026-09-25
closure_implementation_authorized: no
new_repository_effect_authorized: no
production_deployment_authorized: no
adr_status_changed: no                    # 0018–0021 保持 Proposed
contract_version_changed: no              # 上游修订只以候选文本形式给出（设计附录 A、B）
```

全部源码核查与实验都在 `2172369803` 上进行；主工作区未改动。r2、r3 修订期间确认 `vnext/` 与该基线无差异。
5E 期间主线的回修提交不属于本文基线，由 S1 kickoff 复核（执行计划 §2）。

权威输入：

- `AGENTS.md`、[testing-conventions](../../../testing-conventions.md)、
  [纵切指南](../guides/slice-design-execution-and-review-guide.md)、
  [比例化保障政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)
- [P5 设计 §2A、§2A.4.1、§6、§9](p5-business-vertical-slices-design.md)
- [Architecture](../architecture/architecture-and-refactoring-plan.md) §4、§7、§13
- [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md) §4.4、§5、§8
- [Business Lifecycle 3.0.0](../contracts/business-lifecycle-and-state.md) §2–§6
- [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md) §2、§3、§7、§9
- [Ruleset Activation](../contracts/ruleset-activation-and-migration.md) §1、§3、§5
- [Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md) §4、
  [ADR 0016](../adr/0016-graceful-lifecycle-and-integrity-recovery.md)、[ADR 0017](../adr/0017-sql-spelling-declared-type-unification.md)
- [P3 能力设计](p3-capability-foundation-design.md) §4.2、[R4 设计](p3-r4-storage-projection-design.md) §4、
  [R5 设计](p3-r5-comparison-design.md) §5、[R6 设计](p3-r6-risk-surface-bundle-design.md)
- [5E 设计](p5-5e-history-compare-design.md) §5、§6.6
- 旧设计 oracle：`docs/backend-vnext/capabilities/project-identity-and-dataset-replacement.md`（仅行为追溯）；
  legacy 源码只在主工作区 `legacy/` 中作为行为 oracle 只读使用

## 2. 由实际代码得出的 readiness

| 事实（E） | 证据 | 对本收口的意义 |
| --- | --- | --- |
| 导入门禁已冻结 54 条违例、8 个运行时环、16 个不可达模块 | `T/architecture_baseline.py`、`T/support/import_rules.py` | S1–S5 的机械工作清单 |
| Preview 原始域与规范域比较不一致 | 起草实验与审核复现：`com_cfg` 同内容两侧 `DEGRADED` | S2b 的阶段门槛测试 |
| 规则集 52 条：显式键 19、带忽略列 13、SKIP 8、BROWSE_ONLY 13、UPDATE_ONLY 11、ORDERED 9。带忽略列的 13 条中，4 条真正丢弃存储列，9 条是 ordered 表的 `no`（同时是结构列） | `migrated_table_ruleset_snapshot()`；审核报告 F5 | 规则视图必须覆盖的角色；ordered `no` 的处置（设计 §4.4） |
| Submission 已持久化 `canonicalization_manifest_ref/digest`，finalize 时由 `canonicalization-manifest` owner 长期保护 | `B/domain/submission/models.py`、`B/application/submission/finalize_transaction.py` | commit 规范元数据无需新存储 |
| Archive 已有带审计的确认与异常处置事件机制 | `B/domain/archive/models.py`、`B/application/archive/queries.py` | 身份异常处置可复用 |
| surface 已实现替换展示，但从 comparison 导入 `IdentityStatus`，且没有调用方传入 `table_artifacts`；comparison 替换模式无 facts；risk 无处理 | `B/capabilities/surface_assembly/contracts.py`、`B/capabilities/comparison/pair_planning.py` | 身份工作量评估；surface 改用中性标注（设计 §6） |
| `logics.xml` 被暂存但未解析 | `B/capabilities/source_package_staging/contracts.py`、`B/application/preview_jobs.py` | S3 接入点 |
| composite 派生表主键含 `TEXT` 列；Dolt 2.1.11 拒绝 `TEXT` 主键 | `B/capabilities/snapshot_materialization/compose.py`；审核报告 E3 | DC20 改为 `VARCHAR(64)`，不再是停止条件 |
| 独立审核补充事实 E-a…E-i：存储类型词表、Dolt 约束、SET 解码、descriptor 与伪 gid、schema 盲区、expected parent 与删表、INITIAL 非空供给、ordered `no`、import 包组成 | 审核报告 §3、§4、§7；设计 §2.2 | S2a、S2b、S3 的输入 |

## 3. 范围、风险与信任假设

- 范围：设计 §1 的目标；不包括 5E slice 内容、Phase 6 实现与部署。
- 主要风险：
  - 规范快照同一性依赖投影与 Repository 读取两条路径一致；由 S2a 的真实 Dolt integration owner 把关；
  - 真实数据的类型覆盖未知；由 S1 kickoff 普查决定 S2a 的类型词表范围（DC12、DC15、DC22）；
  - S2b 一次性改变 Preview、Submit 与 History 的结果语义；S2a 结束时 R1 仍存在（执行计划 §2 的中间状态说明）；
  - 规则激活对各流程的影响（设计 §4.9）需要与 Ruleset Activation 契约保持一致；
  - S4 新增用户确认交互与 A 类持久事实。
- 信任假设沿用 P5 §3：同机 Backend 与 worker 属于单一信任域；外部 HTTP 输入、artifact 内容、scope 与路径仍不可信。
- 身份确认的 actor 与时间只来自 session 与服务端时钟；理由内容视为不可信输入，受设计 §7.6 的输入边界约束。
- 真实数据只在主机侧使用，行数据、真实项目名与主机路径不进入 Git（决议记录 §4）。

## 4. 交付物与复审边界

r3 交付（全部为文档）：

1. 本 Entry Brief；
2. [详细设计](p5-arch-closure-design.md)（附录 A：Business Lifecycle 3.1.0 候选；附录 B：Canonical Storage、Ruleset Activation、
   ADR 0016 / Operation Lifecycle、Contract Taxonomy、P5 设计、Architecture 的修订候选）；
3. [执行计划](p5-arch-closure-execution-plan.md)（S2 拆分为 S2a、S2b）；
4. ADR 0018–0021（状态保持 Proposed）；
5. [P5 §2A.4.1](p5-business-vertical-slices-design.md#p5-architecture-review-20260925) 第二轮复核补充；
6. [S0 独立审核报告](p5-arch-closure-s0-independent-docs-review.md)、两份 r2 独立复审报告
   （[第一份](p5-arch-closure-s0-independent-rereview.md)、[第二份](p5-arch-closure-s0-independent-rereview-2.md)）、
   [S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md)与[修订处置表](p5-arch-closure-s0-revision-disposition.md)；
7. [formal README](../README.md) 的索引更新。

复审结论按纵切指南 §6 给出（通过 / 定向修订 / 整体返工）。

DC1–DC27 是 repository owner 的决定（DC1–DC9 于 2026-09-25，DC10–DC27 于 2026-09-26）。复审不以偏好重新裁决这些
决定；如发现某项决定与上游 Contract 或不变量冲突、无法实施或会造成未被认识的业务损失，应作为 finding 提出并说明依据。

r3 复审可只核对 r3 差异，重点确认：

- 两份 r2 复审的 findings 是否按处置表 §8 关闭（处置表以 RV1-、RV2- 前缀区分两份报告的 RR 编号），DC23–DC27 是否落到所列位置；
- 受理判定顺序（设计 §7.6、ADR 0020）是否与现行实现一致：授权与 exact scope 先于 same-key 重放；
- business schema digest 与 manifest `canonical_schema_digest` 的区分（设计 §4.1、附录 B.1）是否无歧义；存储身份改用存储规则事实后，
  §4.5 的对齐与来源标记是否自洽；
- 附录 B.2（Ruleset §1、§5）、B.3（incident 范围，DC25）、B.4–B.6 的替换文本能否按字面并入；
- 执行计划 S1 验收（含 DC26 的精确放行）与 S2a/S2b 路径预算是否与被删符号的使用方一致。

r2 复审时提出的重点仍然适用：

- 处置表中每条 finding 与决议是否关闭，改动是否传播到设计、计划、ADR 与附录中的所有相关位置；
- 规则激活语义（设计 §4.9、附录 B.2）与 Ruleset Activation §1、§5 及 Canonical Storage §7、§9 是否一致；
- 规范身份（设计 §4.1）与规范状态摘要（§5.3）能否使 `NO_CANONICAL_CHANGE` 与 Preview 展示得出一致结论（F2、F11）；
- T1 冻结与 prepare 按 expected parent 删表（§4.8）是否与 evidence-first 恢复、CAS 闭合（F3、DC18）；
- DC9 删除清单（§5.5）是否准确，ADR 0016 的范围修订（附录 B.3）是否只收窄 incident 适用范围；
- 身份确认的输入边界、错误码与判定顺序（§7.6）是否闭合（N1）；
- 执行计划的 S1 验收能否由 `import_rules` 机械核对，路径预算是否覆盖，S2a/S2b 边界是否清楚（F10、DC21）；
- 附录 A、B 的候选文本能否在接受时直接并入。

## 5. 通过后的事件（互相独立，不自动推导）

- 文档复审通过：
  - ADR 0018–0021 状态改为 Accepted；
  - Business Lifecycle 按附录 A 升至 3.1.0；
  - 附录 B 的候选并入对应文档：Canonical Storage 升至 3.1.0（§2、§4）、Ruleset Activation §1 与 §5、ADR 0016 与
    Operation Lifecycle §4 的 incident 范围、Contract Taxonomy §4.4/§4.6/§5/§13、P5 §2A.2/§6.1/§2A.4、
    Architecture §7.1/§7.2/§9.1/§10/§13；
  - P3-R3/R4/R5 设计与 5E §6.6 加“由 ADR 00xx 取代”的标注，不改写历史正文；
  - 以上由 owner 以单独的 docs 提交完成。
- 实现授权：由 repository owner 另行给出，最早在 P5-5E slice exit 之后。
- 本分支合入主线：5E slice exit 之后。

## 6. 验证与镜像决策

docs-only：检查链接、锚点与源码路径；不运行实现测试，不构建镜像。本轮引用的实验与规则统计为只读核查，
结果记录在设计 §2、本文 §2 与审核报告 §3、§7。
