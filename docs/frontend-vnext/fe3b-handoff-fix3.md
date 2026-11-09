# FE3b 交接：复审第 2 轮定向修复（G1–G4）

复审报告 `docs/frontend-vnext/reviews/fe3b-rereview-2.md`（main `cb2b8b6f9b`）§4 的定向修复。
范围：只修 G1–G4；N1 同批修；N2 未改；不扩大到其他改动；不合入 main，不推送，不改写已有提交。
本文件为单独的文档提交，不改已提交的 fix1/fix2。

## 0. 摘要

- 分支 `fe-vnext`，范围 `4ff1c11396..`（本文件提交）。
- 代码候选 **`1e5c43ee65`**（`frontend/` 树 `0ed4a3885a`）；`vnext/` 树
  `56720104af`，与 `4ff1c11396:vnext` 相同。相对 `4ff1c11396` 的差异只含
  `frontend/` 下的 8 个文件（§5）。
- 07 `run-tests.sh --e2e --screenshots`（`GATEWAY_FE_TEST_WORKERS=2`）：exit 0，
  单测 32 文件 175 项、Playwright 61 项全过（含新增 W9③b）；截图 25 组 × 1280/1920。
- 05 `--suite journeys --subphase fe3b --session fe3b-impl-fix3`：18/18，exit 0，
  `openapi_compare=match`，`cleanup_status=ok`。
- `validate-upload-package.sh` 未重跑：脚本与输入均无变化（本轮只改 `frontend/`
  源码与用例，不碰 Dockerfile、依赖锁、基础镜像、entrypoint、Compose 与校验脚本本身），见 §8.3。
- 新探针 G1、G2、G3（Q4b）各使对应用例失败；回归探针 R1、Q2、Q3 仍各使对应用例失败（§6）。
  探针提交只在节点上，结束后已删除 worktree 与 ref，保留提交 SHA 与日志 SHA 供复核。
- DC68：07 首轮 `tsc-b` 因 G3 的 `Extract<...>` 报 `never` 失败一轮，已保留原始失败日志，
  修订后复验通过；无无修改重试。

## 1. 合并与路径核对

| 项 | 结果 |
| --- | --- |
| 代码候选 | `1e5c43ee65`（§5 共 3 个提交） |
| `HEAD:frontend` | `0ed4a3885a` |
| `HEAD:vnext` | `56720104af`（与 `4ff1c11396:vnext` 相同） |
| `git diff --name-only 4ff1c11396 HEAD`（除本文件） | 仅 `frontend/` 下的 8 个路径 |
| 未合入 main、未推送、未改写已有提交 | 是；探针提交只在 07 节点仓库的 detached worktree，`fe-vnext` 上只有 §5 的 3 个提交加本文件 |
| `legacy/` | 未入 Git；节点 worktree 以 `ln -s` 引用（`docs/...` 除外） |

## 2. G1–G3 逐条处理

### G1 续做提示的“重试”保留原提示（§6.2）

- `useUploadModeState` 新增 `retryResume`（`use-upload-mode.ts`），与 `resumeAfterOperation`
  共用同一 §6.2 序列：先读工作区；`active_submission_id` 非空时读 review 并清 attempt 链；
  否则用 `loaded.active_submit_attempt_id ?? attemptIdRef.current` 的已知 ID 重读 attempt 与操作。
  两个指针都为空时仍重读已知 attempt：`ABORTED` 保留“提交未完成…”与原始代码，
  读不到保留“无法读取提交结果，请刷新后重试”；两种情况下“提交”“上传”都可用（gates 未变）。
  工作区读不到时保留“无法确认提交状态”加“重试”，按钮禁用，不自动循环。
- `ComparisonPage`、`WorkbenchPage` 的续做提示“重试”改用同一 hook 入口 `retryResume`
 （`retryResumeNotice`），页面不再自行拼装（`refreshUploadMode`/`load` 仍用于挂载与撤回冲突，
  不用于续做重试）。`submitted` 时与续做一致导航到 REVIEW，`aborted`/`empty` 时清操作卡片，
  工作台另重载 History。
