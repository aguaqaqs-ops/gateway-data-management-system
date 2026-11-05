# FE3 kickoff 定向复审（第 1 轮）

- **对象：** main 本地提交 `de9cd5cb6f`（`docs/frontend-vnext/fe3-kickoff.md` 修订 1）相对 `5c360bfb1b` 的改动。
  该提交只改这一个文件；`vnext/` 树仍为 `2791d3ff3d`。
- **依据：** [kickoff 审核](fe3-kickoff-review.md)（`920f068da4`）；BE-a 设计补充（`f20f08bea9`）；源码（只读）。
- **范围：**
  - B1–B4；
  - 审核报告中标注“建议随本次修订”的 N1、N2、N3、N7、N13；
  - 新增的 §6.1“工作区被占用时的提交与上传”、W8、§11 Q9；
  - 修订是否引入新的矛盾。

  其余 N 条只抽查 §15 所列位置是否属实。
- **方法：** 在只读 worktree `/home/dev/gdds-p6-logs/fe3-kickoff-review-wt` 中检出 `de9cd5cb6f`。本轮只读开发主机上的文档与源码，没有访问 04、05，也没有访问 ct108。
- **日期：** 2026-11-05。
- **结论：通过。**
  - B1–B4 与五条 N 都已按审核意见修订，所引用的源码事实我都核对过，属实。
  - Q9 的建议成立，后端依据比文中写的还多一条（§2.3）。
  - 第 3 节有 4 条小的文字修正，可以在记录 owner 确认时一并改，不需要再复审。
  - 第 4 节有一项后端生命周期缺口，**交设计会话，转后端设计会话**，应在 BE-a 实施前处理。它不阻塞本文的确认。
- **owner 决定的记录：** O1 已由 owner 决定（M1 测完才能退出 FE3a）。§3.2 与 §11 Q8 的写法与该决定一致。

## 1. B1–B4

| 项 | 修订后 | 核对 | 结论 |
| --- | --- | --- | --- |
| B1 t1 通过标准（§8.3） | 读取 bundle manifest 的四个汇总数；预期值用 `python3 -I` 的 `ast.literal_eval` 从同一 vnext 树的 `real_dump_journey.py` 读取 | 用 `ast.parse` 加 `ast.literal_eval` 程序核对：`S2B_DATASET_BASELINE` 只在第 138 行赋值一次，`S1B_V2_PREVIEW_CHANGED_COUNTS` 只在第 180 行赋值一次，都是普通 `Assign`，值是纯字面量（数字中的 `_` 不影响读取）。读出的值：t1 v1、v2 的 `preview_table_count` 都是 124；`rd-t1-a-v2` 的变化表数是 4。v1 “`table_count = changed_table_count = 124 + 1`”与后端第 2737–2741 行一致 | **通过**（`composite_changed` 的说法见 §3 R3） |
| B2 冒烟范围（§3.3） | 归档候选界面移入“要等 BE-d”；403 限于上传与 Preview；写明 Preview 结果的判据 | 两项 403 在当前 backend 上都能走到：上传 403 用无权限身份；Preview 403 用新增的“提交人（无 Preview 权限）”，`UploadStepCard` 先上传再发起 Preview。判据可以由程序断言，下载失败不作断言 | **通过** |
| B3 R10、R5（§4.6、§4.7） | R10 改为四项，新增无 Preview 权限的身份，提交 403 只由模拟接口覆盖；R5 的回放状态码按 route | 四项都能走到；提交 403 只能由模拟接口覆盖，原因写对了；R5 写明提交 202、审核 200，并排除了上传 | **通过** |
| B4 提交失败后的指针（§6.1、§6.2、§5.3） | 按 attempt 状态分支，增加“结果待确认”；URL 中操作的类型按 `job_kind` 判断；写明续做卡片位置；模拟数据补“operation 终态、attempt 未结束”的场景 | 三个分支与 BE-a 设计补充 §2 的生命周期表一致：`FINALIZED` 原子切换为 `active_submission_id`；确认 `ABORTED` 后两个指针都清空；执行、等待恢复或结果未知时保留 attempt 指针，不按 operation 终态推断（`p6-be-a-design.md:33`）。`SubmitAttemptResponse` 含 `operation_id`，`OperationResponse` 含 `job_kind`。工作台续做卡片的位置属实（`WorkbenchPage.tsx` 中 `OperationStatusPanel` 在 `workspace-tree-heading` 之后） | **通过**（Preview 页续做卡片的位置写反了，见 §3 R2；`MANUAL_RECOVERY_REQUIRED` 的归类见 §3 R4） |

