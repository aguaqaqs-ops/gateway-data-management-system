# FE2c 审核报告

- **审核对象：** 分支 `fe-vnext`。
  - 代码候选 `dfe0ed52ba7eb6110a4555b34a78a01d5d1aec34`，`frontend/` 树 `12dbec1bc1`；
  - handoff 提交 `5830bc73c428fd738caf74890aa6f31b9e3b01c5`（相对代码候选只改 `docs/frontend-vnext/fe2c-handoff.md`，`frontend/` 树相同）。
- **范围：** `fe-fe2b-exit..5830bc73c4`。
  - 区间中 `fe-fe2b-exit`（`31f4310ff8`）到 `84c3d91a1a` 是 main 上已合入的文档提交（FE2a/FE2b 审核报告、kickoff），`frontend/` 树在 `84c3d91a1a` 仍为 `a0f8ce750b`；
  - FE2c 的实际改动是 `84c3d91a1a..5830bc73c4`：6 个提交，20 个文件（`frontend/` 19 个，加 handoff）。`vnext/` 没有改动。
- **依据：**
  - [FE2 kickoff](../fe2-kickoff.md) §2（FE2c 一行）、§3 N1/N2、§4.5、§6.1、§6.2、§6.4、§7.2–§7.5、§10；
  - [UI 优化方向](../ui-optimization-direction.md) §7.2（S2 上传步骤卡）、§7.3（S3 审核顶栏）、T1、C6；
  - 后端源码：上传校验、Preview/提交/审核/归档路由与应用层（各条注明位置）；
  - AGENTS“前端测试（FD7）”。
- **日期：** 2026-11-04。
- **结论：定向修复。**
  - 证据本身可信：04 权威运行的日志、截图清单、工具链身份与缓存来源都能对上（§2.1）；我在 05 上的独立运行也通过（§2.2）。
  - 带入项 N2、N3、N4 达标；D1 计数已接入，但完成标准中的“固定 fixture 单测”与草图布局没有做到（§3）。
  - 写操作旅程接到真实后端时走不通，e2e 的路由桩掩盖了这些问题：
    - 浏览器打包的 tar 每个成员的长度都写成 0，后端上传校验拒收（B1，后端代码实测）；
    - Preview 发起与归档确认、异常处理不带后端必需的 `Idempotency-Key`（B2）；
    - 归档对话框在首次预检时永远禁用“确认归档”，桩数据给出了后端不会产出的方案（B3）；
    - 归档审计事件查询缺必填参数，`expected_sequence` 的算法与后端不同（B4）。
  - 另有幂等 key、`operation_id` 写入 URL、需要管理员处理、错误码显示、工具栏上传入口、测试覆盖、单测间歇失败等问题，共 11 项需要修复（§4）。
  - 上传模式的“撤回”属于 §10 停止条件（需要后端字段），交设计会话（§7）。

## 1. 范围

| 内容 | 主要文件 |
| --- | --- |
| 上传步骤卡与浏览器打包 | `features/workbench/UploadStepCard.tsx`、`upload-package.ts`（新增） |
| 提交 | `features/workbench/SubmitDialog.tsx`（新增）、`api/journeys.ts`（`runSubmitJourney` 增加身份确认与 key） |
| 审核 | `features/workbench/ReviewActions.tsx`（新增）、`journeys.ts`（`applyReviewAction` 增加 key） |
| 归档主线 | `features/workbench/ArchiveMainlineDialog.tsx`（新增）；调用 FE1 的 `runArchiveJourney` |
| 页面接线 | `pages/WorkbenchPage.tsx`（上传卡、页面锁定、归档入口、抽屉摘要）、`pages/ComparisonPage.tsx`（Preview 顶栏“提交”、审核顶栏） |
| 带入项 | `history-summary.ts`（D1）、`wait-duration.ts`（N2）、`vite.config.ts` 与 `check-production-build.mjs`（N3、N4）、`api/session.ts`（N4） |
| 测试 | 新增 3 个单测文件（打包、摘要、时长）；e2e 新增 6 个 FE2c 场景，共 21 个 |

`frontend/src/features/dev/`（模拟接口与场景模块）在本阶段没有改动；FE2c 的写路由响应都写在 `e2e/workspace-shell.spec.ts` 的路由桩里（见 B9）。

## 2. 证据核对

### 2.1 handoff 中的 04 证据

我在 04 上逐项读取并重算：

