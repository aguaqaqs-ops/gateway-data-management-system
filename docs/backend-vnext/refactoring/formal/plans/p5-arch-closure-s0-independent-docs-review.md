# P5 架构收口 S0 独立文档审核报告

- 状态：独立审核报告（docs-only）。本报告不接受 ADR、不修改 Contract 版本、不改变任何阶段状态，也不构成实现授权。
- 日期：2026-09-25
- 审核者：未参与本轮起草的独立 reviewer
- 审核依据：[纵切指南](../guides/slice-design-execution-and-review-guide.md) §5–§6、`AGENTS.md`、
  [testing-conventions](../../../testing-conventions.md)、
  [比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)
- 结论：**定向修订**

## 1. 结论与判定理由

**定向修订。** 核心方向成立，且与 DC1–DC9 及多数上游 Contract 一致：

- 在规范域比较，规范快照有两个生产者；
- 以 Backend 持有的 manifest 作为 commit 规范元数据权威；
- comparison 去流程化；
- 项目身份的确认在 Submit 受理时收集。

R1–R6 的事实与 Entry Brief 的 readiness 表均回到源码核实成立。R1 已独立复现。导入基线的 54/8/16 条目都能映射到设计 §9 的某一行。

需要修订的问题集中在少数章节和接口：设计 §4.1–§4.4、§4.7、§5.1–§5.5、§8、§9 部分行，执行计划 S1 验收与路径预算，附录 A 及 ADR 0018/0019/0021 的对应条款。修订这些不需要重建核心模型和主执行路径，所以不判整体返工。但其中 8 项是接受前必须关闭的阻塞项（F1–F6、F9、F10），因此不能判通过。

最关键的四项：

- **F1**：规则集绑定判据与 accepted 的 Ruleset Activation Contract 冲突。任何非破坏性规则激活后，所有已有业务基线都无法 Preview，Submit 因此死锁。
- **F2**：§4.1 的“规范快照同一性”只约束三类摘要，没有规定规范 descriptor 如何派生。实验已确认至少 SET、JSON、主键可空、列序、伪 gid 五类分歧。其中 JSON 的分歧来自 Dolt 存储规范化，无法由编码 owner 修正。
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
| F7 | 待验证假设 | 否（实施前置） | Preview 提前失败的范围未量化，真实数据覆盖未验证 |
| F8 | 待验证假设 | 否（S2 冻结前关闭） | SNAPSHOT_ONLY/BROWSE_ONLY 的存储变化在 Preview 中不可见 |
| F9 | 已证实缺陷 | 是 | 初始基线语义不闭合 |
| F10 | 已证实缺陷 | 是 | 执行计划：S1 验收不可兑现，S1“行为不变”有隐含变化，S2 预算与 DC9 清单有遗漏 |
| N1–N6 | 非阻塞建议 | 否 | 见 §4.11 |

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
  4. **JSON。** 投影接受 JSON 列：codec 映射为 STRING，DDL 仍写 JSON。Dolt 会规范化 JSON 文本（E3）。信息在存储时已经改变，编码 owner 无法修正，§14 第 1 项必然触发。
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
     - JSON：以 LONGTEXT 存储，或列为不支持；
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
  4. 对“parent 中有、规范快照中无”的表给出处置：渲染 DROP，或在 Preview 就形成明确 blocker。
  5. 说明与 §2A.2 的关系。
- **关闭标准**：
  - §4.2/§4.7 给出入口 owner、签名、Attempt 字段与 fingerprint 组成；
  - 路径预算和测试 owner 与之对应（`test_submit_transactions.py`、`test_submit_job_prepare.py`、`test_submit_artifact_protection.py`）；
  - 删表场景有明确预期。

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

- **类别**：待验证假设。影响可能是全部真实上传的 Preview 失败。实施前置。
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

- **N1（W4 细节）**：
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
- **N3（W2 端口）**：
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
   - `NO_CANONICAL_CHANGE`：baseline 漂移这一侧由现有检查闭合；规则集漂移这一侧未闭合（F1）。
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
3. S1 kickoff 记录代表性真实数据的类型覆盖核查结果（F7），并据此确定 S2 范围。
4. S2 阶段门槛之前，真实 Dolt 同一性 integration owner 通过（F2）。
5. S3 验收之前，composite 键列类型的决定已实施，并经 Dolt 导入验证（F6）。
6. 每个阶段按 testing-conventions 记录镜像决策；最终候选按执行计划 §6 fresh 重建。

## 7. 链接与路径检查

提交前用脚本检查了本报告的全部相对链接与锚点（0 个问题），以及文中全部反引号源码路径：以 vnext 开头的路径在 worktree 中存在，
带行号引用的行号不超出文件长度；以 legacy 开头的路径在主工作区存在。
