# FE4a 复审第 3 轮

- **复审对象：** fix3 区间 `919e22d4745b7238bf7f91e90fd587ed823dfa9e..59c5b8cfca0ae6d07a64a6a4e1645f724fa2ad1f`（5 个提交）。
  - 代码候选 `268b24f4b472c9846faaff25c29dd2c84a32833d`，`frontend/` 树 `802bdfb1a42b5319b483f3c4324d2b609a1b57b0`；
  - handoff 提交 `59c5b8cfca0ae6d07a64a6a4e1645f724fa2ad1f`（`refs/fe4a/fix3`）：相对候选只加 `docs/frontend-vnext/fe4a-handoff-fix3.md`，`frontend/` 树相同；
  - 开发主机上该提交在分支 `fe4a-fix3`；07 审核仓库的 `refs/fe4a/fix3` 指向同一提交，`main` 仍为 `16ffe72829`。
- **依据：** [复审第 2 轮](fe4a-rereview-2.md)（`ae0afdf9db`）§2.2–§2.5、§4 K1–K3、§5 N13–N18；[复审第 1 轮](fe4a-rereview-1.md)（`e903158bdb`）；[FE4 kickoff](../fe4-kickoff.md)（修订 4，main `0dd609ecff`）§3.8、§7.2、§7.3、§15.2、§15.4；fix2 handoff（`919e22d474`）与 `fe4a-handoff-fix3.md`。
- **复审会话：** FE4a 审核会话（会话名 `fe4a-rereview3`，本轮在新对话中承担审核会话角色，没有实施会话的上下文）。
- **日期：** 2026-11-10/11，07 上的运行与核对在 2026-11-10 23:39 至 2026-11-11 00:10 UTC 之间。
- **结论：通过。** K1–K3 与 N13 都已按第 2 轮 §4、§5 修复，复验符合：
  - K1：自检覆盖行过滤 0–4 并逐行全比；第 2 轮的 4 个变异现在都使 `--self-test` 失败；4 项节点复验输出与第 2 轮逐字节相同；
  - K2：规则 4 的断言已加到 `upload-mode.spec.ts`，只豁免 `fe3b-w4-approved-withdraw`；3 个失败探针（实施会话 2 个、本会话 1 个）都在预期位置失败，候选开截图全部通过；
  - K3：回源日志头有 UTC、handoff 所在工作区的 HEAD 与 handoff SHA256；P-H1–P-H7、H8、H8b 正反符合；逐字重跑与实施会话日志除开头字段外逐行相同；
  - 本会话独立全量通过；第 ② 次稳定性比较 exit 0；fix3 候选与 fix2 候选的截图之间没有内容变化，FE3c 非噪声集合不变。

  另有 4 条非阻塞（§5 N19–N22），其中 N20 涉及回源脚本对 fix3 handoff 的配对范围，本会话已人工补齐核对，不影响本轮结论。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| 提交链 | `919e22d474` → `e5f5af58c7`（K1）→ `d90eeccb9a`（K2）→ `268b24f4b4`（K3）→ `45e01f990d`（handoff 草稿 C0）→ `59c5b8cfca`（handoff），线性，每个提交只有一个父提交 |
| 各提交的 `:vnext` | 5 个提交都是树 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| 各提交的 `frontend/` 树 | `e5f5af58c7`：`f641a07c2b4ac738bf64ed368ef7bbfd2d792ee0`；`d90eeccb9a`：`be4cad7db39cca1e13bd51d647db5b0aa7d6a640`；`268b24f4b4`、`45e01f990d`、`59c5b8cfca`：`802bdfb1a42b5319b483f3c4324d2b609a1b57b0`，与 handoff §2 一致 |
| `git diff --name-only 919e22d474 59c5b8cfca` | 4 个路径：handoff、`frontend/e2e/upload-mode.spec.ts`、`frontend/scripts/check-handoff-hex.py`、`frontend/scripts/compare-screenshots.py`；没有可选 N14 的另两个 spec |
| `frontend/src/`、`e2e-real/`、`t1.spec.ts`、`run-real-backend-e2e.sh`、`validate-upload-package.sh`、`package*.json`、`openapi.json`、`generated/` | 无改动 |
| handoff §3 逐 hunk 清单 | 覆盖全部改动，没有未列出的改动。计数有两处小出入（N22） |

## 2. 独立运行、探针与核对

### 2.1 本会话的运行（07，`gw-dms-07.lan`）

§2 各表格中的相对路径都相对于 07 `/home/dev/gdds-fe-logs/fe4a-rereview3/`。

开始前 `ssh -o BatchMode=yes ct109-gw-dms-07 'echo OK'` 返回 `OK`，`/home/dev/gdds-node-busy.d` 不存在。新建 detached worktree `/home/dev/gdds-fe4a-rereview3`（`59c5b8cfca`，clean）。工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`（07 现场由 manifest 读出），7 个 RootFS DiffID 与 handoff §8.1 相同；npm 缓存归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`；`GATEWAY_FE_TEST_WORKERS=2`。

