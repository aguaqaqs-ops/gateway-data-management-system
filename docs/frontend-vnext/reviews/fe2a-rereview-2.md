# FE2a 复审报告（第 2 轮）

- **复审对象：** 分支 `fe-vnext`，代码候选 `a80a2e93af663cda6f4f972a0840df5142df4cea`（`frontend/` 树 `f1c238248a`）；
  handoff 提交 `c1b8fc818a129c7b367234132621d91138fe6468`（只改 handoff，`frontend/` 树相同）。
- **范围：** `c1abe10cf8..c1b8fc818a`，4 个提交：`bd6a666be3`、`813da6cd61`、`a80a2e93af`、`c1b8fc818a`。
- **依据：** [FE2a 复审第 1 轮](fe2a-rereview-1.md) §5、§6。
- **日期：** 2026-11-03。
- **结论：PASS。** N1、N2 已修复并通过变异探针验证，R6 已更正。FE2a 剩下的工作是 04 阶段退出取证（§5），以及 owner 确认无草图页面的截图和阶段退出。

## 1. 范围

本轮只改动了以下文件，fixture、依赖、lockfile、runner 和 `vnext/` 都没有改动（`vnext/` 树仍为 `2791d3ff3d`）。**通过。**

- `frontend/src/features/view-model/formula-view.ts`
- `frontend/src/features/view-model/formula-view.test.ts`
- `frontend/src/features/view-model/view-status.ts`（新增）
- `frontend/src/features/view-model/view-status.test.ts`（新增）
- `frontend/src/pages/ComparisonPage.tsx`
- `frontend/e2e/workspace-shell.spec.ts`
- `docs/frontend-vnext/fe2a-handoff.md`

## 2. N1、N2、R6 核对

- **N1 公式分组：**
  - 无名子表达式的运算符与父链不同时，生成一行分组（例如“+ （* 分组）”），组内操作数缩进一层；
  - 截图 `formula-history`、`formula-preview` 中，fixture 公式显示为“+ 测控装置:测量电压”之后接“+ （* 分组）”，组内“* 3 / * 测量电压 / * 4”缩进一层，含义正确；History 两侧仍按行对齐，“* 3”与“* 5”标为修改；
  - `formula-view.test.ts` 用 fixture 的完整 AST 形状断言分组行的深度为 1、组内各行深度为 2，并断言 History 的对齐结果。
- **N2 视图状态：**
  - 视图没有变化表时显示“一致”，否则显示“更新”；降级表数、失败表数和有比较提示的表数放在悬停提示中；
  - 后端 `changed_table_count` 把除未变化、业务等价以外的所有表都计入（`surface_assembly/_assembly.py:123`），所以降级表或失败表不会被显示为“一致”；
  - `view-status.test.ts` 覆盖四种情形；e2e 断言两个 Preview 视图都显示“更新”，悬停提示中有“2 张表降级比较”和“3 张表有比较提示”。
- **R6：** handoff §9 中更正后的两个值，与第 1 轮复审我重算的结果一致。

## 3. 复跑与证据

### 3.1 我在 05 上的独立运行

