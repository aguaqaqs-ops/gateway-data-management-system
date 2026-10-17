# P5 架构收口 S0 Owner 决议记录

- 状态：**已决议**（repository owner，2026-09-26）。本记录是 S0 文档修订的输入；不改变 ADR 状态与 Contract 版本，不构成实现授权。
- 日期：2026-09-26
- 决议人：repository owner
- 记录人：独立 reviewer。依据审核报告 §7.10 的建议与 owner 的逐项答复整理。
- 依据：
  - [S0 独立审核报告](p5-arch-closure-s0-independent-docs-review.md)（含 2026-09-26 复核补充）；
  - [详细设计](p5-arch-closure-design.md) §1 的 DC1–DC9。本记录的决议编号接续为 DC10–DC22，修订时并入设计 §1 的决定表。
- 补充：2026-09-26 复审后，owner 按[第二份独立复审报告](p5-arch-closure-s0-independent-rereview-2.md) §8 的建议对 O1–O5
  作出决议，记录为 DC23–DC27，见 §7。
- 补充：2026-10-12 S2b 真实数据旅程停止后，owner 决议无主键表的兜底规则，记录为 DC29，见 §12。
- 补充：2026-10-14 owner 决议调试与取证分开、P5 性能指标分三层，记录为 DC30，见 §13。
- 补充：2026-10-15 S2b t4 真实数据暂停后，owner 决议 Catalog 上限、读取失败的终态与 P5 的性能范围，记录为 DC31，见 §14；其中第三部分修订 DC30 的 B 层处理与业务容量目标的用法。
- 补充：2026-10-17 owner 决议把 Phase 6 规划讨论稿的 V2 并入 S5，扩展 S5 的测量范围，记录为 DC32，见 §15。
- 补充：2026-10-17 owner 决议缩短阶段取证耗时（按包沿用测试结果；真实数据按阶段改动面确定范围），记录为 DC33，见 §16；其中第二部分修订 DC30 的取证要求。

```yaml
record_kind: p5_arch_closure_s0_owner_decisions
decided_by: repository_owner
decided_at: 2026-09-26
review_report: p5-arch-closure-s0-independent-docs-review.md @ 89668aaf56
documents_under_revision: entry brief / design / execution plan / ADR 0018-0021 @ 3e5d5807e5
code_inspection_base: 2172369803
decisions: DC10-DC22
conditional_decisions: [DC12, DC15]   # 触发条件由 S1 kickoff 真实数据普查判定
adr_status_changed: no
contract_version_changed: no
implementation_authorized: no
next_step: 作者按本记录与审核 findings 修订 S0 文档并逐条写明处置，然后独立复审
```

## 1. 决议总览

| ID | 决议 | 来源 | 细化的现有决定 |
| --- | --- | --- | --- |
| DC10 | 比较语义统一使用运行期（当前激活）规则集；存储身份不同按 Canonical Storage §7 对齐 | F1；D1、D2 | DC2 |
| DC11 | 规则激活前后：旧 Preview 受理时拒绝；已受理的纯计算 operation 恢复时稳定失败；Submit 在 T1 后只用冻结产物 | F1、F4；D3、D4 | DC2 |
| DC12 | JSON 列：有则以 LONGTEXT 无损存储，无则 fail-closed；不采用有损的统一表示 | F2；D5 | —（条件决议） |
| DC13 | 列序不属于规范业务状态 | F11、F2；D6 | DC1 |
| DC14 | 规范投影失败时 Preview 整体 FAILED，一次列出全部失败的表与列 | F7；D7 | DC1 |
| DC15 | 普查发现词表外类型时，在 S2 内扩充存储类型词表 | F7；D8 | —（条件决议） |
| DC16 | SNAPSHOT_ONLY/BROWSE_ONLY 表内容变化产出可见的表级事实 | F8；D9 | DC1 |
| DC17 | 初始基线恒为空，不支持预置数据的初始库 | F9；D10 | DC7 |
| DC18 | 上传代表完整规范状态；删表以冻结的 expected parent 为依据 | F3；D11 | — |
| DC19 | DC9 之后，Repository 读取不一致按依赖异常处理，不建持久 incident | F4；D12 | DC9 |
| DC20 | composite `source_table` 为 `VARCHAR(64)`，由派生表 schema owner 修复 | F6；D13 | DC4 |
| DC21 | S2 拆分为 S2a、S2b，分别独立审核 | N6；D15 | — |
| DC22 | 真实数据：4 份代表性 dump，含同一项目前后两个版本，均带 `logics.xml` | F7；D14 | — |

## 2. 决议详情

### DC10 比较规则集

- **决议**：比较语义统一使用运行期（当前激活）规则集。
- **来由**：owner 先决定“使用两侧中较新的规则”，随后同意 D1（取两侧与运行期中最新者）和 D2（规则回滚时按运行期）。两者合并后的等价表述就是本条：没有回滚时，运行期规则就是两侧与运行期中最新者；发生回滚时同样按运行期。
- **约束**：
  - 不保存历史规则集文档，也不需要规则集全序。ruleset id、version、digest 只用于 provenance 与存储身份判定。
  - 删除设计 §4.4 的 `RULESET_BINDING_MISMATCH`。§5.4 不再以 commit 元数据中的规则集判定失败；operation 内“受理时冻结”与“执行时运行期”不一致的情况按 DC11 处理。
  - 某侧存储身份（`storage_projection_version`、逐表 storage rule 或 canonical schema）与运行期不同时，按 Canonical Storage §7 做 schema-change alignment：按兼容列与有效键 fallback；无法安全对齐时表级 degraded，并在表事实中标明原因。整个 pair 不因此失败。
  - 三节点 History 的整份结果使用同一个运行期规则集。
  - 与 Ruleset Activation §5 原文一致，该节无需修订；与 Canonical Storage §7、§9 一致，这两节也无需修订。
- **验收要点**：ADDITIVE 激活后，旧基线仍可 Preview；两侧存储身份不同时，按对齐规则产出表级事实。

### DC11 规则激活与 operation

- **尚未受理的旧 Preview**：AcceptSubmit 发现 PreviewResult 上传侧投影所用规则集的 digest 与运行期不同时，按 derived-stale 拒绝，用户需重跑 Preview。稳定错误码由设计确定，可复用 `PREVIEW_DERIVED_STALE`。
- **已受理的 Preview/History 在激活后恢复**：稳定失败，由用户重跑；不得静默改用运行期规则重算。
- **Submit**：T1 之后只使用冻结的规范产物（规范表集合、manifest、prepare 包 checkpoint），不依赖运行期规则，prepare 也不重新投影。
- **Contract**：为 Ruleset Activation §1 提供修订候选：纯计算 operation（Preview、History compare）在激活后恢复时可以稳定失败、由用户重跑；带外部 effect 的 operation 按冻结产物继续执行。依据：激活前有 graceful drain，只有 drain 超时或崩溃时才会遇到这种情况。
- **验收要点**：激活前完成的 Preview 在激活后受理被拒；Preview/History 恢复时规则不一致会稳定失败。

### DC12 JSON 列（条件决议）

