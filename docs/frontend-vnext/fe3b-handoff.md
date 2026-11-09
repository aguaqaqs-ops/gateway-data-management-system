# FE3b 交接：契约与基础

FE3 拆分后的第一阶段（FE3b）。范围按 kickoff（main `885f5c4b64`）§3.2 的 FE3b 行与 §15.2：
快照与清理、tar/OPFS 同字节互通、上传模式撤回与占用、终局处置只读显示、FE3b 的真实 backend
旅程，以及 FE3a 带入项。归档核验、逐项接受/撤销、关闭出口与 R8/R12 属 FE3c，不在本阶段。

## 0. 摘要

- 分支 `fe-vnext`，起点 tag `fe-fe3a-exit`（`0e7caf66f4`，前端树 `8a9f11c84f`）。
- 合入 main `748de5034d`（`--no-ff`），合并提交 `db466112e0e4a1fa3b2e466435fdc104c14290ae`；
  FE3b 期间不再合入 main。
- 代码候选 `5a0cdbad9c662658be3822ad96940f7ca7221283`；前端树
  `8764289b6b26dc3cab648a921cd9ef92f3da7e1f`；`vnext/` 树
  `56720104af34a1eb677336f57bdbc07444a56615`。相对 `748de5034d`：44 个文件、+6533/−465，
  全部位于 `frontend/` 与 `docs/frontend-vnext/`。
- 三次调试运行均通过（均为调试运行，证据运行留给审核通过后的 04）：
  - 07 `run-tests.sh --e2e --screenshots`：exit 0，161 个单测 + 47 个 Playwright 用例，
    134 张 PNG（67 张 × 1280/1920）；
  - 05 `run-real-backend-e2e.sh --suite journeys --subphase fe3b`：18/18，exit 0，
    runtime OpenAPI 与快照规范化后逐字节一致；
  - 05 `validate-upload-package.sh`：4 个包、0 失败，缺 `dbcfg.sql` 的包按
    `UPLOAD_CLOSURE_INVALID` 拒绝。
- 本文件为单独的文档提交（仅 `docs/frontend-vnext/fe3b-handoff.md`），不改动代码候选树。

## 1. 合并与路径核对（kickoff §2.1、§3.2）

| 项 | 结果 |
| --- | --- |
| 合并提交 | `db466112e0e4a1fa3b2e466435fdc104c14290ae`（父：`0e7caf66f4`、`748de5034d`） |
| 合入的 main | `748de5034d` |
| `HEAD:vnext` | `56720104af34a1eb677336f57bdbc07444a56615` |
| `748de5034d:vnext` | 同上（相等） |
| `git diff --name-only 748de5034d HEAD` | 仅 `frontend/` 与 `docs/frontend-vnext/` 下的路径 |
| `build-backend-dependency-base.sh --print-input` | `gateway-backend-deps:lock-d054366c02fa`，输入 `d054366c02fa2a28…57aad` |
| 合入带入的前端提交 | `55d56efb6e`（`GATEWAY_FE_TEST_WORKERS`，仅 `frontend/scripts/run-tests.sh`），保留并纳入审核范围 |

kickoff 以 main `885f5c4b64` 阅读（晚于 `748de5034d`，未合入）。未推送、未改写任何已被引用的提交。

## 2. 快照、类型与契约同步（kickoff §5.1–§5.4）

### 2.1 快照来源与比对

- 来源原件：生产 OpenAPI 导出，路径见 FE3b 前置检查 §3（04 产物
  `production-openapi.json`），SHA256
  `977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`。
- 规范化：在主机上用 `python3 -I` 执行
  `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"`（不用 Node，避免
  浮点与 `0.0` 的序列化差异），写入 `frontend/openapi.json`：146,455 字节，SHA256
  `e26d9e14b4ee7e699220fafc8b6b8e3420a6d7335fa2171ea685beebc440574a`。
- 运行时比对（05 journeys 每次运行前，经 toolchain 容器与 preview 代理读取 `/openapi.json`）：
  `openapi_compare=match`；`openapi-snapshot.normalized.json` 与
  `openapi-runtime.normalized.json` 均为上述 SHA256。快照因此已与真实 backend 证明一致，
  不再只是静态比对。
- 类型：`npm run generate:api-types`（`openapi-typescript 7.13.0`）重生成
  `frontend/src/features/api/generated/openapi.d.ts`，3,409 行（+549/−221），
  `tsc -b` 通过；`npm run check:api-types` 验证重新生成与提交内容逐字节相同。

### 2.2 清理清单（删除的退回路径、类型变通与标记）

