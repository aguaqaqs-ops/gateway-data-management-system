# FE3a 审核报告

- **审核对象：** 分支 `fe-vnext`。
  - 代码候选 `bd320eaee5912ca9fe81b2a67fdf26a7d01144d9`，`frontend/` 树 `22c6cc27aa`；
  - handoff 提交 `dd8168b2b8fee1b9e4969975bf6845d4557fec65`（只新增 `docs/frontend-vnext/fe3a-handoff.md`，`frontend/` 树相同）。
- **范围：** `fe-fe2c-exit..dd8168b2b8`。来自 main 的提交（经合并提交 `a3834a977c` 带入，main `8983fe86a6`）不在前端审核范围内。
- **依据：** [FE3 kickoff](../fe3-kickoff.md)（main `3d3373e7fa`，已含于 `8983fe86a6`）§3.2、§3.3、§4、§5.2、§5.4、§7、§8.1、§8.4、§9、§10；
  [FE2 kickoff](../fe2-kickoff.md) §6.5、§7；AGENTS“前端测试（FD7）”。
- **日期：** 2026-11-05。
- **结论：定向修复。**
  - 已做到：路径核对通过；上传输入迁移逐字节不变；类型一致性检查有效；两项传输的记录完整、可复核；05 上我独立运行的全量 runner 与 `--suite smoke` 都通过；
    三个探针中“占用目录已存在”“快照改一处”的行为符合 kickoff。
  - M1 数据可复核，我的复测结果与之一致。按 §8.4 的默认标准不需要改流式，但 handoff 漏报了浏览器主进程的增量，需由 owner 一并判断（§5）。
  - 运行框架有 6 项需要修复：只播种一个 scope；中断后记 `exit_code=0`；残留检查误判后把节点标为 `cleanup-failed`；OpenAPI 比对不经代理且不留 diff；
    冒烟没有等到 bundle 下载失败再断言；日志字段与会话名不符合 §4.2、§4.9（B1–B6）。
  - 带入项：n3 为了让用例通过改了产品行为，提示与禁用原因自相矛盾（B7）；M7 摘要仍显示工作区原始 ID（B8）；n8 用了红色错误样式（B9）。
  - 上传输入只备了一份真实 e2e 输入，§4.6 要求的上传序列没有写出（B10）；该输入方案的设计决定没有书面记录，**交设计会话**（§6）。
  - handoff 有几处与实际不符，随修复一并改正（B11）。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| `git rev-parse dd8168b2b8:vnext` 与 `8983fe86a6:vnext` | 都是 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96` |
| `git diff --name-only 8983fe86a6 dd8168b2b8` | 只含 `frontend/`（28 个文件）与 `docs/frontend-vnext/fe3a-handoff.md` |
| kickoff 确认提交 `3d3373e7fa` 是否在合入的 main 中 | 是 |

| 内容 | 主要文件 |
| --- | --- |
| 运行框架与冒烟 | `scripts/run-real-backend-e2e.sh`、`playwright.real.config.ts`、`e2e-real/smoke.spec.ts`、`e2e-real/fixtures/real-{sql.sql,logics.xml}`；`vite.config.ts`（preview 也代理） |
| 上传输入 | `src/test/fixtures/source/upload-inputs/*`（8 个）；生成器改为读文件 |
| 类型一致性 | `src/features/api/generated-types.test.ts` |
| M1 | `scripts/run-packaging-measure.sh`、`playwright.packaging.config.ts`、`e2e-packaging/packaging-memory.spec.ts`；`UploadStepCard.tsx` 加 `data-phase` |
| 带入项 | `submit-summary.ts`（新增）、`SubmitDialog.tsx`（M7、n8）、`UploadStepCard.tsx`（n8）、`ComparisonPage.tsx` 与 `e2e/workspace-shell.spec.ts`（n3） |
| 调试中的修复 | `client.ts`：上传 manifest 的 `raw_sha256` 改为 `sha256:<hex>`（FE2 的缺陷，只有真实 backend 能发现；修正正确） |

## 2. 证据与独立运行

### 2.1 handoff 中的 05 证据

| 项 | 核对 |
| --- | --- |
| 冒烟日志 | `real-smoke-bd320eaee5/real-backend-e2e-smoke-bd320eaee5-20261105T080349Z-1255447.log`，SHA256 `80d2f0bc…7e94` 一致；4 passed，`openapi_compare=match`，`cleanup_status=ok`，`exit_code=0`；日志与 Compose 日志中没有 token |
| 全量 runner | handoff 所记日志与截图聚合 `307feb80…e0f` 一致（94 张） |
| M1 报告 | 三份 JSON 的 SHA256 一致；每次的 `VmHWM` 基线都等于 `VmRSS`（`clear_refs` 生效）；FULL 场景 `input_completeness=FULL`，两个包都有 `size_bytes` |
| 依赖镜像 | 05 与开发主机的 `dependency-input-sha256` label 加全部 `RootFS.Layers` 的摘要相同；来源提交 `3123c3b760` 在 main 上，vnext 树 `2791d3ff3d` |
| 组态目录 | 三个 `SHA256SUMS-*.txt` 的 SHA256 与 handoff 一致；在 05 上 `sha256sum -c` 全部通过（19 / 19 / 528 个文件） |

### 2.2 我在 05 上的运行

审核 worktree `/home/dev/gdds-fe-fe3a-review`（detached `dd8168b2b8`，clean），源码经 git bundle 传入（SHA256 `63fff7e1…01be`）。

| 运行 | 结果 | 日志 |
| --- | --- | --- |
| `run-tests.sh --e2e --screenshots` | exit 0；29 个单测文件 136 项、34 个 e2e 通过；截图 94 张 | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261105T082335Z.log`，SHA256 `25089c31…a0f3` |
| `--suite smoke` | exit 0；4 passed；`openapi_compare=match`；`cleanup_status=ok`，运行后无本次容器、网络、卷、RS tag 与占用标记 | `/home/dev/gdds-fe-logs/fe3a-review/smoke-dd8168b2b8/real-backend-e2e-smoke-dd8168b2b8-20261105T082510Z-1273031.log`，SHA256 `1a0d68b9…3480` |
| M1 复测 t4 v1 FULL（3 次） | renderer 增量 651.2 / 640.2 / 668.2 MiB；浏览器主进程 424.9 / 422.1 / 418.9 MiB；与 handoff 一致 | 报告 `/home/dev/gdds-fe-evidence/fe3a-review/m1-dd8168b2b8/t4v1-full.json`，SHA256 `9a82315b…d45c` |

截图中有若干张与实施方逐字节不同（如 `archive-mainline-result-1280`），属页面计时等动态内容，不是问题。

### 2.3 探针（一次性 worktree，会话名改为 `fe3a-review`）

探针提交只在 05 上：`9c4abeb4e4`（会话名）、`bcee3fa846`（在其上把快照 `info.title` 改一处）。

| 探针 | 结果 |
| --- | --- |
| 占用目录预先存在（内放他人标记） | 符合：exit 3；他人标记逐字节不变；未创建容器 |
| 快照改一处 | 符合：`openapi_compare=mismatch`，exit 2，未运行浏览器用例，清理正常。日志目录只有原始运行时 JSON，没有两份规范化 JSON 与 diff（B4） |
| 运行中途中断，SIGINT 发给进程组（等同 Ctrl-C），时点为套件开始后 3 秒 | 清理正常、无残留。**但中断没有生效**：`docker exec` 继续跑完，`tee` 已退出，日志只剩第 1 个用例，却记 `suite_exit=0`、`exit_code=0`（B2） |
| 运行中途中断，SIGTERM 发给脚本进程，同一时点 | 清理正常、无残留；日志没有 `suite_exit`，仍记 `exit_code=0`，脚本以 0 退出（B2） |
| 补充：占用目录不存在，但他人容器占着 8000 | 脚本获取占用后在残留检查处退出（正确）；随后清理核对把他人的 8000 记为本次残留，`cleanup_status=failed`，占用标记被整体覆盖为一行 `purpose=cleanup-failed (fe3a-review)`，节点保持占用（B3） |
| 意外发现 | 第一次中断探针时，我的 ssh 命令行含有 “dolt” 字样，脚本的 `pgrep -f dolt` 把它当成 dolt 进程，开跑即退出，并同样留下 `cleanup-failed` 标记（B3） |

探针留下的标记、容器与 worktree 都已清理。

## 3. 需要修复（阻塞）

### B1 只播种一个 scope，handoff 误称 5 个

`run-real-backend-e2e.sh:331-397` 只生成一条映射、一个仓库、一个 `business_baseline_node_id`，五个身份共用同一 scope。
handoff §2.2 写“播种 5 个 scope”，日志 `identity_scopes=smoke(submitter/…)` 也是一个 scope 中的五个身份。

- kickoff §4.6 要求每个互相独立的旅程用自己的 scope，多 scope 时 key 与节点 ID 互不相同、映射全部在 backend 启动前写好；§3.1 把运行框架放进 FE3a，就是为了 FE3b“只需加场景”。现在 FE3b 要先改播种。
- 冒烟本身因工作区按 actor 隔离，用一个 scope 结果不受影响，但框架没有多 scope 能力，审核要求的“多 scope 播种的 key 与节点 ID 互不相同”无从核对。
- **修复：** 播种改为按 scope 列表循环（每个 scope 各自的 key、仓库、节点 ID、身份组），映射一次写好再起 backend；冒烟至少用两个 scope（例如“上传与 Preview”一个，“权限拒绝”一个），日志逐 scope 记录仓库 ID 与 `INITIAL` 提交 ID。改正 handoff。

### B2 中断后记录 exit 0

见 §2.3。脚本只有 `trap cleanup EXIT`，`cleanup` 中 `exit_code=$?` 在信号退出时为 0（`run-real-backend-e2e.sh:86-87`）；套件阶段的 `docker exec … | tee`（`:512-519`）收到 Ctrl-C 后继续运行，结果不再进日志。

- 后果：一次被中断、结果不全的运行，日志与退出码都显示成功。日志是证据（§4.9），这一点不能接受。
- **修复：** 为 INT、TERM、HUP 设 trap，记录信号与非 0 退出码（130/143/129）后进入同一清理；清理第一步删除工具链容器，`docker exec` 随之结束。用例结果以 Playwright 的结果文件（例如 JSON reporter 输出到日志目录）为准，不只依赖 `tee` 的输出。复做 §2.3 的两个中断探针，日志应记非 0 退出码。

### B3 残留检查误判，并错误地把节点标为 `cleanup-failed`

- `pgrep -f dolt`（`:122`、`:218`）匹配整条命令行，任何参数里带 “dolt” 的进程都会命中（见 §2.3 意外发现）。应按进程名匹配（`pgrep -x dolt`，或读 `/proc/*/comm`）。
- 清理核对（`:118-125`）对 8000 端口与 dolt 不区分“本次创建”与“运行前已存在”。运行前检查发现他人资源而退出时，清理把它当作本次清理失败，保留标记并改写为 `cleanup-failed`（§2.3 补充探针）。
  kickoff §4.2 的意思是：运行前不满足就退出、不清理他人资源，这时应正常释放本次的占用；只有本次已经起过栈（`PROJECT_NAME` 已设）时，8000 与 dolt 才属于清理核对的内容。
- 改写标记时整体覆盖（`:140`、`:144`），会话名、开始时间、hostname、worktree、HEAD 都丢了。kickoff 是“把用途改写为 `cleanup-failed`”：只改 `purpose` 一行，其余保留，另加失败时间。
- 运行前残留检查（`:222`）只查容器名前缀，没有查本脚本前缀的卷与网络（§4.2 第三点）。
- **修复：** 以上四点；补一个回归探针：他人占用 8000 时脚本退出，节点不留标记。

### B4 OpenAPI 比对不经代理，失败时不留 diff

`run-real-backend-e2e.sh:425-450` 在宿主机直接请求 `http://127.0.0.1:8000/openapi.json`，而且在工具链容器启动之前。