- 代表性 dump 的存储表中**有** JSON 列时：规范存储与 import DDL 都用 LONGTEXT 保存原文（无损），规范 descriptor 同步为 LONGTEXT，两侧按字符串编码与比较。
- **没有** JSON 列时：JSON 列 fail-closed，按不支持的类型处理，并登记重开条件“真实数据出现 JSON 列”。
- 不采用两侧统一 JSON 规范表示。Dolt 的 JSON 规范化是有损的：大整数丢失精度，重复键只保留最后一个，数值写法被改写（审核报告 E9）。
- 触发时点：S1 kickoff 真实数据普查（DC22）。若触发，实施放在 S2a。

### DC13 列序不属于规范业务状态

- 规范状态身份、`NO_CANONICAL_CHANGE`、comparison 提前退出与 schema 事实都不考虑列序。只有列序不同的上传判为无规范变化，不产生 commit。
- 规范 schema digest 由以下两部分组成：
  - 按列名排序的列定义（列名、规范化类型、可空性）；
  - 有序主键。主键列顺序仍属于存储身份，本决议只针对非键的列序。
- Repository 中的物理列序由写入时的 import DDL 决定，不作为身份；读取与比较一律按列名对齐。
- `fast_row_digest` 若保留，只作为快照内部诊断，不进入规范状态身份；或改为按列名顺序计算。
- 对 F11 与 F2 的约束：规范状态身份与 descriptor 同一性都按本决议排除列序。

### DC14 规范投影失败时的 Preview 形态

- Preview 整体 FAILED，不做部分 Preview。
- typed 诊断一次列出全部失败的表与列：投影在单表失败后继续收集，不在第一个失败处停止。
- 与 Business Lifecycle §2 的 required table 语义一致。
- FULL 模式下 INITIAL 侧的投影失败同样使 Preview FAILED，诊断中标明失败所在的一侧。

### DC15 存储类型词表（条件决议）

- S1 kickoff 普查若在存储表中发现词表外类型（DATETIME、DECIMAL、FLOAT、TINYINT 等），在 S2a 内扩充存储类型词表，同时覆盖规范同一性、renderer 与真实 Dolt 往返验证。
- 未发现时维持 fail-closed，并登记重开条件“生产数据出现词表外类型”。

### DC16 SNAPSHOT_ONLY/BROWSE_ONLY 的可见性

- 这两类表在行数或内容 digest 不同时，产出表级“内容已变化”事实：不含记录，不参与行级风险，在 Preview 与 Review 中可见。
- 其余事实形态按设计 §4.3 与 legacy oracle 核对后冻结。

### DC17 初始基线恒为空

- INITIAL BaselineNode 引用的 commit 必须是没有用户表的空提交。不支持预置数据的初始库。
- INITIAL 节点即零表规范状态，`canonical_binding` 取运行期规则集。物化时读取一次 catalog，断言没有用户表；不满足则稳定失败，用于防止误供给。不做其他特殊处理。
- DC7 据此恒成立：before 侧为 INITIAL 的 pair，身份评估为 `NOT_APPLICABLE`。
- compose harness 改为不预导入基线数据，由首个 Submit 建立数据。该变更随 S2b 进行，不放在要求“行为不变”的 S1。

### DC18 上传代表完整规范状态

- 上传中没有的表在新 commit 中删除，包括两种情况：用户删除的表；未归档 sibling Submission 在 main 上新增的表。
- prepare 在 T1 之后、effect 之前读取冻结 expected parent（`repository_expected_commit_id`）的表目录，确定待删除的表，生成确定性的 replay。结果写入 prepare 包 checkpoint，重试时复用；沿用 expected commit 的 CAS。
- Preview 仍以业务基线比较：被删除的表显示 `DELETED_TABLE`，并按既有表删除风险规则提示。
- 验收要点：
  - 业务基线等于 main 时，用户删表；
  - 业务基线不等于 main 时，sibling 新增表；
  - 业务基线不等于 main 时，sibling 删除表。

### DC19 DC9 之后的读取不一致

- Repository 读取不一致（如 `REPOSITORY_ROW_COUNT_MISMATCH`）按依赖异常处理：普通 FAILED，附诊断、日志与指标，不创建持久 incident。
- ADR 0019 写明这一范围。ADR 0016 与 Operation Lifecycle §4 的 incident 范围限定为“与 Backend 持有的期望值矛盾”和 CAS 歧义，修订候选文本随 S0 接受。
- ADR 0016 的 Operation integrity（`scan_active_integrity`、worker startup 扫描、control DB 完整性检查）不受影响。

### DC20 composite 键列类型

- `composite_signal_point.source_table` 声明为 `VARCHAR(64)`（MySQL 标识符长度上限，与 legacy 一致），由派生表 schema owner 修改，并校验来源表名长度。
- storage_projection 在投影阶段（即 Preview）拒绝不能作主键的列类型，如 TEXT、BLOB。
- 撤销设计 §8 中“不得在 composite 侧绕开”的限制；§14 第 2 项改为已决事项。

### DC21 S2 拆分

- **S2a**：W3 comparison 入口去流程化；ComparisonRuleView 与列处置（含 F5）；编码修复（SET 等），以及 DC12、DC15 触发后的类型处理；真实 Dolt 同一性 integration owner。
- **S2b**：切换到规范域比较；W2 commit 规范元数据与 `NO_CANONICAL_CHANGE`（含 F11、DC13）；DC9 删除；DC17、DC18 相关改动与 compose harness 调整。
- 两段分别交独立审核。F7 与 DC22 的普查结论在 S2b 语义验收前落定。

### DC22 真实数据

- owner 提供 4 份代表性 dump（小、中小、中等、大），其中至少一个项目有前后两个版本，均带 `logics.xml`。
- 覆盖范围：有序表（IEC104 gid/no）与无序表（标准键表）。其他协议族与软件版本在生产环境中扩展，重开条件为“出现新的协议族或软件版本”，届时重跑普查与相关验收。
- 本轮验收口径：
  - 代表性 dump 走通 Preview → Submit → History 链路；
  - 普查结果记录在 S1 kickoff handoff；
  - 真实数据覆盖不到的边界由合成夹具证明，清单见审核报告 §7.7。
- F7 在 S2 语义验收前关闭。存放方式见 §4。

## 3. 审核补充的采纳

以下审核建议经 owner 确认采纳（2026-09-26）：

- **F11 作为阻塞项新增。** 规范状态身份由表集合与每表三部分组成：
  - 规范 schema digest，按 DC13 排除列序；
  - 内容 digest；
  - 行数。

  comparison 提前退出要求规范 schema 相等；schema 差异产出明确事实。
- **F3** 以冻结的 expected parent 为依据（DC18），撤回“在 Preview 阶段形成 blocker”的备选。
- **F1、F4** 的三个场景分别定义（DC10、DC11）。Canonical Storage §7、§9 与 DC10 一致，无需修订。
- **F2** 的 JSON 措辞按审核报告 §7.6 更正，不采用统一表示（DC12）。
- **以下两项升为实施必达条件**：
  - N1 中 `identity_confirmations` 的数量上限、重复 action 的处理与理由长度的错误处置；
  - N3 中 `CommitCanonicalMetadataPort` 以 `(repository_id, commit_id)` 为键，只在已授权 scope 内解析。
- **推进顺序与验收证据的处理**按审核报告 §7.8。

## 4. 真实数据存放建议

