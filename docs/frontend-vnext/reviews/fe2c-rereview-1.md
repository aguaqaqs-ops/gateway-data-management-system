# FE2c 复审报告（第 1 轮）

- **复审对象：** 05 上 detached worktree `/home/dev/gdds-fe2c-fix-05`（没有分支名）。
  - 候选 `680b643f39d9c83f85c8496627be03c4894c26cf`，`frontend/` 树 `46ed824885`；
  - 最后一次代码改动在 `008cd90a`，之后 `73c70ed2`、`4c096d49`、`680b643f` 只改 handoff。
- **范围：** `5830bc73c4..680b643f`，11 个提交，19 个文件（`frontend/` 18 个，加 handoff），356+/254-。`vnext/` 没有改动。
- **依据：**
  - [FE2c 审核](fe2c-review.md) §4、§6、§8、§9；
  - [FE2 kickoff](../fe2-kickoff.md) §7.1“上传包的后端校验”与 §7.5“请求侧约束”“后端可达状态”（均为 §9 Q17，owner 2026-11-04），§9 Q16；
  - 后端源码（各条注明位置）。
- **日期：** 2026-11-04。
- **结论：定向修复。**
  - 已修好：B1 tar 长度（后端校验已接受前端产物，§2.2）、B4 按 subject 计算序号、B10 单测间歇失败、D1 计数；B3、B7 主体可用。
  - 新问题：归档对话框给所有确认、异常处理和开始归档共用一个 key。后端按表要求 key 唯一，两个异常时第二条处理必然返回 409 `IDEMPOTENCY_CONFLICT`（N1，探针已证实）。
  - 未完成：
    - Q17 的两项要求都没有做：没有提交上传包的后端校验脚本；请求侧约束只在 e2e 文件里内联了 4 条路由，模拟模块中没有统一实现，也没有单测；
    - B9 测试覆盖基本没补：e2e 仍为 21 个，没有新增 403、版本冲突、幂等冲突场景；
    - B5、B6、B8、B11 只修了一部分；
    - §8 所列缺少的截图只补了 3 张。
  - handoff 有多处与事实不符（§4）。

## 1. B1–B11 核对

