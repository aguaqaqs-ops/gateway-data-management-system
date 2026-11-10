# FE4a 审核

- **审核对象：** 分支 `fe-vnext`，范围 `fe-fe3c-exit..7a6520620b`（前端部分只有 `16ffe72829..7a6520620b` 两个提交）。
  - 代码候选 `674c24fbb21f6ddbc6cfcade2d5112635d8280eb`，`frontend/` 树 `154a5a4af52192caf9b8d038e68285ce3185fca5`；
  - handoff 提交 `7a6520620bbd6bdabc946fe07641ef09ff18b3bb`：新增 `docs/frontend-vnext/fe4a-handoff.md`，并给 `frontend/scripts/check-handoff-hex.py` 加 `--allow`（+8 行），`frontend/` 树 `caf88e80ae7b9a5d93ad70ab451f758612d39117`。
- **依据：** [FE4 kickoff](../fe4-kickoff.md)（main `a4c4d60827`）§3–§8、§10；[FE3 kickoff](../fe3-kickoff.md) §4.6、§6.4、§8、§16；带入项原文：[FE3b 复审第 1 轮](fe3b-rereview-1.md) N2、[第 2 轮](fe3b-rereview-2.md)、[第 3 轮](fe3b-rereview-3.md) N2/N6、[FE3b 证据核对](fe3b-evidence-check-1.md) N7/N8、[FE3c 审核](fe3c-review.md) N2–N5、[FE3c 复审第 1 轮](fe3c-rereview-1.md) M1–M3、[FE3c 证据停止核对](fe3c-evidence-stop-1.md) N9；后端 Q21 答复（`git show main:docs/backend-vnext/refactoring/formal/plans/p6-fe3-q21-answer.md`）；`fe4a-handoff.md`。
- **审核会话：** FE4a 审核会话（新会话，会话名 `fe4a-review`），不是 FE4a 实施会话，也不沿用 FE3 审核会话的上下文。
- **日期：** 2026-11-10（时间均为 UTC）。
- **结论：定向修复。** 路径核对、Q21、令牌、入口的 J1/J2 选择、真实旅程与 t1 的调试日志都符合；handoff 中的十六进制值全部回源一致。以下问题需要修复后复审（§4 F1–F9）：
  - C2 的用例没有区分力：探针去掉在途合并后，W9④ 等 5 条用例全部通过（F1）；
  - C6 只改了归档对话框，FE3b 复审第 1 轮 N2 指出的 `ClosureReason` 没有改；折叠按字符数判断，不是 kickoff 要求的渲染行数（F2）；
  - C8 没有处理 FE3c 审核 N5 本身：`collectionNotice` 在同一对话框会话中仍不清除（F3）；
  - C9 成功后仍保留一个禁用的“已关闭”危险按钮和“取消”，与“只保留关闭对话框的按钮”不符（F4）；
  - kickoff §7.3 要交 owner 看的 C6、C8 状态没有截图；FE3c 到 FE4a 的截图差异没有逐项列出，其中 C3 分隔线另外改动了 10 张、C5 改动了 2 张不在 §7.3 清单内的截图（F5）；
  - `--force-color-profile=srgb` 对截图没有整体影响，删除（F6）；
  - 取证工具的若干缺口（F7）：wrapper 会自动接管同会话或空的占用标记，`--shots-dir` 与入口参数脱节；回源脚本不核对“文件名 + SHA”的配对，不给来源参数时也报 OK；
  - OPFS 删除重试保留，但收窄并补单测（F8）；
  - handoff 有几处与日志不符，最重要的是 A–I 全量实际用的是 Playwright 默认并发，不是 `GATEWAY_FE_TEST_WORKERS=2`（F9）。
- **交设计会话：** C4 的“逐字节相同”是否改为容差判定（D1）；V12 在 1280 下横向溢出（D2）。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| `git rev-parse 7a6520620b:vnext`、`674c24fbb2:vnext`、`16ffe72829:vnext` | 都是 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `git diff --name-only 16ffe72829 7a6520620b` | 25 个文件：`frontend/` 24 个、`docs/frontend-vnext/` 1 个，没有其他路径 |
| `fe-fe3c-exit` | tag `43e66d3eb7` → `06b454b0ef`；其 `frontend/` 树 `46e425f84e` 等于 `16ffe72829:frontend`，范围内的前端改动全部来自 `674c24fbb2`、`7a6520620b` |
| `16ffe72829..7a6520620b` | 两个提交，没有合入；`fe-vnext` 在 `7a6520620b`，未推送 |
| `package.json`、`package-lock.json`、`openapi.json`、`src/features/api/generated/` | 范围内无改动：npm 缓存与 OpenAPI 快照不变 |
| 打包流程筛查（kickoff §7.4 第 1 步）：`git diff --stat fe-fe3c-exit 7a6520620b -- frontend/src/features/workbench/upload-package.ts frontend/src/features/workbench/UploadStepCard.tsx` | 为空：不触发 t4 重测，不需要第 2 步 |
| 调试运行所在的 WIP 提交 | `07a55a1db6`（J1/J2、t1）、`2ee0e9f614`、`8af927f3f6`、`8164fe6d88`（A–G）与更早的 J1/J2 调试提交 `4aadcb86b8`、`19cc78711f`、`c3150b6f3f` 都不是候选的祖先，也没有任何 ref 指向（`674c24fbb2` 是压缩后的单一提交）。本会话已在开发主机建本地 ref `refs/review/fe4a/debug/<短号>` 保留它们，防止被 gc 回收（F9） |