| 位置 | 处理 |
| --- | --- |
| `frontend/src/features/api/client.ts` | 删除 `RETURNED_FOR_REVISION → REJECTED` 的 `safeReviewStatus` 映射与 `safeReviewEvent` 的 `event_kind` 映射 |
| `frontend/src/features/view-model/workspace.ts` | 删除 `RETURNED_FOR_REVISION` 分支；`REJECTED` 统一“已退回” |
| `frontend/src/pages/ComparisonPage.tsx` | 删除 `RETURNED_FOR_REVISION: "需修改"` 条目；`REJECTED` 由“已拒绝”改为“已退回” |
| `frontend/src/features/dev/mock-data.ts` | 模拟值表与场景不再出现 `RETURNED_FOR_REVISION` |
| `frontend/e2e/workspace-shell.spec.ts` | 断言改为“审核：已退回”；不再有“拒绝”作为该状态的文案 |
| 201/202 变通 | 新增/重放分别使用 `SubmitAcceptedResponse` 与各 201/200、202/200 的生成类型，删除 FE2 §7.5 的“重放体按 200 类型”变通 |
| `sessionStorage["gateway-submit-operation"]` | `SubmitDialog.tsx` 的写、`ComparisonPage.tsx` 的读/清、`WorkbenchPage.tsx` 的读/清全部删除；n3 用例改为在 mock 中预置 `active_submit_attempt_id` + attempt，覆盖不减（ABORTED 恢复与 W9 读取失败两条） |
| `archive_disposition` | 直接改名 `submission_disposition`，并新增 `disposition_source_kind`、`disposition_result_id`、`closure`；无双读、无旧字段别名 |
| 模拟值表 | `subject_kind` 6 值、`action` 7 值、`issue_code` 9 值（含 7 个业务码）；blockers 增 `ARCHIVE_PENDING_REVIEW`；review-events 增 `BASELINE_VERSION_CONFLICT`（`ARCHIVE_CLOSED` 的文案属 FE3c 关闭路径） |
| `journeys.ts` | `ArchiveSubjectKind` 与 `anomalyResolutions[].action` 改用生成类型 |
| `ArchiveMainlineDialog.tsx` | `anomalyAction` 对 5 个 `subject_kind` 穷举映射（未知值由类型检查拒绝），不再“其余一律 ACKNOWLEDGE_EXCLUSION” |
| `check-production-build.mjs` | mock token 排除模式扩展为 `dev-token-(?:submitter|reviewer|archive-confirmer|no-permission|upload-only|no-preview)` |

### 2.3 `mock-data.ts:120` 的处理

`fe2a-history-ref-old`（APPROVED + `NOT_CANDIDATE_BASE_ADVANCED` + 身份例外，无处置）保留为
**D5 防御性数据**：DC89 下不可达，仅用于验证“有 flag、无处置”的旧显示回退；已在代码中加注释
标明防御性，测试只断言工作区映射，不宣称 backend 可达。原 `:458` 处的
PENDING + `NOT_CANDIDATE_BASE_ADVANCED` 组合（DC89 下不可达）改为 APPROVED，使该 flag 数据
处于可达形态；`mock-data.test.ts` 新增断言：带 `eligibility_note` 的节点必须是 APPROVED。

### 2.4 处置与动作的模拟数据规则

- 处置只出现在 APPROVED 的 SUBMISSION 节点上；`ARCHIVED_BASELINE` 只配 `ARCHIVE` 来源、
  `result_id` 非空、`closure` 为空，且能对上一个 `ARCHIVED_SUBMISSION` 基线
  （`promoted_baseline_node_id`）；`CLOSED_NOT_ARCHIVED` 分别配 `ARCHIVE`（`result_id` 非空）
  或 `MANUAL_CLOSE`（`result_id` 为空、`closure` 非空）；不出现
  `ARCHIVED_BASELINE + MANUAL_CLOSE`。
- `eligibility_note` 只表示“所基于的基线已不是当前基线”，与处置无关；有处置时隐藏该标签。
- Review 的 `submission_disposition` 与 History 节点一致；已处置的提交不再出现在任何 workspace
  的 `active_submission_id`（陈旧的 workspace 读取按 §6.1/W10 重新读取）。

## 3. tar 接收与 OPFS（kickoff §5.5）

### 3.1 解析与预算

- PAX 记录在 `Uint8Array` 上按字节解析：ASCII 十进制长度 + 空格，长度包含前缀数字、
  `key=value` 与结尾 `\n`；记录必须落在 payload 内且以 `\n` 结束，相邻记录按字节边界切分，
  之后才对 key/value 做严格 UTF-8 解码。删除原先“整段解码后按 `text.length/slice`”的做法。
- 两层分离：切分层只负责切分与解码 `(key, value)`；成员层（某个成员的 PAX 扩展头）只接受
  `path` 与 `size`，重复 key、其他 key、空值一律拒绝并中止安装。
- 标准 PAX `size`：ASCII 十进制、非负、≤ `Number.MAX_SAFE_INTEGER`；出现时覆盖 ustar 头的八进制
  size（后端头 size 为 0），有效大小必须等于 closure 的 `size_bytes` 且不超过剩余
  `Content-Length` 字节，否则在写 OPFS 前拒绝。
- 预算在分配前检查：`MAX_PAX_PAYLOAD_BYTES = 16,777,216`（单个本地 PAX payload，不含 512 字节头
  与 padding）、`MAX_PATH_UTF8_BYTES = 8,388,608`（单个 path 的 UTF-8 字节数，ustar name/prefix
  同限）、manifest/closure 各 16,777,216；普通成员不设前端固定上限，按 closure/剩余字节流式写入。
  `PAX_LIMIT = 1 MiB` 已删除。
- 任一失败（截断、流错误、大小/路径/顺序/摘要不匹配、预算超限）都中止本次安装、删除临时内容，
  UI 显示 bundle 下载失败（沿用既有文案与错误码），不显示“无差异”，不降级为仅 manifest；
  已安装的同一 bundle 不受影响；HTTP 200 或 operation SUCCEEDED 不等于本地安装成功。

### 3.2 同字节互通 fixture

目录 `frontend/src/test/fixtures/backend-interop/be-d-0ba45e5ef8/`，10 个条目（kickoff 的
“10 个互通文件”是计数勘误：9 个文件 + `SHA256SUMS`）：

