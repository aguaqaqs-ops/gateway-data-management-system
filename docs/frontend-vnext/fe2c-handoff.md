# FE2c 定向修复 handoff（第 4 轮）— R6 / R7

- 候选提交：`e3835718eb6879a7461c176820c5576f87c48b81`，`frontend/` tree `960ab1f6a1f7f368d47824b3e1570be85be517c5`。
- 复审范围：`01a232c40be247bb9b22d69c23d3f054bf75c590..<本 handoff 提交>`；05 detached worktree `/home/dev/gdds-fe-fix4-e3835718-05`，运行和 handoff 前均为已提交 clean 状态。
- 依据：`docs/frontend-vnext/reviews/fe2c-rereview-3.md` §3（R6、R7，n1–n7）、AGENTS“前端测试（FD7）”“镜像身份”。
- 05 完整 runner：exit 0，130 unit tests + 32 e2e，94 张截图。上传包校验输入未变化，本轮未重跑校验脚本。
- bundle：`/home/dev/gdds-test-tmp/fe2c-fix4-e3835718.bundle`；04 取证待复审通过后一次运行。

## 1. 提交清单

`git log --oneline 01a232c40b..HEAD`：

```text
e3835718 test(frontend): assert dialog alerts in viewport at both round-4 widths
ec503f39 fix(frontend): keep dialog alerts in view and widen round-4 error surfaces
```

## 2. 逐项对照

| ID | 提交 | 测试 / 用例 | 截图 | 状态 |
| --- | --- | --- | --- | --- |
| R6 归档错误提示进入可视区域 | `ec503f39`、`e3835718` | `FE2c 归档 403、审计冲突与阻断项` 在 1920 与 1280 对错误码与“刷新预检”断言 `toBeInViewport()`；`FE2c 审核 403、版本冲突与超时重试复用同一幂等键` 对“刷新审核信息”在两种宽度断言；`FE2c 提交被中止时显示原始错误代码`、`FE2c 提交对话框显示需要管理员处理并可跟随到成功` 对长内容提交对话框在两种宽度断言 | `archive-audit-conflict-*`、`review-version-conflict-*`、`submit-aborted-*`、`submit-manual-recovery-*` | 完成 |
| R7 对话框禁用 `nowrap`、影响文字不溢出 | `ec503f39` | `.dialog` 设 `white-space: normal`，`.confirm-impact` 允许换行；`FE2c 审核退回必须填写理由并可撤回` 在 1280 对通过、退回、撤回三个对话框断言 `.confirm-impact` 的 `scrollWidth <= clientWidth + 1` | `review-reject-dialog-*`、`review-withdraw-dialog-*` | 完成 |
| n1 刷新失败进入失败阶段 | `ec503f39` | `FE2c 上传冲突后刷新失败时进入失败阶段并显示原因`：冲突后刷新失败，显示 `REFRESH_FAILED` 与原因，阶段为失败 | `upload-failure-retry-*` | 完成 |
| n2 下载阶段文案与状态不矛盾 | `ec503f39` | `PreviewJourneyInput.onDownloadStart` 使阶段在上传结果返回后进入下载；下载阶段 5xx 文案为“预览已生成，但下载比较结果失败，请重试”。现有 `FE2c 上传失败后重试不重复上传` 只覆盖 Preview 进行中的前端文案，下载阶段文案未单独断言 | `upload-failure-retry-*` | 部分（下载阶段文案无专门 e2e） |
| n3 提交刷新续做失败与禁用 | `ec503f39` | 比较页读取 `sessionStorage` 提交标记；`ABORTED`/缺少 submission 时显示“提交未完成”与原始错误码，读取失败显示刷新提示，续做期间 Preview 的“提交”按钮禁用并说明原因。成功路径由 `FE2c 提交执行中刷新后成功后进入提交结果` 覆盖，失败/禁用分支无专门 e2e | — | 部分（失败分支无专门 e2e） |
| n4 第 2 轮运行说明 | — | 第 2 轮失败运行的说明已在本文件 §3 与历史记录中保留 | — | 完成 |
| n5 修正错误注释 | `ec503f39` | 归档场景注释改为“非阻断分支跟随 current candidate；阻断分支沿用 submission-1” | — | 完成 |
| n6 归档无权限禁用原因与复制 | `ec503f39` | `loadError` 就地显示 `SCOPE_FORBIDDEN` 与“当前身份没有归档权限”；失败提示与预检错误均提供“复制错误代码” | `archive-permission-denied-*`、`archive-audit-conflict-*` | 完成 |
| n7 补 1280 截图 | `ec503f39` | 新增 `upload-running-modified-only-1280`；本轮重拍截图均含 1280/1920 | `upload-running-modified-only-*` | 完成 |
| N7（上一轮复核）写操作场景 | `ec503f39` | 403、版本/幂等冲突、提交 ABORTED、归档阻断项均保留；审核用审核人、归档用归档人并核对 token | `archive-blocked-*`、`submit-aborted-*` | 完成 |
| N8（上一轮复核）阶段名与摘要 | `ec503f39` | MODIFIED_ONLY 阶段名与摘要行保持第 3 轮实现；空基线禁用按 Q18 已撤回 | `upload-running-modified-only-*`、`upload-selected-*` | 部分（空基线按 Q18 撤回） |

