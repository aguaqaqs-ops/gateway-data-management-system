# FE4b 交接：业务导航、行定位与 BE-b 消费者判据

FE4b 覆盖 kickoff §5.3（BE-b 消费者判据）、§7.3（截图清单）与 fe-handoff 合并。起点为
`fe4b-base`（`3e5f24583d`，main `16ffe7282` 的审核提交）；本阶段只改 `frontend/` 与
`docs/frontend-vnext/`，`vnext/` 树保持 `2faac9fc1da9a6fd15eddef894f5c6e1652fba95`。

## 0. 摘要

- 分支 `fe-vnext`，候选 `fcf4268c1a531a8f44fe04038668ab475507acb5`；前端树
  `f3f1fdf1238346f3ed561cd80d6799c4dc64f4a2`；`vnext` 树 `2faac9fc1da9a6fd15eddef894f5c6e1652fba95`。
  相对 `3e5f24583d`：39 个提交、615 个文件、+3756/−1816，全部位于 `frontend/` 与
  `docs/`（前端交接文档与 fe-handoff 带入的 `docs/device-directory/handoff-fe-handoff.md`）。
- 本阶段新增/修改：`duplicates-orphans` 冻结修复、19 张 `fe4b-*` mock 截图、fe-handoff 合并、
  `frontend/e2e-real/lib/consumer-criteria.ts` 判据 helper、13 张 t1 真实数据截图。
- 最终候选证据（同一提交 `fcf4268c1a`）：
  - 07 `run-tests.sh --e2e --screenshots`：连续两次 exit 0，各 252 个 vitest + 106 个 Playwright、
    152 张 PNG；
  - 04 `run-tests.sh --e2e --screenshots`：exit 0，106 个 Playwright、152 张 PNG；
  - 04 `run-real-backend-e2e.sh --suite journeys --subphase fe4b`：20/20，exit 0，
    OpenAPI runtime 与快照规范化后逐字节一致；
  - 04 `validate-upload-package.sh`：4 个包、0 失败；
  - 05 `run-real-backend-e2e.sh --suite t1 --subphase fe4b`：1/1，exit 0。
- 本文件与 `fe4b-summary.md` 为文档提交，随后打 `fe-fe4b-exit`，并 `--no-ff` 合入 main；
  未推送。

## 1. 合并与路径核对

| 项 | 结果 |
| --- | --- |
| 候选 | `fcf4268c1a531a8f44fe04038668ab475507acb5` |
| 起点 tag | `fe4b-base` = `3e5f24583d` |
| `HEAD:vnext` | `2faac9fc1da9a6fd15eddef894f5c6e1652fba95` |
| `3e5f24583d:vnext` | 同上（相等） |
| `git diff --name-only 3e5f24583d fcf4268c1a` | 仅 `frontend/`、`docs/frontend-vnext/` 与 `docs/device-directory/handoff-fe-handoff.md`（fe-handoff 带入） |
| fe-handoff 合并 | `e225b63224`（父：`7daf61bdb2`、`251640f104`） |
| 依赖基镜像 | `gateway-backend-deps:lock-578e079b762e`（04 上传校验使用） |

toolchain 镜像 `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest
`sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；npm 缓存归档
SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`
（来源提交 `a2fb4a027a`）。04 使用 `/home/dev/gdds-fe-cache/frontend/npm-cache`；05 使用
`/home/dev/gdds-fe-cache/fe0/npm-cache`。两处归档摘要相同。

## 2. 冻结修复与导航可见性

`duplicates-orphans` 冻结的根因不是网格重绘，而是测试在 1280 视口下点击了不可见的
导航项：`ComparisonPage.tsx` 的 `sidebarCollapsed` 默认在 `innerWidth <= 1440` 收起侧栏，
`.sidebar-is-collapsed .navigation-sidebar { display: none; }` 使 `.nav-item` 的点击
永远等不到可见。修复：

- `frontend/e2e/workspace-shell.spec.ts` 新增 `expandNavigation()`：若「展开导航」按钮可见则
  点击，再等 200ms；`openPreview`、`openItem`、`openTab` 与 `fe4b-orphans-view-table` 起始
  都调用它。1280 截图因此能看到业务导航，符合 kickoff 第 464 行的截图目的。
- `openTab` 选择器从 `.nav-tab[data-tab-key]` 改为 `.nav-tab button[data-tab-key]`
  （`data-tab-key` 在按钮上，外层 `.nav-tab` 只是容器）。
- `ComparisonPage.tsx` 的固定列改为 `freezeColumns = (debug ? 5 : 2) + pinnedColumnCount`，
  让 pinned 业务列真正冻结（原先只冻结了 `#` 元列），符合 F6「固定列按 pinned」。

