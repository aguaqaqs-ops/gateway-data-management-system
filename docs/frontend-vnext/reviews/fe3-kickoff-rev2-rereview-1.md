# FE3 kickoff 修订 2 定向复核第 1 轮

- **日期：** 2026-11-08（节点只读核对 07:42–07:43Z）。
- **会话：** FE3 kickoff 修订 2 审核会话（与前端设计会话不是同一会话）。只核 [修订 2 审核](fe3-kickoff-rev2-review.md)（`d076903d7f`，owner 答复 `244a24b811`）的必改项与采纳的建议项，逐条对照 kickoff §15.4。
- **复核对象：** 本地 main `docs/frontend-vnext/fe3-kickoff.md`：
  - 第 1 步修订 `dfdcd00b90`（B1–B3、N1–N4、Q14 状态）；
  - 第 2 步修订 `885f5c4b64`（C1–C3、N5–N8、新增 Q20）。
- **方法：** 开发主机阅读两次提交的 diff 与修订后全文；用 `748de5034d` 的 `frontend/` 与 `vnext/` 源码核对新点名的行号与枚举；在 scratchpad 以 `git archive` 取 `748de5034d` 的输入运行 `--print-input`；04、05、07 只读核对（§3）。

## 0. 结论

| 部分 | 结论 |
| --- | --- |
| 第 1 步（FE3b） | **通过。** B1–B3、N1–N4 全部按意见处理，Q14 标为已决定。另有一处计数勘误 E1（不阻塞，已在提示词中写明） |
| 第 2 步（FE3c） | **通过。** C1–C3、N5–N8 全部处理；Q20 待 owner 决定。一处措辞不准 R1（不阻塞） |

- 第 1 步通过、owner 已确认 B1 选甲与 Q14（`244a24b811`），§13.3 前置的现场核对全部满足（§3）。**FE3b 实施提示词已按 §4 填写，可以发出。**
- FE3c 提示词仍在 `fe-fe3b-exit` 之后、Q18 补缺交付、§16.6 定稿、owner 确认 Q15–Q20 以后发出。

## 1. 第 1 步逐条（kickoff §15.4）