- **路径**：`/home/dev/gateway-real-dumps/`。
  - 位于所有 Git worktree 之外。
  - 不放在主工作区 `legacy/`、`runtime-data/` 等 gitignored 目录下（这些目录仍在仓库树内，容易被误提交）。
  - 不放在会话临时目录或 `/tmp`。
- **权限**：目录 700、文件 600，属主为 dev。
- **目录结构**：

```text
/home/dev/gateway-real-dumps/
  README.local.md        # 来源、真实项目名映射、用途限制、保留期；只在本机，不进入 Git
  datasets.json          # 数据集清单，字段见下
  rd-t1-a-v1/
    package.tar.gz       # 与生产上传一致的 TAR_GZ：/sql/dbcfg.sql 与 /comps/logic/logics.xml
  rd-t2-b-v1/
  rd-t3-c-v1/
  rd-t3-c-v2/            # 同一项目 c 的后一版本（成对数据；实际放在拥有成对数据的规模档）
  rd-t4-d-v1/
  census/                # S1 kickoff 普查输出：只含结构统计，不含行数据
  runs/                  # 真实数据运行产物（若需保留），不进入 Git
```

- **命名**：dataset ID 为 `rd-<规模档>-<项目别名>-v<版本>`。规模档 t1 小、t2 中小、t3 中等、t4 大；项目用字母别名，真实项目名只记在 `README.local.md`。
- **文件**：优先保存生产实际上传的 TAR_GZ 包。若只有原始文件，按包内布局存放（`sql/dbcfg.sql`、`comps/logic/logics.xml`），由脚本确定性打包。
- **`datasets.json` 字段**：`dataset_id`、`tier`、`project_alias`、`version`、`pair_of`（成对数据指向前一版本）、`files`（相对路径、字节数、SHA-256）、`has_logics_xml`、`note`。
- **使用方式**：
  - 脚本通过环境变量 `GATEWAY_REAL_DUMP_ROOT` 定位数据，仓库中不写死主机路径。
  - 真实数据旅程从主机侧经公开 HTTP 上传接口发起，不把该目录挂载进 backend、worker 或 repository 容器，因此不改变容器边界。
  - 普通 CI 与 `./vnext/scripts/run-tests.sh` 不依赖真实数据。
- **可记录信息**：
  - handoff 与 runbook 记录 dataset ID、SHA-256、规模、列类型分布、表数、总行数、耗时与结论（符合 [testing-fixtures](../../../testing-fixtures.md) 与 [Fixture Oracle](../contracts/fixture-oracle-and-conformance.md) 对外部 dataset 的要求）。
  - 表名与列名属于 schema 标识符，可以记录，用于定位不支持的类型。
  - 行数据、真实项目名与主机路径不进入 Git。
- **清理**：运行产生的 artifact、Dolt 数据与日志都含真实数据，随 compose teardown 清理，或移到 `runs/` 下保留；不进入 Git。

## 5. 需同步修订的文档

| 文档 | 需修订内容 | 依据 |
| --- | --- | --- |
| 设计 §1 | 决定表并入 DC10–DC22 | 全部 |
| 设计 §4.1–§4.4 | descriptor 级同一性（排除列序）、类型词表、JSON 处置；删除 `RULESET_BINDING_MISMATCH`；提前退出要求规范 schema 相等 | F2、F11、DC10、DC12、DC13、DC15 |
| 设计 §4.2、§4.5、§4.7 | import 包渲染入口的 owner 与签名；只发布 manifest 的入口；PreviewResult 绑定规范表集合；Attempt 字段与 fingerprint；按 expected parent 删表 | F3、DC18 |
| 设计 §4.3 | 列处置（ordered `no`）；SNAPSHOT_ONLY/BROWSE_ONLY 的表级事实 | F5、DC16 |
| 设计 §4.6、§5.3、§5.4 | 规则激活语义；规范状态身份；受理时的陈旧拒绝 | F1、F11、DC10、DC11 |
| 设计 §5.1、§7.2 | INITIAL 恒为空与断言 | F9、DC17 |
| 设计 §5.5 | 读取不一致的处置；删除清单补全 | F4、F10、DC19 |
| 设计 §8、§14 | composite 键列类型；停止条件第 1、2 项改为已决事项 | F6、DC12、DC20 |
| 设计 §12 | 测试 owner：真实 Dolt 同一性 integration、F11 共享参数表、migration、删表三种情形 | F2、F11、F3、N6 |
| 设计附录 A | 第 1、2、5 项按 DC10、DC11、DC13、DC17 修订；补 Business Lifecycle §2 的 XML 条款 | F1、F4、F11、F9 |
| ADR 0018 | Decision 3 改为运行期规则集 + §7 对齐 | DC10 |
| ADR 0019 | Decision 5、6；读取不一致范围；与 ADR 0016 的衔接 | DC10、DC19 |
| ADR 0021 | 初始基线表述与 DC17 一致 | DC17 |
| 执行计划 | S2 拆分；S1 验收与路径预算修正；compose harness 调整随 S2b；S1 kickoff 普查 | F10、DC17、DC21、DC22 |
| Contract 候选文本（随 S0 接受） | Canonical Storage §2（删除 comparison projection 独立 contract 的表述，升版本）；Business Lifecycle §2 的 XML 条款（并入 3.1.0）；Ruleset Activation §1（纯计算 operation 恢复可稳定失败）；ADR 0016 / Operation Lifecycle §4 的 incident 范围；Contract Taxonomy 的 hidden summary 两行 | F4、DC11、DC19 |

## 6. 后续步骤

1. 作者按本记录与审核报告的 findings 修订 S0 文档，包括上游 Contract 候选文本，并逐条写明处置。
2. 独立复审：检查 finding 是否关闭、改动是否传播到相关章节，以及是否引入新的冲突。
3. 复审通过后，按 Entry Brief §5 接受 ADR 与 Contract 候选。实现授权另行给出，最早在 P5-5E slice exit 之后。
4. S1 kickoff：
   - 把本分支合入 5E exit 后的主线，并复核漂移；
   - 按 DC22 完成真实数据普查；
   - 按 DC12、DC15 的触发条件落定类型处置。

## 7. 复审后补充决议（DC23–DC27）

- 状态：**已决议**（repository owner，2026-09-26）。owner 对[第二份独立复审报告](p5-arch-closure-s0-independent-rereview-2.md)
  §8 的 O1–O5 一律采纳复审建议。
- 记录人：第二份复审报告的复审者。
- 本节不改变 ADR 状态与 Contract 版本，不构成实现授权。设计、执行计划、ADR 与附录的对应修改在 r3 中完成。

```yaml
record_kind: p5_arch_closure_s0_owner_decisions_supplement
decided_by: repository_owner
decided_at: 2026-09-26
source: p5-arch-closure-s0-independent-rereview-2.md §8 @ ca6502d8a4
decisions: DC23-DC27          # 对应复审报告的 O1–O5
conditional_decisions: [DC27] # 触发条件由 S1 kickoff 普查判定
adr_status_changed: no
contract_version_changed: no
implementation_authorized: no
```

### 7.1 决议总览

