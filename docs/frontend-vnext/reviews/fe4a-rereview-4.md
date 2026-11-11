# FE4a 复审第 4 轮（定向复审 fix4）

- **复审对象：** fix4 区间 `59c5b8cfca0ae6d07a64a6a4e1645f724fa2ad1f..16f4306306d082690e612cee4d3c768977447fd9`（3 个提交）。
  - X：`d12e3b8f706c99c66d0de2e1763f145f95862c92`（第一个候选，05 调试停止，保留）；
  - Y：`26236839f7ce3e0f2c2fedd5cddd62b657ee87ea`（修正候选，`frontend/` 树 `d8e9a2e717e8d153b3a7794f25b76186c4bc4d5e`）；
  - H：`16f4306306d082690e612cee4d3c768977447fd9`（fix4 handoff，`refs/fe4a/fix4`，开发主机分支 `fe4a-fix4`），相对 Y 只加 `docs/frontend-vnext/fe4a-handoff-fix4.md`。
- **依据：** [FE4 kickoff](../fe4-kickoff.md) 修订 7（开发主机 main 合并提交 `42f48bea58`）§16、§17、§7.2、§7.3、§8 FE4a、§10 Q18–Q20、§11.2 第 10 项、§3.8；[复审第 3 轮](fe4a-rereview-3.md)（`35c60972ff`）；[证据核对第 1 轮](fe4a-evidence-check-1.md)（`14f8daa7f8`）；fix4 handoff 与实施会话的交付回复。
- **复审会话：** FE4a 审核会话（会话标签 `fe4a-rereview4`，运行时会话名 `fe4a-review`；本轮在新对话中承担审核会话角色）。
- **日期：** 2026-11-11，07 上的运行在 03:47–03:58 UTC 之间。
- **结论：通过。** 下一步见 §7：`fe-vnext` 用 `--ff-only` 快进到 H，在 H 上按 kickoff §16.5–§16.7 跑四项证据。
  - 路径与 diff 范围符合 §5.2、§16.2 第 3 项与 §17.4；
  - `expectDisabledWithReason` 按 §17.2 实现，两支不互相回退；`expectReviewReasonShownOnce` 按 §16.2 第 2 项实现，四处调用齐全；
  - 区分力探针 7 个提交全部符合预期，包括 kickoff 没有要求、本会话补充的“不回退”探针；
  - 07 模拟接口全量通过；与复审第 3 轮 `full1` 的 `--stable` 比较 exit 0，没有内容变化；
  - 05 调试日志 20 个 scope 全部通过，§16.2 第 5 项与 §17.5 的落点都在日志中找到，J1、J2 共 8 次预检的异常集合与 FE3 kickoff §4.6 的表一致；
  - §11.2 第 10 项核对：只有三种结构，与 §17.1 和 handoff §4.2 一致；
  - 回源复跑与实施会话日志除开头字段外逐行相同；handoff 中 9 处 SHA256 全部经过路径配对，没有 `--allow`。

  另有 2 条非阻塞（§5 N23、N24），都是 handoff 文字问题，不影响本轮结论。

## 1. 路径核对与范围

开发主机只读核对 git 对象。

| 检查 | 结果 |
| --- | --- |
| 提交链 | `59c5b8cfca` → `d12e3b8f70`（X）→ `26236839f7`（Y）→ `16f4306306`（H），线性，每个提交只有一个父提交 |
| `:vnext` | `16ffe72829`、`59c5b8cfca`、X、Y、H 都是 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `frontend/` 树 | `59c5b8cfca`：`802bdfb1a42b5319b483f3c4324d2b609a1b57b0`；X：`f6a8a1e2649d86b8335e32d920159872fe8ce0c7`；Y 与 H：`d8e9a2e717e8d153b3a7794f25b76186c4bc4d5e`，与 handoff §1 一致 |
| §5.2 路径核对（`<main>` 为 `16ffe72829`） | `git diff --name-only 16ffe72829 16f4306306` 只含 `frontend/` 与 `docs/frontend-vnext/` 下的路径 |
| `59c5b8cfca..Y` | 只有 `frontend/e2e-real/journeys.spec.ts`（+5）与 `frontend/e2e-real/lib/ui.ts`（+31/−1） |
| `X..Y` | 只有 `frontend/e2e-real/lib/ui.ts`（+18/−13） |
| `Y..H` | 只有 `docs/frontend-vnext/fe4a-handoff-fix4.md`（新建） |
| `frontend/src/`、`frontend/e2e/`、`t1.spec.ts`、`frontend/scripts/` | 无改动 |
| `fe-vnext` | 开发主机仍为 `59c5b8cfca`（`/home/dev/gdds-fe` 检出），复审期间未动 |
| 节点上的 ref | 07：`refs/fe4a/fix4` → H，`refs/fe4a-fix4/26236839f7` → Y，`refs/fe4a-fix4/d12e3b8f70` → X；05：后两者相同 |
| 打包流程筛查（§7.4） | `git diff --stat fe-fe3c-exit 16f4306306 -- frontend/src/features/workbench/upload-package.ts frontend/src/features/workbench/UploadStepCard.tsx` 为空，不触发 t4 |