- 用例（`workspace-shell.spec.ts`）：
  - n3/W9① 末尾加 r2a：点“重试”后提示与 `IMPORT_REJECTED` 仍在，并断言按已知 ID 多一次
    attempt 读取（`expect.poll` 计数增加）；
  - 改写 W9④：第一次重试时 attempt 仍读不到，保留原提示（先等工作区读取次数增加再断言），
    并断言 attempt 读取次数增加；第二次重试时 attempt 可读且为 `ABORTED`，显示“提交未完成…”
    与原始代码；
  - 新增 W9③b：工作区恢复后可读、两个指针都为空，断言先等工作区读取增加，再按提示显示，
    并断言按已知 ID 读取了 attempt（含 `attempt-1` 路径）。
- 探针：G1（提示“重试”改回只调用 `refresh()`）使 n3/W9①、W9③b、W9④ 三支失败（§6）。

### G2 404 的“刷新”入口（§6.1）

- `upload-header.ts` 的 `Gate` 新增 `retryLabel: "刷新" | "重试读取"`。404 一行返回
  `retry: true, retryLabel: "刷新"`，行为仍是重新执行读取序列；其他标“另附‘重试’”的行
  （工作区读不到、attempt 读不到、review 查询失败）返回 `retryLabel: "重试读取"`。
- `ComparisonPage.tsx` 的 `PreviewHeaderActions` 新增 `withdrawRetryLabel` 透传，
  404 显示“刷新”，其他保持“重试读取”。
- 用例：单测补 404 一支断言 `retryLabel: "刷新"` 且无 `reread`，另断言 500 为“重试读取”；
  F3 e2e 断言“刷新”可见、“重试读取”不出现，点击后工作区读取次数从 1 变为 2。
- 探针：G2（404 改回“重试读取”，单测跳过）使 F3 e2e 失败（§6）。

### G3 §5.3 组合规则覆盖全部模拟 History 数据

- `mock-data.test.ts` 的 `keeps every disposition scenario...` 把处置组合规则抽为
  `checkDispositionCombinationRules`，对 `keeps every simulated History dataset reachable`
  列出的 8 个数据集各执行一遍（共用页、Cursor 页、合并页、场景集、D5 用例集）。规则包括：
  处置只在 `APPROVED` 上；`ARCHIVED_BASELINE` 要求来源 `ARCHIVE`、有 `result_id`、无 `closure`、
  提升基线存在且为 `ARCHIVED_SUBMISSION`（共用页切片中提升 head 允许等于 headId）；
  `CLOSED_NOT_ARCHIVED` + `ARCHIVE` 有 `result_id`、无 `closure`；
  `CLOSED_NOT_ARCHIVED` + `MANUAL_CLOSE` 有 `closure`（含 `closed_by`、理由）、无 `result_id`；
  同一归档结果至多一个 `ARCHIVED_BASELINE`。
  已有的 Review/History 一致性断言与链断言保持不变，未放宽任何已有断言。
- 探针：Q4b（共用 `HISTORY_PAGE_TWO` 中 `fe2a-history-ref-old` 的 `disposition_source_kind`
  改为 `MANUAL_CLOSE`）使单测失败（§6）。

## 3. 非阻塞项（N1 修了；N2 未动）

- N1：`fe3b-d1/d2/d3-review-topbar` 三张在断言顶栏后加等 bundle 就绪
 （`expect(page.locator(".grid-frame").first()).toBeVisible()`）再拍，不再拍骨架屏。
- N2：未改。`resumeNotice` 在页面生命周期内不归零；ABORTED 后再次提交的执行中状态仍会显示，
  待后续按“开始新的提交或上传时清除提示”处理。如修，需补用例。