## 2. N1、N2、N3、N7、N13，新增的 §6.1 占用规则、W8 与 Q9

### 2.1 五条 N

| 项 | 核对 | 结论 |
| --- | --- | --- |
| N1 05 的 npm 缓存（§2.2、§4.1） | 路径、归档与 SHA256 与上一轮节点核对一致；变量名与 `run-tests.sh` 相同（`GATEWAY_FRONTEND_NPM_CACHE`、`GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE`） | **通过**。可顺带写上 `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT`，否则日志中的来源提交记为 `unknown` |
| N2 tar 前提（§2.1、§2.3、§12） | 前端前提写得准确（`posix-tar.ts` 第 341、398、406、416 行）；已作为 D1 交 BE-d kickoff 审核，并登记在 §12 | **通过** |
| N3 RS 构建（§4.3、§4.4） | 依赖镜像 tag 的算法与 `build-repository-service-image.sh` 一致（`lock-${UV_LOCK_SHA256:0:12}`、label `gateway.p2r1.uv-lock-sha256`）。显式设置 `GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE`、禁网，并且构建前先核对依赖镜像，因此脚本不会走到缓存 URL 分支。所有 `up` 都带 `--no-build`。§4.4 第 3 步写明了 | **通过** |
| N7 工具链容器（§4.2、§4.5、§4.8） | 清理时先删工具链容器；残留检查与清理后核对都包括它。它带有 `com.docker.compose.project` label，所以第 1 步万一失败，`down --remove-orphans` 也会删掉它 | **通过** |
| N13 Python 规范化（§5.1） | 规则为 `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"`。上一轮已程序核对：当前快照按此重排后逐字节不变 | **通过** |

### 2.2 §6.1 占用规则、W8 与 Q9

Q9 引用的两项后端行为都属实，而且后端依据比文中写的还多一条：

- **待审核期间上传：** `review_transaction.py` 调用 `assert_review_workspace_bindings`（`application/submission/review.py:79–103`）。该函数核对工作区的 generation、`current_upload_revision_id`、`current_preview_result_id` 与占用是否都与提交一致，不一致即抛出 `ReviewWorkspaceOccupancyConflict`。
  这项核对对撤回、通过、退回**都适用**。所以待审核时一旦上传，提交人不能撤回，审核人也不能通过或退回。这比 §6.1 只写撤回更有理由禁用上传，可以在 §6.1 补上一句。
- **已通过后上传：** `application/archive/start.py:411–442` 的 `_release_workspaces_for_archive` 在开始归档时，把每个候选工作区的当前上传与 Preview 清空，并删除占用。属实。

**结论：** 禁用“提交”与“上传”是成立的界面决定，不需要后端新增字段。W8 的断言可以实现。§9 截图清单、§13.3、§13.4 都已纳入 W8。Q9 的建议成立，可以交 owner 确认。例外情况见第 4 节。

### 2.3 其余 N 条的抽查

§15 所列 N4–N6、N8–N12、N14–N25 都在所写位置上，内容与审核意见一致。§2.1 关于 ct108 占用标记的说明也已改正。链接全部能解析，包括新增的 `reviews/fe3-kickoff-review.md`。

## 3. 文字修正（不阻塞，不需要再复审）

