# FE2a 审核报告

- **审核对象：** 分支 `fe-vnext`，代码候选 `764d9527579ee121d2021ad28df74553e742a5ed`（`frontend/` 树 `48b57c187e`）；
  handoff 提交 `57e77505f6c79752a7abd5f8df5deeb7080b19a0`（只改 handoff，`frontend/` 树相同）。
- **范围：** `fe-fe1-exit..57e77505f6`。其中 `1e62249f3a`、`240d83a271`、`7d6d8ad69d` 是 main 上的 kickoff 文档提交（fe-vnext 由 main 快进得到），实施部分为 `7d6d8ad69d..57e77505f6` 的 26 个提交。
- **依据：** [FE2 kickoff](../fe2-kickoff.md) §3–§5、§7、§10；[前端 kickoff](../frontend-kickoff.md) FD1–FD8、§6；[BE-b 草案](../be-b-navigation-and-presentation-draft.md) §4.4、§4.7；[Composite Signal Device](../../backend-vnext/capabilities/composite-signal-device.md) §Frontend；S3、S4 草图。
- **日期：** 2026-11-03。
- **结论：定向修复。** 运行证据、fixture 复现和 FE1 带入项中的 N4、N6、D1、行分隔色都核对通过。但有 9 项阻塞：两项是 fixture 或公式数据与后端生产路径不符，五项是页面行为错误，另外两项是截图证据不完整和测试空跑。
  其中 B3、B5 依赖设计会话先答复 §6 的 D1、D2；其余各项可以直接修复。04 上已有的取证运行对应的是本候选，修复后要在最终候选上重新运行 04 并重拍截图。

## 1. 范围与依赖

- **范围：** `7d6d8ad69d..57e77505f6` 只改动了 `frontend/` 和 `docs/frontend-vnext/fe2a-handoff.md`。`vnext/` 树仍为 `2791d3ff3d`；AGENTS、kickoff、UI 优化方向和审核报告都没有改动。**通过。**
- **依赖：** `package-lock.json` 未变。`package.json` 只新增两个脚本（`check:production-build`、`check:browser-types`），没有新增依赖。工具链镜像、npm 缓存和后端依赖镜像都沿用既有预填充，不需要重新传输。**通过。**
- **runner：** 新增 `--screenshots <绝对路径>`，拒绝写到 worktree 内的路径；工具链身份改为用 `docker save` 导出后，比较 config digest 与 7 个 DiffID；新增浏览器类型检查和生产构建检查两步。行为正确，浏览器类型检查的问题见 B9。

## 2. FD 遵守情况

| 项 | 结论 |
| --- | --- |
| FD1 无 legacy 兼容层 | 通过。`ViewKind`、`diagnosticText`、内联 `diagnostics` 都已删除，`src/` 中没有 legacy 引用。但 `model.ts` 留有应用不调用的旧过滤函数，见 B9 |
| FD2 统一认证封装 | 通过。唯一的请求点是 `ComparisonPage.tsx:177` 的 bundle 下载，经 `createAuthenticatedFetch`，用 fetch 流式读取。token 目前固定为 `null`，带入 FE2b（R2） |
| FD3 浏览期间不向后端取数 | 通过。只有加载 bundle 时请求一次；切换视图、页签、过滤、Debug、刷新（本地已有 bundle）都不再请求，e2e 在刷新前后比较了请求计数。切换模式后再切回会重新下载，见 R1 |
| FD5 侧栏 | 功能基本到位：方案 A、单一滚动区、分组展开记在本地、宽度可调、折叠窄栏的三个入口、当前项滚到可见、无导航时回退为单组。徽章文案和回退侧栏的问题见 B7 |
| FD6 占位与回退 | 无导航产物时回退为单组，标“占位导航”；未知导航编码显示“导航提示（{code}）”。通过 |

## 3. 复跑与证据核对

### 3.1 我在 05 上的独立运行

