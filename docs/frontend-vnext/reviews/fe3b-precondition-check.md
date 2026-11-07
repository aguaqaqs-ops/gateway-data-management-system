# FE3b 前置条件核对

- **日期：** 2026-11-07（节点核对 15:35–15:37Z）。
- **会话：** FE3b 审核与协调会话。只读核对，未改 kickoff、源码与节点状态。
- **核对对象：** 本地 main `d04f718ccd`，`vnext/` 树 `56720104af`，`frontend/` 树 `44a9b5177b`。
- **依据：** [FE3 kickoff](../fe3-kickoff.md) §2、§3.2、§4.6、§5、§6、§8、§12、§13.3；
  [FE3a handoff](../fe3a-handoff.md) 与 `reviews/fe3a-*.md`；
  后端 [FE3b 评估交接](../../backend-vnext/refactoring/formal/plans/p6-fe3b-backend-assessment-handoff.md)（`229fb33fc6`）、
  [BE-d 前端交接](../../backend-vnext/refactoring/formal/plans/p6-be-d-frontend-handoff.md)、
  [V2 归档界面交接](../../backend-vnext/refactoring/formal/plans/p6-v2-frontend-handoff.md)、DC89、DC90。

## 0. 结论

**前置条件未全部满足。本会话不发出 FE3b 实施提示词。**

- 节点、镜像、缓存与 t1 输入都已就绪，不需要预填充（§4）。
- 后端接口已经交付，kickoff §2.3 表中各行都满足；但合入后的 OpenAPI 与后端规则**超出了 kickoff 的预期**（关闭出口、归档业务核验、`submission_disposition`、退回已删除、tar/PAX consumer 修复），
  按 kickoff §5.2、§10 与本会话任务的规定，属于“与 kickoff 不符”，停下交 owner 转设计会话修订 kickoff（§3）。
- kickoff §3.2 的另一项前置——§6.1 暂定行按后端处理方式定稿——后端已定（DC89、DC90），设计会话尚未定稿（§2）。
- BE-a、BE-d 已在 main 上并获联合后端技术 GO，但**没有阶段退出 tag**，后端写明“实际阶段退出另办”（§1）。是否以此作为 FE3b 的开始条件，交 owner 决定。

缺的条件、负责方与预计时间见 §7。

## 1. 后端合入

