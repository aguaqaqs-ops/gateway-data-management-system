# Formal Contract Migration Execution Plan

本文是正式新前后端契约迁移和旧前端兼容层拆除的临时执行台账。正式 contract 来源是 `../contracts/comparison-bundle.md`、`../../shared-contracts/` 和相关 backend-vnext contract 文档；本文只记录执行顺序、准备动作、手动验证反馈和暂停条件。

## Purpose

- 指导正式 contract 迁移期间的前端准备、backend route 切换、bundle loader 切换和 compat 删除。
- 为每个执行 slice 记录自动测试、手动操作、结果反馈、差异结论和是否进入下一步。
- 防止迁移过程中把旧 formal DTO、旧 preview/workbench sidecar 或 compat read model 误提升为正式 contract。
- 保留旧实现离线 oracle 的差异分析价值，但不把旧实现作为目标兼容对象。

## Preparation

前端准备：

- 不复制整个 `gateway-data-management-system/frontend/` 目录。
- 不备份 `node_modules/`、`dist/` 或其它可再生成目录。
- 建议在开始实现前创建迁移分支，例如 `formal-contract-migration`。
- 建议在开始实现前打基线 tag 或记录基线 commit，用作回滚点。
- 前端改动按 route group 小步提交，每步提交后记录测试和手动反馈。

后端准备：

- 使用 `gateway-data-management-system/backend/.venv/` 运行后端命令。
- `removed formal app adapter` 已在 Slice 9 删除；正式入口为 `backend_vnext.api.formal_main` / `formal_app.py`。
- 新正式 app/router、operation polling、state store 和 bundle publisher 作为 formal path 维护。
- 任何旧字段进入新契约前必须标记为 core fact、derived projection、adapter-only 或 removed。

对照准备：

- 旧实现只作为离线 oracle，用于 normalized diff / risk 差异分析。
- 对照结果必须判定为旧 bug、新 bug 或 intentional change。
- 不以旧 bundle layout、旧 sidecar 文件名或旧 risk reason code 名称作为正式目标。

## Manual Testing Strategy

手测分两条线推进，推荐先完成流程与状态数据，再集中处理 diff / risk 数据查看问题。

第一线：Flow / read-model smoke。

- 目标是确认主流程能从 SSO 走到 archive、下一批和 history compare。
- 重点检查 session、workspace tree、work tree、batch、workspace、submission、archive node、history node、allowed actions 和 operation gating。
- 这一线只要求 preview/history bundle 能打开并有基本 summary，不逐表深查 diff/risk。
- 如果这一线失败，先暂停修流程和 read model，不进入 diff/risk deep check。

第二线：Diff / risk deep check。

- 在流程稳定后集中检查表列表、change kind、row inserted/deleted/updated、risk level、reason、target 和 history pair 切换。
- 重点覆盖 ordered 表、特殊表、空表、无 key 表、schema change、ignored columns 和 degraded / unsupported 状态。
- 新旧结果差异进入 normalized oracle 分析，结论必须是旧 bug、新 bug 或 intentional change。
- diff/risk 问题不应反复阻塞已通过的流程/read-model 判断，除非它影响 operation readiness、bundle closure 或 action gating。

推荐人工验收顺序：

1. Flow Smoke：SSO -> workspace -> upload -> preview open -> submit -> review -> archive -> next baseline -> history compare。
2. Read Model Audit：检查 workspace tree / work tree / batch / submission / archive / history 节点字段和状态。
3. Bundle Open Smoke：确认 preview/history bundle 可打开，summary 有值，表列表可加载。
4. Diff/Risk Deep Check：逐表和逐风险点检查展示正确性。
5. Oracle Analysis：对 diff/risk 差异做 normalized 归因。

## Execution Slices

### Slice 0: Baseline and Branch

目标：

- 建立迁移分支和基线记录。
- 确认正式 contract 文档和临时执行台账可追踪。

完成条件：

- 已记录当前 commit / tag。
- 已记录 frontend、backend 基线测试命令和结果。
- 未复制整个 frontend 目录。

### Slice 1: Shared Session and Control-plane

目标：

- 正式实现 SSO/session 与 control-plane internal gateway/batch APIs。
- 保持它们与 workspace/submission/archive/history read model 分离。

验证：

- SSO consume 后 `GET /api/session` 返回 actor、gateway、project、permissions、display_context。
- Control-plane upsert/disable/current/latest/open-batch summary 使用正式 shared contract。
- display_context 不参与权限和业务 hash。

### Slice 2: Workspace Tree

目标：

- 前端 workspace tree 切到正式 read model。
- 不再依赖 compat store 拼出的旧 tree DTO shape。

验证：

- `GET /api/workspace-tree` 能表达 gateway、current batch、baseline list、workspace、submission 和 allowed actions。
- 左侧导航和当前 workspace 选择只依赖正式 fields。
- 无 host path、repo path、cache-local ref。

### Slice 3: Upload Operation

目标：

- 上传入口收敛为 `POST /api/workspaces/{workspace_id}/uploads`。
- 前端按 operation polling gating 后续预览动作。
- 覆盖 `INITIALIZE_BASELINE`、`MODIFIED_ONLY`、`FULL`。

验证：

- `INITIALIZE_BASELINE` 不被解释为 modified 相对空表 diff。
- `MODIFIED_ONLY` 在 baseline source artifact 无法解析时明确 unresolved，不伪造 before。
- `FULL` 主链路为 `initial -> modified`，baseline initial diagnostics 不反向改写主 preview facts。
- READY 后 preview refs 和 bundle download metadata 可解析。

### Slice 4: Submit Polling

目标：

- Submit 改为异步 finalize command。
- `Submission(PENDING_REVIEW)` 只在 submit operation READY 后创建。

验证：

- `POST /api/submissions` 返回 operation。
- `GET /api/operations/{operation_id}` 的 status / phase 足以驱动前端 gating。
- finalize 失败时 workspace 不被伪装成 review-ready。
- submit source package 和 preview upload package digest 不要求相等。

### Slice 5: Review

目标：

- 前端 review action 切到正式 submission 状态机。
- approve 不触发 archive。

验证：

- `PENDING_REVIEW -> IN_REVIEW -> APPROVED` 可完成。
- withdraw / reject 后 workspace 重新开放，并要求重新生成 preview token。
- review action 不依赖旧 actor body；public actor 来自 session。

### Slice 6: Archive Mainline

总原则：

- Slice 6 先按子功能迁移旧后端 archive 语义，再迁移整体 formal API 和前端 journey。
- 旧后端 archive 功能语义是验收标准；新设计可以简化模型，但不能简化功能。
- 异常 initial / modified、多提交链路、组态时间与提交时间异常判据、人工 resolution、initial history 保留都必须迁移。
- Archive execute 必须真实 promote mainline，并且 required archive tasks 全部完成后才能标记 operation READY。

#### Slice 6.0: Archive Parity Audit

目标：

- 梳理旧后端 archive 子功能和测试场景，形成 vNext parity matrix。
- 区分 vNext 已有模型字段、已实现逻辑和仍缺失的旧语义。

验证：

- parity matrix 覆盖正常归档、异常 initial、异常 modified、多提交链路、pending/incomplete summary、人工 resolution、initial history archive node。
- 明确哪些旧测试要迁移到 `tests/backend_vnext/`，哪些旧 contract test 保留为 oracle。

#### Slice 6.1a: Configuration Generated Time Source Chain

目标：

- 从原始 SQL `version_manager.saved_time` 提取 `configuration_generated_at`。
- 将该字段写入 vNext `SnapshotSummary`，并在 submit finalize 后固化到 repository commit/ref hidden summary table。
- 确认 repository ref materialization/readback 能从 FINAL/protected summary 恢复该字段。

验证：

- upload preview 可携带 provisional summary，但 archive 判据不能只依赖 provisional summary、operation-local summary file 或可重算 cache。
- archive 可用的时间事实必须来自 FINAL hidden summary table 或等价 protected summary record。
- 缺表、缺列、空值或解析失败时保持 `null`，只跳过受影响的时间 abnormal 判定，不用提交/审核/归档/operation 时间替代。

#### Slice 6.1b: Batch Graph / Snapshot Summary 判据迁移

目标：

- 在 vNext archive domain 中实现旧后端 batch graph 和 snapshot summary 判据。
- 从 baseline FINAL/protected summary、submission initial/modified FINAL/protected summary、配置生成时间、提交时间和 digest 关系推导归档可行性。

验证：

- `UNRESOLVED_INITIAL_STATE`、`TIME_ABNORMAL_INITIAL`、`TIME_ABNORMAL_MODIFIED`、pending/incomplete summary 均能被自动判定。
- 多提交 initial/modified 链路能解释上下游关系，只阻塞真正异常的 root initial。

#### Slice 6.2: Anomaly Resolution 与 Candidate 选择闭环

目标：

- 迁移人工 anomaly resolution 对 batch graph 阻塞条件的解除逻辑。
- 支持异常 initial 作为 `BASELINE_INITIAL_HISTORY` 被选择和保留。

验证：

- manual external change / abnormal modified / incomplete summary resolution 能解除对应阻塞。
- mainline modified 与 initial history 组合选择规则完整，candidate hash 和 confirmation hash 防止 stale execute。

#### Slice 6.3: Archive Execute Domain Flow

目标：

- 在 vNext domain/flow 内完成 promote mainline、baseline archive nodes 创建、archive status 更新和 batch close。
- 将 archive snapshot materialization 作为 archive operation 内 required async task。
- 为未来压缩数据包、远传等并行/串行 post-archive tasks 预留 task projection；required task 全部完成后才 READY。

验证：

- execute 返回 `ARCHIVE_PROMOTE` operation，后台执行 promote 与 required tasks。
- READY 后 mainline 真实推进，`MAINLINE_MODIFIED` 和 `BASELINE_INITIAL_HISTORY` archive nodes 正确持久化。
- 失败时记录 frozen / retryable / final 语义，不伪造成功。

#### Slice 6.4: Formal Archive API 迁移

目标：

- 将 archive snapshot、anomaly resolution、candidate、confirmation、selection、dry-run、execute 和 execution records 接入 `formal_app.py`。
- Formal route 只做 session/access、DTO mapping 和 ErrorEnvelope，不在 route 中重写 archive 判据。
- Archive execute 继续使用 6.3 的同步 domain flow；operation envelope / required task READY gating 后续单独切片。

验证：

- public actor、gateway、project、permissions 只从 signed session cookie 和 control-plane session context 得到。
- formal app/helper 不 import `removed formal app adapter`。
- formal archive responses 不暴露 host path、repo path、cache-local ref、debug-only 字段。

#### Slice 6.5: Frontend Archive Journey 与异步进度

前置状态：

- Formal archive execute 已接入 `ARCHIVE_PROMOTE` operation gating。
- Execute route 同步完成 hash/selection/graph precheck；precheck 通过后返回 operation envelope。
- Operation READY 前不发布 execution record、archive nodes、batch closeout 或 next batch。
- Workspace tree `active_operations` 可展示 in-flight archive operation。
- Formal session archive execute 已按 submit 模式轮询 `/api/operations/{operation_id}`，并从 READY `ready_result` 消费 archive execute payload。
- Workspace tree 对 `ARCHIVE_PROMOTE` 提供 archive 排队/执行中/完成/失败标签。

目标：

- 前端 archive journey 使用 formal archive routes 和 operation-gated execute path。
- Normal pass path 保持一键归档；pending summary、needs confirmation、integrity block、多 workspace confirmation 或 graph anomaly 自动进入 review panel。
- Review panel 承载 diagnostics refresh、anomaly resolution、`BASELINE_INITIAL_HISTORY` candidate、selection、dry-run 和 archive operation polling。
- archive execute 使用 operation polling，并在 workspace header/tree 显示 batch/workspace/submission 对应进度。
- 已有同 batch `ARCHIVE_PROMOTE` active operation 时禁用重复 execute，并展示 archive 排队/执行中状态。

验证：

- archive snapshot、confirmation、candidate、selection、dry-run、execute 主路径可完成。
- 异常 graph/reason 信息继续驱动人工确认和解释。
- operation READY 后刷新 formal tree，展示 closed batch、next batch、mainline archive node 和 baseline initial history node。
- batch 关闭/下一批打开仍沿用后端/control-plane 行为；前端只刷新和展示结果。

### Slice 7: History Compare

目标：

- History compare 使用 vNext formal session routes 和只读 operation/read model。
- READY 前不返回半成品 bundle 或 workbench download refs。

验证：

- 请求只接受业务节点：`BASELINE_MAINLINE`、`BASELINE_INITIAL_HISTORY`、`SUBMISSION_MODIFIED`。
- 不接受 Dolt ref、commit hash、host path、cache ref 或 `table_names`。
- 2 节点和 3 节点 pair plan 都可完成。
- READY 后返回 `history-comparison-bundle/v1` metadata 和 download refs。
- Archived `BASELINE_INITIAL_HISTORY` node 可作为独立 history compare 输入。
- Direct formal bundle loader 仍留给 Slice 8；本轮继续通过 workbench bundle download 打开只读历史比较。

### Slice 8: Bundle Loader

目标：

- 前端 bundle loader 从 preview/workbench-compatible sidecars 切到正式 `ComparisonBundle` / `ComparisonSurface`。
- Formal history compare Workbench 直接下载 `comparison_bundle_download`，不再使用 workbench-compatible sidecar。

验证：

- 表导航、diff 浏览、risk 浏览、diagnostics 和 history pair 切换均从正式 bundle/artifact refs 派生。
- 不再读取 `old history workbench manifest`、legacy aliases 或 synthetic preview identity。
- bundle 不暴露 host path、repo path 或 cache-local ref。
- Row-level diff artifact 面向前端使用 Parquet；JSON 仅用于 manifest、surface、closure、risk report 等 metadata。
- Non-READY history compare 不发布 formal bundle download/artifact。

### Slice 9: Compat Deletion

目标：

- 清理已迁移完成的流程控制兼容层，让正式路径只保留 formal API、formal state store、formal operation/read model。

完成边界：

- 删除旧 `removed formal app adapter` / `removed formal main adapter` 入口、compat route tests 和 active compat smoke runbook。
- 将事实上的正式 read model 从 `formal_state_store.py` 迁名为 `formal_state_store.py`。
- 将同步 wait helper 从 `formal_operation_wait.py` 迁名为 `formal_operation_wait.py`，错误文案不再使用 compatibility 表述。
- 将 formal session security 从 `formal_security.py` 迁名为 `formal_security.py`。
- 删除 removed history adapter、legacy history download field、old history route 和前端 `source_kind="history_comparison"` 分支。

保留边界：

- Upload preview / baseline diagnostics 仍使用 preview-compatible bundle sidecar，后续 bundle/data-surface cleanup 再处理。
- 旧非 vNext runtime 的 history workbench publisher 不在本 slice 范围内。
- normalized diff / risk oracle 差异继续作为后续数据面 cleanup 输入，不阻塞流程兼容层删除。

## Manual Feedback Log

每个 slice 完成后追加记录：

```text
Date:
Slice:
Operator:
Environment:
Backend command(s):
Frontend command(s):
Manual actions:
Expected:
Actual:
Flow/read-model result:
Bundle open smoke result:
Diff/risk result:
Artifacts:
Normalized diff/risk oracle result:
Decision: continue | pause | rollback
Follow-up:
```

```text
Date: 2026-07-09 CST +0800
Slice: Archive READY Boundary / Next Baseline Publish Fix
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
Expected:
  Formal archive execute performs synchronous precheck, then keeps archive state unpublished until required baseline source preparation succeeds.
  In-flight ARCHIVE_PROMOTE operations block upload/archive entry points.
Actual:
  Added PREPARE_NEXT_BASELINE_SOURCE before execute_archive_mainline in the formal archive operation.
  The preparer probes the selected mainline submit source package artifact through preview materialization before batch closeout/next baseline opening.
  Preparation failure leaves the current batch OPEN/READY_FOR_ARCHIVE and publishes no execution, archive node, or next batch.
  Operation resource refs now include blocks_upload=true; the formal frontend blocks upload while ARCHIVE_PROMOTE is active.
Decision:
  Large upload parse/diff performance remains a separate follow-up; this slice only fixes the archive READY publish boundary.
```

```text
Date: 2026-07-11 CST +0800
Slice: Ordered Provider Hot Path prepare/digest/replay experiment rollback
Operator: Codex
Expected:
  Evaluate whether small object-copy optimizations in ordered prepare/digest/replay reduce FULL comparison_core time.
  Preserve ordered semantics, records payload, risk payload, frontend API, projection contract, and bundle refs.
Experiment:
  Tried tuple/list index fast paths in prepare_ordered_rows.
  Tried reducing replay_validation row flattening/copies by passing OrderedPreparedRow sequences.
  Tried ordered row digest streaming, then reverted it immediately because per-field canonical JSON calls were slower than the existing single payload digest.
Backend command(s):
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_compute_stage7.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
Actual:
  The retained prepare/replay changes produced only noise-level improvement in comparison_core and ordered_provider.
  The extra complexity was not justified, so the prepare/replay changes, benchmark counter additions, and experiment-only tests were rolled back.
Benchmark result:
  large INITIALIZE_BASELINE upload.total: 18001 ms.
  large-1 + large-2 FULL upload.total: 47403 ms.
  FULL comparison_core.total: 18449 ms, essentially flat against the prior ~18527 ms baseline.
  FULL ordered_provider total: 18275 ms, essentially flat against the prior ~18403 ms baseline.
  Ordered phase totals: prepare_rows 1741 ms, ordered_digest 3086 ms, replay_validation 277 ms.
Decision:
  Do not retain or retry this micro-optimization direction.
  The next meaningful optimization should target projection_build reuse/cost, ordered algorithmic changes, or comparison parallelism rather than small object-copy reductions.
```

```text
Date: 2026-07-06 CST +0800
Slice: 8 Bundle Loader
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter tests/backend_vnext/unit/test_history_compare_flow.py tests/unit/test_history_compare_operations.py tests/unit/test_history_comparison_compute.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/localWorkbenchBundle.test.js src/data/previewTableData.test.js src/data/workspaceApi.test.js
  npm run build
Expected:
  Formal history compare Workbench opens from ComparisonBundle / ComparisonSurface without preview/workbench-compatible sidecars.
  Frontend-facing row diff artifacts use Parquet.
Actual:
  Formal history compare READY payload now exposes comparison_bundle_download.
  Formal bundle tar contains manifest, artifact closure, pair surfaces, table surfaces, risk metadata, and Parquet records when records exist.
  Frontend formal history compare path downloads/stores the formal bundle and adapts surfaces into the read-only Workbench model.
Flow/read-model result:
  Non-READY history compare keeps bundle/download null and bundle artifact routes return not-ready errors.
Bundle open smoke result:
  Formal path no longer consumes old history workbench manifest, preview_index.json, diff_summary.json, or synthetic preview identity.
Diff/risk result:
  Formal records-only tables read Parquet diff records through the Workbench table data path.
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_app.py
  gateway-data-management-system/backend/backend_vnext/api/formal_state_store.py
  gateway-data-management-system/frontend/src/data/localWorkbenchBundle.ts
  gateway-data-management-system/frontend/src/data/previewTableData.ts
  gateway-data-management-system/frontend/src/App.tsx
Normalized diff/risk oracle result:
  not run
Decision: Slice 8 formal bundle loader complete for the formal history compare path
Follow-up:
  Slice 9 can remove compat/debug history sidecars after full journey smoke confirms no remaining formal frontend dependency.
```

