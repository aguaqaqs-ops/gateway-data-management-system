# FE3b 交接：审核定向修复（B1–B9）第 1 轮

审核报告 `docs/frontend-vnext/reviews/fe3b-review.md`（main `704509b6b3`）的定向修复。
范围：只修报告列出的问题，不做 FE3c。本文件为单独的文档提交，不改动代码。

## 0. 摘要

- 分支 `fe-vnext`，起点 `afd7711e4b`（代码候选 `5a0cdbad9c`）。
- 代码候选 **`403e2faefc`**（`frontend/` 树 `4d5a8356`）；`vnext/` 树
  `56720104af`，与 `748de5034d` 相同。相对 `748de5034d` 的差异只含
  `frontend/` 与 `docs/frontend-vnext/`。
- 07 `run-tests.sh --e2e --screenshots`：exit 0，单测 32 文件 171 项、Playwright
  55 项全过，截图 138 张（69 组 × 1280/1920，聚合 SHA 见 §8）。
- 05 `--suite journeys --subphase fe3b`：18/18，exit 0，`openapi_compare=match`，
  `cleanup_status=ok`。
- 05 `validate-upload-package.sh`（修复后）：4 个包、0 失败，exit 0；后端校验
  镜像由脚本在本机以 `GATEWAY_DOCKER_BUILD_NETWORK=none` 构建（venv
  `/app/backend/.venv`），config digest 与全部 RootFS DiffID 已记入日志。
- 4 个回归探针各使对应用例失败（§9），探针提交只在节点上，复审后已清理
  worktree，保留 `refs/review/fe3b/probe-*-fix4` 供复核。
- `fe3b-upload-validator:latest` 与 `fe3b-upload-backend:latest`（本轮之前手工
  构建）已删除。

## 1. 合并与路径核对

| 项 | 结果 |
| --- | --- |
| 代码候选 | `403e2faefc` |
| `HEAD:vnext` | `56720104af`（与 `748de5034d:vnext` 相同） |
| `git diff --name-only 748de5034d HEAD` | 仅 `frontend/` 与 `docs/frontend-vnext/` 下的路径 |
| 未推送、未改写已有提交 | 是；探针提交只在 07 节点仓库的 `refs/review/fe3b/probe-*-fix4`，不在 `fe-vnext` 上 |

## 2. B1–B9 逐条处理

### B1 上传步骤卡占用禁用

- `UploadStepCard` 新增 `occupancyReason` 输入（`UploadStepCard.tsx`），只禁用
  “上传并生成预览”并显示与工具栏相同的原因；目录选择按钮不受占用影响。
- `WorkbenchPage` 把 hook 的 `gates.upload` 原因同时传给工具栏与步骤卡，
  删除了自己的 `uploadOccupancy` 规则。
- 用例：W8 模拟（`upload-mode.spec.ts`）断言步骤卡按钮禁用、原因文本与目录
  选择可用，撤回后恢复可用；真实 `r4-submit`、`r7-withdraw`（W8 段与 W2 段）、
  `r7-approved` 断言步骤卡按钮的禁用与原因、撤回后恢复。

### B2 一次性重读

- `useUploadModeState` 在 gates 要求 `reread` 时重读一次工作区（`rereadKey`
  按 workspace 指针 + review 状态 + 处置 + attempt 状态 pin，
  `rereadConsumed` 保证每种过时快照只重读一次，不循环）。
- hook 用 in-flight 去重，StrictMode 双挂载只发一次工作区请求；W10-recovery
  用例断言恰好 2 次工作区请求。
- 用例：W10 新增“陈旧指针重读后恢复可用”一支（workspace 表与 Preview 页都
  覆盖）。该用例不依赖 StrictMode 双执行：去掉重读逻辑后终局原因常驻，
  用例失败（探针 P-B2，§9）。

### B3 续做后状态一致

- `resumeAfterOperation`（hook）：操作到终态后先重读工作区，再用已知
  attempt ID 重读 attempt（取 `abort_code`）与其 operation，同步更新页面持有
  的 workspace、attempt、operation 及各自读取错误；禁用原因只从同一份状态
  派生。