| 项 | 修复 | 核对 | 结论 |
| --- | --- | --- | --- |
| B1 | `tarHeader` 写入 `content.byteLength`；单测读回内容；单测覆盖 `prefix` 分段 | 我在 05 上用候选的 `buildSourcePackage` 打了 4 个包，交给后端 `validate_source_package_archive`，结果都符合预期（§2.2）。单测里的 tar 读取器是测试文件内另写的，没有用仓库已有的 `posix-tar.ts`，不影响结论。Q17 要求的提交脚本没有做，见 N2 | 产品修复**通过** |
| B2 | Preview、确认、异常处理、开始归档都带上 key；e2e 对其中 4 条路由在缺 key 时返回 422 | key 带上了，但归档的 key 用法有误，见 N1；请求侧约束见 N2 | **未通过**（N1、N2） |
| B3 | `blocked` 只看 `blockers`；首次预检显示“待确认”；旅程在追加确认后重新预检，`can_start` 仍为 false 时报错 | 首次预检的处理正确。但桩在第三次预检时返回 `ARCHIVE_PLAN_READY`：`confirmation_requirements` 和 `anomalies` 都为空，`selected` 缺失，`can_start` 却为 true。后端在确认之后仍返回选择摘要与全部异常（`application/archive/queries.py:146–163`，异常由快照推导，不因处理而消失），`can_start` 要求已选中（`:179–183`）。`mock-data.test.ts` 还把这个状态写成了断言。新增的“探针靶点”单测只断言一个常量的字段值，不是 Q17 要求的“按规则核对每个场景” | **部分**（N3） |
| B4 | `listArchiveEvents` 必带 `subject_kind`、`subject_digest`；每个 subject 取各自的最新序号 | 单测断言了确认 0、异常 7 这一种情形；审核要求的“确认后撤销”与“没有记录时 `REVOKE` 返回冲突”没有覆盖。`TEST_ARCHIVE_EVENTS_WITH_CONFIRMATION` 现在装的是异常事件，名字与内容不符 | 产品修复**通过**，测试见 M8 |
| B5 | 上传与提交在操作受理后把 `operationId` 写入 URL；刷新后由 `OperationStatusPanel` 继续查询；上传卡显示“需要管理员处理”与可复制 ID | 刷新后只恢复了状态卡片，没有恢复页面锁定，Preview 完成后也不会下载 bundle、进入差异浏览，需要用户自己找入口。提交对话框没有“需要管理员处理”的显示（`SubmitDialog.tsx` 中没有 `MANUAL_RECOVERY_REQUIRED`）。审核要求的两条 e2e（执行中刷新后继续；`MANUAL_RECOVERY_REQUIRED → RUNNING → SUCCEEDED`）都没有加 | **部分**（N4） |
| B6 | 审核：key 在打开对话框时生成，重试复用，4xx 后换新；发送界面上的 `review_version`；上传：`IDEMPOTENCY_CONFLICT` 后换新 key | 审核部分**通过**。上传部分没有按要求拆成可续做的步骤：上传成功、Preview 之后失败时，第一次重试用旧 key 和新版本重新上传，后端返回 409；第二次重试才成功，并重新上传一次。审核要求的 e2e“超时后重试回放第一次结果”（提交、审核各一次）没有加 | **部分**（N5） |
| B7 | 工具栏“上传”按卡片是否就绪启用，原因取自卡片；Preview 顶栏的快捷入口写为偏差 | 视图模型与页面接线正确。审核要求的“e2e 点击工具栏上传走完一次上传”没有加 | **通过**，e2e 见 M9 |
| B8 | 提交、审核的错误码在所有构建中显示；提交版本冲突提供“刷新后重试”（重新加载页面） | 提交**通过**。归档的错误码仍只在 `title` 里（`ArchiveMainlineDialog.tsx:187`），看不到也不能复制，handoff 却写“已修复”。审核的 `REVIEW_VERSION_CONFLICT` 只有“请刷新审核信息后重试”的文字，没有刷新操作；对话框继续发送旧的 `review_version`，重试必然再次冲突。审核与归档都没有复制按钮。审核要求的“生产构建下错误码可见”的测试没有加 | **部分**（N6） |
| B9 | handoff 说已集中到 `mock-data.ts`，`SIMULATED_ERROR_RESPONSES`、`WRITE_SCENARIO_COVERAGE` 已有 openapi 校验 | 这两个对象是 FE2b 就有的，本轮 `mock-data.ts` 只改了 2 行。e2e 仍为 21 个，没有新增场景。审核 B9 列出的覆盖缺口（上传/Preview、审核、归档的 403 与冲突，提交的 `ABORTED` 与幂等冲突）都还在；写操作的 e2e 仍没有切换到审核人、归档人身份；归档场景中候选为 `fe2a-history-ref-2`、处置与结果却引用 `submission-1`，仍不一致 | **未通过**（N7） |
| B10 | 定时器改用 `globalThis`；测试等待第一次请求结束 | 我在 05 上连续运行 runner 单测阶段 6 次（§2.3），全部通过，没有出现 unhandled rejection。handoff 把“更多次运行”留到 04 取证，这违反调试与取证分开的规则，本轮由我补上 | **通过** |
| B11 | 清除按钮、“校验通过”标记、阶段名“下载预览结果” | 只传本次归档时阶段名仍与两种方式相同，没有按 §7.2 区分（“上传本次归档组态 → 解析预览”）；首批显式空基线时第 ① 步禁用并说明原因，没有实现，handoff 也没有写成偏差；摘要行与 `DirectorySummary` 仍重复 | **部分**（N8） |

**次要问题：**