| 项 | 内容 |
| --- | --- |
| 日志 | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261103T180513Z.log`，SHA256 `d9132334…a446883`，与 handoff 及 sidecar 一致；wrapper `fe2c-exit-dfe0ed52-04-wrapper.log` `addf1fd2…69619371` 一致 |
| 节点与时间 | 起止 hostname 都是 `gw-dms-test-04.lan`；`18:05:13Z`–`18:05:48Z` |
| HEAD 与树 | 起止都是 `dfe0ed52ba`；`frontend/` 树起止都是 `12dbec1bc1`；运行后 worktree `/home/dev/gdds-fe2c-gate` clean，`legacy` 链接指向主仓库 |
| 工具链 | config digest `sha256:a0d7b2b4…a1017`；7 个 RootFS DiffID 与固定值一致，04 上 `docker image inspect` 的 DiffID 也一致 |
| 缓存 | `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，SHA256 `0d861824…089f4`（我在 04 上重算一致），来源提交 `a2fb4a027a`；`package_lock_resolved_count=305`；`docker_network=none` |
| 步骤 | 离线安装 280 个包；27 个单测文件 120 项通过；生产检查通过；e2e 21 passed；`exit_code=0` |
| 截图 | 61 张，清单 `fe2c-exit-dfe0ed52-04-screenshots.txt` SHA256 `68a9f422…92d8e7`，与目录中逐张重算一致 |

**04 上的运行次数与 handoff 不符（M5）：** 04 的 `frontend/` 日志目录中有四次 FE2c 运行，全部 exit 0：

| 开始 | HEAD | 截图目录 |
| --- | --- | --- |
| `17:45:29Z` | `a2bcaf866a` | `fe2c/a2bcaf86-04` |
| `17:47:48Z` | `a2bcaf866a` | `fe2c/a2bcaf86-04`（同一目录） |
| `17:55:57Z` | `48f4e0203d` | `fe2c/48f4e020-04` |
| `18:05:13Z` | `dfe0ed52ba` | `fe2c/dfe0ed52-04`（证据） |

handoff §5 只写了前两次，漏了 `17:55` 那次。这不影响 `18:05` 这次运行本身的有效性，但 04 被当成了调试节点（§7.4：调试在 05，04 只在退出时完整运行一次）。

### 2.2 我在 05 上的独立运行

- **源码传输：** bundle `src-review-fe2c-5830bc73.bundle`（`fe-vnext ^84c3d91a1a`），SHA256 `eab3105c…d696c9f6c5c2`；worktree `/home/dev/gdds-fe-review-fe2c-5830bc73-05`，detached `5830bc73c4`，`frontend/` 树 `12dbec1bc1`，clean。
  - 第一次打包没有给 ref，`git bundle` 拒绝生成空 bundle，没有取回任何内容；改用分支名后重做，记录在 `review-setup-05.log`（`0e3b6388…2bce4af0`）。
- **运行：** `./frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-evidence/fe2c/review-5830bc73-05`：
  - 日志 `/home/dev/gdds-fe-logs/fe2c/review/frontend-tests-20261103T235910Z.log`，SHA256 `b4009a5d…2c468d37`；
  - `23:59:10Z`–`23:59:44Z`，起止 HEAD 与树一致，exit 0；120 项单测、生产检查、21 个 e2e 通过；
  - wrapper `runner-wrapper-05.log`（`88b081e9…27124b46`），运行后 worktree clean。
- **占用标记：** 运行与探针期间，05 上有基线会话的占用标记（`p6-baseline-measure`，用途“W4 KEY_EMPTY tool validation”，`23:56:56Z` 起），不是计时测量。按 AGENTS，不连真实 backend 的前端运行不需要等待，因此照常运行；探针日志记录了标记内容。
- **截图：** 61 张，清单 `screenshot-sha256-review-05.txt`（`e39e37a1…60d5112`）。与 04 相比 57 张逐字节相同，不同的 4 张是：
  - `submit-identity-confirmation-1280/1920`；
  - `s2-compare-tray-1920`；
  - `history-compare-result-drawer-1280`。

  `manual-recovery-required-1280/1920` 两个节点逐字节相同，N2 的“截图可复现”已经做到。

## 3. 带入项（§6.4）

| ID | 结论 | 说明 |
| --- | --- | --- |
| D1 | **未完成** | 只从校验通过的本地 bundle 计算；bundle 未就绪时不显示数字，这两点做到了。没做到的：完成标准要求“单测用固定 fixture 断言各比较对的四项计数”，`history-summary.test.ts` 用的是手写的 `as unknown as ComparisonSurface` 对象；“变更表”把 `DEGRADED`、`FAILED`、`BUSINESS_EQUIVALENT` 都算进去；布局与草图 `compare-1920` 差得较多。见 B9、S2 |
| N2 | 达标 | `formatWaitDuration` 的边界有单测；e2e 用 `freezePageClock` 固定 `Date`；两个节点拍到的 `manual-recovery-required` 逐字节相同 |
| N3 | 达标 | 清单移到 `node_modules/.cache/frontend-build/production-modules.json`；检查脚本在 `dist/.vite/rollup-modules.json` 存在时失败。我在已提交的一次性 worktree 中重做 B3 负向探针，检查按预期失败（§5 P5） |
| N4 | 达标 | 生产构建不读取 `__gatewayTestConfig`，并加入禁止模式；去掉 `import.meta.env.DEV` 判断后检查报 `__gatewayTestConfig`（§5 P6）；e2e 的 700 ms 超时照常生效 |

