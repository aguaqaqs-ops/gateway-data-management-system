# FE4a fix3 handoff

- 基线：`919e22d4745b7238bf7f91e90fd587ed823dfa9e`（`fe-vnext`，fix2 handoff）
- 代码候选：`268b24f4b472c9846faaff25c29dd2c84a32833d`
- handoff 提交：本文件所在提交，由 `refs/fe4a/fix3` 指向；其父为 C0（见 §2）
- 运行节点：`ct109-gw-dms-07` / `gw-dms-07.lan`
- 范围：K1、K2、K3、N13；N16 按说明记录；N14 未做。未改 `frontend/src/`。

## 1. 结论

- K1：`frontend/scripts/compare-screenshots.py --self-test` 覆盖行过滤 0–4，逐行全像素比较；原脚本 exit 0，四个变异全部 exit 1。见 §4。
- K2：规则 4 的溢出断言已加到 `upload-mode.spec.ts` 的截图 helper；只豁免 `fe3b-w4-approved-withdraw`，1280 与 1920 都溢出 12 px（1292/1280、1932/1920）。两个探针分别验证“去掉豁免则 W4 失败”和“人为溢出则断言失败”。见 §5。
- K3：回源日志头增加 UTC、`handoff`、`handoff_HEAD`、`handoff_sha256`，原 `--repo` 的 HEAD 改为 `repo_HEAD`；核对逻辑未改。15 个 P-H 用例与两个 `--self-log` 用例结果与 fix2 语义一致。见 §6。
- N13：审核仓库的 fix2 c12 探针 ref 已从 `6c2ddb7097c93ca9be0431b2587b0e3a874c885f` 更正为 `5a1f32bf5e6f60fe239d73b4c0a7577c4bd304c4`。见 §7。
- 最终候选两次全量均 96/96、exit 0；`--stable` exit 0，内容变化/尺寸不同/缺失均为 0；FE3c 对比的非噪声集合与 fix2 逐文件相同。见 §8。

## 2. 提交链与树

| 提交 | 说明 | `frontend/` 树 | `vnext/` 树 |
| --- | --- | --- | --- |
| `919e22d4745b7238bf7f91e90fd587ed823dfa9e` | fix2 handoff（基线） | `e2f0a80fd5f7497071d149c376f673b19ac5be73` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `e5f5af58c74dc01c15dd9e8f70316b5e513b73d3` | K1：self-test 覆盖 5 种行过滤 | `f641a07c2b4ac738bf64ed368ef7bbfd2d792ee0` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `d90eeccb9adea33989d4025a001b2e91c2ad0dbf` | K2：收窄规则 4 豁免 | `be4cad7db39cca1e13bd51d647db5b0aa7d6a640` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `268b24f4b472c9846faaff25c29dd2c84a32833d` | K3：回源日志头 provenance | `802bdfb1a42b5319b483f3c4324d2b609a1b57b0` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| C0 | handoff 草稿（去掉 log-SHA 行，用于 L0） | `802bdfb1a42b5319b483f3c4324d2b609a1b57b0` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| 本文件所在提交 | handoff 最终提交，`refs/fe4a/fix3` 指向它 | `802bdfb1a42b5319b483f3c4324d2b609a1b57b0` | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |

C0 与最终提交都只改 `docs/frontend-vnext/fe4a-handoff-fix3.md`，所以两者 `frontend/`、`vnext/` 树与代码候选 `268b24f4` 相同。本文件无法在正文写入自身提交号；最终提交号见交付回复和 `refs/fe4a/fix3`。

## 3. 改动路径与逐 hunk

`git diff --name-only 919e22d4745b7238bf7f91e90fd587ed823dfa9e <handoff 提交>`：

```
docs/frontend-vnext/fe4a-handoff-fix3.md
frontend/e2e/upload-mode.spec.ts
frontend/scripts/check-handoff-hex.py
frontend/scripts/compare-screenshots.py
```

逐 hunk：

