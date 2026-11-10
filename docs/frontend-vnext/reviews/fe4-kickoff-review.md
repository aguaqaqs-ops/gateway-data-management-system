# FE4 kickoff 审核

- **审核对象：** 分支 `fe4-kickoff`，范围 `16ffe72829..79ccde87d6`（`e0082180e0` 新增 `fe4-kickoff.md`；`79ccde87d6` 改前端 kickoff §7、§9 与 FE3 kickoff §11 Q21、§12）。
- **审核会话：** 按 AGENTS“角色与子 agent”新建，只读，只写本报告。审核日期 2026-11-10（UTC）。
- **方法：** 只用 `git show`、`git diff`、`git grep`、`git rev-parse` 等静态读取；没有建 worktree 运行任何东西，没有登录测试节点，没有生成 OpenAPI（第 2 项的静态方法已足够下结论）。十六进制回源用开发主机上的一次性 `python3 -I` 脚本（放在会话 scratchpad，不入库）。
- **结论：定向修订。** 阻塞 2 项（B1、B2），非阻塞 11 项（N1–N11），交 owner 5 项（D1–D5）。FE4a 的合入点、`vnext/` 树、依赖输入与“HTTP 无变化”的结论经独立核对成立；阻塞项都是文档事实与范围写法，不涉及重新设计。

## 0. 审核期间的工作区与 reflog

| 对象 | 核对 | 结果 |
| --- | --- | --- |
| `/home/dev/gdds-fe4-kickoff`（`fe4-kickoff`） | reflog | 03:51:35 建在 `16ffe72829`，03:58:46 提交 `e0082180e0`，03:59:28 提交 `79ccde87d6`；之后无切换。worktree clean |
| `/home/dev/gdds-s5-design-main`（`main`） | reflog、status | 只有 merge 记录：03:35:29 快进到 `16ffe72829`，**03:54:14 合入 `p7-s1a-a` 得 `00ca325c2e`**；无 checkout。clean |
| `/home/dev/gdds-fe`（`fe-vnext`） | reflog、status | 停在 `e22e39ba15`（01:56:47 提交），无切换，clean |
| 主工作区（`fe3b-evidence-04`） | reflog | 最后一次 checkout 为 2026-11-09 03:43:46，审核期间无切换 |

## 1. 当前事实（草案 §2）

**方法：** 逐项 `git rev-parse`、`git cat-file -p`、`git merge-base --is-ancestor`，并用脚本把草案中每个十六进制值回到 git 对象或来源文档（见第 10 项）。

| 草案陈述 | 核对 | 结论 |
| --- | --- | --- |
| `fe-fe3c-exit` 对象 `43e66d3eb7` → `06b454b0ef`；被测 `e22e39ba15`；`frontend/` 树 `46e425f84e` | `git cat-file -t`、`rev-parse` | 成立；`06b454b0ef` 的父提交是 `e22e39ba15`，只新增 `fe3c-evidence-04.md` |
| main 合入提交 `475022300c`、退出记录 `16ffe72829`；main 在 tag 合入后没有 `frontend/` 改动 | `git log`、`git diff 475022300c 16ffe72829 -- frontend` | 成立（diff 为空） |
| `16ffe72829:vnext` = `p6-exit^{commit}:vnext` = `49c1de43be` | `rev-parse` | 成立；`p6-exit` 对象 `e4791d4e8d` → `b0fc25e881`，tag 说明原文与草案引用一致，未推送 |
| `fe-vnext` 能快进到 `16ffe72829` | `merge-base --is-ancestor e22e39ba15 16ffe72829` | 成立；`e22e39ba15` 不是 `b0fc25e881` 的祖先，草案“用 `p6-exit` 目标快进不到”成立 |
| `frontend/openapi.json` SHA256 与 FE3c 原件 | `git show 16ffe72829:frontend/openapi.json \| sha256sum`；`fe3c-handoff.md` §3 | 成立（`4c2ddca7…620a`；原件 `ce58f20a…c079`） |
| 工具链 config digest、npm 归档与来源提交 `a2fb4a027a` | `fe3c-evidence-check-1.md` §4 第 85 行、`fe3c-handoff.md` §9.2 | 成立（来源提交的写法与 FE3c 证据一致；FE0 handoff 记录原始生成提交为 rebase 前的另一提交，与此不矛盾） |
| 占位与浏览器计算的代码位置 | `git grep` | 成立；`fallbackNavigation`（`model.ts:295`）、`snapshotRowIdentity`（`table-rows.ts:170`）、`NAVIGATION_COPY` 10 项。占位 fixture 另有一个 `projections/business-navigation/diagnostics.json`，草案未列（N8） |
| `fd9e383d76..16ffe72829` 的 `vnext/` 72 个文件 | `git diff --name-only \| wc -l` | 成立；但 §6.2 的分类不完整（N1） |
| **main = `16ffe72829`** | `rev-parse main`、reflog | **审核时不成立。** 本地 main 已于 03:54:14（草案提交前 4 分钟）合入 `p7-s1a-a`，得 `00ca325c2e`，未推送（远端跟踪 ref 仍为 `16ffe72829`）。新增 20 个文件，全部在 `docs/backend-vnext/` 下：P7 总体设计、执行计划、S0 决议、S1a 设计与执行计划、S1a-A 入口与验证脚本，以及 9 份 Contract 的“P7-S1a 目标补充（待实现）”。`00ca325c2e:vnext` 仍为 `49c1de43be`；`AGENTS.md`、`docs/frontend-vnext/`、testing-conventions 未改。见 B1 |
| “P7 设计与执行计划只是开发主机上未提交的草稿”（草案头部、§2.3、§4、Q5） | `git show 00ca325c2e:…/p7-s0-owner-decisions.md` | **审核时不成立。** 它们已提交在本地 main。S0 决议头部写“S0 已收口；Owner 已确认分组/抽取阶段安排，授权下一编码会话推进 S1a A–G 至本地 exit”。P7 文档中没有 BE-b 字样。见 B1、D1 |