## 3. 判据 helper（kickoff §5.3 / FE-BEB-03）

新增 `frontend/e2e-real/lib/consumer-criteria.ts`：

- `BundleCriteriaReader`：按 `artifact-closure.json` 的 `closure_entries` 解析
  `artifact_id → logical_path`，校验 `raw_sha256`/`size_bytes`，用 `hyparquet` 在内存解码
  Parquet；不调用产品 view-model 的筛选/定位/汇总函数，不重算身份 digest。
- `assertBundleConsumerCriteria(bundle, context)` 对每个 pair 断言：
  1. 导航形状：固定五组顺序（普通模式）/ `groups` 为空且两侧 `replacement_sides`
     （替换模式）；group/item/tab 唯一；每表整表页签 ≤1 且与筛选页签互斥；同表筛选页签同组；
     谓词 `values` 非空、同类型、去重、按整数或 UTF-8 字节升序。
  2. 未引用表：未被任何页签引用的 surface 表，两侧 `row_count=0`（`null` 绑定表示该侧无快照，
     按 0 计）、`change_kind ∈ {UNCHANGED, BUSINESS_EQUIVALENT}`、无风险/无注释。
  3. 按侧覆盖：仅对「该侧有绑定且该表全部筛选页签 `facts.basis=EXACT`」的侧计算；谓词匹配行
     并集 + 同侧 `DEVICE_ROWS_UNASSIGNED.row_count` = 该侧 `row_count`。
  4. 行定位：`record_kind ∈ {ROW_ADDED, ROW_DELETED, ROW_MODIFIED}` 的普通行集合与 locator
     身份集合相等、身份严格升序且不重复；存在侧 index 在 `[0,row_count)`、同侧不重复、context
     为 null；缺快照侧 index 为 null，有筛选页签时 context 为非空对象；有普通行记录但
     `row_locator_ref=null` 直接失败（不允许表级回退）。
- 接线：`journeys.spec.ts` 的 `uploadAndPreview`、`uploadDirsAndPreview`、r3 恢复包与
  r9-history 下载（用 `recordBundleBodies` 在响应到达时即读 body，避免导航后 body 不可读）；
  `t1.spec.ts` 的 step1/step4 两个 bundle。所有运行都输出
  `criteria <scope> <pair>[tabs=…,fallbackTabs=…,fallbackTables=…,locatedTables=…,locatedRows=…,filterSides=…]`。

## 4. 截图清单

Mock（07/04，均 1280/1920 两宽，共 38 张）：

- `fe4b-nav-two-views`、`fe4b-nav-single-view`、`fe4b-device-tabs`、`fe4b-single-tab-item`、
  `fe4b-sidebar-search`、`fe4b-columns-pinned`、`fe4b-before-only-column`、
  `fe4b-keyless-before-unavailable`、`fe4b-located-rows`、`fe4b-formula-before`、
  `fe4b-gid-change`、`fe4b-duplicates`、`fe4b-orphans-view-table`、`fe4b-table-fallback`、
  `fe4b-table-scope`、`fe4b-filter-unsupported`、`fe4b-count-unknown`、`fe4b-comment-only`、
  `fe4b-preview-topbar-device`（fe-handoff 合并后）。
- 侧栏搜索词为「复合信号」。

真实数据 t1（05，30 张：13 名 ×2 宽 + 4 张沿用）：

- 沿用 FE4a：`fe4-t1-workbench`、`fe4-t1-preview-v1`、`fe4-t1-preview-v2-baseline_to_initial`、
  `fe4-t1-preview-v2-initial_to_modified`、`fe4-t1-review`、`fe4-t1-history-3node`、
  `fe4-t1-archive`；另保留 `t1-v1-diff`、`t1-v2-diff`、`t1-archive-v1`、`t1-history-three-nodes`。
- 新增：`fe4-t1-nav-groups`、`fe4-t1-device-tabs`、`fe4-t1-forward-channel`、
  `fe4-t1-columns`、`fe4-t1-located-rows`、`fe4-t1-nav-diagnostics`。