**helper 代码核对（Y 的 `ui.ts:132-165`）：**

- `expectDisabledWithReason` 依次为 `toBeDisabled()`、`toHaveAccessibleDescription(reason)`，再读取一次 `aria-describedby`；
- 有 id 时逐个取所指元素，文字（`trim` 后）等于 `reason` 的第一个元素断言可见，没有命中则在 `:151` 失败并直接 `return`，不进入兄弟元素分支；
- 没有 id 时用 `59c5b8cfca` 原来的 `xpath=following-sibling::span[contains(@class, "disabled-reason")]`，断言文字与可见；
- `expectReviewReasonShownOnce`：`.review-actions .review-actions__reason` 计数 1、文字等于 `reason`、可见；`.review-actions .disabled-reason` 计数 0；
- `journeys.spec.ts` 只在 `r7-reviewer-withdraw`（`:961`）、`r11-review-conflict`（`:1217`）、`j1-archive-mainline`（`:1550`）、`j2-manual-close`（`:1936`）各调用一次 `expectReviewReasonShownOnce`，原有调用未改。

## 2. 独立运行、探针与核对

### 2.1 07 模拟接口全量（kickoff §16.4 第 3 项）

开始前 `ssh -o BatchMode=yes ct109-gw-dms-07 'echo OK'` 返回 `OK`，`/home/dev/gdds-node-busy.d` 不存在，本轮新建路径都不存在。新建 detached worktree `/home/dev/gdds-fe4a-rereview4`（Y，clean，建了 `legacy` 符号链接）。

- **工具链：** `mcr.microsoft.com/playwright:v1.64.1-noble`，用 Y 的 `docker-save-image-identity.py` 对 `docker save` 归档现场导出身份，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 个 DiffID，与实施会话的身份文件逐字节相同。
- **npm 缓存：** 默认 `/home/dev/gdds-fe-cache/frontend/npm-cache`，归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`。
- **命令：** Y 的 `run-evidence-wrapper.sh --session fe4a-review --worktree /home/dev/gdds-fe4a-rereview4 --entry run-tests.sh --log-dir /home/dev/gdds-fe-logs/fe4a-rereview4 --shots-dir /home/dev/gdds-fe-shots/fe4a-rereview4/full1 -- --e2e`，`GATEWAY_FE_TEST_WORKERS=2`。

| 项 | 结果 |
| --- | --- |
| 起止 | wrapper `20261111T034745Z`–`20261111T035027Z`，入口 `2026-11-11T03:48:08Z`–`2026-11-11T03:50:27Z` |
| HEAD 与树 | 起止都是 Y，`frontend/` 树 `d8e9a2e7`，`vnext/` 树 `49c1de43be`，起止 clean |
| 结果 | `exit_code=0`、`entry_exit=0`；类型检查、lint、构建通过；单测 35 个文件 214 项；Playwright `Running 96 tests using 2 workers`，96 passed |
| 截图 | 198 张 PNG |

| 文件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/fe4a-review-run-tests-20261111T034745Z.log` | `c5f05a7d8c1098a70ece260bb9ec308d1edb4c4fbd92e443d65e39354f91a88c` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/full1-shots.sha256` | `01864ac43ed8c3273614234aa547ee4ec38edd120c778418a651debd456e3f9c` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/identity-toolchain-07.json` | `4961e044044f603d9e088b02ab556af4faa4f41b3b4cbae9e4759fa13f87dcfc` |

wrapper 日志另有 `.sha256` 旁注，内容一致。截图清单格式同复审第 3 轮（相对 `full1` 的路径），198 行。wrapper 记录的 `tracked_frontend_archive_sha256` 随提交时间变化，不作判据（复审第 3 轮 §7 第 3 项）。

### 2.2 与复审第 3 轮 `full1` 的稳定性比较

**本会话的操作错误：** 第一次核对 rr3 清单时，在错误的当前目录运行 `sha256sum -c`（清单是相对路径），198 个文件全部报告找不到。只读操作，没有副作用。改为在 rr3 `full1` 目录内运行，重做一次通过：`/home/dev/gdds-fe-logs/fe4a-rereview4/rr3-manifest-check.log` SHA256 `f66a3a441bb077c953dba114205c38ae47ee83ade23cfcdead00f7e6f481a04b`（日志第一行记录了这次重做）。

| 项 | 结果 |
| --- | --- |
| rr3 清单 | `/home/dev/gdds-fe-logs/fe4a-rereview3/full1-shots.sha256` 现场 SHA256 与交接一致（见下表）；在 `full1` 目录内 `sha256sum -c` 通过，198 个 PNG |
| 两侧文件名 | 198 个相对路径完全相同；按文件字节 184 张相同、14 张不同 |
| 比较脚本 | `/home/dev/gdds-fe4a-rereview4/frontend/scripts/compare-screenshots.py`（Y），与 `59c5b8cfca` 相同（`git diff` 为空），SHA256 见下表，与复审第 3 轮 §2.3 一致 |
| 命令 | `python3 -I <脚本> --stable /home/dev/gdds-fe-shots/fe4a-rereview3/full1 /home/dev/gdds-fe-shots/fe4a-rereview4/full1` |
| 结果 | **exit 0**：`内容变化=0 尺寸不同=0 缺失=0 噪声=14 相同=184`；噪声每张最多 20 个像素（`1280/fe3b-w6-recovery.png`），最大连通块 7 |

