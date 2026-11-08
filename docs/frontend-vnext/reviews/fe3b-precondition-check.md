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

## 8. 对 kickoff 修订的建议（owner 2026-11-07 同意修订后补充）

本节是审核会话的建议，供设计会话修订时参考；设计结论由设计会话给出，需要拍板的由 owner 决定。
下列后端行为来自源码阅读，未运行产品；标“待实测”的项在 FE3b 05 调试首轮确认。

### 8.1 发现的设计冲突

1. **合成输入没有生成时间，A 之后的每次归档都要先逐项接受异常。**
   - 事实：`frontend/e2e-real/fixtures/upload-inputs/` 三份 SQL 与 `sql-replacement-current.sql` 的 `version_manager` 只有 `project_id, build, no`，没有 `saved_time`。
     t1 两个真实目录有 `saved_time`（`2026-04-17 14:58:10` 等）。
   - 后端（`application/archive/business_validation.py`）：baseline 为空 INITIAL 时不做时间质量检查；baseline 有内容后，候选一侧选不出时间即 `GENERATION_TIME_MISSING`（`CONFIGURATION_TIME_QUALITY`），
     baseline 选不出时间即 `BASELINE_TIME_UNAVAILABLE`。DC90 规定这些异常须由 `archive_submission` 持有人逐项填理由接受后才能归档。
   - 推断（待实测）：归档 A 不出时间异常；归档 B（FULL）会出 INITIAL、MODIFIED 两侧各一项 `GENERATION_TIME_MISSING`，外加 `BASELINE_TIME_UNAVAILABLE`；C、D 同理。
   - 影响：kickoff §4.6 的 A→B→C 序列与 R8 离不开逐项接受界面；kickoff 目前没有这个界面。
   - 建议：**不改输入。** 缺生成时间正好产生“同码、同目标、不同 `subject_digest`”的两侧独立项（后端要求重点覆盖），可作为该场景的来源。
     Q10 的派生规则只为“backend 接受上传”补列，补 `saved_time` 会改变这一规则的含义。kickoff 写明每步的预期异常清单，在 05 调试首轮按实际 preview 结果校正；与推断不符时停下交设计会话。
2. **`NOT_CANDIDATE_BASE_ADVANCED` 不再表示“卡住”。**
   - 事实：`application/history/projection.py:210-218` 对所有“`APPROVED` 且所基于的 baseline 不是当前 head”的提交返回该标记，不看处置；HTTP 层原样映射（`http/schemas/history.py:109-113`）。
     所以已归档的 A、归档时被关闭的同级提交、手工关闭的提交都会带这个标记。
   - DC89 之后，过期的 `APPROVE` 被拒绝，归档会关闭其余已通过的同级提交，还有手工关闭出口，“已通过、基线已前移、仍占用工作区”的路径已不可达。
   - 建议：删除 §6.1 两张表中的两行暂定内容；组态树、审核顶栏按 `submission_disposition` 优先显示（“已归档”“已关闭（未归档）”＋关闭人、时间、理由）；
     该标记只在 `submission_disposition` 为空时显示。另经 owner 向后端澄清“有处置时该标记是否应为 null”，不阻塞修订。
3. **n3（FE3a 审核 B7）与“指针为准”：不构成冲突，规则需写清。**
   - B7 反对的是“提示说失败、按钮却仍写‘确认中’”；后端要求的是“读取失败、operation 终态都不等于占用已释放”。
   - 建议规则：续做得到 `ABORTED` 或读取失败后，先重新读取工作区，“提交”按 §6.1 的指针表决定；工作区也读不到时保持禁用，原因写“无法确认提交状态”，并附“重试”。
     这样提示与禁用原因一致（满足 B7），也不在指针未清时解锁（满足后端）。n3 的模拟用例按此改为基于指针。

### 8.2 阶段拆分（需 owner 决定）

- **建议：拆成两段。**
  - **FE3b 契约与基础：** §5 快照刷新与旧路径清理（退回、201/202 变通、`archive_disposition`→`submission_disposition`）；Review/History 的终局处置**只读显示**；§6 撤回、占用禁用与 §6.2 指针恢复（含 n3）；
    tar/PAX consumer 修复与同字节 tar（`b08a310c…`）的 OPFS 互通证据；真实旅程 R1–R7、R10、R11，R9 只做两节点（不需要归档）。tag `fe-fe3b-exit`。
  - **FE3c 归档核验与完整旅程：** 归档业务核验显示与逐项接受/撤销、关闭出口、`ARCHIVE_PENDING_REVIEW` 与过期 `APPROVE` 409 的界面；R8、R9 三节点、A–D 序列与 §4.6 留给 FE3b 的各项；t1 旅程与 M1 复测；FE3 退出。tag `fe-fe3c-exit`，FE4 从它开始。
