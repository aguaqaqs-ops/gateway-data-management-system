# FE2b handoff — 工作台、路由与历史比较

**状态：FE2b 实现与 04 阶段退出取证完成，等待审核会话核对证据。** 本文替代此前的停止报告。未创建 `fe-fe2b-exit` tag，未推送。

## 候选与审核范围

- 分支：`fe-vnext`；上一阶段 tag `fe-fe2a-exit`，提交 `e301cc0f88427b390bbeef009e2b2f7058bddc0a`。
- 原 FE2b 审核候选：`5ac704c6038fc3078cc70117b7e8d2c7443c22d1`；审核报告来自 main 本地提交 `9868069a66e38b9b47743ecce17167f6a9d0601e`，文件 `/home/dev/gateway-data-management-system/docs/frontend-vnext/reviews/fe2b-review.md`。
- 定向修复源码候选：`5d1749675621a020a052690b95d55111af5509f9`，frontend tree `a0f8ce750b053d83907435f9c0ba1357603c5472`。
- 修复提交：`548cd290a2`、`aed2ccfac0`、`b49f584ab7`、`de0ef51337`、`9dde8f0101`、`5d17496756`。均在 `fe-vnext` 后续提交，未推送、未改写已有提交。
- 源码审核范围：`fe-fe2a-exit..5d1749675621a020a052690b95d55111af5509f9`。复审范围：`bf4942e0a8..<本 handoff 文档提交>`；本文件作为单独文档提交，不改 frontend 树。
- 状态：B1–B9 已定向修复；05 调试与 04 权威退出取证均已完成，当前等待审核会话核对 04 证据。未创建 `fe-fe2b-exit` tag，未推送。
- 05 全量运行日志：`/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T154941Z.log`，SHA256 `01951df3f663ba8476533ccf9d1d064f3ae0af97c1b1a8e3541e60944039c862`；截图目录 `/home/dev/gdds-fe-evidence/fe2b/5d174967-05/`.

## 1. 范围完成情况

| 要求 | 状态与证据 |
| --- | --- |
| §6.3 N1、N2、R2、R5、R7、S1、S2（甲） | 完成。S2 只有验收截图，没有演示截图；对应测试与探针见第 2、5 节。 |
| 模拟会话与身份 | 完成。开发环境提供提交人、审核人、归档确认人、无权限身份；请求携带所选身份 token。R2 生产产物检查覆盖模拟 API、身份选择和 `src/features/dev/` 模块。 |
| 工作台组态树与 History | 完成。工作区经 `POST /v1/workspaces` CreateOrGet，参数来自会话 `business_project_id` 和 `gateway_device_external_key`，不发送 `Idempotency-Key`；接受后端行为 201/200。History 由 `GET /v1/history` 以 `limit/cursor` 分页获取；没有工作区列表接口。 |
| 当前会话操作与基线状态 | 完成。“进行中的操作”只指本会话发起且 operation id 在 URL 中的操作；基线状态按 `eligibility_note` 展示。 |
| 正式工作台 | 完成。四列、搜索、列排序与调宽；详情面板 400px，视口 ≤1440px 默认折叠，1920px 默认展开；短状态标签与折叠的长原因。没有实现 Q4“历史初始备份”。 |
| 上下文工具栏 | 完成。视图模型列出全部操作、业务启用条件及禁用原因并有单测。原始组态备份/本次归档组态是 OPEN 工作区的目录快捷入口，FE2c 接入点击；Preview 留在详情面板。归档主线根据审核及 `eligibility_note` 条件启用。FE2c 写操作未由 e2e 点击。 |
| 比较托盘与结果抽屉 | 完成。History 比较最多选 3 节点，首次 POST 202、同 key 回放 200；按 operation id 轮询，完成后下载 bundle 并打开 History 差异浏览。托盘在比较/下载期间锁定，下载失败可重试。逐比较对的表数和变更表摘要尚未展示，作为偏差列于第 8 节。 |
| Preview、History、审核三种入口 | 完成。Preview 使用工作区 `current_preview_result_id`；History 从比较托盘进入；待审提交由“基线节点 → 提交”发起 History 比较并只读读取 `GET /v1/submissions/{submission_id}/review`。审核写操作留给 FE2c。 |
| URL 路由 | 完成。工作台与差异浏览可从 URL 直达；节点、比较、模式和 operation id 可寻址；`request`、`previewRequest`、`reviewRequest`、`historyRequest` 不再作为参数。 |
| FE2c 边界 | 上传步骤停在 FE2c；目录入口暂不执行写操作；审核、提交与归档写操作未接入；不提供历史初始备份入口；没有审核顶栏或演示截图。 |

## 2. 带入项完成标准

| 带入项 | 完成情况与验证 |
| --- | --- |
| N1 幂等意图 | `frontend/src/features/api/idempotency.test.ts` 的 `reuses the stored key after a timeout and creates a key when the selected nodes change` 测试产品 helper：timeout 后从 sessionStorage 恢复同一 key，节点改变时生成新 key。e2e `History 比较超时重试复用同一幂等键，刷新后按 URL 中 operation_id 续查` 和 `查看差异超时后的重试复用同一幂等意图` 覆盖两条入口；模拟接口按 key 回放首次结果。 |
| N2 轮询 | `frontend/src/features/api/polling.test.ts` 覆盖状态请求超时仍运行、网络/5xx/429 有上限退避，以及 history-compares 五种状态；e2e 覆盖运行中、连接中断、刷新后按 URL operation id 续查。 |
| MANUAL_RECOVERY_REQUIRED | 单测覆盖 `MANUAL_RECOVERY_REQUIRED → RUNNING → SUCCEEDED` 与 `MANUAL_RECOVERY_REQUIRED → FAILED`，30 秒轮询；e2e 检查“需要管理员处理”、可复制操作 ID、无重试按钮、“刷新状态”以及状态变化。此状态不是终态；操作终态为 `SUCCEEDED`、`FAILED`、`CANCELLED`、`SUPERSEDED`。 |
| R2 生产构建 | 正向：最终 runner 的生产构建探针输出 `production dist contains no simulated API, identity selection, or mock data modules`。B3 负向探针在 `App.tsx` 直接导入并使用 `mock-data`，生产检查按预期 exit 1，详见第 5 节。身份选择只随开发模拟会话提供。 |
| R5 连接状态 | `frontend/src/features/api/connection-status.test.ts` 覆盖已连接、连接中断、未请求前隐藏；错误页隐藏已连接状态。e2e `所选模拟身份携带对应 token；无权限错误页不显示已连接` 核对错误页不出现“已连接”。 |
| R7 公式 | `frontend/src/features/view-model/formula-view.test.ts` 恢复第 1 轮前缀断言 `| - 线路保护装置 A:线路电流`，并覆盖一元减号为首个子节点时输出 `- Device 1:X`。公式抽屉内容可随高度滚动，重拍 `formula-preview-*` 与 `formula-history-*`。 |
| S1 正常业务场景 | `preview-workbench-normal` 是一个转发通道遥测表；前后各 90 行，新增/删除/修改各 6 行，导航、pair 与主表诊断为空。`backend-fixture.test.ts` 的 `matches the backend summary for the normal transfer-channel telemetry browse` 对照后端摘要；e2e 普通页签打开主表并拍 S3/S4 主表、悬停、Debug。产出风险：view `MEDIUM_HIGH`；annotations `MEDIUM_HIGH`、`MEDIUM_LOW`。另含 `composite_signal_point` 0→0 表，见第 8 节。 |
| S2（甲） | 比较托盘截图展示 2/3 节点；上传步骤仍留 FE2c，没有演示截图。 |
| B1 | `formula-view.test.ts` 的 `renders production EXPRESS, POINT and DIGITAL ASTs as mapped formula lines` 与 `renders unary minus as the first child without an outer operator prefix` 恢复父级 `|` 并覆盖首子节点一元减号；公式截图见第 6 节，去前缀变异探针见第 5 节。 |
| B2 | `mock-data.test.ts` 的 `keeps every simulated History node within the backend node rules` 遍历全部模拟 History 节点，对照 `vnext/backend/src/gateway_backend/application/history/contracts.py:108-113`。 |
| B3 | `check-production-build.mjs` 检查 Vite rendered module 清单；直接导入 mock-data 的负向探针按预期失败，见第 5 节。 |
| B4 | e2e `所选模拟身份携带对应 token；无权限错误页不显示已连接` 与 `无权限身份发起历史比较时托盘显示统一权限提示和错误码`。 |
| B5 | `idempotency.test.ts` 的 `reuses the stored key after a timeout and creates a key when the selected nodes change` 测试产品 helper；两条入口的超时重试 e2e 与换新 key 变异探针见第 5 节。 |
| B6 | `workspace.test.ts` 的 `formal workbench tree and contextual actions` 覆盖动作视图模型；e2e `正式工作台呈现 History、四列表格、操作说明与 1280/1920 详情面板`。 |
| B7 | e2e `历史比较抽屉在 bundle 就绪前隐藏打开入口并允许下载重试` 与 `History 比较仍在运行和连接中断状态清晰显示`；逐比较对表数/变更摘要列为第 8 节偏差。 |
| B8 | `workspace.test.ts` 树模型测试及 e2e `正式工作台呈现 History、四列表格、操作说明与 1280/1920 详情面板` 覆盖同层基线、子节点、比较标记、排序与折叠。 |
| B9 | e2e `FE2b 正常业务场景以普通页签打开主表且无导航或表诊断` 移开鼠标并等待 tooltip 消失后拍主表，再重新悬停拍图。 |
| M1–M9、M11 | 已随本轮修正：状态标记分离、History 状态文案、权限/404 不误报连接中断、节点 URL 语义、审核状态文案、基于服务端时间计算已等待时长、有限轮询断言、转移来源核对、无任务时隐藏任务指示、ordered move 保留测试。对应覆盖见 `workspace.test.ts`、`OperationStatusPanel.test.ts`、`polling.test.ts`、`mock-data.test.ts`、`presentation.test.ts` 与 e2e。 |
| M10 | 记录为 fixture 事实：生成摘要还包含 `composite_signal_point` 0→0 的快照表，在导航中归入“其他表”；主遥测表及导航、pair、表诊断均符合场景标准。 |

