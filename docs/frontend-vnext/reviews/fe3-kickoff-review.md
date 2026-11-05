# FE3 kickoff 审核报告

- **审核对象：** main 本地提交 `5c360bfb1b`（`docs/frontend-vnext/fe3-kickoff.md`，草案，未推送），父提交 `2c79d0947f`。
  两者的 `vnext/` 树都是 `2791d3ff3d`，与 BE-a 设计的引用基线 `d0a8143d80` 相同。
- **依据：** AGENTS（专用测试节点、DC67、DC68、DC70 补充、前端测试（FD7）、Docker / Compose 验证、全局比例化保障）；
  testing-conventions“前端测试（FD7）”；前端 kickoff §3.3、§4.2–§4.4、§5、§6、§7、§7.1；FE2 kickoff §6.5、§7、§9 Q16–Q19、§10；
  FE2c 各轮审核报告；DC70、DC73、DC75；BE-a 设计补充（`f20f08bea9`）及其审核（`fcbfb4c1a0`）；BE-a / BE-d 任务草案；后端交接 §2。
- **日期：** 2026-11-05。审核会话只写本报告，不改 kickoff 正文。
- **结论：定向修订。** 方向成立：乙方案的拆分、独立脚本、生产构建加注入身份、指针取代 `sessionStorage` 标记，以及撤回按钮始终显示，都可以按建议确认。
  需要先修订 4 处验收条件，否则实施会做不到，或者会按错误的标准判定：
  - **B1** t1 的表数标准取错了字段：census 的 133 不是 Preview 的 125；
  - **B2** §3.3 中有两项在当前 backend 上走不到；
  - **B3** R10、R5 的期望与后端行为不符；
  - **B4** §6.2 写的指针在提交失败后的行为与 BE-a 不一致。

  这 4 处都只需改文字，不改阶段安排。修订后做一次定向复审，只看 B1–B4 和第 4 节中标注“建议随本次修订”的条目。

## 1. 方法

- 在开发主机的只读 detached worktree `/home/dev/gdds-p6-logs/fe3-kickoff-review-wt`（`5c360bfb1b`）中阅读文档与源码；主工作区只用于提交本报告。
- 04、05 只做只读核对：`ssh … 'echo OK'`、`docker images`、`docker image inspect`、`ls`、`find`、`sha256sum`。没有获取占用标记，没有运行测试、Compose、构建或浏览器。两台节点核对时都没有占用标记。
- 没有访问 ct108。§2.1 中 ct108 占用标记的内容（`p6-baseline-measure`，自 2026-11-04T23:10:53Z）因此未核对。
- 开发主机上的真实数据只统计文件数、字节数、路径长度、是否有非 ASCII 文件名，以及成员 SHA256 是否相等，不输出 SQL、业务值或文件名。
- 程序核对的内容：
  - 快照的重排格式：Python `json.dumps(indent=2, sort_keys=True) + "\n"`；
  - t4 长路径能否按 ustar 规则拆分；
  - 链接与锚点是否都能解析；
  - 依赖输入自 `p6-backend-image-exit` 起是否有变化（`git diff`）。

## 2. 事实核对（§2）

