# FE3 kickoff 修订 2 审核

- **日期：** 2026-11-08（节点只读核对 07:13–07:23Z）。
- **会话：** FE3 kickoff 修订 2 审核会话（与前端设计会话不是同一会话）。只审 kickoff，不审代码；未改 kickoff 正文、源码与节点状态。
- **审核对象：** 本地 main `docs/frontend-vnext/fe3-kickoff.md`，区间 `53403631bc..5ff82b303e` 中的设计会话提交：
  - 第 1 步 `d702307836`（FE3b：§1–§6、§9、§10、§12、§13.3、§13.4、§15.2）；
  - 第 2 步 `771cc083b0`（FE3c：§16、§4.6 J1/J2 与预期异常、§4.7 R8/R12、§8、§9、§13.5、§13.6、§15.3）；
  - 后端答复记录 `5ff82b303e`（Q18 与生成时间预期）。
  - 治理提交 `ea3b17307d` 只核是否与设计冲突（§1.3）。
- **方法：** 开发主机只读 detached worktree `/home/dev/gdds-reviews/fe3-kickoff-rev2-review-wt`（`5ff82b303e`）阅读文档、`frontend/` 与 `vnext/` 源码；
  生产 OpenAPI 原件用 `python3 -I` 程序抽取；04、05、07 只做 `echo OK`、`docker image inspect`、`ls`、`sha256sum`，未取占用标记，未运行测试、Compose、构建或浏览器（操作记录见 §5）。
- **依据：** FE3b 前置条件核对（下称“核对报告”）§1–§10；AGENTS（专用测试节点、前端测试（FD7）、Docker / Compose 验证）；testing-conventions“前端测试（FD7）”“真实 backend e2e”；
  前端 kickoff FD4、§3.3；DC75、DC89、DC90；后端 FE3b 评估交接、BE-d 前端交接（含 §2.1，`20d3b885f6`）、V2 交接、归档业务核验设计、S3 协调 §16（`1981882cc6`）；
  生产 OpenAPI 原件（SHA256 `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`，已重算）；后端源码只读。

## 0. 结论

| 部分 | 结论 | 必改项 |
| --- | --- | --- |
| 第 1 步（FE3b） | **定向修订** | B1 合入哪个 main（交 owner 选择，交设计会话改文字）；B2 §5.5 PAX key 白名单与后端合法向量冲突；B3 §5.3/§6.2/§6.4 清单遗漏（含一处会让已关闭提交仍可进入归档主线的映射） |
| 第 2 步（FE3c） | **定向修订** | C1 t1 上的 M1 线性外推会误判超标；C2 关闭理由缺 4096 字节上限；C3 实测校正的比较口径要区分 `issues` 与 `anomalies` |

- **最重要的事实变化：** 当前 main（`5ff82b303e`）的 `vnext/` 树已是 `e0a40d93ef`，不再是 `56720104af`。S3（P6 比较/风险 Rust 接线）直接在 main 上提交，改了 `rust/Cargo.lock`，
  使 `build-backend-dependency-base.sh --print-input` 得到 `gateway-backend-deps:lock-ca0ba0a24a5e`；该镜像只在开发主机上（6 小时前建），04、05 没有。
  按 kickoff §10，FE3b 若照 §3.2“合入当时的 main”执行，合并后第一步就会停止。HTTP 层没有改动，OpenAPI 预计不变（§1.2）。
- **§2.3 的 18 行与 OpenAPI 原件、后端交接逐行一致；“FE3b 不需要新增后端字段”成立。** 节点、镜像、缓存与 t1 输入现场核对与 §2.2 一致，三节点均无占用标记。
- **Q14 成立**（§2.6）。Q15、Q16、Q17、Q19 的建议成立；Q17 需同时处理 C1。Q18 的状态写法与 S3 协调 §16 一致（§3.5）。
- **本会话暂不发出 FE3b 实施提示词。** 发出前提：B1–B3 由设计会话修订并经本会话定向复核；owner 选定 B1 并确认 Q14；本会话现场再核一次接口、镜像与占用（§4）。

## 1. 核对对象与产品树

### 1.1 kickoff 区间与产品树

| 提交 | `vnext/` 树 | 说明 |
| --- | --- | --- |
| `53403631bc`（FE3a 退出记录） | `2791d3ff3d` | 区间起点 |
| `d702307836`、`771cc083b0` | `56720104af` | = `p6-be-a-d-exit` 产品 `49403f21aa` 的树 |
| `748de5034d`（docs(p6): record S3 implementation authorization…） | `56720104af` | **main 第一父链上 `vnext/` 仍为 `56720104af` 的最后一个提交**；含 `p6-be-a-d-exit`、`20d3b885f6`、`55d56efb6e` 与 kickoff 两步 |
| `ea3b17307d`（治理） | `ef5e1635af` | 之前已有 S3 A–C 的 `vnext/` 改动 |
| `5ff82b303e`（当前 main） | `e0a40d93ef` | 与 `56720104af` 相比改动 53 个文件，全部在比较、风险、快照、table access 的计算路径与测试；无 `http/`、路由或 DTO 改动 |

### 1.2 依赖镜像输入（开发主机程序核对）

在 scratchpad 中用 `git archive` 取出两份最小输入，运行各自提交的 `build-backend-dependency-base.sh --print-input`（只读，基础镜像已在开发主机）：

| 提交 | `rust/Cargo.lock` SHA256 | 依赖镜像 tag |
| --- | --- | --- |
| `49403f21aa` | `bac3443e…37d29` | `gateway-backend-deps:lock-d054366c02fa`（与 04/05 镜像 label `d054366c02fa2a28…57aad` 一致） |
| `5ff82b303e` | `65e8e5bf…32175` | `gateway-backend-deps:lock-ca0ba0a24a5e`（`gateway-compute-core` 新增 `arrow-data`，`sha2` 移到正式依赖） |