## 3. Fixture 生成与复现

### 生成入口与复现命令

生成脚本提交：`d1da70c015dc74a9c82fbd923d974a3cf9415a7a`，路径 `frontend/scripts/generate-backend-bundle-fixtures.sh`。它调用 `frontend/scripts/generate-backend-bundle-fixture.py`，通过 `gateway-backend-deps:lock-d054366c02fa` 中的 `/build/backend/.venv/bin/python` 导入挂载源码树中的后端本地包。源码只读挂载，network 为 `none`，不启动 Dolt/Compose；两个输出目录必须在 worktree 外且运行前为空。单测可选；后续复现命令就是此脚本。

```bash
TMPDIR=/home/dev/gdds-test-tmp \
frontend/scripts/generate-backend-bundle-fixtures.sh \
  --output-one /home/dev/gdds-fe-logs/fe2b/fixture-output-one-3736d21854 \
  --output-two /home/dev/gdds-fe-logs/fe2b/fixture-output-two-3736d21854 \
  --log-dir /home/dev/gdds-fe-logs/fe2b
```

成功生成日志：`/home/dev/gdds-fe-logs/fe2b/backend-fixtures-3736d21854-20261103T135340Z-822046.log`，SHA256 `617bac0537e5240bb4de58f572045efac4a3cc9effb589b2be88988c36291917`。节点 `gw-dms-test-05.lan`，2026-11-03 13:53:40Z 至 13:54:07Z，HEAD `3736d218545947ec7dc3e380d49c5ecbfc3d96fc`，exit 0。两次各 226 个文件，目录树 SHA256 都为 `5aaf509380e5efb52ef4d7103da1fbdf0c9483720c4666a676d46b7c2b2b9a9a`，`byte_identical=true`。`generate()` 两次成功，没有遇到生产代码无法生成场景的情况。复审报告（main 本地提交 `b9574f2558`）更正了复现位置：复审方是在代码候选 `5ac704c6` / handoff `bf4942e0a8` 上重新生成两次，各 226 个文件并与已提交 fixture 逐字节一致，不是在 `5d174967` 上执行。此后至 handoff `7682297b72`，fixture 生成器、输入 JSON 与 `vnext/` 均未改动，因此该复现结果适用于当前代码候选。实施会话没有再次生成 fixture。

### 生成输入与镜像身份

- 镜像：`gateway-backend-deps:lock-d054366c02fa`
- config digest：`sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`
- 19 个 RootFS DiffID（按镜像顺序）：
  `sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a`,
  `sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104`,
  `sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15`,
  `sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1`,
  `sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a`,
  `sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25`,
  `sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588`,
  `sha256:d9100de052a9a4cbb39754e9bcdbebe082b0c8e4cd1a5d4f446cef2cd4ac87e1`,
  `sha256:01614bf2b27515a3ea31f460030cef9e37a2d7d65d7cffdac5f3d7b6d49671c1`,
  `sha256:2f04268a672be20980a33289ad5086de8a8a7db36b51cff7fcfea0995baec29f`,
  `sha256:3c5de003195a21e12a21ff7a4976b687ef61ef946f74a6465281c6f6f2720cc6`,
  `sha256:3b36040844dfd8c76fbc316aafd0929d65e602016261737368cf63e245598dd6`,
  `sha256:bfb2b2a172006ee7882fcc751dcef85d418a0e24837b11d30220cf21183c1dce`,
  `sha256:b6b4b17f0450d4b8b752e1fb44298477f29e1f74d65584d3182227e9ff20b12c`,
  `sha256:50e4a188b1446b8b9a51ccb3d9745164e86d6b9bdb1f342e9774fe93a4f853d3`,
  `sha256:a7afafdb6a8aa5d13ade8b6eef2986bd37d07e84b2d0b3767f7bb0eb535bf5f4`,
  `sha256:678693472110b1f3f8c40466db580981b7952ede803eaa1518f59d3730ab2814`,
  `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`,
  `sha256:c338f3f88c37281e775f0b6dfdfa4c079858214cf04733e88f0bda4e4ca4a1f0`。
- 镜像记录来自 `/usr/local/share/gateway-backend-dependency-base/inputs.json`。运行时只将 `vnext/backend/uv.lock` 与 `.python-version` 作为阻断输入核对；两者与镜像相同：`uv.lock` `d18d89a24a8acae02eb6b3b23c342c1b673ea0e7e87add93d0762edfa18b822d`，`.python-version` `3a55324cbeddc91df012407d051dad08c88624c95a82fbdb856728729fbd14ab`。
- Q14（owner 已确认）：`vnext/backend/pyproject.toml` 与 `vnext/rust/Cargo.lock` 的差异仅记录，不停止。镜像/候选 SHA256 分别为：pyproject `4c091e36d4762f11b4085f207528548502ae723e7876d2feeeedcd4cd56f9c7f` / `747b219d8fcef9a30723183604ebc136e787ab57416d77c078ad68e062f5d9ef`；Cargo.lock `bac3443e4d16c22ed16adaadbaf3d3e7b713d78516e14938cdbca50ebd837d29` / `0d79e098d5da6c241fa0807fd8dd0c7ff8a628f088cb02c2d3be46a5964c6380`。pyproject 差异是 mypy 配置；Cargo.lock 用于 cargo fetch，生成器不编译 Rust。没有更新或重建依赖镜像，没有使用转发代理。
- 生成器输入 SHA256：`frontend/scripts/generate-backend-bundle-fixture.py` `d2b30b8956b44fa5efdd2370c357d979f0a22b5bf7acd2d17c3dab7ef994aa18`；`frontend/scripts/docker-save-image-identity.py` `c205c3c044d388ce7a75f36eb4d02ef209b4487ef4d2f39229d4abc98f179a45`；`business-navigation.json` `fef43f6e1fbee8e8cf0b9882fbe0469ae3219749bdfb7f408a9c94b88f284127`；`navigation-diagnostics.json` `c0d4b157580f8b428b2e8bb9c63b78a4bfe6a4bcb51c65a0f6ac2cfd81d2f791`；`business-navigation-workbench.json` `a06d0b2e8148278bf2aa9127d9d8ac872d7f3891ba31d9664dc0b8168e58981c`。