| 项 | kickoff 所写 | 核对结果 |
| --- | --- | --- |
| `fe-fe2c-exit` | tag 对象 `86901e038d` → `749f219d5f`，测试提交 `220325da37`，`frontend/` 树 `960ab1f6a1`；main 合入 `0430e0e738` | 一致。`0430e0e738` 的父提交是 `998d9b58bc` 与 `749f219d5f`；`fe-vnext` 在 `749f219d5f` |
| S2a | 证据复核 2 通过，候选 `3b3d9c97bc`；main 上没有 `p6-s2a-exit` | 一致。报告在 main 上，结论为“证据通过”；`3b3d9c97bc` 只在 `p6-s2a` 分支上；没有 `p6-s2a*` tag |
| BE-a | `f20f08bea9`；审核 `fcbfb4c1a0`；归属订正 `680f9a60f0` | 一致，三个提交都在 main 上 |
| 基准剩余项、W4 剩余 14–30 小时 | 引自交接 §2.1 与 W4 重复键停止复核 | 一致（停止复核第 52 行）。ct108 占用标记未核对（见 §1） |
| 快照自 `a2fb4a027a` 起后端 HTTP 层没有改动 | §5.2 | 一致：`git diff a2fb4a027a 2c79d0947f -- vnext/backend/src` 为空 |
| 依赖镜像 tag | main vnext 树需要 `lock-c668cef8e47e`，由 `--print-input` 得出 | 成立。`--print-input` 的五个输入文件和 `Dockerfile.dependency-base` 自 `p6-backend-image-exit`（`72dd45a47b`）起都没有改动；开发主机与 04 的 `lock-c668cef8e47e` label 都是 `c668cef8e47e…bea290`。`--print-input` 需要节点本机有 `rust:1.97.0-bookworm`，04、05 都有 |
| 05 / 04 依赖镜像 | 05 缺 `lock-c668cef8e47e`，只有 `lock-d054366c02fa`；04 有 | 一致。04 同时也有 `lock-d054366c02fa` |
| RS 依赖镜像 `gateway-p2r1-repository:lock-6dc9659f0aee` | 两节点都有 | 一致，label `uv-lock-sha256` 都是 `6dc9659f…` |
| `gateway-repository-service:local` | 05 revision `80ce756619`；04 revision `3b3d9c97bc` | 一致（05 的 `build-input-revision` 是 `4158ea39d4`） |
| 前端工具链 | 两节点都有 | 一致（`mcr.microsoft.com/playwright:v1.64.1-noble`） |
| npm 缓存 `/home/dev/gdds-fe-cache/frontend/` | 两节点都有 | **只有 04 符合。** 05 的缓存在 `/home/dev/gdds-fe-cache/fe0/npm-cache`，归档在 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`。两节点归档的 SHA256 相同（`0d861824…0089f4`），来源提交都是 `a2fb4a027a`（N1） |
| 源包 | 两节点都有，只含 `/sql/dbcfg.sql` 与 `/comps/logic/logics.xml`，没有 `.pmc` | 一致。04、05 与开发主机上 `rd-t1-a-v1/-v2`、`rd-t4-d-v1` 的 SHA256 相同（`42794011…`、`4019737f…`、`95408cc3…`） |
| 节点上没有组态目录原件 | 04、05 都没有 | 一致。两节点的 `/home/dev/gateway-real-dumps` 下只有 `datasets.json`、`packages/`、`runs/`（05 另有 `testdata1/`）；`/home/dev` 下深度 6 以内没有 `.pmc` |
| 组态目录与源包的对应 | t1 两个成员都一致；t2–t4 `dbcfg.sql` 一致 | 文件数与字节数全部一致（t1：19/19，6,853,875/6,854,427）。**8 个目录的两个成员都与对应源包一致**，t2–t4 的 `logics.xml` 也一致，比 kickoff 写的更强 |
| 根目录恰好一个 `.pmc`，且有 `sql/dbcfg.sql` | 沿用 legacy | 一致：`upload-package.ts:67–70`；legacy `workspaceUpload.ts:85–93`。8 个目录的根目录都恰好有一个 `.pmc` |

t1 与 t4 目录还有两点要在实施时注意，都不阻塞：

- t1 的两个目录各有 3 个非 ASCII 文件名和 3 个空文件；`large-1` 有 498 个非 ASCII 文件名，有 2 个路径超过 100 字节（最长 103 字节）。
- 我按 `tarHeader` 的拆分规则程序核对过这 2 个长路径，都能拆成 `prefix` 与 `name`。后端 `normalize_package_path` 只限制 1024 字节和 32 段，不拒绝非 ASCII。因此 t1 和 M1 的输入不会在打包或后端校验时被拒。

## 3. 阻塞项

### B1 t1 的通过标准取错了字段（§8.3，第 410–412 行）

**问题：** 第 410 行要求“Preview v1 的表数等于 S1 census 中 `rd-t1-a-v1` 的表数”。两个数对不上：

- census（`p5-arch-closure-s1-census.json`）中 `rd-t1-a-v1` 的 `table_count` 是 133（`source_ddl_table_count` 132），其中含 `SKIP` 8 张、`SNAPSHOT_ONLY` 1 张；
- 后端 t1 对 Preview 的预期是 `S2B_DATASET_BASELINE["rd-t1-a-v1"]["preview_table_count"] + 1` = 125。见 `real_dump_journey.py:138–147` 与 `_assert_s1b_preview_summary`（第 1726–1738 行），+1 是派生表 `composite_signal_point`。

按 kickoff 的写法，正确的 t1 旅程也会判为失败。

第 412 行的“逐表核对 v2 Preview 的表状态与行级记录数”也难以由程序完成。后端 t1 只断言汇总数（`table_count`、`changed_table_count`、`degraded_table_count`、`failed_table_count`），没有逐表的状态可以对照。

**改法：** 预期值从被测候选的同一 vnext 树读取，不手抄：

- **v1：** `table_count = changed_table_count = preview_table_count + 1`（t1 为 125），`degraded_table_count = failed_table_count = 0`（同第 2737–2741 行）。
- **v2：** `table_count = 125`，`degraded_table_count = failed_table_count = 0`，`changed_table_count = S1B_V2_PREVIEW_CHANGED_COUNTS["rd-t1-a-v2"] + composite_changed`。前一项是 4（第 180 行起），后一项为 0 或 1（第 3078 行）。
  `composite_changed` 取同一 vnext 树上后端 t1 运行（BE-d 的 05 t1）的结果；取不到时 handoff 记录实际值是 4 还是 5，并注明没有对照。
- **对照的内容：** 把“逐表核对”改成核对四个汇总数，由程序读取下载到的 bundle manifest 中的 `pairs[].summary`。

这样通过标准可以完全由程序判定。前端上传的是整个目录（19 个文件），后端忽略 Contract 以外的成员，后端 t1 上传的是规范化源包。两者的 `dbcfg.sql` 与 `logics.xml` 逐字节相同（§2），因此预期值可以直接沿用。

### B2 §3.3“FE3a 可以验证”中有两项在当前 backend 上走不到（第 128–130 行）

这是 FE3a 冒烟的验收清单（§4.7：“§3.3 所列各项”），FE3a 现在就要开始，因此列为阻塞。

- **“归档候选为空时的界面”走不到。** 归档入口只在组态树的提交节点上：`WorkbenchPage.tsx:392` 要求 `selected?.kind === "submission"`，`view-model/workspace.ts:253–254` 也只对提交节点给出“归档主线”。当前 backend 上 History 只有 `INITIAL`，提交又要先下载 bundle，因此整个 FE3a 都不会出现提交节点。
- **403 只能验证上传一项。** 工作区按 `owner_actor_id` + 设备 + 项目隔离（`application/workspace/services.py:57–70`），每个身份有自己的工作区。无权限身份的工作区没有上传，无法进入 Preview。审核、归档都需要提交节点。
- **“Preview 结果可读”的判据没有写明。** Preview 成功后，前端会立即下载 bundle：`runPreviewJourney` 由 `UploadStepCard.tsx:207–239` 调用，续做路径见 `WorkbenchPage.tsx:130`。在当前 backend 上这一步必然失败，界面进入错误状态。

**改法：**

- 删去“归档候选为空时的界面”，并在“要等 BE-d”一项中补上它；
- “无权限身份的 403 显示”改为“无权限身份上传返回 403 的显示”；
- 写明冒烟的判据：
  - `GET .../preview-results/{id}` 返回 200，且所含 `preview_result_id` 与工作区的 `current_preview_result_id` 一致（用 `page.waitForResponse` 等方式由程序断言）；
  - 之后的 bundle 下载失败不作断言，但页面上不能出现未捕获错误。

另外，§3.3“要等 BE-d”一项中“提交入口在 Preview 顶栏”的说法成立：`SubmitDialog` 只在 `ComparisonPage` 的 PREVIEW 模式中渲染，“提交”按钮在 `!bundle` 时禁用（`ComparisonPage.tsx:485`）。“不下载 bundle 就走不到审核与归档”也成立：审核顶栏要等 History bundle（`ReviewActions` 中的 `bundleReady`），归档要求提交已审核通过。

### B3 R10、R5 的期望与后端行为不符（§4.7，第 245、249 行）

**R10 中 Preview 与提交的 403 在真实 backend 上产生不了：**

- 提交与上传使用同一个权限 `upload_submit_workspace`：上传见 `application/workspace/services.py:94`，提交见 `application/submission/accept.py:77`。能上传的身份必然能提交。工作区又按 actor 隔离，无法用别人的工作区。
- §4.6 的身份中，没有“能上传但没有 `preview_workspace`”的身份。
- 无权限身份进入审核模式时，`GET .../review` 会先返回 403（`ComparisonPage` 的 `loadBundle` 先调用 `getReviewFacts`）。因此“审核 403”出现在页面加载时，不在“通过”按钮上。

**R5 写的“backend 回放 200”只对审核成立。** 按 FE2 kickoff §7.5 的 N1：提交第一次与回放都返回 202；`review-events` 第一次 201、回放 200。另外，`route.fetch()` 要重放请求体，上传是含 Blob 的 multipart，不适合用于 R5。kickoff 已限定为“提交或审核”，这一点正确。

**改法：**

- R10 的真实 e2e 覆盖四项：
  - 无权限身份上传 403；
  - 增加“只有上传、没有 Preview 权限”的身份，验证 Preview 403；
  - 无权限身份打开审核模式时 review 查询 403；
  - 无权限身份进入“归档主线”时候选查询 403。
- 提交 403 只由模拟接口覆盖，并在 handoff 中说明原因。
- R5 的回放状态码按 route 写：提交 202，审核 200。

### B4 §6.2 写的提交失败后指针行为与 BE-a 不一致（第 352 行）

**问题：** 第 352 行写“失败或 `ABORTED` 时两者都为空”。BE-a 设计补充 §2 的生命周期表（`p6-be-a-design.md:33`）写的是：

> 执行、等待、人工恢复或结果未知：保留 attempt ID；不能按 Operation terminal status 推断释放

只有“经既有规则确认 `ABORTED` 并释放”后，两个指针才都为空。operation 进入 `FAILED`，或停在 `MANUAL_RECOVERY_REQUIRED` 时，`active_submit_attempt_id` 可能仍然非空。

按 kickoff 的写法实现，会出现两种情况：前端在 operation 失败后认定指针已清空；或者因为 §6.1 第一行“提交正在执行”，撤回按钮一直禁用，而界面不知道原因。

**还有一个缺口：** `gateway-submit-operation` 标记删除后，前端怎样判断 URL 中的 `operationId` 是提交还是 Preview？上传与提交写入 URL 时都用 `operationKind=operation`（`UploadStepCard.tsx`、`SubmitDialog.tsx:170–175`）。现在靠 `sessionStorage` 标记区分。

**改法：**

1. 第 352 行改为：
   - 操作到达终态后重新读取工作区与 attempt（`GET .../submit-attempts/{id}`）；
   - attempt 为 `FINALIZED`：指针转为 `active_submission_id`；
   - attempt 为 `ABORTED`：两个指针都为空，显示“提交未完成”；
   - operation 已到终态、但 attempt 仍为 `PREPARED`/`EFFECT_PENDING`，且指针仍非空：显示 FE2c 已有的“需要管理员处理”提示，不自动重试。
2. §6.1 第一行的原因区分两种情况：
   - operation 未到终态：“提交正在执行，完成后才能撤回”；
   - operation 已到终态、attempt 未结束：“提交结果待确认，需要管理员处理”。
3. §6.2 写明：URL 中操作的类型以 `GET /v1/operations/{id}` 返回的 `job_kind`（`backend-vnext/submit` 或 `backend-vnext/preview`，FE2 kickoff §7.5 取值表）为准，再与指针所指 attempt 的 `operation_id` 比较。还要写明续做卡片显示在哪个页面：Preview 页，或刷新时所在的工作台。
4. 模拟数据中“operation 终态、attempt 未结束、指针保留”的场景，按 BE-a §2 的生命周期表构造（§7.5“后端可达状态”）。

## 4. 非阻塞意见

标“建议随本次修订”的，改动小，影响实施会话的第一步，建议和 B1–B4 一起改；其余可以在提示词发出前或实施中处理。

| # | 位置 | 意见与依据 | 建议 |
| --- | --- | --- | --- |
| N1 | §2.2 第 53 行 | 05 的 npm 缓存路径与 kickoff 不符（§2）。`run-tests.sh` 的默认路径是 `/home/dev/gdds-fe-cache/frontend/...`，所以在 05 上运行要设置 `GATEWAY_FRONTEND_NPM_CACHE` 与 `..._ARCHIVE` | 建议随本次修订：改正 05 的路径；新脚本与 `run-tests.sh` 使用同样的变量 |
| N2 | §2.3 第 85 行 | “满足”还缺一个前提，由 BE-d 决定。前端 `posix-tar.ts` 的要求：第 1、2 个成员是 `manifest.json` 与 `artifact-closure.json`（第 398、406 行）；之后的成员与 closure 条目逐个对应，顺序相同，`logical_path` 不重复（第 341、416 行）。BE-d 草案 §3 还在考虑“同一 `source_ref` 对应多个 `logical_path` 时的去重”。如果后端按内容只发一次、而 closure 中仍有多个条目，前端会报“tar 成员顺序或路径不匹配” | 建议随本次修订：§2.3 写明前端的这一前提。**交设计会话**，在 BE-d kickoff 审核中确认（BE-d） |
| N3 | §4.3 第 174–177 行 | 两处要写明。① `build-repository-service-image.sh` 找不到 label 匹配的 RS 依赖镜像时，会自动改用缓存 URL 构建（第 145–161 行），构建默认用 `host` 网络。② compose 中 RS 有 `image:` 与 `build:`（`compose.yaml:120`），`up` 时如果本次 tag 不存在，会按 compose 的参数构建：`USE_PRELOADED_DEPENDENCIES=0`，从 GitHub 下载 Dolt。后端 harness 每次 `up` 都带 `--no-build`（`compose_gate_harness.py:1190、1195`） | 建议随本次修订：<br>• 构建前程序核对 `gateway-p2r1-repository:lock-<uv.lock 前 12 位>` 存在且 label 一致；<br>• RS 构建也设 `GATEWAY_DOCKER_BUILD_NETWORK=none`；<br>• 所有 `up` 都带 `--no-build`。<br>这样“构建需要访问网络即停止”可以由程序实现。预置依赖模式下 RS 的 Dockerfile 只检查 Dolt 与 uv 已在镜像中（`Dockerfile:16–18`），不下载，可以离线构建 |
| N4 | §4.3 第 171–173 行 | ① 给 05 补依赖镜像时，AGENTS 的 backend/worker 规则要求在 CT201 的 clean worktree 运行 `build-backend-dependency-base.sh --save <归档>`（标签已存在时会复用并核对 label），并记录完整输入摘要、tag、config digest、全部 DiffID、归档 SHA256 与起止时间；不是直接 `docker save`。② S2a 合入后，main 的依赖输入会变成 `p6-s2a` 的 `pyproject.toml`/`Cargo.lock`，tag 可能就是两节点都已有的 `lock-d054366c02fa`。FE3b 仍按 `--print-input` 结果核对 | 改为按 AGENTS 的流程写；FE3b 一段保持“按标签与身份核对” |
| N5 | §4.3、§4.9 | 比例化。在日志中记录 config digest 与全部 DiffID，每次都要 `docker save` 4.67 GB 的依赖镜像（`run-tests.sh` 已经为工具链做了一次）。按 AGENTS，跨节点身份比较只在传输时需要；`backend/Dockerfile:19` 在预置依赖模式下已经核对 tag、输入摘要与五个输入文件 | 每次运行记录 tag、`dependency-input-sha256` label、本机 image ID、`docker image inspect` 的 `RootFS.Layers`；config digest 与 DiffID 在传输时比较一次，写进 handoff |
| N6 | §4.4 第 184 行 | Compose 项目名只能用小写字母、数字、`-` 与 `_`；`20261105T101500Z` 这样的时间戳含大写字母，会被拒绝 | 写明时间戳用小写（例如 `20261105t101500z`） |
| N7 | §4.5、§4.8 | 工具链容器用 `docker run --network <项目名>_default` 加入 Compose 网络，但不属于 Compose 项目。中断时如果它还连在网络上，`compose down` 删不掉网络（network has active endpoints），按 §4.2 会变成 `cleanup-failed` | 建议随本次修订：<br>• 工具链容器使用固定名称与项目 label；<br>• 清理时先停止并删除它，再 `down`；<br>• 运行前残留检查与清理后核对也包括它 |
| N8 | §4.5 | 生产构建没有身份切换：`gateway-session-change` 只由 `DevIdentityControl` 发出，`currentGatewaySession()` 在调用时读取 `window.__gatewaySession`。多身份旅程要为每个身份建一个 browser context，各自 `addInitScript`。OPFS 也按 context 隔离，R2“再次打开同一 Preview 不重新下载”要在同一个 context 中验证 | 写入 §4.5 |
| N9 | §4.4、§4.9 第 276 行 | 第 185 行写“token …日志中不输出”，但 Playwright trace 的网络记录含 `Authorization` 请求头，`addInitScript` 的内容也可能进入 trace。token 每次随机生成，栈清理后就失效，风险很低，但正文的说法不准确。另外，t1 的参考截图中有真实业务值，第 276 行只提到 Compose 日志与 trace | 改为“trace 中含本次运行的临时 token，只留在节点上”；t1 截图同样只留在节点上，只把 SHA256 写进 handoff |
| N10 | §4.5 第 195 行 | Vite 的 `preview.proxy` 与 `preview.host` 默认沿用 `server` 的设置，`vite.config.ts` 中的代理不分模式，可以使用。生产构建中 `window.__gatewaySession` 在每次请求时读取（`session.ts:20–21`），`addInitScript` 注入有效；`check-production-build.mjs` 不禁止 `__gatewaySession` | §5.2 的运行时 `/openapi.json` 改为在工具链容器内经 preview 服务器的代理读取，顺带证明代理可用 |
| N11 | §4.6 | ① 身份文件格式与后端一致（`sessions[]`：`token`、`actor_id`、`gateway_device_external_key`、`business_project_id`、`permissions`；见 `real_dump_journey.py` 的 `_write_compose_secrets`）。每个身份要有不同的 `actor_id`：本人撤回按 `Submission.created_by` 判定，工作区也按 actor 隔离。② 组态树读 History，需要 `read_project_history`（`history/queries.py:27`）；审核模式的历史比较与轮询也需要它（`history/compare.py:234`、`operation_scope.py:152`）。各身份都带这一项是对的。③ 多个 scope 时，每个 scope 播种要用不同的 RS `Idempotency-Key`。harness 固定使用 `compose-seed-repo`（`compose_gate_harness.py:1145`），照抄会回放同一个仓库。`business_baseline_node_id` 也要互不相同。backend 启动前要写好全部映射 | 写入 §4.6 |
| N12 | §4.6 第 224–229 行 | 把 SQL 移到共用文件可行：生成器以 `sql.encode("utf-8")` 计算摘要（第 206–207 行），文件内容与字符串逐字节相同（含结尾换行）时，fixture 不会变；可以用现有的“生成两次逐字节比较”和跨实现摘要测试核对。需要补充四点：<br>• 真实 e2e 还要 `logics.xml`，它现在由 f-string `_composite_logic()` 生成，也要移到文件；`_workbench_telemetry_sql()` 由程序生成，留在生成器中即可。<br>• 每个 scope 的上传顺序要保证每次提交都有规范变化，否则提交返回 409 `NO_CANONICAL_CHANGE`。例如“归档后 FULL（INITIAL + MODIFIED）”之后，再上传 MODIFIED_ONLY 时不能还用 `MODIFIED_SQL`。<br>• 这些输入只经过进程内物化，没有经过 Repository import（Dolt）。风险不大（表结构简单，keyless 表自 P5 DC29 起、ordered 表的空白区间自 G8 起都已支持），但应在 FE3a 调试开始时先在 05 上走一遍。<br>• R4 的身份确认只用模拟接口覆盖。可以把 `REPLACEMENT_CURRENT_SQL`（`project-b`）作为一次 MODIFIED_ONLY 上传，在真实 backend 上产生 `DIFFERENT_PROJECT` 并覆盖确认；成本很低 | 写明上传顺序与 XML 文件；增加 replacement 输入 |
| N13 | §5.1 第 282–283 行 | 规范化要在 Python 中做。快照含 `9007199254740991.0`、`0.0`（`openapi.json:14–15` 等处），Node 的 `JSON.stringify` 会写成 `9007199254740991` 与 `0`，逐字节比较就会失败。我已核对：宿主机 `python3 -I`，`json.dumps(obj, indent=2, sort_keys=True) + "\n"`，重排后与当前快照逐字节相同（快照没有非 ASCII 字符） | 写明在宿主机用 `python3 -I` 规范化，并固定 `ensure_ascii` 的取值 |
| N14 | §5.3 | 同步清单还缺两项：<br>① 模拟接口新增“本人撤回”身份时，`check-production-build.mjs:26` 的禁用模式 `dev-token-(?:submitter\|reviewer\|archive-confirmer\|no-permission)` 要一并扩充，否则新的模拟 token 进入生产构建也查不出来。<br>② 有了指针后，Preview 顶栏的“提交”在任一指针非空时应禁用并给出原因（目前只在 `!bundle` 或续做期间禁用，后端会返回 409 `SUBMIT_OCCUPANCY_CONFLICT`）。待审期间“上传”是否禁用，后端不拦（`upload-revisions` 的 409 只有幂等冲突与版本冲突），属于界面决定 | ① 补入 §5.3；② 补入 §6.1。待审期间上传的行为**交设计会话**决定 |
| N15 | §6.1 第 333–334 行 | 撤回或退回后指针会清空（BE-a §2），所以“指针非空且 `status = REJECTED/WITHDRAWN`”只会在工作区读取过时时出现。kickoff 没有出现按 actor 或按指针推断可撤回的情况：GET review 成功就说明调用方持有两个审核权限之一，再加上 `PENDING`，可以撤回（BE-a §3），推断成立 | 这两行改为：先重新读取一次工作区，再按新状态显示。模拟场景按“读取工作区之后被退回”的竞争构造（FE2 kickoff §7.5“后端可达状态”） |
| N16 | §6.3 W1–W7 | 在模拟接口与真实 e2e 中都可以实现。W5 的真实 e2e 需要两个 context 同时打开（提交人与审核人），见 N8。W6 只用模拟接口覆盖是合理的 | 13.4 的探针“预期版本改为工作区版本”：需要先确认场景中两个版本的取值确实不同（工作区版本经过上传、Preview、受理、finalize 已多次递增，通常不同） |
| N17 | §8.2 第 398–404 行 | 后端 t1 的顺序（`JOURNEY_STEP_IDS`）是：v1 workspace/upload/preview/submit/repository-read/approve/archive → repeat-v1（同一输入重复上传，断言没有变化）→ v2 … approve → history。history 是**两节点**（v1 提交、v2 提交，见 `_history_compare`）。kickoff 的第 6 步是三节点，并且省略了 repeat-v1 | 不要求一致，但不应写“对应”。改为“按后端 t1 的主线顺序，省略 repeat-v1；历史比较用三节点”，避免审核时按逐步对应去核对 |
| N18 | §8.1 | ① “目录只读”：工具链容器以 root 运行，`chmod` 防不住写入，要用只读 bind mount（`:ro`）挂进容器。② 没有写明谁执行传输、谁生成逐文件 SHA256 清单 | 写明由实施会话在 owner 授权后执行，并把清单的 SHA256 写入 handoff；容器内只读挂载 |
| N19 | §8.4 第 418–434 行 | 测量方法基本可行，有五处要补：<br>① **FULL 模式。** FULL 先打 ① 的包，再打 ②（`UploadStepCard.tsx:207–208`），打 ② 时 ① 的压缩包还在内存中，GC 不及时时 ① 的 tar 也可能还在。`buildTar` 先把文件内容存一份，再拼一份整包，峰值约为目录大小的 2 倍。t4 的 MODIFIED_ONLY 约 0.65 GB；FULL 可能超过 1 GiB。建议把 `large-1` 同时用作 ① 和 ②，测一组 FULL，不需要再传 `large-2`。<br>② **进程。** `setInputFiles` 选目录时，本地启动的浏览器拿到的是文件路径，读文件内容发生在 `file.arrayBuffer()`，选择目录不会复制文件内容。`new File([bytes])` 的数据会交给浏览器主进程的 Blob 存储，上传时由网络服务进程读取。因此要记录浏览器进程树中的全部进程（renderer、browser、utility/network、GPU），主指标仍是 renderer。`SystemInfo.getProcessInfo` 只能在浏览器级 CDP 会话上调用（`browser.newBrowserCDPSession()`），而且是实验性接口。拿不到 PID 时，从浏览器主进程向下遍历 `/proc` 中的子进程，按命令行中的 `--type=` 区分。Playwright 默认关闭 Chromium 沙箱，得到的 PID 就是容器内 `/proc` 中的 PID。<br>③ **峰值清零。** 每次新开浏览器，进程的 `VmHWM` 就从进程启动时算起，但页面加载本身也会抬高峰值。建议在“确认上传”前对 renderer 写一次 `/proc/<pid>/clear_refs`（值 5），把峰值清零。<br>④ **包大小。** 用路由拦截时，含 Blob 的 multipart 请求体通常拿不到（Chromium 不把 Blob 内容交给拦截层）。改从 multipart 中 `manifest` 部分的 `size_bytes` 读取（前端在 `client.ts` 中按 `File.size` 填写）。实施时先验证。<br>⑤ **打包耗时。** “确认上传”到上传请求发出之间还有 CreateOrGet 与 `sha256`（`client.ts` 中的 `uploadRevision`）。改用步骤卡已有的阶段耗时（`begin("packaging")`），或写明这一时段包含哪些步骤 | 写入 §8.4。默认标准见第 5 节 Q3 |
| N20 | §9、§13.3 | FE3b 的 05 t1 是调试还是证据，没有写清楚。§13.3 要求实施会话在 handoff 前跑一次，§13.4 不要求审核会话重跑。如果审核要求修复，新候选上的 t1 由谁、何时重跑没有规定。按 DC30，证据应在最终候选上运行一次 | 写明：t1 证据在审核通过后、于最终候选的 clean 已提交 worktree 上运行一次（与 04 取证同一时点）；handoff 前的那次是调试 |
| N21 | §3.2 第 110 行与 §13.1 第 501 行 | FE3a 的退出条件包含 M1，但提示词第 5 项允许“没传好目录就先做其余各项”。目录迟迟传不到时，FE3a 能不能退出，两处说法不一致 | 交 owner（见第 6 节 O1） |
| N22 | §3.2 第 115 行 | 只比较 `git diff <main> <候选> -- vnext` 为空，查不出候选对 AGENTS、后端文档或其他路径的改动；FE3a 也没有同样的核对 | 改为：<br>• `git rev-parse <候选>:vnext` 与 `<main>:vnext` 相等；<br>• `git diff --name-only <main> <候选>` 只含 `frontend/` 与 `docs/frontend-vnext/`；<br>• FE3a 同样核对 |
| N23 | §4.2 第 151–152 行 | 目录已存在时“退出、稍后重试”，与 DC70 补充“失败即等待、不抢占”含义相同，但用词不同。占用标记中的会话名没有规定 | 写成“退出即等待，不抢占；长时间未释放报告 owner（DC70 补充第 1 项）”；规定会话名，例如 `fe3a-impl`、`fe3a-review` |
| N24 | §4.1 | AGENTS 与 testing-conventions 的 FD7 一节没有提到新的真实 backend e2e 脚本（入口、节点、占用、证据） | 按 DC72 第 2 项的做法，FE3a handoff 写出建议条文，由 owner 转治理会话 |
| N25 | §4.2 第 153 行 | 获取占用标记后再持有 `flock /tmp/gateway-compose-gate.lock`。有占用标记时 flock 是双重保险，成本很低，可以保留 | 用非阻塞方式获取（`flock -n`），失败即退出，与占用标记的处理一致；harness 的做法是等待 1800 秒 |

**检查过、没有问题的地方：**

- **镜像构建：** 依赖镜像只核对 label、不在节点上构建，符合 AGENTS 的 backend/worker 规则（另见 N4、N5）。
- **`down -v --remove-orphans --rmi local`：** backend/worker 没有 `image:` 键，`--rmi local` 只删除本项目的 `<项目名>-backend`、`<项目名>-worker`。RS 有自定义 `image:`，不会被删。依赖镜像、工具链与 client e2e 镜像不是服务镜像，也不受影响。另外，04 上有 302 个、05 上有 68 个后端 Compose 门禁遗留的 `*-backend:latest`/`*-worker:latest` 镜像，harness 的 `down` 不带 `--rmi`；这不属于前端，不要清理。
- **网络：** 工具链容器加入 `<项目名>_default` 后，可以按服务名 `backend` 解析。
- **释放顺序：** §4.2“清理 → 核对 → 释放 flock → 删除占用标记”，以及清理失败时保留标记，与 DC70 补充第 3、5 项一致。
- **OpenAPI：** §5.2 的停止分支正确：FE3a 有任何差异即停止；FE3b 刷新后仍有差异，或差异与预期不符，交设计会话。§5.4 的检查成本很低，可以防止手改生成文件，保留。
- **撤回文案：** §6.1 的 409 文案与 OpenAPI 一致。`review-events` 的 409 有 `IDEMPOTENCY_CONFLICT`、`REVIEW_VERSION_CONFLICT`、`REVIEW_TRANSITION_CONFLICT`、`WORKSPACE_OCCUPANCY_CONFLICT` 四个，后三个刷新后重新判断，`IDEMPOTENCY_CONFLICT` 用通用文案。GET review 的 403 `SCOPE_FORBIDDEN`、404 `RESOURCE_NOT_FOUND` 已在快照中。
- **停止条件：** §9、§10 与 DC30、DC36、DC68 一致：
  - 04 取证在审核之后；
  - t1 在 05，05 的数字只作报告；
  - 脚本自身错误按 DC68 重做一次；
  - 被测对象运行后的失败不重做。
- **文档本身：** 链接与两个 DC 锚点都能解析；章节交叉引用正确。§12 已登记 FE4 重拍节点与 DC36 的冲突。

## 5. owner 已原则同意的 Q1–Q7：逐条判断

| # | 判断 | 说明 |
| --- | --- | --- |
| Q1 乙 | **成立** | 运行框架与新接口无关，工作量最大，可以先做、先审。代价是多一次审核与 04 取证，可以接受。B2 修订后，FE3a 冒烟的范围是可以实现的 |
| Q2 传输 t1 与 t4 v1 目录 | **成立** | 节点上确实没有组态目录原件（§2），源包缺 `.pmc`，前端会拒收。按 N18 只读挂载，并写明由谁传输。按 N19 测 FULL 时把 `large-1` 用作 ① 和 ②，不需要扩大授权范围 |
| Q3 M1 测量与默认标准 | **成立，需补充方法** | 提前到 FE3a 测量并加入 t4 是对的：t1 只有 6.9 MB，测不出问题。按现在的实现，峰值约为目录大小的 2 倍，MODIFIED_ONLY 大概率满足两条默认标准。真正可能超标的是 FULL 模式（N19 ①）。建议标准对 MODIFIED_ONLY 与 FULL 都适用，其余按 N19 补充 |
| Q4 独立脚本 | **成立** | 与 FE2c 的上传包校验脚本做法一致，`run-tests.sh` 继续不依赖后端镜像 |
| Q5 生产构建加注入身份 | **成立** | 注入可以生效（N10）。需要每个身份一个 context（N8），trace 中含临时 token（N9） |
| Q6 以指针取代 `sessionStorage` 标记 | **成立，需先改 B4** | 指针可以跨标签页与设备找回提交尝试。但标记删除后，URL 中操作的类型要改用 `job_kind` 判断；operation 失败后指针可能仍然保留。这两点按 B4 写入后，删除标记不会丢失覆盖 |
| Q7 撤回始终显示 | **成立** | 与 F4 和草图 `header-upload` 一致。按 B4、N15 修订后，禁用原因与后端可达的状态一一对应 |

没有不成立的建议，因此没有需要交 owner 的替代方案。

## 6. 需要 owner 决定或转交的事项

| # | 事项 | 建议 |
| --- | --- | --- |
| O1（交 owner） | 如果 Q2 的目录传输晚于 FE3a 的其余工作，FE3a 是否必须等 M1 才能退出（N21） | 必须等 M1。提前测量的目的就是在 FE3b 之前知道要不要改流式打包。传输是一次性的小操作，不太可能拖住 FE3a；真被拖住时，再由 owner 决定把 M1 移到 FE3b |
| D1（交设计会话，再转 BE-d） | tar 成员与 closure 条目逐个对应、`logical_path` 不重复，这一前提是否由 BE-d 保证（N2） | 在 BE-d kickoff 审核中确认。如果 BE-d 要按内容去重，必须由 closure 本身表达共享，不能出现多个条目对应同一个 tar 成员 |
| D2（交设计会话） | 有待审核提交时，上传是否禁用（N14 ②） | 建议禁用，原因写“已有待审核的提交，撤回后才能重新上传”。否则用户上传后，撤回会因为占用绑定不符而返回 409 `WORKSPACE_OCCUPANCY_CONFLICT`。这是界面决定，不需要后端新增字段 |

## 7. 留下的内容

- **开发主机：**
  - 只读审核 worktree `/home/dev/gdds-p6-logs/fe3-kickoff-review-wt`（detached，`5c360bfb1b`，clean）。保留到定向复审结束，复审会话可以沿用，用完后执行 `git worktree remove`；
  - 空目录 `/home/dev/.claude/jobs/0117fb21/tmp/pkg`（任务临时目录，随任务删除）。
- **04、05：** 没有留下任何内容，只做了只读命令。
- **ct108：** 没有访问。