### 1.1 调试运行之后的改动（`git diff 07a55a1db6 674c24fbb2`）

7 个文件：三个 e2e spec（等待、C11 闸门、截图 helper）、`playwright.config.ts`（srgb 参数）、`local-bundle.ts`（OPFS 重试）、`ArchiveMainlineDialog.tsx`、`styles.css`。handoff §9 只写了“测试等待、C11 闸门、截图 helper 与 OPFS 重试”，漏了后三项：

- `ArchiveMainlineDialog.tsx`：C6 短理由改回与 FE3c 相同的 JSX（`<p>已由 … 接受：{reason}</p>`），长理由改为 `ReasonText` 包住子节点。渲染文字不变，`reason` 为空时与 FE3c 一样不显示“—”；
- `styles.css`：`.compare-actions` 去掉 `align-items: flex-start; gap: 8px`，分隔线改为左右各 4px；
- `playwright.config.ts`：加 `--force-color-profile=srgb`（只在模拟接口配置中）。

对证据运行中 J1/J2 与 t1 的风险：真实旅程按角色和文字定位，渲染文字没变，按钮间距与真实配置无关，OPFS 重试只在删除抛出 `DOMException` 时多等最多 200 ms，风险低。`journeys.spec.ts`、`t1.spec.ts`、`run-real-backend-e2e.sh` 自 `07a55a1db6` 起没有改动。但 §4 的定向修复会改归档对话框与关闭流程，`journeys.spec.ts` 第 1862 行在关闭成功后点“取消”，F4 会连带修改它，所以修复后需要一次 J1/J2 调试运行（kickoff §7.2 允许按需），证据运行在新的最终候选上覆盖其余部分。

## 2. 独立运行、探针与核对

### 2.1 本会话的运行（07，`gw-dms-07.lan`）

工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`（入口按内置的 config digest `sha256:a0d7b2b49ffa…1a017` 与 7 个 RootFS DiffID 核对通过），npm 缓存 `/home/dev/gdds-fe-cache/frontend/npm-cache`（归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`），`GATEWAY_FE_TEST_WORKERS=2`。全量运行都经候选中已提交的 wrapper 启动，会话名 `fe4a-review`；运行前后节点上没有其他占用标记。

| 运行 | 提交 | 起止 | 结果 | 截图清单 SHA256 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- |
| R：模拟接口全量 `run-tests.sh --e2e --screenshots` | `7a6520620b`（`frontend/` `caf88e80ae`），起止 clean | 11:58:02–12:00:41 | exit 0：单测 35 个文件 210 项，Playwright 90 项，`e2e_workers=2`；190 张截图，`/home/dev/gdds-fe-shots/fe4a-review/full1` | `8b18782562cabbd4df4347fc7d35d6a145217f280e4becea0e5ed72de31ec453` | wrapper `a1c4138c394e0765f789fcd761715df80a7486c58c3264ce08d60bd279d16f2b`；入口 `ba554b179aaa611080ada45107725c2ec9a61be7287c1e96a4963bdd44b50796` |
| S：探针 P-SRGB（去掉 `--force-color-profile=srgb`），同上 | `a298db1dd3`（`frontend/` `9bfb754ef3`），起止 clean | 12:01:02–12:03:40 | exit 0：90 项通过；190 张截图，`…/fe4a-review/probe-srgb` | `e9656861a99bdfea5d5db4c246f46b77bdffa1ff60fde7e0e0b2be566025bc88` | wrapper `4421c5bd5e35691f61a5577ccba7d6cd69e48f3813f58c883cd69d30722cbe88`；入口 `a67d1e957c955ff0f36ffd29805e5c0efe8c26631def578e3e7d5c1551297cbf` |

### 2.2 探针（已提交的一次性 worktree，只在 07 上）

探针提交在 `refs/review/fe4a/probe-*`，经 git bundle 传到 07，各建 detached worktree `/home/dev/gdds-fe4a-review-probe-<名>`。用例探针由 `/home/dev/gdds-fe-logs/fe4a-review/run-probe.sh`（SHA256 `74edfa2bdcd878e2796c5e1eb304ba35af4e8be24866b923033a5cb9fb322628`）运行：取占用标记，在同一工具链镜像中离线 `npm ci`、`npm run test:unit`（生成 fixture），再运行指定用例。日志在 `/home/dev/gdds-fe-logs/fe4a-review/probes/`。

第一轮 C1、C2、C5 探针（12:08）因我的脚本漏了 fixture 生成步骤，用例在读取 `src/test/fixtures/generated/*.tar` 时失败，没有触及被测逻辑，也没有副作用；保留日志（`9dd25542…8c83`、`a8aae0dc…d9f7db`、`1c625256…3a1c`），补上 `npm run test:unit` 后各重做一次，并先用候选跑对照。

