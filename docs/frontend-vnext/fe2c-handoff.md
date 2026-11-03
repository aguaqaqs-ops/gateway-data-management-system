# FE2c handoff — 写操作旅程

## 候选与审核范围

- 分支 `fe-vnext`，FE2c 代码候选 `a2bcaf866a678eb02a15d58a8388759572b76299`（frontend tree `4ce344205cd6dceadb4e3334b1757a0b6af633f6`），父提交 `84c3d91a1a`（FE2b exit 后 main 文档合并）。handoff 文档提交在本文件落库后生成；`fe-fe2c-exit` 指向该 handoff 提交。
- 审核范围 `fe-fe2b-exit..<FE2c handoff 提交>`；代码候选仍为 `a2bcaf866a`。`31f4310ff8`（`fe-fe2b-exit` 指向的 handoff 提交）是候选的祖先。
- 本阶段未改写既有提交、未推送；`fe-fe2c-exit` 由设计会话在本 handoff 提交上创建。04 权威运行之后只追加了本 handoff 文档，frontend tree 未变化。

## 1. 范围完成情况

| 要求 | 实现 | 证据 |
| --- | --- | --- |
| 上传步骤卡（目录选择、浏览器打包、逐步校验、错误列表） | `src/features/workbench/UploadStepCard.tsx`、`upload-package.ts`；根目录/`.pmc`/`sql/dbcfg.sql`/5000 文件/1GB 校验；`CompressionStream` 生成确定性 tar.gz | 单测 7 个；e2e `FE2c 上传步骤卡校验目录并锁定页面`；截图 `upload-invalid`、`upload-selected` |
| 上传与 Preview 期间页面锁定、卡片内进度时间线 | `workspace-page--uploading` + `page-lock-overlay`；`OperationStatus` 五阶段；运行中卡片收拢为摘要 | e2e 同场景；截图 `upload-locked-1280` |
| Preview 启动并进入差异浏览 | `runPreviewJourney` 复用 + `onComplete` 跳转 `mode=PREVIEW` | e2e 同场景；上传请求带 `Idempotency-Key` |
| 提交前身份确认 | `SubmitDialog.tsx`：`DIFFERENT_PROJECT`→`ACCEPT_DATASET_REPLACEMENT`、`UNVERIFIABLE`→`ACCEPT_UNVERIFIABLE_DETAILED_RESULT`，逐项复选框 + 理由；提交携带 `assessment_set_digest` | e2e `FE2c 提交前要求确认项目身份差异并进入审核`；截图 `submit-identity-confirmation` |
| 审核顶栏（通过/退回/撤回） | `ReviewActions.tsx`：通过 primary、退回 danger + 必填理由、撤回 danger + 二次确认；History bundle 未就绪时禁用 | e2e `FE2c 审核退回必须填写理由并可撤回`、`FE2c 审核撤回需要二次确认`；截图 `header-review` |
| 归档主线 | `ArchiveMainlineDialog.tsx`：候选→预检→异常处理→逐项确认→“确认后的影响”→最终确认；无 `window.confirm` | e2e `FE2c 归档主线确认预检、异常与影响`；截图 `archive-mainline`、`archive-mainline-result` |
| 403 与版本冲突 | 上传/提交/审核/归档分别映射为内联错误；403 显示“当前身份没有该操作的权限”+ 错误码；版本冲突显示“数据已被更新”+ 刷新提示，不自动重放 | e2e `FE2c 提交 403 与版本冲突显示内联错误`；上传/审核/归档同类分支 |
| 按钮按业务状态启用 | 上传需有效“本次归档组态”；审核需 `PENDING`；归档需 `APPROVED` 且无 `eligibility_note` | workbench e2e 与审核/归档 e2e |

写操作身份由模拟会话选择，生产构建不包含身份选择器或模拟 API（第 5 节 R2 检查）。

## 2. 带入项完成标准

