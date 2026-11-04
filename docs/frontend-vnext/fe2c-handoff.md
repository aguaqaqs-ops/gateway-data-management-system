# FE2c 定向修复 handoff（第 3 轮）— R1–R5 / m1–m6

- 候选提交：`9518278fef1ca43f42bdf0e76461ba95c21658e2`，`frontend/` tree `88f51b147120baf11040ac74978cbc0bd2e72103`。
- 复审范围：`e42d40e52614385f2242acbc46592b431a6fcc5a..<本 handoff 提交>`；05 detached worktree `/home/dev/gdds-fe-fix3-9518278fef-05`，运行和 handoff 前均为已提交 clean 状态。
- 依据：`docs/frontend-vnext/reviews/fe2c-rereview-2.md`（R1–R5、m1–m6）、《FE2 kickoff》§9 Q18（owner 2026-11-04）、§7.1“生成入口”“上传包的后端校验”、AGENTS“前端测试（FD7）”“镜像身份”。
- 05 完整 runner：exit 0，130 unit tests + 31 e2e，93 张截图；上传包校验脚本：exit 0，4/4 package 符合预期。04 取证待复审通过后一次运行。
- bundle：`/home/dev/gdds-test-tmp/fe2c-fix3-9518278fef.bundle`，SHA256 `9b0dc16197045614744e5292344e5c9052f518c595a44be270c048932e4f38e4`。

## 1. 提交清单

`git log --oneline e42d40e526..HEAD`：

```text
9518278fef test(frontend): fix regex escaping in upload conflict e2e
2ff96ebc53 fix(frontend): resume submit on comparison page and align round-3 e2e
e084e64413 fix(frontend): use frontend copy for unexpected upload failures
bfdcda3537 fix(frontend): FE2c round-3 Q18, conflict recovery and validator entry
98bfb9522a Merge branch 'main' into fe-vnext
5028b9f9d1 docs(frontend-vnext): record FE2c D1 decision Q18 (no empty-baseline disable in FE2)
c22e9fe01f docs(frontend-vnext): FE2c rereview-2 (targeted fixes, narrow)
```

## 2. 逐项对照