## 4. 需要修复

**B1. 浏览器打包的 tar 头没有写成员长度，后端拒收全部上传**（`frontend/src/features/workbench/upload-package.ts:121`）

- **现象：** `tarHeader` 在偏移 124（ustar 的 `size` 字段）写入 `writeOctal(header, 124, 12, 0)`，每个成员的长度都是 0，内容却照常追加在头之后。
  读取方按长度 0 跳过内容，把第一个成员的内容块当成下一个头；头无效时 Python `tarfile` 在流模式下直接视为结束。
- **实测**（§5 P1、P2）：
  - 用候选的 `buildSourcePackage` 打包 `station.pmc`、`sql/dbcfg.sql`、`comps/logic/logics.xml` 三个文件；
  - 交给后端的上传校验 `validate_source_package_archive`（`vnext/backend/src/gateway_backend/application/workspace/upload_admission.py:53`），在依赖镜像 `lock-d054366c02fa` 中运行；
  - 后端只读到一个成员 `('comps/logic/logics.xml', 0)`，结果为 `UploadClosureInvalidError: required /sql/dbcfg.sql is missing`，即 422 `UPLOAD_CLOSURE_INVALID`；
  - 同样三个文件用 Python `tarfile` 打包的对照组，后端校验通过。
- **为什么测试没发现：** 单测只断言了 `name`、`mode`、`mtime`，没有读回内容；e2e 的上传路由桩对任何请求体都返回 201。
- **修复：**
  - 在 `size` 字段写入 `content.byteLength`；
  - 单测用仓库已有的 tar 读取器（`features/bundle/posix-tar.ts`）把产物读回，逐个比较路径与内容；
  - 另加一条单测覆盖 `prefix` 分段（路径长于 100 字节）；
  - handoff 中附一次用后端 `validate_source_package_archive` 校验前端产物的结果。可以沿用本报告的 `backend-accept.py`，或写成 `frontend/scripts/` 下的脚本，与 fixture 生成使用同一依赖镜像。

**B2. Preview 发起、归档确认与异常处理不带 `Idempotency-Key`，后端返回 422**（`frontend/src/features/api/journeys.ts:182`、`:343`、`:359`）

- **后端：** 下列路由缺少该请求头时返回 422 `REQUEST_VALIDATION_FAILED`：
  - `preview-operations`（`http/routes/preview_operations.py:45–50`）；
  - `archive-confirmations`、`archive-anomaly-resolutions`、`archives`（`http/routes/archives.py:116`、`:159`、`:232`，经 `http/orchestration/archive.py:68–73`）。

  kickoff §7.5 的幂等回放规则也列出了这几条路由。
- **现象：** `runPreviewJourney` 调用 `api.startPreview(...)` 时没有传 key；`runArchiveJourney` 中两个 append 调用也没有。
  这些是 FE1 的旅程函数，FE2c 首次把它们接到界面上，按 N1（“旅程函数按步骤接收 key”）应当一并补齐。
- **实测**（§5 P3）：让 e2e 路由桩在缺少该请求头时按后端返回 422，上传与归档两个 FE2c 场景都失败（上传停在工作台，URL 没有进入 `mode=PREVIEW`）。
- **修复：**
  - 旅程函数按步骤接收 key：上传、Preview、每一条确认、每一条异常处理、开始归档各一个；
  - key 由界面在用户确认时生成，同一意图的重试复用，规则与提交相同（见 B6）；
  - 路由桩对这些路由在缺少该请求头时返回 422，作为回归测试。

**B3. 归档对话框首次预检后“确认归档”一直禁用；e2e 桩给出了后端不会产出的方案**（`frontend/src/features/workbench/ArchiveMainlineDialog.tsx:103`，`frontend/e2e/workspace-shell.spec.ts:302–311`）

- **后端：** `preview_archive_plan`（`application/archive/queries.py:136–200`）的规则：
  - 只要选中了候选，`confirmation_requirements` 就包含选择摘要；
  - `audit_valid` 看审计记录中该摘要的最新确认是否为肯定，以及每个异常是否已处理；
  - `can_start = selected and not blockers and audit_valid`。

  因此在追加确认之前，首次预检一定是 `can_start = false`、`audit_validity = false`，`blockers` 为空。