| ID | 复审事项 | 决议 | 细化的现有决定 | 关联 finding |
| --- | --- | --- | --- | --- |
| DC23 | O1 | Ruleset Activation §5 末句随附录 B.2 一并修订 | DC10、DC11 | 复审 RR-F2 |
| DC24 | O2 | Preview 在受理时冻结运行期规则集 digest | DC11 | 复审 RR-F2 |
| DC25 | O3 | manifest digest 不符按稳定失败处理，不属于 incident 范围 | DC19 | 复审 RR-F3 |
| DC26 | O4 | canonical row hash 的 Rust 绑定放在哪里，由 Backend Architecture 在 r3 中从三个选项中择一 | — | 复审 RR-F4 |
| DC27 | O5 | DC12 触发时，在 B.1 或 S2a handoff 中写明版本轴的处理（条件决议） | DC12 | 复审 RR-F6 第 5 点 |

### 7.2 决议详情

#### DC23 Ruleset Activation §5 随 B.2 修订

- **决议**：附录 B.2 同时给出 Ruleset Activation §5 末句的修订候选，例如：“已捕获旧 snapshot 的带外部 effect operation
  按冻结产物继续；纯计算 operation（Preview、History compare）按 §1 稳定失败，由用户重跑。”
- **取代**：DC10 约束中“与 Ruleset Activation §5 原文一致，该节无需修订”一句。DC10 的比较语义不变。
- **r3 落点**：附录 B.2；设计 §4.9 末句；ADR 0019 Consequences 列出 Ruleset §5。复审 RR-F2 的其余修正一并完成：B.2 中
  Submit 的边界改为“T1 冻结规范产物之后（含 PREPARED）”，并写明 B.2 收窄的是 §1 首句在恢复场景下的含义。

#### DC24 Preview 在受理时捕获规则集

- **决议**：Preview 受理时把运行期规则集 digest 冻结进 job payload。这与 History 受理的做法一致，也符合 P5 §6.1
  “Preview 接受后冻结 ruleset/contract versions”与 DC11 的字面要求。每一步执行前比较运行期 digest 与冻结值，不同即稳定
  失败，尚未开始 materialize 的 Preview 也不例外。materialize checkpoint 与 PreviewResult 记录的“投影所用规则集 digest”
  就是这个冻结值。
- **r3 落点**：设计 §4.6、§4.9；ADR 0019 Decision 6；稳定错误码由设计确定；恢复用例（`test_preview_job_worker.py`）覆盖
  “受理后、materialize 前发生激活”的情形。

#### DC25 manifest digest 不符的处置

- **决议**：`CommitCanonicalMetadataPort` 读取 manifest artifact 时，若 digest 与 Submission 的记录不符，按稳定失败处理，
  附诊断、结构化日志与指标，不创建持久 incident。附录 B.3 中“与 Backend 持有的期望值相矛盾的读回”限定为两类：Repository
  返回值与 Backend 期望值的矛盾（例如 T3 回显的 manifest digest、expected parent），以及 CAS 或结果歧义。Backend artifact
  store 的读回不属于 `RepositoryIntegrityIncident` 的范围。
- **r3 落点**：设计 §5.1（错误码）；附录 B.3 的文字；ADR 0019 Decision 1、7；复审 RR-F3 要求新增的测试 owner 覆盖 digest
  不符的情形。

#### DC26 canonical row hash Rust 绑定的放置

- **决议**：由 Backend Architecture 在 r3 中从复审 RR-F4 的三个选项中选定一个，写入设计 §9 的 A6 行与执行计划 S1：
  1. import 规则显式放行 `capability:canonical_row_hash → ext:compute`；
  2. Rust 绑定作为由 composition 选择的 provider 放在 infrastructure，只把契约与 IPC 编解码移入 capability；
  3. 保留该违例，在 S1 验收中登记为 Phase 6 延期项。
- **约束**：若修改 import 规则，这属于对 P5 §2A.2 门禁的精确放行，须在同一 diff 中说明，并把 `tests/support/import_rules.py`
  列入 S1 预算。无论选哪一项，S1 验收列出的条目都须与迁移后 `import_rules` 的输出一致。

#### DC27 DC12 触发时的版本轴（条件决议）

- **决议**：DC6 下不做兼容。S1 kickoff 普查若触发 DC12（存储表中有 JSON 列，改以 LONGTEXT 存储），在附录 B.1 或 S2a handoff
  中按 Canonical Storage §8 写明是否提升 storage projection version 及理由。未触发时，B.1 中“storage projection version 不变”
  保持有效。
- **触发时点**：S1 kickoff 普查后。

### 7.3 后续步骤

1. r3 修订同时处置两份复审报告的 findings（[第一份](p5-arch-closure-s0-independent-rereview.md) @ `34ff1827cf`，
   [第二份](p5-arch-closure-s0-independent-rereview-2.md) @ `ca6502d8a4`）与 DC23–DC27，并更新修订处置表。
2. 由未参与 r3 修订的 reviewer 核对差异。
3. 复审通过后，按 Entry Brief §5 接受 ADR 与 Contract 候选。实现授权另行给出，最早在 P5-5E slice exit 之后。

## 8. 接受后补充决议（DC28）

#### DC28 身份确认理由允许多行

- **来源**：[r4 独立核对](p5-arch-closure-s0-independent-rereview-r4.md)的 owner 事项 O6。r4 让身份确认理由沿用 Review 理由规则，
  该规则拒绝全部控制字符，因此理由只能单行；Archive 理由只限字节数，允许多行。
- **决议**（repository owner，2026-09-27）：身份确认理由允许多行。
- **规则**：HTTP DTO 仍为 `BoundedDiagnosticReason`（1–4096 UTF-8 字节）。Submission 领域的共享理由校验放行 LF（U+000A）、
  CR（U+000D）与 TAB（U+0009）；其余 C0/C1 控制字符、代理码点与非字符码点仍拒绝；至少含一个非空白字符；按原文持久化，
  不做换行规范化。是否放行由调用方显式选择：身份确认理由放行，Review 理由保持现行规则，行为不变。
- **落点**：设计 §7.6 与 §12，ADR 0020 Decision 5，执行计划 S4 的验收与路径预算（`test_review_domain.py` 为共享校验的 owner）。
  Business Lifecycle 3.1.0 未规定理由字符集，不需要修订。

## 9. S1 修订登记延期（2026-09-27）

- **DC26 / canonical row hash**：S1 采用 DC26 选项 3。`compute.py` 与 `canonical_row_hash_ipc.py` 已迁入
  `capabilities/canonical_row_hash/`，但尚无生产 journey 消费者；`import_rules` 不可达基线保留
  `canonical_row_hash.{compute,canonical_row_hash_ipc,contracts}` 三条，关闭阶段 **Phase 6**（Rust 覆盖与性能输入），
  理由见设计 §9 A6 与 `vnext/backend/tests/architecture_baseline.py`。
- **external_target_sync（设计 §9 A9）**：三模块（`contracts`、`_ledger_digest`、`_reference_executor`）保持生产不可达，
  登记为**外部目标延期**；真实外部目标 journey 出现时由 mutation_planning owner 重开，不在 S1–S2b 强行接入。

## 10. S1 复审测量、数据配对与真实数据格式缺口承接（2026-10-10）

以下三项按 repository owner 于 2026-10-10 在独立评审对话中作出的决定登记：