**合入点写法的评估：** `00ca325c2e` 的 `vnext/` 与 `16ffe72829` 相同，FE4a 的被测后端不受影响；固定用 `16ffe72829` 仍然正确（它不带 P7 文档，路径核对更简单）。但草案的理由“之后的 main 可能含 P7 代码”已经过时，应改成实际事实；并在 §11.1 前置条件中写明“发提示词时由审核会话重核”：`fe-vnext` 仍为 `e22e39ba15`、`p6-exit` 仍指向 `b0fc25e881`、main 当前头与其 `vnext/` 树（只记录，不改变合入点）。并入 B1 的改法。

## 2. 后端变化对前端的影响（草案 §6.2、§6.3）

### 2.1 按路径的实际改动

`git diff --name-status fd9e383d76 16ffe72829 -- vnext`，72 个文件：

| 区域 | 文件 | 草案是否提及 |
| --- | --- | --- |
| `backend/benchmarks/` | 4（2 新增） | 提及 `real_dump_journey.py` |
| `application/` | `canonical_metadata/table_access.py`、`history/compare_jobs.py`、`pair_pipeline.py`、`preview_jobs.py`、`submission/finalize_transaction.py`、`submission/ports.py` | 只概括为“History、Preview、Submit 与 checkpoint”，`canonical_metadata`、`pair_pipeline` 未提 |
| `artifacts/` | `computation_cache.py`（新增）、`snapshot_table_export_cache.py` | 提及 |
| `bootstrap/operation_worker.py` | 1 | 未提 |
| `capabilities/comparison/` | 6（3 新增） | 提及 |
| `capabilities/risk_evaluation/` | 4（2 新增） | 提及 |
| `capabilities/snapshot_materialization/` | 5 | **未提** |
| `infrastructure/control_db/` | 7（1 新增） | 概括为 control DB |
| `infrastructure/repository_read/` | 2 | **未提** |
| `repository_client/src/` | 5（`arrow_stream`、`client`、`deadline`、`errors`、`retry`；请求改受调用方期限约束） | **未提** |
| Rust | `comparison/mod.rs`、`lib.rs`、`records.rs`、`records/{builders,cache,facts}.rs`、`gateway-compute-python/src/comparison_records.rs` | 只写“Rust `records/` 改了 3 个” |
| 测试 | 23 | 概括提及 |

`http/`、`domain/`、`capabilities/{bundle_assembly,surface_assembly}/`、`vnext/fixtures/`、`deploy/`、`application/workspace/`、`settings.py`、`app.py`、`vnext/scripts/`、两个 backend Dockerfile、`repository_service/` 均无改动，与草案一致。

### 2.2 DTO、错误码、枚举与 OpenAPI 的来源是否只在 `http/` 下

不只在 `http/` 下，所以按路径判断需要补一步导入闭包核对。我做了这一步：

- OpenAPI 由 `app.py` 的 FastAPI 应用、`http/routes/` 与 `http/schemas/` 生成。routes 与 schemas 导入的非 `http` 模块是 `application/{archive,history/contracts,job_definitions,submission/contracts,submission/review_contracts,submit_registry,workspace/preview,workspace/services}`、`domain/{archive,submission,workspace}`、`operations/contracts`，**都不在 72 个文件中**。
- 整个 `http/` 导入的非 `http` 模块中，只有两个改了：`application/history/compare_jobs.py`（`http/orchestration/history_compare.py` 使用的 `HISTORY_COMPARE_STEP_ASSEMBLE`、`history_compare_step_id`、`history_compare_assemble_state_from_checkpoint` 三者在两棵树中逐字相同）与 `application/submission/ports.py`（Protocol 新增 `touch_computation_cache_producer`，不是 schema）。
- 前端模拟数据可达性表（`features/dev/mock-data.ts::SIMULATED_STRING_VALUES`）引用的 13 个后端来源中，只有 `preview_jobs.py` 在改动集合里，其 `PREVIEW_JOB_KIND` 不变。

**结论：** 运行时 `/openapi.json` 预期不变，草案 §6.3 甲（FE4a 不要新原件、靠运行时比对）的依据成立。不需要运行产品生成 OpenAPI。

### 2.3 “诊断码只是搬移”