| 探针 | 提交 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| 对照：候选上的 C1、W9④、V11、V12、C8 | `7a6520620b` | 全部通过 | **6 项通过** | `8baaba47eaf512c3daa2497c6c1518b0acbdccb9bf9039f66094f44543e156ce` |
| P-C1：打开提交对话框时不清除续做提示 | `1d18ce4700` | C1 用例失败 | **符合**：在“提示框应消失”处失败（收到 1 个） | `bfcf2fa905c2e2608f927e74e69baa1f0df4477821d8e74c62f493add75d729a` |
| P-C2：`retryResume` 不等在途 `refresh()`、不经 `InflightGate`（恢复 C2 之前） | `9e6b2fea22` | attempt 读取次数的断言失败 | **不符合**：W9④、W9③、W9③b 与两条续做重试用例共 5 项全部通过（F1） | `e548a319f1ec61d126c150e57a618d12820d2712baaa789fe3f7a3c37b3426ae` |
| P-C5：审核动作结束后不调用 `reloadReviewContext` | `e509bbc6c8` | V11、V12 失败 | **符合**：两条都失败在 History GET 次数（4，应 > 4） | `92ac0e171b1290ed6426b3b61e412e9f1b7586eb294afb6519c1fee747ef69a4` |
| P-C8：恢复 C8 之前的单一提示变量 | `c9e7b188c6` | C8 两条失败 | **符合**：两条都失败在 `.form-warning` 冲突提示处 | `9d7972be3c6101a66189faceed6b4f976dd721e67ec928cbf3221fbe3dd80df8` |
| P-C8b（补充）：保留两处横幅，但普通加载不清除旧冲突提示 | `e28619b902` | 只有第二条失败，且失败在“旧冲突提示应消失” | **符合**：第 521 行失败，第一条通过 | `fe1b228600ac01b1a040cd0ebe8a99a4a1fcab6a419ea5c62af96f3a3f6166ff` |
| P-C11：“加载中显示骨架…”改回固定 1200 ms 延迟加不带参数的 `unrouteAll()`，`--workers=8 --repeat-each=20` | `22f9bef19a` | 观察，不强求复现 | **未复现**：20/20 通过；候选同配置对照 20/20 通过 | 探针 `65fbb0482d2432622fdf199681df7fc2c25a639fe8cf8c2e8251f80865fa2d10`；对照 `1ce17c0675d7bf15fd9658bb54076d2e1d3d54f2f5f08ca42002a39b8692a63b` |
| P-W：wrapper 的 `--log-dir` 取成 `$1` | `ea9e9033fe` | 在运行入口前退出 | **符合**：`wrapper_error=log-dir must be absolute (got --log-dir)`，exit 2；没有写日志、没有占用标记、没有启动容器 | — |
| P-W2（补充）：用候选的 wrapper，把日志目录放在 worktree 内 | `7a6520620b` | 应拒绝 | **不符合**：照常运行入口（`validate-upload-package.sh --help`，exit 0），`status_start` 已显示该日志为未跟踪文件（F7）。运行后删除该目录，worktree 恢复 clean | — |
| P-H1：handoff 副本中改错一个 64 位 SHA 的一位 | — | 报未命中 | **符合**：`unresolved sha256`，exit 1 | — |
| P-H2（补充）：互换 t1 workbench 1280/1920 两张截图的 SHA | — | 报配对错误 | **不符合**：`OK: 82 distinct full token(s)`（F7） | — |
| P-H3（补充）：不给 `--git-objects`、`--sha-file` | — | 不应报 OK | **不符合**：只打印 unverified，最后 `OK`，exit 0（F7） | — |
| P-H4（补充）：改错一个 10 位提交号的一位 | — | 报未命中 | **符合**：`unresolved git object: 674c24fbb3` | — |
| P-H5（补充）：把 `frontend/` 树号换成另一个存在的提交号 | — | 报类型或关系不符 | **不符合**：报 OK（只核对对象存在）（F7） | — |
| P-H6（补充）：在 07 上对正确的 handoff 用 `--source-dir /home/dev/gdds-fe-shots/fe4a-c4-h` | — | 正确的行不报错 | **不符合**：一行多对“路径 + SHA”时两两交叉比较，正确的 §7 两行产生交叉误报，全文共报 37 条问题；表格行（文件名没有 `/`）完全不参与配对（F7） | — |

### 2.3 截图比对

逐字节比较按文件名进行；像素比较用本会话的纯标准库 PNG 比较脚本（07 `/home/dev/gdds-fe-logs/fe4a-review/pngdiff.py`，SHA256 `ca31128ec178d430f7307df20d9c5c7d98c1bc2214edc0d8c8b08f4455bae403`），输出不同像素数、范围与最大通道差。FE3c 证据截图从 04 复制到 07 后按清单 `63a0e6006952152e7cd59db22ada9b34e4774f4f99676c22041b31f9ea1129f2` 逐个核对一致。

**同一前端内容的不同运行（C4 残留）：**

| 比较 | 逐字节不同 | 性质 |
| --- | --- | --- |
| H 与 I（实施会话，默认并发） | 13 张，与 handoff §5 一致 | 每张 1–73 像素，最大差 58 |
| H 与 R | 24 张，其中 16 张不在 handoff 的 13 张之内（例如 `s4-grid-main-1920`、`s3-workbench-upload-1920`、`1280/fe3b-w4-approved-withdraw`） | 每张 ≤ 21 像素，最大差 58 |
| R 与 S（只差 srgb 参数） | 17 张 | 每张 ≤ 56 像素，最大差 58 |

差异都是表格边框接缝像素（x=347/916、y=291/383 一带，差 58）、圆角处 1 级灰度和个别文字边缘，没有内容差异，与 handoff §5 的定位一致。但每对运行中出现差异的文件不同，13 张不是封闭集合。R 与 S 的差异与运行间噪声同量级，没有整体偏色：srgb 参数既不能使截图稳定，也没有改变截图，按 F6 删除。

**FE3c 证据截图与本会话 R（39 张不同）：**

