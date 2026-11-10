# FE3c 证据核对 1

结论：**通过**。04 三项与 05 t1 都在被测提交 `e22e39ba15` 的 clean worktree 上一次通过，没有重做。记录字段齐全；日志、截图与镜像身份都已在节点上重算，结果一致。下一步是 owner 看图（含 M2），然后进行 FE3 exit。

| 项 | 值 |
| --- | --- |
| 证据 handoff | `06b454b0ef3e16a93ed9ecd13cb1a2942030f4d9`（分支 `fe3c-evidence-04`，父提交 `e22e39ba15`，只新增 `docs/frontend-vnext/fe3c-evidence-04.md`） |
| 被测提交 | `e22e39ba1528c7a0339c9c800d87fb3f3f95190a`（测试修复 `e8864ce1da`，产品代码 `cbb14f578c`） |
| `HEAD:frontend` / `HEAD:vnext` | `46e425f84eb28936563c8751295a8829e33f3ad6` / `6368c9c40cf08a97eecf2a0c457a6c16ce448080` |
| 依据 | [停止核对](fe3c-evidence-stop-1.md) §3、§4；[fix2 定向核对](fe3c-fix2-check.md)；[复审第 1 轮](fe3c-rereview-1.md) §6 |

## 1. 提交与 worktree

- `e22e39ba15..06b454b0ef` 只新增 handoff 一个文件（436 行），不改其他文件。
- 分支 reflog 显示，初版 `df6b23bde0` 在 03:16:44 提交，03:17:37 被 `--amend` 成现提交。此前它没有被推送，也没有被任何审核引用，handoff 第 9 节已说明。这次 amend 不违反“不改写已被审核引用的提交”。
- 开发主机：
  - 主工作区仍在 `fe3b-evidence-04`，最后一条 reflog 是 11-09 的提交，没有新的切换；
  - `gdds-fe` 的 `fe-vnext` 在 `e22e39ba15` 之后没有新提交；
  - S5 worktree（main）的最新 reflog 是我的 `5ddd73b962` 快进。

  handoff 写在独立 worktree `/tmp/fe3c-evidence-doc` 中。
- 04、05：
  - 新 worktree `/home/dev/gdds-fe3c-evidence-e22e39ba` 为 detached `e22e39ba15`，树与上表相同，`status` 为空，`legacy` 链接存在；
  - reflog 只有建立时的一条；
  - `refs/fe3c-evidence/e22e39ba15` 指向被测提交；
  - 上一轮 `gdds-fe3c-evidence-031dc3d7` 未动。
- 两节点当前没有占用标记。传输 bundle 已删，04、05 的 `/tmp` 与 `/home/dev` 下都没有 `fe3c-evidence-*.bundle`。

## 2. 节点重算

| 运行 | 节点 | 起止（UTC） | exit | 外层日志 SHA256 | 入口日志 SHA256 |
| --- | --- | --- | --- | --- | --- |
| a `run-tests.sh --e2e --screenshots`，`GATEWAY_FE_TEST_WORKERS=2` | `gw-dms-test-04` | 02:44:09–02:46:44 | 0 | `094c293632b808ebeb282e664833bef9362b30e773c9dd38e837be5867610b5e` | `614da0b7939862a94c323388163defcb647ee5db8020214eabba697d60a10a14` |
| b `validate-upload-package.sh` | `gw-dms-test-04` | 02:52:23–02:53:51 | 0 | `2d32508b870331a1154567e95d871ec506499e36dcf13cc2d1a6f7e38eb710d9` | `dc5e9f387c37fe8e30d3ab1e067b1439b249237f2d1200b802fbe1e7f3fb9aa3` |
| c `run-real-backend-e2e.sh --suite journeys` | `gw-dms-test-04` | 02:54:17–03:02:03 | 0 | `4e5e80d1090436bcfd38dea260e5d0a6becd561c9e02350ab9356000bda94b8b` | `de0b92b98167bb5032b30df95e5bdd8ee858859a0de78717bdc13d8af16f4333` |
| t1 `run-real-backend-e2e.sh --suite t1` | `gw-dms-test-05` | 02:46:55–02:51:05 | 0 | `463a127da189cf2dc52c5b87c1213206d8b509774343ee68778adc954ebb8fa1` | `f8a6387ec016c14e6ec421a79fbf2416ed89fc0329b1cddd61979258b0a70bdb` |