```
artifact-closure.json  manifest.json  index.json  pax-records.json  size-vectors.json
bundle.tar
size-8589934591-header-only.bin  size-8589934592-header-only.bin  size-9007199254740991-header-only.bin
SHA256SUMS
```

- 目录与来源 `/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/`
  逐字节相同；`SHA256SUMS`（sha256sum 格式，覆盖 9 个文件）SHA256
  `662afdfc8958eecb25db143646bf6226f509abe8c29270f85e83ed47664810d9`。
- `bundle.tar` 24,576 字节，SHA256
  `b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`；`manifest.json`
  `320f44e7…`、`artifact-closure.json` `becf0b70…`、`index.json` `199d4511…`、
  `pax-records.json` `0fa31f37…`、`size-vectors.json` `b8d23e94…`。

### 3.3 用例

单测（`frontend/src/features/bundle/interop-fixture.test.ts`，6 条）：

1. 原样安装 backend 互通 bundle，6 个成员与元数据同字节；
2. 切分层/成员层分别解码 literal、99 前缀与 101 前缀的长路径；
3. 成员层拒绝相邻记录（`comment`）与不支持的 key；
4. 切分层拒绝 3 个非法向量（长度错、缺换行、截断 UTF-8）；
5. 读取 3 个 header-only size 向量（8,589,934,591 / 8,589,934,592 / 9,007,199,254,740,991），
   随后因数据不完整拒绝且不提交；
6. 路径与 PAX payload 预算在分配前生效（1.5 MiB 路径通过、8,388,609 字节拒绝、头部声明
   16,777,217 的 PAX 在读 payload 前拒绝、非安全整数 size 拒绝）。

Playwright（`frontend/e2e/bundle-interop.spec.ts`，3 条）：真实下载 + OPFS 安装并核对 6 个文件的
大小与浏览器内 SHA256；截断 512 字节中止；篡改 1 字节 parquet 中止（无残留内容、UI 显示下载失败、
请求计数 1 正/2 负）。OPFS 布局 `gateway-comparison-bundles-v1/<digest>/`。

运行节点与日志：07 上 `fe3b-mock-20261108n`（见 §8）；单测与 mock e2e 同属一次 `run-tests.sh`。

## 4. 上传模式撤回与占用（kickoff §6.1–§6.3）

### 4.1 实现

- 撤回原因判定抽成纯模块 `frontend/src/features/workbench/upload-header.ts`
  （`deriveUploadModeGates`）：按 §6.1 顺序返回 enabled/disabled 与原因，输入为
  workspace、review facts、submit attempt、operation 与各自读取状态。撤回按钮在 Upload 模式
  always-visible，只按该模块禁用并给出标题/可见原因（Q7）。
- 撤回携带 `review_version`（Review facts 的版本，不是 workspace 版本）；不按 actor 或指针推断
  可撤回；失败 409 统一“审核状态已变化，已重新读取”并重新读取 workspace + review，不自动重发。
- 提交续做：URL 的 `operation_id` 保留；`job_kind` 来自 `GET /v1/operations/{id}`；页面加载/刷新
  先读 workspace，若 `active_submit_attempt_id` 非空且 URL 无对应 submit operation，则经
  `GET /v1/workspaces/{id}/submit-attempts/{attempt_id}` 取回 `operation_id` 并写入 URL；
  URL 与服务器不一致时以服务器为准。Q14：续做失败先重读 workspace，再按 §6.1 指针表决定；
  读取失败时保持禁用“无法确认提交状态”并提供重试，不出现“确认中”与失败并存。
- 提交/上传占用：任一指针非空禁用提交；workbench 的上传（工具栏与步骤卡）同样禁用并给出原因，
  避免与待审核提交冲突（backend 对 review 操作返回 409 `WORKSPACE_OCCUPANCY_CONFLICT`）。
- 删除 `gateway-submit-operation` 标记的全部读写（见 §2.2），`gateway-preview-operation` 不变。

### 4.2 W1–W10 覆盖

| 用例 | 模拟 e2e（`e2e/upload-mode.spec.ts`） | 真实 journeys | 结果 |
| --- | --- | --- | --- |
| W1 撤回成功 | “撤回成功后回到上传步骤并恢复上传” | `r7-withdraw` | 通过 |
| W2 撤回后重新上传/预览/提交 | 同上（指针与 upload/preview id 清空） | `r7-withdraw` | 通过 |
| W3 无审核权限 | “没有审核权限的身份不能撤回” | `r7-upload-only`（403 + 原因） | 通过 |
| W4 已通过不可撤回/上传 | “已通过提交不能撤回也不能上传” | `r7-approved` | 通过 |
| W5 版本冲突 | “撤回遇到审核版本冲突时重新读取且不自动重发” | `r11-review-conflict` | 通过 |
| W6 提交执行中/结果未知 | “提交尝试未结束时撤回、提交与上传均禁用” | —（真实环境不可控，仅模拟） | 通过 |
| W7 审核模式撤回回归 | 既有 review 撤回用例 | `r7-reviewer-withdraw` | 通过 |
| W8 待审核禁用上传 | “待审核提交禁用上传，撤回后恢复” | `r4-submit`、`r7-withdraw` | 通过 |
| W9 续做读取失败 | `workspace-shell.spec.ts` “W9 提交续做读取失败时保持禁用并可重试” | —（模拟 `MANUAL_RECOVERY_REQUIRED`/503） | 通过 |
| W10 陈旧工作区遇处置 | “陈旧指针遇到已处置提交时显示终局原因” | —（处置需归档流程，FE3c） | 通过 |

