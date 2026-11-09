# FE3b 04 取证核对 1

- 对象：取证 handoff `a300b16485`（`docs/frontend-vnext/fe3b-evidence-04.md`），核对范围
  `a3b72d4461..a300b16485`（只新增该文件）。
- 被测代码：`dac69890a8`；`frontend/` 树 `54b5a333c6`，`vnext/` 树 `56720104af`。
- 依据：FE3 kickoff §9 FE3b 行；DC30；DC68；复审第 3 轮（`ae3117eb89`）与 N5 定向复核
  （`f8d3cb353d`）。
- 核对者：审核会话（不是实施会话）。只读核对：在 04 上重算 `sha256sum`、读日志、看镜像与残留；
  截图与 05 上复审第 3 轮的截图逐字节、逐像素比较。未运行测试，未起 Compose，未取占用标记。
  04 hostname `gw-dms-test-04`，核对时间约 2026-11-09T05:14Z 至 05:30Z。

## 结论

**证据实质通过，handoff 需要定向勘误。** 三项运行都在 04 的 clean、已提交 detached worktree 上完成，
各一次，exit 均为 0，无需重跑。handoff 中有 5 个 SHA 抄错，§6 的自核对方法查不出这类错误（E1）；
实施会话把开发主机的主工作区从 `main` 切到了自己的分支（P1）。E1 勘误并经脚本复核后，才能把该
handoff 作为 FE3b 退出依据。

## 1. 三项运行

外层包装脚本 `run-item{1,2,3}.sh` 保留在日志目录，写法一致：先记 hostname、起始 UTC、HEAD、
两棵树和 `git status --porcelain --untracked-files=all`，再用 `set -o pipefail` 与 `${PIPESTATUS[0]}` 取入口
exit，最后记结束值。三份外层日志起止 HEAD 均为 `dac69890a8b5…`，两棵树一致，起止 porcelain 均为空，
`entry_exit=0`。

| 项目 | 入口日志要点 | 结论 |
| --- | --- | --- |
| 1 `run-tests.sh --e2e --screenshots` | 03:31:53Z–03:33:55Z；工具链 config `a0d7b2b4…a017` 与 7 个 DiffID；`docker_network=none`；npm 缓存为 04 默认路径，归档 SHA `0d861824…89f4`，来源提交 `a2fb4a027a`；`e2e_workers=2`；单测 32 文件 175 项、e2e `63 passed`、build 与 `check:production-build` 通过；`exit_code=0` | 符合 |
| 2 `validate-upload-package.sh` | 03:34:45Z–03:36:00Z；依赖输入 5 项 expected 与 candidate 一致，`required_inputs_match=true`；校验镜像 `gateway-backend-validate:fe-dac69890a8`（10 位）config `2e93c612…80ae`；4 个包：with/without-logics、long-path 通过，missing-dbcfg 按预期以 `UPLOAD_CLOSURE_INVALID` 拒绝；`RESULT packages=4 failures=0`；`exit_code=0` | 符合 |
| 3 `run-real-backend-e2e.sh --suite journeys` | 03:36:36Z–03:41:57Z；脚本自取占用（`session=fe3b-evidence-04`、`purpose=fe3b-real-backend-e2e-journeys`），03:41:57Z 释放；依赖镜像 label `d054366c…7aad`、RS 依赖 label `6dc9659f…8b11`；RS 镜像 `fe-dac69890a8b5`（12 位）config `1181f4b5…e837`；`provisioned_mappings=18`、`worker_ready=ok`、`openapi_compare=match`；`playwright_process_exit=0`，18/18 passed，`expected=18 unexpected=0 skipped=0 flaky=0 errors=0`；`cleanup_status=ok`、`worktree_clean_end=true`、`exit_code=0` | 符合 |

另核：

- 入口与外层日志中 token 形态的值零命中，没有 `token=` 行或 `Bearer` 字样。
- `input_scope_results=missing` 是预期值，这项事实只由 smoke 套件写出（脚本第 1311 行）。
- 04 当前没有占用标记，没有 `gdds-fe` 容器，没有 `fe-dac69890*` 镜像，8000 端口空闲，没有 dolt 进程。
- 取证 worktree 仍在 `dac69890a8`，干净，`legacy` 软链在。证据分支 `fe3b-evidence-04-dac69890` 指向 `a3b72d4461`。
- 第 1、2 项的占用标记只写在 handoff 里，日志没有记录。按 AGENTS，这两项本来就不需要占用，仅作说明。