| # | 修订 | 核对 | 结论 |
| --- | --- | --- | --- |
| B1 | §2.1 新增“main 的后续变化与 FE3b 合入点”；§2.2 依赖镜像行改为 `748de5034d` 的 `--print-input`；§3.2 FE3b 前置改为合入 `748de5034d`、期间不再合入 main、FE3c 合入当时的 main；§3.2 新增“FE3b 期间 main 的变化”；§4.3 分 FE3b/FE3c，FE3c 新镜像经 CT201 构建或按 owner 许可拷贝并记录身份，开发主机同名镜像不能直接作证据；§5.1 注明 FE3c 原件按 §13.5；§10 两条停止条件分 FE3b/FE3c；§13.3 写定 `748de5034d`、`<main>` 与 `56720104af` | `748de5034d:vnext` = `56720104af`；`--print-input` 得 `gateway-backend-deps:lock-d054366c02fa`（输入 `d054366c02fa2a28…57aad`）；`repository_service/uv.lock` 前 12 位 `6dc9659f0aee`；`748de5034d` 含 `p6-be-a-d-exit`、`20d3b885f6`、`55d56efb6e`；`748de5034d..5ff82b303e` 中 `frontend/` 无改动 | 通过 |
| B2 | §5.5 分为记录切分层（只按字节切分并严格解码，输出 `(key, value)`）与成员层（只接受 `path`/`size`，重复、其他 key、空 value 拒绝并中止安装）；`pax-records.json` 按两层分别断言 | 向量逐字节核对：`literal_utf8` = `12 path=中\n`；`prefix_99` 为 `99 path=` + 90 个 `a` + `\n`；`prefix_101` 为 `101 path=` + 91 个 `a` + `\n`；`adjacent_records` 为 `path=中` 与 `comment=😀` 两条；三个非法向量在切分层（长度、换行、严格 UTF-8）拒绝 | 通过 |
| B3 ① | §6.4 新增组态树“归档主线”规则：有处置时禁用（“该提交已归档／已关闭（未归档）”，处置优先）；只有标记时原因不写“不能归档”；点名 `workspace.ts:247/255`、`workspace.test.ts:62`、`WorkbenchPage.tsx:457/478/534`；D1–D5 补“归档主线”断言，D3 写明父基线仍是 head 时也禁用 | 行号与源码一致（`archiveReady` 在 `:247`，禁用原因在 `:255`） | 通过 |
| B3 ② | §6.2 列全 `gateway-submit-operation`：写 `SubmitDialog.tsx:173/184`；读与清除 `ComparisonPage.tsx:188/199/208/476`、`WorkbenchPage.tsx:106/145/150/455`；e2e `workspace-shell.spec.ts:1584/1610` 改为预置指针与 attempt | 与源码 grep 结果完全一致 | 通过 |
| B3 ③ | §5.3：`journeys.ts:374` 的 action 类型改用生成类型 `AppendArchiveAnomalyResolutionRequest["action"]`；`mock-data.ts:58-68` 审计事件取值表补全；`mock-data.ts:46-52` 两处 `blockers` 加 `ARCHIVE_PENDING_REVIEW`（来源 `queries.py:147`、`:172`） | `ArchiveSubjectKind` 为 6 值（含 `CONFIRM_SELECTION`）；确认动作 `CONFIRM`/`REVOKE`，解析动作 5 个 `ACKNOWLEDGE_*` 与 `REVOKE`；7 个业务 issue_code 与 OpenAPI 枚举一致；`mock-data.ts:46-52` 正是两张 `blockers` 表；`queries.py:147`、`:172` 为两处追加 | 通过 |
| B3 ④ | §5.3 点名 `e2e/workspace-shell.spec.ts:1248` 改为“审核：已退回” | 一致 | 通过 |
| B3 ⑤ | §5.3 写明 D5 为唯一的防御性例外，单独存放并注明“DC89 不可达”；`mock-data.ts:120` 改为可达形态（D4）或改标为 D5 数据，二选一并在 handoff 写明 | 一致 | 通过 |
| N1 | §13.3 先读补 testing-conventions“真实 backend e2e” | 已改 | 通过 |
| N2 | §15.2 末尾补“核对报告 §5、§7 是状态记录” | 已改 | 通过 |
| N3 | §4.7 R10 ④ 写明需先有一个已通过、无处置的提交，handoff 写明 | 已改 | 通过 |
| N4 | §5.3 改为点名 `client.ts:93/98`，注明 `client.test.ts` 没有对应用例 | 已改 | 通过 |
| Q14 | 状态行、§11 表标为已决定（owner 2026-11-08） | 与 `244a24b811` 一致 | 通过 |

**E1（勘误，不阻塞）：** §5.5 与 §13.3 写“10 个文件”“`SHA256SUMS` 覆盖 10 个文件”，实际后端目录是 **9 个文件**：§5.5 列出的 9 个文件名完整正确（`bundle.tar`、`manifest.json`、`artifact-closure.json`、`index.json`、`pax-records.json`、`size-vectors.json` 与 3 个 header-only 文件），`index.json` 列 8 个（不含自身），BE-d 交接也写“全部 8 文件摘要相符”。
提交到前端后目录为 9 个原件加 `SHA256SUMS` 共 10 个，`SHA256SUMS` 覆盖 9 个原件。修订 2 审核 §2.5 也误写“10 个文件”（其表格只有 9 行），以本条为准。
提示词已写明这一点（§4），实施会话不会因计数与本文不符而停止；kickoff 正文由设计会话下次修订时顺带改正（交设计会话）。

## 2. 第 2 步逐条（kickoff §15.4）

