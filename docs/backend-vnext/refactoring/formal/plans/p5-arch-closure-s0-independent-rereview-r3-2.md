# P5 架构收口 S0 文档 r3 独立复审报告（第二份）

- 状态：独立复审报告（docs-only）。本报告不接受 ADR、不修改 Contract 版本、不改变任何阶段状态，也不构成实现授权。
- 日期：2026-09-26
- 复审者：[r2 第二份独立复审](p5-arch-closure-s0-independent-rereview-2.md)的复审者，也是 DC23–DC27 的记录人；未参与 r1 起草、
  S0 审核、r2 或 r3 修订。按[修订处置表](p5-arch-closure-s0-revision-disposition.md) §8.1，r3 可由未参与 r3 修订的 reviewer 只核对差异。
- 复审依据：[纵切指南](../guides/slice-design-execution-and-review-guide.md) §3–§6、`AGENTS.md`、
  [testing-conventions](../../../testing-conventions.md)、
  [比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)；关闭标准以两份 r2 复审报告
  （[第一份](p5-arch-closure-s0-independent-rereview.md)、[第二份](p5-arch-closure-s0-independent-rereview-2.md)）为准；
  DC1–DC27 以 [Owner 决议记录](p5-arch-closure-s0-owner-decisions.md) 为准，不重新裁决。处置表 §8 的自评只作线索。
- 结论：**定向修订**（剩余修正量小，复核只需核对相应差异）

## 1. 结论与理由

**定向修订。** r3 处置了两份 r2 复审的全部阻塞项与建议，并把 DC23–DC27 落到了设计、计划、ADR 与附录。逐项核对后：

- 受理判定顺序已改为“授权与 exact scope → same-key 重放 → 其余受理校验”，与现行实现一致，并有既有用例作为 owner。
- 附录 B.2 同时修订 Ruleset Activation §1 与 §5，Submit 的边界统一为“T1 冻结规范产物之后（含 PREPARED）”，Preview 在受理时
  冻结规则集 digest。并入后 Ruleset Activation 不再自相矛盾。
- `CommitCanonicalMetadataPort` 有唯一的新增 owner，manifest digest 不符按 DC25 稳定失败，附录 B.3 的范围与之一致。
- DC26 选定精确放行 `capability:canonical_row_hash → ext:compute`。本复审在临时副本中模拟了迁移与放行，`import_rules` 的输出
  与 S1 验收所列条目一致（R3E2）。
- S2a/S2b 路径预算覆盖了被删符号的全部使用方（R3E3）；附录 A、B 的插入点、替换文本与 R4 §4.2 的处理均已修正。

仍有 2 项阻塞缺口。它们都只涉及定义或措辞，但一项会把错误的判据写进 ADR 0018 与设计，另一项会让并入后的 Canonical Storage
§4 前后矛盾，因此不能判通过：

| ID | 摘要 | 影响的关闭项 |
| --- | --- | --- |
| RR3-F1 | 用来标记 schema 差异来源的“存储规则事实”包含随源 schema 变化的字段（retained 列、按 DDL 主键得出的 canonical key）。同一规则下，源表增列或改主键会被标为 `STORAGE_PROJECTION_POLICY`，而不是 `SOURCE_SCHEMA` | RV1-F2、RV2-N2 |
| RR3-F2 | manifest `canonical_schema_digest` 的用途被写成“Repository STRUCTURAL 的物理结构核对”。Repository 从不读取该摘要；B.1 按字面并入后与 Canonical Storage §4 自身的表述矛盾 | RV1-F2、附录 B.1 |

另有 3 项非阻塞建议（RR3-N1–RR3-N3），见 §5.2。其中 RR3-N1 的表述与已接受的 Canonical Storage §5 冲突，建议随同一轮修正一并处理。

RR3-F1 的成因之一是我在 r2 第二份复审 RV2-N2 中把 retained 列与 canonical key 也称为“规则侧事实”，这一措辞不准确，r3 沿用了它。
本报告据实判定，不因此降低或提高其严重程度。

## 2. 复审对象