- **码集合：** 抽取两棵树 `backend/src`、Rust、`repository_client/src`、`shared_kernel`、`repository_contracts/src` 中全部 `"[A-Z][A-Z0-9_]{4,}…"` 字面量，`fd9e383d76` 983 个、`16ffe72829` 985 个；删除 0，新增 2：`CHECK_RECORDS_CLOSURE`（`__all__` 中的内部符号名）与 `RISK_CANDIDATES_FORMAT`（值为 `risk-table-candidates/v1` 的常量名）。都不是诊断码。
- **产生条件：** `ORDERED_PROVENANCE_MISSING`、`ORDERED_PROVENANCE_INVALID` 从 `production.py::_ordered_policy` 移到 `task_input.py::ordered_policy`，函数体逐行相同。
- **写入位置：** 新增的调用点有两处。① 缓存身份 `build_table_task_identity` 捕获 `ValueError`/`StandardComparisonError` 并返回 `NotCacheable("incomplete-semantics")`，只关闭缓存，不提前失败；② 逐表路径 `_compare_task_native` 的 `native_input()` 照旧抛出，由原有的逐表降级出口写入 surface 表诊断。结论与 Q21 答复 §3.1 的出口一致。`ValueError("row_diff_detail_policy is invalid")` 同样只能以类名出现，草案判断成立。

**结论：** “诊断码只是搬移”成立。

### 2.4 草案没有写到的一处 operation 行为变化（N2）

`compare_jobs.py` 的 assemble 步骤在 S5/S6 改为按需读取行（`_ensure_history_demands_once`），旧树 assemble 只处理取消；新树 assemble 新增两类终态发布：`HistoryCompareInputError`（`CommitCanonicalMetadataError` 的码，或 `HISTORY_COMMIT_UNAVAILABLE`）与**不可重试的** `RepositoryProviderError`（以其 `code.value` 作为诊断码；旧树 materialize 对此是 `assert exc.retryable`）。因此 `HistoryCompareResultResponse.diagnostic.code` 的可达取值在 assemble 阶段扩大了。前端只显示 `diagnostic.message`，不按码映射；模拟数据可达表只列 `HISTORY_RULESET_VERSION_MISMATCH`，仍是可达子集。所以没有渲染影响，但草案 §6.2 第 4 行“无前端可见变化”的依据不完整，应写明这一点。

### 2.5 依赖输入

`build-backend-dependency-base.sh` 的 tag 输入是五个文件的 SHA256、Python/uv/Rust selector、基础镜像名与基础镜像身份（config digest 与 DiffID）。五个文件、脚本本身、`backend/Dockerfile.dependency-base`、`backend/Dockerfile` 与 `repository_service/uv.lock` 在 `fd9e383d76..16ffe72829` 中 blob 均不变。只要节点上 `rust:<channel>-bookworm` 的身份与 FE3c 时相同，`--print-input` 必然仍得 `lock-578e079b762e`。草案“以发提示词时所选节点上的实测为准”的写法正确。

## 3. 范围是否完整（草案 §3）

**方法：** 逐条对照 `16ffe72829:docs/frontend-vnext/fe3-kickoff.md` §3.2 第 299–313 行（交 FE4 kickoff 的非阻塞项）与各审核报告原文。

| 来源 | 原文位置 | 草案 | 结论 |
| --- | --- | --- | --- |
| FE3b N2 | `fe3b-rereview-2.md:187`、`fe3b-rereview-3.md:117` | C1 | 一致 |
| FE3b N6 | `fe3b-rereview-3.md:120` | C2 | 一致 |
| FE3b N7 | `fe3b-evidence-check-1.md:117` | C3（三张截图名在 `upload-mode.spec.ts:546,551,594` 存在） | 一致 |
| FE3b N8 | `fe3b-evidence-check-1.md:121` | C4 | 一致 |
| FE3c N2 | `fe3c-review.md:197` | C5 | 一致 |
| FE3c N3 | `fe3c-review.md:198`；另并入 `fe3b-rereview-1.md:256` N2（单行长理由） | C6 | 一致；但草案头部“依据”没有列 `fe3b-rereview-1.md`（N8） |
| FE3c N4 | `fe3c-review.md:199` | C7 | 一致 |
| FE3c N5 + M1 | `fe3c-review.md:200`、`fe3c-rereview-1.md:155` | C8 | 一致 |
| M2 | `fe3c-rereview-1.md:156` | C9 | 一致 |
| M3 | `fe3c-rereview-1.md:157` | C10 | 一致 |
| N9 | `fe3c-evidence-stop-1.md:100`（11 处 `unrouteAll()` 已用 `git grep` 核对） | C11 | 一致 |
| Q21 | `d3450675bf` 答复 §4 末段 | §3.5 | 一致；文案表与答复的建议逐项对应 |

没有遗漏、合并或误改。M4 与 FE3c N1、N6、N7 在 FE3 §3.2 中标为“已处理、不带入”，草案没有重复列入，正确。

其他来源：

- 前端 kickoff §3.3：分组/列展示 → B1–B3、B9；历史初始备份节点 → §3.7（Q8）；首批空基线 → §3.7（Q9）；复合信号公式 → B7。完整。
- 前端 kickoff §4.5、§4.6 → B9、§3.2（Q6）。完整。
- 前端 kickoff §6“FE4 重拍一次关键页面” → §3.3 FE4b。完整。
- 前端 kickoff §9：侧栏层级、`diagnostics_summary` 已处理；**“P6 计时是否包含整包传输”一行的阶段写的是 P6，P6 已在本地退出，DC74 仍是草案，草案没有处置**（N7、D5）。
- FE3 kickoff §12 中标为 FE4 的两行（重拍节点、`--color-warning-soft`）与 §14 的 BE-b 各项均已覆盖；§12 的“P6 计时与整包下载（DC74 草案）”一行同上，未处置。