| 编号 | 完成情况 | 证据 |
| --- | --- | --- |
| D1 History 比较逐对摘要 | 抽屉对每个 pair 显示表数、变更表数、降级表数，以及逐表新增/删除/修改行数；只从已下载并校验的本地 bundle（`loadComparisonPresentation`）计算，不新增后端字段 | 单测 `history-summary.test.ts`；截图 `history-compare-result-drawer-1280/1920` |
| N2 等待时长 | `formatWaitDuration`：<1 分钟为秒，≥1 分钟为时/分/秒；操作开始时间来自 `started_at`；e2e 固定页面时钟，截图秒数稳定 | 单测 `wait-duration.test.ts`；截图 `manual-recovery-required-1280/1920`、`upload-locked-1280` |
| N3 构建模块清单 | 清单写到 `node_modules/.cache/frontend-build/production-modules.json`；`check-production-build.mjs` 若发现 `dist/.vite/rollup-modules.json` 直接失败 | R2 正向检查通过；B3 负向探针见第 5 节 |
| N4 测试超时配置 | `historyCompareRequestTimeoutMs()` 仅在 `import.meta.env.DEV` 读取 `window.__gatewayTestConfig`，生产固定 30s；生产检查新增 `__gatewayTestConfig` 禁词 | 生产检查通过；超时 e2e 仍通过（沿用 700ms 模拟配置） |

## 3. Fixture 生成与复现

本阶段没有新增或修改后端差异 fixture，沿用 FE2a/FE2b 的 `frontend/src/test/fixtures/generated/*.tar` 与 `preview-workbench-normal`。因此没有重新运行生成器，FE2b handoff 第 3 节的生成器提交 `d1da70c015`、镜像身份 `gateway-backend-deps:lock-d054366c02fa`、输入摘要与风险表仍适用。

上传 e2e 的目录不是后端 fixture：测试在浏览器里用 `DataTransfer` 构造 `station_cfg_0921`（`station.pmc`、`sql/dbcfg.sql`、`comps/logic/logics.xml` 三个文件），通过 `webkitRelativePath` 触发 `collectLocalDirectory`。它验证的是 Source Package Contract 的前端校验与打包，不进入后端解析；真实打包产物由 `upload-package.test.ts` 的 tar/gzip 断言覆盖。

## 4. 模拟响应场景与来源（§7.5）

### 成功响应

新增/使用的写路由场景（`frontend/src/features/dev/mock-data.ts` 与 e2e 路由桩）：

- `POST /v1/workspaces/{id}/upload-revisions` → 201 `UploadRevisionResponse`；FULL 与 MODIFIED_ONLY 两种上传方式由目录选择派生。
- `POST /v1/workspaces/{id}/preview-operations` → 202；`GET /v1/operations/{id}` 覆盖 QUEUED/RUNNING/SUCCEEDED。
- `POST /v1/workspaces/{id}/submit-attempts` → 202；`GET submit-attempts/{id}` FINALIZED；ABORTED 在 UI 只显示“提交未完成”。
- `POST /v1/submissions/{id}/review-events` → 201/200 重放；APPROVE/REJECT/WITHDRAW 后的 `ReviewFactsResponse.status` 同步更新。
- `POST /v1/archive-plan-preview` 两阶段：需确认方案（含 `confirmation_requirements` 与 `PROJECT_IDENTITY_EXCEPTION`）→ 追加确认/异常处理后的可开始方案；`GET /v1/archive-candidates`、`GET /v1/archive-audit-events`、`POST /v1/archive-confirmations`、`POST /v1/archive-anomaly-resolutions`、`POST /v1/archives`、`GET /v1/archives/{id}` 串成完整主线。

### 错误响应与写路由覆盖