- **源码传输：** 从实施仓库只读生成 `git bundle create … ^c1abe10cf8 fe-vnext`，SHA256 为 `8b4733a4b0345e237fcc33387aa2be0dc7437ca20222876c64d9c1a4f304e773`。05 上 `FETCH_HEAD` 等于 `c1b8fc818a`，05 的 main（`c18b9b0993`）没有移动。
- **worktree：** `/home/dev/gdds-fe-rereview2-fe2a-c1b8fc81-05`，detached、clean，已建 `legacy` 链接；运行前确认没有占用标记。缓存来源归档使用 FE0 的 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`。

日志在 05 的 `/home/dev/gdds-fe-logs/fe2a/review-rereview-2/`，节点为 `gw-dms-test-05.lan`：

| 运行 | 起止（UTC） | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 准备 `rereview-setup-05.log` | 09:11:09 | HEAD `c1b8fc818a`、`frontend/` 树 `f1c238248a`、clean | `b5c3aea65c3fcdf4141cd2a7b92174a7c25b05d4dc3903405867df02a37f1795` |
| `run-tests.sh --screenshots` `frontend-tests-20261103T091132Z.log` | 09:11:32–09:11:56 | **exit 0**；17 个文件 72 项单测，e2e 4 passed；HEAD 和树起止不变；运行后 clean；缓存归档 SHA256 `0d861824…089f4` | `875e0cf237a3120668f55218e754581cba4a38e2510f6a8b769327307da274e8` |
| 外层包装 `runner-wrapper-05.log` | 同上 | runner_exit=0 | `269134960fa3fa9646ca2551856d680cc4759aa4827501376c02abe6d11702e4` |
| 缓存归档比对 `npm-cache-archive-compare.log` | 09:12:56 | 见 §3.3 | `6b48654c191264e0b3d27f20a3799d3cd6389d55eddae61ceaf92f2881a48b67` |
| 变异探针 `mutation-probes.log` | 09:13:13–09:14:25 | 见 §3.4 | `c66cd58af18030a3ad57e7bb907691eda3eb555d267a9a112daa4d860529ae79` |

- **日志目录：** 我起初把准备、包装和 runner 日志写进了 `/home/dev/gdds-fe-logs/fe2a/rereview-2/`。这个目录名已被实施会话用来存放本轮的修复日志，文件名不重叠，没有覆盖任何文件（实施会话的 4 个日志重算 SHA256 都与 handoff 一致）。随后我把自己的文件移到 `review-rereview-2/`，SHA256 不变。
- **截图：** 我拍的 30 张截图（`/home/dev/gdds-fe-evidence/fe2a/rereview2-c1b8fc81-05/`）与 handoff §9 截图表中的 SHA256 全部一致。相比第 1 轮，只有语义色、加载骨架和错误页三组没有变化；其余因视图状态文字或公式分组改变，都重拍了。

### 3.2 handoff 证据

- **最终运行：** runner 日志 `rereview-2/frontend-tests-20261103T090519Z.log`（`17a76a49…39ca`）重算一致；日志中 HEAD 为 `a80a2e93af`，`frontend/` 树为 `f1c238248a`，exit 0。
- **中间运行：** 两次 exit 1（`281d2562…`、`8be09f14…`）都是公式测试中的 AST 形状不完整，追加提交后从新 worktree 从头重跑，处理正确。
- **preflight：** 缓存路径填错的 preflight 日志（`e32683e3…`）发生在 runner 启动之前，按 DC68 处理。

### 3.3 缓存来源记录（勘误）

handoff §9 写的是“npm cache 沿用 FE0 预填充……归档 SHA256 `91ccf614…`”。实际情况：

- 从第 1 轮修复起（`frontend-tests-20261103T080331Z.log`、`081521Z` 和本轮的三次运行），实施会话把 `GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE` 指向了 `/home/dev/gdds-fe-logs/fe2a/npm-cache-prefilled-a2fb4a02-05.tar.gz`。这个文件是 07:49Z 在 05 上把缓存目录重新打包得到的，SHA256 为 `91ccf614…`，不是 FE0 从 CT201 传来的归档（`0d861824…089f4`）。
- 我在 05 上解开两个归档逐文件比较：内容完全相同；05 上被挂载的缓存目录 `/home/dev/gdds-fe-cache/fe0/npm-cache` 也与 FE0 归档完全相同。所以实际使用的缓存没有问题，只是记录的来源不对。
- **我的疏漏：** 第 1 轮复审我只核对了 runner 日志中的 hostname、HEAD、树和 exit code，没有核对缓存来源字段，因此 rereview-1 §2.2 写“与 handoff 一致”时漏掉了这一点。在此更正。
- **要求：** 05 是调试节点，不影响本轮结论。但 04 取证必须使用 04 上 FE0 预填充的归档（默认路径 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，SHA256 `0d861824…089f4`），不要使用节点上自行打包的副本。handoff 中的缓存来源写 CT201 的 FE0 预填充（来源提交 `a2fb4a027a`、归档 `0d861824…089f4`），`91ccf614…` 只能作为 05 上的本地副本注明。

### 3.4 变异探针

05 上的一次性 worktree，跑 runner（不含 e2e），用后删除。

| 探针 | 改动 | 结果 |
| --- | --- | --- |
| N1 | 去掉异运算符分组分支 | exit 1；只有公式渲染与 History 对齐两个用例失败 |
| N2 | 视图状态恒为“更新” | exit 1；只有视图状态用例失败 |

## 4. Findings（均为非阻塞）

**R7. 一元运算符被显示为分组**（`formula-view.ts:92`）
单子节点的一元运算符（如 `-`）也进入了新的分组分支，显示为“| （- 分组）”加一行缩进的“- 线路保护装置 A:线路电流”。Composite Signal Device §Frontend 规定“一元操作符显示为前缀”，第 1 轮的“| - 线路保护装置 A:线路电流”才符合规则，现在的用例也改成了断言分组形式。公式含义没有错，只是显示啰嗦。建议把分组分支放到单子节点分支之后（只对两个及以上子节点的异运算符表达式分组），并恢复原断言；可以留到 FE2b，或在 owner 看截图时一并决定。

**R8. handoff 中的缓存来源**（§3.3）
在 04 取证的 handoff 中按 §3.3 更正。

**R5、R2**：带入 FE2b（同第 1 轮）。

## 5. FE2a 退出前剩余事项

1. **04 取证**（kickoff §6、§7.3、§7.4）：
   - 在 `ct108-gw-dms-04` 的 clean detached worktree 上，用代码候选 `a80a2e93af` 运行一次完整的 `./frontend/scripts/run-tests.sh --screenshots <worktree 外的绝对路径>`，重拍全套截图；
   - 工具链镜像和 npm 缓存沿用 04 上 FE0 的预填充（默认路径），运行前核对 config digest、7 个 DiffID 和归档 SHA256 `0d861824…089f4`；
   - 日志记录 hostname、起止时间、起止 HEAD 和 `frontend/` 树、exit code 和 SHA256。04 上 `764d952757` 那次运行只作为历史记录；
   - 取证提交只改 handoff，提交后由审核会话做证据核对。
2. **owner 确认：** 无草图页面的截图（公式抽屉 Preview/History、数据集替换双侧浏览、加载骨架、错误页、导航回退），以 04 的截图为准；R7 是否在 FE2a 内处理也在这时决定。
3. **退出：** owner 确认后，由设计会话把附注 tag `fe-fe2a-exit` 打在 04 取证的 handoff 提交上，然后合入 `main`。
4. **合入后可以清理：**
   - 审核会话：开发主机上的 `/home/dev/gdds-fe-review-fe2a-57e77505`、`/home/dev/gdds-fe-rereview1-fe2a-c1abe10c`；05 上的 `…-05` 对应 worktree 与 `/home/dev/gdds-fe-rereview2-fe2a-c1b8fc81-05`（本轮在开发主机上只用 `git show` 只读查看实施仓库，没有另建 worktree）；
   - 实施会话：已被取代的 05、04 worktree，以及 05 上重新打包的缓存副本 `fe2a/npm-cache-prefilled-a2fb4a02-05.tar.gz`（证据目录中保留其 SHA256 记录即可）。