- kickoff §5.2：在工具链容器内经 preview 服务器的代理读取，顺带证明代理可用；不一致时日志目录保存**两份规范化 JSON 与 diff**。现在只保存原始运行时 JSON（探针 3 已证实）。
- §5.1 要求宿主机用 `python3 -I`，这里是 `python3`。
- **修复：** 先构建并起 preview，再在容器内经 `http://127.0.0.1:4173/openapi.json` 取回，交宿主机 `python3 -I` 规范化比较；不一致时写 `openapi-snapshot.normalized.json`、`openapi-runtime.normalized.json` 与 `openapi.diff`。比对不通过仍不运行浏览器用例。
  这会把比对挪到 `npm run build` 之后，没有关系；也可以把 preview 与 Playwright 拆成两步，由脚本先起 preview。

### B5 冒烟判据不完整

`e2e-real/smoke.spec.ts`：

- **bundle 下载失败后的未捕获错误没有被等到。** kickoff §3.3：bundle 下载这一步不作断言，但页面上不能出现未捕获错误。用例在读到 Preview 结果后立即检查 `pageErrors`（`:153-159`），下载请求此时可能还没返回，解析失败也还没发生。
  应先等到 `GET …/preview-results/{id}/bundle` 的响应，再等页面进入下载失败后的稳定状态（界面上的失败提示），然后断言没有 `pageerror`。