- **理由：**
  - 归档核验与关闭是新界面，要先出草图或文字规格并经 kickoff 审核，是修订中最费时的部分。FE3b 只需较小的修订即可开始，不等这部分设计；
  - 同字节 tar 互通是后端写明的“FE3 依赖解除”条件，可以先做完；
  - 由 §8.1 第 1 项，A 之后的归档都要接受异常，归档相关旅程放进同一段，边界清楚；
  - 每段审核面更集中。
- **代价：** 多一次审核与 04 取证。
- **不拆的做法：** 一段完成，审核与取证各一次，但要等全部设计（含新界面草图）完成才能开始。

### 8.3 其他修订项

| kickoff 位置 | 建议 |
| --- | --- |
| §2.1、§2.2、§2.3 | 按本报告 §1–§4 更新事实；§2.3 补关闭、业务核验、`submission_disposition`、`pending_submission_ids`、引用上限 1/1601、review-events 409 新增码、PAX consumer 修复各行 |
| §4.7 R6 | 改为：审核人 REJECT（必填理由）→ 指针清空 → 重新上传同一输入 → 提交 → 通过；审核顶栏撤回回归不变 |
| 新增关闭旅程（FE3c） | 归档确认人对已通过提交关闭（必填理由）→ 断言 201、重放 200 显示首次操作者；提交人工作区释放、baseline 不动；Review 显示 `APPROVED` ＋“已关闭（未归档）”；提交人重新上传、预览、提交 → 通过 → 归档 |
| 关闭入口 | 只对 `archive_submission` 显示。建议放在归档主线对话框中候选与阻塞处，不放在提交人顶栏；位置与样式需草图或文字规格 |
| R8（FE3c） | 覆盖：待审核阻塞（`ARCHIVE_PENDING_REVIEW`，显示待审核提交，草稿不阻塞）；过期 `APPROVE` 409 的提示与刷新；三类新异常的显示（原始状态与处理状态分开，接受后不显示为通过）；两侧独立项分别接受、撤销其一后归档被拒；引用不分页、不截断 |
| §5.3 | 补：closed union 与关闭响应的模拟数据按 OpenAPI 类型；`submission_disposition` 两个位置；新错误码的文案与取值核对；删除 `client.ts::safeReviewStatus/safeReviewEvent` 的退回映射 |
| §6.1 | 删除暂定行（§8.1 第 2 项）；“该提交已退回”一行对照 REJECT 的界面用词确认 |
| §8 t1（FE3c） | 建议第 4 步改为 FULL（① = t1 v1 目录，② = t1 v2 目录），按 `pair_id` 核对 baseline→① `changed_table_count = 0`、①→② 与 §8.3 的 v2 预期值相同；覆盖后端建议的“FULL 双 pair”。归档 v1 时出现业务核验异常则走接受界面并在 handoff 列出（预计不会：baseline 为空 INITIAL） |
| tar/PAX | `PAX_LIMIT` 按 Contract 中合法 `logical_path` 的最大字节数确定，不取消上限；该数值需经 owner 向后端取得 |
| §4.2、§9 | 模拟接口各项优先 07（`GATEWAY_FE_TEST_WORKERS=2`）；真实 backend 调试与 t1 在 05；取证在 04。截图清单补：业务核验面板（含两侧独立项）、接受与撤销对话框、关闭对话框、终局处置显示、待审核阻塞提示 |
| §13.3 | 带入本报告 §6 的清单；写明起点合入的是**含后端退出结果**的 main |

### 8.4 阻塞项

- **不阻塞修订开始：**
  - BE-a、BE-d 的退出由后端并行办理。办完后本会话核对退出 tag、合入提交和 `vnext/` 树：树仍为 `56720104af` 时本报告 §3、§4 的结论不变；改变时重新核对接口和依赖镜像输入。
  - 后端两项澄清：PAX 路径的最大字节数；有处置时 `NOT_CANDIDATE_BASE_ADVANCED` 的语义。前者在 tar 修复定稿前要有答案。