### Fixture 场景与风险

风险等级来自后端生成的 surface view 与 risk annotations；既保留 view 汇总等级，也列出 annotation 中的等级。

| Fixture | 产出风险等级 |
| --- | --- |
| `fe2a/preview-full` | view：`MEDIUM_HIGH`（两个 pair）；annotations：`MEDIUM_HIGH`、`MEDIUM_LOW` |
| `fe2a/preview-modified-only` | view：`MEDIUM_HIGH`；annotations：`MEDIUM_HIGH`、`MEDIUM_LOW`、`UNKNOWN` |
| `fe2a/preview-replacement` | view：`HIGH`；无 risk annotations |
| `fe2a/history-three-nodes` | 两个 pair 的 view 均为 `MEDIUM_HIGH`；annotations：`MEDIUM_HIGH`、`MEDIUM_LOW` |
| `fe2a/preview-no-navigation` | view：`MEDIUM_HIGH`；annotations：`MEDIUM_HIGH`、`MEDIUM_LOW`、`UNKNOWN` |
| `fe2b/preview-workbench-normal` | view：`MEDIUM_HIGH`；annotations：`MEDIUM_HIGH`、`MEDIUM_LOW` |

FE2b S1 fixture 已由上述生成器产出并提交。文件位于 `frontend/src/test/fixtures/source/backend/fe2b/preview-workbench-normal/`；表为 `b1_n1_iec104_yc_list`（遥测量），导航组为“转发通道”，前后各 90 行，新增/删除/修改各 6 行。导航、pair 和表诊断均为空。已有 FE2a fixture 与截图保留。

## 4. 模拟响应场景与来源（§7.5）

### 成功响应

成功 JSON 响应均用 `frontend/src/features/api/generated/openapi.ts` 生成类型加 `satisfies` 约束。除后端行为例外 `POST /v1/workspaces` 的 201，以及 `POST /v1/history-compares` 的 202，状态码在该 route 的 OpenAPI responses 中声明；workspaces 201/200 和 history-compares 202/200 的响应体均按同一个 OpenAPI schema 约束。二进制 bundle 由后端生成 fixture 提供。

| Route | Method / status | Schema / 场景 |
| --- | --- | --- |
| `/v1/workspaces` | POST 201、200 | `WorkspaceResponse`；CreateOrGet 新建、已存在 |
| `/v1/history?limit=100`、`/v1/history?limit=100&cursor=cursor%2Fnext` | GET 200 | `HistoryListResponse`；首页、游标页 |
| `/v1/workspaces/{workspace_id}/upload-revisions` | POST 201 | `UploadRevisionResponse` |
| `/v1/workspaces/{workspace_id}/preview-operations` | POST 202 | `OperationAcceptedResponse` |
| `/v1/operations/{operation_id}` | GET 200 | `OperationResponse`；QUEUED/RUNNING 与成功、失败、取消、替代、人工恢复状态及转移序列 |
| `/v1/workspaces/{workspace_id}/submit-attempts` | POST 202 | `SubmitAcceptedResponse` |
| `/v1/submissions/{submission_id}/review-events` | POST 201 | `ReviewAppliedResponse` |
| `/v1/submissions/{submission_id}/review` | GET 200 | `ReviewFactsResponse`，审核浏览只读读取 |
| `/v1/history-compares` | POST 202、200 | `HistoryCompareAcceptResponse`；首次受理与幂等回放，回放使用首次响应体 |
| `/v1/history-compares/{operation_id}` | GET 200 | `HistoryCompareResultResponse`；QUEUED、RUNNING、SUCCEEDED、FAILED、CANCELLED |
| `/v1/history-compares/{operation_id}/bundle` | GET 200 | `application/x-tar`；History 比较 bundle |
| `/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle` | GET 200 | `application/x-tar`；后端生成 Preview fixture bundle |
| `/v1/archive-plan-preview` | POST 200 | `PreviewArchivePlanResponse` |
| `/v1/archive-confirmations` | POST 201 | `ArchiveAuditAppendResponse` |
| `/v1/archive-anomaly-resolutions` | POST 201 | `ArchiveAuditAppendResponse` |
| `/v1/archives` | POST 201 | `ArchiveStartedResponse` |

### 错误响应与写路由覆盖

全部 JSON 错误体为 `ErrorResponse`。`mock-data.test.ts` 读取 `frontend/openapi.json`，逐项核对 route、状态码与描述中的 code；字符串字段测试核对 `SIMULATED_STRING_VALUES` 中的带源码位置值表。`WRITE_SCENARIO_COVERAGE` 与 OpenAPI 的所有公共 v1 POST routes 完整对照，并逐个验证成功、403 与该 route 已声明的版本/幂等冲突；未声明的冲突不模拟。

| Route | 模拟状态码与错误 code |
| --- | --- |
| `GET /v1/history` | 403 `SCOPE_FORBIDDEN` |
| `POST /v1/workspaces` | 403 `SCOPE_FORBIDDEN`；422 `REQUEST_VALIDATION_FAILED`；503 `SERVICE_NOT_READY` |
| `POST /v1/workspaces/{workspace_id}/upload-revisions` | 403 `SCOPE_FORBIDDEN`；409 `WORKSPACE_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT` |
| `POST /v1/workspaces/{workspace_id}/preview-operations` | 403 `SCOPE_FORBIDDEN`；409 `WORKSPACE_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT` |
| `POST /v1/workspaces/{workspace_id}/submit-attempts` | 403 `SCOPE_FORBIDDEN`；409 `WORKSPACE_VERSION_CONFLICT`、`BASELINE_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT` |
| `POST /v1/submissions/{submission_id}/review-events` | 403 `SCOPE_FORBIDDEN`；409 `REVIEW_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT` |
| `POST /v1/history-compares` | 403 `SCOPE_FORBIDDEN`；409 `IDEMPOTENCY_CONFLICT`、`ADMISSION_CONFLICT`；429 `ADMISSION_LIMIT_REACHED` |
| `POST /v1/archive-plan-preview` | 403 `SCOPE_FORBIDDEN`；409 `CANDIDATE_BINDING_CONFLICT` |
| `POST /v1/archive-confirmations` | 403 `SCOPE_FORBIDDEN`；409 `BASELINE_VERSION_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT` |
| `POST /v1/archive-anomaly-resolutions` | 403 `SCOPE_FORBIDDEN`；409 `BASELINE_VERSION_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT` |
| `POST /v1/archives` | 403 `SCOPE_FORBIDDEN`；409 `BASELINE_VERSION_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT` |
| `GET /v1/history-compares/{operation_id}` | 503 `HISTORY_INTEGRITY_FAILURE` |
| `GET /v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle` | 503 `SERVICE_NOT_READY` |

### 字符串值来源与 FE1/FE2a 模拟数据改正

唯一字符串取值表：`frontend/src/features/dev/mock-data.ts:SIMULATED_STRING_VALUES`。核对测试：`frontend/src/features/dev/mock-data.test.ts` 的 `keeps OpenAPI string fields within backend source values` 与 `keeps operation and workspace labels aligned with the sourced values`。值均来自表内所列后端源码位置。FE1/FE2a 的 journeys 与组件模拟响应也改成 OpenAPI 生成类型约束，不留无类型响应体。

已改正的字段和值：

