# FE4a 定向修复 handoff（fix1）

日期：2026-11-10
范围：`docs/frontend-vnext/reviews/fe4a-review.md` §4 的 F1–F9，以及 §5 的 N1–N4。第一轮 handoff `docs/frontend-vnext/fe4a-handoff.md` 保持原样；本文件末尾按 F9 对它作更正。

## 1. 候选与路径核对

工作区 `/home/dev/gdds-fe`，分支 `fe-vnext`。修复提交链：

| 提交 | 说明 |
| --- | --- |
| `7a6520620b` | 第一轮 handoff 提交（审核对象） |
| `6bcf62d4e2e2732c234ef51c3acf13068b206e70` | F1–F9 代码、用例、wrapper、hex 脚本 |
| `501fd7469cfb896902b50536ce551d8e7ab03b6c` | wrapper 只读入口输出、转发 `--screenshots` |
| `b10ae47fa3cd76109637dd209d41f684dde6f511` | V10 成功后改为点“关闭” |
| `8e2045a58bb098dd2dafdc1f0ebe771cba1b2ca4` | C6 折叠截图滚动到卡片后取图 |

handoff 提交：本文件所在提交（`git rev-parse HEAD`），只改本文件与回源脚本。
handoff 提交的 tree：frontend `e022d89b35`（仅脚本），vnext `49c1de43be`。

最终候选 `8e2045a58bb098dd2dafdc1f0ebe771cba1b2ca4`：

- `HEAD:frontend` = `5c4661078dac5b1d6826ef4407446b4b01e3a5b9`
- `HEAD:vnext` = `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`
- `<main>` 提交 = `16ffe72829`
- 候选 `vnext/` 树 = `49c1de43be`，与 `<main>` 一致，未改 `vnext/`
- 工作区提交后 clean；未 rebase、未改写既有提交、未合入 main、未推送

## 2. 修复项

### F1（C2）重试快速连点只读取一次

- `frontend/src/features/workbench/use-upload-mode.ts`：`retryResume` 保持“先等在途 promise，再进 `InflightGate`”的合并；本次没有改回退逻辑，新增用例把该行为固定下来。
- `frontend/e2e/workspace-shell.spec.ts:1980` 新增 `C2 重试快速连点两次只读取一次工作区与一次 attempt`。fixture 增加 `workspacePostHold`（`POST /v1/workspaces` 可挂起一次），流程：先制造“无法读取提交结果”提示 → 点“重试” → 等 workspace POST 挂起 → 再点“重试” → 释放 → 断言 workspace POST 与 attempt GET 各为 `before + 1`（等号，不是大于）。
- 探针自验：把该测试文件放到 `refs/review/fe4a/probe-c2`（去掉在途等待与 `InflightGate` 的探针）上运行，用例失败：`expect.poll` 的 workspace POST 期望 3、实得 4；日志 `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-probe-c2-20261110T125724Z.log`，整文件 SHA256 `e8dc0ade94ef065a5fa4fc4bfbe8aaff0015dc0a0d4629604723fb03c6b637ec`，exit 1。候选上同一用例通过（focused2、full2、full3）。

### F2（C6）理由折叠按实际溢出判定

