# 实施 kickoff：网关前端跳转入口（`frontend/`，任务名 `fe-handoff`）

你是网关前端“设备目录跳转入口”的实施者。设备目录是独立系统，选中设备后把会话放在地址片段中，跳转到网关前端。你的任务是让网关前端接住这个会话、在页面加载之间保持它，并在标题栏显示所在设备。设计已由 owner 确认。

## 1. 先读

1. `AGENTS.md`，尤其是“前端测试（FD7）”一节：节点、工具链镜像、npm 缓存、日志与截图规则。
2. `docs/device-directory/design.md` §7（会话与跳转）、§11（Q1：试运行阶段允许把会话存在 `sessionStorage`）。
3. `docs/device-directory/interfaces.md` I6：跳转片段的格式与网关前端的处理步骤，是本任务的验收依据。
4. `docs/frontend-vnext/frontend-kickoff.md` §4.3（FD2：一个会话对应一个设备，切换设备即切换会话。该原则不变）。
5. 现有代码：
   - `frontend/src/features/api/session.ts`：`window.__gatewaySession`；
   - `frontend/src/features/api/authenticated-fetch.ts`：注释写明不在浏览器存储中保存凭据，Q1 是它的试运行例外；
   - `frontend/src/features/dev/DevIdentityControl.tsx`、`frontend/src/App.tsx`、`frontend/src/main.tsx`；
   - `frontend/src/pages/WorkbenchPage.tsx` 中的 `workspace-topbar`、`frontend/src/pages/ComparisonPage.tsx` 中的 `compare-header`；
   - `frontend/e2e-real/lib/ui.ts`：真实后端 e2e 通过 `addInitScript` 注入会话，不能被你的改动破坏。

## 2. 基线与边界

- 从 `main` 的最新提交（应包含 `18d290f20b`）创建短期分支 `fe-handoff`，在独立 worktree 中开发。不推送。
- 只改 `frontend/`，以及以下文档：
  - `docs/device-directory/` 下的 handoff；
  - `docs/frontend-vnext/frontend-kickoff.md` §4.3：补一句 Q1 例外，并链接到 design。
- 不改 `vnext/`、`directory/`。OpenAPI 快照不变，后端接口不变。

## 3. 关键事实

工作台与差异浏览页之间用 `window.location.assign` 整页跳转（见 `WorkbenchPage.tsx` 中对 `pageUrl("compare", …)` 的调用），每次跳转都会重新加载页面，内存中的会话会丢失。所以会话必须在**每次页面加载时**从 `sessionStorage` 恢复，这是本任务的核心。

## 4. 功能要求

### 4.1 会话启动

在首次渲染前完成会话启动，放在独立模块中，`main.tsx` 只负责调用。按以下优先级确定会话：

1. **地址片段中有 `gdds-handoff`：**按 I6 解码与校验。
   - 校验规则：`v === 1`；`token`、两个键、`display` 的四个字段都是非空字符串；`return_url` 是 http 或 https 地址。
   - 解码方式：base64url 无填充，再用 `TextDecoder` 按 UTF-8 解码。
   - 合法时：设置 `window.__gatewaySession`，保存 `display` 与 `return_url`，写入 `sessionStorage` 的 `gdds-gateway-session` 键，再用 `history.replaceState` 去掉片段，路径与查询串保持不变。
   - 不合法时：同样去掉片段，并显示“跳转信息无效，请从设备目录重新进入”。不要静默回退到旧会话。
2. **`window.__gatewaySession` 已被预先设置**（测试注入）：保持不变，不读也不写 `sessionStorage`。
3. **`sessionStorage` 中有 `gdds-gateway-session`：**校验后恢复。损坏的内容删除，按“无会话”处理。
4. **以上都没有：**无会话。

补充要求：

- `sessionStorage` 读写抛异常时（例如隐私模式），仅在本次加载中使用内存中的会话，页面照常工作。
- 开发模式下，已有跳转会话时，`DevIdentityControl` 不得覆盖它。可以选择不加载该控件，也可以让它让位；在 handoff 中说明你的选择。
- 生产构建中仍不得包含 `DevIdentityControl`，以 `check:production-build` 为准。