- **源码传输：** 从实施仓库只读生成 `git bundle create … ^240d83a271 fe-vnext`，SHA256 为 `b9d4ae122752ef534ff7a09fd32998aee6fae059808d7959f136e1e091f22d69`。在 05 上 verify 并 fetch 后，`FETCH_HEAD` 等于 `57e77505f6`，05 的 main 停在 `240d83a271`，没有移动。
- **worktree：** `/home/dev/gdds-fe-review-fe2a-57e77505-05`，detached、clean，已建 `legacy` 链接；运行前确认 05 没有占用标记。

日志在 05 的 `/home/dev/gdds-fe-logs/fe2a/review/`，节点为 `gw-dms-test-05.lan`：

| 运行 | 起止（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 准备 `review-setup-05.log` | 00:25:46 | HEAD `57e77505f6`、`frontend/` 树 `48b57c187e`、clean | `6d72718f716335e0eb29f274cf5622a599989cb2684b4f579e2135ac2f4288ab` |
| `run-tests.sh --screenshots` `frontend-tests-20261103T002622Z.log` | 00:26:22–00:26:43 | **exit 0**；13 个文件 61 项单测，e2e 4 passed；HEAD 和树起止不变；运行后 clean | `5366fab9612504fdac241950e8705b9aa7767048b3ef92b6a47c8f4879dd078b` |
| 外层包装 `runner-wrapper-05.log` | 同上 | runner_exit=0 | `74c619f4e755cb66705b3cbdfd5625b61ca43c7703dfe5535c54ebcebc6b88b6` |
| fixture 重新生成 `fixture-regen-05.log` | 00:31:56–00:31:59 | 后端依赖镜像（19 个 DiffID，首尾与 handoff 一致），`--network none`，`vnext/` 只读挂载；198 个文件与提交的 fixture **逐字节相同**；五个 bundle 的 digest 和风险等级与 handoff 表格一致 | `a362d897e894eb4663c17211fae5b5ce387c51ff27aeb2a8595b51b6cafe66a7` |
| 变异探针 `mutation-probes.log` | 00:33:15–00:35:35 | 见 §3.3 | `daaf3d89fd4c121a40200f1e4fb19eba26f9d6e8a5c8ae6e2ec8a8e77551265f` |
| N4 探针重做 `mutation-probe-n4-redo.log` | 00:35:50–00:36:26 | 见 §3.3 | `e2e82afad31e3d788473b6481c2df60f19836e6eeca6689886fe28546aa23877` |

我在 05 上拍的 30 张截图（`/home/dev/gdds-fe-evidence/fe2a/review-57e77505-05/`）中有 29 张与 04 的逐字节相同。不同的一张是 `navigation-fallback-1920`，对照后内容相同，只是像素级渲染差异。

### 3.2 handoff 证据

- **运行日志：**
  - 05 runner（`79f35505…2a78`）、05 包装日志（`ec7b0d9d…bca3`）、04 runner（`f340f225…8c96`）、04 包装日志（`4b1b64ce…c85e`）重算一致；
  - 两份 runner 日志中，起止 hostname、HEAD `764d952757`、`frontend/` 树 `48b57c187e`、`exit_code=0`、`docker_network=none` 和缓存归档 SHA256（`0d861824…089f4`）都与 handoff 一致；
  - 04 的 worktree 仍是 detached、clean。
- **其他日志：** 以下日志的 SHA256 都与 handoff 一致：fixture 的两次生成（`ee9f7a03…`、`aa3f8139…`）、复现（`26d1a3c7…`）与汇总（`9b6cd02a…`）日志；三份源码传输失败日志和成功的 bundle/fetch 日志；后端依赖镜像身份 JSON（`0c1d87ef…`）与核对日志（`39fac1ab…`）；04 上 `89645c84ec` 的内部 runner 日志（`2e341261…`，exit 0，外层日志未落盘，与 handoff 说明相符）。
- **截图：** 04 证据目录有 30 张，与 handoff 表格中的 15×2 个 SHA256 全部一致。
- **DC68：** clone 被 `safe.directory` 拒绝、bundle verify 缺仓库参数、04 缺少前置对象，这几次都发生在建立 worktree 之前，失败日志已保留，改用 bundle/fetch/worktree 后成功，处理符合 DC68。权威 runner 开始后的非零退出都作为候选缺陷处理，追加提交后从头重跑，符合 runner 停止规则。

