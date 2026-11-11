# FE4a 证据核对第 2 轮

**结论：证据通过。** H（`16f4306306`）上的四项证据各运行一次，全部通过；第 ③ 次稳定性比较 exit 0；证据核对第 1 轮留下的 05-t1 §8.3 逐条核对与 M1 增量已补上，都符合。kickoff §5.2 的 FE4a 退出条件中，只剩 owner 对 §6 各项的确认。另有 3 条非阻塞（§5），都是取证写法问题，值本身已现场核对正确。

- **审核会话：** FE4a 审核会话（会话标签 `fe4a-rereview4`，运行时会话名 `fe4a-review`）。
- **核对时间：** 2026-11-11 05:20–05:40 UTC。
- **方式：**
  - 开发主机只读核对 git 对象，并对取回的日志与清单原文做只读对照；
  - 04、05 上只读核对日志与产物，没有运行测试，没有取占用标记；
  - 07 上做第 ③ 次稳定性比较（只读后处理，`python3 -I`）。
- **04 的占用标记：** 核对时 04 上有占用标记，属于后端 BE-b 会话（`owner.json` 中 `session` 以 `be-b-b5-` 开头），用途“backend stage gate”，05:16 UTC 开始，晚于本轮证据结束（04:53 UTC），与本轮无关。本会话没有触碰它。
- **依据：** [FE4 kickoff](../fe4-kickoff.md) 修订 7（`42f48bea58`）§5.2、§7.2–§7.5、§8 FE4a、§16.5–§16.7；FE3 kickoff §4.6、§8.3、§8.4；[复审第 4 轮](fe4a-rereview-4.md)（`42aeb69336`）§7；[证据核对第 1 轮](fe4a-evidence-check-1.md)（`14f8daa7f8`）§2、§5。

## 1. 被测对象与提交

| 项 | 值 |
| --- | --- |
| 证据提交 H | `16f4306306d082690e612cee4d3c768977447fd9` |
| 证据 handoff 提交 | `c2199b82f7f1ef7c35b09221e8f8eeb8a423f961`，父提交为 H，只新增 `docs/frontend-vnext/fe4a-evidence.md` |
| `frontend/` 树 | `d8e9a2e717e8d153b3a7794f25b76186c4bc4d5e`（H 与 handoff 提交相同） |
| `vnext/` 树 | `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3` |
| `fe-vnext` | 开发主机为 `c2199b82f7`（由 `59c5b8cfca` 快进到 H，再加 handoff 提交），`/home/dev/gdds-fe` clean |
| 节点 | 04、05 的 `refs/fe4a-evidence/16f4306306` → H；两节点 worktree `/home/dev/gdds-fe4a-evidence-16f43063` 的 HEAD 为 H，`git status --porcelain --untracked-files=all` 为空 |
| bundle | 开发主机、04、05 现场重算相同，见表下 |
| 打包流程筛查（§7.4） | `fe-fe3c-exit..H` 的两个打包文件 diff 为空，不触发 t4 |

bundle：`/home/dev/gdds-bundles/fe4a-evidence-16f4306306.bundle` SHA256 `44edc28318a465b042eb18e47c37c6dda049db6c60a198fb21e21f14c4846587`。

## 2. 四项证据

### 2.1 运行与日志

各日志的 SHA256 都在所在节点现场重算，与 `.sha256` 旁注及 handoff 一致。下表的 wrapper 与入口字段取自日志原文。