| ID | 提交 | 测试 / 用例 | 截图 | 状态 |
| --- | --- | --- | --- | --- |
| R1 按 Q18 删除空基线禁用 | `bfdcda35` | 删除 `emptyBaseline`、两段说明与 `FE2c 首批空基线禁用原始组态备份`；`FE2c 上传步骤卡校验目录并锁定页面` 断言第 ① 步“可选”且可操作 | `upload-selected-*`、`upload-empty-*` | 完成 |
| R2 确定 4xx 丢弃 key/结果，版本冲突改刷新 | `bfdcda35` | e2e：`FE2c 上传版本冲突后刷新再上传使用新版本与新 key`（点击“刷新”，第二次上传 `expected_workspace_version` 12→14、key 换新并成功）；探针见 §4 | `upload-version-conflict-*` | 完成 |
| R3 校验脚本按生成入口约束 | `bfdcda35` | `frontend/scripts/validate-upload-package.sh`：preflight 按镜像 `inputs.json` 比对 `uv.lock`/`.python-version`（不符 exit 2），`pyproject.toml`/`Cargo.lock` 只记录；`docker-save-image-identity.py` 取 config digest 与全部 DiffID；空输出目录、worktree 外日志与 `.sha256`；4 包结果符合预期 | 脚本日志见 §3 | 完成 |
| R4 错误提示分行并保持在对话框内 | `bfdcda35` | 审核、提交、归档、上传统一 `.form-error` 分行布局；e2e `FE2c 审核 403、版本冲突与超时重试复用同一幂等键` 在 1280 断言“刷新审核信息”按钮边界框完全落在对话框内；探针见 §4 | `review-version-conflict-*`、`submit-aborted-*`、`archive-audit-conflict-*`、`upload-failure-retry-*` | 完成 |
| R5 退回/归档切换到对应身份并核对 token | `bfdcda35` | `FE2c 审核退回必须填写理由并可撤回` 以 `reviewer` 发起并断言 `/review-events` 为 `Bearer dev-token-reviewer`；`FE2c 归档主线确认预检、异常与影响` 以 `archive-confirmer` 发起并断言归档、确认、异常请求均带 `Bearer dev-token-archive-confirmer`；撤回仍为提交人 | `review-reject-dialog-*`、`review-withdraw-dialog-*`、`archive-mainline-*` | 完成 |
| m1 操作状态回调引用稳定 | `bfdcda35` | `OperationStatusPanel` 用 ref 保存回调，effect 只依赖 `operationId` 与刷新计数；`FE2c 执行中刷新后恢复页面锁定并继续到差异浏览` 通过 | — | 完成 |
| m2 固定时钟、前端文案、去掉相反状态卡 | `bfdcda35`、`e084e644` | `FE2c 上传失败后重试不重复上传` 先 `freezePageClock`；失败标题取前端文案（不再显示模拟接口 `message`）；上传进行中隐藏通用操作卡，失败后 URL 已清理，无“已完成/失败”并存 | `upload-failure-retry-*` | 完成 |
| m3 空基线两段说明 | `bfdcda35` | 随 R1 删除，无残留 | — | 完成 |
| m4 提交刷新后成功入口 | `bfdcda35`、`2ff96ebc` | 提交受理时在 `sessionStorage` 记录 operation/attempt；比较页与工作台在刷新后显示操作卡，成功后读取 attempt 并进入 `mode=REVIEW` 提交结果；e2e `FE2c 提交执行中刷新后成功后进入提交结果` | — | 完成 |
| m5 生产构建文字检查不作为 N6 证据 | — | 保留 `check:production-build`，本表不将其列为 N6 的证据；N6 由就地错误码与复制按钮的 e2e 支撑 | — | 完成 |
| m6 归档异常目标提交注释 | `bfdcda35` | 归档场景注释说明异常目标固定为 `submission-1`，候选显示名可切换为 `fe2a-history-ref-2`，两者不要求相等 | `archive-blocked-*` | 完成 |
| N7（上一轮复核）写操作场景 | `bfdcda35` | 上传/Preview、审核、归档的 403 与 route 声明的版本/幂等冲突，提交 ABORTED、归档阻断项均保留；审核用审核人、归档用归档人并核对 token | `archive-blocked-*`、`submit-aborted-*` | 完成 |
| N8（上一轮复核）阶段名与摘要 | `bfdcda35` | MODIFIED_ONLY 显示“上传本次归档组态 → 解析预览 → 下载预览结果 → 写入本地 → 完成”；摘要行仅在未选择目录时显示；首批空基线禁用已按 Q18 撤回 | `upload-running-modified-only-*`、`upload-selected-*` | 部分（空基线项按 Q18 撤回，见 §6） |

## 3. 05 运行清单

全部在 `gw-dms-test-05.lan` 的已提交 clean worktree 运行；日志目录 `/home/dev/gdds-fe-logs/fe2c/fix-3`。

| HEAD | 开始（UTC） | exit | 日志 | SHA256 |
| --- | --- | --- | --- | --- |
| `bfdcda3537` | 2026-11-04T11:55:17Z | 2 | `frontend-tests-20261104T115517Z.log` | `3b3062cb5064da23aca76913280c0ccea46f3c930936add83082e8e2364e4d09` |
| `e084e64413` | 2026-11-04T11:56:24Z | 0 | `frontend-tests-20261104T115624Z.log` | `c93735bbd2c3dc991a8400e340a5f32591f6edc9a18d8d22d2fc8a39606bbd6b` |
| `e084e64413` | 2026-11-04T11:57:13Z | 1 | `frontend-tests-20261104T115713Z.log` | `50c13ddc31c41f1705d51038e7f8aabc11898e95dfcccebe36bf1f9d788ac4a5` |
| `2ff96ebc53` | 2026-11-04T12:00:09Z | 1 | `frontend-tests-20261104T120009Z.log` | `f6d06e2897ba5f9deb4948505d886f432bdaa26c40bee761d8fc4b0f756fbe10` |
| `9518278fef` | 2026-11-04T12:01:07Z | 0 | `frontend-tests-20261104T120107Z.log` | `84f0073979fe11592c0f8a458fc408ede9099859a5e178a43fa95caf75d37194` |
| `9518278fef`（校验脚本） | 2026-11-04T12:02:07Z | 0 | `upload-validator-9518278fef-20261104T120207Z-1070818.log` | `6608dc3dcedd8092cc2a226da8a645cbd9d72e573a2e7a4487497ffbd426f15a` |

