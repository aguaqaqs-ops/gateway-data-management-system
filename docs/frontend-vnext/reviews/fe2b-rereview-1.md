# FE2b 复审报告（第 1 轮）

- **复审对象：** 分支 `fe-vnext`，代码候选 `5d1749675621a020a052690b95d55111af5509f9`（`frontend/` 树 `a0f8ce750b`）；
  handoff 提交 `7682297b72071cd08473039409ee58eaa68fa216`（只改 handoff，`frontend/` 树相同）。
- **范围：** `bf4942e0a8..7682297b72`，7 个提交，24 个文件。没有改动 fixture、生成器及其输入 JSON、依赖或 lockfile；`vnext/` 树仍为 `2791d3ff3d`。
- **依据：** [FE2b 审核](fe2b-review.md) §4、§6、§8。
- **日期：** 2026-11-03。
- **结论：PASS。**
  - B1–B9 都已修复，M1–M9、M11 一并处理，M10 已在 handoff 中说明；
  - 三个变异探针都能检出；
  - 剩下的工作：
    - 04 阶段退出取证；
    - owner 看图确认（§4）；
    - 两项偏差交 owner 决定：抽屉缺少各比较对的摘要，以及 M10。
  - 另有 4 项次要问题（§3），建议带入 FE2c。

## 1. B1–B9 核对

| 项 | 修复 | 核对 |
| --- | --- | --- |
| B1 | 单子节点统一用 `prefix + operator`（`formula-view.ts:93`）；恢复 `"| - 线路保护装置 A:线路电流"` 断言；新增“一元减号为第一个子节点”的用例；公式内容区随抽屉伸展 | 截图 `formula-preview` 中最后一行“\| - 线路保护装置 A:线路电流”完整可见。**通过** |
| B2 | 两份模拟数据已改正；`mock-data.test.ts` 按 `history/contracts.py:108–113` 核对全部模拟 History 节点；`historyStatus` 不再看基线的 `archive_disposition` | **通过** |
| B3 | Vite 插件把渲染进产物的模块清单写到 `dist/.vite/rollup-modules.json`，检查脚本拒绝 `src/features/dev/` 下的模块 | 我在新候选上重做了上一轮的探针 1：runner exit 1，输出“production dist includes development-only modules”（§2.3）。**通过**。清单的位置见 §3 N3 |
| B4 | 错误页在 `SCOPE_FORBIDDEN` 时以“当前身份没有该操作的权限”为标题；托盘就地显示这句文案与错误码，可复制；操作卡片同样处理 | 新增 e2e 覆盖加载、操作查询和发起历史比较三处的 403。截图 `workspace-error-no-connected` 的标题已改。**通过** |
| B5 | 意图逻辑提成 `resolveHistoryCompareIntent` / `readHistoryCompareIntent`；“查看差异”与托盘共用 `startOrRetryCompare`；超时由 `historyCompareRequestTimeoutMs()` 读取，e2e 通过 `addInitScript` 设置为 700 ms | `idempotency.test.ts` 现在测试产品函数。实施会话的探针（`9afb7a59a7`，在 key 复用条件上加 `&& current.key === ""`）使单测失败。**通过**。测试钩子见 §3 N4 |
| B6 | 工作区为 `OPEN` 时两个目录按钮启用（点击在 FE2c 接入）；“归档主线”按审核状态与 `eligibility_note` 启用；开发备注已删除 | **通过** |
| B7 | 比较对显示为“节点 i → 节点 i+1”，`pair_id` 放进悬停提示；bundle 分下载中、已就绪、下载失败（可重试）三种状态，就绪后才显示“打开差异工作台”；状态文字取 §4.5；运行中锁定托盘与工具栏中的比较操作，按钮显示“比较中” | 截图 `history-compare-running`、`history-compare-result-drawer`。**通过** |
| B8 | 各基线放在同一层，当前基线在最上，其余按时间倒序；提交与工作区挂在所属基线下；可以展开和折叠；树上有“比较 N”；状态用圆点加文字；排序只在同一父节点内进行；删除了“展开全部” | 截图 `s1-workbench`、`s2-compare-tray`，与草图 S1 的结构一致。**通过** |
| B9 | 拍主表截图前移开鼠标，1280 重新悬停 | `s4-grid-normal-main-1280` 没有悬停提示，与 `s4-grid-normal-hover-1280` 不同。主表截图与 `s3-workbench-normal` 相同，两者本来就是同一画面。**通过** |

**次要问题：**

- 已核对：
  - M1：附加标记不再占用状态位，文字为“项目身份例外”；
  - M2：基线与规则迁移不再显示状态，只有当前基线加“当前基线”；
  - M3：操作卡片按错误码显示，不再一律显示“连接中断”；
  - M4：工作台节点使用单独的 `workbenchNode` 参数，往返差异浏览后选择仍在；
  - M5：审核状态有了文字；
  - M7：去掉了无意义的断言，终态用例的 mock 改为有限次返回；
  - M9：没有任务时不再显示任务指示。