## 2. 身份与 SHA 复算

在 04 上对日志目录、第 2 项输出、第 3 项日志与证据、截图清单和 npm 归档重算 `sha256sum`；镜像身份取自入口
日志的 `docker save` 记录、`docker image inspect` 的 RootFS 层，以及 `p2r1` 镜像 `docker save` 的
`manifest.json`。handoff 共有 115 个长度 ≥ 57 的十六进制值，逐个与上述来源比对：

- 109 个与来源逐字一致，包括全部工具链、依赖镜像、校验镜像与 RS 镜像的 DiffID，以及三项运行的外层和入口日志 SHA。
- bundle SHA `6eb95d04…e432` 无法复核，两地 bundle 都已删除。它只是传输中间件，不影响证据。
- 5 个与来源不符（E1）。

截图：`shots.sha256` 的 SHA 为 `13c705e3…f222`，与 handoff 一致。清单 146 行，与目录中的 146 个 PNG
一一对应，`sha256sum -c` 全部通过。

## 3. 截图

- 25 组 `fe3b-*` 截图在 `1280/`、`1920/` 下都有，文件名与 handoff §4 映射表完全对应；
  48 组回归截图各有两种宽度。
- 与 05 上复审第 3 轮的截图（代码 `1e5c43ee65`）比较：`1e5c43ee65..dac69890a8` 只改了测试与 handoff，
  146 张中 128 张逐字节相同，18 张不同。逐像素比较，差异都在小块区域：
  - 一行进度线；
  - 9 行高的时间文字，例如“执行中”提示的“已等待 138 小时 32 分 25 秒”对 05 上的“136 小时 25 分 41 秒”；
  - 运行中卡片的计时。

  原因是截图里显示的时间按墙钟计算（见 N8），页面结构没有差异。复审第 3 轮看过的 N3、N4 对应截图
  （`fe3b-withdraw-unknown`、`fe3b-d3-*`、`fe3b-w8-upload-disabled`）与 05 逐字节相同。

## 4. 发现

### E1 handoff 中 5 个 SHA 抄错（需勘误，不需重跑）

| 行 | 内容 | handoff 中的值 | 实际值（04 重算） |
| --- | --- | --- | --- |
| 99 | `gateway-p2r1-repository:lock-6dc9659f0aee` config digest | `98d0801b…7302ad9ec`（63 位，缺末位） | `98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9` |
| 151 | `tracked_frontend_archive_sha256` | `dc9650f1…4ec529`（63 位，缺末位） | `dc9650f17fdf4e4e035aa0d88bafe9c6154af850a84135089e54a641f4ec5292` |
| 194 | `missing-dbcfg.tar.gz` | `66ce688f…17336bbc3d8541811`（57 位，后段错乱） | `66ce688f656a618adcc57f556dd31bc86fceaade17336bb3d84764a3585518b1` |
| 215 | Compose 日志 | `b0ed41cb…bfcf72e19b6…`（64 位，第 50 位 `b` 写成 `e`） | `b0ed41cbf480172c64f13dd664bb87e59a8de4c3e7bfbcf72b19b6221e04d4aa` |
| 219 | `suite-summary.txt` | `c1898be8…aab8286b5…`（63 位，漏一个 `6`） | `c1898be81ba76ecfa219aab82866b58480be99bf5e656cef46b1b25e555654c3` |

§6 的自核对有两处问题：

- `grep -oE '[0-9a-f]{64}'` 只能取到恰好 64 位的值，63 位和 57 位的值被直接跳过；
- §6 称“其余日志/清单/产物共 20 个值在 04 上重新计算，与本文逐字一致”，但第 215、219 行就在这 20 个值的范围里，却不一致。这说明该比对实际没有逐字进行。

这与复审第 2 轮 G4（handoff SHA 与 tag 位数）同类，是第二次出现。

