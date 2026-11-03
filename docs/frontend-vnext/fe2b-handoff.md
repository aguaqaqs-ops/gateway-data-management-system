# FE2b handoff — 工作台、路由与历史比较

**状态：FE2b 实现及 CT05 调试证据完成，待审核与复审。** 本文替代此前的停止报告。未在 CT04 取证，未创建 `fe-fe2b-exit` tag，未推送。

## 候选与审核范围

- 分支：`fe-vnext`
- 上一阶段 tag：`fe-fe2a-exit`，提交 `e301cc0f88427b390bbeef009e2b2f7058bddc0a`
- FE2b 源码候选：`5ac704c6038fc3078cc70117b7e8d2c7443c22d1`，frontend tree `7ba49223ea9cbc69a34eb2c6a8ccb3418c3361b5`
- 源码审核范围：`fe-fe2a-exit..5ac704c6038fc3078cc70117b7e8d2c7443c22d1`
- handoff 作为单独文档提交紧接源码候选之后；最终审核 HEAD 为该文档提交。文档提交不改变 `frontend/`，05 权威运行绑定到上述源码候选。
- 代码候选完整运行日志：`/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T144106Z.log`，SHA256 `f04ec8f1749ef2bd53ed3a558bc8174b9ca23999e55f02471b5f0ab1f4b4cc59`
- 完整证据截图：`/home/dev/gdds-fe-evidence/fe2b/5ac704c6-05/`

## 1. 范围完成情况

| 要求 | 状态与证据 |
| --- | --- |
| §6.3 N1、N2、R2、R5、R7、S1、S2（甲） | 完成。S2 仅有验收截图，没有演示截图。各项对应测试和探针见第 2、5 节。 |
| 模拟会话与身份 | 完成。开发环境提供提交人、审核人、归档确认人、无权限身份；请求带当前身份 token。`check:production-build` 正向和负向探针分别通过及按预期失败。 |
| 工作台组态树与 History | 完成。工作区经 `POST /v1/workspaces` CreateOrGet，参数取当前会话 `business_project_id` 和 `gateway_device_external_key`，不发送 `Idempotency-Key`；客户端接受 201/200。History 从 `GET /v1/history` 以 `limit/cursor` 分页获取。没有工作区列表接口。 |
| 当前会话操作与基线状态 | 完成。“进行中的操作”限定为本会话发起并以 URL `operationId` 标识的操作；基线状态按 History `eligibility_note` 展示。 |
| 正式工作台布局 | 完成。四列、搜索、排序、调宽；详情面板 400px，≤1440px 默认折叠，1920px 默认展开；状态短标签和长原因折叠。未实现 Q4“历史初始备份”。 |
| 上下文工具栏 | 完成。视图模型列出全部操作、启用条件和禁用原因并有单测。FE2c 写操作没有在 e2e 中点击；History 比较属于本阶段并有完整 e2e。 |
| 比较托盘与结果抽屉 | 完成。History 比较最多选择 3 个节点，POST 首次 202、同 key 回放 200；轮询完成后下载 bundle 并可打开 History 差异浏览。新增 e2e 已验证 bundle GET 和打开差异页。 |
| Preview、History、审核三种入口 | 完成。Preview 使用工作区 `current_preview_result_id`；History 使用比较托盘；待审提交由“基线节点 → 提交”进入只读审核，读取 `GET /v1/submissions/{submission_id}/review`。审核写操作留给 FE2c。 |
| URL 路由 | 完成。工作台与差异浏览可从 URL 直达，节点、比较、模式和 operation id 保留；`request`、`previewRequest`、`reviewRequest`、`historyRequest` 不再作为参数。 |
| FE2c 边界 | 上传步骤卡在 FE2c；审核/提交/归档写操作未接入点击流程；没有审核顶栏；不提供初始备份入口。 |

## 2. 带入项完成标准

