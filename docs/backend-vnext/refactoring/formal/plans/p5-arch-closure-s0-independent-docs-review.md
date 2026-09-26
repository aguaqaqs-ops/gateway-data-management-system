# P5 架构收口 S0 独立文档审核报告

- 状态：独立审核报告（docs-only）。本报告不接受 ADR、不修改 Contract 版本、不改变任何阶段状态，也不构成实现授权。
- 日期：2026-09-25
- 审核者：未参与本轮起草的独立 reviewer
- 审核依据：[纵切指南](../guides/slice-design-execution-and-review-guide.md) §5–§6、`AGENTS.md`、
  [testing-conventions](../../../testing-conventions.md)、
  [比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)
- 结论：**定向修订**
- 修订：2026-09-26 复核补充，内容包括 repository owner 对 F1 的新决定、真实数据安排，以及对另一份独立评审意见的核实与采纳，见 §7

## 1. 结论与判定理由

**定向修订。** 核心方向成立，且与 DC1–DC9 及多数上游 Contract 一致：

- 在规范域比较，规范快照有两个生产者；
- 以 Backend 持有的 manifest 作为 commit 规范元数据权威；
- comparison 去流程化；
- 项目身份的确认在 Submit 受理时收集。

R1–R6 的事实与 Entry Brief 的 readiness 表均回到源码核实成立。R1 已独立复现。导入基线的 54/8/16 条目都能映射到设计 §9 的某一行。

需要修订的问题集中在少数章节和接口：设计 §4.1–§4.4、§4.7、§5.1–§5.5、§8、§9 部分行，执行计划 S1 验收与路径预算，附录 A 及 ADR 0018/0019/0021 的对应条款。修订这些不需要重建核心模型和主执行路径，所以不判整体返工。但其中 8 项是接受前必须关闭的阻塞项（F1–F6、F9、F10），因此不能判通过。2026-09-26 复核新增阻塞项 F11，并补强 F1、F3、F4，阻塞项共 9 项，见 §7。

最关键的四项：

- **F1**：规则集绑定判据与 accepted 的 Ruleset Activation Contract 冲突。任何非破坏性规则激活后，所有已有业务基线都无法 Preview，Submit 因此死锁。
- **F2**：§4.1 的“规范快照同一性”只约束三类摘要，没有规定规范 descriptor 如何派生。实验已确认至少 SET、JSON、主键可空、列序、伪 gid 五类分歧。其中 JSON 的分歧来自 Dolt 存储规范化，仅修 Repository 解码不足以修正（2026-09-26 措辞修正，见 §7.6）。
- **F3**：Submit 复用 Preview 规范投影所需的 import 包渲染入口，与 capability DAG 冲突。T1 绑定仍依赖按 id 前缀和摘要的启发式。
- **F4**：Canonical Storage §2、Business Lifecycle §2 的 XML 条款、ADR 0016 / Operation Lifecycle §4 需要随本轮修订，但文档没有给出候选文本，或把修订排在实现之后。

## 2. 审核对象

```yaml
docs_branch: p5-arch-closure-docs
docs_worktree: /home/dev/gdds-p5-arch-closure-docs
docs_commit: 3e5d5807e546f920499bb36066fc299e04546706   # 含 8b46e793506667ba446b4b3d2492c450ed9bbef5
code_inspection_base: 217236980350d523101936af5464fbbd9ad66f88
vnext_diff_check: "git diff --stat 2172369803 3e5d5807e5 -- vnext" 输出为空（本轮开始前执行确认）
main_workspace_usage: 只读使用其 backend .venv 与 gitignored legacy/（仅作行为 oracle）
s4_drift: 不追踪（按任务约定由 S1 kickoff 复核）
```

被审核的 9 个文件：