- **S1-F4 可达性基线**：批准将原包级 facade 规则测得的 10 个不可达模块更正为按导入符号展开后的 14 个。旧规则在包内任一模块可达时扩展整个 facade；修正后的规则只在可达模块实际导入对应 wrapper 符号时展开惰性导入，因此 `composite_signal._ast`、`_bind`、`_digest`、`materialize` 四项正确归入不可达基线，并延期至 S3 接入可达调用方后关闭。更正只适用于测量语义，不准新增真实 import 违例或运行时环；后续输出仍只减不增。执行计划 §7 与设计 §9 同步记录该边界。
- **DC22 数据集配对**：同一规模档的 `-1` 与 `-2` 是同一项目的 v1、v2；不同规模档代表不同项目，不跨档配对。`datasets.json` 中仅各档 v2 的 `pair_of` 指向同档 v1；S2b 同项目链路与 S4 项目身份预期据此执行。
- **真实数据格式缺口的承接**：S1 普查暴露的三处解析器与真实数据不一致，统一由[S1 合入后的治理修订计划](p5-arch-closure-post-s1-governance-plan.md) G2“真实数据格式保真前置”承接，时点为 S1 合入后、S2a kickoff 前：
  - 8 份数据在生产解析路径上的 `SET @saved_cs_client`（`table_access` 未放行 mysqldump 标准语句）；
  - t2 的 `COMPOSITE_LOGIC_FAILED`（`Digital forbids attribute 'value'`）：vnext `composite_signal/_ast.py` 把 legacy 与真实数据中小写的 `value` 误写为 `Value`；
  - t3/t4 `logics.xml` 超出 `max_xml_depth=64`。

  S1 未改动 G2 涉及的解析逻辑（`table_access` 的 SQL 语句白名单与 XML 预算、`composite_signal/_ast.py`）；S1 整体只在 `composite_signal` 的 facade 中搬迁了一个惰性包装，不改变行为。普查结果如实记录这些失败。生产上传当前只走 SQL 物化，composite 与 XML 解析器处于不可达基线（执行计划 §2 S1 的 14 项不可达中即有 `composite_signal._ast`、`table_access._xml_parser`、`table_access.xml` 等，均由 S3 关闭），因此 t2 的 composite 失败**不阻塞** S2b 的 DC22；第 2 次独立复审 N4 中“阻塞 S2b”的说法不成立，予以更正。t3/t4 的重复键与有效键扫描待 G2 修复后，随 G2 验收中的普查重跑补齐（治理修订计划 G2 验收）。

## 11. S1 合入后的治理决定（2026-10-10）

以下四项按 repository owner 在 S1 合入后的评审对话中作出的决定登记；细节见[治理修订计划](p5-arch-closure-post-s1-governance-plan.md)。

- **主线开发**：S2a 起直接在 `main` 上实施，阶段边界用附注 tag，审核对象为提交区间（执行计划 §8.1，AGENTS.md「主线开发与阶段边界」）。
- **G3 control DB**：采用基线 schema 方案 A，不再新增前向 migration；实施为独立一步，在 G2 之后、S2a 之前，先写规格并经 owner 确认（治理修订计划 G3）。
  在规格确认之前，设计 DC6 与 §10 的 migration 表述保持原状。
- **G8 重复有效键**：先由 G2 的普查重跑补齐统计（含整行完全相同与同键冲突的分类），再由 owner 决议处置方向；契约禁止去重与 last-write-wins，实现侧不得自行处理。
- **G2 阶段边界**：G2（含 G6、G7）独立审核通过后打 tag `p5-g2-exit`，S2a 的区间起点以其后的 tag 为准。
- **S1 旧 worktree 与分支**：留到 P5 exit 一并清理，清单见治理修订计划 G10。

## 12. S2b 真实数据补充决议（DC29，2026-10-12）

#### DC29 无主键表的兜底规则

- **来源**：S2b 真实数据旅程停止（`p5-s2b` handoff @ `3b85bc22cb` §5）：t1-v1 的 Preview 规范投影报 23 项 `KEY_MISSING`。
  这些表的源 DDL 没有 `PRIMARY KEY`，而命中的规则要求 `DDL_PRIMARY_KEY`。S1 普查 JSON 的 `effective_key_scan`（`status: partial`）
  早已列出这些表，此前没有提交 owner，属于审核方疏漏。
- **owner 判断**：真实业务数据中存在无主键表，业务上没有主键也能正常运行；这类表通常不是核心数据，重要表已由显式规则规定键。
  业务数据积累过程中还会出现新的无主键表，需要兜底规则，不能每次都靠紧急补规则。
- **决议**（repository owner，2026-10-12）：
  1. **适用范围**：SNAPSHOT_ONLY、BROWSE_ONLY 与 raw-PK 兜底（`STANDARD_RAW_PK_FALLBACK`）三类规则改为“源 DDL 有主键用主键，没有主键按
     keyless 处理”。其余规则不变：显式键规则、ordered 规则、protocol 规则、`device_cfg`（严格 DDL 主键）与 SKIP。
  2. **规则表示**：三类规则使用新的 canonical key policy `DDL_PRIMARY_KEY_OR_KEYLESS`；现有 `DDL_PRIMARY_KEY` 保持严格语义，
     现有 `EXPLICIT_KEYLESS` 保留给显式规则。新策略是规则侧事实，写入 manifest 每表条目；有效键（源主键，或为空）取自源 schema，
     `canonical_key_columns` 为空即该表按 keyless 存储。规则集版本提升，规则集 digest 随之变化。
  3. **存储**：keyless 表按多重集合保存。完全相同的重复行全部保留，不去重；投影前后行数相等；内容摘要与行顺序无关
     （沿用现有 keyless 内容摘要）。写入不做按行补丁：内容变化时整表重写，内容不变为 NOOP。
  4. **比较**：keyless 兜底表按整行多重集合比较（`KeylessPolicy.FULL_ROW_DIGEST_SET_DIFF`）。内容相同为 UNCHANGED；
     变化记为整行新增或删除，不产生字段级变化；表状态不为 DEGRADED，不触发 `KEY_DEGRADED` 风险。
     `DEGRADE_NO_COMPARE_KEY` 保留给其他无法确定比较键的情形。SNAPSHOT_ONLY/BROWSE_ONLY 仍只产出表级事实（DC16）。
  5. **主键出现或消失**：源 DDL 中某表新增或去掉主键，归 `SOURCE_SCHEMA`（设计 §4.5），该表整表重写。比较侧有效键变化仍按现有规则
     标记键降级、需要审核；这只在切换的那一次出现。
  6. **记录与可见性**：manifest 每表条目（策略与键列）是持久记录，随 commit 规范元数据保存，可据此查出某次提交中走兜底的表。
     Preview 对这类表给出表级只读提示 `KEYLESS_FALLBACK`（HTTP DTO 与 OpenAPI 同步），不进入风险规则、不阻断、不改变表状态。
     不新增登记表或持久状态机。
  7. **已知清单**：S1 普查的 8 份 dump 中每份 23–33 张，合计 35 个表名（取自 `p5-arch-closure-s1-census.json`）：
     `cnt_manage_cfg`、`comm_user_data`、`dev104_cfg`、`forwardtable_yc1`、`forwardtable_yc2`、`forwardtable_yk1`、`forwardtable_yt1`、
     `forwardtable_yx1`、`forwardtable_yx2`、`forwardtbl_lst_cs`、`forwardtbl_lst_dz`、`forwardtbl_lst_qt`、`forwardtbl_lst_yc`、
     `forwardtbl_lst_yk`、`forwardtbl_lst_ym`、`forwardtbl_lst_yt`、`forwardtbl_lst_yx`、`iec101_cfg`、`iec104_cfg`、`iec104gw_cfg`、
     `iec61850c_cfg`、`jdxx_cfg`、`mms_rp_cdc_index`、`nbridge_cfg`、`nr103d_cfg`、`nr103ht_cfg`、`out_time_cfg`、`project`、`sc_cfg`、
     `scada_cfg`、`sg_manage_cfg`、`sntp_cfg`、`vqc_cfg`、`wave_cfg`、`wf_cfg`。
     其中 `forwardtable_*` 命中 SNAPSHOT_ONLY，`project` 命中 BROWSE_ONLY，其余命中 raw-PK 兜底。S2b 全部按本决议处理，不猜测业务键。
  8. **升级为有键**：上线前由业务方筛查清单，把重要且有自然键的表补为显式键规则；上线前没有历史数据，不需要迁移。
     上线后，把 keyless 表改为有键会改变 canonical key，属于 `STORAGE_BREAKING`，按
     [Ruleset Activation and Migration](../contracts/ruleset-activation-and-migration.md) 走迁移（迁移操作尚未实现）。
  9. **不采用定期重建**：Dolt 按内容寻址，内容不变的重建不产生变化；内容变化是真实变化，应经 Preview 与 Submit。
     Submit 之外的定时写入违反 ADR 0015“不自动创建空 commit”，也破坏 commit 规范元数据与 `NO_CANONICAL_CHANGE` 的前提。
     Dolt 存储空间维护（如 `dolt gc`）与本决议无关，需要时另行立项。