- `frontend/src/features/workbench/disposition-display.tsx:20` 新增共享 `ReasonText`：`useLayoutEffect` 测量 `node.scrollHeight > node.clientHeight + 1`，`ResizeObserver` 跟随宽度变化；初始 clamp 3 行，只有实际溢出才显示“展开”，展开后显示“收起”，正文 `white-space: pre-wrap` 保留换行。不再使用换行数或字符数。
- `frontend/src/features/workbench/disposition-display.tsx:47` 的 `ClosureReason` 改为 `<ReasonText>{reason}</ReasonText>`；`ReviewDispositionLine` 的“查看关闭理由”details 保持不变。
- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:30` 引入共享组件；删除本地 `REASON_FOLD_THRESHOLD=120` 与本地 `ReasonText`；ACCEPTED/REVOKED 卡片（`:414`、`:417`）无条件使用 `<ReasonText as="p">`。
- `frontend/src/styles.css`：`.reason-text`、`.reason-text__body`、`.reason-text__body--clamped`（`display:-webkit-box`、`-webkit-line-clamp:3`、`overflow:hidden`），替换旧 `.archive-reason--clamped`。
- 用例：
  - `frontend/e2e/archive-validation.spec.ts:315` 长单行（原 C6）折叠截图、展开截图；`:320` 展开后断言全文与“收起”。
  - `frontend/e2e/archive-validation.spec.ts:323` 超过 3 行的多行理由：折叠、展开、再收起。
  - `frontend/e2e/archive-validation.spec.ts:346` 不超过 3 行：不出现“展开”。
  - `frontend/e2e/upload-mode.spec.ts:393` 工作台详情面板的关闭理由（4 行）：折叠、展开；`:404` 加 `fe4a-d3-manual-close-collapsed` 截图。
- 截图：`fe4a-c6-reason-collapsed` / `fe4a-c6-reason-expanded` 的 1280 与 1920 两套，用 `cardScreenshot` 滚到卡片后取图；`fe4a-d3-manual-close-collapsed` 1280/1920。

### F3（C8 / FE3c N5）提示生命周期

- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:160-172`：后续加载若集合未变化，`setCollectionNotice(null)`；若集合变化，设置通用提示。
- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:174-178`：`pendingNotice.current === null` 的普通加载仍清冲突提示；`:177` 之后清 `pendingNotice.current`。
- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:181-184`：加载失败时先清 `pendingNotice.current`，避免下一次成功加载保留过期的 409 提示。
- 用例：
  - `frontend/e2e/archive-validation.spec.ts:548` 集合变化提示出现后，做一次成功的接受（集合不变），断言集合变化提示与冲突提示都消失。
  - `frontend/e2e/archive-validation.spec.ts:589` 409 后把下一次预检改为 403，加载失败，再恢复并重新预检；断言冲突提示不残留。
  - 原 C8 两条（`:484`、`:507`）保留；第一条加 `fe4a-c8-both-notices` 截图。

### F4（C9）关闭成功后的底部按钮

- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:561-570`：`closeResult` 存在时 actions 只渲染一个 `<Button variant="primary">关闭</Button>`；不再渲染“取消”、禁用的危险按钮“已关闭”和重复的禁用原因。成功区正文仍显示关闭人、时间、理由（各一次）。
- `frontend/e2e-real/journeys.spec.ts:1862`：成功后点击由“取消”改为 `getByRole("button", { name: "关闭", exact: true })`。
- `frontend/e2e/archive-validation.spec.ts:680` V9：成功后断言唯一“关闭”可用，`取消`、`已关闭`、`确认关闭` 均为 0，正文不再重复“已关闭”；`:715-718` 为对应断言。`frontend/e2e/archive-validation.spec.ts:810` V10 同步改为点“关闭”。
- 本项触发一次 05 J1/J2 调试运行（见 §4）；`501fd..8e2045a` 只改 mock e2e 测试，未改 `e2e-real/` 或应用代码。

### F5 截图与交 owner 清单

- 新增截图：
  - `1280/fe4a-c8-both-notices.png`、`1920/fe4a-c8-both-notices.png`：红色集合变化提示与灰色冲突提示同时出现。
  - `fe4a-c6-reason-collapsed` / `fe4a-c6-reason-expanded` 的 1280/1920 归档卡片。
  - `fe4a-d3-manual-close-collapsed` 的 1280/1920 详情面板长关闭理由。
- FE3c 证据截图（04 `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/`，190 张）与新候选 full3（198 张）按相对路径逐字节比较：190 张共有、0 缺失、8 新增、43 张不同。完整分类与像素差见 §5；差异原因引用审核报告 §2.3 的分类（C3 分隔线、C4 固定等待/helper、C9、C5/D2、F2、运行噪声）。
- 交 owner 看图的文件：
  - C3 在 §2.3 范围的 4 张：`fe3b-w6-withdraw-busy`、`fe3b-w6-preview-resumed-card`（各 1280/1920）。
  - C3 波及其他 12 张（报告 §2.3 原文写 10 张，按所列六组×2 实为 12 张）：`fe3b-w10-stale-preview`、`fe3b-w4-approved-withdraw`、`fe3b-withdraw-forbidden`、`fe3b-withdraw-unknown`、`bundle-error`、`loading-skeleton`（各 1280/1920）。
  - C9 4 张：`fe3c-close-dialog`、`fe3c-close-result`（各 1280/1920）。
  - C5/D2 2 张：`fe3c-review-closed-1280/1920`（1280 宽度下图片宽 1340，横向溢出；未改代码，等设计会话决定）。
  - C8 灰色横幅：`1280/fe4a-c8-both-notices.png`、`1920/fe4a-c8-both-notices.png`（灰色 `.form-warning`，与 FE3c 红色 `.form-error` 不同）。
  - C6 4 张：`fe4a-c6-reason-collapsed` / `fe4a-c6-reason-expanded` 的 1280/1920。
  - D3 2 张：`fe4a-d3-manual-close-collapsed` 1280/1920。
  - C4 固定等待抽 2 张：`1280/fe3b-w6-resumed-card.png`、`1920/fe3b-w6-attempt-running.png`。
  - V12 2 张：`fe3c-review-closed-1280.png`、`fe3c-review-closed-1920.png`（实际在截图根目录，不在 `1280/` 子目录）。

### F6 删除 srgb

- `frontend/playwright.config.ts` 删除 `launchOptions: { args: ["--force-color-profile=srgb"] }`；full3 截图在不带该参数时生成，颜色与布局目视正常。

### F7 取证工具

wrapper（`frontend/scripts/run-evidence-wrapper.sh`）：

- 占用标记 `/home/dev/gdds-node-busy.d` 已存在时一律 exit 3，不运行入口；空目录、本会话残留、他人标记都不接管。real-backend 入口仍由入口自行取得，wrapper 只检查不存在。
- `--shots-dir` 对 `run-tests.sh` 自动追加 `--screenshots <dir>`；入口自带 `--screenshots` 时必须 realpath 相同，否则 exit 2。
- 日志目录 realpath 落在 worktree 内时 exit 2，不运行入口。
- `status_start` 非空时 exit 2，不运行入口。
- 结果字段只从入口输出段（`entry_output_begin` 之后、`entry_output_end` 之前）读取；缺失时写 `wrapper_field_missing <key> reason=...`，不写 MISSING。
- 结束时记录占用标记内容或 `busy_end=absent`，再释放本次自己取得的标记。
- 记录排序后的 `GATEWAY_*` 有效值；敏感名（TOKEN/SECRET/PASSWORD/PASSWD/CREDENTIAL/AUTH/COOKIE/KEY/URL）只记 `[redacted sha256=…]`。
- 仍写日志 `.sha256` 旁注，记录 hostname、起止 UTC、起止 HEAD、frontend/vnext 树、起止 status。

回源脚本（`frontend/scripts/check-handoff-hex.py`）：

- 新增 `--evidence-file`：把取回的日志/清单原文作为 64 位值的来源，并参与“名字 + SHA”位置配对。
- `--sha-file` / `--source-dir` 对同一行的多对“名字 + SHA”按位置配对（等量按顺序；数量不等时优先取该值之前最近的名称，再退化到最近名称），不再做全行笛卡尔比较；表格行参与。
- 64 位值没有 SHA 来源时输出 `unverified` 并 exit 1；短值没有 `--git-objects` 时同样 exit 1；`--allow` 只用于明确不是对象的标签。
- 可选对象类型核对：值附近出现独立的“树 / tree / 提交 / commit”时，用 `git cat-file -t` 核对 tree/commit，类型不符 exit 1；`worktree` 中的 `tree` 子串不算标签。
- 行为与 §3 的 P-H1–P-H6 正反复验一致。

### F8（OPFS 删除重试）

- `frontend/src/features/bundle/local-bundle.ts:78` `removeEntry` 导出；`:83` 只在 `DOMException.name === "NoModificationAllowedError"` 且 `attempt < 4` 时重试；其他 DOMException 立即抛出，`NotFoundError` 直接返回。
- `frontend/src/features/bundle/local-bundle.test.ts:16` 新增假 `FileSystemDirectoryHandle` 四例：两次短暂失败后成功（3 次调用）、持续失败在第 5 次后抛出（5 次）、其他 DOMException 立即抛出（1 次）、`NotFoundError` 直接返回（1 次）。

### F9 对原 handoff 的更正

见 §8；原 `docs/frontend-vnext/fe4a-handoff.md` 未改。

### N1–N4

- N1：`frontend/src/pages/ComparisonPage.tsx:423-435` `reloadReviewContext` 同时请求 `getReviewFacts` 与 `listHistory`，但只使用 facts，History 结果有意丢弃；基线变化由下一次锚点读取接管。V12 因此会重读 review facts 两次，属已知冗余，不在本阶段改。
- N2：`frontend/src/features/workbench/use-upload-mode.ts:333-339` 的 `submitted` 分支删除 `setResumeSeq(+1)`；`resumeNotice` 不再因“已提交”分支递增。
- N3：`frontend/src/features/view-model/archive-dialog.test.ts:101` `MODIFIED_BEFORE_INITIAL` 的 left 改为 `2026-11-05T12:00:00Z`、right 改为 `2026-11-06T12:00:00Z`，期望文案同步为“② 2026-11-05 12:00:00 UTC 早于 ① 2026-11-06 12:00:00 UTC”。
- N4：`frontend/src/features/view-model/diagnostics.test.ts:38` 删除码断言增加通用文案 `formatSurfaceDiagnostic(removed).message === "比较过程有提示"`。

## 3. F7 复验结果

所有探针在 07 `gw-dms-07.lan` 的 `/home/dev/gdds-fe4a-impl`（HEAD `501fd7469c`）上运行。

wrapper P-W/P-W2（日志 `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-wrapper-probes2-20261110T125914Z.log`，整文件 SHA256 `9fb4aef961de20951d6080b4af5ae73590bf6b4707ea8422fb60757bebba4530`）：

| 用例 | 操作 | 结果 |
| --- | --- | --- |
| w1 正 | 合法 run-tests，带 `--shots-dir` | exit 0；`entry_args=--screenshots …`；只读入口段 `hostname_end`；`GATEWAY_FE_TEST_WORKERS=2` 被记录；`GATEWAY_FE_SECRET_TOKEN` 为 `[redacted sha256=…]`；`busy_end` 有标记内容 |
| w1b 负 | 入口不写 `hostname_end` | `wrapper_field_missing hostname_end reason=entry did not log hostname_end`，不取 wrapper footer |
| w2 负 | 日志目录在 worktree 内 | exit 2，无日志、未运行 |
| w3 负 | `status_start` 非 clean | exit 2，`entry_ran=0` |
| w4 负 | 空占用标记目录 | exit 3，未运行 |
| w5 负 | 本会话残留标记 | exit 3，未运行 |
| w6 负 | real-backend 遇空标记 | exit 3，未运行 |
| w7 负 | 入口自带 `--screenshots` 与 `--shots-dir` 不同 | exit 2 |
| w8 负 | `--log-dir` 缺值 | exit 2，无日志 |

hex P-H1–P-H6（日志 `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-hex-probes-20261110T125944Z.log`，整文件 SHA256 `c560f53a774b2255ac7b3439f729cd7545c1423c208f0eae3751515dc7930b8a`）：

| 用例 | 结果 |
| --- | --- |
| P-H1 正/负：正确 64 位树/提交；改错一位 | 正 exit 0；负 exit 1 `unresolved` |
| P-H4 正/负：正确 10 位提交；改错一位 | 正 exit 0；负 exit 1 |
| P-H5 正/负：提交号标成“树”；正确树号 | 负 exit 1 `object type mismatch`；正 exit 0 |
| P-H3 正/负：无来源 64 位；加 `--evidence-file` | 负 exit 1 `unverified`；正 exit 0 |
| P-H2 正/负：两张截图 SHA 正确配对；互换 | 正 exit 0（`--source-dir` 与 `--sha-file` 两种）；负 exit 1 两条 `pairing mismatch` |
| P-H6 正/负：一行多对（正文与表格行）正确；互换 | 正 exit 0、4 条 pairing ok、无交叉误报；负 exit 1 两条 mismatch |

注：wrapper-probes2 与 hex-probes 日志末行是脚本追加的自记哈希（分别对应去掉末行后的内容），表中记录的是整文件当前 SHA256；自记行本身不参与本表取值。

## 4. 调试运行

| 运行 | 节点 / hostname | UTC 起止 | 起止 HEAD | exit | wrapper 日志 | wrapper SHA256 | 入口日志 | 入口 SHA256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| focused1（C2） | 07 / gw-dms-07.lan | 2026-11-10T12:55:45Z–12:55:53Z | `6bcf62d4e2` | 1 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-focused-20261110T125545Z.log` | `31736016efdc8f60f9cce35b9685bff4fb0c30949ba88770ffce547c6551fc47` | — | — |
| focused2（C2C6/C8/D3） | 07 / gw-dms-07.lan | 2026-11-10T12:56:03Z–12:56:23Z | `6bcf62d4e2` | 0 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-focused2-20261110T125603Z.log` | `7e12701f20d0cf9bcbf29d869cbb7e36a5e477213c7258dc1faad14a02724ed4` | — | — |
| probe-c2 自验 | 07 / gw-dms-07.lan | 2026-11-10T12:57:24Z–12:57:46Z | `bf792803a2`（探针临时提交） | 1 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-probe-c2-20261110T125724Z.log` | `e8dc0ade94ef065a5fa4fc4bfbe8aaff0015dc0a0d4629604723fb03c6b637ec` | — | — |
| wrapper probes | 07 / gw-dms-07.lan | 2026-11-10T12:59:00Z–12:59:00Z | `501fd7469c` | 0 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-wrapper-probes-20261110T125900Z.log` | `5894c7a977a614e405c848160b13c49646b909e0a82d5527e2ecc4d7201dfc72` | — | — |
| wrapper probes2 | 07 / gw-dms-07.lan | 2026-11-10T12:59:14Z–12:59:14Z | `501fd7469c` | 0 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-wrapper-probes2-20261110T125914Z.log` | `9fb4aef961de20951d6080b4af5ae73590bf6b4707ea8422fb60757bebba4530` | — | — |
| hex probes | 07 / gw-dms-07.lan | 2026-11-10T12:59:44Z–12:59:45Z | `501fd7469c` | 0 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-hex-probes-20261110T125944Z.log` | `c560f53a774b2255ac7b3439f729cd7545c1423c208f0eae3751515dc7930b8a` | — | — |
| V9 focused | 07 / gw-dms-07.lan | 2026-11-10T12:59:56Z–13:00:09Z | `501fd7469c` | 0 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-v9-20261110T125956Z.log` | `9d6701b8100ccbd9b9fa35be8d7d27a7c2a4b607e655cadbd81b24ddd3c398d0` | — | — |
| 全量 mock run1 | 07 / gw-dms-07.lan | 2026-11-10T13:00:18Z–13:03:14Z | `501fd7469c` | 1 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-run-tests-20261110T130018Z.log` | `692a26b0cf9da94d7f2aaa3436315234c6ef08b17f0ca55ace80815cc844958a` | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261110T130041Z.log` | `04a7f991cf0f0c3c4d792e401551c1aadfda62cff83f81dc6306862c2a9ccadc` |
| 全量 mock run2 | 07 / gw-dms-07.lan | 2026-11-10T13:04:18Z–13:07:00Z | `b10ae47fa3` | 0 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-run-tests-20261110T130418Z.log` | `b8bfa6b3bb48b70c75375cf439b584d4cf46efdc8fd6d82485a7e4610efc38be` | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261110T130441Z.log` | `f23348e0c2649c960525bc2ab70dced6af67fffb5a7ac868e8d6b3cd141c0f47` |
| 全量 mock run3（最终） | 07 / gw-dms-07.lan | 2026-11-10T13:12:45Z–13:15:03Z | `8e2045a58b` | 0 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-run-tests-20261110T131222Z.log` | `a55eada992c403fe4c5fb485d035c2ef8b0adfe279abe3268bad7747f72a3d48` | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261110T131245Z.log` | `61e795fa25be47ffd95826afa7789276eb5f2b60bc3c93eadbed51ace6432212` |
| J1/J2 真实 backend | 05 / gw-dms-05.lan | 2026-11-10T13:01:52Z–13:05:44Z | `501fd7469c` | 0 | `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-run-real-backend-e2e-20261110T130152Z.log` | `d552577595ff8344ee298657a65f646351d07e02e59db197ae2aaad5d10ae2b2` | `/home/dev/gdds-fe-logs/fe4a-impl/real-backend-e2e-journeys-fe4a-impl-501fd7469-20261110T130152Z-3259501.log` | `e4d76d58b22adb1e71e8552ff0f3278ba7d7c4fd03b9f5799571cee6470c2a7f` |