- `OperationResponse.job_kind`：`backend-vnext/preview`、`backend-vnext/submit`、`backend-vnext/history-compare`。
- `WorkspaceResponse.state`：`OPEN`、`CLOSED`；`SubmitAcceptedResponse.state`：`PREPARED`。
- 审计 `subject_kind`：`CONFIRM_SELECTION`、`APPROVED_SIBLING_EXCLUDED`、`PROJECT_IDENTITY_EXCEPTION`；audit `action` 取值也按后端定义列入取值表。
- anomaly `issue_code`：`APPROVED_SIBLING_EXCLUDED`、`PROJECT_IDENTITY_EXCEPTION`。
- `confirmation_requirements`：`sha256:selection-subject`；archive blockers：`ACTIVE_SUBMIT_ATTEMPT`、`ARCHIVE_INTEGRITY_FAILURE`。
- 操作状态、History 比较状态、诊断码、History eligibility note 均由取值表约束。模拟响应未使用 `RETURN_FOR_REVISION` 或 `RETURNED_FOR_REVISION`。

所有写操作场景的主数据位于 `COMPLETE_RESPONSE_SCENARIOS`、`WRITE_SCENARIO_COVERAGE`、`SIMULATED_ERROR_RESPONSES`，同文件中使用生成 schema 的 `satisfies`。e2e 模拟接口以 `Idempotency-Key` 为键保存首次 history-compare 请求体和响应；同 key 不同请求体会失败，重放返回相同 operation id 与首次响应内容。场景内 operation id 与 fixture refs 保持一致。

## 5. 05 测试与运行证据

### 最终源码候选完整运行

- 节点：`ct108-gw-dms-05`，hostname `gw-dms-test-05.lan`；未占用节点计时标记。
- clean detached worktree：`/home/dev/gdds-fe-fe2b-5d174967-05`，HEAD `5d1749675621a020a052690b95d55111af5509f9`，frontend tree `a0f8ce750b053d83907435f9c0ba1357603c5472`；起止 HEAD/tree 一致。
- runner：2026-11-03T15:49:41Z 至 2026-11-03T15:50:15Z，exit 0。完整入口 `frontend/scripts/run-tests.sh --screenshots /home/dev/gdds-fe-evidence/fe2b/5d174967-05`。
- 完整运行日志 `/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T154941Z.log`，SHA256 `01951df3f663ba8476533ccf9d1d064f3ae0af97c1b1a8e3541e60944039c862`；wrapper `/home/dev/gdds-fe-logs/fe2b/targeted-full-run-5d174967-05-corrected-cache-source-wrapper.log`，SHA256 `d024b18c78521a64402992aae26e160b593feff8d48e881ce3fd9795071ad571`。
- 结果：typecheck、lint、24 个单测文件/107 tests、生产 build、R2 正向生产检查、15/15 模拟接口 e2e 与 `--screenshots` 全部通过。R2 输出：`production dist contains no simulated API, identity selection, or mock data modules`。
- 工具链镜像：`mcr.microsoft.com/playwright:v1.64.1-noble`；config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`。RootFS DiffID：`sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`、`sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`、`sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`、`sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`、`sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`、`sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`、`sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`。
- npm 缓存：`/home/dev/gdds-fe-cache/fe0/npm-cache`，预填充缓存；来源归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`；来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`，package-lock 解析项 305 个。未使用转发代理。

### B3 生产构建负向探针

- 临时 commit `9991da34aecf7f00dc1402a66bd981f3fe15c249`，frontend tree `d7015e72c8f6ac4cdd8f17b78ad346459c678110`；在 `App.tsx` 直接导入并使用 `./features/dev/mock-data`。
- CT05 clean detached worktree：`/home/dev/gdds-fe-fe2b-probe-b3-5d174967-05`。生产检查按预期 exit 1：`production dist includes development-only modules: /tmp/frontend/src/features/dev/mock-data.ts`。
- runner log `/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T155510Z.log`，SHA256 `23329e270523306f4fb3a3a40084595c020c6ae967eedbfe7c9251be0990d3b0`；wrapper `/home/dev/gdds-fe-logs/fe2b/probe-b3-runner-5d174967-05-wrapper.log`，SHA256 `d18ac783885441bbcbced8b8fc8f2930f7a2f16fdc7405fbc051c4e517af7891`。类型检查、lint、单测和 build 在预期的探针失败前通过。

### B1 与 B5 单测变异探针

| 探针 | 临时改动与结果 | 运行日志及 SHA256 |
| --- | --- | --- |
| B1 去掉公式上层前缀 | 临时 commit `73349f65a2ac97fcdff8b2a52384081293d13396`，frontend tree `80c7eff702c63bc0165acedb6fe91744a0aa4045`；公式单测按预期失败，检出 `| -` 前缀丢失，runner exit 1。 | `/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T155323Z.log` `b70ea9add277b4d15ce30acd028205f2cf2945f7a201730f678c44c6a3efdf38`；wrapper `/home/dev/gdds-fe-logs/fe2b/probe-b1-runner-5d174967-05-wrapper.log` `7b3711ea058aea6d757bcac8c55c3368dcb7e317d9cbf27323debccb69508c2c`。 |
| B5 重试生成新 key | 临时 commit `9afb7a59a70e87fb69f64e29c5110c16aca91a6a`，frontend tree `f1f835c8dd1653ea108c1be011540dca03bc7bbe`；单测预期失败，断言捕获 `intent-key-1` 被错误换成 `intent-key-2`，106/107 通过，runner exit 1。 | `/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T155420Z.log` `94282f1bec8373bb1ed2f43b8614c80884d0da11aa2c489fe73e562225d5f9bc`；wrapper `/home/dev/gdds-fe-logs/fe2b/probe-b5-runner-5d174967-05-wrapper.log` `6292a62b930c4b39c8f8f25c70d682b00c05fa8cc6c583d2909156d4252150c8`。 |

B1 探针在断言失败后的测试 teardown 另输出一条未处理异步 `window is not defined` 警告；公式断言已明确因前缀变异失败，探针退出码为 1。该现象只发生在故意破坏测试期望的临时 worktree 中。

### 定向修复调试记录

以下是在 05 clean detached worktree 调试源码时的失败；按用户指示修复后重跑。每次运行都保留日志，最终 5d174967 候选完整入口 exit 0。

| 候选 | 失败 | 日志 SHA256 | 修正提交 |
| --- | --- | --- | --- |
| `548cd290a2` | typecheck：Rollup `ModuleInfo.isIncluded` 类型不可用 | `17d853c8070836bd03156977522c8e197e3b32a39b3970beb4bc4e583e07a50a` | `aed2ccfac0` 改为检查 rendered module 清单 |
| `aed2ccfac0` | 新的一元负号用例期望文本不含实际设备名 | `b520f69cfe8f3894fe90a7dfec256c488f9a40ea7c92cdff43bfa632ab581638` | `b49f584ab7` 修正测试标签 |
| `b49f584ab7` | e2e 搜索数量预期过时；bundle 中断场景实际会自动重试一次 | `fa2e36f322908776d37b77dc638d8311fdcea4cdc8163a43e1a40e2de1091284` | `de0ef51337` 修正断言与场景 |
| `de0ef51337` | e2e 对比较抽屉期望两条 pair，但响应 fixture 只提供一条 | `75a5af05dc13f2f1cf111a7c4daa746269d74d33f6acdf1cac042de8fc90e0f2` | `9dde8f0101` 修正为该场景一条 pair |
| `9dde8f0101` | runner 通过；人工查看公式截图发现最后一行被裁切 | `3b92efa6e1939b986d02be817de3b85d75153b8be3bfbb5b7326829357a648ec` | `5d17496756` 让公式内容区占满抽屉并可滚动；其后 15:49 完整运行通过 |

最终候选另有一次完整 runner 在 npm 缓存来源提交参数有误时通过，但该次不作为证据；保留日志 `/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T154807Z.log` SHA256 `b44c13b82bb7f34be801ff10a0ed34fb96c458c17260395104e463d3a34baf21`，wrapper `/home/dev/gdds-fe-logs/fe2b/targeted-full-run-5d174967-05-wrapper.log` SHA256 `19e3696b40ae048a571fb6080146caa96a7c59084fa4095382dfdac9f9a68807`。按 DC68 校正来源提交参数后，从完整入口起点重跑，使用本节列出的 15:49 运行作为候选证据。

### CT04 退出权威运行

- 节点：`ct108-gw-dms-04`，hostname `gw-dms-test-04.lan`。clean detached worktree `/home/dev/gdds-fe-fe2b-5d174967-04`；legacy 链接指向 `/home/dev/gateway-data-management-system/legacy`；运行前无占用标记。
- 唯一一次入口：`./frontend/scripts/run-tests.sh --screenshots /home/dev/gdds-fe-evidence/fe2b/5d174967-04`。runner 于 `2026-11-03T16:28:07Z` 开始、`2026-11-03T16:28:47Z` 结束，exit 0。起止 HEAD 均为 `5d1749675621a020a052690b95d55111af5509f9`，起止 frontend tree 均为 `a0f8ce750b053d83907435f9c0ba1357603c5472`，运行后 worktree clean。
- 结果：typecheck、lint、24 个单测文件/107 tests、生产 build、R2 正向生产检查、15/15 e2e 和 screenshots 全部通过。
- 权威日志在 CT04：`/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T162807Z.log`，SHA256 `25f3295dc943bd61d1c72e83e18e617a952550ce984dcb7a107bc07a92665c1a`。外层 wrapper `/home/dev/gdds-fe-logs/fe2b/runner-wrapper-fe2b-exit-04-5d174967.log`，SHA256 `be36d79eb09d4bc20d3365d8986feb1286e9bfca5f0319af44a3b640a5df783a`。运行前核对记录 `/home/dev/gdds-fe-logs/fe2b/preflight-fe2b-exit-04-5d174967.log`，SHA256 `bb7a114eb83a0877c5c8a05044581b82e07beac42f797dd4cc99bdad527be406`。
- 工具链沿用 04 的 FE0 预填充：`mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；7 个 RootFS DiffID 为 `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`、`sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`、`sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`、`sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`、`sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`、`sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`、`sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`。身份按 config digest 与全部 DiffID 核对。
- npm 使用默认预填路径 `/home/dev/gdds-fe-cache/frontend/npm-cache` 和归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`；归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`。未使用节点自行打包的缓存副本，也未使用转发代理。