## 4. BE-b（草案 §2.3、§3.1、§4、§5.3）

1. **`diagnostics_summary` 自由文本并入 BE-b 是否有据：有据。** BE-b 草案 §4.10 与 §6 Q10 由 `022ab5042d`（2026-11-03 03:14 UTC）写入，提交说明写明“Owner confirmed 2026-11-03 (FE2 kickoff Q6-Q9) … stable codes for free-text entries folded into BE-b (draft 4.10)”；前端 kickoff §5 BE-b 行（第 143 行）已写“诊断稳定编码（owner 2026-11-03，FE2a 审核 D1–D3，BE-b 草案 §4.8–§4.10）”；FE2 kickoff §5.5（第 278 行）同样指向 §4.10。前端 kickoff §9 那一行是 `80de06ab5c`（2026-11-02）写的，早于该决定。§4.10 列的三类（异常类名、风险引擎英文短句、`DUPLICATE_EFFECTIVE_KEY:<表名>`）覆盖了 §9 举的两个例子。**`79ccde87d6` 的更正正确。**可在更正文字中补引前端 kickoff §5 与 FE2 kickoff §5.5，便于回源（可选）。
2. **第二步与实施的前置能否执行：** FE4b 的前置（BE-b 退出并合入 main、§4 六项交付齐全、本文第 2 步经审核与 owner 确认）写法可执行。但 §4 的交付清单只要求 OpenAPI 差异；P7 S1a 的目标补充把 `artifact_id` 改为新格式、bundle 改为多 root 交付并会传递改变 surface/bundle 摘要（`00ca325c2e` 上 `comparison-bundle.md` 末节、`p7-s1a-a-entry-and-contract.md` 第 114 行）。若 BE-b 交付的树包含这些改动，前端的 bundle 解析、互通 fixture 与生成器都会受影响，而 OpenAPI 看不出来。建议 §4 增加一项：bundle 传输、manifest、ArtifactRef 与 surface 相对 `6368c9c40c` 的变化说明，以及新的互通 fixture（并入 B1 的改法）。
3. **Q4、Q5 与 FD8、P6 退出状态：** Q4（第二步由后端设计会话写，前端核对面向前端的部分）与 FD8“P6 退出后实现、Phase 8 前完成”一致。Q5 的建议以“P7 的计划尚未提交”为前提，审核时该前提不成立：P7 S0 已收口、S1a 编码已获授权，且 S1a 本身就改 bundle/surface 的引用与摘要。“在 P7 改动 Preview/History 组装或产物的阶段之前先固定 BE-b”已经无法照字面执行。另外 P6 退出 tag `p6-exit` 仍未推送，Q2 已注明。见 B1、D1。

## 5. 拆段（草案 §5）

- **互不重叠、独立验收：** FE4a（归档对话框、续做提示、诊断文案、令牌、测试、取证工具）与 FE4b（导航、列、行定位、fixture）改动面基本不重叠；两段各有前置、退出 tag、审核范围与退出条件，可以独立验收。路径核对（`<候选>:vnext` 等于 `<main>:vnext`，diff 只含 `frontend/` 与 `docs/frontend-vnext/`）可执行。
- **唯一的重叠点（B2）：** §5.2 FE4a 行与 §11.1 范围第 6 项要求 FE4a“固定 FE4b 正式重拍用的截图清单”，而 §3.3 写“暂定页面如下，第 2 步定稿”，清单中的侧栏分组、装置页签、中文列名、行定位连线在 FE4a 的后端上并不存在。FE4a 实施会话无法照此完成，审核会话也无法判定“已固定”。
- **FE4a 在新后端树上重跑的理由：** 充分。`49c1de43be` 对 FE4a 是被测后端：S5 计算缓存改变了 Preview/History 的执行路径，S6 改了 History 元数据与 assemble 读取（第 2.4 节），`repository_client` 改了请求期限。只靠运行时 OpenAPI 比对不能证明真实旅程仍通过。范围（`journeys` 完整集与 `t1`）与 C7 改真实旅程本身也相符。是否需要在 FE4a 调试与证据中各跑一次完整集，见 N6、D2。
- **正式重拍放在 FE4b：** 符合前端 kickoff §6“FE4 … 重拍一次关键页面作为证据”与 FD7。FE4a 的 t1 截图只作参考、不作验收，写法正确。
- **前端 kickoff §7 FE4 行与 §9：** 与 §5.2 一致，并注明“待 owner 确认”。

## 6. 测试与证据（草案 §7、§8）