1. `frontend/e2e/upload-mode.spec.ts`（+16，单个 hunk `@@ -47,12 +47,28 @@`）
   - 新增 `expectNoHorizontalOverflow(page)`，读 `document.documentElement.scrollWidth` 与 `window.innerWidth`，断言前者不大于后者，失败消息带两个值。
   - `screenshot()` 的每个宽度循环里，在 `settleAfterResize()` 之后、`page.screenshot()` 之前调用该断言；仅当截图名为 `fe3b-w4-approved-withdraw` 时跳过。
   - 注释写明 N5：`.disabled-reason` 超出容器，该截图名在 1280 与 1920 都溢出 12 px（1292/1280、1932/1920），只豁免这一名字，交 FE4b。
2. `frontend/scripts/check-handoff-hex.py`（+9/-1，两个 hunk）
   - 增加 `from datetime import datetime, timezone`。
   - `main()` 头部增加 UTC 时间、`handoff` 绝对路径、`handoff_HEAD`（`git -C <handoff 所在目录> rev-parse HEAD`，失败写 `not a git worktree`）、`handoff_sha256`（文件 SHA256）；原 `HEAD` 行改名 `repo_HEAD`。核对与分类逻辑未动。
3. `frontend/scripts/compare-screenshots.py`（+28/-7，三个 hunk）
   - 文件头分类说明改为：`相同` 是解码后的像素完全相同（字节不同但解码结果相同也归入此类）；`尺寸不同` 是 width、height 或通道数不同；`缺失` 是只在一侧存在。
   - `decode_png()` 记录每行 filter type，返回值增加 `filters`。
   - `self_test()` 用 7×5 RGBA 渐变图替换旧的 6×6 图；`make_png()` 的 `y % 5` 使五行分别使用过滤 0、1、2、3、4；断言 `filters == [0,1,2,3,4]`、逐行解码像素与原像素全等、每行与上一行不同。

## 4. K1：5 种行过滤的 self-test

实现见 §3 第 3 项；判定逻辑、`DIFF_PIXEL_LIMIT=100`、`COMPONENT_SIZE_LIMIT=16` 与输出格式未改。`--self-test` 在 07 的候选 worktree 上运行：

```
python3 -I frontend/scripts/compare-screenshots.py --self-test
```

结果 exit 0，输出 `self-test: ok`；日志 `/home/dev/gdds-fe-logs/fe4a-fix3/k1-selftest.log`，SHA256 `b8ed9769688118577dab7a5190e37e97a8ed7e07ec11d37638e9d44b32c03672`。候选脚本 SHA256 `0887a45ecbac9c9d21ec5b0217859f05e565d0198068112cd4ddfcd03ec68eb8`。

四个变异各复制一份脚本，只把对应过滤类型的预测项替换为 `output[index] = output[index]`（做法同复审报告 §2.3）：

| 变异 | 去掉的预测项 | 预期 | 实际 | diff SHA256 | 日志 SHA256 | 变异脚本 SHA256 |
| --- | --- | --- | --- | --- | --- | --- |
| mut1 | filter 1 的 left | exit 1 | exit 1；`row filter 1/2/3/4 pixels` | `eed94d8c7bf6cb42c7bdb981badcd5ddd3f4f39b2e4738d8eb846d1400e7ea4a` | `d71724498b96cd83040cf9174599ff4a2e6a25c708944d890fa5e3bf49706dbf` | `9dc30b134b97043637791ef890d48fe560d3b13672cd58dbc4b32ff0818c709f` |
| mut2 | filter 2 的 up | exit 1 | exit 1；`row filter 2/3/4 pixels` | `230bc8bb6e12b59d88fd68c37c4734b2d7a5fc3104064266a402cb869b22df82` | `771076577d524edd03a39ea862aff841513bcf32e99b1d9dd9b782caad41c5a2` | `85517fc6b030b1f58c92ede9bd67be4d11f76b92cbd8d17297a4a0693a216c0d` |
| mut3 | filter 3 的 up-left 平均 | exit 1 | exit 1；`row filter 3/4 pixels` | `d3ae07a63df8101fba431372974e58cb05c34b049a33a679f23e9ef971bcbb52` | `0670cec3d3b59b391920ee2222aae065ebfd5f1ae30605073168f93a7eddf837` | `2581b430edf887f48550c1da55b972ebac067fa721c6a0b0f234d4233bd7bbda` |
| mut4 | filter 4 的 Paeth | exit 1 | exit 1；`row filter 4 pixels` | `21c112d88abb24100a581b8f88ee768fdaaa2f82a35adc7c0c94d9f6fb2a1db9` | `9faf7c7dddd9d8ecebc2abb1bcf298236b908e92c41d2d5f67cdc3d36e57ef21` | `d6dc479bce8ee960bc7b344f2d32a0907dd2883ef14387d1ddee03a9cfc38ecb` |