- 选点（写入 `journey-cases.log`）：device-tabs `item=device:composite tabs=12 tab=table`；
  forward-channel `item=channel:b1_n2 tabs=10 tab=iec104_syx_list`；两者 1280/1920 都触发
  溢出，脚本已验证溢出菜单可达最后一项；nav-diagnostics `pair=initial_to_modified
  code=APP_TABLE_NOT_FOUND item=global:app_cfg`；columns/located
  `table=b1_n2_iec104_syx_list item=channel:b1_n2 tab=iec104_syx_list`。
- `fe4-t1-nav-groups-1920.png` 与 `fe4-t1-preview-v2-initial_to_modified-1920.png` 同为
  `f8ab2df8…`：1920 下侧栏本就展开全部五组，属预期，不是重复截图错误。

## 5. 证据运行记录

| 运行 | 节点 | 时间（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| mock-9 | `gw-dms-07.lan` | 17:07:39–17:10:14 | 252 vitest + 106 Playwright，152 PNG，exit 0 | `1391ef9a5784974b52641041f46f140d0b82f313904e2439981faeb3b22f933d` |
| mock-10 | `gw-dms-07.lan` | 17:12:06–17:14:40 | 同 mock-9（连续第二次） | `a5ee14730c70c1b854decd017969c7984ba552452f7f1b9a1b2780ff8268d2ab` |
| 04 mock | `gw-dms-test-04.lan` | 17:19:17–17:21:50 | 106 Playwright，152 PNG，exit 0 | 运行日志 `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261111T171917Z.log`，`46bbf3b7943a42cfe8b9a178fa5a2eac3b418825bb16d3aa25f88fa35b30c495` |
| 04 journeys | `gw-dms-test-04.lan` | 17:06:59–17:17:27 | 20/20，exit 0，`cleanup_status=ok` | `f7e5d6e0c4238283bc92e83a5d78e200441ac0d77ba77456e0ca386a72ef731d` |
| 04 validate | `gw-dms-test-04.lan` | 17:21:50Z 起 | `packages=4 failures=0` | `4dd013fa6aeb680cb12e57ca37ec1cfd01e0c72c533a3032e064059c466f5bcd` |
| 05 t1 | `gw-dms-test-05.lan` | 17:08:45–17:13:01 | 1/1，exit 0 | `214b3809a6f18decc7a48d4bf84193b1456d1e906106cfb23af3e231e3c79b4f` |

- 所有运行均记录 `head_start=head_end=fcf4268c1a`、`frontend_tree_start=end=f3f1fdf1…`；
  mock-9/10 的截图目录分别为 `/home/dev/gdds-fe-shots/fe4b-mock-9`、
  `/home/dev/gdds-fe-shots/fe4b-mock-10`；04 为
  `/home/dev/gdds-fe-evidence-04/fe4b-fcf4268c1a/shots`。
- journeys `journey-cases.log` SHA256
  `70ac42cc962674e3dd02ac129b5b0acd85da0a71c75c865a1a713a3d4a1d5e24`；
  替换模式判据行 `criteria j1-archive-mainline replacement initial_to_modified[tabs=12,
  fallbackTabs=0,fallbackTables=0,locatedTables=0,locatedRows=0,filterSides=0]`。
- t1 `journey-cases.log` SHA256
  `ea7f729e115ccc5f6eab1f6011c9713bca20dce4a571951e36b88c1513f601f2`；判据：
  step1 `initial_to_modified[tabs=169,filterSides=11,locatedTables=0]`；step4
  `baseline_to_initial[tabs=116,filterSides=3]`、
  `initial_to_modified[tabs=116,fallbackTabs=0,locatedTables=1,locatedRows=6,filterSides=6]`
  （与 BE-b 基准 v2 FULL 1 张表 6 行一致）。
- t1 M1：`t1-v1-modified renderer_increment_bytes=20336640`（19.39 MiB），
  `t1-full=7176192`。FE4a 为 19,300,352（18.41 MiB），FE3a 基准 24.86 MiB、2× 上限
  49.72 MiB，未超。
- 截图证据目录：04 `…/fe4b-fcf4268c1a/shots`（152 个文件，含 19 名 `fe4b-*` ×2）；
  05 `/home/dev/gdds-fe-logs/fe4b-t1-evidence-3/evidence/`（30 张 PNG；
  `--evidence-dir` 只收到 `test-results`，截图按 Playwright testInfo 输出目录落在 log-dir 的
  `evidence/`，与 `journey-cases.log` 同目录）。

