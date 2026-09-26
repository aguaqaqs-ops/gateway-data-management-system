# P5 架构收口 S0 文档 r2 独立复审报告

- 状态：独立复审报告（docs-only）。本报告不接受 ADR、不修改 Contract 版本、不改变任何阶段状态，也不构成实现授权。
- 日期：2026-09-26
- 复审者：未参与 r1 起草、S0 审核与 r2 修订的独立 reviewer
- 复审依据：[纵切指南](../guides/slice-design-execution-and-review-guide.md) §3–§6、`AGENTS.md`、
  [testing-conventions](../../../testing-conventions.md)、
  [比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)。
  关闭标准以 [S0 独立审核报告](p5-arch-closure-s0-independent-docs-review.md)（含 §7 复核补充）为准；
  DC1–DC22 以 [Owner 决议记录](p5-arch-closure-s0-owner-decisions.md) 为准，不重新裁决。
  [r2 修订处置表](p5-arch-closure-s0-revision-disposition.md) 的“状态”一栏只作线索，逐条独立重判。
- 结论：**定向修订**

## 1. 结论与理由

**定向修订。** r2 把 S0 审核的核心问题落到了可实施的定义上，总体方案与主执行路径成立：

- 运行期规则集（DC10）解除了 F1 的死锁。`RULESET_BINDING_MISMATCH` 已删除；设计 §4.9 的“激活类别 × 场景”对照表把
  AcceptSubmit 陈旧拒绝、恢复时稳定失败、Submit 使用冻结产物三条路径接到了一起。
- “规范 descriptor = import schema”（设计 §4.1、§4.2）加上真实 Dolt 往返 owner，使 F2 可以测试。
- import 包由 infrastructure publication adapter 组装；T1 冻结规范表集合闭包与 manifest；prepare 按冻结的 expected parent
  推导 `removed_tables`（设计 §4.3、§4.8）。本复审在 Dolt 2.1.11 上复现了删表回放，确认不改 Repository 即可通过回放与
  STRUCTURAL 校验（RE6）。
- 规范状态摘要覆盖 schema 且排除列序（设计 §4.1、§5.3），F11 的定义部分关闭。
- F5、F6、F9 的文档部分关闭；F7、F8 的文档部分已按标注时点到位。

复审另发现 6 项阻塞缺口。每项都能在有限章节内修正，不需要重建核心模型或主执行路径，所以不判整体返工。但其中两项触及
基础边界，两项使附录不能在接受时直接并入，两项使执行计划不能按原文兑现，所以不能判通过：

| ID | 摘要 | 影响的关闭项 |
| --- | --- | --- |
| RR-F1 | 受理判定顺序把 same-key 重放放在权限与 scope 之前，与现行实现相反，授权边界被倒置 | N1 |
| RR-F2 | 附录 B.2 没有处理 Ruleset Activation §5 末句（“已捕获旧 snapshot 的 operation 继续使用原规则”），并入后与 DC11 矛盾；B.2 的“effect 边界”与设计的“T1 之后”不一致 | F1、F4 |
| RR-F3 | N3 的实施必达条件（`CommitCanonicalMetadataPort` 的键与 scope、manifest digest 校验）没有测试 owner 与阶段验收 | N3 |
| RR-F4 | S1 验收不能由 `import_rules` 机械兑现：`compute.py` 迁入 capability 后新增一条 layer 违例 | F10 |
| RR-F5 | S2a/S2b 路径预算遗漏了被删机制的若干使用方；按预算执行，S2a 的 compose 门禁无法运行 | F10 |
| RR-F6 | 附录 B.4 漏掉 Contract Taxonomy §4.4、§4.6 中的 comparison projection；附录 A 第 1 项与 B.3 的插入点在句中；设计 §11、ADR 0018 与附录 B 对 R4 §4.2 的处理不一致 | F4 |

另有 5 项非阻塞建议（RR-N1–RR-N5），见 §5.2。原 findings 的关闭情况见 §4：F2、F3、F5、F6、F9、F11 已关闭（文档层，
实施待阶段验证）；F1、F4、F7、F8、F10 部分关闭；N2、N4、N5、N6 已关闭；N1、N3 部分关闭。

## 2. 复审对象

```yaml
docs_branch: p5-arch-closure-docs
docs_worktree: /home/dev/gdds-p5-arch-closure-docs
rereview_commit: 5858eaaa08e8a32948d3ab08f827224baef30ddd   # 复审开始时的 HEAD
concurrent_commit: 34ff1827cf   # 复审期间分支上新增的另一份复审报告；只新增该报告，被复审文件与 vnext/ 均未改动
r1_commit: 3e5d5807e5
review_report_commits: [8d89ca3c86, 89668aaf56]
owner_decisions_commit: 3f3b1de192
code_inspection_base: 217236980350d523101936af5464fbbd9ad66f88
vnext_diff_check: "git diff --stat 2172369803 5858eaaa08 -- vnext" 输出为空
r1_to_r2_diff: "git diff --stat 3e5d5807e5 5858eaaa08" 为 12 个文件，+1984 / -423
main_workspace_usage: 只读使用 vnext/backend/.venv 与 gitignored legacy/（行为 oracle）
s4_drift: 不追踪（由 S1 kickoff 复核）
```

本报告的全部结论在看到 `34ff1827cf` 之前形成，未参考该报告。任务指定的报告路径已被 `34ff1827cf` 中的另一份复审报告占用，
经任务委托方同意，本报告以 `-2` 后缀另存，不修改该报告。

被复审文件（@ `5858eaaa08`）：