- 删除虚构的 operation `ABORTED`：`journeys.ts` 的 `pollOperation` 终态、
  `OperationStatusPanel` 的完成集合、`upload-header.ts` 的 `TERMINAL`。
  终态集合为 `SUCCEEDED/FAILED/CANCELLED/SUPERSEDED`，
  `MANUAL_RECOVERY_REQUIRED` 单独处理；`CANCELLED`/`SUPERSEDED` 下 attempt
  未结束显示“需要管理员处理”（单测覆盖）。
- `n3/W9①` 改为可达序列：加载时 attempt `PREPARED` + 操作 `RUNNING`；
  结束后 attempt `ABORTED` + `abort_code`，两个指针清空。正式用例覆盖演示
  c（工作区/attempt 读取失败→“无法确认提交状态”，不再与“提交正在执行”并存，
  W9②③）与演示 d（`IMPORT_REJECTED` 可见，W9①）。

### B4 两页共用 hook

- 新增 `useUploadModeState`（`frontend/src/features/workbench/use-upload-mode.ts`）：
  读取 workspace→review→attempt→operation，续做结束后的重读（B3）与一次性
  重读（B2），记录各项“加载中”与“读取失败”，输出 `deriveUploadModeGates`。
- `ComparisonPage` 与 `WorkbenchPage` 只消费该 hook；工作台自己的占用规则
  已删除。
- `deriveUploadModeGates` 区分“加载中”与“读不到”：首次读取完成前显示
  “正在读取提交状态”，不显示“无法确认提交状态”与“重试读取”（一并解决 N3）。
  attempt 已知而操作读取中时保持“提交正在执行”（单测覆盖）。
- 单测覆盖工作台分支：`MANUAL_RECOVERY_REQUIRED`、终态 + attempt 未结束、
  `CANCELLED`、`SUPERSEDED`、已关闭 attempt 按提交指针判断、上传侧终局重读。
- 顺手拆分：Preview 顶栏动作（`PreviewHeaderActions`）、详情面板处置部分
  （`DispositionDetails`）。

### B5 bundle 与 review 新错误码

- 新增 `bundleErrorTitle`（`local-bundle.ts`）：两个 bundle 路由在 OpenAPI 中
  列出的码各有前端文案（Preview 503 `BUNDLE_INTEGRITY_FAILURE`；History
  404 `ARTIFACT_UNAVAILABLE`、503 `BUNDLE_INTEGRITY_FAILURE`，以及同路由的
  `SERVICE_NOT_READY`、`SCOPE_FORBIDDEN`、`RESOURCE_NOT_FOUND`、
  `AUTHENTICATION_REQUIRED`）。
- `ComparisonPage` 与工作台 History bundle 下载把 `ApiError` 的服务器码原样
  带到错误状态（可见、可复制），不再一律映射成 `BUNDLE_LOAD_FAILED`；
  文案标题走 `bundleErrorTitle`。不据错误响应构造空 bundle（下载层先校验）。
- `SIMULATED_ERROR_RESPONSES` 新增：review 查询 403/404、review-events
  `BASELINE_VERSION_CONFLICT`（已有）/`ARCHIVE_CLOSED`、Preview bundle 503
  `BUNDLE_INTEGRITY_FAILURE`、History bundle 404 `ARTIFACT_UNAVAILABLE`/
  503 `BUNDLE_INTEGRITY_FAILURE`。单测解析新快照覆盖 §2.3 新增/变化的码，
  并断言 bundle 路由列出的每个码都有文案。

### B6 上传包校验脚本

- `validate-upload-package.sh` 在本机以 `GATEWAY_DOCKER_BUILD_NETWORK=none`
  构建后端校验镜像（tag `gateway-backend-validate:fe-<HEAD12>`，
  `DEPENDENCY_BASE_IMAGE` 取预检通过的依赖基础镜像，
  `USE_PRELOADED_DEPENDENCIES=1`，context 为 `vnext/`），venv 路径为
  `/app/backend/.venv`；日志记录该镜像的 config digest 与全部 RootFS
  DiffID。依赖输入核对保持不变（仍在依赖基础镜像中执行，输入表新增
  `vnext/backend/Dockerfile`）。