### 3.3 变异探针

05 上的一次性 worktree，每个探针一个本地提交，跑 runner（不含 e2e），用后删除。

| 探针 | 改动 | 结果 | 说明 |
| --- | --- | --- | --- |
| N4 | `MemoryBundleStore` 每次读取都重算摘要 | 首次 exit 1，但失败在 lint（我写成了常量条件 `if (true)`，没有触及被测代码）；改为 `if (path.length > 0)` 后重做一次，exit 1，只有“hashes an artifact once per opened browsing session”失败 | N4 有效，且有唯一的测试 owner |
| R4 | 删除 `containsSearchText` 跳过二进制值的分支 | **exit 0，61 项全部通过** | R4 用例空跑，见 B9 |
| N6 配置 | `tsconfig.app.json` 的 `types` 加回 `node` | **exit 0**，`check:browser-types` 仍报告通过 | 浏览器类型检查脚本不检查应用配置，见 B9 |
| N6 行为 | 在 `src/App.tsx` 中使用 `Buffer` | exit 2，`TS2591: Cannot find name 'Buffer'` | 当前配置满足 N6 完成标准 |

## 4. FE1 带入项（kickoff §3）

| ID | 结论 |
| --- | --- |
| N4 | 通过。打开 bundle 时校验 manifest 和 closure；每个打开会话中，产物首次读取时校验摘要，结果记在会话内；读取或解析失败时重新下载一次。探针见 §3.3 |
| N6 | 配置通过：应用 tsconfig 不含 Node 类型，测试用独立的 `tsconfig.test.json`。runner 新增的检查脚本是空跑，见 B9 |
| R4 | **未满足。** 用例空跑，被测函数也不在应用的搜索路径上，见 B9 |
| 行分隔色 | 通过。`--color-row-separator: #EEF1F4` 作为表格 `borderColor`，截图中行分隔可见 |
| D1 | 通过。导航诊断经 `SurfaceProjectionRef.diagnostics_ref` 读取单独产物；10 个 v1 编码都有文案，占位符与 params 一致（用例逐码核对模板与参数表）；未知编码有回退；`diagnostics_ref` 为 null 时不显示。文案与 BE-b §4.7 一致，其中 `CHANNEL_TABLE_UNCLAIMED` 是 `0e0d14f1d1` 定稿的中性文案 |

## 5. Findings

### 阻塞

**B1. composite_signal_point 的 fixture 数据不是后端生产路径产出的；比较对与输入参数也和生产作业不一致**
`frontend/scripts/generate-backend-bundle-fixture.py:72`、`:102`、`:132`、`:189`、`:460`–`:527`

- **公式数据：** 生成器把 `composite_signal_point` 直接写在 SQL 里，经 `materialize_sql_snapshot` 物化，公式 AST 是自编的 `{"kind":"ADD","args":[1,2]}`。生产路径中：
  - 这张表由 `materialize_business_snapshot` 从 `logics.xml` 合成；
  - SQL 里已有这张表时，合成直接失败（`snapshot_materialization/compose.py:153`，`SQL tables already contain composite_signal_point`）；
  - AST 的结构是 `EXPRESS{operator, children, name?}`、`POINT{name}`、`DIGITAL{value}`（`composite_signal/_digest.py:19`）。

  因此公式抽屉、“公式已改”判定和装置名称映射，都是在后端不会产出的数据上测试的。这违反 kickoff §7.1“不手写 bundle”的原则。