`SIMULATED_ERROR_RESPONSES` 与 `WRITE_SCENARIO_COVERAGE` 已覆盖：403 `SCOPE_FORBIDDEN`；上传/提交/审核/归档的 409 `WORKSPACE_VERSION_CONFLICT`、`BASELINE_VERSION_CONFLICT`、`REVIEW_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT`；归档的 `ARCHIVE_AUDIT_VERSION_CONFLICT`、`CANDIDATE_BINDING_CONFLICT`；历史比较的 409/429。错误体统一 `ErrorResponse`，错误码来自 `openapi.json` 对应路由/状态的描述；`mock-data.test.ts` 继续用 `openapi.json` 校验。

提交的 `PROJECT_IDENTITY_CONFIRMATION_REQUIRED`/`MISMATCH`、`PREVIEW_DERIVED_STALE`、`PREVIEW_BINDING_CONFLICT`、`SUBMIT_OCCUPANCY_CONFLICT`、`NO_CANONICAL_CHANGE` 在提交对话框中有文案映射，但按 §7.5 的写路由最小覆盖要求没有加入默认 mock 错误列表。

### 字符串值来源

`SIMULATED_STRING_VALUES` 已记录本阶段使用的枚举来源：`UploadRevisionInput.input_completeness`、`SubmitAttemptResponse.abort_code`、`ReviewFactsResponse.status`、`PreviewArchivePlanResponse.anomalies[].subject_kind`、`disposition`、`StoreOperationStatus` 等。新增界面上的 `归档为新基线`、`关闭且不归档` 是 disposition 的展示文案，不改变模拟字段值。

## 5. 05 测试与运行证据

### 最终源码候选完整运行

- 节点：`ct108-gw-dms-05`；调试 worktree `/home/dev/gdds-fe2c-debug`，与候选 `a2bcaf86...` 的 frontend 内容一致（rsync 自开发 worktree；无 `.git`，最终证据以 04 为准）。
- 2026-11-03 17:37Z 完整运行：typecheck、lint、27 个单测文件/120 tests、生产 build、`check:production-build`、21/21 e2e 全部通过。
- 生产检查输出：`production dist contains no simulated API, identity selection, or mock data modules`。

### N3 生产构建负向探针

- 在 CT05 的候选副本 `/home/dev/gdds-fe2c-probe` 的 `App.tsx` 加 `import "./features/dev/simulated-api";`（未提交、未进入候选）。
- 在固定工具链容器中执行 `npm run build` 后运行 `node scripts/check-production-build.mjs`，预期 exit 1：`production dist includes development-only modules: /src/src/features/dev/mock-data.ts`、`/src/src/features/dev/simulated-api.ts`。
- 日志 `/home/dev/gdds-fe-logs/fe2c/probe-b3-05.log`，SHA256 `79b79fb1936ce7d388b2c1ddc53392f00311d5d2d951c6844d34ff21c21f6140`。

### CT04 退出权威运行