- **节点、占用：** 与 AGENTS（`16ffe72829`）一致：五节点池、所有前端运行原子取标记、`run-real-backend-e2e.sh` 自管标记（外层重复获取 exit 3）、计时测量期间不运行其他任务、`GATEWAY_FE_TEST_WORKERS=2`、拓扑说明。节点建议只作建议，不是固定用途，写法正确。
- **证据项与截图范围：** 符合 FD7（1280 与 1920、截图在 worktree 外并记 SHA256、对照 sketches，不做像素级比对）。FE3c 证据截图清单 SHA256 `63a0e600…29f2` 回源到 `fe3c-evidence-04.md:83`。
- **DC68（N3）：** AGENTS 原文（“专用测试节点”节第 68 行）为“首次失败后，同一具体故障允许最多三轮自行修复、适用独审与受影响步骤复验；不因被测对象已经运行就立即交 owner。每轮先停止该次执行、保留原始失败及日志/SHA、确认收尾，再固定修订稿复验；三轮仍未解决、原因/副作用不明或超出既有授权时交 owner。不得无修改自动重试、改预期掩盖结果或跳过身份/缓存前提；产品 finding 按阶段已有修复与停止规则办理。只读后处理/预检、代码传输准备的不计次数澄清继续适用。”草案 §7.2 的“三轮”与适用范围（工具/取证错误；产品问题走审核流程）正确，但漏了：适用独审、确认收尾、固定修订稿复验、不跳过身份/缓存前提、不因被测对象已运行就立即交 owner、只读后处理与代码传输准备不计次数。
- **§7.4 打包代码路径：**
  - 更正正确：`features/upload/` 在 `fe-fe3b-exit`、`fe-fe3c-exit`、`09351e42ad`、`16ffe72829` 中都不存在；打包代码在 `features/workbench/upload-package.ts`（`collectLocalDirectory`、`buildTar`、`buildSourcePackage`，无外部导入）与调用它的 `features/workbench/UploadStepCard.tsx`。
  - FE3 kickoff §11 Q23 理由 ② 的路径写错了，但**结论仍然成立**：`git diff --stat fe-fe3b-exit fe-fe3c-exit` 与 `fe-fe3b-exit 09351e42ad` 对这两个文件都为空。FE3c 不需要在 t4 上重测 M1，FE4 也不需要补测。
  - 顺带核对 FE3b：`fe-fe3a-exit..fe-fe3b-exit` 只有 `087281ce65` 改了 `UploadStepCard.tsx`，内容是给“上传并生成预览”按钮加 `occupancyReason` 禁用，不涉及打包流程；FE3b 同样不需要 t4 重测。
  - 但这说明 §7.4 用“两个文件的 `git diff --stat` 非空”作触发条件会误触发（C1 若在上传开始处清除提示，就可能改到 `UploadStepCard.tsx`）。见 N4。
- **§7.5 与 §11 的两条教训：** §3.8、§7.5 与 §11.1“日志与回源”都写进了 wrapper 写日志前检查参数（含 FE3c 的 `LOG_DIR` 取成 `$2` 的教训）与 handoff 十六进制值脚本回源（含 FE3b 5 个 SHA 抄错的教训）；§11.2 第 4、7、9 项有对应探针与核对。完整。wrapper 的占用检查细节见 N10。

## 7. 提示词草稿与交接（草案 §11、§12）

- FE4a 实施、FE4a 审核、FE4b 都写明由新会话承担，FE3 会话与另一子阶段的会话不接；同一子阶段 finding 由原审核会话连续复审。符合 AGENTS“角色与子 agent”。
- 交接材料：§12 列出的文件在 `16ffe72829` 上全部存在（`fe3b-evidence-04.md`、`fe3c-evidence-04.md`、`fe3c-handoff.md` 及 fix1、fix2、各审核报告；`fe3c-handoff.md` §5.5 与 testing-conventions 的“前端测试（FD7）”“真实 backend e2e”节存在）。小误：§12“未测”一行把“过期 `APPROVE` 409 只由模拟接口覆盖”归到 FE3 kickoff §4.7，实际在 §15.3（第 1401 行）；§4.7 只写了提交 403 与“仍在运行”/`MANUAL_RECOVERY_REQUIRED`（N8）。
- 发提示词的前置条件：Q1、Q2、Q3、Q7、Q10、节点与镜像核对、`--print-input` 都写在 §11.1 标题中，可核对。缺“重核 main 与 `p6-exit`”（第 1 项），以及 §11.1 范围第 6 项不可执行（B2）。

## 8. owner 问题（草案 §10）

- **建议、理由、不采用方案的代价：** Q3、Q6、Q7 三项齐全。Q1 的“不拆的代价”在 §5.1、不在表中；Q10 只写了“只能引用提交号”。**Q2、Q4、Q5、Q8、Q9 没有写不采用方案及其代价**（N5）。
- **不能由设计会话决定的事项：** 草案已列使用未推送的本地 P6 退出树、Q4/Q5 后端分工与排期、Q8/Q9 业务需要、Q10 合入与推送、两段退出的 tag/合入/推送。齐全。
- **缺少的问题：**
  1. P7 S1a 已获授权编码，BE-b 与它的先后与衔接（D1，取代 Q5 的现有前提）；
  2. FE4a、FE4b 的真实数据范围确认：AGENTS“主线开发与阶段边界”与 DC33、DC98 要求真实范围在 kickoff 写明、阶段退出前由 owner 确认，且“不默认完整旅程或重复性能采样”（D2）；
  3. 是否需要在 FE4a 证据前推送 `p6-exit` 与 main，或接受证据只绑定本地树（D3；Q2 只写了“注意”）；
  4. 前端 kickoff §9“P6 计时是否包含整包传输”与 DC74 草案在 P6 退出后的去向（D5）。