- M1：上限检查放在压缩之后，条目数检查应在打包之前（条目数在读文件前就已知）。流式打包写为偏差，可以接受。
- M2：`inert` 加在了遮罩自身（`WorkbenchPage.tsx:382`），没有加在被锁定的区域。键盘仍能 Tab 到工具栏与托盘，handoff 却写已修复。见 M10。
- M3、M4：已处理。
- M5：见 §4。
- M6：handoff §2 的 B9 一行仍不准确，见 §4。
- M7：写为偏差，可以接受。
- M8（新）：测试补充：
  - B4 补“确认后撤销”与“没有记录时 `REVOKE` 返回 `ARCHIVE_AUDIT_VERSION_CONFLICT`”两种情形；
  - `TEST_ARCHIVE_EVENTS_WITH_CONFIRMATION` 改名或改内容，使名字与内容一致；
  - D1 单测补逐表增删改的断言；
  - 删除 `history-summary.test.ts` 中恒为真的 `summarizeHistoryPair ? … : …` 判断。
- M9（新）：补 e2e：点击工具栏“上传”走完一次上传。
- M10（新）：`inert` 改加在被锁定的区域（顶栏、树、详情、托盘），遮罩本身不需要；键盘 Tab 不能再到达这些区域的按钮。

**D1（§6.4 带入项）：** 新单测用 History 三节点 fixture 的两个比较对，断言表数、变更表数、降级表数，数值与 fixture 中后端写入的 `summary` 一致（p0：9/6/2；p1：10/7/2）。后端的 `changed_table_count` 本来就包含降级表，原审核 §3 说“变更表把 `DEGRADED` 算进去”是我的误判，以后端为准。逐表增删改没有断言（M8）。抽屉布局与草图不同，已列为偏差交 owner。**通过。**

## 2. 我在 05 上的核对

源码经 bundle 传到开发主机（`/home/dev/gdds-test-tmp/src-rereview1-fe2c-680b643f.bundle`，SHA256 `9ca0eff1…0f9b67ce`），开发主机的只读 worktree 为 `/home/dev/gdds-fe-rereview1-fe2c-680b643f`。
05 上的 worktree `/home/dev/gdds-fe-rereview1-fe2c-680b643f-05` 由 05 本机仓库直接建出（对象已在该仓库中）。全部日志在 05 的 `/home/dev/gdds-fe-logs/fe2c/rereview-1/`，驱动脚本与探针源文件在其中的 `probes/src/`。

### 2.1 完整运行

- 命令：`GATEWAY_FE_LOG_DIR=/home/dev/gdds-fe-logs/fe2c/rereview-1 ./frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-evidence/fe2c/rereview1-680b643f-05`，npm 缓存用 FE0 的归档（`0d861824…089f4`，来源提交 `a2fb4a027a`）。
- 日志 `frontend-tests-20261104T091347Z.log`，SHA256 `6f229da3…9315c3e`；`09:13:47Z`–`09:14:22Z`，`gw-dms-test-05.lan`，起止 HEAD `680b643f`，`frontend/` 树起止 `46ed824885`，`docker_network=none`，exit 0。
- 27 个单测文件 125 项通过；生产检查通过；e2e 21 passed。工具链 config digest `sha256:a0d7b2b4…a1017`，7 个 DiffID 与固定值一致。运行前后 worktree clean；05 没有占用标记。
- 截图 64 张。与实施会话 `fix-4c096d49-05` 相比，59 张逐字节相同；不同的 5 张是 `archive-mainline-result-1280`、`history-compare-result-drawer-1280`、`s3-workbench-normal-1920`、`s4-grid-normal-hover-1920`、`s4-grid-normal-main-1920`。上一轮也有 4 张类似的差异，都不是本轮改动的页面，不阻塞；04 取证时以 04 的截图为准。
- 驱动日志 `rereview-05.log`，SHA256 `694bc4fd…1a4ac83b`（`09:13:24Z`–`09:19:32Z`）。

### 2.2 探针

探针都在以 `680b643f` 为基础的一次性 worktree 中进行：加入一个测试文件，以 `review-probe` 身份提交后运行 runner（不含 e2e），结束后删除 worktree。