- **比较对与输入：** 生成器直接调用 pipeline，但参数与生产作业不同：
  - 生产 Preview 作业对两个比较对都传 `view_id=initial_to_modified`（`application/preview_jobs.py:1914`），fixture 中 FULL 的两个视图 ID 却各不相同；
  - 生产 History 的 pair_id 是 `<operation_id>-p<i>`，fixture 写成 `node_1_to_node_2`；
  - 输入角色和显示名：生产 Preview 为 `baseline`/`initial`/`modified` 与 `Baseline`/`Initial`/`Modified`；生产 History 为节点 `ref_id` 与 `node-<i>`。fixture 写成大写角色和中文显示名；
  - 替换场景用了生产不存在的 pair/view ID `replacement_pair`。
- **失败场景：** 真实 FULL bundle 中两个视图 ID 相同。当前页面按 pair_id 选择视图（URL 同时记 `pair`），所以暂时没有出错；但没有任何测试覆盖这种形状，以后改成按视图 ID 区分时，fixture 测试仍会全部通过。公式查看器换上真实 AST 后，当前实现无法显示（见 B2）。
- **建议修复：**
  - 生成器改为经 `materialize_business_snapshot` 输入 SQL 加 `logics.xml`，生成 `composite_signal_point`；公式中的 POINT 名称使用 `Device N:测点` 形式，以覆盖名称映射；
  - pair_id、view_id、输入角色与显示名按 `preview_jobs`、`compare_jobs` 的现有取值构造，能导入常量的直接导入；
  - 重新生成后，在 05 上逐字节复现；
  - 视图 ID 是否应该改，见 D3，不影响本项修复。

**B2. 公式抽屉显示原始 AST JSON 树，不符合公式展示规则**
`frontend/src/pages/ComparisonPage.tsx:562`（`FormulaTree`）、`:311`（`openFormula`）、`:374`、`:381`

- **规则：** BE-b §4.4 规定公式展示沿用 Composite Signal Device §Frontend：
  - 把连续同类的 `|`、`+`、`*` 链压平为逐行的业务公式；
  - POINT 名称按 `^Device ([0-9]+):(.*)$` 映射为“装置名称:测点”，映射用同侧的 `device` 表；
  - 不提供原始 XML 或 AST JSON。
- **现状：**
  - 抽屉逐键显示 `kind:`、`args:`、`0:`、`1:`（截图 `formula-history`、`formula-preview`）；
  - 测点标题“Device 65532:测点 · device:8”直接拼接了原始键；
  - “查看公式”入口放在表头和变更导航条上，只要当前比较对里有 `composite_signal_point` 表，所有表都会显示这个入口；kickoff §5.4 要求放在公式列的单元格上。在 `added_table` 上，这个按钮被挤成竖排的“查 看 公”（截图 `navigation-fallback-1920`）。
- **建议修复：**
  - 按 §Frontend 的规则实现展示：压平、名称映射、改动行底色加左侧强调边框；History 与审核用两侧对齐对照，Preview 只显示上传侧；
  - 入口放到 `composite_signal_point` 公式列的单元格上；
  - 测试用 B1 生成的真实 AST。

**B3. 前端在浏览器中复刻了后端的行语义摘要，缺少 Contract 和跨实现向量，已知类型上与后端不一致**
`frontend/src/features/view-model/table-rows.ts:49`–`:134`

- **现状：** 为了把快照表的行与 records、标注对上，`snapshotRowIdentity` 用 `gateway-vnext:row:v1\0` 和自写的标量帧重算了 `DigestKind.ROW`。
  - 这套编码属于 shared_kernel（`scalar.py`）与 `comparison/row_encoding.py` 的内部实现，没有任何 Contract 规定前端可以或应该复刻；
  - 测试只验证了 fixture 中 INT/VARCHAR 列的一个标注能对上。