- 校验结束（无论成功失败）删除本次构建的 tag，不在节点上留存。
- 本轮结束时已删除 05 上的 `fe3b-upload-validator:latest` 与
  `fe3b-upload-backend:latest`（均为本人创建）。
- 未动 `vnext/`，未要求后端提供镜像。

### B7 模拟数据可达性

- 处置场景数据搬入 `mock-data.ts`（`DISPOSITION_SCENARIO_NODES`、
  `DISPOSITION_SCENARIO_BASELINES`、`DISPOSITION_REVIEW_FACTS`），
  `upload-mode.spec.ts` 的 D1–D5 改为引用；单测按 §5.3 逐条断言
  （`mock-data.test.ts`“keeps every disposition scenario…”）：
  处置只出现在 `APPROVED` 的 `SUBMISSION` 上；`ARCHIVED_BASELINE` ⇒
  `ARCHIVE` + `result_id` 非空 + 无 `closure` + 有 `promoted_baseline_node_id`
  指向的 `ARCHIVED_SUBMISSION` 基线；两种关闭的字段组合；
  无 `ARCHIVED_BASELINE + MANUAL_CLOSE`；一个归档结果最多一个
  `ARCHIVED_BASELINE`；Review 与 History 节点一致；已处置提交不在任何
  workspace 的 `active_submission_id`（W10 的竞争数据在 spec 中单独注明）。
- D5 作为唯一允许的例外单列（“DC89 不可达，防御性”）。
- 改正不可达数据：`d4` 补 `promoted_baseline_node_id`（指向新增的
  `baseline-arch-2`）并改用 `archive-result-2`（与 `d-arch` 不再共享同一
  归档结果）；`d4` 保留历史 `eligibility_note`（§5.3 允许与处置共存，
  D4 照常验证处置优先）。

### B8 必测断言与显示

- W6：新增“刷新后找回操作卡片”（`fe3b-w6-resumed-card`）与“操作终态而
  attempt 未结束时显示需要管理员处理”（`fe3b-w6-recovery`）。
- W9：三支全覆盖。① ABORTED 可达序列（与 n3 同一用例）；② 操作在页面上
  结束后工作区重读仍有指针但 attempt 读不到 → “无法确认提交状态”，点
  “重试”后恢复读取（管理员处理）；③ 工作区读不到 → 同上。
  “重试”按钮用 exact 匹配，避免与“重试读取”歧义。
- D1/D2：打开审核模式，断言顶栏两个标签与三个按钮的禁用原因；D2 断言
  “归档时选中了其他提交”的一行说明。
- D3：断言关闭时间（标题为 UTC 原值、文本为组态树同款本地格式）、4 行理由
  折叠与展开（`展开理由`）、父基线仍是 head 时“归档主线”禁用且原因为
  “该提交已关闭（未归档）”。`result_id` 为空仍显示已关闭。
- §6.4 显示修正：
  - 审核顶栏标签下方一行说明（`ReviewDispositionLine`），关闭理由可展开；
  - 详情面板关闭理由全文显示、保留换行，超过 3 行才折叠（`ClosureReason`）；
    删除重复的“终局状态”一行（统一为“审核状态”+“终局处置”）；
  - 关闭时间与组态树相同本地格式（`MM/DD HH:mm`），悬停显示 UTC 原值；
  - 有理由关闭的树节点状态位悬停提示“有理由关闭，详情见右侧面板”。
- `job_kind`：按 §6.2 实现。URL 中的 operation 经
  `GET /v1/operations/{id}` 读 `job_kind`：是提交但与指针不一致时以指针
  为准替换 URL（用例覆盖）；是 Preview 时不动（用例覆盖）。
- 删除 `r7-upload-only` 中过时的注释与报错文本；审核模式 403 改为断言具体
  文案 + `SCOPE_FORBIDDEN`（与产品行为一致）。

### B9 与审核报告 B9 所列不符之处

- §4.1：步骤卡已禁用（B1）；`job_kind` 来自 `GET /v1/operations/{id}`
  （B8 实现），handoff 如实写明。