树核对：focused1/focused2 的 frontend 树 `b1e27cd52f`；probe-c2 的 frontend 树 `7ea7df7c9d`；wrapper probes、V9、全量 run1、J1/J2 的 frontend 树 `eee3d38b3a`；全量 run2 的 frontend 树 `8441d59984`；全量 run3 的 frontend 树 `5c4661078d`；以上所有运行的 vnext 树 `49c1de43be`。

补充：

- focused1 是 DC68 工具错误：直接 docker 运行前没有生成 `src/test/fixtures/generated/preview-full.tar`；worktree 未动，补 `node scripts/build-golden-bundle-fixture.mjs` 后 focused2 通过。
- 全量 run1 是产品用例修正：V10 在成功后仍点“取消”，改为“关闭”后 run2 通过；run1 的失败日志保留。
- full3 截图 198 张，清单 `/home/dev/fe4a-full3-shots.sha256`，整文件 SHA256 `e754465be932deeea8d5f7801cd94340812a1763ae2ba734bf95d860601bc8c2`；单测 35 文件/214 项，Playwright 95 项。
- 05 运行使用 npm 缓存 `/home/dev/gdds-fe-cache/fe0/npm-cache`，归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a`。
- 工具链镜像 `mcr.microsoft.com/playwright:v1.64.1-noble`（镜像名，不附摘要）。
- 工具链 config digest `a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；RootFS DiffID：
  - `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`
  - `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`
  - `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`
  - `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`
  - `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`
  - `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`
  - `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`