- **需要 owner：** 是否拆段（§8.2）。
- **最费时：** 归档核验与关闭界面的设计（草图或文字规格）及其 kickoff 审核。
- **发出提示词的前提：** 修订后的 kickoff 经 owner 确认；BE-a、BE-d 退出已汇报（或 owner 豁免）；本会话再现场核对一次接口、镜像与占用。

## 9. 后续核对（2026-11-07，BE-a/BE-d 退出与后端澄清之后）

- **BE-a/BE-d 退出：** 合并为一个附注 tag `p6-be-a-d-exit`（对象 `66b9083941`）→ `77b9aeea74`，在 main 第一父链上；产品 `49403f21aa`，`vnext/` 树仍为 `56720104af`，退出 handoff `9ee1f47b32`。
  §1 中“阶段退出手续未办”已解决；树未变，§3、§4 的结论不变（依赖镜像仍为 `lock-d054366c02fa`）。
- **后端澄清**（`20d3b885f6`，只改文档，产品与 tag 未变；见 [BE-d 前端交接 §2.1](../../backend-vnext/refactoring/formal/plans/p6-be-d-frontend-handoff.md)）：
  - 单个 `logical_path` 的 UTF-8 接收上界 8,388,608 字节（8 MiB），按字节计，不按 JS `length`；后端没有独立的路径长度常量，这是由 manifest/closure 各 16 MiB 推出的保守预算，不保证可达；
  - 单个局部 PAX payload 上限 16,777,216 字节（16 MiB），不含 512 字节 header 与 padding；先按 header 声明的大小检查，再分配读取；
  - manifest、closure 仍各 16 MiB（前端 `METADATA_LIMIT` 已是该值）；
  - 已处置的提交仍可带 `NOT_CANDIDATE_BASE_ADVANCED`，只作历史说明；终局状态看 `submission_disposition`，占用看工作区指针。与 §8.1 第 2 项的建议一致。
- **§8.4 中两项后端澄清已关闭。** 修订 kickoff 不再缺后端信息；剩余的只有 owner 对 §8.2 拆段的决定（若尚未明确）与设计会话的修订本身。

## 10. FE3b 实施提示词草案（owner 2026-11-07 同意拆段）

- **状态：** 审核会话起草。设计会话修订 kickoff 时并入 §13.3，并写 FE3c 的提示词；修订后的 kickoff 与本草案不一致时，以 kickoff 为准，本会话发出前对齐。
- **发出前提：** 修订后的 kickoff 经 owner 确认；本会话现场再核对一次接口、镜像与节点占用；填好方括号中的值。