| 带入项 | 完成情况与验证 |
| --- | --- |
| N1 幂等意图 | `frontend/src/features/api/idempotency.test.ts`：`reuses a key for retrying one intent and creates a new key for another`。e2e `History 比较超时重试复用同一幂等键，刷新后按 URL 中 operation_id 续查` 让第一次 POST 在客户端超时，重试沿用 key；模拟接口按 key 返回首次响应，记录 202 后 200。相同意图复用 key，新意图创建新 key。 |
| N2 轮询 | `frontend/src/features/api/polling.test.ts`：状态请求超时仍为运行中；网络、5xx、429 有上限退避后转为连接中断；History 比较限于 QUEUED、RUNNING、SUCCEEDED、FAILED、CANCELLED。e2e 覆盖运行中、连接中断、URL operation id 刷新续查。 |
| MANUAL_RECOVERY_REQUIRED | `polling.test.ts` 覆盖 MANUAL_RECOVERY_REQUIRED → RUNNING → SUCCEEDED 及 MANUAL_RECOVERY_REQUIRED → FAILED；进入该状态后轮询间隔为 30 秒。e2e 核对“需要管理员处理”、显示并复制 operation id、不显示重试按钮，并通过“刷新状态”观察状态变化。该状态不是终态；终态仅 SUCCEEDED、FAILED、CANCELLED、SUPERSEDED。 |
| R2 生产构建 | 正向：候选完整 runner 输出 `production dist contains no simulated API or identity selection code`。负向：临时 probe commit `9afa58ba39a8c5dec3146f8c8efec27a2ab678bf` 在 `App.tsx` 静态导入模拟接口模块，生产构建探针以 exit 1 检出 `index-DgeDlAPd.js: /simulated[-_ ]api/i`。probe 不在 `fe-vnext` 分支。日志见第 5 节。 |
| R5 连接状态 | `frontend/src/features/api/connection-status.test.ts`：已连接、连接中断、首次请求前不显示均有单测；error page 隐藏已连接状态。e2e `所选模拟身份携带对应 token；无权限错误页不显示已连接` 检查错误页中“已连接”数为 0。 |
| R7 公式 | `frontend/src/features/view-model/formula-view.test.ts` 恢复一元减号前缀断言（表达式行以 `- 线路保护装置 A:线路电流` 开始）；重拍 `formula-preview` 与 `formula-history` 两个视口。 |
| S1 正常业务场景 | `preview-workbench-normal` 是一个转发通道的遥测表，前后各 90 行，新增/删除/修改各 6 行；正常导航；导航和表诊断均为空。`backend-fixture.test.ts` 的 `matches the backend summary for the normal transfer-channel telemetry browse` 对照后端摘要，e2e 普通页签打开主表并拍 S3/S4 主表、悬停、Debug。产出风险：view `MEDIUM_HIGH`；annotation `MEDIUM_HIGH`、`MEDIUM_LOW`。 |
| S2（甲） | 比较托盘部分截图展示 2/3 个节点；上传步骤仍留在 FE2c。没有演示截图。 |

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

成功生成日志：`/home/dev/gdds-fe-logs/fe2b/backend-fixtures-3736d21854-20261103T135340Z-822046.log`，SHA256 `617bac0537e5240bb4de58f572045efac4a3cc9effb589b2be88988c36291917`。节点 `gw-dms-test-05.lan`，2026-11-03 13:53:40Z 至 13:54:07Z，HEAD `3736d218545947ec7dc3e380d49c5ecbfc3d96fc`，exit 0。两次各 226 个文件，目录树 SHA256 都为 `5aaf509380e5efb52ef4d7103da1fbdf0c9483720c4666a676d46b7c2b2b9a9a`，`byte_identical=true`。`generate()` 两次成功，没有遇到生产代码无法生成场景的情况。

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

### 最终候选完整运行