| 运行 | 提交 | 起止 | 结果 | 日志 | SHA256 |
| --- | --- | --- | --- | --- | --- |
| 模拟接口全量：候选 wrapper，入口 `run-tests.sh --e2e`，带 `--shots-dir` | `59c5b8cfca`（`frontend/` 树 `802bdfb1a4`），起止 clean | 23:39:36–23:42:18 | exit 0：类型检查、lint、构建通过；单测 35 个文件 214 项；Playwright 96 项，`e2e_workers=2`；198 张截图 | `fe4a-rereview3-run-tests-20261110T233936Z.log` | `a19258b42c300d2f3cf6c7f1f1a040c2ad8fc515c1e754f02a31f949179a28cd`（`.sha256` 旁注一致） |

截图在 07 `/home/dev/gdds-fe-shots/fe4a-rereview3/full1`，清单 `/home/dev/gdds-fe-logs/fe4a-rereview3/full1-shots.sha256` SHA256 `dd6892b7f5138ad4af636302c2543507fff9d532719774a161d3e5d11c38b621`（198 行，格式同第 2 轮）。

wrapper 记录的 `tracked_frontend_archive_sha256` 为 `9164890c2750e33be9a88c8def90d39d9be9aae5d900f8c379ba81d0634c564a`，实施会话两次全量为 `c7de453b43fd5b023f0715d3ea1755bb90b43f9afee5ba6216e86a4d6718d347`。两者 `frontend/` 树相同；差异来自 `git archive` 以提交时间作为文件时间：在 07 上对 `268b24f4b4` 与 `59c5b8cfca` 分别 `git archive ... frontend` 恰好得到这两个值。该值随提交变化，不能代替树号做身份比较（§7 第 3 项）。

### 2.2 K2 探针（07，均开截图，另有一个 N14 对照）

运行器 `/home/dev/gdds-fe-logs/fe4a-rereview3/run-probe.sh` SHA256 `ec301e151c677e18ad651a34ba1c6b319f3aed1c83d3902bca0ba4996cfa63dd`：由第 2 轮同名脚本只改会话名、日志目录与 `RR3_SHOTS`。批处理 `/home/dev/gdds-fe-logs/fe4a-rereview3/run-k2-probes.sh` SHA256 `53e8f034993ccdaa9be710d3d366dc6e3bd99b7f64906d19d765d43176c36f16`，输出 `/home/dev/gdds-fe-logs/fe4a-rereview3/run-k2-probes.out` SHA256 `6830713c5a5d3b6833692e612425fca96465685cce6c49c2da011f3d354472ee`。探针日志在 `/home/dev/gdds-fe-logs/fe4a-rereview3/probes/`。

本会话的操作错误：复制运行器时全局替换把第 2 行注释里的来源也改成了 `fe4a-rereview3`；第一个探针运行期间改正（只改该注释行，`sed -i` 生成新文件，不影响已在运行的进程）。上面的 SHA256 是改正后的文件；第一个探针用的是改正前的文件，两者只差该注释。

本会话补做的探针在开发主机一次性 worktree 中提交，ref `refs/review/fe4a-rr3/probe-exempt-other`，bundle `/home/dev/gdds-bundles/fe4a-rr3-probes.bundle` SHA256 `34d12344a7e9d125b332ac719f38af797be1bc55fed68c92f2be170d41314db0`（开发主机与 07 相同）。实施会话两个探针相对父提交 `268b24f4b4` 的差异已逐个核对，只含 handoff §5 所述的改动。

| 探针 | 提交 | 预期 | 结果 | 日志 | SHA256 |
| --- | --- | --- | --- | --- | --- |
| 实施：去掉豁免（开截图，`-g W4`） | `356e9e5a18e9e31621814e618368c1503ce60de6` | W4 失败 | **符合**：exit 1，`页面横向溢出：scrollWidth=1292 innerWidth=1280` | `probes/probe-impl-no-exemption-shots-20261110T234559Z.log` | `a44487e463b19755b6745ba13a2e2a16dc136c64aed90c26185e551890dd4f78` |
| 实施：W1 截图前设置 `minWidth=3000px`（开截图，`-g W1/W2`） | `837354330f01b4a6ee783c12aed38bedd5f9b206` | 断言失败 | **符合**：exit 1，`scrollWidth=3000 innerWidth=1920` | `probes/probe-impl-injected-overflow-shots-20261110T234610Z.log` | `f02d72d5ca3d323048790ee82802da63b1a8569819d6d5400496b956d3a8cff4` |
| 本会话：豁免名改成 `fe3b-w4-approved-upload`（开截图，`-g W4`） | `e497b755502c2c3af727d1559ba579ea6394d4de`（`frontend/` 树 `0a602adf3d58fee8f4ec4d68e64acd95f640dbba`） | W4 失败 | **符合**：exit 1，失败在 `upload-mode.spec.ts:297`（`fe3b-w4-approved-withdraw` 的截图调用），1292/1280；同一用例中改为豁免的 `approved-upload`（:292）通过 | `probes/probe-rr3-exempt-other-shots-20261110T234621Z.log` | `3dc07227da9d421f0abb757a914e7617d9e1e970b71cb9a0a424f8367f3dfdda` |
| 候选整份 `upload-mode.spec.ts`（开截图） | `59c5b8cfca` | 全部通过 | **符合**：18 passed | `probes/probe-rr3-candidate-upload-mode-shots-20261110T234632Z.log` | `47ae9a2db2e391384e4f2f0da73b4c7e6cd601e0071588a31483a1530698f0ee` |
| N14 对照：去掉豁免、**不开**截图 | `356e9e5a18` | W4 通过（断言不执行） | **符合**：1 passed | `probes/probe-impl-no-exemption-noshots-n14-20261110T234645Z.log` | `210ce1393ffc6ace25e8beb0b87b1c8030119d23506a4645995468e634110528` |