```text
Date: 2026-07-07 CST +0800
Slice: 9 Compat Deletion / Formal Flow Cleanup
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_history_compare_flow.py tests/unit/test_history_compare_operations.py tests/unit/test_history_comparison_compute.py tests/backend_vnext/unit/test_submit_finalize_flow.py tests/backend_vnext/unit/test_upload_preview_flow.py tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py
  cd /home/issac/test-dir/fasttest-mysql
  gateway-data-management-system/backend/.venv/bin/pytest -q control-plane-system/backend/tests/test_api.py::test_control_plane_create_gateway_and_sso_smoke_against_gateway_vnext_formal_app
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/localWorkbenchBundle.test.js src/data/previewTableData.test.js src/data/formalWorkspaceState.test.js src/components/HistoryCompareView.test.js
  npm run build
Expected:
  Formal flow no longer depends on the old adapter app/main or removed history download path.
Actual:
  Deleted formal adapter app/main, renamed formal store/wait/security modules, and removed history adapter routes.
Flow/read-model result:
  Formal history compare READY path publishes comparison_bundle_download only.
Bundle open smoke result:
  Formal frontend opens history compare through history_comparison_bundle source only.
Diff/risk result:
  unchanged; upload preview sidecar cleanup remains deferred.
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_app.py
  gateway-data-management-system/backend/backend_vnext/api/formal_state_store.py
  gateway-data-management-system/backend/backend_vnext/api/formal_operation_wait.py
  gateway-data-management-system/backend/backend_vnext/api/formal_security.py
  gateway-data-management-system/frontend/src/data/localWorkbenchBundle.ts
  gateway-data-management-system/frontend/src/data/workspaceApi.ts
Normalized diff/risk oracle result:
  not run
Decision: Slice 9 formal flow compat deletion complete
Follow-up:
  Bundle/data-surface cleanup can separately address upload preview sidecars, formal surface slimming, and diff/risk contract hardening.
```

记录规则：

- `Artifacts` 可写截图路径、日志路径、operation id、bundle id 或测试报告路径。
- `Flow/read-model result` 用于记录主流程、tree/work tree、operation gating 和状态字段。
- `Bundle open smoke result` 只记录 bundle 是否能打开、summary 和表列表是否可加载。
- `Diff/risk result` 可在后续集中补录；若尚未深查，写 `deferred`。
- 如果 `Decision=pause`，必须写明暂停条件和下一步调查方向。
- 如果出现新旧 diff/risk 差异，必须归类为旧 bug、新 bug 或 intentional change 后再继续。

## Pause Conditions

遇到以下情况必须暂停，不继续切下一 slice：

- 新旧 normalized diff / risk 结果差异无法解释。
- Operation status / phase 不足以前端判断下一步动作。
- READY 前需要读取半成品 bundle 才能维持 UI。
- `INITIALIZE_BASELINE` 被误处理为相对空表 diff。
- `MODIFIED_ONLY` 在 baseline source unresolved 时伪造 before。
- Submit finalize 失败但 workspace/submission 被展示成可 review。
- Archive 异常判据未与旧后端 parity 对齐，却继续推进 formal API 整体迁移。
- Archive execute 只更新 read model，未真实 promote mainline。
- Archive execute operation 在 required archive tasks 全部完成前标记 READY。
- History compare 暴露 Dolt ref、commit hash、host path 或 cache ref。
- Frontend client 仍必须依赖旧 DTO shape 才能完成主路径。
- Bundle loader 无法从正式 artifact refs 完成 diff/risk 浏览。
- compat 删除会影响 vNext core facts、cache key、digest、repository state 或正式 artifact identity。

## Verification Matrix

| Slice | Backend checks | Frontend checks | Manual checks | Oracle / artifact checks |
| --- | --- | --- | --- | --- |
| 0 Baseline | baseline backend tests | baseline frontend tests | record branch/tag | none |
| 1 Session/control-plane | shared contract/API tests | session client tests | SSO enter workspace | no host/debug fields |
| 2 Workspace tree | workspace read model tests | tree state tests | navigate batches/workspaces | action gating fields complete |
| 3 Upload | upload operation/flow tests | upload state gating tests | INITIALIZE/MODIFIED/FULL uploads | normalized diff/risk compare |
| 4 Submit | submit operation/finalize tests | submit polling tests | submit and wait READY | source/binding digests verified |
| 5 Review | submission state tests | review action tests | start/approve/reject/withdraw | no archive side effect |
| 6.0 Archive parity audit | old archive use-case inventory | none | review staged plan | parity matrix complete |
| 6.1 Archive batch graph | batch graph / summary tests | none | inspect anomaly reasons | old archive oracle aligned |
| 6.2 Archive resolution/selection | anomaly resolution / candidate tests | archive panel state tests | select abnormal initial history | stale hash and resolution checks |
| 6.3 Archive execute flow | archive flow/promote task tests | operation projection tests | dry-run/execute | mainline promoted and required tasks READY |
| 6.4 Formal archive API | formal route/ErrorEnvelope tests | archive API client tests | formal archive command smoke | no compat import or debug fields |
| 6.5 Frontend archive journey | formal archive integration tests | archive polling/UI tests | archive and open next batch | archive nodes and operation gating |
| 7 History compare | history operation tests | history polling tests | 2/3 node compare | history bundle closure |
| 8 Bundle loader | bundle/artifact tests | bundle loader tests | browse diff/risk/history pairs | no legacy sidecars required |
| 9 Compat deletion | full journey tests | full E2E smoke | complete journey | no compat route/file dependency |

## Compat Deletion Checklist

- [x] Frontend route usage audit shows no dependency on formal adapter routes.
- [x] Frontend bundle loader no longer reads preview/workbench-compatible sidecars for formal history compare.
- [x] Backend journey test does not import `removed formal app adapter`.
- [x] No formal contract tests depend on `formal_state_store.py`.
- [x] Operation polling replaces compat synchronous wait behavior.
- [ ] Archive execute uses formal repository mainline promote.
- [ ] History compare uses formal read-only operation and bundle.
- [x] Adapter-only golden tests have been migrated to formal contract tests or deleted.
- [x] Formal adapter runbook has been archived or removed from active execution docs.

## Manual Feedback Entries

```text
Date: 2026-07-04 15:56:10 CST +0800
Slice: 0 Baseline and Branch
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch before migration branch: main
  migration branch: formal-contract-migration
  upstream state before branch: main...origin/main [ahead 12]
  baseline code commit: d2291c26989aa23243850c27d1ed16cd4a6771fb
  tag at baseline code commit: none
  python: Python 3.12.12 via gateway-data-management-system/backend/.venv/
  node: v24.12.0
  npm: 11.7.0
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test
  npm run build
Manual actions:
  none
Expected:
  Record current commit/tag, frontend baseline checks, backend baseline checks, and frontend copy status.
Actual:
  Frontend npm test passed: 142 passed, 0 failed.
  Frontend npm run build passed with Rollup PURE annotation warnings from @glideapps/glide-data-grid and one chunk-size warning.
  Backend pytest completed with known baseline red point: 845 passed, 1 failed, 2 skipped, 4 warnings in 820.08s.
  Known backend baseline failure:
    tests/backend_vnext/integration/test_snapshot_materialization_parallelism_benchmark.py::test_snapshot_materialization_large_preview_finalize_benchmark
    finalized preview snapshot_digest != full materialization snapshot_digest.
  No copied gateway frontend directory was found; only the existing gateway-data-management-system/frontend, control-plane-system/frontend, and docs/frontend directories are present.
Flow/read-model result:
  not run in Slice 0
Bundle open smoke result:
  not run in Slice 0
Diff/risk result:
  deferred
Artifacts:
  none
Normalized diff/risk oracle result:
  not run in Slice 0
Decision: continue
Follow-up:
  Track the snapshot digest mismatch as a known baseline issue. It does not block Slice 1.
  Use focused Slice 1 backend checks for session/control-plane work and reserve full backend pytest for the next larger integration checkpoint.
```

```text
Date: 2026-07-04 16:31:15 CST +0800
Slice: 1 Shared Session and Control-plane
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
  baseline tag: formal-contract-migration-baseline-20260704
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/contract/test_control_plane_session.py tests/contract/test_internal_gateway_device_upsert.py tests/contract/test_internal_baseline_batch_commands.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  none
Expected:
  Add a vNext formal API entry for shared session and control-plane gateway/batch contracts without deleting or rewriting removed formal app adapter.
Actual:
  Added backend_vnext/api/formal_app.py as a formal vNext API entry for SSO/session and control-plane internal gateway/batch routes.
  Added backend_vnext unit coverage for formal app session cookie shape, display_context presentation-only behavior, internal route error envelopes, missing/disabled gateway handling, and no direct removed_formal_app_adapter import.
  Backend new formal app tests passed: 4 passed.
  Backend focused contract tests passed: 12 passed.
  Backend formal adapter app regression passed: 45 passed.
  Frontend npm test command passed: 142 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  automated session/control-plane route checks passed; full flow smoke not run
Bundle open smoke result:
  not run in Slice 1
Diff/risk result:
  deferred
Artifacts:
  none
Normalized diff/risk oracle result:
  not run in Slice 1
Decision: continue
Follow-up:
  Manual SSO enter-workspace smoke remains before broader Slice 2 work.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-04 17:13:24 CST +0800
Slice: 1 Shared Session and Control-plane manual smoke addendum
Operator: User
Environment:
  branch: formal-contract-migration
Backend command(s):
  not recorded
Frontend command(s):
  not recorded
Manual actions:
  Created gateway manually through control-plane.
  Entered gateway workspace through SSO/session flow.
  Confirmed workspace page loaded and Dolt tree was visible.
Expected:
  SSO/session and control-plane gateway setup allow entering workspace before Slice 2.
Actual:
  Gateway creation succeeded.
  Workspace entry succeeded.
  Dolt tree displayed.
Flow/read-model result:
  pass for Slice 1 manual SSO enter-workspace smoke
Bundle open smoke result:
  not applicable to Slice 1
Diff/risk result:
  deferred
Artifacts:
  none recorded
Normalized diff/risk oracle result:
  not run in Slice 1
Decision: continue
Follow-up:
  Conditions are met to enter Slice 2 Workspace Tree.
```

```text
Date: 2026-07-04 17:21:05 CST +0800
Slice: 2 Workspace Tree automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/formalWorkspaceState.test.js src/data/workspaceApi.test.js
  npm run build
Manual actions:
  none
Expected:
  Expose formal vNext GET /api/workspace-tree without relying on removed formal app adapter route shape.
  Workspace tree response expresses gateway, current batch, baseline list, actor workspace, submissions, tree nodes and allowed actions.
  Response does not expose host path, repo path, cache-local ref, registry, operation journal or debug-only fields.
Actual:
  Added GET /api/workspace-tree to backend_vnext/api/formal_app.py.
  Route resolves actor, gateway, project and permissions from signed session/control-plane context.
  Route maps missing gateway and project mismatch to formal ErrorEnvelope responses.
  Added vNext formal app coverage for no-workspace tree, seeded actor workspace projection, display_context not granting archive_mainline, missing gateway/project mismatch errors and no host/debug/cache-local fields.
  Backend formal app tests passed: 8 passed.
  Backend formal adapter app regression passed: 45 passed.
  Frontend npm test command passed: 142 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  automated workspace tree read-model checks passed
Bundle open smoke result:
  not run in Slice 2
Diff/risk result:
  deferred
Artifacts:
  none
Normalized diff/risk oracle result:
  not run in Slice 2
Decision: continue
Follow-up:
  Manual Slice 2 acceptance remains before Slice 3: SSO enter workspace, confirm formal /api/workspace-tree succeeds, and confirm left navigation/current workspace selection works.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-04 20:28:30 CST +0800
Slice: 2 Workspace Tree manual smoke addendum
Operator: User
Environment:
  branch: formal-contract-migration
Backend command(s):
  not recorded
Frontend command(s):
  not recorded
Manual actions:
  Opened workspace tree from the formal workspace page.
  Selected a business data folder from the workspace tree/navigation.
Expected:
  Formal /api/workspace-tree succeeds and left navigation/current workspace selection works before Slice 3.
Actual:
  Workspace tree was visible.
  Business data folder selection worked.
Flow/read-model result:
  pass for Slice 2 manual workspace tree smoke
Bundle open smoke result:
  not applicable to Slice 2
Diff/risk result:
  deferred
Artifacts:
  none recorded
Normalized diff/risk oracle result:
  not run in Slice 2
Decision: continue
Follow-up:
  Conditions are met to enter Slice 3 Upload Operation.
```

```text
Date: 2026-07-04 21:01:14 CST +0800
Slice: 3 Upload Operation automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_removed formal app adapter tests/backend_vnext/unit/test_upload_preview_flow.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  none
Expected:
  Add formal POST /api/workspaces/{workspace_id}/uploads and GET /api/operations/{operation_id}.
  FULL upload is one formal request carrying initial_file and modified_file.
  INITIALIZE_BASELINE is not interpreted as an empty-table diff.
  MODIFIED_ONLY unresolved baseline source returns a terminal failed operation without marking preview ready.
  Manual process entry can use backend_vnext.api.formal_main instead of removed_formal_main_adapter.
Actual:
  Added backend_vnext/api/formal_upload.py for formal upload normalization, operation envelope mapping, preview generation and bundle metadata/artifact serving.
  Added backend_vnext/api/formal_main.py with BACKEND_VNEXT_FORMAL_* settings and default port 8001.
  Added formal app routes for /api/workspaces/current, /api/workspaces/{workspace_id}, /api/workspaces/{workspace_id}/uploads, /api/operations/{operation_id}, and preview bundle metadata/artifact.
  Frontend session FULL upload now posts one multipart /uploads request with initial_file and modified_file, then polls the formal operation contract.
  Explicit empty first-baseline upload mode is mapped to INITIALIZE_BASELINE.
  Smoke runbook now defaults to backend_vnext.api.formal_main and keeps compat main as fallback.
  Backend formal app tests passed: 11 passed.
  Backend focused command passed: 58 passed.
  Frontend npm test command passed: 144 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  automated upload operation checks passed; manual formal process smoke not run
Bundle open smoke result:
  automated preview bundle metadata/artifact route checks passed; browser bundle open smoke not run
Diff/risk result:
  deferred
Artifacts:
  none
Normalized diff/risk oracle result:
  not run in Slice 3
Decision: continue
Follow-up:
  Manual Slice 3 acceptance remains: start backend_vnext.api.formal_main, enter workspace through SSO, perform one FULL upload, confirm operation READY, preview bundle opens, and workbench shows the expected diff/risk summary.
  Submit/review/archive/history remain for later slices.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-04 21:22:54 CST +0800
Slice: 3 Upload Operation manual smoke addendum
Operator: User
Environment:
  branch: formal-contract-migration
  backend entry: backend_vnext.api.formal_main
Backend command(s):
  not recorded
Frontend command(s):
  not recorded
Manual actions:
  Started the formal main backend entry.
  Entered workspace through SSO.
  Performed the first single business-data upload.
Expected:
  Slice 3 formal upload operation supports first explicit-empty baseline initialization.
  Submit/review/archive/history are not expected to pass before later slices.
Actual:
  First INITIALIZE_BASELINE upload succeeded.
  Full journey stopped at submit because Slice 4 and later routes were not migrated yet.
Flow/read-model result:
  pass for first formal upload smoke; full flow intentionally deferred
Bundle open smoke result:
  upload preview bundle smoke passed enough to continue
Diff/risk result:
  deferred
Artifacts:
  none recorded
Normalized diff/risk oracle result:
  not run in Slice 3
Decision: continue
Follow-up:
  Conditions are met to enter Slice 4 Submit Polling.
  Full manual journey should be rerun after submit/review/archive/history slices are available.
```