- **现象：**
  - 对话框用 `blocked = blockers.length > 0 || !can_start`，首次预检后就显示“归档被阻止”（列表为空），并以“当前预检存在阻断项”禁用确认按钮；用户无法开始任何一次归档；
  - e2e 的前两次预检响应在 `ARCHIVE_PLAN_READY` 上展开，带着未确认的 `confirmation_requirements` 和未处理的异常，却保留了 `can_start: true`、`audit_validity: true`。这个状态后端不会产出，正是 §7.5 要防止的情形。
- **实测**（§5 P4）：只把桩的首次预检改成 `can_start: false, audit_validity: false`，归档场景在 `toBeEnabled` 处失败（按钮为 disabled）。
- **修复：**
  - 首次预检只按 `blockers` 阻断；`can_start = false` 且 `audit_validity = false` 时，显示为“待确认”，不显示为阻断；
  - 追加确认与异常处理后重新预检，此时仍为 `can_start = false` 才阻断，并显示原因；
  - 桩按后端规则构造，并在 `mock-data.ts` 中写成带转移说明的场景（见 B9）。

**B4. 归档审计事件查询缺必填参数，`expected_sequence` 的算法与后端不同**（`frontend/src/features/api/client.ts:175`，`journeys.ts:326`、`:339`）

- **后端：**
  - `GET /v1/archive-audit-events` 的 `subject_kind`、`subject_digest` 是必填查询参数（`openapi.json`；`application/archive/queries.py` 的 `list_archive_audit_events` 按单个 subject 查询）；
  - 追加确认时，`expected_sequence` 必须等于该 subject 当前的最新序号，没有记录时为 0（`application/archive/audit.py:148–150`，不等即 `ArchiveAuditVersionConflict`）。异常处理同样按各自的 subject 判断。
- **现象：**
  - `listArchiveEvents` 只传 `after_sequence`，后端返回 422；
  - 即使查询成功，`runArchiveJourney` 取全部事件的最大序号再加 1，并把同一个计数器依次用于不同 subject。全新状态下送出的是 1，后端期望 0。
- **修复：**
  - 按 subject 查询，分页时带上 `subject_kind`、`subject_digest`；
  - 每个 subject 的 `expected_sequence` 取该 subject 的最新序号（没有为 0）；
  - 单测用后端规则断言：全新状态、已有确认、确认后撤销三种情形下送出的序号；
  - 桩的 `archive-audit-events` 校验必填参数，并按 subject 返回事件。

**B5. 上传/Preview 与提交没有按 N2、§4.5 处理进度**（`UploadStepCard.tsx:177–203`，`SubmitDialog.tsx:128–168`，`journeys.ts:189`、`:253`）

- **要求：**
  - §3 N2：`operation_id` 写入 URL，刷新后继续轮询；
  - §4.5：`MANUAL_RECOVERY_REQUIRED` 显示“需要管理员处理”和可复制的操作 ID，轮询继续，并提供“刷新状态”；
  - §2 的 FE2c 一行包括“需要管理员处理”。
- **现象：**
  - 两处轮询都只在组件内存中进行，URL 不含 `operation_id`。上传或提交执行中刷新页面，进度、页面锁定和结果都丢失，用户无法得知后台操作的结果；
  - 进入 `MANUAL_RECOVERY_REQUIRED` 后，上传卡仍显示“生成并下载 Preview 进行中”，提交对话框仍显示“提交执行中”，都没有管理员提示与操作 ID；
  - 两条路径都没有这类 e2e。
- **修复：**
  - Preview 与提交的 `operation_id` 写入 URL，刷新后按 URL 恢复轮询与页面锁定，可复用 FE2b 的 `OperationStatusPanel`；
  - 在上传卡与提交对话框中显示需要管理员处理的状态；
  - e2e 覆盖：执行中刷新后继续；`MANUAL_RECOVERY_REQUIRED → RUNNING → SUCCEEDED`。

**B6. 审核与上传的幂等 key 不符合 N1；审核绕过了版本校验**（`ReviewActions.tsx:57`，`journeys.ts:306`，`UploadStepCard.tsx:170`）

- **审核：**
  - 每次点击确认都传 `crypto.randomUUID()`。超时或断连后再点一次就是新的意图，后端不会回放第一次的结果；
  - `applyReviewAction` 在发送前重新读取 `review_version`，发送的不是审核人看到的版本。审核人看到的状态已过时，`REVIEW_VERSION_CONFLICT` 也不会出现，违背 §6.2“不自动重放写操作”的用意。