### 4.2 界面

- **设备位置：**有跳转会话时，工作台和差异浏览页的标题栏都显示“地区一 / 地区二 / 项目名（站号）”和“返回目录”链接，链接指向 `return_url`。测试注入的会话没有 `display` 时不显示，现有布局保持不变。样式沿用现有 token，在 1280 与 1920 两种宽度下都不能挤压现有元素。
- **无会话：**生产模式下显示“未选择设备，请从设备目录进入”，不再带空 token 请求接口。
- **会话失效：**有跳转会话时，接口返回 401 `AUTHENTICATION_REQUIRED`，就清除 `sessionStorage` 中的会话，显示“会话无效或已过期，请从设备目录重新进入”和返回链接。不要自动重试，不要循环跳转。
- **尚无数据（B7）：**设备只有初始基线时，提交树附近显示“尚无数据”，上传入口照常可用。
  - 先用 mock 数据确认当前工作台在“历史只有初始节点”时如何显示。mock 数据的形状以 OpenAPI 快照为准。
  - 后端返回的形状如果与你的判断不一致，或者需要后端配合，就停下报告。

### 4.3 凭据

- token 不出现在 console、日志、错误信息、截图或测试快照中。
- 片段清除后，地址栏和浏览历史中不再保留 token：用 `replaceState`，不用 `pushState`。
- 更新 `authenticated-fetch.ts` 的注释，说明 `sessionStorage` 是试运行例外（Q1）。

## 5. 测试与节点

- **单元测试：**
  - 片段解码与校验，用参数表覆盖各种非法输入；
  - 四级优先级；
  - `sessionStorage` 不可用；
  - 损坏的存储内容；
  - 401 处理；
  - 开发模式下不被模拟身份覆盖。
- **mock e2e：**
  1. 带片段打开 → 片段已清除、标题栏显示设备；
  2. 从工作台进入差异浏览页（整页加载）→ 会话仍在；
  3. 刷新 → 会话仍在；
  4. 新开空白标签页 → 无会话页面；
  5. 接口返回 401 → 失效提示；
  6. 历史只有初始节点 → “尚无数据”与上传入口。
- **回归：**`frontend/e2e-real` 现有用例不改，仍然通过。
- **节点：**类型检查、lint、单元测试、构建、截图、mock e2e 在 07 节点运行，`GATEWAY_FE_TEST_WORKERS=2`。连真实后端的 e2e 在 05 节点调试，按 DC70 补充取得整机占用标记。阶段退出时，在 04 节点的 clean、已提交 worktree 上用 `frontend/scripts/run-tests.sh --e2e --screenshots <worktree 外的绝对路径>` 完整运行一次，作为证据。不在开发主机上运行测试。
- 日志与截图按 `AGENTS.md` FD7 记录：hostname、起止时间、起止 HEAD、exit code、SHA256、工具链镜像身份、npm 缓存来源。本任务不新增 npm 依赖；需要新依赖时先停下。
- **截图：**每个状态截 1280 与 1920 两种宽度：工作台带设备位置、差异浏览页带设备位置、无会话、会话失效、跳转信息无效、尚无数据。

## 6. 交付

- 完成后写 `docs/device-directory/handoff-fe-handoff.md`，内容包括：
  - 提交列表；
  - 对 design 和 I6 的偏差及理由；
  - `DevIdentityControl` 的处理方式；
  - “尚无数据”的判定依据；
  - 测试日志与截图清单，记录节点、HEAD、exit code、SHA256；
  - 未解决问题。
- 写完后停下，等待审核。审核在只读的 detached worktree 中进行。
- 本任务合入 `main` 后，目录系统任务才进入阶段 2 端到端。端到端的真实旅程由目录任务负责；你只需保证 e2e-real 的回归通过。

## 7. 必须停下报告的情况

- 需要改 `vnext/`、`directory/`，需要改 OpenAPI 快照，或需要新增依赖；
- design 或 I6 有歧义，或与现有前端行为冲突；
- 后端在“只有初始基线”时的返回无法支持 B7；
- 缓存缺失，或工具链镜像身份不符（按 DC67、DC68 处理）。
