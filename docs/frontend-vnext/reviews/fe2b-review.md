# FE2b 审核报告

- **审核对象：** 分支 `fe-vnext`。
  - 代码候选 `5ac704c6038fc3078cc70117b7e8d2c7443c22d1`，`frontend/` 树 `7ba49223ea`；
  - handoff 提交 `bf4942e0a8906d125e4447ca941b5044d4221257`（只改 `docs/frontend-vnext/fe2b-handoff.md`，`frontend/` 树相同）。
- **范围：** `fe-fe2a-exit..bf4942e0a8`，20 个提交，53 个文件。`vnext/` 树没有变化（仍为 `2791d3ff3d`）。
- **依据：**
  - [FE2 kickoff](../fe2-kickoff.md) §2（FE2b 一行）、§4、§6、§7；
  - [UI 优化方向](../ui-optimization-direction.md) F1–F9、T1–T3、C6；
  - 草图 S1、S2 的比较托盘部分、S3 的 Preview 与 History 顶栏；
  - AGENTS“前端测试（FD7）”。
- **日期：** 2026-11-03。
- **结论：定向修复。**
  - 证据可信：
    - 我在 05 上的独立运行通过；
    - fixture 在最终候选上逐字节复现；
    - handoff 中的日志与截图 SHA256 都能对上。
  - N2、R5、S2 达标；N1 只在比较托盘路径上达标。
  - 有 9 项需要修复（§4）：
    - R7 没有按完成标准做到；
    - 模拟 History 数据违反后端约束；
    - 生产构建检查漏掉了模拟数据模块；
    - 没有权限拒绝文案；
    - “查看差异”路径的 N1；
    - 工作区工具栏的含义；
    - 历史比较结果抽屉；
    - 组态树与草图 S1 不符；
    - 1280 截图有误。

## 1. 范围

| 内容 | 主要文件 |
| --- | --- |
| 页面与路由 | `App.tsx`（`page=workspace/compare`）、`pages/WorkbenchPage.tsx`（新增）、`pages/ComparisonPage.tsx`、`features/view-model/commands.ts`（URL 状态改为 `workspaceId`、`previewResultId`、`submissionId`、`operationId`） |
| 工作台视图模型 | `features/view-model/workspace.ts`（新增：组态树、上下文工具栏）、`features/workbench/OperationStatusPanel.tsx` |
| API 层 | `client.ts`（不再在内部生成幂等 key）、`journeys.ts`（`pollOperation` 改写，新增 `pollHistoryCompare`）、`idempotency.ts`、`connection-status.ts`、`session.ts`、`application-api.ts` |
| 模拟会话与数据 | `features/dev/DevIdentityControl.tsx`、`features/dev/mock-data.ts`、`features/dev/simulated-api.ts` |
| 带入项 | `formula-view.ts`（R7）、`presentation.ts`（标准记录与 ordered 记录二选一）、`check-production-build.mjs`（R2） |
| fixture | `scripts/generate-backend-bundle-fixtures.sh`（新增，Q14）、生成器新增 `preview-workbench-normal`（S1） |
| 测试 | 新增 `polling`、`idempotency`、`connection-status`、`workspace`、`mock-data` 单测；e2e 由 4 个增加到 11 个 |

`presentation.ts` 中“有比较键且有标准记录时只用标准记录，否则用 ordered 记录”的改动属于 FE2a 已有的浏览层。
六个 fixture 都由后端生产代码产出：其中 ordered 表的 surface 比较键都是 `[]`，有比较键的表都没有 ordered 记录。
所以在这些输入下，这条规则不会丢掉 ordered 记录中的移动。
后端是否会产出“既有比较键又有 ordered 记录”的表，我没有在源码中确认（surface 的比较键取自快照 manifest 的 `canonical_key_columns`，`storage_projection/project.py:417`），见 M11。

## 2. 证据核对

### 2.1 handoff 证据

在 05 上重算，结果与 handoff 一致：