- **已知不一致：**
  - `SET`：后端编码为字符串序列集合（`row_encoding.py:335`），前端按单个字符串编码；
  - `BIT`：后端按二进制编码（`scalar.py:194`），前端返回 null；
  - `DECIMAL` 的规范文本、`SOURCE_LITERAL_ANOMALY` 等，前端也没有按后端规则处理。
- **失败场景：** 真实数据（FE3 t1）中，主键或比较列含 SET、BIT、DECIMAL 的表，行标识算不出来或与后端不同。修改行会显示成“未变更行 + 末尾的删除行”，行风险丢失。Comparison Surface Contract（`comparison-surface.md:256`）要求缺少行标识时展示表级风险，不得伪造行级样式。
- **建议修复：** 先由设计会话决定定位方式（D1）。若保留前端计算：
  - 按 shared_kernel 的标量帧规则完整实现；
  - 用 `shared_kernel/tests/canonical_cases.py` 的向量做跨实现测试；
  - 另设一个唯一的 owner 测试：五个 fixture 中每条行级 record 和每个 ROW 标注，都能在对应一侧恰好对上一行；
  - 对不上时退回表级风险展示。

**B4. 新增表的每一行显示两次**
`frontend/src/features/view-model/table-rows.ts:289`–`:296`、`:309`

- **现状：** 整表新增且没有 records 时，先把当前侧每一行作为“新增”加入；随后逐行循环又把同一行作为“未变更”加入一次。
- **失败场景：** 截图 `navigation-fallback-1280/1920` 中，`added_table` 的 `9 新表` 出现两次，第二行没有“新增”标记。整表删除的路径没有这个问题，因为删除表没有当前侧行。
- **建议修复：** 已按整表新增或删除处理的一侧不再进入逐行循环；在 `table-rows.test.ts` 中用后端 fixture 的 `added_table` 断言行数和类型（作为该行为的唯一 owner）。

**B5. 比较对级的诊断显示在每一张表上；v1 实际产出的诊断编码都没有文案**
`frontend/src/pages/ComparisonPage.tsx:377`、`frontend/src/features/view-model/diagnostics.ts:37`、`frontend/src/features/view-model/diagnostics.test.ts:22`

- **现状：** 表格区把 `surface.diagnostics.diagnostics_summary`（整个比较对所有表的汇总）和当前表的诊断拼在一起显示。
- **失败场景：**
  - 打开 `device`（本身没有诊断），也会看到 4 条“比较过程有提示”。这 4 条来自 `schema_demo`、`keyless_demo` 和 `b1_n1_iec104_yc_list`（截图 `s3-workbench-upload`、`s4-grid-main`、`s4-grid-debug`）；
  - 真正降级的 `keyless_demo` 只显示“比较过程有提示”，没有降级原因；`b1_n1_iec104_yc_list` 的 `ORDERED_DIFF_UNSUPPORTED` 有文案，但同表的 `ORDERED_REQUIRED_COLUMN_MISSING` 没有。§4.3 要求 `DEGRADED` 的信息行显示来自诊断的降级原因。
- **原因：** v1 实际写入的编码（`DEGRADE_NO_COMPARE_KEY`、`ORDERED_REQUIRED_COLUMN_MISSING`、`CURRENT_ONLY_COLUMNS`、`INCOMPATIBLE_SELECTED_COLUMNS` 等）都不在文案表里。文案表只有 kickoff §5.5 举的 5 个例子。测试只遍历文案表自己的键，并明确断言 `DEGRADE_NO_COMPARE_KEY` 显示通用文案，等于把缺口固定成了预期行为。
- **建议修复：**
  - 表格区只显示当前表的诊断；比较对级的汇总放到视图级位置（例如视图页签的悬停提示）；
  - 文案表按 D2 的答复补齐；
  - 测试以后端实际可能产出的编码集合为准，不以文案表自身为准。