## 9. 同分支对旧文档的修改（`79ccde87d6`）

- 改动范围与草案 §13 一致：前端 kickoff §7 FE4 行、§9 两行；FE3 kickoff §11 Q21 一行、§12 三行。共 7 行改动，没有其他改动。
- 没有改写历史记录：FE3 §3.2 退出记录、Q18–Q20、Q22、Q23 未动；§12“FE4 真实数据重拍的节点”保留原文，只在末尾追加“已由 DC91 关闭”。
- 措辞与新事实一致，只有一处：FE3 kickoff Q21 的状态列写“前端文案在 FE4a 修改”，§12 两行的阶段列写“FE4a”，都默认 Q1 已按拆段决定；前端 kickoff §7 行则注明了“待 owner 确认”。建议这三处同样注明“拆段待 owner 确认（FE4 kickoff Q1）”（N9）。

## 10. 十六进制核对

**方法：** 一次性脚本读取草案全文与 `79ccde87d6` 的全部新增行，提取长度不少于 7 的十六进制 token（排除纯数字），对每个值：长度不超过 40 时 `git rev-parse --disambiguate` 要求唯一命中并记录对象类型；再在 `16ffe72829` 与 `d3450675bf` 的 `docs/`、`AGENTS.md`、`frontend/openapi.json`、`frontend/src/features/view-model/` 文本与 `p6-exit`、`fe-fe3c-exit` tag 说明中查找原文。

- **草案：** 26 个不同值，全部回源。git 对象唯一命中 19 个（commit 12、tree 5、tag 2）；64 位值 5 个（`openapi.json` 规范化结果、FE3c 原件、工具链 config、npm 归档、FE3c 截图清单）均在来源文档中原样出现，`openapi.json` 另经 `sha256sum` 现场重算一致；12 位 tag 后缀 `578e079b762e`、`6dc9659f0aee` 在 FE3 kickoff 与后端交接中原样出现。8 位的 `e22e39ba` 出现在证据目录名 `fe3c-e22e39ba/` 中，唯一命中提交 `e22e39ba15`。**无未命中值，无长度异常值。**
- **`79ccde87d6` 新增行：** 3 个不同值（`56720104af`、`6368c9c40c` 为 tree，`d3450675bf` 为 commit），全部唯一命中。无长度异常值。
- **本报告：** 提交前用同一脚本核对，结果见文末附录。

## 11. 问题清单

### 阻塞（B）

**B1 main 与 P7 的事实过时，Q5 的前提不成立。**
依据：草案头部第 18 行、§1 第 2、4 条、§2.2 main 行、§2.3 末条、§4“与 P7 的衔接”行、§6.1“不合入之后的 main”、§9 第 2 条、§10 Q5；对照 `git reflog main`、`00ca325c2e:docs/backend-vnext/refactoring/formal/plans/p7-s0-owner-decisions.md` 头部、`00ca325c2e:docs/backend-vnext/contracts/comparison-bundle.md` 末节、`p7-s1a-a-entry-and-contract.md` 第 114 行。
改法：
1. §2.2 写明本地 main 已为 `00ca325c2e`（2026-11-10 03:54 UTC 合入 `p7-s1a-a`，未推送），新增内容全部在 `docs/backend-vnext/`，`vnext/` 仍为 `49c1de43be`；FE4a 仍固定用 `16ffe72829`，理由改为“它是 FE3 退出记录且不带 P7 文档；之后的 main 已有 P7 S1a 的设计与 Contract 目标补充，S1a 编码已获授权，随时可能带入 `vnext/` 改动”。
2. 头部“不作依据”与 §2.3 改写为事实：P7 S0 决议与 S1a 设计已提交在本地 main、未推送，S0 决议写明 owner 已授权 S1a A–G 编码；P7 文档未提及 BE-b。是否以这些文档作为 BE-b 排期依据交 owner（D1），前端设计会话不据此推导 BE-b 设计。
3. Q5 改写：去掉“P7 的计划尚未提交”与“在 P7 改动 Preview/History 组装之前先固定 BE-b”的前提，写明 S1a 本身改变 `artifact_id` 格式、bundle 交付与 surface/bundle 的物理元数据摘要；请 owner 决定 BE-b 第二步以 S1a 之前还是之后的树为基础、两者的先后，具体评估仍由后端设计会话做。给出不采用各方案的代价。
4. §4 交付清单增加一项：bundle 传输、manifest、ArtifactRef 与 surface 相对 `6368c9c40c` 的变化说明（含届时已合入的 P7 改动）与重新生成的互通 fixture。
5. §11.1 前置条件增加：发提示词时由审核会话重核 `fe-vnext` 仍为 `e22e39ba15`、`p6-exit` 仍指向 `b0fc25e881` 且 `vnext/` 为 `49c1de43be`，并记录 main 当前头及其 `vnext/` 树；FE4a 合入点不随之改变。

