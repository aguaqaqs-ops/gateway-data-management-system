# FE4a 复审第 2 轮

- **复审对象：** 分支 `fe-vnext`，fix2 区间 `c6656ce5e4..919e22d474`（4 个提交）。
  - 代码候选提交 `dd4ae64611cbd51aebdb4d7ad3326c3df8b44bc4`，`frontend/` 树 `e2f0a80fd5f7497071d149c376f673b19ac5be73`；
  - handoff 提交 `919e22d4745b7238bf7f91e90fd587ed823dfa9e`：只新增 `docs/frontend-vnext/fe4a-handoff-fix2.md`，`frontend/` 树与候选相同；
  - 07 上用最终 bundle `/home/dev/fe4a-fix2-final.bundle`（开发主机现场 SHA256 `0e130c80e1289899d26d8d8c6415cd005afffb0a51a4e704f2b8dc29342ff5ee`）取得的 `refs/fe4a/fix2`，与开发主机 `fe-vnext` 一致。
- **依据：** [复审第 1 轮](fe4a-rereview-1.md)（`e903158bdb`）§4 G1–G5、§5 N5–N12；[FE4 kickoff](../fe4-kickoff.md)（修订 4，main `0dd609ecff`）§3.8、§7.3、§15.2、§15.4；`fe4a-handoff-fix2.md`。
- **复审会话：** FE4a 审核会话（会话名 `fe4a-rereview2`，本轮在新对话中承担审核会话角色，没有实施会话的上下文）。
- **日期：** 2026-11-10（时间均为 UTC）。
- **结论：定向修复。** 产品代码全部符合：G1 恢复了“一次加载”的重读结果，G2 两条 C8 用例有区分力，C12 五条规则都有能区分的用例；本会话独立全量通过，第 ② 次稳定性比较 exit 0；看图清单由脚本生成，与本会话的比较结果逐文件一致；回源脚本 P-H1–P-H7 正反都符合。需要修复后再复审（§4 K1–K3，都只涉及工具与测试范围，不改应用代码）：
  - 截图比较脚本的 `--self-test` 只核对了行过滤类型 1；把解码器中类型 2、3、4 的预测去掉，自检仍报 `ok`（K1）；
  - 规则 4 的偏离可以缩小：`upload-mode.spec.ts` 的 27 个截图名中只有 `fe3b-w4-approved-withdraw` 溢出（1280、1920 两种宽度都溢出 12 px），实施会话把整份用例都排除在断言之外（K2）；
  - 回源脚本日志开头的 HEAD 是 `--repo` 主检出的 HEAD（07 上为 `16ffe72829`），不是被核对 handoff 所在的提交，也没有时间（K3，G4 的遗留）。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| `c6656ce5e4` 的 4 个后续提交 `d9fc3b3d56`、`0853e2a96c`、`dd4ae64611`、`919e22d474` 的 `:vnext` | 都是树 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| 提交链 | `c6656ce5e4` → `d9fc3b3d56` → `0853e2a96c` → `dd4ae64611` → `919e22d474`，线性；各提交的 `frontend/` 树与 handoff §1 一致 |
| `git diff --name-only c6656ce5e4 919e22d474` | 11 个文件：`frontend/` 10 个、handoff 1 个，与 handoff §1 列表相同 |
| `e2e-real/`、`t1.spec.ts`、`run-real-backend-e2e.sh`、`validate-upload-package.sh`、`upload-mode.spec.ts`、`package*.json`、`openapi.json`、`generated/` | 无改动 |
| 打包流程筛查（kickoff §7.4 第 1 步）：`upload-package.ts`、`UploadStepCard.tsx` | 为空：不触发 t4 |
| 归档 ref `refs/archive/fe4a/probe-c2-selfcheck` | 开发主机指向 `bf792803a212af955c2da457781b9608864ef335`，其 `frontend/` 树为 `7ea7df7c48b0c6c14757882ba6e4d3abe92dd147`，与 handoff §5 更正一致 |

handoff §9 的逐 hunk 清单覆盖了本轮全部改动，没有未列出的改动。

