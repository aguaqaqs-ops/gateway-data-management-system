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

- 从 `3e5f24583dee3d3c44705e4ef34557890557568b`（`be-b-exit` 的目标，已包含 `18d290f20b`）创建短期分支 `fe-handoff`，在独立 worktree 中开发。不推送。（owner 2026-11-11 随 FE4 kickoff Q22 修改，原为“从 main 的最新提交”。）
  - 不从更新的 main 起步：本任务的提交将合入前端 FE4b 的集成线 `fe-vnext`，FE4 kickoff §6.5 要求 `git diff --name-only 3e5f24583d <你的提交>` 只含 `frontend/` 与 `docs/` 下的路径，`vnext/` 树为 `2faac9fc1d`；更新的 main 带有根目录 `AGENTS.md` 等改动，会使该检查失败。
  - 分支或 worktree 已经存在时，按其实际基线核对上面的条件，不重置、不改写已有提交；不满足时停下报告。
  - 背景：基线中的后端已是 BE-b，而现有前端尚未适配 BE-b 的导航与 bundle，由 FE4b 适配；本任务不处理这一点。
  - 前端角色安排按 owner 2026-11-11 的决定（FE4 kickoff §10 Q26）：前端不需要固定长程任务的角色分工，不参考后端角色分配规则。
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
- **回归：**`frontend/e2e-real` 现有用例不改。本任务不在真实 backend 上运行回归：基线中的后端已是 BE-b，现有前端未适配，在其上得到的结果不能说明本任务的行为。真实回归在本任务的提交合入 FE4b 的 `fe-vnext` 之后，由 FE4b 的 `journeys` 调试与证据承担（FE4 kickoff §6.5）；那只证明测试预置会话的路径，地址片段与 `sessionStorage` 的行为仍由本任务的单测与 mock e2e 负责。
- **节点：**类型检查、lint、单元测试、构建、截图、mock e2e 在 07 节点运行，`GATEWAY_FE_TEST_WORKERS=2`。本任务不跑真实后端 e2e。审核通过前，在 04 节点（或五节点池内其他合格节点）的 clean、已提交 worktree 上用 `frontend/scripts/run-tests.sh --e2e --screenshots <worktree 外的绝对路径>` 完整运行一次，作为证据；记录提交、截图目录与截图清单的 SHA256，FE4b 以它作为本任务截图的比较原件。所有运行按原子占用标记取得节点。不在开发主机上运行测试。
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
- 目录系统任务 `dir-v1` 阶段 2 的放行条件见下面的“集成与退出”。端到端的真实旅程由目录任务负责。

### 集成与退出（owner 2026-11-11，FE4 kickoff §10 Q22；取代原“审核与推进分工”中的合入、tag 与通知）

本任务与前端 FE4b 并行，FE4b 作为集成线。分三种情形（FE4 kickoff §6.5）：

- **审核通过后：** 审核会话把审核通过的提交号、审核结论，以及 04 截图证据（提交、目录、清单 SHA256）写入 `/home/dev/gdds-stage-exchange/fe4b/handoffs/fe-handoff.md`，并告知前端设计会话。**不合入 main，不打 tag，不通知目录任务。**
- **合入 FE4b（情形 1、2）：** FE4b 尽量在其第一次 `journeys` 调试之前，把该提交以 `--no-ff` 合入 `fe-vnext`，只此一次；冲突由 FE4b 的实施方解决。会话启动与凭据处理（§4.1、§4.3）若需修正，仍交回本任务的实施会话。
- **`fe-handoff-exit`：** owner 确认 FE4 退出时，由执行 FE4 退出的会话把 tag 打在被合入的审核通过提交上。附注写明：该提交只完成了本任务的组件审核（代码、单测、mock e2e 与截图）；真实回归发生在 FE4b 的最终候选，引用其提交与证据日志。本任务随 FE4b 的退出进入 main。tag 是否推送由 owner 另行决定（不在 FE4 退出的推送授权内）。试运行使用 FE4 退出后的 main，不从该 tag 单独部署。
- **目录放行：** FE4 退出（含本任务）后，由执行 FE4 退出的会话通知 `dir-v1` 进入阶段 2。
- **情形 3（FE4b 最终候选之前未能合入）：** FE4b 不等本任务。FE4 退出后，把当时的 main 合入 `fe-handoff` 分支，在真实 backend 上完成回归与审核，再合入 main、打 `fe-handoff-exit`，由本任务的审核会话通知目录任务。此时目录放行条件为：FE4 已退出，且本任务已验证并进入 main。
- 可以在节点上自行复跑模拟接口验收，作为独立验证；根据试运行反馈起草后续 kickoff。

修正的分工：

- 审核发现的问题写成修正清单，交回实施会话。实施会话修完后，由审核会话复审。
- 不影响行为的小问题（文档笔误、测试命名等），审核会话可以直接改，并在审核记录中逐项列明。
- 例外：会话启动与凭据处理（§4.1、§4.3）相关的修正一律交回实施会话，审核会话不直接改。

## 7. 必须停下报告的情况

- 需要改 `vnext/`、`directory/`，需要改 OpenAPI 快照，或需要新增依赖；
- design 或 I6 有歧义，或与现有前端行为冲突；
- 后端在“只有初始基线”时的返回无法支持 B7；
- 缓存缺失，或工具链镜像身份不符（按 DC67、DC68 处理）。
- 基线不是 `3e5f24583d`，或本任务的提交不满足 §2 所列的路径与 `vnext/` 条件；
- 本任务的改动与 FE4b 的改动冲突，需要改变 FE4b 的范围或 FE4 kickoff 已定的规则时，停下报告前端设计会话。