## 6. 截图清单与视觉偏差

CT05 调试截图共 50 张，目录 `/home/dev/gdds-fe-evidence/fe2b/5d174967-05/`；其清单在 CT05，SHA256 `a5fdc5e02a0b8e42342ca2f3a14198ed0cfb8ee02ab194adcef136bcf52868fa`。退出取证以 CT04 的 50 张截图为准：目录 `/home/dev/gdds-fe-evidence/fe2b/5d174967-04/`；清单 `/home/dev/gdds-fe-logs/fe2b/screenshot-sha256-5d174967-04.txt` 存在 CT04，SHA256 `bea5e1b49c163a6275c59a3e84a01e0116c7663522b4e0951f3caeebe8f9960d`。

| 文件 | SHA256 |
| --- | --- |
| `bundle-error-1280.png` | `e91644ff3ad84b2a878c7e1517cc9f7835877a95d817852b03c940e6f766f564` |
| `bundle-error-1920.png` | `fb5c3dd88c95655ddc89f0ca0b1a1a4e6d0a3158a70cd760c74caef1f592430f` |
| `dataset-replacement-browse-1280.png` | `cc78cb9509090b9fa570ea5a04b7b049c63d29e897c370e0117841631e4e9c4e` |
| `dataset-replacement-browse-1920.png` | `6c2c94f4f69e0d22ef0276714eee54ec69fb735889c9ab0a810836d59d4e5465` |
| `formula-history-1280.png` | `8dcf32cde558446a768c297cc37f8d0dd6bbb7f951e9c1c679de142ba0466e4a` |
| `formula-history-1920.png` | `98dc6ae986a0b53ec09543a24ce0e6a1ee1182a646a29a00d626b8b2ec878f25` |
| `formula-preview-1280.png` | `aadb7db014e12ee7e31267e48c867fc93d27e488020bbbcaaf2c3d1487a20dd3` |
| `formula-preview-1920.png` | `2cc21db1eb53f730c0bb366acc7fbdda695b0a441824deab1c8db4b11ebb66b7` |
| `history-compare-connection-interrupted-1280.png` | `9e5feedc510a78a2571130769648c1ea60e6ac120f7d7be0a6667822b640fd80` |
| `history-compare-connection-interrupted-1920.png` | `e9cbca6945517973bbbba2df523be847acb474230410790f02a83c601555741b` |
| `history-compare-result-drawer-1280.png` | `46d103e9d62649ddf9a4c988311f6f243764d2116c9000a799ce011aaea40ee3` |
| `history-compare-result-drawer-1920.png` | `826c72b795d2d3ff155c91c4abd5c713ffa05779912f3ef4219248af24c21454` |
| `history-compare-running-1280.png` | `bac9a75d4760d47498e9518bcdcebf1ad15fce96bb2f6a1adc613e021d44fd47` |
| `history-compare-running-1920.png` | `9d1d27f63c0058ed2be3ce3f2409e38edd5504cdc9e36ad1cb29628e92d2b1ec` |
| `loading-skeleton-1280.png` | `1a09a7bb84166539b7f4e58673a61be0e658b8937e04da7253750e946108b83c` |
| `loading-skeleton-1920.png` | `4a401678b2edd8331ddc279078aaa44b609a7ff3c9dcd3f839f99207708179a0` |
| `manual-recovery-required-1280.png` | `4335c774570f098f93967b9e91589d342fbf299475a37f21bc54c0a3232e5437` |
| `manual-recovery-required-1920.png` | `879e4258417a927c69cc1cea20f14359cfa9d3d9e1d71bbeee97c65f1935883b` |
| `navigation-fallback-1280.png` | `a84ba53eafa2c86726b5df494cbbac7f778b7255631c8c0204efe54184df9a72` |
| `navigation-fallback-1920.png` | `e6da1ad3759e2458c5dd11ad7f6f290d44eff353ad9bae5c46f0844e7ebdf848` |
| `s1-workbench-1280.png` | `206fc6eb8be094c2a1ca6c2395e2e2a9ff17bf8b8d7c845bc2682ab3c6fa0b9d` |
| `s1-workbench-1920.png` | `bcd4ed3a728e735e902803d176e8403d247dc90a0912365128b6f953c202f475` |
| `s2-compare-tray-1280.png` | `3a6d9da0501087b204bdf64eb802b48172c645c8dc355879f3428dcdbd96950b` |
| `s2-compare-tray-1920.png` | `2831e2c3cf8af2f1dc0aa84ffa3004131717ae4caf69d8d4a17c3cccb7bee238` |
| `s3-header-history-1280.png` | `22ef7766e9f1e6fa8b45c460622f1867ebd2649edea977bd4040d3ae741b4b6f` |
| `s3-header-history-1920.png` | `14dcc76039dd7edbf8b603c4dc09812c21163e2721869c057c978ebf81cde847` |
| `s3-header-upload-1280.png` | `ff82e1426d90c4c5e39864fe9628c9675bbe3e77a8d669f13701268edff622d4` |
| `s3-header-upload-1920.png` | `a46f7e9a6859ed3ef29fa68dee2fb1a86668fda53184c8e38c3f3c00b769eb97` |
| `s3-workbench-normal-1280.png` | `fe83b6c8f5dd83ab26dad57e4a421388bba2749a55646ef4da3c1650c464bd5f` |
| `s3-workbench-normal-1920.png` | `78511e8edbb57b51c54b6c3cde3e3b6a53b746084edb38c3f4b5f490b6304685` |
| `s3-workbench-upload-1280.png` | `2e34e78e2525a83292d2000efb6dbf8a87ddef874b615b9a9f019518a35f3339` |
| `s3-workbench-upload-1920.png` | `d4e4b908e65c17adb509a3cef60a986735f5e2b38b81e76ca1f59a83d06844f4` |
| `s4-grid-debug-1280.png` | `b6a12370f2175d725fe5c1121949135344e7859c6c45a06c1645074b5bf8b7e2` |
| `s4-grid-debug-1920.png` | `795cf64ee1a79d5d7254272a6a0c6b36295d87433b4e7c96301cce28ac91ac0e` |
| `s4-grid-hover-1280.png` | `0e7d0b4353776801e515f250307f49449e0b33f3ef728f4ecfe648a5384181c9` |
| `s4-grid-hover-1920.png` | `54a0ba5283a178ef7a3dc11b2f01178a18d6379363720691a13ca645ba5d5169` |
| `s4-grid-main-1280.png` | `2e34e78e2525a83292d2000efb6dbf8a87ddef874b615b9a9f019518a35f3339` |
| `s4-grid-main-1920.png` | `2898da72e70699d024fa3ccc9e694b53097a859bd0b662fe6da36ebbd64b13b3` |
| `s4-grid-normal-debug-1280.png` | `69b95897de57182602841de8b12f91775710c8e8c57ed9b5c35560e57f23f96f` |
| `s4-grid-normal-debug-1920.png` | `03eb9f633e4742ff29c48e2f4bae09c743efa42d9e41ffaad9173e1a04973ede` |
| `s4-grid-normal-hover-1280.png` | `722414b84f5089351f254fc1179521f2f3e77096d324ac7eb66dd490254df2e0` |
| `s4-grid-normal-hover-1920.png` | `94ffb3e1434f31f7fd00c4cd1d2186cb5d1cfce1f6b91e4dd0bf54d834a53a0b` |
| `s4-grid-normal-main-1280.png` | `fe83b6c8f5dd83ab26dad57e4a421388bba2749a55646ef4da3c1650c464bd5f` |
| `s4-grid-normal-main-1920.png` | `78511e8edbb57b51c54b6c3cde3e3b6a53b746084edb38c3f4b5f490b6304685` |
| `s4-semantic-tokens-1280.png` | `116f9cbb8991ace7deef04e4f5029a211ff933c38aee5e3348f5cba63bcd8b2c` |
| `s4-semantic-tokens-1920.png` | `15fe88e318ed59410b184631888681262349d9220dda26a5f49ac6f12c16dcba` |
| `tab-overflow-1280.png` | `f89e42e99af51028d3cc69eff3212e06ef88f89912d93b7387b5fb44892dab87` |
| `tab-overflow-1920.png` | `f33c88bacfcc4cf0842cc5fe8ea7ce11ec6a9e401e4d30e80b48bd1e447e2ca1` |
| `workspace-error-no-connected-1280.png` | `2cec217a60b77863b056a2fcd2e08a100732597ce420d920a61b1d43f6edc233` |
| `workspace-error-no-connected-1920.png` | `4acd5f25b89efa2b25cddbd06644cf070ac2f3cd509b59753d77155dbb86fd69` |