- **上传：**
  - key 在任何失败后都保留。后端的上传指纹包含 `expected_workspace_version`（`application/workspace/contracts.py:86–111`）；
  - 上传成功后，若 Preview 发起失败、轮询断开或 bundle 下载失败，重试会以同一个 key 和已变化的版本重新上传，后端返回 409 `IDEMPOTENCY_CONFLICT`；
  - 界面提示“请重新开始上传”并允许重试，但 key 仍不变，重试必然再次失败，只有重新选择目录才能恢复。
- **修复：**
  - 审核：key 按对话框意图生成，超时、断连与 5xx 保留，确定失败（4xx）后换新 key；发送 `facts.review_version`（界面上的版本），冲突时提示刷新；
  - 上传：旅程拆成可续做的步骤，已成功的上传在重试时不再重发，或沿用第一次的请求内容；`IDEMPOTENCY_CONFLICT` 之后换新 key；
  - 单测覆盖上述两种情形；e2e 覆盖提交、审核各一次“超时后重试回放第一次结果”。

**B7. 工具栏“上传”快捷入口永远禁用；Preview 顶栏没有上传快捷入口，handoff 的说法不符**（`features/view-model/workspace.ts:234`，`pages/WorkbenchPage.tsx:370`）

- **现象：**
  - 视图模型对 `upload` 固定返回 `blocked(...)`，页面又用 `action.enabled && uploadReady` 合成，结果恒为 false；
  - 截图 `upload-selected-1920` 中，两个目录都已通过校验、卡片内的上传按钮可用，工具栏的“上传”仍禁用，旁边写着“需先选择本次归档组态目录”；
  - handoff §8 第 2 条说“PREVIEW 顶栏的‘原始组态备份/本次归档组态/上传’按草图保留为快捷入口”，但 `ComparisonPage.tsx` 中没有这些按钮，`s3-header-upload` 截图中也没有。
- **修复：**
  - 工具栏的上传按 `uploadReady` 启用，原因取卡片给出的原因；
  - Preview 顶栏按草图 `header-upload` 补上三个快捷入口，或在 handoff 中如实写成偏差交 owner；
  - e2e 点击工具栏“上传”走完一次上传。

**B8. 生产构建中写操作错误不显示错误码；版本冲突没有刷新入口**（`SubmitDialog.tsx:194–195`，`ReviewActions.tsx:79`、`:88`、`:97`，`ArchiveMainlineDialog.tsx:184`）

- **要求：**
  - §6.2：权限拒绝就地显示“当前身份没有该操作的权限”，并显示错误码；版本冲突提示“数据已被更新”，并提供刷新；
  - §7.5：`ABORTED` 显示“提交未完成”，原始码按 C6 放在悬停提示与 Debug 中，可复制。
- **现象：**
  - 提交、审核对话框的错误码只在 `import.meta.env.DEV` 时显示，归档只放在 `title` 中。生产用户看不到错误码，`title` 也不能复制；
  - e2e 断言“`SCOPE_FORBIDDEN` 可见”能通过，只因为 e2e 跑的是开发构建；
  - 提交、审核的版本冲突只有文字，没有刷新操作。提交对话框冲突后，按钮仍可点击，但再次发送的仍是打开时读取的 `expected_workspace_version`，必然再次冲突。
- **修复：**
  - 错误码在所有构建中都显示，并提供复制。上传卡已经这样做，与 FE2b 托盘的权限提示一致；
  - 版本冲突提供“刷新”，重新读取工作区、History 头与审核信息后再允许确认；
  - 补一条生产构建的 e2e 或组件测试，确认错误码可见。

**B9. 测试覆盖与模拟响应没有达到 §7.2、§7.5、§6.4 的要求**（`e2e/workspace-shell.spec.ts:94–339`，`history-summary.test.ts`）

- **覆盖缺口：** §7.5 要求每个写操作至少覆盖成功、403，以及该 route 声明了的版本冲突与幂等冲突；§7.2 要求覆盖轮询超时、刷新后继续与幂等重试。目前：
  - 上传、Preview 没有 403、`WORKSPACE_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT` 场景；
  - 审核没有 403、`REVIEW_VERSION_CONFLICT`、`IDEMPOTENCY_CONFLICT`；
  - 归档没有 403、`BASELINE_VERSION_CONFLICT`、`ARCHIVE_AUDIT_VERSION_CONFLICT`、`CANDIDATE_BINDING_CONFLICT`、阻断项（`ACTIVE_SUBMIT_ATTEMPT`、`ARCHIVE_INTEGRITY_FAILURE`）；
  - 提交没有 `ABORTED`、`IDEMPOTENCY_CONFLICT`，也没有超时后重试回放；
  - 只有提交覆盖了 403 与 `WORKSPACE_VERSION_CONFLICT`。

  handoff §1 写“上传/审核/归档同类分支”，指的是代码里有分支，没有测试经过它们。