- M6（等待时长取自 `started_at`）有新问题，见 §3 N2。
- M8、M11：handoff 中有说明，`presentation.test.ts` 新增一条用例：表既有比较键又有 ordered 记录时，移动记录不丢。

`presentation.ts` 的改动已对照：只有在标准记录与 ordered 记录描述同一批行时，才只用标准记录；ordered 记录中的 `ORDERED_ROW_MOVED` 会保留。**通过。**

## 2. 证据

### 2.1 handoff 证据

在 05 上重算，结果与 handoff 一致：

| 证据 | SHA256 | 核对 |
| --- | --- | --- |
| 候选完整运行 `frontend-tests-20261103T154941Z.log` | `01951df3…44039c862` | 一致。HEAD `5d17496756`，`frontend/` 树 `a0f8ce750b`；缓存来源提交 `a2fb4a027a`，归档 `0d861824…089f4`；exit 0 |
| 外层 `targeted-full-run-5d174967-05-corrected-cache-source-wrapper.log` | `d024b18c…071ad571` | 一致 |
| 缓存来源提交参数填错的那次运行 `frontend-tests-20261103T154807Z.log` | `b44c13b8…a34baf21` | 一致。按 DC68 处理：改正参数后从头重跑，这次不作为证据，处理正确 |
| B1 探针 `frontend-tests-20261103T155323Z.log` | `b70ea9ad…3efdf38` | HEAD `73349f65a2`（父提交为候选），只改 `unaryPrefix`；exit 1 |
| B5 探针 `frontend-tests-20261103T155420Z.log` | `94282f1b…5d5f9bc` | HEAD `9afb7a59a7`（父提交为候选），只改 key 复用条件；exit 1 |
| B3 探针 `frontend-tests-20261103T155510Z.log` | `23329e27…0990d3b0` | HEAD `9991da34ae`（父提交为候选），在 `App.tsx` 直接导入 `mock-data`；exit 1，检出 `src/features/dev/mock-data.ts` |
| 截图清单 `screenshot-sha256-5d174967-05.txt` | `a5fdc5e0…bcf52868fa` | 开发主机与 05 上的副本相同。50 项与 05 证据目录一致 |

**fixture 的说法需要更正：**

- handoff 第 3 节写“复审方随后在最终源码候选上独立调用该脚本两次”。实际上，我是在上一个候选 `bf4942e0a8`（代码 `5ac704c6`）上复现的。
- 由于 `bf4942e0a8..7682297b72` 没有改动生成器、输入 JSON 和 `vnext/`，复现结果对新候选仍然成立。
- 04 取证的 handoff 应把这句改为“在 `5ac704c6`/`bf4942e0a8` 上复现，此后生成输入未变”。

### 2.2 我在 05 上的独立运行

- **源码传输：** 只读生成 `git bundle create … fe-vnext ^bf4942e0a8`，SHA256 `37b09797…b134dc2d`。05 上 `FETCH_HEAD` 为 `7682297b72`，main（`7ac79ab53c`）没有移动。
- **worktree：** `/home/dev/gdds-fe-rereview1-fe2b-7682297b-05`，detached、clean，已建 `legacy` 链接；没有占用标记。
- **缓存：** 使用 FE0 归档（`0d861824…089f4`）。

日志在 05 的 `/home/dev/gdds-fe-logs/fe2b/review-rereview-1/`，节点为 `gw-dms-test-05.lan`：

| 运行 | 起止（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 准备 `rereview-setup-05.log` | 16:10:48 | HEAD `7682297b72`，`frontend/` 树 `a0f8ce750b`，clean | `1fca3394…dd90a8e75` |
| `run-tests.sh --screenshots` `frontend-tests-20261103T161125Z.log` | 16:11:25–16:11:59 | **exit 0**。24 个文件 107 项单测通过；生产检查通过（含模块清单）；e2e 15 passed。HEAD 与树起止不变，运行后 clean | `3b08a3c0…caf70590` |
| 外层 `runner-wrapper-05.log` | 同上 | `runner_exit=0` | `6e412d82…54a83b3` |
| 截图清单 `screenshot-sha256-rereview1-05.txt` | — | 50 张 | `a1d2286c…5120ec` |

**截图：** 50 张中 46 张与实施会话的截图逐字节相同，其余 4 张我逐张看过：

- `manual-recovery-required-1280/1920` 中“已等待”的秒数不同（24597 与 25901），原因见 §3 N2；
- `history-compare-result-drawer-1280`、`workspace-error-no-connected-1280` 内容相同，只是像素级渲染差异。

