# FE2c 定向修复 handoff — B1–B11 / M1–M7

- 修复范围：`5830bc73c4..4c096d49`（05 detached worktree `/home/dev/gdds-fe2c-fix-05`，11 个提交）。
- 审核报告：`/tmp/fe2c-review.md`（结论定向修复，B1–B11 + M1–M7，复审范围 `5830bc73c4..4c096d49`）。
- 运行：05 完整 runner（含 `--e2e --screenshots`）exit 0，27 单测文件/125 tests + 21 e2e + 64 截图。04 取证待复审通过后一次运行。
## 1. 05 提交清单

| 提交 | 内容 |
| --- | --- |
| `4c1a916a` | B1–B8/B10–B11 首批：tar size、per-subject key、blocked 拆分、URL resume、dialog key、uploadReady、错误码、单测间歇修复、上传阶段名 |
| `87fa333d` | B7 空目录提示（`需先选择本次归档组态目录`） |
| `04d5307f` | B3/D1：archive 422 桩 + `NEEDS_CONFIRMATION(audit_validity:false)` + D1 fixture 单测 |
| `5480f51b` | e2e 补 import `ARCHIVE_PLAN_NEEDS_CONFIRMATION` |
| `c5d2e3ec` | B3 对话框确认键不再被初始 `can_start=false` 阻塞（journey 追加确认后重预检） |
| `b97b6ba7` | docs：上一版 handoff（`c5d2e3ec` runner exit 0） |
| `5c29b8d1` | B3/B6 探针靶点单测：`NEEDS_CONFIRMATION` 后端规则 + 对话框 key/界面版本 |
| `008cd90a` | e2e 补缺失双宽度截图（`upload-selected-1280`、`upload-locked-1920`、`archive-mainline-result-1280`） |
| `73c70ed2` | docs：handoff 绑定 `73c70ed2` 确认运行（125 tests + 21 e2e + 64 png） |
| `cd40b409` | docs：handoff 绑定 `cd40b409` 确认运行（125 tests + 21 e2e + 64 png） |
| `4c096d49` | docs：本 handoff（`4c096d49` runner exit 0，125 tests + 21 e2e + 64 png） |
`git -C /home/dev/gdds-fe2c-fix-05 diff 5830bc73c4..HEAD --stat`：19 文件，354+/254-。

## 2. B1–B11 修复对照

| ID | 修复 | 文件 |
| --- | --- | --- |
| B1 | `tarHeader(path, content.byteLength)` + `writeOctal(124,12,size)`；单测读回内容 + prefix 分段；预留 M1 字节/条目上限 | `upload-package.ts`、`upload-package.test.ts` |
| B2 | Preview/确认/异常处理/开始归档按步骤收 key；缺 key 桩返回 422 `REQUEST_VALIDATION_FAILED`（preview/archive-confirmations/anomaly-resolutions/archives） | `journeys.ts`、e2e spec |
| B3 | `blocked = blockers.length>0`；`needsConfirmation` 只做提示；确认键可用性只看缺失项（不看初始 `can_start`）；桩首检用 `NEEDS_CONFIRMATION(can_start:false, audit_validity:false)`；单测按后端规则锁死该语义（探针靶点） | `ArchiveMainlineDialog.tsx`、`mock-data.ts`、e2e、`mock-data.test.ts` |
| B4 | `listArchiveEvents({subjectKind, subjectDigest, afterSequence?})` 必填；每 subject 取最新 sequence（无记录 0）；单测断言 CONFIRM 0 / ANOMALY 7；桩缺参数 422 | `client.ts`、`journeys.ts`、`journeys.test.ts`、e2e |
| B5 | `onOperationAccepted(operation_id)` → URL 写 `operationId+operationKind=operation`；MANUAL 显示可复制 ID + 刷新跟随；`showOperationStatus` 覆盖 `operationId!=null && (kind null/operation)` | `journeys.ts`、`UploadStepCard.tsx`、`SubmitDialog.tsx`、`WorkbenchPage.tsx` |
| B6 | 对话框 key：打开生成、确认复用、4xx 换新；`applyReviewAction(api, submissionId, reviewVersion, …)` 发界面版本；单测断言不重读版本 + 复用传入 key（探针靶点） | `ReviewActions.tsx`、`journeys.ts`、`journeys.test.ts` |
| B7 | 空目录 `uploadReady=false` + 提示；有效目录 `enabled`；Preview 顶栏仍无上传快捷入口（偏差，见 §5） | `workspace.ts`、`workspace.test.ts`、`WorkbenchPage.tsx`、`UploadStepCard.tsx` |
| B8 | 错误码全构建可见 + 复制；版本冲突刷新：工作区（`window.location.reload`）、归档（刷新预检）；`ABORTED` 显示原始码 | `SubmitDialog`、`ReviewActions`、`ArchiveMainlineDialog` |
| B9 | 集中 `mock-data.ts`（`SIMULATED_ERROR_RESPONSES` + `WRITE_SCENARIO_COVERAGE`）+ `mock-data.test.ts` openapi 校验；e2e 补 422（preview/archive/audit）+ 复用 403/409；B1–B4 单测按后端规则 | 各文件 |
| B10 | `globalThis.setTimeout/clearTimeout` + 单测 `globalThis.setTimeout` | `idempotency.ts`、`.test.ts` |
| B11 | 阶段名：`下载预览结果 / 写入本地 / 完成，进入差异浏览`；清除按钮、`校验通过`、`FileList\|File[]\|null`；IDEMPOTENCY_CONFLICT 换 key | `UploadStepCard.tsx` |