```text
Date: 2026-07-04 21:32:22 CST +0800
Slice: 4 Submit Polling automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_acceptance_flow.py tests/backend_vnext/unit/test_submit_finalize_flow.py
  ./.venv/bin/python -m py_compile backend_vnext/api/formal_app.py backend_vnext/api/formal_submit.py backend_vnext/api/formal_upload.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  none
Expected:
  Add formal POST /api/submissions using signed session context, multipart source upload and operation polling.
  SUBMIT_FINALIZE operation READY creates Submission(PENDING_REVIEW) and marks the workspace submitted.
  Failed finalize or preview binding mismatch does not create a submission and does not mark the workspace submitted.
  Frontend formal session submit sends one multipart command and polls /api/operations/{operation_id}.
Actual:
  Added backend_vnext/api/formal_submit.py for formal submit normalization, preview/binding validation, submit acceptance/finalize, and READY operation mapping.
  Formal app POST /api/submissions now returns the shared operation envelope and GET /api/operations/{operation_id} serves upload/submit operations from the shared operation store.
  Submission is created only after finalize READY; failed finalize returns a terminal operation without mutating workspace submission state.
  Submit source package digest is allowed to differ from the preview upload package digest; optional expected_source_payload_sha256 validates only the current multipart body payload sha.
  Frontend submitWorkspaceFromSession now posts multipart /api/submissions and polls the formal operation contract until READY or terminal failure.
  Backend formal app tests passed: 14 passed.
  Backend compat formal app tests passed: 45 passed.
  Backend submit acceptance/finalize tests passed: 8 passed.
  Frontend npm test command passed: 146 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  automated submit polling checks passed; manual formal process smoke not run
Bundle open smoke result:
  not run in Slice 4
Diff/risk result:
  deferred
Artifacts:
  none
Normalized diff/risk oracle result:
  not run in Slice 4
Decision: continue
Follow-up:
  Manual Slice 4 acceptance remains: start backend_vnext.api.formal_main, SSO into workspace, complete INITIALIZE_BASELINE upload, click Submit, confirm operation READY, and verify workspace tree/read model shows PENDING_REVIEW submission.
  Review/archive/history remain for later slices.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-04 21:53:35 CST +0800
Slice: 5 Review automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/python -m py_compile backend_vnext/api/formal_app.py backend_vnext/api/formal_review.py backend_vnext/api/formal_submit.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/unit/test_submission_use_cases.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  none
Expected:
  Add formal POST /api/submissions/{submission_id}/review-actions using signed session context.
  START_REVIEW / APPROVE / REJECT use review_submission permission; WITHDRAW allows the submitter to reopen its pending submission without review permission.
  APPROVE does not trigger archive or promote mainline.
  REJECT / WITHDRAW reopen the workspace and clear latest preview so a fresh preview token is required before resubmit.
  Frontend formal session review helpers send the unified review command without actor_id and unwrap READY action envelopes.
Actual:
  Added backend_vnext/api/formal_review.py for formal review action envelope mapping and state transition error handling.
  Formal app added GET /api/submissions/{submission_id} and POST /api/submissions/{submission_id}/review-actions with formal ErrorEnvelope failures.
  Frontend session review helpers now call /review-actions with action-only JSON and preserve the existing { submission, workspace } caller shape.
  Backend formal app tests passed: 20 passed.
  Backend compat formal app tests passed: 45 passed.
  Backend submission use-case tests passed: 45 passed.
  Frontend npm test command passed: 148 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  automated review state machine checks passed; manual formal process smoke not run
Bundle open smoke result:
  not run in Slice 5
Diff/risk result:
  deferred
Artifacts:
  none
Normalized diff/risk oracle result:
  not run in Slice 5
Decision: continue
Follow-up:
  Manual Slice 5 acceptance remains: start backend_vnext.api.formal_main, SSO into workspace, complete INITIALIZE_BASELINE upload, submit to PENDING_REVIEW, start review, approve, and confirm workspace tree/read model shows APPROVED without archive execution.
  Run a separate reject or withdraw smoke to confirm workspace reopens and requires a fresh preview token.
  Archive/history remain for later slices.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-05 10:10:55 CST +0800
Slice: 5.5 Submit True Async Correction automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/python -m py_compile backend_vnext/api/formal_app.py backend_vnext/api/formal_submit.py backend_vnext/api/formal_review.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_acceptance_flow.py tests/backend_vnext/unit/test_submit_finalize_flow.py
  ./.venv/bin/pytest -q tests/unit/test_submission_use_cases.py
  ./.venv/bin/pytest -q tests/contract/test_formal_workspace_tree.py tests/contract/test_formal_workspace_workflow_routes.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  none
Expected:
  POST /api/submissions creates and returns a SUBMIT_FINALIZE operation without running finalize to completion in the request thread.
  Background finalize creates Submission(PENDING_REVIEW) only after operation READY.
  Failed background finalize leaves workspace unsubmitted and creates no submission.
  Duplicate in-flight submit for the same workspace returns the existing operation.
  Frontend formal submit polling exposes operation status/phase updates to task progress.
Actual:
  Formal submit now stages/accepts in the request path, returns a QUEUED operation envelope, and runs finalize in a process-local ThreadPoolExecutor.
  READY operation publish replaces the operation result with the formal submit ready_result and then creates the PENDING_REVIEW submission.
  Failed finalize returns terminal failed operation without submitting the workspace.
  Formal app registers submit-service shutdown cleanup.
  Frontend submitWorkspaceFromSession accepts onOperationUpdate and App uses it to show queued/running/ready/failed submit progress.
  Backend formal app tests passed: 21 passed.
  Backend compat formal app tests passed: 45 passed.
  Backend submit acceptance/finalize tests passed: 8 passed.
  Backend submission use-case tests passed: 45 passed.
  Backend formal workspace contract tests passed: 17 passed.
  Frontend npm test command passed: 148 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  automated async submit checks passed; manual formal process smoke not run
Bundle open smoke result:
  not run in Slice 5.5
Diff/risk result:
  deferred
Artifacts:
  none
Normalized diff/risk oracle result:
  not run in Slice 5.5
Decision: continue
Follow-up:
  Manual Slice 5.5 acceptance remains: start backend_vnext.api.formal_main, SSO into workspace, upload INITIALIZE_BASELINE, click Submit, confirm UI shows queued/running finalize progress, then poll reaches READY and workspace tree/read model shows PENDING_REVIEW submission.
  Re-run Slice 5 review smoke after async submit: START_REVIEW -> APPROVE.
  Archive/history remain for later slices.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-05 10:42:00 CST +0800
Slice: 5.6 Upload Preview Ready Sync + Cache Completion Async automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_acceptance_flow.py tests/backend_vnext/unit/test_submit_finalize_flow.py
  ./.venv/bin/pytest -q tests/unit/test_submission_use_cases.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  none
Expected:
  Formal upload keeps preview readiness synchronous: parsing, materialization, diff/risk compute, preview bundle generation, and workspace.latest_preview are complete before /uploads returns READY.
  Comparison core cache completion is split from preview readiness and runs as a non-blocking background operation.
  Workspace tree exposes formal active/background operation projections without host/debug/cache-local fields.
  Frontend shows cache completion as non-blocking header/tree status while still allowing diff view and submit after upload READY.
Actual:
  UploadPreviewFlowInput can skip synchronous ASYNC_COMPARISON_CORE_CACHE_COMPLETION while still publishing READY preview outputs.
  Formal upload calls upload preview with cache completion skipped, returns UPLOAD_PREVIEW READY, then starts PREVIEW_CACHE_COMPLETION in a process-local ThreadPoolExecutor.
  PREVIEW_CACHE_COMPLETION operation uses formal resource_refs including workspace_id, preview_bundle_id, blocks_preview=false, and blocks_submit=false.
  /api/workspace-tree now includes active_operations for upload cache completion and in-flight submit finalize operations.
  Frontend formal tree view attaches operation badges to workspace nodes and displays a compact operation strip in the tree header.
  Backend upload preview tests passed: 3 passed.
  Backend formal app tests passed: 22 passed.
  Backend compat formal app tests passed: 45 passed.
  Backend submit acceptance/finalize tests passed: 8 passed.
  Backend submission use-case tests passed: 45 passed.
  Frontend npm test command passed: 149 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  automated sync-preview/background-cache checks passed; manual formal process smoke not run
Bundle open smoke result:
  automated preview bundle metadata/artifact checks passed
Diff/risk result:
  preview bundle remains available immediately after upload READY
Artifacts:
  none
Normalized diff/risk oracle result:
  not run in Slice 5.6
Decision: continue
Follow-up:
  Manual Slice 5.6 acceptance remains: start backend_vnext.api.formal_main, SSO into workspace, upload INITIALIZE_BASELINE/FULL, confirm diff view opens immediately after upload READY, and confirm any cache optimization indicator is non-blocking.
  Submit async smoke remains: click Submit, confirm queued/running finalize progress, then READY creates PENDING_REVIEW.
  Archive/history remain for later slices.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-05 11:05:00 CST +0800
Slice: 5.6 Submit UI non-blocking correction automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  none; frontend-only correction
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  user reported formal submit UI still showed the strict backend-processing modal and blocked interaction
Expected:
  Formal session submit remains asynchronous and visible, but does not use the blocking StrictTaskModal path.
  Header shows queued/running/ready/failed submit status while diff viewing and navigation remain available.
  Duplicate submit is still guarded while the submit operation is in flight.
Actual:
  Formal session submit was split from the global taskState/StrictTaskModal path in App.tsx.
  Submit operation polling now updates a non-blocking header status pill.
  Only the submit button is guarded by the local in-flight submit operation state.
  Dev/test submit and other strict task flows remain unchanged.
  Frontend npm test command passed: 149 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  frontend async submit UI correction passed automated checks; manual confirmation pending
Decision: continue
Follow-up:
  Manual retest formal submit: click Submit from diff view, confirm no locked StrictTaskModal appears, header shows submit progress, and diff/table navigation remains usable while backend finalize/import runs.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-05 11:22:00 CST +0800
Slice: 5.6 Workspace tree active-operation auto-refresh automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  none; frontend-only correction
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  user reported workspace tree shows non-blocking operation state but does not automatically refresh during async phases; header network indicator was not backed by formal API status
Expected:
  Workspace tree auto-refreshes only while formal active_operations contains QUEUED/RUNNING async operations.
  Auto-refresh respects operation poll_after_ms with frontend min/max throttling to avoid excessive load.
  Silent polling does not clear the current tree on transient failures.
  Header connection indicator reflects recent formal API refresh success/failure rather than browser navigator online alone.
Actual:
  FormalWorkspacePage now derives refresh interval from active_operations and polls silently only during active async operation phases.
  Refresh interval is clamped between 1000ms and 5000ms, and overlapping refreshes are skipped.
  FormalWorkspaceTree header now receives connectionStatus/connectionDetail and renders checking/online/offline status.
  Frontend npm test command passed: 149 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  frontend active-operation polling and API-backed connection indicator passed automated checks; manual confirmation pending
Decision: continue
Follow-up:
  Manual retest workspace tree during PREVIEW_CACHE_COMPLETION or SUBMIT_FINALIZE active operation: confirm operation badges refresh automatically and stop polling after terminal state.
  Confirm connection indicator turns online after successful /api/workspace-tree refresh and offline on formal API failure.
```

```text
Date: 2026-07-05 13:49:49 CST +0800
Slice: 5.7 Formal connection status and async refresh UX correction automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  none; frontend-only correction
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  user reported submit async polling made the workspace tree connection badge flicker between 已连接 and 检测中
  user also confirmed the diff/workbench header dot should reflect recent formal backend API status, not browser navigator.onLine
Expected:
  Silent workspace-tree refresh keeps the last formal backend connection status stable while a refresh is in flight.
  Active operation auto-refresh only runs for QUEUED/RUNNING operations and clamps low poll_after_ms values to a 3000ms minimum.
  Formal diff/workbench header dots use the recent formal API transport/server connectivity status, while dev/non-formal paths keep browser online/offline semantics.
  No heartbeat, SSE, WebSocket, or new health endpoint is introduced.
Actual:
  Formal workspace active refresh helper now clamps active operation polling between 3000ms and 5000ms.
  Silent /api/workspace-tree refresh no longer resets the recent formal backend connection status to checking.
  Formal workbench header status dots now use the shared recent formal API connectivity status; dev/non-formal workbench keeps browser online/offline semantics.
  Local packaging errors and business-level terminal operations are not treated as backend connectivity failures.
  Frontend npm test command passed: 150 passed, 0 failed. Existing npm script also ran the full src/**/*.test.js suite.
  Frontend npm run build passed with the same Rollup PURE annotation and chunk-size warnings recorded in Slice 0.
Flow/read-model result:
  frontend formal connection status and active-operation refresh UX correction passed automated checks; manual confirmation pending
Decision: continue
Follow-up:
  Manual retest formal submit/cache async phase: confirm operation badges refresh without 已连接/检测中 flicker.
  Stop formal backend during active refresh or trigger manual refresh and confirm the status changes to 连接异常.
  Static idle pages are not expected to detect backend shutdown until the next formal API call.
```

```text
Date: 2026-07-05 20:43:07 CST +0800
Slice: 6 Archive staged migration planning
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  none; documentation-only planning update
Frontend command(s):
  none; documentation-only planning update
Manual actions:
  user confirmed Slice 6 should be split because archive migration is heavier than a route migration
  user emphasized old backend archive anomaly logic must be fully inherited, including abnormal initial validation, multi-submission initial/modified explanations, configuration time and submission time anomaly judgments, manual resolution, and initial history retention
Expected:
  Split the single Slice 6 Archive Mainline entry into staged implementation steps.
  Make old backend archive functional parity the gate before formal archive API and frontend journey migration.
Actual:
  Slice 6 is now staged as 6.0 Archive Parity Audit, 6.1 Batch Graph / Snapshot Summary, 6.2 Anomaly Resolution and Candidate Selection, 6.3 Archive Execute Domain Flow, 6.4 Formal Archive API, and 6.5 Frontend Archive Journey.
  Pause conditions and verification matrix now explicitly block formal archive migration before anomaly parity and required archive task readiness are proven.
Flow/read-model result:
  not run; planning-only entry
Bundle open smoke result:
  not run
Diff/risk result:
  deferred
Artifacts:
  docs/backend-vnext/notes/formal-contract-migration-execution-plan.md
Normalized diff/risk oracle result:
  not run
Decision: continue to Slice 6.0 planning/implementation after commit
Follow-up:
  Begin Slice 6.0 by auditing old archive use cases and mapping them to vNext parity tests before implementing formal archive routes.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-05 21:24:38 CST +0800
Slice: 6.0 Archive Parity Audit
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/unit/test_archive_use_cases.py -k "batch_graph or anomaly or baseline_archive_nodes"
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_archive_service.py tests/backend_vnext/unit/test_archive_flow.py
Frontend command(s):
  none
Manual actions:
  reviewed old archive oracle tests, formal workflow oracle tests, vNext archive service/selection/policy, and vNext archive flow tests
Expected:
  Create an executable archive parity matrix before implementing Slice 6.1.
  Identify which archive behaviors are covered, partial, missing, or formal-only gaps in vNext.
Actual:
  Added docs/backend-vnext/notes/archive-parity-audit.md.
  The audit maps normal PASS, pending summary, unresolved initial, raw-exact unresolved, time abnormal initial/modified, peer-chain root abnormal initial, manual resolutions, initial history candidate selection, baseline archive nodes, formal route workflow, formal tree visibility, and required archive task readiness.
  Added A00 Configuration Generated Time Source Chain after review: vNext must prove SQL version_manager.saved_time -> SnapshotSummary -> upload/submit protected summary -> archive graph propagation before time-abnormal archive parity.
  Clarified A00 source-of-truth semantics: upload preview summary is provisional, while archive decisions must read configuration_generated_at from submit-finalized FINAL hidden summary table or equivalent protected summary readback.
  Split Slice 6.1 into 6.1a Configuration Generated Time Source Chain and 6.1b Batch Graph / Snapshot Summary to avoid mixing source-chain persistence with graph inference.
  Current vNext status is mostly partial/missing for automatic batch graph inference and formal route migration; explicit candidate/resolution promote flow and open-ref closeout have existing vNext coverage.
  Old archive oracle focused check passed: 10 passed, 18 deselected.
  Current vNext archive baseline passed: 2 passed.
Flow/read-model result:
  not run; audit-only entry
Bundle open smoke result:
  not run
Diff/risk result:
  deferred
Artifacts:
  docs/backend-vnext/notes/archive-parity-audit.md
Normalized diff/risk oracle result:
  not run
Decision: continue to Slice 6.1 after review
Follow-up:
  Start Slice 6.1a by implementing or verifying A00, then continue to Slice 6.1b for batch graph / snapshot summary parity rows A01-A08.
  Do not start formal archive API migration until the audit's Do Not Proceed Conditions are satisfied.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-05 22:02:23 CST +0800
Slice: 6.1a Configuration Generated Time Source Chain automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization_repository_ref.py tests/backend_vnext/unit/test_repository_import_readback.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  none; backend source-chain only
Manual actions:
  none
Expected:
  vNext SnapshotSummary carries configuration_generated_at as a timezone-aware optional datetime.
  SQL materialization extracts version_manager.saved_time from the final valid row without using upload/submit/review/archive/operation time as a fallback.
  Provisional preview summary and FINAL materialization preserve the field.
  Hidden summary payload and repository-ref readback restore the field from FINAL/protected summary facts.
Actual:
  Added SnapshotSummary.configuration_generated_at payload roundtrip with legacy missing-field compatibility.
  Materialization now reads version_manager.saved_time, including INSERT column-list order, and returns None for missing table, missing column, empty, or invalid values.
  Preview-to-final finalization preserves the extracted value.
  Repository-ref materialization restores configuration_generated_at from hidden summary readback.
  Focused backend checks passed: snapshot materialization 23 passed; repository ref/readback 18 passed; submit finalize flow 2 passed.
Flow/read-model result:
  A00 source chain implemented and covered by focused tests
Bundle open smoke result:
  not run
Diff/risk result:
  not run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/models.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/materializer.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization_repository_ref.py
Normalized diff/risk oracle result:
  not run
Decision: continue to Slice 6.1b after review
Follow-up:
  Implement Slice 6.1b Batch Graph / Snapshot Summary parity using FINAL/protected summary configuration_generated_at facts as graph inputs.
  Do not start formal archive API migration until audit rows A01-A08 and downstream resolution/execution gates are satisfied.
  The known snapshot digest mismatch from Slice 0 remains accepted as a non-blocking baseline red point.
```

```text
Date: 2026-07-05 22:24:47 CST +0800
Slice: 6.1a Configuration Generated Time Source Chain projection follow-up
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
Frontend command(s):
  none; frontend already consumes configuration_generated_at in formal workspace state
Manual actions:
  user reported that after upload + submit, the workspace node did not show configuration generated time before archive
Expected:
  Submit finalize projection should expose the SQL-derived configuration_generated_at before archive.
  The value must come from the FINAL source snapshot summary used by submit finalize, not from upload/submit/review/archive/operation timestamps.
Actual:
  Formal submit now passes source_snapshot.summary.configuration_generated_at into create_submission after SUBMIT_FINALIZE reaches READY.
  Submission payload and workspace tree submission node reuse existing configuration_generated_at fields, so no frontend contract change is required.
  Missing FINAL summary time remains null.
Flow/read-model result:
  formal submit projection follow-up passed automated checks: formal app 22 passed; snapshot materialization 23 passed
Bundle open smoke result:
  not run
Diff/risk result:
  not run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_submit.py
  gateway-data-management-system/backend/backend_vnext/api/formal_state_store.py
  gateway-data-management-system/backend/backend_vnext/flows/submit_finalize.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py
Normalized diff/risk oracle result:
  not run
Decision: continue to Slice 6.1b
Follow-up:
  Manual retest upload + submit and confirm the workspace tree submission node shows configuration generated time before archive.
  Keep archive graph decisions gated on FINAL/protected summary facts in Slice 6.1b.
```

```text
Date: 2026-07-06 18:10:00 CST +0800
Slice: 6.1b Batch Graph / Snapshot Summary automated checks
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  none; frontend contract remains additive/read-only for batch_graph
Manual actions:
  none
Expected:
  Archive snapshot exposes a structured batch_graph projection instead of null.
  Graph decisions consume submit FINAL summary-derived submission facts and workflow state only.
  PROVISIONAL preview, source package payloads, repository physical catalog, and duplicate canonical storage details do not feed archive authority.
Actual:
  Added batch-graph/v1 projection with overall_status, blocking_reason_codes, reachable/pending/unresolved/time-abnormal submission ids, nodes, edges, and diagnostics.
  Archive dry-run and execute precheck now include batch graph blocking reasons.
  Archive candidate creation requires approved FINAL facts: repository_commit_hash and configuration_generated_at.
  Workspace tree now includes upload_initial_snapshot action state; explicit empty first baseline disables initial upload while keeping modified upload available.
  Added initial_configuration_generated_at internal projection from initial materialization to workspace/submission state for graph time checks.
Flow/read-model result:
  focused backend checks passed
Bundle open smoke result:
  not run
Diff/risk result:
  not run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_state_store.py
  gateway-data-management-system/backend/backend_vnext/api/removed formal app adapter
  gateway-data-management-system/backend/backend_vnext/api/formal_upload.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_removed formal app adapter
Normalized diff/risk oracle result:
  not run
Decision: continue to Slice 6.2 after review
Follow-up:
  Implement anomaly resolution and candidate selection unlock semantics for graph blocking reasons.
  Keep archive execute domain-flow migration deferred to Slice 6.3.
```