候选全量（§2.1）也开了截图，`upload-mode.spec.ts` 的用例全部通过。

### 2.3 截图比较脚本（K1）

脚本 `/home/dev/gdds-fe4a-rereview3/frontend/scripts/compare-screenshots.py` SHA256 `0887a45ecbac9c9d21ec5b0217859f05e565d0198068112cd4ddfcd03ec68eb8`（与 handoff §4 一致）。

**代码核对：** 自检改用 7×5 RGBA 渐变图，`make_png` 的 `y % 5` 使第 0–4 行分别用过滤 0–4；`decode_png` 返回每行过滤类型，自检断言为 `[0, 1, 2, 3, 4]`，逐行把解码结果与原像素全部比较，并断言第 1–4 行与上一行不同。渐变在 x、y 两个方向都变化，“左”“上”“左上”预测项都不为零。`classify`、`differing_pixels`、两个上限常量、`print_results` 与退出码未改；`decode_png` 返回值新增的 `filters` 只在自检中使用。N16：文件头改为“相同 = 解码后的像素完全相同”“尺寸不同 = 宽、高或通道数不同”“缺失 = 只在一侧存在”，与 `classify` 的实现一致。

**变异（07）：** `/home/dev/gdds-fe-logs/fe4a-rereview3/k1-mutants.sh`（SHA256 `4949f3fa59fb9df1f3b334e49ecbf96c78c6d20a6f4dba72b9cfaf58b1517994`）从 fix3 脚本重新生成变异：把 `unfilter_row` 中对应类型的整行赋值替换为 `output[index] = output[index] & 0xFF`，替换前断言原文只出现一次。输出 `/home/dev/gdds-fe-logs/fe4a-rereview3/k1-mutants.out` SHA256 `56ec8245ee67967c3d92a62b6aa0a5d708bb2fb22c3bc69d1492313b05fa5236`，文件在 `/home/dev/gdds-fe-logs/fe4a-rereview3/cmpmut/`。

| 变异 | `--self-test` | diff | diff SHA256 | 日志 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- |
| 原脚本 | exit 0 `self-test: ok` | — | — | `cmpmut/orig.log` | `b8ed9769688118577dab7a5190e37e97a8ed7e07ec11d37638e9d44b32c03672` |
| 类型 1 | **exit 1**：`row filter 1/2/3/4 pixels` | `cmpmut/mut-f1.diff` | `4e240e14861c201754d69dda168b3c72e7e0946e491d0afff7d5304d4ee11d2d` | `cmpmut/mut-f1.log` | `d71724498b96cd83040cf9174599ff4a2e6a25c708944d890fa5e3bf49706dbf` |
| 类型 2 | **exit 1**：`row filter 2/3/4 pixels` | `cmpmut/mut-f2.diff` | `586762862beffa3d52e6e982a22a0afa2ccbd51e95c857f7104d8441fcdca452` | `cmpmut/mut-f2.log` | `771076577d524edd03a39ea862aff841513bcf32e99b1d9dd9b782caad41c5a2` |
| 类型 3 | **exit 1**：`row filter 3/4 pixels` | `cmpmut/mut-f3.diff` | `3574d40e29013b68eff789eb9b720ae485436a69b7f86780a1e5f77e0a126e82` | `cmpmut/mut-f3.log` | `0670cec3d3b59b391920ee2222aae065ebfd5f1ae30605073168f93a7eddf837` |
| 类型 4 | **exit 1**：`row filter 4 pixels` | `cmpmut/mut-f4.diff` | `59e469250951c0247116a7a9aafca0d82f5cd515d91c307185b71b573d28c58a` | `cmpmut/mut-f4.log` | `9faf7c7dddd9d8ecebc2abb1bcf298236b908e92c41d2d5f67cdc3d36e57ef21` |
| 补充：`paeth()` 本身改为恒返回“左” | exit 0 `self-test: ok`（N19） | `cmpmut/mut-paeth.diff` | `63a40cad4e78df2695639109daa2bd7475a41af8555bb71b9e834bedd8daff6e` | `cmpmut/mut-paeth.log` | `b8ed9769688118577dab7a5190e37e97a8ed7e07ec11d37638e9d44b32c03672` |