**B2 FE4a 要求“固定 FE4b 重拍的截图清单”，但清单要到 FE4b 第 2 步才定稿。**
依据：§3.3 FE4a 条与 FE4b 条“暂定页面如下，第 2 步定稿”；§5.2 FE4a 行；§11.1 范围第 6 项。
改法：FE4a 只在 t1 套件中加入不依赖 BE-b 的关键页面参考截图（工作台、Preview v1 与 v2 FULL、审核模式、历史比较三节点、归档主线），截图名与 1280/1920 宽度固定；依赖 BE-b 的页面（侧栏分组、装置页签、中文列名与列序、行定位连线、导航诊断）在 FE4b 第 2 步定稿并实现。同步改 §5.2 与 §11.1 第 6 项的措辞，FE4a 退出条件不含 BE-b 页面。

### 非阻塞（N）

- **N1** §6.2 的分类漏了 `snapshot_materialization/`（5）、`repository_read/`（2）、`canonical_metadata/table_access.py`、`pair_pipeline.py`、`bootstrap/operation_worker.py`、`repository_client/src/`（5，请求改受调用方期限约束）与 Rust 的 `comparison/mod.rs`、`lib.rs`、`records.rs`、`gateway-compute-python`。依据：本报告第 2.1 节。改法：补全分类，并在第 1 行补一句导入闭包核对（routes/schemas 只导入未改模块；`http/` 导入的两个已改模块所用符号不变）。结论不变。
- **N2** §6.2 第 4 行“无前端可见变化”漏了 History 比较 assemble 步骤新增的终态失败发布。依据：本报告第 2.4 节、`16ffe72829:…/compare_jobs.py:533–567`。改法：写明 `HistoryCompareResultResponse.diagnostic.code` 在 assemble 阶段可能出现 `RepositoryProviderError` 的码，前端只显示 message，模拟数据可达表仍是子集，无渲染影响；真实旅程若出现，按 §6.2 末条在 handoff 中列出。
- **N3** §7.2 的 DC68 摘要不完整。依据：本报告第 6 节引用的 AGENTS 原文。改法：直接引用原文或链接，至少补上适用独审、确认收尾、固定修订稿复验、不跳过身份/缓存前提、不因被测对象已运行就立即交 owner、只读后处理与代码传输准备不计次数。
- **N4** §7.4 的触发条件按文件判断会误触发，且没有写 Q23 理由 ② 的复核结论。依据：本报告第 6 节、`087281ce65`。改法：`git diff --stat` 只作筛查；非空时由审核会话判断 `collectLocalDirectory`、`buildTar`、`buildSourcePackage` 或上传步骤卡的打包阶段（`begin("packaging")` 到下一阶段）是否改变，只有改变才在 t4 上重测。补一句“按实际路径复核，`fe-fe3b-exit..fe-fe3c-exit` 中两个文件均无改动，Q23 理由 ② 的结论成立，FE4 不需要补测”。
- **N5** §10 中 Q2、Q4、Q5、Q8、Q9 缺“不采用方案及其代价”，Q1、Q10 不全。改法：逐题补一句。例：Q4 不采用（前端设计会话写第二步）的代价是前端会话要做后端实现层设计；Q8 不采用（在 FE4 中做）的代价是需要先立项后端任务、FE4 退出随之推迟。
- **N6** FE4a 的运行次数偏多：调试要求四项完整运行各至少一次，审核会话再独立跑 `run-tests.sh` 与 `journeys`，证据再各跑一次，`journeys` 共三次完整集，`t1` 两次。AGENTS 规定调试只跑必要的 focused 测试与受影响的真实数据段，DC98 也说“不默认完整旅程”。改法：调试只要求受影响的用例与 C7 改动后的 J1、J2；完整集与 t1 只在证据中各跑一次；或写明多跑的理由，交 owner（D2）。
- **N7** 前端 kickoff §9“P6 计时是否包含整包传输”（阶段写 P6）与 FE3 kickoff §12“P6 计时与整包下载（DC74 草案）”在 P6 退出后没有去向。改法：在 §3.9 或 §3.7 写明“不在 FE4，交 owner（D5）”，不改历史记录。
- **N8** 小的引用错误：§0“依据”缺 `fe3b-rereview-1.md`（C6 引用了其 N2）；§2.1 占位 fixture 漏 `projections/business-navigation/diagnostics.json`；§6.2“Rust `records/` 改了 3 个”与实际不符；§12 把“过期 `APPROVE` 409”归到 FE3 kickoff §4.7，实际在 §15.3。
- **N9** `79ccde87d6` 中 FE3 kickoff Q21 状态列与 §12 两行写“FE4a”，默认 Q1 已决定。改法：注明“拆段待 owner 确认（FE4 kickoff Q1）”，与前端 kickoff §7 行一致。
- **N10** §3.8 wrapper 的占用检查只写“没有他人的有效占用标记”，没有区分本人标记与他人标记，也没有写 wrapper 为哪些入口获取标记（`run-tests.sh`、`validate-upload-package.sh`）、哪些不获取（`run-real-backend-e2e.sh`）。回源脚本“在宿主机用 `python3 -I` 运行”应写明是测试节点宿主机还是开发主机（只读回源可在开发主机做，节点现场重算的 SHA256 必须在节点做）。
- **N11** §6.2 末条说 t1 的预期值从被测树读取模块级常量，而 `real_dump_journey.py` 在本区间有改动。改法：写明发提示词前由审核会话确认 FE3 kickoff §8.3 用到的常量名在 `49c1de43be` 中仍存在（只读 `git grep` 即可），避免在节点上才发现读不到而停止。