**B6. 视图级风险和状态没有显示；数据集替换场景下唯一的高风险不可见；身份结论缺失时显示为“不同项目”**
`frontend/src/pages/ComparisonPage.tsx:345`、`:540`

- **视图页签：** S3 第二行的视图分段控件带状态或风险徽章（“一致”“高风险”）。实现中的视图页签只有文字，`surface.view.risk_level` 在页面上没有出现。
- **失败场景：** 数据集替换 bundle 只有比较对级的 `HIGH`（项目身份不同）。截图 `dataset-replacement-browse` 中，页面任何位置都没有出现“高风险”。
- **身份结论：** `ReplacementBrowser` 在身份评估缺失时，把结论默认成 `DIFFERENT_PROJECT`，于是显示“身份结论：不同项目”。这是编造的结论；`identityStatusText` 中“项目身份评估不可用”的分支因此永远不会走到。
- **建议修复：**
  - 视图页签按 S3 显示视图级状态和风险徽章；
  - 评估缺失时显示“项目身份评估不可用”；
  - 补一个用例：替换 bundle 的视图风险为 `HIGH` 时可见。

**B7. 导航徽章和表状态文案不符合 §4.3 的权威文案**
`frontend/src/pages/ComparisonPage.tsx:60`、`:364`、`:367`

- **导航徽章：** 所有非 `UNCHANGED` 的项都显示“更新”，包括新增（截图中的“直流屏”）、删除、替换、失败，也包括 `BUSINESS_EQUIVALENT`。§4.3 规定：
  - 新增为“新增”，删除为“删除”加删除线，失败为“失败”，替换为“替换”；
  - 业务等价不显示徽章，悬停提示说明。
- **当前表信息行：** `REPLACED` 的徽章显示为“更新”。
- **悬停提示：** 状态文字把 `BUSINESS_EQUIVALENT` 写成“有修改”。
- **回退侧栏：** 回退为单组时，侧栏不显示任何徽章，也没有删除线（截图 `navigation-fallback`）。
- **建议修复：** 导航徽章、信息行和悬停提示统一使用 `table-state.tsx` 中按 §4.3 定义的一份映射；回退侧栏使用同一套徽章；单测覆盖 9 个 `SurfaceChangeKind`。

**B8. 两张 1920 截图的表格区是空白；还有多处与 S3、S4 不符，handoff 未列为偏差**
`frontend/e2e/workspace-shell.spec.ts:98`–`:99`、`:114`–`:116`

- **空白截图：** `s3-workbench-upload-1920.png` 和 `s4-grid-debug-1920.png` 的表格区是空白的。原因是点击“查看整表”后立即截图，没有等表格画布绘制完成。04 和 05 上的截图逐字节相同，说明这个问题每次都会重现，不是偶发。这两张截图因此不能用来验收 S3 工作台和 S4 Debug。
- **与草图不符、handoff 也未列为偏差的地方**（kickoff §7.3 要求修正，或列为偏差交 owner）：

  | 位置 | 草图 | 实现 |
  | --- | --- | --- |
  | 顶栏第一行（S3） | “返回工作台”、面包屑（视图 › 分组 › 项 › 页签）、模式标签（上传/审核/历史比较·只读） | 只有图标返回按钮和固定的“工作台 / 差异浏览”，没有当前位置 |
  | 顶栏第二行（S3） | 视图分段控件（带徽章）、“全部/仅看差异”分段控件；右侧“开发环境 User/Debug” | 多了草图中没有的模式页签（上传预览/审核/历史比较），视图页签没有徽章，“只看变化 / 风险”是右侧的开关按钮 |
  | 页签行（S3） | 页签带行数、变化徽章和风险徽章 | 只有名称和圆点 |
  | 信息行（S3、S4） | 表名、增删改计数、带计数的风险徽章和“变更 n / m”在同一行，下面一条风险原因 | 大标题、元信息、多条诊断提示框、单独的风险说明卡片和单独的变更导航条依次排列，表格在 1080 高的截图中从约 550px 处才开始（草图约 230px） |
  | 变更分布条（S3、S4 语义色规范） | 表格右侧的竖向分布条 | 表格上方的横向条 |
  | 表格（S4） | 列宽铺满；当前变更的框覆盖整行；删除线只划数据列；折叠行带“展开” | 列只占约一半宽度；当前变更框只覆盖已画出的列；删除线也划过 `#` 和“变更”列；折叠行没有“展开” |
  | Debug 侧栏（S4） | — | 导航诊断的 JSON 把提示文字挤成一列窄条（`s4-grid-debug-1920`） |