草图对应：S1 为 `s1-workbench-*`（1280 详情折叠、1920 展开）；S2 为 `s2-compare-tray-*`（2/3 节点，上传步骤留 FE2c）；S3 Preview/History 顶栏为 `s3-header-upload-*` / `s3-header-history-*`，审核顶栏留 FE2c。普通页签正常场景拍了 `s3-workbench-normal-*`、`s4-grid-normal-main-*`、`s4-grid-normal-hover-*`、`s4-grid-normal-debug-*`。主表 1280 与悬停图哈希不同；e2e 移开鼠标并断言 tooltip 消失后拍主表，再重新悬停拍 hover。公式两组与 `s4-semantic-tokens-*` 已重拍。

无草图页面，单列交 owner 看图：`history-compare-running-*`、`manual-recovery-required-*`、`history-compare-connection-interrupted-*`、`navigation-fallback-*`、`workspace-error-no-connected-*`。错误页没有“已连接”。保留异常和边界截图：`bundle-error-*`、`loading-skeleton-*`、`dataset-replacement-browse-*`、`tab-overflow-*`。

草图核对：S1 树同层展示基线、工作区/提交挂在所属基线下，支持折叠、比较序号及状态圆点；排序限于同一父节点。S2 运行中锁定托盘；S3 Preview/History 顶栏齐全。尚未展示逐比较对的表数和变更表摘要，列为第 8 节偏差。没有像素比对。

## 7. 停止与 DC68 记录

### Owner 已处理的原停止项

owner 基于 FE2 kickoff §7.1、Q14（本地 main `7ac79ab53c` 已含）确认：继续由本执行者完成，不新开会话；依赖镜像继续使用 `gateway-backend-deps:lock-d054366c02fa`；只阻断核对 `uv.lock` 与 `.python-version`，pyproject / Cargo.lock 差异记录即可。脚本提交后从生成第一步重新开始。以下三项原始失败日志保留：

| 失败 | 证据 |
| --- | --- |
| 远程 Bash 编排在脚本体运行前语法错误 | `/home/dev/gdds-fe-logs/fe2b/dc68-generation-attempt-1-05.log`，SHA256 `f090bcd4ba3f50e8e6f238b9194ac0367ce0973848db41667b5487fc724a09d2` |
| 初始预检错误地要求 pyproject/Cargo.lock 全部镜像输入相同，生成器未调用 | `/home/dev/gdds-fe-logs/fe2b/fixture-generation-1-6569391-05.log`，SHA256 `a6cac49b7e7a02b12bbcd898c3d660be8e7fb6008cf5b0fd04f533a1ac42754c`；修正记录 `/home/dev/gdds-fe-logs/fe2b/dc68-generation-preflight-correction-05.log`，SHA256 `bb37c41d68b0b3dffe548db529413ea9d0d95e93944a25de8b35c98c97a68351` |
| 首次生成重试使用系统 `python3`，导入后端时缺少 FastAPI；发生在 `generate()` 前，无 fixture 写入 | `/home/dev/gdds-fe-logs/fe2b/fixture-generation-1-retry1-6569391-05.log`，SHA256 `0268c4f8f329278e66f05b9e54ce1a41e6c2113c78e8b52d850e2d580154e18d`；指定镜像 venv 的预检 `/home/dev/gdds-fe-logs/fe2b/generator-venv-preflight-05.log`，SHA256 `9806b2f73a0182bf360a990df85d266704b9702992a455204c26ea22ea2402b9` |

### 脚本提交后的重做与命令错误

脚本 commit 为 `d1da70c015dc74a9c82fbd923d974a3cf9415a7a`。之后重新从两个空输出目录运行并两次生成逐字节比较，成功日志见第 3 节。没有发生 `generate()` 内部失败。