补充模拟用例：§6.1“没有待审核提交与状态无法确认时的撤回禁用原因”
（`fe3b-withdraw-none`）与“工作区读取失败时撤回显示无法确认提交状态”（workspace 503 →
`fe3b-withdraw-unknown`）；FE3a 带入的 ABORTED 恢复与 n3 指针改写用例保留。

## 5. 终局处置只读显示（kickoff §6.4）

- 组态树、详情面板与审核模式顶栏统一从 `submission_disposition` 派生：已归档（info）/
  已关闭（未归档，neutral）；详情显示“终局处置”，`ARCHIVE` 来源显示“原因：归档时选中了其他
  提交”，`MANUAL_CLOSE` 显示关闭人/关闭时间/关闭理由（完整文本，超过 3 行折叠）；时间本地化、
  hover 显示 UTC；审核模式顶栏显示处置标签与禁用原因。
- 处置优先于 `NOT_CANDIDATE_BASE_ADVANCED`：有处置时不显示“基线已更新”标签，归档主线按处置
  原因禁用；“归档基线 n”与树标签共用同一标签函数（M7）。
- 有处置时审核按钮禁用（“该提交已归档”/“该提交已关闭（未归档）”）；不做关闭入口（FE3c）。

| 用例 | 覆盖 |
| --- | --- |
| D1 已归档 | `upload-mode.spec.ts` D1–D5：树“已归档”、详情“成为归档基线 1”、审核标签、归档主线禁用 |
| D2 归档时关闭 | 详情“原因：归档时选中了其他提交”，主线禁用 |
| D3 有理由关闭 | 关闭人/关闭时间/多行原因折叠展开；`result_id` 为空仍按已关闭处理 |
| D4 处置优先 | APPROVED + 处置 + flag：不显示“基线已更新”，主线按处置原因禁用 |
| D5 仅 flag（防御） | 显示“基线已更新”，主线原因“该提交所基于的基线已不是当前基线”（无“不能归档”） |

另有 `workspace.test.ts` 的 D1–D5 工作区映射单测（4 种处置组合、flag 优先级、主线启用条件）。

## 6. 真实 backend 旅程（kickoff §4.7）

### 6.1 入口与环境

- 入口 `frontend/scripts/run-real-backend-e2e.sh`（独立于 `run-tests.sh`），`--session` 必填；
  脚本自行获取/释放 DC70 占用与 `flock -n`，失败时按 §4.2 释放顺序收尾（清理、验证、释放、
  删除标记）。
- `--suite journeys --subphase fe3b`：每个 scope 独立 repo/INITIAL、独立身份集；54 个身份，
  18 个 scope；每 scope 的 workspace/上传目录都在 worktree 外，日志与证据目录分离。
- 身份：`submitter`（`workspace_read`、`read_project_history`、`upload_submit_workspace`、
  `preview_workspace`、`withdraw_own_submission`，无 `review_submission`）、
  `submitter-upload-only`（同上但无 `withdraw_own_submission`）、
  `submitter-no-preview`（仅 `upload_submit_workspace`）、`reviewer`、`archiver`、`none`。
- 上传输入（由共享 fixture 派生，仅 `b1_n1_iec104_yc_list` 增加 `gid`；其余字节相同）：
  - `modified_only` = 派生 `sql-baseline.sql` + `logics-1.xml`（输入 A）；
  - `full_initial` = 派生 `sql-baseline.sql` + `logics-1.xml`（①=A）；
  - `full_modified` = 派生 `sql-initial.sql` + `logics-2.xml`（②）。
  派生文件在 `frontend/e2e-real/fixtures/upload-inputs/`，单测固定派生规则；共享 fixture 未改。

### 6.2 每个 scope 的上传序列

| scope | 序列 |
| --- | --- |
| r1-states、r4-submit、r5-idempotency、r6-reject-approve、r7-withdraw、r7-upload-only、r7-approved、r7-stale、r7-reviewer-withdraw、r9-history、r10-*、r11-* | ① A（MODIFIED_ONLY） |
| r2-preview | ① A，浏览器取 Preview bundle 后重开比对（同 context 不重下载） |
| r2-full | ① A（FULL 第一步，`full_initial`）+ ② B②（`full_modified`），生成两个比较对（0→1、1→2） |
| r3-truncated | ① A，用 route 截断一次真实 tar 响应 |
| r6-reject-approve | ① A → 退回 → 用同一 A 重传 → 通过 |
| r7-reviewer-withdraw | ① A，reviewer 在审核模式顶栏撤回 |
| r10-archive | ① A → reviewer 通过（使归档主线入口可达），再验证无权限候选查询 403 |

### 6.3 结果（最终候选，05 run l）

18/18 通过，exit 0，`openapi_compare=match`，`cleanup_status=ok`；详见 §8 的运行记录。
覆盖 R1/R2/R3/R4/R5/R6/R7（W1–W4、W7、W8、W10 的真实部分）/R9（两节点）/R10（四个 403）/
R11（review 与 workspace 两类版本冲突）；R4 身份确认与三节点 R9、R8/R12 属 FE3c。
R10 的“提交 403”在真实 backend 不可达（仅模拟覆盖），已在此说明。

冒烟：`--suite smoke` 保留 FE3a 用例，删除了“下载比较结果失败”的临时断言，改为进入差异浏览后
断言无 uncaught `pageErrors`；bundle 标识按 tar `ETag` + manifest bundle 摘要记录。