| 文件 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/fe4a-rereview3/full1-shots.sha256` | `dd6892b7f5138ad4af636302c2543507fff9d532719774a161d3e5d11c38b621` |
| `/home/dev/gdds-fe4a-rereview4/frontend/scripts/compare-screenshots.py` | `0887a45ecbac9c9d21ec5b0217859f05e565d0198068112cd4ddfcd03ec68eb8` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/cmp/stable-rr3-vs-rr4.log` | `57fbd7b0086faf5c52b2157861a7a789f5740474a83bb50db0737998e302f367` |

按 kickoff §16.4 第 3 项，这次比较代替 fix4 的第 ①、② 次稳定性比较；fix4 不改产品代码与模拟接口用例，截图没有内容变化，owner 按 `59c5b8cfca` 看过的看图清单继续适用，不重新看图。

### 2.3 区分力探针（kickoff §16.4 第 2 项、§17.4）

**能否直接导入：** `ui.ts` 只从 `./env` 导入函数 `resultsDir`；`env.ts` 顶层只有类型与函数定义，环境检查（`requireEnv`）只在调用 `identities()`、`journeyScopes()` 时执行。所以模拟接口用例可以直接导入，不需要复制 helper。探针提交没有改 `frontend/e2e-real/`（7 个提交相对 Y 的 `frontend/e2e-real` diff 都为空），断言用的就是 Y 的 `ui.ts`。

**做法：**

- 基础探针 `probe-base` 在 Y 之上只改 `frontend/e2e/upload-mode.spec.ts`：
  - 从 `../e2e-real/lib/ui` 导入 `expectDisabledWithReason`、`expectReviewReasonShownOnce`、`reviewAction`、`stepUploadAction`、`workshopAction`；
  - 末尾加 5 个 `RR4` 用例：
    - 结构记录：打印各按钮的 `aria-describedby`、`title`、所指元素与后面的兄弟元素；
    - 审核顶栏原因断言：D1 页面，三个审核按钮，原因“该提交已归档”；
    - 审核顶栏只显示一次：D1 页面；
    - 工具栏原生按钮原因断言：W8 页面，`workshopAction("上传")`，原因“已有待审核的提交，撤回后才能重新上传”；
    - `Button` 自带原因对照：W8 页面，`stepUploadAction`，原因同上。
- 其余 6 个探针都以 `probe-base` 为父提交，各改一处产品代码；`no-fallback` 另加一个“回退对照”用例：helper 的复制件，没有命中所指元素时改为回退到兄弟元素分支。
- 源文件与改法脚本在 07 `/home/dev/gdds-fe-logs/fe4a-rereview4/probe-src/`；`patch.py` 对每处替换先断言原文恰好出现一次。
- 运行器在工具链容器中离线 `npm ci`，生成 fixture 后只跑 `-g RR4`，单 worker，自行取放占用标记。

**本会话的操作错误：** 第一版运行器 `/home/dev/gdds-fe-logs/fe4a-rereview4/run-probe.sh` SHA256 `fd54afafeb1565dff4794ab63e2a547754ee9db9dd6f38334405034c57420e44` 由复审第 3 轮的运行器改来。为避免产品改动使单测失败，去掉了 `npm run test:unit`，同时也去掉了它前面的 fixture 生成（`build-golden-bundle-fixture.mjs`）。

- **结果：** 7 个探针全部因 `ENOENT ... src/test/fixtures/generated/preview-full.tar` 失败，每个日志的错误都只有这一种；
- **证据：** 批处理输出 `/home/dev/gdds-fe-logs/fe4a-rereview4/run-rr4-probes.out` SHA256 `6abd8867381d93556dd9c094faeb8e354781c738cd2eeb2e44395dcd24e243ba`，日志在 `probes/`；
- **修正：** 第二版 `/home/dev/gdds-fe-logs/fe4a-rereview4/run-probe-v2.sh` SHA256 `8ea505a682e96bed993e74b136b4cb02d6327656741641718948bf23f310c8fa` 只在 Playwright 前加回 fixture 生成，其余不变，日志写到 `probes2/`；批处理 `/home/dev/gdds-fe-logs/fe4a-rereview4/run-rr4-probes-v2.sh` SHA256 `5aa4baea73186ba720e3b787db5ee3bb47e2c328189b846564c261f406a7f40d`；
- **重做：** 重做一次，结果如下表。

批处理输出 `/home/dev/gdds-fe-logs/fe4a-rereview4/run-rr4-probes-v2.out` SHA256 `efb7c689642e62a51999fe3318e396901a2c03ec18e14e27716b99633122136f`。下表“失败位置”中的行号指 Y 的 `ui.ts`。