- 节点：`ct108-gw-dms-05`，hostname `gw-dms-test-05.lan`
- clean detached worktree：`/home/dev/gdds-fe-fe2b-5ac704c6-05`，HEAD `5ac704c6038fc3078cc70117b7e8d2c7443c22d1`，frontend tree `7ba49223ea9cbc69a34eb2c6a8ccb3418c3361b5`
- 运行时间：2026-11-03 14:41:06Z 至 14:41:39Z；exit 0；worktree 起止 HEAD/tree 一致。
- 权威入口：`frontend/scripts/run-tests.sh --screenshots /home/dev/gdds-fe-evidence/fe2b/5ac704c6-05`
- 完整入口日志：`/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T144106Z.log`，SHA256 `f04ec8f1749ef2bd53ed3a558bc8174b9ca23999e55f02471b5f0ab1f4b4cc59`
- wrapper 日志：`/home/dev/gdds-fe-logs/fe2b/full-runner-5ac704c6-05-wrapper.log`，SHA256 `912f971174c6bb16b48980affa88e5e582647f40172e5309e15edf9fa6a7da71`
- 结果：typecheck、lint、22 个单测文件/99 tests、生产 build、正向 R2 检查通过；11/11 模拟接口 e2e 通过。History e2e 验证首次超时/同 key 回放、operation id 刷新续查、状态运行时的结果抽屉、bundle GET、点击打开 History 差异浏览。
- npm 缓存：`/home/dev/gdds-fe-cache/fe0/npm-cache`；来源归档 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`；来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`；package-lock 解析项 305 个。使用预填缓存，未用代理。
- 工具链镜像：`mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；RootFS DiffID：
  `sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`,
  `sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`,
  `sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`,
  `sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`,
  `sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`,
  `sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`,
  `sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`。

### R2 负向生产构建探针

- 临时探针 commit：`9afa58ba39a8c5dec3146f8c8efec27a2ab678bf`，父提交为最终源码候选 `5ac704c6038fc3078cc70117b7e8d2c7443c22d1`；仅在临时 detached worktree 的 `frontend/src/App.tsx` 加静态 import `./features/dev/simulated-api`。
- CT05 worktree：`/home/dev/gdds-fe-fe2b-r2-negative-probe-5ac704c6-05`，frontend tree `81043903c56b2d14c8ad099940de299ce3731fa9`，clean detached。
- 生产检查按预期 exit 1，错误定位到 `index-DgeDlAPd.js: /simulated[-_ ]api/i`。类型检查、lint、单测和 build 均在探针失败前通过。
- 运行日志：`/home/dev/gdds-fe-logs/fe2b/frontend-tests-20261103T144315Z.log`，SHA256 `a08974d381f2ff6a6198e697d20b72a13e83b3d07ac87aff546d169292cec8d6`；wrapper `/home/dev/gdds-fe-logs/fe2b/r2-negative-probe-5ac704c6-05-wrapper.log`，SHA256 `594401b35946476c30a00a5d468b2bc0c286bb63e63b452ba961806dfc77394b`。该 exit 1 是负向探针预期结果。

### 调试阶段失败与修正提交

所有测试失败均发生在 CT05 的 clean detached worktree，保留原始日志和 SHA；最终候选完整 runner exit 0。下表列出失败点与后续修正提交。

| 候选 | 失败 | 日志 SHA256 | 后续修正 |
| --- | --- | --- | --- |
| `32fa827` | typecheck | `8e6eebff6c41e6f071f43565d8d288e21ef813e00aea3d7c248a62d47de25f9e` | `57d5203` 类型修正 |
| `57d5203` | lint | `adca30f018f20b4aae962ae56c79dac00d244ac401afa8350257534b1d58362f` | `6e6c2d1` lint 修正 |
| `6e6c2d1` | 单测 91/98 | `6bdb1091b333db1d79ef377b02c1b7e10c81f036ffb2b7c3a88a90d4134ebf97` | `1970c355` fixture/模拟数据更新，随后继续补足场景 |
| `1970c355` | 单测 2 项 | `466c975ad2f161506d80c8a913ad0d4d24db2ba75869cc5bea6d6da65e6318d3` | `5d7d7d5` 及其后 fixture 修正 |
| `5d7d7d5` | e2e collection：Node 环境 `import.meta.env` 未定义 | `9d204ccb2ed4108f511faced9bef4713bf2d23d7eff9295b76b8dcda9e29338c` | `e9e8a4b` 测试环境修正 |
| `e9e8a4b` | e2e 8/11：搜索期待、人工恢复文案、侧栏语义 | `1a43b0ba000b7e7c31cf59049654670045c7eb2653dbd97351d670963e3dff2b` | `84a7dc2` |
| `84a7dc2` | e2e 9/11：精确标题/选择器 | `eb25dee894dc2c82777aca93426091c4523fcfcc96f0395d06b6143126567b14` | `e8afa41` |
| `e8afa41` | e2e 10/11：悬停选错列 | `c32e6dd3ae1440ae738eb19ebbe736927a06e084de074bb63e404c59cf560c6b` | `005aabe5` |
| `005aabe5` | e2e 10/11：悬停 tooltip 未触发 | `4a687d10a7afaf2ffcde4b617a260dd69161cf6ee0e715414c8d241fd27c1ebd` | `83d0962a` |
| `83d0962a` | e2e 10/11：整表位置无效导致 changed-cell 扫描找不到 tooltip | `914282448941eed786730addcafdc519fa6dde340e561ac84bd3f7537cdc7650` | `e3b147f6`、`911016f7` |
| `e3b147f6` | 单测发现标准/ordered 记录重复与无公开 compare key 时的定位问题 | `5e6df9139223a5643f9ce48428f13727955fc8b1a35dc864eb9e575454ef58ff` | `911016f7` 改为无显式 key 时使用 ordered positional records |

`911016f7`、`d3ef4105` 和 `78c06533` 的完整 runner 均通过；之后分别增加跨实现摘要核对、调整 1280 截图先后顺序。最终在 `5ac704c6` 对全部新断言与截图重新运行完整入口并通过。对应通过日志分别为 `frontend-tests-20261103T142240Z.log` SHA256 `65464df2519a0a058c5ae37440d7d463b3027e5edd9882963eb4dcfc13e3c37a`、`frontend-tests-20261103T142441Z.log` SHA256 `9346c23e3b5d336c004a4f64691e2ae83497227d40e94ddca66ec4ef33f15c5e`、`frontend-tests-20261103T142843Z.log` SHA256 `5ac53ea6efc96560acd8a16bc7c2c80aa9525924bf8d08fb4fd7ec921d8e1aba`。

## 6. 截图清单与视觉偏差

截图目录：`/home/dev/gdds-fe-evidence/fe2b/5ac704c6-05/`。共 50 张。SHA256 清单文件：`/home/dev/gdds-fe-logs/fe2b/screenshot-sha256-5ac704c6-05.txt`，SHA256 `1261b0dc99bfaa5aefa7d760afa364cdbe44c9530cc218e8f4d16f685cbca7d4`。已人工对照草图检查布局、层级、语义色、禁用原因和焦点呈现；未做像素比对。

| 文件 | SHA256 |
| --- | --- |
| `bundle-error-1280.png` | `e91644ff3ad84b2a878c7e1517cc9f7835877a95d817852b03c940e6f766f564` |
| `bundle-error-1920.png` | `fb5c3dd88c95655ddc89f0ca0b1a1a4e6d0a3158a70cd760c74caef1f592430f` |
| `dataset-replacement-browse-1280.png` | `cc78cb9509090b9fa570ea5a04b7b049c63d29e897c370e0117841631e4e9c4e` |
| `dataset-replacement-browse-1920.png` | `6c2c94f4f69e0d22ef0276714eee54ec69fb735889c9ab0a810836d59d4e5465` |
| `formula-history-1280.png` | `6477d79e18d9d9eb6e2b03f54e1da3b91d68b20081b0bfc774f7b61b529ecb80` |
| `formula-history-1920.png` | `09c127358d8b9e268101f9d1f0579bc22fb0c7c59bf1fecee818eda4fc1c6825` |
| `formula-preview-1280.png` | `56d218ab3df1dbf21300323acfb91f0e3683ef20410a1818d5a668874358d959` |
| `formula-preview-1920.png` | `5dac6bf104ab0b723eef7071919bc0894ac4335cc9b958d9027e5f86fa14f77f` |
| `history-compare-connection-interrupted-1280.png` | `d97092d382775d1bcee4b1eea74247c41e108f79d9ea09e54743c21a2e1712b9` |
| `history-compare-connection-interrupted-1920.png` | `c57103d104aaa8a2b0c0f84d15590d185f52cba6d37b0214fd2799d258e3327b` |
| `history-compare-result-drawer-1280.png` | `c8f9ce8b665140172fcddbea192a831119a30542bc8a2bebbd82cfe3baf33178` |
| `history-compare-result-drawer-1920.png` | `0230bf9c3d866e6f899ff151f80ab2893a192afa7a7e58fdf65e2771bf5a3877` |
| `history-compare-running-1280.png` | `22ae554b785c180108b74076f56100cc94f9f630953d519605bd19718fe0c7c0` |
| `history-compare-running-1920.png` | `9efea8cfc491e561679e9785ec9ff1b83408c62c0f70c2f45bce75d5dce847ea` |
| `loading-skeleton-1280.png` | `1a09a7bb84166539b7f4e58673a61be0e658b8937e04da7253750e946108b83c` |
| `loading-skeleton-1920.png` | `4a401678b2edd8331ddc279078aaa44b609a7ff3c9dcd3f839f99207708179a0` |
| `manual-recovery-required-1280.png` | `65cea88f65023b71ecbe341aefcca6f89ed12a0d7b0b435b6e3d1921f3a2985f` |
| `manual-recovery-required-1920.png` | `9480dfcab83e6e863652c792a2a8714aa6e9bc4a5804014dce96b20ebb58cd27` |
| `navigation-fallback-1280.png` | `a84ba53eafa2c86726b5df494cbbac7f778b7255631c8c0204efe54184df9a72` |
| `navigation-fallback-1920.png` | `e6da1ad3759e2458c5dd11ad7f6f290d44eff353ad9bae5c46f0844e7ebdf848` |
| `s1-workbench-1280.png` | `7d7fb7d5299b9d8df3e77cadb16e1d3623435d81b279fc610d1fa355c892b7a8` |
| `s1-workbench-1920.png` | `b777e9fa5b93c662292259d67de2534165f6a853bcbec987e8be73f4b5dae41b` |
| `s2-compare-tray-1280.png` | `2db4f9fc9d8f9c3f34dcd35151ab4cdbd05f496f37c4c5ef5171ee356acee3af` |
| `s2-compare-tray-1920.png` | `4d3586b6b56725aec044b8ea4e1d94f115c52f94958ec46e6031783baf86299b` |
| `s3-header-history-1280.png` | `22ef7766e9f1e6fa8b45c460622f1867ebd2649edea977bd4040d3ae741b4b6f` |
| `s3-header-history-1920.png` | `14dcc76039dd7edbf8b603c4dc09812c21163e2721869c057c978ebf81cde847` |
| `s3-header-upload-1280.png` | `ff82e1426d90c4c5e39864fe9628c9675bbe3e77a8d669f13701268edff622d4` |
| `s3-header-upload-1920.png` | `a46f7e9a6859ed3ef29fa68dee2fb1a86668fda53184c8e38c3f3c00b769eb97` |
| `s3-workbench-normal-1280.png` | `722414b84f5089351f254fc1179521f2f3e77096d324ac7eb66dd490254df2e0` |
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
| `s4-grid-normal-main-1280.png` | `722414b84f5089351f254fc1179521f2f3e77096d324ac7eb66dd490254df2e0` |
| `s4-grid-normal-main-1920.png` | `78511e8edbb57b51c54b6c3cde3e3b6a53b746084edb38c3f4b5f490b6304685` |
| `s4-semantic-tokens-1280.png` | `116f9cbb8991ace7deef04e4f5029a211ff933c38aee5e3348f5cba63bcd8b2c` |
| `s4-semantic-tokens-1920.png` | `15fe88e318ed59410b184631888681262349d9220dda26a5f49ac6f12c16dcba` |
| `tab-overflow-1280.png` | `f89e42e99af51028d3cc69eff3212e06ef88f89912d93b7387b5fb44892dab87` |
| `tab-overflow-1920.png` | `f33c88bacfcc4cf0842cc5fe8ea7ce11ec6a9e401e4d30e80b48bd1e447e2ca1` |
| `workspace-error-no-connected-1280.png` | `a61f2f31d097a82815811bd5a2bb4130736548d661a48a5e7a1a6df0ca843307` |
| `workspace-error-no-connected-1920.png` | `5a6d0b614fb801b6b475d5e3f9942a33ab3287e39a42a36f3286513523f7b97d` |

草图对应：S1 为 `s1-workbench-*`（1280 折叠、1920 展开）；S2 为 `s2-compare-tray-*`（2/3 节点，上传流程仍在 FE2c）；S3 Preview/History 顶栏分别为 `s3-header-upload-*` / `s3-header-history-*`，审核顶栏留在 FE2c。正常业务场景使用普通页签拍 `s3-workbench-normal-*`、`s4-grid-normal-main-*`、`s4-grid-normal-hover-*`、`s4-grid-normal-debug-*`。`formula-preview-*`、`formula-history-*` 与 `s4-semantic-tokens-*` 已重拍。

无草图页面，单列交 owner 看图：`history-compare-running-*`、`manual-recovery-required-*`、`history-compare-connection-interrupted-*`、`navigation-fallback-*`、`workspace-error-no-connected-*`。错误页截图没有“已连接”。现有边界截图继续保留：`bundle-error-*`、`loading-skeleton-*`、`dataset-replacement-browse-*`、`tab-overflow-*`。

草图与后端事实没有发现需要改 Contract 或后端字段/接口的冲突。视觉差异：无需升级 owner 决策的偏差。审核期间请 owner 对照草图复核上述成组证据。

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

## 8. 已知差异与待处理事项

- Q14 的 pyproject.toml 与 Cargo.lock 差异如第 3 节记录，已由 owner 决议接受；无待 owner 决定项。
- 没有发现需要后端新增字段/接口（FD3）的事项，也没有 FE2b 范围外的设计问题。
- Review/re-review 前不运行 CT04；审核通过后，按阶段流程在最终 handoff HEAD 的 04 clean detached worktree 运行一次权威入口并完成全套截图取证。tag 由设计会话创建。

## 9. 本阶段 worktree 与传输文件清单（供退出后清理）

除当前开发 worktree `/home/dev/gdds-fe` 与共享 backend repo `/home/dev/gateway-data-management-system` 外，本阶段在 CT05 创建的 clean detached worktree：

`/home/dev/gdds-fe-fe2b-6569391-05`、`/home/dev/gdds-fe-fe2b-d1da70c015-05`、`/home/dev/gdds-fe-fe2b-32fa827-05`、`/home/dev/gdds-fe-fe2b-57d5203-05`、`/home/dev/gdds-fe-fe2b-6e6c2d12bc-05`、`/home/dev/gdds-fe-fe2b-3736d218-05`、`/home/dev/gdds-fe-fe2b-1970c355-05`、`/home/dev/gdds-fe-fe2b-5d7d7d52-05`、`/home/dev/gdds-fe-fe2b-e9e8a4bf-05`、`/home/dev/gdds-fe-fe2b-84a7dc22-05`、`/home/dev/gdds-fe-fe2b-e8afa41c-05`、`/home/dev/gdds-fe-fe2b-005aabe5-05`、`/home/dev/gdds-fe-fe2b-83d0962a-05`、`/home/dev/gdds-fe-fe2b-e3b147f6-05`、`/home/dev/gdds-fe-fe2b-911016f7-05`、`/home/dev/gdds-fe-fe2b-d3ef4105-05`、`/home/dev/gdds-fe-fe2b-78c06533-05`、`/home/dev/gdds-fe-fe2b-5ac704c6-05`、`/home/dev/gdds-fe-fe2b-r2-negative-probe-45a84476-05`、`/home/dev/gdds-fe-fe2b-r2-negative-probe-5ac704c6-05`。每个 FE2b linked worktree 都有指向 `/home/dev/gateway-data-management-system/legacy` 的本地 symlink。R2 临时源码 worktree：`/home/dev/gdds-fe-r2-negative-probe-source`、`/home/dev/gdds-fe-r2-negative-probe-source-5ac704c6`。

传输 bundle 留在两端的 `/home/dev/gdds-fe-logs/fe2b/`；对应 worktree 同短 SHA：`fe2b-candidate-6569391.bundle`、`fe2b-candidate-d1da70c015.bundle`、`fe2b-candidate-32fa827.bundle`、`fe2b-candidate-57d5203.bundle`、`fe2b-candidate-6e6c2d12bc.bundle`、`fe2b-3736d218.bundle`、`fe2b-1970c355.bundle`、`fe2b-5d7d7d52.bundle`、`fe2b-e9e8a4bf.bundle`、`fe2b-84a7dc22.bundle`、`fe2b-e8afa41c.bundle`、`fe2b-005aabe5.bundle`、`fe2b-83d0962a.bundle`、`fe2b-e3b147f6.bundle`、`fe2b-911016f7.bundle`、`fe2b-d3ef4105.bundle`、`fe2b-78c06533.bundle`、`fe2b-5ac704c6.bundle`、`r2-negative-probe-45a84476.bundle`、`r2-negative-probe-5ac704c6.bundle`。

本轮最新源码 bundle SHA256 `444ff4994e45a5fc515342ed9e4bb03327e44e6a17cfaf3af6c82bcb77d39e0c`；传输与 worktree 建立日志 `/home/dev/gdds-fe-logs/fe2b/bundle-transfer-worktree-5ac704c6-05.log` SHA256 `5c8b0120fa750d310ddd1e9cd417ee3b01c84b2589008a5e67c5dc8cb02d9ac3`。最新 R2 临时 probe bundle SHA256 `7260cdab7a2788e958531d31dbbdd91f609726f9b8a63f2693391cd2a8a06e21`；其 worktree 建立日志 `/home/dev/gdds-fe-logs/fe2b/bundle-transfer-worktree-r2-negative-5ac704c6-05.log` SHA256 `aaed8e31887ea1c4975cd07505f0b713459ffa9e49b8b70c446cf5c259a71063`。

生成输出目录、测试日志与截图目录均位于 worktree 外，见第 3、5、6 节。审核/复审及 04 阶段取证完成前保留；退出清理时再删除本节列出的临时 worktree、bundle 和生成输出。