| 原因 | 文件 | 是否在 kickoff §7.3 范围 |
| --- | --- | --- |
| C3 分隔线（撤回与提交两个禁用原因同时出现的顶栏，约 4200–5800 像素，限于顶栏） | `fe3b-w6-withdraw-busy`、`fe3b-w6-preview-resumed-card`（1280、1920） | 在 |
| 同上 | `fe3b-w10-stale-preview`、`fe3b-w4-approved-withdraw`、`fe3b-withdraw-forbidden`、`fe3b-withdraw-unknown`（1280、1920）、`bundle-error-1280/1920`、`loading-skeleton-1280/1920` | **不在**：同一 C3 改动波及的其他页面，需列入交 owner 看图的清单（F5） |
| C4 固定时长（“已等待 8 秒”等文字处，200–1100 像素） | `fe3b-w6-attempt-running`、`fe3b-w6-resumed-card`（1280、1920）、`upload-running-modified-only-1280/1920`、`history-compare-connection-interrupted-1280/1920` | 由 C4 引起 |
| C4 的截图 helper（视口等待、`animations: "disabled"`） | `1920/fe3b-withdraw-enabled`：FE3c 拍到了尚未随视口变宽的表格（即 handoff 所说的 1920 空网格竞态），FE4a 已正常；`1920/fe3c-many-first`：FE3c 拍到“完成”按钮颜色过渡中途（差 22） | 由 C4 引起 |
| C9 | `fe3c-close-dialog`、`fe3c-close-result`（1280、1920） | 在 |
| C5（V12 重读后显示处置） | `fe3c-review-closed-1280/1920`：尺寸变为 1340×1241 与 1920×1224 | **不在**；handoff §7 已列给 owner，但 1280 下横向溢出（D2） |
| 运行间噪声（≤ 21 像素） | `1280/fe3b-d1-review-topbar`、`1280/fe3b-d2-review-topbar`、`1280/fe3b-w5-conflict`、`1280/fe3b-w8-upload-disabled`、`1920/fe3b-w6-recovery`、`archive-blocked-1280`、`workspace-error-no-connected-1280` | 不是内容变化 |

**令牌（§3.6）：** `.form-warning` 的三处使用对应的截图 `submit-manual-recovery-1280/1920`、`manual-recovery-required-1280/1920`、`submit-result-1280/1920`、`1280/fe3b-w6-recovery` 与 FE3c 逐字节相同；`1920/fe3b-w6-recovery` 只有左上角 4 个像素差 1，不在提示框内。

### 2.4 真实旅程与 t1（核对 05 上的调试日志，不重跑）

| 运行 | 起止 | HEAD / 树 | 结果 | 日志 SHA256（05 现场重算） |
| --- | --- | --- | --- | --- |
| J1/J2：`--suite journeys --subphase fe4a --session fe4a-impl`，经 wrapper | 07:51:29–07:55:23（套件 07:52:49–07:55:18） | `07a55a1db6`；`frontend/` `7c059ec3f0`；`vnext/` `49c1de43be`；起止 clean | `playwright_grep=--grep=j1-archive-mainline\|j2-manual-close`，2 项通过，`suite_exit=0`，`openapi_compare=match` | 入口 `f792d0d42b17ed4e10bca7269b5afafe9c2fd89240f8a720b221b560238d75a5`；wrapper `c000f7e50a3998abafa0dd3644fed79bae67972ebcb986a31b126b97cc3e6621` |
| t1：`--suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs`，经 wrapper | 07:55:41–07:59:57 | 同上 | 1 项通过，`suite_exit=0`，`openapi_compare=match`，`worktree_clean_end=true` | 入口 `557bc3a1618022fc460dfe26c573c06fa4f2cee059a3625b2734eafd2f8562be`；wrapper `c97092a2fc2f7fa8d908fbe82c60bd9482d76b341e2d07477540f7d2f404ea93` |

- 05 上 FE4a 只有这一次 t1 运行；J1/J2 另有 `4aadcb86b8`、`19cc78711f`、`c3150b6f3f` 上的三次调试运行，属 kickoff §7.2 的“按需”。
- **J1、J2 的异常集合：** 通过轮的逐次集合在 05 的 `/home/dev/gdds-fe-logs/evidence/journey-cases.log`（SHA256 `6cdf69c072f99b7942d699ebddc275da614a2795ca42413e529f35b7fa68199c`，07:52:59–07:55:17 的行）。按提交 ID 对应 A–E 后逐项与 FE3 kickoff §4.6 比较，全部相符：J1 第 2 步 1 项；第 7 步 3 项（B ①②缺生成时间、BTU [B]）；第 11 步 2 项（C2）；第 13 步 3 项（含 D 的身份例外）；J2 第 1 步 1 项；第 3 步 8 项（缺生成时间 ×5：B①、B②、C②、E①、E②；BTU [B, C, E]；同级排除 ×2：C、E）；第 5 步 7 项（E 来源未解释、缺生成时间 ×4、BTU [B, E]、同级排除 E）；第 8 步 2 项。第 4 步 `statuses=201,200`。没有 §4.6 以外的编码。handoff §3 说 journey-cases.log 未保留，与事实不符（F9）。
- **C7：** J1 第 8、10、11、13 步与 J2 第 1、7、8 步都改为 `acceptAnomaliesViaUi`；第 8 步只接受“①原始组态备份”的卡；未接受完时“确认归档”保持禁用，归档会超时失败，所以“全部接受”有隐含的完成判据。J1 第 9 步与 J2 第 4 步的 BTU 仍用 API，不在 C7 列出的步骤内。J1 第 14 步改由 `reviewerSession` 执行。J1 74 秒、J2 75 秒（只报告）。
- **t1（§8.3）：** 两份清单 `cdb598cd…0163`、`fa2450fa…a96a` 各 19 个文件 `sha256sum -c` 通过；预期值从 `vnext/backend/benchmarks/real_dump_journey.py` 读取；v1 MODIFIED_ONLY `table_count = changed = 125`；v2 FULL 两个比较对按 `pair_id` 取用，`baseline_to_initial.table_count=125`，`composite_changed=0`。程序判定，`expectNoPageErrors` 通过。
- **M1：** `t1-m1 step=t1-v1-modified renderer_increment_bytes=20058112`（19.13 MiB），与 FE3a 的 24.86 MiB 并列，比值 0.77，未超 2 倍。测量窗口是 `measurePackaging` 包住的上传打包；`fe4-t1-workbench` 在窗口之前，`fe4-t1-preview-v1` 在 Preview 完成之后，切换宽度不在窗口内；第 207 行在第 1 步前已设 1920×1080，截图 helper 结束时也停在 1920×1080，窗口内的视口与 FE3c 相同。
- **参考截图：** 7 个页面名 × 2 种宽度共 14 张，在 05 的 `/home/dev/gdds-fe-logs/evidence/t1-real-data-journey-with-M1-re-measurement-<名>-<宽度>.png`（另有 Playwright 附件副本，文件名中 `_` 被换成 `-` 并带 sha1 后缀）；14 个 SHA256 与 handoff §4 表逐个相同。拍摄顺序（节点本地时间 15:56:58 → 15:59:49）与步骤顺序一致。handoff 的 sha 清单把它们记在不存在的 `/home/dev/gdds-fe-logs/artifacts/t1/` 下（F9）。