```text
Date: 2026-07-06 CST +0800
Slice: 6.2 Anomaly Resolution and Candidate Selection Closure
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
Expected:
  Manual anomaly resolutions are persisted with actor/reason audit fields and are bound to current batch graph diagnostics.
  Resolution coverage clears only the intended graph blocking conditions and cannot hide unrelated root diagnostics.
  Root abnormal initial submissions can produce selected BASELINE_INITIAL_HISTORY candidates; peer-chain downstream submissions cannot.
  TIME_ABNORMAL_MODIFIED mainline selection requires MANUAL_ACCEPT_ABNORMAL_MODIFIED.
  Stale candidate_set_hash failures leave selected batch state unchanged.
Actual:
  Added anomaly resolution records to the formal adapter archive store and archive snapshot payload.
  Batch graph now reports raw blocking reason codes, resolved reason codes, and effective blocking reason codes.
  Resolution coverage is diagnostic scoped, so resolving one root does not clear another root with the same reason code.
  Archive candidate and selection validation now support BASELINE_INITIAL_HISTORY selection for resolved root abnormal initial cases.
  Compat archive execute still rejects selected initial history candidates; final archive-node persistence remains Slice 6.3.
Flow/read-model result:
  focused backend checks passed
Bundle open smoke result:
  not run
Diff/risk result:
  not run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_state_store.py
  gateway-data-management-system/backend/backend_vnext/api/removed formal app adapter
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_removed formal app adapter
  docs/backend-vnext/notes/archive-parity-audit.md
  docs/backend-vnext/notes/formal-contract-migration-execution-plan.md
Normalized diff/risk oracle result:
  not run
Decision: continue to Slice 6.3 execute domain-flow migration after review
Follow-up:
  Persist selected BASELINE_INITIAL_HISTORY archive nodes with immutable refs and associated mainline links.
  Move archive execute into the formal operation/task model before formal archive API migration.
```

```text
Date: 2026-07-06 CST +0800
Slice: 6.3 Archive Execute Domain Flow
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
Expected:
  Compat archive execute creates MAINLINE_MODIFIED and selected BASELINE_INITIAL_HISTORY archive nodes in one synchronous domain flow.
  Only MAINLINE_MODIFIED promotes the batch main hash; initial-history nodes are retained as immutable history refs.
  Initial-history nodes are independently visible in the workspace tree and can be resolved by history compare.
  Execute remains synchronous in compat; async required task READY gating is deferred.
Actual:
  Added retained initial source package projection to workspace/submission state for baseline initial history readback.
  Execute now validates frozen selected initial candidates, creates mainline and history archive nodes, records associated mainline and anomaly resolution ids, and preserves idempotent replay.
  Workspace tree now emits independent baseline_initial_history nodes.
  History compare now resolves BASELINE_INITIAL_HISTORY archive node ids through the initial source package.
Flow/read-model result:
  focused backend checks passed
Bundle open smoke result:
  not run
Diff/risk result:
  not run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_state_store.py
  gateway-data-management-system/backend/backend_vnext/api/removed formal app adapter
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_removed formal app adapter
  docs/backend-vnext/notes/archive-parity-audit.md
  docs/backend-vnext/notes/formal-contract-migration-execution-plan.md
Normalized diff/risk oracle result:
  not run
Decision: continue to formal archive API migration after review
Follow-up:
  Migrate archive execute into formal routes/operation runtime in later slices.
  Keep async required task gating separate from the compat domain-flow checkpoint.
```

```text
Date: 2026-07-06 CST +0800
Slice: 6.4 Formal Archive API Migration
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Expected:
  Formal archive routes expose archive snapshot, anomaly resolution, candidate, confirmation, selection, dry-run, execute, and execution records.
  Routes use formal session permissions and ErrorEnvelope mapping, not compat app delegation.
  Execute remains synchronous; Archive Execute Operation Gating stays deferred.
Actual:
  Added formal archive DTOs and route handlers in formal_app.py.
  Formal route tests cover normal mainline archive, archive permission denial, stale hashes, blank anomaly reason, and abnormal initial history workflow.
  Compat archive tests and submit finalize tests continue to pass.
Flow/read-model result:
  focused backend checks passed
Bundle open smoke result:
  not run
Diff/risk result:
  git diff --check pending final run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_app.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py
  docs/backend-vnext/notes/archive-parity-audit.md
  docs/backend-vnext/notes/formal-contract-migration-execution-plan.md
Decision: continue to Archive Execute Operation Gating / frontend archive journey as separate later slices after review
Follow-up:
  Implement Archive Execute Operation Gating before moving frontend archive journey to operation polling.
  Keep formal archive routes as the stable API surface for future frontend migration.
```

```text
Date: 2026-07-06 CST +0800
Slice: 6.5 prerequisite - Archive Execute Operation Gating
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Expected:
  Formal archive execute returns ARCHIVE_PROMOTE operation envelope after synchronous precheck.
  Archive execution records, archive nodes, batch closeout, workspace closeout, and next-batch opening appear only after operation READY.
  Stale execute hashes fail synchronously with formal ErrorEnvelope and do not create partial archive state.
  Workspace tree exposes in-flight archive operations through active_operations.
  Frontend session archive execute polls the operation until READY before reading the archive payload.
Actual:
  Added FormalArchiveService with background ARCHIVE_PROMOTE operation execution.
  Added store-level execute validation for formal precheck without state mutation.
  Formal route tests now poll operation READY for normal and abnormal initial archive workflows.
  Added focused gating test that blocks the background worker and verifies no archive state is published before READY.
  Added frontend archive operation polling, failure handling, missing-ready-result handling, and workspace tree ARCHIVE_PROMOTE operation tagging.
Flow/read-model result:
  focused backend and frontend checks passed
Bundle open smoke result:
  not run
Diff/risk result:
  git diff --check pending final run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_archive.py
  gateway-data-management-system/backend/backend_vnext/api/formal_app.py
  gateway-data-management-system/backend/backend_vnext/api/formal_state_store.py
  gateway-data-management-system/backend/backend_vnext/api/formal_upload.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py
  gateway-data-management-system/frontend/src/App.tsx
  gateway-data-management-system/frontend/src/components/ArchiveMainlineReviewPanel.tsx
  gateway-data-management-system/frontend/src/components/FormalWorkspaceTree.tsx
  gateway-data-management-system/frontend/src/data/workspaceApi.ts
  gateway-data-management-system/frontend/src/data/workspaceApi.test.js
  gateway-data-management-system/frontend/src/data/formalWorkspaceState.test.js
  docs/backend-vnext/notes/archive-parity-audit.md
  docs/backend-vnext/notes/formal-contract-migration-execution-plan.md
Decision: continue to Slice 6.5 frontend archive journey after review
Follow-up:
  Refine frontend archive journey UX beyond the now-working operation polling path.
  Keep compat execute synchronous until legacy/manual parity routes are retired.
```

```text
Date: 2026-07-06 CST +0800
Slice: 6.5 Frontend Archive Journey and Async Progress
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js src/components/archiveMainlineReviewModel.test.js
  npm run build
Expected:
  Formal workspace archive uses the formal routes and operation-gated execute path.
  Normal pass archive stays one-click; pending summary, confirmation needs, integrity block, and graph anomalies open the review panel.
  In-flight ARCHIVE_PROMOTE operations block duplicate archive execute and show archive queued/running progress.
  Archive completion refreshes the formal tree so mainline and baseline-initial-history archive nodes are visible.
Actual:
  Added active archive operation resolution for formal workspace state.
  Formal archive action now blocks duplicate execute when the current batch has an active ARCHIVE_PROMOTE operation.
  Archive review panel shows archive queued/running state with refresh and close actions while execute is in flight.
  Formal workspace page passes ARCHIVE_PROMOTE state into the review panel and shows archive operation progress messages.
  Added focused frontend state tests for active archive operation resolution and duplicate archive blocking.
Flow/read-model result:
  focused backend and frontend checks passed
Bundle open smoke result:
  not run
Diff/risk result:
  git diff --check passed
Artifacts:
  gateway-data-management-system/frontend/src/App.tsx
  gateway-data-management-system/frontend/src/components/ArchiveMainlineReviewPanel.tsx
  gateway-data-management-system/frontend/src/data/formalWorkspaceState.ts
  gateway-data-management-system/frontend/src/data/formalWorkspaceState.test.js
  docs/backend-vnext/notes/archive-parity-audit.md
  docs/backend-vnext/notes/formal-contract-migration-execution-plan.md
Decision: Slice 6.5 frontend archive journey complete for the formal session path
Follow-up:
  Keep internal/debug archive execute on the existing synchronous compatibility path.
  Real Dolt immutable refs and optional post-archive tasks remain outside Slice 6.5.
```

```text
Date: 2026-07-06 CST +0800
Slice: 7 History Compare
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_removed formal app adapter
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_history_compare_flow.py
  ./.venv/bin/pytest -q tests/unit/test_history_compare_operations.py tests/unit/test_history_comparison_compute.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js src/components/HistoryCompareView.test.js
  npm run build
Expected:
  Formal history compare routes accept only business nodes and reject ref/cache/path/table inputs.
  READY responses carry history-comparison-bundle/v1 metadata and workbench download refs.
  Non-READY or failed operations do not publish bundle/download artifacts.
  BASELINE_INITIAL_HISTORY archive nodes can be selected as independent history compare inputs.
Actual:
  Added vNext formal history comparison routes and strict request DTOs.
  Reused the existing read-only history compare flow and history workbench bundle adapter without exposing compat/internal routes.
  Added formal route tests for 2-node compare, 3-node compare with BASELINE_INITIAL_HISTORY, invalid input rejection, and non-READY bundle gating.
  Added frontend API test assertions that only ordered business nodes are sent and non-READY response download fields remain null.
Flow/read-model result:
  focused backend and frontend checks passed
Bundle open smoke result:
  formal history workbench tar artifact opens in focused route test
Diff/risk result:
  git diff --check passed
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_app.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py
  gateway-data-management-system/frontend/src/data/workspaceApi.test.js
  docs/backend-vnext/notes/archive-parity-audit.md
  docs/backend-vnext/notes/formal-contract-migration-execution-plan.md
Decision: Slice 7 formal history compare complete for the session path
Follow-up:
  Slice 8 completed direct formal ComparisonBundle / ComparisonSurface loading for the formal history compare path.
  Internal/debug/compat history routes remain unchanged until compat deletion.
```

```text
Date: 2026-07-05 23:19:38 CST +0800
Slice: 5.8 Submit polling pressure and synchronous validation UI stabilization
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  user reported operation polling appeared too frequent during async submit/cache observation
  user clarified submit has a synchronous validation stage that should block UI until POST /api/submissions returns an operation envelope
Expected:
  Formal operation polling should not run below a 3000ms interval.
  Submit synchronous validation should use the blocking task modal while refreshing workspace state, packaging source, and waiting for submit acceptance.
  After the first operation envelope/update is observed, the UI should leave blocking mode and use the existing non-blocking header/tree operation state.
Actual:
  Non-terminal formal operation envelopes now return poll_after_ms=3000; terminal envelopes still return null.
  Frontend formal upload/submit operation polling clamps low poll_after_ms values to a 3000ms minimum.
  Formal session submit now shows a blocking submit task during workspace refresh, source package creation, and POST /api/submissions acceptance.
  The first observed submit operation update clears the blocking task and continues with header/tree async operation status.
  Focused backend checks passed: formal app 22 passed.
  Focused frontend checks passed: frontend npm test command passed 150 tests; npm run build passed with the existing Rollup PURE annotation and chunk-size warnings.
Flow/read-model result:
  submit polling pressure and synchronous validation UI stabilization passed automated checks
Bundle open smoke result:
  not run
Diff/risk result:
  not run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_upload.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py
  gateway-data-management-system/frontend/src/App.tsx
  gateway-data-management-system/frontend/src/data/workspaceApi.ts
  gateway-data-management-system/frontend/src/data/workspaceApi.test.js
Normalized diff/risk oracle result:
  not run
Decision: continue after manual Step A retest
Follow-up:
  Manual retest submit: confirm blocking modal covers source package validation/acceptance, then clears once async finalize/import polling begins.
  Manual retest logs during async phase: confirm operation polling frequency is roughly 3000ms or slower.
  Large upload performance benchmark is intentionally deferred and must not be hidden by converting upload preview generation into a polling operation.
```

```text
Date: 2026-07-05 23:43:08 CST +0800
Slice: Step B Large upload benchmark instrumentation
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/workspaceApi.test.js src/data/formalWorkspaceState.test.js
  npm run build
Manual actions:
  none in this implementation step; large dataset manual benchmark remains pending
Expected:
  Add opt-in benchmark instrumentation for large formal upload without changing formal API responses or upload preview-ready semantics.
  Capture frontend packaging/fetch timings and backend multipart read, stage, SQL materialize, preview diff/risk, bundle assembly, workspace write, cache enqueue, and submit auxiliary timings.
  Use ~/test-dir/business-benchmark-data/business_large/large for manual first-upload and submit-to-ready benchmarking.
Actual:
  Backend benchmark logs are gated by BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and emit JSON log lines with a shared benchmark run id.
  Frontend benchmark logs are gated by localStorage.formalUploadBenchmark=1 and emit JSON console lines prefixed with [formal-upload-benchmark].
  Upload contract remains synchronous preview-ready; no UPLOAD_PREVIEW polling behavior change was introduced.
  Submit benchmark logging is coarse-grained and auxiliary only.
  Focused backend checks passed: formal app 22 passed; upload preview flow 3 passed.
  Focused frontend checks passed: frontend npm test command passed 150 tests; npm run build passed with the existing Rollup PURE annotation and chunk-size warnings.
Flow/read-model result:
  benchmark instrumentation passed automated checks; manual large run pending
Bundle open smoke result:
  not run
Diff/risk result:
  not run
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_app.py
  gateway-data-management-system/backend/backend_vnext/api/formal_upload.py
  gateway-data-management-system/backend/backend_vnext/api/formal_submit.py
  gateway-data-management-system/frontend/src/data/workbenchUploadPackage.ts
  gateway-data-management-system/frontend/src/data/workspaceApi.ts
Normalized diff/risk oracle result:
  not run
Decision: continue after manual large benchmark
Follow-up:
  Start formal main with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and a fresh state root.
  In the browser console run localStorage.setItem("formalUploadBenchmark", "1") before selecting the large dataset.
  Select ~/test-dir/business-benchmark-data/business_large/large and run INITIALIZE_BASELINE upload, then submit to READY.
  Compare frontend package/fetch timings with backend route/service stage timings to locate the 80-120s upload bottleneck.
```

```text
Date: 2026-07-06 CST +0800
Slice: Step C Upload internal benchmark breakdown
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py
Frontend command(s):
  not required; no frontend code change
Manual actions:
  user confirmed Step B bottleneck split and requested deeper source package, SQL materialize, and upload preview breakdown
Expected:
  Keep upload preview-ready synchronous and do not introduce UPLOAD_PREVIEW polling.
  Add opt-in benchmark logs for source package staging, non-streaming TAR_GZ member reads, SQL materialization internals, upload preview comparison/risk/surface, records artifact writes, and background cache completion.
  Record current implementation facts: TAR_GZ staging is not streaming; FULL uses two-worker stage/materialize for initial and modified inputs, while the main preview pair remains single-path after materialization.
Actual:
  Added shared backend benchmark logger helpers under backend_vnext/formal_upload_benchmark.py.
  Source package staging now logs load entries, tar/zip member enumeration and reads, manifest digest build, payload JSON build, artifact put, required SQL resolve, and total staging time when BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1.
  Snapshot materialization now logs context creation, SQL source resolve, SQL parse, table loop, digest build, configuration_generated_at extraction, summary object build, and total materialization time under the same run id.
  Upload preview now logs comparison/risk analytics, comparison core, risk evaluation, surface assembly, records artifact put, publish result, and cache completion details.
  Focused backend checks passed: formal app 22 passed; upload preview flow 3 passed.
  Large benchmark completed against /home/issac/test-dir/business-benchmark-data/business_large/large with state root /home/issac/test-dir/backend-vnext-formal-benchmark-state-stepc-20260706-002533.
  Dataset observed: 528 files, about 304 MiB input, upload package payload about 317807308 bytes.
  Frontend upload timings: file read 857 ms, tar build 137 ms, gzip store 3130 ms, sha256 547 ms, package total 4682 ms, POST /uploads fetch 64457 ms, click upload to diff 71743 ms.
  Backend upload timings: route multipart read 241 ms, source package stage 5672 ms, SQL materialize 33546 ms, preview comparison/risk/surface 22441 ms, preview bundle assemble 153 ms, workspace preview-ready write 4 ms, cache enqueue 1 ms, upload total 61866 ms.
  Source package staging details confirmed streaming=false: tar getmembers 441 ms, tar member read 1483 ms, payload JSON build 2830 ms, artifact put 376 ms, staging total 5388 ms.
  SQL materialize details: source-package context/ref resolve 3317 ms, parse SQL 7570 ms, table loop 22640 ms, digest build 10 ms, configuration_generated_at extraction 7 ms, total 33546 ms.
  Preview details: comparison core 22367 ms across 292 tables, risk evaluation 2 ms, surface assembly 67 ms, records artifact writes 0 ms, run_upload_preview total 22441 ms.
  Submit auxiliary timings: frontend submit package 5133 ms, submit acceptance fetch 8634 ms, poll to READY 174201 ms; backend sync submit total 5654 ms, async finalize 174088 ms, async publish submission 8 ms.
  Current implementation fact confirmed: preview-ready upload still performs package staging, SQL materialize, comparison/risk, preview bundle assembly, and workspace preview-ready persistence synchronously; only cache completion is non-blocking.
Flow/read-model result:
  large INITIALIZE_BASELINE upload returned a preview-ready result and the diff view could open after the synchronous upload response
Bundle open smoke result:
  preview bundle produced during the large upload; diff/workbench opened after upload completion
Diff/risk result:
  comparison core completed as the main blocking preview stage and reported unchanged data for the initial baseline upload
Artifacts:
  gateway-data-management-system/backend/backend_vnext/formal_upload_benchmark.py
  gateway-data-management-system/backend/backend_vnext/api/formal_upload.py
  gateway-data-management-system/backend/backend_vnext/api/formal_submit.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/source_package.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/materializer.py
  gateway-data-management-system/backend/backend_vnext/flows/upload_preview.py
  gateway-data-management-system/backend/backend_vnext/flows/comparison_risk.py
Normalized diff/risk oracle result:
  not run
Decision: continue to optimization planning
Follow-up:
  First optimization candidate: source package and SQL materialize path, especially non-streaming TAR_GZ staging, large payload JSON build, source-package ref/context resolve, SQL parse, and per-table row normalization loop.
  Second optimization candidate: comparison core, which is currently the largest preview-ready stage after SQL materialization.
  Submit async finalize has a separate large-data bottleneck at about 174 seconds and should be split in a later submit/archive persistence benchmark.
  Do not change upload into an UPLOAD_PREVIEW polling operation; preserve the contract that upload returns only once preview/diff is ready.
```