- [Entry Brief](p5-arch-closure-s0-entry-brief.md)
- [详细设计](p5-arch-closure-design.md)
- [执行计划](p5-arch-closure-execution-plan.md)
- ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
  [0019](../adr/0019-commit-canonical-metadata-authority.md)、
  [0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
  [0021](../adr/0021-flow-neutral-comparison-entry.md)
- [P5 §2A.4.1 补充](p5-business-vertical-slices-design.md#p5-architecture-review-20260925)
- [formal README](../README.md) 索引项

下文带行号的源码路径均相对仓库根目录，行号以 `2172369803` 为准。§3.1 中不带 vnext 前缀的短路径相对于
`vnext/backend/src/gateway_backend/`（Repository Service 部分相对于 `vnext/repository_service/src/gateway_repository_service/`）。
以 legacy 开头的路径只存在于主工作区（gitignored）。

## 3. 实际核查与局限

### 3.1 只读核查范围

- Preview：`vnext/backend/src/gateway_backend/application/preview_jobs.py` 全部物化、组装与发布路径。
- Submit：
  - AcceptSubmit 预检与 T1（`http/orchestration/submit_acceptance.py`、`application/submission/accept.py`、`accept_transaction.py`）；
  - prepare 与 import 包构造（`application/submit_jobs.py`、`repository_import_artifact.py`、`capabilities/mutation_planning/import_replay.py`）；
  - finalize 的保护转移。
- History：`application/history/compare_jobs.py` 的物化、策略投影与 integrity 机制，相关端口、路由、DTO 与 migration v6。
- capability：
  - comparison（入口、规划、标准/ordered 算法、公共面 99 个导出）；
  - snapshot_materialization（SQL/Repository 两条物化路径、摘要、标量编码、compose）；
  - storage_projection（投影、codec、发布、import schema 渲染）；
  - table_rules（52 条规则）；
  - surface/risk/bundle 的替换与身份字段。
- Repository Service：`arrow_mapping.py`（SQL 类型 → Arrow）、versioned read 目录（`SHOW CREATE TABLE` 解析、`COUNT(*) AS OF`）、versioned import 流程与 STRUCTURAL 校验、create-repository。
- 供给与 compose harness：`infrastructure/control_db/sqlite_mapping.py`、`tests/support/compose_gate_harness.py`。
- 上游文档：任务列出的全部 Contract、设计与 ADR，另加 Operation Lifecycle and Repository Integrity §4、ADR 0016、ADR 0017、旧身份设计 oracle。
- legacy oracle（主工作区）：BROWSE_ONLY 语义、composite 派生表 DDL、导入标量类型支持。

### 3.2 实验

脚本放在审核者的临时目录，未入库。Python 实验按任务约定的 `PYTHONPATH` 方式用主工作区 backend venv 执行 worktree 源码。

| # | 实验 | 结果 |
| --- | --- | --- |
| E1 | R1 复现。规则取 `com_cfg`（EXPLICIT key `index`，ignored `no`）。原始侧是 SQL 表 `no, index, name`、`PRIMARY KEY(no)`，经 `_sql_request_from_bytes` / `_sql_materialization_request` 物化。规范侧用 `FakeRepositoryTableAccessProvider` 构造列 `index, name`、主键 `(index)`，行内容相同。按 Preview 方式调用 `bind_pair_input` / `plan_pair` / `compare_plan`，身份评估用 `_PreviewIdentityAssessment`（SAME_PROJECT） | FULL `baseline_to_initial` 与 MODIFIED_ONLY `initial_to_modified` 都是 pair `DEGRADED`，表诊断为 `CURRENT_ONLY_COLUMNS`、`EFFECTIVE_KEY_CHANGED`（current_only=`no`，key_before=`index`，key_current=`no`）。与设计 R1 一致 |
| E2 | 同一性探针：同一内容分别走 SQL 解析路径与 Repository 元组路径。Repository 侧用 fake provider，值形态按 `arrow_mapping.py` 经 `to_pylist()` 后的 Python 值构造 | INT+VARCHAR+NULL：三个摘要相等。ENUM：相等。SET：三个摘要都不等，SQL 侧为 `SqlSetValue(members=('x','y'))`，Repository 侧为 `StringScalar("['x', 'y']")`。伪 gid：规范 descriptor 若沿用原始 `INT`，行摘要抛 `CanonicalEncodingError`；改用 codec `INT UNSIGNED` 后相等。列序不同：`raw_content_digest` 相等，`fast_row_digest` 与 `raw_state_digest` 不等 |
| E3 | Dolt 2.1.11（临时 HOME，已预置 `versioncheck.disabled` / `metrics.disabled`，仓库外的临时库） | `TEXT` 主键被拒（"blob/text column 'source_table' used in key specification without a key length"）；`PRIMARY KEY(source_table(64), …)` 被拒（"prefix index on string column … unsupported"）；`VARCHAR(64)` 主键可建。显式 `NULL` 的主键列被拒（"All parts of PRIMARY KEY must be NOT NULL"）。SET 写入 `'y,x'` 读回 `'x,y'`。JSON 写入 `{"b": 1,   "a": [1, 2]}` 读回 `{"a": [1, 2], "b": 1}`。`CHAR(5)` 尾随空格保留（长度 5） |
| E4 | ruleset digest 探针 | 现行 `sha256:6f74c865…`。追加一条新表 SKIP 规则（ADDITIVE）后为 `sha256:4531c58f…`；只把 `app_cfg` 的 artifact_scope 改为 UPDATE_ONLY（纯比较变化）后为 `sha256:6becc3ba…` |
| E5 | `python -m tests.support.import_rules` | 与冻结基线一致：54 条违例（layer 27、capability-surface 12、unowned-root-module 6、private 6、contracts-leaf 3）、8 个运行时环、16 个不可达模块 |
| E6 | 规则集统计（`migrated_table_ruleset_snapshot()`） | 52 条。STANDARD_DIFF 21、BROWSE_ONLY 13、ORDERED_DIFF 9、SKIP 8、SNAPSHOT_ONLY 1；EXPLICIT_KEY 模式 19；UPDATE_ONLY 11。有 `ignored_columns` 的 13 条中，只有 4 条有 `dropped_columns`；9 条 ordered 规则的 ignored 与 structural 交集为 `no` |
| E7 | 被审核 9 个文件的相对链接与锚点检查 | 0 个问题 |

### 3.3 局限

- 没有真实业务 dump。旧验收矩阵提到的 large-* / small-cut-* 数据集不在仓库，也不在本机。
- Repository 读取侧用 fake provider 模拟 Arrow → Python 值，依据的是 `arrow_mapping.py` 源码，没有经过 HTTP/Arrow 实链路。
- Dolt 探针直接走 CLI，没有经过 Repository Service。
- 没有端到端运行 Preview、Submit 或 History。F3 中“删表时现行启发式选中基线副本”是代码推断，未运行。
- 未追踪 5E-S4 期间主线的变化。
- 未构建镜像，未跑全量测试。

### 3.4 镜像决策记录（testing-conventions“每轮评审记录”）

```text
Current HEAD: 3e5d5807e5（被审文档）；本报告提交后为仅含本报告的新提交
Container rebuild required: no
Reason: docs-only 独立审核；未触碰 image/deployment/container 边界；实验只读执行 worktree 源码
Last verified image revision: none（本轮）
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: 无；各阶段门禁按执行计划 §6
Required execution point: 不适用
```

## 4. Findings

| ID | 类别 | 阻塞接受 | 标题 |
| --- | --- | --- | --- |
| F1 | 已证实缺陷 | 是 | 规则集绑定与 Ruleset Activation Contract 冲突，非破坏性激活会导致 Preview/Submit 死锁；缺少规则集陈旧拒绝 |
| F2 | 已证实缺陷 | 是 | 规范快照同一性定义不足，已有确定的编码与存储分歧 |
| F3 | 已证实缺陷 | 是 | Submit 复用规范投影的入口所有权、manifest 发布与 T1 绑定未闭合；删表不成立 |
| F4 | 已证实缺陷 | 是 | 上游 Contract 修订缺少候选文本或排在实现之后 |
| F5 | 已证实缺陷 | 是 | 列处置规则与现有 ordered 规则、Canonical Storage §2 不一致 |
| F6 | 已证实缺陷 | 是（S3 前） | composite `TEXT` 主键停止条件已确定触发，规定的处置方向不当 |
| F7 | 待验证假设 | 否（S2 语义验收前必须关闭，见 §7.7） | Preview 提前失败的范围未量化，真实数据覆盖未验证 |
| F8 | 待验证假设 | 否（S2 冻结前关闭） | SNAPSHOT_ONLY/BROWSE_ONLY 的存储变化在 Preview 中不可见 |
| F9 | 已证实缺陷 | 是 | 初始基线语义不闭合 |
| F10 | 已证实缺陷 | 是 | 执行计划：S1 验收不可兑现，S1“行为不变”有隐含变化，S2 预算与 DC9 清单有遗漏 |
| F11 | 已证实缺陷 | 是 | 规范状态身份与提前退出存在 schema 盲区（2026-09-26 新增，见 §7.3） |
| N1–N6 | 非阻塞建议 | 否 | 见 §4.11；N1 的输入边界部分与 N3 于 2026-09-26 升为实施必达条件，见 §7.7 |

### F1 规则集绑定与 Ruleset Activation Contract 冲突

- **类别**：已证实缺陷（与 accepted Contract 冲突，且造成未被认识的业务损失）；阻塞。
- **位置**：
  - 设计 §4.4 第 168–170 行（`RULESET_BINDING_MISMATCH`）、§4.6、§5.3 第 233–234 行、§5.4、§14 第 4 项、附录 A 第 5 项；
  - ADR 0018 Decision 3、ADR 0019 Decision 5。
- **依据**：
  - [Ruleset Activation](../contracts/ruleset-activation-and-migration.md) §3（第 46–51 行）：`ADDITIVE`、`COMPARISON_BEHAVIORAL`、`RISK_ONLY` 不改变 storage，可以直接激活；只有 `STORAGE_BREAKING` 进入 `MIGRATION_REQUIRED`。
  - 同一 Contract §4：migration 只 rebuild 受影响的表，不自动创建空 commit。
  - 同一 Contract §5（第 67 行）：History compare 统一使用程序当前默认 ruleset，历史 snapshot 只作 provenance，**不增加 mismatch 分支**。
  - 5E 的 `HISTORY_RULESET_VERSION_MISMATCH` 比较的是“accept 时冻结的版本”与“worker 运行期版本”，属于 operation 内部一致性，不是 commit provenance 判据（[5E 设计](p5-5e-history-compare-design.md) §5.2）。
  - E4：`ruleset_digest` 覆盖整份规则文档。新增一条 SKIP 规则（ADDITIVE）或只改一处 artifact_scope（纯比较变化），digest 都会变。
  - Preview 陈旧判定只比较 baseline（`vnext/backend/src/gateway_backend/domain/workspace/policies.py:94-99`）。
  - 现行 prepare 用运行期规则集重新投影（`vnext/backend/src/gateway_backend/application/submit_jobs.py:1350-1374`）。§4.7 改成复用 Preview 投影后，这层隐式保护就没有了。
- **触发场景**：
  - (a) 部署任何规则变化。例如本计划 S3 的 DC4 规则变更本身，或新增一张 SKIP 表。之后凡是 BaselineHead 为 Submission commit 的 workspace，其 Preview 基线侧的 manifest digest 都不等于运行期 digest，返回 `RULESET_BINDING_MISMATCH`。没有 READY Preview 就不能 Submit，BaselineHead 也就无法推进。涉及任一旧 commit 的 History 比较全部失败。
  - (b) Preview 在规则激活前完成、激活后才受理。Submit 会写入旧规则的投影。若该激活属于 `STORAGE_BREAKING`，就违反 Ruleset §3“不能让不同表混用新旧 projection”。
- **影响**：投产后每次规则变更实际上都变成数据迁移事件，而非破坏性变更在 Contract 下没有迁移路径（不创建 commit）。DC6 只豁免本轮的兼容层，不覆盖将来的激活。
- **最小修正方向**：
  1. 把 `canonical_binding` 拆成两部分：
     - “存储身份”：`storage_projection_version` 加逐表 storage rule digest 或 canonical schema，来自 manifest；
     - “比较语义”：运行期 `ComparisonRuleSet`。
  2. Preview 基线侧与 History 节点只要求存储身份兼容。STORAGE_BREAKING 由 migration 处理。比较语义一律用运行期规则集，符合 Ruleset §5。
  3. AcceptSubmit 或 prepare 拒绝上传侧投影规则集与运行期不一致的 PreviewResult，作为 derived-stale 返回稳定错误码。
  4. 同步修订附录 A 第 5 项、ADR 0018/0019 与 §14 第 4 项。
- **关闭标准**：
  - 设计给出“激活类别 → Preview / History / AcceptSubmit / prepare 行为”对照表，且与 Ruleset §3/§5 一致；
  - 有唯一测试 owner 覆盖两个场景：ADDITIVE 激活后旧基线仍可 Preview；激活前的 Preview 在激活后受理被拒。

### F2 规范快照同一性（§4.1）定义不足

- **类别**：已证实缺陷；阻塞。
- **位置**：设计 §4.1 第 108–111 行、§4.2 第 115–119 行、§12 第 1 行、§14 第 1 项；执行计划 §3 S2 行“条件”列。
- **依据**：1–3 由 E2 确认，4、5 由 E3（Dolt 探针）确认，6、7 来自源码。

  1. **SET。** Repository Service 把 SET 映射为 Arrow `list<string>`（`vnext/repository_service/src/gateway_repository_service/arrow_mapping.py:356-367`）。Backend 按批对每列调用 `to_pylist()`（`vnext/backend/src/gateway_backend/infrastructure/repository_read/http_arrow.py:297-305`）。`map_repository_column` 把 SET 拼写映射为 STRING/STANDARD（`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/scalar_encoding.py:60-75`、`156-162`），值再经 `_as_text` 变成 `str(list)`（同文件 `165-178`）。E2 中三个摘要都不等。当前 History 两侧都走 Repository，分歧对称所以不报差异，但记录里展示的是 `"['x', 'y']"`。
  2. **伪 gid / unsigned。** 投影把 gid 改写为 `UnsignedIntegerScalar`（`vnext/backend/src/gateway_backend/capabilities/storage_projection/_ordered.py:86-88`），codec 固定为 `INT UNSIGNED`（`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:513-521`）。规范 descriptor 若沿用原始 DDL 的 `INT`，摘要计算直接失败。
  3. **列序。** `fast_row_hash` 按 descriptor 顺序拼接（`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_digest.py:98-102`），`raw_state_digest` 包含 `fast_row_digest`（同文件 `156-170`）。因此 §5.3 的“规范状态摘要”对列序敏感。设计没有规定规范快照的列序，也没有说明列序变化是否算规范变化。
  4. **JSON。** 投影接受 JSON 列：codec 映射为 STRING，DDL 仍写 JSON。Dolt 会规范化 JSON 文本（E3）。信息在存储时已经改变，仅修 Repository 解码不足以修正，§14 第 1 项必然触发（2026-09-26 措辞修正，见 §7.6）。
  5. **主键可空。** Dolt 拒绝显式 NULL 的主键列（E3），而 import DDL 按原始 nullable 输出 `NULL`/`NOT NULL`（`vnext/backend/src/gateway_backend/capabilities/storage_projection/import_replay.py:83-93`）。结果是 Preview 通过、Submit 在 Repository 失败。
  6. **比较不只看摘要。** 不走提前退出时，comparison 用 `(scalar_type.upper(), nullable)` 判定列兼容（`vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:946-947`），键列不兼容即 DEGRADED。只要求三个摘要相等，无法保证“有行变化”时比较正确。
  7. **测试 owner。** §12 的唯一 owner 用 fake provider，发现不了 4、5，也发现不了 1 中由 Arrow 形态引起的部分。
- **触发场景**：含 SET 或 JSON 列的表、ordered 表、原始可空的显式键、列序变化的上传与基线比较。后果是 `NO_CANONICAL_CHANGE` 永不命中，或误报变化。
- **影响**：R1 与 R3 修复、提前退出、`NO_CANONICAL_CHANGE` 的前提不成立。S2 的阶段门槛会在实现中途停下。
- **最小修正方向**：
  1. 在 §4.1/§4.2 定义“规范 descriptor = import schema”：
     - 列集合与顺序为 retained_columns，即 import DDL 顺序；
     - scalar_type 用 codec 拼写，按 ADR 0017 及 Repository `normalize_sql_type` 规范化；
     - 键列一律 NOT NULL，gid 为 `INT UNSIGNED`；
     - ordered metadata 为 `CANONICAL_PSEUDO_GID`。
  2. 同一性不变量扩展到 descriptor 级（列名、列序、scalar_type、nullable、compare key）加三个摘要。
  3. 列出存储类型词表，并逐类给出处置：
     - SET：Repository 读取解码为 `SqlSetValue`；
     - JSON：以 LONGTEXT 存储、列为不支持，或两侧统一 JSON 规范表示（后者有损，见 §7.6）；
     - CHAR 尾随空格：E3 已确认保留，无需处置。
  4. 执行计划把 `scalar_encoding.py` 从“条件”改为“必改”。
  5. 新增真实 Dolt integration owner：导入规范快照，经 Repository 读取路径读回，断言 descriptor 与摘要都相等；覆盖 NULL、ENUM、SET、JSON、CHAR、伪 gid、unsigned。
- **关闭标准**：
  - 修订后的 §4.1 有可测试的完整定义与类型词表；
  - §12 增加上述 integration owner；
  - 对已知类别，§14 第 1 项不再是“待发现”。

### F3 Submit 复用规范投影的接口与 T1 绑定未闭合

- **类别**：已证实缺陷；阻塞。
- **位置**：设计 §4.2 第 121–124 行、§4.5、§4.7 第 196–204 行；ADR 0018 Decision 2 与 Consequences 中的“Preview 所见即 Submit 所写”。
- **依据**：
  1. **包渲染的所有权。** import 包 = `manifest.json` + `replay.sql`，其中 `replay.sql` 由 storage_projection 的 schema SQL 加 mutation_planning 的 DML 组成（`vnext/backend/src/gateway_backend/repository_import_artifact.py:113-176`）。DML 需要 `repository_base_digest` 与 REBUILD_ALWAYS 规划（`vnext/backend/src/gateway_backend/capabilities/mutation_planning/import_replay.py:68-120`）。DAG 中 mutation_planning 依赖 storage_projection（`vnext/backend/tests/test_architecture.py:68`、`75`），所以 storage_projection 拿不到 DML。§4.2 把 `render_repository_import_package(canonical_table_set, manifest) -> bytes` 放在 storage_projection，还缺 `repository_base_digest` 输入，所有权和签名都不成立。
  2. **manifest 发布。** 设计写“manifest 由既有发布路径（`publish.py`）持久化”，但 `publish_canonicalization` 要求 `replay_sql`，并与 package 一起发布（`vnext/backend/src/gateway_backend/capabilities/storage_projection/publish.py:53-61`）。Preview 阶段还没有 replay，需要一个只发布 manifest 的入口。
  3. **T1 绑定。** 现行 AcceptSubmit 把 preview 保护集中“不是 source/closure、也不以若干前缀开头”的 artifact 都当作快照表候选（`vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py:107-160`；`vnext/backend/src/gateway_backend/application/submission/contracts.py:62-75`）。prepare 再按表名分组：优先取 `snapshot_digest == attempt.snapshot_digest` 的一份，否则取出现次数最少的 digest（`vnext/backend/src/gateway_backend/application/submit_jobs.py:2151-2210`）。
     - 加入规范表、manifest 与身份评估 artifact 之后，这套启发式区分不了原始与规范，也区分不了 MODIFIED/INITIAL/BASELINE。
     - PreviewResult 也没有绑定规范表集合。
     - §4.7“沿用 E 的 pin 转移模式”不足以定义 Attempt 冻结哪些输入。
     - 按代码推断（未运行）：对“基线有、上传删除”的表，现行启发式已会选中基线副本，投影随之报 `snapshot_digest must be shared`（`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:165-176`）。
  4. **删表。** Repository 在从 expected parent 建出的私有分支上重放 replay（`vnext/repository_service/src/gateway_repository_service/versioned_import/command.py:173-178`）。replay 只对包内的表 DROP/CREATE（`vnext/backend/src/gateway_backend/capabilities/storage_projection/import_replay.py:36-40`、`83-93`）。STRUCTURAL 校验要求候选的用户表集合与 manifest 完全相同（`vnext/repository_service/src/gateway_repository_service/versioned_import/verification.py:263-272`）。所以上传删除某张表时，Preview 显示 `DELETED_TABLE`，Submit 却必然 `VERIFICATION_FAILED_NOT_PUBLISHED`。
  5. **与 §2A.2 的关系。** P5 §2A.2 规定“用例 publication adapter 归 infrastructure，由 composition 接线”。§4.7 改为 Application 直接写 bytes，没有说明是否修订 §2A.2。
- **触发场景**：S2 按 §4.2/§4.7 实现 Submit 路径时；FULL 模式下 Preview 保护集同时含 BASELINE、INITIAL、MODIFIED 三侧的原始表与规范表时；任何删除了某张表的上传。
- **影响**：W1 的 Submit 半边无法照文档实施；T1 fingerprint、prepare input closure 与保护转移都缺少权威输入定义。
- **最小修正方向**：
  1. 确定 import 包渲染的 owner：由 Application 组合（storage_projection 出 schema/manifest，mutation_planning 出 DML，再打包），或由 mutation_planning 提供公开入口。签名包含 repository base 与 mutation policy。
  2. 新增只发布 manifest 的入口。
  3. PreviewResult 显式绑定 MODIFIED 侧规范表集合与 manifest（ref + digest）。T1 把它冻结到 Attempt 的新字段并纳入 fingerprint；prepare 只消费这个集合；删除按前缀和摘要的启发式。
  4. 对“parent 中有、规范快照中无”的表给出处置：prepare 依据冻结的 expected parent 渲染 DROP。原“在 Preview 阶段形成 blocker”的备选已于 2026-09-26 撤回，见 §7.4。
  5. 说明与 §2A.2 的关系。
- **关闭标准**：
  - §4.2/§4.7 给出入口 owner、签名、Attempt 字段与 fingerprint 组成；
  - 路径预算和测试 owner 与之对应（`test_submit_transactions.py`、`test_submit_job_prepare.py`、`test_submit_artifact_protection.py`）；
  - 删表场景有明确预期，并覆盖“业务基线 ≠ main”的场景（见 §7.4）。

### F4 上游 Contract 修订缺失或排在实现之后

- **类别**：已证实缺陷。下游设计静默修改了上游，违反[纵切指南](../guides/slice-design-execution-and-review-guide.md) §3。阻塞。
- **位置**：设计 §11、附录 A；执行计划 S0（第 43–44 行）、S5（第 103 行）；Entry Brief §5。
- **依据**：
  1. **Canonical Storage §2。** [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md) 3.0.0 §2（第 37 行）规定：comparison projection 负责“跨版本 alignment、selected value columns、ordered semantics 和 records”，与 storage projection “具有不同 contract、DTO、version 和 cache identity”。ADR 0018 删除 comparison_projection，改由 `ComparisonRuleView` 承担比较语义，且不做跨版本比较。但设计 §11 与 ADR 0018 Consequences 都没有列出 Canonical Storage。
  2. **Business Lifecycle §2 的 XML 条款。** [Business Lifecycle](../contracts/business-lifecycle-and-state.md) 3.0.0 §2（第 144–145 行）写明“可选 table/XML/ordered/risk 增强失败可发布 READY”。DC8 让 `logics.xml` 失败导致 Preview FAILED。设计只说要修订 P5 §6.1，附录 A 没有包含这一条。
  3. **ADR 0016 / Operation Lifecycle §4。** [ADR 0016](../adr/0016-graceful-lifecycle-and-integrity-recovery.md) Decision（第 28 行）与 [Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md) §4（第 60 行）都把 “Repository/content readback mismatch” 列为必须创建 durable incident 的权威事实问题。设计 §5.2、§5.5 与 ADR 0019 Decision 6 一方面把读取不一致（含新增的 `REPOSITORY_ROW_COUNT_MISMATCH`）降为普通 FAILED，另一方面声称“ADR 0016 不受影响”。DC9 本身可以实施，但需要写明它取代或收窄的范围。
  4. **Contract Taxonomy §5。** [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md) §5 仍有 “Hidden SnapshotSummary table schema/content” 与 “Hidden table 的普通版本化存储”两行。设计 §11 只列了删除 Comparison Projection 行、新增 Project Identity 行。
  5. **修订时点。** 执行计划把 owning 文档修订放在 S5，但 S2/S3 已经实现上述语义（DC8 在 S3），实现期间会与 accepted 文本冲突。
- **触发场景**：S0 按 Entry Brief §5 只接受 ADR 与附录 A；S2 删除 comparison projection 概念与 History integrity，S3 让无效 `logics.xml` 使 Preview FAILED。
- **影响**：S2–S4 的实现与验收以 accepted Contract 为准时会相互矛盾。审核者无法判定“符合 Contract”，而上游 owner 也没有机会对变化作出决定。
- **最小修正方向**：
  - 仿照附录 A，为 Canonical Storage §2（含版本号）与 Business Lifecycle §2 的 XML 条款补充候选文本，与 ADR 一起在 S0 接受。
  - ADR 0019 写明哪些读取不一致不属于 ADR 0016 / Operation Lifecycle §4 的 incident 类，理由是不再与 Backend 持有的期望值比较；或者保留一条最小的 incident 路径。
  - 设计 §11 补上 Contract Taxonomy 的 hidden 行。
  - 把 Contract 修订前移到 S0 接受时，或对应阶段开工之前。
- **关闭标准**：每一项上游变化都有候选文本、owner 与接受时点，并在 Entry Brief §5 中列明。

### F5 列处置规则与 ordered 规则、Canonical Storage §2 不一致

- **类别**：已证实缺陷；阻塞（§4.3 须修订）。
- **位置**：设计 §4.3 第 128–130 行、§2.1 R1；Entry Brief §2 第 3 行。
- **依据**：
  - E6：52 条规则中有 13 条带 `ignored_columns`，但只有 4 条带 `dropped_columns`（com_cfg、composite_signal_point、net_cfg、scdmod_para）。
  - 9 条 IEC104 ordered 规则既有 `ignored_columns=("no",)`，又有 `structural_columns=("no",)`（`vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:198-212`）。
  - storage 视图只按 `dropped_columns` 删列（`vnext/backend/src/gateway_backend/capabilities/storage_projection/view.py:33-39`），所以这 9 张表的 `no` 被保留为结构列。
  - History 把 `ignored_columns` 当作比较排除使用（`vnext/backend/src/gateway_backend/application/history/compare_jobs.py:890-915`）。
  - Canonical Storage §2（第 50 行）与 R4 §4.2 规定：ignored 列一律 `DROP_FROM_STORAGE`，且不得同时作为 effective key、ordered identity 或其他 required structural column。现有 9 条规则已经违反。
  - 设计 §4.3 重申“ignored_columns 维持 DROP_FROM_STORAGE”，但冲突校验只列了规范键与 ordered 身份列，漏了结构列，也没有安排这 9 条规则的迁移。
  - R1 说 13 条带忽略列的表“系统性降级”，但其中 9 张 ordered 表的问题来自键和位置语义，不是列丢弃。显式键也只在与 DDL PK 不同时才导致 `EFFECTIVE_KEY_CHANGED`。
- **触发场景**：S2 实现 ComparisonRuleView 与规则校验时，要么现有规则校验失败，要么 ignored 在 ordered 表上同时保留两种含义。
- **影响**：`ComparisonRuleView` 与 `StorageRuleView` 对同一字段给出不同解释，ordered 表的 `no` 会被当作存储丢弃列或值比较列，与 Canonical Storage §3“`no` 不进入普通 row-content modified 判定”冲突。
- **最小修正方向**：
  - ordered 规则去掉 ignored 中的 `no`（位置由 ordered 策略处理），或显式建模为 compare-excluded 的结构列；
  - 校验规则补上“结构列”；
  - 修正 R1 与 Entry Brief 的影响面表述。
- **关闭标准**：§4.3 与 Canonical Storage §2 一致，并列出受影响规则与 ruleset digest 的变化（DC6 下没有兼容负担）。

### F6 composite `TEXT` 主键停止条件已确定触发

- **类别**：已证实缺陷；阻塞 S3（在 S0 修订中即可关闭）。
- **位置**：设计 §8 第 367–368 行、§14 第 2 项；执行计划 S3（第 80 行）；Entry Brief §2 最后一行。
- **依据**：
  - E3：Dolt 拒绝 `TEXT` 主键，也不支持前缀索引主键；`VARCHAR(64)` 可以建表。
  - vNext 派生表定义了 `source_table TEXT`（`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/compose.py:88`）。
  - legacy 派生表使用 `source_table VARCHAR(64)`（主工作区 `legacy/backend_vnext/capabilities/composite_signal/materializer.py:80-90`）。
  - 投影不校验键列类型（`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:500-561`），所以 Preview 会 READY，Submit 在 Repository 失败，与“所见即所写”相悖。
- **触发场景**：S3 接入 composite 后，第一个含 `composite_signal_point` 的 Submit 在 Repository 重放 import DDL 时失败；或 S3 按计划先验证 Dolt 行为时立即命中停止条件。
- **影响**：S3 一开工就会停。§8 规定“由 storage_projection owner 以 ADR 规定键列字符串类型的规范化，不得在 composite 侧绕开”，把最直接的 owner 修复（由派生表 schema owner 声明有界 VARCHAR）排除在外，转而要求一个通用的类型改写机制，不符合比例化原则。
- **最小修正方向**：
  - S0 修订时直接决定：派生表 schema owner（snapshot_materialization compose / composite_signal contract）把 `source_table` 声明为有界 VARCHAR，以 legacy 的 64 为 oracle，并校验来源表名长度；
  - storage_projection 在投影阶段（即 Preview）拒绝不可作键的类型；
  - 把 §14 第 2 项改为已决事项。
- **关闭标准**：§8 给出确定的列类型与校验；S3 验收包含真实 Dolt 导入 composite 表。

### F7 Preview 提前失败的范围未量化（与 DC1 相关）

- **类别**：待验证假设。影响可能是全部真实上传的 Preview 失败。不阻塞纯结构的 S1，但必须在 S2 语义验收前关闭（2026-09-26 调整，见 §7.7）。
- **位置**：设计 §4.2 第 119 行、§4.5；ADR 0018 Consequences。
- **依据**：
  - storage_projection 只接受 STRING 族（含 JSON/ENUM/SET）、INT、BIGINT 与 INT UNSIGNED（`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:500-511`；[ADR 0017](../adr/0017-sql-spelling-declared-type-unification.md) 规定词表外返回 `UNSUPPORTED_TABLE`）。任何降级描述符（没有 PK 的 KEYLESS、重复键）都被直接拒绝（同文件 `414-458`）。
  - 现状：这些情形下 Preview 为 READY（表显示 DEGRADED），Submit 在 prepare 失败。DC1 之后变成整个 Preview FAILED。FULL 模式下 INITIAL 侧从不写入，但它的投影失败同样会让 Preview FAILED。
  - legacy 导入支持 decimal、float、bool（主工作区 `legacy/backend_vnext/core/scalar_encoding.py:60-95`），并把 `version_manager.saved_time` 当作时间值解析（主工作区 `legacy/backend_vnext/capabilities/snapshot_materialization/materializer.py:1741-1784`）。若真实库中 `saved_time` 是 DATETIME，所有真实上传都会在 `version_manager` 上失败，身份规则也随之失效。
  - 设计只写了一句原则，既没有列出类型词表，也没有评估影响范围。
- **触发场景**：真实上传中任一存储表（非 SKIP）含 TINYINT、SMALLINT、DECIMAL、FLOAT、DOUBLE、DATE/DATETIME/TIMESTAMP/TIME、BIT、BOOLEAN、BINARY/BLOB 或 BIGINT UNSIGNED 列，或存在无 PK、重复键的表。
- **影响**：S2 上线后 Preview 可能对全部真实数据不可用。用户从“能看到差异、提交时失败”变成“完全看不到差异”，且这一变化没有被量化。
- **最小修正方向**：
  - 设计列出会让 Preview FAILED 的表类别与列类别，以及结果形态：整体 FAILED 加 typed 诊断，还是按表 blocker。表述需与 Canonical Storage §3 的 “typed blocker” 及 Business Lifecycle §2 的 required/optional 区分对齐。
  - S1 kickoff 用代表性真实 dump 只读跑一遍 SQL 物化加 storage projection，列出落在存储表中的不支持类型。
  - 若确有不支持类型，在 S2 exit 前排入类型词表扩展（含同一性、renderer 与 Dolt 验证），或改用按表 blocker。
- **关闭标准**：设计给出清单与决定；S1 kickoff 记录代表性数据的核查结果。

### F8 SNAPSHOT_ONLY/BROWSE_ONLY 的存储变化在 Preview 中不可见

- **类别**：待验证假设，需要 owner 明确是否可接受；在 S2 冻结事实形态前关闭。
- **位置**：设计 §4.3 角色表（第 149–155 行）、§5.3。
- **依据**：
  - 按角色表，SNAPSHOT_ONLY 不产出比较事实，BROWSE_ONLY 只给存在性与行数事实。
  - 这两类表都会存入 Repository，因此计入 `raw_state_digest`。
  - legacy 的 BROWSE_ONLY 恒为 UNCHANGED（主工作区 `legacy/backend_vnext/capabilities/comparison/planner.py:333-372`、`legacy/backend_vnext/capabilities/comparison/engine.py:626-651`）。
- **触发场景**：只修改了 `forwardtable_*`，或 `version_manager`、`dev_list` 等表的上传。Preview 全部 UNCHANGED，却不被 `NO_CANONICAL_CHANGE` 拒绝。
- **影响**：审核人看不到实际提交的存储变化，Review/Archive 在不可见的内容上作决定。这与 DC1“Preview 展示规范业务状态的差异”不一致。
- **最小修正方向**：两类表在行数或 `raw_content_digest` 不同时，产出表级“内容已变化”事实（不含记录、不参与行级风险），并在 Review 可见；或者由 owner 明确接受该情形并写入设计。
- **关闭标准**：§4.3 冻结事实形态时覆盖该情形，并有测试 owner。

### F9 初始基线语义不闭合

- **类别**：已证实缺陷；阻塞。
- **位置**：设计 §5.1 第 212–213 行、§4.5 第 179–180 行、§7.2（DC7）；ADR 0021 Decision 3；附录 A 第 5 项。
- **依据**：
  - 文档里两种说法并存：§5.1 与 ADR 0021 说初始基线是“空规范状态、以零表传入”，§4.5 说基线侧“从 BaselineHead 的 exact commit 读取”。
  - 供给 mapping 文件接受任意 `business_baseline_commit_id`，不校验该 commit 为空（`vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_mapping.py:80-115`）。
  - compose harness 默认 `import_baseline=True`：先直接导入 `CREATE TABLE t`，再把这个 commit 作为 INITIAL 节点（`vnext/backend/tests/support/compose_gate_harness.py:577`、`1198-1245`）。
  - 生产的 create-repository 只执行 `dolt init`，产生空提交。
- **触发场景**：现有 compose 旅程（种子 INITIAL 含表 `t`）按新语义运行；运维供给时把 mapping 指向非空 commit。
- **影响**：
  - 若按“零表”合成，非空 INITIAL commit 里的表被忽略，`NO_CANONICAL_CHANGE` 与比较结果都会出错；表集合不一致还会触发 F3 的 STRUCTURAL 失败。
  - 若按读取处理，§5.1 与 ADR 0021 的“零表”定义不成立。
  - DC7 按节点类型判定 `NOT_APPLICABLE`，在非空 INITIAL 上会漏检跨项目上传。
- **最小修正方向**：
  - 定义 INITIAL 节点：从 Repository 读取，`canonical_binding` 取运行期规则集，并断言 catalog 为零表；不满足时稳定失败，或者明确允许“种子 INITIAL”并规定其身份语义。
  - 更新 compose harness 的默认值，并纳入 S2 路径预算。
- **关闭标准**：§5.1、ADR 0021、附录 A 第 5 项表述一致；compose 旅程的 INITIAL 数据符合该定义。

### F10 执行计划：S1 验收、“行为不变”与路径预算

- **类别**：已证实缺陷；阻塞（执行计划须修订）。
- **位置**：设计 §9 的 A2 行、job 模块复制行、S1 约束（第 391 行）与 §5.5；执行计划 S1 验收（第 56–60 行）、§3 路径预算 S2 行（第 115 行）。
- **依据**：
  1. **A2 修法仍违例。** 导入规则中 http 区只允许依赖 `{http, application, domain, operations, artifacts, ext:web}`（`vnext/backend/tests/support/import_rules.py:86`）。“HTTP admission 改用 source_package_staging 公开入口”仍是 http → capability 的 layer 违例，S1 验收（基线只剩 http_arrow 与 repository_import_artifact）因此无法达成。需要把受理逻辑移入 Application。
  2. **计数错误。** S1 验收写“A2 http_arrow 三条”，基线中实际只有两条（`vnext/backend/tests/architecture_baseline.py:28-37`）。
  3. **codec 合并改变载荷。** S1 把 Snapshot/Summary 编解码并入 snapshot_materialization contracts，但两份 `_summary_payload` 已经分叉：Preview 版含 `raw_content_digest` 与 `fast_row_digest`（`vnext/backend/src/gateway_backend/application/preview_jobs.py:1955-1980`），History 版不含（`vnext/backend/src/gateway_backend/application/history/compare_jobs.py:1559-1580`）。合并必然改变其中一侧的 checkpoint 载荷，与“golden、digest 不变 / 只改导入路径的测试不改断言”冲突。
  4. **改名产生新条目。** canonical_row_hash 相关模块改名后会出现新名字的不可达条目，按基线规则需要在同一 diff 中给出理由。计划写成“只剩”，不准确。
  5. **S2 生产路径遗漏**：
     - `vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py:238`：仍调用 BaselineCanonicalDigestPort；
     - `vnext/backend/src/gateway_backend/http/dependencies.py:159`：`FailClosedBaselineCanonicalDigestPort`；
     - 组合根：新 port 的接线，以及删除 `vnext/backend/src/gateway_backend/http/runtime.py:273` 的适配器；
     - `vnext/backend/src/gateway_backend/http/routes/operations.py:71` 与 `vnext/backend/src/gateway_backend/http/schemas/operation.py:30`：Operation DTO 暴露 History integrity incident；
     - `vnext/backend/src/gateway_backend/http/wiring.py:29`：`PRODUCTION_OPENAPI_PATHS` 含 integrity-ack；
     - `application/history` 下的 errors 与 contracts；
     - `scalar_encoding.py` 应为必改（见 F2）。
  6. **S2 测试路径遗漏**：
     - `test_production_wiring.py`、`test_operation_http.py`、`test_history_http.py`、`test_artifact_staging_conformance.py`；
     - control DB migration 测试；
     - `tests/support` 下的 `repository_ref_materialization.py`、`history_compare_job_harness.py`、`preview_job_harness.py`、`compose_gate_harness.py`。

     另外，`test_submit_*` 这类通配不符合纵切指南 §4“不使用整层通配代替影响分析”。
  7. **DC9 删除清单遗漏**：
     - 上述 Operation DTO 字段与 OpenAPI 路径集合；
     - 只为 incident 映射而存在的 `MaterializationDiagnostic.expected_digest_ref/observed_digest_ref`（`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/contracts.py:188-189`，唯一消费者是 compare_jobs 的 integrity 逻辑）；
     - fake provider 里的 per-read 篡改钩子。

     按比例化政策 §6.2，删除一个机制时应同时删除它的 mock、fixture 与 probe。已核实：ADR 0016 的 Operation integrity 代码路径（`operations/store.py` 的 `scan_active_integrity`、`worker_startup`、control DB 的 PRAGMA 检查）与此独立，不受影响。
- **触发场景**：S1 按 §9 实施后运行 `import_rules`，基线仍残留 A2 的 layer 违例；S1 合并 codec 后既有 checkpoint 断言变化；S2 按预算实施时需要改动预算外的文件。
- **影响**：S1 的阶段退出无法按计划签署，S2 需要反复扩预算，独立审核缺少可核对的边界。
- **最小修正方向**：
  - A2 改为把受理逻辑移入 Application；
  - 更正 S1 验收的计数，并允许改名产生的条目；
  - 把 codec 合并移到 S2，或在 S1 写明 checkpoint 载荷允许变化并提升 checkpoint 契约版本；
  - 补齐 S2 的必改路径与测试路径，去掉通配；
  - 补全 DC9 删除清单。
- **关闭标准**：S1 验收能由 `import_rules` 机械验证；S2 预算覆盖以上文件。

### 4.11 非阻塞建议

- **N1（W4 细节）**（2026-09-26：前两项输入边界升为实施必达条件，见 §7.7）：
  - `identity_confirmations` 应规定列表上限与重复 action 的处理。
  - 理由超长、确认多余这两种情况用什么错误码需要明确；目前“多余”复用 `…_REQUIRED` 语义不清。
  - 需规定与 `NO_CANONICAL_CHANGE` / `PREVIEW_DERIVED_STALE` 的判定先后。
  - 需定义 `assessment_set_digest` 的组成（pair 顺序；是否包含 NOT_APPLICABLE 的 pair）。
  - 旧验收矩阵中“SQL reader 与 archive reader 生成相同 assessment”应改写为“投影侧与 Repository 侧生成相同 assessment”（依赖 F2）。
  - 补一条 FULL 混合模式旅程：基线 pair 为 replacement，initial→modified 为 detailed。
  - 写明不采用旧设计的 side-local business projection，以及 R5 §5.1 的“server-side policy allowance”。
- **N2（W3 输入闭合）**：
  - surface 当前从 comparison 导入 `IdentityStatus`（`vnext/backend/src/gateway_backend/capabilities/surface_assembly/contracts.py:20`、`684`），而目标 DAG 没有 surface → project_identity 边。需确定身份标注类型的 owner，或由 surface 自持中性枚举。
  - “同名表导出两侧快照”需要 Application 向 surface 传入 `table_artifacts`，目前没有任何调用方传入（同文件 `790`）。这不只是“补测试”。
- **N3（W2 端口）**（2026-09-26 升为实施必达条件，见 §7.7）：
  - `CommitCanonicalMetadataPort` 应以 `(repository_id, commit_id)` 为键。
  - 需写明规则集身份的来源：取自 finalize 时由 `canonicalization-manifest` owner 长期保护的 manifest artifact（`vnext/backend/src/gateway_backend/application/submission/finalize_transaction.py:226-265`，读取时需校验 digest），还是持久化为列。
- **N4（compare-excluded 语义）**：E 中只有排除列变化时，结果是 `SCHEMA_ONLY_CHANGED` 加 `IGNORED_COLUMNS_CHANGED`（`vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:732-742`）。设计要求排除列在记录中携带前后值用于展示，应一并定义表状态与记录形态。
- **N5（表述精度）**：
  - R3 的基线流水线在 AcceptSubmit 预检中执行（`submit_acceptance.py:238`），发生在写事务之前，不在 T1 写事务内。
  - R4 的 `to_pylist()` 是按批、按列调用，不是逐行。
  - `publish_ready_tables` 不是 facade 导出。
- **N6（计划规模与持久化）**：
  - S2 同时承载 W1、W2、W3、DC9、migration 与 compose，范围过大。可考虑拆为 S2a（W3 入口、ComparisonRuleView、编码修复与 integration owner）和 S2b（切换到规范域、W2、DC9）。
  - §12 缺少 migration 的测试 owner。
  - 不回填数据的前向 migration 需处理已有行（例如新增 NOT NULL 列），或明确要求重建 control DB。

## 5. 逐项核查结论（对应任务 1–9）

1. **R1–R6 与 readiness 表**：
   - R1 已独立复现（E1）。
   - R2 属实：Preview 与 History 都只传 `ALL_CHANGES`，BROWSE_ONLY/SNAPSHOT_ONLY 无消费者。
   - R3 属实，时点精度见 N5。
   - R4 属实：hidden summary 由行重建，版本取运行期常量，每张表读两遍。
   - R5 属实：`optional_xml_document_ref` 被暂存但无消费者，`materialize_business_snapshot` 未被调用。
   - R6 属实。
   - readiness 表各项计数全部正确（E5、E6）。“13 带忽略列”的含义问题见 F5。
2. **W1**：
   - 方向与 Canonical Storage §3（keyless 必须显式分类、失败在 Preview 暴露）、P5 §6.1 的 pair 拓扑、Business Lifecycle §2–§3 一致。
   - 同一性可行性见 F2，提前失败见 F7。
   - 复用投影后，pin 转移机制本身可行，但 T1 绑定未定义（F3）。prepare 的确定性重建与 checkpoint 复用可以保持。T2/T3 evidence-first 的请求字节与恢复语义不受影响。规则集陈旧判定见 F1。
3. **W2**：
   - 各类 commit 的规范元数据都可得：Submission 必有 manifest ref/digest（`vnext/backend/src/gateway_backend/domain/submission/models.py:210`），与 Review 状态、closed-not-archived 无关；finalize 时 manifest 被长期保护。
   - INITIAL 节点见 F9，端口键见 N3。
   - `NO_CANONICAL_CHANGE`：baseline 漂移这一侧由现有检查闭合；规则集漂移这一侧未闭合（F1）；判据本身还有 schema 盲区（F11，2026-09-26 新增）。
   - DC9 的范围见 F4、F10。ADR 0016 的 Operation integrity 代码不受影响。
4. **W3**：
   - Application 能表达全部现有拓扑：FULL 两个 pair；MODIFIED_ONLY 基线→modified；History 2–3 个节点对应 DETAILED pair；初始基线作为零表 before。
   - 待删除的流程词汇（`ARCHIVE_REPLAY`、`INITIAL_SNAPSHOT`、continuation 等）在 comparison 之外没有消费者，唯一例外是 surface 的 `IdentityStatus`（N2）。
5. **W4**：
   - 适用性规则可以实施（DC7 依赖 F9 的 INITIAL 定义）。
   - T1 事务内校验可行：只依赖 control DB 中的 PreviewResult。
   - 只要 Attempt 持久化确认内容，fingerprint 与 same-key 重放就可以实现。
   - Attempt 到 Submission 的复制、Review/History 的只读展示可以实施。
   - Archive 的 subject digest 绑定 candidate digest，与旧设计“candidate 内容变化使确认失效”一致；复用异常处置事件与 StartArchive 校验可行。
   - 两个 409 码与旧设计一致。
   - 细节见 N1。
6. **W5**：
   - DC8 与 P3-R3 一致：composite 不变量失败使业务物化 FAILED；XML digest 或 EMPTY 标记进入快照身份。
   - 与 P5 §6.1 的冲突文档已认识；与 Business Lifecycle §2 的冲突未认识（F4）。
   - TEXT 主键见 F6。
   - DC4 把 `formula_ast_json`、`point_name` 恢复为存储列。按 Ruleset Contract 这属于 STORAGE_BREAKING，但该表从未落库，DC6 下无影响。
   - XML digest 只进入 `snapshot_digest`、不进入 `raw_state_digest`：规范状态就是派生行，这可以接受。
   - Submit 复用投影覆盖 composite 表，前提是 F2、F3、F6 关闭。
7. **W6**：54 条违例、8 个环、16 个不可达模块都映射到了 §9 的行（`snapshot_materialization._catalog` 随 compose 在 S3 变为可达）。问题见 F10。
8. **执行计划**：
   - 阶段依赖与顺序合理：S3 先于 S4 的理由成立。
   - 镜像重建判定符合 AGENTS.md：compose e2e 改动与阶段退出都触发重建。
   - 测试 owner 基本唯一。需要补 integration owner（F2）与 migration owner（N6）。`NO_CANONICAL_CHANGE` 目前出现在 5 个测试文件中，需要收敛到设计指定的唯一 owner。
   - 停止条件可操作，但第 1、2 项已知会触发（F2、F6），应改为事先决定。
   - 路径预算见 F10。
9. **一致性与比例化**：
   - ADR 与设计一致（F1 的冲突在两处都存在）。
   - 附录 A 的缺口见 F1、F4、F9。
   - 新增的 A 类持久事实都有明确 consumer：PreviewResult 规范摘要与身份结论用于 AcceptSubmit；确认记录用于 Review 与 Archive；Archive 身份异常复用现有事件。
   - 除 F1 的整体 digest 绑定外，没有发现多余机制。
   - 基础边界：T1 事务与 CAS 沿用现有实现；输入上限见 N1；跨 scope 键见 N3。

## 6. 修订后通过时仍保留的实施前置条件

1. P5-5E slice exit 为 pass 后才能开始 S1。S1 kickoff 按执行计划 §2 复核 E 级事实与基线漂移。
2. S0 接受时一并接受上游修订的候选文本（F4、附录 A）。实现授权由 repository owner 另行给出。
3. S1 kickoff 用 owner 提供的 4 份真实 dump（小、中小、中等、大）完成只读类型普查并记录，满足 §7.7 的条件，并据此确定 S2 范围（F7）。
4. S2 阶段门槛之前，真实 Dolt 同一性 integration owner 通过（F2）；F11 的 schema 身份与 F3 的 expected parent 删表处置有真实 Dolt 证据。
5. S3 验收之前，composite 键列类型的决定已实施，并经 Dolt 导入验证（F6）。
6. 每个阶段按 testing-conventions 记录镜像决策；最终候选按执行计划 §6 fresh 重建。
7. §7.10 所列 owner 确认事项中，标注“S0 修订前”的在 S0 修订中逐项落定，其余按表中标注的时点落定。

## 7. 复核补充（2026-09-26）

本节补充三方面内容：repository owner 对 F1 的新决定、owner 提供的真实数据安排、另一份独立评审意见的核实与采纳。复核时确认 HEAD `8d89ca3c86` 下 `vnext/` 与代码基线仍无差异。补充实验同样在审核者临时目录执行，未修改仓库中本报告以外的文件。

### 7.1 补充实验

| # | 实验 | 结果 |
| --- | --- | --- |
| E8 | schema-only 变化探针：用 SQL 路径物化变化前后的两个快照，比较 `raw_state_digest` 与 `compare_schema_digest`，并按 Preview 方式运行 comparison | 见下表 |
| E9 | Dolt 2.1.11 JSON 往返（沿用 E3 的临时库） | `{"a": 1.0, "b": 1e2, "c": 12345678901234567890, "d": 0.10, "f": -0}` 读回为 `{"a": 1, "b": 100, "c": 12345678901234567000, "d": 0.1, "f": 0}`；`{"k": 1, "k": 2}` 读回为 `{"k": 2}` |

E8 结果：

| 变化 | `raw_state_digest` | `compare_schema_digest` | Preview 比较结果 |
| --- | --- | --- | --- |
| 空表新增列 | 不变 | 改变 | SCHEMA_CHANGED |
| INT→BIGINT（空表或有数据） | 不变 | 不变 | UNCHANGED |
| VARCHAR(8)→VARCHAR(32)（有数据） | 不变 | 不变 | UNCHANGED |
| NULL→NOT NULL（有数据） | 不变 | 不变 | UNCHANGED |
| 主键 (a,b)→(b,a)（有数据） | 不变 | 不变 | UNCHANGED |
| 列序变化（空表） | 不变 | 不变 | UNCHANGED |
| 列序变化（有数据） | 改变 | 不变 | UNCHANGED |

### 7.2 F1：owner 新决定与仍需定义的内容

Owner 决定（2026-09-26）：比较统一使用两侧中较新的规则集，取代设计 §4.4、§5.4 中“两侧规则集 digest 必须相等”的判据。

评估：这个决定解除了 F1 的死锁，也与 Canonical Storage §7、§9 一致（版本不同时做 schema-change alignment，按兼容列和有效键 fallback，不安全时表级 degraded）。修订时还需补齐五条定义：

1. **全序。** “较新”需要可比较的版本。现有 `RULESET_VERSION` 在规则集快照与 manifest 两处都被校验写死为 `"v2"`（`vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py:432-433`、`vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py:297-298`），digest 本身没有先后。需要规定每次规则变更单调升版，并放开读取历史 manifest 时的版本校验。
2. **可取回性。** History 比较两个旧 commit 时（规则分别为 R1、R2，运行期已是 R3），字面的“两侧较新”是 R2，但程序中只有 R3。要么按 digest 永久保存规则集文档（新增持久事实），要么取“两侧与运行期中最新”。后者在没有回滚时恒等于运行期规则，不需要新增持久化，并与 Ruleset §5 一致。
3. **回滚。** Ruleset §5 规定回滚只影响之后的操作。基线规则比运行期新时，字面规则会选中基线规则，但上传侧按运行期投影、Submit 也按运行期写入，比较与写入不一致。需要规定此时的处理。
4. **三节点 History。** 需说明规则按每个 pair 各取，还是整份结果统一取所有节点中最新的一个；后者能保证同一份结果内语义一致。
5. **存储身份不同。** 两侧存储投影不同（STORAGE_BREAKING）时，按 Canonical Storage §7 做 alignment 并产出表级事实，不再失败。

F1 的其余部分按三个场景分别定义，见 §7.5。

更新后的关闭标准：

- 设计写明规则取法、全序与取回方式，并给出“激活类别 × 三个场景 → Preview / History / AcceptSubmit / prepare / 恢复行为”对照表；
- 与 Ruleset §1、§5 及 Canonical Storage §7、§9 一致，或附上对应的 Contract 修订候选文本；
- 测试 owner 覆盖三点：ADDITIVE 激活后旧基线仍可 Preview；激活前完成的 Preview 在激活后受理被拒；两侧存储身份不同时按 alignment 产出表级事实。

### 7.3 新增 F11：规范状态身份与提前退出存在 schema 盲区

- **类别**：已证实缺陷；阻塞。该问题由另一份独立评审首先提出，本审核用 E8 复测并扩大了范围。
- **位置**：设计 §5.3（规范状态摘要取 `raw_state_digest`）、§4.4（提前退出沿用现有 `raw_content_digest` 判定）、§12 第 7 行；附录 A 第 2 项。
- **依据**：
  - `raw_state_digest` 每表只包含表名、行数、`raw_content_digest` 与 `fast_row_digest`，不含 schema（`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_digest.py:156-170`）。
  - 行摘要按列名排序编码（同文件 `74-95`）。E8 显示整数位宽、字符串长度和可空性的变化都不改变行摘要。
  - comparison 提前退出只要求 `compare_schema_digest`、行数与 `raw_content_digest` 相等（`vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:950-961`）。而 `compare_schema_digest` 只含表名、排序后的列名和排序后的键名（`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_digest.py:114-127`），不含类型、可空性、列序和键序。
  - Canonical Storage §9 以 “R4 canonical schema/content/storage-business digest 不变” 作为 `NO_CANONICAL_CHANGE` 的判据。storage projection 的 canonical schema digest 覆盖列名、类型、可空性与主键（`vnext/backend/src/gateway_backend/capabilities/storage_projection/_digest.py:80-89`）。
- **触发场景**：
  - 只放宽列长度、调整类型或可空性、调整主键列顺序，或给空表新增列：拟议的 `NO_CANONICAL_CHANGE` 会误拒，合法的 schema 更新无法提交。
  - 类型、长度、可空性、键序变化：Preview 显示 UNCHANGED，审核看不到。
  - 有数据表的列序变化：Preview 显示 UNCHANGED，却允许提交。
  - 现行 History 比较有同样的盲区，属于现有缺陷。
- **影响**：Submit 判定与 Preview 展示对同一变化给出不一致的结论。软件升级带来的 schema 变更要么无法入库，要么审核看不到。
- **与 F2 的关系**：F2 要求两条生产路径结果一致，但两条路径完全可能一致地遗漏 schema，所以单列。F11 的修复依赖 F2 的 descriptor 级定义。
- **最小修正方向**：
  1. 规范状态身份由表集合与每表的三部分组成：完整规范 schema digest（有序列名、规范化类型、可空性、有序主键）、内容 digest、行数。是否纳入列序取决于 §7.10 D6 的决定。
  2. comparison 提前退出要求完整规范 schema 相等。两侧内容相同但 schema 不同时，产出明确的 schema 事实（类型、可空性、键序、列序）。
  3. 按上述定义修订附录 A 第 2 项的 “canonical business digest”。
  4. 只把现有 `compare_schema_digest` 并入状态摘要不够，它不含类型、可空性与键序。
- **关闭标准**：设计给出上述定义。唯一测试 owner 同时证明两点：规范状态相同则摘要相同；E8 中各类 schema 变化都不会被判为无变化，且在 Preview 中可见。同构用例按 AGENTS 收敛为共享参数表。

### 7.4 F3 补强：删表以冻结的 expected parent 为依据

- **依据**：SubmitAttempt 分别冻结业务基线 `business_baseline_commit_id` 与 T1 时的 Repository main `repository_expected_commit_id`（`vnext/backend/src/gateway_backend/application/submission/accept_transaction.py:396-434`）。前一个 Submission 已提交但尚未归档时，main 已经前进而业务基线不变，这正是 Business Lifecycle §5 的 sibling 情形。import 在 expected parent 上重放，STRUCTURAL 校验要求表集合完全一致（见 F3 依据 4）。
- **扩大的触发场景**：未归档的 sibling Submission 在 main 上新增一张表后，下一个 Submit 即使没有删除任何表，也会因 “user table set mismatch” 失败。
- **撤回**：撤回原 F3 修正方向第 4 条中“在 Preview 阶段形成 blocker”的备选。Preview 以业务基线为准，处理不了 Preview 之后 main 的变化。
- **修正方向**：
  - prepare 在 T1 之后、effect 之前读取冻结 expected parent 的表目录（只读 Repository 访问），确定待删除的表，生成确定性的 replay；
  - 结果写入 prepare 包 checkpoint，重试复用同一个包，并沿用 expected commit 的 CAS；
  - 新 commit 的内容等于上传的完整规范状态。
- **补充关闭标准**：验收覆盖三种情形：业务基线等于 main 时用户删表；业务基线不等于 main 时 sibling 新增表；业务基线不等于 main 时 sibling 删除表。

### 7.5 F1/F4 扩充：Canonical Storage §7/§9 与 Ruleset §1

- [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md) §7（第 218–221 行）规定版本不同时必须做 schema-change alignment、fallback 与表级 degraded；§9 验收要求 “Projection version change 使用 alignment/fallback”。原设计的“不等即失败”与之矛盾。按 §7.2 的新决定改为 alignment 后二者一致，F4 对这两节只需确认一致；若修订时仍保留失败语义，就必须一并修订 §7、§9。
- [Ruleset Activation](../contracts/ruleset-activation-and-migration.md) §1（第 20 行）规定已启动的 operation 继续使用启动时捕获的规则；设计 §4.6 则规定恢复时按运行期规则重新派生，digest 不同即失败。5E 已有同类“稳定失败”的先例，但收口设计需要写明契约立场。
- 三个场景分别定义，不再统称“规则陈旧”：
  1. **旧 commit 的 provenance**：按 §7.2 的规则取法比较；存储身份不同时按 Canonical Storage §7 做 alignment。
  2. **尚未受理的旧 Preview**：若 PreviewResult 的上传侧投影规则集与运行期不一致，AcceptSubmit 按 derived-stale 拒绝。
  3. **已受理 operation 的恢复**：
     - Submit 在 T1 之后只使用冻结的规范产物，不依赖运行期规则，天然满足 §1；
     - Preview/History 二选一：按 digest 取回捕获的规则集继续执行；或在 Ruleset §1 中明确纯计算 operation 可以稳定失败、由用户重跑（激活前有 graceful drain，只有超时或崩溃才会遇到这种情况）。
- 以上都是对契约立场的澄清，不要求新增在线迁移框架。

### 7.6 F2 修正：JSON 的措辞与选项

- **措辞**：“编码 owner 无法修正”改为“仅修 Repository 解码不足以修正”。
- **新增选项**：两侧统一 JSON 规范表示，即规范投影与 Repository 读取两侧都先把 JSON 列转换为同一规范形式，再做编码。
- **限制**：E9 表明 Dolt 的 JSON 规范化是有损的（大整数丢失精度、重复键只保留最后一个、数值写法被改写）。统一表示要么同样有损，要么对无法无损往返的值 fail-closed，两者都需要显式决定。LONGTEXT 仍是无损的默认选项。若真实 dump 中没有 JSON 列，可以先 fail-closed，并登记重开条件，见 §7.10 D5。

### 7.7 分类调整与真实数据安排

- **F7**：不阻塞纯结构的 S1，但必须在 S2 语义验收前关闭。Owner 将在本轮修复中提供 4 份真实 dump（小、中小、中等、大）。作为 F7 类型覆盖和设计 §13 测量规模梯度的主要证据，这些数据足够，但需满足以下条件：
  1. 覆盖在用的软件版本与协议族（IEC104 ordered 表、协议配置表、装置点表）；至少一份带 `logics.xml`、一份不带；并确认 `version_manager.saved_time` 的真实类型。
  2. 至少一个项目提供前后两个版本。身份规则的 SAME_PROJECT、FULL 上传、History 与 §13 链路都需要这种成对数据；不同项目之间则构成 DIFFERENT_PROJECT。大数据档最好也有成对版本。
  3. 真实数据覆盖不到的边界继续使用合成夹具：SET/JSON、可空显式键、删表、纯 schema 变化、sibling 在 main 上新增表、UNVERIFIABLE、ordered 空白 gid。
  4. dump 保存在 Git 外（[testing-fixtures](../../../testing-fixtures.md) 第 24、29 行；[Fixture Oracle](../contracts/fixture-oracle-and-conformance.md) 第 131–133 行）。S1 kickoff handoff 记录 dataset ID、SHA-256 与列类型普查结果；普查发现的问题提炼为最小的合成 golden。
- **升为实施必达条件**：以下两项属于比例化政策 §3 的基础边界，须写入修订后设计的验收：
  - N1 中 `identity_confirmations` 的数量上限、重复 action 的处理与理由长度的错误处置；
  - N3 中 `CommitCanonicalMetadataPort` 以 `(repository_id, commit_id)` 为键，且只在已授权 scope 内解析。

  N1 的其余部分以及 N2、N4、N5、N6 仍为非阻塞建议。

### 7.8 推进顺序与验收证据

采纳如下顺序：

1. 补齐 S0 设计与上游候选文本；
2. P5-5E slice exit pass；
3. 对 exit 后的代码复核漂移；
4. S1–S5 修复与验收；
5. 最终候选的全量测试、五包静态检查、fresh 镜像与容器门禁；
6. P5 整体 exit review。

既有的 5E exit 保留为历史验收证据；收口改动后的代码须以新候选的证据验收。F1、F3、F4、F11 不得作为普通延期项带入 P5 exit。

### 7.9 更新后的 findings 状态

| ID | 类别 | 阻塞 | 2026-09-26 变化 |
| --- | --- | --- | --- |
| F1 | 已证实缺陷 | 是 | owner 已决定规则取法（§7.2），待补定义与三个场景（§7.5） |
| F2 | 已证实缺陷 | 是 | JSON 措辞与选项修正（§7.6） |
| F3 | 已证实缺陷 | 是 | 以 expected parent 为依据，撤回 Preview blocker 备选（§7.4） |
| F4 | 已证实缺陷 | 是 | 扩充 Ruleset §1；Canonical Storage §7/§9 随 F1 新决定确认一致（§7.5） |
| F5、F6、F9、F10 | 已证实缺陷 | 是 | 无变化 |
| F11 | 已证实缺陷 | 是 | 新增（§7.3） |
| F7 | 待验证假设 | 否（S2 语义验收前必须关闭） | 真实数据安排见 §7.7 |
| F8 | 待验证假设 | 否（S2 冻结事实形态前关闭） | owner 已决议（DC16），待设计修订 |
| N1（输入边界部分）、N3 | 基础边界 | 实施必达 | 由建议升级（§7.7） |
| N1 其余部分、N2、N4、N5、N6 | 非阻塞建议 | 否 | 无变化 |

结论仍为定向修订。接受前须关闭的阻塞项为 F1–F6、F9、F10、F11。

### 7.10 需要 repository owner 确认的事项

决议状态：repository owner 已于 2026-09-26 对 D1–D15 作出决议，见 [S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md)（DC10–DC22）。下表保留为审核时的建议与依据。

以下事项影响业务语义或契约立场，不宜由作者自行决定。每项附审核建议与确认时点。

| # | 事项 | 审核建议 | 关联 | 确认时点 |
| --- | --- | --- | --- | --- |
| D1 | “较新规则”的精确取法：字面的“两侧中较新”，还是“两侧与运行期中最新” | 取后者。没有回滚时它恒等于运行期规则，不需要持久化历史规则集，也与 Ruleset §5 一致。若坚持前者，需接受按 digest 永久保存规则集文档（新增持久事实），并修订 Ruleset §5 | F1 | S0 修订前 |
| D2 | 规则回滚后、基线规则比运行期新时，Preview 如何处理 | 一律按运行期规则投影与比较，存储差异按 Canonical Storage §7 做 alignment | F1 | S0 修订前 |
| D3 | 激活前完成、激活后才受理的 Preview | AcceptSubmit 按 derived-stale 拒绝，由用户重跑 Preview | F1 | S0 修订前 |
| D4 | 已受理的 Preview/History 在规则激活后恢复 | 稳定失败、由用户重跑，并在 Ruleset §1 注明纯计算 operation 的这一例外。若 D1 选择持久化规则集，可改为取回捕获的规则继续 | F1、F4 | S0 修订前 |
| D5 | JSON 列的存储方式 | 默认以 LONGTEXT 无损存储；若真实数据中没有 JSON 列，先 fail-closed 并登记重开条件。不建议采用有损的统一表示 | F2 | S1 kickoff 普查后 |
| D6 | 列序是否属于规范业务状态 | 取决于设备或工具是否按位置读取列。若都按列名读取，建议排除列序（状态身份按列名计算）；若存在按位置读取，则纳入身份，并在 Preview 中作为 schema 变化展示 | F11 | S0 修订前 |
| D7 | 规范投影失败时 Preview 的结果形态 | 整体 FAILED，但一次列出全部失败的表与列（现有投影遇到第一个失败即停止，需要调整），与 Business Lifecycle §2 一致。若普查显示不支持的类型很普遍，优先扩充类型词表，而不是做部分 Preview | F7 | S0 修订前 |
| D8 | 本轮是否扩充存储类型词表 | 若普查发现 DATETIME、DECIMAL、FLOAT、TINYINT 等出现在存储表中，建议在 S2 内扩充（含同一性、renderer 与 Dolt 验证），否则真实数据无法使用 | F7 | S1 kickoff 普查后 |
| D9 | SNAPSHOT_ONLY/BROWSE_ONLY 表的内容变化是否在 Preview/Review 中可见 | 产出表级“内容已变化”事实，不含记录，不参与行级风险 | F8 | S2 冻结事实形态前 |
| D10 | INITIAL 基线是否必须为空 | 必须为空（读取时断言零表），种子数据一律经 Submit 进入；compose harness 改为不预导入。若运维确有“预置数据的初始库”需求，需另定其身份语义 | F9 | S0 修订前 |
| D11 | 上传是否代表完整规范状态 | 是。上传中没有的表（包括用户删除的表，以及 sibling 在 main 上新增的表）在新 commit 中删除；Preview 标为 DELETED_TABLE，并按表删除风险提示 | F3 | S0 修订前 |
| D12 | DC9 之后 Repository 读取不一致如何处置 | ADR 0019 写明：不再与 Backend 期望值比较后，读取不一致（如 `REPOSITORY_ROW_COUNT_MISMATCH`）按依赖异常处理，即普通 FAILED 加诊断、日志与指标，不建持久 incident；ADR 0016 与 Operation Lifecycle §4 的 incident 范围限定为“与 Backend 期望值矛盾”或 CAS 歧义 | F4 | S0 修订前 |
| D13 | composite `source_table` 的列类型 | `VARCHAR(64)`（MySQL 标识符长度上限，与 legacy 一致），由派生表 schema owner 修复，并撤销设计中“不得在 composite 侧绕开”的限制 | F6 | S0 修订前 |
| D14 | 4 份 dump 的组成与存放 | 确认：是否有同一项目的前后版本；覆盖哪些软件版本与协议族；是否带 `logics.xml`；Git 外的存放路径；handoff 中可记录的信息粒度（表名、列类型普查） | F7 | S1 kickoff 前 |
| D15 | S2 是否拆分 | 拆为 S2a（W3 入口、ComparisonRuleView、编码修复与 integration owner）和 S2b（切换到规范域、W2、DC9），分别独立审核 | N6 | S0 修订前 |

以下事项由作者按 finding 自行处置，无需 owner 另行决定：

- F5 中 ordered `no` 的建模方式；
- F10 中 A2 受理逻辑移入 Application；
- F3 中 import 包渲染入口的 owner 与签名；
- N1 的错误码与判定先后；
- N2 中 surface 身份类型的 owner；
- N4 中排除列的展示方式。

## 8. 链接与路径检查

提交前用脚本检查了本报告（含 2026-09-26 补充）的全部相对链接与锚点，结果为 0 个问题；同时检查了文中全部反引号源码路径：以 vnext 开头的路径在 worktree 中存在，带行号引用的行号不超出文件长度；以 legacy 开头的路径在主工作区存在。