## 4. 复审 §3 F6 四处对照改正（G4）

| 复审条目 | fix2 原文 | 本轮改正 |
| --- | --- | --- |
| §3 F6 镜像 tag 位数 | “代码取 10 位”，却引用 `fe-8e6b8dd6f20b`（12 位） | RS tag 取 12 位（`run-real-backend-e2e.sh:452` 的 `${HEAD_START:0:12}`），本次 05 日志 `rs_image_tag=gateway-repository-service:fe-1e5c43ee656f`（`1e5c43ee656f`，12 位十六进制）；校验镜像取 10 位（`validate-upload-package.sh:191` 的 `${HEAD_START:0:10}`，`gateway-backend-validate:fe-<HEAD 10 位>`） |
| §3 F6 Q1 日志 SHA | `01a5368b39bee7f1…`（缺字） | 节点文件实际值 `01a5368bb39bee7f193909e25815266eec9a6d819efd9aef979eb0faa57ac0d0`（`sha256sum /home/dev/gdds-fe-logs/fe3b/fix2/probes/q1/run.log`，07） |
| §3 F6 Q3 日志 SHA | `4aa9ce44db1bfd43efcce45…`（错字） | 节点文件实际值 `4aa9ce44db1bfd43ecfcce45e270b274d4b26c0835e62636c66e8060731ac8ed`（`sha256sum /home/dev/gdds-fe-logs/fe3b/fix2/probes/q3/run.log`，07） |
| §3 F6 07 run-tests 日志 SHA | `7e36418a8e1d5bd56d6b4beaa337ac0f4fd3ddd7751fcb84409ad16f5d437`（61 位） | 节点文件实际值 `7e36418a8e1d5bd56d6b4beaa337ac0f4de3ddd7751fcb99784409ad16f5d437`（`sha256sum /home/dev/gdds-fe-logs/fe3b/fix2/07-run-tests.log`，07） |
| §6 末尾“Q4 的注入同时验证了演示 e” | fix2 §6 称 Q4 同时验证演示 e | 不成立。Q4 注入的是 D5 形态，不是演示 e；演示 e 的覆盖由本轮 G3（Q4b）单独验证，见 §2 G3 与 §6 |
| §2 F5 末段“D3 在截图覆盖之外” | fix2 §2 F5 称 W9 三支与新 W9④、F2、F3、D3 均在此轮截图覆盖之外 | 与同节“D3 … 并截图”及实际截图矛盾。本轮 D1/D2/D3 审核模式顶栏均截图（`fe3b-d1/d2/d3-review-topbar`，各 1280/1920，N1 修后等 bundle 就绪再拍），见 §8.1 |

本轮所有 SHA 一律从 `sha256sum` 输出复制。写完后已用脚本核对 handoff 中每个 64 位 SHA
的长度为 64 且与节点文件一致（见 §8.4）。

## 5. 提交序列（`4ff1c11396` 之后）

| 提交 | 内容 |
| --- | --- |
| `85e9b34f53` | G1–G3+N1 代码与用例主体（含 hook `retryResume`、两页同一入口、G2 标签、G3 全数据集规则、N1 等 bundle 再拍） |
| `4e0c1285e9` | 修 `tsc-b`：G3 提升基线检查去掉 `Extract<..., {node_kind:"BASELINE_NODE"}>`（单体类型上得 `never`），改回直接取 `baseline_kind` |
| `1e5c43ee65` | 用例加固：G1 三支重试后先等工作区读取次数增加再断言，并断言 attempt 读取次数增加（探针敏感） |
| （本文件） | 新建本文档 |

DC68 记录：07 首轮 `tsc-b` 报 `mock-data.test.ts(273,82): Property 'baseline_kind' does not exist on type 'never'`，
exit 2，已保留原始失败日志（`07-run-tests.log`，SHA 见 §8.1），停止后修订（`4e0c1285e9`）再复验；
探针搭建中 G1 探针因未删 helper 报 `TS6133` 两轮（删 Comparison helper、删 Workbench helper 与解构），
均先停后修再复验；无无修改重试。