### 2.3 我的探针

05 上的一次性 worktree，以 `7682297b72` 为基础，重做上一轮的探针 1（`App.tsx` 导入 `./features/dev/mock-data` 并使用 `WORKSPACE_RESPONSE`），用后删除。

- 结果：runner exit 1，生产检查输出“production dist includes development-only modules”。
- 日志在 `review-rereview-1/probes/`：
  - `probe-b3.log`：`a80e9aec…228bfe5f`；
  - runner `frontend-tests-20261103T161421Z.log`：`51bbde90…f0704be70`；
  - 脚本 `probe-b3.sh`：`72ed296a…228daa20`。

## 3. 次要问题（不阻塞，建议带入 FE2c）

- **N1** handoff 中 fixture 复现的说法（§2.1），在 04 取证的 handoff 中更正即可。
- **N2** 操作卡片的等待时长现在从 `started_at` 计算（M6）。
  - 截图中模拟数据的 `started_at` 是固定的 `2026-11-03T09:00:01Z`，所以显示“已等待 25901 秒”。这个值随拍摄时间变化，截图不能复现；
  - 长时间直接显示秒数也不好读。
  - **建议：**
    - 超过一分钟按“时/分/秒”显示；
    - e2e 用 Playwright 的 `page.clock` 固定时间，或让模拟数据的时间相对测试时间生成。
- **N3** 模块清单写在 `dist/.vite/rollup-modules.json`，会随构建产物一起发布，内容是源码路径。建议写到 `dist` 之外，或检查完成后删除。
- **N4** `window.__gatewayTestConfig` 在生产构建中同样生效。影响只是超时可以被页面脚本改短，建议只在开发构建中读取，或者改由模拟会话注入。

## 4. 交 owner 确认

**截图：**

- 以 04 取证的截图为准；
- 我在 05 上的同一套截图在 `/home/dev/gdds-fe-evidence/fe2b/rereview1-7682297b-05/`，可以先看。

| 组 | 文件 |
| --- | --- |
| 草图 S1 工作台 | `s1-workbench-1920/1280` |
| 草图 S2 比较托盘 | `s2-compare-tray-1920/1280`、`history-compare-running-*` |
| 历史比较结果抽屉 | `history-compare-result-drawer-*` |
| 草图 S3 的 Preview、History 顶栏 | `s3-header-upload-*`、`s3-header-history-*` |
| §6.3 S1 正常业务场景 | `s3-workbench-normal-*`、`s4-grid-normal-main/hover/debug-*` |
| 无草图页面 | `history-compare-connection-interrupted-*`、`manual-recovery-required-*`（N2）、`workspace-error-no-connected-*`、`navigation-fallback-*`、`formula-preview/history-*` |

**偏差，需要 owner 决定：**

1. 草图 `compare-1920` 中，抽屉的每个比较对有表数、变更表数、降级表数和按表列出的增删改计数。
   - 实现只显示节点、比较对“节点 i → 节点 i+1”和差异记录数；
   - 摘要需要在工作台解析已下载的 bundle，可以在 FE2c 补，也可以接受现状。
2. M10：S1 fixture 中有一张 0 → 0 行的 `composite_signal_point`，放在“其他表”中。它是生成器固定生成的表，可以接受。

## 5. 下一步

1. **04 取证**（kickoff §7.3、§7.4）：
   - 在 `ct108-gw-dms-04` 的 clean detached worktree 上，对代码候选 `5d17496756` 运行一次完整的 `./frontend/scripts/run-tests.sh --screenshots <worktree 外的绝对路径>`；
   - 工具链镜像与 npm 缓存沿用 04 上 FE0 的预填充（默认路径），运行前核对：
     - config digest；
     - 7 个 DiffID；
     - 归档 SHA256 `0d861824…089f4`；
   - 取证提交只改 handoff，同时完成 N1 的更正；提交后由审核会话做证据核对。
2. **owner：** 确认 §4 的截图与两项偏差；N2–N4 是否带入 FE2c 也在此时决定。
3. **退出：** 由设计会话把附注 tag `fe-fe2b-exit` 打在 04 取证的 handoff 提交上，然后合入 `main`。
4. **合入后可以清理：**
   - 审核会话：
     - 开发主机上的 `/home/dev/gdds-fe-review-fe2b-bf4942e0`（本轮已切到 `7682297b72` 只读查看）；
     - 05 上的 `/home/dev/gdds-fe-review-fe2b-bf4942e0-05`、`/home/dev/gdds-fe-rereview1-fe2b-7682297b-05`；
     - 两端的 `src-review-fe2b-bf4942e0.bundle`、`src-rereview1-fe2b-7682297b.bundle`；
   - 实施会话：handoff 第 9 节列出的 worktree 与 bundle。