## 3. 05 运行清单

全部在 `gw-dms-test-05.lan` 的已提交 clean worktree 运行；日志目录 `/home/dev/gdds-fe-logs/fe2c/fix-4`。探针为一次性 worktree 中的 focused Playwright 运行，也列在此处。

| HEAD | 类型 | 开始（UTC） | exit | 日志 | SHA256 |
| --- | --- | --- | --- | --- | --- |
| `ec503f39` | runner（全量） | 2026-11-04T15:35:59Z | 0 | `frontend-tests-20261104T153559Z.log` | `4f367b48642c8b24c5662096894d6a8ca1f67d0b016b786c541c3952f5ec3321` |
| `e3835718` | runner（全量） | 2026-11-04T15:41:51Z | 0 | `frontend-tests-20261104T154151Z.log` | `1a96df74044e304ab79a66da9a19ca55a19fe07d37c6dbc27f2f07c96c5493db` |
| `ec503f39`（探针改动） | focused e2e | 2026-11-04T15:38:07Z | 1 | `probe-r6.log` | `493af073c8930f4ce53c687d18c94f8e5949b41bd3a8294d57159aefca5ab6d7` |
| `ec503f39`（探针改动） | focused e2e | 2026-11-04T15:39:09Z | 1 | `probe-r7.log` | `8a4e259eb3373373e962e6a199f0aba3a5dbe8d551de0f627cdfd87e77477b78` |
| `ec503f39`（探针改动，缺 fixture） | focused e2e | 2026-11-04T15:43:10Z | 1 | `probe-r7-nofixture.log` | `15d0c2efb879435de1b79236452221af534a97030b2327f586c7963e0361f273` |

第 1 次全量运行即为绿色；第 2 次在全量运行前补充了 1920 与 1280 的显式 `toBeInViewport` 断言，未改写已运行的 `ec503f39`。R7 探针首次运行因探针环境未生成 golden bundle fixture 而失败（`probe-r7-nofixture.log`）；生成 fixture 后重跑，失败点变为预期的 `.confirm-impact` 溢出断言。上传包校验脚本本轮未运行：`pyproject.toml`、`uv.lock`、`.python-version`、`Cargo.lock`、`rust-toolchain.toml` 与本轮输入均未变化。

## 4. 探针

在一次性 worktree `/home/dev/gdds-fe-probe-fix4-05` 中完成，完成后删除。

| 探针 | 改动 | exit | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| R6 错误提示移回滚动区底部 | 归档对话框 `alert={null}`，失败块放回 `.dialog__body` 末尾 | 1 | `FE2c 归档 403、审计冲突与阻断项` 在 `expect(refreshPreflight).toBeInViewport()` 失败，`viewport ratio 0` | `493af073c8930f4ce53c687d18c94f8e5949b41bd3a8294d57159aefca5ab6d7` |
| R7 恢复对话框 `nowrap` | 删除 `.dialog{white-space:normal}` 与 `.confirm-impact` 换行 | 1 | `FE2c 审核退回必须填写理由并可撤回` 在 `.confirm-impact` 溢出轮询处失败 | `8a4e259eb3373373e962e6a199f0aba3a5dbe8d551de0f627cdfd87e77477b78` |

## 5. 截图

