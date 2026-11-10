# FE4a 复审第 1 轮

- **复审对象：** 分支 `fe-vnext`，fix1 区间 `7a6520620b..c6656ce5e4`（5 个提交）。
  - 代码候选提交 `8e2045a58bb098dd2dafdc1f0ebe771cba1b2ca4`；它的 `frontend/` 树 `5c4661078dac5b1d6826ef4407446b4b01e3a5b9`；
  - handoff 提交 `c6656ce5e49ead66fc03e80ae80fac9370341a03`：新增 `docs/frontend-vnext/fe4a-handoff-fix1.md`，并改 `frontend/scripts/check-handoff-hex.py`，`frontend/` 树 `e022d89b3500da7533d92c75488529e60b4e303c`；
  - 07 上用 bundle `/home/dev/gdds-bundles/fe4a-fix1e.bundle`（SHA256 `bfa615941bdd07bc5360c86c91d6e0044fbf3371a04ff4abff440807e110c4ff`）中的同名提交，与开发主机 `fe-vnext` 一致。
- **依据：** [FE4a 审核](fe4a-review.md)（`541febf566`）§4 F1–F9、§5 N1–N6；[FE4 kickoff](../fe4-kickoff.md)（main `0dd609ecff`，修订 4）§3.4、§3.8、§7.2、§7.3、§8、§10 Q14–Q16、§11.2、§15；FE3 kickoff §4.6、§16；`fe4a-handoff-fix1.md`。
- **复审会话：** FE4a 审核会话（会话名 `fe4a-rereview1`，本轮在新对话中承担审核会话角色，没有实施会话的上下文）。
- **日期：** 2026-11-10（时间均为 UTC）。
- **结论：定向修复。** F1、F4、F6、F8 与 N1–N4 符合；F2 的代码与截图符合；wrapper（F7 前半）全部负向用例都在运行入口前退出；回源脚本 P-H1–P-H6 正反都符合；模拟接口全量在候选上通过；J1/J2 调试日志与 FE3 kickoff §4.6 一致。需要修复后再复审（§4 G1–G5）：
  - fix1 删掉了归档对话框“一次加载”重读后的 `loaded = reloaded`，重读后显示的是第一次（与候选不一致的）预检方案；handoff 没有列出这处改动，B4 用例不能发现（G1，产品回归）；
  - F3 的两条新用例没有区分力：分别回退 F3 的两处修复后，C8 的 4 条用例全部通过（G2）；
  - 回源脚本不再报告长度异常的值，63、39、13 位的值整份 handoff 报 OK（G3，F7 的回归）；
  - handoff §7 记录的回源命令不能复现，`--allow` 被用在 git 对象上，其中一个树号是错的（G4）；
  - kickoff 修订 4 要求并入本轮的 F10（截图比较脚本与第 ① 次稳定性比较）与 F11（C12）没有交付（G5）。

## 1. 路径核对与范围

| 检查 | 结果 |
| --- | --- |
| 下列各提交的 `:vnext`：`7a6520620b`、`6bcf62d4e2`、`501fd7469c`、`b10ae47fa3`、`8e2045a58b`、`c6656ce5e4`（均为提交） | 都是树 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `git diff --name-only 7a6520620b c6656ce5e4` | 16 个文件：`frontend/` 15 个、`docs/frontend-vnext/fe4a-handoff-fix1.md`，没有其他路径 |
| 提交链 | `7a6520620b` → `6bcf62d4e2` → `501fd7469c` → `b10ae47fa3` → `8e2045a58b` → `c6656ce5e4`，线性，没有合入；`8e2045a58b..c6656ce5e4` 只改 handoff 与回源脚本 |
| `package.json`、`package-lock.json`、`openapi.json`、`src/features/api/generated/` | 无改动 |
| 打包流程筛查（kickoff §7.4 第 1 步）：`upload-package.ts`、`UploadStepCard.tsx` | 为空：不触发 t4 |
| `501fd7469c..c6656ce5e4` 中的 `frontend/src`、`frontend/e2e-real`、`run-real-backend-e2e.sh` | 为空：05 的 J1/J2 调试运行（`501fd7469c`）与候选的应用代码、真实旅程用例相同 |

### 1.1 handoff 没有列出的改动

`6bcf62d4e2` 在 `ArchiveMainlineDialog.tsx` 的 `load` 中把 `let loaded` 改为 `const loaded`，并删除了 §16.2“一次加载”分支末尾的 `loaded = reloaded;`。handoff §2 的 F3 一节只写了集合提示与 `pendingNotice` 的改动，没有提到这一处。影响见 G1。

## 2. 独立运行、探针与核对

### 2.1 本会话的运行（07，`gw-dms-07.lan`）

新建 detached worktree `/home/dev/gdds-fe4a-rereview1`（`c6656ce5e4`，clean）。工具链 `mcr.microsoft.com/playwright:v1.64.1-noble`，npm 缓存归档 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，`GATEWAY_FE_TEST_WORKERS=2`。运行前后节点上没有占用标记。