## 7. FE3a 带入项

- N1：新增 `frontend/e2e/tsconfig.json` 与 `frontend/e2e-real/tsconfig.json`，由根 `tsconfig.json`
  引用，`tsc -b`（typecheck/build）覆盖 e2e 与 e2e-real；strict 在 mock 重的 spec 中关闭，
  其余沿用 app 配置。
- N2：bundle 标识 = tar `ETag` + manifest bundle 摘要；journeys 逐 scope 记录。
- N5：冒烟删除临时断言；进入差异浏览后再断言 `pageErrors`。
- n3：按 §6.2/Q14 改为指针 + attempt 驱动（不再依赖 sessionStorage），并新增 W9 读取失败分支，
  覆盖不减。
- M1：本阶段未改 pack 代码，按 Q20 不重测 t4；t1 的 M1 报告中继留给 FE3c。
- 未沿用 FE3a handoff 的勘误项。

## 8. 证据与运行记录

### 8.1 07（ct109-gw-dms-07，`gw-dms-07.lan`）mock 全量

`GATEWAY_FE_TEST_WORKERS=2`；工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`；
npm 缓存 `/home/dev/gdds-fe-cache/frontend/npm-cache`，归档
`/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`（SHA256
`0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交
`a2fb4a027a`）。

| # | HEAD | 起–止（UTC） | exit | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| 1 | `ff342a5872` | 09:58:28–09:58:43 | 1 | `71fe1ef0bdbd1882287cef852c04ceaa4259803b04f70afb20775f77264ccfa1` |
| 2 | `940be4b5b8` | 10:02:53–10:05:19 | 1 | `b585391651e8a30cdb02118b15d01cf770c511dfb01a9692b7c4960b6523881c` |
| 3 | `865a35117a` | 10:10:11–10:12:13 | 1 | `91229c3f0fbe767b60b8ad3cd39bd8b3bfe873dd65437647462821b1112bfb2c` |
| 4 | `963c9be60e` | 10:14:50–10:17:27 | 1 | `e51b7362b9d4671e04b72d60f97a0e08474c1b70407c34806afacbfafcd5ae7a` |
| 5 | `c1950cbe85` | 10:20:48–10:22:45 | 1 | `0e6d652c80138276a89a459c3c95a5544650cf973e057a1a0fc67465d4176ec9` |
| 6 | `98228749f2` | 10:25:03–10:26:54 | 0 | `203dea89cfed4378fe0e4e14c7064b10b361d4ee35e0792a566e1dd6090a5ad5` |
| 7 | `79271c448c` | 10:32:50–10:33:03 | 1 | `354150afe7160b07fe99ca370296bf5547d9a393e6607057a7df938ca46db2dd` |
| 8 | `9b3811104c` | 11:12:09–11:14:05 | 1 | `b6cc8e304eb9674b81bf779484b4ab37a630f5272835bfb88171669142356609` |
| 9 | `ef4fd3656b` | 11:19:26–11:21:17 | 1 | `f5c538b98a91ad79c9cda231a3798db4941b2b7395bbf2629e74d348d68a4427` |
| 10 | `fc7c894ca6` | 11:27:34–11:29:28 | 1 | `d844b68c839de220b7f720be91f3a123d54b96a309ab0e71c04642630400c711` |
| 11 | `669b7bbf26` | 11:30:26–11:32:19 | 1 | `ff0db4b37def82073fb655617a825a04662b6909c8a293666514b3045e20445e` |
| 12 | `c6b84124ce` | 11:34:53–11:36:44 | 0 | `25ef318eab063c7ce0870bc0c25a2dba43eb344b71654027f0b0a2d92f295260` |
| 13 | `bea468ab24` | 11:43:06–11:44:59 | 0 | `7a2fa26ccacf9587146f389b192ed7c015725d063584da14974793ec2556f7de` |
| 14 | `5a0cdbad9c` | 12:00:08–12:02:01 | 0 | `30ce43fc9930a153b50a081343761299c9f6b0a54b54eae0a88460a9fb7a4031` |

- 1–5、7–11 为调试中的失败轮（单测/Playwright 断言、e2e fixture、copy 对齐），修复提交见 §10；
  6、12、13、14 为 exit 0 的完整运行，14 为最终候选。
- 14 的细节：161 个单测通过；47 个 Playwright 通过；截图 134 张（67 个页面 × 1280/1920），
  聚合 SHA256 `37ed040bb11ebfaabb46b0975febe023010d74de572afb95dc3d16e708eee841`；
  截图目录 `/home/dev/gdds-fe-shots/fe3b-mock-20261108n`。
- 工具链身份：config digest
  `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`；RootFS DiffID：
  `bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`,
  `1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`,
  `c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`,
  `89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`,
  `ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`,
  `16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`,
  `d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`。
- 两次启动失败（exit 2）为环境参数错误（`--log-dir` 不是该入口选项、npm 缓存归档路径写错），
  未开始 npm ci/测试，不构成被测对象失败；修正后从头运行。

### 8.2 05（ct108-gw-dms-05，`gw-dms-test-05.lan`）真实 journeys

工作树 `/home/dev/gdds-fe-79271c448c`（detached，`legacy` 软链，clean）；会话 `fe3b-impl`；
npm 缓存 `/home/dev/gdds-fe-cache/fe0/npm-cache`，归档
`/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`（SHA 同上，来源 `a2fb4a027a`）。