| # | 修订 | 核对 | 结论 |
| --- | --- | --- | --- |
| C1 | §8.4：t1 复测只报告并作回归对照（MODIFIED_ONLY 超过 FE3a t1 v1 的 24.86 MiB 的 2 倍时报告并交设计会话；FULL 只报告）；超标判断只用 t4；FE3b/FE3c 改动打包代码时在 05 用 t4 v1 重测两种模式各 3 次并按标准判定；判断标准加“线性外推不用于 t1”；新增 §11 Q20；§3.2、§13.5、§13.6 同步 | 05 上有 `source-dirs/t4-v1`；Q20 写明改变 Q3、Q12 的判定口径，交 owner | 通过（Q20 待 owner） |
| C2 | §2.3 第 14 行改为 1–4096 UTF-8 字节；§16.6 补上限、两种禁用原因与 3500 字节计数，请求发原文；V9 补 4096/4097 字节边界 | 与 `validate_utf8_reason`（经 `compute_close_request_fingerprint`）一致 | 通过 |
| C3 | §4.6 实测校正：用带 `selected` 的预检；`issues` 与表去掉同级、身份两类后比较；`anomalies` 与全表比较 | 与 `_derive_anomalies`（无 `selected` 时返回空）及 `ArchiveBusinessIssueResponse.subject_kind` 三值一致 | 通过 |
| N5 | J2 第 5 步与 V10 改为“全部 subject 随候选集重新派生，全部回到未处理” | 一致 | 通过 |
| N6 | J1 第 9 步写定 `ARCHIVE_ANOMALY_UNRESOLVED`，并写明原因 | 与 `start.py:177-194` 一致 | 通过 |
| N7 | V6 写明可达构造（空 `INITIAL`；200 个 FULL，① 有效、② 缺时间；选中 1 个，199 项同级排除）；§16.5 给 `ARCHIVE_SCOPE_LIMIT_EXCEEDED` 专用文案“候选提交超过归档上限，需要管理员处理”，V13 可加断言 | 构造可达（① 有效、② 缺失时比较为 `NOT_COMPARABLE`，不产生时间倒退项） | 通过；括注见 R1 |
| N8 | §5.1、§10 注明 FE3c 按 §13.5；§4.3 写明 FE3c 预填充；§13.5 改为占位 `[FE3c 依赖镜像 tag]`，并要求已按 §4.3 预填充、记录来源与身份 | 一致 | 通过 |

**R1（措辞，不阻塞）：** §16.5 括注写“候选超过 200 个或引用超过上限”时返回 `ARCHIVE_SCOPE_LIMIT_EXCEEDED`。后端只在候选或待审核提交的读取超过上限时返回该码（`snapshot.py:73-74`、`:111`、`:140-141`）；请求中的引用超过 `maxItems` 是 422，异常数超过 `8N+1` 是 503 `ARCHIVE_INTEGRITY_FAILURE`。
建议括注改为“候选或待审核提交超过归档读取上限”。文案本身可以保留（交设计会话，可在 FE3c 前顺带改）。

## 3. §13.3 前置的现场核对（2026-11-08 07:42–07:43Z）

| 项 | 核对 | 结论 |
| --- | --- | --- |
| 接口 | 生产 OpenAPI 原件 SHA256 重算为 `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`；`748de5034d:vnext` = `56720104af`（与原件同树） | 满足 |
| 依赖镜像 | `748de5034d` 的 `--print-input` = `gateway-backend-deps:lock-d054366c02fa`；04、05 有该镜像：config `sha256:b5b5422411de38e5…e4b92a`，19 层，`RootFS.Layers` 全文摘要两节点相同，label `d054366c02fa2a28…` | 满足 |
| RS 依赖镜像 | `gateway-p2r1-repository:lock-6dc9659f0aee`：04、05、07 config `sha256:98d0801b1140a903…ad9ec9`，16 层相同，label 一致 | 满足 |
| 工具链 | `mcr.microsoft.com/playwright:v1.64.1-noble`：04、05、07 config `sha256:a0d7b2b49ffa0e99…a1017`，7 层相同 | 满足 |
| npm 缓存 | 04、07 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，05 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，SHA256 前缀均为 `0d861824f807b9d7` | 满足 |
| 互通 fixture | 开发主机原件目录 9 个文件，`bundle.tar` SHA256 `b08a310c…332a2`，与 §5.5 一致（计数见 E1） | 满足 |
| 起点 | `fe-vnext` 在 `0e7caf66f4`（`fe-fe3a-exit`），worktree `/home/dev/gdds-fe` 在该提交且 clean | 满足 |
| 节点占用 | 04、05、07 均无 `/home/dev/gdds-node-busy.d`；无容器发布 8000；无 dolt 进程。资源：04、05 为 64 vCPU / 64 GiB，07 为 8 vCPU / 16 GiB | 满足（发出时空闲；实施时由脚本原子获取） |