| 运行 | 提交 | 起止 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| 模拟接口全量：候选 wrapper，入口 `run-tests.sh --e2e`，带 `--shots-dir` | 提交 `c6656ce5e4`（前端树 `e022d89b35`），起止 clean | 14:06:12–14:08:54 | exit 0：类型检查、lint、构建通过；单测 35 个文件 214 项；Playwright 95 项，`e2e_workers=2`；198 张截图，清单 `/home/dev/gdds-fe-logs/fe4a-rereview1/full1-shots.sha256` SHA256 `3947c12695b05c34a830b3b47b603f27836cda4bb606978c596cba1cf78f29a5` | `fe4a-rereview1-run-tests-20261110T140612Z.log` `98aa6b8aa3d94b0af65a38922a7c4cf5b022c4fff1cd98fd23069385f6c13aa4` |

截图在 07 `/home/dev/gdds-fe-shots/fe4a-rereview1/full1`。wrapper 自动生成了 `--screenshots /home/dev/gdds-fe-shots/fe4a-rereview1/full1`，记录了 `GATEWAY_FE_TEST_WORKERS=2`、占用标记内容与 `busy_end`，结果字段 `wrapper_field hostname_end`、`wrapper_field exit_code=0` 取自入口输出段。

### 2.2 代码探针（已提交的一次性 worktree，只在 07 上运行）

探针提交在开发主机与 07 的 `refs/review/fe4a-rr1/probe-*`，经 bundle 传到 07（`fe4a-rr1-probes.bundle` `53a8df286f4984cb068b0e6f2bd2c6571b50322e5aa21c276124b61c7e870f3c`、`fe4a-rr1-probes2.bundle` `1d9ef01a31197700c2a2fc9d0d2a97112ffd06da4f3766ad77ab75bd3ebf01d8`、`fe4a-rr1-probes3.bundle` `be4deeaeb9bb9695dfdf8ac67aa1ab16c9db9e5a9d951fb320a6277a1ef73465`），各建 detached worktree `/home/dev/gdds-fe4a-rr1-probe-<名>`。用例由 `/home/dev/gdds-fe-logs/fe4a-rereview1/run-probe.sh`（SHA256 `965c6ecbd09cc282ee613e0fb6121ed7b7ed697fb0603b9517906ca3d1eca22a`，由审核会话原 `run-probe.sh` 只改会话名与日志目录）运行：取占用标记，在同一工具链镜像中离线 `npm ci`、`npm run test:unit`，再运行指定用例，`--workers=1`。

| 探针 | 提交 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| P-C2r：在候选上去掉 `retryResume` 的在途等待与 `InflightGate`（同原 P-C2） | `f54dac1896` | F1 用例失败 | **符合**：workspace POST 期望 3、实得 4 | `9a2aa3fc3f245474eb8daadc3f4730b802ffb6119dde843abc54e35b3ed577dc` |
| P-B4：只加一条用例 B4b：第一次预检与第一次候选读取不一致，且第一次预检带阻止项“已有提交正在处理”；重读后应显示第二次预检 | `f23ea71823` | 若重读后显示第二次预检，B4b 通过 | **不符合**：B4b 失败在“已有提交正在处理，完成后才能归档”应为 0 处（收到 1），即重读后显示的是第一次预检；原 B4 通过（G1） | `01cb0cedb4495677d59c4d6a85d5bddde5b7c8d7f535c5de78e28cd4af03e1d5` |
| P-B4fix：在 P-B4 上恢复 `let loaded` 与 `loaded = reloaded;` | `8039bbb980` | B4、B4b 都通过 | **符合**：2 项通过 | `a62f47deeb4b355aa18cfed41312d13026351d6f7c8720c9bb78c59ba1b34305` |
| P-F3a：去掉“集合未变时 `setCollectionNotice(null)`” | `f9a827a59a` | “C8 集合未变的成功接受后清除集合变化提示”失败 | **不符合**：C8 的 4 条全部通过（G2） | `489b7d9091cc15c9730018aef54d21f7ae59c7de2f39aedf9f5bcf1b39437baf` |
| P-F3b：去掉加载失败时的 `pendingNotice.current = null` | `0e53218e50` | “C8 加载失败后不保留待处理的冲突提示”失败 | **不符合**：C8 的 4 条全部通过（G2） | `7f6b810b72bc2fd043a49883a43310bd0e280831883512bc48c51ca664b4ce46` |
| P-F3s：只加两条加强的 F3 用例（见 G2） | `d7a2f07522` | 在候选上通过 | **符合**：C8 的 4 条与两条加强用例共 6 项通过 | `eb792d58abc1ff38209c2e63293f9ed02c16794a2f6bbdbd639f6934a0eba367` |
| P-F3s-a：P-F3s 加 P-F3a 的回退 | `18c9a607a8` | 加强的 F3a 用例失败 | **符合**：失败在集合变化提示应为 0 处（收到 1），其余 5 项通过 | `4303a13c673fc356879ea4ceb7e54b9b95f251e06aa20b62a325981669f5b35a` |
| P-F3s-b：P-F3s 加 P-F3b 的回退 | `f6516be20d` | 加强的 F3b 用例失败 | **符合**：失败在冲突提示应为 0 处（收到 1），其余 5 项通过 | `76e001e635ff39a161160244dd059590f53b0ed4107fb4168635f9c72deb577b` |