- **建议修复：**
  - 截图前等待表格完成绘制（例如断言行数，或等待某个单元格内容可见），重拍全套；
  - 表中各项逐项修正，或在 handoff 中列为偏差交 owner；
  - 模式页签如果保留，需要设计会话或 owner 认可，否则删除（同时解决 R1）。

**B9. R4 的用例空跑，测的还是应用不调用的函数；浏览器类型检查脚本不检查应用配置**
`frontend/src/features/view-model/model.test.ts:111`、`model.ts:462`、`:556`、`frontend/src/features/view-model/table-rows.ts:168`、`frontend/scripts/check-browser-types.sh:13`

- **R4 用例：**
  - 用例中的行标识是 `Uint8Array.from([0x12, 0x34])`，字节值是十进制 18 和 52，搜索“12”本来就不会命中。删掉跳过二进制值的分支后，61 项仍全部通过（§3.3）；
  - 被测的 `filterChangedRows`、`applyNavigationRowFilter` 在应用里没有调用方。页面实际用的是 `buildBrowseRows` 的 `displayRowSearchText`，过滤则是 `loadTable` 内的另一份实现；
  - 实际的搜索路径会把二进制值显示成“二进制值”，所以搜索“二进制”会命中所有含二进制列的行，这也没有测试。
- **浏览器类型检查：** `check-browser-types.sh` 用自己的命令行参数编译探针文件，不读取 `tsconfig.app.json`。把 `node` 加回应用配置后，runner 仍然报告通过（§3.3）。
- **建议修复：**
  - 删除无调用方的 `filterChangedRows`、`applyNavigationRowFilter` 及其用例；
  - R4 用例改为测实际的搜索路径，用含字节 `12`（`0x0c`）的行标识，并断言搜索“二进制”不命中二进制值；
  - 浏览器类型检查改为在 `src/` 下放探针文件、用 `tsc -p tsconfig.app.json` 编译；或者删除这个脚本，按 kickoff §3 做一次性探针并写进 handoff（我的探针结果可以引用）。

### 非阻塞

**R1. 从其他模式切回 Preview 会重新下载 bundle**（`e2e/workspace-shell.spec.ts:178`–`:181`）
切换模式时 `set-bundle` 清空了 bundle 摘要，回到 Preview 时本地已有的 bundle 不被复用。e2e 还把“请求数加 1”写成了预期。建议按模式保存摘要，切回时复用本地 bundle；如果按 B8 删除模式页签，此项随之消失。

**R2. 带入 FE2b**
- `ComparisonPage.tsx:20` 的 token 固定为 `null`，FE2b 接入模拟会话时改为真实的 token 来源；
- bundle 地址来自 URL 的 `request`、`previewRequest`、`reviewRequest`、`historyRequest` 参数，这是 FE2a 的测试脚手架，FE2b 的页面路由要替换掉它；
- `check-production-build.mjs` 的禁止模式要与 FE2b 实际的模拟接口和身份选择模块名对应，否则检查不起作用（目前应用里还没有这类代码，所以检查结果没有意义）。