- **Preview 结果的匹配过宽。** `path.includes("/preview-results/")`（`:133`）也匹配 `…/bundle`，当前 backend 的 `/bundle` 正好返回 200 的 JSON。改为 `/\/preview-results\/[^/]+$/`。
- **“组态树只有 `INITIAL`”没有断言。** 现在只看到“初始基线”文字（`:111`）。应由程序断言 `GET /v1/history` 返回一个节点、`baseline_kind = INITIAL`、`head.node_id` 与之相同。
- `playwright.real.config.ts` 没有 `screenshot: "only-on-failure"`，与 §4.7“失败时保存 trace、截图”不符。

### B6 日志字段与会话名

- **会话名写死为 `fe3a-impl`**（`:66`），审核与取证无法按 §4.2、§13.2 使用 `fe3a-review`；FE3b 还要用 `fe3b-impl`。我的独立冒烟只能以 `fe3a-impl` 运行，探针要改源码才能换名。
  改为必填参数（例如 `--session <名称>`），校验格式，写进日志。项目名前缀与残留检查中的 `fe3a` 同理改为由子阶段参数决定（§4.4）。
- **§4.9 要求、日志中没有的字段：**
  - 身份名与**权限**（现在只有名字）；
  - 占用标记的内容、获取与**释放**时间，flock 的释放时间（现在只有获取路径）；
  - 每个用例的起止时间（list reporter 只有耗时）；
  - 结尾的 `HEAD:frontend`、`HEAD:vnext` 树与 worktree 是否 clean（开头也只检查、不记录 clean）；
  - 依赖镜像的 `RootFS.Layers`（§4.3；现在只记数量）。
