# FE2a 复审报告（第 1 轮）

- **复审对象：** 分支 `fe-vnext`，代码候选 `2b62bf21a09f9cde69528eb520cdc5f6296a9486`（`frontend/` 树 `26003bda19`）；
  handoff 提交 `c1abe10cf8f5d83e3f6ab1b0c570c60744a1515c`（只改 handoff，`frontend/` 树相同）。
- **范围：** `57e77505f6..c1abe10cf8`，13 个提交。`fe-vnext` 没有合入设计文档提交，这样处理可以。
- **依据：** [FE2a 审核报告](fe2a-review.md) §5、§7；FE2 kickoff 当前版本（main `f4f413886e`）的 §4.2、§4.3、§5.1、§5.3–§5.6、§7。
- **日期：** 2026-11-03。
- **结论：定向修复。** B1–B9 和 R3 都已修复；fixture 逐字节复现，5 个变异探针都由对应的 owner 用例发现，30 张截图与草图基本相符。
  剩下两项阻塞，改动都很小：公式抽屉把不同运算符的无名子表达式拆平，导致公式含义改变（N1）；视图状态文字套用了表级文案（N2）。
  第 2 轮复审只看这两项和 handoff 勘误，然后进入 04 取证。

## 1. 范围与依赖

- `57e77505f6..c1abe10cf8` 只改动了 `frontend/` 和 `docs/frontend-vnext/fe2a-handoff.md`；`vnext/` 树仍为 `2791d3ff3d`。**通过。**
- `package-lock.json` 未变。`package.json` 和 runner 只删除了 `check:browser-types` 一步（B9）。工具链镜像、npm 缓存和后端依赖镜像沿用既有预填充。**通过。**
- **取数点（FD3）：** 应用里仍只有 `ComparisonPage.tsx:213` 的 bundle 下载一处，经认证封装发出。**通过。**

## 2. 复跑与证据

### 2.1 我在 05 上的独立运行

- **源码传输：** 从实施仓库只读生成 `git bundle create … ^57e77505f6 fe-vnext`，SHA256 为 `5a4dccbca3937f19de23f9bc13f83fe0545b2b27060c5729b9d20b010658153f`。05 上 `FETCH_HEAD` 等于 `c1abe10cf8`，05 的 main（`c18b9b0993`）没有移动。
- **worktree：** `/home/dev/gdds-fe-rereview1-fe2a-c1abe10c-05`，detached、clean，已建 `legacy` 链接；运行前确认没有占用标记。

日志在 05 的 `/home/dev/gdds-fe-logs/fe2a/rereview-1/`，节点为 `gw-dms-test-05.lan`：

| 运行 | 起止（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 准备 `rereview-setup-05.log` | 08:26:33 | HEAD `c1abe10cf8`、`frontend/` 树 `26003bda19`、clean | `f6ba6c795f9c940ff70f504e2b8270319dd5b3c9c0e8677e191b44948a3d59e1` |
| `run-tests.sh --screenshots` `frontend-tests-20261103T082710Z.log` | 08:27:10–08:27:34 | **exit 0**；16 个文件 70 项单测，e2e 4 passed；HEAD 和树起止不变；运行后 clean | `10e00a06c68aa30b858c87bd9e1d6af222f81b398b27bf35504130fa65936cb6` |
| 外层包装 `runner-wrapper-05.log` | 同上 | runner_exit=0 | `cffc62e004292a3758c267b568929ab7a86db5c297f1240496bc81efc6509673` |
| fixture 重新生成 `fixture-regen-05.log` | 08:27:34–08:27:37 | 后端依赖镜像，`--network none`，`vnext/` 只读挂载；213 个文件与提交的 fixture **逐字节相同**；五个 bundle 的 digest 与 handoff 一致 | `e94894c6913c0f27ce36fbc958f9bd7547ddd905eab6ae428d2107e3799c7d73` |
| 变异探针 `mutation-probes.log` | 08:29:09–08:32:02 | 见 §2.3 | `be980edb42e861b0818dd0803bb14d2c985b80f84e22e0b0df2ce6da9d5340ed` |
| 探针重做 `mutation-probes-redo.log` | 08:32:14–08:33:57 | 见 §2.3 | `acb0cd69846ae2c439c04d9b74fd78be1ac7d0b6b1976483367a8cc0554e0b79` |