```yaml
docs_branch: p5-arch-closure-docs
docs_worktree: /home/dev/gdds-p5-arch-closure-docs
rereview_commit: ffba1138ef0b8e7f3646c1fd883086b803ece63d   # r3；复审开始时的 HEAD
diff_base: f984381ab3        # DC23–DC27 决议记录；已核对与记录人所写文本逐字一致（85 行新增，0 行删除）
concurrent_commit: 783acefe94   # 复审期间分支上新增的另一份 r3 复审报告；只新增该报告，被复审文件与 vnext/ 未改动
code_inspection_base: 217236980350d523101936af5464fbbd9ad66f88
vnext_diff_check: "git diff --stat 2172369803 ffba1138ef -- vnext" 输出为空
r3_diff: "git diff --stat f984381ab3 ffba1138ef" 为 9 个文件，+427 / -180
main_workspace_usage: 只读使用 vnext/backend/.venv
```

本报告的结论在看到 `783acefe94` 之前形成，未参考该报告。

被复审的 r3 差异：

- [详细设计](p5-arch-closure-design.md)（含附录 A、B）、[执行计划](p5-arch-closure-execution-plan.md)、
  [Entry Brief](p5-arch-closure-s0-entry-brief.md)；
- ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
  [0019](../adr/0019-commit-canonical-metadata-authority.md)、
  [0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)（ADR 0021 在 r3 中未改动）；
