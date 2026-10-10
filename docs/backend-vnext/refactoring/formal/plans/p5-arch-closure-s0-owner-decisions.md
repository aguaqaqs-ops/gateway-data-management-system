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