4 个变异的输出与实施会话 handoff §4 的日志逐字节相同（SHA256 相同；本会话的变异写法带 `& 0xFF`，实施会话不带，两者等价）。补充变异中自检的编码器与解码器共用同一个 `paeth()`，所以自检看不出 `paeth()` 本身的错误；同一变异对 `fe4a-c4-h`/`fe4a-c4-i` 的 `--stable` exit 1（内容变化 12），真实截图会暴露它（`/home/dev/gdds-fe-logs/fe4a-rereview3/cmpmut/mut-paeth-h-vs-i.log` SHA256 `1da04c92e68bd3d88c7c2cbe9357a8ecef73f0031d5e5426f7031d95f340dfc8`）。

**节点复验（07，fix3 脚本）：** 批处理 `/home/dev/gdds-fe-logs/fe4a-rereview3/run-compares.sh` SHA256 `e36d55cf5b1f1cba44700f5f138b2c6c363f298b1a3882e8d04165e08fba25e3`，7 个比较并行，输出在 `/home/dev/gdds-fe-logs/fe4a-rereview3/cmp/`，汇总 `/home/dev/gdds-fe-logs/fe4a-rereview3/run-compares.out` SHA256 `0e4e6f27049eb9080a5675635d3a01dd667f0fe60547222ecacffac52ce4cc82`（汇总末尾多出一行空的 `rr2-vs-rr3.log` 与一条找不到 `.rc` 的报错：那是 §2.4 另起的比较，汇总时尚在运行，结果另见 §2.4）。

| 比较 | 结果 | 输出 | SHA256 |
| --- | --- | --- | --- |
| `--stable fe4a-c4-h fe4a-c4-i` | exit 0，`噪声=13 相同=177` | `cmp/h-vs-i.log` | `2d64e646fad40523f43dd8efd4a400b3d14350f210e81c7a111cba4414be080f` |
| `--stable fe4a-c4-h fe4a-review/full1` | exit 0，`噪声=24 相同=166` | `cmp/h-vs-r.log` | `79b41af696ad5f7c95c68afae6ca8008efc882dc6abff75685e70dd4003ea6a6` |
| `--stable fe4a-review/full1 fe4a-review/probe-srgb` | exit 0，`噪声=17 相同=173` | `cmp/r-vs-s.log` | `b2539801490472069f711332b8a5eb7a474ea6cc74ed6a4708fe2ca6f0c26a45` |
| 比较模式 `fe4a-review/fe3c-04-copy fe4a-review/full1` | exit 0，`内容变化=30 尺寸不同=2 缺失=0 噪声=7 相同=151` | `cmp/fe3c-vs-r.log` | `92375307e993ec8ebb61e8fa1fb4df61c812dce81a129c73901a9117f21feaf3` |

四项都与 kickoff §3.8 一致，且与第 2 轮 `recheck/` 的四个输出逐字节相同。判定仍按解码后像素，计数不变。

### 2.4 稳定性比较与看图清单

| 比较 | 结果 | 输出 | SHA256 |
| --- | --- | --- | --- |
| **第 ② 次**（kickoff §7.3）：实施会话第 ① 次中的第一次 `fe4a-fix3/full-run1` 与本会话 `fe4a-rereview3/full1`，同一 `frontend/` 树、同一节点，`--stable` | exit 0：`内容变化=0 尺寸不同=0 缺失=0 噪声=16 相同=182`；噪声每张最多 21 个像素、最大连通块 7 | `cmp/stable2-run1-vs-rr3.log` | `4d50bced0a8ae8547b278ceadac728a224e7c47b44265599cc5807d006e038b9` |
| 第 ① 次复核：`full-run1` 与 `full-run2`，`--stable` | exit 0，`噪声=15 相同=183`；噪声最大为 `history-compare-result-drawer-1280.png` 59 个像素、连通块 14，与 handoff §8.2 相同 | `cmp/stable1-run1-vs-run2.log` | `59edbeed8ef37c6b0e3083b91bcabf59f0067af2b064daa48decd416b4b6b254`，与实施会话 `/home/dev/gdds-fe-logs/fe4a-fix3/cmp-run1-vs-run2.log` 逐字节相同 |
| FE3c 证据截图副本 `fe4a-review/fe3c-04-copy` 与本会话 `full1`，比较模式 | exit 0：`内容变化=38 尺寸不同=4 缺失=8 噪声=10 相同=138` | `cmp/fe3c-vs-rr3.log` | `ba7019f61e124151cd4ae621b741264ddeac2850e660a1e1bf0760aa9b14c158` |
| 补充：第 2 轮候选（fix2）`fe4a-rereview2/full1` 与本会话 `full1`，`--stable` | exit 0：`内容变化=0 尺寸不同=0 缺失=0 噪声=13 相同=185`；噪声最多 21 个像素、连通块 6；按文件字节 185 张相同 | `cmp/rr2-vs-rr3.log` | `18ac2632ed4291054079667f7a992f52a8ae87a1ab9c69c805e1d85b00a84be2` |