| 证据 | SHA256 | 核对 |
| --- | --- | --- |
| 代码候选完整运行 `frontend-tests-20261103T144106Z.log` | `f04ec8f1…cc59` | 一致 |
| 外层 `full-runner-5ac704c6-05-wrapper.log` | `912f9711…a7da71` | 一致 |
| R2 负向探针 `frontend-tests-20261103T144315Z.log` | `a08974d3…c8d6` | 一致。HEAD `9afa58ba39` 只比候选多一行 `import "./features/dev/simulated-api"`；生产检查 exit 1，检出 `/simulated[-_ ]api/i` |
| fixture 生成 `backend-fixtures-3736d21854-…-822046.log` | `617bac05…6291917` | 一致 |
| 截图清单 `screenshot-sha256-5ac704c6-05.txt` | `1261b0dc…7cbca7d4` | 一致。这个文件在**开发主机**上，05 上没有；handoff 应写明所在节点 |

handoff 第 6 节的 50 张截图 SHA256，与 05 证据目录 `/home/dev/gdds-fe-evidence/fe2b/5ac704c6-05/` 及上面的清单逐项一致。

### 2.2 我在 05 上的独立运行

- **源码传输：**
  - 在开发主机上只读生成 `git bundle create … fe-vnext ^e301cc0f88`，SHA256 `3ac05359…fc88b6b`；
  - 05 上 `FETCH_HEAD` 为 `bf4942e0a8`，main（`7ac79ab53c`）没有移动。