- **模拟响应：**
  - FE2c 的写路由响应直接写在 e2e 路由桩里，例如 Preview 的 202 响应、审计事件的空列表、归档方案的两阶段，没有放进 `features/dev/` 的场景模块；
  - 这些对象没有用生成类型 `satisfies` 约束，也没有注明所依据的状态转移（§7.5“一处定义”“状态序列”“注明来源”）；
  - B3 的不可能状态就是在这里产生的。
  - 标识前后不一致：归档场景的候选是 `fe2a-history-ref-2`，异常、处理结果与归档结果却引用 `submission-1`（截图 `archive-mainline-result` 中“归档提交 submission-1”）。
- **身份：** 审核通过与归档都在“提交人”身份下完成（截图右上角）。§6.2 的模拟会话要覆盖审核人与归档确认人，但这几条写操作的 e2e 没有切换身份，也没有核对请求所带的 token。
- **D1：** 单测改为用 History 三节点 fixture 解析出的 surface，断言各比较对的表数、变更表数、降级表数与逐表增删改。
- **修复：** 按上面的清单补场景，场景集中到 `mock-data.ts`；B1–B4 的回归测试按后端规则写。

**B10. 单测 `idempotency.test.ts` 间歇失败，会让权威 runner 随机 exit 1**（`frontend/src/features/api/idempotency.test.ts:20`，`idempotency.ts:47–50`）

- **现象：** 第一次请求的模拟 Promise 在 30 ms 后才 resolve，测试只等待 2 ms 的超时便继续。测试文件结束、jsdom 拆除 `window` 之后，这个 Promise 才 resolve，`requestWithTimeout` 中的 `window.clearTimeout` 抛出 `ReferenceError: window is not defined`。vitest 将其作为 unhandled rejection 计入，结果为 exit 1。
- **频率：** 我在 05 上跑了 8 次单测阶段（1 次完整运行、7 次探针），其中 3 次出现这个错误（`probe-archive-backend-plan.attempt1/attempt2`、`probe-n4-unguarded.attempt1`），每次 120 项测试都通过。
  这条测试来自 FE2b（`548cd290a2`），FE2c 没有改它。但它直接影响 FE2c 04 取证能否一次通过，因此列在这里。
- **修复：**
  - 测试结束前等待第一次请求的 Promise settle，或改用 `vi.useFakeTimers()`；
  - `requestWithTimeout` 改用 `globalThis.setTimeout`/`clearTimeout`；
  - 修复后在 05 上连续运行单测阶段若干次，确认不再出现，结果写进 handoff。

**B11. 上传卡与草图 S2 的功能差异**（`UploadStepCard.tsx`，草图 `upload-selected`、`upload-running`、`upload-locked-1280`）

- **现象：**
  - 选过“原始组态备份”后没有清除（草图中的 ✕）。用户无法退回“仅本次归档”，只能刷新页面；
  - owner 确认的阶段名（UI 优化方向 §7.2）是“上传原始组态备份 → 上传本次归档组态 → 下载预览结果 → 写入本地 → 完成，进入差异浏览”，只传本次归档时为“上传本次归档组态 → 解析预览”。实现用的是“生成并下载 Preview”，两种上传方式也没有区分；
  - 草图要求“首批显式空基线：第 ① 步禁用并就地说明原因”，没有实现；
  - 每一步同时显示摘要行和 `DirectorySummary` 卡片，内容重复；没有草图中的“校验通过”标记。
- **修复：**
  - 补清除与“重新选择”，按草图显示校验结果；
  - 阶段名按 §7.2，区分两种上传方式；
  - 补空基线时的禁用原因；
  - 不能按草图做的，作为偏差写进 handoff。

## 5. 变异探针

全部在 05 上的一次性 worktree 中进行：以 `5830bc73c4` 为基础，改动以 `review-probe` 身份提交后运行 runner，结束后删除 worktree。
脚本与日志在 `/home/dev/gdds-fe-logs/fe2c/review/probes/`：`probes.log` `5fec5c13…6aa5afee`、`probes-rerun.log` `65a396fc…521a1be`、`probes-rerun2.log` `231ef90e…73182a4`。