- §5 表：D1 审核标签（新增 D1/D2 审核模式用例）、D3 多行原因折叠展开有用例。
- §2.4：处置规则由 `mock-data.test.ts` 保证（B7）。
- §7 N1：`e2e/` 与 `e2e-real` 两个工程整体 `strict: false`，且
  `e2e/tsconfig.json` 再次编译 `../src/**/*.ts`；本轮未收窄，如实写明。
  收窄会改变既有 spec 的类型检查基线，超出定向修复范围。
- 本 handoff 不引用不存在的章节；§3.3 的 §6.4 差异逐条见 B8。
- N4（工作区节点在被占用时仍标“可提交”）：等 owner 看图后决定，本轮未改。

## 3. 非阻塞项

- N1：`run-real-backend-e2e.sh` 在构建 RS 镜像后把 config digest 与完整
  RootFS DiffID 写入日志（本次 05 运行已记录，§8）。
- N4：未改（见上）。

## 4. 路径核对

- `git rev-parse HEAD:vnext` = `56720104af`（与 `748de5034d:vnext` 相同）。
- `git diff --name-only 748de5034d HEAD` 仅含 `frontend/` 与
  `docs/frontend-vnext/`。

## 5. 提交序列（相对 `fe-fe3a-exit`，`afd7711e4b` 之后）

```
087281ce65 fix(frontend): FE3b review fixes B1-B5, B7-B8 and N1
df3e8c5abd fix(frontend): drop unused Schemas alias and attempt binding in ComparisonPage
069a8f65a5 fix(frontend): mount resume card on attempt read; report swallowed workspace errors
fa507ee77c fix(frontend): keep last known upload-mode snapshot on failed re-reads
403e2faefc fix(frontend): parse print-input JSON for validator dependency tag check
```

`087281ce65..403e2faefc` 为调试中发现的实现缺陷修复（类型检查、resume 卡片
挂载时机、失败快照处理、脚本 tag 解析），都在 B1–B8 范围内。

## 6. 回归验证（一次性探针提交，只在 07 节点）

| 探针 | 撤掉的修复 | 对应用例 | 提交 | 节点 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- | --- |
| 探针 | 撤掉的修复 | 对应用例 | 提交 | 节点（hostname） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- | --- |
| P-B1 | 步骤卡占用禁用 | W8（`upload-mode.spec.ts`“W8 待审核提交禁用上传”） | `008b0536fe` | 07（`gw-dms-07.lan`） | 失败符合预期：步骤卡“上传并生成预览”可用（应禁用） | `da44dc4323ea7d8fab4adb42b06e2275fd7d1ad1b76f36bc3e0a025a1fff5c37` |
| P-B2 | 一次性重读 | W10-recovery（“W10 陈旧指针重读后恢复可用”） | `efad58b0f5` | 07（`gw-dms-07.lan`） | 失败符合预期：上传保持禁用（应恢复可用） | `84aeed8c3a0e98bc3ceb986b90e8b88f65b3860bac0d5326f8638ec9f03fd1ee` |
| P-B3 | 续做后状态更新 | n3/W9①（可达序列） | `b4c9aeb9d6` | 07（`gw-dms-07.lan`） | 失败符合预期：不出现“提交未完成…”，无 `IMPORT_REJECTED` | `0295f9ae3a846f12b93f864596c776cb8fd30e1c962a2eacfc1ad8f1f18b1ee5` |
| P-B5 | bundle 服务器码透传 | “bundle 接口失败显示可重试错误页” | `96272654be` | 07（`gw-dms-07.lan`） | 失败符合预期：显示 `BUNDLE_LOAD_FAILED`（应为 `SERVICE_NOT_FOUND`） | `b92b3fc482d42e85f13c61781d0fa1cf5513411504585dbdea13a098712b41c3` |

探针 refs：`refs/review/fe3b/probe-{b1,b2,b3,b5}-fix4`（07 节点仓库）。
探针 worktree 已删除；完整 SHA 见各日志文件。

## 7. B2 专项说明（StrictMode 与重读计数）