第 1 次运行因遗漏 `refresh` 字段在 typecheck 失败；第 3 次运行有 3 个 e2e 失败（提交刷新后比较页缺少续做入口、上传失败文案、版本提取正则）；第 4 次运行因正则转义被 lint 拒绝。每次修复均追加提交后从头重跑，未改写已运行提交。

## 4. 探针

在一次性 worktree `/home/dev/gdds-fe-probe-fix3-05` 中完成，完成后已删除。

| 探针 | HEAD | exit | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| R2：保留 4xx 后的 key/版本（不丢弃） | `31a5b55e` | 1 | `FE2c 上传版本冲突后刷新再上传使用新版本与新 key` 失败（第二次仍为旧版本/旧 key） | `82392c57e2b63425ddde1ef1aa1ade2466e9ce3b5c890f571f6a34d50c78ff91` |
| R4：错误提示改回单行内联 | `ae0cd534` | 1 | 审核 e2e 的对话框边界断言失败 | `f755d9a66d097b27b3d636d6ebc810e097f43a9e14ed571ba73659cad55a6184` |
| R3：`uv.lock` 改一个字节 | `c77ed667` | 2 | preflight 报 `required_input_mismatch=backend/uv.lock`，未进入打包 | `3382e7b9407f2554a2a57e9e7c997d279926eaece8e979cf331c36a902b83c85` |
| R3：输出目录非空 | `9518278fef` | 2 | `output directory must be empty before validation`，未进入 preflight/打包 | `bbb24e0afa32aa2734d8ebe0742bac356e59e6bc86b8cdd1d5e20eb4a1740e47` |

R2 探针的前两次尝试分别因未使用变量导致 typecheck 失败、以及只删除了 catch 中的重置而 `refreshAfterConflict` 仍重置进度，均未触发目标断言（日志 `0cbc53f9…`、`e3adfce8…`）；修正为同时不重置后得到上表结果。

## 5. 截图

- 目录：`/home/dev/gdds-fe-evidence/fe2c/fix-3-9518278fef-05`，93 张 png，1280/1920 双宽度。
- 聚合 SHA256：`4286296a77d60259479628fa1cc9675497d60acb3423316aa8df7516c9bd0e25`（`find -name '*.png' -print0 | sort -z | xargs -0 sha256sum | sha256sum`）。
- R4/R5 重拍：`review-version-conflict-*`、`review-reject-dialog-*`、`review-withdraw-dialog-*`、`archive-mainline-*`；`upload-failure-retry-*` 同时固定了页面时钟。R1 删除 `upload-empty-baseline-*`。

## 6. 偏差

- 首批空基线不再禁用上传第 ① 步，也不显示空基线说明；依据 Q18 甲，缺口已登记在前端 kickoff §3.3（History 尚无“基线为空”的事实）。上一轮 N8 的该子项随之撤回，N8 状态记为“部分”。
- 无其他偏差。

## 7. 复现与证据环境

- 工具链镜像 `mcr.microsoft.com/playwright:v1.64.1-noble`：config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；RootFS DiffID 共 7 个，见 runner 日志。
- 依赖镜像 `gateway-backend-deps:lock-d054366c02fa`：config digest `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`；RootFS DiffID 共 19 个，见校验脚本日志。
- 两者身份均由 `docker image save` + `frontend/scripts/docker-save-image-identity.py` 取得，不使用 `docker image inspect .Id`。
- npm 缓存：`/home/dev/gdds-fe-cache/fe0/npm-cache`，来源归档 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交 `a2fb4a027a6f62218109783674cfc37bd64e14a5`。
- 校验脚本输出目录 `/home/dev/gdds-fe-evidence/fe2c/fix-3-9518278fef-upload`，日志目录 `/home/dev/gdds-fe-logs/fe2c/fix-3`，均在 worktree 外；preflight 记录 `pyproject.toml` 与 `Cargo.lock` 与镜像记录不同（只记录，不阻止）。

## 8. 复审与 04 取证

- 复审对象：`e42d40e526..<本 handoff 提交>` 的提交区间；候选 `9518278fef`。
- 04 完整运行与截图待复审通过后执行一次；本轮未在 04 运行。

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