## 3. M1–M7

- M1：`MAX_ARCHIVE_BYTES=256MiB`、`MAX_ARCHIVE_ENTRIES=8192`，超限抛 413 提示（流式打包未做，偏差）。
- M2：`page-lock-overlay` 加 `inert`（TS `as object` 透传）。
- M3：运行中标题 `已用时（页面计时）`，与操作 `started_at` 的“已等待”区分。
- M4：提交对话框注明“后端按动作只保留最后一条理由”。
- M5：本次 05 运行 3 次失败 + 1 次通过均记录（`04d5307f` 进口、`5480f51b` 确认键、`c5d2e3ec` 通过）；bundle 在 `/home/dev/gdds-test-tmp`；worktree 均为已提交 detached；日志在 `/home/dev/gdds-fe-logs/fe2c/`。
- M6：§4 场景来源修正（`mock-data.ts` + e2e 桩）；“上传/审核/归档同类分支”已有测试覆盖（§2）。
- M7：未改（提交摘要仍为原始 ID；取用 History 标签需跨页数据，偏差）。

## 4. 05 权威运行证据

- 命令：`bash frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-evidence/fe2c/fix-4c096d49-05`（05 detached `4c096d49`，clean；`GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`，archive `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，`GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a6f62218109783674cfc37bd64e14a5`）。
- 日志：`/home/dev/gdds-fe-logs/frontend/frontend-tests-20261104T081709Z.log`，SHA256 `8010bc7c396120618fcc48d877a6637f78c5b8e7e8f0b13c6626b4590e547460`；`started_at=2026-11-04T08:17:09Z`，`ended_at=2026-11-04T08:17:43Z`，`hostname=gw-dms-test-05.lan`，`head_start=head_end=4c096d49`，`frontend_tree=46ed8248…`，`exit_code=0`。
- 结果：typecheck 0；lint 0；27 单测文件 125 tests 通过；21/21 e2e 通过；生产构建检查通过（`production dist contains no simulated API…`）。
- 工具链/npm 缓存：`mcr.microsoft.com/playwright:v1.64.1-noble`（config `sha256:a0d7b2b4…`，7 DiffID 与既有值一致），`docker_network=none`，npm cache `source_commit=a2fb4a02`，`package_lock_resolved_count=305`，archive SHA `0d861824…`，tracked archive `cfb5ba72…`（handoff 为 docs-only 增补引起变化，未改测试输入）。
- 证据目录：`/home/dev/gdds-fe-evidence/fe2c/fix-4c096d49-05/`，64 png（逐文件 SHA 总和 `719a3b6a…`；SHA 待 04 取证时重算）。
- 失败过程（M5 要求记录）：`04d5307f`（缺 import，20/21）、`5480f51b`（B3 桩变严后确认键被初始 can_start 阻塞，20/21）、`c5d2e3ec` 通过（61 png）、`008cd90a` 通过（64 png）、`cd40b409`/`73c70ed2`/`41081b87`/`ec34b134` 通过（64 png）；本轮 `4c096d49` 通过（64 png）。首次直连默认缓存路径失败（`npm cache is missing or empty: /home/dev/gdds-fe-cache/frontend/npm-cache`），改用既有 fe0 缓存 env 后重跑通过。
## 5. 探针（§9 要求，结果进 handoff）

- 本轮新增探针靶点单测（均在 05 已提交，`5c29b8d1`；本地反向验证已通过，未污染证据 HEAD）：
  - B1：`upload-package.test.ts` 去掉 size 写入 → 读回单测失败（2 failed / 9；`size` 0 ≠ 内容长）；后端 `validate_source_package_archive` 复用报告 P1/P2 结论（前端产物拒收 `UPLOAD_CLOSURE_INVALID`，Python 对照通过）。
  - B2：去掉任一步 key → 对应 422 桩使上传/归档 e2e 失败（报告 P3 已证；本轮桩保留 422 回归）。
  - B3：`NEEDS_CONFIRMATION`  fixture 改 `can_start:true` → 新增单测失败（1 failed / 7：`audit_validity:false` 与 `can_start:false` 必须同现）。
  - B6：`applyReviewAction` 内重读版本/换新 key → 新增单测失败（2 failed / 12：必须发送界面版本 + 复用传入 key，不重读 `getReviewFacts`）。
- B10：本地 `vitest run` 27/125 通过 + 本轮 05 runner 通过；报告 P4/P6 的间歇背景已由 `globalThis` 修复覆盖，更长连续次数待 04 取证时补。
## 6. 截图（64 张，`fix-4c096d49-05/`）

`archive-mainline-1280/1920`、`archive-mainline-result-1280/1920`、`bundle-error-*`、`dataset-replacement-browse-*`、`formula-history/preview-*`、`header-review-*`、`history-compare-connection-interrupted/running/result-drawer-*`、`loading-skeleton-*`、`manual-recovery-required-*`、`navigation-fallback-*`、`s1-workbench-*`、`s2-compare-tray-*`、`s3-header-history/upload-*`、`s3-workbench-normal/upload-*`、`s4-grid-*`、`s4-semantic-tokens-*`、`submit-identity-confirmation-*`、`tab-overflow-*`、`upload-invalid-*`、`upload-locked-1280/1920`、`upload-selected-1280/1920`、`workspace-error-no-connected-*`。

缺少（偏差，沿用报告 §8，相对上一轮已补 3 张）：退回/撤回对话框、上传空状态/运行中卡片/失败重试、`ABORTED`、归档被阻断、写操作 403/409 单独截图。改动涉及的截图已重拍（archive-mainline、upload 阶段、submit 进度）。
## 7. 已知偏差（不能按草图修正，交 owner）

1. PREVIEW 顶栏无上传快捷入口（B7 后半）。
2. 上传打包非流式（M1 后半，大目录内存 2x）。
3. 提交摘要仍为原始 ID（M7）。
4. 截图缺项见 §6；`history-compare-result-drawer` 布局仍为小字 + 全表（未按 compare-1920 四卡片改）。
5. 上传模式“撤回”缺失（原 handoff §8.1，后端无字段，属 §10 停止条件）。

## 8. 复审与 04 取证

- 复审范围：`5830bc73c4..4c096d49`（以 05 为准；本地 `fe-vnext` 仍在 `5830bc73c4` + dirty 文件，未提交，勿作证据；本 handoff 为 docs-only，测试输入与 runner 一致）。

## 9. 写操作步骤与 key 规则（N1、N5 设计）

本轮先按本节实现，再改代码。key 只在当前页面/对话框的内存状态中保存，不写入 URL、`localStorage` 或 `sessionStorage`；刷新后只按 URL 中的 `operationId` 继续已受理的操作，未受理的步骤没有可续结果，按新意图重新开始，不重放旧 key（依据 kickoff §7.5 N2“`operation_id` 写入 URL，刷新后继续轮询”）。

| 步骤 | key 何时生成、何时复用、何时换新 | 重试从哪一步续做（已成功步骤使用的已知结果） | 依据 |
| --- | --- | --- | --- |
| 上传 `POST .../upload-revisions` | 用户点“上传并生成预览”时生成 `uploadKey`；同一次选择的重试复用它；目录选择改变、上传被 4xx 拒绝或刷新后重新开始时换新 | 上传成功后记录 `upload_revision_id`、`generation`、返回工作区的 `optimistic_version`；重试不再上传，直接从 Preview 续做。上传请求本身重放时必须仍发送首次的 `expected_workspace_version`（上传成功后工作区版本已前进，重发旧版本会与记录的指纹不符） | `application/workspace/services.py:86–151`（先按 key 查已有 revision，再比较 `compute_upload_request_fingerprint`，最后才做版本 CAS）；`application/workspace/contracts.py:86–111`（指纹含 `expected_workspace_version` 与各 artifact 的 `raw_sha256`） |
| Preview `POST .../preview-operations` | 与上传同时生成独立的 `previewKey`；同一次上传结果的重试复用；上传结果变化、刷新后重新开始或 Preview 返回 4xx 时换新 | Preview 受理后记录 `operation_id`，只轮询该操作；若受理响应丢失，用同一 `previewKey`、同一 upload revision、同一预期基线/版本重发，后端按已保存的 acceptance 回放同一个 `operation_id`，不产生第二次 Preview | `application/workspace/preview.py`（`deterministic_preview_operation_id` 与 `validate_start_preview_binding`：受理记录按 `(workspace_id, key)` 查找，指纹不符才报 `IDEMPOTENCY_CONFLICT`；回放返回先前 `operation_id`） |
| 提交 `POST .../submit-attempts` | 提交对话框打开时生成；同一提交意图的重试复用；终端 4xx（含工作区/基线版本冲突）换新，刷新事实后重新确认 | 受理后记录 `operation_id`，只轮询；操作成功后再取 `submit-attempts/{id}` 与 `submissions/{id}`。受理响应丢失时用同一 key 与同一请求体重发，返回第一次响应体；不重新上传或 Preview | kickoff §7.5“幂等回放”；`http/routes/submit_attempts.py` |
| 审核 `POST /v1/submissions/{id}/review-events` | 审核对话框打开时生成；同一 `expected_review_version` 与动作的重试复用；4xx（含 `REVIEW_VERSION_CONFLICT`）换新，界面刷新审核事实后重新确认 | 成功即结束；失败重试只重发同一动作与同一 `expected_review_version`。版本冲突后先重读 `GET .../review`，用新的 `review_version` 重新生成 key | `http/routes/reviews.py`、`http/orchestration/review.py`；kickoff §7.5 |
| 每条归档确认 `POST /v1/archive-confirmations` | 用户点“确认并开始归档”时，按 `subject_digest` 各生成一个 key 并记入对话框进度；该 subject 的重试复用；该 subject 的 `expected_sequence`、目标摘要或选择改变时换新，`ARCHIVE_AUDIT_VERSION_CONFLICT` 后刷新预检并换新 | 成功追加后记录该 subject 的 `sequence` 与事件 id；重试跳过已成功追加的记录，只处理剩余记录；开始归档请求使用已记录的 confirmation refs（`subject_digest` + `sequence`），不按新序号重发 | `infrastructure/control_db/schema.py:747–790`（`archive_confirmation_events` 的 `UNIQUE(repository_id, idempotency_key)` 与 `UNIQUE(repository_id, subject_digest, sequence)`）；`application/archive/audit.py:117–125`（按 key 查已有事件，指纹不符报冲突，否则回放）；`application/archive/contracts.py:271–311`（确认指纹含 `subject_digest`、`expected_sequence`、选择摘要等） |
| 每条异常处理 `POST /v1/archive-anomaly-resolutions` | 与确认同时、按异常的 `subject_digest` 各生成一个 key；重试复用；异常内容或 `expected_sequence` 改变时换新，冲突刷新后换新 | 成功追加后记录该异常的 `sequence` 与事件 id；重试跳过已成功记录，只处理剩余异常；开始归档请求使用已记录的 anomaly refs | `infrastructure/control_db/schema.py:793+`（`archive_anomaly_resolution_events` 同样两个 UNIQUE）；`application/archive/audit.py:238–246`；`application/archive/contracts.py:312–365` |
| 开始归档 `POST /v1/archives` | 所有确认与异常处理成功后、首次发“开始归档”时生成 `startKey`；同一次选择与同一组 refs 的重试复用；选择、候选摘要或 refs 改变时换新，刷新预检后换新 | 受理后记录 `operation_id`/归档结果；请求丢失时用同一 key 与同一组 refs 重发，后端按已保存计划回放。已成功的确认与异常处理不重发 | `application/archive/start.py:80–139`（按 key 查已保存计划，指纹不符报 `IDEMPOTENCY_CONFLICT`，匹配则回放）；`application/archive/contracts.py:367+`（开始指纹含 `candidate_set_digest`、选中集、排序后的 confirmation/anomaly refs） |

实现约定：

- 归档 journey 接受一个可变的进度对象（按 subject 的 key、已追加的 sequence、开始 key、开始结果），对话框在重试之间保留它；失败不会清空已成功的记录。
- 只有 `IDEMPOTENCY_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT` 或用户改变输入时，才丢弃对应步骤的 key 并刷新预检；网络错误、超时、5xx、429 一律保留 key 重试。
- 单元测试固定两条：两个异常各自使用自己的 key 与序号；开始归档失败后重试不重发确认/异常处理，并使用同一 `startKey`。