| # | 改动 | 预期 | 结果 |
| --- | --- | --- | --- |
| P1 | 加单测：读回 `buildTar` 第一个成员的 `size` 字段，并输出打包产物 | 失败 | 失败：`size` 字段为 `00000000000`，期望 9（`probe-tar-size.out` `9ea6611f…19d63692`） |
| P2 | 把 P1 产物交给后端 `validate_source_package_archive`（依赖镜像 `lock-d054366c02fa`，network none，源码只读） | 拒收 | 拒收：`required /sql/dbcfg.sql is missing`；Python `tarfile` 打包的对照组通过（`backend-accept.log` `234e92b6…9fd65a4d`，产物 `frontend-package.tar.gz` `c0ef73bf…df003a3`）。第一次运行时我的脚本漏了 `shared_kernel` 的导入路径，没有执行到校验；日志保留为 `backend-accept-attempt1-importpath.log`，修正后重做一次 |
| P3 | 路由桩：Preview、归档确认、异常处理缺少 `Idempotency-Key` 时按后端返回 422 | 写操作场景失败 | 上传、归档两个场景失败（`probe-required-idempotency-keys.out` `8a7b2788…6b44d4e`） |
| P4 | 路由桩：首次归档预检按后端规则返回 `can_start: false, audit_validity: false` | 归档场景失败 | 失败：`确认归档` 为 disabled（`probe-archive-backend-plan.out` `96e32124…9015b0ff`）。前两次运行都在单测阶段遇到 B10 的间歇错误，未进入 e2e；第三次在该探针中另行跳过那一条 FE2b 单测 |
| P5 | N3：`App.tsx` 导入 `./features/dev/simulated-api` | 生产检查失败 | 失败：`production dist includes development-only modules`（`probe-n3-dev-import.out` `2d9e9874…7a80a00c`） |
| P6 | N4：去掉 `session.ts` 的 `import.meta.env.DEV` 判断 | 生产检查失败 | 失败：`production dist contains development simulation code: index-….js: /__gatewayTestConfig/`（`probe-n4-unguarded.out` `bfac0a4d…91a467`）。第一次运行遇到 B10，重做一次 |

## 6. 次要问题（不阻塞，可随本轮一起修）

- **M1：** 前端只限制目录 1 GB 与 5000 个文件。后端另有限制：压缩后不超过 256 MiB、条目不超过 8192（`capabilities/source_package_staging/contracts.py:101–111`），超过时返回 413。
  `buildTar` 把全部文件读进内存后再复制成一个数组，1 GB 的目录需要两倍以上的内存。建议打包后检查压缩大小并就地提示，打包改为流式。
- **M2：** 页面锁定遮罩只拦截鼠标（`WorkbenchPage.tsx:382`），键盘 Tab 仍能到达工具栏与托盘按钮。建议对锁定区域加 `inert`。
- **M3：** 上传执行中同时显示“已用时”（页面计时）和“已等待”（操作 `started_at`）两个时长，截图 `upload-locked-1280` 中分别为 0 秒与 8 秒。保留一个，或分别说明含义。
- **M4：** 提交对话框按比较对逐项确认，后端按动作确认（`application/submission/accept.py:270–286`，同一动作只取一条）。两个比较对都需要同一种确认时，只有最后一条理由会被保存。建议按动作合并，或在界面上说明。
- **M5：** 证据流程：
  - 04 运行了四次，handoff 只记两次（§2.1）；
  - 05 的调试目录 `/home/dev/gdds-fe2c-debug` 是 rsync 副本，没有 `.git`；N3 探针在未提交的副本上做，不符合 AGENTS“clean、已提交 worktree”；
  - bundle 放在 `/tmp`，不在 `/home/dev/gdds-test-tmp`；
  - 04 主仓库因 fetch 新建了 `refs/heads/fe-vnext`；
  - 日志写在 `/home/dev/gdds-fe-logs/frontend/`，没有按阶段放进 `fe2c/`。

  下一轮在 05 上用已提交的 detached worktree 调试，04 只在复审通过后运行一次。
- **M6：** handoff 的其他不准确之处：
  - §4 说写路由场景在 `mock-data.ts` 与 e2e 路由桩中，实际 `features/dev/` 没有改动；
  - §1“403 与版本冲突”一行写“上传/审核/归档同类分支”，但没有对应测试（B9）。
- **M7：** 提交对话框的摘要直接显示 `preview-1`、`fe2a-history-ref-1` 等原始 ID；审核顶栏的模式标签只有“审核”。草图允许拿不到序号时只显示“审核”，但 History 中有提交节点的标签（如“提交 2”），可以取用。

## 7. 交设计会话的问题

**上传模式的“撤回”入口**（handoff §8 第 1 条）

- **现状：**
  - 草图 `header-upload` 在上传模式顶栏有“撤回”；
  - vnext 的 `WorkspaceResponse` 只有 `current_preview_result_id`、`current_upload_revision_id` 等字段，没有指向当前提交的字段（`openapi.json`），工作台无法确定上传模式下可撤回的是哪一个提交。