P-F3s-a、P-F3s-b 第一次构造时，本会话的 `git cherry-pick -q` 因不支持 `-q` 而失败，两个 ref 指向了与 P-F3s 相同的提交；那两次运行（日志 `34c70e20d604fecaac52ba122d42d1e9b9101202cba56b073c57a3230fea564c`、`060cb6a8533ec6abdbc289ec6a823a24d8b0c2fc84af170c3c58f94c32123545`）实际是 P-F3s 的重复，6 项通过。修正构造后各重做一次，结果见上表。没有触及候选 worktree。

未做回退探针的项：F2（逻辑与截图核对，见 §3.1）、F4（V9 的断言直接对应按钮集合）。

### 2.3 取证工具探针

**wrapper**（对象为候选中的 wrapper 脚本）：探针脚本 `/home/dev/gdds-fe-logs/fe4a-rereview1/wrapper-probes.sh` SHA256 `5d6999ad29eef4ebc23585d7fc2854768abeabf7b3b577d0bf604a43caeaddfc`，输出 `wrapper-probes.log` SHA256 `d5605abfec42e1bc192683109b18846ee0e5a061d64c019cacd5f65e734ceb8e`；重做脚本 `/home/dev/gdds-fe-logs/fe4a-rereview1/wrapper-probes-redo.sh` SHA256 `e259432240511c0e86fca5c18eebe9d67208fe0c357057b6baa1af4f13f186e5`，输出 `wrapper-probes-redo.log` SHA256 `e4a573822baa8f2eade6540aef93aeb84b3fa3d902c772cba527e03098187ba6`。

以上文件都在 07 的 `/home/dev/gdds-fe-logs/fe4a-rereview1/`。

| 用例 | 结果 |
| --- | --- |
| `--log-dir` 缺值（原 P-W 的同类错误） | exit 2，没有写日志、没有占用标记 |
| 日志目录在 worktree 内（原 P-W2） | exit 2 `log dir must be outside the worktree`；worktree 保持 clean |
| 截图目录在 worktree 内 | exit 2 |
| 入口自带 `--screenshots` 与 `--shots-dir` 不同 | exit 2 |
| 起点不 clean（另建一次性 worktree 放一个未跟踪文件） | exit 2 `worktree is not clean at start`，日志记录了 `status_start=?? untracked-probe-file`，没有 `entry_output_begin` |
| 空占用标记目录 | exit 3，标记保持原样 |
| 本会话残留标记 | exit 3，标记内容未变，没有接管 |
| `run-real-backend-e2e.sh` 遇到已有标记 | exit 3 |
| 正向：`validate-upload-package.sh --help` | exit 0；`GATEWAY_FE_TEST_WORKERS=2` 原样记录，`GATEWAY_FE_PROBE_TOKEN`、`GATEWAY_FE_PROBE_URL` 只记 SHA256，日志中没有明文；`busy_end` 为标记内容，结束后标记不存在；`.sha256` 旁注与日志一致；入口不输出 `exit_code` 时写 `wrapper_field_missing exit_code reason=…` |

第一次脚本中的“起点不 clean”与“本会话残留标记”两项是本会话脚本的错误（在仓库外执行 `git worktree add`；两次运行落在同一秒，先撞到“日志文件已存在”），都没有运行入口，没有副作用；修正后各重做一次，结果如上。

**回源脚本**：候选中的 `/home/dev/gdds-fe4a-rereview1/frontend/scripts/check-handoff-hex.py` SHA256 `7c35d5938a7854c3f044cb012544ce0fb2245ef7cad36ad3ceec5320e408ba62`；探针脚本 `/home/dev/gdds-fe-logs/fe4a-rereview1/hex-probes.sh` SHA256 `5949bb8b001931b1a3b77ab415284806b846e99b344eedfaf2346049e5df7bfa`，输出 `hex-probes.log` SHA256 `6ef90651ebe266352974d72e8567ad59f563512dcabc0db46f1b2c8c38fa109e`。