| HEAD | 起–止（UTC） | exit | 日志 SHA256 | 说明 |
| --- | --- | --- | --- | --- |
| `79271c448c` | 10:32:35–10:35:33 | 1 | `3c583c296291fe0b8a92d1428ea60fa9389f5ae41f0d346fa85d7c380eca75f1` | 1/18；manifest 摘要与 403 折叠 |
| `11b7d658e2` | 10:39:38–10:42:35 | 1 | `a096f82a29ac082dce349071a00dc1cc11a371b3d82a71884ac74acd70299e28` | 2/18；closure 字段；openapi match |
| `b81102d845` | 10:44:14–10:47:12 | 1 | `f95d77bd85ffb79806b1104dd2be964ba3e65080b0fc7d0628dfc12f07ae52de` | 诊断：closure=undefined |
| `f568455156` | 10:48:31–10:51:24 | 1 | `a3b7ed309b41eed4fbf90873bcab52c0aab5991abe297875103b83757af10f56` | 2/18；ETag 引号 |
| `4f5d28bbb7` | 10:52:38–10:59:44 | 1 | `1aaf7915b456e47ed604d8ec177e64fbb9c61bc209a3a173431805c0de6d8786` | 7/18 |
| `434ba08222` | 11:03:12–11:10:31 | 1 | `f80c5a948f8c24cccf6de1f1dd9d8198ebe55a0779e6865eae36a1786db21de5` | 16/18 |
| `9b3811104c` | 11:11:45–11:16:58 | 1 | `9feb518f6a603c4e5b679f0708808025d79c35ad4ab4b7f2261809df6901b5da` | 17/18 |
| `ef4fd3656b` | 11:18:59–11:24:12 | 0 | `801bdcfa506ddddd13e0e110a2f59e53f66e5733b683365bfc7ac4b5b84ecb1a` | 18/18 |
| `fc7c894ca6` | 11:27:21–11:32:30 | 0 | `84791acd944dfe9f920d71591b07a084f7e44ee7e9d9204633927c07e5b00b3e` | 18/18；HEAD 中途变化，不作证据 |
| `c6b84124ce` | 11:36:57–11:42:10 | 0 | `0f612df45654816b3eacc6961e180f397b1f91d71218780651ee317afb33a24a` | 18/18 |
| `bea468ab24` | 11:48:46–11:53:55 | 0 | `d10ebeb7bd25c451143b3794e8f9de1f0d25f47e3fa93433831c66f65769632a` | 18/18 |
| `5a0cdbad9c` | 11:58:06–12:03:18 | 0 | `c143a13d9c275636836aa8689a57019ed7a5deda9fdc51e42e813030d45e0aca` | 18/18；最终候选，openapi match，cleanup ok |

失败轮均为测试侧对后端契约的读法错误（语义 manifest 摘要、closure 语义条目、ETag 引号、
`BundleAssemblyStatus=READY`、提交后 upload/preview 保留、上传目录选择、树节点选择），
修复只改 e2e 读取与断言，未改 `vnext/`、未放宽产品校验。

### 8.3 05 上传包校验

`frontend/scripts/validate-upload-package.sh --output <空目录> --log-dir <目录>`，不获取占用。

- 首次用预置 `gateway-backend-deps:lock-d054366c02fa`：exit 1，`validate-backend` 报
  `ModuleNotFoundError: No module named 'gateway_compute'`——依赖基础镜像不含本地包与 Rust 扩展。
  日志 SHA `bf194f8533cc24208b022bc81e412a0f0fad23ea54ed8c0f1b37a256fcf658ff`。
- 用 `05` 本机构建的 backend 镜像：`/build/backend/.venv` 不存在（运行时 venv 在
  `/app/backend/.venv`），preflight exit 127。
- 为满足入口既有接口（`GATEWAY_BACKEND_DEPS_IMAGE` 需提供 `/build/backend/.venv`），在 05 构建
  包装镜像 `fe3b-upload-validator:latest`：`FROM gateway-backend-deps:lock-d054366c02fa` +
  `COPY --from=<backend 镜像> /app/backend/.venv /build/backend/.venv` +
  `ln -sf /usr/local/bin/python3 /usr/local/bin/python3.14`。产品代码与校验脚本未改。
- 该镜像校验：exit 0，`required_inputs_match=true`，`RESULT packages=4 failures=0`；
  `missing-dbcfg` 按 `UPLOAD_CLOSURE_INVALID` 拒绝，with-logics/without-logics/long-path 通过；
  包 SHA256 分别 `6a562b07…`（with-logics）、`1c4ab2ba…`（without-logics）、
  `8730309a…`（long-path）、`66ce688f…`（missing-dbcfg）；日志
  `/home/dev/gdds-fe-logs/fe3b-upload-20261108c/upload-validator-bea468ab24-20261108T114721Z-326314.log`，
  SHA256 `33a1253b57ff0f468ba8f3ab1ada5dee772374c5b224ce26b9d44738094a99ea`。
  包装镜像 config digest `sha256:2559f4f52080ae130cfb2200885e21c2563bf365a0356e7042c14c7d249e3ec8`，
  21 个 DiffID = 依赖基础镜像 19 层 + 上述 venv 与 python 链接两层。

**偏差**：该包装镜像是为通过入口预检而做的本机环境步骤，不属于产品交付物；04 证据运行时若依赖
基础镜像仍缺本地包，需要同样的镜像准备（或由 04 的 backend builder 阶段产物提供），请 owner
在审核时确认记录方式。