- **落点**：
  - [Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md) §3 末句与 §9，版本升至 `3.2.0`（§8）：
    manifest 的 `contract_version` 写 `3.2.0`，读取接受 `3.0.0`、`3.1.0`、`3.2.0`。DC29 不提升 storage projection version：
    此前能投影成功的表，规范字节与内容摘要不因 DC29 改变（由 golden 证明）；新路径只用于此前被拒绝的表。
    （2026-10-16 更正：同一区间内 S2a-F1 的负零规范化 `26560b2595` 已把 storage projection version 从 `1` 提升到 `2`，
    原文“不变”不准确，见 S2b 审核 S2b-F3。）
  - [P3-R4 存储投影设计](p3-r4-storage-projection-design.md) §5.2 与[详细设计](p5-arch-closure-design.md) §4.1、§4.5 加注；
  - 执行计划 §2 S2b（内容 11 与验收）、§3 S2b（DC29 路径）、§8.5（S2b.8）。
- **停止条件**：Repository Service 无法无损写入或读回 keyless 表（含完全相同的重复行），或需要修改 Repository public contract 才能做到时，
  停止并交 owner。

## 13. 调试与取证分开、P5 的性能指标（DC30，2026-10-14）

#### DC30 调试与取证分开；P5 性能指标分三层

- **来源**：S2b 自 2026-10-12 起约 56 小时中，机器被占用约 47 小时：完整门禁 27 次（每次约 30 分钟，全部 exit 0，没有发现任何问题），
  真实数据运行约 23 次（合计约 33 小时）。其中 7 次各约 2 小时，都停在主机脚本伸进容器做核对的探针自身的错误上；3 次各 4–5 小时，卡在 t2 的 Submit
  直到超时。t1（6,097 行）走完一轮约需 2 小时。原因之一是 S2b 提示词把“每次修复 → 新 V → 完整门禁 → 真实数据”当成了调试循环（审核方的流程设计问题）。
- **决议**（repository owner，2026-10-14）：

  **一、调试与取证分开**（执行计划 §8.9）
  1. 调试期间只跑 focused 测试与出问题的那一段真实数据；可以在未提交的 worktree 上运行，结果不作为证据。
  2. 调试收敛后只取证一次：在最终 V 上运行完整权威 runner 一次，随后在同一 V 上完整运行真实数据一次。
  3. V 之后、H 之前只改 `vnext/backend/benchmarks/` 与其专属测试 `tests/test_real_dump_*.py` 时（不进入镜像），门禁结果沿用：
     在最终提交上补跑这两个测试文件与五包静态检查，重跑真实数据，carried 照常判定。改动产品代码则形成新的 V。
  4. 真实数据脚本支持只跑某一档、从指定步骤开始、开发模式保留栈；每一步完成即核对；先跑 t1，t1 通过后再跑 t2–t4；
     核对走公开 HTTP 接口（DC22），不再用 docker exec 在容器内执行核对代码。

  **二、P5 的性能指标分三层**（详细设计 §13）

  | 层 | 内容 | P5 中的处理 |
  | --- | --- | --- |
  | A 能跑完 | 每档每个 operation 都在保护超时内进入终态，全程走完 | 硬性，属于正确性；卡住或超时即失败 |
  | B 没有结构性的慢 | 耗时随数据量大致线性增长；读写与网络往返按表或按批计算，不按行；没有空等或重复全表读取 | P5 内修复（结构缺陷） |
  | C 常数级的慢 | Python 逐行处理、摘要、编码等正常但不够快的开销 | 只记录，不判定；进入 S5 测量与 Phase 6 候选 |

  1. **保护超时**：拿到第一次带时间戳的完整运行之前，每个 operation 上限 60 分钟，只用于区分慢与卡住；之后改为各步实测耗时的 5 倍、最低 5 分钟，按档写入脚本。
  2. **B 层的判断**：
     - 规模比例：按总行数，t2、t3、t4 约为 t1 的 16、44、72 倍；某一步的耗时增长明显超过行数倍数即为结构性问题；
     - 墙钟与 CPU：每步开始和结束时各读一次 backend、worker、repository-service 容器的 cgroup `cpu.stat`；墙钟远大于 CPU 时间为空等（B 层），CPU 饱和为计算（C 层）；
     - 修复 B 层问题时，用确定性的计数断言做回归（例如回放写入为批量语句、读取一张表的请求次数与行数无关），不在 CI 中设计时阈值（Performance Measurement Guidance §7）。
  3. **C 层的记录**：每次取证的真实数据运行，在 handoff 中给出各档、各步的墙钟与 CPU 时间（按设计 §13 的分类拆分），以及数据集 ID 与行数；不建设测量平台或基线状态机。
  4. B 层问题在本阶段改动过的路径上本阶段修；不在本阶段路径上的，登记到 S5 并在 handoff 写明。

  **三、业务容量目标**（owner 2026-10-14 给出，见本部分末两条）
  - 形式：最大项目规模（规范业务行总数、最大单表行数、表数、上传包字节数），以及该规模下 Preview、Submit、History 各自可接受的完成时间。
  - 不用 SQL 文件的文本行数：mysqldump 的扩展 INSERT 一行包含多条记录，行数取决于导出格式，与系统工作量不成比例。
  - 提供后即为 Performance Measurement Guidance §5 的“已接受的业务容量目标”，Phase 6 据此排序；P2 封存上限 `v8_supported_rows_max: 100000`
    （t3、t4 为 26.9 万、43.7 万行）同时复核。
  - **目标**（owner 2026-10-14）：最大项目约为 t4 的 2 倍，即约 87 万规范业务行、约 640 张表、上传包约 11 MB（t4：320 表、43.7 万行、5.6 MB）；
    该规模下 Preview 在 10 分钟内完成。Submit 与 History 暂不设定，S5 报告实测值后由 owner 决定。
  - **在 P5 中的用法**：不作为 P5 的通过门槛（P5 只以 A、B 两层判定）。S5 以 t4 的实测为基础，按 B 层确认的线性关系外推到目标规模，报告与 10 分钟的差距
    和主要开销，作为 Phase 6 的排序依据与退出目标；外推是推算而非实测，报告须写明。同时核对目标规模下的 replay SQL 字节数与上限 200 MiB 的余量，
    以及 P2 测量矩阵对 100 万行以内“受控预览”的标注是否需要更新（该标注只用于测量分类，生产路径不据此拒绝）。

  **四、缩短完整门禁**：backend 批次单进程约 24 分钟。S2b 合入后、S3 kickoff 前作为独立一步处理（治理修订计划 G11）。