- 其余四个输入（`backend/pyproject.toml`、`uv.lock`、`.python-version`、`rust-toolchain.toml`）与 `repository_service/uv.lock`（`6dc9659f0aee`）不变。
- `lock-ca0ba0a24a5e` 在开发主机存在（image `15a18396cec1`，6 小时前），04、05、07 都没有。

### 1.3 治理提交 `ea3b17307d`

只在 §4 开头与 §8.4 开头加 testing-conventions「真实 backend e2e」的引用、改 §4.1 末条与 §12 一行的状态、把 M1“峰值清零”改为“以重置后的 `VmHWM` 为基线”（注明 owner 2026-11-08 确认、与 FE3a 实现一致）。
与设计内容不冲突。testing-conventions 中“脚本自行获取占用，调用前手工获取即 exit 3”与 kickoff §4.2 一致。§12 中“待独立审核与 owner 确认”现仍准确（`f17ed3713f` 记录独审通过、待 owner 接受）。

## 2. 第 1 步（FE3b）

### 2.1 事实（§2.1–§2.3）

**§2.1、§2.2：**

| 项 | kickoff | 核对 |
| --- | --- | --- |
| `p6-s2a-exit` | 对象 `ec02169f35` → `53b676a629`，在 main 第一父链上 | 一致 |
| `p6-be-a-d-exit` | 对象 `66b9083941` → `77b9aeea74`；产品 `49403f21aa`；树 `56720104af` | 一致 |
| `fe-fe3a-exit` | 对象 `8dd0f765b3` → `0e7caf66f4`，`frontend/` 树 `8a9f11c84f`；合入 `86fa2e4e8a` | 一致；`fe-vnext` 仍在 `0e7caf66f4` |
| “`49403f21aa..e8c45eb642` 没有改动 `vnext/`” | — | 在 `e8c45eb642` 时成立；**到当前 main 已不成立**（§1.1，B1） |
| 工具链 `playwright:v1.64.1-noble` | config `a0d7b2b4…a1017`，7 个 DiffID | 04/05/07：config `sha256:a0d7b2b49ffa0e99…a1017`，7 层，`RootFS.Layers` 全文摘要三节点相同 |
| `gateway-backend-deps:lock-d054366c02fa` | 04/05 有；config `b5b54224…e4b92a`；19 层 | 04/05：config `sha256:b5b5422411de…e4b92a`，19 层相同，label `d054366c02fa2a28…`；07 无（不需要）；开发主机 image `b5b5422411de` |
| `gateway-p2r1-repository:lock-6dc9659f0aee` | config `98d0801b…ad9ec9`，16 层 | 04/05/07 一致，label `6dc9659f0aeea1b4…` |
| npm 缓存 | 三份归档 SHA256 `0d861824…0089f4` | 04、07 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，05 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`，前缀均为 `0d861824f807b9d7` |
| t1 目录（05） | 清单 `cdb598cd…0163`、`fa2450fa…a96a`；19/19 | 清单 SHA256 相同；目录内 `sha256sum -c` 19/19 通过；19 文件 / 6,853,875 B 与 19 / 6,854,427 B |
| `GATEWAY_FE_TEST_WORKERS=2` | 07 使用 | main 的 `frontend/scripts/run-tests.sh`（`55d56efb6e`）读取并校验为正整数，传给 Playwright `--workers` |
| 占用标记 | — | 04、05、07 均无 `/home/dev/gdds-node-busy.d` |

结论：除“main 的 `vnext/` 仍为 `56720104af`、不需要预填充”这一项因 S3 已过时外，其余事实成立。

**§2.3 逐行（OpenAPI 原件 + 后端源码）：**

| 行 | 核对 | 结论 |
| --- | --- | --- |
| 1、2 | `WorkspaceResponse` required 含 `active_submit_attempt_id`、`active_submission_id`，均 `string \| null`；`POST /v1/workspaces` 201/200 同 schema；`GET .../submit-attempts/{id}` 存在 | 一致 |
| 3 | `assert_review_permission`：有 `review_submission` 直接通过，否则 GET（action 为空）与 WITHDRAW 要求 `withdraw_own_submission`；`assert_review_target_authorized` 只放行本人 | 一致 |
| 4 | `ApplyReviewRequest.expected_review_version`；`ReviewFactsResponse.review_version` required | 一致 |
| 5 | `GET .../review` 403 `SCOPE_FORBIDDEN`、404 `RESOURCE_NOT_FOUND` | 一致 |
| 6 | OpenAPI 无字段，按 BE-a 规则 | 一致（真实 e2e 验证） |
| 7 | `POST /v1/workspaces` 201 + 200 “Existing workspace”；`POST /v1/history-compares` 202 + 200 | 一致 |
| 8 | `ApplyReviewRequest.action` = `APPROVE/REJECT/WITHDRAW`；`ReviewFactsResponse.status` 无退回 | 一致 |
| 9 | 两个 bundle 路由 200 `application/x-tar`，headers `Content-Length`、`ETag`、`Content-Disposition`；Preview 404 `RESOURCE_NOT_FOUND`、503 `SERVICE_NOT_READY, BUNDLE_INTEGRITY_FAILURE`；History 404 `RESOURCE_NOT_FOUND, ARTIFACT_UNAVAILABLE`、503 `BUNDLE_INTEGRITY_FAILURE` | 一致 |
| 10、11 | BE-d 交接 §1–§3；fixture 见 §2.5 | 一致 |
| 12 | `SubmissionDispositionResponse` 五字段 required；`HistoryNodeResponse.submission_disposition` 枚举 `ARCHIVED_BASELINE/CLOSED_NOT_ARCHIVED`，`disposition_source_kind` `ARCHIVE/MANUAL_CLOSE`，`disposition_result_id`，`closure`；schema 中无 `ArchiveDispositionResponse`；`ArchiveResultResponse.dispositions` 为 `SubmissionDispositionResponse` | 一致 |
| 13 | `application/history/projection.py:210-218` `_derive_eligibility_note` 只看 `APPROVED` 与基线 | 一致 |
| 14 | 关闭路由 201/200，409 六码一致，另 403/404/413/422/429/503；`Idempotency-Key` 由 `request.headers` 读取（OpenAPI 未列为参数，与其他写路由相同） | 一致。“非空 `reason`”实为 1–4096 UTF-8 字节（`validate_utf8_reason`，见 C2） |
| 15 | `business_validation` 五字段；`ArchivePreviewAnomalyResponse` 新增字段齐全，`details` 为五个类型的 union；`subject_kind` 五值；`AppendArchiveAnomalyResolutionRequest.action` 六值 | 一致（`detected_status` 在该 schema 中是 string，不是枚举） |
| 16 | 两个响应 required 含 `pending_submission_ids`、`pending_submission_count`；`POST /v1/archives` 409 含 `ARCHIVE_PENDING_REVIEW` | 一致 |
| 17 | `confirmation_refs` maxItems 1、`anomaly_resolution_refs` maxItems 1601；`ARCHIVE_MAX_CANDIDATES = 200`、`ARCHIVE_MAX_REQUEST_BYTES = 256 * 1024` | 一致 |
| 18 | review-events 409：`IDEMPOTENCY_CONFLICT, REVIEW_VERSION_CONFLICT, REVIEW_TRANSITION_CONFLICT, WORKSPACE_OCCUPANCY_CONFLICT, BASELINE_VERSION_CONFLICT, ARCHIVE_CLOSED` | 一致 |

**“FE3b 不需要新增后端字段”：成立。** 撤回所需 `review_version` 由本人可读的 review 给出；占用、恢复由两个指针与 attempt 给出；处置显示所需字段（含 `promoted_baseline_node_id`）都在 History 节点与 Review 中；R10 ④ 用候选查询 403。

### 2.2 拆段（§3.2）

- FE3a、FE3b、FE3c 三行的前置、退出 tag 与审核区间可以执行：`fe-fe3a-exit..<FE3b 候选>`、`fe-fe3b-exit..<FE3c 候选>` 形式与 FE3a 一致；FE3c 前置写明“Q18 补缺已交付、§16.6 定稿”。
- 路径核对规则可执行；`55d56efb6e` 的例外写法正确：它在 `748de5034d` 与当前 main 中，不在 `fe-fe3a-exit` 中，只改 `frontend/scripts/run-tests.sh`；区间内 main 上再无其他 `frontend/` 改动。
- **问题在“开始时先把当时的 main 合入”（B1）。** 路径核对本身没错，但“当时的 main”现在会带入 S3 进行中的 `vnext/`，导致依赖镜像不符而停止，也让 §5.1“运行时 OpenAPI 与原件来自同一 `vnext/` 树”的前提不再成立。

### 2.3 场景（§4.7）与核对报告的对应

| 修订 | kickoff | 核对报告 | 结论 |
| --- | --- | --- | --- |
| R6 改为“退回 → 重新提交 → 通过” | §4.7 R6：`REJECT`（必填理由）→ 两个指针清空 → 同一输入重新上传 → Preview → 提交 → 通过；另回归 W7 | §3.3、§8.3 R6 | 对应 |
| R4 身份确认、R8、R9 三节点、R12 移到 FE3c | R4 拆为“到 `PENDING`：FE3b／身份确认：FE3c”；R8、R12 为 FE3c；R9 两节点 FE3b、三节点 FE3c；R1 归档后的树在 FE3c | §8.2、§8.3 | 对应 |
| 删去冒烟中的“下载失败”断言 | §3.3 末条、§4.7 冒烟：改为断言 tar 下载、安装成功并进入差异浏览，再断言无未捕获错误；记录 `ETag` 与 bundle 摘要 | §6 第 4 项（N2、N5）、第 5 项 | 对应 |
| FULL 恰好两个比较对 | R2 | §6 第 1 项最后一条 | 对应 |
| R10 四项 | ④ 需要在同一 scope 中有 `APPROVED` 的提交节点：现有 `workspace.ts:247` 只有 `APPROVED` 且无基线标记时才启用“归档主线” | — | 可执行；实施时注意 scope 内先有已通过的提交（非阻塞 N3） |

### 2.4 契约同步（§5.3）——用 `frontend/` 源码核对

`frontend/` 树以 main `5ff82b303e`（= `fe-fe3a-exit` 的 `frontend/` 加 `55d56efb6e`）为准。

| 清单项 | 源码中的全部位置 | kickoff 是否列出 |
| --- | --- | --- |
| `RETURNED_FOR_REVISION` 映射 | `src/features/api/client.ts:93`、`:98` | 列出 |
| 同上状态文字与色调 | `src/features/view-model/workspace.ts:39`（显示“已退回”）、`:52` | 列出 |
| “需修改” | `src/pages/ComparisonPage.tsx:38`（`RETURNED_FOR_REVISION: "需修改"`） | 列出 |
| `client.test.ts` 中的对应用例 | **不存在**：`client.test.ts` 没有 `RETURNED_FOR_REVISION`；生成类型 `openapi.d.ts:515/871/1070/1082/1084/1098/1114` 随刷新消失 | kickoff 写了一个不存在的用例（N4） |
| “已拒绝”→“已退回” | `ComparisonPage.tsx:38`；**mock e2e `e2e/workspace-shell.spec.ts:1248` 断言“审核：已拒绝”** | e2e 断言未点名（B3-④） |
| `archive_disposition` → `submission_disposition` | 前端代码中没有消费；只有 `src/features/dev/mock-data.test.ts:116` 断言“没有 `archive_disposition`” | 足够 |
| `eligibility_note` 只在 `APPROVED` | `src/features/dev/mock-data.ts:458`（`PENDING` + 标记，kickoff 已点名）；`mock-data.ts:120`（`APPROVED` + 标记 + 无处置，即 D5 形态） | `:120` 与 §5.3“只构造可达组合”冲突（B3-⑤） |
| 5 个 `subject_kind` 的 action 穷举 | `src/features/workbench/ArchiveMainlineDialog.tsx:35-36`；**`src/features/api/journeys.ts:374` 的 `action` 类型只有三值**；**`mock-data.ts:58-68` 取值表（`ArchiveAuditEventResponse.subject_kind/action/issue_code`）不含三类新值**；`mock-data.ts:50-52` `ArchiveCandidatesResponse.blockers` 不含 `ARCHIVE_PENDING_REVIEW` | 只点名 `anomalyAction`（B3-③） |
| 删除 `gateway-submit-operation` | 写：`SubmitDialog.tsx:173/184`；读与清除：`ComparisonPage.tsx:188/199/208/476`、**`WorkbenchPage.tsx:106/145/150/455`**；mock e2e：**`e2e/workspace-shell.spec.ts:1584/1610`** | §6.2 只点名前两个文件（B3-②） |
| 模拟 token 禁用模式 | `scripts/check-production-build.mjs:26` | 列出 |

**§6.4 映射遗漏（B3-①，影响行为）：** `workspace.ts:247` `archiveReady = reviewStatus === "APPROVED" && eligibilityNote == null`。

- 手工关闭且基线未变的提交（J2 的 C）没有标记，按现有逻辑“归档主线”仍可用；已归档的提交带标记，按钮禁用原因仍是“…不能归档”（`workspace.ts:255`、`workspace.test.ts:62`）。
- §6.4 只规定了审核模式按钮的禁用原因，没有规定组态树“归档主线”动作。需要补：有处置时禁用，原因“该提交已归档”或“该提交已关闭（未归档）”；只有标记、无处置（D5，按 DC89 不可达）时的原因按 §6.4 的说明文字，不写“不能归档”。
- `WorkbenchPage.tsx:457`（状态标签）、`:478`（`title` 含“不能归档”）、`:534`（详情“归档原因”）已被 §6.4 的文字覆盖，建议点名文件以便核对。

### 2.5 tar（§5.5）

- **PAX 按字节、`size` 覆盖、预算先查后分配、失败中止 OPFS：** 与 BE-d 交接 §1–§2.1 一致。现实现（`posix-tar.ts:199-218`）先整体解码再按 `text.length` 推进，`PAX_LIMIT` 在读取之后才检查；PAX payload 经 `readMemberBytes` 只受 16 MiB `METADATA_LIMIT` 约束；`installBundleTar` 的 `catch` 已调用 `transaction.abort()`。§5.5 要求的改动点准确。
  后端 `tar_stream.py` 的 PAX header 名为 `PaxHeaders/path`、header size 在 `pax_size` 时为 0，与 §5.5 一致。
- **fixture 10 个文件（开发主机原件）：** 与 §5.5 及 `index.json` 全部一致，合计 44,129 B（“约 45 KB”）。

  | 文件 | 字节 | SHA256 |
  | --- | --- | --- |
  | `bundle.tar` | 24,576 | `b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2` |
  | `manifest.json` | 6,062 | `320f44e71bdf70f802a83c3362515a7399694a400b88551b9da41be9c8fb4f67` |
  | `artifact-closure.json` | 5,232 | `becf0b703c3dad4bf033341c88c3580ecdc66ae695a728bce5d912cf79f8897a` |
  | `index.json` | 3,376 | `199d451123df6a0354e51c92e411aad1770553909d18ff07e6d4fecdd14ea38d`（不在自身清单中） |
  | `pax-records.json` | 733 | `0fa31f374dd1b5aa3abe21444b897b45230c9271d7c0bf03f46e2fc34cef0f69` |
  | `size-vectors.json` | 566 | `b8d23e94143fa6cf0b2899ca3b88492e99215d6e19ffd412b4ddd7dcab51c06d` |
  | `size-8589934591-header-only.bin` | 512 | `113775f2209f4f8b282db49432606cbc247aabc8415fbd1293d352f63be30d53` |
  | `size-8589934592-header-only.bin` | 1,536 | `06a761a2e0494b34d01327b7a4d81b1207e3de6a46fa777ec4b9a47766d91581` |
  | `size-9007199254740991-header-only.bin` | 1,536 | `877b1ea28bfb63210a770c187703ec165ffe0062b5c2662629d832cbfee9bf64` |

  `index.json`：`bundle_digest = sha256:2be243c3…d5ef050`，`content_length = 24576`，`ordinary_artifacts` 4 项（ASCII 长路径、中文、非 BMP），与 §5.5 单测描述一致。
- **B2：PAX key 白名单与后端合法向量冲突。** `pax-records.json` 的 `adjacent_records` 是 `12 path=中\n` + `16 comment=😀\n`。§5.5 一方面规定“只接受 `path` 与 `size`，其他 key 拒绝”，另一方面把 `adjacent_records` 列为“解析正确”的 4 个合法向量之一。
  BE-d 交接只说后端当前只生成 path/size，没有要求前端拒绝或接受其他 key。两条规定同时照做无法实现。需要设计会话写明其中一种：
  - 推荐：把“按字节切分记录”与“成员级 key 白名单”分成两层。`adjacent_records` 用于切分层：断言切出两条记录、`path=中`、`comment=😀`；作为成员的 PAX payload 时因 `comment` 被白名单拒绝（单测各断言一次）。
  - 或者：放宽为“忽略未知 key、只取 path/size”，但需说明为何不按 §5.5“不预先放宽”的原则。

### 2.6 占用与处置（§6.1–§6.4）

- **暂定行已删除：** §6.1 两张表都没有 `NOT_CANDIDATE_BASE_ADVANCED` 行；§6.1 末段、§12 第一行写明删除理由。成立。
- **处置优先：** §6.1 撤回表中 `submission_disposition` 行优先于审核状态各行与标记；占用表同；§6.4 规定处置非空时不显示“基线已更新”。与 V2 交接 §3、FE3b 评估交接 §3 一致。
- **`NOT_CANDIDATE_BASE_ADVANCED` 只作历史说明：** §2.3 第 13 行、§6.1、§6.4 的写法与 `20d3b885f6` 一致；任何情况不显示为阻塞。成立。
- **上传禁用文案：** 七行覆盖两个指针的全部组合与读取失败；`PENDING` 时撤回绑定冲突与 `APPROVED` 时归档/关闭清空上传的依据（`assert_review_workspace_bindings`；`manual_close.py:114-118`）正确。
- **W1–W10、D1–D5 可测性：** W1–W5、W7、W8 在真实 backend 上可产生（W3 用仅上传身份：GET review 走 `withdraw_own_submission` 检查得 403；W5 两个 context，撤回或退回后版本变化）；W6、W9、W10 只在模拟接口，理由写明。D1–D5 在模拟接口可构造；D5 按 DC89 不可达，需在 §5.3 写成显式的防御性例外（B3-⑤）。
- **Q14 的建议成立：**
  - 后端只保证“查询失败、operation 终态都不等于占用释放”，前端以工作区指针为准是唯一不越界的做法；
  - 重读工作区后按指针与 §6.1 表决定，读不到时保持禁用并给“重试”，提示与禁用原因不会矛盾（满足 FE3a 审核 B7）；
  - 不需要后端新字段；“读取失败即恢复可用”会在指针未清时放出“提交”，后端以 409 `SUBMIT_OCCUPANCY_CONFLICT` 拒绝，体验更差。

### 2.7 §9、§10、§12、§13.3、§13.4、§15.2

- **§9、§10、§12 一致：** §9 FE3b 三行与 §3.2 退出条件、§13.3 交付项一致（07 调试、05 `journeys` 与上传包校验调试、04 三项证据）。§10 列出“合入后 `--print-input` 不再得 `lock-d054366c02fa` 即停止”——与 B1 直接相关。§12 状态与 §2.1、§6.1 一致。
- **§13.3：** 占位符 `[kickoff 确认提交]`、`[合入用 main 提交]` 清楚。需要改的地方：
  - “main 的 `vnext/` 树 `56720104af`”“不需要预填充”“预期 `56720104af`”按 B1 的选择改写；
  - “先读”补 testing-conventions「真实 backend e2e」（治理已把脚本执行细节移到该节；非阻塞 N1）。
- **§13.4：** 占位符清楚；四个探针前提写明（05 探针先确认两个版本取值不同）。可以执行。
- **§15.2 与核对报告 §1–§10：** §3.3 的 10 行、§6 的 10 项、§8.1–§8.4、§9、§10 都有对应。未出现的只有 §5（推送状态）与 §7（还差的条件），二者是状态记录，不需要修订；建议补一行说明（非阻塞 N2）。

### 2.8 第 1 步意见汇总

| # | 意见 | 负责 |
| --- | --- | --- |
| **B1** | **合入哪个 main。** 当前 main 的 `vnext/` 是 S3 进行中的 `e0a40d93ef`，依赖镜像需要 `lock-ca0ba0a24a5e`（04/05 没有），FE3b 照现文会在合并后停止。两个选择：<br>甲（推荐）：FE3b 合入 `vnext/` 仍为 `56720104af` 的最后一个 main 提交 `748de5034d`。被测 backend 是已退出的 `p6-be-a-d-exit` 树，`lock-d054366c02fa` 不变，不需要预填充，§5.1“与原件同树”成立；FE3b 期间不再合入 main；FE3c 开始时连同 Q18 补缺一起合入，届时按 AGENTS 由 owner 安排新依赖镜像预填充。<br>乙：合入当前 main。需 owner 按 AGENTS 在 CT201 clean worktree 构建并预填充 `lock-ca0ba0a24a5e` 到 04/05（开发主机上现有的同 tag 镜像来源未记录，不能直接作证据）；FE3b 真实 e2e 将跑在尚未退出的 S3 计算路径上；S3 继续改 `vnext/` 时，路径核对与镜像会反复变化。<br>设计会话据 owner 选择改 §2.1（补当前事实）、§3.2“当时的 main”、§4.3、§10、§13.3。 | 交 owner（选择）；交设计会话（文字） |
| **B2** | §5.5 PAX key 白名单与 `adjacent_records` 冲突，见 §2.5。 | 交设计会话 |
| **B3** | 清单补全（§2.4）：① §6.4 补组态树“归档主线”动作按处置禁用（`workspace.ts:247/255`、`workspace.test.ts:62`），点名 `WorkbenchPage.tsx:457/478/534`；② §6.2 删除 `gateway-submit-operation` 补 `WorkbenchPage.tsx:106/145/150/455` 与 `e2e/workspace-shell.spec.ts:1584/1610`；③ §5.3 action 映射补 `journeys.ts:374` 类型与 `mock-data.ts` 取值表（审计事件 `subject_kind/action/issue_code`、候选 `blockers` 加 `ARCHIVE_PENDING_REVIEW`）；④ §5.3 点名 `e2e/workspace-shell.spec.ts:1248` 的“已拒绝”；⑤ §5.3 写明 D5（`APPROVED` + 标记 + 无处置）是防御性模拟、不受“只构造可达组合”约束，并处理 `mock-data.ts:120`。 | 交设计会话 |
| N1 | §13.3 先读补 testing-conventions「真实 backend e2e」。 | 交设计会话 |
| N2 | §15.2 补一行：核对报告 §5、§7 为状态记录，无需修订。 | 交设计会话 |
| N3 | R10 ④ 要在该 scope 内先有 `APPROVED` 的提交节点，建议在 §4.7 或上传序列中注明。 | 交设计会话 |
| N4 | §5.3 中“`client.test.ts` 中的对应用例”不存在，删去或改为“生成类型与 `client.ts` 中的映射”。 | 交设计会话 |

## 3. 第 2 步（FE3c）

### 3.1 §16 与 OpenAPI 原件、V2 交接

| 项 | 核对 | 结论 |
| --- | --- | --- |
| `detected_status` | 卡片：`queries.py` 中来源项 `UNEXPLAINED`、其余 `DETECTED`；概况：`ArchiveSourceDiagnosticResponse.detected_status` 三值、`ArchiveTimeComparisonResponse.detected_status` 四值 | 一致 |
| `resolution_status` / `latest_sequence` / `accepted_*` / `reason` | `_with_resolution`：无事件 `UNRESOLVED`、sequence 0、reason 空；肯定事件 `ACCEPTED`、三者非空；否则 `REVOKED`、`accepted_*` 空、`reason` 为撤销理由；`audit.py` 拒绝 sequence 0 上的 `REVOKE`，所以 `REVOKED` 时 sequence ≥ 2 | 与 §16.8 一致 |
| `details` union | 五个类型；`ArchiveSourceIssueDetailsResponse`（`states`、`edges`、`detected_status`）、`ArchiveTimeQualityDetailsResponse`（`generated_time`）、`ArchiveBaselineTimeDetailsResponse`（`generated_time` 可空、`comparison_status`）、`ArchiveTimeRegressionDetailsResponse`（`comparisons`）、空类型；`ArchiveGeneratedTimeResponse.status` 六值 | §16.3 的问题文字表覆盖全部 issue_code 与 status |
| 引用上限 | 确认 1、异常 1601（`8 × 200 + 1`） | 一致 |
| 理由 | `validate_utf8_reason`：1–4096 UTF-8 字节，不去空白；资源解析对接受与 `REVOKE` 都调用（`audit.py:208`）；**关闭也调用**（`compute_close_request_fingerprint`） | §16.4 正确；§16.6 缺上限（C2） |
| 关闭路由 | 201/200；409 六码；403/404/413/422/429/503；`CloseSubmissionResponse` 含 `closed_by/closed_at/reason/released_workspace_id/workspace_version` | 与 §16.6 一致 |
| 接受路由 409 | `IDEMPOTENCY_CONFLICT, BASELINE_VERSION_CONFLICT, CANDIDATE_SET_CONFLICT, CANDIDATE_BINDING_CONFLICT, ARCHIVE_AUDIT_VERSION_CONFLICT`；候选集变化、subject 不在当前预检时后端实际返回 `BASELINE_VERSION_CONFLICT`（`audit.py:255-284`） | 与 §16.4 一致 |
| review-events、archives 新 409 | 见 §2.1 第 16、18 行；archives 409 全集还含 `ARCHIVE_SCOPE_LIMIT_EXCEEDED`、`WORKSPACE_OCCUPANCY_CONFLICT` | §16.5 覆盖后者；前者走“其他沿用 FE2c”（非阻塞 N7） |
| V6 请求体 | 399 项异常引用 + 1 项确认引用，紧凑 JSON 约 43,258 B；全部 sequence 取 2^53−1、ID 取 255 字节时约 49,273 B；1601 项极端情况约 194,715 B | 都在 262,144 B 以内 |

### 3.2 §4.6 J1、J2 的预期异常（对照 `business_validation.py`、`queries.py`、`start.py`、`audit.py`、`manual_close.py`）

- **时间质量按上传侧检查：** `business_validation.py:148-153`：`initial_origin == "UPLOADED"`（FULL）检查 ① 与 ②，否则只检查 ②；与基线是否为空无关。合成 SQL 的 `version_manager` 只有 `project_id, build, no`（三份派生文件与 `sql-replacement-current.sql` 均如此），预期 `COLUMN_ABSENT` → `GENERATION_TIME_MISSING`。成立。
- **`BASELINE_TIME_UNAVAILABLE`：** `:120-124`：基线非空且无选定时间、候选非空时一项，受影响集合为本轮全部候选（按 submission_id 字节序）。空 `INITIAL` 时 `baseline_side` 为 `None`（`snapshot.py` 以 `baseline_is_initial` 绑定），无该项、来源 `NOT_APPLICABLE`。成立。
- **同级排除数目：** `_derive_anomalies`：选中项以外每个候选一项；`PROJECT_IDENTITY_EXCEPTION` 只在选中项有身份确认时出现。J1、J2 各步数目正确。
- **各步逐项（以 `reached` 闭包推演）：**

  | 步 | 推演 | 结论 |
  | --- | --- | --- |
  | J1-2 | 空 `INITIAL`：A ② 一项 | 1 项，成立 |
  | J1-7 | 基线 A；B ① = A → 可达；候选只有 B：B ①、B ②、BTU [B] | 3 项，成立 |
  | J1-11 | 基线 B；C 复用基线：C ②、BTU [C] | 2 项，成立 |
  | J1-13 | 基线 C；D 复用基线：D ②、BTU [D]、身份例外 | 3 项，成立 |
  | J2-3 | 基线 A；B ① = A；C 复用 A，`reached` 加入 C ②；E ① = C ② → 可达；时间 5 项 + BTU [B, C, E] + 同级 2 项 | 8 项，成立 |
  | J2-5 | 关闭 C 后：E ① 不在 {A, B ②} 中，E ② = B ② 已可达，连通分量只有 E ① → `INITIAL_SOURCE_UNEXPLAINED` [E]；时间 4 项 + BTU [B, E] + 同级 [E] | 7 项，成立 |
  | J2-8 | 基线 B；C 复用基线：C ②、BTU [C] | 2 项，成立 |

- **J2 第 3 步“E 的 ① 匹配 C 的 ②”：** 推演要求两者的 `canonical_state_digest` 与三个规则身份相同；同一组文件、同一规则下应当相同，kickoff 已列为假定并有停止规则。可接受。另：B 的 `matching_sources` 除“当前基线”外还会有“C 的 ①”（C 复用基线，`:130-138` 的同级匹配），概况列会多出一项来源，不影响比较集合。
- **J2 第 5 步的原因写法（非阻塞 N5）：** 每个 anomaly 的 subject payload 都含 `selection_subject_digest`，它由 `candidate_set_digest` 派生（`queries.py:349-420`），所以关闭后**全部**项重新派生、全部回到“未处理”，不只是受影响集合变化的 BTU。预期值不变（此前只接受过 BTU），建议改写原因，避免实施时误以为其余项会保留已接受状态。
- **J1 第 9 步的 409 码是确定的（非阻塞 N6）：** `start.py:177-194` 先调用 `_validate_audit_for_start`，B ② 最新事件为 `REVOKE` → `ARCHIVE_ANOMALY_UNRESOLVED`；`ARCHIVE_AUDIT_VERSION_CONFLICT` 只由审计追加（`audit.py:294-299`）产生，开始归档走不到；陈旧 sequence 在 `_validate_audit_refs` 中是 `CANDIDATE_BINDING_CONFLICT`。建议写定为 `ARCHIVE_ANOMALY_UNRESOLVED`。界面文案两者相同，不影响设计。
- **身份与权限：** 归档确认人（`archive_submission` + 两项读）可读候选、预检、接受、开始归档、关闭；s2 有 `withdraw_own_submission`，可读本人 C 的审核（J2-6）；s3（仅上传）只需上传、提交与读工作区；审核人退回、通过与三节点比较都有权限。都能做到，关闭另待 Q18。
- **实测校正规则（C3）：** “首轮不符即停、交设计会话”可执行，但比较口径要补两点，否则首轮必然误停：
  - `business_validation.issues` 只含三类业务 `subject_kind`；同级排除与身份例外只在 `anomalies` 中。表格把二者混在一起，需写明 `issues` 与表中去掉这两类后的集合比较，`anomalies` 与全表比较；
  - `anomalies` 只在预检带 `selected` 时非空（`_derive_anomalies` 首行）。写明每次比较用带选中项的预检。

### 3.3 过期通过（§16.7）

成立。`list_pending_review_facts` 只取当前基线下的提交（`snapshot.py:134-157`），有 `PENDING` 即阻塞归档；进行中的提交以 `ACTIVE_SUBMIT_ATTEMPT` 阻塞；提交本身对陈旧 Preview 返回 `BASELINE_VERSION_CONFLICT`。单 scope 正常操作中不会出现“基线已前移、提交仍待审核”，`review_transaction.py:138-144` 的 409 只是并发防护，由模拟接口覆盖合理。

### 3.4 t1（§8）

- **`baseline_to_initial` 的 `changed_table_count = 0`：** ① 与已归档的 v1 是同一目录、同一规则，规范内容相同，必然为 0（除非后端有缺陷），“不为 0 即停”合适。
- **`initial_to_modified` 沿用原预期：** 正确。原 MODIFIED_ONLY 的 v2 也是相对“内容即 v1”的基线比较，常量 `S2B_DATASET_BASELINE`、`S1B_V2_PREVIEW_CHANGED_COUNTS` 的对照关系不变。
- **按 `pair_id` 判定：** 可执行。后端 pair id 为 `baseline_to_initial`、`initial_to_modified`（`domain/workspace/models.py:445-446`、`preview_jobs.py:249-250`），默认视图 `initial_to_modified`（`pair_pipeline.py:73`）。
- **M1 复测指标：** `VmHWM` 增量方法与 `RssAnon`/`RssFile`/`RssShmem` 采样写清楚。**判定有问题（C1）：** §8.4“FE3c：…renderer 按 §8.4 的标准判断（t1 目录小，外推按目录大小线性计算）”。
  FE3a 在 t1 v1 MODIFIED 上测得 renderer 增量 24.86 MiB（FE3a handoff §6），目录 6,853,875 B，线性外推到 1 GB 约 3.5 GiB，**已超过 3 GiB**；FULL 打两个包，外推更大。
  小目录的增量主要是固定开销，按比例放大没有意义，照此判定会误触发“改为流式打包”。建议：FE3c 的 t1 复测只报告，并与 FE3a 的 t1 数值对照作回归检查；超标判断仍只用 t4（FE3a 结论）；打包代码在 FE3b/FE3c 中有改动时，按 §8.4 在 05 重测 t4。这改变 Q3/Q12 下的判定口径，需 owner 确认。

### 3.5 Q15–Q19

| # | 判断 |
| --- | --- |
| Q15 不补 `saved_time` | **成立。** 与 Q10 派生规则的含义一致；缺时间产生两侧独立项与 BTU，正是后端要求重点覆盖的；后端已确认生成时间预期（S3 协调 §16）。时间倒退等只由模拟接口覆盖，t1 有真实时间作补充。 |
| Q16 关闭入口放在归档对话框“候选提交” | **成立。** 候选查询与预检只对 `archive_submission` 开放（403），入口天然只对归档确认人出现；关闭所需基线取自同一次预检；V2 交接 §2“关闭不要求先接受异常”与 §16.2“有阻断项时仍显示”一致。 |
| Q17 t1 第 4 步改 FULL | **成立**，判据见 §3.4；需同时处理 C1。 |
| Q18 | **状态写法与 S3 协调 §16 一致：** FE3c 前置为“补缺已交付（固定的 Contract/OpenAPI 与后端独审结果）”（§3.2、§10、§13.5）；§16.6 写明“补缺交付前不定稿，模拟数据不加该字段”；前端不写死、不推断、不追加审核权限（§10、§16.6、§11）。后端答复不是实施授权这一点也已写明。 |
| Q19 不另画草图 | **成立。** FE2 的归档对话框同样无草图；§16.2 线框与 §16.3 文字规格足以确定位置与层级，§9 列出的截图交 owner 看图确认。对话框内容增加较多，若 owner 希望先看排版，按 Q19 的备选补草图。 |

### 3.6 §13.5、§13.6、§15.3

- **§13.5：** 前置写明 `fe-fe3b-exit`、Q15–Q19 确认、Q18 补缺交付且 §16.6 定稿；占位 `[补缺交付提交]`、补缺后 OpenAPI 路径与 SHA256 由审核会话填写；`--print-input` 的 tag 以现场核对为准。可以执行。
  建议同时在 §5.1、§10 注明“FE3c 的比对原件按 §13.5”，避免两处仍写 `977b2258…` 造成矛盾（非阻塞 N8）。按 B1 甲，FE3c 合入时会同时带入 S3 的 `vnext/`，届时依赖镜像需预填充，建议在 §4.3 预先写明（非阻塞 N8）。
- **§13.6：** 占位清楚；四个探针前提可行；t1 只核日志与截图 SHA256 合理。
- **§15.3：** 覆盖核对报告 §8.1 第 1 项（并写明改正）、§3.3/§8.3 的 R8、关闭旅程、关闭入口、t1 FULL 与 M1、截图清单，以及 FE3b 评估交接 §3、§4.1、§4.2 与 V2 交接 §2。没有漏项。

### 3.7 第 2 步意见汇总

| # | 意见 | 负责 |
| --- | --- | --- |
| **C1** | §8.4 FE3c 的 t1 M1 不按线性外推判定：只报告并与 FE3a t1 对照；超标判断沿用 t4；打包代码有改动时重测 t4（§3.4）。 | 交设计会话；判定口径交 owner 确认 |
| **C2** | §16.6 关闭理由补“超过 4096 个 UTF-8 字节时禁用”（同 §16.4 的规则与计数显示）；§2.3 第 14 行“非空 `reason`”改为 1–4096 UTF-8 字节。 | 交设计会话 |
| **C3** | §4.6 实测校正写明比较口径：`issues` 与去掉同级、身份两类后的表比较；`anomalies` 与全表比较；预检带 `selected`。 | 交设计会话 |
| N5 | J2 第 5 步改写“回到未处理”的原因（全部 subject 随候选集重新派生）。 | 交设计会话 |
| N6 | J1 第 9 步写定 `ARCHIVE_ANOMALY_UNRESOLVED`。 | 交设计会话 |
| N7 | V6 写明构造方式（空 `INITIAL`、① 有效时间、② 缺时间），保证 399 项可达；`ARCHIVE_SCOPE_LIMIT_EXCEEDED` 是否需要专用文案由设计会话定。 | 交设计会话 |
| N8 | §5.1、§10 注明 FE3c 比对原件按 §13.5；§4.3 写明 FE3c 合入新 main 后需要的依赖镜像预填充。 | 交设计会话 |

## 4. 后续

1. **owner：** 选定 B1（推荐甲：FE3b 合入 `748de5034d`）；确认 Q14；第 2 步时确认 Q15–Q19 与 C1 的判定口径；安排 Q18 后端补缺。
2. **设计会话：** 按 §2.8 修订第 1 步（B1–B3 必改，N1–N4 建议），按 §3.7 修订第 2 步（C1–C3 必改，N5–N8 建议）。第 2 步的修订可在 FE3b 实施期间进行。
3. **本会话：** 对第 1 步修订做定向复核；通过且 owner 确认 Q14 后，按 §13.3 前置现场核对（接口、依赖镜像 tag 与身份、RS 依赖镜像、工具链、npm 缓存、04/05/07 占用），填写占位后发出 FE3b 实施提示词。
4. **FE3c 提示词**在 `fe-fe3b-exit` 之后、Q18 补缺交付、§16.6 定稿、第 2 步复核通过且 owner 确认以后才发出。

## 5. 操作记录

- 开发主机：`git worktree add --detach /home/dev/gdds-reviews/fe3-kickoff-rev2-review-wt 5ff82b303e`（只读阅读）；在 scratchpad 中以 `git archive` 取两份最小输入运行 `--print-input`（读取本机基础镜像，未构建、未改 worktree）。
- 节点（只读，07:13Z 与 07:22Z 两次）：`ssh -o BatchMode=yes … 'echo OK'`；`docker image ls/inspect`（含 `ctr -n moby content get` 读 manifest 的 config digest）；`ls`；npm 归档与 t1 清单 `sha256sum`、目录内 `sha256sum -c --quiet`。
  核对脚本对 04、07 上不存在的 `source-dirs/` 执行 `ls` 返回非零（04/07 本就没有 t1 目录），属本会话命令的预期结果，无副作用。
- 未取占用标记，未运行测试、Compose、构建或浏览器；未改 kickoff、源码与节点状态。

## 6. owner 答复（2026-11-08）

- **B1 选甲：** FE3b 合入 `748de5034d`（`vnext/` 树 `56720104af`，依赖镜像 `lock-d054366c02fa`）。FE3b 期间不再合入 main；FE3c 开始时连同 Q18 补缺合入当时的 main。
- **Q14：** 同意设计会话的建议（§2.6）。
- **后端并行：** S3、S4 可以继续在 main 上推进。`748de5034d..d076903d7f` 中 main 只改了 `docs/frontend-vnext/` 下的 kickoff 与本报告，没有改 `frontend/`。
- **镜像：** 允许按需在节点间拷贝。FE3b 按甲不需要新镜像；FE3c 需要新依赖镜像时，按 AGENTS 记录来源与身份（config digest 与全部 DiffID）。

对实施条件的影响：

- 后端改 main 不影响 FE3b：路径核对以 `748de5034d` 为 `<main>`，候选 `vnext/` 树应为 `56720104af`。后端若改了 `frontend/` 或 `docs/frontend-vnext/`，FE3b 不受影响；到 FE3c 合入时这些改动进入 FE3c 审核范围（同 `55d56efb6e` 的例外）。
- FE3b 的证据绑定 `p6-be-a-d-exit` 的 backend 树。`fe-fe3b-exit` 合回 main 后，FE3b 前端与 S3 backend 的组合要到 FE3c 才在真实 backend 上验证。
- 05 与 04 上前端真实 e2e 与后端运行按 DC70 占用标记互斥；用途为计时测量时前端等待。
- 仍需完成：设计会话修订 B1（按甲改写 §2.1、§3.2、§4.3、§10、§13.3）、B2、B3；本会话定向复核；之后现场核对并发出提示词。