- 05 wrapper 日志 `/home/dev/gdds-fe-logs/fe4a-impl/fe4a-impl-run-real-backend-e2e-20261110T130152Z.log`，SHA256 `d552577595ff8344ee298657a65f646351d07e02e59db197ae2aaad5d10ae2b2`
- 05 入口日志 `/home/dev/gdds-fe-logs/fe4a-impl/real-backend-e2e-journeys-fe4a-impl-501fd7469-20261110T130152Z-3259501.log`，SHA256 `e4d76d58b22adb1e71e8552ff0f3278ba7d7c4fd03b9f5799571cee6470c2a7f`
- 05 journey-cases `/home/dev/gdds-fe-logs/fe4a-impl/evidence/journey-cases.log`，SHA256 `b9835b914f1dd31688c7bfbf3fef7625730c7fff20b0fae80291923fcb74fd26`
- 05 results `/home/dev/gdds-fe-logs/fe4a-impl/results.json`，SHA256 `9c7d12c8c31f22bdca496df52c8be5da863bb43f33acf5a5cf8cf08a664d28f7`
- 05 证据清单 `/home/dev/fe4a-fix1-05.sha256`（汇总上述路径与 SHA）。
- 07 证据清单 `/home/dev/fe4a-fix1-07.sha256` 汇总上表各日志与截图清单。