| 用例 | 预期 | 结果 |
| --- | --- | --- |
| H0：fix1 handoff，来源为 07/05 的 sha 清单、full3 截图清单与现场截图、full3 入口日志（`--evidence-file`） | exit 0 | 符合（另见 G4） |
| P-H1：64 位值改一位 | exit 1 | 符合：`unverified sha256` 与 `pairing mismatch` |
| P-H4：10 位提交号改一位 | exit 1 | 符合：`unresolved git object` |
| P-H5：把“树 `5c4661078d`”换成提交号 | exit 1 | 符合：`object type mismatch` |
| P-H3：不给 SHA 来源；不给 `--git-objects` | 都 exit 1 | 符合 |
| P-H2：表格行两张截图互换 SHA（`--source-dir` 与 `--sha-file` 两种） | 正 0、负 1 | 符合：两条 `pairing mismatch` |
| P-H6：同一行正文两对“名字 + SHA”，正确与互换 | 正 0、负 1 | 符合，没有交叉误报 |
| **P-H7（新增）**：只含一个 63 位值、39 位提交号或 13 位值的 handoff | exit 1，报告长度异常 | **不符合**：三种都 `OK: 0 distinct full token(s)`，exit 0；对 fix1 handoff 删掉一个 64 位值的末位，结果 `OK: 51 …`，该值不在输出中（`/home/dev/gdds-fe-logs/fe4a-rereview1/hexprobe/p-len63.log` SHA256 `bb2929b9d516223b52899da27070b5df4923bea6fa65518531e28a4934398a13`）。`7a6520620b` 的旧脚本对同一副本报 `abnormal length 63`（G3） |

### 2.4 handoff §7 回源的复现

在 07 上用候选脚本按 handoff §7 记录的参数原样运行：exit 1，8 个 64 位值未核对：工具链 config digest `a0d7b2b49ffa…1a017` 与 7 个 RootFS DiffID（输出 `hex-asrecorded.log` SHA256 `f0c6cad01b5eb2be815f425576691c1999cedd445097402a0d0bb4f4d8ae19ef`）。这些值本身正确，出现在 full3 的入口日志中；加上 `--evidence-file /home/dev/gdds-fe-logs/frontend/frontend-tests-20261110T131245Z.log` 后，输出 `hex-withev.log`（SHA256 `8c06adc4def2cb0ce1b34e670f9368b60de547b58b00afa9b34b43dce77fc75d`）与实施会话的最终回源输出排序后逐行相同。即实际运行用了这个参数，handoff 没有记录，`fe4a-fix1-hex-final.log` 本身也不记录命令。

去掉 `--allow a2fb4a027a --allow bf792803a2 --allow 7ea7df7c9d` 再运行：`a2fb4a027a`、`bf792803a2` 都是能解析的提交（`type=commit`），唯一的问题是 `unresolved git object: 7ea7df7c9d`（输出 `hex-withev-noallow.log` SHA256 `3147f6bb2cd6029921f0ef64081b930626bbdd9b2e21ae4ef80b36d0d4a9e221`）。

probe-c2 自验日志记录的 `frontend_tree_start` 是 `7ea7df7c48b0c6c14757882ba6e4d3abe92dd147`（树），即探针提交的 `frontend/` 子目录对象。handoff §4 的“probe-c2 的 frontend 树 `7ea7df7c9d`”抄错了后两位，`--allow` 把它当成“非 git 对象”放过（G4）。

该探针提交 `bf792803a2` 原先只是 07 上一个 worktree 的 detached HEAD，没有 ref 指向。

### 2.5 截图比较

kickoff 修订 4 要求的 `frontend/scripts/compare-screenshots.py` 不在候选中（G5）。本会话用一次性脚本 `/home/dev/gdds-fe-logs/fe4a-rereview1/rr1-cmp.py`（SHA256 `9c07f2b9e0e792f4c93decc98d9fe094f2cb9ae1a8ed839b64535db9f0b9b6e4`，只用标准库，按 Q14 的判据：不同像素 ≤ 100 且最大 8 邻接连通块 ≤ 16 为噪声）取得下面的数据。它不是 §3.8 的交付物，结果只作本轮参考，不代替第 ①、② 次稳定性比较。

| 比较 | 结果 | 输出 SHA256 |
| --- | --- | --- |
| 实施会话 full3（`8e2045a58b`；清单 `/home/dev/fe4a-full3-shots.sha256` SHA256 `e754465be932deeea8d5f7801cd94340812a1763ae2ba734bf95d860601bc8c2`）与本会话 full1（`c6656ce5e4`，两者应用代码相同） | 198 张：191 张相同、7 张噪声，没有内容变化、尺寸不同或缺失 | `a8ac7db90e02324b0afce5ae9f162153121c38f789fecf14ab25316d695480d3` |
| FE3c 证据截图副本（07 现场重算的清单 `fe3c-copy-shots.sha256` SHA256 `63a0e6006952152e7cd59db22ada9b34e4774f4f99676c22041b31f9ea1129f2`，与 kickoff 记录一致）与本会话 full1 | 32 张内容变化、2 张尺寸不同、8 张只在 FE4a 中（C6、C8、D3 的新截图）、7 张噪声、149 张相同 | `fbc4a50f492d42dd7de5aa0976989281a6e7396b4ef70969f8b495fe0af2c35a` |