四个变异均 exit 1（exit 文件均为 `1`），原脚本 exit 0。日志与 diff 都在 `/home/dev/gdds-fe-logs/fe4a-fix3/`。

**N16：** 采用“在说明中写明现行做法”，未把实现改成字节相等。`相同` 仍按解码后的像素逐值相同判断；字节不同但解码相同的两张图归入 `相同`。这样不改分类结果、两个上限与输出格式；差异说明见 §3。

## 5. K2：规则 4 豁免收窄

`upload-mode.spec.ts` 的截图 helper 现在与 `workspace-shell.spec.ts`、`archive-validation.spec.ts` 使用同一断言；除 `fe3b-w4-approved-withdraw` 外，27 个截图名在 1280/1920 都会先检查横向溢出。只改测试，不改 `frontend/src/`、预览页顶栏、样式或上限。N14 未做：`if (!screenshotDirectory) return;` 仍在断言之前，因此溢出断言只在设置 `GATEWAY_FE_SCREENSHOT_DIR` 时执行；本节的探针与两次全量都开了截图。

探针（都基于 `268b24f4`）：

| 探针 | 提交 | `frontend/` 树 | ref | 预期 | 实际 | 日志 SHA256 |
| --- | --- | --- | --- | --- | --- | --- |
| 去掉豁免 | `356e9e5a18e9e31621814e618368c1503ce60de6` | `b3c3eda5c866aabbfe20d8dfb9cf5a8a6d187c32` | `refs/review/fe4a-fix3/probe-no-exemption` | W4 失败 | exit 1；`W4 已通过提交不能撤回也不能上传`，`页面横向溢出：scrollWidth=1292 innerWidth=1280` | `0c9908cb41014c8e6e7fb29d60b2959a2b3d7d37089f5a463408e546d4c897f6` |
| 另一个截图状态人为溢出 | `837354330f01b4a6ee783c12aed38bedd5f9b206` | `626885f640d3133d3bde27852c8bb6ba5d638b86` | `refs/review/fe4a-fix3/probe-injected-overflow` | W1 断言失败 | exit 1；W1/W2 失败，`页面横向溢出：scrollWidth=3000 innerWidth=1920`；95 passed / 1 failed | `40d1fe1f39fae4a37b0f3e4a716e789ea308664418ebe0ff96e1333403f55da7` |

人为溢出是在 W1 截图前临时设置 `document.documentElement.style.minWidth = "3000px"`，只改探针测试，不改产品。候选本身两次全量 96/96，`upload-mode.spec.ts` 的 W1/W2、W3、W4、W8、W10（两个）、D1–D5、F3、W5、W6（四个）、§6.1（两个）全部通过。探针 worktree 保留在 `/home/dev/gdds-fe4a-fix3-probe-noexempt`、`/home/dev/gdds-fe4a-fix3-probe-overflow`。

## 6. K3：回源日志头

`check-handoff-hex.py` 现在在输出开头依次记录：`utc`、`argv`、`hostname`、`cwd`、`handoff`、`handoff_HEAD`、`handoff_sha256`、`repo`、`repo_HEAD`。`handoff_HEAD` 用 `git -C <handoff 所在目录> rev-parse HEAD` 取得；不在 git 工作区时写 `not a git worktree`。`handoff_sha256` 是 handoff 文件的 SHA256。核对、配对、对象类型和 `--allow` 逻辑未改。候选脚本 SHA256 `fa6e20f45dc05370dc671f154cb540ed23d1222747f7f49322e2404dfe676efb`。