### 2.5 十六进制回源（本会话独立完成）

- handoff 中共 82 个不同的值：57 个 64 位、6 个 40 位、19 个 7–12 位；没有长度不是 7–12、40、64 的值。
- 57 个 64 位值全部命中本会话的现场重算或原始日志：07 上的 A–I 日志、run H 清单与 15 张 H 截图、npm 缓存归档、`raster/rt-1..6.png`（`4389c199…8255`）与 `twice/1280/fe3b-w6-preview-resumed-card*.png`（`612c593e…6bce1`）；05 上的 J1/J2 与 t1 入口日志和 wrapper 日志、两份 t1 清单、14 张 t1 截图、`gateway-backend-deps:lock-578e079b762e` 的 image ID（19 层）与输入摘要标签、RS 依赖镜像的 `uv-lock-sha256` 标签（同 `git show 16ffe72829:vnext/repository_service/uv.lock | sha256sum`）、t1 日志中的工具链身份与 OpenAPI 规范化摘要。
- 40 位与 7–12 位值都能解析为 git 对象；“提交 → `frontend/` 树”的 5 组配对（`2ee0e9f614`→`a4bbc16b90`、`8af927f3f6`→`bb76fd2a59`、`8164fe6d88`→`8cbba38878`、`674c24fbb2`→`154a5a4af5`、`07a55a1db6`→`7c059ec3f0`）逐个用 `git rev-parse <提交>:frontend` 核对一致；`578e079b762e`、`6dc9659f0aee` 是镜像 tag 后缀，已按镜像标签核对。
- 本报告中的 23 个完整 64 位值、8 个截断写法与全部提交号也按上述来源与 git 对象核对过一次。
- 值都对，路径与说明有误：§7 的 `1280/fe3c-review-closed.png`、`1920/fe3c-review-closed.png` 实际是根目录下的 `fe3c-review-closed-1280.png`、`-1920.png`；t1 截图的位置见 §2.4。实施会话用的 `/home/dev/fe4a-work/handoff-sha256.txt` 是手工汇编的清单，含 `toolchain-diffid-1`、`raster-test-static-page`、`same-launch-pair-screenshot` 等标签和不存在的路径。handoff §10 的“82 个全部命中”只说明 handoff 与这份清单一致，不是 kickoff §3.8 要求的回源（F7、F9）。

## 3. 逐项核对

### 3.1 带入项 C1–C11