要求在 `a300b16485` 之上单独提交一次勘误，只改 `fe3b-evidence-04.md`：

1. 按上表替换 5 个值。
2. 重写 §6 的核对方法，改成脚本完成：
   - 列出文中所有长度 ≥ 7 的十六进制串；
   - 对每个 40 或 64 位的值，确认它逐字出现在对应来源中（`sha256sum` 输出、入口日志或 `docker save` 身份文件）；
   - 长度不是 7–12、40、64 的值一律报错。

   §6 写明脚本、来源文件和输出，删去“20 个值逐字一致”的旧说法。
3. bundle SHA 注明“删前两地一致，现已无法复核”。

### P1 开发主机主工作区被切离 `main`（流程偏差）

2026-11-09T03:43:46Z，实施会话在开发主机主工作区 `/home/dev/gateway-data-management-system` 执行了
`checkout: moving from main to fe3b-evidence-04`，并在该分支提交了 `a300b16485`。主工作区至今仍停在该分支。
`main` 目前由另一会话检出在 `/home/dev/gdds-s5-design-main`，那里有未提交的改动。

AGENTS 和 DC68 澄清 2 规定：不切换正在使用的 worktree；审核与实施在各自的 worktree 中进行。实施会话已有
自己的 worktree `/home/dev/gdds-fe`（`fe-vnext`），handoff 应提交在那里。

- 勘误提交在 `/home/dev/gdds-fe` 或另建的独立 worktree 中做，不要再用主工作区。
- 主工作区切回 `main` 需要 `main` 不再被别处检出，由 owner 协调。现在不要动主工作区，也不要动
  `/home/dev/gdds-s5-design-main`。
- 本报告同样因此无法直接提交到 `main`：报告提交在独立 worktree `/home/dev/gdds-fe3b-evcheck-report` 的
  本地分支 `fe3b-evidence-check-1` 上，父提交为当时的 `main`（`c32c9aabd9`），待 `main` 可用时合入。

### 非阻塞（交 owner 看图）

- **N3、N4（沿用）：**
  - `fe3b-withdraw-unknown` 中按钮间距小；
  - 长单行关闭理由不折叠（`fe3b-d3-*`）；
  - 被占用时工作区节点仍标“可提交”（`fe3b-w8-upload-disabled`）。
- **N7（新）：** 预览页顶栏中，撤回与提交两个禁用原因并排显示，中间没有分隔，读起来像一句话：
  “提交正在执行，完成后才能撤回提交正在执行，完成后才能继续”。见 `fe3b-w6-withdraw-busy`、
  `fe3b-w6-preview-resumed-card`、`fe3b-w6-attempt-running`，两种宽度都有。05 上复审第 3 轮的截图中也是如此，
  不是本候选引入的。交 owner 看图时决定是否在 FE3c 调整。
- **N8（新）：** 截图测试中“已等待 …”等时间文字由墙钟减去固定的 mock 开始时间得出，所以显示 138 小时这样的值，
  每次运行的截图也不相同。不影响验收；建议之后在截图用例中固定时钟。

## 5. 交 owner 看图

- 目录：04 上的 `/home/dev/gdds-fe-shots/fe3b-04-dac69890`；清单 `shots.sha256` 的 SHA 为
  `13c705e3b782aa2ff50c993fafa605d3d540c2b1a590a72a782648b41692f222`。
- 文件与 kickoff §9 各项的对应关系见 handoff §4。另请一并确认 N3、N4、N7。

## 6. 下一步

1. 实施会话按 E1 提交 handoff 勘误（在独立 worktree 中，见 P1），交付勘误提交 SHA。审核会话用脚本复核
   `a300b16485..<勘误提交>`，这一步只看文档，不重跑。
2. owner 看图，确认 N3、N4、N7。
3. 两项完成后，审核会话给出 FE3b 退出建议：tag 对象、合入方式与清理清单。
4. owner 协调主工作区切回 `main`（P1），并决定本报告分支何时合入 `main`。

保留：04 上的取证 worktree、证据分支、日志、输出和截图目录保留到 FE3b 退出；05 上复审第 3 轮与 N5 复核的
保留项不变。