- [P5 §2A.4.1](p5-business-vertical-slices-design.md#p5-architecture-review-20260925)、[formal README](../README.md)、
  [修订处置表](p5-arch-closure-s0-revision-disposition.md) §8。

路径与行号约定：以 `vnext/` 开头的路径相对仓库根目录，行号以 `2172369803` 为准；文档行号以 `ffba1138ef` 为准。处置表以 RV1-、RV2-
前缀区分两份 r2 复审的编号，本文沿用。

## 3. 核查、实验与局限

### 3.1 实验

脚本放在复审者的临时目录，未入库。本轮的 Python 实验设置 `PYTHONDONTWRITEBYTECODE=1`，或在临时副本上运行。

| # | 实验 | 结果 |
| --- | --- | --- |
| R3E1 | 基线确认：HEAD、`vnext/` 差异、r3 差异统计；`f984381ab3` 与记录人所写文本逐行对照 | 与 §2 一致；`f984381ab3` 只新增 85 行，内容与记录人文本相同 |
| R3E2 | DC26 模拟：在 backend `src` 与 `import_rules.py` 的临时副本中，把 `compute.py`、`canonical_row_hash_ipc.py` 移入 `capabilities/canonical_row_hash/`，并只对 `(capability:canonical_row_hash, ext:compute)` 这一对 zone 放行 | 违例 52 条（两条 unowned-root-module 消失，没有新增 layer 违例）；该 owner 下 compute、contracts、ipc 三个模块不可达，与执行计划 S1 验收所列一致 |
| R3E3 | 路径预算普查：对 S2a 删除的 14 个符号与 S2b 删除的 18 个符号，逐个 grep 使用方（仅 `.py`），按路径后缀与执行计划 §3 对应阶段的预算比对 | 全部使用方都落在对应阶段预算内（S1 删除的 `cache/`、`http/runtime.py`、comparison provider 除外） |
| R3E4 | 存储规则事实探针：用 `derive_storage_rule_view` 对同一规则、只改源 schema 的两份 descriptor 求存储视图 | `com_cfg`（EXPLICIT）源表增列 `remark`：retained 由 `(index, name)` 变为 `(index, name, remark)`；回退规则（DDL_PRIMARY_KEY）源表主键由 `(a)` 改为 `(a, b)`：canonical key 随之改变。两例的 storage rule digest 都改变 |
| R3E5 | manifest `canonical_schema_digest` 的消费方普查（backend、repository_service、repository_contracts、repository_client 源码） | 只有 mutation planning 判断表 schema 是否变化（`vnext/backend/src/gateway_backend/capabilities/mutation_planning/_planner.py:290`）、发布时的自洽核对（`vnext/backend/src/gateway_backend/capabilities/storage_projection/publish.py:306`）、manifest digest 载荷与包编解码；Repository Service 中没有任何使用 |
| R3E6 | r3 引用的现行事实核对 | 既有 T1 重放用例存在（`vnext/backend/tests/test_submit_transactions.py:2126`、`2180`）；Archive 理由在 HTTP 与 Application 两层都是 1–4096 UTF-8 字节（`vnext/backend/src/gateway_backend/operations/contracts.py:27`、`vnext/backend/src/gateway_backend/application/archive/contracts.py:26-27`、`58-66`）；既有 control DB adapter 测试为模块级 unit（如 `vnext/backend/tests/test_sqlite_submit_repository.py:27`）；ADR 0001 §4 与 Contract Taxonomy §4.4 支持 capability facade 直接调用 PyO3 production provider |
| R3E7 | 链接、锚点与路径：r3 改动的 9 个文件及决议记录 | 链接与锚点 0 个问题；反引号中的源码与测试文件名，除执行计划标为新增的文件外均存在 |

### 3.2 局限

- 本轮只核对 r3 差异，并对 r2 已关闭项做回归抽查，没有重新完成 r2 的全部核查。
- R3E2 只模拟了 A6 的迁移与放行，不代表完整的 S1 结果。
- R3E3 以符号 grep 为主；只改导入路径的测试按执行计划 §3 在 handoff 中列出，不在本轮核对范围。
- worktree 的 `vnext/` 下有 2026-09-25 生成的 `__pycache__`（gitignored），不是本复审产生；复审期间没有新增或改动任何 `.pyc`。
- 没有真实 dump，没有构建镜像，没有跑全量测试。

### 3.3 镜像决策记录（testing-conventions“每轮评审记录”）

```text
Current HEAD: ffba1138ef（被复审文档）；复审期间分支 HEAD 前进到 783acefe94（只新增另一份 r3 复审报告）
Container rebuild required: no
Reason: docs-only 独立复审；未触碰 image/deployment/container 边界；实验只读执行 worktree 源码或其临时副本
Last verified image revision: none（本轮）
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: 无；各阶段门禁按执行计划 §6
Required execution point: 不适用
```

## 4. 两份 r2 复审的关闭情况

文档位置为 r3 行号。

| 编号 | 判定 | 依据 | 说明 |
| --- | --- | --- | --- |
| RV1-F1、RV2-F1 | 已关闭 | 设计 §7.6（499–511）、§12（623）；ADR 0020 Decision 5（42）与 Required Verification（67）；执行计划 S4（198） | 顺序与现行实现一致（`vnext/backend/src/gateway_backend/application/submission/accept.py:74-76`、`142-160`）；重放只越过其后可漂移的校验；既有用例覆盖 scope 映射失效与只有 head 漂移两种情形，S4 补撤权用例 |
| RV1-F2（RV2-N2 同源） | 部分关闭 | 设计 §4.1（156、164–177）、§4.5（276–278）；附录 B.1（691–693）；ADR 0018 Decision 1（38）、3（48）、Alternatives（72–73） | 两个摘要的名称、owner、列序语义、commit 侧来源与“都不进入 `canonical_binding`”已写明。存储规则事实的定义错误（RR3-F1）；manifest 摘要的消费方写错（RR3-F2） |
| RV2-F2（RV1-F3 前半同源） | 已关闭 | 附录 B.2（701–711）；设计 §4.6（285–286）、§4.8（328）、§4.9（340–348）、§12（613）；ADR 0019 Decision 6 与 Consequences；执行计划 S2a 第 6 项 | §1 的恢复规则、§1 第二段“当前不采用”、§5 末句替换与“不增加 mismatch 分支”的范围说明，并入后互不矛盾；原引文逐字存在（Ruleset Activation 20、22–25、69 行） |
| RV2-F3（RV1-F5 同源） | 已关闭 | 设计 §5.1（357–361）、§12（618）；附录 B.3（713–720）；ADR 0019 Decision 1、7、Required Verification；执行计划 S2b 验收（159–161）与测试预算（329–330） | owner 唯一且标为新增，参数表覆盖跨 Repository、未登记、scope 外、INITIAL、digest 不符与历史版本 |
| RV2-F4 | 已关闭 | 设计 §9 A6；执行计划 S1 验收（95–97）、§3 S1（234、255–262） | R3E2；放行只针对一个 owner 的一条 zone 边，符合 P5 §2A.2“不新增按 basename 或整层放行的豁免” |
| RV2-F5（RV1-F4 同源） | 已关闭 | 执行计划 §3 S2a（272–304）、S2b（306–347）；设计 §5.5 | R3E3 |
| RV2-F6 第 1–4 点（RV1-F3 后半同源） | 已关闭 | 附录 A（659–661）、B.3（716）、B.4（722–746）、B.5（748–758）、B.6（760–790）；设计 §11；ADR 0018 Consequences | 插入点改为整句或整段之后；B.4 覆盖 Taxonomy §4.4、§4.6、§13；B.5、B.6 给出替换文本；R4 §4.2 统一为只加取代标注。B.4 §4.4 替换图的方向见 RR3-N2 |
| RV2-F6 第 5 点、DC27 | 已关闭 | 附录 B.1（695–699）；设计 §4.2 JSON 行；ADR 0018 Decision 6；执行计划 S2a 第 3 项 | manifest `contract_version` 自 S2a 记录 3.1.0，读取接受历史版本 |
| RV2-N1 | 已关闭 | 设计 §4.4（259–266）、§12（606–607）；ADR 0018 Decision 5 | 触发条件含 business schema digest；表级内容事实计入变化计数，并有 surface owner |
| RV2-N3 | 已关闭 | 设计 §5.1（361）；ADR 0019 Decision 1 | 读取与写入分开校验；owner 为 `test_commit_canonical_metadata.py` |
| RV2-N4 | 已关闭 | 设计 §12（616–617）；执行计划 S2b | 新增 integration 模块，unit 模块只保留包 checkpoint 复用 |
| RV2-N5 | 已关闭 | 设计 §4.1（150）、§4.9、§7.6（491）；ADR 0019 Decision 5；ADR 0020 Decision 5 | 四点均已处理；理由校验复用的 owner 见 RR3-N3 |
| RV1 §4（E-e 与 R1 表述） | 已关闭 | 设计 §2.2（105）；P5 §2A.4.1（238） | — |
| RV1 §6（`HistoryIntegrityFailure`、标识符引用） | 已关闭 | 设计 §4.3（222）、§5.5（406） | — |
| RV2 §6 附带意见 | 基本关闭 | 设计 §4.7、§4.8（319）、§5.1、§13；执行计划 S1、S2a；附录 B.6 | §4.8 对保护转移范围的表述见 RR3-N1 |

DC23–DC27 的落点均与处置表 §8.4 一致：DC23 见附录 B.2 与设计 §4.9（348）；DC24 见设计 §4.6、§4.9、§10（569）与执行计划 S2a；
DC25 见设计 §5.1（360）、§5.5 与附录 B.3；DC26 见设计 §9 A6 与执行计划 S1；DC27 见设计 §4.2、附录 B.1 与执行计划 S2a 第 3 项。

回归抽查：`RULESET_BINDING_MISMATCH`、“两侧规则集 digest 相等”、`TEXT` 主键停止条件与 INITIAL 的旧说法没有重新出现；r2 已关闭
的 F1–F11 关闭依据在 r3 中未被改动或削弱。

## 5. 新 findings

| ID | 类别 | 阻塞 | 标题 |
| --- | --- | --- | --- |
| RR3-F1 | 已证实缺陷 | 是 | 存储规则事实包含随源 schema 变化的字段，schema 差异来源会被错误标记 |
| RR3-F2 | 已证实缺陷 | 是 | manifest `canonical_schema_digest` 的用途写错，附录 B.1 不能按字面并入 |
| RR3-N1 | 已证实缺陷（表述） | 否 | T1 后其余 Preview artifact “继续由 PreviewResult 持有”与 Canonical Storage §5 冲突 |
| RR3-N2 | 非阻塞建议 | 否 | 附录 B.4 的 Taxonomy §4.4 替换图与 B.6 的依赖方向不一致 |
| RR3-N3 | 非阻塞建议 | 否 | 身份确认理由复用 Archive 的校验函数，未写明共享校验的 owner |

### 5.1 阻塞项

#### RR3-F1 存储规则事实包含随源 schema 变化的字段，schema 差异来源会被错误标记

- **类别**：已证实缺陷（定义错误）；阻塞。
- **位置**：设计 §4.1（156 行）、§4.5（278 行）、§4.9（340 行）、§5.4（385 行）、§12（608 行）、附录 A 第 6 项（675 行）；ADR 0018
  Decision 3（48 行）、Alternatives（73 行）；ADR 0019 Decision 1（37 行）；执行计划 S2a 第 4 项（119 行）。
- **依据（已证实）**：
  - 设计 §4.1 把存储身份定义为“manifest 每表已记录的 canonical key policy、canonical key、ordered policy 与 retained/structural/
    dropped 列”，并说明“存储身份不用 schema 摘要表示，因为规范 schema 还取决于源 schema”。§4.5 规定：两侧存储规则事实不同标为
    `STORAGE_PROJECTION_POLICY`，事实相同而 business schema 不同标为 `SOURCE_SCHEMA`。
  - 但其中两项同样取决于源 schema：
    - retained 列等于源 descriptor 的列减去规则的 dropped 列
      （`vnext/backend/src/gateway_backend/capabilities/storage_projection/view.py:35-39`）；
    - `DDL_PRIMARY_KEY` 策略下的 canonical key 取自源 descriptor 的主键（同文件 `43-46`）。这包括回退规则与 `device_cfg` 规则，
      即所有未单独配置规则的表。

    两者都原样写入 manifest（`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:279-282`）。
    只有 key policy、ordered policy、structural 列、dropped 列，以及 `EXPLICIT` 策略下的显式键，完全来自规则
    （`view.py:33`、`41-42`、`80-83`）。
  - R3E4：同一规则下，源表增列、或回退规则表在 DDL 中改主键，都会改变 retained 或 canonical key。
- **触发场景**：用户在上传中给某表新增一列（最常见的 schema 变化），或改动未单独配置规则的表的主键。按 r3 的判据，两侧存储规则
  事实不同，来源被标为 `STORAGE_PROJECTION_POLICY` 或 `BOTH`；只有类型、长度、可空性这类变化才可能被标为 `SOURCE_SCHEMA`。
- **影响**：Canonical Storage §7 要求的 schema 变化来源标记，在最常见的情形下出错。审核人会看到“规则变更”，而规则并没有变。比较
  本身不受影响：对齐始终按列名与有效键进行。但该判据会随 ADR 0018 一并接受，S2a 按它编写 `test_comparison_planning.py` 时，要么
  固化错误语义，要么在实施中途回到 owner 修订。
- **最小修正方向**：把“存储规则事实”限定为只来自规则的字段：canonical key policy、ordered policy、structural 列、dropped 列（含
  理由），以及 `EXPLICIT` 策略下的显式键；retained 列与按 DDL 主键得出的 canonical key 属于 schema，不计入。这些字段都已记录在
  现有 manifest 中，不需要新增持久字段。同步修正 ADR 0018 Decision 3 中“键”与“列处置”的措辞，以及 Alternatives 的理由。
- **关闭标准**：上述位置对存储规则事实的定义一致，且只含规则侧字段。`test_comparison_planning.py` 的共享参数表至少覆盖：同一规则下
  源表增列、改 DDL 主键 → `SOURCE_SCHEMA`；规则改变 dropped 列或显式键 → `STORAGE_PROJECTION_POLICY`；两者同时发生 → `BOTH`。

#### RR3-F2 manifest `canonical_schema_digest` 的用途写错，附录 B.1 不能按字面并入

- **类别**：已证实缺陷（候选 Contract 文本不准确）；阻塞（附录 B.1 不能按字面并入）。
- **位置**：附录 B.1 的 §4 增补（693 行）；设计 §4.1 对照表的“用途”行（174 行）；ADR 0018 Alternatives（72 行）。
- **依据（已证实）**：
  - r3 写道，该每表 schema digest“服务 manifest/package 与 Repository STRUCTURAL 的物理结构核对”。
  - Repository 从不读取该摘要：
    - Canonical Storage §4 规定 Repository Service 只消费 manifest 中的 required table、schema 与 row count 做 structural check
      （92–94 行）；
    - §6.1 规定的 package `manifest.json` 只含表名、列定义、主键与行数，没有每表 schema digest；
    - STRUCTURAL 比较的是这些列与主键（`vnext/repository_service/src/gateway_repository_service/versioned_import/verification.py:263-311`）；
    - Repository Service 源码中没有任何对 `canonical_schema_digest` 的引用（R3E5）。
  - 它的实际消费方是：mutation planning 用它判断表 schema 是否变化（按 DDL 列序；
    `vnext/backend/src/gateway_backend/capabilities/mutation_planning/_planner.py:290`）、发布时的自洽核对
    （`vnext/backend/src/gateway_backend/capabilities/storage_projection/publish.py:306`），以及 manifest digest 的载荷。
- **触发场景**：S0 接受时按 B.1 并入 Canonical Storage §4。
- **影响**：并入后，§4 一处说 Repository 只消费表、schema 与行数，另一处说该摘要服务 Repository STRUCTURAL，前后矛盾。读者会误以为
  Repository 校验 schema digest，或以为改动该摘要会影响 STRUCTURAL。“不可互换”的结论本身正确，只是理由与消费方写错。
- **最小修正方向**：三处改为：该摘要用于 manifest 发布时的自洽核对与 mutation planning 的 schema 变化判断，并计入 manifest digest；
  Repository STRUCTURAL 比较的是 package `manifest.json` 中的列、主键与行数，不使用该摘要。ADR 0018 Alternatives 的理由相应改为
  “改变它的语义会影响 mutation planning 与已接受的 Canonical Storage §4 定义”。
- **关闭标准**：设计、附录 B.1 与 ADR 0018 对该摘要消费方的表述与源码一致；B.1 并入后，Canonical Storage §4 内部不再矛盾。

### 5.2 非阻塞项

#### RR3-N1 T1 后其余 Preview artifact “继续由 PreviewResult 持有”与 Canonical Storage §5 冲突

- **类别**：已证实缺陷（表述）；非阻塞，建议随 RR3-F1、RR3-F2 一并修正。
- **位置**：设计 §4.8（319 行）、§10（571 行）。
- **依据**：
  - r3 写“本设计只转移上述 Attempt 需要的 artifact，其余继续由 PreviewResult 按 P5 §9 的规则持有”。
  - Canonical Storage §5（128 行）规定，full-row artifact 只在“尚未被接受的 current Preview 或 active SubmitAttempt 需要时”持久 pin，
    且“历史 Preview 引用本身不继续 pin”。
  - 现行 T1 在转移后清除 `current-preview` 与 `preview-operation` 两个 owner 的保护
    （`vnext/backend/src/gateway_backend/application/submission/accept_transaction.py:321-335`）。
- **影响**：按字面实现时，其余 Preview artifact 会在受理后继续被 pin，直到 Workspace 释放。这比 Contract 规定的保留时间更长，违背
  “第一版不长期保存重复 full-row archive”。没有数据丢失。
- **建议**：改为“其余 Preview artifact 在 T1 随 Preview 的保护一并解除（Canonical Storage §5），此后按 P5 §9 的 TTL 做 best-effort
  清理”；§10 同步。

#### RR3-N2 附录 B.4 的 Taxonomy §4.4 替换图与 B.6 的依赖方向不一致

- **类别**：非阻塞建议。
- **位置**：附录 B.4（724–735 行）；附录 B.6（762–787 行）。
- **依据**：B.4 保留了原图的线性写法：`storage_projection -> RepositoryImportArtifact -> snapshot -> comparison …`，读起来像
  storage_projection 位于 snapshot 上游。B.6 的 Architecture §7.1 新图与设计 §3 的目标结构则是 snapshot_materialization →
  storage_projection。原图本身就有这个问题，但 r3 既然给出了替换文本，宜一并对齐。
- **建议**：B.4 的替换图改为与 B.6 同向，例如 `snapshot -> storage_projection -> mutation_planning -> RepositoryImportArtifact`，
  `snapshot + table_rules(ComparisonRuleView) -> comparison -> risk -> surface -> bundle`，`snapshot -> project_identity`。

#### RR3-N3 身份确认理由复用 Archive 的校验函数，未写明共享校验的 owner

- **类别**：非阻塞建议。
- **位置**：设计 §7.6（491 行）；ADR 0020 Decision 5。
- **依据**：r3 写“与 Archive 理由使用同一校验（E：`validate_utf8_reason`）”。该函数属于 Archive Application，抛出
  `ArchiveRequestValidation`（`vnext/backend/src/gateway_backend/application/archive/contracts.py:58-66`）。Submit 直接调用它，会让
  Submission Application 依赖 Archive Application，并在 Submit 路径上抛出 Archive 的错误类型。数值边界本身一致：HTTP 层的
  `BoundedDiagnosticReason` 与 Application 层都是 4096 字节。
- **建议**：写明共享校验的位置。可以由 HTTP DTO 沿用 `BoundedDiagnosticReason` 返回 422，Application 层使用 Submission 自有或
  提取出的共享校验；不从 Archive Application 导入。

## 6. 专项结论

- **DC26 的精确放行**：符合 P5 §2A.2，放行的是一个 owner 的一条 zone 边，不是 basename 或整层豁免。符合 P5 §2A.3，没有预建 provider
  框架。符合 ADR 0001 §4（Python capability facade 经 PyO3 调用 Rust）与 Contract Taxonomy §4.4（可以首版直接使用 Rust production
  provider）。`contracts.py` 仍须保持叶子，不导入 compute，以满足 P5 §2A.2“只 import contract 不应加载重型执行依赖”。
- **business schema digest 与 manifest `canonical_schema_digest` 的区分**：名称、owner、列序语义、commit 侧来源与“两者都不进入
  `canonical_binding`”已无歧义；剩余问题是存储身份的判据（RR3-F1）与 manifest 摘要消费方的表述（RR3-F2）。存储规则事实按
  RR3-F1 修正后，§4.5 的对齐与来源标记能够自洽：对齐不依赖来源标记，来源标记只用规则侧字段判断。
- **附录能否按字面并入**：附录 A 第 1–6 项、B.2–B.6 可以（B.4 的方向问题为建议）；B.1 须先按 RR3-F2 修正。
- **身份确认理由**：与 Archive 的数值边界一致（HTTP 与 Application 都是 1–4096 UTF-8 字节），按原文持久化；owner 问题见 RR3-N3。
- **执行计划**：S1 验收在 DC26 下可以机械兑现（R3E2）；S2a 的 compose 预期已改为“History 与空基线旅程不变，非空基线 Preview 的变化
  在 handoff 说明”；镜像重建判定与停止条件未变，仍符合 AGENTS.md。

## 7. 修订后通过时仍保留的实施前置条件

1. RR3-F1、RR3-F2 在 S0 再修订中关闭，RR3-N1 建议同时处理；复核只需核对相应差异。
2. [r2 第二份复审](p5-arch-closure-s0-independent-rereview-2.md) §7 第 2–4 项继续有效：5E slice exit 为 pass 后才开始 S1，S1 kickoff
   复核漂移并完成真实数据普查；S0 接受时一并接受附录 A、B；S2b 门槛前真实 Dolt 同一性 owner 通过；S3 验收前 composite 键列类型经
   Dolt 导入验证；各阶段记录镜像决策，最终候选 fresh 重建；F7 在 S2b 语义验收前以真实数据关闭，F8 在 S2a 冻结前与 legacy oracle 核对。

## 8. 需要 owner 决定的事项

无。RR3-F1、RR3-F2 与各项建议都是定义或措辞的修正，不改变 DC1–DC27 的任何决定。

## 9. 链接与路径检查

提交前用脚本检查了本报告：

- 全部相对链接与锚点都能解析；
- 反引号中以 `vnext/` 开头的路径在 worktree 中都存在，带行号的引用不超出文件长度；
- 只写文件名的测试文件：`test_commit_canonical_metadata.py` 是 r3 执行计划标为新增的文件，其余在 `vnext/backend/tests/` 中存在。

同一脚本对 r3 改动的 9 个文件与决议记录做了链接与锚点检查，结果为 0 个问题（R3E7）。