- **worker 就绪**（§4.4“等 `/readyz` 与 worker 就绪”）没有等。worker 启动后会打出 `code=worker_ready`，可以按 Compose 日志等待。冒烟通过不受影响，但 FE3b 的旅程会依赖它。

### B7 n3：用改产品行为的方式让用例通过

`ComparisonPage.tsx:193` 把 `submitResumeActive` 改为不可变，删除了 `ABORTED`、读取失败、操作失败三处的 `setSubmitResumeActive(false)`。

- 后果：续做得到 `ABORTED` 或读取失败后，页面显示“提交未完成，请检查上传与 Preview 后重试”或“无法读取提交结果，请刷新后重试”，同时“提交”一直禁用，禁用原因仍是“提交结果确认中，请稍候”（`:483`）。提示与禁用原因自相矛盾，要重试只能刷新页面。
- 这与 FE2c 的行为、也与 FE3b 的目标不一致：kickoff §6.2 写明 `ABORTED` 后两个指针都为空，按 §6.1 的表“提交”不再禁用。
- handoff §3.3 说明了来由：新用例断言“续做期间禁用”时，模拟接口很快返回 `ABORTED`，按钮已恢复可用，于是改了产品代码。问题在用例的时序，不在产品。
- n3 的完成标准只要求 e2e 覆盖，不要求改行为。
- **修复：** 恢复 FE2c 的行为。用例中让操作查询先停在 `RUNNING`（路由按信号放行），断言“提交”禁用且原因为“提交结果确认中，请稍候”；放行后断言 `ABORTED` 与读取失败的提示，以及“提交”恢复可用。
  如果实施方认为读取失败后应保持禁用，交设计会话定文案，不在本阶段自行改。

### B8 M7：摘要仍显示工作区原始 ID

`submit-summary.ts:76` 中“工作区”一行的显示值就是 `workspace_id`。真实 backend 上它是 UUID，截图 `submit-manual-recovery-1280` 中显示 `workspace-fe2b`。

- 完成标准（kickoff §7 M7）：摘要不显示原始 ID，拿不到显示名时才显示 ID。组态树中工作区的显示名是“工作区 <网关设备>”（截图 `manual-recovery-required-1280`：“工作区 gateway-17”），对话框已经读取了工作区，可以直接用 `gateway_device_external_key`；原始 ID 放悬停提示。
- 单测（`submit-summary.test.ts:42`）把原始 ID 写成了期望值，一并改。
- 修复后重拍 `submit-*` 中显示摘要的各张，交 owner 看图。

