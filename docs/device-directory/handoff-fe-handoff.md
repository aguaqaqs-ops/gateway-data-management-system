# Handoff：网关前端跳转入口（`fe-handoff`）

- **状态：** 待审核（实施会话 `fe-handoff`）。按 owner 2026-11-11 决定，本轮**不合入 main**、不打 tag、不通知目录任务；审核结论写 `/home/dev/gdds-stage-exchange/fe4b/handoffs/fe-handoff.md`。
- **基线：** `3e5f24583dee3d3c44705e4ef34557890557568b`（owner 指定，不从新 main 开始）。
- **分支：** `fe-handoff`（开发 worktree `/home/dev/gdds-fe-handoff`）。
- **提交：**
  - `764b3155a182c1a3f62fd9b413e8ae14cdf1f84d` — 全部实现与测试改动（本文件的证据即绑定此提交，前端 tree `a9fc7b84c8ab6219bfdc359e06aa4c4d4775fc12`）。
  - 之后仅新增本文件（doc-only，前端 tree 不变）。
- **任务权威：** `docs/device-directory/kickoff-fe-handoff.md`（`4e4badc87c`）+ FE4b 追加提示 `fe-handoff-sketches-addendum.md`；界面按 S5 草图提交 `1f6dc95917`（清单 SHA256 `05ca6615…7925224`）。
- **范围核对：** 只改 `frontend/` 与 `docs/frontend-vnext/frontend-kickoff.md` §4.3（补 Q1 例外一句）+ 本文件；未改 `vnext/`、`directory/`、OpenAPI 快照；未新增依赖（图标用已有 `lucide-react`）。未跑真实后端回归（owner 决定，由 FE4b 在合入后承担）。

## 1. 实现概要

| 文件 | 内容 |
| --- | --- |
| `frontend/src/features/session/handoff-session.ts`（新） | 会话状态机 `none/preset/handoff/invalid/expired`；首次渲染前 `initializeGatewaySession()`：片段（`gdds-handoff`）→ `window.__gatewaySession` → `sessionStorage`（`gdds-gateway-session`）→ 无会话；base64url 无填充 + UTF-8 解码；校验 `v===1`、四个非空字符串、`return_url` http(s)；`history.replaceState` 去片段（path+query 不变）；storage 异常仅内存；401 转 `expired` 并保留 `display`（内存）与 `returnUrl`。 |
| `frontend/src/features/session/SessionComponents.tsx`（新） | `DevicePath`（`MapPin`，分段：地区/地区/项目名/（站号），`title` 与 `aria-label` 为全文）、`ReturnToDirectoryLink`（`ListTree`）、`DeviceBar`（差异页设备栏）、`SessionGate`（品牌顶栏 + 居中卡片）。 |
| `frontend/src/main.tsx` | 首次渲染前调用 `initializeGatewaySession()`。 |
| `frontend/src/features/api/authenticated-fetch.ts` | 注释写明 Q1 试运行例外；401 `AUTHENTICATION_REQUIRED` 时使跳转会话过期。 |
| `frontend/src/features/dev/DevIdentityControl.tsx` | 不让开发身份覆盖跳转会话；没有可发布身份时不渲染。 |
| `frontend/src/features/dev/mock-data.ts` | 初始基线-only 的 workspace/history fixture。 |
| `frontend/src/features/view-model/workspace.ts` | `hasOnlyInitialBaseline(history)`：节点非空且全部为 `BASELINE_NODE` + `INITIAL`。 |
| `frontend/src/pages/WorkbenchPage.tsx` | handoff 时设备位置替换设备键、右端分隔线 + 返回目录；无会话/失效整页 `SessionGate`；“尚无数据”提示条。 |
| `frontend/src/pages/ComparisonPage.tsx` | `sr-only` 标题后新增设备栏（不动主行、处置说明与视图行）；blocked 时整页 `SessionGate`。 |
| `frontend/src/styles.css` | 按 S5 草图新增 `.device-context*`、`.device-path*`、`.return-directory`、`.topbar-divider`、`.workspace-brand--device`、`.device-bar`、`.session-gate*`、`.tree-empty-note`。 |
| `frontend/e2e/workspace-shell.spec.ts` | 8 个新用例 + 截图；原有用例未改语义。 |
| `frontend/src/features/session/handoff-session.test.ts`（新） | 解码/校验参数表、四级优先级、不回退旧会话、storage 不可用/损坏、401、dev 身份发布条件。 |
| `docs/frontend-vnext/frontend-kickoff.md` §4.3 | 补一句 sessionStorage 是 Q1 试运行例外。 |

## 2. 对 design/I6 与 S5 草图的取舍