| # | 结论 | 说明 |
| --- | --- | --- |
| C1 | 符合 | 两种做法都实现：提交对话框打开与上传开始时 `clearResumeNotice()`；工作区指针离开续做结果时 `resumeNotice` 为 null。新用例在打开对话框处断言提示框消失，P-C1 使其失败。上传开始一侧没有用例（只有页面接线一行），可接受。另见 N2 |
| C2 | **不符合**（F1） | `InflightGate` 与两个单测只证明这个类本身；`retryResume` 接入它的那一层没有任何用例能区分：P-C2 去掉等待与合并后，W9④ 新增的“attempt 读取次数增加”断言照常通过（该断言用 `toBeGreaterThan`，一次和两次读取都满足）。kickoff 要求“快速连点只产生一次读取序列（用例断言 attempt 读取次数）”。G3 的放宽已按数据集收窄，符合 |
| C3 | 符合 | 两个原因同时存在时渲染分隔线，W6 断言分隔线可见、两个 `aria-describedby` 不同；看图确认分隔有效。`Button` 合并调用方 `aria-describedby` 的改动对顶栏没有作用（调用方没有传），无害。分隔线同时改变了另外 10 张截图（§2.3），需要列给 owner |
| C4 | 部分符合（D1） | `page.clock.setFixedTime` 固定 `Date`、所有截图 `animations: "disabled"`、视口切换后等待画布尺寸一致。含时长的截图文字已固定（“已等待 8 秒”）。逐字节相同未达成，残留性质见 §2.3；H、I 都在默认并发下运行，本会话在 2 个 worker 下的两次运行（R、S）同样有残留 |
| C5 | 符合（N1） | 409 `BASELINE_VERSION_CONFLICT` 与 `ARCHIVE_CLOSED` 后同时重读 review 与 History；V12 的模拟数据带处置，断言按 §6.4 显示；P-C5 使 V11、V12 失败。History 的结果被丢弃，见 N1 |
| C6 | **不符合**（F2） | 归档卡片：摘要全文与 `issue_code`、`subject_digest` 放进 `title`，V1 有断言。理由折叠：① kickoff 写明含 FE3b 复审第 1 轮 N2，而 N2 说的是 `disposition-display.tsx` 的 `ClosureReason`（工作台详情面板的关闭理由）：它仍按换行数判断，折叠后全部隐藏、只剩“展开理由”，很长的单行理由不折叠，本次未改；② 归档对话框按理由长度超过 120 个字符判断，不是渲染行数：拉丁字符的 121 字理由可能只占两行却出现无效的“展开”，带前缀的 100 字中文理由可能超过 3 行却不折叠 |
| C7 | 符合 | 见 §2.4 |
| C8 | **部分符合**（F3） | 冲突提示与集合变化提示已分两处，每次成功加载清除待用提示；P-C8、P-C8b 证明两条新用例有区分力。但 FE3c 审核 N5 的原问题是 `collectionNotice` 在同一对话框会话中不清除，后续成功操作后仍显示旧提示：现在它仍只在打开对话框时清除，集合未变的后续加载不清除。加载失败时 `pendingNotice` 也不清除，下一次成功加载会保留旧冲突提示 |
| C9 | **部分符合**（F4） | 正文已改为“关闭提交 2（不归档）。”，V9 有断言。成功后底部是“取消”加一个禁用的危险按钮“已关闭”，按钮下另有禁用原因“已关闭”，加上正文的“已关闭。”同一状态出现三次；kickoff 要求“只保留关闭对话框的按钮” |
| C10 | 符合（N3） | 四条映射逐字对照 §16.3 一致 |
| C11 | 符合 | 11 处都改为 `{ behavior: "wait" }`；三个延迟改为闸门，`historyBundleDelayMs` 已无调用点并删除。P-C11 未复现原竞态（§2.2），如实记录 |

### 3.2 Q21（kickoff §3.5）

符合。`SURFACE_COPY` 与 `SURFACE_DIAGNOSTIC_CODES` 删除 `ROW_IDENTITY_UNSUPPORTED`、`ORDER_KEY_UNSUPPORTED`、`COMPARISON_MODE_NOT_DETAILED`、`BLANK_PROVENANCE_INVALID`，`git grep` 在 `frontend/` 中只剩单测里的删除断言；`ORDERED_PROVENANCE_*` 放在有序表组，文案“有序表缺少空行来源信息，或该信息无效”；`METADATA_*_REQUIRES_NATIVE_ROWS` 放在内部组，文案“比较时发生内部错误”；保留项不变。单测断言新增 4 个码的文案，已有用例覆盖“完整编码、冒号前缀、异常类名、通用文案”的匹配顺序。删除断言只查码表，不查文案表（N4）。

### 3.3 令牌（kickoff §3.6）

符合。`.form-warning` 的背景直接用 `var(--color-surface-muted)`，`--color-warning-soft` 在 `frontend/` 中已无引用；相关截图与 FE3c 逐字节相同（§2.3）。C8 新的冲突横幅也用 `.form-warning`（灰底），与 FE3c 用红色 `.form-error` 显示该文字不同，这一点随 F5 交 owner 看图。

### 3.4 取证工具与入口（kickoff §3.8、§7.2）

- **入口的 J1/J2 选择：** 符合。`--subphase fe4a` 只播种 `FE4A_SCOPE_SLUGS` 中的两个 scope，并加 `--grep=j1-archive-mainline|j2-manual-close`；`fe3b`、`fe3c` 分支不变，`PLAYWRIGHT_GREP` 为空时 `${2:+"$2"}` 不传参数，仍是完整集。调试日志记录了 `playwright_grep`。
- **wrapper：** 参数检查、`set -o pipefail` 风格的退出码、`.sha256` 旁注、按入口区分的标记处理、起止 HEAD 与 `git status` 都有，P-W 证明参数取错时不运行入口。缺口见 F7：自动接管本会话或空的标记；`--shots-dir` 与入口参数无关；不拒绝 worktree 内的日志目录和非 clean 的起点；`report_field hostname_end` 在入口没有输出该行时会读到 wrapper 自己写的同名行；结束时只记录标记目录的列表而不是内容；不记录 `GATEWAY_FE_TEST_WORKERS` 等影响运行的变量（F9 的并发误记正是这个缺口造成的）。
- **回源脚本：** 能发现改错一位的 SHA 与提交号（P-H1、P-H4）。缺口见 F7：不核对“文件名 + SHA”的配对（P-H2）；不给来源参数也报 OK（P-H3）；只核对对象存在，不核对类型与关系（P-H5）；`--source-dir` 在一行多对时误报、表格行不参与（P-H6）；不能直接以取回的日志与清单原文作为来源，只能靠手工汇编的 sha 清单。

## 4. 需要修复（阻塞）