### B9 n8：用红色错误样式表示“需要管理员处理”

`SubmitDialog.tsx:211` 与 `UploadStepCard.tsx:340` 把这一行改成了 `.form-error`。

- 这一状态不是失败：系统仍在查询，可能最终成功（用例“FE2c 提交对话框显示需要管理员处理并可跟随到成功”）。同一对话框里已有警示样式 `.form-warning`（“Preview 结果已基于旧基线”）；工作台的同一状态用黄色警示卡片（截图 `manual-recovery-required-1280`）。
  n8 的标准是“使用同一区域其他提示的提示样式”，警示样式才是同一区域中语义一致的那一种。
- 排版（提示、ID、复制、正文分行）本身达标。
- **修复：** 改为警示样式；重拍 `submit-manual-recovery-1280/1920`，交 owner 看图。
- `UploadStepCard.tsx` 属于 kickoff §9 列出的打包代码文件。虽然只是样式改动，按 §9 仍在新候选上重测 M1（约 3 分钟），handoff 写明。

### B10 上传输入与上传序列不全

- kickoff §4.6 要求写出每个 scope 的上传序列，至少覆盖四类：第一次 MODIFIED_ONLY、归档后的 FULL（① + ②）、内容不同的再一次 MODIFIED_ONLY、`DIFFERENT_PROJECT`；并在 05 上让真实 backend 先走一遍这些输入。
  handoff §5 只列了冒烟实际做的一次上传，四类序列写成“留待 FE3b”。
- 共用 fixture 的三份 SQL 都含无 gid 的 `b1_n1_iec104_yc_list`，在真实 backend 上都会 `KEY_MISSING`。新增的 `real-sql.sql` 是 `sql-modified.sql` 给这张表补了 `gid` 列，`real-logics.xml` 与 `logics-3.xml` 相同。
  FE3b 需要的另外几份输入（第一次上传、归档后 FULL 的 ①②、replacement）都还没有，也没有经过真实 backend。
- **修复：** 按设计会话对 §6 的决定，备齐四类序列所需的真实 e2e 输入，写出每个 scope 的序列（每次提交相对当时基线的规范变化）；在 05 上逐份走到 Preview `SUCCEEDED`。
  FULL 与 replacement 的规范变化要在归档后才能完全证实，FE3a 先核对 Preview 成功与差异非空，handoff 注明。

### B11 handoff 改正

- §2.2 “播种 5 个 scope”（见 B1）。
- §6 判断写成“满足‘单次 1 GB 目录不超过 1 GiB’”，与 §8.4 不符。标准是：t4 v1 的 renderer 增量 ≤ 1 GiB；按目录大小线性外推到 1 GB ≤ 3 GiB。
- §6 只报 renderer。§8.4 要求记录全部进程，JSON 中有，handoff 应列出浏览器主进程的增量（见 §5）。
- §6 与 §2.3 写“生产构建”，kickoff §8.4 写的是开发构建。用生产构建更接近用户实际，我认为可以接受，但应作为偏差列出。
- §9 第 1 项写“设计会话已确认”，main 上没有记录（见 §6）。

## 4. 非阻塞意见

| # | 意见 |
| --- | --- |
| N1 | `packaging-memory.spec.ts:102` 写 `clear_refs` 失败被吞掉，`:268` 等待 FULL 文案的断言也被吞掉。本次数据证明两者都生效，但失败时应直接报错，不能静默得到错误数据 |
| N2 | `submit-summary.ts` 复制了组态树的标签规则（`view-model/workspace.ts:81-84`），注释写“与组态树同一规则”，实际不同：组态树显示“归档基线”，不带序号，“当前基线”是状态标签；摘要显示“当前基线（归档基线 1）”，用户在树上找不到“1”。建议抽出共用函数；树上是否显示序号交设计会话。`submissionDisplayName` 只在单测中使用 |
| N3 | `generated-types.test.ts` 自己写了一遍 `openapi-typescript openapi.json` 的参数，与 `package.json` 的 `generate:api-types` 可能不同步。可改为从 `package.json` 读取该脚本，或调用 `npm run generate:api-types -- -o <临时路径>` |
| N4 | 会话文件与 bearer 文件为 `0644`，放在 `${TMPDIR:-/tmp}` 下的 `0755` 目录。测试节点单用户，可以接受；建议节点上设置 `TMPDIR=/home/dev/gdds-test-tmp`（与后端一致），handoff 写明 |
| N5 | 05 上前一位实施者的遗留：RS tag `gateway-repository-service:fe-2061d9c5a498`、`/tmp/gateway-fe3a-e2e.VN4aBy`（含已失效的 token 文件）、9 个 `gdds-fe-fe3a-*` worktree。退出时清理 |
| N6 | handoff §8 的建议条文：第 2、4 项属于测试实现细节，不适合放进 AGENTS，可放 testing-conventions；第 5 项与现有 FD7 条文重复。由 owner 转治理会话时取舍 |