FE3c 比较中 50 个非噪声文件（38 + 4 + 8，按“路径 + 类别”）与以下三份逐文件相同，只差噪声：

- fix2 `/home/dev/gdds-fe-logs/fe4a-fix2/cmp-fe3c-vs-run3.log` SHA256 `42c748aac23a21f8dc2962e53361985d7e397c88f4f2ce8bdd125cd75634720d`；
- 第 2 轮 `/home/dev/gdds-fe-logs/fe4a-rereview2/cmp-fe3c-vs-rr2.log` SHA256 `7ac16908f756ce14c87628145720d1315993180565dade5f90e3238fd2241de9`；
- 实施会话 fix3 `/home/dev/gdds-fe-logs/fe4a-fix3/cmp-fe3c-vs-run1.log` SHA256 `114c7fe7427dd43985dd5b9b9e74872d645dd2d0b366ea17b928c38dc51d03f2`。

K2 只在截图前加断言，没有改变任何截图；N14 未做。所以 fix2 handoff §6.4 的分组与第 2 轮的看图结论继续适用，不需要重新分组。

**看图（本会话）：** fix3 不改应用代码，fix2→fix3 的截图没有内容变化，因此只看了与 K2 直接相关的被豁免截图 `/home/dev/gdds-fe-shots/fe4a-rereview3/full1/1280/fe3b-w4-approved-withdraw.png` SHA256 `5e6974a9e13a657ed083b3f58b7d2071e50a75674bc7b02349aaf08ce7b551e4`。顶栏右侧“提交”按钮下的禁用原因“该提交已通过审核，归档或关闭后才能重新上传”超出视口，末尾被截断，与 N5 的描述一致。

### 2.5 回源脚本（K3）

候选脚本 `/home/dev/gdds-fe4a-rereview3/frontend/scripts/check-handoff-hex.py` SHA256 `fa6e20f45dc05370dc671f154cb540ed23d1222747f7f49322e2404dfe676efb`（与 handoff §6 一致）。

**代码核对：** `main()` 先打印 `utc`、`argv`、`hostname`、`cwd`、`handoff`、`handoff_HEAD`（`git -C <handoff 所在目录> rev-parse HEAD`，不在 git 工作区时写 `not a git worktree`）、`handoff_sha256`、`repo`、`repo_HEAD`。除了 `datetime` 导入与这几行输出，没有其他改动，核对、配对、对象类型与 `--allow` 逻辑未改。

**探针：** `/home/dev/gdds-fe-logs/fe4a-rereview3/hex-probes.sh` SHA256 `2f57cdaedc3d5190999d5eb0d326990ad429ecbfa7c3abf0ce865553ecb7df68`。它由第 2 轮同名脚本复制，改了 worktree、handoff、来源参数（按 handoff §9.1）与日志目录；被改一位的值从 fix3 handoff 重新选，并在运行前检查替换确实发生。输出 `/home/dev/gdds-fe-logs/fe4a-rereview3/hex-probes.out` SHA256 `0d1c12bab3964e6343184644c30a29293e4c159a528bcbe9cc73b879adf2cd5b`，各用例日志在 `/home/dev/gdds-fe-logs/fe4a-rereview3/hexprobe/`。

| 用例 | 预期 | 结果 |
| --- | --- | --- |
| H0：fix3 handoff，按 §9.1 的来源 | exit 0 | 符合：`70 distinct full token(s); git=18 sha256=52 allowed=0 abnormal=0`；日志头 `handoff_HEAD: 59c5b8cfca0ae6d07a64a6a4e1645f724fa2ad1f`，`handoff_sha256: 94ca2375dc1b0d28c902c889293384688ba82c90c110358c84dbf2a7312cdbc9` |
| P-H1：§5 探针日志的 64 位值改一位 | exit 1 | 符合：`unverified sha256` |
| P-H4：8 位提交号 `268b24f4` 改一位；另把 40 位 K1 提交号改一位 | 都 exit 1 | 符合：都报 `unresolved git object` |
| P-H5：§7 “`frontend/` 树”后的树号换成提交号 `5a1f32bf5e` | exit 1 | 符合：`object type mismatch ... handoff says tree, git says commit` |
| P-H2（真实表格）：§8.1 wrapper 日志行把第一次的 SHA 换成第二次的 | exit 1 | **不符合，exit 0**：该行的写法 `` `路径`，SHA256 `值` `` 不在脚本支持的两种配对形态内，见 N20。脚本逻辑与 fix2 相同，不是 fix3 引入的；本会话已对 handoff 中全部 52 个 SHA256 人工核对配对（§3.3） |
| P-H3：不给 SHA 来源；不给 `--git-objects` | 都 exit 1 | 符合 |
| P-H2、P-H6（合成）：表格与正文两对，正确与互换；`--sha-file` 来源正确与互换 | 正 0、负 1 | 符合 |
| P-H7：只含 63、39、13 位值的副本 | 都 exit 1 | 符合：都报 `abnormal length` |
| H8：把 handoff 自记的 L0 哈希改一位 | exit 0（按设计跳过） | 符合 |
| H8b：同一行同时含自记日志名与另一张截图的错误 SHA | exit 1 | 符合：`pairing mismatch` |