| 探针 | 提交（`refs/review/fe4a-rr4/…`） | 产品改动 | 预期 | 实际 |
| --- | --- | --- | --- | --- |
| `probe-base` | `e15b5c4d1bae8b8eb5f6ee9111d287b5f5379158` | 无 | 5 项都通过 | **符合**：5 passed，exit 0 |
| `probe-c12-per-button` | `0d5e6450f781e349bc909b3b157d3ee7fc1bc272` | `ReviewActions.tsx`：`groupReason` 置空、`approveUsesGroup = false`，三个按钮各自显示原因 | 只显示一次失败；原因断言通过 | **符合**：只有“只显示一次”失败，在 `:161`（计数期望 1，实际 0）；三个按钮的原因断言通过 |
| `probe-shared-removed` | `d649f99467a43555de897363d86ead59aef98d4f` | 删掉 `span.review-actions__reason`，保留 `aria-describedby` | 原因断言失败 | **符合**：原因断言在 `:134` 失败（可访问描述为空）；只显示一次也失败 |
| `probe-shared-hidden` | `75fe6cf35e5e9a8d49a14649e95505664d6e2995` | 共享原因加 `display: none` | 原因断言失败 | **符合**：`:134` 通过（被引用的隐藏元素仍计入描述），在 `:146` 失败（期望可见，实际 hidden）；只显示一次在 `:163` 失败 |
| `probe-toolbar-no-sibling` | `3b461d66fe6cf49c3cf27dc135ece9e3d44965dd` | 删掉工具栏按钮后面的 `span.disabled-reason` | 工具栏原因断言失败 | **符合**：在 `:155` 失败（`element(s) not found`）；其余 4 项通过 |
| `probe-toolbar-no-title` | `9f60793d6dcfe23c2fabfbe5c21a0e4e262e6263` | 删掉工具栏按钮的 `title` | 工具栏原因断言失败 | **符合**：在 `:134` 失败（描述为空）；其余 4 项通过 |
| `probe-no-fallback`（本会话补充） | `8fea44a53bd0e3384b546238918f63776a39583b` | 工具栏按钮加 `aria-describedby` 指向新元素，其文字为原因加一个隐藏子元素 `†`；兄弟 `span.disabled-reason` 保留 | Y 的原因断言失败；回退对照通过 | **符合**：Y 的 helper 在 `:151` 失败；`:134` 已通过，可访问描述等于原因（隐藏子元素不计入），而所指元素的文字不等于原因；回退对照通过，共 5 passed、1 failed |

**结构记录（`probe-base`，模拟接口页面）：**

- 审核按钮：`aria-describedby` → `span.review-actions__reason`（父元素 `.review-actions`），没有 `title`，后面没有兄弟原因；
- 工具栏“上传”：没有 `aria-describedby`，`title` 等于原因，后面的兄弟元素是 `span.disabled-reason`，没有 `id`；
- 步骤卡“上传并生成预览”：`aria-describedby` → 同一 `button-wrap` 内的 `span.disabled-reason`，有 `id`，没有 `title`。

与 §17.1 的表一致。

| 日志（`probes2/`） | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/probes2/probe-base-20261111T035622Z.log` | `242f4ee0ad893e1df51b0ead2235dd991a540361728645d4ac695eec9136e323` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/probes2/probe-c12-per-button-20261111T035635Z.log` | `2b1b6a3ba9c8abb8bfbad49be907abf1e35e93d2633c900cd7f0cf6946e784b5` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/probes2/probe-shared-removed-20261111T035651Z.log` | `1152d629b1f02624abed304c20fb95f5e4a31d67bda292ff74c278f325836107` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/probes2/probe-shared-hidden-20261111T035713Z.log` | `66e3e935b5b72bf158fec0402399064a3aff87d4821b1032751b2196640081de` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/probes2/probe-toolbar-no-sibling-20261111T035734Z.log` | `a10d96211d373d92f8e39d0466f3d4b8ead72a5138e695fc011343a390b145f0` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/probes2/probe-toolbar-no-title-20261111T035750Z.log` | `0696bce9b63d2d943df1f62a1a7b1d0774bace817c78c3d7e7502d253707e710` |
| `/home/dev/gdds-fe-logs/fe4a-rereview4/probes2/probe-no-fallback-20261111T035806Z.log` | `52c944e368257490ec5950cf47405107f638ce1b09aa7b7eb7d8f670825a3af4` |

各日志都有 `.sha256` 旁注；日志头记录 hostname、HEAD、`frontend/` 树、`status=0`（探针 worktree clean）与参数。

**探针与 kickoff 的对应：**

| kickoff 情形 | 探针 |
| --- | --- |
| §16.4 第 2 项，不改产品代码 | `probe-base` |
| §16.4 第 2 项，回退 C12 第 3 条 | `probe-c12-per-button` |
| §16.4 第 2 项，删掉共享原因 | `probe-shared-removed` |
| §16.4 第 2 项，共享原因不可见 | `probe-shared-hidden` |
| §16.4 第 2 项，`Button` 自带原因对照 | 各探针中的对照用例，7 个探针都通过 |
| §17.4，工具栏按钮不改 | `probe-base` |
| §17.4，删掉后面的 `span.disabled-reason` | `probe-toolbar-no-sibling` |
| §17.4，删掉按钮的 `title` | `probe-toolbar-no-title` |