操作均为只读：`ssh -o BatchMode=yes … 'echo OK'`、`docker image inspect`（含 `ctr -n moby content get` 读 config digest）、`docker ps`、`pgrep`、`ls`、`sha256sum`；未取占用标记，未运行测试、Compose、构建或浏览器。

## 4. FE3b 实施提示词（已填写，可发出）

按 kickoff §13.3 填写：`[kickoff 确认提交]` = `885f5c4b64`（第 1 步经本复核通过、owner 已确认 B1 与 Q14；第 2 步的 FE3c 部分尚待 owner，不影响 FE3b）。另补 E1 的计数说明与本报告的阅读。

> 你是 FE3b 前端实施会话。FE3 已拆成 FE3b（契约与基础）与 FE3c（归档核验与完整旅程），本阶段只做 FE3b。
>
> **先读：**
> - AGENTS：“专用测试节点”“前端测试（FD7）”“Docker / Compose 验证”；testing-conventions“前端测试”与“真实 backend e2e”；
> - 前端 kickoff §4.3、§4.4、§7.1 与 FD4；FE2 kickoff §4.1、§7.5；
> - FE3 kickoff（main `885f5c4b64`）全文，重点 §2.1（含“main 的后续变化与 FE3b 合入点”）、§2.3、§3.2 FE3b 一行、§4、§5、§6、§9、§10；
> - `docs/frontend-vnext/reviews/fe3-kickoff-rev2-review.md`（含 §6 owner 答复）与 `reviews/fe3-kickoff-rev2-rereview-1.md`（本提示词与 E1 勘误）；
> - FE3a handoff 与 `reviews/fe3a-*.md`；`reviews/fe3b-precondition-check.md` 的 §3、§6、§8、§9；
> - 后端：`docs/backend-vnext/refactoring/formal/plans/` 下的 `p6-fe3b-backend-assessment-handoff.md`、`p6-be-d-frontend-handoff.md`（含 §2.1）、`p6-v2-frontend-handoff.md` §3、`p6-be-a1-handoff.md`。
>
> **后端事实（已核对，不需要再等后端）：** 见 kickoff §2.1、§2.2。`p6-s2a-exit` → `53b676a629`；`p6-be-a-d-exit` → `77b9aeea74`（产品 `49403f21aa`）；FE3b 合入的 main `748de5034d` 的 `vnext/` 树 `56720104af`；生产 OpenAPI 原件 SHA256 `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`；依赖镜像 `gateway-backend-deps:lock-d054366c02fa`、RS 依赖镜像 `gateway-p2r1-repository:lock-6dc9659f0aee`、工具链与 npm 缓存在 04、05 上齐备（07 有后三者），不需要预填充（审核会话 2026-11-08 07:43Z 现场核对）。
> 当前 main 的 `vnext/` 已因 S3 改变，FE3b 不合入（kickoff §2.1，owner 选甲）；后端在 main 上继续推进 S3、S4 不影响 FE3b。
>
> **起点与分支：**
> - `fe-vnext` 在 `fe-fe3a-exit`（→ `0e7caf66f4`），开发主机 worktree `/home/dev/gdds-fe`；
> - 先把 main `748de5034d` 以 `--no-ff` 合入 `fe-vnext`，不 rebase，FE3b 期间不再合入 main；合并会带入 main 上的前端提交 `55d56efb6e`（`GATEWAY_FE_TEST_WORKERS`），保留，由 FE3b 审核核对；
> - kickoff 以 main `885f5c4b64` 为准阅读（它晚于 `748de5034d`，不需要合入）；
> - 合并后按 kickoff §3.2 做路径核对（`<main>` 为 `748de5034d`；候选 `vnext/` 树必须为 `56720104af`；差异只含 `frontend/` 与 `docs/frontend-vnext/`）；
> - 合并后的 HEAD 上 `build-backend-dependency-base.sh --print-input` 必须仍得 `lock-d054366c02fa`，否则停止。
>
> **范围（kickoff §3.2 FE3b 一行）：**
> 1. **快照与清理（§5.1–§5.3）：** 用真实 backend 起栈取 `/openapi.json`，按 §5.1 规范化写入并重新生成类型，同一提交；与原件规范化后逐字节相同，不同即停止。按 §5.3 删除退回修改的全部路径、201/202 变通，`archive_disposition` 直接改为 `submission_disposition`；`REJECTED` 统一显示为“已退回”；模拟数据按 §5.3 的可达组合与指针规则（D5 是唯一的防御性例外）；归档对话框的 action 按 5 个 `subject_kind` 穷举映射，`journeys.ts` 的 action 类型改用生成类型，`mock-data.ts` 取值表按后端枚举补全；错误码单测解析新快照；`check-production-build.mjs` 覆盖新增模拟 token。
> 2. **tar 与 OPFS（§5.5）：** PAX 按字节解析，记录切分层与成员层分开，成员层只接受 `path`/`size`；标准 PAX `size`；接收预算先检查再分配；失败中止 OPFS 安装。把后端互通目录 `/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/` 中 §5.5 列出的 **9 个文件**原样提交到 `frontend/src/test/fixtures/backend-interop/be-d-0ba45e5ef8/`，并加 `SHA256SUMS` 覆盖这 9 个文件（目录共 10 个文件；kickoff 写的“10 个互通文件”是计数勘误，以文件名清单为准，见复核报告 E1）。单测与模拟 e2e 按 §5.5 编写，`pax-records.json` 按两层分别断言。不自造替代 fixture，不生成大文件。
> 3. **上传模式撤回与占用（§6.1–§6.3）：** 按 §6.1 的两张表实现撤回按钮与“提交”“上传”的禁用原因；撤回带 `review_version`；不按 actor 或指针推断可撤回；冲突后重新读取，不自动重发。§6.2 按 `active_submit_attempt_id` 与 `job_kind` 恢复，删除 `gateway-submit-operation` 标记的全部位置（§6.2 列出），续做失败按 §6.2 的规则（Q14 已决定）；n3 用例改为基于指针，覆盖不减。§6.3 W1–W10 在模拟接口全部覆盖；“真实”一列为“是”的进入真实 e2e。
> 4. **终局处置只读显示（§6.4）：** 组态树、详情面板与审核模式顶栏按 §6.4 的表；处置优先于 `NOT_CANDIDATE_BASE_ADVANCED`；组态树“归档主线”有处置时禁用；D1–D5 由模拟接口覆盖（D5 为防御性数据，§5.3）。不做关闭入口。
> 5. **真实 backend 旅程（`--suite journeys`，§4.7 中“子阶段”为 FE3b 的部分）：** R1、R2、R3、R4（到 `PENDING`）、R5、R6（`REJECT` → 重提 → 通过）、R7、R9（两节点）、R10（④ 需先有一个已通过、无处置的提交）、R11；身份按 §4.6，“提交人（本人撤回）”带 `withdraw_own_submission`、不带 `review_submission`；上传按 §4.6 的“FE3b 的上传”，handoff 写出每个 scope 的上传序列。冒烟按 §3.3、§4.7 删除“下载比较结果失败”的临时断言，进入差异浏览后再断言 `pageErrors`。
> 6. **FE3a 带入：** 为 `e2e*/` 加 tsconfig 并纳入类型检查（FE3a 复审 N1）；按 tar 的 `ETag` 与 bundle 摘要记录 bundle 标识（N2）。
>
> **不做（FE3c）：** 归档业务核验的显示、逐项接受与撤销、关闭出口、待审核阻塞与过期通过的界面、R4 身份确认、R8、R9 三节点、R12、§4.6 的 A–D 归档序列及其核对、t1 旅程、M1 复测。不改 `vnext/`；不在浏览器中重算 SQL、来源或时间。
>
> **节点：**
> - 类型检查、lint、单测、构建、截图、模拟接口 e2e 在 07（`ct109-gw-dms-07`），设置 `GATEWAY_FE_TEST_WORKERS=2`，不获取占用标记；
> - 真实 backend e2e 与上传包校验在 05（`ct108-gw-dms-05`），由脚本按 kickoff §4.2 获取占用（会话名 `fe3b-impl`）与 `flock -n`，结束后清理并释放；调用前不要手工获取占用（脚本会以 exit 3 退出）；后端占用 05 时等待；
> - 某节点占用标记的用途为计时测量时，前端在该节点上的任何运行都等待；
> - 不在 04 上运行，04 取证在审核通过后进行；
> - 05、07 上运行时按 kickoff §2.2 设置 npm 缓存的环境变量；源码经 git bundle 传到节点，在 clean、已提交的 detached worktree 中运行，日志与截图写在 worktree 外。
>
> **停止条件：** kickoff §10。脚本自身的错误按 DC68 重做一次，重做再失败即停止；被测对象运行后的失败不按 DC68 重做。
>
> **交付：** 07 上 `run-tests.sh --e2e --screenshots`、05 上 `--suite journeys` 与 `validate-upload-package.sh` 各一次通过（均为调试运行）后，提交代码候选与 handoff `docs/frontend-vnext/fe3b-handoff.md`，内容包括：
> - 合并提交、所合入的 main（`748de5034d`）与 `vnext/` 树、路径核对结果；
> - 快照来源与比对结果；清理清单（删除的退回路径、类型变通与 `sessionStorage` 标记）；`mock-data.ts:120` 的处理方式（§5.3）；
> - W1–W10、D1–D5 与用例的对应；旅程各项结果，只由模拟接口覆盖的项及原因；每个 scope 的上传序列；
> - tar 修复与同字节互通：fixture 目录与 `SHA256SUMS` 的 SHA256、用例名、运行节点与日志 SHA256；预算边界用例；
> - 截图清单（kickoff §9 FE3b）；
> - 每次运行的节点、hostname、起止时间、起止 HEAD、exit code、日志 SHA256；工具链（config digest 与全部 DiffID）、npm 缓存（来源提交、归档 SHA256）、依赖镜像（tag、label、config digest、全部 DiffID）与 RS 镜像身份；
> - 偏差与未决事项。不沿用 FE3a handoff 的勘误项（kickoff §3.2）。
>
> 不推送。
>
> **审核通过后的 04 取证（由审核会话指明）：** 在 04 的 clean、已提交 detached worktree 上各运行一次：`run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`run-real-backend-e2e.sh --suite journeys`。

## 5. 后续

- **owner：** 转发 §4 的提示词给 FE3b 实施会话；FE3c 前确认 Q15–Q20（Q20 即 C1 的判定口径），安排 Q18 后端补缺。
- **设计会话：** 下次修订时改正 E1（§5.5、§13.3 的文件计数）与 R1（§16.5 括注），不需要单独提交。
- **FE3b 审核：** 按 kickoff §13.4，审核会话在 FE3b handoff 提交后进行。