- 节点：`ct108-gw-dms-04`，hostname `gw-dms-test-04.lan`。clean detached worktree `/home/dev/gdds-fe2c-gate`，HEAD `a2bcaf866a678eb02a15d58a8388759572b76299`，frontend tree `4ce344205cd6dceadb4e3334b1757a0b6af633f6`；legacy 链接指向 `/home/dev/gateway-data-management-system/legacy`；运行前无占用标记。
- 唯一作为证据的入口：`./frontend/scripts/run-tests.sh --screenshots /home/dev/gdds-fe-evidence/fe2c/a2bcaf86-04`，环境变量 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a6f62218109783674cfc37bd64e14a5`。runner 于 `2026-11-03T17:47:48Z` 开始、`2026-11-03T17:48:26Z` 结束，exit 0。起止 HEAD 与 frontend tree 一致，运行后 worktree clean。
- 结果：typecheck、lint、27 个单测文件/120 tests、生产 build、R2 正向生产检查、21/21 模拟接口 e2e 与 61 张截图全部通过。R2 输出同 05。
- 权威日志（CT04）：`/home/dev/gdds-fe-logs/frontend/frontend-tests-20261103T174748Z.log`，SHA256 `c6e3c97350da7a7aea7a3d35747cc5daf389b5eb47c024d0f8e0fa6361da0043`。外层 wrapper `/home/dev/gdds-fe-logs/frontend/fe2c-exit-a2bcaf86-04-wrapper.log`，SHA256 `d39c48b03854c6d24c4bc082199c51053b6da8bd5d6593def9dca6d8fd4ffde2`。
- 工具链镜像：`mcr.microsoft.com/playwright:v1.64.1-noble`；config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；7 个 RootFS DiffID 与 `frontend/scripts/run-tests.sh` 中固定值一致（identity 按 config digest 与全部 DiffID 核对）。
- npm 缓存：`/home/dev/gdds-fe-cache/frontend/npm-cache` 与 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`；归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`，`package-lock.json` 解析项 305 个。未使用转发代理，Docker network `none`。
- 更早一次同入口运行（17:45:29Z，日志 `frontend-tests-20261103T174529Z.log`）也 exit 0，但 `npm_cache_source_commit=unknown`，不作为证据；补上缓存来源参数后从入口起点重跑，以上 17:47:48Z 运行为准。

## 6. 截图清单与视觉偏差

CT04 截图 61 张，目录 `/home/dev/gdds-fe-evidence/fe2c/a2bcaf86-04/`；清单（文件名与 SHA256）`/home/dev/gdds-fe-logs/frontend/fe2c-exit-a2bcaf86-04-screenshots.txt`，清单 SHA256 `51e982edb5e747b33046ef880e1167bfab88fdda6245fddf555cfd89c5440e23`。全部截图：

| 文件 | SHA256 |
| --- | --- |
| `archive-mainline-1280.png` | `c99e1a2643ed754ccdc9fff48f40eaca91f8a5b43242b737458b9af9fc996b5b` |
| `archive-mainline-1920.png` | `f1d3d4dab8e5a854762651420d7c7e50912aa9eadbe01763fd279b81a6cd9e8f` |
| `archive-mainline-result-1920.png` | `b723ff55aae1511b2f90cd79daa5b7b22c2fad08702827ab4798f98041d2746b` |
| `bundle-error-1280.png` | `59f4e9d60e5664b4d2231d9028d6b1557974876cf44d3195cc7761b60163eb18` |
| `bundle-error-1920.png` | `20494b3816ec43025b4b9355cf70b3ce9450262c6cacdb9f33baf84606fb216a` |
| `dataset-replacement-browse-1280.png` | `b0edfd14181cd04ad171a86f044e8784a0c6389dc545c47d3edfb8fcd79435f5` |
| `dataset-replacement-browse-1920.png` | `6bec4feb143177864c95917ccca2317df4a2688d5c4edd70b07fa7f5a6fd6fb0` |
| `formula-history-1280.png` | `8dcf32cde558446a768c297cc37f8d0dd6bbb7f951e9c1c679de142ba0466e4a` |
| `formula-history-1920.png` | `98dc6ae986a0b53ec09543a24ce0e6a1ee1182a646a29a00d626b8b2ec878f25` |
| `formula-preview-1280.png` | `abfd1c18d9033531190457d4c9e88a09a50cbc8bd784b4d290ebbb5f3b44f6cd` |
| `formula-preview-1920.png` | `bcef8f49363b6fb443aa50cc95f831cba83c94f6eb875dcdea304836215c0c2c` |
| `header-review-1280.png` | `b2cc3b92475a9b1be6c71c75e9ce0f7fb57d0611b2c523adbabf52f12f34acef` |
| `header-review-1920.png` | `8075e94c635de8845f2c41adaebf57184dbf87a01e281f037c4fd27cf02650cb` |
| `history-compare-connection-interrupted-1280.png` | `9e5feedc510a78a2571130769648c1ea60e6ac120f7d7be0a6667822b640fd80` |
| `history-compare-connection-interrupted-1920.png` | `e9cbca6945517973bbbba2df523be847acb474230410790f02a83c601555741b` |
| `history-compare-result-drawer-1280.png` | `40a4c0b22832a45f99b44cd44c668fb99883ae001277e1b422dd7f5d254360e0` |
| `history-compare-result-drawer-1920.png` | `7364eddc869b494ded0d4cf44c8c004707e6eb41d2f068285545c5412f6913a4` |
| `history-compare-running-1280.png` | `19aec68efd5576f35f44282614cf5af6f29f50d7e0b4c7db7d3142b5d1b6d82f` |
| `history-compare-running-1920.png` | `ec709620f7314f2165e931423278d4c10018fb8cc6d0a1729d7a95fc80eb6b5d` |
| `loading-skeleton-1280.png` | `6cbdf791f1130167d343a0557776cd780859533ea6d7b9e6eeda1b806796ba88` |
| `loading-skeleton-1920.png` | `bd889713e17225dad97c926856eb813c7f3497df8966b67fe9bd8cc6979331c8` |
| `manual-recovery-required-1280.png` | `762f9b129cd47c55215ea52f31fe59cad1f757e3fe1cd19a0d5d1b23f1695df8` |
| `manual-recovery-required-1920.png` | `aacb3c5478259ba34282e340caa1f54c6944c09bbf960242cc8a5251b6b5c1c7` |
| `navigation-fallback-1280.png` | `d91097cf850ef654f75a577e2c8c9771b0727a7f55c67229857b3c2b4c65e4e4` |
| `navigation-fallback-1920.png` | `7d7fa558ad9f9aca05881bbbe906c2f62c1dbe05e18229f38d62e7c37337cffe` |
| `s1-workbench-1280.png` | `206fc6eb8be094c2a1ca6c2395e2e2a9ff17bf8b8d7c845bc2682ab3c6fa0b9d` |
| `s1-workbench-1920.png` | `3fe487a8153615934efc111671b6da79bf36304c7f1ae1dfba441bee9ecfe2df` |
| `s2-compare-tray-1280.png` | `3a6d9da0501087b204bdf64eb802b48172c645c8dc355879f3428dcdbd96950b` |
| `s2-compare-tray-1920.png` | `2831e2c3cf8af2f1dc0aa84ffa3004131717ae4caf69d8d4a17c3cccb7bee238` |
| `s3-header-history-1280.png` | `22ef7766e9f1e6fa8b45c460622f1867ebd2649edea977bd4040d3ae741b4b6f` |
| `s3-header-history-1920.png` | `14dcc76039dd7edbf8b603c4dc09812c21163e2721869c057c978ebf81cde847` |
| `s3-header-upload-1280.png` | `bdc4b17c807dfe3f66d63d967dbc167a55889f620587ad929891946f5c2752e0` |
| `s3-header-upload-1920.png` | `a6d60e45fc3ea208fdd2131be99b21732b68961bb2b74f8d9abed1347a9002c8` |
| `s3-workbench-normal-1280.png` | `7ca5fe081ffc641693aa67828ffc756e4dcd3e2c04401de070d6b1f85bf71d9c` |
| `s3-workbench-normal-1920.png` | `5daa18c8a823068b691d300d1f51f2eb626f06847ec9d822bc26149f95018d1f` |
| `s3-workbench-upload-1280.png` | `1087705dc5122e5b855fa4a57c0a61edc295a12012a5b53827775d14ae4bf615` |
| `s3-workbench-upload-1920.png` | `0190d27d4263f9e4d4792820c98a785255410aafe068a0db352f877fd3d26f3d` |
| `s4-grid-debug-1280.png` | `96e20e014176e6e82a291927d6e0f86071e3de566724ba1fb34d7ecc66eea650` |
| `s4-grid-debug-1920.png` | `93961d36d83013e4b328126f23764598f836529e3efeb37bbaa979160592d2d8` |
| `s4-grid-hover-1280.png` | `40e83937b9591c22768f650c29ac3e1e9c13e46d67701b336119bd0cef139848` |
| `s4-grid-hover-1920.png` | `ceb1a6f828ad2b026574a68d714490e2a5672890e857ea5850701e4a9dd5eee4` |
| `s4-grid-main-1280.png` | `1087705dc5122e5b855fa4a57c0a61edc295a12012a5b53827775d14ae4bf615` |
| `s4-grid-main-1920.png` | `6caf2660092c371414bf93ba74d6f6898236df46a3b07c92446ab878c91cd35c` |
| `s4-grid-normal-debug-1280.png` | `0e30bea87b3fb481f5fb0c930c2815a88c5f897ded665e5aea28bc46dfc63cd6` |
| `s4-grid-normal-debug-1920.png` | `c2aa4070f0ec44a9d6cab0b73ee79fa9f0d796db0701a0ff925e1118337fa04b` |
| `s4-grid-normal-hover-1280.png` | `8e10187802d9797021c693cb1da7efec8472b54f20df98262f09ac25764853a8` |
| `s4-grid-normal-hover-1920.png` | `899cef79da21068e025b7b9fa5a36a4aac0c205844b19db5260b8fa3e04dbc48` |
| `s4-grid-normal-main-1280.png` | `7ca5fe081ffc641693aa67828ffc756e4dcd3e2c04401de070d6b1f85bf71d9c` |
| `s4-grid-normal-main-1920.png` | `5daa18c8a823068b691d300d1f51f2eb626f06847ec9d822bc26149f95018d1f` |
| `s4-semantic-tokens-1280.png` | `116f9cbb8991ace7deef04e4f5029a211ff933c38aee5e3348f5cba63bcd8b2c` |
| `s4-semantic-tokens-1920.png` | `15fe88e318ed59410b184631888681262349d9220dda26a5f49ac6f12c16dcba` |
| `submit-identity-confirmation-1280.png` | `578c51eb8b6c01c72ae8cfd54991565591a47b47028c5264bc8a584d0c0b46d1` |
| `submit-identity-confirmation-1920.png` | `651a17063877fdefa5cc638b300070ed54d1e746f4b3c4f2bf669ff5f7dc3f5b` |
| `tab-overflow-1280.png` | `c66810efccf1809ff40c57c1095849bffd279b83325faad4483557bc46368465` |
| `tab-overflow-1920.png` | `ec0dfd53f2316d4a24447b6c1c41816e8b9742d2bf1cd9457b80e1d56881f136` |
| `upload-invalid-1280.png` | `4d532fa95da7790be2a481e5fe9c9cd8128d3d26377718a016e1f3e32580994e` |
| `upload-invalid-1920.png` | `ab7e55584cd9e6295c35e233c8315f31fcccf9b8ee3be0437bf9a3fda5e5227f` |
| `upload-locked-1280.png` | `dbcb3bb4286235fc0a3f179b91b4ad8a9478365e31211b88ef01f7570cba54dc` |
| `upload-selected-1920.png` | `ab3076d08525c376ea98641a2ad42f9b34276db01c3111b12f5e0d859c904f52` |
| `workspace-error-no-connected-1280.png` | `730d6a537152013846170dead716d90b9e85235cbcbe6f7deffc7ffc65e47ec9` |
| `workspace-error-no-connected-1920.png` | `4acd5f25b89efa2b25cddbd06644cf070ac2f3cd509b59753d77155dbb86fd69` |

视觉核对结论：

- 上传步骤卡、错误列表、运行中摘要与进度时间线符合 `upload-*` 草图；`upload-locked-1280` 整页覆盖层、卡片可读。
- 审核顶栏在 1280/1920 均显示“撤回/退回/审核通过”，通过为 primary、退回/撤回为 danger outline。
- 归档对话框“预检状态/需逐一确认项/异常处理/确认后的影响”齐全，底部按钮固定可见；结果页显示新基线与处理计数。
- 已知偏差：1280 下提交对话框内容高于可用高度，body 可滚动且首行摘要会随滚动移出（截图为滚动后状态）；不影响操作。上传/Preview 运行中页面以覆盖层锁定，不提供取消入口，符合 T1。

## 7. 停止与 DC68 记录

本阶段没有触发停止条件，没有 FD3 事项。调试期间出现过一次实现缺陷：`SubmitDialog`/`ArchiveMainlineDialog` 在 `setState` updater 中读取 `event.currentTarget`，导致复选框/文本域更新抛错；改为先捕获值再更新状态，属于普通实现修复，不是被测对象运行后的证据失效，也未按 DC68 重做验收运行。N3 负向探针与 05/04 运行均按计划完成。

## 8. 已知差异与待处理事项

1. **上传模式下的“撤回”入口缺失。** vnext `WorkspaceResponse` 没有指向当前提交的字段，工作台无法判断上传模式下的可撤回提交；FE2c 未新增后端字段，撤回只出现在审核顶栏。草图 `header-upload` 中上传模式的“撤回”按钮未实现，交 owner 决定是否需要在后续阶段补 API。
2. **上传快捷按钮的落点。** PREVIEW 顶栏的“原始组态备份/本次归档组态/上传”按草图保留为快捷入口，但实现为回到工作台并展开上传卡（保留 `workbenchNode`），避免出现第二套上传界面；提交执行中全部禁用。
3. **模拟 API 的执行入口。** 本阶段 e2e 继续使用路由桩，`simulated-api` 只作为场景/类型来源；这与 FE2b 的证据方式一致，没有新增运行时模拟服务器。
4. **1280 提交对话框滚动。** 双身份确认时内容超过可视高度，对话框 body 滚动、footer 固定；不影响确认与提交。

## 9. 本阶段 worktree 与传输文件清单（供退出后清理）

- 开发 worktree：`/home/dev/gdds-fe`（`fe-vnext`，候选提交 `a2bcaf866a`）。
- CT05 调试目录：`/home/dev/gdds-fe2c-debug`（rsync 副本，无 `.git`）；N3 探针副本 `/home/dev/gdds-fe2c-probe`。
- CT04 取证 worktree：`/home/dev/gdds-fe2c-gate`（detached HEAD `a2bcaf866a`），legacy 链接指向 `/home/dev/gateway-data-management-system/legacy`；共享仓库临时分支 `refs/heads/fe-vnext` 被本次 fetch 更新到 `a2bcaf866a`（该分支原本不存在）。
- 源码 bundle：开发主机 `/tmp/fe2c.bundle`，CT04 `/home/dev/fe2c.bundle`；内容为 `fe-vnext` 相对 `31f4310ff8` 的增量。
- 运行日志：CT04 `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261103T174748Z.log` 与 `fe2c-exit-a2bcaf86-04-wrapper.log`；截图清单 `/home/dev/gdds-fe-logs/frontend/fe2c-exit-a2bcaf86-04-screenshots.txt`；CT05 探针日志 `/home/dev/gdds-fe-logs/fe2c/probe-b3-05.log`。
- 截图：CT04 `/home/dev/gdds-fe-evidence/fe2c/a2bcaf86-04/`；05 调试副本 `/home/dev/gdds-fe-evidence/fe2c-all/`、`/home/dev/gdds-fe-evidence/fe2c-debug/`。
- 证据保留到审核会话核对完成、`fe-fe2c-exit` 创建后再清理。

## 10. FE2c 带入事项（给后续阶段）

- 若补上传模式撤回，先由 backend 提供当前上传模式提交的绑定字段，再在草图的 PREVIEW 顶栏接回；不要在 FE2 会话里新增后端字段。
- 提交对话框在窄屏的摘要首行滚动问题可在 FE2d 统一对话框尺寸策略时处理。
- 归档异常处理目前只覆盖 `APPROVED_SIBLING_EXCLUDED` 与 `PROJECT_IDENTITY_EXCEPTION`；新增 `subject_kind` 时同步补 UI 文案和 e2e。