32 张内容变化与 2 张尺寸不同都能对应到 handoff §5 的分组（C3 16 张、C4 固定时长 8 张、C4 helper 2 张、C9 4 张、F2 2 张；C5/D2 2 张尺寸不同）。两处归因需要更正（N8）。

**看图（本会话）：** `1280/fe4a-c6-reason-collapsed`、`-expanded`：三行截断加省略号，“展开/收起”可用，展开后全文，符合 F2；切换链接比正文缩进一个空格（N6）。`1280/fe4a-c8-both-notices`：红色集合变化提示在上、灰色冲突提示在下，与 kickoff §15.3 的说明一致，交 owner。`1280/fe3c-close-result`：成功后底部只有一个主按钮“关闭”，正文的关闭人、时间、理由各出现一次，符合 F4。`1920/fe3b-d3-manual-close`：详情面板 4 行关闭理由全文加“收起”。

### 2.6 真实旅程（核对 05 上的调试日志，不重跑）

| 运行 | 起止 | HEAD / 树 | 结果 | 日志 SHA256（05 现场重算） |
| --- | --- | --- | --- | --- |
| J1、J2：wrapper `--entry run-real-backend-e2e.sh -- --suite journeys --subphase fe4a --session fe4a-impl` | 13:01:52–13:05:44 | `501fd7469c`；`frontend/` `eee3d38b3a`；`vnext/` `49c1de43be`；起止 clean | `playwright_grep=--grep=j1-archive-mainline\|j2-manual-close`，2 项通过，`suite_exit=0`，`openapi_compare=match`，`cleanup_status=ok`，`worktree_clean_end=true`；`busy_end=absent` | wrapper `d552577595ff8344ee298657a65f646351d07e02e59db197ae2aaad5d10ae2b2`；入口 `e4d76d58b22adb1e71e8552ff0f3278ba7d7c4fd03b9f5799571cee6470c2a7f`；case log `b9835b914f1dd31688c7bfbf3fef7625730c7fff20b0fae80291923fcb74fd26`；results `9c7d12c8c31f22bdca496df52c8be5da863bb43f33acf5a5cf8cf08a664d28f7` |

- 工具链身份（config digest 与 7 个 DiffID）、`gateway-backend-deps:lock-578e079b762e`（image ID `sha256:2d13e70aa3101dba0bd4f07695ce4886c844b930787b56fafad0bda2c9a0dfbd`）与 RS 依赖镜像 `lock-6dc9659f0aee` 与审核时相同。
- **异常集合：** 从 `/home/dev/gdds-fe-logs/fe4a-impl/evidence/journey-cases.log` 按步骤统计：J1 第 2 步 1 项、第 7 步 3 项（BTU、INITIAL 与 MODIFIED 缺生成时间）、第 11 步 2 项、第 13 步 3 项（含 `PROJECT_IDENTITY_EXCEPTION`）；J2 第 1 步 1 项、第 3 步 8 项（缺生成时间 ×5、BTU、同级排除 ×2）、第 5 步 7 项（含 `INITIAL_SOURCE_UNEXPLAINED`）、第 8 步 2 项；第 4 步 `statuses=201,200`。与审核报告 §2.4 核对过的 07:52 运行逐步相同，因此与 FE3 kickoff §4.6 相符。
- F4 对 `journeys.spec.ts:1862` 的改动（点“关闭”）在该运行中通过。
- 入口把 case log 与截图写在 `--log-dir` 下的 `evidence/`，`--evidence-dir` 只接收 Playwright 的 `test-results`（N9）。

## 3. 逐项核对

### 3.1 F1–F9

