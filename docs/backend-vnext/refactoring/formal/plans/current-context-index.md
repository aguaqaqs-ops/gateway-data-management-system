# Current Context Index

最近核对：2026-11-10 04:06Z。本文只作检索入口，规则、授权与状态由下列 owner/固定来源决定。

## 当前阶段与下一入口

- **P6 已退出**：附注 tag `p6-exit` 指向 `b0fc25e881cb4ce39b1cc847bad92b4ccb06b809`。原文可用 `git show p6-exit` 读取；[最终报告](p6-s6-report.md)、[III 执行](p6-s6-iii-execution.md)与[协调记录](p6-s6-coordination.md)是证据入口。范围为六包、本地容器、fresh t4 最小链；不签 FE、P7、独立 SDK 或 production，原失败/UNKNOWN/取消项及维护限制不改。
- **main 核对点**：`00ca325c2ed6d705abfa39e9528ef148e6029cfc`，核对时 clean；其 `vnext` tree 仍为 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`，等于 P6 exit。之后的实际 HEAD/并行变化须重新核对。
- **P7-S1a A 已核收并合入 main**：A_GO 绑定 `355c54a0022fde8237f788c0007e375801ff5288`，main 合入提交为上述 `00ca325c2e`。该核收只覆盖 A 文档/设计入口，Contract 的“目标补充（待实现）”没有因此成为已实现行为；不表示 B–G、S1a EXIT_GO、产品或容器通过。
- S1a 下一入口依次是 [A 入口/消费者与 Contract 目标](p7-s1a-a-entry-and-contract.md)、[执行计划](p7-s1a-execution-plan.md)、[存储/资源设计](p7-s1a-storage-resource-design.md)与[实施提示词](p7-s1a-implementation-prompt.md)；总体与决议见 [P7 design](p7-design.md)、[P7 execution](p7-execution-plan.md)、[S0 Owner 决议](p7-s0-owner-decisions.md)及[处理组/测试抽取设计](p7-processing-groups-and-test-extraction-design.md)。[A 静态稿](p7-s1a-a-verification.md)和对应脚本保留历史输入/失败说明，不在本整理中执行。

A_GO 的原审签署在外置 `/home/dev/gdds-p7-s1a-reviews/a/355c54a0-a-go.md`，SHA256 为 `3d22ae5e4b11143e505bfb7de3cc4b06c7f226a2cee6009639580f7a2f9ddfbb`；由该原审核收 06 静态原件，本整理仅只读该签署，不重签或复验其产品。仓库内 A 实施文档保留当时的候选自述，最终 A 状态以上述固定签署和 main 合入为依据。

需要固定字节时，例如：

```bash
git show 355c54a0022fde8237f788c0007e375801ff5288:docs/backend-vnext/refactoring/formal/plans/p7-s1a-a-entry-and-contract.md
```

S1a B 隔离工作区 `/home/dev/gdds-p7-s1a-b` 在核对时有未提交产品改动；这只说明并行实施现场，不构成 B 通过依据。本索引不接管其实施、审核或合入。输入推进后只重核受影响依赖，未知用途先保留。

## 先找 owner，再读源码

| 问题 | 当前已合入 owner / 源码入口 | S1a 已合入目标的读取边界 |
| --- | --- | --- |
| 多 root、发布、保护与清理 | [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、[Business Lifecycle](../contracts/business-lifecycle-and-state.md)、[Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md)；`vnext/backend/src/gateway_backend/{artifacts,infrastructure/artifact_store,infrastructure/control_db,application,bootstrap}/` | 已合入 S1a 的详细设计及同路径 Contract“目标补充（待实现）”；不当作当前源码已生效行为 |
| canonical/export/comparison artifact、bundle | [artifacts 说明](../../../artifacts.md)及 formal owner；`vnext/backend/src/gateway_backend/capabilities/` | 已合入 S1a 的 `artifacts.md` 与 `contracts/{snapshot-table-access,comparison-bundle,comparison,risk}.md`，按 A 消费者表核 producer/decoder |
| RS roots、发布对与一致集合 | [Repository Service](../contracts/repository-service.md)、[Storage Mutation](../contracts/storage-mutation-and-change-set.md)；`vnext/repository_service/src/gateway_repository_service/` | 已合入 S1a 的对应 Contract 与执行计划；B–G 未因此被声明通过 |
| 语义归属、政策与 ADR | [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md)、[比例化保障政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)、[ADR0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md) | 计划/索引只引用唯一 owner；历史授权不扩大为当前权限 |

正式 owner 全导航见 [formal README](../README.md)。总纲、实施阶段规划和 FE 文档的同步由其原 owner 负责，本轮不代改；前端从 [frontend kickoff](../../../../frontend-vnext/frontend-kickoff.md) 进入，不能由 P6 或本整理结果推导 FE 验收。

## 当前授权与执行规则

[AGENTS](../../../../../AGENTS.md)、[testing-conventions](../../../testing-conventions.md) 和 [S0 Owner 决议](p6-s0-owner-decisions.md)是仓库通用执行规则入口：含 DC91 节点池、DC97 协调与现行 DC68。执行前仍先核本轮用户/任务明确输入及适用范围，不从历史“未授权”或专项许可推导当前授权。

**S1a 特定输入另行适用**：[A 入口 §1](p7-s1a-a-entry-and-contract.md#1-实际入口和来源) 明确本轮用户给出的旧节点分工/DC68优先于其本地 main 通用新版；06 focused、04 权威、05 默认真实调试，不继承 P6 06 完整旅程专项许可，也不默许三轮恢复。该限制属于 S1a，本索引既不覆盖它，也不把它扩展为其他任务的通用规则。

**本次文档整理**的角色、模型与验证授权来自 [cleanup 提示词](p6-p7-documentation-cleanup-prompt.md#4-角色模型与上下文)和[执行方案](p6-p7-documentation-cleanup-execution-plan.md#5-角色与工作包-ac)：每包新建实施/独审/验证者；只在开发主机做文档/Git 静态核查，不 import 产品、不跑产品测试/lint/编译/Compose、不连接测试节点。S1a 角色来源仍是其固定实施提示词及其引用的 [P6-S6 模型来源](p6-s6-implementation-prompt.md#3-角色模型与上下文)，不把 P6 任务权限一并继承。

实际 worktree/分支先用 `git worktree list --porcelain`、`git status --short` 和 `git rev-parse HEAD` 核对；工作区绝对路径和过去的 clean 状态不是永久保证。共享文件写入冲突交所属协调者处理，不切换或修改他人的被测树。

## 历史追溯与恢复

本轮仅归档 A 原审核准的三份已关闭中间记录；[机器可读 TSV 清单](p6-p7-documentation-cleanup-manifest.tsv)逐文件列 `original_path`、`source_commit`、`source_blob`、`sha256`、理由、后续 owner 与依赖处置。完整 source_commit 为 `5ddd73b962e2432f961a46f6743395a53a388435`，已是 main 祖先；最终合入时还须复核可达性。

只读恢复到本人临时目录，不覆盖活跃路径，例如：

```bash
git show 5ddd73b962e2432f961a46f6743395a53a388435:docs/backend-vnext/refactoring/formal/plans/p4-r2-s6-remediation-appendix.md > /本人临时目录/p4-r2-s6-remediation-appendix.md
```

另外两文件按清单完整路径同样读取，并核 SHA256。原相对链接按来源提交解释，不改写失败为通过。R2 最终结论仍见 [最终 handoff](p4-r2-durable-store-atomic-transition-handoff.md)和[S6 独审](p4-r2-s6-independent-review.md#8-independent-remediation-rerun)；P5 round4 由保留的 [round5 handoff](p5-5b-s6-remediation-round5-handoff.md)、[S6 最终独审](p5-5b-s6-independent-review-5.md)及 [S8 handoff](p5-5b-s8-handoff.md)承接，容器 skip/defer 与旧轮限制保留。

较早归档见 [P3→P4 handoff](p3-p4-cleanup-handoff.md)及[manifest](p3-p4-cleanup-manifest.yaml)、[P2→P3 manifest](p2-p3-cleanup-manifest.yaml)；各原 tag/最终签署不改。P5/P4 历史默认入口见 [formal README](../README.md#历史入口与恢复)。

## 仍须保留的实际消费者

- [P2 feasibility](p2-r1-runtime-provider-feasibility.md)：`vnext/scripts/test_input_closure.py` 纳入 RS 闭包；`vnext/repository_service/tests/test_p2_r1_audit_corrective.py` 实读 methodology 字节。
- `legacy/` 与 P3 handoff：`vnext/backend/tests/support/table_rules_legacy_oracle.py` 动态加载 legacy；capability 的 Authority docstring 仍引用 P3 parser/source/table-rules handoff。
- [P5 census](p5-arch-closure-s1-census.json)：`vnext/backend/benchmarks/real_dump_journey.py`、`s4_submit_measurement_driver.py` 和 `vnext/backend/tests/test_table_access_sql_census.py` 实读。
- [P6-S4 C review](p6-s4-c-review.md)：`vnext/fixtures/vectors/mutation/sql-replay/v1/batch-boundaries.json` 的 independent_review 固定引用。
- P6 原始成功/失败、有效 Owner 决议、各阶段最终原审/handoff，以及 S1a 的 [P6-S6 prompt](p6-s6-implementation-prompt.md)/[协调记录](p6-s6-coordination.md)模型来源继续保留。其余未逐文件核清的过程记录暂缓，见[协调记录](p6-p7-documentation-cleanup-coordination.md#3-保留与延期)。

从本入口限定 owner/源码路径检索；需要全量当前文本仍可用普通 `rg`，需要已归档原文用清单及 `git show`。文件/命中/输出字节只是检索辅助统计，不是 Codex 时延、正确率或 token 成本实测。