- 脚本语法检查通过：`generator-script-syntax-d1da70c015-05.log`，SHA256 `6eb754eab5f17b4e0c586151f86982d4321764a858b58049d96e10a4f4ed4fc9`。
- 只读 fixture 检查首次因 CT05 无 `jq`、并误用包含 tar metadata 的 `cmp` 比较而失败；修正为 Perl `JSON::PP` 和 `diff -qr`，确认两份 S1 数据相同、13 个文件差异为空、诊断为空且 90 行 before/current，未改源码/worktree。记录 `/home/dev/gdds-fe-logs/fe2b/supplemental-inspection-failure-3736d21854.log`，SHA256 `5a6ec792c000c5fbc39948285fee3fd227928b0b5f8222942786cbd0d46109ee`。owner 后续允许节点安装 jq；本次无需安装。
- 一次只读镜像存在性查询使用错 tag `gateway-frontend-test:fe0`；校正为固定镜像 tag `mcr.microsoft.com/playwright:v1.64.1-noble`。日志 `/home/dev/gdds-fe-logs/fe2b/tool-error-image-tag-1970c355.log`，SHA256 `2da2982308fe6a26b44c036ed99312ac167006ccea1d2dfaadd97d9ae21e6b08`，未改变 Docker 状态。
- 一次 `rg` pattern 查询语法错误：`tool-error-rg-pattern-1970c355.log`，SHA256 `e94d23bf7d1a40ab5dd5aaf59d3c4e36b4d067449a59df6e90359987f8cbf45c`。
- 较早 R2 bundle 初次创建时使用了 bundle 不含的 ref 名；未产生有效 bundle/测试副作用。记录 `tool-error-r2-probe-bundle-45a84476.log`，SHA256 `8ca4e5f731a252e1b94d48efb07d23f020e93c7e611273340aa5e373381d8618`；用临时 ref 成功打包的 probe 随后完成。
- 本轮只读日志查询误用 CT05 未安装的 `rg`；改用 `grep -E` 后成功。失败与重试记录分别为 `/home/dev/gdds-fe-logs/fe2b/tool-error-remote-rg-missing-20261103.log` SHA256 `728830584469d6fef0036d58d7dc36e82075a2a79d051fa8ce67600803020d25`、`dc68-remote-grep-retry-20261103.log` SHA256 `10d8d91ea6420b7f8766e8d7424518c8303724c74ca5efa07dee1970c812bfc1`。
- R2 bundle transfer 的只读 fetch 先查了不存在的 `refs/heads/fe-vnext`，随后回退按显式 probe commit SHA fetch 并成功建立 clean worktree。记录在 follow-up DC68 log；bundle SHA 与成功 worktree log 见第 9 节。
- 一次本地 sha256sum 查询误把 CT05 runner log 当成本地文件，改为 SSH 在 CT05 读取。错误命令、无副作用范围、修正结果记录于 `/home/dev/gdds-fe-logs/fe2b/dc68-followup-inspection-errors-20261103.log`，SHA256 `8e194e8314fae10f1a8238f5987fa99e6e2d44a4e9aa7f2c580f1c3953ca0a64`。

上述新命令错误均为被测对象运行前后的只读证据查询、无产品/worktree 副作用，已修正并记录。无缓存缺失、镜像身份不符、测试节点不符或需要后端新增接口/字段的情况。最终代码候选完整 runner 成功；R2 负向 exit 1 为预期探针结果。

### 定向修复阶段的 DC68 记录