| # | 结论 | 说明 |
| --- | --- | --- |
| F1 | 符合（N5） | 新用例在 workspace POST 挂起时连点“重试”，断言 workspace POST 与 attempt GET 各为 `before + 1`；P-C2r 使其失败（期望 3、实得 4） |
| F2 | 符合（N6） | `ReasonText` 由 `ClosureReason` 与归档卡片共用，先按 3 行 clamp 渲染，用 `scrollHeight > clientHeight + 1` 判断是否显示“展开”，`ResizeObserver` 跟随宽度，展开后可收起，`pre-wrap` 保留换行；`REASON_FOLD_THRESHOLD` 与换行数判断已删除。用例覆盖长单行、4 行、3 行以内与详情面板 4 行理由。多行用例（每行只有 3 个字）在按字符数判断的旧逻辑下不会折叠，长单行用例在按换行数判断的旧逻辑下不会折叠，所以两条用例分别能区分两种旧做法；未做回退探针。`ReviewDispositionLine` 的“查看关闭理由”没有改，kickoff 与审核报告都没有要求 |
| F3 | **代码符合，用例不符合**（G2） | 集合未变时清除 `collectionNotice`、加载失败时清除 `pendingNotice` 两处修复正确（P-F3s 通过，P-F3s-a、P-F3s-b 失败）；但实施会话的两条新用例在两处修复分别回退后都通过 |
| F4 | 符合 | `closeResult` 存在时只渲染主按钮“关闭”；V9 断言“取消”“已关闭”“确认关闭”都不存在、正文不重复“已关闭”；V10 与 `journeys.spec.ts:1862` 改为点“关闭”，J1/J2 调试运行通过 |
| F5 | 部分符合（G5、N8） | 新截图 C6、C8、D3 各两种宽度都已生成；FE3c 到候选的差异表能覆盖本会话比较得到的全部内容变化与尺寸不同。但修订 4 要求清单由比较脚本生成（§7.3、§15.3），并加入 C12 改动后的审核顶栏，本轮没有 |
| F6 | 符合 | `--force-color-profile=srgb` 已删除 |
| F7 | wrapper 符合；回源脚本不符合（G3） | wrapper 见 §2.3，全部要求已实现；回源脚本的配对、来源要求与类型核对符合（P-H1–P-H6），但长度异常检测回归 |
| F8 | 符合 | 只对 `NoModificationAllowedError` 重试；4 个单测覆盖短暂失败后成功、持续失败在第 5 次后抛出、其他 `DOMException` 立即抛出、`NotFoundError` 直接返回 |
| F9 | 部分符合（G4、N7） | 第 1–5 项更正准确；第 6 项写成“引用审核会话保留的 refs，或自建 refs/archive”，没有选定；第 7 项与审核报告 N6 不符；本轮 handoff 自身又出现回源命令不全与树号抄错（G4） |

### 3.2 N1–N4

- **N1：** handoff 写明 History 结果有意丢弃、review 读两次，可接受。
- **N2：** `submitted` 分支不再递增 `resumeSeq`，符合。
- **N3：** `MODIFIED_BEFORE_INITIAL` 的测试数据改为左值早于右值，期望文案同步，符合。
- **N4：** 删除码另断言通用文案“比较过程有提示”，符合。

### 3.3 kickoff 修订 4 带来的要求

kickoff 修订 4（main `0dd609ecff`，12:52:43）在 fix1 第一个提交（`6bcf62d4e2`，12:54:00）之前提交。§15.4 要求审核会话把 §15 转给实施会话，作为 F10（§3.8 截图比较脚本与 C4 第 ① 次稳定性比较）、F11（C12）并入 fix1。候选中没有 `compare-screenshots.py`，没有 C12 的改动，也没有在最终候选上连续两次的全量运行（full2 在 `b10ae47fa3`、full3 在 `8e2045a58b`，不是同一提交）；handoff §9 仍写“D1、D2 已交设计会话，在收到决定前不改代码”。本会话无法确认 §15.4 的转达是否送达实施会话；无论原因，这两项都是 FE4a 退出条件的一部分（§5.2），列为 G5，本报告 §4 G5 即为转达。

## 4. 需要修复（阻塞）

- **G1（产品回归：§16.2 一次加载）：** 恢复 `let loaded` 与重读分支末尾的 `loaded = reloaded;`，使候选、选择引用与显示的方案都来自第二次读取。把 P-B4 的 B4b（`refs/review/fe4a-rr1/probe-b4`，提交 `f23ea71823`）并入 `archive-validation.spec.ts`，或在 B4 中加同样的断言：第一次预检要能与第二次在界面上区分开。用 P-B4（未修复，应失败）与 P-B4fix（应通过）复验。改动只在对话框的竞态路径，J1/J2 不能确定地覆盖，不需要追加真实旅程调试运行；证据运行的完整集照常覆盖其余部分。
- **G2（F3 用例区分力）：** 两条用例改为：
  - 集合未变的接受：等接受对话框关闭、第 3 次预检请求发出且读取完成（“正在读取归档候选并预检…”消失、“预检状态”可见）之后，再断言集合变化提示为 0。现在的断言在归档对话框尚未重新出现时就会通过；
  - 加载失败：让 409 之后紧接的那一次重新预检失败（在点“确认关闭”之前设 `previewForbidden = true`），恢复后重新预检，再断言冲突提示为 0。现在的用例中 409 之后的重读已经成功并清除了 `pendingNotice`，后面的失败不经过被修复的路径。
  可直接采用 P-F3s（`refs/review/fe4a-rr1/probe-f3s`，提交 `d7a2f07522`）中的两条用例替换。用 P-F3s-a、P-F3s-b 复验：各自对应的用例必须失败。