P-H 用例复用 fix2 的测试文件 `/home/dev/gdds-fe-logs/fe4a-fix2/hex-probes/`，在 07 上重跑。P-H1/P-H2/P-H6 的正例需要 `--source-dir /home/dev/gdds-fe-logs/fe4a-fix2/hex-probes`，否则 64 位值会因没有来源而失败；P-H3 无来源用例故意不给来源；P-H3 evidence 用 `--evidence-file .../evidence.txt`；P-H4/5/7 只需 `--git-objects --repo /home/dev/gdds-fe4a-impl`。结果：

| 用例 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- |
| P-H1 正确 64 位树/提交 | exit 0 | exit 0 | `5a59cf2ed5de77868595fe2cb0d7327d34248b126761d057006da9078d3bc57e` |
| P-H1 改错一位 | exit 1 | exit 1；pairing mismatch | `be2ed42c50f449bd8e1b042b1994bd837f3c14ea78a8291b282bc24b70e7f8fd` |
| P-H2 两对正确 | exit 0 | exit 0 | `ce853a3d3068971d217ca02521879082b83251b096368429886c849bc6cf0517` |
| P-H2 互换 | exit 1 | exit 1；pairing mismatch | `adf7a48c4193e8ff3c409c0c62413a97daacbf191efe662708d19521db46d299` |
| P-H3 无来源 | exit 1 | exit 1；unverified sha256 | `0a21f783f4885a9bdbc58af81017fffdc65e762e8c862d0c747e35d369351eef` |
| P-H3 加 evidence | exit 0 | exit 0 | `f38d474ca2a7951f297a13bfc10a3bcb19df6c435777ecf5f7aab74de776223e` |
| P-H4 正确 10 位提交 | exit 0 | exit 0 | `35625601ff039522b8cc641fc518deeca3f23d69acbf9ad48d724787503324b3` |
| P-H4 改错一位 | exit 1 | exit 1；unresolved git object | `28aaab0bac660f857984deba84b41ff796cb6df6c3fc1d19f1219a67caa7f187` |
| P-H5 正确树 | exit 0 | exit 0 | `0fa8885bb5804060c815822a94d422360a96f49408ecbb84a9e53d5e481cf3e8` |
| P-H5 提交号标成树 | exit 1 | exit 1；object type mismatch | `7c6e73a37d9f1116abe93cc60980203512812c413136272d4b187686273fc8f8` |
| P-H6 两对正确 | exit 0 | exit 0 | `74a959a0c8243016ee3c6b1cb548a357599098e3ca212975dd38770cede0d797` |
| P-H6 互换 | exit 1 | exit 1；pairing mismatch | `2a329b184e26a248344c8b78f347a6cb9d0a3a61de4dcedd630609d17b00f774` |
| P-H7 63 位 | exit 1 | exit 1；abnormal length 63 | `3834d6a21222cec7f17494eadeb9ed4bfb24e03af92a37dbb38cc3489ca69063` |
| P-H7 39 位 | exit 1 | exit 1；abnormal length 39 | `d49edb5e16170a4324d166e7c1b228570138c6a3a31bd6a81ba94f7a57b5475a` |
| P-H7 13 位 | exit 1 | exit 1；abnormal length 13 | `58938554db75bdf29dfbe8c7fdb8a46691c404786a539ffb40acf77d8c65a49e` |

`--self-log` 两个情形：

| 用例 | 构造 | 预期 | 结果 | 日志 SHA256 |
| --- | --- | --- | --- | --- |
| 自记哈希改一位 | 同一行有 `hex-handoff.log` 与改过一位的 64 位值，无其他 token | exit 0 | exit 0；`0 distinct full token(s)` | `a3445ba6f5518d2dd2b1a2f5835238d0ac74615124f195fb7b407a0d101156f6` |
| 同行另一对配对错误 | 同一行另有 `pair-b.png` + 错误 SHA256 | exit 1 | exit 1；`pairing mismatch ... pair-b.png on-site sha256 is 0bda... handoff says be169...` | `c7c7050bf5fb479db48948306edf34fb0d22cbd576740a80b0b63e7ec71aa431` |