- 上表 8 个 SHA256 与 05 case log `56399d9ffdd8d295cd57c56220fe6b09e7b35f20447c60190a0a19a18a840a45` 都在节点上现场重算，与 handoff 及各自的 `.sha256` 文件一致。
- 04 三项依次运行、没有重叠。05 与 04 是不同宿主，t1 与 a 部分并行，符合 AGENTS。
- 上一轮（`031dc3d754`）的 5 个 SHA256 也在节点上重算过，与[停止核对](fe3c-evidence-stop-1.md) §1 及 handoff §5 一致。handoff 自报的 §5 转抄错误已改正。

## 3. wrapper 记录

- **字段。** 四份外层日志都记录了：
  - hostname；
  - 起止时间；
  - 起止 HEAD、`HEAD:frontend` 与 `HEAD:vnext`，两侧都等于被测值；
  - 起止 `git status --porcelain --untracked-files=all`，两侧都为空；
  - `busy_marker_at_start`（为空）；
  - 入口 `exit_code`（wrapper 用 `set -o pipefail`，退出码在重定向下直接取得）；
  - 入口日志路径与结果字段。

  c 与 t1 另有：
  - 入口脚本自己取得的占用标记（会话名、用途、开始时间、HEAD）；
  - `occupancy_released_at`；
  - `busy_marker_at_end`（为空）。
- **参数检查。** wrapper 在写日志前检查：参数个数；worktree、日志和截图目录都是绝对路径；日志目录存在；截图目录在 worktree 外；没有他人占用标记（用途为计时测量时等待）。上一轮 `LOG_DIR` 的问题不会重现。
- **中途补丁。** 四份 `.sh` 的 mtime 都是 02:51:44Z，晚于 a 结束（02:46:44）和 t1 结束（02:51:05），早于 b 开始（02:52:23）。所以没有在运行中改脚本。补丁只影响运行后列举日志目录文件的循环，不影响入口命令和已有记录。
- **结果字段：**
  - a：`Test Files 34 passed`、`Tests 207 passed`；`Running 86 tests using 2 workers`、`86 passed`；`e2e_workers=2`。
  - b：
    - `RESULT packages=4 failures=0`、`final_stage=done`；
    - 没有设 `GATEWAY_BACKEND_DEPS_IMAGE`，日志解析出 `dependency_image=gateway-backend-deps:lock-578e079b762e`；
    - `required_inputs_match=true`。
  - c：20/20 passed（含 `j1-archive-mainline`、`j2-manual-close`）；`openapi_compare=match`、`cleanup_status=ok`。case log 中 `j2-step4 … statuses=201,200`，与复审第 1 轮相同。
  - t1：
    - 1 passed；`openapi_compare=match`、`cleanup_status=ok`；
    - 两份清单 `cdb598cd…0163`、`fa2450fa…a96a` 各 19 个文件，我在 05 上重新 `sha256sum -c` 通过；
    - `table_count=125`、`composite_changed=0`。
- **日志中的凭据。** 8 份日志中没有 `Bearer`、`Authorization:`、`token=`、`password=`。

## 4. 镜像与缓存身份

在节点上用 `docker image save` 读取 config 与 `rootfs.diff_ids`，不比较 inspect ID：

| 镜像 | 节点 | config digest | DiffID |
| --- | --- | --- | --- |
| `mcr.microsoft.com/playwright:v1.64.1-noble` | 04、05 | `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017` | 7 个，与 handoff §3.1 及各入口日志逐项相同 |
| `gateway-backend-deps:lock-578e079b762e` | 04、05 | `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939` | 19 个，与 handoff §3.2 逐项相同 |
| `gateway-p2r1-repository:lock-6dc9659f0aee` | 05 | `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9` | 16 个，个数与 handoff §3.4 相同 |

- tag 后缀 `6dc9659f0aee` 等于 `e22e39ba15:vnext/repository_service/uv.lock` 的 SHA256 前 12 位。
- 两个 RS 镜像各自在本节点构建。config 不同（04 为 `abd4e7f7…7c36`，05 为 `b16535b4…197f`），但 `org.opencontainers.image.revision` 都是被测提交，`source-tree-sha256` 相同，所以只按各次运行自记的值记录。
- validator 镜像（§3.3）的 13 个 DiffID 与 b 的入口日志一致。
- npm 归档：04 为 `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz`，05 为 `/home/dev/gdds-fe-logs/fe0/npm-cacache-fe0.tar.gz`。两者现场重算都是 `0d861824f807b9d72de3cfff26e3c41bdfae502cdaf39036f38f4fa32c0089f4`，来源提交都是 `a2fb4a027a`。

## 5. 截图

- **清单。** 截图目录为 04 的 `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots`。
  - `shots.sha256` 的 SHA256 为 `63a0e6006952152e7cd59db22ada9b34e4774f4f99676c22041b31f9ea1129f2`，共 190 行；
  - 现场 `sha256sum -c` 全部通过；
  - 清单中的文件与目录中的实际文件一一对应。