**逐字重跑：** `/home/dev/gdds-fe-logs/fe4a-rereview3/k3-verbatim.sh`（SHA256 `151075d7d87dd8937f2a0c563d5bf38edfba0efb10b9a43a4a320d9d7ad36f87`）在 `/home/dev/gdds-fe4a-impl`（HEAD `59c5b8cfca`，clean）逐字执行 handoff §9.1 的命令，只把输出重定向到本会话目录，避免覆盖实施会话日志。输出 `/home/dev/gdds-fe-logs/fe4a-rereview3/k3-verbatim.out` SHA256 `2ad1ecbf1da1394a69783a98a2c8acfc5f95d134aeb30dbd2d9a2f1de1a7ced5`。

- 重跑 exit 0，日志 `/home/dev/gdds-fe-logs/fe4a-rereview3/k3/hex-handoff-final-rr3.log` SHA256 `cde796477947cb7ead0319982175f3b9cfe1102953bc518990736d54c4a12d0a`；开头 9 行中只有 `utc` 与实施会话 L1 不同，第 10 行起与 L1 逐行相同；
- 实施会话 L1 `/home/dev/gdds-fe-logs/fe4a-fix3/hex-handoff-final.log` SHA256 `504cfdb2a55ae684346a853d619373782a23af98c7f4bfe0e0db7b3c6c517cf6`（现场重算），与实施回报一致；
- handoff 自记的 L0 `/home/dev/gdds-fe-logs/fe4a-fix3/hex-handoff.log` SHA256 `496e922edec4baaafbb76cb6bc6e28170e77fcccb76da6f6f53c827d5e548bfa`（现场重算），与 §9.2 相同；L0 头为 `handoff_HEAD: 45e01f990d2c3ae580681e258d4253e26f9b5498`（C0）、`handoff_sha256: 8063150fe5fcad2566516e201c9ddc11b69963c156a6f8e4f77cfcd80058a0b0`；
- C0 中 handoff 文件的 SHA256 与 `/home/dev/gdds-fe-logs/fe4a-fix3/fe4a-handoff-fix3-H0.md` 都是 `8063150fe5fcad2566516e201c9ddc11b69963c156a6f8e4f77cfcd80058a0b0`，与 §9.2 相同。handoff §6.1 的自引用处理成立。

## 3. 逐项核对

### 3.1 K1–K3、N13

| # | 结论 | 说明 |
| --- | --- | --- |
| K1 | 符合 | 过滤 0–4 各一行、与上一行不同、逐行全比；4 个变异都使自检失败；判定、上限、输出格式未改；节点复验 4 项与第 2 轮逐字节相同。`paeth()` 本身的错误自检看不出（N19，非阻塞） |
| K2 | 符合 | 断言在截图 helper 内、`settleAfterResize()` 之后、`page.screenshot()` 之前；只豁免 `fe3b-w4-approved-withdraw` 一个名字，按名字全等比较，有 N5/FE4b 注释；预览页顶栏与样式未改；handoff §5 写明 1280 与 1920 都溢出 12 px。3 个失败探针与候选通过都符合（§2.2）。N14 未做，断言只在开截图时执行，已由对照探针确认 |
| K3 | 符合 | 日志头字段齐全，`handoff_HEAD` 等于被核对 handoff 所在提交，`repo_HEAD` 单独标注；逐字重跑除开头字段外逐行相同；正反用例除 P-H2 真实表格外都符合，P-H2 的偏差来自既有配对范围（N20） |
| N13 | 符合 | 07 `refs/review/fe4a-fix2/probe-c12-error-in-row` → `5a1f32bf5e6f60fe239d73b4c0a7577c4bd304c4`；`probe-c12-overflow-only` 仍为 `6c2ddb7097c93ca9be0431b2587b0e3a874c885f` |

### 3.2 N16、N18