- **worktree：** `/home/dev/gdds-fe-review-fe2b-bf4942e0-05`，detached、clean，已建 `legacy` 链接；没有占用标记。
- **缓存：** 使用 FE0 归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`（`0d861824…089f4`，来源提交 `a2fb4a027a`）。

日志在 05 的 `/home/dev/gdds-fe-logs/fe2b/review/`，节点 `gw-dms-test-05.lan`：

| 运行 | 起止（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 准备 `review-setup-05.log` | 14:57:47 | HEAD `bf4942e0a8`，`frontend/` 树 `7ba49223ea`，clean | `3fbfd7c4…b95817` |
| `run-tests.sh --screenshots` `frontend-tests-20261103T145820Z.log` | 14:58:20–14:58:53 | **exit 0**。typecheck、lint、build 通过；22 个文件 99 项单测通过；生产包检查通过；e2e 11 passed。HEAD 与树起止不变，运行后 clean | `d310bc33…2b02e8` |
| 外层 `runner-wrapper-05.log` | 同上 | `runner_exit=0` | `cd9c85ae…98eed` |
| fixture 生成 `fixture-logs/backend-fixtures-bf4942e0a8-20261103T150122Z-852228.log` | 15:01:22–15:01:49 | exit 0。依赖镜像 config `sha256:b5b54224…4b92a`；`uv.lock`、`.python-version` 与镜像一致；两次各 226 个文件，`byte_identical=true` | `296c8776…ac306a` |
| 外层 `fixture-wrapper-05.log` | 同上 | `gen_exit=0`，运行后 worktree clean | `f699283b…24ceee` |
| 与已提交 fixture 比较 `fixture-compare-committed.log` | 15:03:06 | 六个 fixture 与 `frontend/src/test/fixtures/source/backend/` 逐字节相同 | `2bf55d70…f0d415` |
| 截图清单 `screenshot-sha256-review-05.txt` | — | 50 张，见下 | `a6e88cc0…5e8caf` |
| 变异探针 `probes/mutation-probes.log` | 15:05:16–15:08:28 | 见 §5 | `dfe1aed0…57e1266` |

- **fixture：**
  - handoff 的生成日志对应 `3736d21854`，之后 `1970c355` 提交 fixture，生成器再无改动；
  - 我在最终候选上重新生成，结果与提交内容相同，所以 fixture 对应最终候选。
- **截图：**
  - 我拍的 50 张中，49 张与实施会话的截图逐字节相同；
  - 不同的一张是 `workspace-error-no-connected-1280`，我对照了图像，内容相同，只是像素级渲染差异。

## 3. 带入项与 §7.5

| 项 | 结论 | 说明 |
| --- | --- | --- |
| N1 | **部分达标** | 比较托盘路径达标：意图保存在状态和 `sessionStorage` 中，超时后“重试发起比较”复用同一 key；e2e 记录到 202 后 200，变异探针也检出。“查看差异”路径不符（B5）。单测 `idempotency.test.ts` 不测试产品代码（B5） |
| N2 | 达标 | `pollOperation` 与 `pollHistoryCompare`：状态请求超时视为仍在运行；网络错误、5xx、429 有上限退避，超过后为“连接中断”；四个终态；`MANUAL_RECOVERY_REQUIRED` 之后改为 30 秒轮询，两个恢复场景都有单测。e2e 覆盖“仍在运行”、连接中断、按 URL 刷新后继续 |
| `MANUAL_RECOVERY_REQUIRED` | 达标 | 显示“需要管理员处理”和可复制的操作 ID，不提供重试；“刷新状态”立即查询；e2e 跟随到 `RUNNING`、`SUCCEEDED` |
| R2 | **部分达标** | 请求携带所选身份的 token（e2e 断言三种身份）；URL 不再接受 `request` 等四个参数；负向探针有效。但禁止模式漏掉了模拟数据模块本身（B3） |
| R5 | 达标 | 状态取最近一次请求的结果，第一次请求前不显示；bundle 下载不计入；错误页隐藏“已连接”，有单测与 e2e |
| R7 | **未达标** | B1 |
| S1 | 达标，截图有误 | 生成器用生产代码产出 90 行遥测表，增、删、改各 6 处，没有导航或表诊断，并进入跨实现摘要测试。普通页签截图已拍，但 1280 有误（B9） |
| S2（甲） | 达标 | `s4-semantic-tokens` 已重拍，没有演示截图 |
| §7.5 生成类型、错误码、取值表 | 达标 | 全部模拟响应用 `satisfies` 约束；错误码单测解析 `openapi.json` 的描述；`journeys.test.ts` 中列出的错误值都已改正；workspaces 为 201/200，history-compares 为 202/200 |
| §7.5 取值以后端为准 | **未达标** | 生成类型约束不到后端的跨字段约束（B2） |

## 4. 需要修复

**B1. R7：一元减号前的上层运算符被丢掉**（`frontend/src/features/view-model/formula-view.ts:93`，`formula-view.test.ts:31`、`:33`、`:80`）

- **现象：**
  - 新分支只对 `-` 去掉了上层前缀：`node.operator === "-" ? "- " : prefix + operator`；
  - fixture 公式 `… | 6 | (−线路电流)` 因此显示为“| 6”接“- 线路保护装置 A:线路电流”，看起来像“6 减线路电流”，`|` 连接关系没有了；
  - 测试也改成断言这个结果。
- **完成标准：** §6.3 R7 要求“恢复第 1 轮的前缀断言”。第 1 轮（`ce0efc3c22`）的断言是 `"| - 线路保护装置 A:线路电流"`，复审第 2 轮 R7 也说明这才符合规则。
- **截图：**
  - 公式抽屉的内容区高度固定，最后一行被截断；
  - `formula-preview` 与 `formula-history` 的截图都看不到这一行，无法用截图验收 R7。
- **修复：**
  - 单子节点分支统一使用 `prefix + operator + " "`，恢复第 1 轮断言；
  - 加一条一元减号作为第一个子节点的用例（没有上层前缀时显示“- X”）；
  - 让公式内容区随抽屉高度伸展，或在截图前滚到底，重拍两组截图。

**B2. 模拟 History 数据违反后端约束**（`frontend/src/features/dev/mock-data.ts:98`、`:445`）

- **现象：**
  - `HISTORY_PAGE_ONE` 的基线节点 `fe2a-history-ref-1` 带有 `archive_disposition: "ARCHIVED_BASELINE"`；
  - `TEST_HISTORY_CURSOR_FIRST` 的基线节点没有 `baseline_kind`。
- **后端：** `application/history/contracts.py:108–113` 规定：
  - 基线节点必须有 `baseline_kind`；
  - 不能带 `review_status`、`archive_disposition`，`identity_exception` 也不能为 true。

  这两份数据后端不会产出，OpenAPI 中这些字段都是可选的，所以生成类型约束不到。
  §7.5 正是为了防止前端自造后端不会产出的取值。`historyStatus` 对基线节点判断 `archive_disposition`（`workspace.ts:29`），也是按这份错误数据写的。
- **修复：**
  - 改正这两份数据；
  - 在 `mock-data.test.ts` 中加一条单测，按 `contracts.py` 的节点规则核对全部模拟 History 节点：
    - 基线节点必须有 `baseline_kind`，没有提交专属字段；
    - 提交节点必须有 `review_status`，没有 `baseline_kind`；

  测试注明源码位置；
  - 删去 `historyStatus` 中针对基线节点的 `archive_disposition` 判断。

**B3. 生产构建检查没有覆盖模拟数据模块**（`frontend/scripts/check-production-build.mjs:6–13`）

- **现象：**
  - 禁止模式只能识别 `simulated-api.ts` 入口（错误消息文字与 `GatewaySimulatedApiModule`）和身份选择；
  - 单测直接 `import … from "../dev/mock-data"`，生产代码同样可以这样导入，检查识别不出。
- **探针：** 在 `App.tsx` 中直接导入 `./features/dev/mock-data` 并使用 `WORKSPACE_RESPONSE`。
  - runner exit 0，生产检查输出“production dist contains no simulated API or identity selection code”；
  - 主包由 764.79 kB 变为 768.18 kB，模拟数据确实进入了产物（§5 探针 1）。
- **要求：** §7.5 写的是“生产构建检查禁止该模块”，禁止的是模拟数据本身，不只是一个入口文件。
- **修复（任选其一）：**
  - 在 `mock-data.ts` 中放一个只在该模块出现的标记字符串，加入禁止模式；
  - 或者构建后检查 Rollup 的模块清单（如 `build.manifest` 或插件输出），断言没有 `src/features/dev/` 下的模块。

  然后用直接导入 `mock-data` 的探针重做负向检查。

**B4. 没有权限拒绝文案**（`WorkbenchPage.tsx:110–112`、`:200–203`、`:292`；`design-system/components.tsx:142`）

- **现象：** §6.2 要求后端返回权限拒绝时就地显示“当前身份没有该操作的权限”，并显示错误码（T3、C6）。代码里没有这句文案：
  - 加载工作区或 History 时，403 进入通用错误页，标题为“暂时无法显示结果”（截图 `workspace-error-no-connected`），而“重试”对权限拒绝没有用；
  - FE2b 唯一的写操作 `POST /v1/history-compares` 返回 403 时，托盘显示后端 `message` 原文加错误码。
- **测试缺口：** §7.2 要求 FE2b 的写操作旅程包含权限拒绝。现有 e2e 只覆盖加载时的 403，`POST /v1/history-compares` 的 403 场景只存在于模拟数据中，没有 e2e 使用。
- **修复：**
  - 按 `ApiError.code === "SCOPE_FORBIDDEN"`（或 status 403）统一映射为该文案，错误码放在悬停提示与可复制详情中；
  - 错误页在权限拒绝时用这句文案作标题；
  - 加一个 e2e：无权限身份发起历史比较，托盘就地显示该文案与 `SCOPE_FORBIDDEN`。

**B5. “查看差异”路径没有按意图复用 key；N1 单测不测试产品代码**（`WorkbenchPage.tsx:276–284`、`:190`；`idempotency.test.ts`）

- **现象：**
  - 非待审提交的“查看差异”会新建意图后直接 `sendHistoryCompare`，但没有 `setCompareIntent`，也没有存入 `sessionStorage`；
  - 第一次请求超时后，托盘只显示错误，没有“重试发起比较”；
  - 用户只能点“历史比较”，而那会用托盘中的节点（可能为空或是别的节点）和新 key 发起，违反 N1“同一意图的重试复用该 key”。
- **单测：** `idempotency.test.ts` 只是断言一个 `vi.fn()` 收到了测试自己传进去的 key，产品代码只调用了 `createIdempotentIntent`。删掉工作台中的复用逻辑，这个测试仍然通过。
- **超时：** `sendHistoryCompare` 的客户端超时写在应用代码里，开发构建为 700 ms，用来配合 e2e 的 900 ms 延迟。开发时连真实 backend（FE3）也会按 700 ms 判超时。
- **修复：**
  - “查看差异”与托盘共用同一个意图状态（含 `sessionStorage`），超时后显示同一个重试按钮；
  - 把“意图 → key → 重试”的状态逻辑提成可单测的函数（或 hook），单测断言：
    - 同一意图重试用同一 key；
    - 改变节点选择后用新 key；
    - “查看差异”的意图可以重试；
  - 超时时长作为参数注入，e2e 通过模拟会话或测试配置设置，不按 `import.meta.env.DEV` 写死。

**B6. 工作区工具栏的含义与 F2、S2 不符**（`features/view-model/workspace.ts:155–159`、`:172–174`；`WorkbenchPage.tsx:273–274`、`:370`）

- **草图与方向：**
  - F2 的工作区操作“原始组态备份 / 本次归档组态 / 上传”是上传的三个步骤；
  - S2 的取舍写明“S1 工具栏的三个上传按钮保留为快捷入口”；
  - 草图 S1（1280）中“上传”的禁用原因“需先选择本次归档组态目录”也说明，前两个按钮用来选择目录。
- **实现：** 把这两个按钮做成打开 Preview 的两个视图（`pair=baseline_to_initial`、`initial_to_modified`）。
  - 只上传本次归档组态（MODIFIED_ONLY）时，Preview 没有 `baseline_to_initial`，“原始组态备份”按钮仍可点；
  - FE2c 接入上传时，这两个按钮必须改成另一种含义，工具栏的单测与 e2e 都要重写。
- **启用条件：** §2 要求工具栏按 F2、F4 显示全部操作及其启用条件与禁用原因，写操作的点击在 FE2c 接入。现在“归档主线”在满足条件时仍禁用，原因是“归档主线操作在 FE2c 接入”；详情面板也写着“写操作会在 FE2c 接入。”。这些都是开发备注，不应显示给用户。
- **修复：**
  - 视图模型按业务状态给出启用条件，例如：
    - 工作区为 `OPEN` 时，可以选择两个目录；
    - 已审核通过且没有 `eligibility_note` 时，可以归档；
  - FE2b 中未接入的按钮可以无操作，e2e 不点；
  - Preview 入口保留在详情面板（“查看本次组态差异”），需要时再加“查看原始组态差异”，按是否有 `baseline_to_initial` 启用；
  - 去掉两处开发备注。

**B7. 历史比较结果抽屉**（`WorkbenchPage.tsx:337–357`）

- **比较对名称：** 抽屉中以 `<strong>` 显示原始 `pair_id`（截图中为 `fe2a-history-fixture-p1`）。§4.2 规定 History 比较对按顺序显示“节点 1 → 节点 2”，不依赖 `pair_id`；C6 规定原始值只放在悬停提示或 Debug 中。
- **下载状态：**
  - 状态一变为 `SUCCEEDED`，抽屉就显示“bundle 已下载并校验”和“打开差异工作台”，这时 `ensureLocalBundle` 可能还没完成；
  - 下载失败时，这句话和错误会同时显示。
- **状态文字：** `QUEUED` 与 `RUNNING` 都显示“仍在运行”，§4.5 规定为“排队中”“执行中”；“仍在运行”是 N2 中状态请求超时时的说法。`FAILED` 用的是 info 色。
- **托盘：** 比较运行中，托盘的节点仍可移除，“历史比较”按钮仍可点。F5 与草图 S2 的 `tray-running` 要求执行中节点锁定，按钮显示“比较中”。
- **修复：**
  - 比较对显示为“节点 i → 节点 i+1”（与托盘序号一致），`pair_id` 放进悬停提示；
  - 区分“下载中”“已就绪”“下载失败（可重试）”，就绪后再显示打开按钮；
  - 状态文字取 §4.5；
  - 运行中锁定托盘。

**B8. 组态树与草图 S1 不符，handoff 却写“无需升级 owner 决策的偏差”**（`workspace.ts:75–84`、`:127–128`；`WorkbenchPage.tsx:305`、`:323–330`、`:144–148`）

- **层级：**
  - 基线按 `parent` 链逐级嵌套（截图中“归档基线”缩进在“初始基线”之下），每归档一次就多一层缩进；
  - 草图 S1 中各基线是同一层，最新的在最上面，提交与工作区挂在所属基线下。
- **展开与折叠：** 草图中节点可以展开和折叠，实现中没有；“展开全部”按钮只是清空搜索框。
- **比较标记：** F5、F6 要求树上有“比较 N”标记，并与托盘、抽屉的序号一致（草图 `main-1920`、`compare-1920`）。实现中没有。
- **状态：** F7 要求状态用圆点加中文，实现中用的是灰色标签。
- **排序：** 列排序会把整棵树拍平重排，缩进保留下来，但父子关系看不出了。
- **修复：** 修正层级、比较标记与状态圆点；展开与折叠要么实现，要么去掉“展开全部”；排序在同一父节点内进行。实在不能按草图做的，按 AGENTS FD7 作为偏差逐条写进 handoff，交 owner 确认。B7 中抽屉缺少各比较对的表数与变更表摘要（草图 `compare-1920`），如果这一段不做，也列为偏差。

**B9. S1 的 1280 截图带着悬停提示**（`frontend/e2e/workspace-shell.spec.ts:681–686`）

- **现象：**
  - 1920 的悬停截图拍完后鼠标没有移开，接着拍的 `s3-workbench-normal-1280` 与 `s4-grid-normal-main-1280` 都带着悬停提示；
  - `s4-grid-normal-hover-1280` 与这两张逐字节相同（SHA256 都是 `722414b8…`）；
  - 1280 时 `hoverChangedTelemetryValue` 发现提示已经显示，就直接返回了，没有重新悬停。
- **修复：** 拍主表截图前把鼠标移到表格外，并等提示消失；1280 重新悬停到改动格后再拍。

## 5. 变异探针

05 上的一次性 worktree，以 `bf4942e0a8` 为基础改一处后本地提交（作者 `review-probe`），跑 runner，用后删除。
日志在 `/home/dev/gdds-fe-logs/fe2b/review/probes/`，脚本 `fe2b-review-probes.sh`（`d8ec28b0…f6592`）。

| 探针 | 改动 | 结果 | runner 日志 SHA256 |
| --- | --- | --- | --- |
| 1 直接导入模拟数据 | `App.tsx` 导入 `./features/dev/mock-data` 并使用 `WORKSPACE_RESPONSE` | **exit 0，未检出**（B3）。主包增大 3.4 kB | `38d4effd…57c31` |
| 2 `SUPERSEDED` 不再是终态 | `journeys.ts` 去掉 `SUPERSEDED` 判断 | exit 1，88/99 后测试死循环、内存耗尽。能检出，但不是断言失败（M7） | `a040d231…9f379a4` |
| 3 重试换新 key | `WorkbenchPage.tsx` 每次重试都新建意图 | exit 1，只有 N1 的 e2e 失败 | `039bc1fa…94f4297e` |

## 6. 次要问题（不阻塞，可随本轮一起修）

- **M1** `statusForNode`（`WorkbenchPage.tsx:53–57`）在工具栏与详情面板中用“基线已更新”“项目身份例外”取代状态。§4.1 规定这两个是附加标记，“不占状态位”。树上的标签写的是“身份例外”，§4.1 为“项目身份例外”。
- **M2** `historyStatus`（`workspace.ts:27–44`）与 §4.1 不一致：
  - 非 head 的初始基线状态写“初始基线”，与类型文字重复；
  - 非 head 的归档基线写“已归档”；
  - 规则迁移写“已迁移”。

  §4.1 中这几种都没有状态，只在是 head 时加“当前基线”。
- **M3** `OperationStatusPanel.tsx:207–211`：非临时错误（403、404）也显示为“连接中断”和“重试查询”。应按错误码显示。
- **M4** 工作台选中的节点没有写入 URL，返回工作台后选择丢失；`openPreview` 把工作台的节点键作为差异浏览页的 `node`（导航节点）传过去，两页的 `node` 参数含义不同。C3 要求状态可寻址。
- **M5** 审核模式顶栏 `审核：{status}`（`ComparisonPage.tsx:439`）在非 `PENDING` 时显示原始枚举。
- **M6** “已等待 N 秒”在刷新后从 0 重新计时。`OperationResponse` 有 `created_at` 与 `started_at`，操作卡片可以从这两个字段计算。History 比较的响应没有时间字段，可以维持现状。
- **M7** `polling.test.ts:75–76` 断言一个常量数组等于它自己，没有意义。终态用例的 mock 用的是 `mockResolvedValue`（无限次），终态判断出错时会死循环，最好改成有限次返回，让失败表现为断言失败。
- **M8** §7.5 要求“每个场景注明所依据的转移”，`MANUAL_RECOVERY_TO_SUCCESS`、`MANUAL_RECOVERY_TO_FAILED` 没有注明 `operations/state.py` 的转移。
- **M9** 顶栏任务指示没有任务时固定显示“工作区就绪”，“需要管理员处理”时也是。草图中只在有任务时显示。
- **M10** S1 fixture 的导航中多出一个“其他表”分组，里面是 0 → 0 行的 `composite_signal_point`。如果是生成器固定生成的表，在 handoff 中注明即可。
- **M11** `presentation.ts` 的二选一规则（§1）：在 handoff 中说明依据，或加一条单测，覆盖既有比较键又有 ordered 记录的表，断言移动记录不丢。

## 7. 截图核对（草图 S1、S2 托盘、S3 顶栏）

| 截图 | 对照 | 结论 |
| --- | --- | --- |
| `s1-workbench-1920/1280` | S1 `main-1920`、`narrow-1280` | 两行顶栏、连接状态、四列、搜索、“只显示当前基线”、详情面板 400px（1280 折叠）一致。偏差见 B6、B8、M1、M9 |
| `s2-compare-tray-1920/1280` | S2 `tray-selected` | 序号、单项移除、清空、主按钮层级一致。已满时的说明在工具栏的禁用原因中，没有在托盘内；托盘内说明要求见 F5 |
| `history-compare-running`、`history-compare-result-drawer` | S2 `tray-running`、S1 `compare-1920` | B7、B8 |
| `history-compare-connection-interrupted` | 无草图 | 顶栏“连接中断”、抽屉“重试查询”清楚，可交 owner |
| `manual-recovery-required` | 无草图 | 语义色、操作 ID 与复制、“刷新状态”符合 §4.5，可交 owner（M9） |
| `workspace-error-no-connected` | 无草图 | 没有“已连接”。标题文案见 B4 |
| `s3-header-upload`、`s3-header-history` | S3 `header-upload`、`header-history` | 模式标签、视图分段（“节点 1 → 节点 2”）、全部/仅看差异、User/Debug 一致 |
| `s3-workbench-normal`、`s4-grid-normal-main/hover/debug` | S3 `workbench-upload`、S4 `grid-main`、`grid-debug` | 1920 正常；1280 见 B9 |
| `formula-preview`、`formula-history` | 无草图 | B1 |
| `s4-semantic-tokens` | S4 `semantic-tokens` | 与 FE2a 相同，通过 |

## 8. 复审范围与要求

1. 修复 B1–B9。M1–M11 可以一起修，不修的在 handoff 中说明。
2. **探针：**
   - 对 B3 重做负向探针：直接导入 `mock-data`，检查应失败；
   - B1、B5 的新单测各做一次变异探针：
     - B1 去掉上层前缀；
     - B5 重试换新 key；
   - 结果写进 handoff。
3. **截图：**
   - 重拍：
     - 公式两组；
     - 工作台、托盘、抽屉各组；
     - S1 正常场景 1280；
     - 错误页；
   - 不能按草图修正的，作为偏差逐条列出，交 owner。
4. **运行：**
   - 在 05 上完整运行 runner（含 `--screenshots`）；
   - fixture 只要生成器与源 JSON 不变，就不必重新生成；改了就按 §7.1 重新生成两次并比较。
5. 复审范围为 `bf4942e0a8..<新 handoff 提交>`，通过后再做 04 取证。

## 9. 本轮在节点上留下的内容

- **开发主机：** 只读 review worktree `/home/dev/gdds-fe-review-fe2b-bf4942e0`；bundle `/home/dev/gdds-test-tmp/src-review-fe2b-bf4942e0.bundle`。
- **05：**
  - worktree `/home/dev/gdds-fe-review-fe2b-bf4942e0-05`；
  - bundle `/home/dev/gdds-test-tmp/src-review-fe2b-bf4942e0.bundle`；
  - 日志、fixture 输出与探针结果 `/home/dev/gdds-fe-logs/fe2b/review/`；
  - 截图 `/home/dev/gdds-fe-evidence/fe2b/review-bf4942e0-05/`。

  探针 worktree 已删除。

FE2b 退出合入后再清理。