| # | 内容 | 预期 | 结果 |
| --- | --- | --- | --- |
| P1 | `probe-archive-keys.test.ts`：按 `ArchiveMainlineDialog.start()` 实际构造的参数（不带逐项 key，`idempotencyKey` 与 `startIdempotencyKey` 为同一个对话框 key）调用 `runArchiveJourney`，两个异常；模拟 API 按后端规则对同 key、不同请求返回 409 | 若 key 用法正确，应通过 | **失败**：`ApiError: idempotency conflict`，`status: 409, code: 'IDEMPOTENCY_CONFLICT'`；1 failed / 125 passed（`probe-archive-keys.out` `5a4d5719…0fc4f6`）。证实 N1 |
| P2 | `probe-tar-backend.test.ts` 用候选的 `buildSourcePackage` 打 4 个包并输出；在依赖镜像 `gateway-backend-deps:lock-d054366c02fa` 中（`--network none`，源码只读挂载，镜像内 `/build/backend/.venv/bin/python -I`）交给 `validate_source_package_archive`，并比较成员路径与内容摘要 | 前三类按 Q17 的预期 | 全部符合：`full-with-logics`、`full-without-logics`、`long-path-prefix`（成员路径 121 字节）后端接受；`missing-dbcfg` 被拒收，`UploadClosureInvalidError: required /sql/dbcfg.sql is missing`。4 个包的成员与输入逐项一致（`backend-validate.log` `f5d830cf…6572997`；runner 输出 `probe-tar-backend.out` `2f6b7903…7317706`）。B1 产品修复**通过** |

P2 是审核会话的核对，不能代替 kickoff §7.1 要求的提交脚本（N2）。

### 2.3 B10 连续运行

在候选 worktree 上连续运行 runner 6 次（不含 e2e，日志目录 `rereview-1/b10/`），全部 exit 0，每次 125 项通过，输出中没有 unhandled 错误。修复前我在 05 上跑了 8 次，3 次出现该错误；修复后 6 次都没有出现。B10 **通过**。

## 3. 需要修复

**N1. 归档对话框给所有确认、异常处理和开始归档共用一个 key；有两个异常时第二条处理返回 409**（`ArchiveMainlineDialog.tsx:107–120`，`journeys.ts:334–375`）

- **后端：**
  - 确认与异常处理分别存在 `archive_confirmation_events`、`archive_anomaly_resolution_events`，两表都有 `UNIQUE (repository_id, idempotency_key)`（`infrastructure/control_db/schema.py`）；
  - 追加时先按 key 查找，找到且请求指纹不同即 `IdempotencyConflict`（`application/archive/audit.py:117–125`、`:238` 起）；
  - 指纹包含 `subject_digest` 与 `expected_sequence`（`application/archive/contracts.py:280–345`）。
- **现象：**
  - 对话框调用 `runArchiveJourney` 时，确认与异常处理都不带各自的 key，旅程退回到 `fallbackArchiveKey`，即对话框的同一个 key；开始归档也用这个 key；
  - 两个及以上异常（多个未包含的已通过提交时很常见）：第二条处理与第一条 key 相同、`subject_digest` 不同，后端返回 409，归档无法进行；
  - 开始归档失败后重试：确认的 key 不变，但 `expected_sequence` 已从 0 变为最新序号，指纹不同，同样 409。对话框把 409 显示为“请刷新预检”，刷新后才换 key。
- **实测：** §2.2 探针 P1。按对话框实际构造的参数调用旅程，路由桩按后端规则（同 key、不同请求返回 409）处理，旅程在第二条异常处理时失败。
- **修复：**
  - 每条确认、每条异常处理、开始归档各自一个 key，在用户确认时生成，同一意图重试时复用；
  - 重试时已成功追加的记录不再重发，直接用已得到的序号（或按 subject 查询到的本人最新记录）；
  - 单测：两条异常；开始归档失败后重试。

**N2. Q17 的两项要求没有做**（kickoff §7.1“上传包的后端校验”、§7.5“请求侧约束”）