### 8.4 镜像与运行时身份（05 运行）

- 依赖基础镜像：`gateway-backend-deps:lock-d054366c02fa`，config digest / image id
  `sha256:d363b45a33be8d0034f49f156998753086d09c4c171e75896f1e4beab4ff49ff`，label
  `gateway.backend.dependency-input-sha256` 与输入一致，输入
  `d054366c02fa2a284948610e47b1c07bbdba98684b847846ca922d7da3d57aad`；19 个 RootFS DiffID：
  `sha256:f2c42f900cb3b12d5456f76b4fa6454a52df3981323d3a1b1a17fe4c4955ab4a`,
  `sha256:d13007d6a3979078792cbc2afff5c74eb1a14f5a02394f6cae0a873a0752c104`,
  `sha256:af68230260cdbb7ac206fc2f95bf67c1a75ebdcf3e4014accffd3c8bcb478e15`,
  `sha256:ac06852f1f7254083486500d54ef4292d46b2c868df62ba93466e633c78a7cf1`,
  `sha256:a9a1dcf9cd75357904971362ed8395b2feb40790c75a06b85852133a204ba79a`,
  `sha256:c7b432c3f658b7dd011573e85ed7bdbe36769855537890eef470c62367b68c25`,
  `sha256:ca61d18a121a5670b32df53fa9afeeee4290a8f2680c8621a7076d8253151588`,
  `sha256:d9100de052a9a4cbb39754e9bcdbebe082b0c8e4cd1a5d4f446cef2cd4ac87e1`,
  `sha256:01614bf2b27515a3ea31f460030cef9e37a2d7d65d7cffdac5f3d7b6d49671c1`,
  `sha256:2f04268a672be20980a33289ad5086de8a8a7db36b51cff7fcfea0995baec29f`,
  `sha256:3c5de003195a21e12a21ff7a4976b687ef61ef946f74a6465281c6f6f2720cc6`,
  `sha256:3b36040844dfd8c76fbc316aafd0929d65e602016261737368cf63e245598dd6`,
  `sha256:bfb2b2a172006ee7882fcc751dcef85d418a0e24837b11d30220cf21183c1dce`,
  `sha256:b6b4b17f0450d4b8b752e1fb44298477f29e1f74d65584d3182227e9ff20b12c`,
  `sha256:50e4a188b1446b8b9a51ccb3d9745164e86d6b9bdb1f342e9774fe93a4f853d3`,
  `sha256:a7afafdb6a8aa5d13ade8b6eef2986bd37d07e84b2d0b3767f7bb0eb535bf5f4`,
  `sha256:678693472110b1f3f8c40466db580981b7952ede803eaa1518f59d3730ab2814`,
  `sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`,
  `sha256:c338f3f88c37281e775f0b6dfdfa4c079858214cf04733e88f0bda4e4ca4a1f0`。
- backend / worker：`sha256:7e4759e586afb32ca5e335ea5a06e1fc9857a4d38700d1eed7640f89dd1e6e41`、
  `sha256:d8515826514475af19c17f9f370b28c09e2c3c62a401163b9ce13f217f8f82c9`。
- RS：tag `gateway-repository-service:fe-bea468ab2409`，image id
  `sha256:f8b6f66d6a859c32b41df6fa83c6431c7f7a97a64c470a402670295630e4d5ca`；labels
  `gateway.p2r1.build-input-revision=a6876d560050285321fd9f62942d590a03f35d64`、
  `gateway.p2r1.source-tree-sha256=sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`、
  `gateway.p2r1.uv-lock-sha256=6dc9659f0aee…`、`org.opencontainers.image.revision=bea468ab24…`、
  dolt 2.1.11、uv 0.11.28、pyarrow 25.0.0、mysql-connector 9.7.0。RS 完整 DiffID 未在运行结束前
  落盘（镜像按脚本清理），以标签身份与同节点重建保证可比；若 04 需要完整 DiffID，复跑时可从
  `docker image inspect` 补齐。
- Compose 项目：`gdds-fe-fe3b-bea468ab2409-20261108t114924z`（最终 journeys）；网络
  `<project>_default`；toolchain 容器 `<project>-toolchain`。Docker 29.9.1 / Compose 5.6.0。

### 8.5 最终候选的运行

`5a0cdbad9c` 只改了模拟数据与单测（把不可达的 PENDING + flag 节点改为 APPROVED，并给 D5 数据
加注释），不触碰产品代码与真实 e2e 输入。最终候选在同一次运行上完整通过：

- 07 `run-tests.sh --e2e --screenshots`：exit 0，161 单测 + 47 Playwright，日志
  `30ce43fc9930a153b50a081343761299c9f6b0a54b54eae0a88460a9fb7a4031`（§8.1 第 14 行）；
- 05 `--suite journeys`：11:58:06–12:03:18Z，exit 0，18/18，`openapi_compare=match`，
  `cleanup_status=ok`，compose 项目 `gdds-fe-fe3b-5a0cdbad9c66-20261108t115843z`，日志
  `c143a13d9c275636836aa8689a57019ed7a5deda9fdc51e42e813030d45e0aca`；
  RS `gateway-repository-service:fe-5a0cdbad9c66`
  （`sha256:52acfb38106131ae624723dc4e6a6fa43858a4eee705b40b3dff45d0091ddfe7`），backend
  `sha256:eea4a6457b34a1e17d7ee3f9b965456ecefd1de04cd6b14489d41434d2b5c392`，worker
  `sha256:5ab2749eb87418b8dcd8255402d9bc983afcde040157bfacdb424052e59dfebe`；
