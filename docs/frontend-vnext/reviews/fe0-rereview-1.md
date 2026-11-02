# FE0 复审报告（第 1 轮）

- **复审对象：** 分支 `fe-vnext`，修复候选 `e22f510a82a143ccee76a1b3b3b6c854aa755129`。测试绑定的代码提交是
  `d62eb3603747d3dceed2269c3cfc74be100b73e3`，两者之间只改了 handoff，`frontend/` 树都是 `47e901a848`。
- **范围：** `6c5dbcb1c4..e22f510a82`，包含两个提交：`d62eb36037` 代码修复、`e22f510a82` handoff。
- **依据：** [FE0 审核报告](fe0-review.md) §6 的复审范围；设计会话对 D1 的答复（main `bb6a09252a`）。
- **日期：** 2026-11-02。
- **结论：PASS。** B1、B2 已修复并验证；D1 已由设计会话在 kickoff §8 定为 KEEP；所选 N 项均已落实。
  FE0 剩下的工作是 04 阶段退出取证（§5），以及 owner 的退出确认。

## 1. 范围

`6c5dbcb1c4..e22f510a82` 只改动了以下文件：

- `frontend/README.md`
- `frontend/e2e/workspace-shell.spec.ts`（新增）
- `frontend/package-lock.json`
- `frontend/playwright.config.ts`
- `frontend/scripts/run-tests.sh`
- `docs/frontend-vnext/fe0-handoff.md`

`package.json`、`.gitignore`、`vnext/`、AGENTS、kickoff、UI 优化方向、`docs/backend-vnext/` 和审核报告均未改动。**通过。**

## 2. 逐项核对

### B1 lockfile 的 registry 身份：已修复

- 把修复前的锁文件按 `http://192.168.233.184:4873/` → `https://registry.npmjs.org/` 做一次文本替换，结果与新锁文件**逐字节相同**。
  所以除主机外没有任何改动，integrity、版本、包集合都不变。
- 新锁文件里有 305 处官方 URL，局域网主机出现 0 次。SHA256 为 `811fa3dfbf22233738906335b35ec3e2abf0846f510a157cb69ff18db71f0f7c`，与 handoff 一致。
  修复前的锁文件快照 `package-lock-before-b1.json` 的 SHA256（`64e87a37…b760b`）与 `6c5dbcb1c4` 中的锁文件一致。
- `run-tests.sh` 在运行前检查 lock source：
  - 正向：两次运行都通过，日志记录 `package_lock_resolved_count=305`。
  - 负向探针：在 05 的一次性 worktree 中把一处 `resolved` 改回局域网主机，runner 以 exit 2 拒绝运行，并提示使用官方源；容器没有启动，也没有产生日志。探针用完即删。
- 缓存沿用原来的预填充。原缓存按旧锁文件生成，两个锁文件的 integrity 相同，因此新锁文件可以离线安装；实施方的单独安装和我的两次复跑都证明了这一点。
  README 已写明局域网 registry 只用于取包。

### B2 `--e2e` 可运行：已修复

- `frontend/e2e/workspace-shell.spec.ts` 的用例名是“打开应用显示工作台骨架页”，按业务行为命名。它断言一级标题可见，没有使用空跑选项。
- 05 复跑 `run-tests.sh --e2e`，exit 0，日志显示 `1 passed (1.1s)`。这也证明工具链镜像里的浏览器能在 network none 容器中正常启动。

### D1 复合信号公式查看：设计会话已答复

- kickoff §8 的这一行现在是 **KEEP**（owner 2026-11-02 确认）：
  - History 和 Preview 都提供改前、改后的公式对照。
  - Preview 缺少的基线侧数据，由 BE-b 在表有变化时补齐 `composite_signal_point` 与 `device` 的基线侧整表。
  - BE-b 落地前，Preview 中公式有变化的测点只显示上传侧公式，并以 `formula_digest` 前后值不同标示“公式已改”。
  - 名称映射与数据可得性见 BE-b 草案 §4.4。
- 这与审核时核对到的源码事实一致（修改记录不带 `formula_ast_json`，删除记录带基线侧的选中列）。
- 设计会话同时把 BE-b 范围和 `composite-signal-device.md` 的过时段落列入 BE-b 第二步替换，审核报告第 5 节的第 2 项也随之有了去向。
- 至此清单中没有未判定项，FE0 的这一退出条件已满足。

### N 项

| 项 | 核对结果 |
| --- | --- |
| N1 | 按约定保留到 FE1，FE1 审核时核对 |
| N2 | runner 把 RootFS DiffID 与写死的七项预期值比较，不一致时 exit 2；日志记录 DiffID 和缓存归档的 SHA256 |
| N3 | 容器只接收 `git archive HEAD frontend` 生成的 tar，不再复制被 Git 忽略的文件 |
| N4 | `reuseExistingServer: false` |
| N5 | README 写明 `none` 只适用于模拟接口，FE3 的设置方式也已写明 |
| N6 | 默认路径与阶段无关，可以用环境变量覆盖 |
| N7 | handoff 已更正锁文件来源提交，并引用治理提交 `f0ad2461ac` 中“入口保持独立”的结论 |

### 证据核对

