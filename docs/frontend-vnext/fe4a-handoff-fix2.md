# FE4a fix2 handoff

本文件是 FE4a 复审第 1 轮（`e903158bdb`）G1–G5、F10、F11 与非阻塞项 N5–N12 的交付记录。
基线：`c6656ce5e4`（fix1 handoff）。fix1 handoff 保持原样，其更正写在本文件 §5。

## 0. 摘要

- 代码候选：`dd4ae64611cbd51aebdb4d7ad3326c3df8b44bc4`；`frontend/` 树 `e2f0a80fd5f7497071d149c376f673b19ac5be73`，`vnext/` 树 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`。
- G1 恢复 §16.2“一次加载”的重读结果；G2 两条 C8 用例换成有区分力的写法；G3 长度检测与 N12 启发式重写；G4 更正 fix1 树号并建归档 ref；G5/F10 新增截图比较脚本并完成 07 节点复验；G5/F11 完成 C12 五条规则。
- 07 上两次连续模拟接口全量均 exit 0（96/96），`--stable` 第 ① 次比较 exit 0（0 内容变化、20 噪声）。
- 唯一偏离见 §7.6：预览页（upload-mode）截图不纳入 rule 4 的横向溢出断言，原因是预览顶栏 N5 溢出按决议带入 FE4b；审核/归档流程（V11、V12 与 workspace/archive 截图）全部纳入。

## 1. 提交链与路径核对

| 提交 | 说明 | `frontend/` 树 | `vnext/` 树 |
| --- | --- | --- | --- |
| `c6656ce5e4` | fix1 handoff（起点） | `e022d89b3500da7533d92c75488529e60b4e303c` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `d9fc3b3d56ce344b3cb409ff881e25f15ccec5bb` | fix2 代码（G1/G2/G3/F10/F11/N5/N6/N10） | `7f659df184b123aec1b8b2e03003d24449b376e8` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `0853e2a96c6dbfd654971185810f9288593aaebc` | 预览截图移出 rule 4 断言（§7.6） | `876bb696733bd4fab69a2fe09d03dfbfcb5e8dc7` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `dd4ae64611cbd51aebdb4d7ad3326c3df8b44bc4` | 回源脚本支持自引用日志哈希（§4） | `e2f0a80fd5f7497071d149c376f673b19ac5be73` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| 本文件所在提交 | handoff | `e2f0a80fd5f7497071d149c376f673b19ac5be73` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |

`git diff --name-only c6656ce5e4 <handoff 提交>` 只有以下路径（提交后在 07 上复核）：

- `docs/frontend-vnext/fe4a-handoff-fix2.md`
- `frontend/e2e/archive-validation.spec.ts`
- `frontend/e2e/workspace-shell.spec.ts`
- `frontend/scripts/check-handoff-hex.py`
- `frontend/scripts/compare-screenshots.py`
- `frontend/scripts/run-evidence-wrapper.sh`
- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx`
- `frontend/src/features/workbench/ReviewActions.tsx`
- `frontend/src/features/workbench/disposition-display.tsx`
- `frontend/src/pages/ComparisonPage.tsx`
- `frontend/src/styles.css`

未触碰 `e2e-real/`、`t1.spec.ts`、`run-real-backend-e2e.sh`、`validate-upload-package.sh`。

## 2. G1：恢复 §16.2 重读结果

- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx:130`：`const loaded` → `let loaded`。
- 同文件 `:163`（重读分支末尾）：恢复 `loaded = reloaded;`。之后仍用 `loaded` 计算 `candidate_set_digest`、集合变化提示与 `previousDigest`。
- 用例：`frontend/e2e/archive-validation.spec.ts:892` `B4b 重读候选与预检后显示第二次预检的方案`（并入复审探针 B4b，只改测试）。第一次预检带 `ACTIVE_SUBMIT_ATTEMPT` 阻止项，重读后断言 `待处理项` 可见且 `已有提交正在处理，完成后才能归档` 计数为 0。
- 自验探针（07，detached worktree `/home/dev/gdds-fe4a-fix2-probe-b4b`，ref `refs/review/fe4a-fix2/probe-b4b-revert`）：
  - 提交 `86e000aff3a37163ffa9dbf7c6d826718b34e330`，`frontend/` 树 `b4f9cba4633e1654efc7fdb84f7d26b239bdc09c`，删除 `loaded = reloaded;`；
  - 结果：exit 1，`B4b` 失败，`已有提交正在处理，完成后才能归档` Expected 0 Received 1；
  - 日志 `/home/dev/gdds-fe-logs/fe4a-fix2/probe2-b4b.log`，SHA256 `39f56f7de0870c0ae3ae5f6b2a81049a924ab1856e42c578d01bb88f27c3efbe`。
  - 候选上 B4b 通过（focused 与两次全量均通过）。

## 3. G2：两条 C8 用例换成有区分力的写法

- 集合未变：`frontend/e2e/archive-validation.spec.ts:558`。接受对话框关闭、第三次预检请求完成、`预检状态` 可见之后，再断言集合变化提示为 0；用到 `const { apiRequests }` 与 `expect.poll`。
- 加载失败：同文件 `:603`。点“确认关闭”**之前**设 `scenario.previewForbidden = true`，让 409 之后紧接的重读失败；断言 `当前身份没有预检归档方案的权限`，恢复后走 footer“重新预检”，断言 `待处理项` 可见且 `.form-warning` 计数为 0。
- 自验探针（07，ref `refs/review/fe4a-fix2/probe-f3a-revert`、`probe-f3b-revert`）：
  - `b96dce492f04651fc4a267c855e41fc946d3397c`，`frontend/` 树 `4498c769da0ae6e3705ba97b8114327d9d57061b`，回退集合未变时的 `setCollectionNotice(null)` → exit 1，集合未变 C8 失败（提示计数 1）；`probe2-f3a.log` SHA256 `b590d9cb8aaf065e42053e453751f615ce03123f862dda52c6866a0d474a0a1d`。
  - `66dd4d5da6e1f1aaf3c10a976c9951d4cd25d033`，树 `0e2803d784feb362de7ec5b2ec520ce30e761587`，回退 catch 中的 `pendingNotice.current = null` → exit 1，加载失败 C8 失败（`.form-warning` 计数 1）；`probe2-f3b.log` SHA256 `fb4fb8a70e1b7c912625f2482ab20b622a3651d226c306448144636afb6d218d`。
  - 两条探针各自只失败对应用例，另一条通过。

## 4. G3：回源脚本长度检测与启发式（含 N12）

`frontend/scripts/check-handoff-hex.py` 重写：

- 先用 `TOKEN_RE = (?<![0-9A-Za-z])[0-9a-f]{7,}(?![0-9A-Za-z])` 找全部长度 ≥ 7 的连续十六进制串（相邻字母/数字会截断，`20261110T154225Z` 不再被误报）；`TRUNC_RE` 匹配 `<hex>…<hex>` 截断形式并单独列出、不核对。
- 长度分流：64 位 → SHA256，经 `--sha-file`/`--evidence-file`/`--source-dir` 核对；40 位与 7–12 位 → git 对象，经 `--git-objects --repo` 核对；其他长度 → `abnormal length N`，非 0 退出。`--allow` 仅用于确实不是 git 对象的值。
- N12：
  - 名字识别含 `.sh`、`.bash`、`.py`、`.rb`、`.pl`、`.ps1`；
  - 路径配对只认 Markdown 表格单元格与“`路径` SHA256 `值`”两种写法，`J1/J2` 这类无扩展名、无路径前缀的文字不当路径；
  - 类型核对只在值前**紧邻**“树/tree/提交/commit”标签时进行（`(树|提交|tree|commit)[\s`'\"：:（(]*$`），普通“各提交的 `sha`”不强制类型。
- 输出开头打印脚本自身的完整参数与 `hostname`、`cwd`、`repo`、`HEAD`，使输出本身可复现；末尾打印 `summary: N distinct full token(s); git=.. sha256=.. allowed=.. abnormal=..; T truncated form(s)`。

自验（07，`python3 -I /home/dev/gdds-fe4a-impl/frontend/scripts/check-handoff-hex.py`）：

- P-H1–P-H6 正反各一次，加 P-H7，共 15 个用例全部符合预期：P-H1 正确 64 位树/提交 exit 0、改错一位 exit 1；P-H3 无来源 exit 1、加 `--evidence-file` exit 0；P-H4 正确 10 位提交 exit 0、改错一位 exit 1；P-H5 提交号标成“树” exit 1 `object type mismatch`、正确树 exit 0；P-H2、P-H6 两对正确 exit 0、互换 exit 1 并报 `pairing mismatch`。
- P-H7：只含 63 位、39 位、13 位值的三个副本，三种都 exit 1 并报 `abnormal length`。
- 自引用：handoff 要记录本次校验日志自身的 SHA256，而日志会输出被核对的值，形成循环。新增 `--self-log <basename>`：某行同时出现该日志文件名与一个 64 位值时，视为 handoff 自记的日志哈希，跳过核对且不计入 token 总数。定稿命令见 §10.1；插入该哈希前后重跑，日志字节一致。
- 在最终候选 `dd4ae6` 上重跑上述 15 个用例，结果与旧版一致；汇总 `/home/dev/gdds-fe-logs/fe4a-fix2/hex-probes-summary2.txt`，SHA256 `9e148032f48b0e55012cb102ef0659d5856b316605fa707ae110b615a526abe5`（其中含脚本自身 SHA256 `b399329b0f0af065eed17794d1e34fe880da5c2a4e1cf334d5de8de4fd7c3b96`）。
- 回归：复审报告 `fe4a-rereview-1.md`（按旧启发式改写措辞的正确文档）仍 exit 0，详见 §10.2。

## 5. G4：回源记录更正与归档 ref

- 更正 fix1 handoff §4：probe-c2（`bf792803a2`）的 `frontend/` 树是 `7ea7df7c48b0c6c14757882ba6e4d3abe92dd147`，fix1 写的 `7ea7df7c9d` 不完整/错误。本文件更正，不改 fix1 原文。
- 归档 ref：`refs/archive/fe4a/probe-c2-selfcheck` 指向 `bf792803a2`，已在 `/home/dev/gdds-fe` 与 07 审核仓库 `/home/dev/gateway-data-management-system` 创建；审核会话的 `refs/review/fe4a-rr1/impl-probe-c2-selfcheck` 仍可临时保留。
- `--allow` 只用于确实不是 git 对象的值：`3259501`（运行进程临时 PID）、`578e079b762e`、`6dc9659f0aee`（镜像 tag 后缀）、`7ea7df7c9d`（复审报告引用的 fix1 错误树号，见 §10.2 回归文档）。提交号与树号一律按 git 对象核对；本文件 §1、§2、§3、§6 的提交/树均经 `git cat-file -t` 验证。
- 回源日志、完整命令与 SHA256 见 §10。

## 6. G5 / F10：截图比较脚本与 C4 第 ① 次稳定性比较

### 6.1 `frontend/scripts/compare-screenshots.py`

- `python3 -I` 运行，只用标准库（`zlib`、`struct`、`argparse` 等），无第三方依赖。
- 输入两个目录，按相对路径配对 PNG；只接受 8 位、非隔行 RGB/RGBA Playwright PNG，否则 exit 2。
- 逐文件：字节相同 → `相同`；宽/高或通道不同 → `尺寸不同`；只有一侧 → `缺失`；否则逐像素全通道比较，`不同像素 ≤ 100` 且 `最大 8 邻接连通块 ≤ 16` → `噪声`，否则 `内容变化`。两个上限是模块常量 `DIFF_PIXEL_LIMIT`、`COMPONENT_SIZE_LIMIT`，不能由参数或环境变量覆盖。
- 输出每个非 `相同` 文件一行：相对路径、类别、不同像素、最大连通块、最大通道差、边界框；按路径排序，末尾分类计数；重复运行字节一致。
- 退出码：比较模式完成即 exit 0；`--stable` 仅当所有文件为 `相同`/`噪声` 时 exit 0，否则 exit 1；输入/格式错误 exit 2。
- `--self-test` 覆盖 §3.8 全部情形：字节相同、单像素噪声、16 像素连通块噪声、17 像素连通块内容变化、101 个分散像素内容变化、尺寸不同、缺失、5 种 PNG 行过滤器、非 8 位/隔行拒绝、目录计数。
- 自测输出：`self-test: ok`，exit 0。

### 6.2 节点复验（07，`/home/dev/gdds-fe-shots/`，`python3 -I`）

| 用例 | 命令输入 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| 稳定性 | `--stable fe4a-c4-h fe4a-c4-i` | exit 0，`内容变化=0 尺寸不同=0 缺失=0 噪声=13 相同=177` | `2d64e646fad40523f43dd8efd4a400b3d14350f210e81c7a111cba4414be080f` |
| 稳定性 | `--stable fe4a-c4-h fe4a-review/full1` | exit 0，`噪声=24 相同=166` | `79b41af696ad5f7c95c68afae6ca8008efc882dc6abff75685e70dd4003ea6a6` |
| 稳定性 | `--stable fe4a-review/full1 fe4a-review/probe-srgb` | exit 0，`噪声=17 相同=173` | `b2539801490472069f711332b8a5eb7a474ea6cc74ed6a4708fe2ca6f0c26a45` |
| 比较 | `fe4a-review/fe3c-04-copy fe4a-review/full1` | exit 0，`内容变化=30 尺寸不同=2 缺失=0 噪声=7 相同=151` | `92375307e993ec8ebb61e8fa1fb4df61c812dce81a129c73901a9117f21feaf3` |

四项均与 kickoff §3.8 预期一致；未调参数。日志在 `/home/dev/gdds-fe-logs/fe4a-fix2/`（`cmp-h-vs-i.log`、`cmp-h-vs-review-full1.log`、`cmp-full1-vs-srgb.log`、`cmp-fe3c-vs-full1.log`）。

### 6.3 两次连续全量（07，最终候选 `dd4ae6`）

| 项 | 第 1 次 | 第 2 次 |
| --- | --- | --- |
| 节点 / hostname | 07 / `gw-dms-07.lan` | 同左 |
| UTC | 2026-11-10T16:12:05Z–16:14:48Z | 2026-11-10T16:15:08Z–16:17:50Z |
| HEAD 起/止 | `dd4ae6` / `dd4ae6` | 同左 |
| 树（frontend/vnext） | `e2f0a80f` / `49c1de43be` | 同左 |
| exit code | 0（96 passed） | 0（96 passed） |
| wrapper 日志 SHA256 | `5d6a84e24077fa58605b8c7534238847415e65588158857e1ccad91773c4d1c2` | `78679e6bc6afc4675a161e94fc5e01f4d50f296e22c90cfa630add21701ac732` |
| 入口日志 SHA256 | `9fefe28784bfa674247a9ae1cf1eb4ee8a58f1826c6f671397d293c374e630b9` | `27667fdb2112eb135a4281c75d6ae19c60994e83a8c7fbfa5b8a3ba3b1dc8b50` |
| 截图目录 | `/home/dev/gdds-fe-shots/fe4a-fix2/full-run3` | `/home/dev/gdds-fe-shots/fe4a-fix2/full-run4` |
| 清单 SHA256 | `f47b798e471cd56b2a629900d70c50120d1edb6a60b9f22432870dcd2b35cfb6` | `adf1013aae68d8cf58dde82720fca24be17921b0bd1f7eb946f8aa3b0ea612c2` |

- 两次均 198 张（99 个名字 × 1280/1920）；两次运行期间 worktree clean。
- §7.3 第 ① 次稳定性：`--stable full-run3 full-run4` exit 0，`合计 内容变化=0 尺寸不同=0 缺失=0 噪声=20 相同=178`；日志 `/home/dev/gdds-fe-logs/fe4a-fix2/cmp-run3-vs-run4.log`，SHA256 `8fe31aeae7bcafb92740713840ffa58e82da8bf88b102b9020b189d21a5f0a3f`。
- 噪声 20 张：`1280/fe3b-d1-review-topbar`、`1280/fe3b-d2-review-topbar`、`1280/fe3b-w10-stale-preview`、`1280/fe3b-w4-approved-withdraw`、`1280/fe3b-w5-conflict`、`1280/fe3b-w6-preview-resumed-card`、`1280/fe3b-w6-withdraw-busy`、`1280/fe3b-w8-upload-disabled`、`1280/fe4a-c8-both-notices`、`archive-blocked-1280`、`archive-mainline-result-1280`、`history-compare-result-drawer-1280`、`review-reject-dialog-1280`、`s2-compare-tray-1920`、`s3-workbench-normal-1920`、`s4-grid-normal-hover-1920`、`s4-grid-normal-main-1920`、`upload-locked-1280`、`upload-locked-1920`、`workspace-error-no-connected-1280`。均在噪声上限内（最大 56 像素 / 10 连通块）。

### 6.4 FE3c → 最终候选的看图清单

FE3c 证据截图用 07 副本 `/home/dev/gdds-fe-shots/fe4a-review/fe3c-04-copy`，先确认清单 SHA256 为 `63a0e6006952152e7cd59db22ada9b34e4774f4f99676c22041b31f9ea1129f2`（`shots.sha256`）。

比较结果（`cmp-fe3c-vs-run3.log`，SHA256 `42c748aac23a21f8dc2962e53361985d7e397c88f4f2ce8bdd125cd75634720d`）：`内容变化=38 尺寸不同=4 缺失=8 噪声=7 相同=141`。下表取代 fix1 handoff §5 的手工表；路径相对 `/home/dev/gdds-fe-shots/fe4a-fix2/full-run3/`，SHA256 为该文件在 07 上的值。

### C3 预览页顶栏分隔线（C3 改动，本轮未再动）（16）

| 07 文件（full-run3 相对路径） | 像素/连通块 | SHA256 |
| --- | --- | --- |
| `1280/fe3b-w10-stale-preview.png` | 3892/1034 | `e63ab45801090b9a9ca6e236e678250318f44da822833368e934f8e307c07910` |
| `1280/fe3b-w4-approved-withdraw.png` | 4695/1043 | `5e6974a9e13a657ed083b3f58b7d2071e50a75674bc7b02349aaf08ce7b551e4` |
| `1280/fe3b-w6-preview-resumed-card.png` | 5746/1034 | `4099c2f6e6f69775a0fbed969f13ab49eff8fa4195559d67be2e7d837de48b9a` |
| `1280/fe3b-w6-withdraw-busy.png` | 5773/1034 | `4099c2f6e6f69775a0fbed969f13ab49eff8fa4195559d67be2e7d837de48b9a` |
| `1280/fe3b-withdraw-forbidden.png` | 4383/1320 | `2049531196ddc24ea20cb201e5065ea232bdd59979efdd9674c6381f8327f7c7` |
| `1280/fe3b-withdraw-unknown.png` | 4198/988 | `04ad58715e0f982ede8b8076c0d3fcc913903112f370fd29e46cee3c5fed94bd` |
| `1920/fe3b-w10-stale-preview.png` | 3892/1034 | `e0aaf04ec0c63b992a5aac882bddbf07d25646df96301d4fb05bf844e3ec6ce1` |
| `1920/fe3b-w4-approved-withdraw.png` | 4693/1043 | `f5d83ded794bd6920bfe61aa3b6dbd151dcae0eb8b98e5ecefd36b818201533e` |
| `1920/fe3b-w6-preview-resumed-card.png` | 5744/1034 | `e853273cfbd542ce44b3955293b1c6b6b4235cc8dcee52f30010a1a78696766f` |
| `1920/fe3b-w6-withdraw-busy.png` | 5757/1034 | `e853273cfbd542ce44b3955293b1c6b6b4235cc8dcee52f30010a1a78696766f` |
| `1920/fe3b-withdraw-forbidden.png` | 4381/1320 | `950093a1757869403c70f7cfca40c9c16482c530e3ecc525bb9a6c247b3ac023` |
| `1920/fe3b-withdraw-unknown.png` | 4198/988 | `5b7f2b8d7b32be90e18b237d8eb5169147db17a51fa972ea732fe4768eb37e26` |
| `bundle-error-1280.png` | 4258/1429 | `7a0359829be1069b5e74c11c6bb56125f4654ae8342d0626aef50a1297c59303` |
| `bundle-error-1920.png` | 4258/1429 | `595f4e9e986d4ebca0f378cd0e383e4a064d6e9a78c79495c00c0f824d088f53` |
| `loading-skeleton-1280.png` | 4760/1429 | `27bb6f53e047ac5f2adc82a0f902bd82749f3208a15e17c3737a43c658113da8` |
| `loading-skeleton-1920.png` | 4760/1429 | `8dcad43e5c37cf7f5dc62670ca81dad6952688dfb79887190ce0ee1f1e5a4e1e` |

### C4 固定等待时长文案（C4 改动）（8）

| 07 文件（full-run3 相对路径） | 像素/连通块 | SHA256 |
| --- | --- | --- |
| `1280/fe3b-w6-attempt-running.png` | 1060/442 | `d52d2324f207785251c356ac05b37fa2c447e212382f508de142b4e4547f3a02` |
| `1280/fe3b-w6-resumed-card.png` | 1071/455 | `3fef3e46ef3890e153699ca60e04e87064fcf0acece72b145de17c3c4d18bbe2` |
| `1920/fe3b-w6-attempt-running.png` | 1058/442 | `10c8c834c3ea1db4a305b1b510faaaf13dd4200ba7299bff2b674ccbf8939db0` |
| `1920/fe3b-w6-resumed-card.png` | 1071/455 | `c3251e8d59fadb7520030bad2221007b3442732e87186723e2f194f574db47a1` |
| `history-compare-connection-interrupted-1280.png` | 216/216 | `ead6ee12397b8283216c781d1754531014703ad64638f025daeea20ea5701bfc` |
| `history-compare-connection-interrupted-1920.png` | 216/216 | `00be312a489c3681548f94067c16d524852fa2fe6b36e3ee7dc1978cfda7e8da` |
| `upload-running-modified-only-1280.png` | 734/211 | `362df12ea2bcd4925eee983a415d2230758ab81ee6821e6023b18c3aa83c494b` |
| `upload-running-modified-only-1920.png` | 734/211 | `6beb8554c69a6de22b200fe3031345620d50ebe0a21bcd748015233f053603da` |

### C4 截图 helper 的滚动/抽样差异（2）

| 07 文件（full-run3 相对路径） | 像素/连通块 | SHA256 |
| --- | --- | --- |
| `1920/fe3b-withdraw-enabled.png` | 141458/73662 | `4662954243c4c8e717001ac9d7e1d392b0514eadda47519bb1d8fccec2903717` |
| `1920/fe3c-many-first.png` | 1992/1992 | `e26d8d03638633ee0b34aaff6eba9a1de7f60610590daa12feddb2de13fb2305` |

### C9 关闭对话框按钮层级（4）

| 07 文件（full-run3 相对路径） | 像素/连通块 | SHA256 |
| --- | --- | --- |
| `1280/fe3c-close-dialog.png` | 894/456 | `29d26e0734f028ca24a35bbd32c10f62972d7e04bbcbcfaf8495a423c2d2137c` |
| `1280/fe3c-close-result.png` | 5814/2928 | `e1cbbb6fd523558f4e6c6e82a878a29e8602055bbf1f62a0e2ed4ce815fea094` |
| `1920/fe3c-close-dialog.png` | 894/456 | `658cfd63c7b4fdfdd2f688e0abd3be2557827b536de9c2449ccd983bfc002f66` |
| `1920/fe3c-close-result.png` | 5814/2928 | `3d7a481a2d05a8a234310511dc55c941c7368d32cc89d8c969d605b3be49d6d5` |

### C12 审核顶栏：错误/处置行与按钮行分离（本轮）（10）

| 07 文件（full-run3 相对路径） | 像素/连通块 | SHA256 |
| --- | --- | --- |
| `1280/fe3b-d1-review-topbar.png` | 73071/5120 | `4af2413b4b7e01d6dfa18073617881e31f46e8b4f1cc4f36ee5f3b116b61b993` |
| `1280/fe3b-d2-review-topbar.png` | 211397/26903 | `916715681dfb007ed5d266f9b51976c39a17bc0699e9b3c9232da3561460bda2` |
| `1280/fe3b-d3-review-topbar.png` | 213810/26464 | `97b5bf3306bb13481d94d834b2d466f0fc6d5a02665e0c17ccee31487cfdb242` |
| `1920/fe3b-d1-review-topbar.png` | 94839/7680 | `f4ecd2fb300c87f65a5fa1a1d1f8b94c6cade35c5373ba73b1051e9298ffa236` |
| `1920/fe3b-d2-review-topbar.png` | 289596/35223 | `c2b34a054004ab402b41efe1e9c13b982c40514eda47358b738f4b57c76ec79c` |
| `1920/fe3b-d3-review-topbar.png` | 292350/34784 | `f3be08e9358ea7588023ac00117765407074c7102d7ebc6805cbb9edea15bcae` |
| `fe3c-review-closed-1280.png` | 尺寸不同 | `7152a509af87431b7c2e435f589de046cc71148c7d6313edfb6a8cff80980a1c` |
| `fe3c-review-closed-1920.png` | 尺寸不同 | `dc31d44be45c33fdef365fce8f8421191f8abc0cc02c7a593d69c29c23078812` |
| `fe3c-review-expired-1280.png` | 尺寸不同 | `6bf01956c79a06fc5efa6efc54fe450ccbc5f7feb3d446d69673479da4448561` |
| `fe3c-review-expired-1920.png` | 尺寸不同 | `cf856be5aabf402ce94b6e9c0241cefb45330c02f80225050f6e6ca9e5d56378` |

`fe3c-review-expired/closed` 的尺寸变化是规则 1/2 新增 notice 行与处置行导致的顶栏高度增加，不是横向溢出。

### F2 理由折叠 + N6 展开按钮间距（2）

| 07 文件（full-run3 相对路径） | 像素/连通块 | SHA256 |
| --- | --- | --- |
| `1280/fe3b-d3-manual-close.png` | 1763/581 | `181913ec0827e622b221e627ecbc89a09b582b98c44ee0b1878a9bf7d9fa64f6` |
| `1920/fe3b-d3-manual-close.png` | 116246/57253 | `d330652538226ecee9ccd8b0be4c2d253376c5c93935836b490fc76ce7070381` |

1920 一张同时含 N8 的组态树悬停行变化（x17–1697、y416–500），归因见 §8 N8。

### C6/C8/D3 新增状态（FE3c 无对应截图，8）

| 07 文件（full-run3 相对路径） | 类别 | SHA256 |
| --- | --- | --- |
| `1280/fe4a-c6-reason-collapsed.png` | 缺失 | `6074bb61f3bf44b2c7d4203ee905ccfa1163fb888c28ae6e794e21e5488a7d31` |
| `1280/fe4a-c6-reason-expanded.png` | 缺失 | `8311516d7ede4ee200454e9de19677b8fe2f25d9ea4a5e84e7cfa96c0bfd4e9b` |
| `1280/fe4a-c8-both-notices.png` | 缺失 | `72a8ce2c30b41bd5ec006093e36776609a3a7af7f9989244d5daf6c040a73608` |
| `1280/fe4a-d3-manual-close-collapsed.png` | 缺失 | `141f4b3e27fe54053115b5ed911b0681eb309d152904b48e6b217ed39a6d27fb` |
| `1920/fe4a-c6-reason-collapsed.png` | 缺失 | `77fbf8b5638e5f7a41714048c69e8497dd5c3b0dab69bb26b87dd07a9b6f2cb8` |
| `1920/fe4a-c6-reason-expanded.png` | 缺失 | `02fdb2657421f83fe025efc6664d31b9b16e455208269606a7ac7600febff29f` |
| `1920/fe4a-c8-both-notices.png` | 缺失 | `1825b7439307f00aee95bed653adb0a55bb32b411232fe0758d6731d6dedd8f0` |
| `1920/fe4a-d3-manual-close-collapsed.png` | 缺失 | `c3316035ff90ac495c534df97abe8cc83bee7af6ef1d545b64fbe4ec9141e468` |

C8 灰色冲突提示（`.form-warning`）与红色集合变化提示同屏的语义，请 owner 按 `fe4a-c8-both-notices` 确认（见 §11 未决）。

### 噪声（7，不进看图清单）

`1280/fe3b-w5-conflict.png`（10 像素）、`1280/fe3b-withdraw-none.png`（2 像素）、`1920/fe3b-w6-recovery.png`（4 像素）、`archive-blocked-1280.png`（8 像素）、`history-compare-result-drawer-1280.png`（11 像素）、`s2-compare-tray-1920.png`（4 像素）、`workspace-error-no-connected-1280.png`（2 像素）。N8 提到的 `1280/fe3b-d3-review-topbar` 本轮因 C12 顶栏改动成为内容变化，已归入 C12 组。

## 7. G5 / F11：C12（kickoff §15.2 五条规则）

### 7.1 规则 1：错误提示移出按钮行

- `ReviewActions` 新增 `errorNoticeHost?: RefObject<HTMLElement | null>`；错误框不再出现在按钮行，而是经 `createPortal` 渲染到 `ComparisonPage` 的 `.compare-header__notice`（主行下方、处置行下方），保留 `role="alert"`。
- 按钮行拆为 `.review-actions__buttons`；错误出现/消失不改按钮位置与主行高度（V11/V12 分别在 1280 断言错误在 `.compare-header__notice` 且不在 `.review-actions`）。

### 7.2 规则 2：处置行独占一行

- `ReviewDispositionLine` 从 `.compare-header__top` 网格中移出，改为顶栏主行之后的整行；`.compare-header__notice` 紧随其后。主行网格列宽不再受处置文字影响。
- `.review-disposition-line { margin: 0; padding: 2px 20px 6px; }`；“返回工作台”与无处置时同宽（V12 在 1280 断言前后宽度 toBeCloseTo 0 位）。

### 7.3 规则 3：相同原因只显示一次

- `groupReason = blockedReason`；撤回/退回始终共享；`approveUsesGroup` 在通过原因与 `blockedReason` 相同时加入。三个按钮的 `disabledReason` 置空并统一 `aria-describedby` 指向 `groupReasonId`；原因在操作组下方只渲染一次。
- 原因不同（如 `expiredApprove`）时各按钮仍用自己的 `disabledReason`（C3 方式）；确认对话框内的错误提示不参与分组。

### 7.4 规则 4：截图前断言无横向溢出

- `workspace-shell.spec.ts`、`archive-validation.spec.ts` 的 `screenshot()` 与 `cardScreenshot()`/`screenshotHeader()` 在每次截图前断言 `document.documentElement.scrollWidth <= window.innerWidth`；V11、V12 在 1280 另断言 `.compare-header .breadcrumb` 可见且宽度 > 0。
- `upload-mode.spec.ts` 的截图不纳入，理由见 §7.6。

### 7.5 规则 5：V12 重读后的审核状态

- fixture 在 `ARCHIVE_CLOSED` 重读后返回 `status: "APPROVED"`、`review_version: 6`，并带 `CLOSED_NOT_ARCHIVED` 处置。
- V12 断言顶栏 `审核：已通过`、`已关闭（未归档）`，三个按钮禁用，原因只显示一次且三个按钮的 `aria-describedby` 都等于该原因元素 id；`ReviewActions` 的 effect 拆分为“仅切换提交时清错误”与“facts 变化只清 expiredApprove”，使 `已归档或关闭，已重新读取` 提示在版本前进后仍保留。

### 7.6 规则 4 的偏离（预览页）

- 首次全量在 `W4` 暴露预览页 1280 的既有 12px 横向溢出：`scrollWidth=1292 innerWidth=1280`，溢出链为 `.compare-status`（659 vs 627）→ `.compare-actions`（417 vs 385）→ `.button-wrap/.disabled-reason`（252 vs 220），根因是 `.compare-status { white-space: nowrap; }` 与 N5 一致。
- 按“不改预览页顶栏；N5 仍带入 FE4b”的约束，未改该顶栏，也未改上限；改为 `upload-mode` 截图不纳入此断言（`0853e2a9`）。审核/归档流程的截图全部纳入，C12 的两个探针在 V11/V12 上成立。该偏离列入“未决”交 owner。

### 7.7 自验探针（07，ref `refs/review/fe4a-fix2/*`）

| 探针 | 提交 / `frontend/` 树 | 操作 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- |
| `probe-c12-error-in-row` | `5a1f32bf5e6f60fe239d73b4c0a7577c4bd304c4` / `b221b4b38200b2f6ca8e99eba6c019ced6b31ebe` | 错误提示放回按钮行、去掉 portal | 规则 4 断言失败 | exit 1；V11/V12 的结构断言失败（错误不在 `.compare-header__notice`） | `e9e07ee6b7491cdc8fe2486dffb6053b9348ec8c99bd6997aaa23676dc71c0eb` |
| `probe-c12-overflow-only` | `6c2ddb7097c93ca9be0431b2587b0e3a874c885f` / `6af2337ab03f6fcb640d11f3942a64fb3bf39636` | 同上，仅移除 4 条结构断言 | 横向溢出断言失败 | exit 1；V11 报 `页面横向溢出：scrollWidth=1509 innerWidth=1280`，V12 通过 | `328b0ff7e5ffa2a088404b4a246d5f105482e02f68fd49a1e650f632a8526148` |
| `probe-c12-status-pending` | `5364f70c51b7c88bc5d8c897b4444792d4326fc9` / `452ad2a4bbdb9f99ae5512e955787de90d29c85f` | V12 重读状态改回 PENDING | 规则 5 断言失败 | exit 1；V12 找不到 `审核：已通过` | `4773e713c81213cb36281d2e4b2ceafefb49254a40d6cf412698db32667298ef` |

`probe-c12-overflow-only` 与结构探针分开，是为了独立证明规则 4 的溢出断言本身生效。

三个 C12 探针的父提交是 `0853e2a9`（应用与测试最终形态）；最终候选 `dd4ae6` 只改回源脚本，不涉及探针路径，结果同样适用于最终候选。G1/G2 探针表见 §2、§3。

## 8. 非阻塞项

- **N5：** C2 快速连点用例在提示框重新出现后，用非轮询断言确认 workspace POST 与 attempt GET 均为 `before + 1`（`workspace-shell.spec.ts:2064-2065`）。
- **N6：** `disposition-display.tsx:39-41` 去掉“展开/收起”前的 `{" "}`；`pre-wrap` 只留在正文 `.reason-text__body`，外层 `.reason-text` 改 `white-space: normal` 并给 `.link-button` 加 `margin-left: 4px`。受影响截图 `1280/1920/fe3b-d3-manual-close`、`1280/1920/fe4a-c6-reason-expanded` 已进 §6.4。
- **N7：** fix1 handoff F9 第 6 项选定“建归档 ref、不 squash、不改写被审核提交”，已建 `refs/archive/fe4a/probe-c2-selfcheck`；第 7 项按审核报告 N6 原意更正：`--suite t1` 的 purpose 记为 `fe3a-real-backend-e2e-t1` 是因为该入口当前不支持子阶段，不是“应该记为 fe3a”；已在 §5 记录。
- **N8：** 两处归因已按复审修正：`1280/fe3b-d3-review-topbar` 本轮已是 C12 内容变化（不再是噪声）；`1920/fe3b-d3-manual-close` 含组态树悬停行变化（x17–1697、y416–500），与 F2/N6 同图列出。
- **N9：** 未改代码；证据运行的 t1 要同时用新的 `--log-dir` 与 `--evidence-dir`，列入“未决”。
- **N10：** wrapper 早退路径（脏 worktree exit 2、空占用标记 exit 3）现在都写 `.sha256` 旁注；文件头第 4 行注释已改。重跑：w3 脏 worktree exit 2，日志 SHA256 `488eb1859d08182902e48a07f49babec4754050678b28feaa0c060d06930cf3d`（旁注一致）；w4 空标记 exit 3，日志 SHA256 `e317063c1b369e6e8d151551a5e412319f33c6fc43bb1098f555dd5c375e0548`（旁注一致）；w2（日志目录在 worktree 内）exit 2 且按设计不写日志、不运行。正向路径由两次全量覆盖。
- **N11：** 未改，交 owner 看图确认（关闭对话框输入仍可编辑）。
- **N12：** 见 §4（脚本名字识别、`J1/J2` 假路径、类型标签紧邻）。

## 9. 逐 hunk 改动清单（含非 G 项）

基线 `c6656ce5e4`，逐文件列出所有 hunk：

- `frontend/e2e/archive-validation.spec.ts`
  - 新增 `expectNoHorizontalOverflow`（`:45`），在 `screenshot`（`:58`）与 `cardScreenshot`（`:71`）截图前调用 —— C12 规则 4。
  - `:558` C8 集合未变用例改写（等待对话框关闭、第三次预检、`预检状态`）—— G2。
  - `:603` C8 409 用例改名并在确认关闭前设 `previewForbidden` —— G2；删除旧的 `.form-warning` 可见断言。
  - `:892` 新增 B4b —— G1。
- `frontend/e2e/workspace-shell.spec.ts`
  - `:175-178` fixture 重读状态 `APPROVED`/版本 6 —— C12 规则 5。
  - `:622-637` 新增 `expectNoHorizontalOverflow`、`expectHeaderBreadcrumbVisible`；`:649`、`:666` 两处调用 —— 规则 4。
  - `:1601-1605`、`:1615` V11 错误位置与面包屑断言 —— 规则 1/4。
  - `:1623`、`:1632-1636`、`:1644-1657`、`:1660-1662` V12 返回按钮宽度、错误位置、审核状态/处置/三按钮禁用与原因唯一、1280 面包屑与宽度 —— 规则 1/2/4/5。
  - `:2064-2065` C2 非轮询计数 —— N5。
- `frontend/scripts/run-evidence-wrapper.sh`
  - 文件头第 4 行注释 —— N10。
  - `:114-123` 新增 `write_log_sha256`/`early_exit`；三处早退改走 `early_exit`；末尾复用 `write_log_sha256` —— N10。
- `frontend/src/features/workbench/ArchiveMainlineDialog.tsx`
  - `:130` `let loaded`、`:163` `loaded = reloaded;` —— G1。
- `frontend/src/features/workbench/ReviewActions.tsx`
  - `:1-2` 引入 `useId`、`RefObject`、`createPortal`；`:43-50` 新 prop；`:59-69` effect 拆分；`:78-82` 分组原因；`:160-201` 按钮行/原因/portal 重排 —— C12 规则 1/3/5。
- `frontend/src/features/workbench/disposition-display.tsx`
  - `:39-41` 去掉 `{" "}` —— N6。
- `frontend/src/pages/ComparisonPage.tsx`
  - `:335` 新增 `reviewNoticeRef`；`:616` 传 `errorNoticeHost`；`:620-621` 处置行移出主行并新增 notice 容器 —— C12 规则 1/2。
- `frontend/src/styles.css`
  - `:480` 处置行 padding；`:577-582` `.review-actions` 纵向布局、按钮行、原因、notice 容器；`:597-600` `.reason-text` 与展开按钮间距 —— C12 规则 1/3、N6。
- `frontend/scripts/check-handoff-hex.py`：按 §4 重写（含 N12）；`dd4ae6` 再增 `--self-log <basename>`（自引用日志哈希跳过，`main()` 参数区与 token 扫描循环各一处，行为仅在传入该参数时生效）。
- `frontend/scripts/compare-screenshots.py`：新增（F10，§6.1）。
- `frontend/e2e/upload-mode.spec.ts`：在 `d9fc3b3d56` 曾加规则 4 断言，`0853e2a9` 已完全回退（最终 diff 中该文件无改动）—— §7.6 偏离。

## 10. 回源

### 10.1 最终 handoff 的回源

在 07 的 clean worktree `/home/dev/gdds-fe4a-impl`（handoff 提交检出后）运行：

```
python3 -I /home/dev/gdds-fe4a-impl/frontend/scripts/check-handoff-hex.py \
  --handoff docs/frontend-vnext/fe4a-handoff-fix2.md \
  --git-objects --repo /home/dev/gateway-data-management-system \
  --sha-file /home/dev/gdds-fe-logs/fe4a-fix2/handoff-sources2.sha256 \
  --sha-file /home/dev/gdds-fe-shots/fe4a-fix2/full-run3.sha256 \
  --sha-file /home/dev/gdds-fe-shots/fe4a-fix2/full-run4.sha256 \
  --sha-file /home/dev/gdds-fe-shots/fe4a-review/fe3c-04-copy/shots.sha256 \
  --evidence-file /home/dev/gdds-fe-logs/fe4a-fix2/image-id.txt \
  --source-dir /home/dev/gdds-fe-shots/fe4a-fix2/full-run3 \
  --allow 3259501 --allow 7ea7df7c9d --allow 578e079b762e --allow 6dc9659f0aee \
  --self-log hex-handoff.log
```

结果：exit 0，`summary: 106 distinct full token(s); git=29 sha256=73 allowed=4 abnormal=0; 0 truncated form(s)`；日志 `/home/dev/gdds-fe-logs/fe4a-fix2/hex-handoff.log`，SHA256 `9ea2859354a351dd384e1e56aa740f56a9db0cc1075a99ce4bfa0007e2d58fa3`。
### 10.2 复审文档回归（旧启发式改写的正确文档）

在 07 运行：

```
python3 -I /home/dev/gdds-fe4a-impl/frontend/scripts/check-handoff-hex.py \
  --handoff /home/dev/gdds-fe-logs/fe4a-fix2/rereview-1.md \
  --git-objects --repo /home/dev/gateway-data-management-system \
  --sha-file /home/dev/gdds-fe-logs/fe4a-fix2/rereview-sources2.sha256 \
  --evidence-file /home/dev/gdds-fe-logs/fe4a-fix2/image-id.txt \
  --allow 3259501 --allow 578e079b762e --allow 6dc9659f0aee --allow 7ea7df7c9d
```

结果：exit 0，`summary: 73 distinct full token(s); git=29 sha256=40 allowed=4 abnormal=0; 1 truncated form(s)`；日志 `/home/dev/gdds-fe-logs/fe4a-fix2/hex-rereview2.log`，SHA256 `cead7ab6e20e6c664fbdc57dc5079258ec1549c33916750b3e4ded69965dad29`。

### 10.3 fix1 handoff §7 命令的复现问题（G4）

fix1 §7 的命令缺 `--evidence-file`，且把 `a2fb4a027a`、`bf792803a2`、`7ea7df7c9d` 放进 `--allow`；本文件 §10.1/§10.2 用完整参数重跑，提交号与树号均按 git 对象核对，未使用 `--allow` 放行任何 git 对象。

## 11. 已完成 / 未测 / 未决

**已完成**

- G1–G5、F10、F11（C12 五条规则）及 N5、N6、N7、N8、N10、N12。
- 07 上两次连续模拟接口全量（各 96/96，exit 0），`--stable` 第 ① 次 exit 0。
- 比较脚本节点复验四项全部符合预期；G3 探针 15 例全部符合预期。
- 归档 ref、fix1 树号更正、bundle 与 07 ref 更新（见 §12）。

**未测**

- 真实旅程、t1、`validate-upload-package.sh`：按任务约束本轮不跑。
- upload-mode 预览页截图不纳入规则 4 断言（§7.6），因此该页 1280 的 N5 溢出未在本轮修复。

**未决**

- N9：证据运行的 t1 要同时用新的 `--log-dir` 与 `--evidence-dir`。
- N11：关闭对话框输入仍可编辑，交 owner 看图确认。
- §7.6 的规则 4 偏离：预览页 N5 溢出随 FE4b 处理，请 owner 确认接受“本轮审核/归档截图全断言、预览截图除外”。
- C8 灰色冲突提示与红色集合变化提示同屏（`fe4a-c8-both-notices`）的视觉语义，请 owner 确认。

## 12. 交付物与保留物

- 代码候选与 handoff 提交见 §1；07 实施 worktree `/home/dev/gdds-fe4a-impl` 停在 handoff 提交且 clean。
- 代码 bundle：`/home/dev/fe4a-fix2-code3.bundle`（`fe-vnext`，含 `dd4ae6`，SHA256 `934de2a034e72f262cd773dc1d2de57e59a75174b28cdbe03c0c4efa4e1c2871`）。最终 handoff 提交另经 `/home/dev/fe4a-fix2-final.bundle` 传到 07；07 审核仓库 `refs/fe4a/fix2` 指向 handoff 提交。bundle 无法包含自身哈希，最终 bundle 的 SHA256 在交付回报中给出。
- 07 探针 worktree（保留，供复审）：`/home/dev/gdds-fe4a-fix2-probe-b4b`、`-probe-f3a`、`-probe-f3b`、`-probe-c12err`、`-probe-c12overflow`、`-probe-c12status`；临时脏 worktree `gdds-fe4a-fix2-probe-dirty` 与诊断 worktree `/home/dev/gdds-fe4a-w4diag` 已清理。
- 未删除审核会话的 `fe4a-review*`、`fe4a-rereview1*`、`fe4a-rr1-probe-*` worktree、日志与截图；`fe4a-rereview1/full1` 保留给复审第 2 轮。