| # | 结果 | wrapper 日志 | SHA256 |
| --- | --- | --- | --- |
| 04-a | 起止 HEAD 为 H，`frontend/` 树 `d8e9a2e7`，起止 clean；单测 35 个文件 214 项；`Running 96 tests using 2 workers`，96 passed；`exit_code=0`、`entry_exit=0`；198 张截图 | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-run-tests-20261111T043941Z.log` | `088da58cc4fd0834c20d2e4f3b8acfe4a12ae85028a78ff8ad1d9e4c95a1f2f5` |
| 04-b | `dependency_image` 为 `--print-input` 给出的 backend 依赖 tag，config 与预检一致；`RESULT packages=4 failures=0`；`entry_exit=0`；起止 clean | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-validate-upload-package-20261111T044322Z.log` | `b1d4932eab7697969cf0e54811492c200f3ac254a9b3f6bc9f120a7d081094f1` |
| 04-c | `openapi_compare=match`、`suite_exit=0`、`cleanup_status=ok`、`entry_exit=0`、`busy_end=absent`；20/20，`suite_stats_flaky=0`；起止 HEAD 为 H、起止 clean | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/fe4a-evidence-04-run-real-backend-e2e-20261111T044548Z.log` | `94da0b0f3b9430aed5cc86b10639a650be5f05ffb28ec08b2ff907edc2339ce2` |
| 05-t1 | `1 passed (2.9m)`；`openapi_compare=match`、`suite_exit=0`、`cleanup_status=ok`、`exit_code=0`；起止 HEAD 为 H，`frontend/`、`vnext/` 树起止一致 | `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/fe4a-evidence-05-run-real-backend-e2e-20261111T044048Z.log` | `3a450ca0b666f3549f0b0d729201d98d89653c655d0f789c35bd79b4d42d954e` |

| 入口日志 | SHA256 |
| --- | --- |
| `/home/dev/gdds-fe-logs/frontend/frontend-tests-20261111T044003Z.log` | `33fdee3515a3eb4a3958d8afbf5188846c1a2e11b1b8f70696ca85070ab5d1de` |
| `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/entry-upload-validator.log` | `a7dda95ef19204a9adb52190de282517a0dca6999c489a251de15a62cb21ab37` |
| `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/entry-journeys.log` | `70ef17c069e1d4f9655ad950053a2d11feafd44b49541ce9de243bfc285338b1` |
| `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/entry-t1.log` | `3f1a22d78913203f861b634e639bdd4235043a4aa2db9632c5a63a05a27b9d81` |

三份安全名副本与同目录的原名入口日志（带进程号后缀）逐字节相同（`cmp`）。

- **镜像身份：** 04、05 各次运行前的身份文件（`precheck-*/identity-*.json`），与开发主机上回源用的副本逐字节相同：
  - 工具链 config `sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017`，7 个 DiffID；
  - backend 依赖 `sha256:46c00a3b032e93fae3d86b0adb797c16902b0117477b6275c267ab6eec7fe939`，19 个；
  - RS 依赖 `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9`，16 个。

  与复审第 4 轮 07 上导出的工具链身份文件也相同。
- **两节点各自构建的 RS 镜像：** config digest 不同，属本机构建的预期（handoff §4）。

### 2.2 04-c 的异常集合

case log `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/evidence/journey-cases.log` SHA256 `21bc936b4f12ac65dde0ba409d8937d30de05a00fc591394912eca8cc2a635ad`，共 37 行。

取回后由脚本逐行解析 `anomalies=` 与 `business_issues=`。J2 中的身份按第 4 步的 `closed=` 与第 7 步的 `archived=`、`closed=` 对应：B 为第 7 步归档的提交，C 为第 4 步关闭的提交，E 为第 7 步关闭的提交。

| 行 | 步骤 | 项（按身份） | 与 FE3 kickoff §4.6 |
| --- | --- | --- | --- |
| 19 | J1 第 2 步 | GTM `MODIFIED` | 一致 |
| 22 | J1 第 7 步 | BTU、GTM `INITIAL`、GTM `MODIFIED` | 一致 |
| 25 | J1 第 11 步 | BTU、GTM `MODIFIED` | 一致 |
| 27 | J1 第 13 步 | BTU、GTM `MODIFIED`、PIE | 一致 |
| 30 | J2 第 1 步 | GTM `MODIFIED` | 一致 |
| 32 | J2 第 3 步 | ASE [C]、ASE [E]、BTU [B, C, E]、GTM `INITIAL` [B]、[E]，GTM `MODIFIED` [B]、[C]、[E] | 一致 |
| 34 | J2 第 5 步 | ASE [E]、ISU `INITIAL` [E]、BTU [B, E]、GTM `INITIAL` [B]、[E]，GTM `MODIFIED` [B]、[E] | 一致 |
| 36 | J2 第 8 步 | BTU、GTM `MODIFIED` | 一致 |

（GTM＝`GENERATION_TIME_MISSING`，BTU＝`BASELINE_TIME_UNAVAILABLE`，ASE＝`APPROVED_SIBLING_EXCLUDED`，PIE＝`PROJECT_IDENTITY_EXCEPTION`，ISU＝`INITIAL_SOURCE_UNEXPLAINED`。）

- **`business_issues`：** 8 行都等于 `anomalies` 去掉 ASE 与 PIE。
- **证据核对第 1 轮 §5 的未执行部分：** 第 21–29 行（J1 第 4 步起）、第 36–37 行（J2 第 8 步）、第 12 行（`r7-reviewer-withdraw`）、第 17 行（`r11-review-conflict`）都已执行。这与 handoff §7.3 及复审第 4 轮 §2.4 中的 05 调试一致。
- **C12 第 1 条：** handoff §7.4 已按 N24 写作“真实旅程未覆盖，由模拟接口 V12 覆盖”。

### 2.3 05-t1：FE3 kickoff §8.3 逐条（补证据核对第 1 轮 §2）

- **预期值：** 本会话从 H 的 git 对象中取出 `vnext/backend/benchmarks/real_dump_journey.py`，用 `python3 -I` 的 `ast.literal_eval` 独立读取：
  - `S2B_DATASET_BASELINE["rd-t1-a-v1"]["preview_table_count"] = 124`；
  - `S2B_DATASET_BASELINE["rd-t1-a-v2"]["preview_table_count"] = 124`；
  - `S1B_V2_PREVIEW_CHANGED_COUNTS["rd-t1-a-v2"] = 4`。
- **入口读取：** 入口同样在宿主机用 `ast.literal_eval` 读取（`run-real-backend-e2e.sh`），日志记 `t1_expected_from=vnext/backend/benchmarks/real_dump_journey.py`。
- **判定方式：** 四个汇总数由 `t1.spec.ts`（H）的断言判定，用例通过即全部满足。下表把每条断言对应到 §8.3。

| §8.3 条目 | 断言（`t1.spec.ts`） | 预期 | 结果 |
| --- | --- | --- | --- |
| 输入核对 | 入口 `t1_manifest_verified=t1-v1 files=19`、`t1-v2 files=19`；清单 SHA256 与 FE3a 一致 | 两份 19 行 | 符合 |
| v1 Preview | `:252-255`：`table_count`、`changed_table_count` 等于 `v1PreviewCount + 1`，`degraded`、`failed` 为 0；`initial_to_modified` 按 `pair_id` 取 | 125、125、0、0 | 符合 |
| v2 FULL 恰好两对 | `:360`：`pair_id` 排序后等于 `["baseline_to_initial", "initial_to_modified"]` | 两对 | 符合 |
| `baseline_to_initial` | `:362-364`：`changed`、`degraded`、`failed` 都为 0；`table_count` 只记录 | 0、0、0；记录值 125 | 符合（case log 第 6 行 `table_count=125`） |
| `initial_to_modified` | `:367-374`：`table_count = v2PreviewCount + 1`，`degraded`、`failed` 为 0，`changed = 4 + composite_changed` | 125、4、0、0 | 符合（case log 第 5 行 `composite_changed=0`） |
| `composite_changed` 对照 | — | 同一 vnext 树上没有后端 t1 运行结果 | 记录实际值 0，没有对照（按 §8.3） |
| 无未捕获错误、下载校验 | `:431` `expectNoPageErrors`；每次下载经 `parseBundleTar`，并按 `bundle_digest` 等待安装 | — | 符合 |
| 第 3 步异常 | case log 第 3 行 `t1-step3 anomalies=[]` | t1 v1 有生成时间，空 `INITIAL` 上没有异常 | 符合 |
| 参考截图 | 14 张 `fe4-t1-*`（7 个名字 × 1280、1920），在 05 `evidence/` 下 | 齐全 | 符合；清单在 05 上 `sha256sum -c` 通过，handoff §8.4 中 14 行“文件名 → SHA256”与清单逐行一致 |

- **case log：** `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/evidence/journey-cases.log` SHA256 `7a82bfa1a81ac650bcde8cd194488628441350325ae3d7439983449a3095a7c8`。
- **参考截图清单：** `/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/evidence/t1-reference-shots.txt` SHA256 `d45d1ceece47a78988f4619060c1fa8ac8aecf46c2d4463ddb8ab912a9c9000b`。

### 2.4 M1 增量（补证据核对第 1 轮 §2）

| 场景 | renderer 增量 | 对照 | 判定 |
| --- | --- | --- | --- |
| 第 1 步 t1 v1 MODIFIED_ONLY | 19,300,352 字节＝18.41 MiB（case log 第 7 行） | FE3a 24.86 MiB 的 0.74 倍；`59c5b8cfca` 证据为 20.38 MiB | 未超过 2 倍，不需交设计会话 |
| 第 4 步 FULL | 241,664 字节 | 与第 1 步同一浏览器实例，增量偏低，不可比较（FE3 kickoff §8.4） | 只报告 |

同一行还记录了 `max_rss_anon`、`max_rss_file`、`max_rss_shmem`，只报告。

## 3. 第 ③ 次稳定性比较（kickoff §7.3、§16.5）

- **复制截图：** 04 证据截图 `/home/dev/gdds-fe-evidence-04/fe4a-16f43063/shots` 经开发主机管道（`tar`）复制到 07 `/home/dev/gdds-fe-shots/fe4a-rereview4/evidence-04-copy`，按 04 的清单逐文件核对，198 个 PNG 全部一致。
  - 04 清单：`/home/dev/gdds-fe-evidence-04/fe4a-16f43063/shots/shot-files.txt` SHA256 `3db69cef9dc15ac8adeece2d52ce061f108ac4b754db384ebbaa4a77f233aa35`（04 上 `sha256sum -c` 也通过）；
  - 复制记录：`/home/dev/gdds-fe-logs/fe4a-rereview4/ev2/evidence-04-copy.log` SHA256 `bc4c645c7df731b38fc0f23d50a9ae633e2c6f99758be2272b286db23ce055be`。
- **树号：** 两边都是 `d8e9a2e717e8d153b3a7794f25b76186c4bc4d5e`：04-a wrapper 记录的 `frontend_tree_start`、`frontend_tree_end`，以及复审第 4 轮 07 全量的 wrapper 记录。
- **命令：** 用 Y 的比较脚本 `/home/dev/gdds-fe4a-rereview4/frontend/scripts/compare-screenshots.py` SHA256 `0887a45ecbac9c9d21ec5b0217859f05e565d0198068112cd4ddfcd03ec68eb8`（与 `59c5b8cfca` 相同）运行 `python3 -I compare-screenshots.py --stable /home/dev/gdds-fe-shots/fe4a-rereview4/full1 /home/dev/gdds-fe-shots/fe4a-rereview4/evidence-04-copy`。
- **结果：** **exit 0**，`内容变化=0 尺寸不同=0 缺失=0 噪声=19 相同=179`。噪声每张最多 56 个像素（`upload-locked-1920.png`），最大连通块 10，都在上限（100、16）内。
- **输出：** `/home/dev/gdds-fe-logs/fe4a-rereview4/ev2/stable3-rr4-vs-ev04.log` SHA256 `386a597214c0ee3e7761bb9e37f76e5268901fc076e6ab03d05b6495ebf0fb30`。

C4 的三次稳定性比较都已通过：第 ①、② 次由复审第 4 轮的比较代替（§16.4 第 3 项），第 ③ 次为本节。owner 看图的对象是复审第 4 轮 07 上的截图 `/home/dev/gdds-fe-shots/fe4a-rereview4/full1`，它与复审第 3 轮的截图之间没有内容变化，证据截图通过本节与它绑定。

## 4. 回源

- **来源清单：** 实施会话的两份来源清单在所在节点 `sha256sum -c` 都通过：
  - 04：`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-04/handoff-sources-04.txt`，23 行；
  - 05：`/home/dev/gdds-fe-logs/fe4a-evidence-16f43063-05/handoff-sources-05.txt`，16 行。

  开发主机上回源用的副本（`/home/dev/gdds-fe4a-handoff/`），包括来源清单、证据文件与身份文件，都与节点原件逐字节相同。
- **输入：** handoff 提交中的文件，与实施会话回源日志记录的 `handoff_sha256` 相同。
- **复跑：** 在开发主机上做只读对照：用 H 的 `check-handoff-hex.py` 读取 handoff 提交中的文件，参数同实施会话。
  - exit 0：`47 distinct full token(s); git=8 sha256=39 allowed=0 abnormal=0; 0 truncated form(s)`；
  - 与实施会话日志 `/home/dev/gdds-fe4a-handoff/check-handoff.log` 相比，开头字段之后逐行相同。
- **配对：** handoff 中 64 位值共出现 41 次，其中 32 次经过路径配对。未配对的 9 次中：
  - 7 次是 config digest 与 `input_sha256`，来自证据文件，不是文件哈希；
  - 2 次是文件哈希，写法不能配对，见 N25。这两个值本会话已在节点与开发主机现场重算，都正确。
- **抽查：** 节点现场重算的结果与 handoff 相同：
  - 04：四份 wrapper 与入口日志、case log、截图清单、bundle；
  - 05：wrapper 与入口日志、case log、参考截图清单、bundle。
- **交付回复：** 没有手抄哈希，只有提交号与路径。

## 5. 非阻塞

- **N25 两个文件哈希的写法不能配对：** handoff 有两处文件哈希写成脚本不能配对的形式，违反了证据提示词“中间不加逗号或括号”的要求：
  - §2 的 bundle 行，路径与 SHA256 之间隔着范围与字节数；
  - §3.3 的 `print-input-before-run.json` 行，写成“，SHA256”。

  两个值都由来源清单提供，本会话已现场核对（§1、§4），不影响结论。N20 的回源脚本修正随 FE4b 进行，届时可以一并让脚本报告“有路径却未配对”的文件哈希。
- **N26 04-a 入口日志写在共享默认目录：** `run-tests.sh` 支持 `GATEWAY_FE_LOG_DIR`，本可以写进本次日志目录 `fe4a-evidence-16f43063-04/`；实际写在默认的 `/home/dev/gdds-fe-logs/frontend/`。文件名带时间戳，没有覆盖其他文件，已列入来源清单，handoff 中如实写明。FE4b 的证据提示词写明设置该变量。
- **N27 wrapper 记录（沿用）：**
  - 04-b 的 `wrapper_field_missing exit_code`，入口记录的是 `entry_exit=0`，同证据核对第 1 轮；
  - wrapper 在释放标记前把标记内容记为 `busy_end`，这是 wrapper 的既定写法，复审第 4 轮在 07 上的运行也一样。运行后两节点的标记都已释放。

  这两项不影响判据，FE4b 修订 wrapper 时可以一并处理：在释放后记录 `busy_end`，或改名为 `busy_before_release`。
- **记录：** 05-t1 的 `--evidence-dir` 下只有 `test-results`，参考截图在日志目录的 `evidence/`；04-c 的 `journeys-evidence` 同样只有空的 `test-results`。这是入口的既有行为，同证据核对第 1 轮。

## 6. FE4a 退出

**kickoff §5.2 FE4a 退出条件：**

| 条件 | 状态 |
| --- | --- |
| 审核通过 | 复审第 4 轮通过（`42aeb69336`） |
| 证据（§7.2 FE4a 证据行）各一次通过 | 通过（本报告 §2，在 H 上） |
| C4 的三次稳定性比较都通过 | 通过（复审第 4 轮 §2.2 与本报告 §3） |
| §7.3 看图清单中的截图经 owner 确认 | **待 owner**。看图对象：07 `/home/dev/gdds-fe-shots/fe4a-rereview4/full1`，与复审第 3 轮的截图没有内容变化 |

**交 owner 确认（汇总自复审第 3、4 轮 §6）：**

- §7.3 看图清单（分组见 fix2 handoff §6.4）；
- 规则 4 的唯一豁免 `fe3b-w4-approved-withdraw`：1280 与 1920 都溢出 12 px，禁用原因被截断，随 FE4b 的 N5 处理；
- C8 灰色冲突提示与红色集合变化提示同屏时的颜色；
- N11（关闭成功后输入仍可编辑）与 N15（“收起”的位置）。

**owner 确认后（设计会话执行，kickoff §6.4、§10 Q12）：**

1. 在 `fe-vnext` 头 `c2199b82f7` 上打附注 tag `fe-fe4a-exit`；
2. 推送 tag `fe-fe4a-exit`；main 是否推送随后端节奏，由 owner 决定；
3. FE4a 期间不合入 main（§10 Q2）。合入方式按 kickoff §6.4 与设计会话安排；`fe4a-review` 分支上的审核报告随 FE4a 退出合入；
4. 退出后清理：§16.6、§17.5 列出的保留产物，以及各轮审核的 worktree、ref 与截图，到这时可以清理，由设计会话统一安排。

**带入 FE4b 的项：**

- N5（预览页顶栏禁用原因溢出，豁免随之删除）；
- N19（比较脚本自检对 Paeth 没有区分力）；
- N20 与 N25（回源脚本的配对范围）；
- N26（证据提示词设置 `GATEWAY_FE_LOG_DIR`）；
- N27（wrapper 的两个记录字段）；
- N24（C12 第 1 条在真实旅程中未覆盖；FE4b 如果构造过期通过或 `ARCHIVE_CLOSED` 场景，可以补上）；
- §17.2 的可选项：工作台工具栏原生按钮统一改为 `Button` 组件；
- 复审第 3 轮 N14、N17；
- 审核清单补充（证据核对第 1 轮 §4）：DOM 结构改动时 grep `e2e-real/` 中的定位器，并核对共享 helper 全部调用处的结构。

## 7. 本会话的遗留

- **07：**
  - `/home/dev/gdds-fe-shots/fe4a-rereview4/evidence-04-copy`：04 证据截图的副本；
  - `/home/dev/gdds-fe-logs/fe4a-rereview4/ev2/`：复制记录与第 ③ 次比较的输出。
- **05：** `/home/dev/gdds-fe-logs/fe4a-rereview4-05/`，复审第 4 轮回源用的清单。
- 其余同复审第 4 轮 §8。以上都保留到 FE4a 退出。
- 本会话没有改动实施会话的产物与 04 上他人的占用标记，没有推送，没有改 `fe-vnext`，没有打 tag。

## 8. 本报告的回源

在 07 上用 Y 的回源脚本核对本报告的副本。来源如下，没有使用 `--allow`：

- **git 对象：** 经 bundle 传到 07 的 handoff 提交与 `fe4a-review` 分支；
- **04、05 清单：** 实施会话的两份来源清单，传到 07 后先用旁注核对；
- **07 清单：** 现场重算的 `report2-sources-07.sha256`，覆盖 `ev2/` 的全部文件。

结果：exit 0，`31 distinct full token(s); git=12 sha256=19 allowed=0 abnormal=0; 0 truncated form(s)`。其中 16 处文件哈希全部按路径配对通过，另 3 个 config digest 来自身份证据文件。反例：交换 §2.1 表中 04-a 与 04-b 两个 wrapper 日志的 SHA256，exit 1，报 2 处 `pairing mismatch`。

结果与命令在 07 `/home/dev/gdds-fe-logs/fe4a-rereview4/report2-hex/`；回源日志自身的哈希不写入本报告。