- **落点**：执行计划 §2 S2b 与 S5、§8.1、§8.2、§8.9；详细设计 §13；治理修订计划 G11 与 §3；AGENTS.md「主线开发与阶段边界」。
- **修订（DC31，2026-10-15）**：第二部分 B 层由“P5 内修复”改为“只记录”，除非它使 A 层无法满足；第三部分的容量目标改为 Phase 6 的退出目标。见 §14 第三部分。

## 14. Catalog 上限、读取失败的终态与 P5 的性能范围（DC31，2026-10-15）

#### DC31 Catalog 上限按容量确定；读取类步骤的失败必须终态；P5 只验证正确性

- **来源**：S2b 停止 handoff（`p5-s2b` @ `668055f55e`，§8.2）。t4 v1 Preview 用时 2,581 秒（worker CPU 2,571 秒），Submit 用时 815 秒，均成功。
  之后公开 `GetVersionedCatalog` 首次请求 28 秒（Repository Service CPU 145 秒）后返回 `503 SERVICE_NOT_READY`，缓存后重试仍为 503。
  Contract 规定成功 Catalog JSON 上限为 256 KiB，超出时返回同一错误码：t3（200 表）未触发、t4（320 表）触发，原因高度可能是超限，但错误 DTO 不区分分支，只能推断。
  归档后重传 Preview 由 worker 经同一 API 读取基线 Catalog，收到 `RepositoryClientError`；worker 容器重启一次后没有重新领取任务，公开 operation 到
  3,602 秒保护窗口结束仍为 `RUNNING`、无 diagnostic，违反 DC30 的 A 层。按 t4 实测线性外推，目标规模（约 2× t4）的 Preview 约 86 分钟，与 10 分钟目标相差约 8–9 倍。
- **决议**（repository owner，2026-10-15）：

  **一、Catalog 上限（保持单一接口）**
  1. `GetVersionedCatalog` 保持一次返回整个 Catalog，不分页，不新增接口。
  2. 上限按容量确定：`MAX_CATALOG_JSON_BYTES` 取 t4 Catalog 成功响应 JSON 字节数的 4 倍并向上取整到 MiB（覆盖约 2× t4 的目标规模，另留 2 倍余量）。
     字节数与取值写入 handoff 和 Repository Service Contract。
     - 补充（owner 2026-10-15，原 t4 调试栈已删除）：调试阶段用离线估算取值，不为测量重建 t4 栈。在进程内对 t3、t4 的 v1 运行存储投影，
       用 Catalog 的 wire 模型序列化投影后的表结构、主键与行数并计字节（不读出行数据，不经 Docker）。t3 低于、t4 高于 256 KiB 即确认停止时 503 的原因；
       另以合成 Catalog 的 focused 用例证明“超限 → 原错误码”的机制。
     - 取证运行经公开接口记录各档 Catalog 的实际字节数；上限低于 t4 实际值的 3 倍（目标规模 2 倍外加 1.5 倍余量）时，按实际值重新取值并形成新的 V。
     - 离线估算做不出时，授权在开发模式下只重建 t4 v1（上传、Preview、Submit，保留栈），用不提交的临时改动测量。
  3. 响应超限不再返回 `503 SERVICE_NOT_READY`（它表示“暂时未就绪，可重试”，而超限是确定性的）：改为专用错误码 `RESPONSE_LIMIT_EXCEEDED`，HTTP 500，
     client 与 worker 按不可重试处理。`GetOperation` 的 256 KiB 上限数值不变，超限时同样改用该错误码。
  4. Repository Service Contract、wire 常量、OpenAPI 与 golden 直接改到目标形态，不建兼容层（AGENTS.md「项目前提」）。
  5. S5 的容量核对在 replay SQL 200 MiB 之外，加上目标规模下 Catalog 字节数与新上限的余量。

  **二、读取类步骤的失败必须进入终态**（属于 A 层，即正确性）
  1. Preview 与 History 比较等 `PURE_RECOMPUTE` 步骤遇到的仓库读取错误分两类，都不得落入 `UNCLASSIFIED`：
     - 临时性（连接失败、超时、真正的 `SERVICE_NOT_READY`）：按 `RETRYABLE` 在现有恢复预算内重试，用尽后 operation 为 `FAILED`；
     - 确定性（4xx、`RESPONSE_LIMIT_EXCEEDED`、契约或解码错误）：按 `PERMANENT`，operation 直接为 `FAILED`。
     两类都带公开 operation API 可见的 diagnostic code。不用 `MANUAL_RECOVERY_REQUIRED`：这些步骤没有外部副作用，用户重新发起即可。
  2. handler 抛出的异常不得使 worker 进程退出。进程因外部原因退出时，重启后的 worker 须在“租约时长加退避”之内接管过期租约，按
     [R5 重试、接管与副作用恢复设计](p4-r5-retry-takeover-effect-recovery-design.md)的处置进入重试或终态。本次“重启后未重新领取、operation 保持 `RUNNING`”
     的具体路径由实施方以 focused 测试复现，写入 handoff。
  3. 测试：focused 故障注入参数表（Catalog 确定性错误 → `FAILED` 并带 diagnostic；临时性错误 → 重试后成功，或预算用尽后 `FAILED`）；
     一条 Compose 旅程在 Preview 进行中终止 worker，operation 最终进入终态（已有覆盖 Preview 的同类旅程时复用，不另建）。
  4. 停止条件：需要新增 operation 或 step 状态、修改 R5 恢复设计的处置表，或改变 `EXTERNAL_EFFECT` 步骤的语义。

  **三、P5 只验证正确性，性能整体留给 Phase 6**（修订 DC30 第二、三部分）
  1. P5 的通过条件只含正确性：真实数据各档、各步结果正确，并保留 A 层——每个 operation 在保护超时内进入终态。卡住、无终态或超时属于正确性问题，照常阻断。
  2. B 层由“P5 内修复”改为“只记录”：取证运行照常记录各步墙钟、CPU 与规模比例，疑似结构性的慢写进 handoff 并登记到 S5，P5 不修；
     例外是它使 A 层无法满足（某一步超出保护超时）。
  3. 调试阶段可在 t4 Preview 运行期间从主机侧采样一次热点（例如 py-spy），不改产品代码，结果写进 handoff 的 C 层表；容器权限不允许时跳过并说明。
  4. 业务容量目标（约 2× t4，Preview 10 分钟内）是 Phase 6 的退出目标。S5 照常以 t4 实测外推并报告差距，写明 B 层未经修复确认，外推只用于排序。
  5. Phase 6 可按需重新设计、重写实现（包括 Rust、缓存、存储与读取路径）。约束是公共 Contract 与业务语义：需要改 Contract 时走 owning Contract 修订；
     项目没有兼容要求，不建兼容层。
  6. 对照基准：S2b 取证运行在 handoff 中按档、按版本记录可经公开接口取得的结果事实——规范状态摘要、Preview 表级状态计数、Submit 结果、History
     比较的记录总数与 bundle / surface 摘要（不含行数据；按类型的记录数没有公开接口，2026-10-16 按 S2b 复审更正）。Phase 6 改写后在同一数据集上应得到相同结果，作为改写的正确性对照。