- **处理：** 这属于 §10 的停止条件（需要后端新增字段）。实施会话没有停下，而是写成偏差，当前实现也没有破坏任何规则。
- **请设计会话决定：**
  - **甲（建议）：** FE2 中撤回只出现在审核顶栏（已实现），上传模式不提供；在前端 kickoff §3.3 登记为缺口，由 BE-a 或后续后端任务决定是否在 `WorkspaceResponse` 中加入当前提交。
  - **乙：** 先由后端补字段，FE2c 等待后接回。

  1280 下提交对话框首行摘要随滚动移出（handoff §8 第 4 条），是 owner 截图确认时的事项。若 B8 加入刷新操作后对话框更高，建议改为摘要固定、只滚动确认区。

## 8. 截图核对（草图 S2 上传步骤卡、S3 审核顶栏、无草图页面）

| 截图 | 结论 |
| --- | --- |
| `header-review-1280/1920` | 符合草图 `header-review`：撤回、退回为红色描边，审核通过为主按钮；模式标签只有“审核”（M7） |
| `upload-invalid`、`upload-selected` | 校验错误列表与上传方式符合草图；缺少清除与“校验通过”（B11）；工具栏“上传”禁用原因错误（B7） |
| `upload-locked-1280` | 遮罩与卡片可读；阶段名与草图不同（B11）；两个时长（M3） |
| `submit-identity-confirmation-1280/1920` | 两项确认的复选框与理由清楚，按钮层级正确；1280 首行摘要移出（§7） |
| `archive-mainline-1280/1920`、`archive-mainline-result-1920` | 预检、确认项、异常处理、确认后的影响与结果齐全；对话框底部按钮固定。但截图中的状态来自后端不会产出的桩数据（B3、B9） |
| `history-compare-result-drawer-1280/1920` | D1 计数显示为一行小字（“表 10 变更 7 降级 2”），逐表计数折叠在“每张表的新增 / 删除 / 修改行数”中，且列出全部表。草图 `compare-1920` 是比较对页签、四张统计卡片和只列变更表的清单。建议按草图调整，否则作为偏差交 owner |
| `manual-recovery-required-1280/1920` | 显示“已等待 8 秒”，两个节点逐字节相同（N2） |

**缺少的截图**（§2 FE2c 一行、§7.3“每个页面与状态两种宽度”）：

- 只有一种宽度：`upload-selected`（缺 1280）、`upload-locked`（缺 1920）、`archive-mainline-result`（缺 1280）；
- 完全没有：退回对话框、撤回对话框、上传空状态（草图 `upload-empty`）、上传执行中的卡片（草图 `upload-running`）、上传失败与重试、提交未完成（`ABORTED`）、归档被阻断、写操作的权限拒绝与版本冲突。

## 9. 复审范围与要求

1. 修复 B1–B11。M1–M7 可以一起修，不修的在 handoff 中说明。§7 等设计会话答复后按答复处理。
2. **探针：**结果写进 handoff。
   - B1：去掉 `size` 写入后，读回测试应失败；附一次后端 `validate_source_package_archive` 校验前端产物的结果；
   - B2：去掉任一步的 key 后，路由桩的 422 应使 e2e 失败；
   - B3：归档桩恢复 `can_start: true` 的不可能状态，按后端规则写的单测应失败；
   - B6：审核重试换新 key 后，单测应失败；
   - B10：修复后连续运行单测阶段若干次，记录次数与结果。
3. **截图：** 补 §8 所列缺少的截图，重拍改动涉及的全部截图。不能按草图修正的，逐条列为偏差，交 owner。
4. **运行：** 在 05 的已提交 detached worktree 上完整运行 runner（含 `--e2e --screenshots`）。
5. 复审范围为 `5830bc73c4..<新 handoff 提交>`，通过后再在 04 上取证一次。

## 10. 本轮在节点上留下的内容

- **开发主机：** 只读 review worktree `/home/dev/gdds-fe-review-fe2c-5830bc73`；bundle `/home/dev/gdds-test-tmp/src-review-fe2c-5830bc73.bundle`。
- **05：**
  - worktree `/home/dev/gdds-fe-review-fe2c-5830bc73-05`；
  - bundle `/home/dev/gdds-test-tmp/src-review-fe2c-5830bc73.bundle`；
  - 日志与探针结果 `/home/dev/gdds-fe-logs/fe2c/review/`；
  - 截图 `/home/dev/gdds-fe-evidence/fe2c/review-5830bc73-05/`。

  探针 worktree 已全部删除（`git worktree list` 中没有 `fe2c-review-probe`）。

FE2c 退出合入后再清理。