## 5. M1 的数据与建议（交 owner）

| 场景 | renderer 增量（中位 / 最大） | 浏览器主进程增量（3 次） | 打包耗时中位 |
| --- | --- | --- | --- |
| t1 v1 MODIFIED（19 个文件，6.85 MB） | 26.1 / 31.1 MiB | 2.0 / 1.7 / 2.7 MiB | 76 ms |
| t4 v1 MODIFIED（528 个文件，317.3 MB） | 665.8 / 676.3 MiB | 198.5 / 205.4 / 202.2 MiB | 2278 ms |
| t4 v1 FULL（同一目录作 ①②） | 665.3 / 666.3 MiB | 421.0 / 417.0 / 419.0 MiB | 4622 ms |
| t4 v1 FULL，审核复测 | 651.2 / 668.2 MiB | 424.9 / 422.1 / 418.9 MiB | 4558 ms |

- **方法：** 符合 §8.4：每次新浏览器；CDP 取进程；`clear_refs` 清零后基线 `VmHWM` 等于 `VmRSS`；记录全部进程；包大小取 manifest 的 `size_bytes`；打包耗时取 `data-phase`；每场景 3 次。
- **按默认标准：** t4 v1 renderer 最大 676.3 MiB ≤ 1 GiB；线性外推到 1 GB 约 2.08 GiB ≤ 3 GiB。**不需要改流式**，这是我的建议。
- **请 owner 一并看的数字：** 浏览器主进程在 MODIFIED 时增加约 200 MiB，FULL 时约 420 MiB，约等于每读一遍目录增加 0.65 倍目录大小。
  FULL 时两进程合计约 1.06 GiB，外推到 1 GB 约 3.4 GiB。默认标准只看 renderer，按标准仍然通过；若 owner 认为应看浏览器整体，结论会不同。
- FE3b 在 t1 旅程中用生产构建复测（§8.4），按计划进行。

## 6. 交设计会话

**真实 e2e 的上传输入。** handoff 说，共用 fixture 在真实 Preview 上 `KEY_MISSING` 后，实施方按 §4.6 停下，设计会话决定新增真实 e2e 专用输入。

- main 与 `fe-vnext` 上都没有这项决定的记录；kickoff §4.6 仍写着“不另写 SQL”“真实 e2e 由这些文件组成上传目录”。
- 请设计会话在 kickoff §4.6 记录：
  - 真实 e2e 与模拟 fixture 分开的理由（共用 SQL 中故意无 gid 的诊断表）；
  - 真实输入的来源规则（是否一律从共用 SQL 派生、只补 key 列）；
  - FE3b 四类上传序列所需输入的范围（B10）。
- B10 的修复以此为准。

## 7. 修复后的复审与取证

- **复审范围：** `dd8168b2b8..<修复候选>`。复审时重做 §2.3 的中断探针、补充探针（他人占用 8000）与快照探针，并在 05 上运行一次 `--suite smoke`。
- **M1：** B9 改动 `UploadStepCard.tsx`，在新候选上重测三个场景（§9）。
- **截图：** M7、n8 的截图修复后交 owner 看图确认（kickoff §9）。
- **04 取证（复审通过后）：** kickoff §9 FE3a 行，在 04 的 clean、已提交 detached worktree 上各运行一次：
  `run-tests.sh --e2e --screenshots <目录>`、上传包后端校验脚本、`run-real-backend-e2e.sh --suite smoke`（会话名按 B6 使用取证会话的名称）。
- 审核用的 05 worktree `/home/dev/gdds-fe-fe3a-review` 与 ref `refs/fe3a-review/candidate` 保留到复审结束。
