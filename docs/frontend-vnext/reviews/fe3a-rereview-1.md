# FE3a 复审报告（第 1 轮）

- **复审对象：** 开发主机分支 `fe-vnext`。
  - 代码候选 `ee064f11cc66632a4832d62df082840f56bad7b8`，`frontend/` 树 `0875c46387`；
  - handoff 提交 `f9d1de1764` 与 DC68 探针记录 `76cce6814f42c372ac3e40144cbe8a9a1eedb93f`（相对代码候选只改 handoff，`frontend/` 树相同）。
- **范围：** `dd8168b2b8..76cce6814f`。
  - 其中 `417408d41d` 合入 main `550ddbcede`（只有文档：FE3a 审核、kickoff Q10–Q12 与后端会话的 P6 文档）；
  - 相对 `550ddbcede` 只改 `frontend/` 与 `docs/frontend-vnext/fe3a-handoff.md`；`frontend/` 相对 `dd8168b2b8` 为 20 个文件（+963/−190）；`vnext/` 树仍为 `2791d3ff3d`。
- **依据：** [FE3a 审核](fe3a-review.md)（`a0b9604ddd`）§3、§4；[FE3 kickoff](../fe3-kickoff.md) §4.2、§4.6（Q10）、§4.9、§7 M7（Q11）、§8.4（Q12）。
- **日期：** 2026-11-05。
- **结论：定向修复，范围小。**
  - B1–B11 都已处理，逐条见 §1。在 05 上，我的完整 runner、真实 smoke、M1 抽测和 8000 端口探针都通过（§2）。
  - 剩下 2 项需要修复（§3），都在真实 e2e 的脚本与用例里，不涉及产品代码与打包代码，不需要重测 M1：
    - R1：脚本判定套件通过时不看 Playwright 的退出码与 `skipped`。Playwright 在容器内被中断时仍会写出 JSON 结果，其中 `unexpected=0`，脚本会以 exit 0 结束。这是 B2 想排除的情形，我在 05 上复现了 Playwright 的这一行为；
    - R2：“B FULL”用例没有断言这次上传确实是 FULL。
  - 修完后第 2 轮只核对这两处与一次 05 smoke，然后去 04 取证。

## 1. B1–B11 与非阻塞项核对

| 项 | 核对 | 结论 |
| --- | --- | --- |
| B1 | 播种按 `SCOPE_SLUGS` 循环，共 7 个 scope：上传与预览、权限拒绝，以及 5 个输入 scope。每个 scope 有自己的 `Idempotency-Key`、仓库、`business_baseline_node_id`、device key/project 与身份组。映射一次写好后才启动 backend。日志逐 scope 记录仓库 ID 与 `INITIAL` 提交 ID，`provisioned_mappings=7` | **通过** |
| B2 | INT/TERM/HUP 各有 trap，记录信号与 130/143/129 后进入同一清理。清理第一步删除工具链容器。套件放到后台后 `wait`，信号能立即处理。结果以 JSON reporter 写出的文件为准。实施方的 INT、TERM 探针分别得到 rc=130、143，清理为 ok | 信号路径**通过**；套件结果判定见 R1 |
| B3 | dolt 改为读 `/proc/*/comm` 并精确匹配。8000 与 dolt 只在 `STACK_STARTED=1` 时纳入清理核对。改写标记时只改 `purpose` 一行，另加 `cleanup_failed_at`。运行前检查增加本前缀的卷与网络。我复做了 8000 探针（§2.3） | **通过** |
| B4 | 先起 preview，在容器内经 `127.0.0.1:4173/openapi.json` 读取，由宿主机 `python3 -I` 规范化。两份规范化 JSON 都保存，不一致时写 `openapi.diff`，exit 2，不跑浏览器用例 | **通过** |
| B5 | 等到 `/bundle` 的响应与“预览已生成，但下载比较结果失败，请重试”出现后，才断言没有 `pageerror`。Preview 结果按 `/\/preview-results\/[^/]+$/` 匹配。程序断言 History 只有一个 `INITIAL` 节点，且 `head.node_id` 与它相同。配置加了 `screenshot: "only-on-failure"` | **通过** |
| B6 | `--session` 必填并校验格式，`--subphase` 决定项目名与残留检查的前缀。日志补全了 §4.9 的字段：身份与权限、占用标记内容及获取/释放时间、flock 获取/释放时间、逐用例起止、结尾两棵树与 clean、依赖镜像 `RootFS.Layers`。脚本等待 `code=worker_ready` | **通过** |
| B7 | `ComparisonPage.tsx` 与 `fe-fe2c-exit` 逐字节相同，FE2c 的行为已恢复。n3 的两条 e2e 用 `operationHold` 让操作查询停在 RUNNING，断言“提交”禁用及原因；放行后断言 ABORTED 与读取失败的提示，以及“提交”恢复可用 | **通过** |
| B8 | 摘要中“工作区”显示 `gateway_device_external_key`，原始 ID 放悬停提示。组态树显示“工作区 gateway-17”，二者一致。单测改正，另加“拿不到显示名时回退到 ID”。截图见 §2.2 | **通过** |
| B9 | 两处都改为 `.form-warning form-warning--stacked`，分行保留。样式见 N8 | **通过** |
| B10 | 与 kickoff §4.6（Q10）逐项核对：<br>- 派生文件位置、文件名、两行替换一致；<br>- `real-logics.xml` 已删除，`sql-replacement-current.sql` 与 `logics-1/2/3.xml` 直接读共用目录；<br>- `logics.xml` 的配对一致；<br>- 上传目录的组成一致，FULL 的 ① 与 ② 各用一个目录；<br>- 单测核对：共用文件逐字节不变；替换点各出现一次；派生结果与提交的文件逐字节相同；派生目录只有三份 SQL；<br>- 5 个输入 scope 都基于空 `INITIAL`，每个都断言 Q10 的判据，只记录的项写入 `input-scope-results.json`；<br>- handoff §5 写出了每个 scope 的序列 | **通过**；FULL 的断言见 R2 |
| B11 | handoff §6 的判断按 §8.4 原文；已列出浏览器主进程的增量；生产构建列为偏差；§9 第 1 项引用 Q10 | **通过**；小错见 N6 |
| M7 / Q11 | `baseline-labels.ts` 由组态树与摘要共用，`submit-summary.ts` 不再复制规则。“归档基线 n”按 `created_at` 升序编号，同时刻按 `ref_id`；`INITIAL` 不编号。树与对话框读取的是同一个分页合并后的 `listHistory()`，编号一致。单测覆盖了同时刻与多个归档基线 | **通过** |
| N1 | `clear_refs` 写入失败与 FULL 文案等待失败都会让测量失败 | **通过** |
| N3 | 从 `package.json` 读取 `generate:api-types`，只替换输出路径 | **通过** |
| N4、N5 | 节点上设置 `TMPDIR`；前一位实施者的 RS tag、`/tmp` 运行目录与 `gdds-fe-fe3a-*` worktree 已清理 | **通过**；另有两个遗留见 N7 |