- [r2 修订处置表](p5-arch-closure-s0-revision-disposition.md)
- [Entry Brief](p5-arch-closure-s0-entry-brief.md)
- [详细设计](p5-arch-closure-design.md)（含附录 A、B）
- [执行计划](p5-arch-closure-execution-plan.md)
- ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
  [0019](../adr/0019-commit-canonical-metadata-authority.md)、
  [0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
  [0021](../adr/0021-flow-neutral-comparison-entry.md)
- [P5 §2A.4.1](p5-business-vertical-slices-design.md#p5-architecture-review-20260925) 第二轮补充
- [formal README](../README.md) 索引项

作为输入阅读、不复审其结论的历史记录：审核报告、Owner 决议记录。

路径与行号约定：以 `vnext/` 开头的路径相对仓库根目录，行号以 `2172369803` 为准（worktree 中 `vnext/` 与之相同）；以
`legacy/` 开头的路径只存在于主工作区；文档行号以 `5858eaaa08` 为准。审核报告与决议记录使用 r1 章节号，本文已按处置表 §5
换算为 r2 编号。

## 3. 核查范围、实验与局限

### 3.1 只读核查范围

- 文档：处置表、Entry Brief、设计（含附录 A、B）、执行计划、ADR 0018–0021、P5 §2A.4.1 与 README。逐条对照审核报告
  F1–F11、N1–N6 的关闭标准与 DC10–DC22。
- 上游原文：Ruleset Activation 全文；Canonical Storage 全文；Business Lifecycle §1A–§9；Operation Lifecycle §1–§4；ADR 0016；
  Contract Taxonomy §4.4、§4.6、§5、§13；Architecture §7、§9.1、§10、§13；P5 §2A、§4、§6.1、§9；5D 设计 §2、§6。
- 源码：
  - AcceptSubmit 的预检、T1、重放顺序与请求指纹；T1 与 finalize 的保护转移；
  - storage_projection 的投影、codec 与 import replay；mutation_planning 的 DML；
  - Repository Service 的 replay、`add --all` 与 STRUCTURAL 校验；
  - History 受理与规则集冻结；manifest 与规则集的版本校验；table_rules 的列处置校验；
  - import 规则与冻结基线；被删机制的全部使用方（grep）。
- 测试：设计 §12 各 owner 的存在性与 marker；compose harness 的基线种子方式。

### 3.2 实验

脚本放在复审者的临时目录，未入库。Python 实验按任务约定的 `PYTHONPATH` 方式，用主工作区 backend venv 执行 worktree 源码。

| # | 实验 | 结果 |
| --- | --- | --- |
| RE1 | 基线确认：`git rev-parse HEAD`；`git diff --stat 2172369803 5858eaaa08 -- vnext`；`git diff --stat 3e5d5807e5 5858eaaa08` | HEAD 为 `5858eaaa08e8…`；`vnext/` 无差异；r2 改动 12 个文件 |
| RE2 | 在 worktree 源码上重算 import 规则（`find_violations`、`runtime_cycles`、`unreachable_modules`） | 54 条违例（layer 27、capability-surface 12、private 6、unowned-root-module 6、contracts-leaf 3）、8 个运行时环、16 个不可达模块，与冻结基线逐项相等 |
| RE3 | S1 的 A6 迁移模拟：把 backend `src` 与 `import_rules.py` 复制到临时目录，只把 `compute.py`、`canonical_row_hash_ipc.py` 移入 `capabilities/canonical_row_hash/` 后重算 | 违例变为 53 条：两条 unowned-root-module 消失，新增 `('layer', 'gateway_backend.capabilities.canonical_row_hash.compute', 'gateway_compute')`；不可达条目为该 owner 下的 compute、contracts、ipc 三个模块 |
| RE4 | 规则集统计（`migrated_table_ruleset_snapshot()`） | 52 条；STANDARD_DIFF 21、BROWSE_ONLY 13、ORDERED_DIFF 9、SKIP 8、SNAPSHOT_ONLY 1；EXPLICIT_KEY 19；UPDATE_ONLY 11；带 ignored 的 13 条中 4 条有 dropped，9 条 ordered 规则的 ignored 与 structural 都是 `no`；digest `sha256:6f74c865…`。与 Entry Brief §2、审核 E4/E6 一致 |
| RE5 | Dolt 2.1.11 探针（临时目录独立 HOME，预置 `versioncheck.disabled`、`metrics.disabled`） | `dolt init` 后没有用户表；`TEXT` 主键被拒；`VARCHAR(64)` 主键可建；显式 `NULL` 的主键列被拒；SET 写入 `'y,x'` 读回 `x,y`；JSON 读回被规范化，`12345678901234567890` 变为 `12345678901234567000`；同一文本存入 LONGTEXT 原样读回 |
| RE6 | 删表回放模拟（同一临时 HOME）：基线提交含表 a、b；sibling 提交在 main 上新增表 c；从 main 建私有分支，执行 `DROP TABLE IF EXISTS b`、`DROP TABLE IF EXISTS c` 与 a 的 DROP/CREATE/INSERT，`add --all` 后提交 | 候选只剩用户表 a；`dolt diff --summary` 显示 b、c 为 dropped，a 为 modified。结合 STRUCTURAL 的纯函数比较逻辑，manifest 只列 a 时校验一致 |
| RE7 | 被删机制使用方普查：对设计 §4.7、§4.8、§5.3、§5.5、§6 列出的删除符号逐个 grep（src 与 tests） | 与路径预算的差异见 RR-F5 |
| RE8 | 链接与锚点检查：被复审的 11 个文件 | 0 个问题；本报告的检查见 §9 |

### 3.3 局限

- 没有真实 dump；没有端到端运行 Preview、Submit 或 History。
- RE6 直接用 Dolt CLI 模拟私有分支上的回放与提交，没有经过 Repository Service。STRUCTURAL 能否通过，是由
  `verification.py` 的纯函数比较逻辑推出的，没有实际调用。
- RE3 只移动了两个文件，不代表完整的 S1 结果。
- 路径预算核查以 grep 被删符号的使用方为主，没有覆盖“只改导入路径”的测试；执行计划 §3 规定这类测试在 handoff 中列出。
- 没有追踪 5E-S4 期间主线的变化。
- 一次 `dolt version` 在默认 HOME 下执行。该 HOME 已预置 `versioncheck.disabled`，命令只查询版本，没有建库，也没有写任何
  仓库。其余 Dolt 操作都在临时目录的独立 HOME 中进行。
- 没有构建镜像，没有跑全量测试。

### 3.4 镜像决策记录（testing-conventions“每轮评审记录”）

```text
Current HEAD: 5858eaaa08（被复审文档）；复审期间分支 HEAD 前进到 34ff1827cf（只新增另一份复审报告）
Container rebuild required: no
Reason: docs-only 独立复审；未触碰 image/deployment/container 边界；实验只读执行 worktree 源码与临时 Dolt 库
Last verified image revision: none（本轮）
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: 无；各阶段门禁按执行计划 §6
Required execution point: 不适用
```

## 4. 原 findings 关闭情况

文档位置按 r2 编号，括号内为 `5858eaaa08` 的行号。源码缩写：`B` = `vnext/backend/src/gateway_backend/`，只在本表中用于
缩短单元格；正文与 §5 使用完整路径。

| ID | 判定 | 文档依据 | 源码与实验依据 | 说明 |
| --- | --- | --- | --- | --- |
| F1 | 部分关闭 | 设计 §4.1（148–151）、§4.5（255）、§4.6（266、273）、§4.7（280–283）、§4.9（304–316）、§5.3（343）、§12（567、570–572）；ADR 0018 D3；ADR 0019 D5、D6 | RE4；`B/application/history/compare.py:106-121`；`B/http/orchestration/preview_acceptance.py:98`；`B/application/preview_jobs.py:1227-1230` | 死锁已解除；对照表与审核 §7.2 要求的三个测试 owner 到位。Ruleset §5 末句与 DC11 的冲突没有处理，Submit 边界用词不一致，Preview 的捕获时点未定义（RR-F2）。“四项定义”的判断见 §4.1 |
| F2 | 已关闭（文档） | 设计 §4.1（133–171）、§4.2（173–198）、§5.2（336）、§12（561–562）、§14 第 1 项（601）；ADR 0018 D1、D6 与 Required Verification | RE5；`B/capabilities/storage_projection/project.py:513-521`（伪 gid）；`vnext/repository_service/src/gateway_repository_service/arrow_mapping.py:356-367`（SET） | 定义可测试，integration owner 已列入 S2a，待 S2a 证明。ordered `no` 的可空性见 RR-N5 |
| F3 | 已关闭（文档） | 设计 §3（127）、§4.3（200–206）、§4.8（285–302）、§10（530–531）、§12（574–575）；ADR 0018 D2；执行计划 S2b 第 2–3 项 | RE6；`vnext/repository_service/src/gateway_repository_service/versioned_import/verification.py:263-311`；`B/application/submission/contracts.py:255-311` | 入口 owner、签名、Attempt 字段与指纹组成已给出；删表三种情形有 owner。待 S2b 验证；owner 所在模块的 marker 见 RR-N4 |
| F4 | 部分关闭 | 附录 A（611–629）、附录 B（631–687）；Entry Brief §5（117–127）；设计 §11 | 逐字核对上游原文（§6.9） | 候选文本、owner 与接受时点基本齐备。B.2 缺 §5（RR-F2）；B.4 缺 Contract Taxonomy §4.4、§4.6，两处插入点在句中（RR-F6） |
| F5 | 已关闭（文档） | 设计 §4.4（208–245）；附录 B.1（641–643）；ADR 0018 D4；Entry Brief §2（67） | RE4；`B/capabilities/table_rules/contracts.py:657-667`（ordered `no` 的例外分支，实施时删除） | 与 Canonical Storage §2 一致，受影响规则与 digest 变化已列出。待 S2a |
| F6 | 已关闭 | 设计 §4.2（189）、§8（489）、§14（609）；ADR 0018 D6；执行计划 S3 | RE5；`B/capabilities/snapshot_materialization/compose.py:88`；`legacy/backend_vnext/capabilities/composite_signal/materializer.py:80-89` | S3 验收含真实 Dolt 导入 |
| F7 | 部分关闭 | 设计 §4.2（175–198）、§12（585）、§13；执行计划 S1 kickoff 第 4–5 项（64–74）、S2b 验收（157–158） | `B/capabilities/storage_projection/project.py:500-511`；`B/capabilities/snapshot_materialization/sql_declared_types.py:18-20` | 文档部分到位（词表、失败类别、DC14 形态、普查与真实数据验收）。数据证据待 S1 kickoff 普查与 S2b，符合“S2 语义验收前关闭”的时点 |
| F8 | 部分关闭 | 设计 §4.4（239–250）；ADR 0018 D5；执行计划 S2a 验收（120） | — | 文档部分到位，事实形态待 S2a 按 legacy oracle 冻结。与 schema-only 变化的交叉见 RR-N1 |
| F9 | 已关闭（文档） | 设计 §5.1（323）、§6（396）、§7.2（420–421）；附录 A 第 1 项；ADR 0019 D2、ADR 0020 D2、ADR 0021 D3；执行计划 S2b 第 1、7 项与 compose 验收（155） | RE5；`vnext/backend/tests/support/compose_gate_harness.py:1198-1245` | 四处表述一致；与 Business Lifecycle §1A.2、5D §6 不冲突（§6.6）。插入点见 RR-F6 |
| F10 | 部分关闭 | 设计 §9（492–514）；执行计划 S1 验收（81–94）、§3（201–357） | RE2、RE3、RE7 | 审核列出的各项（A2 移入 Application、计数、codec 合并移至 S2a、改名条目、S2 路径、DC9 清单）均已处理。新发现 RR-F4、RR-F5 |
| F11 | 已关闭（文档） | 设计 §4.1（156–165）、§4.5（256–257）、§5.3（341–344）、§12（563）；ADR 0018 Required Verification；ADR 0019 D5 | `B/capabilities/snapshot_materialization/_digest.py:74-91`、`114-127`、`156-170` | 定义与共享参数表 owner 已给出。存储身份判据与命名见 RR-N2；与角色表的交叉见 RR-N1 |
| N1 | 部分关闭 | 设计 §7.5（438–440）、§7.6（444–472）、§12（579）；ADR 0020 D5、D8；执行计划 S4（178–188） | `B/application/submission/accept.py:74-76`、`142-160` | 实施必达的输入边界（数量、重复、枚举、digest 格式、理由长度 → 422）已写入设计与验收；错误码、摘要组成、FULL 混合旅程与不采用项均已写明。判定顺序把重放放在权限之前（RR-F1） |
| N2 | 已关闭 | 设计 §3（125）、§6（398）、§7.4（434）；ADR 0020 D3、D7；ADR 0021 D3 | — | surface 使用自有中性类型；Application 传入两侧 `table_artifacts` |
| N3 | 部分关闭 | 设计 §5.1（324–327）；ADR 0019 D1 与 Required Verification（75） | — | 要求已写入设计与 ADR，但 §12 没有 owner，执行计划 S2b 没有验收项（RR-F3） |
| N4 | 已关闭 | 设计 §4.4（247–248） | `B/capabilities/comparison/standard.py:733-742` | 表状态与新增、删除行记录已定义。修改行记录中排除列是否展示前后值没有写明，可在 S2a 冻结事实形态时补上 |
| N5 | 已关闭 | 设计 §2.1 R3、R4（86–87）；§4.3（204） | `B/capabilities/snapshot_materialization/__init__.py:5`、`159` | `publish_snapshot_table_artifact` 确为 facade 导出 |
| N6 | 已关闭 | 设计 §1 兼容性（74–76）、§10、§12（582）；执行计划 §1、§2 | — | S2 已拆分；migration owner 按表归属；新增列允许旧行为空，环境在 S2b 前重建 |

### 4.1 F1：“全序、可取回、回滚、三节点”是否仍需要

审核报告 §7.2 的关闭标准要求写明规则取法、全序与取回方式。结合 DC10 逐项判断：

- **全序：不再需要。** 比较只取运行期规则；DC11 的陈旧判定与恢复判定都只比较 digest 是否相等，不需要先后关系。但
  §7.2 第 1 项同时指出的“读取历史 manifest 时版本校验写死”并不随之消失。DC10 仍要读取旧 commit 的 manifest，作为
  provenance 与存储身份的来源；而 `CanonicalizationManifest.__post_init__` 把 contract、storage projection 与 ruleset 的
  版本固定为当前常量（`vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py:290-298`）。见 RR-N3。
- **可取回：不再需要。** 运行期规则始终在程序内，不需要按 digest 取回或持久化历史规则集。
- **回滚：不再需要单独定义。** 回滚后运行期规则就是回滚后的规则，上传侧投影、比较与 Submit 写入都用它，激活前完成的
  Preview 在受理时被拒。但 Ruleset §5 末句对回滚场景的表述与 DC11 冲突，见 RR-F2。
- **三节点：已定义。** 设计 §4.7 第 3 条（282）规定整份结果使用同一运行期规则集。

### 4.2 传播完整性与 r1 残留

- DC10–DC22 的落点与处置表 §4 一致。抽查了 DC10、DC11、DC13、DC14、DC16–DC20 在设计正文、附录、执行计划、ADR、Entry Brief
  与 P5 §2A.4.1 中的表述，没有发现互相矛盾之处（RR-F2 所述 §5 问题除外）。
- r1 残留：
  - `RULESET_BINDING_MISMATCH` 只在设计 §4.5（255）以“删除 r1 的”形式出现；
  - “两侧规则集 digest 相等”只在 ADR 0018 Context（23）与 Alternatives（65）作为被放弃的方案出现；
  - `TEXT` 主键只在历史说明中出现，设计 §14（609）明确不再是停止条件；
  - 未拆分的“S2”只在执行计划 §1（36）作为 S2a、S2b 的统称出现；
  - INITIAL 的表述统一为“恒为空、物化时断言、以零表 `before` 传入”（设计 §4.6 第 264 行、§5.1、§6、§7.2；ADR 0019–0021；
    附录 A 第 1 项）。

  没有发现与 r2 决议冲突的残留。
- 不一致之处：设计 §11、ADR 0018 Consequences 与附录 B 对 R4 §4.2 的处理不同（RR-F6）；ADR 0019 D5 对现行实现的描述
  不准（RR-N5）。

## 5. 新 findings

| ID | 类别 | 阻塞 | 标题 |
| --- | --- | --- | --- |
| RR-F1 | 已证实缺陷 | 是 | 受理判定顺序把 same-key 重放放在权限与 scope 之前 |
| RR-F2 | 已证实缺陷 | 是 | 附录 B.2 没有覆盖 Ruleset Activation §5 末句，Submit 的边界用词与设计不一致 |
| RR-F3 | 已证实缺陷 | 是 | N3 的实施必达条件没有测试 owner 与阶段验收；manifest digest 不符的处置未定义 |
| RR-F4 | 已证实缺陷 | 是 | S1 验收不能由 `import_rules` 机械兑现 |
| RR-F5 | 已证实缺陷 | 是 | S2a/S2b 路径预算遗漏被删机制的使用方 |
| RR-F6 | 已证实缺陷 | 是（第 1 点） | 附录 A、B 不能按字面直接并入 |
| RR-N1 | 非阻塞建议 | 否（S2a 冻结前） | 只存不比的表与 schema 事实的交叉未写明 |
| RR-N2 | 非阻塞建议 | 否（S2a 冻结对齐用例前） | “存储身份”的判据与命名 |
| RR-N3 | 待验证假设 | 否（S2b 前） | 历史 manifest 的解码被当前版本常量锁定 |
| RR-N4 | 非阻塞建议 | 否 | 删表 integration owner 所在模块是 unit 模块 |
| RR-N5 | 非阻塞建议 | 否 | 表述精度与小缺口 |

### 5.1 阻塞项

#### RR-F1 受理判定顺序把 same-key 重放放在权限与 scope 之前

- **类别**：已证实缺陷（基础授权边界）；阻塞。
- **位置**：设计 §7.6 判定顺序（460–469 行）；ADR 0020 Decision 5 第 3 点（40 行）。
- **依据（已证实）**：
  - r2 规定“1. same-key 重放（E，先于全部业务校验）；2. scope 与权限；……”。
  - 现行实现的顺序相反：
    - `validate_accept_submit` 先校验权限，再解析 scope，然后才检查重放
      （`vnext/backend/src/gateway_backend/application/submission/accept.py:74-76`）；
    - 重放函数先核对 workspace 的精确 scope 与 Repository 映射，再查幂等记录（同文件 `142-160`）；
    - HTTP 编排同样先校验权限（`vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py:188-203`）；
    - T1 路径先重新解析 fresh scope，再查幂等记录（`accept.py:285-300`）。
  - [5D 设计](p5-5d-archive-design.md) §2 把“重放先验证当前授权，再用既有 Attempt”列为现有语义。`AGENTS.md` 与比例化政策
    把 API 认证授权和跨 scope 列为不能以比例化跳过的基础边界。
- **触发场景**：实现者按 ADR 0020 的顺序实现。已失去提交权限、或 scope 映射已经变化的调用方，携带原 workspace_id 与
  幂等键重放请求，得到原 Attempt 的结果。
- **影响**：授权检查被绕过，泄露 Attempt 与 Operation 信息。文中把该顺序标注为现行实现（E），会误导实现者与审核者。
- **最小修正方向**：两处都改为“1. 权限与 scope（含 workspace 精确 scope 与 Repository 映射）；2. same-key 重放；3. workspace、
  revision、preview 绑定与 CAS；……”，与现行实现一致。
- **关闭标准**：设计 §7.6 与 ADR 0020 D5 的顺序一致，且与现行实现相符；§12 身份确认行的 owner 覆盖“无权限或 scope 不符的
  重放被拒”，或写明由既有测试承担。

#### RR-F2 附录 B.2 没有覆盖 Ruleset Activation §5 末句，Submit 的边界用词与设计不一致

- **类别**：已证实缺陷（上游 Contract 文本冲突）；阻塞（附录 B 不能直接并入，F1 关闭标准中“与 Ruleset §1、§5 一致，或附上
  修订候选”未满足）。
- **位置**：附录 B.2（648–652 行）；设计 §4.9 末句（316 行，“Ruleset §5 …… 与本节一致，无需修订”）；ADR 0019 Consequences
  （70 行，只列 §1）；决议记录 DC10 第 55 行的同一表述保留为历史记录。
- **依据（已证实）**：
  - [Ruleset Activation](../contracts/ruleset-activation-and-migration.md) §5（67–69 行）：“ruleset rollback 只影响未来
    operation……；已捕获旧 snapshot 的 operation 继续使用原规则。”
  - DC11 与设计 §4.9 第 3 行：已受理的 Preview/History 在激活后恢复时稳定失败。回滚也是一次激活，须经 Ruleset §2 的 drain
    与重启，所以跨越激活的 operation 只能是恢复的 operation。
  - 并入 B.2 后，§1 的新增句要求这类 Preview/History 稳定失败，§5 末句仍要求它们继续使用原规则，Contract 自相矛盾。
    B.2 结尾“与 §5 一致”的断言也不成立。
  - B.2 写“带外部 effect 的 operation 跨越 effect 边界后，按冻结产物继续”。设计 §4.8、§4.9 与 DC11 规定 Submit 在 **T1
    之后**就按冻结产物继续。[Business Lifecycle](../contracts/business-lifecycle-and-state.md) §3（168 行）把 `PREPARED`
    定义为“尚未跨越可能产生 effect 的边界”，所以处于 PREPARED 的 Attempt 在 B.2 的文字下没有规定。
- **非阻塞的附带问题（捕获时点）**：History 在受理时冻结运行期 digest（§4.7），Preview 只在 materialize checkpoint 中记录
  （§4.6 第 266 行）。现行 Preview 受理只在 job payload 中冻结常量 `ruleset_version`
  （`vnext/backend/src/gateway_backend/http/orchestration/preview_acceptance.py:98`），执行时也只校验版本
  （`vnext/backend/src/gateway_backend/application/preview_jobs.py:1227-1230`）。因此，激活前受理、尚未开始 materialize 的
  Preview 恢复后会直接按新规则计算。这与 DC11“已受理的……不得静默改用运行期规则重算”以及 §4.9 第 3 行的字面不符。计算
  结果本身一致（全程使用新规则），没有业务损失，但需要写明。
- **触发场景**：S0 接受时按 B.2 并入 Ruleset Activation；此后的实现或审核引用 §5 末句，要求恢复的 History 继续使用受理时的
  规则。
- **影响**：接受后的 Contract 自相矛盾，S2a、S2b 的恢复语义没有唯一依据；PREPARED 状态的 Submit 没有规定。
- **最小修正方向**：
  1. B.2 同时给出 §5 末句的修订文本，例如“已捕获旧 snapshot 的带外部 effect operation 按冻结产物继续；纯计算 operation 按
     §1 稳定失败，由用户重跑”。同步改正设计 §4.9 末句，并在 ADR 0019 Consequences 中列出 §5。
  2. B.2 中 Submit 的边界改为“T1 冻结规范产物之后（含 PREPARED）”。
  3. 写明 B.2 收窄的是 §1 首句“运行期间不受后续 activation 影响”在恢复场景下的含义。
  4. （非阻塞）在 §4.6 定义 Preview 的捕获时点。建议在受理时把运行期规则集 digest 写入 job payload，与 History 一致，也与
     [P5 §6.1](p5-business-vertical-slices-design.md)（364–365 行，“Preview接受后……冻结……ruleset/contract versions”）一致。
     若改为在 materialize 开始时捕获，需 owner 确认这是对 DC11 字面的收窄（§8 O2）。
- **关闭标准**：按 B.2 并入后，Ruleset §1、§5 没有矛盾；设计 §4.9、ADR 0019 与 B.2 对 Submit 边界的用词一致；Preview 的捕获
  时点写入 §4.6，并由 `test_preview_job_worker.py` 覆盖。

#### RR-F3 N3 的实施必达条件没有测试 owner 与阶段验收；manifest digest 不符的处置未定义

- **类别**：已证实缺陷（基础边界缺验收）；阻塞。
- **位置**：设计 §5.1（324–327 行）、§12（557–587 行）；执行计划 S2b 验收（142–158 行）与 §3 S2b 测试预算（303–318 行）；
  ADR 0019 D1、Required Verification（75 行）；附录 B.3（659 行）。
- **依据（已证实）**：
  - 审核报告 §7.7 把 N3 升为实施必达条件，要求“写入修订后设计的验收”。设计 §5.1 与 ADR 0019 写明了要求，但：
    - §12 没有对应的唯一 owner；
    - S2b 验收列出的 owner 中没有它；
    - S2b 测试预算中没有针对新增 `sqlite_commit_metadata.py` 的测试文件。
  - 纵切指南 §4 要求验收回答“哪个唯一测试 owner 证明哪个业务不变量”。
  - 同一端口的 manifest digest 校验失败没有处置。§5.1 只写了“无法解析时稳定失败（`COMMIT_CANONICAL_METADATA_MISSING`）”。
    附录 B.3 把“与 Backend 持有的期望值（如 CanonicalizationManifest digest……）相矛盾的读回”列为 incident 范围，而 DC9
    删除后 History 已经没有 incident 机制。读取 manifest artifact 时 digest 不符，按 B.3 字面可能要求建 incident，按设计则
    没有规定。
- **触发场景**：S2b 实现 `CommitCanonicalMetadataPort` 时只测正常路径，跨 Repository、冻结 scope 之外或未登记的 commit 都没有
  测试；manifest 损坏时，实现者自行选择错误码与处置。
- **影响**：跨 scope 读取这一基础边界没有回归保护；digest 不符的处置在实现中漂移，或与 B.3 冲突。
- **最小修正方向**：
  1. §12 增加一行唯一 owner，例如为 control DB adapter 新增单元测试，用共享参数表覆盖：其他 Repository 的 commit、未登记的
     commit、冻结 scope 之外的 Submission、INITIAL 标记、manifest digest 不符。执行计划 S2b 的验收与测试预算同步列出。
  2. §5.1 写明 digest 不符时的稳定错误码与处置；B.3 写明其 incident 范围是否包括 Backend artifact store 的读回（建议与
     owner 确认，见 §8 O3）。
- **关闭标准**：§12、S2b 验收与测试预算三处一致列出该 owner；§5.1 与 B.3 对 digest 不符的处置一致。

#### RR-F4 S1 验收不能由 `import_rules` 机械兑现

- **类别**：已证实缺陷（执行计划）；阻塞（F10 的关闭标准是“S1 验收能由 import_rules 机械验证”）。
- **位置**：设计 §9 A6 行（500 行）；执行计划 S1 验收（81–91 行）、§3 S1 的 A6 预算（216–219 行）与测试预算（242–250 行）。
- **依据（已证实，RE3）**：
  - `vnext/backend/src/gateway_backend/compute.py:5` 导入 Rust 扩展 `gateway_compute`，import 规则把它归入 `ext:compute`
    区（`vnext/backend/tests/support/import_rules.py:46`）。capability 区只允许依赖其他 capability 与 artifacts（同文件 `83`）。
  - 在临时副本中只把 `compute.py`、`canonical_row_hash_ipc.py` 移入 `capabilities/canonical_row_hash/`：两条 unowned-root-module
    消失，同时新增 `('layer', 'gateway_backend.capabilities.canonical_row_hash.compute', 'gateway_compute')`。
  - S1 验收要求违例基线“只剩”三条（`http_arrow` 两条与 `repository_import_artifact`），并只允许改名带来的**不可达**条目替换。
    这条 layer 违例不在其中。基线规则要求新增条目在同一 diff 中给出理由并经评审（`vnext/backend/tests/architecture_baseline.py:6-7`）。
  - 另外，`vnext/backend/tests/test_architecture.py:146-150` 与 `180-194` 按旧路径读取这两个文件，`85-86` 的禁止前缀表引用旧
    模块名。它们在 S1 已列入预算的 `test_architecture.py` 中，可以随迁移一起修改。
- **触发场景**：S1 按路径预算完成 A6 后运行 `python -m tests.support.import_rules`。
- **影响**：S1 阶段退出无法按所列条目签署。实施者只能临时扩充基线或修改规则，而这需要事先决定。
- **最小修正方向**（择一，由作者或 Backend Architecture owner 决定，见 §8 O4）：
  1. import 规则显式允许 `capability:canonical_row_hash → ext:compute`（ADR 0001 下 capability 自有 Rust provider 的做法），
     把 `tests/support/import_rules.py` 列入 S1 预算，并在规则形态参数表中加一行；
  2. Rust 绑定不进入 capability，作为由 composition 选择的 provider 放在 infrastructure，只把契约与 IPC 编解码移入 capability；
  3. 保留该违例，在 S1 验收中列为第四条已登记条目（Phase 6 延期），并在同一 diff 给出理由。
- **关闭标准**：S1 验收列出的违例、运行时环与不可达条目，与按预算完成迁移后 `import_rules` 的输出一致。修订时可以用 RE3
  的方法模拟核对。

#### RR-F5 S2a/S2b 路径预算遗漏被删机制的使用方

- **类别**：已证实缺陷（执行计划）；阻塞（F10 的关闭标准包括“S2 预算覆盖”；按预算执行，S2a 的 compose 门禁无法运行）。
- **位置**：执行计划 §3 S2a（253–280 行）、S2b（282–320 行）；S2a 验收（123–124 行）。
- **依据（已证实，RE7）**：
  - **S2a 测试预算缺 compose 文件。** S2a 删除 `_table_policies_from_checkpoint`（S2a 第 6 项），并删除 comparison 的流程词汇
    `bind_pair_input`、`PairViewKind`、`PairRole`、`TrustedFlowApplicabilityBinding`（S2a 第 4 项）。它们的使用方有：
    - `vnext/backend/tests/test_history_compose_e2e.py:15`、`254-265`，以及 `vnext/backend/tests/test_ordered_compare_compose.py:13`、
      `154-157`：模块级导入 `_table_policies_from_checkpoint`，并读取 checkpoint 中的 `table_policies`；
    - `vnext/backend/tests/support/compose_gate_harness.py:849-875`、`913-957`：History oracle 脚本使用上述全部符号。

    这三个文件只列在 S2b 预算中，而 S2a 验收要求在阶段末“运行既有 compose 旅程”。按预算执行，两个 compose 模块在收集阶段
    就会 ImportError。
  - **S2a 测试预算缺 `test_architecture.py`。** S2a 让 comparison 依赖 table_rules（`ComparisonRuleSet`），而 capability DAG
    中 comparison 的上游仍是 `{comparison_projection, snapshot_materialization}`（`vnext/backend/tests/test_architecture.py:70`）。
    S1 预算只写了“删除两个占位 owner 与对应 DAG 边”。ADR 0021 Required Verification 要求的架构检查也在 S2a 范围内。
  - **S2b 生产预算缺两个文件。** DC9 删除在 S2b 执行，但以下路径不在 S2b 预算中：
    - `vnext/backend/src/gateway_backend/application/history/compare.py:137-141`：受理阻断（`has_pending_integrity_for_commit`
      → `HistoryIntegrityUnresolved`）；
    - `vnext/backend/src/gateway_backend/http/orchestration/history_compare.py:37`、`56`、`248-252`、`271`、`347-350`：integrity
      incident 的 DTO 读取与错误映射。S1 要求 HTTP DTO 不变，所以这些代码会保留到 S2b。
  - **条件项**（取决于实施方式）：
    - `vnext/backend/tests/support/http_workspace_harness.py:976` 与 `vnext/backend/tests/support/http_shutdown_harness.py:230`
      用 `table_ruleset_version` 构造 HTTP 依赖，S2a 改为注入运行期规则集 digest 后需要修改；
    - 若 S2b 给 `PreviewResult`、`SubmitAttempt` 增加必填字段，直接构造它们的测试也要修改：`test_sqlite_submit_repository.py`、
      `test_submit_domain.py`、`test_workspace_domain.py`、`test_preview_read_http.py`。
- **影响**：S2a 无法按预算完成阶段门禁；S2b 的删除不完整，或需要临时扩预算。
- **最小修正方向**：把上述文件分别列入 S2a、S2b 的必改或条件预算；S2a 的 compose 验收写明 History oracle 随入口改写一起更新。
- **关闭标准**：对被删符号重新 grep，所有使用方都落在对应阶段的预算中。

#### RR-F6 附录 A、B 不能按字面直接并入

- **类别**：已证实缺陷（上游候选文本不完整）。第 1 点阻塞，其余非阻塞。
- **位置**：附录 A 第 1 项（615–616 行）、附录 B.1（645 行）、B.3（654–661 行）、B.4（663–671 行）、B.5（675 行）、B.6（681 行）、
  附录 B 末段（686–687 行）；设计 §11（546 行）；ADR 0018 Consequences（75 行）。
- **依据（已证实）**：
  1. **B.4 有遗漏。** 删除 comparison projection 之后，[Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md)
     仍有三处把它当作现行 owner：§4.4 的允许依赖方向（188–197 行，含 `-> comparison_projection`）、§4.6 的 artifact 内容
     owner 表（266 行，“Comparison projection table | Comparison Projection capability”）、§13 第 9 项（654 行）。B.4 只修订
     §5。P5 §2A.4 的对应行（191 行）要求同步“总纲/ownership”。
  2. **插入点在句中。**
     - 附录 A 第 1 项要插在“Repository provisioning/initial commit 的真实性仍由既有 owner 负责”之后。原文此处以逗号接
       “不得靠 Archive 创建 commit 或猜测 main 来补归属。”（Business Lifecycle 89–90 行）。
     - B.3 要插在“权威事实问题必须创建 durable `RepositoryIntegrityIncident`（或等价 control record）”之后。原文此处以
       “，至少保存：”接字段清单（[Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md) 60–73 行）。

     按字面插入会截断原句。
  3. **只有指令，没有替换文本。** B.6 对 [Architecture](../architecture/architecture-and-refactoring-plan.md) §7.1 只写
     “删除 comparison_projection”，没有给出新的依赖图（原图 350–362 行）。B.5 对 P5 §2A.2 只写“撤销”，没有说明同一句后半
     “5D/5E 若需要增加流程分支……”（146–148 行）是否保留。
  4. **R4 §4.2 的处理不一致。** 设计 §11 写“R4 设计 §4.2 追加 `compare_excluded_columns` 与 ordered `no` 的处置”；ADR 0018
     Consequences 称其候选文本在附录 B；而附录 B 末段规定 P3-R4 §4.2 只加“取代”标注、不改写正文，也没有候选文本。
  5. （非阻塞）B.1 把 Canonical Storage 升至 3.1.0，但没有说明 `CanonicalizationManifest.contract_version` 是否随之变化；
     该值现为常量 `"3.0.0"`（`vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py:40`）。另外，
     “storage projection version 不变（列策略、键与 canonical bytes 不变）”在 DC12 触发时不再成立：JSON 改以 LONGTEXT 存储
     会改变规范类型。按 [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md) §8（234 行），需要说明
     版本轴如何处理。
- **最小修正方向**：
  - B.4 增加 §4.4、§4.6 的候选文本，并给 §13 第 9 项加“取代”标注；
  - 附录 A 第 1 项与 B.3 改为以整句或整段为插入点（B.3 放在字段清单之后）；
  - B.5、B.6 给出替换文本；
  - 统一设计 §11、ADR 0018 与附录 B 对 R4 §4.2 的处理；
  - B.1 补充 manifest contract_version 的说明，以及 DC12 触发时的版本说明（见 §8 O5）。
- **关闭标准**：附录 A、B 的每一项都能按字面并入；并入后，上游文档中不再有与 ADR 0018–0021 冲突的现行表述。

### 5.2 非阻塞项

#### RR-N1 只存不比的表与 schema 事实的交叉未写明

- **类别**：非阻塞建议；在 S2a 冻结事实形态前关闭（与 F8 同一时点）。
- **位置**：设计 §4.4 角色表（239–245 行）与 247–248 行、§4.5（257 行）、§12（563、566 行）；DC16。
- **依据**：
  - §4.5 一般性地规定，两侧内容相同但 schema 不同时产出 schema 事实，不得显示为 UNCHANGED。角色表对 SNAPSHOT_ONLY 与
    BROWSE_ONLY 只规定“行数或 `raw_content_digest` 不同时”产出表级内容事实，没有提 schema。
  - 规范状态摘要包含 schema，所以这两类表只改 schema 时允许提交。若实现只按角色表理解，Preview 与 Review 都看不到这一
    变化，而这正是 F8、F11 要消除的情形。`test_canonical_state_identity.py` 的参数表没有角色维度。
  - 只有 compare-excluded 列变化时，表状态为 UNCHANGED 而允许提交（247–248 行）。pair 与 Preview 的摘要层面是否显示为
    “有变化”，没有写明。
- **建议**：
  - 角色表写明 schema 事实适用于所有存储角色，或把 DC16 事实的触发条件扩展到规范 schema digest；
  - F11 的参数表加入角色维度；
  - 写明表级内容事实会使 pair 摘要显示为有变化。

#### RR-N2 “存储身份”的判据与命名

- **类别**：非阻塞建议；在 S2a 冻结 `test_comparison_planning.py` 的对齐用例前关闭。
- **位置**：设计 §4.1（148–151、158 行）、§4.5（255 行）；ADR 0018 D3。
- **依据**：
  - §4.1 以“`storage_projection_version` 与逐表 canonical schema digest”作为存储身份，并要求判断某侧的存储身份与“运行期规则集
    推导出的存储视图”是否不同。但规范 schema 取决于源 schema，仅凭运行期规则推导不出旧 commit 应有的 schema digest。
    schema digest 不同，也可能只是源 schema 变了；Canonical Storage §7（222 行）区分了
    `SOURCE_SCHEMA | STORAGE_PROJECTION_POLICY | BOTH`。
  - manifest 的每表记录中已有可比较的规则侧事实：key policy、ordered policy、retained/structural/dropped 列与 canonical key
    （`vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py:226-241`）。`compute_storage_rule_digest`
    也已存在，但没有写入 manifest（`vnext/backend/src/gateway_backend/capabilities/storage_projection/_digest.py:65-77`）。
  - 名称冲突：manifest 已有字段 `canonical_schema_digest`，按 Canonical Storage §4（105–107 行）列保持 DDL 顺序；r2 新定义的
    canonical schema digest 按列名排序。两者同名，实现者可能直接把 manifest 字段用于状态摘要，与 DC13 冲突。
- **建议**：
  - 存储身份改用规则侧事实（例如把运行期规则应用到旧 commit 的规范 descriptor，比较键、丢弃列与 ordered policy），或把
    逐表 storage rule digest 写入 manifest；
  - 新 digest 换一个名字（例如 business schema digest），并写明 manifest 的 `canonical_schema_digest` 语义不变、不进入状态摘要；
  - 写明 vNext 比较没有 native diff 路径，所有比较都按列名与有效键对齐，因此始终满足 Canonical Storage §7 在版本不同时的要求。

#### RR-N3 历史 manifest 的解码被当前版本常量锁定

- **类别**：待验证假设（代码事实已证实，触发取决于将来是否升版）；非阻塞；在 S2b 前关闭。
- **位置**：设计 §5.1（326 行）；ADR 0019 D1；DC10“ruleset id、version、digest 只用于 provenance 与存储身份判定”。
- **依据**：
  - `CanonicalizationManifest.__post_init__` 要求 `contract_version == "3.0.0"`、`storage_projection_version == "1"`、
    `ruleset_version == "v2"`（`vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py:290-298`）；
  - table_rules 同样把 `RULESET_VERSION` 固定为 `"v2"`
    （`vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py:24`、`432-433`）。
- **触发场景**：将来任一次修改这些常量之后（例如规则集升版，或 B.1 之后修改 manifest 的 contract_version），
  `CommitCanonicalMetadataPort` 无法解码旧 commit 的 manifest。所有以旧 Submission 为基线的 Preview，以及涉及旧节点的
  History 都会失败，重新出现 F1 的死锁形态。
- **建议**：设计写明 provenance 解码接受历史版本，或写明激活只改变 digest、不改变这些版本；ADDITIVE 激活的用例同时覆盖
  “旧 manifest 的 version 与运行期不同”。

#### RR-N4 删表 integration owner 所在模块是 unit 模块

- **类别**：非阻塞建议。
- **位置**：设计 §12（575 行）；执行计划 S2b 验收（146 行）。
- **依据**：`vnext/backend/tests/test_submit_job_prepare.py:62` 是模块级 `pytestmark = pytest.mark.unit`；Backend 的 conftest
  只给没有标注的测试补 unit（`vnext/backend/tests/conftest.py:27-36`）。在该模块中加入依赖真实 Repository 的用例，会同时
  带 unit 与 integration 标记而被 `-m unit` 选中，违反 AGENTS 的分类约束（移开 dolt 后 `-m unit` 会失败）。
- **建议**：放入 integration 模块（新建，或复用 `test_submit_job_effect.py` 这类模块级 integration 文件），或调整该模块的
  标记，并用“移开 dolt 再跑 `-m unit`”验证。

#### RR-N5 表述精度与小缺口

- ADR 0019 D5 说规范状态摘要“取代 `raw_state_digest` 作为 canonical business digest”。现行实现的 canonical business digest
  由 Preview bundle digest 派生（`vnext/backend/src/gateway_backend/application/submission/contracts.py:313-316`），
  `raw_state_digest` 是 r1 的提案。建议改为“取代现行由 bundle digest 派生的值（以及 r1 提议的 `raw_state_digest`）”。
- ordered 表的 `no`：Canonical Storage §3 规定为 `INT NOT NULL`（67 行），现行投影只把 gid 强制为 NOT NULL，`no` 沿用源的
  可空性（`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:518`、`558`）。§4.1 的 descriptor 定义
  可以一并写明 `no` 的可空性。
- 身份确认理由按“去除首尾空白后 1–1000 字符”约束，现有 Archive 理由按 1–4096 UTF-8 字节校验
  （`vnext/backend/src/gateway_backend/application/archive/contracts.py:26-27`、`58-66`），Archive 的身份异常处置沿用后者。
  建议统一计量单位，并写明持久化的是原文还是去除空白后的文本。
- DC11 的依据写“只有 drain 超时或崩溃时才会遇到这种情况”。但 Operation Lifecycle §1（25–26 行）允许 drain 时 checkpoint
  后由 durable runtime 接管，所以受理后仍在排队或已 checkpoint 的 Preview/History，在激活后都会稳定失败。这不改变决议，
  但会影响对用户影响面的预期，可以在 runbook 中说明。

## 6. 专项复核结论

### 6.1 运行期规则集与 Ruleset Activation §1、附录 B.2

- **不冲突的部分。** 激活必须经过 drain 与重启（Ruleset §2），在一个进程生命周期内，“运行期规则”就是启动时捕获的规则，
  DC10 与 §1 首句一致。只有恢复的 operation 会跨越激活。B.2 为它们增加规则：纯计算 operation 稳定失败，Submit 按冻结产物
  继续。这一立场本身自洽，也消除了现行实现中 Preview 只校验版本常量、恢复后可能混用新旧规则的风险
  （`vnext/backend/src/gateway_backend/application/preview_jobs.py:1227-1230`）。
- **问题。** §5 末句、Submit 的边界用词与 Preview 的捕获时点，见 RR-F2。
- **附带说明。** History 受理的指纹包含规则版本，激活后以同一个 key 重放会返回 409
  （`vnext/backend/src/gateway_backend/application/history/compare.py:106-121`）。r2 改用 digest 后，用户重跑需要使用新的
  幂等键，可以在错误说明中写明。

### 6.2 T1 冻结与 evidence-first 恢复、请求指纹、same-key 重放、保护转移

- **闭合。**
  - 现行指纹已经包含服务端派生的绑定值（快照表 ref、ready closure、expected commit 等），重放时由 Attempt 的冻结字段重算
    （`vnext/backend/src/gateway_backend/application/submission/contracts.py:255-311`，重放计算在同文件后续的
    `compute_replay_accept_fingerprint`）。r2 把闭包与 manifest 的 ref/digest 冻结进 Attempt 并纳入指纹，沿用同一模式。
  - prepare 的全部输入（冻结闭包、manifest、冻结 expected parent 的表目录）都不可变。包只构建一次并写入 checkpoint，T2 的
    请求证据与 T3 的核对（Canonical Storage §6、§9）都不受影响。
  - manifest 在 Preview 阶段发布，T1 转移给 Attempt，finalize 时由 `canonicalization-manifest` owner 长期保护
    （`vnext/backend/src/gateway_backend/application/submission/finalize_transaction.py:226-265`），满足 Canonical Storage §4
    “临时 package 可能被删除前 durable 保存”（96–97 行）。
- **保护转移范围变窄。** 现行实现在 T1 把 Preview 持有的全部 artifact 转给 Attempt
  （`vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py:107-163`、
  `vnext/backend/src/gateway_backend/application/submission/accept_transaction.py:321-335`）；r2 只转移闭包、闭包 artifact、
  manifest、source 与 ready closure（设计 §4.8、§10）。这与 Canonical Storage §5 和 P5 §9 的“Attempt 需要的”一致，其余
  Preview artifact 在 T1 而不是 finalize 时解除 pin。submit job 只把 ready closure ref 作为绑定值核对
  （`vnext/backend/src/gateway_backend/application/submit_jobs.py:2128`），没有发现 T1 之后的读取方。建议 §4.8 写明这一变化。

### 6.3 prepare 的 `removed_tables`

- **不改 Repository 即可通过回放与 STRUCTURAL 校验。**
  - Repository 在私有分支上用 `dolt sql` 执行 replay，不做语句级校验
    （`vnext/repository_service/src/gateway_repository_service/versioned_import/provider.py:134-151`、
    `vnext/repository_service/src/gateway_repository_service/candidate_a/dolt_cli.py:452-458`）；
  - 提交前 `add --all` 会暂存删表（`provider.py:163`）；
  - STRUCTURAL 比较候选的用户表集合、表名顺序、行数、主键与逐列定义是否与 manifest 相同
    （`vnext/repository_service/src/gateway_repository_service/versioned_import/verification.py:263-311`）；
  - manifest 只列上传的表，replay 对 `removed_tables` 只做 DROP（渲染入口在
    `vnext/backend/src/gateway_backend/capabilities/storage_projection/import_replay.py:36-40`、`83-93` 的基础上扩展），二者一致。

  RE6 在 Dolt 上复现了“用户删表”与“sibling 新增表”同时出现的情形。
- **与 CAS、重试、sibling 情形闭合。**
  - `removed_tables` 由冻结的 expected parent（不可变 commit）确定性推导，随包写入 checkpoint，重试时复用。
  - 同一 Repository 同时只有一个活跃 Attempt：occupancy 表以 `repository_id` 为主键
    （`vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py:890-895`），CAS 保证提交时 main 仍是该 parent。
  - 业务基线 ≠ main 时，Preview 仍按业务基线展示，sibling 新增的表在新 commit 中被删除，这是 DC18 明示的结果。sibling 只在
    未归档时存在；一旦某个 sibling 归档，其余 sibling 按 Business Lifecycle §5 关闭，因此不构成未被认识的业务损失。
- **只读 catalog。** `get_versioned_catalog(repository_id, commit_id)` 已存在
  （`vnext/repository_client/src/gateway_repository_client/client.py:306-336`），没有 wire 变化。该接口会返回每表行数，而
  prepare 只需要表名；大库上多出的计数开销可以在设计 §13 的测量中关注。

### 6.4 规范状态摘要与 `NO_CANONICAL_CHANGE`

- 与 Canonical Storage §5（141–145 行）、§9（239 行）和 Business Lifecycle §3（156–158 行）一致：比较对象仍是“Preview 的
  canonical business digest 与当前业务 base”。只改被丢弃列时，规范 schema、行数与内容摘要都不变，得到
  `NO_CANONICAL_CHANGE`。附录 A 第 3 项给出了定义。
- 与 Canonical Storage §4 中 manifest 每表 schema digest（按 DDL 列序）属于不同的语义域，二者不冲突；命名风险见 RR-N2。
- 旧行缺少摘要时按 derived-stale 拒绝（设计 §1 兼容性），不会被误判为无变化。

### 6.5 只有 compare-excluded 列变化

自洽。表状态 UNCHANGED 表示参与比较的值没有变化；表级内容事实表示存储内容变了；状态摘要包含这些列，所以允许提交，
Review 可见（DC16）。现有规则中只有 composite 表的两列会成为 compare-excluded（S3）。摘要层面的显示与修改行记录的形态，
见 RR-N1 与 §4 的 N4 说明。

### 6.6 INITIAL 恒为空

- **与 Business Lifecycle §1A.2 不冲突。** §1A.2 把 initial commit 的真实性交给 provisioning owner，附录 A 第 1 项补充“必须为空、
  物化时断言”。[P5 §4](p5-business-vertical-slices-design.md)（302–303 行）本来就规定 provisioning 创建 initial empty commit，
  并登记 explicit-empty 的基线。
- **与 5D 设计 §6 不冲突。** v4→v5 迁移与 seed 只登记已 provision 的 initial 身份，不校验 Repository 内容（5D 设计 340–354、
  356–383 行）。DC17 的断言在物化时生效，是补充而不是替代。
- **代价。** 误供给要到首个 Preview（或涉及 INITIAL 节点的 History）才暴露，而 INITIAL 节点不能修改；恢复方式是按 §1A.1 把
  scope 改绑到新的 Repository。这一代价可以接受，建议在运维说明中写明。
- compose harness 的 schema-seeded 种子（`vnext/backend/tests/support/compose_gate_harness.py:1198-1245`）在 S2b 改为空提交，
  已列入预算。附录 A 第 1 项的插入点见 RR-F6。

### 6.7 附录 B.3

- **只收窄 incident 的适用范围。**
  - Submit 中 Repository 返回值与 T1、checkpoint 的矛盾，仍然进入人工恢复终态
    （`vnext/backend/src/gateway_backend/application/submit_jobs.py:874-880`），即 Operation Lifecycle §4 所说的“等价 control
    record”，不受影响；
  - ADR 0016 的 Operation integrity 不受影响（设计 §5.5 第 374 行）。
- **没有削弱对权威事实的实际保护。** 被删除的 History integrity 检查，依赖从行重建的 hidden summary（R4），本质是同一数据读
  两次再比较，并不能保护权威事实。实质收窄只有一处：Repository 内部读取不一致（行数不符）改为普通失败。这是 DC19 的决定，
  ADR 0019 保留了重开条件。
- 缺口：manifest digest 不符的处置（RR-F3）、插入点（RR-F6）。§3 的“先处理 integrity incident”按 §4 的范围理解、不改原文，
  可以接受。

### 6.8 S2a 结束时的中间状态

- **可以接受，前提是：**
  - 阶段之间不对外发布（执行计划 114 行已写明）；
  - S2a 的门禁由能力层 owner 与 History（两侧都来自 Repository）承担，不以 Preview 在非空基线上的结果作为验收依据；
  - handoff 记录 Preview 的变化。
- **需要注意。** S2a 在 Preview 中启用角色语义，并要求提前退出时 schema digest 相等。原始上传侧与规范基线侧的差异（R1）可能以
  新的 schema 事实出现，而不只是“R1 仍存在”。执行计划 S2a 验收中的“既有 compose 旅程预期结果不变”，应理解为 History 与
  空基线旅程；非空基线上的 Preview 若有变化，按“在 handoff 说明原因”处理。
- S2a 的 compose 门禁需要先完成 RR-F5 的预算修正才能运行。

### 6.9 附录 A、B：引文、插入位置、版本号与并入

- **引文逐字核对。** 以下引文都与原文一致（原文跨行处按原文换行）：
  - 附录 A 第 1 项：Business Lifecycle 89 行；第 2 项：同文件 144 行；
  - B.1：Canonical Storage 37 行、50–52 行；
  - B.2：Ruleset Activation 20 行；
  - B.3：ADR 0016 28–29 行；Operation Lifecycle 60 行、53 行；
  - B.4：Contract Taxonomy 397、400、401、422–423 行；
  - B.5：P5 设计 146、375、188 行；
  - B.6：Architecture 709 行。
- **版本号正确。** Business Lifecycle 与 Canonical Storage 的现行版本都是 3.0.0（两文件第 11 行），升至 3.1.0 符合两者的版本规则。
- **能否直接并入。**
  - 可以直接并入：附录 A 第 2–6 项、B.1（除 RR-F6 第 5 点外）、B.4 已有的各项、B.5 第 2、3 项、B.6 第 2–4 项；
  - 需要先修改：附录 A 第 1 项与 B.3 的插入点、B.4 的遗漏、B.5 第 1 项、B.6 第 1 项（RR-F6），以及 B.2（RR-F2）。
- Architecture §9.1（491 行）“业务系统拥有……storage/comparison projection……语义”是描述性的归属清单，不修改也不产生冲突，
  可以顺带更新。

### 6.10 源码抽查

- **R1–R6 均成立。**
  - R1 已由审核实验 E1 复现。本复审核对了两侧的来源：上传侧 `_sql_request_from_bytes`
    （`vnext/backend/src/gateway_backend/application/preview_jobs.py:2014`），基线侧 `materialize_repository_ref`（同文件 `920-930`）。
  - R2：Preview 与 Submit 中没有 `table_policies`。
  - R3：预检中计算基线 digest（`vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py:225-247`）。
  - R4：以运行时常量从行重建 hidden summary（`vnext/backend/src/gateway_backend/infrastructure/repository_read/http_arrow.py:343-411`），
    随后再读一遍（`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/repository_ref.py:185`）。
  - R5：`optional_xml_document_ref` 与 `materialize_business_snapshot` 在所属 capability 之外没有使用方。
  - R6：`vnext/backend/src/gateway_backend/application/preview_jobs.py:1337-1340`。
- **E-a…E-i 均成立。**
  - E-a：`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:500-511`；
  - E-b：RE5；
  - E-c：`vnext/repository_service/src/gateway_repository_service/arrow_mapping.py:356-367`、
    `vnext/backend/src/gateway_backend/infrastructure/repository_read/http_arrow.py:297-305`、
    `vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/scalar_encoding.py:60-75`、`165-178`；
  - E-d：`project.py:513-521`、`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_digest.py:98-102`；
  - E-e：`_digest.py:74-91`、`114-127`、`156-170`；
  - E-f：`verification.py:263-311`、`import_replay.py:36-40`、`83-93`、`submit_acceptance.py:107-163`；
  - E-g：RE4、`vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py:657-667`；
  - E-h：`compose_gate_harness.py:1198-1245`；
  - E-i：`vnext/backend/src/gateway_backend/capabilities/mutation_planning/import_replay.py:68-120`、
    `vnext/backend/tests/test_architecture.py:68`、`75`。
- **S1 验收。** 逐条对照基线（RE2、RE3）：除 RR-F4 外，S1 所列修复都能移除对应条目。`parse_sql` 已由 table_access 的 facade
  导出，A8 不需要改动 table_access 的 facade。
- **路径预算。** 见 RR-F5。
- **测试 owner。** §12 列出的 25 个测试文件中，18 个现存，7 个（`test_canonical_snapshot_identity.py`、
  `test_canonical_state_identity.py`、`test_comparison_canonical_domain.py`、`test_table_rules_comparison_view.py`、
  `test_comparison_rule_roles.py`、`test_project_identity.py`、`test_comparison_replacement.py`）在执行计划中标为新增。每个
  不变量只有一个 owner；按入口或层次拆分的三行（恢复、身份确认、composite）各自证明不同的侧面，可以接受。缺 N3 的 owner
  （RR-F3）；删表 owner 的 marker 见 RR-N4。

### 6.11 比例化与基础边界

- **新机制都有明确的 consumer 与理由：**
  - `RepositoryParentCatalogPort` → prepare 推导 `removed_tables`（DC18）；
  - `CommitCanonicalMetadataPort` → Preview 基线侧与 History 节点的 `canonical_binding`；
  - 规范表集合闭包 → T1 冻结、prepare 输入与保护转移（F3）；
  - 身份确认 → AcceptSubmit、Review 只读展示与 Archive 处置（DC3）。

  它们都复用现有的事务、保护与异常处置机制，没有新增 broker、sidecar、证据状态机或兼容层。
- **基础边界：**
  - 输入上限（§7.6）完整；
  - 跨 scope 的要求写入了设计，但缺验收（RR-F3）；
  - 授权先于重放的顺序被倒置（RR-F1）；
  - CAS 与事务沿用现行实现，T1 内新增的校验都只读 control DB；
  - Repository 读取的响应大小沿用 client 的上限。
- 没有发现过度设计。

### 6.12 执行计划

- **阶段顺序合理。** S2a 作为 S2b 的门槛、S3 先于 S4，理由都成立。
- **S1“行为不变”可以兑现。** codec 合并已移至 S2a，A2 的受理逻辑移入 Application；验收清单需按 RR-F4 修正。synthetic job
  与 external effect 桩移出生产包后，worker 集成测试需要改为测试侧注入
  （`vnext/backend/src/gateway_backend/bootstrap/operation_worker.py:50`、`488-494`）。这属于设置变化，不是断言变化，在
  handoff 中说明即可。
- **镜像重建判定**（执行计划 §6）符合 AGENTS.md：每个阶段退出都重建，S5 fresh 重建；S1 kickoff 只做合入、复核与主机侧
  普查，不重建。
- **停止条件可操作。** 设计 §14 第 7 项是生产期的重开条件，不会在本收口的阶段内触发。
- **测试写法符合 AGENTS。** 纯规则、解析与投影测试不引入 Dolt；同构用例使用共享参数表（执行计划 §4）；integration owner 经真实
  Repository Service 访问 Dolt，其 DoltRunner 预置了离线配置。marker 问题见 RR-N4。普查脚本目录 `vnext/backend/benchmarks/`
  已存在。

## 7. 修订后通过时仍保留的实施前置条件

1. RR-F1–RR-F6 在 S0 再修订中关闭，并经复审确认；复审可以只核对差异。
2. 审核报告 §6 第 1–6 项继续有效：
   - P5-5E slice exit 为 pass 后才开始 S1，S1 kickoff 复核 E 级事实与基线漂移；
   - S0 接受时一并接受附录 A、B；
   - S1 kickoff 用 4 份真实 dump 完成普查，并按 DC12、DC15 落定类型处置；
   - S2b 门槛之前，真实 Dolt 同一性 owner 通过，F11 与 F3 有真实 Dolt 证据；
   - S3 验收之前，composite 键列类型经 Dolt 导入验证；
   - 各阶段记录镜像决策，最终候选 fresh 重建。
3. RR-N1、RR-N2 在 S2a 冻结事实形态与对齐用例之前关闭；RR-N3 在 S2b 之前关闭。
4. F7 在 S2b 语义验收前以真实数据关闭；F8 在 S2a 冻结前与 legacy oracle 核对。

## 8. 需要 owner 决定或确认的事项

以下事项影响上游 Contract 文本或 owner 决议的适用范围，本复审只给出建议，不作决定。

决议状态：repository owner 已于 2026-09-26 按下表建议对 O1–O5 作出决议，记录为 DC23–DC27，见
[S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md) §7。下表保留为复审时的建议与依据。

| # | 事项 | 建议 | 关联 | 确认时点 |
| --- | --- | --- | --- | --- |
| O1 | 修订 Ruleset Activation §5 末句。决议记录 DC10 称 §5 无需修订，但 DC11 需要它修订 | 随 B.2 一并修订：带外部 effect 的 operation 按冻结产物继续，纯计算 operation 按 §1 稳定失败 | RR-F2 | S0 再修订前 |
| O2 | Preview 规则集的捕获时点 | 受理时冻结运行期 digest，与 History、P5 §6.1 一致，这也是 DC11 的字面要求。若改为在 materialize 开始时捕获，需确认这是对 DC11 的收窄 | RR-F2 | S0 再修订前 |
| O3 | manifest digest 不符是否属于 B.3 的 incident 范围 | 不属于。B.3 的“与 Backend 期望值矛盾”限定为 Repository 返回值（例如 T3 回显的 manifest digest、expected parent）；Backend artifact 损坏按稳定失败处理，附诊断、日志与指标 | RR-F3、DC19 | S0 再修订前 |
| O4 | canonical row hash Rust 绑定的放置与 import 规则 | 由 Backend Architecture 在 RR-F4 的三个选项中择一。若修改 import 规则，属于对 P5 §2A.2 门禁的精确放行，需在同一 diff 中说明 | RR-F4 | S0 再修订前 |
| O5 | DC12 触发（JSON 改以 LONGTEXT 存储）时的版本轴 | DC6 下不需要兼容，但按 Canonical Storage §8，在 B.1 或 S2a handoff 中写明是否提升 storage projection version | RR-F6 第 5 点 | S1 kickoff 普查后 |

## 9. 链接与路径检查

提交前用脚本检查了本报告：

- 全部相对链接与锚点都能解析（按 GitHub 标题规则计算锚点，并识别显式 `<a id>`）。
- 反引号中以 `vnext/` 开头的路径在 worktree 中都存在；带行号的引用，行号都不超出文件长度。
- 以 `legacy/` 开头的路径在主工作区中存在，行号也不超出文件长度。
- 只写文件名的测试文件：§6.10 列出的 7 个新增文件按提案名书写，其余在 `vnext/backend/tests/` 中存在。

同一脚本对被复审的 11 个文件做了链接与锚点检查，结果为 0 个问题（RE8）。