| 项 | 事实 | 结论 |
| --- | --- | --- |
| S2a | 附注 tag `p6-s2a-exit`（对象 `ec02169f35`）→ `53b676a629`，在 main 第一父链上；合入提交 `588f4939bb`（merge(p6): integrate reviewed S2a closeout evidence） | 满足 |
| S2b | `p6-s2b-exit`（对象 `6076acbd55`）→ `9220f3cdec`，在 main 上 | 满足（不是 FE3b 的前置，记录备查） |
| BE-a、BE-d | 直接在 main 第一父链上开发，没有分支合并提交，也没有 tag。联合后端技术 GO：独审 `ccdd1eb39d` §25，实施 handoff `233e6f788b`，产品提交 `49403f21aa`（`vnext/` 树 `56720104af`）；owner 已确认 DC33 范围（[联合交接 §13](../../backend-vnext/refactoring/formal/plans/p6-be-a-d-joint-validation-preparation.md#13-owner最终dc33范围确认与交接)） | 代码已在 main；**阶段退出手续未办**（同 §13：“实际阶段退出时的最终 HEAD 闭包/镜像绑定和仓库退出手续……当前没有执行”） |
| 当前 main 的 `vnext/` 树 | `d04f718ccd:vnext` = `49403f21aa:vnext` = `56720104af44a1eb677336f57bdbc07444a56615`；`49403f21aa..main` 没有改动 `vnext/` | 产品树固定 |

kickoff §3.2 的前置写的是“合入 main”，按字面已满足；本会话任务写的是“已退出并合入”。若 owner 要求以退出 tag 为准，FE3b 需等后端办理退出；
若 owner 接受以技术 GO 与固定树为准，建议在提示词中写明：后端退出若改动 `vnext/`，FE3b 须重新合入 main，并按 §3.2 路径核对以最后一次合入的 main 为准。

## 2. 两项后端决定（kickoff §12）

### 2.1 基线已前移后才通过的提交

- **后端已定（DC89，owner 2026-11-07）：** 当前 baseline 下有未关闭的 `PENDING` 时阻塞归档（`ARCHIVE_PENDING_REVIEW`，草稿不阻塞）；新的 `APPROVE` 在写事务中检查当前 baseline，过期返回 409 `BASELINE_VERSION_CONFLICT`；`WITHDRAW`/`REJECT` 保留出口。
  源码：`review_transaction.py:144`，`archive/queries.py:146-147`，`archive/start.py:156`。
- **另加出口（DC90）：** `POST /v1/submissions/{id}/closure`，“有理由关闭、不归档”，只有 `archive_submission` 可用。
- **kickoff 未定稿：** §6.1 表中 `NOT_CANDIDATE_BASE_ADVANCED` 两行仍写“暂定”，§12 仍列为开放项，§6.3 的对应场景未补。
  按 DC89，归档会关闭其余已通过的同级提交，新的过期通过会被拒绝，原文描述的“永久占用”路径已不存在；但 schema 中 `eligibility_note: NOT_CANDIDATE_BASE_ADVANCED` 仍在。
  这一行是删除、改写还是指向关闭出口，由设计会话定。
- **结论：** 后端决定已记录；kickoff §3.2 要求的“§6.1 文案已据此定稿”**未满足**。

### 2.2 tar 成员与 closure 的对应

- **后端结论（DC89、BE-d 交接 §3）：** `manifest.json`、`artifact-closure.json` 在前；之后最终 closure 每个条目按顺序对应一个普通文件；共享由 assembler 在 closure 中表达，下载层不按 `source_ref`/hash 去重，不用 hardlink/symlink。
- **与 kickoff §2.3 最后一行的前端要求比较：** 一致。
- **但出现了 kickoff 没有预期的 consumer 修复项**（BE-d 交接 §1–§2）：
  - PAX 记录按 UTF-8 字节解析（现 `posix-tar.ts::parsePaxPath` 按字符切片）；
  - 支持标准 PAX `size` 覆盖 ustar size 字段（现只读八进制 header）；
  - 前端 `PAX_LIMIT=1MiB` 与后端合法路径域的对齐，需设计会话给出资源策略；
  - 用后端交付的同一个生产 tar（24576 字节，SHA256 `b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`，开发主机副本已核 SHA）在专用节点上证明解析、摘要与 OPFS 安装；失败时中止 OPFS 事务。
- **结论：** 对应关系满足；新增的 consumer 范围要进 kickoff（§3）。

## 3. 接口逐项核对

对象：当前联合候选的生产 OpenAPI（`/home/dev/gdds-reviews/artifacts/p6-be-ad-final-04-copy-mop1T4t8/p6-be-ad-final-04/resume-a-5OBTboKj/new-authority-compose-53h3ekqp/production-openapi.json`，
SHA256 `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`，已核），以及 main 上的后端源码。前端快照 `frontend/openapi.json` 仍是 `a2fb4a027a` 的版本（SHA256 `a7d9b409…be337`）。

### 3.1 kickoff §2.3 各行

| §2.3 行 | OpenAPI / 源码 | 结论 |
| --- | --- | --- |
| `active_submission_id` | `WorkspaceResponse` 中 required、`string \| null` | 满足 |
| `active_submit_attempt_id` | 同上；`GET .../submit-attempts/{id}` 存在 | 满足 |
| 本人读取审核状态 | `withdraw_own_submission`（`application/submission/review.py:38`）；无 `review_submission` 时只能读本人提交（`:51-54`） | 满足 |
| 撤回的预期版本 | `ApplyReviewRequest.expected_review_version`；`ReviewFactsResponse.review_version` required | 满足 |
| 无权限 403、他人/跨 scope/不存在 404 | `GET .../review`：403 `SCOPE_FORBIDDEN`，404 `RESOURCE_NOT_FOUND` | 满足 |
| 撤回后可重新上传 | 由 BE-a 规则保证，OpenAPI 无对应字段；真实 e2e 中验证 | 满足（待 e2e） |
| 201/200、202/200 | `POST /v1/workspaces` 201 + 200 “Existing workspace”；`POST /v1/history-compares` 202 + 200 | 满足 |
| `RETURN_FOR_REVISION` 删除 | OpenAPI 与源码中都没有 `RETURN_FOR_REVISION`/`RETURNED_FOR_REVISION`；`action` 枚举为 `APPROVE`、`REJECT`、`WITHDRAW` | 满足 |
| 整包 tar 与头前错误码 | 两个 bundle 路由 200 为 `application/x-tar`，带 `Content-Length`、`ETag`、`Content-Disposition`。Preview：404 `RESOURCE_NOT_FOUND`，503 `SERVICE_NOT_READY, BUNDLE_INTEGRITY_FAILURE`；History：404 `RESOURCE_NOT_FOUND, ARTIFACT_UNAVAILABLE`，503 `BUNDLE_INTEGRITY_FAILURE` | 满足（成员对应见 §2.2） |

### 3.2 kickoff 没有预期的变化

与前端快照相比（程序比对）：

- **新增路由：** `POST /v1/submissions/{submission_id}/closure`（201/200，403/404/409/413/422/429/503）。
- **新增 schema 21 个：** `CloseSubmissionRequest/Response`、`SubmissionClosureSummaryResponse`、`SubmissionDispositionResponse`，以及归档业务核验与异常 subject 相关的 17 个（`ArchiveBusinessValidationResponse`、`ArchiveBusinessIssueResponse`、`ArchiveSourceIssueDetailsResponse` 等 closed union）。
- **删除：** `ArchiveDispositionResponse`；History 节点的 `archive_disposition` 改为 `submission_disposition`，并新增 `disposition_source_kind`、`disposition_result_id`、`closure`。
- **改动的 schema 14 个：** 包括 `ReviewFactsResponse`（新增 required-nullable `submission_disposition`）、`ArchiveCandidatesResponse`（新增 required `pending_submission_ids`、`pending_submission_count`）、`StartArchiveRequest`（`confirmation_refs` 上限 1，`anomaly_resolution_refs` 上限 1601）、`AppendArchiveAnomalyResolutionRequest`、`ArchivePreviewAnomalyResponse`、`PreviewArchivePlanResponse`、`HistoryNodeResponse`、`WorkspaceResponse` 等。
- **错误码：** `POST .../review-events` 的 409 新增 `BASELINE_VERSION_CONFLICT`、`ARCHIVE_CLOSED`；`POST /v1/archives` 的 409 含 `ARCHIVE_PENDING_REVIEW`。

### 3.3 对 kickoff 的影响（交设计会话）

以下是本会话看到的不符之处，供设计会话修订时逐项处理；不在本报告中给出设计结论。

| kickoff 位置 | 不符 |
| --- | --- |
| §1、§3.2 FE3b 一行、§13.3 | 范围只有“快照＋撤回＋旅程＋t1”。后端交付另含：归档业务核验的显示与逐项接受/撤销（3 个新 action，按 `subject_digest` 区分的独立项）、有理由关闭出口、Review/History 的终局处置显示、tar/PAX consumer 修复与同制品 OPFS 互通。后端建议拆成五个交付块（评估交接 §6 末段），FE3b 是否再拆子阶段由设计会话与 owner 定 |
| §2.1、§2.2 | 仍是 2026-11-05 的事实（S2a 未退出；05 缺依赖镜像；BE-a/BE-d 未实施） |
| §2.3 | 未覆盖 §3.2 的变化；最后一行的“有前提”已由 DC89 消除，但 consumer 修复项要补 |
| §4.6 “留给 FE3b” | D 的 `DIFFERENT_PROJECT` 与 C 的变化在归档后可能触发新的来源/时间异常，归档时需要逐项接受；序列与判据需要据此写明 |
| §4.7 R6 | 依赖“退回（必填理由）”，该动作已删除；需改为 REJECT→重提，并另覆盖关闭出口 |
| §4.7 R8 | 只写“异常处理（若有）”；新增三类异常、引用上限、同码不同 subject 的独立接受、`ARCHIVE_PENDING_REVIEW`、过期 APPROVE 409 都没有场景 |
| §5.3 | 同步规则未包括 `archive_disposition` 改名、`submission_disposition`、新异常 union 与关闭响应的模拟数据 |
| §6.1、§6.3 | 暂定行未定稿（§2.1）；“该提交已退回”的说法与 REJECT 的文案关系需确认 |
| §6.2、§7 n3 | 后端交接 §3 要求“查询失败、operation 终态都不等于占用释放”，而 FE3a 审核 B7 让续做读取失败后恢复 FE2c 的行为（提交按钮恢复可用）。删除 `sessionStorage` 标记、改为基于指针后，两者需由设计会话统一 |
| §8.2 | t1 只有 MODIFIED_ONLY；后端建议浏览器 t1 覆盖 FULL 双 pair、历史比较与异常出口，且 t1 归档可能遇到真实来源/时间异常 |
| §12 | 两个开放项的状态需更新 |

## 4. 节点与镜像

| 项 | 需要 | 04 | 05 | 07 | 结论 |
| --- | --- | --- | --- | --- | --- |
| backend 依赖镜像 | `--print-input`（main `d04f718ccd`）得 `gateway-backend-deps:lock-d054366c02fa`，输入 `d054366c02fa2a28…57aad` | 有；label 一致；config `sha256:b5b54224…e4b92a`；19 个 DiffID 与开发主机相同 | 同 04 | 无（07 不跑真实 backend，不需要） | 就绪 |
| RS 依赖镜像 | `repository_service/uv.lock` SHA256 `6dc9659f0aee…` → `gateway-p2r1-repository:lock-6dc9659f0aee` | 有；label 一致；config `sha256:98d0801b…ad9ec9`；16 个 DiffID 相同 | 同 04 | 同 04 | 就绪 |
| 前端工具链 | `mcr.microsoft.com/playwright:v1.64.1-noble`，config `sha256:a0d7b2b4…a1017` | 7 个 DiffID 相同 | 同 | 同 | 就绪 |
| npm 缓存 | `package-lock.json` 自 `d62eb36037`（FE0）未变 | 归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` SHA256 `0d861824…0089f4` | `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，同 SHA | `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，同 SHA | 就绪；仍是 FE3a 的那一份 |
| t1 组态目录 | FE3a handoff §4.1 | — | `source-dirs/t1-v1`、`t1-v2`：清单 SHA256 分别为 `cdb598cd…0163`、`fa2450fa…a96a`，与 handoff 相同；在各目录内 `sha256sum -c` 19/19 通过；文件数与字节数 19/6,853,875、19/6,854,427；`dbcfg.sql`、`logics.xml` 的 SHA256 与 handoff 相同 | — | 就绪 |
| 占用标记 | — | 无 | 无 | 无 | 核对时空闲 |

- 方法：开发主机是经典 image store，`docker image inspect` 的 ID 即 config digest；节点是 containerd store，用 `ctr -n moby content get <manifest>` 读出 manifest 的 `config.digest`。DiffID 比较 `RootFS.Layers` 全文。
- 镜像与 FE3a 不同：FE3a 用 `lock-c668cef8e47e`；main 合入 S2a 后需要 `lock-d054366c02fa`，两节点已有（kickoff §4.3 的预计成立）。上传包校验脚本 `validate-upload-package.sh` 默认就是 `lock-d054366c02fa`，FE3a 时的两项 record-only 差异在当前 main 上预计消失。
- **不需要 DC67 预填充。**
- 操作记录：第一次 t1 清单核对在 `source-dirs/` 下运行 `sha256sum -c`，清单中的相对路径无法解析而全部报“无法读取”。这是本会话命令的工作目录错误，只读、无副作用；改为在各目录内运行后 19/19 通过。不是证据运行。
- t1 预期值：当前 `vnext/backend/benchmarks/real_dump_journey.py` 中 `S2B_DATASET_BASELINE`、`S1B_V2_PREVIEW_CHANGED_COUNTS` 可用 `ast.literal_eval` 读取（t1 v1/v2 `preview_table_count` 均为 124，v2 changed 为 4），与 kickoff §8.3 一致。

## 5. 推送状态

- 远端 `main` 在 `2c79d0947f`（FE2c 退出记录）。本地 main `d04f718ccd` 领先 817 个提交，可快进。
- 未推送：`fe-fe3a-exit` tag、合入提交 `86fa2e4e8a`、退出记录 `53403631bc`、`fe-vnext` 分支，以及 `p6-s2a-exit`、`p6-s2b-exit` 和 BE-a/BE-d 的全部提交。
- 不影响 FE3b 开始；推送需 owner 授权。

## 6. FE3a 带入 FE3b 的事项（写进将来的提示词）

kickoff 修订后若有变化，以修订后的文本为准。

1. **§4.6 留给 FE3b 的项：**
   - B 的 FULL：基线 → ① 比较对 `changed_table_count = 0`（不为 0 停下交设计会话），① → ② 比较对 ≥ 1；
   - C 相对 B 有变化；D 的身份对为 `DIFFERENT_PROJECT`；
   - A、B、C、D 的提交都不返回 `NO_CANONICAL_CHANGE`；
   - FULL 按复审第 1 轮 R2 断言上传方式：恰好两个比较对 0→1 与 1→2，点击上传前等到页面显示“原始备份 + 本次归档”。
2. **M1 复测（§8.4，Q12）：** t1 v1、v2 用生产构建复测；打包期间约每 100 ms 采样各进程 `RssAnon`、`RssFile`、`RssShmem` 并报告最大值；`VmHWM` 方法不变；只有 renderer 不满足标准时才改流式。
3. **会话文件与 n3：** 本人撤回身份补 `withdraw_own_submission`；删除 `gateway-submit-operation` 标记后，n3 用例改为基于指针，覆盖不减（与 §3.3 中 B7 的统一结论一并执行）。
4. **复审第 1 轮非阻塞项：**
   - N1：为 `e2e*/` 加 tsconfig 并纳入类型检查；
   - N2：按 BE-d 的 tar 格式记录 bundle 标识（FE3a 改记 Preview 的 `bundle_digest`）；
   - N5：换成 tar 后，各输入 scope 等页面进入差异浏览再断言 `pageErrors`；
   - N8：`--color-warning-soft` 未定义，“需要管理员处理”为灰底；如需改黄色，属设计令牌，由设计会话决定是否纳入。
5. **运行框架：** `--suite journeys`、`--suite t1`、`--input-root` 目前以 exit 2 拒绝，FE3b 实现；FE3a 旧 smoke 以出现“下载比较结果失败”为判据，换成 tar 后要删除该临时判据（后端交接 §6）。
6. **04 退出条件包含上传包后端校验（kickoff §3.2）。** FE3a handoff 漏记这一项，由审核会话补跑。提示词逐项列出 04 的三次运行：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys`。
7. **FE3a handoff 勘误**（证据核对 §3）在 FE3b handoff 中不再沿用错误说法。
8. **来自 main 的前端改动：** main 上 `55d56efb6e`（06/07 节点就绪时加入 `GATEWAY_FE_TEST_WORKERS`，只改 `frontend/scripts/run-tests.sh`）不经 `fe-vnext` 进入 main，合入后会出现在 FE3b 的审核范围中。kickoff §3.2 只把来自 main 的文档与 `vnext/` 排除在前端审核之外，这一处 `frontend/` 改动由 FE3b 审核一并核对。
9. **节点分工更新（AGENTS 2026-11-06/07）：** 类型检查、lint、单测、构建、截图与模拟接口 e2e 优先在 07（`GATEWAY_FE_TEST_WORKERS=2`）；真实 backend 调试与 t1 在 05；最终取证在 04。kickoff §4.2、§9 只写了 04/05，修订时同步。
10. **治理：** FE3a handoff §8 给 AGENTS 与 testing-conventions 的真实 e2e 条文尚未写入（两文件中都没有 `run-real-backend-e2e`），仍待 owner 转治理会话；不阻塞 FE3b。

## 7. 还差的条件

| # | 条件 | 负责 | 预计 |
| --- | --- | --- | --- |
| 1 | FE3 kickoff 修订：吸收 §3.2 的接口变化与 §3.3 各项，定稿 §6.1 暂定行，更新 §2、§4.6、§4.7（R6、R8）、§5.3、§8、§12、§13.3；决定是否把 FE3b 再拆子阶段。输入：后端 FE3b 评估交接、BE-d 与 V2 前端交接、本报告 | 前端设计会话（owner 转发） | 修订约 1 天；新增界面范围较大，按以往惯例还需 kickoff 审核与复审，合计约 1–2 天 |
| 2 | 修订中需要 owner 拍板的事项（例如子阶段拆分、R6 替代方案、§6.2/n3 的读取失败行为） | owner | 随 #1 |
| 3 | 是否要求 BE-a、BE-d 先办阶段退出（§1） | owner 决定；办理由后端协调者 | 不要求则无等待；要求则以后端安排为准 |
| 4 | 修订后的 kickoff 经 owner 确认，再由本会话核对一次 §3 与 §6，然后发出提示词 | 本会话 | #1–#3 完成后当天 |

节点、镜像、缓存与 t1 输入（§4）不在等待项中；发出提示词前本会话再现场核对一次占用标记与镜像。