1. **设备位置与返回目录。** kickoff §4.2 只写“标题栏显示”；按追加提示与 S5：工作台用设备位置**替换**原设备键、返回目录放右端并加竖分隔线；差异页在 `sr-only` 标题后**新增一行设备栏**，主行/处置说明行/视图行不动（避免 FE4b 冲突）。
2. **分段收缩。** 地区各 ≤12em 不收缩，站号 ≤16em 不截断，只收缩项目名。项目名下限写成 `min(8em, max-content)`：短名称不再与站号之间出现 8em 空白，长名称收缩时仍保住 8em 下限（受内容本身约束）。若 owner 要求严格 `min-width: 8em`（短名称也留空），回退一行 CSS 即可。
3. **无会话/无效页面。** 只有品牌名顶栏 + 居中卡片；没有 `return_url` 可用，所以不给返回链接（I6 的失效场景有 `return_url`，见下）。
4. **会话失效页面。** 主按钮“返回目录”、一行“设备：…”，并在**内存**中保留 `display`；`sessionStorage` 已清除。这实现了 Q-S5-4 的选项甲。
5. **尚无数据。** 提示条放在 `.workspace-table-scroll` 内、表格之后（`tree-empty-note` 内含 `info-note`）：标题“尚无数据”+ “该设备只有初始基线。选择组态目录并上传后，即可提交第一次组态。”。判定依据是 `hasOnlyInitialBaseline(history)`：历史节点全部为初始基线（`BASELINE_NODE` + `INITIAL`）且非空；真实 backend 只有初始基线时返回的历史即该形状（`design.md` §7 B7：网关后端支持在空初始基线上完成第一次提交）。上传入口不改，仍在右侧详情面板的“上传组态目录”。
6. **会话启动细节。** 片段不合法时同样去掉片段、不回退旧会话；测试注入的 `__gatewaySession` 优先于 storage 且不读写 storage；storage 写入失败仅内存可用；开发模式有跳转会话时不加载开发身份（见 §3）。

## 3. `DevIdentityControl` 的处理

- 选择“让位”：跳转会话、无效、失效三种状态下组件返回 `null`，不渲染身份选择；`window.__gatewaySession` 由开发端发布且跳转会话存在时不发布自己的身份；只有 handoff 会话不拥有身份时才显示。
- 生产构建仍不含该控件，`npm run check:production-build` 通过（见证据日志）。
- **与草图差异：** S5 草图顶部有“模拟身份/提交人”控件，本实现（开发构建、有跳转会话时）不显示。这是 kickoff 允许的两种处理之一；生产不受影响。

## 4. 验证

均在与 owner 约定的前端节点 `ct109-gw-dms-07`（`gw-dms-07.lan`）执行；worktree `/home/dev/gdds-fe-handoff-07`，clean、已提交，运行期间未写入。

| 项目 | 值 |
| --- | --- |
| 权威入口 | `frontend/scripts/run-tests.sh --e2e --screenshots <dir>`（`GATEWAY_FE_TEST_WORKERS=2`） |
| 提交 | `764b3155a1`（`head_start=head_end`，`git status` clean） |
| 结果 | 类型检查、lint、单测（36 文件 / 236 项）、构建、`check:production-build` 全部通过；e2e 104 passed，exit 0 |
| 日志 | `/home/dev/gdds-fe-logs/fe-handoff/frontend-tests-20261111T120852Z.log`，SHA256 `fea33f673463e8f6615595c930382d2bf81eef7a8c6f5654e72c1085ebcf4bbe` |
| 截图目录 | `/home/dev/gdds-fe-shots/fe-handoff-764b3155a1`（212 个 PNG，含既有回归截图） |
| 清单 | 目录内 `manifest.sha256`（按路径排序的逐文件 SHA256），其 SHA256 `e059408793516279b6aa227a7535ccce00a79fae1f2bf0740d644fe53b0ee5e2` |
| 工具链镜像 | `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，RootFS DiffID 7 项见日志（`…bec87777…` 等） |
| npm 缓存 | `/home/dev/gdds-fe-cache/frontend/npm-cache`（源归档 `npm-cacache.tar.gz`，SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，源提交 `3e5f24583d`，预填充于 2026-11-06 11:11:46 +0800） |
| 网络 | `docker_network=none`（离线 `npm ci`） |

本任务新增/更新的截图（1280 与 1920 各一）：`workbench-device`、`compare-preview-device`、`compare-review-device`、`no-session`、`session-expired`、`handoff-invalid`、`workbench-no-data`。

e2e 覆盖（与 kickoff §5 对应）：

1. 片段 → 清除片段（hash 为空、`from=directory` 保留）+ 设备位置/`title`/`aria-label`/返回链接 + sessionStorage 与全部请求使用跳转 token；
2. 工作台 → 差异浏览整页加载仍保留会话与设备栏；
3. 刷新后仍在；
4. 新标签页无会话：显示“未选择设备…”，零 `/v1/` 请求；
5. 401：失效提示、设备行、返回主按钮、storage 已清、≤2 次请求（不自动重试）；
6. 非法片段：无效提示、不回退旧会话、无返回链接；
7. 只有初始基线：“尚无数据”+ 上传入口可用；
8. 长设备名：只收缩项目名、站号不截断、页面不溢出。

## 5. 未决 / 待确认

1. **追加提示的权威性：** 本实现按 `fe-handoff-sketches-addendum.md` 与 S5 调整了 kickoff §4.2 的界面细节（设备栏位置、尚无数据位置、失效页设备行、无返回链接），请审核确认这是对 §4.2 的预期解释。
2. **短名称的项目名下限：** 见 §2.2；严格 8em 会让“示例项目（站-01）”出现约 4em 空隙。
3. **开发身份控件：** 有跳转会话时隐藏，截图因此与草图不同（§3）。
4. **真实后端未验证：** 按 owner 决定本轮不做真实 backend 回归；`e2e-real/lib/ui.ts` 的 `addInitScript` 注入路径未改动（preset 会话行为保持），合入后由 FE4b 真实回归覆盖。
5. **目录 start prompt 笔误：** `/home/dev/gdds-stage-exchange/fe4b/prompts/fe-handoff-start.md` 第 11 行写 `fe5b`，应为 `fe4b`（设计会话已登记待确认，不影响本任务）。