### 交 owner（D）

- **D1** P7 S0 已收口、S1a 编码已获授权（本地 main `00ca325c2e`，未推送），而 BE-b 第二步尚未开始。需要 owner 决定：P7 文档能否作为 BE-b 排期依据；BE-b 第二步以 S1a 之前还是之后的树为基础；两者谁先合入 main；由哪个后端会话评估。这取代草案 Q5 现有的前提。
- **D2** FE4a、FE4b 的真实数据范围（DC33、DC98）：FE4a 的 `t1` 是否在调试与证据中各跑一次，还是只在证据中跑一次；`journeys` 完整集的次数；M1/t4 只在打包流程改变时触发。草案写了范围，但没有作为 owner 问题列出。
- **D3** FE4a 的证据绑定未推送的本地 P6 退出树 `49c1de43be`。是否在 FE4a 证据前推送 `p6-exit` 与 main，还是接受证据只绑定本地树并在推送时重核（草案 Q2 只写了“注意”）。
- **D4** Q21 答复分支 `p6-fe3-q21-answer`（`d3450675bf`）的合入与推送（草案 Q10 已列，此处重申它是 FE4a 提示词的前置之一）。
- **D5** 前端 kickoff §9“P6 计时是否包含整包传输”与 DC74 草案在 P6 退出后的处置。

### 需要 owner 先决定才能继续的事项

1. Q1（拆段）与 D1（BE-b 与 P7 S1a 的关系）：决定后设计会话才能完成 B1 的 Q5 改写；FE4a 本身不依赖 D1。
2. Q2、Q3、Q7、Q10 与 D2、D3：FE4a 提示词的前置。
3. Q4、Q5（改写后）：BE-b 第二步何时开始、由谁写。

## 12. 给设计会话的修订提示词

> 你是前端设计会话。FE4 kickoff 审核结论为“定向修订”，报告在 main 的 `docs/frontend-vnext/reviews/fe4-kickoff-review.md`（用 `git show main:<路径>` 读取）。请在 `fe4-kickoff` 分支（worktree `/home/dev/gdds-fe4-kickoff`）上追加提交，不改写 `e0082180e0`、`79ccde87d6`，不合入 main，不推送。
>
> **必须修改：**
> 1. **B1：** 按报告第 11 节 B1 的五点改写：main 已为本地 `00ca325c2e`（P7 S1a 文档，未推送，`vnext/` 仍为 `49c1de43be`）；P7 S0 已收口、S1a 编码已获授权的事实写入头部、§2.2、§2.3、§4、§6.1、§9；FE4a 仍固定用 `16ffe72829`，换上新理由；Q5 去掉“P7 计划未提交”的前提，改为请 owner 决定 BE-b 与 S1a 的先后（报告 D1），并写不采用各方案的代价；§4 交付清单增加 bundle 传输、manifest、ArtifactRef 与 surface 的变化说明和新的互通 fixture；§11.1 前置条件增加“审核会话发提示词时重核 `fe-vnext`、`p6-exit` 与 main”。不要以 P7 文档推导 BE-b 的设计内容。
> 2. **B2：** FE4a 只在 t1 套件中加入不依赖 BE-b 的关键页面参考截图（列出页面与截图名规则），依赖 BE-b 的页面留到 FE4b 第 2 步；同步改 §3.3、§5.2 与 §11.1 范围第 6 项。
>
> **建议一并修改：** N1–N11（报告第 11 节），其中：
> - N3 直接引用 AGENTS 的 DC68 原文；
> - N4 把 §7.4 的触发改为“筛查 + 审核判断打包流程”，并补 Q23 理由 ② 的复核结论；
> - N5 补齐 Q2、Q4、Q5、Q8、Q9 的“不采用及代价”；
> - N6 重新考虑 FE4a 的调试运行，或写明理由；
> - N9 在 FE3 kickoff Q21 状态列与 §12 两行注明“拆段待 owner 确认”。
>
> **新增 owner 问题：** 报告 D1（取代 Q5 的前提）、D2（真实数据范围，DC33/DC98）、D3（未推送 P6 树）、D5（P6 计时与 DC74 的去向）。
>
> 修订后在 §13 列出本次修改的节，并用脚本核对新增文本中的十六进制值。提交后交回审核会话做定向复核，复核只看 B1、B2 与新增的 owner 问题，以及 N 项的处理说明。

## 附录：本报告的十六进制核对

提交前用第 10 项的脚本核对本报告（语料加上 `00ca325c2e`）：

- 27 个不同值，git 对象唯一命中 22 个（commit 16、tree 4、tag 2，其中 8 位的 `e22e39ba` 为证据目录名，命中提交 `e22e39ba15`）；12 位 tag 后缀 2 个在来源文档中原样出现。
- 截断值 3 个，前 8 位加后 4 位在 `16ffe72829` 的文档中各唯一对应一个 64 位值：`4c2ddca7…620a`（`frontend/openapi.json` 规范化 SHA256）、`ce58f20a…c079`（FE3c OpenAPI 原件）、`63a0e600…29f2`（FE3c 截图清单）。
- 无未命中值；除上述有意截断外，无长度不在 7–12、40、64 之内的值。