- **F1（C2 用例区分力）：** 补一条用例，在续做提示的“重试”上快速连点两次（或在在途 `refresh()` 未结束时点“重试”），断言 workspace 读取与 attempt 读取各只增加一次（用等号，不用“大于”）。用 P-C2（`refs/review/fe4a/probe-c2`）复验：新用例必须失败。
- **F2（C6）：**
  - 把 `ClosureReason` 与归档对话框的 `ReasonText` 合成一个组件：先按 3 行 clamp 渲染，用实际溢出（例如 `scrollHeight > clientHeight`）决定是否显示“展开”；展开后显示全文，可收起；保留换行（`white-space: pre-wrap`）。不再用换行数或字符数判断；
  - 用例覆盖：很长的单行理由折叠；超过 3 行的多行理由折叠；不超过 3 行的理由不出现“展开”；工作台详情面板的关闭理由同样适用；
  - 交 owner 看图的截图（1280、1920）：归档卡片长理由折叠与展开、详情面板长关闭理由折叠。
- **F3（C8 / FE3c N5）：** 后续加载集合未变时清除 `collectionNotice`；加载失败时也清除 `pendingNotice`。补一条用例：集合变化提示出现后，再做一次成功的接受（集合不变），提示消失。
- **F4（C9）：** 关闭成功后底部只保留一个关闭对话框的按钮（标签“关闭”），不再显示禁用的危险按钮与重复的禁用原因。同步修改 V9 与 `journeys.spec.ts` 第 1862 行；改后跑一次 J1/J2 调试运行（kickoff §7.2 允许按需）。
- **F5（看图范围与截图清单）：**
  - 补 C8 冲突提示与集合变化提示同时出现的截图（1280、1920），以及 F2 的截图；
  - handoff 按 kickoff §7.3 列出 FE3c 证据截图到 FE4a 的全部逐字节差异与原因（可直接引用 §2.3 的分类），把 C3 波及的 10 张、C5 的 2 张、C8 横幅改用灰底一并列入交 owner 看图的清单。
- **F6：** 删除 `playwright.config.ts` 中的 `launchOptions: { args: ["--force-color-profile=srgb"] }`（§2.3：R 与 S 的差异与运行间噪声同量级）。
- **F7（取证工具）：**
  - wrapper：占用标记已存在时一律不运行入口：本会话的残留标记报告并退出，由操作者按收尾规则确认后手工删除，不自动接管；空目录同样退出（可能是他人刚 `mkdir` 尚未写入）。`run-tests.sh` 带截图时，由 wrapper 用 `--shots-dir` 生成入口的 `--screenshots` 参数，或校验入口参数中的截图目录与 `--shots-dir` 相同。拒绝位于 worktree 内的日志目录，`status_start` 不 clean 时不运行入口。结果字段只从入口输出的部分读取。结束时记录标记内容（或写明不存在）。记录 `GATEWAY_FE_TEST_WORKERS` 等 `GATEWAY_*` 变量的有效值（不含凭据）；
  - 回源脚本：表格行与同一行的多对“名字 + SHA”按位置配对，并与 `--sha-file` 或现场重算中的同名文件核对；有 64 位值却没有任何 SHA 来源、或有短值却没有 `--git-objects` 时，结果为“未核对”且非 0 退出；增加以取回的日志与清单原文作为来源的选项（值必须在原文中出现），代替手写标签；可选：对写明“树”“提交”的值核对对象类型。用 P-H1–P-H6 的副本复验；
  - 两个工具的正反验证写进 handoff，并在节点上运行一次。
- **F8（OPFS 删除重试）：** 保留：它修的是真实的产品路径（截断下载中止后删除目录失败，界面显示 `BUNDLE_LOAD_FAILED`，A、E 两次都是这个原因），不只是测试问题。但只对 `NoModificationAllowedError` 重试，其他 `DOMException` 照旧抛出；补单测（用假的 `FileSystemDirectoryHandle`，不需要浏览器）：短暂失败两次后成功、持续失败在最后一次后抛出、其他错误立即抛出、`NotFoundError` 直接返回。`local-bundle.ts` 不在 kickoff §7.4 的打包范围内，不触发 t4。
- **F9（handoff 更正，写在 fix1 handoff 中，不改原 handoff）：**
  - A–I 的 `e2e_workers` 都是 `playwright-default`，不是 `GATEWAY_FE_TEST_WORKERS=2`；修复后的模拟接口全量按 kickoff 用 2 个 worker；
  - journey-cases.log 在 05 的 `/home/dev/gdds-fe-logs/evidence/` 中保留着；
  - §9 漏列的三项改动（§1.1）；
  - t1 参考截图与 V12 截图的实际路径与文件名（§2.4、§2.5）；
  - C4 残留的 13 张是一次抽样，不是封闭集合；
  - 回源改用 F7 修正后的脚本，来源用现场重算与日志原文，不用手工汇编的清单；
  - 调试运行所在的 WIP 提交已压缩掉，handoff 写明本会话保留的 `refs/review/fe4a/debug/*`，或由实施会话改建 `refs/archive/fe4a/*`。

## 5. 非阻塞