- **落点**：执行计划 §2 S2b 内容 12 与验收、§3 S2b、§8.5 S2b.9、S5；详细设计 §13；Repository Service Contract（由 S2b 实施方按本决议修改）。

## 15. S5 测量范围扩展为 Phase 6 的下界输入（DC32，2026-10-17）

#### DC32 S5 的测量按阶段、按表分段，并测基本操作的吞吐

- **来源**：[Phase 6 规划讨论稿](p6-planning-discussion.md) §3、§9 V2。Phase 6 改为“先测下界、再定目标”，需要每个阶段的耗时构成、逐表成本和本机基本操作的吞吐。
  设计 §13 原定的单链路测量不足以支撑：旧实现的逐表统计已经不存在，需要重新实测。
- **决议**（repository owner，2026-10-17）：讨论稿的 V2 并入 S5。S5 的测量在设计 §13 的基础上增加以下内容。

  **一、阶段分段**
  1. Preview、Submit、History 三类 operation 的每一步，拆到以下阶段：解析与物化；规范投影与表摘要；基线读取（RS I/O 与 Arrow → Python 转换分开）；
     比较；风险与 surface；artifact 写入；mutation planning 与回放；Repository 导入与提交。每段记录墙钟与 CPU 时间。
  2. 分段至少覆盖 t4 的 v1 Preview、重传 v1 Preview、v2 Preview、v1 Submit、v2 Submit 和 History；t1–t3 至少覆盖 v2 Preview，用于看规模关系。

  **二、逐表成本**
  1. 每张表、每个阶段记录墙钟与线程 CPU 时间，以及结构特征：行数、列数、比较角色、是否 ordered、产出的记录数、本次是否有变化。
  2. 输出只含表名与数字，不含行数据。完整明细存放在决议记录 §4 授权的外部目录；handoff 给出按比较角色、行数区间汇总的分布表，以及耗时最高的若干张表。

  **三、基本操作吞吐**
  1. 在本机分别测量：包解压；现有 SQL 解析；Arrow → Python 转换；现有摘要计算，以及标准库可用的 SHA-256 与 BLAKE2b；Arrow IPC 写入与内存映射读取；
     RS 逐表 Arrow 读取；同样规范数据直接导入 Dolt（在外部临时目录中的 Dolt 仓库，测完删除）。
  2. BLAKE3 一并测量（owner 2026-10-17 补充授权）：S5 实施方在 backend 的 dev group 中增加 `blake3`，按 AGENTS.md「改依赖」用 `uv add --dev` 精确钉版本
     （取实施时 PyPI 上已发布至少两周的最新稳定版），lock 保持 canonical PyPI identity（`test_canonical_lock_identity.py`），handoff 记录版本与 lock 的变化。
     - 只授权 `blake3`；不授权其他依赖变化。只用于 `benchmarks/` 中的测量，不进入生产代码。
     - backend 镜像构建复制 `uv.lock`，这属于强制重建项；S5 的最终门禁本来就要 fresh 构建，不另增门禁。
     - 如果项目所用的 Python 版本没有可用的预编译 wheel，需要在构建时编译 Rust，则不增加该依赖，在 handoff 中说明，BLAKE3 的吞吐留给讨论稿 V1。
     - Rust 内核的吞吐仍留给 V1。

  **四、两个时间指标**
  1. 每个 operation 分别记录“用户可见时间”（受理到结果可读）与“完成时间”（operation 终态）；当前实现中两者相同，照样分开记录，作为 Phase 6 的对照。
  2. 条件允许时，按同一口径测一次旧实现（`legacy/backend_vnext/`）的 t4 Preview 两个指标；旧实现的运行环境无法恢复时，在 handoff 中说明原因，不阻塞 S5。

  **五、实施方式与边界**
  1. 测量在进程内调用生产 capability 的入口完成（同 `real_dump_census.py` 的方式），不另写一套逻辑；需要容器内的数据时，用 S2b 起的 journey 计时与 cgroup CPU 记录。
  2. 不为测量改动产品代码，也不新增常驻的计时机制。确需在产品代码内计时的，按 G11b 的先例：使用不提交的临时补丁，补丁与日志存放在 worktree 外。
  3. 测量属于调试运行（DC30），不是门禁证据；它不改变 S5 的通过条件（DC31：P5 只验证正确性），但测量结果是 S5 的必交物。
  4. 测量脚本与其测试放在 `vnext/backend/benchmarks/` 与 `tests/test_real_dump_*.py`。
- **落点**：执行计划 §2 S5、§3 S5；详细设计 §13；Phase 6 规划讨论稿 §9 V2、§10 第 7 项。

## 16. 缩短阶段取证耗时（DC33，2026-10-17）

#### DC33 按包沿用测试结果；真实数据按阶段改动面确定范围

- **来源**：owner 要求后续过程尽量避免全量运行。权威 runner 约 33 分钟（backend 的 Compose 旅程 25 分钟、RS serial 6 分钟），真实数据 t1–t4 约 5.5 小时（t4 为 2.8 小时）。
- **决议**（repository owner，2026-10-17）：

  **一、按包沿用测试结果**：包的测试输入闭包与上一次已验证 V 相同时，沿用那次的结果，不再运行。闭包的定义、完整性实测、沿用条件、工具与文档改动，
  按[治理修订计划](p5-arch-closure-post-s1-governance-plan.md) G12 第 1 项实施并独立审核后生效；S5 最终门禁与发布门禁不适用。

  **二、真实数据按阶段改动面确定范围**（修订 DC30 第一部分的取证要求）：
  1. 取证的真实数据范围在阶段 kickoff 时写明，阶段退出前由 owner 确认；范围之外的不变量依靠更小的档位或既有的 focused / Compose 覆盖。
  2. S3 为完整 t1–t4（已在进行；2026-10-17 第二次停止后，owner 修订为新 V 上 t4 完整、t1 冒烟，t2/t3 沿用 `f73deee604` 的结果，见治理修订计划 §3 第 9 项）；S4 为 t1–t3 完整运行、t4 只运行 v1 提交与 v2 Preview、`DIFFERENT_PROJECT` 用小档之间的跨档上传验证；S5 最终候选为完整 t1–t4。
  3. 不在 P5 内建设多档并发运行的基础设施。
- **落点**：治理修订计划 G12；执行计划 §2 S4、§8.9；AGENTS.md「主线开发与阶段边界」。第一部分生效后，再同步 AGENTS.md「跑测试」「镜像身份等价」与 testing-conventions。