> 你是 FE3b 前端实施会话。FE3 已拆成 FE3b（契约与基础）与 FE3c（归档核验与完整旅程），本阶段只做 FE3b。
>
> **先读：**
> - AGENTS：“专用测试节点”“前端测试（FD7）”“Docker / Compose 验证”；testing-conventions“前端测试”；
> - 前端 kickoff §4.3、§4.4、§7.1；FE2 kickoff §7.5；
> - FE3 kickoff（main `[kickoff 确认提交]`）全文，重点 §3.2 FE3b 一行、§4、§5、§6、§10、§13.3；
> - FE3a handoff 与 `reviews/fe3a-*.md`；
> - `reviews/fe3b-precondition-check.md` 的 §3、§6、§8、§9；
> - 后端：[FE3b 评估交接](../../backend-vnext/refactoring/formal/plans/p6-fe3b-backend-assessment-handoff.md)、[BE-d 前端交接](../../backend-vnext/refactoring/formal/plans/p6-be-d-frontend-handoff.md)（含 §2.1 接收预算）、[V2 交接](../../backend-vnext/refactoring/formal/plans/p6-v2-frontend-handoff.md) §3、[BE-a 交接](../../backend-vnext/refactoring/formal/plans/p6-be-a1-handoff.md)。
>
> **后端事实（已核对，不需要再等后端）：**
> - `p6-s2a-exit` → `53b676a629`；`p6-be-a-d-exit` → `77b9aeea74`（产品 `49403f21aa`）；当前 main 的 `vnext/` 树 `56720104af`；
> - 生产 OpenAPI 原件 SHA256 `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`（路径见 FE3b 评估交接 §2）；
> - 依赖镜像 `gateway-backend-deps:lock-d054366c02fa`、RS 依赖镜像 `gateway-p2r1-repository:lock-6dc9659f0aee`、工具链镜像在 04、05 上身份一致（config digest 与全部 DiffID）；npm 缓存归档 SHA256 `0d861824…0089f4`（来源提交 `a2fb4a027a`）在 04、05、07 上。不需要预填充。
>
> **起点与分支：**
> - `fe-vnext` 在 `fe-fe3a-exit`（→ `0e7caf66f4`），开发主机 worktree `/home/dev/gdds-fe`；
> - 先把 main `[合入用 main 提交]` 以 `--no-ff` 合入 `fe-vnext`，不 rebase；合并会带入 main 上的前端提交 `55d56efb6e`（`GATEWAY_FE_TEST_WORKERS`），保留；
> - 合并后按 kickoff §3.2 做路径核对：候选的 `vnext/` 树等于所合入 main 的 `vnext/` 树（预期 `56720104af`）；相对该 main 的差异只含 `frontend/` 与 `docs/frontend-vnext/`；
> - 合并后的 HEAD 上 `build-backend-dependency-base.sh --print-input` 必须仍得 `lock-d054366c02fa`，否则停止。
>
> **范围（FE3b）：**
> 1. **快照与清理（kickoff §5）：**
>    - 用真实 backend 起栈取 `/openapi.json`，按 §5.1 规范化写入 `frontend/openapi.json` 并重新生成类型，同一提交；记录与原件 `977b2258…` 规范化后是否逐字节相同，不同即停止；
>    - 删除退回动作的全部路径：`client.ts::safeReviewStatus/safeReviewEvent` 的映射、`ComparisonPage.tsx`、`view-model/workspace.ts` 中的状态与文案、模拟数据与用例；
>    - 删除 201/202 的类型变通；`archive_disposition` 直接改为 `submission_disposition`，不双读；
>    - 模拟数据按新生成类型，`WorkspaceResponse` 补两个指针（至多一个非空，符合 BE-a 生命周期表，含“operation 终态而 attempt 未结束”）；错误码单测解析新快照；`check-production-build.mjs` 覆盖新增模拟 token。
> 2. **终局处置只读显示：** 组态树与审核页把审核状态与 `submission_disposition` 分开显示，处置优先于 `NOT_CANDIDATE_BASE_ADVANCED`（该标记只作历史说明）；`MANUAL_CLOSE` 的 `result_id` 为 null 仍是已关闭。文案按修订后的 kickoff。不做关闭操作入口（FE3c）。
> 3. **上传模式撤回与占用（kickoff §6）：**
>    - 按修订后的 §6.1 表（暂定行已删除）实现撤回按钮与“提交”“上传”的禁用原因；撤回带 `review_version`；不按 actor 或指针推断可撤回；冲突后重新读取，不自动重发；
>    - §6.2：按 `active_submit_attempt_id` 与 `job_kind` 恢复，删除 `gateway-submit-operation` 标记；续做读取失败或 `ABORTED` 后先重读工作区，按指针决定“提交”；工作区也读不到时保持禁用并给“重试”（核对报告 §8.1 第 3 项，以修订后的 kickoff 为准）；n3 用例改为基于指针，覆盖不减；
>    - §6.3 W1–W8：模拟接口全部覆盖；真实 e2e 覆盖 W1–W5、W7、W8，W6 只在模拟接口。
> 4. **tar 与 OPFS：**
>    - `posix-tar.ts`：PAX 记录在 `Uint8Array` 中按 UTF-8 字节解析（长度前缀位数进入固定点），严格解码 key/value；支持标准 PAX `size` 覆盖 header 中的八进制 size，校验十进制与安全整数范围；
>    - 接收预算：单个路径 UTF-8 不超过 8,388,608 字节，单个局部 PAX payload 不超过 16,777,216 字节（不含 header 与 padding），先按声明大小检查再分配；manifest、closure 仍各 16 MiB；
>    - 路径安全、重复成员、closure 顺序与逐成员摘要校验保留；截断、流错误或摘要不符时中止 OPFS 安装，不提交半包，不显示为“无差异”；
>    - **同字节互通：** 把后端交付的 `bundle.tar`（24,576 字节，SHA256 `b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`）与 `pax-records.json`、`size-vectors.json` 及其 header-only 向量原样提交为前端 fixture（文件来源见 BE-d 前端交接 §3），测试先断言 SHA256；用它在浏览器中验证解析、全部摘要与 OPFS 安装（模拟接口 e2e），并有单测覆盖 PAX 字节边界、99→101 位数边界、中文与非 BMP、size 边界与超预算拒绝。不得自造替代 fixture，不生成大文件。
> 5. **真实 backend 旅程（`--suite journeys`，kickoff §4.7 中属于 FE3b 的部分）：**
>    - R1；R2（MODIFIED_ONLY 与 FULL，下载 tar 核 `Content-Length`、`ETag` 与逐成员摘要，进入差异浏览，同一 context 再次打开不重新下载）；R3；R4 的提交到 `PENDING`（身份确认留 FE3c）；R5；
>      R6 改为：审核人 REJECT（必填理由）→ 指针清空 → 重新上传 → 提交 → 通过，另回归审核顶栏撤回；R7；R9 只做两节点；R10 四项；R11；
>    - 身份按 kickoff §4.6，“提交人（本人撤回）”带 `withdraw_own_submission`、不带 `review_submission`；本人撤回不用审核人或全权限身份代替；保留无权限身份的 403；
>    - 删除 FE3a smoke 中以“下载比较结果失败”为判据的临时断言；各输入 scope 进入差异浏览后再断言 `pageErrors`（FE3a 复审 N5）。
> 6. **FE3a 带入：** 为 `e2e*/` 加 tsconfig 并纳入类型检查（N1）；按 tar 的 `ETag`/bundle 摘要记录 bundle 标识（N2）。
>
> **不做（FE3c）：** 归档业务核验显示、逐项接受与撤销、关闭出口、待审核阻塞与过期通过的界面、R8、R9 三节点、A–D 序列与 kickoff §4.6 留给后续的各项、t1 旅程、M1 复测。不改 `vnext/`；不在浏览器中重算 SQL、来源或时间。
>
> **节点：**
> - 类型检查、lint、单测、构建、截图、模拟接口 e2e 在 07，设置 `GATEWAY_FE_TEST_WORKERS=2`，不获取占用标记；
> - 真实 backend e2e 与上传包校验在 05，由脚本按 kickoff §4.2 获取占用（会话名 `fe3b-impl`）与 `flock -n`，结束后清理并释放；
> - 某节点占用标记的用途为计时测量时，前端在该节点上的任何运行都等待；
> - 不在 04 上运行，04 取证在审核通过后进行；
> - 05、07 上运行时按 kickoff §2.2 设置 npm 缓存的三个环境变量；源码经 git bundle 传到节点，在 clean、已提交的 detached worktree 中运行，日志与截图写在 worktree 外。
>
> **停止条件：** kickoff §10，以及：
> - 合入后的接口、运行时 OpenAPI 与修订后的 kickoff 或核对报告 §3 不符；
> - 真实 e2e 发现后端缺陷或后端不接受输入：保留日志与 trace，交设计会话与后端，不在前端绕过；
> - 需要后端新增字段或接口；依赖镜像、RS 依赖镜像、工具链或 npm 缓存缺失或身份不符，或构建需要访问网络；需要修改 `vnext/`；清理核对失败；
> - 脚本自身的错误按 DC68 重做一次，重做再失败即停止；被测对象运行后的失败不按 DC68 重做。
>
> **交付：** 07 上 `run-tests.sh --e2e --screenshots`、05 上 `--suite journeys` 与 `validate-upload-package.sh` 各一次通过（均为调试运行）后，提交代码候选与 handoff `docs/frontend-vnext/fe3b-handoff.md`，内容包括：
> - 合并提交、所合入的 main 与 `vnext/` 树、路径核对结果；
> - 快照来源与比对结果；清理清单（删除的退回路径与类型变通）；
> - W1–W8 与用例的对应；旅程各项结果，只由模拟接口覆盖的项及原因；每个 scope 的上传序列；
> - tar 修复与同字节互通：fixture 的 SHA256、用例名、运行节点与日志 SHA256；预算边界用例；
> - 截图清单（1280 与 1920）：§6 各状态（撤回可用、§6.1 每种禁用）、撤回对话框、冲突提示、撤回成功后的上传步骤卡、W8、终局处置显示、快照刷新后有变化的页面；
> - 每次运行的节点、hostname、起止时间、起止 HEAD、exit code、日志 SHA256；工具链（config digest 与全部 DiffID）、npm 缓存（来源提交、归档 SHA256）、依赖镜像（tag、label、config digest、全部 DiffID）与 RS 镜像身份；
> - 偏差与未决事项。
>
> 不推送。
>
> **审核通过后的 04 取证（由审核会话指明）：** 在 04 的 clean、已提交 detached worktree 上各运行一次：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys`。