- 目录：`/home/dev/gdds-fe-evidence/fe2c/fix-4-e3835718-05`，94 张 png，1280/1920 双宽度。
- 聚合 SHA256：`eed5369263ac91c20c5d24794fbf7d7451871746059ad0ef338313033827e5f7`（`sha256sum *.png | sort -k2 | sha256sum`）。
- 重拍：`archive-audit-conflict-*`、`review-reject-dialog-*`、`review-withdraw-dialog-*`、`review-version-conflict-*`、`submit-aborted-*`、`submit-manual-recovery-*`、`archive-permission-denied-*`、`archive-blocked-*`、`upload-failure-retry-*`、`upload-running-modified-only-*`；新增 `upload-running-modified-only-1280`。

## 6. 偏差

- n2：下载阶段的“预览已生成，但下载比较结果失败”文案没有专门 e2e；现有重试用例在 Preview 进行中失败，断言的是通用前端文案。
- n3：提交刷新续做的失败（`ABORTED`、读取失败）与“提交”按钮禁用分支没有专门 e2e，只有成功续做用例。
- 无其他偏差；不涉及上传包校验输入，校验脚本未运行。

## 7. 复现与证据环境

- 工具链镜像 `mcr.microsoft.com/playwright:v1.64.1-noble`：config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；RootFS DiffID 共 7 个，见 runner 日志。
- npm 缓存：`/home/dev/gdds-fe-cache/fe0/npm-cache`，来源归档 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`。
- runner 日志目录 `/home/dev/gdds-fe-logs/fe2c/fix-4`，截图目录与探针 worktree 均在 worktree 外。
- 上传包校验脚本及其输出沿用第 3 轮：`/home/dev/gdds-fe-logs/fe2c/fix-3/upload-validator-9518278fef-20261104T120207Z-1070818.log`，4/4 通过；本轮未改校验输入。

## 8. 复审与 04 取证

- 复审对象：`01a232c40be247bb9b22d69c23d3f054bf75c590..<本 handoff 提交>` 的提交区间；候选 `e3835718`。
- 04 完整运行与截图待复审通过后执行一次；本轮未在 04 运行，未推送、未打 tag。

## 9. 写操作步骤与 key 规则（N1、N5 设计）

本轮先按本节实现，再改代码。key 只在当前页面/对话框的内存状态中保存，不写入 URL、`localStorage` 或 `sessionStorage`；刷新后只按 URL 中的 `operationId` 继续已受理的操作，未受理的步骤没有可续结果，按新意图重新开始，不重放旧 key（依据 kickoff §7.5 N2“`operation_id` 写入 URL，刷新后继续轮询”）。第 3 轮补充：提交受理后另在 `sessionStorage` 记录 `operationId`、`workspaceId`、`submitAttemptId`，仅用于刷新后取回提交结果，不保存任何幂等 key。

| 步骤 | key 何时生成、何时复用、何时换新 | 重试从哪一步续做（已成功步骤使用的已知结果） | 依据 |
| --- | --- | --- | --- |
| 上传 `POST .../upload-revisions` | 用户点“上传并生成预览”时生成 `uploadKey`；同一次选择的重试复用它；目录选择改变、上传被确定 4xx 拒绝（408/429 除外）或刷新后重新开始时换新 | 上传成功后记录 `upload_revision_id`、`generation`、返回工作区的 `optimistic_version`；重试不再上传，直接从 Preview 续做。上传请求本身重放时必须仍发送首次的 `expected_workspace_version`（上传成功后工作区版本已前进，重发旧版本会与记录的指纹不符） | `application/workspace/services.py:86–151`（先按 key 查已有 revision，再比较 `compute_upload_request_fingerprint`，最后才做版本 CAS）；`application/workspace/contracts.py:86–111`（指纹含 `expected_workspace_version` 与各 artifact 的 `raw_sha256`） |
| Preview `POST .../preview-operations` | 与上传同时生成独立的 `previewKey`；同一次上传结果的重试复用；上传结果变化、刷新后重新开始或 Preview 返回确定 4xx（408/429 除外）时换新 | Preview 受理后记录 `operation_id`，只轮询该操作；若受理响应丢失，用同一 `previewKey`、同一 upload revision、同一预期基线/版本重发，后端按已保存的 acceptance 回放同一个 `operation_id`，不产生第二次 Preview | `application/workspace/preview.py`（`deterministic_preview_operation_id` 与 `validate_start_preview_binding`：受理记录按 `(workspace_id, key)` 查找，指纹不符才报 `IDEMPOTENCY_CONFLICT`；回放返回先前 `operation_id`） |
| 提交 `POST .../submit-attempts` | 提交对话框打开时生成；同一提交意图的重试复用；终端 4xx（含工作区/基线版本冲突）换新，刷新事实后重新确认 | 受理后记录 `operation_id`，只轮询；操作成功后再取 `submit-attempts/{id}` 与 `submissions/{id}`。受理响应丢失时用同一 key 与同一请求体重发，返回第一次响应体；不重新上传或 Preview | kickoff §7.5“幂等回放”；`http/routes/submit_attempts.py` |
| 审核 `POST /v1/submissions/{id}/review-events` | 审核对话框打开时生成；同一 `expected_review_version` 与动作的重试复用；4xx（含 `REVIEW_VERSION_CONFLICT`）换新，界面刷新审核事实后重新确认 | 成功即结束；失败重试只重发同一动作与同一 `expected_review_version`。版本冲突后先重读 `GET .../review`，用新的 `review_version` 重新生成 key | `http/routes/reviews.py`、`http/orchestration/review.py`；kickoff §7.5 |
| 每条归档确认 `POST /v1/archive-confirmations` | 用户点“确认并开始归档”时，按 `subject_digest` 各生成一个 key 并记入对话框进度；该 subject 的重试复用；该 subject 的 `expected_sequence`、目标摘要或选择改变时换新，`ARCHIVE_AUDIT_VERSION_CONFLICT` 后刷新预检并换新 | 成功追加后记录该 subject 的 `sequence` 与事件 id；重试跳过已成功追加的记录，只处理剩余记录；开始归档请求使用已记录的 confirmation refs（`subject_digest` + `sequence`），不按新序号重发 | `infrastructure/control_db/schema.py:747–790`（`archive_confirmation_events` 的 `UNIQUE(repository_id, idempotency_key)` 与 `UNIQUE(repository_id, subject_digest, sequence)`）；`application/archive/audit.py:117–125`（按 key 查已有事件，指纹不符报冲突，否则回放）；`application/archive/contracts.py:271–311`（确认指纹含 `subject_digest`、`expected_sequence`、选择摘要等） |
| 每条异常处理 `POST /v1/archive-anomaly-resolutions` | 与确认同时、按异常的 `subject_digest` 各生成一个 key；重试复用；异常内容或 `expected_sequence` 改变时换新，冲突刷新后换新 | 成功追加后记录该异常的 `sequence` 与事件 id；重试跳过已成功记录，只处理剩余异常；开始归档请求使用已记录的 anomaly refs | `infrastructure/control_db/schema.py:793+`（`archive_anomaly_resolution_events` 同样两个 UNIQUE）；`application/archive/audit.py:238–246`；`application/archive/contracts.py:312–365` |
| 开始归档 `POST /v1/archives` | 所有确认与异常处理成功后、首次发“开始归档”时生成 `startKey`；同一次选择与同一组 refs 的重试复用；选择、候选摘要或 refs 改变时换新，刷新预检后换新 | 受理后记录 `operation_id`/归档结果；请求丢失时用同一 key 与同一组 refs 重发，后端按已保存计划回放。已成功的确认与异常处理不重发 | `application/archive/start.py:80–139`（按 key 查已保存计划，指纹不符报 `IDEMPOTENCY_CONFLICT`，匹配则回放）；`application/archive/contracts.py:367+`（开始指纹含 `candidate_set_digest`、选中集、排序后的 confirmation/anomaly refs） |

实现约定：

- 归档 journey 接受一个可变的进度对象（按 subject 的 key、已追加的 sequence、开始 key、开始结果），对话框在重试之间保留它；失败不会清空已成功的记录。
- 只有确定 4xx（408 与 429 除外）、`IDEMPOTENCY_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT` 或用户改变输入时，才丢弃对应步骤的 key 并刷新；网络错误、超时、5xx、429 一律保留 key 重试。
- 单元测试固定两条：两个异常各自使用自己的 key 与序号；开始归档失败后重试不重发确认/异常处理，并使用同一 `startKey`。