## 5. FE3c → 新候选截图逐字节差异

比较基准：04 的 FE3c 证据 `190` 张，新候选 full3 `198` 张；按相对路径比较 SHA256。43 张不同，分类如下（像素差为实测；原因为报告 §2.3 分类）。

| 组 | 文件（1280/1920） | 像素差 | 原因 |
| --- | --- | --- | --- |
| C3 | `1280/fe3b-w6-withdraw-busy`、`1920/…` | 5773 / 5757 | C3 顶栏分隔线；1280 同时含 C4 时钟 |
| C3 | `1280/fe3b-w6-preview-resumed-card`、`1920/…` | 5744 / 5744 | C3 顶栏分隔线 |
| C3 | `1280/fe3b-w10-stale-preview`、`1920/…` | 3892 / 3892 | C3 分隔线，不在 §2.3 范围，交 owner |
| C3 | `1280/fe3b-w4-approved-withdraw`、`1920/…` | 4693 / 4693 | 同上 |
| C3 | `1280/fe3b-withdraw-forbidden`、`1920/…` | 4381 / 4381 | 同上 |
| C3 | `1280/fe3b-withdraw-unknown`、`1920/…` | 4198 / 4198 | 同上 |
| C3 | `bundle-error-1280/1920` | 4258 / 4258 | 同上 |
| C3 | `loading-skeleton-1280/1920` | 4760 / 4760 | 同上 |
| C4 | `1280/fe3b-w6-attempt-running`、`1920/…` | 1058 / 1058 | 固定等待 8 秒文案（y154–165） |
| C4 | `1280/fe3b-w6-resumed-card`、`1920/…` | 1071 / 1071 | 固定等待文案（y154–165） |
| C4 | `upload-running-modified-only-1280/1920` | 734 / 734 | 固定等待文案（y926–937） |
| C4 | `history-compare-connection-interrupted-1280/1920` | 229 / 216 | 底部固定时长文案 |
| C4 helper | `1920/fe3b-withdraw-enabled` | 141458 | 截图 helper 的滚动/等待差异 |
| C4 helper | `1920/fe3c-many-first` | 1992 | 同上 |
| C9 | `1280/fe3c-close-dialog`、`1920/…` | 894 / 894 | 关闭对话框按钮层级 |
| C9 | `1280/fe3c-close-result`、`1920/…` | 5814 / 5814 | 成功后只保留“关闭” |
| C5/D2 | `fe3c-review-closed-1280` | 尺寸 1280×1134 → 1340×1241 | V12 1280 横向溢出；等设计会话 |
| C5/D2 | `fe3c-review-closed-1920` | 尺寸 1920×1134 → 1920×1224 | 同上 |
| F2 | `1280/fe3b-d3-manual-close`、`1920/…` | 1760 / 116243 | details 内理由改为 3 行 clamp + 展开 |
| F2 | `1280/fe3b-d3-review-topbar` | 2 | 同一 details 行高接缝 |
| 噪声 | `1280/fe3b-d1-review-topbar` | 2 | 运行间接缝/AA |
| 噪声 | `1280/fe3b-withdraw-none` | 2 | 同上 |
| 噪声 | `1280/fe3b-w5-conflict` | 10 | 同上 |
| 噪声 | `1920/fe3b-w6-recovery` | 4 | 同上 |
| 噪声 | `workspace-error-no-connected-1280` | 2 | 同上 |
| 噪声 | `s3-workbench-normal-1920` | 3 | 同上 |
| 噪声 | `s4-grid-normal-hover-1920` | 3 | 同上 |
| 噪声 | `s4-grid-normal-main-1920` | 3 | 同上 |