- **N16：** 选择改说明、不改实现。说明与 `classify` 一致，§3.8 字面的“字节相同”改为“解码后像素相同”，对稳定性判定没有影响。按 §7.3 的写法，“相同”与“噪声”都不算变化，可以接受。
- **N18：** handoff §5 与 `upload-mode.spec.ts` 的注释都写明 1280 与 1920 都溢出 12 px，符合。

### 3.3 handoff 中 SHA256 的配对（人工补核）

fix3 handoff 中的路径与哈希基本写成 `` `路径`，SHA256 `值` ``，回源脚本只对其中 1 处（npm 缓存归档）做了路径配对，fix2 的 handoff 为 52 处（N20）。本会话把 handoff 中全部 52 个 SHA256 逐个对应到来源，并按所在行的含义核对：

- 来源清单 `/home/dev/gdds-fe-logs/fe4a-fix3/handoff-sources.sha256` 的 56 个文件项在 07 现场 `sha256sum -c` 全部一致；
- 13 个标签项逐个现场重算：两个脚本的 SHA256 由 `268b24f4b4` 的 blob 算出；config digest 与 7 个 DiffID 由 07 上镜像的 manifest 读出；`handoff-draft-H0` 由 C0 的 blob 算出；`handoff-log-L0` 由文件算出；`frontend-tracked-archive` 由 `268b24f4b4` 的 `git archive` 算出。都与 handoff 一致；
- 每个值所在的行与其来源文件对应正确：§4 变异表的三列分别为 diff、日志与变异脚本；§5、§6 表的日志与用例名对应；§8.1 两列分别为第一次与第二次。

没有发现配对错误。

## 4. 需要修复（阻塞）

无。

## 5. 非阻塞

- **N19 自检对 Paeth 预测函数本身没有区分力：** `make_png` 与解码器共用 `paeth()`，把它改错时编码、解码一起错，自检仍报 `ok`（§2.3）。节点上的真实截图比较会暴露（补充变异使 H/I 比较出现 12 个内容变化），因此不阻塞。FE4b 沿用该脚本时可以考虑：在自检中写入一段固定的已知编码字节，或给编码器单独实现预测函数。
- **N20 回源脚本不配对 `` `路径`，SHA256 `值` ``：** `SHA_PAIR_RE` 要求路径与 `SHA256` 之间只有空白，表格单元格内同时含路径与哈希时也不算路径单元格。fix3 handoff 几乎全用带逗号的写法，所以脚本只核对了“值是否出现在来源清单中”，没有核对“值是否属于这一行写的文件”；P-H2 真实表格用例因此 exit 0。另外，来源清单中的 13 个标签项（如 `handoff-log-L0`、`toolchain-rootfs-diffid`）没有绑定文件或命令输出，作用接近 `--allow`。本会话已人工补核（§3.3），本轮不需要修改。FE4b 沿用时二选一：让正则接受 `，`/`,` 分隔与单元格内的路径，或在 handoff 中改用脚本支持的两种写法；标签项改为可复算的证据文件，经 `--evidence-file` 提供。
- **N21 handoff 文字小误：** §4 变异表把类型 3 写成“up-left 平均”，实际是左与上的平均；§6 表 “P-H1 改错一位” 的结果写成 `pairing mismatch`，实施会话日志 `/home/dev/gdds-fe-logs/fe4a-fix3/hex-probes3/ph1-bad.log` 实际为 `unverified sha256`（exit 1 正确）。
- **N22 逐 hunk 计数：** handoff §3 写 `check-handoff-hex.py` +9/−1、`compare-screenshots.py` +28/−7 且有三个 hunk；`git diff --numstat` 为 +8/−1 与 +21/−7，比较脚本按默认上下文有 4 个 hunk（`decode_png` 的两处分开）。各项内容都已列出。
- **沿用：** N14（可选，未做）、N15、N17 同第 2 轮；N11 交 owner。

## 6. 交 owner 确认（汇总，不阻塞本轮）

- 规则 4 的唯一豁免 `fe3b-w4-approved-withdraw`（1280、1920 都溢出 12 px，禁用原因文字被截断，随 FE4b 的 N5 处理）；
- C8 灰色冲突提示与红色集合变化提示同屏的颜色（`fe4a-c8-both-notices`，kickoff §15.3）；
- N11（关闭成功后输入仍可编辑）；
- N15（“收起”位置）；
- 看图以复审通过的候选在 07 上的截图为准：本会话 `/home/dev/gdds-fe-shots/fe4a-rereview3/full1`（清单 SHA256 见 §2.1），或实施会话 `/home/dev/gdds-fe-shots/fe4a-fix3/full-run1`（清单 `/home/dev/gdds-fe-shots/fe4a-fix3/full-run1/shots.sha256` SHA256 `50cc7a977b05ab508bd9958ccdcf47c646b2f42eb945753f7e800304de9ce994`）。两者与 fix2 候选的截图之间没有内容变化，分组以 fix2 handoff §6.4 为准。

## 7. 下一步