我拍的 30 张截图（`/home/dev/gdds-fe-evidence/fe2a/rereview1-c1abe10c-05/`），与实施会话证据目录 `/home/dev/gdds-fe-evidence/fe2a/2b62bf21a0-05/` 中的截图、以及 handoff 截图表中的 SHA256，三方全部逐字节一致。

### 2.2 handoff 证据

- **最终运行：** 05 runner（`271de5f1…74ce`）、外层日志（`d440899e…d9b5`）和 focused e2e（`68f6647f…cae4`）重算一致。runner 日志中，起止 hostname、HEAD `2b62bf21a0`、`frontend/` 树 `26003bda19`、`exit_code=0` 都与 handoff 一致；被测 worktree clean。
- **中间运行：** 三次非零 runner 运行和四份 focused e2e 日志重算一致，共 10 个 SHA256；每次失败后都追加提交修复，再从头运行，符合 runner 停止规则。
- **fixture 日志：** 第二次生成（`dc6c77bd…`）、复现（`311c2109…`）、两份摘要（`6f858c2a…`）、`rg` 缺失的操作日志（`504f4040…`）都一致。`rg` 缺失发生在生成器已正常退出之后，属于只读后处理，按 DC68 补充说明不计入重做次数。
- **handoff 抄写错误**（不影响结论，下一轮 handoff 中更正）：
  - 第一次生成日志 `fixture-generation-ce0efc3c22-run-1-05.log` 的实际 SHA256 为 `f7d374c4a8acdfe3cf929f1dafacb2d2a351f129b708d919e9f2e915514fffd8`，handoff 中只写了 62 位，漏了中间的 `9f2e`；
  - Preview 数据集替换的 closure 摘要实际为 `a29400b56b0bde2ce17d1ebbc5affe336927ccf965c1fd463104cbfee18060cc`，handoff 中漏了一个 `b`。

### 2.3 变异探针

05 上的一次性 worktree，每个探针一个本地提交，跑 runner（不含 e2e），用后删除。

| 探针 | 改动 | 结果 |
| --- | --- | --- |
| B3 跳过自校验 | `locationValid` 恒为真 | exit 1；只有“改动一条记录的行标识后退回表级”和“未变更行标注匹配失败退回”两个用例失败 |
| B3 Preview“前”行 | 不再用“后”行的比较键列填充“前”行 | 首次 exit 2，失败在类型检查（我删掉代码后留下了未使用的变量，没有触及测试）；改为保留变量的写法后重做一次，exit 1，只有五 fixture 的唯一 owner 用例失败 |
| B4 整表新增 | 整表新增后仍进入逐行循环 | exit 1；只有 `added_table` owner 用例失败 |
| R4 搜索 | 不再排除二进制列和二进制值 | 首次 exit 2，原因同上（未使用的函数）；重做后 exit 1，只有 R4 用例失败 |
| B5 比较对诊断 | 比较对诊断不再扣除表诊断 | exit 1；只有“五 fixture 中表诊断不进入比较对提示”和“扣除带表名后缀的诊断”两个用例失败 |

两次重做都是我写的探针本身有误：失败发生在类型检查阶段，被测用例还没有运行。失败日志已保留，各重做一次。

## 3. 原阻塞项核对