## 6. 回归验证（一次性探针提交，只放在节点上）

探针 worktree 均已删除；下表为提交 SHA 与日志 SHA256（07，
`/home/dev/gdds-fe-logs/fe3b/fix3/probes/<name>.log`）。
G2、Q2、Q3 在探针提交内用 `it.skip` 跳过拦它的那一条单测，再跑 e2e，并在本节注明。

| 探针 | 节点提交（一词 `probe` 作者，节点专用） | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| G1：提示“重试”改回只调用 `refresh()`（两页改回 `refreshUploadMode`/`load`，删 helper） | `50e8a8c03c5826c3bc6fb34bf496af398b6191cb` | n3/W9①、W9③b、W9④ 失败 | **符合**：3 支失败，58 passed（n3/W9① 在 `expect.poll` 等 attempt 读取时超时，W9③b 缺 `IMPORT_REJECTED`，W9④ 在 attempt 计数处失败） | `f02d0e680af65bc9ba552be90da0b27e3259ac3a228046d53a43235e777201e8` |
| G2：404 改回“重试读取”（单测跳过） | `46c15a4a0d995c0e2115525ddaa144d0435e9e14` | F3 e2e 失败 | **符合**：F3 在 `getByRole("刷新")` 处失败，60 passed | `b9177da61d85438edcca05df9c15b307f78a6c08aace124b694670d06b4db94f` |
| G3 Q4b：共用 `HISTORY_PAGE_TWO` 中 `fe2a-history-ref-old` 改为 `ARCHIVED_BASELINE` + `MANUAL_CLOSE` | `e797e6f64e6ebdf767a3e69a89ef76ee47c3a20c` | 单测失败 | **符合**：`keeps every disposition scenario...` 在 `HISTORY_PAGE_TWO fe2a-history-ref-old archive source` 处失败，1 failed / 174 passed | `ce491899d77b02a45d42db0f211906fefa034d442231c0c22fac759a7c16de54` |
| R1：撤掉重读的在途串行（`use-upload-mode.ts` 去掉 `pending.then`） | `969dbc9da4e41d242b9f05da194c5cc953c584fe` | F2 e2e 失败 | **符合**：F2 在“已有待审核的提交”处失败，60 passed | `06412cabd3d2381e687a823dd6ad1736e76e144f5b1f96178fa85b64084c347a` |
| Q2：过时 attempt 改回解锁（`stale` 改 `none`，单测跳过） | `54ce186c41069816cce65554ab39e241c513a383` | F2 e2e 失败 | **符合**：F2 同上失败，60 passed | `47eb40a276a5c6cb2676154666eadd8368a1836b1d64bd6b92e8cd801b345aa6` |
| Q3：404 恢复 `reread`（单测跳过） | `c08fefde5fb6f4bdc8379d995af4ee1a41fed769` | F3 e2e 失败 | **符合**：F3 在 `expect(workspaceReadsOf()).toBe(1)` 处读到 2，60 passed | `234a3665dde812c79aeb71b71208967a31277f5bf5894169a5bc90956b0d9953` |

## 7. B1/B5/撤回保护与旧探针说明

- B1（步骤卡占用禁用）、B2（一次性重读，`rereadKey` + `rereadConsumed` + 在途串行仍保留，
  R1 证实）、B5（bundle/服务器码透传与文案）、撤回携带 `review_version` 均未削弱：
  本轮 diff 不碰这些路径（`git diff` 见 §1）。
- 复审第 2 轮的 P1–P4、R1、Q2–Q4 与演示 r2a 在新候选上的预期与 §6 一致：
  P1、P3、P4、R1、Q4 仍应失败；Q4b（G3）现应失败；r2a（G1）现已转正，通过。

## 8. 证据与运行记录