| 操作错误 | 记录与修正 |
| --- | --- |
| fixture archive 检查猜错 tar 路径 | `/home/dev/gdds-fe-logs/fe2b/dc68-fixture-tar-inspection.log`，SHA256 `a13d12f674b6f2d4eca978b0387d0b6db43da00156a35cda4d64d3672e7de9ed`。只读 `find` 找到实际 `generated/golden-bundle.tar` 后读取成功，没有访问被测运行。 |
| 在开发主机读取实际位于 CT05 的 runner log | `/home/dev/gdds-fe-logs/fe2b/dc68-local-run-log-query-error.log`，SHA256 `63a8990f07c0c2077556753046c3f3beebac08f71c8cf63498af25b9b65e6caa`。改用 SSH 在 `ct108-gw-dms-05` 读取，日志和 SHA256 核实成功。 |
| CT05 上使用未安装的 `rg` 查询 runner log | `/home/dev/gdds-fe-logs/fe2b/dc68-node-rg-query-error.log`，SHA256 `969d7bac2dd8c655b89976da92a35d8e12039f2e1b96a89c39c2623ffcd3a3c9`。改用已安装的 `grep -E`，成功读取运行时间、结果与日志摘要。 |
| OpenAPI schema 查询指向不存在的生成类型文件 | `/home/dev/gdds-fe-logs/fe2b/dc68-openapi-path-query-error.log`，SHA256 `6e0b48a9047fa51ed790b4f69c62be38f473b29da5d777ea2188d4abd9677374`。改查 canonical `frontend/openapi.json` 与 `WorkbenchPage.tsx`，确认 pair schema 仅有 `record_count`。 |
| handoff 文档编辑脚本的 DC68 段落锚点不匹配 | `/home/dev/gdds-fe-logs/fe2b/dc68-handoff-edit-anchor-error.log`，SHA256 `39e30cfeaf8a6ac39c3686d3f96cd8763f330176149d3d5894badb5680793b4a`。脚本在写文件前停止，无文档变化；改用段落前缀定位后成功。 |
| 最终候选首次 runner 的缓存来源提交参数写错 | 首次日志 `/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T154807Z.log` SHA256 `b44c13b82bb7f34be801ff10a0ed34fb96c458c17260395104e463d3a34baf21`，wrapper SHA256 `19e3696b40ae048a571fb6080146caa96a7c59084fa4095382dfdac9f9a68807`。无产品副作用；修正为缓存来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`，从完整 runner 起点重跑并通过；有效证据见第 5 节。 |

上述均为无副作用的只读取证或测试参数元数据错误，保留日志及摘要并按 DC68 修正；更正后的查询/完整运行成功。没有缓存缺失、镜像身份不符、测试节点不符或生成器 `generate()` 内失败。

### 04 退出取证期间的 DC68 记录

| 操作错误 | 记录与修正 |
| --- | --- |
| 开发主机用原始 commit SHA 创建 bundle 被 Git 拒绝为空 bundle ref | 开发主机日志 `/home/dev/gdds-fe-logs/fe2b/dc68-fe04-bundle-by-sha-error.log`，SHA256 `921358ae34a0dc42efbca3f063fd74e30c4bad574b7af97af1c03e21b39662bd`。未创建 worktree、未运行测试；改用命名 ref `refs/heads/fe-vnext` 创建 bundle，校验后继续。 |
| CT04 在仓库外运行 `git bundle verify` | CT04 日志 `/home/dev/gdds-fe-logs/fe2b/dc68-04-bundle-verify-context-error.log`，SHA256 `39555f3baf05719da054cc3a3656b101c3f7cb453b7cd8f542cb9eaf1abc91c1`。Git 要求在仓库上下文校验；`set -e` 使 fetch 与 worktree 添加未执行。改在共享仓库上下文校验后，fetch 与 clean detached worktree 创建成功。 |
| handoff 更新脚本的清理清单锚点不匹配 | 开发主机日志 `/home/dev/gdds-fe-logs/fe2b/dc68-handoff-cleanup-anchor-error.log`，SHA256 `6c9d7250be87ebd397614a4969fd566413e1d9e2d2aa58bbcc148b5256636893`。脚本在写文件前停止；改为追加清单小节后成功。 |

以上均为无副作用的 bundle 参数、命令上下文或文档编辑错误；保留日志和 SHA256，并按 DC68 修正一次。CT04 权威入口唯一一次运行 exit 0。

## 8. 已知差异与待处理事项

以下两项按复审报告 §4 交 owner 看图并决定：

1. **History 比较抽屉缺少各比较对摘要。** 草图 `compare-1920` 展示每对的表数、变更表数、降级表数，以及逐表的增删改计数；当前抽屉显示节点、`节点 i → 节点 i+1` 和差异记录数。现有 response schema 只有 `record_count`，摘要可在后续从已下载 bundle 解析。请 owner 决定接受现状或要求 FE2c 补齐。
2. **M10：** S1 fixture 含一张 `composite_signal_point` 0→0 行快照表，出现在“其他表”组。它由后端生成器固定生成；请 owner 确认接受该表现。

B1–B9 已修复；M1–M9、M11 已修复并在第 2 节列证据。Q14 的 `pyproject.toml` 与 `Cargo.lock` 差异由 owner 决议接受，见第 3 节。没有需要后端新增字段/接口（FD3）的事项，也没有发现其他 FE2b 范围外设计问题。04 权威 runner 与截图已完成；复审会话核对证据后，退出 tag 由设计会话创建。

## 9. 本阶段 worktree 与传输文件清单（供退出后清理）

除当前开发 worktree `/home/dev/gdds-fe` 与共享 backend repo `/home/dev/gateway-data-management-system` 外，本阶段在 CT05 创建的 clean detached worktree：

`/home/dev/gdds-fe-fe2b-6569391-05`、`/home/dev/gdds-fe-fe2b-d1da70c015-05`、`/home/dev/gdds-fe-fe2b-32fa827-05`、`/home/dev/gdds-fe-fe2b-57d5203-05`、`/home/dev/gdds-fe-fe2b-6e6c2d12bc-05`、`/home/dev/gdds-fe-fe2b-3736d218-05`、`/home/dev/gdds-fe-fe2b-1970c355-05`、`/home/dev/gdds-fe-fe2b-5d7d7d52-05`、`/home/dev/gdds-fe-fe2b-e9e8a4bf-05`、`/home/dev/gdds-fe-fe2b-84a7dc22-05`、`/home/dev/gdds-fe-fe2b-e8afa41c-05`、`/home/dev/gdds-fe-fe2b-005aabe5-05`、`/home/dev/gdds-fe-fe2b-83d0962a-05`、`/home/dev/gdds-fe-fe2b-e3b147f6-05`、`/home/dev/gdds-fe-fe2b-911016f7-05`、`/home/dev/gdds-fe-fe2b-d3ef4105-05`、`/home/dev/gdds-fe-fe2b-78c06533-05`、`/home/dev/gdds-fe-fe2b-5ac704c6-05`、`/home/dev/gdds-fe-fe2b-r2-negative-probe-45a84476-05`、`/home/dev/gdds-fe-fe2b-r2-negative-probe-5ac704c6-05`。每个 FE2b linked worktree 都有指向 `/home/dev/gateway-data-management-system/legacy` 的本地 symlink。R2 临时源码 worktree：`/home/dev/gdds-fe-r2-negative-probe-source`、`/home/dev/gdds-fe-r2-negative-probe-source-5ac704c6`。

传输 bundle 留在两端的 `/home/dev/gdds-fe-logs/fe2b/`；对应 worktree 同短 SHA：`fe2b-candidate-6569391.bundle`、`fe2b-candidate-d1da70c015.bundle`、`fe2b-candidate-32fa827.bundle`、`fe2b-candidate-57d5203.bundle`、`fe2b-candidate-6e6c2d12bc.bundle`、`fe2b-3736d218.bundle`、`fe2b-1970c355.bundle`、`fe2b-5d7d7d52.bundle`、`fe2b-e9e8a4bf.bundle`、`fe2b-84a7dc22.bundle`、`fe2b-e8afa41c.bundle`、`fe2b-005aabe5.bundle`、`fe2b-83d0962a.bundle`、`fe2b-e3b147f6.bundle`、`fe2b-911016f7.bundle`、`fe2b-d3ef4105.bundle`、`fe2b-78c06533.bundle`、`fe2b-5ac704c6.bundle`、`r2-negative-probe-45a84476.bundle`、`r2-negative-probe-5ac704c6.bundle`。

本轮最新源码 bundle SHA256 `444ff4994e45a5fc515342ed9e4bb03327e44e6a17cfaf3af6c82bcb77d39e0c`；传输与 worktree 建立日志 `/home/dev/gdds-fe-logs/fe2b/bundle-transfer-worktree-5ac704c6-05.log` SHA256 `5c8b0120fa750d310ddd1e9cd417ee3b01c84b2589008a5e67c5dc8cb02d9ac3`。最新 R2 临时 probe bundle SHA256 `7260cdab7a2788e958531d31dbbdd91f609726f9b8a63f2693391cd2a8a06e21`；其 worktree 建立日志 `/home/dev/gdds-fe-logs/fe2b/bundle-transfer-worktree-r2-negative-5ac704c6-05.log` SHA256 `aaed8e31887ea1c4975cd07505f0b713459ffa9e49b8b70c446cf5c259a71063`。

本次定向修复新增 CT05 clean detached worktree：`/home/dev/gdds-fe-fe2b-5d174967-05`、`/home/dev/gdds-fe-fe2b-probe-b1-5d174967-05`、`/home/dev/gdds-fe-fe2b-probe-b3-5d174967-05`、`/home/dev/gdds-fe-fe2b-probe-b5-5d174967-05`；均有指向 `/home/dev/gateway-data-management-system/legacy` 的本地链接。开发仓库临时源码 worktree/分支：`/home/dev/gdds-fe-fe2b-probe-b1-src-5d174967` (`fe2b-probe-b1-5d174967`)、`/home/dev/gdds-fe-fe2b-probe-b3-src-5d174967` (`fe2b-probe-b3-5d174967`)、`/home/dev/gdds-fe-fe2b-probe-b5-src-5d174967` (`fe2b-probe-b5-5d174967`)。

本次源码与探针传输 bundle 位于两端 `/home/dev/gdds-fe-logs/fe2b/`：`fe2b-targeted-fix-5d174967.bundle` SHA256 `675835d75a66f3daa2fc5552fc1384bb72866718dc676b5498bbf3a904c9eb96`；`probe-b1-5d174967.bundle` SHA256 `5b9e95a8e9566a0ae3c102ca045c60728bb0a75093c70763e2bd7b2e29f23064`；`probe-b3-5d174967.bundle` SHA256 `1aa79fbe07991752d129a4dce7e3e68a50a2ed8f8bc6f966051a0e88a4d20bd0`；`probe-b5-5d174967.bundle` SHA256 `64eb23bc9efa04851d7be5dbfbbd40ac7f9d7c71683337d6ac6359fbbe1d4e72`。探针 runner 日志、wrapper 日志、最终运行日志和截图清单见第 5、6、7 节。

生成输出目录、测试日志与截图目录均位于 worktree 外，见第 3、5、6 节。审核/复审及 04 阶段取证完成前保留；退出清理时再删除本节列出的临时 worktree、bundle 和生成输出.

### CT04 退出取证 worktree 与文件

- CT04 clean detached worktree：`/home/dev/gdds-fe-fe2b-5d174967-04`；位于共享仓库 `/home/dev/gateway-data-management-system`，legacy 链接已创建。退出清理时同时删除共享仓库临时 fetch ref `refs/codex/fe2b-exit-evidence-7682297b`。
- 开发主机 bundle `fe2b-exit-5d174967-branch.bundle` 与 CT04 bundle `/home/dev/gdds-fe-logs/fe2b/fe2b-exit-5d174967.bundle` SHA256 均为 `46ebd6a79f25129a362603f932a40b9fe1e259fdc7857d8f34b5766b2406f78b`。传输及 clean worktree 记录 `/home/dev/gdds-fe-logs/fe2b/worktree-transfer-fe2b-exit-04-5d174967.log`（CT04），SHA256 `2744bbf6811988f35d1156568cb8063420079db7294af0ac7fc6a885fd3a42cb`。
- 本节列出的 worktree、临时 ref、bundle、日志与截图均在审核会话核对完成及 FE2b 退出后再清理。

## 10. FE2c 带入事项（复审报告 §3）

- **N2（等待时长）：**当前由 `started_at` 计算；模拟时间固定为 `2026-11-03T09:00:01Z`，所以截图秒数随拍摄时间变化，长时间直接显示秒数也难读。FE2c 建议超过一分钟改为时/分/秒，并在 e2e 用 Playwright `page.clock` 固定时间或生成相对测试时间的模拟时间。
- **N3（构建模块清单）：**生产检查使用的 `dist/.vite/rollup-modules.json` 会随构建产物发布且包含源码路径。FE2c 将其移到 `dist` 之外，或检查完成后删除。
- **N4（测试超时配置）：**`window.__gatewayTestConfig` 在生产构建也生效，可由页面脚本缩短请求超时。FE2c 将其限制为开发构建读取，或改由模拟会话注入。