## 2. 我在 05 上的核对

源码经 bundle 传到 05（`/home/dev/gdds-fe-logs/fe3a/fe3a-rereview-76cce6814f.bundle`，SHA256 `efe47e3f…ca4af69e3`，ref `refs/fe3a-rereview/candidate`）。worktree 为 `/home/dev/gdds-fe-fe3a-rereview`（detached `76cce6814f`），运行前后都是 clean。
运行前 05 没有占用标记，也没有容器。驱动脚本为 `/home/dev/gdds-fe-logs/fe3a/rereview-run.sh`，输出在 `rereview-run.out`。

### 2.1 实施方日志

handoff §0.2 列出的 5 份日志（runner、smoke、M1 三份），以及 §0.3 的 4 份探针日志（含 DC68 首次失败的 INT 探针），在 05 上的 SHA256 与 handoff 一致。

### 2.2 完整运行

| 运行 | 起止（UTC） | 结果 | 日志 / SHA256 |
| --- | --- | --- | --- |
| runner `--e2e --screenshots` | 10:50:19–10:51:12 | exit 0；30 个单测文件，34 个 e2e；截图 96 张 | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261105T105019Z.log`，`e8ba83fc…a5151914` |
| 真实 smoke `--session fe3a-rereview` | 10:51:12–10:52:51 | exit 0；`suite_stats_expected=9 unexpected=0 skipped=0`；`openapi_compare=match`；`worker_ready=ok`；`provisioned_mappings=7`；`cleanup_status=ok` | `/home/dev/gdds-fe-logs/fe3a/rereview-smoke-76cce6814f42/real-backend-e2e-smoke-fe3a-rereview-76cce6814f-20261105T105112Z-1374695.log`，`177c183f…c8d65956` |

两次运行的节点都是 `gw-dms-test-05.lan`，起止 HEAD 都是 `76cce6814f`。

**5 个输入 scope**（smoke 日志 `input_scope=` 行）：

| scope | 比较对 | 记录的身份对 |
| --- | --- | --- |
| A | 0→1：changed 9，failed 0 | `NOT_APPLICABLE` |
| B② | 0→1：changed 9，failed 0 | `NOT_APPLICABLE` |
| C | 0→1：changed 9，failed 0 | `NOT_APPLICABLE` |
| D | 0→1：changed 4，failed 0 | `NOT_APPLICABLE` |
| B FULL | 0→1：changed 9；1→2：changed 5；failed 都为 0 | `SAME_PROJECT` |

与 handoff §5 一致。

**截图：** 96 张，目录 `/home/dev/gdds-fe-evidence/fe3a/rereview-screens-76cce6814f42`，聚合 SHA256 `5c13316f…8670dbd80`。与实施方的截图不是逐张逐字节相同，例如 `submit-summary-workspace-1920` 不同；按 FD7 不做像素比对。我看了以下几张：
- `s1-workbench-1920`：树上是“归档基线 1 · 当前基线”和“初始基线”；
- `submit-summary-workspace-1280`：摘要为“gateway-17 / 本次预览 / 当前基线（归档基线 1）/ 3”；
- `submit-manual-recovery-1280`：提示、ID、“复制 ID”和正文分行，使用警示框。

### 2.3 M1 抽测与探针

- **M1**：t4 v1 FULL 跑 3 次，10:53:25 起。报告为 `/home/dev/gdds-fe-evidence/fe3a/rereview-m1-76cce6814f42/t4v1-full.json`，SHA256 `318ddd8f…91e7d4`；日志 SHA256 `010f7ad2…1370be`。
  - renderer 峰值增量：663.86 / 670.35 / 662.25 MiB；
  - 浏览器主进程：425.75 / 418.02 / 420.46 MiB；
  - 与 handoff §6 一致（renderer 最大值 666.13 MiB，主进程约 420 MiB）。最大值 670.35 MiB，外推到 1 GB 约 2.06 GiB。按 Q12 满足。
- **8000 端口探针**：先起一个发布 8000 的他人容器，不建占用目录，再运行脚本。
  - 结果：exit 3，日志写 `error=port 8000 is already published` 与 `cleanup_status=ok`；节点没有留下占用标记，他人容器仍在运行（之后由我删除）；
  - 日志：`/home/dev/gdds-fe-logs/fe3a/rereview-probe8000/real-backend-e2e-smoke-fe3a-rereview-p8000-76cce6814f-20261105T105543Z-1383043.log`，SHA256 `a5c74949…a669933d`。

  第一轮的误判已经消除。
- **Playwright 中断行为**（为 R1 所做，不触及候选 worktree）：
  - 做法：在工具链容器中用候选的 `node_modules` 跑一个三用例的临时 spec，第二个用例等待 20 秒，期间向容器内的 Playwright 发信号。结果文件同为 JSON reporter：

    | 情形 | Playwright 退出码 | JSON `stats` |
    | --- | --- | --- |
    | 容器内 SIGINT | 130 | 写出了文件；`expected=1 skipped=2 unexpected=0` |
    | 容器内 SIGTERM | 143 | 没有写出文件 |
    | `afterAll` 抛错 | 1 | `expected=1 unexpected=1` |

  - 临时目录 `/home/dev/gdds-test-tmp/fe3a-rereview-pwexp` 用完已删除。05 上没有遗留的容器、RS 临时 tag 或占用标记。

## 3. 需要修复（阻塞）

### R1 套件判定不看 Playwright 退出码与 `skipped`

`run-real-backend-e2e.sh:781-838`：`PLAYWRIGHT_EXIT` 只写进日志。结果判定只有一条：`code = 0 if expected > 0 and unexpected == 0 else 1`。

- **失败情形：** Playwright 在容器内收到 SIGINT 时会写出 JSON：已跑完的用例计入 `expected`，中断的和没跑的计入 `skipped`，`unexpected=0`，Playwright 自己以 130 退出（§2.3）。脚本据此得到 0。如果脚本本身没有收到信号，最后就会以 exit 0 结束，而套件只跑了一部分。
- **与 B2 的关系：** B2 的修复处理了“信号发给脚本”的路径，这条路径已经正确。但 B2 的目标是：被中断、结果不全的运行不能显示成功。这里还缺“结果文件存在但不完整”的情形。
- **`docker exec` 的退出码也不可靠：** 实施方第一次 INT 探针的日志中，`docker exec` 客户端在 9 个用例只跑完 1 个时返回 0（`playwright_process_exit=0`）。这次靠结果文件缺失才得到 exit 2，所以两项必须同时检查。
- **修复：** 以下各项同时成立才判为通过：
  - `PLAYWRIGHT_EXIT == 0`；
  - 结果文件存在且能解析；
  - `unexpected == 0`、`flaky == 0`、`skipped == 0`；
  - 顶层 `errors` 为空；
  - `expected > 0`。

  不通过时，日志写明是哪一项。补一个探针：smoke 运行中用 `docker exec <工具链容器> pkill -INT -f "playwright test"` 中断容器内的 Playwright，脚本应以非 0 结束，`cleanup_status=ok`。

### R2 “B FULL”没有断言上传方式

`smoke.spec.ts` 的 `runInputScope` 对 MODIFIED_ONLY 和 FULL 用同一组判据，只要求“② 所在比较对 `changed ≥ 1`”。

- **失败情形：** 页面没有采用 ① 目录时（例如 FE3b 改 §6 上传模式时引入回归），上传就成了只含 ② 的 MODIFIED_ONLY。这时仍有一个比较对 0→1、`changed ≥ 1`，用例照样通过，FE3a 与 FE3b 的证据里都会多出一条实际没跑过的 FULL。
- 本轮的 `input-scope-results.json` 显示确实是 FULL（两个比较对），所以现有结果没有问题。缺的是断言。
- **修复：**
  - 按上传方式断言比较对：MODIFIED_ONLY 恰好一个 0→1；FULL 恰好两个，0→1 与 1→2；
  - FULL 在点击上传前等到页面显示“原始备份 + 本次归档”，与 `packaging-memory.spec.ts` 相同。

## 4. 非阻塞意见

| # | 意见 |
| --- | --- |
| N1 | `smoke.spec.ts` 有两处类型问题，`tsc -b` 不检查 `e2e*/`，所以没有报出来：<br>- `record.scope` 读取 `identity.scope`，`Identity` 接口没有这个字段（运行时 JSON 里有）；<br>- 断言消息用了 `pair.pair_id`，映射后的对象没有这个字段，失败时消息会是 `undefined.failed_table_count`。<br>改 R2 时可以一并修正。`e2e/` 从 FE1 起就不在类型检查范围内，建议 FE3b 为 `e2e*/` 加一个 tsconfig |
| N2 | 5 个输入 scope 的 `bundle_id` 都是空字符串：当前 backend 的 manifest JSON 里既没有 `bundle_id`，也没有 `manifest_ref.artifact_id`。可以改记 Preview 结果的 `bundle_digest`，或者 FE3b 按 BE-d 的格式再定 |
| N3 | `run-real-backend-e2e.sh:604-606` 的注释仍写着“still pending the design-session record (review B10)”，已经过时 |
| N4 | 宿主机还有几处 `python3` 没有加 `-I`：`:343` 调用仓库内脚本，`:353-354`、`:537-538`、`:565` 是内联解析。风险低，建议统一 |
| N5 | 输入 scope 的用例在读到 bundle 后立即断言 `pageErrors`，没有等页面自己下载 bundle 失败。这一点由“上传与 Preview”用例覆盖；FE3b 换成 tar 后，各 scope 会进入差异浏览，可以再统一处理 |
| N6 | handoff 的小错：<br>- §6 第一行的提交号写成 `ee064f11cc66632a4832df082840f56bad7b8`（少了 `62d`），实施方说明中也是这样写的；正确的是 `ee064f11cc66632a4832d62df082840f56bad7b8`；<br>- §9 第 5 项的“这是 §4.1 的明确要求”说的是真实 e2e 的构建，M1 依据的是 §8.4；<br>- §0.1 中 N2 标为“不采纳”，实际已按 Q11 抽出了共用函数 |
| N7 | 05 上还有实施方的两个 worktree：`/home/dev/gdds-fe-m1-05`（`80b1ef0f70`）与 `/home/dev/gdds-fe-smoke-05`（`2061d9c5a4`）。它们不在 N5 的 `gdds-fe-fe3a-*` 之列，退出时一并清理 |
| N8 | `.form-warning` 的背景是 `var(--color-warning-soft, var(--color-surface-muted))`，而 `--color-warning-soft` 没有定义，所以“需要管理员处理”显示为灰色底，不是工作台警示卡片的黄色。这符合 n8 的“同一区域其他提示的样式”：对话框中“Preview 结果已基于旧基线”的提示也是这个样式。owner 看图确认即可。如果要改成黄色，属于设计令牌，不在 FE3a 处理 |

## 5. 下一步

1. 实施方修复 R1、R2，可以顺带处理 N1、N3、N6。只改 `frontend/scripts/run-real-backend-e2e.sh`、`frontend/e2e-real/smoke.spec.ts` 与 handoff，不需要重测 M1。
   在 05 上重新跑 runner（覆盖 lint）、smoke 和 R1 的中断探针，handoff 记录日志与 SHA256。
2. 复审第 2 轮：只核对 `76cce6814f..<修复>` 的这两处，以及一次 05 smoke。
3. 通过后在 04 取证，在 clean detached worktree 上运行：
   - `run-tests.sh --e2e --screenshots`；
   - `run-real-backend-e2e.sh --suite smoke --session fe3a-evidence`。
4. owner 看图：
   - M7：`submit-summary-workspace-*`，以及因编号而变化的树截图；
   - n8：`submit-manual-recovery-*`，含 N8 的颜色。
5. 05 上本轮留下的复审资源（worktree `/home/dev/gdds-fe-fe3a-rereview`、ref `refs/fe3a-rereview/candidate`、bundle、日志与证据目录）保留到复审第 2 轮。第一轮的 `/home/dev/gdds-fe-fe3a-review` 同样保留。