```text
Date: 2026-07-06 CST +0800
Slice: Step D1 SourcePackageManifest optimization
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  not required; no frontend code change
Manual/benchmark actions:
  Built /tmp/backend-vnext-stepd1-large-store.tar.gz from /home/issac/test-dir/business-benchmark-data/business_large/large with gzip store semantics for backend benchmark input.
  Ran formal app TestClient upload against /home/issac/test-dir/backend-vnext-formal-benchmark-state-stepd1-20260706 with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1.
  Continued submit to READY with a fake repository import runner so the benchmark validates source-package readback/materialize without mixing in Dolt import latency.
Expected:
  Replace the source-package artifact payload from giant JSON content_b64 entries to a small manifest with per-file source-package-entry artifact refs.
  Do not support old content_b64 test data or migrations; test state can be cleared.
  Keep upload preview-ready synchronous and do not introduce UPLOAD_PREVIEW polling.
Actual:
  SourcePackageEntry now carries content_artifact_ref for file entries; directory entries do not carry content refs.
  source-package-entry artifacts store original file bytes, while the source-package artifact stores only package metadata, entry metadata, required path, and content_artifact_ref payloads.
  Source package business digests remain based on stable entry metadata and content digests, not artifact refs or random package ids.
  load_source_document_bytes reads required SQL through content_artifact_ref; materialize_sql_dump_source(staged.artifact_ref) now resolves through the manifest artifact.
  content_b64 construction/reader code was removed from the formal source package path.
  Focused backend checks passed: snapshot materialization 24 passed; formal app 22 passed; upload preview flow 3 passed; submit finalize flow 2 passed.
Flow/read-model result:
  large INITIALIZE_BASELINE upload returned READY in 52.883 seconds at HTTP/TestClient level.
  backend upload.total was 51741 ms, down from the Step C backend upload.total of 61866 ms.
Bundle open smoke result:
  preview bundle was produced; preview bundle size was 3440640 bytes.
Diff/risk result:
  comparison core remained the largest post-materialization blocking stage at 21058 ms.
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/source_package.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/sql_source.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/materializer.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/versions.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py
Benchmark result:
  Dataset observed: 528 files, 317343482 input bytes, TAR_GZ benchmark package 318379235 bytes.
  Source package manifest size dropped from the Step C payload JSON size of about 423317976 bytes to 354658 bytes.
  Source package staging total dropped from 5388 ms to 1694 ms; upload.stage_package dropped from 5672 ms to 1817 ms.
  TAR_GZ staging remains streaming=false: tar getmembers 364 ms, tar member read 657 ms, load entries 1022 ms.
  New entry artifact put cost was 666 ms for 528 files / 317343482 bytes.
  Manifest JSON build was 4 ms and source-package artifact put was 1 ms.
  Snapshot materialize source context/ref resolve dropped from 3317 ms to 501 ms.
  Snapshot materialize total dropped from 33546 ms to 28637 ms; parse SQL was 7322 ms and table loop was 20799 ms.
  Upload preview total was 21241 ms; bundle assemble 144 ms; workspace preview-ready write 4 ms; cache enqueue 1 ms.
  Submit acceptance returned in 3.226 seconds at HTTP/TestClient level; submit reached READY in 40.031 seconds with fake repository import.
Normalized diff/risk oracle result:
  not run
Decision: continue to D2 SQL materialize per-table profiling / targeted optimization
Follow-up:
  D1 removed the obvious giant source-package JSON/base64 cost and reduced backend upload by about 10 seconds, but upload still exceeds the 20 second target.
  Next bottlenecks are SQL materialize table_loop/parse and comparison core; do not revisit UPLOAD_PREVIEW polling as a substitute for performance optimization.
  TAR_GZ parsing is still non-streaming and remains a future optimization candidate, but the larger remaining blocking costs are table materialization and comparison core.
```

```text
Date: 2026-07-10 CST +0800
Slice: SQL/source package streaming for formal upload
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Backend command(s):
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
Frontend command(s):
  not required; no frontend API or payload shape change
Manual/benchmark actions:
  Ran upload-only TestClient benchmark with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS=1.
  First upload dataset: /home/issac/test-dir/business-benchmark-data/business_large/large.
  Second FULL upload datasets: /home/issac/test-dir/business-benchmark-data/business_large/large-1 + large-2.
Expected:
  Remove full multipart bytes and full SQL text as mandatory formal upload sync-path inputs.
  Stage TAR_GZ source packages by sequential streaming scan; only the required /sql/dbcfg.sql document is stored as a file-backed source-package-entry artifact.
  Resolve SourceDocumentRef to file-backed SqlDumpSource and parse SQL through a chunked statement iterator.
  Preserve preview READY closure, frontend API, snapshot Parquet output, and default serial snapshot export.
Actual:
  Formal multipart upload now spools to a local file in chunks while computing sha256 and size; FormalUploadFile supports source_path and keeps bytes fallback for tests.
  Formal upload/submit staging uses source_path directly and avoids raw bytes -> write_bytes duplication.
  TAR_GZ staging now uses streaming tar iteration, writes only the required SQL member as a file artifact, and keeps non-required file entries as metadata-only package entries.
  SqlDumpSource now supports file-backed content and parse_sql_dump_source uses parse_mysql_dump_chunks for file-backed sources.
  Added route.multipart_spool, source_package.stage.streaming_extract, snapshot_materialize.sql_source_open, and streaming/source-size/chunk-size parser benchmark fields.
Flow/read-model result:
  large INITIALIZE_BASELINE upload returned READY; backend upload.total was 18165 ms.
  large-1 + large-2 FULL upload returned READY; backend upload.total was 53564 ms.
Benchmark result:
  route.multipart_spool was 22-23 ms per uploaded tar.gz package, with file_backed=true.
  source_package.stage.total was about 1.05-1.17 seconds per package, streaming=true, extracted_file_count=1.
  snapshot_materialize.parse_sql for first upload large was 7668 ms, streaming=true, source_size_bytes=79446967.
  FULL upload parses ran concurrently: initial and modified parse events were about 14046 ms and 13935 ms, while upload.full.stage_materialize_pair was 15198 ms.
  upload.preview.snapshot_parquet_encode remained serial and was about 9.0-9.3 seconds for 137 visible tables / ~223k rows.
  FULL upload.preview.run_upload_preview was 28934 ms, dominated by comparison_core.total at 28789 ms.
  Compared with the previous post-topology-fix large-1 + large-2 run (~101s upload.total, ~39s stage/materialize pair, ~48s comparison core), upload.total dropped to ~54s and stage/materialize pair dropped to ~15s.
Decision:
  SQL/source package streaming is effective and should remain the default formal upload path.
  Next performance target is no longer source package staging; for FULL large-1 + large-2 the main remaining blocking stage is comparison_core, followed by serial snapshot Parquet encode.
Follow-up:
  Investigate comparison_core.total for modified large pairs before further parser work.
  Snapshot Parquet remains synchronous and serial by default; keep worker override only for explicit benchmark/deployment experiments.
```

```text
Date: 2026-07-11 CST +0800
Slice: Comparison core ordered projection reuse + projection hot-path optimization
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Reduce FULL large-1 + large-2 comparison_core.total by removing ordered provider raw table rereads and reducing ProjectionBuilder per-row overhead.
  Keep frontend API, bundle refs, records payloads, risk payloads, and snapshot Parquet strategy unchanged.
Implementation plan:
  Ordered provider should prefer before/current ProjectionTable rows when the projection contains both the stable key and ordered position field.
  Ordered projection retains the `no` position column for ORDERED/ORDERED_DIFF/ORDERED_TABLE_COMPARE roles even when `no` remains in ignored_columns for content-change semantics.
  If projection rows are unavailable or lack required ordered fields, ordered provider falls back to raw SnapshotTable rows and marks benchmark `ordered_input_source=raw_table_fallback`.
  ProjectionBuilder precomputes selected column indexes once and projects tuple/list rows through direct indexes, while preserving normalize_snapshot_row fallback for mapping/non-standard rows.
Non-goals:
  No ordered unchanged early-exit.
  No comparison_core table-level parallelism.
  No ProcessPool, snapshot Parquet strategy, frontend, or bundle contract changes.
Benchmark plan:
  Re-run upload-only benchmark with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS=1.
  Compare the 12 hot b1_n*_iec104_syx_list ordered tables against the previous ~2s/table baseline.
  Compare FULL comparison_core.total against the previous 28789 ms and upload.total against the previous 53564 ms.
Backend command(s):
  gateway-data-management-system/backend/.venv/bin/python -m py_compile gateway-data-management-system/backend/backend_vnext/capabilities/comparison/projection.py gateway-data-management-system/backend/backend_vnext/capabilities/comparison/engine.py gateway-data-management-system/backend/backend_vnext/capabilities/comparison/ordered/provider.py gateway-data-management-system/backend/backend_vnext/capabilities/comparison/ordered/models.py
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
Actual:
  Ordered provider now reports ordered_input_source=projection for all 144 ordered provider invocations in the large upload-only benchmark.
  Ordered provider read_rows phase dropped from the previous ~6162 ms aggregate to 13 ms aggregate because it no longer rereads raw SnapshotTable rows.
  ProjectionBuilder uses precomputed selected indexes and tuple/list direct indexing; mapping/non-standard row fallback remains normalize_snapshot_row.
  ORDERED/ORDERED_DIFF/ORDERED_TABLE_COMPARE projection schemas keep the `no` position column selected so ordered provider can safely consume projection rows while content diff semantics still treat `no` as ignored.
Benchmark result:
  large INITIALIZE_BASELINE upload.total: 17209 ms.
  large INITIALIZE_BASELINE comparison_core.total: 85 ms.
  large INITIALIZE_BASELINE snapshot_parquet_encode: 8915 ms for 137 tables / 223132 rows, worker_count=1.
  large-1 + large-2 FULL upload.total: 45507 ms, down from the previous 53564 ms.
  FULL upload.full.stage_materialize_pair: 15402 ms, approximately unchanged from the previous streaming run.
  FULL upload.preview.run_upload_preview: 20942 ms.
  FULL comparison_core.total: 20799 ms, down from the previous 28789 ms.
  FULL snapshot_parquet_encode: 9049 ms for 137 tables / 223192 rows, worker_count=1.
  12 hot b1_n*_iec104_syx_list ordered tables now take about 1451-1539 ms/table, down from the previous ~1993-2091 ms/table.
  Ordered phase aggregate after reuse: ordered_digest 3347 ms, prepare_rows 2406 ms, read_rows 13 ms, replay_validation 491 ms, records_build 366 ms.
  comparison_core.projection_build aggregate is still 13049 ms across 288 projections; the next comparison_core optimization should target projection logical digest / unchanged early-exit / table-level comparison parallelism rather than raw ordered row rereads.
Decision:
  Keep projection-row reuse and ProjectionBuilder index fast path; both preserve contracts and reduce FULL comparison_core by about 8.0 seconds on the large-1 + large-2 benchmark.
  The remaining comparison_core bottleneck is no longer ordered raw row input. The next slice should avoid or parallelize expensive projection digest/order processing for unchanged or repeated large ordered tables.
```

```text
Date: 2026-07-11 CST +0800
Slice: Projection digest summary early-exit
Operator: Codex
Expected:
  Avoid ProjectionTable construction when SnapshotTableDescriptor already carries an exact matching projection digest summary.
  Keep projection digest contract, frontend API, bundle refs, records payloads, and ordered provider behavior unchanged.
Implementation plan:
  Add SnapshotProjectionDigest as a child of SnapshotTableDescriptor, not as a pseudo table in SnapshotSummary.tables.
  Generate first-round descriptor projection digests only for STANDARD_DIFF tables with effective compare keys.
  Skip SKIP, SNAPSHOT_ONLY, BROWSE_ONLY, ORDERED_DIFF, and no-key tables.
  Compare descriptor projection digests before self_project; exact equal digests produce table facts without projection rows or records.
  Accept FINAL authority for FINAL/history comparisons and allow PROVISIONAL_FAST only when a provisional side is present.
Benchmark plan:
  Use comparison_core.projection_digest_summary_lookup hit/miss events to measure saved projection builds.
  Re-run large upload-only benchmarks separately; this slice's unit acceptance does not require large benchmark execution.
Backend command(s):
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_projection_digest.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_compute_stage7.py -q
Actual:
  SnapshotTableDescriptor payload now roundtrips projection_digests and reads old payloads as an empty tuple.
  Materialization can write FINAL or PROVISIONAL_FAST projection digest summaries for eligible STANDARD_DIFF tables when the projection digest policy enables it.
  Comparison core emits comparison_core.projection_digest_summary_lookup with hit/miss reason and skips projection build on exact hits.
  Formal upload/history comparison inputs now pass materialized summary table_ruleset_version so descriptor projection schema digests can match the comparison schema.
```

```text
Date: 2026-07-11 CST +0800
Slice: Projection digest generation policy and benchmark breakdown
Operator: Codex
Expected:
  Keep SnapshotProjectionDigest and comparison lookup available, but do not make upload preview pay the full projection digest build cost by default.
  Make projection digest build cost visible in materialization benchmark output.
Implementation plan:
  Add SnapshotMaterializationInput.projection_digest_policy with DISABLED default.
  Support FINAL_ONLY and PROVISIONAL_AND_FINAL for explicit final/history or benchmark experiments.
  Gate _materialize_table projection digest generation on the policy and materialization authority.
  Add projection_digest duration/count/row-count fields to table_loop, table_profile and table_loop_profile_summary; emit projection_digest_build only when digests are actually generated.
Actual:
  Upload preview / provisional materialization defaults to DISABLED and no longer generates PROVISIONAL_FAST projection digests unless explicitly requested.
  FINAL_ONLY generates FINAL digests only for final materialization.
  PROVISIONAL_AND_FINAL preserves the previous experimental behavior.
  Benchmark events expose projection_digest_policy, projection_digest_duration_ms, projection_digest_count, projection_digest_table_count and projection_digest_row_count.
Decision:
  Do not optimize build_projection_logical_digest in this slice; first restore upload materialization cost and use the new metrics to decide whether a streaming digest fast path is worth implementing.
```

```text
Date: 2026-07-11 CST +0800
Slice: Ordered unchanged summary early-exit
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Completely unchanged ordered tables should route to SUMMARY_EARLY_EXIT before ORDERED_TABLE_COMPARE.
  Skip projection build, ordered prepare/digest/topology, ordered records, and ordered row-level risk for unchanged ordered tables.
  Preserve ordered provider behavior for added/deleted/modified/moved/degraded ordered tables.
Implementation plan:
  In the comparison planner, check ordered table descriptor equality before emitting the ordered provider route.
  Only early-exit when both sides exist, compare schema/row count/compare key match, and equality is proven by same pair early-exit, FINAL canonical/business/raw digest, or PROVISIONAL fast row digest.
  Use the fastest contract shape: summary-early-exited ordered tables do not carry ordered_extension.
  Keep provider-internal projection digest early-exit, comparison_core parallelism, and snapshot Parquet strategy out of scope.
Benchmark plan:
  Re-run upload-only benchmark with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and default serial snapshot export.
  Compare FULL comparison_core.total, comparison_core.projection_build count/sum, comparison_core.ordered_provider count/sum, summary_early_exit_table_count, records count, and risk annotation count against the previous 45.5s / 20.8s FULL baseline.
Backend command(s):
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
Actual:
  Ordered unchanged tables now route to SUMMARY_EARLY_EXIT before ORDERED_TABLE_COMPARE.
  Unchanged ordered early-exit table facts have status UNCHANGED, no records_ref, no records artifact, and no ordered_extension.
  Added/deleted/modified/degraded ordered tables still enter ORDERED_TABLE_COMPARE.
Benchmark result:
  large INITIALIZE_BASELINE upload.total: 17534 ms; comparison_core.total: 99 ms; all 292 tables were SUMMARY_EARLY_EXIT.
  large-1 + large-2 FULL upload.total: 44282 ms, down from the previous 45507 ms.
  FULL comparison_core.total: 18614 ms, down from the previous 20799 ms.
  FULL provider_counts: ORDERED_TABLE_COMPARE 12, SUMMARY_EARLY_EXIT 280.
  comparison_core.ordered_provider count dropped from 144 to 12; all remaining ordered provider inputs were projection.
  comparison_core.projection_build count dropped from 288 to 24; aggregate duration was 11675 ms.
  The 12 remaining b1_n*_iec104_syx_list modified ordered tables still take about 1442-1640 ms/table and dominate comparison_core.
Decision:
  Keep fastest ordered unchanged early-exit. The remaining comparison_core hotspot is the 12 truly modified ordered tables, not unchanged ordered routing.
```