- **N1** C5 的 `reloadReviewContext` 读取 History 后丢弃结果（审核模式顶栏不显示 History 派生的内容），字面上满足 §16.7 的“重新读取 review 与 History”；成功路径上 review 被读了两次（`ReviewActions` 一次、`reloadReviewContext` 一次）。可接受，fix1 handoff 写明即可。
- **N2** `retryResume` 结果为“已提交”的分支现在也递增 `resumeSeq`（C2 之前不递增）。页面随后整页跳转到审核模式，跳转前可能短暂闪现红色提示框。建议恢复为不递增。
- **N3** C10 的 `MODIFIED_BEFORE_INITIAL` 测试数据左值（11-06）晚于右值（11-05），是后端不会产生的形状（FE2 kickoff §7.5），建议换成左值早于右值。
- **N4** Q21 的删除断言只查码表；可另断言被删除的码按通用文案“比较过程有提示”显示。
- **N5** 1280 下预览页顶栏“提交”的禁用原因在右边被截断（`1280/fe3b-w4-approved-withdraw` 等），FE3c 已如此，不是本阶段引入，可随 FE4b 的顶栏调整处理。
- **N6** t1 运行的占用标记用途写成 `fe3a-real-backend-e2e-t1`（`--suite t1` 不接受子阶段名时默认 `fe3a`），只影响记录。

## 6. 交设计会话

- **D1（C4 是否接受“记录残留差异”代替逐字节相同）：** 本会话的两次运行是第三、第四个样本。残留的性质与 handoff 所述相同（每张 ≤ 73 像素，接缝像素差 58 或 1 级灰度，没有内容差异），但出现差异的文件每次不同（13、24、17 张），不能只记一份固定清单。建议接受容差判定代替逐字节相同：用提交在 `frontend/scripts/` 下的标准库 PNG 比较脚本，对同一提交的两次运行，每张截图不同像素不超过一个固定上限（例如 100）且不得出现成片的文字或区域差异；超出即视为不稳定。是否接受、上限取多少由设计会话与 owner 决定；决定前，FE4a 的 C4 按“固定时钟与固定文字已达成、逐字节相同未达成”记录。
- **D2（V12 在 1280 下横向溢出）：** `ARCHIVE_CLOSED` 后重读出处置，顶栏同时有错误提示框和三个按钮各自的“该提交已关闭（未归档）”，页面宽 1340 px（`fe3c-review-closed-1280`）。布局问题在 FE3c 就存在，只是 C5 之前模拟数据走不到这个状态；真实 backend 上同一操作也会出现。是在 FE4a 中处理（例如同一原因只显示一次，或允许操作区换行），还是作为偏差交 owner 看图后带入 FE4b，由设计会话决定。

## 7. 代码质量

改动集中、范围清楚，不需要重写。`use-upload-mode.ts` 的 `retryResume` 把等待在途读取和合并放在同一个回调里，逻辑可读；`resumeNotice` 在 `useMemo` 中读取 ref，依赖项里没有它们，目前因为 ref 总在同一次 state 更新前写入而正确，F1 的用例补上后可以保持。

## 8. 下一步

1. 实施会话按 §4 F1–F9 修复，提交 fix1 handoff `docs/frontend-vnext/fe4a-handoff-fix1.md`，然后由本会话复审第 1 轮。复审时重跑 P-C2（F1）、P-H1–P-H6 与 P-W/P-W2（F7），并做一次模拟接口全量与截图比对。
2. 修复期间的运行：focused 单测与模拟接口用例；模拟接口全量 `run-tests.sh --e2e --screenshots` 一次（`GATEWAY_FE_TEST_WORKERS=2`）；F4 改了 `journeys.spec.ts`，在 05 跑一次 `--suite journeys --subphase fe4a`。`t1.spec.ts` 不改，不跑第二次 t1 调试。
3. 复审通过后的证据项（kickoff §7.2 FE4a 证据行，届时在复审报告中确认）：在最终候选的 clean、已提交 detached worktree 上，经修正后的 wrapper 各运行一次：
   - 04：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys --subphase fe3c`（完整集 20 个 scope）；
   - 05：`run-real-backend-e2e.sh --suite t1 --input-root /home/dev/gateway-real-dumps/source-dirs`，用新的 `--evidence-dir`，不覆盖调试运行留下的截图与 case log。FE4a 的 t1 参考截图以这次运行在最终候选上拍得的为准，`07a55a1db6` 上的调试截图（preview 页仍是 8px 间隙）作废。
4. 取证后由本会话核对证据日志，给出 FE4a 退出建议（tag `fe-fe4a-exit` 指向证据 handoff；先把审核报告合入本地 main，再以 `--no-ff` 合入 tag；退出时推送该 tag，kickoff §6.4）。
5. **带入 FE4b 的项（目前）：** N5（1280 顶栏禁用原因截断）；D2 若决定不在 FE4a 处理；D1 若采用容差判定，FE4b 的截图核对沿用同一脚本与上限。

## 9. 本会话的遗留

- 开发主机：`refs/review/fe4a/candidate`、`refs/review/fe4a/probe-*`（9 个）、`refs/review/fe4a/debug/*`（8 个）；开发主机上的临时探针 worktree 已删除；本报告在短分支 `fe4a-review`（从 main `4399984fd2` 拉出），FE4a 退出时随 §6.4 合入 main。
- 07：`refs/review/fe4a/*`、worktree `/home/dev/gdds-fe4a-review` 与 `/home/dev/gdds-fe4a-review-probe-{c1,c2,c5,c8,c8b,c11,wrapper,srgb}`、bundle `/home/dev/gdds-bundles/fe4a-review*.bundle`、日志 `/home/dev/gdds-fe-logs/fe4a-review/`、截图 `/home/dev/gdds-fe-shots/fe4a-review/`（含 FE3c 证据截图的副本）。保留到复审结束；复审需要的 P-C2 与 P-SRGB 对照在其中。
- 本会话没有在开发主机上运行测试，没有推送，没有改 `fe-vnext`。