W10-recovery 用例不断言“读取次数 > 1”（开发服务器 StrictMode 会双执行
挂载 effect），而是断言可观察的恢复行为：首次读取过时→重读后可用。
hook 用 in-flight 去重保证挂载只读一次，因此该用例中工作区请求恰好 2 次；
把重读逻辑去掉后终局原因常驻，用例失败（P-B2）。

## 8. 证据与运行记录

### 8.1 07（`gw-dms-07.lan`）mock 全量（最终候选 `403e2faefc`）

- 工作树 `/home/dev/gdds-fe-final-403e2fae`（detached，`legacy` 软链，clean）；
  `GATEWAY_FE_TEST_WORKERS=2`；不获取占用标记。
- 命令：`./frontend/scripts/run-tests.sh --e2e --screenshots
  /home/dev/gdds-fe-shots/fe3b-final-403e2fae`
- 结果：exit 0；typecheck、lint、单测（32 文件 171 项）、构建、生产构建
  检查通过；Playwright 55 项通过。
- 截图：138 张（69 组 × 1280/1920），聚合 SHA256
  `36290006…34d12de49`；fe3b 相关 21 组（42 张，`1280/` 与 `1920/` 子目录，
  含新增 `fe3b-w6-resumed-card`、`fe3b-w6-recovery`），目录见下。
- 日志：`/home/dev/gdds-fe-logs/fe3b/final/frontend-tests-20261108T141648Z.log`，
  SHA256 `edcbdbc4…9686c302d0`。
- 起止：`started_at=2026-11-08T14:16:48Z`，`ended_at=2026-11-08T14:18:50Z`；
  起止 HEAD 均为 `403e2faefc`；`frontend` 树 `4d5a8356`；
  `vnext` 树 `56720104af`。
- 工具链：`mcr.microsoft.com/playwright:v1.64.1-noble`，
  config digest `sha256:a0d7b2b4…a1017`；npm 缓存归档 SHA256
  `0d861824…0089f4`，来源提交 `a2fb4a027a`。

### 8.2 05（`gw-dms-test-05.lan`）真实 journeys（`fa507ee77c`，与最终候选仅差脚本解析）

- 工作树 `/home/dev/gdds-fe-fix4-05`（detached，`legacy` 软链，clean）；
  会话 `fe3b-impl-fix4`，由脚本获取/释放占用与 flock。
- 命令：`./frontend/scripts/run-real-backend-e2e.sh --suite journeys
  --subphase fe3b --session fe3b-impl-fix4 --log-dir …`
- 结果：exit 0；18/18 通过；`openapi_compare=match`；
  `cleanup_status=ok`；日志无 token；结束后无占用标记、无残留容器。
- 日志：`/home/dev/gdds-fe-logs/fe3b/fix4-05/real-backend-e2e-journeys-fe3b-impl-fix4-fa507ee77-20261108T135618Z-586473.log`，
  SHA256 `f8e3b8bc…bebebe5a2`。
- 起止：`started_at=2026-11-08T13:55:57Z`，`ended_at=2026-11-08T14:01:42Z`；
  起止 HEAD 均为 `fa507ee77c`；`frontend` 树 `6220a970`；
  `vnext` 树 `56720104af`；worktree clean。
- 镜像：依赖 `gateway-backend-deps:lock-d054366c02fa`；
  RS `gateway-repository-service:fe-fa507ee77c05`
  （image id `sha256:f57637d6…3b7b7d`，config digest
  `sha256:544bdf65…19cd10d2`，完整 RootFS DiffID 见日志
  `rs_image_rootfs_diff_ids`，28 层）；
  backend `sha256:d766e90f…ac0ee027af`、
  worker `sha256:387761e0…6596c0ab891`；
  Docker 29.9.1 / Compose 5.6.0。

### 8.3 05 上传包校验（`403e2faefc`，修复后的脚本）

- 命令：`./frontend/scripts/validate-upload-package.sh --output
  /home/dev/gdds-fe-upload-20261108-fix6 --log-dir
  /home/dev/gdds-fe-logs/fe3b/fix6-05-upload`（不获取占用）。