1. **证据项不变：** 审核报告 §8 第 3 项与 kickoff §7.2 FE4a 证据行。在最终候选（`frontend/` 树 `802bdfb1a42b5319b483f3c4324d2b609a1b57b0`）的 clean、已提交 detached worktree 上各运行一次：04 `run-tests.sh --e2e --screenshots`、`validate-upload-package.sh`、`--suite journeys`（完整集 20 个 scope）、05 `--suite t1`。
2. **05 的 t1：** 同时使用新的 `--log-dir` 与 `--evidence-dir`（N9）。
3. **第 ③ 次稳定性比较：** 证据运行后，由审核会话把 04 证据截图与本轮通过的候选在 07 上的截图（本会话 `full1` 或实施会话 `full-run1`）用 `--stable` 比较。两者的 `frontend/` 树必须相同，按树号核对；wrapper 记录的 `tracked_frontend_archive_sha256` 随提交时间变化，不作判据（§2.1）。
4. 审核会话核对证据日志后，FE4a 进入退出流程。

## 8. 本会话的遗留

- **开发主机：**
  - `refs/review/fe4a-rr3/probe-exempt-other`；
  - bundle `/home/dev/gdds-bundles/fe4a-rr3-probes.bundle` 与 `/home/dev/gdds-bundles/fe4a-rr3-reviewdocs.bundle`（后者是 `fe4a-review` 分支 `e903158bdb..ae0afdf9db`，供 07 回源本报告，SHA256 `279ba6c2612a6a822f67ee919c95dcbd5c874999b010a42ee9dc3e087a363936`）；
  - 临时 worktree `/home/dev/gdds-fe4a-rr3-probes` 已删除；
  - 本报告提交在短分支 `fe4a-review`，随 FE4a 退出合入 main。
- **07：**
  - `refs/review/fe4a-rr3/probe-exempt-other`、`refs/fe4a/hex-src/fe4a-review-rr3`（→ `ae0afdf9db`；第 2 轮的 `refs/fe4a/hex-src/fe4a-review` 未动）；
  - worktree `/home/dev/gdds-fe4a-rereview3` 与 `/home/dev/gdds-fe4a-rr3-probe-exempt-other`；
  - 日志 `/home/dev/gdds-fe-logs/fe4a-rereview3/`，截图 `/home/dev/gdds-fe-shots/fe4a-rereview3/full1`；
  - 两个 bundle 的副本在 `/home/dev/gdds-bundles/`。

  保留到 FE4a 退出。
- 实施会话与前几轮审核会话的 worktree、ref、日志与截图未改动。07 上没有本会话留下的占用标记。本会话没有在开发主机上运行测试，没有推送，没有改 `fe-vnext`。

## 9. 本报告的回源

在 07 上用候选的回源脚本核对本报告，在 `/home/dev/gdds-fe4a-rereview3` 中运行，`--repo /home/dev/gateway-data-management-system`；07 上有 fix3 全部提交、实施会话与本会话的探针提交，以及经上面 bundle 取得的 `ae0afdf9db`。来源：

- 07 现场重算的清单 `/home/dev/gdds-fe-logs/fe4a-rereview3/report-sources-07.sha256`（SHA256 `bf6f1aaedd3f16e3c65dd97873ddb262bbd97fe07d8d6d109d8d3fc411e909ac`），另有记录该清单哈希的旁注文件作为第二个 `--sha-file`。清单覆盖本会话全部日志、脚本、输出与截图清单，07 上的两个 bundle，fix3 日志目录的全部文件，本报告引用的 fix2、第 2 轮日志与截图清单，被豁免的截图、npm 缓存归档、两个候选脚本与 fix3 handoff；
- 证据文件 `/home/dev/gdds-fe-logs/fe4a-rereview3/report-evidence-07.txt`（`--evidence-file`）：由命令现场写出 07 上工具链镜像 manifest 的 config digest 与层（即 DiffID），以及 `268b24f4b4`、`59c5b8cfca` 两个提交 `git archive ... frontend` 的 SHA256；
- 本会话全量的 wrapper 日志（`--evidence-file`）；
- `--source-dir /home/dev/gdds-fe-logs/fe4a-rereview3`，用于表格中相对路径的现场配对。

没有使用 `--allow`。

结果：exit 0，`84 distinct full token(s); git=28 sha256=56 allowed=0 abnormal=0; 0 truncated form(s)`；其中 48 处路径与 SHA256 的配对按现场文件或来源清单核对通过。反例：把 §2.3 变异表类型 1 的日志 SHA256 换成类型 2 的，exit 1，报 `pairing mismatch`（`neg-swap.log`）。输入副本不在 git 工作区，日志头的 `handoff_HEAD` 为 `not a git worktree`；副本与提交的报告逐字节相同。命令、输入副本与输出在 07 `/home/dev/gdds-fe-logs/fe4a-rereview3/report-hex-input/`（输出 `hex-report.log`；其哈希不写入本报告，避免自引用）。