- **G3（回源脚本长度检测）：** 先找出所有长度 ≥ 7 的连续十六进制串（`7a6520620b` 的 `FULL_RE` 做法），再按长度分流：7–12、40 位按 git 对象核对，64 位按 SHA 核对，其他长度报 `abnormal length` 并非 0 退出；截断写法照旧排除。P-H7 的三种副本（63、39、13 位）都应 exit 1；P-H1–P-H6 重新正反复验一次。kickoff §3.8 与 §11.2 第 4 项都要求“报告长度不是 7–12、40、64 的值”。
- **G4（回源记录）：**
  - 改正 handoff §4 的 probe-c2 树号（`7ea7df7c48`），并给探针提交 `bf792803a2` 建 ref（例如 `refs/archive/fe4a/probe-c2-selfcheck`）。本会话已在开发主机与 07 审核仓库建 `refs/review/fe4a-rr1/impl-probe-c2-selfcheck` 临时保留它；
  - `--allow` 只用于确实不是 git 对象的值（例如入口日志名中的 PID `3259501`）；提交号与树号一律按 git 对象核对；
  - handoff 的回源一节逐字记录完整命令（含全部 `--evidence-file`），回源输出写入日志，日志开头记录命令、hostname、HEAD 与时间，并记日志 SHA256；
  - 可选：脚本在输出开头打印自身参数，使输出本身可复现。
- **G5（修订 4 的 F10、F11，按 kickoff §15.4 并入本轮）：**
  - **F10：** 按 kickoff §3.8 实现 `frontend/scripts/compare-screenshots.py`（输入、逐文件判定、两个常量上限、输出格式、`--stable` 与比较模式、`--self-test` 的全部用例），在 07 上做 §3.8 的节点复验（H/I、H/R、R/S 稳定性模式都 exit 0；`fe4a-review/fe3c-04-copy` 与 `fe4a-review/full1` 比较为 30 张内容变化、2 张尺寸不同、7 张噪声），结果写入 handoff。在最终修复候选上、07 上连续两次模拟接口全量（经 wrapper，`GATEWAY_FE_TEST_WORKERS=2`），以稳定性模式比较，作为 §7.3 第 ① 次；用比较模式生成 FE3c 证据截图到最终候选的变化清单，按原因分组，作为 §7.3 的看图清单（取代 handoff §5 的手工表）；
  - **F11（C12）：** 按 kickoff §15.2 的五条规则修改审核模式顶栏与 V12 数据，五条各有用例；第 4 条的断言加在截图 helper 中，适用于全部截图；`fe3b-d*-review-topbar`、`fe3c-review-expired`、`fe3c-review-closed` 与脚本找出的其他审核顶栏变化列入看图清单。用 §15.2 的两个探针自验（错误提示放回按钮行时，第 4 条的断言在 V11 或 V12 失败；V12 重读状态改回 PENDING 时，第 5 条的断言失败），复审时本会话重跑。C12 不改 `journeys.spec.ts` 与 `t1.spec.ts`，不追加真实旅程或 t1 调试运行（§15.4）。

## 5. 非阻塞

- **N5** F1 用例用 `expect.poll(...).toBe(before + 1)`，一达到就通过；如果第二次点击在第一次读取结束后又排队发起一次读取，计数会在断言之后才变成 `+2`。建议在提示框重新出现后，再用非轮询的断言确认两个计数仍是 `+1`。
- **N6** `.reason-text` 的 `white-space: pre-wrap` 使 `{" "}` 保留下来，“展开/收起”在正文下一行缩进一个空格（`fe4a-c6-reason-*`、`fe3b-d3-manual-close`）。可把 `pre-wrap` 只留在正文 `span` 上，或去掉前导空格；交 owner 看图时一并确认。
- **N7** handoff F9 第 6 项请选定一种：引用开发主机上的 `refs/review/fe4a/debug/*`，或建 `refs/archive/fe4a/*`。第 7 项“t1 占用标记用途应记为 fe3a”与审核报告 N6 的意思相反：N6 说的是 `--suite t1` 不接受子阶段名，标记用途被记成 `fe3a-real-backend-e2e-t1`，只影响记录。
- **N8** handoff §5 的两处归因：`1280/fe3b-d3-review-topbar`（2 像素）是运行间噪声，不是 F2（`ReviewDispositionLine` 没有改）；`1920/fe3b-d3-manual-close` 的差异除了理由单元格，还有组态树“归档基线 1”“提交 1”两行的背景（差异范围 x17–1697、y416–500）：用例在 1280 宽度点击展开控件后切换到 1920，指针落在组态树上，控件位置变了，悬停的行也随之改变。属于 F2 的间接影响，按 G5 用脚本重新生成清单时写明原因。
- **N9** `run-real-backend-e2e.sh` 的 case log 与截图写在 `--log-dir/evidence/`，`--evidence-dir` 只接收 `test-results`。审核报告 §8 第 3 项写的“05 的 t1 用新的 `--evidence-dir`，不覆盖调试运行留下的截图与 case log”，在证据运行时应改为同时用新的 `--log-dir`。
- **N10** wrapper：在“起点不 clean”“节点占用”等早退路径上已写的日志没有 `.sha256` 旁注；文件头第 4 行的注释语句不通。都不影响结果，可顺手修正。
- **N11** 关闭成功后，关闭理由输入框与“我已了解”复选框仍可编辑（已没有提交按钮，不产生请求）。可改为只读，交 owner 看图时一并确认。
- **N12** 回源脚本的两个启发式会误报正确的写法（本会话为本报告回源时遇到，见 §9）：① 名字识别不含 `.sh`、`.py`，不带 `/` 的脚本名不参与配对，同一行的 SHA 会配给别的名字；`J1/J2` 这类带 `/` 的普通文字被当成路径；② 类型核对取离值最近的“树/提交”字样，距离从值的起点算，写在值后面的标签常被前面另一个标签抢走。建议随 G3 一并改：名字只认表格单元格与“`路径` SHA256 `值`”两种写法，类型标签只认紧邻值的写法。