| # | 位置 | 问题 | 改法 |
| --- | --- | --- | --- |
| R1 | §9 第 569 行，与 §3.2、§13.1、§13.2 对照 | 新的矛盾。§9 写 M1“在审核通过的候选上运行”；但 §13.1 要求 M1 数据写进 handoff，§13.2 要求审核会话复核 M1，§3.2 要求“经审核会话与 owner 判断”。按 §9 的写法，审核时还没有数据 | 改为：M1 在送审候选上测量，handoff 记录所用提交；审核要求的修复如果改动打包代码（`upload-package.ts`、`UploadStepCard.tsx`），在新候选上重测 |
| R2 | §6.2 第 444 行 | 写成“Preview 页在顶栏下方”。实际上 `comparison-resume` 在 `ComparisonPage` 的 `<main>` 中排在 `<header className="compare-header">` 之前，CSS 中也没有规则改变它的位置，所以它在顶栏**之上** | 改为“Preview 页在顶栏之上（`comparison-resume`）”。如果设计上要求放在顶栏下方，就写成 FE3b 的改动，不写“与 FE2c 相同” |
| R3 | §8.3 第 522 行 | “按同一 bundle 中 `composite_signal_point` 的状态判定（同后端 t1）”不准确。后端 t1 的 `composite_changed` 来自离线投影（第 2652 行，`offline_composite["counts"]["status"]`），与 Preview 互相独立；前端从同一 bundle 取，只能核对派生表以外变化的表数是否为 4 | 去掉“同后端 t1”，并写明：派生表本身是否变化，只在有后端 t1 对照时独立核对（第 523 行已有对照，保留） |
| R4 | §6.1 第 399–400 行与第 431 行 | `MANUAL_RECOVERY_REQUIRED` 不是终态（FE2 kickoff §7.5），按第 399 行会显示“提交正在执行”，而操作卡片显示的是“需要管理员处理”，两处不一致。另外，“提交”与“上传”的禁用原因表只有一行 attempt，没有和撤回表一样区分出“结果待确认” | 把 operation 为 `MANUAL_RECOVERY_REQUIRED` 的情况并入第 400 行“提交结果待确认，需要管理员处理”；第 431 行也按这两种情况分开写 |

## 4. 交设计会话（转后端设计会话，BE-a 实施前）：基线前移后才通过的提交会永久占用工作区

本项在复审范围之外，但与新增的 Q9 文案直接相关，也会影响 BE-a 的状态机，因此在这里报告。

**事实：**

- 归档候选只包括审核状态为 `APPROVED`、且 `based_on` 当前 head 的提交（`application/archive/snapshot.py:55–74`）。开始归档时，只释放候选所在的工作区（`start.py:419`）。
- 当前状态机中，`APPROVED` 唯一的出路是 `RETURN_FOR_REVISION`（`domain/submission/review.py:64–66`）。BE-a 删除该动作后，`APPROVED` 就没有任何转移了。
- 审核时不检查基线是否已前移（`review_transaction.py` 只检查版本、状态、归档关闭与占用绑定）。

**可以走到的情形：**

1. 同一项目中，A、B 两个工作区都基于 head H0 提交，两者都在 `PENDING`；
2. A 通过并归档，head 前移到 H1。B 仍是 `PENDING`，不是候选，所以没有被释放；
3. 审核人随后通过 B。B 变成 `APPROVED`，History 中带 `NOT_CANDIDATE_BASE_ADVANCED`。

此后 B 的工作区：

- 不能撤回，因为状态是 `APPROVED`；
- 不会被任何归档释放，因为 B 永远不会成为候选；
- 再次提交时，后端返回 `SUBMIT_OCCUPANCY_CONFLICT`。

这个工作区就被永久占用了。BE-a 之前还能靠 `RETURN_FOR_REVISION` 释放。

**对 FE3 的影响：** 这个状态下，§6.1 的“该提交已通过审核，开始归档后才能重新上传”是错的。没有 Q9，后端也会拒绝再次提交，所以 Q9 本身仍然成立。

**建议：**

- 由后端设计会话在 BE-a 实施前决定处理方式，例如：
  - 归档时同时释放基于旧基线的提交；
  - 通过时拒绝基线已前移的提交；
  - 允许本人或审核人对这类提交做某种关闭。
- 前端在 §6.1 的两张表中，为“`APPROVED` 且 History 节点带 `NOT_CANDIDATE_BASE_ADVANCED`”增加一行，原因写“该提交所基于的基线已更新，不能归档，需要管理员处理”，具体文案按后端的处理方式定稿。

## 5. 留下的内容

- 审核 worktree `/home/dev/gdds-p6-logs/fe3-kickoff-review-wt`：复审后已按要求执行 `git worktree remove`。
- 开发主机任务临时目录 `/home/dev/.claude/jobs/0117fb21/tmp/pkg`（上一轮留下的空目录）：已删除。
- 04、05：本轮没有访问，没有留下内容。