### 2.4 05 调试日志与落点（kickoff §16.4 第 4 项、§17.5）

05 `gw-dms-test-05` 上只读核对，没有取占用标记，核对时节点无占用标记。中文内容取回开发主机后核对。

| 项 | 结果 |
| --- | --- |
| wrapper 日志 | `hostname=gw-dms-test-05.lan`；`head_start`、`head_end` 都是 Y；`frontend_tree_start` 为 `d8e9a2e7`，`vnext_tree_start` 为 `49c1de43be`；`status_start=clean`、`status_end=clean`；`openapi_compare=match`、`suite_exit=0`、`cleanup_status=ok`、`entry_exit=0`、`busy_end=absent` |
| `suite-summary.txt` | `suite_cases_total=20 suite_cases_passed=20 suite_cases_failed=0`，`suite_stats_flaky=0` |
| 入口日志 | `20 passed (6.2m)`；`entry-journeys-y.log` 与原名入口日志（带进程号后缀）逐字节相同 |
| 现场重算 | 实施会话 05 清单 `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/handoff-sources-05.sha256` 在 05 上 `sha256sum -c` 全部通过；另抽查 wrapper 日志、case log、`results.json` 与 fe0 npm 归档，都与 handoff 相同 |

| 文件（05） | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/fe4a-impl-run-real-backend-e2e-20261111T031639Z.log` | `913715c09b4f50e78ef0cc468ec444d098ea1313ade2dfa1385cd1519ee4b6c3` |
| `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/evidence/journey-cases.log` | `4bd721ef3789831ed0cd00ca417f569291c41a4b0bdba3f040c70124b5aee4bd` |

**落点（case log 行号）：**

| §16.1 未执行部分 | 落点 | 核对 |
| --- | --- | --- |
| J1 第 4 步以后 | 第 21–29 行：`j1-step4 ok baseline_to_initial.changed=0 initial_to_modified.changed=5`，第 7、10、11、13 步，`j1 ok three-node history compare browsed` | 符合 FE3 kickoff §4.6 J1 第 4 步的判据（0 与 ≥ 1） |
| J2 第 8 步 | 第 36–37 行，`head=3` | 符合 |
| `r7-reviewer-withdraw` 提交人一侧与两侧 `assertClean` | 第 12 行 `r7-reviewer-withdraw ok` | 用例中 `appendCaseLog` 在 `expectPointersCleared`、树状态“已撤回”、`expectEnabled(workshopAction("上传"))` 与两侧 `assertClean` 之后，所以该行出现即这些断言都已通过 |
| `r11-review-conflict` 证据截图与两侧 `assertClean` | 第 17 行；`evidence/r11-review-conflict-r11-review-conflict.png` 存在 | 同上，`appendCaseLog` 在两侧 `assertClean` 之后 |
| X 上失败的三个 scope 的后续步骤 | 第 5、8、10 行 | 符合 |

**J1、J2 各次预检的异常集合**（与 FE3 kickoff §4.6 的表逐项对照；`business_issues` 都等于 `anomalies` 去掉 `APPROVED_SIBLING_EXCLUDED` 与 `PROJECT_IDENTITY_EXCEPTION`）：

| 行 | 步骤 | 项数 | 内容 | 与表 |
| --- | --- | --- | --- | --- |
| 19 | J1 第 2 步 | 1 | `GENERATION_TIME_MISSING`（`MODIFIED`，A） | 一致 |
| 22 | J1 第 7 步 | 3 | `BASELINE_TIME_UNAVAILABLE`（[B]）、`GENERATION_TIME_MISSING`（`INITIAL`、`MODIFIED`，B） | 一致 |
| 25 | J1 第 11 步 | 2 | `BASELINE_TIME_UNAVAILABLE`（[C]）、`GENERATION_TIME_MISSING`（`MODIFIED`，C） | 一致 |
| 27 | J1 第 13 步 | 3 | 同上两类（D）加 `PROJECT_IDENTITY_EXCEPTION`（D） | 一致 |
| 30 | J2 第 1 步 | 1 | `GENERATION_TIME_MISSING`（`MODIFIED`，A） | 一致 |
| 32 | J2 第 3 步 | 8 | `APPROVED_SIBLING_EXCLUDED` × 2（C、E）、`BASELINE_TIME_UNAVAILABLE`（[B, C, E]）、`GENERATION_TIME_MISSING` × 5（B ①②、C ②、E ①②） | 一致 |
| 34 | J2 第 5 步 | 7 | `APPROVED_SIBLING_EXCLUDED`（E）、`INITIAL_SOURCE_UNEXPLAINED`（`INITIAL`，E）、`BASELINE_TIME_UNAVAILABLE`（[B, E]）、`GENERATION_TIME_MISSING` × 4（B ①②、E ①②） | 一致 |
| 36 | J2 第 8 步 | 2 | `BASELINE_TIME_UNAVAILABLE`（[C]）、`GENERATION_TIME_MISSING`（`MODIFIED`，C） | 一致 |

J2 中的身份按第 4 步 `closed=` 与第 7 步 `archived=`、`closed=` 的提交号对应：B 为第 7 步归档的提交，C 为第 4 步关闭的提交，E 为第 7 步关闭的提交。

**fix2 的应用代码改动：**

- **C8（归档对话框重读）与 C12 第 2 条（处置说明独占一行）：** handoff §6 给出的落点成立。J1 第 9–10 步走重新预检路径；J2 用例对 `.review-disposition-line` 断言文字。
- **C12 第 1 条（错误提示移出按钮行）：** handoff 的落点不准确，见 N24。

**07 的 `run-tests.sh`（不带 `--e2e`）：** `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-07/fe4a-impl-run-tests-20261111T031548Z.log` SHA256 `0e66de6a5b2ad506a9c60b1060ee531cde3d59e741bab0d0d91838c9188afdad`（现场重算与旁注一致）。

- 起止 HEAD 为 Y，起止 clean，`run_e2e=0`，`exit_code=0`；
- 类型检查（`tsc -b`，`tsconfig.json` 引用 `e2e-real/tsconfig.json`，所以包含 `e2e-real/`）、lint、单测 35 个文件 214 项与构建都通过。

### 2.5 X 的停止记录（kickoff §17.5）

- **05：** `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-05/fe4a-impl-run-real-backend-e2e-20261111T024803Z.log` SHA256 `8f805f5580fac222df07973afd6fd7f7bee632aed6cc4f7622e71ae41799cd5f`（现场重算与旁注一致）。
  - 日志字段：起止 HEAD 为 X，起止 clean；`openapi_compare=match`、`suite_exit=1`、`cleanup_status=ok`、`busy_end=absent`；
  - `suite-summary.txt`：`r4-submit`、`r7-withdraw`、`r7-approved` 失败，17/20，没有 flaky；
  - 入口日志：三处都是 `aria-describedby references at least one element`（期望大于 0，实际 0），位于 `lib/ui.ts:137`，调用处为 `journeys.spec.ts:590`、`:746`、`:861`；
  - 三个 `artifacts/journeys-*` 目录各有 `error-context.md`、`test-failed-1.png`、`trace.zip`；
  - Y 目录中的 `entry-journeys-x.log` 与 X 目录中的原名入口日志逐字节相同。
- **07：** `/home/dev/gdds-fe-logs/fe4a-fix4-d12e3b8f-07/fe4a-impl-run-tests-20261111T024702Z.log` 起止 HEAD 为 X，起止 clean，`entry_exit=0`，单测 214 项通过。

与 handoff §3、kickoff §17.1 一致。

### 2.6 回源 fix4 handoff（kickoff §16.7）

- **来源清单：** 07 上的两份清单都先用旁注核对。05 清单的 07 副本 SHA256 等于 05 原件的现场值，npm 归档清单与两个依赖镜像身份文件的 07 副本也与 05 原件相同。07 清单在 07 上 `sha256sum -c` 通过，05 清单在 05 上 `sha256sum -c` 通过。
- **复跑：** 在 07 上用 Y 的 `check-handoff-hex.py`，与 `59c5b8cfca` 相同。输入为从 H 的 git 对象取出的 handoff，与实施会话的副本 `handoff-h.md` 逐字节相同。参数与实施会话日志的 `argv` 相同。
  - exit 0：`23 distinct full token(s); git=15 sha256=8 allowed=0 abnormal=0; 0 truncated form(s)`；
  - 与实施会话 `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-07/hex-handoff.log` 相比，开头 11 行中只有 `utc`、`argv`（脚本与 handoff 副本路径）和 `handoff` 不同，第 12 行起逐行相同；
  - 复跑日志 `/home/dev/gdds-fe-logs/fe4a-rereview4/hex-fix4/hex-rerun.log` SHA256 `08c3df47ed74e4276fd105f2e175fd229dfdb50be61871674df7b04379660d0b`。
- **配对：** handoff 中 64 位值共出现 9 次（8 个不同值，npm 归档两行），9 次都有对应的 `ok pairing` 行：07 文件现场配对，05 文件按清单配对。全部用表格分列或“`路径` SHA256 `值`”的写法，没有 `--allow`，没有手抄的标签项。
- **交付回复：** 只有提交号（X、Y、H 的 40 位值与 git 对象一致），没有 SHA256。
- **抽查：** 在所在节点现场重算，结果与 handoff 相同：
  - 05：wrapper 日志、case log、`results.json`、fe0 npm 归档；
  - 07：D1 两份日志、默认 npm 归档。

## 3. 逐项核对

### 3.1 helper 规则（§17.2、§16.2 第 2 项）

| 项 | 结论 | 说明 |
| --- | --- | --- |
| 依次断言禁用、可访问描述、原因可见 | 符合 | `ui.ts:133-134`，随后分支 |
| 有 `aria-describedby`：所指元素中文字等于原因的可见 | 符合 | 探针 `shared-removed`、`shared-hidden` 分别在描述与可见处失败 |
| 没有 `aria-describedby`：后面兄弟 `span.disabled-reason` 文字与可见 | 符合 | 探针 `toolbar-no-sibling` 在 `:155` 失败；`toolbar-no-title` 在描述处失败 |
| 两支不互相回退 | 符合 | 有 id 的分支以 `return` 结束；探针 `no-fallback` 在 `:151` 失败，而回退对照通过 |
| `expectReviewReasonShownOnce` | 符合 | 探针 `c12-per-button` 中只有它失败，原因断言仍通过 |
| 四处调用 | 符合 | §1 |

### 3.2 §11.2 第 10 项

在 `59c5b8cfca` 与 Y 上分别独立运行（开发主机，git 对象）：

```
git grep -n -e 'following-sibling' -e 'xpath=' -e 'disabled-reason' -e 'review-actions' -e 'aria-describedby' -e 'toHaveAccessibleDescription' -e 'getAttribute("title")' <提交> -- frontend/e2e-real
```

- **命中：** 比 handoff §4.1 的命令多两个关键词，命中多出的只有 Y 的 `ui.ts:134`（`toHaveAccessibleDescription`）。`59c5b8cfca` 的 4 处与 Y 的 9 处其余命中都与 handoff §4.1 相同。
- **定位器结论：** 与 handoff 相同。`journeys.spec.ts:233`、`t1.spec.ts:399` 只检查 `.review-actions` 容器可见；`ui.ts:125` 按角色与名称定位；其余命中都在两个 helper 内。

**`expectDisabledWithReason` 全部调用处的实际结构：** Y 中共 14 处，即 `journeys.spec.ts:590`、`595`、`746`、`750`、`815`、`861`、`866`、`870`、`871`、`959`、`960`、`1216`、`1549`、`1935`。逐个对照产品代码（Y）与探针的结构记录：

| 定位函数 | 调用处 | 产品代码 | `aria-describedby` | `title` | 原因元素 | 与 handoff §4.2 |
| --- | --- | --- | --- | --- | --- | --- |
| `workshopAction` | `:590`、`:746`、`:861` | `WorkbenchPage.tsx:529-532` 原生 `<button>` | 无 | `action.reason` | 后面的兄弟 `span.disabled-reason`，无 `id` | 一致 |
| `stepUploadAction` | `:595`、`:750`、`:866` | `UploadStepCard.tsx:333` 的 `Button`，`disabledReason` 含占用原因 | `button-…-disabled-reason` | 无 | 同一 `button-wrap` 内 `span.disabled-reason`，有 `id` | 一致 |
| `compareAction` | `:815`、`:870`、`:871` | `ComparisonPage.tsx:714`、`:717` 的 `Button`，`disabledReason={withdrawReason}`、`{submitReason}` | 同上 | 无 | 同上 | 一致 |
| `reviewAction` | `:959`、`:960`、`:1216`、`:1549`、`:1935` | `ReviewActions.tsx:167-171`；原因分别为 `STATUS_REASON.WITHDRAWN`、“该提交已归档”、“该提交已关闭（未归档）”，不是过期通过，所以“审核通过”也用共享原因 | → `.review-actions__reason` | 无 | 组下方一个 `span.review-actions__reason` | 一致 |

只有三种结构，没有第四种，与 §17.1 一致。不列阻塞 finding。

## 4. 需要修复（阻塞）

无。

## 5. 非阻塞

- **N23 handoff §5.2 中 X 的入口日志副本位置写错：** 原文说 X 的 D2 日志“`fe4a-fix4-d12e3b8f-05` 目录下 … `entry-journeys-x.log`”。该副本实际在 Y 的目录 `/home/dev/gdds-fe-logs/fe4a-fix4-26236839-05/`，X 的目录中只有原名入口日志。两者逐字节相同（§2.5），放在 Y 的目录也避免了写入要保留的 X 目录。不影响结论，证据 handoff 引用时写对位置即可。
- **N24 handoff §6 对 C12 第 1 条的落点不准确：** handoff 写“审核操作错误提示移出按钮行：`r11-review-conflict` 的版本冲突提示与刷新流程”。
  - **实际情况：** `r11-review-conflict` 的版本冲突发生在对话框打开时，提示渲染在对话框内（用例断言 `dialog.locator('[role="alert"].form-error')`）。C12 第 1 条改的是对话框关闭后的提示（`ReviewActions.tsx` 中 `dialog === null && error` 时移到 `.compare-header__notice`），只在过期通过与 `ARCHIVE_CLOSED` 时出现。journeys 的 20 个 scope 都不构造这两种情形；
  - **结论：** 这一处在真实 backend 上仍没有执行过，由模拟接口 V12 覆盖（断言提示在 `.compare-header__notice` 内、不在 `.review-actions` 内，本轮 07 全量通过）。kickoff §16.2 第 5 项只要求写明落点，没有要求补覆盖，所以不阻塞。证据 handoff 中写作“真实旅程未覆盖，由模拟接口 V12 覆盖”。
- **沿用：** 复审第 3 轮的 N19–N22（N20 的回源脚本修正随 FE4b）；N11 交 owner。

## 6. 交 owner 确认（汇总，不阻塞本轮）

- 同复审第 3 轮 §6：规则 4 的唯一豁免 `fe3b-w4-approved-withdraw`、C8 两种提示同屏的颜色、N11、N15。
- **看图：** 本轮 `full1` 与复审第 3 轮 `full1` 之间没有内容变化（§2.2）。owner 按 `59c5b8cfca` 看过的截图仍然有效，不重新看图。第 ③ 次稳定性比较以本轮 `/home/dev/gdds-fe-shots/fe4a-rereview4/full1`（`frontend/` 树 `d8e9a2e7`）为基准。

## 7. 下一步

1. **快进：** 开发主机 `/home/dev/gdds-fe` 的 `fe-vnext` 用 `git merge --ff-only` 从 `59c5b8cfca` 快进到 H（`16f4306306`）。
2. **证据（kickoff §16.5，在 H 上各运行一次）：**
   - 04：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`--suite journeys`（完整集 20 个 scope）；
   - 05：`--suite t1`，使用新的 `--log-dir` 与 `--evidence-dir`。
   - 目录按 §16.6 带 H 的 8 位短号 `16f43063`：
     - worktree `/home/dev/gdds-fe4a-evidence-16f43063`，ref `refs/fe4a-evidence/16f4306306`；
     - 日志 `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/` 与 `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/`；
     - 截图 `/home/dev/gdds-fe-evidence-04/fe4a-16f43063/` 与 `/home/dev/gdds-fe-evidence-05/fe4a-16f43063/`。
   - handoff 中的哈希按 §16.7。证据运行提示词由本会话交给实施会话。
3. **第 ③ 次稳定性比较（审核会话）：** 用 `--stable` 比较 04 证据截图与本轮 `/home/dev/gdds-fe-shots/fe4a-rereview4/full1`。两者的 `frontend/` 树必须都是 `d8e9a2e717e8d153b3a7794f25b76186c4bc4d5e`，按树号核对，不用 `tracked_frontend_archive_sha256`。
4. **证据核对（审核会话）：**
   - 核对四项证据日志；
   - 补上证据核对第 1 轮 §2 留下的两项：05-t1 按 FE3 kickoff §8.3 逐条核对，以及 M1 增量（与 FE3a 的 24.86 MiB 并列）；
   - 核对 J1、J2 的异常集合，以及 N24 的写法。

## 8. 本会话的遗留

- **07：**
  - worktree `/home/dev/gdds-fe4a-rereview4`（Y，clean）；
  - 7 个探针 worktree `/home/dev/gdds-fe4a-rr4-probe-{base,c12-per-button,shared-removed,shared-hidden,toolbar-no-sibling,toolbar-no-title,no-fallback}`，对应 ref `refs/review/fe4a-rr4/probe-*`；
  - 日志 `/home/dev/gdds-fe-logs/fe4a-rereview4/`；截图 `/home/dev/gdds-fe-shots/fe4a-rereview4/full1`；
  - bundle `/home/dev/gdds-bundles/fe4a-rr4-probes.bundle`。
- **开发主机：**
  - 同一 bundle `/home/dev/gdds-bundles/fe4a-rr4-probes.bundle` SHA256 `3e1afdfcbe53e6ec90d5646dfd9abda9ca51f99efcb2bbd3ba281a1c1fc4898b`（两侧相同）；
  - 已 fetch 到 `refs/review/fe4a-rr4/probe-*`；
  - 本报告提交在 `fe4a-review` 分支，随 FE4a 退出合入 main。
- **保留期限：** 以上保留到 FE4a 退出；第 ③ 次比较要用本轮 `full1`。
- **没有动过的内容：**
  - 实施会话的 worktree、ref、日志，X 的产物与 `59c5b8cfca` 的证据产物；
  - 前几轮审核会话的产物。
- **其他：** 07 上没有本会话留下的占用标记。本会话没有在开发主机上运行测试，没有推送，没有改 `fe-vnext`。

## 9. 本报告的回源

在 07 上用 Y 的回源脚本核对本报告的副本（`--repo /home/dev/gateway-data-management-system`），来源如下。

- **git 对象：** 07 上有 X、Y、H、`59c5b8cfca`、`16ffe72829`、探针提交，以及经 bundle 取得的 kickoff 合并提交与 `fe4a-review` 分支。
- **07 清单：** 现场重算的 `report-sources-07.sha256`，附旁注。覆盖：
  - 本会话日志目录的全部文件；
  - rr3 截图清单；
  - 比较脚本与 npm 归档；
  - 实施会话 07 目录中被引用的文件；
  - X 的 07 日志；
  - 探针 bundle。
- **05 清单：** 05 现场重算的 `report-sources-05.sha256`。传到 07 后先用旁注核对，再使用。
- **证据文件：** 工具链身份文件（`--evidence-file`），用于 config digest。

没有使用 `--allow`。结果与命令记录在 07 `/home/dev/gdds-fe-logs/fe4a-rereview4/report-hex/`；回源日志自身的哈希不写入本报告。