测试文件在 `/home/dev/gdds-fe-logs/fe4a-fix3/hex-probes3/`；每个用例的完整日志同名 `.log`。

### 6.1 自引用说明

K3 后日志头包含 handoff 文件的 SHA256。若把该日志自身的 SHA256 写进 handoff，handoff 哈希随之改变，日志头即失效；这是一个没有固定点的循环。处理方式：

1. H0 是最终文件去掉 §9 的 log-SHA 行；提交为 C0。在 H0 上运行得到 L0，L0 头记录 `handoff_HEAD=C0`、`handoff_sha256=SHA(H0)`。
2. H1 插入 L0 与本节说明，提交为最终 handoff 提交（`refs/fe4a/fix3`）。在 H1 上复跑得到 L1，exit 0；L1 头记录最终提交与 SHA(H1)。
3. 本文件记录 L0 的 SHA256；L1 的 SHA256 在交付回复中给出，不写入本文件，否则会再次改变哈希。L0 是 H0 的完整回源日志，H1 相对 H0 只增加 L0 这一行、C0 行和本节说明；H1 的最终复跑 exit 0 已覆盖这些增加。

## 7. N13：c12 探针 ref 更正

07 审核仓库 `/home/dev/gateway-data-management-system` 中，`refs/review/fe4a-fix2/probe-c12-error-in-row` 原先指向 `6c2ddb7097c93ca9be0431b2587b0e3a874c885f`（与 worktree `/home/dev/gdds-fe4a-fix2-probe-c12err` 的 HEAD `5a1f32bf5e6f60fe239d73b4c0a7577c4bd304c4` 不符）。已执行：

```
git -C /home/dev/gateway-data-management-system \
  update-ref refs/review/fe4a-fix2/probe-c12-error-in-row \
  5a1f32bf5e6f60fe239d73b4c0a7577c4bd304c4
```

更正后 ref 与 worktree 一致；该提交的说明是 `probe: probe-c12-error-in-row`，`frontend/` 树 `b221b4b38200b2f6ca8e99eba6c019ced6b31ebe`。`refs/review/fe4a-fix2/probe-c12-overflow-only` 仍指向 `6c2ddb7097c93ca9be0431b2587b0e3a874c885f`，未改。fix2 handoff 原文不改，由本文件记录更正。

## 8. 最终候选的两次全量与比较

### 8.1 运行记录

两次都在 07 的 clean、已提交 worktree `/home/dev/gdds-fe4a-impl`，HEAD `268b24f4b472c9846faaff25c29dd2c84a32833d`，`GATEWAY_FE_TEST_WORKERS=2`，入口 `run-tests.sh -- --e2e`。命令形态：

```
cd /home/dev/gdds-fe4a-impl
GATEWAY_FE_TEST_WORKERS=2 frontend/scripts/run-evidence-wrapper.sh \
  --session fe4a-fix3-full1 \
  --worktree /home/dev/gdds-fe4a-impl \
  --entry run-tests.sh \
  --log-dir /home/dev/gdds-fe-logs/fe4a-fix3 \
  --shots-dir /home/dev/gdds-fe-shots/fe4a-fix3/full-run1 \
  -- --e2e
```

第二次只把 `--session` 改为 `fe4a-fix3-full2`、`--shots-dir` 改为 `full-run2`。