## 6. 调试计数与重做说明（DC68）

- mock 全量：最终候选 `fcf4268c1a` 上连续两次（mock-9/10）。此前在候选演进中另有
  `e225b63224`（mock-5/6）、`d8d58318`（mock-7/8）各两次；这些运行绑定旧提交，不作为最终证据。
- journeys 完整集：共运行三次。第 1 次（`e225`）17/20，失败为旧断言与判据 bug；第 2 次
  （`d8d58318`）18/20，r9 的 body 读取在导航后不可用、r7-withdraw 遇到一次 worker
  `deployment storage root unavailable`（见下）；修复后第 3 次 20/20。
- t1：调试两次（选择器、判据各一次，均在前一候选）后，证据运行在 `e225`、`d8d58318`、
  `fcf4268c1a` 各通过一次；最终证据取 `fcf4268c1a`。t1 的 4.3 分钟与判据值稳定。
- 04 上传校验：`e225` 与 `fcf4268c1a` 各一次 4/0；最终证据取后者。

## 7. 偏差与未决

1. **`fe4b-no-canonical-change` 未截取**：mock e2e 没有 `NO_CANONICAL_CHANGE` 的模拟路径
   （`SubmitDialog.tsx` 有文案），t1 真实数据的最短旅程也不产生该提交结果。按草案记偏差，
   不扩范围；如 owner 需要，可在后续阶段补一条 mock 或单独真实数据用例。
2. **`fe4b-columns-pinned`**：全部 fixture 中没有「pinned 且 display_name≠列名」的列
   （唯一的中文显示名是非 pinned 的 `comment_demo.id`/`device_st.before_only`）。当前用
   `duplicates-orphans` 的 pinned `description` 展示固定列，用 `comment-only` 展示中文名，
   两个语义分开覆盖；需要 owner 确认是否接受。
3. **t1 导航诊断**：本次真实数据只复现 `APP_TABLE_NOT_FOUND`（`global:app_cfg`）；截图为就地
   提示，未覆盖其他代码。
4. **r7-withdraw 偶发**：第 2 次 journeys 运行中，第二个上传的 preview 操作在 worker 侧以
   `ValueError: deployment storage root unavailable` 失败（`runtime_preflight.check`
   的 OSError 分支），同一测试在第 1、3 次运行均通过；第 3 次 20/20 说明是环境/预热类瞬态，
   未改产品代码。
5. **fe-handoff 带入项**：`fe4b-preview-topbar-device` 依赖 fe-handoff 的设备栏
   （`gotoWithHandoff` + `.compare-header .device-bar .device-context`），只在合并后存在。
6. **M1 方差**：调试运行曾记录 27,598,848（26.32 MiB），最终证据为 20,336,640（19.39 MiB），
   均低于 2× 上限；该值仍是单次采样，不作为趋势。

## 8. 提交序列（相对 `fe4b-base`，最早在前）

`64219e2c5b` … `2a4ea17f13`、`20ee52007c`、`c36b9bbe15`、`d04faf9bd1`、`1e3e641814`、
`1862a0fc3d`、`cf6eedc5a6`、`e7b19234fe`、`764b3155a1`（fe-handoff 设备目录）、
`16730f6c0f`、`251640f104`、`9a623431f7`、`f24a5fb75e`、`304e991c85`、`b4ed9c59d1`、
`d78bd7d294`、`cc39083322`、`496cb787bf`、`f65efdb22d`、`d32466be51`、`a059fbbf15`、
`97acb06a88`、`cd13c0b320`、`25d5099b6c`、`6a738607eb`、`862a1adfeb`、`85784805bb`、
`e72cea531f`、`65f82b2935`、`95d61d6944`、`8c3e2a6a2c`、`fa2f16790b`、`88474e610e`、
`415e96c57a`、`7daf61bdb2`、`e225b63224`（Merge fe-handoff）、`d8d583183c`、`fcf4268c1a`。

## 9. 审核建议

- 重点看 §2 的侧栏展开与 `freezeColumns` 语义、§3 判据 3/4 的边界（空绑定、替换模式按侧、
  `DEVICE_UNASSIGNED` 同侧计数）。
- 对照 §4 的 19+13 个截图名核对 kickoff §7.3；`fe4b-*` 应在 04 的 152 个 PNG 里，
  t1 的 30 张在 05 evidence 目录。
- 按 §7 的偏差决定是否补截图/补判据；未推送，tag 与 main 合并按 owner 指示。