- **CT201：** `fix1/source-bundle-d62eb.log`（`65967719…dba`）、`fe-vnext-d62eb36037.bundle`（`a7310943…450e`）的 SHA256 与 handoff 一致；05 上的 bundle SHA256 也相同。
- **05：** `fix1/` 下 `bundle-fetch.log`、`worktree-add.log`、DC68 失败日志 `npm-ci-offline-20261102T095125Z.log`、
  `npm-ci-offline-retry-…095156Z.log`、`frontend-tests-…095215Z.log`、`frontend-tests-…095233Z.log` 的 SHA256 均与 handoff 一致。
  runner 日志记录了 hostname、起止时间、起止 HEAD（`d62eb36037`）、DiffID 和 exit 0。
- **DC68：** 预检时候选变量少录一位，exit 2。当时容器没有启动，失败日志已保留，从该步骤开头重做一次后通过。处理符合 DC68。

## 3. 复跑

- **源码传输：** 在开发主机执行 `git bundle create ... ^f0ad2461ac fe-vnext`，bundle SHA256 为
  `9d4375f8d9450a565bae97c1eef144a0e05dc1d81eccc163cd77a416ae25171c`，两端一致。05 主仓库 verify 并 fetch 后，`FETCH_HEAD` 等于候选；
  main 停在 `bb6a09252a` 未移动，没有建分支。
- **05 worktree：** `/home/dev/gdds-fe-rereview1-fe0-e22f510a-05`（detached，clean，已建 `legacy` 符号链接）。运行前确认节点占用标记不存在。
- **环境变量：** 缓存仍在 `fe0` 路径下，因此显式设置了
  `GATEWAY_FRONTEND_NPM_CACHE=/home/dev/gdds-fe-cache/fe0/npm-cache`、
  `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE=/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`、
  `GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT=a2fb4a027a…`。

日志在 `/home/dev/gdds-fe-logs/fe0/rereview-1/`，节点为 `gw-dms-test-05.lan`：

| 运行 | 起止（UTC） | HEAD（起→止） | exit | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| worktree 准备 `rereview-setup.log` | 10:16:42–10:16:42 | 候选 | 0 | `0f34dc3a286e0bccf0a7c98b847791f7a26b8121a9202736198caf47716e7367` |
| 默认流程 `frontend-tests-20261102T101649Z.log` | 10:16:49–10:16:59 | `e22f510a82` → 同 | **0** | `facdd792ed7274ebc16abb11df4eb9e3bfa1a84c200f007941b7f412f924b381` |
| `--e2e` `frontend-tests-20261102T101659Z.log` | 10:16:59–10:17:10 | `e22f510a82` → 同 | **0**（`1 passed`） | `aa972e059a9e4f56e478337d39424a8640c1404ee931025ab2e7d2d56d0493af` |
| lock source 负向探针 `lock-check-probe.log` | 10:17:19–10:17:19 | 一次性 worktree | 探针 exit 2（符合预期） | `ee0f3e81b478397356e2247160ec1b36237bb3d3b60e15ebc6b7227fba86a92f` |

运行后 worktree 仍然 clean。

## 4. 非阻塞意见（在 04 取证或 FE1 中处理即可）

**R1. `npm_cache_source_commit` 由操作者自由填写，fix1 记录的值不准确**（`frontend/scripts/run-tests.sh` 中的 `NPM_CACHE_SOURCE_COMMIT`）
fix1 的 runner 日志写的是 `d62eb36037`，即新锁文件所在的提交；但缓存实际是按 `62cd5d5641`（与 `a2fb4a027a` 的 blob 相同）生成的。
handoff 正文写对了，日志字段容易误读。04 取证时请填写缓存实际生成时的提交；如果 04 按新锁文件重新取得缓存，就填那次的来源提交。
另外，与阶段无关的默认路径 `/home/dev/gdds-fe-cache/frontend/...` 在 05 上不存在，目前要靠环境变量覆盖。04 预填充时可以直接放到默认路径，并在 handoff 中写明。

**R2. `tracked_frontend_archive_sha256` 随提交变化，不能用来比较源码身份**
`git archive <提交>` 会在 tar 头里写入提交号。所以 `d62eb36037` 与 `e22f510a82` 的 `frontend/` 树相同（都是 `47e901a848`），归档 SHA256 却不同（`0a4b15b1…` 与 `2a9370d8…`）。
建议日志再记录一个 `git rev-parse HEAD:frontend` 的树 id，作为跨提交可比较的源码身份。

**R3. handoff 中 D1 的状态仍是“等待答复”**（`docs/frontend-vnext/fe0-handoff.md` 的 §8 表“复合信号表与公式查看”一行，以及“N2–N6 与 N7”一节末尾）
handoff 写于设计答复 `bb6a09252a` 之前。权威记录是 kickoff §8，不影响本次结论。04 取证更新 handoff 时，请同步为 KEEP 并引用 `bb6a09252a`。

## 5. FE0 退出前剩余事项

1. **04 取证**（kickoff §6）：
   - 按 FD7 把工具链镜像和 npm 缓存预填充到 `ct108-gw-dms-04`，核对 config digest 与全部 DiffID。
   - 在 04 的 clean detached worktree 上，用候选的代码提交运行一次 `frontend/scripts/run-tests.sh --e2e`。
   - 日志记录 hostname、起止时间、HEAD、exit code 和 SHA256，并写入 handoff，同时处理 R1、R3。
2. **结论确认：** owner 确认 FE0 退出；设计会话打 `fe-fe0-exit` 并合入 main。

04 取证只改 handoff，不需要再次复审代码。证据提交后由审核会话做一次证据核对。