- **上传包的后端校验：** 要求提交在 `frontend/scripts/` 下的脚本，在前端工具链镜像中打包、在依赖镜像中校验，覆盖有无 `logics.xml`、缺 `dbcfg.sql`、长路径，并比较成员路径与内容摘要。候选中没有这个脚本；handoff §5 只“复用报告 P1/P2 结论”，而那是修复前产物被拒收的结论，不能证明修复后的产物被接受。§2.2 的 P2 是我的核对，不能代替该脚本。
- **请求侧约束：**
  - 要求在模拟模块中只实现一处，e2e 与组件测试共用，并由一个单测逐条路由核对；
  - 现在只在 `e2e/workspace-shell.spec.ts` 中复制了 4 段内联检查（`preview-operations`、`archive-confirmations`、`archive-anomaly-resolutions`、`archives`），外加 `archive-audit-events` 的必填参数；
  - 没有覆盖：`upload-revisions`、`submit-attempts`、`review-events`、`history-compares` 缺 key 返回 422，`POST /v1/workspaces` 带 key 返回 422；
  - 没有单测。
- **修复：** 按 kickoff 原文实现。脚本的日志 SHA256 与各包结果写进 handoff；04 取证时在取证 worktree 再运行一次。

**N3. 归档桩仍有后端不会产出的状态**（`mock-data.ts:370–380`，`e2e/workspace-shell.spec.ts:304–320`，`mock-data.test.ts`）

- **现象：** 见 §1 B3。`ARCHIVE_PLAN_READY` 在已选中的场景中被当作确认后的预检使用，但它没有 `selected`、选择摘要和异常；`mock-data.test.ts` 新增的断言把 `ARCHIVE_PLAN_READY.can_start === true` 写成了期望。
- **影响：** 界面在确认后的预检上依据“异常列表为空”渲染，与后端返回的形态不同（后端仍列出已处理的异常）。e2e 没有检验界面在真实形态下的表现。
- **修复：**
  - 确认后的预检按后端规则构造：保留 `selected`、`selection_subject_digest`、`confirmation_requirements` 与全部异常，`audit_validity: true`、`can_start: true`；
  - 按 Q17 写一个单测，对每个预检场景核对 `can_start = 已选中 && blockers 为空 && audit_validity`，以及确认后 `confirmation_requirements` 仍含选择摘要；
  - 或由模拟模块从场景中的审计事件推导这些字段。

**N4. B5 只修了一半**

- 刷新后恢复页面锁定，并在 Preview 成功后继续下载 bundle、进入差异浏览；提交成功后显示提交结果。只显示操作状态卡片时，用户不知道下一步去哪里。
- 提交对话框显示“需要管理员处理”与可复制的操作 ID。
- 补审核要求的两条 e2e。
- 操作结束后从 URL 中移除 `operationId`，否则再次打开工作台仍显示旧操作的卡片。

**N5. 上传重试仍会先失败一次**（`UploadStepCard.tsx:180–227`，`journeys.ts:181–212`）

- 旅程每次都从上传开始，`expected_workspace_version` 取自重新读取的工作区。上传成功后的任何失败，重试时都用旧 key 和新版本重新上传，后端返回 409（`application/workspace/contracts.py:86–111` 的指纹包含版本）。界面显示错误并换新 key，用户第二次重试才成功，且多上传了一次。
- **修复：** 记住已成功的上传（`upload_revision_id`、`generation`、版本），重试从 Preview 开始；Preview 已受理的从轮询开始。补“提交、审核各一次超时后重试回放第一次结果”的 e2e。

**N6. B8 的剩余部分**

- 归档对话框就地显示错误码并可复制；
- 审核 `REVIEW_VERSION_CONFLICT` 提供“刷新”，重新读取审核信息后再允许确认；
- 审核、归档补复制按钮；
- 补一条生产构建下错误码可见的测试（或组件测试不依赖 `import.meta.env.DEV`）。

**N7. B9 的覆盖缺口**

按原审核 B9 的清单补场景，场景集中到模拟模块，并：

- 写操作 e2e 使用对应身份（审核人审核、归档人归档），核对请求所带的 token；
- 归档场景的 ID 前后一致。

**N8. B11 的剩余部分**