```text
Date: 2026-07-11 CST +0800
Slice: Upload preview snapshot Parquet same-bundle ref dedupe
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Visible alias logical tables can reuse the canonical table's bundle-local snapshot Parquet ref.
  Each shared ref is exported once and appears once in the artifact closure while all visible table refs remain readable.
  Preserve current-first / before-only snapshot selection, READY closure, frontend API, and default serial export.
Implementation plan:
  Pass visible preview table aliases into snapshot ref binding.
  Resolve alias logical table refs to canonical current/before refs only when the canonical side exists in the selected table set.
  Deduplicate snapshot export tasks by ref and write canonical source rows for shared canonical refs.
  Do not use raw/fast/layout digests for arbitrary snapshot table dedupe in this slice, because equal content digests do not by themselves define frontend browse row-order semantics.
Benchmark plan:
  `upload.preview.snapshot_parquet_encode` reports logical_table_count, export_task_count, deduped_table_count, logical/exported/deduped row counts, and snapshot_ref_reuse_count.
  Re-run large INITIALIZE_BASELINE and FULL upload-only benchmark; if large has few visible aliases, performance gain may be small but dedupe hit metrics must be explicit.
Backend command(s):
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_upload_preview_flow.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
Actual:
  Snapshot refs now reuse visible alias canonical refs inside the same preview bundle.
  Snapshot artifact export tasks are deduped by ref, and artifact closure contains each shared parquet ref once.
  Dedupe uses only visible alias mappings; arbitrary digest-based table dedupe remains out of scope.
Benchmark result:
  large INITIALIZE_BASELINE snapshot encode: logical_table_count=137, export_task_count=135, deduped_table_count=2, deduped_row_count=26, duration_ms=8889.
  large-1 + large-2 FULL snapshot encode: logical_table_count=137, export_task_count=135, deduped_table_count=2, deduped_row_count=26, duration_ms=9298.
  FULL upload.total: 43265 ms; comparison_core.total: 18032 ms.
Decision:
  Keep same-bundle visible-alias snapshot ref dedupe. The current large sample has only two visible alias snapshot hits, so this is primarily a correctness/cleanup optimization rather than a major performance lever for this dataset.
```

```text
Date: 2026-07-06 CST +0800
Slice: Step D2 SQL materialize per-table profiling
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py
Frontend command(s):
  not required; no frontend code change
Manual/benchmark actions:
  Reused /tmp/backend-vnext-stepd1-large-store.tar.gz for large backend upload benchmark.
  Ran formal app TestClient INITIALIZE_BASELINE upload against /home/issac/test-dir/backend-vnext-formal-benchmark-state-stepd2-20260706 with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1.
Expected:
  Add opt-in per-table SQL materialization profiling without changing materialization behavior, digests, summaries, preview bundles, or formal API responses.
  Keep table rules injected through SnapshotMaterializationInput.table_rule_registry; do not expose TableHandlingDecision as a public materializer parameter.
  Do not implement rule-aware SQL parse skip in this step.
Actual:
  Materializer now emits snapshot_materialize.table_loop_profile_summary and per-table snapshot_materialize.table_profile events when benchmark logging is enabled.
  Per-table profile records parsed rows, columns, insert statement count, primary key count, rule decision duration, static role, runtime state, compare mode, keep/include/export flags, skip reason, and internal materialization timings.
  Rule-skipped tables produce profile events with skip_reason=TABLE_RULE_SKIP and do not enter materialized descriptors.
  Materialized tables record descriptor build, reader build, row finalize, row digest, descriptor finalize, and total table duration.
  Benchmark-disabled path emits no per-table profile logs.
  Focused backend checks passed: snapshot materialization 26 passed; formal app 22 passed; upload preview flow 3 passed.
Flow/read-model result:
  large INITIALIZE_BASELINE upload returned READY in 56.942 seconds at HTTP/TestClient level with profiling enabled.
Bundle open smoke result:
  preview bundle was produced; preview bundle size was 3440640 bytes.
Diff/risk result:
  comparison core remained a major blocking stage at 22647 ms.
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/materializer.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py
Benchmark result:
  Dataset observed: 528 files, 317343482 input bytes, TAR_GZ benchmark package 318379235 bytes.
  Backend upload.total was 55738 ms with per-table profiling enabled; this includes profiling/logging overhead and should be compared directionally to D1, not treated as optimized steady-state.
  upload.stage_package was 2176 ms; snapshot materialize total was 30680 ms; parse SQL was 7176 ms; table loop was 23024 ms; comparison core was 22647 ms.
  Profiling emitted 319 table profile events.
  Materialized rows: 246359. Rule-skipped rows: 190355.
  Top slow materialized tables:
    device_st: 9387 ms, 54150 rows, STANDARD_DIFF, row finalize 2988 ms, row digest 6395 ms.
    device_mx: 2998 ms, 14790 rows, STANDARD_DIFF, row finalize 942 ms, row digest 2055 ms.
    device_co: 654 ms, 4590 rows, STANDARD_DIFF, row finalize 217 ms, row digest 437 ms.
    b1_n11_iec104_syx_list: 589 ms, 9822 rows, ORDERED_DIFF, row finalize 233 ms, row digest 356 ms.
    b1_n4_iec104_syx_list: 577 ms, 9822 rows, ORDERED_DIFF, row finalize 235 ms, row digest 341 ms.
  Largest rule-skipped parsed tables:
    scdmod_fcda: 92428 rows.
    device_model_table: 84285 rows.
    scdmod_yk: 6595 rows.
    scdmod_dataset: 3241 rows.
    scdmod_rpt: 2640 rows.
Normalized diff/risk oracle result:
  not run
Decision: continue to D3 optimization planning
Follow-up:
  D2 confirms table materialization cost is concentrated in row digest/finalization for a few large kept tables, especially device_st and device_mx.
  D2 also confirms parse still pays for large skipped tables; scdmod_fcda and device_model_table alone account for 176713 skipped parsed rows.
  Candidate D3 split: first optimize row digest/finalization for kept tables, then add parser-level rule-aware skip for SKIP tables while preserving version_manager/configuration_generated_at extraction.
```

```text
Date: 2026-07-06 CST +0800
Slice: Step D3 Upload provisional materialization boundary correction
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  not required; no frontend code change
Manual/benchmark actions:
  Reused /tmp/backend-vnext-stepd1-large-store.tar.gz for large backend upload + submit benchmark.
  Ran formal app TestClient INITIALIZE_BASELINE upload and submit-to-READY against /home/issac/test-dir/backend-vnext-formal-benchmark-state-stepd3b-20260706 with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1.
Expected:
  Formal upload must use PROVISIONAL snapshot materialization and must not calculate row content digest in the synchronous upload path.
  Submit finalize must continue using FINAL snapshot materialization and calculate row content digest before creating PENDING_REVIEW submission.
  Upload remains synchronous preview-ready; no UPLOAD_PREVIEW polling contract is introduced.
Actual:
  formal_upload now uses materialize_sql_dump_source_preview for upload stage/materialize, including FULL initial/modified paths.
  formal_submit continues to use materialize_sql_dump_source for FINAL materialization.
  materialize_sql_dump_source_preview now emits context, resolve, parse, table loop, and total benchmark events with finalize_canonical_digests=false.
  Focused backend checks passed: snapshot materialization 27 passed; formal app 23 passed; upload preview + submit finalize 5 passed.
Flow/read-model result:
  large INITIALIZE_BASELINE upload returned READY in 34.336 seconds at HTTP/TestClient level.
  submit reached READY in 39.817 seconds with fake repository import and created terminal READY operation.
Bundle open smoke result:
  preview bundle was produced during upload; upload contract remained preview-ready.
Diff/risk result:
  upload comparison core remained the dominant blocking stage at 23589 ms.
Artifacts:
  gateway-data-management-system/backend/backend_vnext/api/formal_upload.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/materializer.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py
Benchmark result:
  Backend upload.total was 33226 ms, down from Step D2 55738 ms and Step D1 51741 ms.
  upload.stage_package was 2068 ms.
  upload.materialize_sql / snapshot_materialize.total was 7342 ms.
  upload parse SQL was 6848 ms; upload table loop was 18 ms.
  upload profile finalize_canonical_digests was false for all table profiles.
  upload row_digest_profile_count was 0.
  submit async finalize was 35334 ms.
  submit profile finalize_canonical_digests was true and submit row_digest_profile_count was 311, confirming row content digest moved to submit FINAL.
Normalized diff/risk oracle result:
  not run
Decision: continue to next upload bottleneck planning
Follow-up:
  D3 restored the intended boundary: upload uses PROVISIONAL facts for preview, submit produces FINAL facts for protected/repository/archive use.
  Remaining upload bottlenecks are SQL parse of all tables, including SKIP tables, and comparison core.
  Candidate next split: parser-level rule-aware skip for SKIP table INSERT rows while preserving version_manager/configuration_generated_at, then comparison-core optimization.
```

```text
Date: 2026-07-06 CST +0800
Slice: Step D4 Rule-aware SQL parse skip
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  not required; no frontend code change
Manual/benchmark actions:
  Reused /tmp/backend-vnext-stepd1-large-store.tar.gz for large backend upload + submit benchmark.
  Ran formal app TestClient INITIALIZE_BASELINE upload and submit-to-READY against /home/issac/test-dir/backend-vnext-formal-benchmark-state-stepd4b-20260706 with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1.
Expected:
  Add parser-level row payload skip for TableStaticRole.SKIP tables without changing upload contract, PROVISIONAL upload semantics, FINAL submit semantics, formal API responses, or table rule injection boundaries.
  Keep rule source inside SnapshotMaterializationInput.table_rule_registry; do not expose a public TableHandlingDecision map parameter.
  Never skip version_manager row parsing so configuration_generated_at remains sourced from SQL version_manager.saved_time.
Actual:
  parse_mysql_dump now accepts an optional table-definition classification hook.
  Materialization passes a hook derived from SnapshotMaterializationInput.table_rule_registry and skips INSERT row expansion for SKIP tables only.
  SKIP table bundles keep row_count, raw SQL digest, fast row digest, and parse skip counters, but do not retain insert statements or expanded rows.
  D2 per-table profiles now expose parse_rows_skipped, parse_skipped_insert_statement_count, and parse_skipped_row_count.
  version_manager remains parsed and materialized as BROWSE_ONLY; configuration_generated_at extraction still works.
  Focused backend checks passed: snapshot materialization 29 passed; formal app 23 passed; upload preview + submit finalize 5 passed.
Flow/read-model result:
  large INITIALIZE_BASELINE upload returned READY in 36.553 seconds at HTTP/TestClient level.
  submit acceptance returned in 3.431 seconds at HTTP/TestClient level.
  submit reached READY in 41.749 seconds with fake repository import and created terminal READY operation.
Bundle open smoke result:
  preview bundle was produced during upload; upload contract remained synchronous preview-ready.
Diff/risk result:
  upload comparison core remained the dominant blocking stage at 25325 ms.
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/sql_parser.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/materializer.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py
Benchmark result:
  Dataset observed: TAR_GZ benchmark package 318379235 bytes, 528 entries.
  Backend upload.total was 35343 ms; upload HTTP/TestClient elapsed was 36553 ms.
  upload.stage_package was 2153 ms.
  upload.materialize_sql / snapshot_materialize.total was 7667 ms.
  upload parse SQL was 7152 ms; upload table loop was 21 ms.
  Rule-aware parse skipped row expansion for 8 SKIP tables, 47 INSERT statements, and 190355 rows.
  Largest parse-skipped tables:
    scdmod_fcda: 92428 rows, 21 INSERT statements.
    device_model_table: 84285 rows, 19 INSERT statements.
    scdmod_yk: 6595 rows, 2 INSERT statements.
    scdmod_dataset: 3241 rows, 1 INSERT statement.
    scdmod_rpt: 2640 rows, 1 INSERT statement.
  Materialized rows remained 246359 across 311 materialized tables.
  upload.preview.run_upload_preview was 25359 ms; comparison_risk.comparison_core was 25325 ms; risk evaluation was 2 ms; surface assembly was 28 ms; bundle assemble was 138 ms.
  submit.sync.stage_package was 2234 ms; submit.sync.sha256 was 194 ms; submit.async.finalize was 38175 ms.
Normalized diff/risk oracle result:
  not run
Decision: continue to comparison-core hotspot profiling/optimization
Follow-up:
  D4 confirms rule-aware parse skip is behaviorally safe and removes unnecessary row payload retention for SKIP tables.
  Parse SQL time did not materially drop below the D3 baseline because the parser still iterates statements, counts rows, and digests raw INSERT values for skipped tables.
  The next high-value optimization target is comparison core, especially the INITIALIZE_BASELINE unchanged self-comparison path and per-table comparison loops.
```

```text
Date: 2026-07-06 CST +0800
Slice: Step E1 Comparison core fast path and hotspot profiling
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_comparison_skeleton.py tests/backend_vnext/unit/test_comparison_compute_stage7.py tests/backend_vnext/unit/test_comparison_ordered_provider.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_comparison_risk_flow.py tests/backend_vnext/unit/test_comparison_projection_table_cache.py tests/backend_vnext/unit/test_comparison_core_cache.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  not required; no frontend code change
Manual/benchmark actions:
  Reused /tmp/backend-vnext-stepd1-large-store.tar.gz for large backend upload + submit benchmark.
  Ran formal app TestClient INITIALIZE_BASELINE upload and submit-to-READY against /home/issac/test-dir/backend-vnext-formal-benchmark-state-stepe1-20260706 with BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1.
Expected:
  Preserve both compare authorities: PROVISIONAL_FAST for upload preview early exit and FINAL_CONTENT for FINAL/protected/history cold compare early exit.
  INITIALIZE_BASELINE self-compare should produce UNCHANGED preview without projection, ordered provider, row indexing, or records artifacts.
  BROWSE_ONLY, SNAPSHOT_ONLY, and SKIP tables must remain filtered out of row compare. Non-empty
  BROWSE_ONLY tables are still eligible for visible surface browsing and current-side snapshot export;
  SKIP/SNAPSHOT_ONLY remain non-comparison, non-browse table-rule exclusions.
Actual:
  Comparison planner now lets same-snapshot pairs route all participating STANDARD/ORDERED tables through SUMMARY_EARLY_EXIT.
  Summary early exit is explicitly justified by SELF_SNAPSHOT, FINAL_CONTENT_DIGEST, or PROVISIONAL_FAST_DIGEST; otherwise it falls back to normal compare/degraded behavior.
  Table diagnostics now include comparison.summary-early-exit with the early-exit reason.
  Comparison benchmark logging now includes plan/provider counts, per-table events, projection build, row index, ordered provider, records build/write, and comparison_core.total.
  Focused backend checks passed: comparison focused 18 passed; snapshot materialization 29 passed; upload preview 3 passed; formal app 23 passed; comparison/cache focused 16 passed; submit finalize 2 passed.
Flow/read-model result:
  large INITIALIZE_BASELINE upload returned READY in 11.637 seconds at HTTP/TestClient level.
  submit acceptance returned in 3.470 seconds at HTTP/TestClient level.
  submit reached READY in 41.686 seconds with fake repository import and created terminal READY operation.
Bundle open smoke result:
  preview bundle was produced during upload; upload contract remained synchronous preview-ready.
Diff/risk result:
  INITIALIZE_BASELINE comparison core used 292 SUMMARY_EARLY_EXIT routes, all with SELF_SNAPSHOT.
  projection_build_count=0, ordered_provider_count=0, row_index_count=0, records_artifact_count=0.
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/comparison/planner.py
  gateway-data-management-system/backend/backend_vnext/capabilities/comparison/engine.py
  gateway-data-management-system/backend/backend_vnext/flows/comparison_risk.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_compute_stage7.py
Benchmark result:
  Dataset observed: TAR_GZ benchmark package 318379235 bytes, 528 entries.
  Backend upload.total was 10307 ms, down from Step D4 35343 ms.
  Upload HTTP/TestClient elapsed was 11637 ms, down from Step D4 36553 ms.
  upload.stage_package was 2403 ms.
  upload.materialize_sql / snapshot_materialize.total was 7614 ms / 7613 ms.
  upload parse SQL was 7084 ms; upload table loop was 17 ms.
  upload.preview.run_upload_preview was 137 ms, down from Step D4 25359 ms.
  comparison_risk.comparison_core was 73 ms, down from Step D4 25325 ms.
  risk evaluation was 1 ms; surface assembly was 59 ms; bundle assemble was 136 ms.
  submit.async.finalize remained 38071 ms because FINAL materialization still computes row content digest during submit.
Normalized diff/risk oracle result:
  not run
Decision: continue to remaining upload optimization only if needed; comparison core is no longer the INITIALIZE_BASELINE bottleneck.
Follow-up:
  The large first-upload path is now below the 20 second target at backend/TestClient level.
  Remaining first-upload blocking cost is dominated by package staging and SQL parse/materialize, not comparison core.
  For true FULL/MODIFIED compare, use the new comparison_core.* benchmark events to identify real projection, ordered provider, row index, and records write hotspots.
```

## Step E2: Summary-Driven Alias Contract

Goal:
  Turn duplicate tables from many physical/logical record copies into one canonical data payload plus logical aliases.
  Keep FINAL authority in SnapshotSummary and use upload-only fast aliases only for preview.

Key decisions:
  Do not add duplicate_group_policy_version.
  Do not add full group history arrays.
  Do not create Dolt SQL views or require every logical table to exist as a physical repository table.
  FINAL duplicate groups are inferred from matching canonical_artifact_ref values in FINAL descriptors.
  previous_canonical_artifact_ref remains a single-hop pointer to the previous mapping.
  PROVISIONAL_FAST aliases are preview/cache-only and must never become archive/history authority.
  CANONICAL aliases come from submit-finalized FINAL/protected summary or repository readback.
  If a duplicate group splits, later equal content must not automatically roll back to the old ref.

### E2a FINAL Canonical Group Resolver

Objective:
  Build the authority model for FINAL duplicate groups.

Implementation target:
  Add a summary-driven resolver that reads previous FINAL summary and current FINAL descriptors.
  Assign current canonical_artifact_ref and previous_canonical_artifact_ref without adding policy/version fields.
  Initial baseline may infer groups from current FINAL facts.
  Later finalize prefers previous summary mapping and only creates new refs when group membership, schema, rules, or compatibility changes.

Non-goal:
  Do not reduce preview bundle size, compare records, or repository physical tables in E2a.

Tests:
  Initial baseline groups duplicate FINAL descriptors.
  Stable duplicate group keeps canonical_artifact_ref.
  Split writes new canonical_artifact_ref and previous_canonical_artifact_ref.
  Later equal content after split does not auto-merge back.
  Explicit incompatible schema/rules force new group refs.

Pause condition:
  If old archive/history semantics require a group merge mechanism, pause and define the explicit resolution source before implementing automatic merge.

### E2b PROVISIONAL Fast Alias Resolver

Objective:
  Add upload-preview-only duplicate aliasing without polluting FINAL facts.

Implementation target:
  Build PROVISIONAL_FAST alias mapping from fast_row_digest, compare_schema_digest, row_count, table rules, compare mode, and required descriptor compatibility.
  Keep version_manager and special fact tables out of unsafe aliasing.
  Store the mapping in preview/bundle metadata, not in FINAL canonical_artifact_ref.

Non-goal:
  Do not let PROVISIONAL_FAST alias feed archive/history or submit-finalized protected summary.

Tests:
  Upload preview can emit PROVISIONAL_FAST aliases.
  Submit finalize recomputes FINAL facts and does not reuse preview alias as authority.
  Missing or mismatched fast facts fall back to normal per-table preview behavior.

Pause condition:
  If fast alias causes visible diff ambiguity for ordered/special tables, restrict aliasing to STANDARD tables before continuing.