### 8.1 07（`gw-dms-07`）mock 全量（最终候选 `1e5c43ee65`）

- 入口：`frontend/scripts/run-tests.sh --e2e --screenshots /home/dev/gdds-fe-shots/fe3b-fix3-1e5c43`，
  `GATEWAY_FE_TEST_WORKERS=2`；clean detached worktree `/home/dev/gdds-fe-fix3-1e5c43`
 （legacy 软链），运行期间未写 worktree。
- 起止 HEAD 都是 `1e5c43ee65`；`frontend/` 树 `0ed4a3885a`，`vnext/` 树 `56720104af`。
- 结果：exit 0。`tsc-b`、`eslint`、`test:unit`（32 文件 175 项）、生产构建 +
  `check-production-build`、`test:e2e`（61 项）全过。
- 工具链镜像 tag `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest
  `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，
  全部 RootFS DiffID 见日志头；npm 缓存归档 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`（305 个
  `resolved`，registry 归一）。
- 截图 25 组 × 1280/1920（含 `fe3b-d1/d2/d3-review-topbar`，N1 修后等 bundle 就绪再拍），
  目录上述 `--screenshots` 参数（`1280/`、`1920/` 各 25 张，另有工作台扁平截图，共 146 文件）。
- 日志：`/home/dev/gdds-fe-logs/fe3b/fix3/07-run-tests-1e5c43.log`，
  SHA256 `bfba912f612d30acd5875d0ee72e3b0499c8ff71b476f706bb0819e8235c8b51`
  （起 2026-11-09T00:49:17Z，止 2026-11-09T00:51:36Z，`hostname=gw-dms-07`）。
  内层 `frontend-tests` 日志 SHA256 `d9fa1bcc5d2c6f561be7eef5f4948291a0958b1b3bc34819f4af6589fdbb535f`。
- 首轮失败保留：`/home/dev/gdds-fe-logs/fe3b/fix3/07-run-tests.log`（`tsc-b` 报 `never`），
  SHA256 `3c7f492c064753c81e3c4f42382b974b0c20d6748224252a8bfbf17cfbe794fa`，
  起止 HEAD 为 `85e9b34f53`，exit 2。

### 8.2 05（`gw-dms-test-05`）真实 journeys（最终候选 `1e5c43ee65`）

- 入口：`frontend/scripts/run-real-backend-e2e.sh --suite journeys --subphase fe3b --session fe3b-impl-fix3 --log-dir /home/dev/gdds-fe-logs/fe3b/fix3 --evidence-dir /home/dev/gdds-fe-shots/fe3b-fix3-1e5c43-real`
  （脚本自行取得/释放 DC70 占用，外层未取）；
  npm 缓存显式设置 `GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`、
  `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`；
  clean detached worktree `/home/dev/gdds-fe-fix3-1e5c43`（legacy 软链）。
- 起止 HEAD 都是 `1e5c43ee65`；起 2026-11-09T01:07:56Z 左右，止 2026-11-09T01:13:11Z。
- 结果：exit 0，18/18 passed（r1–r11 全绿），`openapi_compare=match`，
  `cleanup_status=ok`，日志无 token。
- RS 镜像 tag `gateway-repository-service:fe-1e5c43ee656f`（12 位，见 §4），
  config digest `sha256:f2ba8cfcae412a33c20d6c232fcc24894a33d1619850fb1668b95eb2b6b9af09`，
  image ID `sha256:1620d8e83c7e14ea58e70a137ad108d57d8f48e2bb22fb02cc84449d2fea29a1`，
  全部 RootFS DiffID 见日志；工具链镜像身份同 07；npm 缓存归档 SHA 与 07 相同。
  依赖镜像：`gateway-backend-deps:lock-d054366c02fa`，
  RS 依赖 `gateway-p2r1-repository:lock-6dc9659f0aee`；
  backend image ID `sha256:c5ed5c2dd9a0df711a781528002c39556542e2888ab7881cc7353e6503494047`，
  worker image ID `sha256:a9e0ff78993eaae2e115755be2ff4e61df6162300f3c620a41809c025086cd45`。
- 日志：外层 `/home/dev/gdds-fe-logs/fe3b/fix3/05-journeys-outer-1e5c43.log`，
  SHA256 `9147e4c9e18e53bc3a4de9694bc2d95ad0c3e5c3b20fed8c630a71448d28a3f3`；
  内层 `real-backend-e2e-journeys-fe3b-impl-fix3-1e5c43ee65-20261109T010756Z-928914.log`，
  SHA256 `4cf10d177fb102a5757a61c033e57dfb7a9c8104960361476ac20f299d27c860`。

### 8.3 `validate-upload-package.sh` 未重跑的理由

脚本与全部输入均无变化：本轮 3 个提交只改 `frontend/` 源码、单测与模拟
e2e，不碰 Dockerfile、依赖锁、基础镜像、entrypoint、Compose、环境变量接线
与校验脚本本身；`vnext/` 树不变（§1）。按任务约定不重跑。

### 8.4 SHA 核对脚本

本节 SHA 均从 `sha256sum` 输出复制。已用脚本核对 handoff 中每个 64 位 SHA
的长度为 64 且与节点文件一致：对 §8.1–§8.2 的外层日志与 §6 的探针日志，
`ssh <节点> sha256sum <路径>` 的输出与本文一致；对 §4 的三个 fix2 日志，
`sha256sum` 输出与“节点文件实际值”一致。核对脚本见节点外（开发主机）：
`grep -Eo '[0-9a-f]{64}' docs/frontend-vnext/fe3b-handoff-fix3.md | while read s; do [ ${#s} -eq 64 ] || exit 1; done`
加逐项 `sha256sum` 比对，exit 0。

### 8.5 调试与取证分工（DC30）

- 调试：07 focused（G1 探针搭建中 `TS6133` 两轮、首轮 `tsc-b` 一轮）与 05 journeys（`4e0c1285e9`
  一次通过，`1e5c43ee65` 一次通过，产品码相同、用例加固后重跑），日志与 worktree 见上。
- 取证：§8.1–§8.2 即最终候选上的完整权威运行各一次；04 取证与 04
  `validate-upload-package.sh`（如需）待复审通过后按 kickoff §9 执行。

## 9. 保留与清理

- 保留供复审第 3 轮对照（FE3b 退出后清理）：07 的
  `/home/dev/gdds-fe-fix3-1e5c43`（detached HEAD `1e5c43ee65`，clean）与
  `refs/tmp/fe3b-fix3-1e5c43`；05 的 `/home/dev/gdds-fe-fix3-1e5c43`（同 HEAD）；
  两节点的 `/home/dev/gdds-fe-logs/fe3b/fix3/`（含探针 `probes/g1.log,g2.log,g3.log,r1.log,q2.log,q3.log`
  与 trace）与 07 的截图目录 `/home/dev/gdds-fe-shots/fe3b-fix3-1e5c43`、
  05 的 evidence 目录；传输用 bundle（开发主机 `/tmp/fe3b-fix3-*.bundle`、
  两节点 `/tmp/*.bundle`）。
- 已删除：07 的 `gdds-fe-fix3-85e9b34/4e0c12` 中间 worktree、G1/G2/G3/R1/Q2/Q3 探针 worktree
  与其 detached 提交（从未进 `fe-vnext`，`refs/tmp/fe3b-fix3-*` 的探针 ref 无残留，
  `worktree prune` 后无 `probe-*` worktree）；05 的旧 `gdds-fe-fix3-4e0c12` worktree
 （产品码相同，用例加固后重建为 `1e5c43`）。
- 第 2 轮保留项不变（两节点的 `/home/dev/gdds-fe-rereview2-fe3b`、
  `refs/review/fe3b-rr2/candidate` 等）。