- 05 上传包校验在 `bea468ab24` 上通过；脚本、产品与校验输入在 `bea468ab24..5a0cdbad9c`
  未变化，按镜像身份等价无须重跑。

### 8.6 截图清单（07，最终候选，均含 1280/1920 两版）

`fe3b-withdraw-enabled`、`fe3b-withdraw-forbidden`、`fe3b-withdraw-none`、
`fe3b-withdraw-unknown`、`fe3b-withdraw-dialog`、`fe3b-w5-conflict`、`fe3b-upload-restored`、
`fe3b-w4-approved-withdraw`、`fe3b-w4-approved-upload`、`fe3b-w6-withdraw-busy`、
`fe3b-w6-attempt-running`、`fe3b-w8-upload-disabled`、`fe3b-w10-stale-workspace`、
`fe3b-w10-stale-preview`、`fe3b-d1-archived`、`fe3b-d2-closed-at-archive`、
`fe3b-d3-manual-close`、`fe3b-d4-priority`、`fe3b-d5-flag`（共 19 个页面 × 2 宽度 = 38 张；
另有 FE1/FE2 既有截图，合计 134 张）。目录
`/home/dev/gdds-fe-shots/fe3b-mock-20261108n`，聚合 SHA256 见 §8.1。

## 9. 偏差与未决

1. **上传包校验镜像**：见 §8.3 的包装镜像说明；脚本与产品未改，需 owner 认可该运行方式，或由
   04 用 backend builder 阶段产物提供同名路径后重跑。
2. **RS 完整 DiffID** 未记录（运行结束即删镜像）；标签身份与 image id 已记录。若审核要求完整
   DiffID，需要在 04 上复跑 journeys 时同时记录。
3. **W6、W9 与 D1–D5 仅模拟覆盖**：真实环境无法稳定构造“执行中/结果未知”的提交尝试，归档/
   关闭流程属 FE3c；对应真实路径在 FE3c 旅程中复核。
4. **R10 的提交 403** 在真实 backend 不可达，仅模拟覆盖（§4.6 已说明）。
5. **M1 未重测**：pack 代码未变，按 Q20 只留 t1 报告；t4 由 FE3c 在 pack 变更时判定。
6. 05 的 `fc7c894ca6` 运行因中途切到下一提交，`head_end` 与 `head_start` 不同，已排除，不作为
   证据；有效证据为 `bea468ab24` 与最终候选复跑。
7. 04 证据运行（mock 全量 + journeys + 上传包校验）尚未进行，按 kickoff §13.4 由审核通过后进行；
   本 handoff 不宣称 04 已通过。
8. 未推送；未改 `vnext/`；未在浏览器重算 SQL/来源/时间。

## 10. 提交序列（相对 `fe-fe3a-exit`）

合并 `db466112e0` 之后（按时间正序，节选信息见 git log）：

```
ff342a5872 feat(frontend): FE3b contracts, tar receive, upload-mode gates and disposition display
940be4b5b8 fix(frontend): cover closure write route and disposition fixtures in simulated API tests
865a35117a fix(frontend): align FE3b e2e fixtures with pointer resume and review routes
963c9be60e fix(frontend): gate busy submit while the operation read is in flight; align e2e upload readiness
ae5705df56 fix(frontend): treat ABORTED operations as terminal; hide stale-baseline tags for disposed submissions; typecheck e2e projects
c1950cbe85 fix(frontend): pair the FULL second upload with logics-2 per kickoff 4.6
98228749f2 test(frontend): drive the ABORTED resume case with a failed submit operation
79271c448c feat(frontend): FE3b real-backend journeys suite, permission copy, and owner screenshots
0d56b2d603 fix(frontend): satisfy eslint for real-backend journey tests
11b7d658e2 fix(frontend): verify backend semantic manifest digests and surface 403 codes
b81102d845 test(frontend): report tar/closure size mismatch detail in journey reader
f568455156 test(frontend): read member sizes from the closure semantic entries
4f5d28bbb7 test(frontend): strip ETag quotes before digest comparison
434ba08222 test(frontend): align FE3b real journeys with backend status, retained inputs and tree selection
9b3811104c test(frontend): tolerate comparison tab badges and decode stale withdraw state
ef4fd3656b fix(frontend): keep the stage-specific archive 403 copy; align journey reopen count
fc7c894ca6 test(frontend): assert W8 recovers the occupancy gate without a directory selection race
669b7bbf26 test(frontend): assert the W8 selection hint text rather than a title attribute
c6b84124ce test(frontend): select the upload directory in W8 before asserting recovery
bea468ab24 test(frontend): capture FE3b owner screenshots at both 1280 and 1920
5a0cdbad9c fix(frontend): keep the simulated stale-baseline node APPROVED per DC89
```

## 11. 审核建议

按 kickoff §13.4：审核范围 `fe-fe3a-exit..<本 handoff 提交>`；重点核对 §5.5 的 fixture 与两层
PAX、§6.1 的文案/禁用顺序与指针恢复、§6.4 的处置优先、以及 05 的真实旅程；独立的 07/05 运行
（不依赖本 handoff 的日志）用于确认。审核通过后由 04 运行 mock 全量、journeys 与上传包校验，
再决定 FE3b 退出。