### E2c Unified Alias Contract and Frontend Read Path

Objective:
  Expose one alias contract to the frontend while preserving two scopes.

Implementation target:
  Add table_aliases to preview/history bundle metadata with logical_table_name, canonical_table_name, alias_scope, and pair context.
  Frontend table list continues to show logical tables.
  Opening an alias table reads canonical records and displays the logical table name.
  Bundle closure includes canonical records plus alias mapping, not duplicate member records.

Non-goal:
  Do not change submit/review/archive state machines.

Tests:
  PROVISIONAL_FAST alias table opens in preview.
  CANONICAL alias table opens in repository-backed/history bundle.
  Empty unchanged alias members hidden by the surface are omitted from preview bundle alias metadata.
  Bundle contains no host/debug/cache-local fields.
  Missing canonical records makes bundle not READY.

Pause condition:
  If existing UI components assume records file name equals logical table name, pause and adapt the frontend data access boundary before changing bundle generation.

### E2d Compare / Cache Alias Reuse

Objective:
  Stop repeated compare/cache work for duplicate group members.

Implementation target:
  Planner routes only canonical tables to projection/provider/records generation.
  Alias members derive table facts from canonical result plus logical table metadata.
  comparison_core benchmark records duplicate group count, alias member count, reused provider count, and skipped records count.
  PROVISIONAL_FAST cache remains preview-only; CANONICAL cache binds FINAL summary/repository identity.

Non-goal:
  Do not use PROVISIONAL_FAST for history/archive cold authority.

Tests:
  Alias member does not invoke projection, row index, ordered provider, or records writer.
  Canonical result maps to all logical members with stable table facts.
  Scope mismatch falls back to normal compare.
  BROWSE_ONLY/SNAPSHOT_ONLY/SKIP filtering still wins before alias reuse.

Pause condition:
  If table fact digest cannot represent alias-derived facts without changing consumer expectations, pause and update comparison fact contract first.

### E2e Materialization / Repository Canonical Storage Cutdown

Objective:
  Reduce physical storage and repository import work after alias semantics are proven.

Implementation target:
  FINAL repository import writes canonical table data once and persists alias/member descriptors in hidden summary.
  Repository readback restores SnapshotSummary and uses resolver for logical-to-canonical access.
  No Dolt SQL view is required; application layer resolves aliases.
  Archive/history consume FINAL summary resolver instead of assuming every logical table is physical.

Non-goal:
  Do not implement old-data migration; current test state can be cleared.

Tests:
  Repository readback restores canonical_artifact_ref / previous_canonical_artifact_ref and alias mapping.
  Logical alias table can be compared/read through canonical table data.
  Archive graph reads FINAL/protected summary facts only.
  Repository physical table count drops for duplicate groups without losing logical table listing.

Pause condition:
  If repository import replay-only path cannot omit alias tables without breaking validation, pause and split replay compression from hidden-summary alias readback.

```text
Date: 2026-07-06 CST +0800
Slice: Step E2 Summary-driven alias contract documentation
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  not required; documentation only
Frontend command(s):
  not required; documentation only
Manual/benchmark actions:
  not run
Expected:
  Capture the agreed duplicate table virtualization design in authoritative docs.
  Make future E2a-E2e implementation steps discoverable from the migration execution plan.
Actual:
  Documented summary-driven duplicate table virtualization in the snapshot materialization decision memo.
  Updated snapshot, comparison, and comparison bundle contracts with PROVISIONAL_FAST and CANONICAL alias boundaries.
  Added staged E2a-E2e execution notes with goals, non-goals, tests, and pause conditions.
Flow/read-model result:
  not changed
Bundle open smoke result:
  not run
Diff/risk result:
  not changed
Artifacts:
  docs/backend-vnext/notes/snapshot-materialization-decision-memo.md
  docs/backend-vnext/contracts/snapshot.md
  docs/backend-vnext/contracts/comparison.md
  docs/backend-vnext/contracts/comparison-bundle.md
  docs/backend-vnext/notes/formal-contract-migration-execution-plan.md
Normalized diff/risk oracle result:
  not run
Decision: continue to E2a implementation after documentation review
Follow-up:
  Start with FINAL Canonical Group Resolver before changing preview bundle, frontend alias reads, compare/cache reuse, or repository physical storage.
```

```text
Date: 2026-07-06 CST +0800
Slice: E2a FINAL Canonical Group Resolver
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization_repository_ref.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_upload_preview_flow.py
Frontend command(s):
  not required; backend summary authority only
Manual/benchmark actions:
  not run
Expected:
  Add FINAL summary-driven canonical group authority without adding duplicate_group_policy_version or group history arrays.
  Existing callers without previous_summary continue to work.
  Previous FINAL summary drives inherited groups and split detection.
  New tables may join one unambiguous matching current group; ambiguous matches stay separate.
  Repository readback preserves hidden summary canonical refs instead of recomputing them.
Actual:
  SnapshotMaterializationInput now accepts optional previous_summary and validates it is FINAL.
  assign_canonical_artifact_refs now supports previous_summary and keeps the no-previous-summary baseline behavior.
  FINAL materialization and finalize_snapshot_materialization pass previous_summary into canonical ref assignment.
  Repository ref materialization no longer recomputes canonical refs from hidden summary descriptors.
  Added focused tests for initial grouping, stable inherited grouping, new table join, split previous pointer, no auto-merge after split, ambiguous new table separation, and hidden summary ref preservation.
Flow/read-model result:
  not changed
Bundle open smoke result:
  not run
Diff/risk result:
  not changed
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/models.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/materializer.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/repository_ref.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization_repository_ref.py
Normalized diff/risk oracle result:
  not run
Decision: continue to E2b PROVISIONAL Fast Alias Resolver after review
Follow-up:
  E2a does not reduce preview bundle size, compare records, or repository physical table count yet.
  Keep PROVISIONAL_FAST alias work isolated to E2b/E2c and do not feed upload fast aliases into archive/history authority.
```

```text
Date: 2026-07-06 CST +0800
Slice: E2b PROVISIONAL Fast Alias Resolver
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_upload_preview_flow.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  not required; frontend read path remains unchanged in E2b
Manual/benchmark actions:
  not run
Expected:
  Generate upload-preview-only PROVISIONAL_FAST aliases for duplicate STANDARD_DIFF provisional tables.
  Expose alias metadata through preview_strategy_manifest and preview_index.json.
  Do not change FINAL canonical_artifact_ref, submit finalize, archive/history authority, records generation, cache generation, or frontend table reads.
Actual:
  Added build_provisional_fast_table_aliases for PROVISIONAL summaries only.
  Formal upload writes additive table_aliases metadata to preview strategy manifest and preview bundle preview_index.json.
  Legacy preview bundle adapter accepts additive table_aliases metadata while preserving the existing bundle contract.
  Added focused resolver, bundle adapter, and formal upload coverage.
Flow/read-model result:
  not changed
Bundle open smoke result:
  preview_index.json can carry PROVISIONAL_FAST table_aliases; existing frontend may ignore the field until E2c
Diff/risk result:
  not changed
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/models.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/__init__.py
  gateway-data-management-system/backend/backend_vnext/api/formal_upload.py
  gateway-data-management-system/backend/backend_vnext/capabilities/upload_preview_bundle/payloads.py
  gateway-data-management-system/backend/backend_vnext/capabilities/upload_preview_bundle/assembler.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_snapshot_materialization.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py
Normalized diff/risk oracle result:
  not run
Decision: continue to E2c unified alias contract/frontend read path after review
Follow-up:
  E2b does not reduce preview bundle size, compare/cache work, or repository physical table count.
  Keep ORDERED_DIFF aliasing deferred until records/read-path ambiguity is resolved.
```

```text
Date: 2026-07-06 CST +0800
Slice: E2c Unified Alias Contract and Frontend Read Path
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py tests/backend_vnext/unit/frontend formal workbench tests
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_upload_preview_flow.py tests/backend_vnext/unit/test_submit_finalize_flow.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/localWorkbenchBundle.test.js src/workbench/workbenchModel.test.js src/data/previewTableData.test.js
  npm run build
Manual/benchmark actions:
  not run
Expected:
  Frontend parses unified table_aliases metadata and reads canonical table artifacts while preserving logical table UI state.
  History/workbench bundles can carry CANONICAL aliases derived from FINAL summary facts.
  Duplicate records/cache generation and repository physical cutdown remain deferred to E2d/E2e.
Actual:
  Added CANONICAL alias resolver for FINAL summaries and surfaced aliases in history workbench preview_index metadata.
  PreviewIndex parser validates alias scope, pair/view, and logical/canonical table presence.
  Preview table data loading resolves logical aliases to canonical refs for artifact reads while keeping logical risk/filter/cache identity.
  Added focused backend and frontend tests for alias parsing, validation, navigation identity, and canonical artifact reads.
Flow/read-model result:
  formal state machines unchanged
Bundle open smoke result:
  preview/workbench bundle metadata can carry PROVISIONAL_FAST or CANONICAL table_aliases
Diff/risk result:
  unchanged; alias read path only changes artifact source resolution
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/models.py
  gateway-data-management-system/backend/frontend/src/workbench/formalWorkbenchReadModel.ts
  gateway-data-management-system/frontend/src/types/preview.ts
  gateway-data-management-system/frontend/src/data/localWorkbenchBundle.ts
  gateway-data-management-system/frontend/src/data/previewTableData.ts
Normalized diff/risk oracle result:
  not run
Decision: continue to E2d compare/cache alias reuse after review
Follow-up:
  E2c intentionally keeps duplicate member records/cache generation in place.
  E2d should make planner/cache/records generation alias-aware and then validate bundle closure can omit alias member records.
```

```text
Date: 2026-07-06 CST +0800
Slice: E2d Compare / Cache Alias Reuse
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_comparison_compute_stage7.py tests/backend_vnext/unit/test_comparison_core_cache.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py tests/backend_vnext/unit/frontend formal workbench tests
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_upload_preview_flow.py tests/backend_vnext/unit/test_comparison_risk_flow.py
Frontend command(s):
  cd gateway-data-management-system/frontend
  npm test -- src/data/localWorkbenchBundle.test.js src/data/previewTableData.test.js src/workbench/workbenchModel.test.js
  npm run build
Manual/benchmark actions:
  not run
Expected:
  Comparison core consumes table_aliases and executes real compare/records generation only for canonical tables.
  Alias members remain visible as logical table facts but do not carry their own records_ref or records artifact.
  Upload preview uses PROVISIONAL_FAST alias reuse; history/workbench uses CANONICAL alias reuse.
Actual:
  Added alias-aware DirectedComparisonInput and comparison core cache key payload.
  Comparison engine now derives alias member table facts from canonical results and keeps records closure canonical-only.
  Formal upload passes PROVISIONAL_FAST aliases into comparison input and aligns alias pair_id with the real preview view id.
  History compare injects CANONICAL aliases into compare/cache completion inputs.
  Frontend read-path tests now cover logical alias tables without local artifact refs.
Flow/read-model result:
  formal submit/archive/review state machines unchanged
Bundle open smoke result:
  preview/workbench bundle can omit alias member records and rely on table_aliases for canonical reads
Diff/risk result:
  logical table facts and risk targets remain logical; artifact reads are canonical through E2c resolver
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/comparison/models.py
  gateway-data-management-system/backend/backend_vnext/capabilities/comparison/engine.py
  gateway-data-management-system/backend/backend_vnext/cache/comparison_core.py
  gateway-data-management-system/backend/backend_vnext/api/formal_upload.py
  gateway-data-management-system/backend/backend_vnext/flows/history_compare.py
  gateway-data-management-system/frontend/src/data/previewTableData.test.js
Normalized diff/risk oracle result:
  not run
Decision: continue to E2e materialization/repository canonical storage cutdown after review
Follow-up:
  E2d does not remove duplicate physical snapshot/repository tables.
  ORDERED_DIFF alias reuse remains deferred.
```

```text
Date: 2026-07-06 CST +0800
Slice: E2e Materialization / Repository Canonical Storage Cutdown
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_repository_import_artifacts.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization_repository_ref.py tests/backend_vnext/unit/test_repository_import_readback.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/frontend formal workbench tests tests/backend_vnext/unit/test_history_compare_flow.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_submit_finalize_flow.py
  ./.venv/bin/python -m py_compile backend_vnext/capabilities/repository_import/canonical_storage.py backend_vnext/capabilities/snapshot_materialization/canonical_storage.py backend_vnext/capabilities/snapshot_materialization/repository_ref.py backend_vnext/api/formal_submit.py backend_vnext/api/removed formal app adapter
Frontend command(s):
  not run
Manual/benchmark actions:
  not run
Expected:
  Repository import writes only physical canonical tables for FINAL duplicate groups.
  Hidden summary remains the full logical authority and keeps alias member descriptors.
  Repository ref readback resolves logical alias tables through canonical physical readers.
Actual:
  Added summary-driven logical-to-physical table resolver for FINAL repository storage.
  Repository import artifacts and formal submit plans now use physical canonical table sets.
  Repository ref materialization reads logical alias tables from canonical physical catalog tables while returning hidden-summary descriptors.
  Repository import readback validation continues to validate physical plan tables and no longer requires alias member physical tables.
Flow/read-model result:
  formal upload/submit/review/archive state machines unchanged
Bundle open smoke result:
  history/workbench CANONICAL alias metadata remains compatible with E2c/E2d read path
Diff/risk result:
  unchanged; E2e only reduces repository physical storage/import work
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/canonical_storage.py
  gateway-data-management-system/backend/backend_vnext/capabilities/repository_import/canonical_storage.py
  gateway-data-management-system/backend/backend_vnext/capabilities/repository_import/import_artifacts.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/repository_ref.py
  gateway-data-management-system/backend/backend_vnext/api/formal_submit.py
  gateway-data-management-system/backend/backend_vnext/api/removed formal app adapter
Normalized diff/risk oracle result:
  not run
Decision: E2 materialization/repository alias cutdown complete; continue to next reviewed slice
Follow-up:
  E2e does not create Dolt SQL views and does not cut PROVISIONAL upload materialization.
  ORDERED_DIFF alias reuse remains deferred.
```

```text
Date: 2026-07-06 CST +0800
Slice: Submit Fast Validation / Deep Validation Split
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_repository_import_readback.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_repository_import_artifacts.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_submit_finalize_flow.py
Manual/benchmark actions:
  rerun large real-import benchmark with /home/issac/test-dir/business-benchmark-data/business_large/large
Expected:
  Submit READY validation uses hidden FINAL summary plus physical canonical catalog/schema/row-count checks.
  Submit validation does not materialize repository ref rows or execute business table select *.
  Deep row digest validation remains available through VERIFY_TABLE_DIGESTS.
Actual:
  Added VERIFY_HIDDEN_SUMMARY_CATALOG validation policy for submit repository import plans.
  Added repository import readback fast path that validates hidden summary payload, catalog physical table set, schema, and row counts.
  Kept VERIFY_SCHEMA_ROW_COUNT_SUMMARY and VERIFY_TABLE_DIGESTS on the existing deep/materialized readback path.
Flow/read-model result:
  formal submit/review/archive state machines and API contract unchanged
Bundle open smoke result:
  unchanged
Diff/risk result:
  unchanged
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/repository_import/providers.py
  gateway-data-management-system/backend/backend_vnext/capabilities/repository_import/repository_ref_readback.py
  gateway-data-management-system/backend/backend_vnext/api/formal_submit.py
Normalized diff/risk oracle result:
  not run
Decision: after benchmark, decide whether next slice should target FINAL materialization row digest streaming/parallelism
Follow-up:
  Deep row digest validation is not removed; it is reserved for explicit audit/debug paths.
  This slice does not optimize FINAL materialization or Dolt import execution.
```

```text
Date: 2026-07-06 CST +0800
Slice: Repository Fast Validation Batch Metadata
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_repository_import_readback.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_repository_import_artifacts.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_submit_finalize_flow.py
  git diff --check
Manual/benchmark actions:
  rerun large fake-import and real-import benchmark with /home/issac/test-dir/business-benchmark-data/business_large/large
Expected:
  VERIFY_HIDDEN_SUMMARY_CATALOG keeps hidden summary validation strict.
  Physical canonical catalog/schema/count checks use batched Dolt metadata/count queries instead of per-table subprocess calls.
  Deep validation policies keep the existing repository ref materialization/readback behavior.
Actual:
  Added Dolt CLI batch helpers for information_schema.tables, information_schema.columns, and chunked UNION ALL count(*) queries.
  Updated submit fast validation to use batch table/schema/count maps for all physical canonical plan tables.
  Preserved existing diagnostics for hidden summary mismatch, table set mismatch, schema mismatch, and row-count mismatch.
Benchmark result:
  fake-import upload HTTP: 11.612s
  fake-import submit total: 45.837s
  fake-import FINAL materialization: 34.255s
  real-import upload HTTP: 12.355s
  real-import submit total: 66.517s
  real-import FINAL materialization: 36.809s
  real-import Dolt import: 16.430s
  real-import commit: 0.343s
  real-import validation: 1.293s
  real-import repository runner total: 18.216s
  repository import status: PASSED
  repository validation status: PASSED
  configuration_generated_at: 2026-04-12T09:53:25+00:00
Flow/read-model result:
  submit READY no longer blocks on per-table metadata/count subprocess calls
Bundle open smoke result:
  unchanged
Diff/risk result:
  unchanged
Artifacts:
  gateway-data-management-system/backend/backend_vnext/capabilities/repository_import/dolt_cli.py
  gateway-data-management-system/backend/backend_vnext/capabilities/repository_import/repository_ref_readback.py
  gateway-data-management-system/backend/tests/backend_vnext/unit/test_repository_import_readback.py
Normalized diff/risk oracle result:
  not run
Decision: fast validation bottleneck resolved; next performance slice should target FINAL materialization row digest streaming/parallelism before Dolt import tuning
Follow-up:
  If submit total must fall further, prioritize FINAL materialization row digest/table-loop work because it is now larger than repository runner time.
  Dolt import remains a secondary candidate after materialization is reduced.
```

