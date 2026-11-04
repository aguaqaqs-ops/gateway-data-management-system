# FE2c 定向修复 handoff — B1–B11 / M1–M7

- 修复范围：`5830bc73c4..41081b87`（05 detached worktree `/home/dev/gdds-fe2c-fix-05`，9 个提交）。
- 审核报告：`/tmp/fe2c-review.md`（结论定向修复，B1–B11 + M1–M7，复审范围 `5830bc73c4..41081b87`）。
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
| `41081b87` | docs：本 handoff（`41081b87` runner exit 0，125 tests + 21 e2e + 64 png） |
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

- 命令：`bash frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-evidence/fe2c/fix-ec34b134-05`（05 detached `ec34b134`，clean；`GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`，archive `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，`GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a6f62218109783674cfc37bd64e14a5`）。
- 日志：`/home/dev/gdds-fe-logs/frontend/frontend-tests-20261104T080840Z.log`，SHA256 `cf5d40d3b6ec8b0ed83af1e8d8604485b8d6618eff95ad658d31ddc880962bd1`；`started_at=2026-11-04T08:08:40Z`，`ended_at=2026-11-04T08:09:15Z`，`hostname=gw-dms-test-05.lan`，`head_start=head_end=41081b87`，`frontend_tree=46ed8248…`，`exit_code=0`。
- 结果：typecheck 0；lint 0；27 单测文件 125 tests 通过；21/21 e2e 通过；生产构建检查通过（`production dist contains no simulated API…`）。
- 工具链/npm 缓存：`mcr.microsoft.com/playwright:v1.64.1-noble`（config `sha256:a0d7b2b4…`，7 DiffID 与既有值一致），`docker_network=none`，npm cache `source_commit=a2fb4a02`，`package_lock_resolved_count=305`，archive SHA `0d861824…`，tracked archive `f33a42c3…`（handoff 为 docs-only 增补引起变化，未改测试输入）。
- 证据目录：`/home/dev/gdds-fe-evidence/fe2c/fix-41081b87-05/`，64 png（逐文件 SHA 总和 `38946c37…`；SHA 待 04 取证时重算）。
- 失败过程（M5 要求记录）：`04d5307f`（缺 import，20/21）、`5480f51b`（B3 桩变严后确认键被初始 can_start 阻塞，20/21）、`c5d2e3ec` 通过（61 png）、`008cd90a` 通过（64 png）、`ec34b134` 通过（64 png）；本轮 `41081b87` 通过（64 png）。首次直连默认缓存路径失败（`npm cache is missing or empty: /home/dev/gdds-fe-cache/frontend/npm-cache`），改用既有 fe0 缓存 env 后重跑通过。
## 5. 探针（§9 要求，结果进 handoff）

- 本轮新增探针靶点单测（均在 05 已提交，`5c29b8d1`；本地反向验证已通过，未污染证据 HEAD）：
  - B1：`upload-package.test.ts` 去掉 size 写入 → 读回单测失败（2 failed / 9；`size` 0 ≠ 内容长）；后端 `validate_source_package_archive` 复用报告 P1/P2 结论（前端产物拒收 `UPLOAD_CLOSURE_INVALID`，Python 对照通过）。
  - B2：去掉任一步 key → 对应 422 桩使上传/归档 e2e 失败（报告 P3 已证；本轮桩保留 422 回归）。
  - B3：`NEEDS_CONFIRMATION`  fixture 改 `can_start:true` → 新增单测失败（1 failed / 7：`audit_validity:false` 与 `can_start:false` 必须同现）。
  - B6：`applyReviewAction` 内重读版本/换新 key → 新增单测失败（2 failed / 12：必须发送界面版本 + 复用传入 key，不重读 `getReviewFacts`）。
- B10：本地 `vitest run` 27/125 通过 + 本轮 05 runner 通过；报告 P4/P6 的间歇背景已由 `globalThis` 修复覆盖，更长连续次数待 04 取证时补。
## 6. 截图（64 张，`fix-41081b87-05/`）

`archive-mainline-1280/1920`、`archive-mainline-result-1280/1920`、`bundle-error-*`、`dataset-replacement-browse-*`、`formula-history/preview-*`、`header-review-*`、`history-compare-connection-interrupted/running/result-drawer-*`、`loading-skeleton-*`、`manual-recovery-required-*`、`navigation-fallback-*`、`s1-workbench-*`、`s2-compare-tray-*`、`s3-header-history/upload-*`、`s3-workbench-normal/upload-*`、`s4-grid-*`、`s4-semantic-tokens-*`、`submit-identity-confirmation-*`、`tab-overflow-*`、`upload-invalid-*`、`upload-locked-1280/1920`、`upload-selected-1280/1920`、`workspace-error-no-connected-*`。

缺少（偏差，沿用报告 §8，相对上一轮已补 3 张）：退回/撤回对话框、上传空状态/运行中卡片/失败重试、`ABORTED`、归档被阻断、写操作 403/409 单独截图。改动涉及的截图已重拍（archive-mainline、upload 阶段、submit 进度）。
## 7. 已知偏差（不能按草图修正，交 owner）

1. PREVIEW 顶栏无上传快捷入口（B7 后半）。
2. 上传打包非流式（M1 后半，大目录内存 2x）。
3. 提交摘要仍为原始 ID（M7）。
4. 截图缺项见 §6；`history-compare-result-drawer` 布局仍为小字 + 全表（未按 compare-1920 四卡片改）。
5. 上传模式“撤回”缺失（原 handoff §8.1，后端无字段，属 §10 停止条件）。

## 8. 复审与 04 取证

- 复审范围：`5830bc73c4..41081b87`（以 05 为准；本地 `fe-vnext` 仍在 `5830bc73c4` + dirty 文件，未提交，勿作证据；本 handoff 为 docs-only，测试输入与 runner 一致）。