| 项 | 结论 |
| --- | --- |
| B1 fixture 生产路径 | **通过。** `composite_signal_point` 经 `materialize_business_snapshot` 用 SQL 加 `logics.xml` 合成，AST 为 EXPRESS/POINT/DIGITAL。Preview 的 pair_id、view_id（两个比较对都是 `initial_to_modified`）、输入角色与显示名、`assess_identity` 和 `identity_before_table_set`，我逐项对照了 `preview_jobs` 的 pair_specs，一致。History 用 `<operation_id>-p<i>`、`(index, ref_id, "node-<i>")` 和 `include_all_tables=True`。不再有 `replacement_pair`。`commands.test.ts` 覆盖了两个比较对 view_id 相同时的切换与 URL 恢复 |
| B2 公式查看 | **基本通过，见 N1。** 公式按逐行业务公式显示；同类链压平，命名分组标题带父运算符，单子节点直接展开，一元运算符为前缀，名称映射使用同侧 `device` 表，改名不算公式变化；History 两侧对齐；Preview 只显示上传侧并标“公式已改”；入口在公式列的单元格上 |
| B3 行定位 | **通过。** 自校验只约束有快照的一侧，规则与 2e7428a5e5 的 §5.3 一致。标注按行标识字节对应，不区分 `ROW` 或 `ROW_PAIR`。Preview 的删除行与“前”行由记录值组成，`#` 留空并有悬停提示，删除行放在表末。不支持的类型（行标识算不出）时退回表级。探针见 §2.3 |
| B4 整表新增 | **通过。** 截图 `navigation-fallback` 中 `added_table` 只有一行“+ 新增”；探针见 §2.3 |
| B5 诊断 | **通过。** 表诊断只出现在该表；比较对诊断放在顶栏下方的提示条（数据集替换截图中为“识别为不同数据集，已切换为双侧浏览”）；`device` 上不再出现其他表的提示；文案表与 kickoff §5.5 逐项一致；`DEGRADED` 的原因按文案表顺序选取 |
| B6 视图风险与身份结论 | **风险部分通过，状态文字见 N2。** 视图分段控件带风险徽章，数据集替换的“高风险”可见；身份评估缺失时显示“项目身份评估不可用” |
| B7 §4.3 文案 | **通过。** 侧栏徽章显示新增、删除（加删除线）、更新、替换，有风险时只显示风险等级；回退侧栏也使用同一套徽章；9 个 `SurfaceChangeKind` 由一个映射用例覆盖 |
| B8 截图与草图 | **通过（N2 除外）。** 模式页签已删除，e2e 断言其不存在；截图前等待表格绘制，30 张截图都有内容。审核报告 B8 表中的各项都已修正，见 §4 |
| B9 测试与死代码 | **通过。** `filterChangedRows`、`applyNavigationRowFilter` 及其用例已删除；R4 用例测的是实际的搜索路径；`check-browser-types.sh` 已删除，N6 引用我的类型探针 |
| R3 | **通过。** 按 `BundleIntegrityError` 类型判定错误码 |

## 4. 截图对照

逐张对照 S3、S4 草图（1280、1920 两种宽度）：

- **顶栏（S3）：** 第一行有“返回工作台”、面包屑（视图 › 分组 › 项 › 页签）、模式标签（上传；历史比较·只读）和连接状态；第二行有视图分段控件（含风险徽章）、“全部/仅看差异”和“开发环境 User/Debug”。模式操作区为空，属于 kickoff §5.1 说明的已知差异。
- **页签（S3）：** 带行数（如“4 → 4”）和变化或风险徽章，“更多 n”溢出菜单可用。
- **信息行（S3、S4）：** 表名、状态徽章、增删改计数、带计数的风险徽章、标注数和风险原因合在一张卡片里；“变更 n / m”和竖向分布条在表格右侧。
- **表格（S4）：** 列宽铺满；修改行成对显示，带连线；当前变更的框覆盖整行；删除线只划数据列；折叠行有“展开”；Preview 中的删除行和修改行“前”行 `#` 留空，“前”行中没有改前值的单元格留空。
- **Debug（S4）：** 有 Diff Kind、Row Role（前/后）、Ordered Semantic / Position 三列；侧栏中导航诊断的 JSON 换行显示在提示下方，不再把提示文字挤成窄条。
- **语义色：** 五个等级的颜色与 S4 `semantic-tokens` 一致；`grid-main` 只含 v1 产出的等级，按 §7.1 属于已知差异。
- **无草图页面**（交 owner 看图确认）：公式抽屉（Preview、History）、数据集替换双侧浏览、加载骨架、错误页、导航回退。按 UI 优化方向的原则核对：token、语义色、按钮层级和焦点样式都符合，只有公式抽屉的 N1 问题。

## 5. Findings

### 阻塞