报告 §2.3 的 39 张中，`1280/fe3b-d2-review-topbar`、`1280/fe3b-w8-upload-disabled`、`archive-blocked-1280` 本次相同；本次新增 7 张（F2 3 张、`withdraw-none` 1 张、`s3` 1 张、`s4` 2 张）。这支持 F9：C4 残留是逐次抽样，不是封闭集合。

## 6. J1/J2 异常集合

05 J1/J2，`--suite journeys --subphase fe4a`，HEAD `501fd7469c`；J1 2026-11-10T13:03:10Z–13:04:24Z，J2 13:04:24Z–13:05:39Z；`2 passed (2.5m)`，suite exit 0，openapi compare match，cleanup ok。

J1：

| 步 | 结果 |
| --- | --- |
| 第 2 步 | 1 项：`GENERATION_TIME_MISSING`（MODIFIED） |
| 第 4 步 | `baseline_to_initial.changed=0`，`initial_to_modified.changed=5` |
| 第 7 步 | 3 项：BTU BASELINE、missing INITIAL、missing MODIFIED |
| 第 11 步 | 2 项 |
| 第 13 步 | 3 项（含 `PROJECT_IDENTITY_EXCEPTION`） |

J2：

| 步 | 结果 |
| --- | --- |
| 第 1 步 | 1 项 |
| 第 3 步 | 8 项 |
| 第 4 步 | statuses `201,200` |
| 第 5 步 | 7 项（含 `INITIAL_SOURCE_UNEXPLAINED`，全部 UNRESOLVED） |
| 第 8 步 | 2 项 |

异常集合与 FE3 kickoff §4.6 全部相符，用例内 `expectAnomalySets` 通过，无 §4.6 以外编码。J1/J2 的用例未改（只有 `e2e-real/journeys.spec.ts:1862` 的关闭按钮选择器改动）；`501fd..8e2045a` 未触碰 `e2e-real/` 或应用代码。

## 7. 回源结果

回源在 07 的 clean 候选 worktree `/home/dev/gdds-fe4a-impl`（最终 handoff 提交，见 §1）上运行，输入：

- `--handoff docs/frontend-vnext/fe4a-handoff-fix1.md`
- `--git-objects --repo /home/dev/gdds-fe4a-impl`
- `--sha-file /home/dev/fe4a-fix1-07.sha256 --sha-file /home/dev/fe4a-fix1-05.sha256 --sha-file /home/dev/fe4a-full3-shots.sha256`
- `--source-dir /home/dev/gdds-fe-shots/fe4a-impl-full3`（截图现场重算）
- `--allow 3259501 --allow fe3c-e22e39ba --allow a2fb4a027a --allow bf792803a2 --allow 7ea7df7c9d`（入口临时目录/测试数据标识，非 git 对象）