**R3. 错误码靠正则匹配中文错误消息判定**（`ComparisonPage.tsx` 中 `loadBundle` 的 catch）
`/摘要|完整性|校验|截断/` 匹配消息文字来区分 `BUNDLE_INTEGRITY_MISMATCH` 与 `BUNDLE_LOAD_FAILED`。消息文字一改，判定就会悄悄变化。建议按错误类型判定（已有 `BundleIntegrityError`）。

## 6. 设计问题（转设计会话）

| # | 问题 | 是否阻塞 |
| --- | --- | --- |
| D1 | **前端怎样把 records 和标注对应到快照表的行（B3）。** 现行 Contract 没有给快照表的行提供标识，前端只能复刻后端的行摘要。可选：甲，后端在表产物或 records 中提供可直接对上的标识或位置（改 Contract，属于后端任务）；乙，把行摘要的标量帧规则写进 Contract，前端按 shared_kernel 的规范向量实现并做跨实现测试。选甲时，FE2a 期间前端如何处理也需要明确（例如对不上时退回表级风险） | 阻塞 B3 |
| D2 | **surface 诊断的文案表（B5）。** kickoff §5.5 只举了 5 个编码。v1 实际会写入 `diagnostics_summary` 的还有：`DEGRADE_NO_COMPARE_KEY`、`ORDERED_REQUIRED_COLUMN_MISSING`、`CURRENT_ONLY_COLUMNS`、`BEFORE_ONLY_COLUMNS`、`INCOMPATIBLE_SELECTED_COLUMNS`、`NO_SELECTED_COLUMNS`、`EFFECTIVE_KEY_CHANGED`、`EFFECTIVE_KEY_IGNORED`、`SOURCE_PRIMARY_KEY_CHANGED`、`ROW_IDENTITY_MISSING`、`TABLE_READER_UNAVAILABLE`、`COMPARISON_MODE_NOT_DETAILED` 等（来自 `comparison/`、`surface_assembly/` 中的字面量，需要设计会话核对完整集合）。需要确定：哪些编码给出文案、`DEGRADED` 的信息行显示哪条原因，以及比较对级的汇总显示在哪里 | 阻塞 B5 的文案部分；只显示当前表诊断这一修复不依赖 D2 |
| D3 | **视图 ID 的后端事实与 kickoff 不符（B1）。** kickoff §4.2、§5.6 认为 surface 的视图 ID 是 `baseline_to_initial`、`initial_to_modified`。但生产 Preview 作业对两个比较对都传 `view_id=initial_to_modified`（`preview_jobs.py:1914`），只有 pair_id 不同；History 的视图 ID 等于 pair_id（`<operation_id>-p<i>`）。需要判断：这是否是后端缺陷，留给后端任务修复？在那之前，前端是否按 pair_id 区分视图（当前实现已经这样做）？kickoff §5.6 的表述是否要改？ | 不阻塞 FE2a：前端当前按 pair_id 区分；fixture 按 B1 跟随生产现状即可 |

## 7. 修复后的复审与退出

1. 设计会话答复 D1、D2（D3 可以同时答复）。
2. 实施会话修复 B1–B9，在 05 上重新生成 fixture 并逐字节复现，然后用权威入口完整运行一次（含截图）。
3. 复审范围为 `57e77505f6..<新候选>`，复审报告写到 `fe2a-rereview-1.md`。复审会重新逐张对照截图，并对 B3、B4、B9 做变异探针。
4. 复审通过后，在最终候选上于 04 重新取证并重拍全套截图（kickoff §7.3）。本次 04 运行只作为历史记录。
5. 无草图页面（公式抽屉、数据集替换、加载骨架、错误页、导航回退）在修复后的截图上交 owner 看图确认（kickoff §7.3、Q5）。

**本次审核创建的 worktree**（不涉及被测 worktree）：开发主机上的 `/home/dev/gdds-fe-review-fe2a-57e77505`，05 上的 `/home/dev/gdds-fe-review-fe2a-57e77505-05`。复审结束后删除。