## 6. 代码质量

除 G1 外，改动集中，与 handoff 描述一致。`ReasonText` 的 `useLayoutEffect` 依赖 `children`，每次渲染都会重新挂接 `ResizeObserver`，目前无害。G1 这类“顺手改写”的改动应在 handoff 中逐项列出：本轮的 `const loaded` 很可能是为了消除重新赋值而改的，结果丢掉了一行有业务含义的赋值。

## 7. 下一步

1. 实施会话按 §4 G1–G5 修复，提交 fix2 handoff `docs/frontend-vnext/fe4a-handoff-fix2.md`，由本会话复审第 2 轮。复审时重跑 P-B4/P-B4fix、P-F3s-a/P-F3s-b（或实施会话并入后的同等用例）、P-H1–P-H7、§15.2 的两个 C12 探针、比较脚本的自检与节点复验，并做第 ② 次稳定性比较（本会话独立全量与实施会话第 ① 次中的第一次比较）。
2. 修复期间的运行：focused 单测与模拟接口用例；最终修复候选上 07 连续两次模拟接口全量（`GATEWAY_FE_TEST_WORKERS=2`，经 wrapper）。不追加真实旅程与 t1 调试运行。
3. 复审通过后的证据项不变（审核报告 §8 第 3 项与 kickoff §7.2 FE4a 证据行），另按 §7.3 做第 ③ 次稳定性比较；05 的 t1 同时用新的 `--log-dir` 与 `--evidence-dir`（N9）。
4. 带入 FE4b：N5（审核报告）照旧；D2 已由 C12 在 FE4a 处理，不再带入。

## 8. 本会话的遗留

- 开发主机：`refs/review/fe4a-rr1/probe-{b4,b4fix,f3a,f3b,c2r,f3s,f3s-a,f3s-b}` 与 `refs/review/fe4a-rr1/impl-probe-c2-selfcheck`（实施会话的 `bf792803a2`，经 bundle `fe4a-rr1-impl-probe-c2.bundle` SHA256 `7acdca5a5db9c858ad0e312e40312da46da9b631473ed683acefa0cb16aa63c0` 取回）；bundle `/home/dev/gdds-bundles/fe4a-rr1-probes{,2,3}.bundle`；临时探针 worktree 已删除。本报告提交在短分支 `fe4a-review`，随 FE4a 退出合入 main。
- 07：同名 `refs/review/fe4a-rr1/*`；worktree `/home/dev/gdds-fe4a-rereview1` 与 `/home/dev/gdds-fe4a-rr1-probe-{b4,b4fix,f3a,f3b,c2r,f3s,f3s-a,f3s-b}`；日志 `/home/dev/gdds-fe-logs/fe4a-rereview1/`；截图 `/home/dev/gdds-fe-shots/fe4a-rereview1/full1`（第 ② 次稳定性比较与复审第 2 轮需要）。审核会话原有的 `fe4a-review*` worktree、日志与截图未改动。保留到 FE4a 退出。
- 07、05 上没有本会话留下的占用标记。本会话没有在开发主机上运行测试，没有推送，没有改 `fe-vnext`。

## 9. 本报告的回源

在开发主机上用候选的回源脚本（只读对照，kickoff §3.8）核对本报告。来源：07 现场重算的清单 `report-sources-07.sha256`（本会话全部日志、脚本、输出、截图清单与 bundle），05 现场重算的 J1/J2 四个文件，开发主机上的 bundle，以及取回的 05 J1/J2 入口日志与 07 full3 入口日志原文（`--evidence-file`，提供工具链、依赖镜像身份）。git 对象在开发主机 `/home/dev/gdds-fe` 中解析（`bf792803a2` 已经 bundle 取回）。`--allow` 只用于四个不是 git 对象的值：入口日志名中的 PID `3259501`、本报告引用的错误值 `7ea7df7c9d`、镜像 tag 后缀 `578e079b762e` 与 `6dc9659f0aee`（已在 05 入口日志的镜像标签中核对）。

结果：exit 0，`OK: 73 distinct full token(s), 1 truncated form(s)`，23 处“路径 + SHA”配对一致；唯一的截断写法是 §2.4 的工具链 config digest，完整值见 05 入口日志的 `toolchain_identity`。为通过脚本的配对与类型启发式，本报告若干句子改写了措辞（N12）。命令、来源清单与输出复制到 07 `/home/dev/gdds-fe-logs/fe4a-rereview1/report-hex/`。