| 项 | 第一次 | 第二次 |
| --- | --- | --- |
| hostname | `gw-dms-07.lan` | `gw-dms-07.lan` |
| 起止 UTC | `2026-11-10T17:23:34Z` – `17:26:16Z` | `2026-11-10T17:26:22Z` – `17:29:04Z` |
| 入口起止 UTC | `2026-11-10T17:23:57Z` – `17:26:16Z` | `2026-11-10T17:26:44Z` – `17:29:04Z` |
| 起止 HEAD | `268b24f4b472c9846faaff25c29dd2c84a32833d` / 同左 | 同左 / 同左 |
| worktree 状态 | clean（起止） | clean（起止） |
| exit | 0 | 0 |
| 测试 | 96 passed（35 个测试文件） | 96 passed |
| wrapper 日志 | `/home/dev/gdds-fe-logs/fe4a-fix3/fe4a-fix3-full1-run-tests-20261110T172334Z.log`，SHA256 `dadaa79d3e62df76c3cbade26dc0d0b1b38de5bde720d88f6a4c66168c58d1e1` | `.../fe4a-fix3-full2-run-tests-20261110T172622Z.log`，SHA256 `a6639aa2287f18e0a11b39b5061c19be881e93e87fb83f85169641526ea6af0e` |
| 入口日志 | `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261110T172357Z.log`，SHA256 `88cf88ce82bf85c160374e7e845180f0bde907786fb19ce9b9e6e11b8016ccba` | `.../frontend-tests-20261110T172644Z.log`，SHA256 `74c59a5f89f2d63acf022f24c9ba98f818537925e032cd8b18e19c5118e60f21` |
| 截图目录 | `/home/dev/gdds-fe-shots/fe4a-fix3/full-run1`，198 个 PNG | `/home/dev/gdds-fe-shots/fe4a-fix3/full-run2`，198 个 PNG |
| 清单 | `shots.sha256`，SHA256 `50cc7a977b05ab508bd9958ccdcf47c646b2f42eb945753f7e800304de9ce994` | `shots.sha256`，SHA256 `6a190b762b6a0966b9436a8d61fbcee1e96fa4a5d95f0dc8fecf1071b57a944c` |

工具链与缓存（两次相同）：

- 镜像 `mcr.microsoft.com/playwright:v1.64.1-noble`，config digest `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`。
- RootFS DiffID：`sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278`、`sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07`、`sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9`、`sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d`、`sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc`、`sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5`、`sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb`。
- `docker_network=none`；npm 缓存 `/home/dev/gdds-fe-cache/frontend/npm-cache`，来源归档 `npm-cacache.tar.gz` SHA256 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，`npm_cache_source_commit=unknown`，`package_lock_resolved_count=305`。
- `tracked_frontend_archive_sha256=c7de453b43fd5b023f0715d3ea1755bb90b43f9afee5ba6216e86a4d6718d347`；`e2e_workers=2`。

### 8.2 `--stable`

```
cd /home/dev/gdds-fe4a-impl
python3 -I frontend/scripts/compare-screenshots.py --stable \
  /home/dev/gdds-fe-shots/fe4a-fix3/full-run1 \
  /home/dev/gdds-fe-shots/fe4a-fix3/full-run2
```

exit 0，末行 `合计 内容变化=0 尺寸不同=0 缺失=0 噪声=15 相同=183`；日志 `/home/dev/gdds-fe-logs/fe4a-fix3/cmp-run1-vs-run2.log`，SHA256 `59edbeed8ef37c6b0e3083b91bcabf59f0067af2b064daa48decd416b4b6b254`。15 个噪声文件是像素差不超过上限的截图（最大 `history-compare-result-drawer-1280.png`，59 个不同像素、最大连通块 14）。

### 8.3 FE3c 证据集合复核

```
python3 -I frontend/scripts/compare-screenshots.py \
  /home/dev/gdds-fe-shots/fe4a-review/fe3c-04-copy \
  /home/dev/gdds-fe-shots/fe4a-fix3/full-run1
```

exit 0；`内容变化=38 尺寸不同=4 缺失=8 噪声=8 相同=140`；日志 `/home/dev/gdds-fe-logs/fe4a-fix3/cmp-fe3c-vs-run1.log`，SHA256 `114c7fe7427dd43985dd5b9b9e74872d645dd2d0b366ea17b928c38dc51d03f2`。