## 2. 独立运行、探针与核对

### 2.1 本会话的运行（07，`gw-dms-07.lan`）

新建 detached worktree `/home/dev/gdds-fe4a-rereview2`（`919e22d474`，clean）。工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`（config digest 与审核报告相同），npm 缓存归档 SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，`GATEWAY_FE_TEST_WORKERS=2`。运行前后节点上没有其他占用标记。

| 运行 | 提交 | 起止 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| 模拟接口全量：候选 wrapper，入口 `run-tests.sh --e2e`，带 `--shots-dir` | 提交 `919e22d474`（前端树 `e2f0a80fd5`），起止 clean | 16:42:26–16:45:09 | exit 0：类型检查、lint、构建通过；单测 35 个文件 214 项；Playwright 96 项，`e2e_workers=2`；198 张截图 | `fe4a-rereview2-run-tests-20261110T164226Z.log` `9bf41e780934cad577117b49a4774d3e580011e67a8fb0ee14f0af4d969c4537`（`.sha256` 旁注一致） |

截图在 07 `/home/dev/gdds-fe-shots/fe4a-rereview2/full1`，清单 `/home/dev/gdds-fe-logs/fe4a-rereview2/full1-shots.sha256`，SHA256 `4a4a600089f4f4030cd98af9b52dcfbeba51eb7f20d42c23e3abe0b507d4807e`。

### 2.2 代码探针（07）

探针由 `/home/dev/gdds-fe-logs/fe4a-rereview2/run-probe.sh`（SHA256 `2060ed9c19791a390f1f1159d4da1c2e1c219db00be06646da1e15ead04e32a8`）运行：在复审第 1 轮的同名脚本上只改会话名、日志目录，并在设置 `RR2_SHOTS` 时给容器传 `GATEWAY_FE_SCREENSHOT_DIR`。批处理脚本 `run-all-probes.sh`（SHA256 `11bfd162ce84fdc1ef8013d628ee1c6499246b6b2a509086c57f2a9ec4bfec4e`）与 `run-shot-probes.sh`（SHA256 `bf0436f4c3a1703e62528107f3004fac52ed0245bcd5c39c4abd0ed17a9cc4f5`，开截图重跑 C12 布局探针）。日志都在 `/home/dev/gdds-fe-logs/fe4a-rereview2/probes/`。

`run-all-probes.sh` 的第一次运行因本会话脚本的错误（`run` 函数没有调用探针脚本）在任何探针运行前退出，没有副作用（输出 `run-all-probes-attempt1-scripterror.out`，SHA256 `e3ff5997e95615c9e065bf849e2b7bf4b8a56e00c780ac2a7fdaf2d34152a7e5`）；修正后重做一次，结果见下表。

实施会话的探针（先逐个核对了与父提交的差异，都只含 handoff 所述的一处回退）：

| 探针 | 提交 | 预期 | 结果 |
| --- | --- | --- | --- |
| G1：去掉 `loaded = reloaded;` | `86e000aff3a37163ffa9dbf7c6d826718b34e330` | B4b 失败，B4 通过 | **符合**：B4b 失败在“已有提交正在处理”应为 0 处（收到 1）；B4 通过 |
| G2a：去掉集合未变时的 `setCollectionNotice(null)` | `b96dce492f04651fc4a267c855e41fc946d3397c` | 只有“集合未变”用例失败 | **符合**：`:558` 失败（收到 1），C8 其余 3 条通过 |
| G2b：去掉加载失败时的 `pendingNotice.current = null` | `66dd4d5da6e1f1aaf3c10a976c9951d4cd25d033` | 只有“409 后重新预检失败”用例失败 | **符合**：`:603` 失败（收到 1），其余 3 条通过 |
| C12 规则 1：错误提示放回按钮行 | `5a1f32bf5e6f60fe239d73b4c0a7577c4bd304c4` | V11、V12 失败 | **符合**：两条都失败在错误不在 `.compare-header__notice`；开、关截图两种运行结果相同 |
| C12 规则 4：同上，并去掉 4 条结构断言 | `6c2ddb7097c93ca9be0431b2587b0e3a874c885f` | 横向溢出断言失败 | **符合（需开截图）**：开截图时 V11 报 `页面横向溢出：scrollWidth=1509 innerWidth=1280`；不开截图时 V11 失败在面包屑不可见（N14） |
| C12 规则 5：V12 重读状态改回 PENDING | `5364f70c51b7c88bc5d8c897b4444792d4326fc9` | V12 失败 | **符合**：找不到“审核：已通过” |

探针日志 SHA256（按上表顺序；“开截图”为 `RR2_SHOTS=1` 的重跑）：G1 `00b51bc9114a4bec8c503e6781dd15f481ac44e6180765da1aefa0db95cebe63`；G2a `b45d4762a92863a889852915d34cba98cf3efd99a615d2676cf413fc3172d7fd`；G2b `873c601d77c8a5e1d24641add695244fb9d8add0a307202e03f0143d0eb54a9a`；规则 1 `56560eccb8e75b19368cbd719a0da6337d9035f620f13c4752f1290afa539e2d`、开截图 `bd3c7bb8619f8298b95c416c416d35439a5bcc9ccbee43e472df4ad2092a6e9e`；规则 4 `949c1a82eeae4551d75d8570aa7b103c16e948792f0c71c7a12b79f36f005ae3`、开截图 `68946195493a50cfcd3ce1095381328d691a9816ec9b1d4b4d80830be72bd74f`；规则 5 `ebf9106105da8be2857e7239b81e94213d23759a6eaf19f29ecfe3e078eb2ae6`。

本会话补做的探针（开发主机构造，ref `refs/review/fe4a-rr2/probe-*`，bundle `/home/dev/gdds-bundles/fe4a-rr2-probes.bundle` SHA256 `2159c47efd2e5c7ef3607843f5aab30739b8add05deae5cd587b27928f55c4f1` 传到 07）：

| 探针 | 提交 | 预期 | 结果 |
| --- | --- | --- | --- |
| P-R2：处置说明放回顶栏主行网格（回退规则 2） | `a4cbbc3787a03cf55b5b109074829062aba53680` | V12 失败 | **符合**：“返回工作台”宽度期望 97、实得 209.25；开、关截图结果相同 |
| P-R3：三个按钮各自显示原因（回退规则 3） | `d4f8c00a16c1008064c1210f9e12e681de8fafec` | V12 失败 | **符合**：原因出现 3 次（期望 1） |
| P-U：`upload-mode.spec.ts` 每次截图前记录 `scrollWidth`（不失败） | `06a357dec34c65891b353724f30caea0377c1f85` | 列出溢出的截图 | 18 项通过；54 次截图（27 个名字 × 2 种宽度）中只有 `fe3b-w4-approved-withdraw` 溢出：1280 下 1292、1920 下 1932（K2） |
| 候选 V11、V12（开截图） | `919e22d474` | 通过 | 2 项通过 |

探针日志 SHA256：P-R2 `1616213acab17f3693af0632f47521d57b7bbc4966251e8de192ac8c230c375d`、开截图 `3996abc608a3c1b688f13d60f70e99b27bae1854f26c686b23d3aec849a7968b`；P-R3 `f7843b93faaad296717116a7d6469fbe1332579af112a609e35a1c9c84c25d78`、开截图 `209748faf3d3f085da91a2e4cffe6650fa196a78df43c460df4f66062cc68d5e`；P-U `f02362c68c1b514362a45806f1c6c75ae838a05690ff3f76eee4fa37f0c09cb4`；候选 `b2cbbd5a1b1fff334f66e2285c2f7c7871f1ee1e16be7f3d316f8a3e7d937944`。

### 2.3 截图比较脚本

脚本 `/home/dev/gdds-fe4a-rereview2/frontend/scripts/compare-screenshots.py`，SHA256 `8ada2e159a4f451ac065bb9d7ed77c29113f134b46f06ba2a7efcbd6fc7ae85e`。

**代码核对：** 两个上限是模块常量，没有参数或环境变量入口；判定顺序、8 邻接连通块、输出格式、排序与两种模式的退出码符合 §3.8。两处与说明不一致，不影响结果（N16）。

**自检：** `--self-test` 输出 `self-test: ok`。变异探针（`/home/dev/gdds-fe-logs/fe4a-rereview2/cmpmut/`，汇总 `summary.txt` SHA256 `b47a89811f698229cda978d95c18980b4b7e9525bf4efb90fbaf5f555e566a80`）：分别把解码器中过滤类型 1–4 的预测项去掉：

| 变异 | `--self-test` | 对 `fe4a-c4-h`/`fe4a-c4-i` 的 `--stable` |
| --- | --- | --- |
| 类型 1 | exit 1 `row filter 1` | 未运行 |
| 类型 2 | **exit 0 `ok`** | 内容变化 9（原脚本为 0） |
| 类型 3 | **exit 0 `ok`** | 内容变化 2 |
| 类型 4 | **exit 0 `ok`** | 内容变化 1 |

自检用 6×6 图像轮流使用 5 种过滤类型编码，但只比较了第 1 行一个像素（类型 1）；类型 2–4 的行没有被检查。节点上的真实截图能暴露这类错误，但自检是 FE4b 沿用该脚本时的回归保护，kickoff §3.8 明确要求覆盖 5 种过滤类型，handoff §6.1 也写了“5 种 PNG 行过滤器”（K1）。

**节点复验（本会话重跑，07）：** 输出在 `/home/dev/gdds-fe-logs/fe4a-rereview2/recheck/`。

| 比较 | 本会话结果 | 输出 SHA256 |
| --- | --- | --- |
| H/I：`--stable fe4a-c4-h fe4a-c4-i` | exit 0，`噪声=13 相同=177` | `h-vs-i.log` `2d64e646fad40523f43dd8efd4a400b3d14350f210e81c7a111cba4414be080f` |
| H/R：`--stable fe4a-c4-h fe4a-review/full1` | exit 0，`噪声=24 相同=166` | `h-vs-r.log` `79b41af696ad5f7c95c68afae6ca8008efc882dc6abff75685e70dd4003ea6a6` |
| R/S：`--stable fe4a-review/full1 fe4a-review/probe-srgb` | exit 0，`噪声=17 相同=173` | `r-vs-s.log` `b2539801490472069f711332b8a5eb7a474ea6cc74ed6a4708fe2ca6f0c26a45` |
| 比较模式：`fe4a-review/fe3c-04-copy fe4a-review/full1` | exit 0，`内容变化=30 尺寸不同=2 缺失=0 噪声=7 相同=151` | `fe3c-vs-r.log` `92375307e993ec8ebb61e8fa1fb4df61c812dce81a129c73901a9117f21feaf3` |

四项都与 kickoff §3.8 的预期一致，输出与 handoff §6.2 记录的四个日志逐字节相同（SHA256 相同）。

### 2.4 稳定性比较与看图清单

| 比较 | 结果 | 输出 SHA256 |
| --- | --- | --- |
| **第 ② 次**（kickoff §7.3）：实施会话第 ① 次中的第一次 `fe4a-fix2/full-run3` 与本会话 `fe4a-rereview2/full1`，同一提交树、同一节点，`--stable` | exit 0：`内容变化=0 尺寸不同=0 缺失=0 噪声=8 相同=190`；噪声每张最多 21 个像素、最大连通块 7 | `cmp-run3-vs-rr2.log` `659981f3f9ec0ec4516146348e1552414d2da4dc69d85d00c645de98170eba46` |
| 第 ① 次复核：`full-run3` 与 `full-run4`，`--stable` | exit 0，`内容变化=0 尺寸不同=0 缺失=0 噪声=20 相同=178`，与 handoff §6.3 相同 | `run3-vs-run4.log` `8fe31aeae7bcafb92740713840ffa58e82da8bf88b102b9020b189d21a5f0a3f`（与实施会话日志逐字节相同） |
| FE3c 证据截图副本（`fe4a-review/fe3c-04-copy`）与本会话 `full1`，比较模式 | exit 0：`内容变化=38 尺寸不同=4 缺失=8 噪声=6 相同=142` | `cmp-fe3c-vs-rr2.log` `7ac16908f756ce14c87628145720d1315993180565dade5f90e3238fd2241de9` |

FE3c 比较中 50 个非噪声文件（38 + 4 + 8）与实施会话 `cmp-fe3c-vs-run3.log`（SHA256 `42c748aac23a21f8dc2962e53361985d7e397c88f4f2ce8bdd125cd75634720d`）逐文件相同，两者只差一张噪声；handoff §6.4 各分组表中的 50 个文件名与这 50 个文件完全相同，没有遗漏或多出。逐组核对原因：

- C3 16 张、C4 固定时长 8 张、C4 helper 2 张、C9 4 张与审核报告、复审第 1 轮的归因一致；
- `1280/fe3b-w6-preview-resumed-card` 与 `1280/fe3b-w6-withdraw-busy`（1920 同）在 FE4a 中逐字节相同：两张拍的是同一状态，FE3c 中不同只是因为等待时长文字不同，C4 固定时钟后相同，符合预期；
- C12 10 张：`fe3b-d1/d2/d3-review-topbar` 两种宽度，`fe3c-review-closed/expired` 两种宽度尺寸不同（高度增加，宽度都等于视口），与规则 1、2、3 对应；
- F2 + N6 2 张、C6/C8/D3 新增 8 张（缺失）对应正确。

**看图（本会话）：**

- `fe3c-review-closed-1280`：顶栏主行为“返回工作台”、完整面包屑、审核、已连接、“审核：已通过”“已关闭（未归档）”与三个禁用按钮；“该提交已关闭（未归档）”在按钮组下方只出现一次；下面依次是处置说明（关闭人、时间、“查看关闭理由”）与红色错误框“该提交已归档或关闭，已重新读取”。符合规则 1、2、3、5。
- `fe3c-review-expired-1280`：错误框在顶栏主行下方占满宽度；撤回、退回可用，审核通过的原因单独显示在其下方。符合规则 1、3。
- `1280/fe3b-d2-review-topbar`：原因只显示一次。按钮组贴近顶栏上缘，与 FE3c 中 owner 看过的同一截图相同，不是本轮引起的。
- `1280/fe4a-c6-reason-expanded`：“收起”仍在正文下一行，缩进 4 px（N15）。

### 2.5 回源脚本

候选中的 `/home/dev/gdds-fe4a-rereview2/frontend/scripts/check-handoff-hex.py`，SHA256 `b399329b0f0af065eed17794d1e34fe880da5c2a4e1cf334d5de8de4fd7c3b96`（与 handoff §4 一致）。探针脚本 `/home/dev/gdds-fe-logs/fe4a-rereview2/hex-probes.sh` SHA256 `734d51aa9e3db826d74be41705d65de2ccb5346983ad143dfcaa8285c939f83a`，输出 `hex-probes.log` SHA256 `4d72cd6426f74e25266f0e22ed2694a7cfa1c90bfa829b4df8896144ebddb752`。

| 用例 | 预期 | 结果 |
| --- | --- | --- |
| H0：fix2 handoff，按 handoff §10.1 的全部来源 | exit 0 | 符合：`106 distinct full token(s); git=29 sha256=73 allowed=4 abnormal=0`；输出除开头 5 行外与实施会话 `hex-handoff.log` 逐行相同 |
| P-H1：一个 64 位值改一位 | exit 1 | 符合：`unverified sha256` |
| P-H4：10 位提交号改一位 | exit 1 | 符合：`unresolved git object` |
| P-H5：把“`frontend/` 树”后的树号换成提交号 | exit 1 | 符合：`object type mismatch` |
| P-H2（真实表格）：§6.4 一行换成另一张截图的 SHA | exit 1 | 符合：`pairing mismatch`（现场重算） |
| P-H3：不给 SHA 来源；不给 `--git-objects` | 都 exit 1 | 符合 |
| P-H2、P-H6（合成）：表格与正文两对，正确与互换；`--sha-file` 来源互换 | 正 0、负 1 | 符合 |
| P-H7：只含 63、39、13 位值的副本 | 都 exit 1 | 符合：都报 `abnormal length` |
| H8：把 handoff 自记的日志哈希改一位 | exit 0（按设计跳过） | 符合 |
| H8b：同一行同时含自记日志名与另一张截图的错误 SHA | exit 1 | 符合：该行的配对仍被核对，`--self-log` 只跳过“值是否有来源” |

`--self-log` 跳过的值由本会话直接核对：`/home/dev/gdds-fe-logs/fe4a-fix2/hex-handoff.log` 现场 SHA256 为 `9ea2859354a351dd384e1e56aa740f56a9db0cc1075a99ce4bfa0007e2d58fa3`，与 handoff §10.1 相同。

日志开头的 `HEAD:` 是 `--repo /home/dev/gateway-data-management-system` 的 HEAD（`16ffe728290e1179d9450ea160a0e6ca49473ec6`，07 主检出），不是被核对 handoff 所在的 `919e22d474`；也没有记录时间（K3）。实施会话日志中的 `argv` 是相对路径 `frontend/scripts/check-handoff-hex.py`，handoff §10.1 写的是绝对路径；两者在该 cwd 下等价。

## 3. 逐项核对

### 3.1 G1–G5

| # | 结论 | 说明 |
| --- | --- | --- |
| G1 | 符合 | `let loaded` 与 `loaded = reloaded;` 已恢复；B4b 与复审第 1 轮 P-B4 的用例逐字相同（只去掉 `PROBE` 前缀与注释首行）；回退探针使其失败 |
| G2 | 符合 | 两条用例与 P-F3s 逐字相同；两个回退探针各自只使对应用例失败 |
| G3 | 符合（K3 另计） | 先取全部 ≥ 7 位串再按长度分流；P-H1–P-H7 正反符合；N12 的两处启发式按建议改写，复审第 1 轮报告回归仍 exit 0 |
| G4 | 部分符合（K3） | 树号已更正、归档 ref 已建、`--allow` 只用于非 git 对象、命令逐字记录、脚本打印参数；日志开头的 HEAD 不是被核对的提交，也没有时间 |
| G5 F10 | 部分符合（K1） | 脚本判据、模式、输出符合；节点复验见 §2.3；第 ① 次见 §2.4；看图清单由脚本生成且完整。自检对过滤类型 2–4 没有区分力 |
| G5 F11 | 规则 1、2、3、5 符合；规则 4 部分符合（K2） | 见 §3.2 |

### 3.2 C12 五条规则

| 规则 | 实现 | 用例 | 区分力 |
| --- | --- | --- | --- |
| 1 错误提示移出按钮行 | `ReviewActions` 经 `createPortal` 渲染到 `.compare-header__notice`，保留 `role="alert"` | V11、V12 断言错误在 `.compare-header__notice` 且不在 `.review-actions` | 探针使 V11、V12 失败 |
| 2 处置说明独占一行 | `ReviewDispositionLine` 移出 `.compare-header__top`，位于主行之后、错误提示之前 | V12 断言“返回工作台”宽度与无处置时相同、1280 下面包屑可见 | P-R2 使 V12 失败 |
| 3 相同原因只显示一次 | 撤回、退回共用 `blockedReason`；审核通过的原因相同时加入；三个按钮 `aria-describedby` 指向同一元素；原因不同（过期通过）时各自显示 | V12 断言原因文字只有 1 处、三个按钮都禁用且 `aria-describedby` 都等于该元素 id | P-R3 使 V12 失败 |
| 4 截图前断言无横向溢出 | 三个截图 helper 中加断言；`upload-mode.spec.ts` 整份排除（K2） | 全部截图运行；V11、V12 另断言面包屑 | 规则 4 探针使 V11 失败（需开截图，N14） |
| 5 V12 重读状态为已通过 | fixture 在关闭后返回 `APPROVED`、版本 6；`ReviewActions` 只在切换提交时清除错误 | V12 断言“审核：已通过”“已关闭（未归档）”、三个按钮禁用 | 探针使 V12 失败 |

规则 1 要求“错误出现与消失时，按钮的位置和顶栏主行的高度不变”。错误渲染在主行之外，由结构保证；用例断言的是结构，没有直接测量位置与高度，可以接受。

### 3.3 N5–N12

- **N5：** 在提示框出现后用非轮询断言确认两个计数都是 `before + 1`，符合。
- **N6：** 去掉了 `{" "}`，`pre-wrap` 只留在正文；但新增的 `.reason-text .link-button { margin-left: 4px; }` 使“收起/展开”仍在下一行缩进（N15）。
- **N7、N8：** 符合。
- **N9：** 未改代码，列为证据运行的要求，可以接受。
- **N10：** 早退路径写 `.sha256` 旁注，注释已改，符合。
- **N11：** 未改，交 owner 看图，可以接受。
- **N12：** 符合（§2.5 合成用例与回归）。

## 4. 需要修复（阻塞）

- **K1（比较脚本自检）：** 自检中用 5 种过滤类型编码的图像，解码后逐行与原像素全部比较（至少覆盖类型 0–4 各一行，且这些行与上一行内容不同，使“上”“左上”预测项非零）。复审时本会话重跑 §2.3 的 4 个变异：每个都必须使 `--self-test` 失败。不改判定与上限。
- **K2（规则 4 的范围）：** 在 `upload-mode.spec.ts` 的截图 helper 中加同样的断言，只对 `fe3b-w4-approved-withdraw` 一个截图名豁免（两种宽度），豁免处注明 N5 带入 FE4b；不改预览页顶栏。handoff §7.6 改写为：豁免只有这一个截图名，1280 与 1920 都溢出 12 px，原因是 `.disabled-reason` 超出其容器（N5）。该豁免仍交 owner 确认（§6）。复审时本会话用两个探针复验：去掉豁免时该用例失败；在另一个 upload-mode 截图状态中制造溢出时断言失败。
- **K3（回源日志头）：** 日志开头另记 UTC 时间、被核对 handoff 文件所在 git 工作区的 HEAD（`git -C <handoff 所在目录> rev-parse HEAD`）与 handoff 文件的 SHA256；`--repo` 的 HEAD 若保留，标为 `repo_HEAD`。handoff 的回源一节按实际执行的命令逐字记录。

K1–K3 改动 `frontend/` 树，因此按 kickoff §7.3：

- 实施会话在新的最终候选上、07 上连续两次模拟接口全量（`GATEWAY_FE_TEST_WORKERS=2`，经 wrapper），作为第 ① 次；
- FE3c 变化清单不需要重新分组：应用代码与截图内容不变；用新候选的第一次全量重新跑一次比较模式，确认非噪声文件集合与本轮相同即可；
- 不追加真实旅程与 t1 调试运行。

## 5. 非阻塞

- **N13** 07 上 `refs/review/fe4a-fix2/probe-c12-error-in-row` 指向 `6c2ddb7097`（与 `probe-c12-overflow-only` 相同），handoff §7.7 写的是 `5a1f32bf5e`；worktree `/home/dev/gdds-fe4a-fix2-probe-c12err` 在正确的提交上。请把 ref 改到 `5a1f32bf5e`。
- **N14** 三个截图 helper 在没有设置 `GATEWAY_FE_SCREENSHOT_DIR` 时直接返回，横向溢出断言只在带 `--screenshots` 的运行中执行。符合规则 4 “截图前断言”的字面要求，权威全量与证据运行都带截图；但规则 4 的探针必须在开截图时运行，handoff 的探针记录应注明。可选：把断言移到早退之前，使不拍截图的运行也检查。
- **N15** N6 之后“收起/展开”仍在正文下一行，缩进 4 px。若希望紧接正文末尾，需要让正文在展开时为行内；也可以接受现状，交 owner 随 C6 截图确认。
- **N16** 比较脚本：文件头说明把“只在一侧存在”写进“尺寸不同”，实际归为“缺失”；“相同”按解码后像素相同判断，不是字节相同（§3.8 写的是字节相同）。后者对稳定性比较无影响，改说明或改实现都可以。
- **N17** `ReviewActions` 的错误提示改为只在切换提交、打开对话框、`refreshFacts` 成功与确认开始时清除。页面在其他路径重读 Review（例如 `ComparisonPage.tsx:382` 的 bundle 加载）后，旧的 `REVIEW_VERSION_CONFLICT` 提示与“刷新审核信息”会保留。另外 `errorNoticeHost` 为空时错误不渲染，没有回退位置；当前只有 `ComparisonPage` 使用且总是传入。都不影响现有路径，FE4b 调整顶栏时一并考虑。
- **N18** handoff §7.6 说预览页溢出只在 1280；P-U 显示 1920 下同样溢出 12 px（随 K2 改写）。

## 6. 交 owner 确认（汇总，不阻塞本轮）

- 规则 4 的豁免（K2 之后只剩 `fe3b-w4-approved-withdraw` 一个截图名，随 FE4b 的 N5 处理）；
- C8 灰色冲突提示与红色集合变化提示同屏（`fe4a-c8-both-notices`，kickoff §15.3）；
- N11（关闭成功后输入仍可编辑）、N15（“收起”位置）；
- §7.3 看图清单：以 handoff §6.4 的分组为准，看复审通过的候选在 07 上的截图。

## 7. 下一步

1. 实施会话按 §4 K1–K3 修复，提交 fix3 handoff `docs/frontend-vnext/fe4a-handoff-fix3.md`，由本会话复审第 3 轮（定向）。复审内容：K1 的 4 个变异、K2 的两个探针、K3 的日志头、第 ② 次稳定性比较（本会话独立全量与实施会话第 ① 次的第一次）、FE3c 非噪声集合复核与回源。
2. 复审通过后的证据项不变（审核报告 §8 第 3 项与 kickoff §7.2 FE4a 证据行），另按 §7.3 做第 ③ 次稳定性比较；05 的 t1 同时用新的 `--log-dir` 与 `--evidence-dir`（N9）。

## 8. 本会话的遗留

- 开发主机：`refs/review/fe4a-rr2/probe-{r2,r3,u}`；bundle `/home/dev/gdds-bundles/fe4a-rr2-probes.bundle`；临时 worktree `/home/dev/gdds-fe4a-rr2-probes` 已删除。本报告提交在短分支 `fe4a-review`，随 FE4a 退出合入 main。
- 07：同名 `refs/review/fe4a-rr2/*`；worktree `/home/dev/gdds-fe4a-rereview2` 与 `/home/dev/gdds-fe4a-rr2-probe-{r2,r3,u}`；日志 `/home/dev/gdds-fe-logs/fe4a-rereview2/`；截图 `/home/dev/gdds-fe-shots/fe4a-rereview2/full1`。实施会话与审核会话原有的 worktree、日志与截图未改动。保留到 FE4a 退出。
- 07 上没有本会话留下的占用标记。本会话没有在开发主机上运行测试，没有推送，没有改 `fe-vnext`。

## 9. 本报告的回源

在 07 上用候选的回源脚本核对本报告（`/home/dev/gdds-fe4a-rereview2` 中运行，`--repo /home/dev/gateway-data-management-system`，07 上有实施会话与本会话的全部探针提交）。来源：07 现场重算的清单 `/home/dev/gdds-fe-logs/fe4a-rereview2/report-sources-07.sha256`（SHA256 `07e974a8fa00dcea5543ad4807432c2c5b9945f21d9edafd6424bd7063da4e3c`，覆盖本会话全部日志、脚本、输出、截图清单、bundle 与引用的实施会话日志），开发主机现场重算的两个 bundle 清单，handoff §10.1 的来源清单，以及本会话全量的 wrapper 日志（`--evidence-file`）。没有使用 `--allow`。

结果：exit 0，`65 distinct full token(s); git=27 sha256=38 allowed=0 abnormal=0; 0 truncated form(s)`。命令、输入副本与输出在 07 `/home/dev/gdds-fe-logs/fe4a-rereview2/report-hex-input/`（输出 `hex-report.log`；其哈希不写入本报告，避免自引用）。