```text
Date: 2026-07-11 CST +0800
Slice: Upload Preview Snapshot Parquet Cache Dry-run Metrics
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Measure whether FULL upload can benefit from snapshot Parquet artifact cache reuse without changing
  bundle closure or actually reusing files in the synchronous preview path.
Implementation plan:
  Add dry-run metrics to `upload.preview.snapshot_parquet_encode`.
  Report exact cache eligibility from `row_layout_digest`; when upload preview remains PROVISIONAL and
  lacks `raw_content_digest`, report `missing_row_layout_digest`.
  Report fast candidate grouping from `fast_row_digest`, export columns, row count, row materialization
  profile, scalar encoding version, and the upload-preview Parquet writer contract version.
  Keep `fast_row_digest` as an upload-local candidate signal only; do not use it as the strong key for
  actual Parquet artifact reuse.
Actual:
  Snapshot Parquet export still writes every actual export task to the bundle root before READY.
  Cache dry-run metrics do not read, write, copy, link, or skip any artifact.
  Future real reuse must use a validated cache store, Parquet artifact validation, bundle-local closure,
  and fallback encode; `row_layout_digest` remains the preferred exact key.
Backend command(s):
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py -q
  gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_upload_preview_bundle_assembler.py -q
Benchmark plan:
  Re-run large INITIALIZE_BASELINE and large-1 + large-2 FULL with
  BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and inspect exact eligibility plus fast candidate reuse groups.
Decision:
  This slice is observability only. If exact eligibility is near zero, preview still lacks a safe
  canonical layout key in the sync path. If fast candidate reuse is high, design a separate validated
  preview export cache before enabling reuse.
```

```text
Date: 2026-07-11 CST +0800
Slice: Snapshot Parquet same-bundle fast candidate ref dedupe
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Reduce upload preview snapshot Parquet encode work by sharing bundle-local browse Parquet refs for
  visible tables with identical fast candidate keys.
  Keep comparison aliases, comparison facts, records artifacts, risk annotations and frontend table
  identity unchanged.
Implementation plan:
  Run snapshot-only fast candidate ref rewrite after normal upload preview snapshot refs are bound.
  Dedupe only within the same selected side (`current` with `current`, `before` with `before`).
  Use the first visible table for each side/key group as the canonical Parquet ref; rewrite later group
  members' selected side ref and `browse_table_ref` to that canonical ref.
  Continue exporting by unique bundle ref so only the canonical Parquet is encoded and written.
  Report `fast_snapshot_ref_dedupe_count`, deduped row/estimated byte counts and dedupe groups in
  `upload.preview.snapshot_parquet_encode`.
Non-goals:
  No persistent cache.
  No cross-side reuse.
  No use of `fast_row_digest` as a long-lived artifact cache key.
  No change to ordered records/risk/table status generation.
Benchmark plan:
  Re-run large INITIALIZE_BASELINE and large-1 + large-2 FULL with
  BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS=1.
  Expect export_task_count to drop from the previous 148 toward about 101 and snapshot encode to drop
  from about 9.3s toward 6-7s if candidate groups remain stable.
Benchmark result:
  Run root: /home/issac/test-dir/backend-vnext-upload-fast-ref-dedupe-20260711-155249
  large INITIALIZE_BASELINE upload.total: 14835 ms.
  large INITIALIZE_BASELINE snapshot_parquet_encode: 6268 ms, logical_table_count=150,
  export_task_count=101, deduped_table_count=49, fast_snapshot_ref_dedupe_count=47.
  large-1 + large-2 FULL upload.total: 40442 ms.
  FULL comparison_core.total: 18469 ms.
  FULL snapshot_parquet_encode: 6080 ms, logical_table_count=150, export_task_count=101,
  deduped_table_count=49, fast_snapshot_ref_dedupe_count=47.
  b1_n11~18_iec104_syx_list share tables/current/b1_n11_iec104_syx_list.parquet in both generated
  preview bundles; the member parquet files such as b1_n12_iec104_syx_list.parquet are not emitted.
Decision:
  Keep same-bundle fast candidate ref dedupe. It removes about 47 extra snapshot export tasks on the
  large sample and drops serial snapshot encode from about 9.3s to about 6.1s without changing
  comparison/risk/records identity.
```

```text
Date: 2026-07-11 CST +0800
Slice: Comparison Core run-local duplicate input reuse
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Reduce FULL comparison work for repeated ordered tables whose input rows are identical under the
  same fast candidate key.
  Reuse only transient in-memory projection rows and ordered prepared rows inside one
  `ComparisonEngine.compare()` call.
  Keep table facts, records refs, risk targets, ordered digests and logical table identity independent
  for every table.
Implementation:
  Added a comparison-run reuse context with two caches:
    - projection rows cache keyed by side, fast_row_digest, descriptor column shape, row_count,
      materialization/scalar contract and selected projection columns;
    - ordered prepared rows cache keyed by side, fast_row_digest, projected column shape, stable key,
      position field and pseudo blank policy.
  `self_project()` may reuse cached projected row tuples, but still wraps a fresh `ProjectionTable`
  for the current logical table and recomputes `projection_logical_digest` with that table's
  projection schema digest.
  Ordered provider may reuse prepared rows, but still recomputes ordered digest, semantic ops,
  records artifact, risk inputs and ordered extension per logical table.
Benchmark additions:
  `comparison_core.projection_build` now reports comparison-run projection row cache hit/miss details.
  Ordered `prepare_rows` phase reports prepared-row cache eligibility, hits, source table and saved rows.
  `comparison_core.run_reuse_summary` reports aggregate projection/prepared hit counts and saved rows.
Non-goals:
  No table-level parallelism.
  No persistent cache.
  No ordered digest / records / risk artifact reuse.
  No comparison alias expansion for ordered tables.
Validation plan:
  Focused unit tests cover two duplicate ordered tables where the second table hits projection and
  prepared-row caches while keeping separate records refs.
  Large FULL benchmark should compare `comparison_core.total`, projection_build sum/count and
  ordered prepare phase time against the previous 18.5s comparison_core baseline.
Validation result:
  Backend unit:
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_compute_stage7.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py -q
    -> 82 passed.
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
    -> 351 passed, 1 skipped.
  Benchmark run:
    /home/issac/test-dir/backend-vnext-comparison-run-reuse-20260711-164249
    INITIALIZE_BASELINE large upload.total: 15895 ms.
    FULL large-1 + large-2 upload.total: 35568 ms.
    FULL comparison_core.total: 12189 ms, down from the previous about 18469 ms run.
    FULL projection_build events: 24 total, 20 comparison-run projection row hits,
    saved rows=196550, aggregate duration=6705 ms.
    FULL ordered prepare phase: 12 events, 10 prepared cache-hit tables, saved rows=196550,
    aggregate prepare duration=353 ms.
    FULL run_reuse_summary: projection_rows_cache_hit_count=20,
    ordered_prepare_cache_hit_count=20.
  Observation:
    Projection row cache hits still spend about 230-240 ms per side on table-specific
    projection logical digest recomputation; the row projection/prepare duplication is removed,
    but projection digest remains a visible next bottleneck.
Decision:
  Keep this optimization. It cuts FULL comparison_core by about 6.3s on the large-1 + large-2
  benchmark without changing records/risk/table identity. Next comparison-core work should focus on
  projection logical digest cost or ordered digest/algorithmic cost, not prepare-row micro copying.
```

```text
Date: 2026-07-11 CST +0800
Slice: Projection logical digest two-layer row digest reuse
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Keep the existing projection_logical_digest payload and table-specific semantics, but avoid
  recomputing row_identity_digest and projected_row_value_digest when comparison-run projection rows
  cache hits a duplicate input table.
Implementation:
  Added build_projection_logical_digest_from_parts() to wrap existing row digest parts with the
  current table's projection_schema_digest.
  ProjectionBuilder now keeps ProjectionLogicalDigestParts on the in-memory ProjectionRowsReader.
  Comparison-run projection rows cache entries carry those parts; cache-hit projections use the
  wrapper-only path when parts are available, and fall back to the previous full recompute for
  persistent cache or manually constructed readers that lack parts.
  Benchmark projection_build hit events report projection_digest_parts_reused,
  projection_digest_wrapper_only and projection_digest_recompute_fallback.
  comparison_core.run_reuse_summary reports digest-parts reuse/fallback counts and saved rows.
Non-goals:
  No change to final projection_logical_digest payload.
  No cross-table final digest reuse.
  No snapshot summary or bundle contract change.
  No ordered digest/core result reuse and no table-level parallelism.
Validation result:
  Backend unit:
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_projection_digest.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py -q
    -> 18 passed.
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_compute_stage7.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py -q
    -> 82 passed.
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
    -> 354 passed, 1 skipped.
Benchmark plan:
  Re-run large INITIALIZE_BASELINE and large-1 + large-2 FULL with
  BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS=1.
  Compare FULL comparison_core.total and projection_build aggregate with the previous
  /home/issac/test-dir/backend-vnext-comparison-run-reuse-20260711-164249 baseline.
Benchmark result:
  Run root: /home/issac/test-dir/backend-vnext-projection-digest-parts-20260711-201838
  large INITIALIZE_BASELINE upload.total: 14745 ms.
  large-1 + large-2 FULL upload.total: 30004 ms.
  FULL comparison_core.total: 7289 ms, down from the previous 12189 ms run.
  FULL projection_build events: 24 total, 20 comparison-run projection row hits,
  projection_digest_parts_reuse_count=20, fallback_count=0, saved rows=196550.
  FULL projection_build aggregate duration: 1963 ms, down from 6705 ms; hit duration sum was 0 ms.
  FULL ordered_digest phase remains the largest ordered hot path at about 2856 ms aggregate.
  Snapshot parquet encode stayed stable: export_task_count=101, fast_snapshot_ref_dedupe_count=47.
Decision:
  Keep. The two-layer digest removes the duplicate projection logical digest cost while preserving
  table-specific final digests and records/risk/table identity. The next obvious comparison-core
  target is ordered_digest/core algorithm cost.
```

```text
Date: 2026-07-11 CST +0800
Slice: Ordered digest two-layer prepared row payload reuse
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Reduce ordered_digest cost for duplicate ordered tables without changing final ordered digest
  payload semantics, ordered extension, records, risk annotations or table identity.
Implementation:
  Added OrderedRowsDigestParts plus build_ordered_rows_digest_parts() and
  build_ordered_rows_digest_from_parts().
  build_ordered_rows_digest() keeps its public API and final digest equal to the old payload shape.
  To preserve exact compatibility, digest parts store the prebuilt ordered row payload list; wrapper
  still emits the legacy payload with the current table_name.
  OrderedPreparedRowsCacheEntry can retain ordered digest parts. OrderedDiffEngine writes parts after
  computing a side digest and reuses them on later prepared-cache hits for the same side/key.
  Benchmark ordered_digest phase reports ordered_digest_parts_reused_*, wrapper_only_*,
  recompute_fallback_* and saved row counts. comparison_core.run_reuse_summary reports aggregate
  ordered digest parts reuse/fallback/saved rows.
Non-goals:
  No final ordered digest reuse across logical tables.
  No change to ordered table digest, semantic ops, records, replay validation or risk.
  No table-level parallelism.
Validation result:
  Backend unit:
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py -q
    -> 16 passed.
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_compute_stage7.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py -q
    -> 69 passed.
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
    -> 357 passed, 1 skipped.
Benchmark plan:
  Re-run large INITIALIZE_BASELINE and large-1 + large-2 FULL with
  BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS=1.
  Compare FULL ordered_digest aggregate and comparison_core.total against
  /home/issac/test-dir/backend-vnext-projection-digest-parts-20260711-201838.
Benchmark result:
  Run root: /home/issac/test-dir/backend-vnext-ordered-digest-parts-20260711-203142
  large INITIALIZE_BASELINE upload.total: 14254 ms.
  large-1 + large-2 FULL upload.total: 29879 ms.
  FULL comparison_core.total: 6955 ms, roughly comparable to the previous 7289 ms run and within
  benchmark noise for this slice.
  FULL ordered_digest aggregate: 2863 ms, effectively unchanged from the previous about 2856 ms.
  ordered_digest_parts_reuse_count=20, fallback_count=0, saved rows=196550, but hit-event duration
  remained about 2148 ms because exact legacy digest compatibility still requires hashing the full
  rows payload with table_name.
Decision:
  Reverted. The experiment proved that preserving the exact legacy ordered digest payload prevents
  a useful wrapper-only speedup: prebuilding row payload avoids some object construction, but the
  dominant canonical JSON/hash cost remains. Future ordered_digest optimization should use a
  versioned digest contract change or target ordered core/algorithm reuse instead.
  Post-revert regression: ordered_provider + compute_stage7 + formal_app -> 82 passed;
  full backend_vnext/unit -> 354 passed, 1 skipped.
```

```text
Date: 2026-07-11 CST +0800
Slice: Ordered digest v2 and ordered core reuse design
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
Expected:
  Implement Phase 1 ordered digest v2 so repeated ordered tables can reuse table-independent
  ordered row content digest parts.
  Document Phase 2 ordered core/semantic result reuse but do not implement it in this slice.
Implementation:
  Bumped ORDERED_DIFF_CONTRACT_VERSION to backend-vnext/ordered-diff/v2.
  Ordered rows digest now has two layers: OrderedRowsDigestParts contains side, stable key,
  position field, ordered_policy_digest and ordered_row_content_digest; final digest wraps those
  parts with the current canonical table_name and ordered_digest_contract_version.
  OrderedPreparedRowsCacheEntry can hold ordered digest parts. OrderedDiffEngine writes parts on
  first computation and reuses them on later prepared-cache hits for the same side/key.
  Records manifest metadata and ComparisonOrderedExtension carry ordered-diff v2.
  Benchmark ordered_digest phase reports parts reuse/wrapper-only/fallback and saved rows; run
  summary reports aggregate ordered digest parts reuse/fallback/saved rows.
Phase 2 design:
  Future ordered core/semantic result cache may reuse only table-independent semantic templates
  such as prescan/topology/semantic ops/replay validation.
  It must regenerate final ordered digests, records artifacts, risk annotations, diagnostics and
  table facts for each logical table.
  Phase 2 should be planned separately after v2 digest benchmark results.
Non-goals:
  No ordered core/semantic result reuse in this slice.
  No table-level parallelism.
  No old bundle migration; rerun upload/history comparison to get v2 digests.
Benchmark plan:
  Re-run large INITIALIZE_BASELINE and large-1 + large-2 FULL with
  BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 and BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS=1.
  Compare FULL ordered_digest aggregate and comparison_core.total against
  /home/issac/test-dir/backend-vnext-projection-digest-parts-20260711-201838.
Validation result:
  Backend unit:
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_ordered_provider.py -q
    -> 16 passed.
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_compute_stage7.py gateway-data-management-system/backend/tests/backend_vnext/unit/test_formal_app.py -q
    -> 69 passed, 4 warnings.
    gateway-data-management-system/backend/.venv/bin/pytest gateway-data-management-system/backend/tests/backend_vnext/unit -q
    -> 357 passed, 1 skipped, 4 warnings.
Benchmark result:
  Run root: /home/issac/test-dir/backend-vnext-ordered-digest-v2-20260711-205158
  large INITIALIZE_BASELINE upload.total: 14179 ms.
  large-1 + large-2 FULL upload.total: 25349 ms, down from 30004 ms in
  /home/issac/test-dir/backend-vnext-projection-digest-parts-20260711-201838.
  FULL comparison_core.total: 4221 ms, down from 7356 ms.
  FULL ordered_digest aggregate: 556 ms, down from 2856 ms.
  FULL ordered phase aggregates after v2: prepare_rows 330 ms, replay_validation 278 ms,
  records_build 302 ms, semantic_ops 251 ms, topology_plan 170 ms.
  ordered_digest_parts_reuse_count=20, fallback_count=0, saved rows=196550.
  10 duplicate ordered tables reused both before/current row content digest parts; the two canonical
  tables computed full parts and subsequent duplicates were wrapper-only.
Decision:
  Keep ordered digest v2. The contract version bump unlocks the intended wrapper-only path and
  removes about 2.3 seconds from ordered_digest itself, with about 3.1 seconds reduction in
  comparison_core.total and about 4.7 seconds reduction in FULL upload.total on the large benchmark.
  Phase 2 ordered core/semantic result reuse remains design-only and should be evaluated separately
  against the now-lower comparison_core baseline.
```

```text
Date: 2026-07-06 CST +0800
Slice: FINAL Materialization Row Digest Streaming + Fixed Two-Lane Parallelism
Operator: Codex
Environment:
  repo: /home/issac/test-dir/fasttest-mysql
  branch: formal-contract-migration
Backend command(s):
  cd gateway-data-management-system/backend
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_snapshot_materialization_repository_ref.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_repository_import_readback.py tests/backend_vnext/unit/test_repository_import_artifacts.py
  ./.venv/bin/pytest -q tests/backend_vnext/unit/test_formal_app.py tests/backend_vnext/unit/test_submit_finalize_flow.py
Expected:
  FINAL row digest keeps the existing digest contract while avoiding large normalized row payload objects.
  FINAL materialization uses fixed two-lane batch parallelism when table count/row thresholds are met.
  PROVISIONAL upload preview does not compute raw/business content digest and does not use the FINAL parallel path.
Actual:
  Added streaming row digest helpers that sort per-row canonical bytes and preserve the existing {"rows": ...} digest semantics.
  Updated FINAL materialization, finalize-from-PROVISIONAL, and snapshot readers to reuse the streaming digest path and cache FINAL reader content digests.
  Added fixed two-lane FINAL materialization: parent process handles table rules/request filters, lanes are greedily balanced by row_count, and only two batch jobs are submitted.
Benchmark result:
  fake-import upload HTTP: 11.612s
  fake-import submit total: 30.138s
  fake-import FINAL materialization: 19.444s
  fake-import FINAL table loop: 11.797s
  real-import upload HTTP: 10.843s
  real-import submit total: 45.232s
  real-import FINAL materialization: 19.496s
  real-import FINAL table loop: 11.733s
  real-import Dolt import: 13.873s
  real-import commit: 0.250s
  real-import validation: 0.834s
  real-import repository runner total: 15.289s
  FINAL parallel lane row counts: 123180 / 123179
  FINAL parallel worker compute: about 10.2s
  FINAL parallel wait/merge: about 11.6s
  repository import status: PASSED
  repository validation status: PASSED
  configuration_generated_at: 2026-04-12T09:53:25+00:00
Flow/read-model result:
  formal upload/submit API contract unchanged
Bundle open smoke result:
  unchanged
Diff/risk result:
  unchanged
Artifacts:
  gateway-data-management-system/backend/backend_vnext/core/row_digests.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/materializer.py
  gateway-data-management-system/backend/backend_vnext/capabilities/snapshot_materialization/readers.py
Normalized diff/risk oracle result:
  not run
Decision: FINAL materialization is improved; next performance slice should target SQL row expansion/parser-level streaming before further Dolt import tuning
Follow-up:
  Fixed two-lane parallelism is controlled by BACKEND_VNEXT_SNAPSHOT_MATERIALIZE_FINAL_WORKERS and BACKEND_VNEXT_SNAPSHOT_MATERIALIZE_PARALLEL_MIN_ROWS.
  BACKEND_VNEXT_SNAPSHOT_MATERIALIZE_HEAVY_TABLES can prioritize known large tables while still keeping two lanes balanced.
```