按 `路径 + 分类` 排序后与 fix2 的 `/home/dev/gdds-fe-logs/fe4a-fix2/cmp-fe3c-vs-run3.log` 逐文件比较：38 个内容变化、4 个尺寸不同、8 个缺失完全一致，差异只在噪声集合。fix2 是 7 噪声/141 相同，fix3 是 8 噪声/140 相同；fix3 新增噪声 `1280/fe3b-w10-stale-workspace.png`、`1280/fe3b-w8-upload-disabled.png`、`archive-mainline-result-1280.png`、`review-permission-denied-1920.png`，减少噪声 `1280/fe3b-withdraw-none.png`、`s2-compare-tray-1920.png`、`workspace-error-no-connected-1280.png`。非噪声集合没有增减或改类，fix2 §6.4 的分组不需要重做。

## 9. 回源

### 9.1 命令与结果

最终提交（H1）上的命令，逐字为：

```
cd /home/dev/gdds-fe4a-impl
python3 -I frontend/scripts/check-handoff-hex.py \
  --handoff docs/frontend-vnext/fe4a-handoff-fix3.md \
  --git-objects --repo /home/dev/gdds-fe4a-impl \
  --sha-file /home/dev/gdds-fe-logs/fe4a-fix3/handoff-sources.sha256 \
  --self-log hex-handoff.log \
  > /home/dev/gdds-fe-logs/fe4a-fix3/hex-handoff-final.log 2>&1
```

H0/C0 上的命令相同，只把 `--handoff` 指向 H0、输出改为 `hex-handoff.log`，并得到 L0。L0 的 `handoff_sha256` 是 SHA(H0)，`handoff_HEAD` 是 C0；最终 L1 的 `handoff_sha256` 是 SHA(H1)，`handoff_HEAD` 是最终提交。

结果：L0 与最终复跑都 exit 0；`--allow` 未使用（提交号、树号都是 git 对象，其余 64 位值都有 `handoff-sources.sha256` 或 `--source-dir` 来源）。L1 的 SHA256 在交付回复中给出；L0 的 SHA256 见下方 `log-SHA` 行。

### 9.2 自记日志

本次回源日志（在 H0/C0 上运行）`/home/dev/gdds-fe-logs/fe4a-fix3/hex-handoff.log`，SHA256 `（L0 待插入）`。

H0 的 SHA256 为 `（H0 SHA 待插入）`；C0 见 §2。

## 10. 已完成、未测、未决

**已完成**

- K1 的五种行过滤 self-test、逐行全像素比较、四个变异自验。
- K2 的 helper 断言、单截图名豁免、两个失败探针与候选全量通过。
- K3 的日志头字段、P-H1–P-H7 与 `--self-log` 两情形重跑。
- N13 的 ref 更正。
- 最终候选两次全量、`--stable`、FE3c 非噪声集合复核。

**未测 / 未做**

- 真实 backend 旅程、`t1.spec.ts`、`validate-upload-package.sh`、`e2e-real/` 本轮未运行；按任务要求不追加。
- N14 未做：截图 helper 未设置 `GATEWAY_FE_SCREENSHOT_DIR` 时仍提前返回，溢出断言只在开截图时执行；依赖该断言的探针均注明“开截图运行”。
- N15（“收起”缩进）、N11 交 owner 看图；N17 带入 FE4b。
- 未推送，未合入 main；`fe4a-review*`、`fe4a-rereview1*`、`fe4a-rereview2`、`fe4a-rr*-probe-*` 的 worktree、日志与截图均未删改。fix3 的两个探针 worktree 与 `refs/review/fe4a-fix3/probe-no-exemption`、`refs/review/fe4a-fix3/probe-injected-overflow` 保留。

**未决**

- 自引用：最终复跑日志 L1 的 SHA256 不能写进其自身所校验的 handoff（写进去就改变 handoff 哈希）。本文件记录 L0（H0 的日志）并给出 C0/H0 的 provenance；L1 的 SHA256 由交付回复给出。若审核要求 handoff 正文同时包含最终日志哈希，需要另行约定“日志哈希放 sidecar”的格式。