- 结果：exit 0；`required_inputs_match=true`；
  `RESULT packages=4 failures=0`；`missing-dbcfg` 按
  `UPLOAD_CLOSURE_INVALID` 拒绝；包 SHA256：
  `6a562b07…`（with-logics）、`1c4ab2ba…`（without-logics）、
  `8730309a…`（long-path）、`66ce688f…`（missing-dbcfg）。
- 后端校验镜像 `gateway-backend-validate:fe-403e2faefc` 由脚本在本机以
  `GATEWAY_DOCKER_BUILD_NETWORK=none` 构建（含本地包与 Rust 扩展，
  venv `/app/backend/.venv`），config digest
  `sha256:99f72527…a00c58fca4`，全部 RootFS DiffID 见日志
  `validator_image_rootfs_diff_ids`（13 层）；运行结束已删除该 tag。
- 依赖输入核对沿用依赖基础镜像预检；`vnext/backend/Dockerfile` 纳入输入
  SHA 记录。
- 日志：`/home/dev/gdds-fe-logs/fe3b/fix6-05-upload/upload-validator-403e2faefc-20261108T141421Z-652185.log`，
  SHA256 `b4d3d177…3da419e25e`。
- 起止：`started_at=2026-11-08T14:14:21Z`，`ended_at=2026-11-08T14:15:32Z`；
  起止 HEAD 均为 `403e2faefc`。
- 本轮结束时已删除 `fe3b-upload-validator:latest` 与
  `fe3b-upload-backend:latest`（均输出 `Deleted`）。

### 8.4 截图清单（07 最终运行，均含 1280/1920 两版）

`fe3b-withdraw-enabled`、`fe3b-withdraw-forbidden`、`fe3b-withdraw-none`、
`fe3b-withdraw-unknown`、`fe3b-withdraw-dialog`、`fe3b-w5-conflict`、
`fe3b-upload-restored`、`fe3b-w4-approved-withdraw`、`fe3b-w4-approved-upload`、
`fe3b-w6-withdraw-busy`、`fe3b-w6-attempt-running`、`fe3b-w6-resumed-card`（新增）、
`fe3b-w6-recovery`（新增）、`fe3b-w8-upload-disabled`、
`fe3b-w10-stale-workspace`、`fe3b-w10-stale-preview`、`fe3b-d1-archived`、
`fe3b-d2-closed-at-archive`、`fe3b-d3-manual-close`、`fe3b-d4-priority`、
`fe3b-d5-flag`（共 21 组 × 2 宽度 = 42 张；另有 FE1/FE2 既有截图，
合计 138 张）。目录 `/home/dev/gdds-fe-shots/fe3b-final-403e2fae/`，
聚合 SHA256 见 §8.1。§6、§6.4 的截图 owner 确认后，再决定 FE3b 退出
（FE3 在 FE3c 结束时退出）。

## 9. 偏差与未决

1. W6、W9 的“执行中/结果未知”分支与 D1–D5 仍仅模拟覆盖（真实环境不可控；
   归档/关闭流程属 FE3c）。
2. `e2e/` 与 `e2e-real` 整体 `strict: false`（含重编 `../src`）保持不变，
   如实记录（B9）。
3. 04 证据运行（mock 全量 + journeys + 上传包校验）尚未进行，按 kickoff §9
   在审核通过后于最终候选的 clean detached worktree 上各运行一次。
4. N4 未改，等 owner 看图后决定。
5. 未推送；未改 `vnext/`；未在浏览器重算 SQL/来源/时间。
6. 调试轮 worktree（07 `gdds-fe-fix{1,2,3,4}-*`、05 `gdds-fe-fix{4,6}-05`）
   与探针 refs 按阶段门禁保留至 exit 合入后再清理；传输用 bundle 保留。

## 10. 审核建议

复审范围 `afd7711e4b..<本 handoff 提交>`：核对 B1–B9（§2）；在 07 重跑
`run-tests.sh --e2e --screenshots`；在 05 重跑 `--suite journeys` 与上传包
校验（B6 修复后的脚本）。复审通过后按 kickoff §9 在 04 取证。