结果：`OK: 52 distinct full token(s), 0 truncated form(s)`；52 个不同完整值全部命中现场文件、日志/清单原文或 git 对象，0 个截断形式，0 个未核对值；所有“路径 + SHA”按位置配对一致。

本次回源同时修正了脚本：

- `same_path()` 允许记录路径与 handoff 路径只差绝对路径目录（如 `--sha-file` 中的绝对路径），配对不再因路径前缀不同而漏报。
- 一行内名称与 64 位值数量不等时，优先取该值之前最近的名称，避免表格中后一个路径离前一个值更近而被交叉配对。
- 对象类型标签识别排除 `worktree` 中的 `tree` 子串，只有独立的 `tree`/`commit` 或中文“树/提交”才要求类型。

修正后重新验证 P-H1–P-H6 全部正反向：P-H1/P-H4 正确时 exit 0、改错一位时 exit 1；P-H3 无来源 exit 1、加 `--evidence-file` 原文 exit 0；P-H2/P-H6 两对正确时 exit 0、互换后 exit 1 并报两条 `pairing mismatch`；P-H5 中文“树/提交”正确时 exit 0，把提交号标成“树”时 exit 1 并报 `object type mismatch`。

## 8. 对第一轮 handoff 的更正（F9）

原 `docs/frontend-vnext/fe4a-handoff.md` 不改，更正如下：

1. 运行 A–I 的实际 Playwright 并发是 `e2e_workers=playwright-default`；原 §6 把“设置了 `GATEWAY_FE_TEST_WORKERS=2`”写成了并发本身。fix1 的 full2/full3 日志明确为 `e2e_workers=2`、`--workers=2`。
2. `journey-cases.log` 保留在 05 的 `/home/dev/gdds-fe-logs/evidence/`；fix1 J1/J2 的副本在 `/home/dev/gdds-fe-logs/fe4a-impl/evidence/journey-cases.log`。
3. 原 §9 漏列三项调试后改动：`frontend/src/features/workbench/ArchiveMainlineDialog.tsx`、`frontend/src/styles.css`、`frontend/playwright.config.ts` 的 `--force-color-profile=srgb`。
4. t1 参考截图的实际路径与文件名：05 `/home/dev/gdds-fe-logs/evidence/t1-real-data-journey-with-M1-re-measurement-<名>-<宽度>.png`；Playwright 附件副本把 `_` 换成 `-` 并带 sha1 后缀。V12 截图实际是根目录 `fe3c-review-closed-1280.png` / `fe3c-review-closed-1920.png`，不是 `1280/fe3c-review-closed.png`。
5. C4 残留的 13 张只是一次抽样，不是封闭集合；本次 full3 与 FE3c 比较得到 43 张，噪声集合也不同。
6. 调试运行所在的 WIP 提交已压缩掉；引用审核会话保留的 `refs/review/fe4a/debug/*`，或自建 `refs/archive/fe4a/*`。
7. t1 在 05 的占用标记用途应记为 fe3a，不是本阶段的新用途。

## 9. 已完成 / 未测 / 未决

### 已完成

- F1–F4、F6、F8、N2–N4 的代码/用例；F5 的截图与 43 张差异表；F7 的 wrapper/hex 脚本与正反复验；F9 的更正。
- 07 focused（C2、C6/C8、D3、V9）、07 全量 mock run3、05 J1/J2。
- 探针：P-C2 在 probe-c2 上失败、在候选上通过；P-W/P-W2、P-H1–P-H6 正反均符合预期。
- 候选路径核对、树核对、提交与 handoff。

### 未测

- 未跑第二次 t1；未跑完整 20 scope journeys（证据运行留到复审通过后）；未跑上传包校验；未跑 t2–t4；未做计时。
- 未在 04 上跑最终证据集（按 kickoff §7.2 在复审通过后进行）。

### 未决

- D1（C4 容差判定）与 D2（V12 在 1280 下横向溢出）已交设计会话；在收到决定前不改代码。C4 按“固定时钟与固定文字已达成、逐字节相同未达成”记录。
- 是否接受 C3 波及的 12 张（报告原文写 10 张）、C5/D2 的 2 张、C8 灰色横幅、C6/D3 新折叠样式，交 owner 看图确认。
- N1 的 History 结果丢弃是已知冗余，按审核报告写入手册，不在本阶段改。