**N1. 公式抽屉把不同运算符的无名子表达式拆平，公式含义被改变**
`frontend/src/features/view-model/formula-view.ts:96`、`:113`

- **现状：** 无名 EXPRESS 子节点的运算符与父链不同时，`visit` 只给它的第一个操作数加上自身运算符作为前缀，并与父链的行放在同一层；连接父链的运算符随之丢失。
- **失败场景：** fixture 的公式是 `线路电流 + 1 + 2 + 测量电压 + (3 × 测量电压 × 4)`。截图 `formula-history`、`formula-preview` 中显示为：

  ```
  + 测控装置:测量电压
  * 3
  * 测控装置:测量电压
  * 4
  ```

  四行在同一层，读起来是“测量电压 × 3 × 测量电压 × 4”，与实际含义不同。真实 `logics.xml` 中 `|` 链嵌套 `&` 或 `+` 组的写法很常见，审核人会据此误读公式。
- **建议修复：**
  - 无名的异运算符子表达式作为一个分组：保留父链运算符，例如分组行写“+ (”或“+ 子表达式”；组内操作数缩进一层，按自身运算符逐行展开。
  - 显示格式由实施会话选定，原则是读者能分清分组边界；不需要设计会话定文案，但要写进 handoff。
  - `formula-view.test.ts` 补一个用例，以 fixture 中的这个形状断言父运算符和分组深度。现有用例如果断言了当前的输出，要同步修改。

**N2. 视图状态文字套用了表级文案，含义不对**
`frontend/src/pages/ComparisonPage.tsx:60`

- **现状：** 视图分段控件下方的小字由 `viewStatusText` 生成：有失败表时显示“比较失败”，有降级表时显示“降级比较”，有变化表时显示“有修改”。这些是 §4.3 的表级文字，kickoff 没有为视图定义状态文字；handoff 也没有按定向修复 prompt 的要求，把这一点列为待设计会话决定的事项。
- **失败场景：**
  - 所有截图中两个 Preview 视图都标“降级比较”，原因只是 9 张表中有 2 张降级；
  - 如果某个视图中有一张表比较失败，整个视图会标“比较失败”，读者会以为整个比较失败了。
- **建议修复：**
  - 按 S3 草图：视图没有变化表时显示“一致”，否则显示“更新”；有风险时风险徽章不变；
  - 降级表和失败表的数量放进悬停提示（例如“2 张表降级比较”“1 张表比较失败”），与已有的“n 张表有比较提示”放在一起；
  - S3 草图中已经有“一致”和“更新”，不需要设计会话另定文案；
  - 补一个用例覆盖这四种情形。

### 非阻塞

**R5. 连接状态固定显示“已连接”**（`ComparisonPage.tsx:392`）
页面没有连接检测，bundle 下载失败的错误页上也显示“已连接”。FE2b 或 FE3 接入真实状态时处理；在那之前，可以只在 bundle 已就绪时显示。

**R6. handoff 抄写错误**
§2.2 中的两处 SHA256 抄写错误，在下一轮 handoff 中更正。

**带入 FE2b：** R2 不变（token 来源、URL 中的 bundle 地址脚手架、生产构建检查的禁止模式）。

## 6. 下一步

1. 实施会话修复 N1、N2，在 handoff 中更正 R6，可以顺手处理 R5。在 05 上完整运行一次权威入口（含截图），并重拍公式抽屉与视图分段控件相关的截图（实际上会重拍全套）。
2. 复审第 2 轮范围为 `c1abe10cf8..<新候选>`，只核对 N1、N2、R6 和截图。
3. 复审通过后，在最终候选上于 04 取证并重拍全套截图（kickoff §7.3）；无草图页面的截图交 owner 确认。

**本轮复审创建的 worktree**：开发主机上的 `/home/dev/gdds-fe-rereview1-fe2a-c1abe10c`，05 上的 `/home/dev/gdds-fe-rereview1-fe2a-c1abe10c-05`。另外，第 1 轮审核的 `/home/dev/gdds-fe-review-fe2a-57e77505`（开发主机）和 `…-05`（05）已不再需要，可以在 FE2a 退出后一并删除。