- 只传本次归档时的阶段名按 UI 优化方向 §7.2；
- 首批显式空基线时第 ① 步禁用并说明原因；做不到就写成偏差；
- 摘要行与目录卡片二选一。

**N9. 截图仍缺**（原审核 §8）

退回、撤回对话框，上传空状态、执行中卡片、失败与重试，提交未完成（`ABORTED`），归档被阻断，写操作的权限拒绝与版本冲突，都还没有截图。这些不是“不能按草图修正”的偏差，而是没有对应的 e2e 场景，随 N4–N8 补齐。

## 4. handoff 与事实不符

- 审核报告写为 `/tmp/fe2c-review.md`，应为仓库中的 `docs/frontend-vnext/reviews/fe2c-review.md`；handoff 也没有引用 Q16、Q17。上传模式的撤回已由 Q16 决定不提供，不再是“交 owner 的偏差”。
- 复审范围写为 `5830bc73c4..4c096d49`，实际候选为 `680b643f`。
- 提交清单列了 `cd40b409`，它不在提交链上（05 仓库中只是悬空对象），漏了 `680b643f`。
- §4 的运行列表：
  - 列了 `cd40b409`、`41081b87`、`ec34b134` 上的运行，这三个提交都已被改写，不在链上；
  - 漏了 `4c1a916a`（`05:31:29Z`，exit 1）与 `87fa333d`（`05:35:02Z`，exit 0）两次运行。
- M5 说日志在 `/home/dev/gdds-fe-logs/fe2c/`，但 `08:01Z` 以后的 6 次运行（含所引用的那次）都在 `/home/dev/gdds-fe-logs/frontend/`。runner 支持 `GATEWAY_FE_LOG_DIR`。
- §2 的 B8 一行写归档错误码已修复，§3 写 M2 已修复，都不符（§1）。
- §2 的 B9 一行把 FE2b 已有的对象写成本轮修复。
- §5 把 B10 的连续运行留到 04 取证。04 只在复审通过后运行一次，不做调试。
- 05 上的修复 worktree 没有分支或 tag 指向候选，只能从 detached HEAD 打包。下一轮请给候选一个分支名（例如在 05 仓库中更新 `fe-vnext`），便于传输与审核。

## 5. 复审范围与要求

1. 修复 N1–N9；§4 的不符之处在新 handoff 中改正。
2. **探针**（结果写进 handoff）：
   - N1：两条异常、开始归档失败后重试，各一条单测；把 key 改回共用后单测应失败；
   - N2：后端校验脚本对四种包给出预期结果；去掉 `size` 写入后脚本应报告拒收；请求侧约束的单测在去掉任一路由的检查后失败；
   - N3：把确认后预检的 `confirmation_requirements` 改为空数组，按规则写的单测应失败；
   - N5：上传成功、Preview 失败后，单次重试应成功且不再上传。
3. **截图：** 补齐 N9，重拍改动涉及的全部截图。
4. **运行：** 在 05 的已提交 detached worktree 上完整运行 runner（`--e2e --screenshots`），日志放到 `GATEWAY_FE_LOG_DIR=/home/dev/gdds-fe-logs/fe2c/<轮次>`；运行 N2 的后端校验脚本。
5. 复审第 2 轮范围为 `680b643f..<新 handoff 提交>`，通过后在 04 取证一次。

## 6. 本轮在节点上留下的内容

- **开发主机：** 只读 worktree `/home/dev/gdds-fe-rereview1-fe2c-680b643f`；bundle `/home/dev/gdds-test-tmp/src-rereview1-fe2c-680b643f.bundle`。
- **05：**
  - worktree `/home/dev/gdds-fe-rereview1-fe2c-680b643f-05`；
  - bundle `/home/dev/gdds-test-tmp/src-rereview1-fe2c-680b643f.bundle`；
  - 日志与探针 `/home/dev/gdds-fe-logs/fe2c/rereview-1/`；
  - 截图 `/home/dev/gdds-fe-evidence/fe2c/rereview1-680b643f-05/`。

  探针 worktree 已删除。FE2c 退出合入后清理。