- **文件数。** 1280、1920 各 45 张，其中 `fe3c-*` 各 20 张。`fe3c-confirm-disabled-*` 五个名称在两种宽度下齐全。
- **与 07 运行对比。** 与我在 07 上的 fix2 运行（[fix2 定向核对](fe3c-fix2-check.md) §3）文件集合相同。40 张 `fe3c-*` 中有 37 张逐字节相同。
- **1920 下有两对截图逐字节相同：**
  - `fe3c-blocker-no-entry` 与 `fe3c-confirm-disabled-blocked`；
  - `fe3c-confirm-disabled-unknown` 与 `fe3c-disabled-unknown-code`。

  原因是 B7 的这两段与 V7、V1 使用同一场景（`ARCHIVE_INTEGRITY_FAILURE` 阻断、未知编码）和相同视口。这是 B7 汇集禁用原因的设计，不是截图写错文件。07 上同样如此，1280 下两两不同。owner 看图时，这两对只需各看一张。

## 6. 十六进制核对

用脚本把 handoff 中每个十六进制值与来源逐个对照。来源包括：

- 节点现场 `sha256sum`；
- 从节点取回的 8 份日志、`shots.sha256` 与 `docker image save` 结果；
- git 对象。

结果：

- 非纯数字的值共 229 处：
  - 91 处是 git 对象；
  - 126 处是 64 位值，在节点重算结果或日志全文中；
  - 10 处是镜像 tag 后缀等，见于日志。
- 纯数字 10 处，不计入。
- 截断值 4 处（`cdb598cd…0163`、`fa2450fa…a96a` 各 2 处），都唯一回源。
- 没有长度不是 7–12、40、64 的值。
- 配对检查：
  - 截图“路径 + 宽度”与 SHA 配对 40 行；
  - 日志名与 SHA 配对 14 处；
  - `validate-out` 配对 5 行。

  全部一致。
- 唯一不能回源的是 bundle SHA256 `462d6a57…a90a`（§0、§9 各 1 处），因为文件已按要求删除。这不影响证据：两节点的 `refs/fe3c-evidence/e22e39ba15` 与 worktree 的 HEAD、树都等于被测值。

## 7. 非阻塞项（不需要更正提交）

- **E1.** handoff §8 说“补丁前 a、t1 的外层日志各含两条终端告警，对应空 SHA 的 `new_file=` 行”，这只对 t1 成立。
  - t1 外层日志中有 `new_file=artifacts sha256=` 和 `new_file=evidence sha256=`。
  - a 运行时日志目录中还没有子目录，a 的外层日志没有这样的行。

  这是文字问题，不涉及任何 SHA 值。
- **E2.** c、t1 外层日志中，`result_suite_cases_passed=MISSING` 和 `result_suite_cases_failed=MISSING` 是 wrapper 按单个键取值造成的：这三个计数写在同一行，值已在 `result_suite_cases_total=` 行中给出。
- **E3.** 05 上还有实施会话 fix1 阶段的传输 bundle `/home/dev/fe3c-fix1.bundle`。取证提示词只点名了 07 的两份，所以不算违规。在 FE3 exit 清理时删除。

## 8. 下一步

1. **owner 看图。**
   - 截图在 04 的 `/home/dev/gdds-fe-evidence-04/fe3c-e22e39ba/shots/{1280,1920}/fe3c-*.png`。
   - 真实 backend 旅程截图在 04 的 `/home/dev/gdds-fe-logs/fe3c-evidence2-04/evidence/` 与 05 的 `/home/dev/gdds-fe-logs/fe3c-evidence2-05/evidence/`。
   - M2（关闭对话框显示名重复、成功后按钮仍可点击）看 `fe3c-close-dialog`、`fe3c-close-result` 与 `j2-manual-close-*`，决定接受还是列入 FE4。
2. **FE3 exit。**
   - 附注 tag `fe-fe3c-exit` 指向证据 handoff `06b454b0ef`。tag 说明写：被测提交 `e22e39ba15`、`frontend/` 树、04 三项的入口日志 SHA256，以及 t1 的入口日志 SHA256。
   - 先把审核报告合入 main，再以 `--no-ff` 合入 tag。
   - 在 `fe3-kickoff.md` §3.2 写退出记录，带入项为：
     - FE3b 的 N2、N6、N7、N8；
     - Q21；
     - FE3c 的 N2–N5、N7；
     - M1–M4；
     - N9。
   - 清理开发主机与 04、05、07，包括 E3。
3. **推送与节点同步**须经 owner 授权。
