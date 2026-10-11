# P5 架构收口 G8b 实施交接（有序骨架、移动与位置汇总）

状态：**G8b 实施完成，门禁提交 V（`b42321e272`）上权威 runner exit `0`。** 五包 ruff/mypy、`import_rules` 与 V 的 carried 判定见 §8–§9。等待独立审核；审核通过后由审核方在报告提交上打 `p5-g8b-exit`，并以 `--no-ff` 合入 `main`。

日期：2026-10-11
分支 / worktree：`p5-g8b` / `/home/dev/gdds-p5-g8b`（保留；未推送，未打 tag，未合并 main，未写审核报告）
R0：`392410b452f149603bf8149431d0db392abaa4a0`（main，G3 合入与审核方文档更新之后；建 worktree 时 HEAD 相同，status 为空）
V（门禁提交，最后一个非 handoff 提交）：`b42321e272`
H（本提交，只改本文件）：`git log -1` 所示提交。

## 1. 提交序列

| 提交 | SHA | 用途 |
| --- | --- | --- |
| 1 | `390e7d1590` | `docs(p5-g8b)`：R5 设计 §8–§9 删去 `ORDERED_POSITION_CHANGED`，写明骨架、移动与空白区间；`contracts/ordered-diff.md` 与 `capabilities/ordered-diff-compute.md` 改为引用 R5 §8–§9 |
| 2 | `b42321e272`（V） | `fix(p5-g8b)`：D1–D4 实现（骨架、移动、位置汇总与处理模式、空白区间）与测试 |
| H | 本提交 | 本文件 |

范围（`git diff --name-only 392410b452..V`，8 个路径，记录于 `g8b-scope-R0-V.txt`）：文档 3（R5 设计、`contracts/ordered-diff.md`、`capabilities/ordered-diff-compute.md`）；comparison 能力模块 2（`contracts.py`、`ordered.py`）；测试 3（`test_comparison_ordered.py`、`test_comparison_artifacts.py`、`test_history_compare_jobs.py`）。

## 2. 前置核对与门禁前检查

- worktree 建于 R0（`git worktree add -b p5-g8b /home/dev/gdds-p5-g8b 392410b452`）；`legacy` 符号链接建于 worktree 内（`.git/info/exclude` 忽略），建后 `git status` 为空。
- `GATEWAY_DEV_OFFLINE=1 ./vnext/scripts/prepare-dev-dependencies.sh` exit `0`；五个 `uv.lock` 的 SHA256 与 R0 相同（`g8b-uvlock-sha-R0.txt` 与 `g8b-uvlock-sha-now.txt`）。
- R0 上存在 G8b 规格与 G3 独立审核报告（`p5-arch-closure-g8b-spec.md`、`p5-arch-closure-g3-independent-review.md`）。
- 门禁前检查（运行前记录）：HEAD `b42321e272`，分支 `p5-g8b`，`git status` 为空，`pgrep -x dolt` 为空，无 compose project 标签的容器，`docker compose ls` 为空，8000 端口无监听。
- 镜像目录中的历史残留镜像未做任何 docker 清理，未触碰 `gateway-repository-client-e2e:local` 与 `gateway-repository-client-e2e-base:local`。

## 3. 规格 §1 表格的实际结果

全部场景由参数表 `BACKBONE_OUTCOMES`（`vnext/backend/tests/test_comparison_ordered.py`）证明；“旧结果”列与 R0 上同一探针的输出一致（`g8b-probe-R0.out`，22 个场景，无错误）。`test_backbone_reports_moves_blank_intervals_and_summarised_shifts` 逐项断言有序记录种类、空白区间种类与行数、`position_changed_count` 与 `table_processing_mode`。

| 规格 §1 场景 | 应有结果 | 实际（参数表 id） | 旧结果（规格记录） |
| --- | --- | --- | --- |
| 删掉两段空白之间的一个真实行 | 无空白记录 | 空白记录无；ROW_DELETED 1；骨架位置变化 1；SHIFT_REPAIRED（`real-row-removed-between-blank-segments`） | 2 条空白删除 + 1 条空白插入 |
| 在空白段中间插入一个真实行 | 无空白记录 | 空白记录无；ROW_ADDED 1；位置变化 1；SHIFT_REPAIRED（`real-row-inserted-inside-blank-segment`） | 1 条删除 + 2 条插入 |
| 真实行移到别处，空白行未动 | 无空白记录 | 空白记录无；ROW_MOVED 1；位置变化 1；REORDER_COMPLEX（`real-row-moved-with-blank-rows-untouched`） | 1 条删除 + 1 条插入 |
| 在空白段之后追加一个真实行 | 无空白记录 | 空白记录无；ROW_ADDED 1；位置变化 0；TAIL_SEGMENT（`real-row-appended-after-blank-segment`） | 1 条删除 + 1 条插入 |
| 6 个真实行中把第 1 行移到末尾 | 1 条 MOVED | ROW_MOVED 1；位置变化 5；REORDER_COMPLEX（`first-of-six-real-rows-moved-to-end`） | 6 条 MOVED |
| 顶部插入 1 个空白行，后面 5 个真实行 | 1 条空白插入 | BLANK_INSERT_INTERVAL 1（row_count 1）；无有序记录；位置变化 5；SHIFT_REPAIRED（`blank-row-inserted-above-five-real-rows`） | 1 条空白插入 + 5 条 POSITION_CHANGED |

其余参数表场景（同一参数表，用于证明 D3/D4 的规则边界）：

| 参数表 id | 结果 |
| --- | --- |
| `blank-row-inserted-inside-segment` | 空白插入 1；位置变化 1；SHIFT_REPAIRED |
| `blank-row-deleted-inside-segment` | 空白删除 1；位置变化 1；SHIFT_REPAIRED |
| `blank-and-real-rows-changed-in-the-same-table` | 空白插入 1；ROW_ADDED 1、ROW_DELETED 1；位置变化 0；TAIL_SEGMENT |
| `blank-row-appended-at-tail` | 空白插入 1；位置变化 0；TAIL_SEGMENT（见 §4.3） |
| `blank-notation-and-payload-changes-are-ignored` | 无任何记录；mode 为 None；表状态 UNCHANGED |
| `tie-keeps-the-earlier-before-row-in-the-backbone` | ROW_MOVED 1（gid3）；位置变化 1；REORDER_COMPLEX |
| `tie-among-three-longest-runs-keeps-earliest-rows` | ROW_MOVED 1（gid3）；位置变化 1；REORDER_COMPLEX |
| `content-only-update-is-a-local-patch` | ROW_MODIFIED 1；位置变化 0；LOCAL_PATCH |
| `content-update-with-tail-insert-is-a-local-patch` | ROW_ADDED 1、ROW_MODIFIED 1；位置变化 0；LOCAL_PATCH（见 §4.3） |
| `tail-replacement-without-position-shift` | ROW_ADDED 1、ROW_DELETED 1；位置变化 0；TAIL_SEGMENT |
| `absolute-renumber-only-is-summarised` | 无有序记录；位置变化 2；SHIFT_REPAIRED |
| `two-row-swap-moves-one-row` | ROW_MOVED 1；位置变化 1；REORDER_COMPLEX（见 §4.1） |
| `in-place-replacement-without-position-shift` | ROW_ADDED 1、ROW_DELETED 1；位置变化 0；TAIL_SEGMENT（见 §4.3） |

## 4. 规则实现与判定依据

### 4.1 骨架与并列规则（D1）

- 骨架：两侧共有真实行按 before 侧 `no` 排列，取其 current 侧位置序列的最长递增子序列。并列时取字典序最小的 before 侧下标序列，即按 before 顺序逐个比较、优先保留 before 侧位置较前的行。
- 实现（`_backbone_indices`）：对 current 位置序列逆序做 patience sorting 得到每个下标的 reach（以该下标起始的最长递增长度），O(n log n)；再自最长层起，逐层取位于上一选中下标之后的第一个 reach 等于当前层的下标。结果即字典序最小的最长递增下标序列。不做候选枚举，不设预算。
- 确定性：结果只依赖两侧 `no` 排序后的 current 位置序列，不依赖哈希或集合迭代顺序。
- 测试：
  - `test_backbone_is_the_earliest_longest_increasing_run_in_before_order`：长度 0–6 的全部排列（共 874 个）与穷举参考（按组合顺序取首个最长递增下标元组）逐一比较；
  - `test_backbone_of_a_long_table_skips_only_the_moved_row`：5000 行、首行移到末尾，骨架为其余全部行；
  - 参数表 `tie-keeps-the-earlier-before-row-in-the-backbone`（位置序列 `[1,3,2]`）与 `tie-among-three-longest-runs-keeps-earliest-rows`（`[1,3,2,4]`，三个最长子序列）。
- 可见后果（请审核确认）：并列时被标为移动的是 before 侧较后的那一行，它不一定是绝对 `no` 改变的行。例：F1 `keyed_ignored_column`（gid1 的 `no` 1→99，gid2 的 `no` 2→2）标出 gid2 为 ROW_MOVED（before 与 current 均为 2），gid1 的位置变化计入 `position_changed_count = 1`。两行互换（`two-row-swap-moves-one-row`）同理。规则按规格 D1 字面实施，未改。

### 4.2 移动（D2）

- 两侧共有且不在骨架中的真实行记为 ORDERED_ROW_MOVED；`row_moved_count` 等于这些行数。一次移动只标出被移动的行（S5 中仅 gid1）。

### 4.3 位置汇总与处理模式（D3）

- ORDERED_POSITION_CHANGED 删除。`OrderedSummary.position_changed_count` = 骨架行中 `no` 改变的行数（不含移动行）。
- 一次移动会改变被其跨越的骨架行的绝对 `no`（S5 中为 5 行），因此移动表的 `position_changed_count` 可以非零；这是绝对位置汇总，不影响模式（移动优先）。
- 处理模式（`_processing_mode`，按顺序取第一条命中）：
  1. 有移动 → `ORDERED_REORDER_COMPLEX`；
  2. 有骨架位置变化 → `ORDERED_SHIFT_REPAIRED`；
  3. 有真实行新增/删除或空白区间变化，且无内容修改 → `ORDERED_TAIL_SEGMENT`；
  4. 有内容修改 → `ORDERED_LOCAL_PATCH`；
  5. 无变化 → `None`。
- 规格 D3 未直接列出的情形，本实现按下列依据决定（待审核，见 §11）：
  - 仅空白区间变化（`blank-row-appended-at-tail`）→ `ORDERED_TAIL_SEGMENT`。依据：ordered-diff 契约 §Table Processing Mode（“尾部新增/删除/blank interval 输出 ORDERED_TAIL_SEGMENT”）与 legacy `_tail_only`（含 BLANK_INSERT/DELETE）。注意：此时 `ordered_extension.status` 仍为 `ORDERED_UNCHANGED`（既有语义，空白变化由 `blank_extension` 报告），与非空 mode 不一致。
  - 内容修改与新增/删除并存、无移动、无位置变化（`content-update-with-tail-insert-is-a-local-patch`）→ `ORDERED_LOCAL_PATCH`。依据：legacy `_tail_only` 中含内容修改即不是 tail。旧实现为 TAIL。
  - 无位置变化的替换（同位置删除并新增，`in-place-replacement-without-position-shift`；尾部替换，`tail-replacement-without-position-shift`）→ `ORDERED_TAIL_SEGMENT`，与旧实现一致（旧实现：新增或删除即 TAIL）。

### 4.4 空白区间（D4）

- 锚点：两侧各自的骨架行。非骨架真实行（新增、删除、移动）对空白分段透明。每个锚点对内比较两侧空白行数：净增记 `BLANK_INSERT_INTERVAL`，净减记 `BLANK_DELETE_INTERVAL`，`row_count` 为差值；区间位置取该锚点对内首末空白行的位置，某侧无空白时该侧位置为空。
- `interval_digest` 公式不变（`{before, after, count}`，count 取有空白一侧的计数），锚点改为骨架行。
- `before/current_occupancy_digest` 保持为各侧自身的空白分布（锚点为本侧全部真实行，公式与 R0 相同），不随配对变化。
- 空白行字段与空白写法（NULL、0、pseudo）不参与比较，不进入记录与 digest。`blank-notation-and-payload-changes-are-ignored` 与既有 `test_blank_payload_change_has_no_ordinary_or_blank_record`、`test_blank_no_renumber_keeps_occupancy_digest_and_records_stable` 覆盖。
- 空串写法未加参数行：`_integer` 对非空字符串直接拒绝，IEC104 `gid` 为整数列，空串只会以整列字符串类型的空白标记出现；本步未改其行为。

## 5. 删除 ORDERED_POSITION_CHANGED 的影响面

- 代码：`capabilities/comparison/contracts.py`（枚举值删除）；`capabilities/comparison/ordered.py`（记录生成删除，`_processing_mode` 与空白区间改写）。`row_encoding.py` 与 `surface_assembly/_assembly.py` 只读取 `position_changed_count`，未改动。
- 测试：
  - `test_comparison_ordered.py`：`test_ordered_content_and_move_are_separate_records`（移动 2→1，位置变化 2→1）；`test_ordered_move_only_has_no_content_update`（两条 MOVED 改为一条）；`test_ordered_absolute_renumber_is_position_change_not_move`（不再产生记录，断言改为 `records == ()` 与 mode）。
  - `test_history_compare_jobs.py`：F1 的 `move_only` 与 `keyed_ignored_column` 两例由 `(ROW_MOVED, ROW_MOVED)` 改为 `(ROW_MOVED,)`。
  - `test_comparison_artifacts.py`：两个 fixture 依赖 POSITION 记录产生有序记录族，已改输入，断言意图不变。`_ordered_result_with_standard_and_moves` 改为 4 行反转并修改首行内容（标准记录 1，有序记录 4：1 个 MODIFIED + 3 个 MOVED，仍超过每表上限 4）；`test_publish_uses_independent_ordered_and_blank_artifacts` 改为有序移动加空白变化（不产生标准记录，仍为 ORDERED 与 BLANK 两族）。
- 文档：R5 设计 §8–§9；`contracts/ordered-diff.md`；`capabilities/ordered-diff-compute.md`（提交 1）。
- HTTP DTO 与前端：无引用。全仓库检索 `POSITION_CHANGED` 仅剩历史计划文档与 R5 §9 的“不进 blank signature”原则句（保留）。
- golden：`vnext/fixtures/golden` 不含比较事实，未改动。

## 6. golden 与 compose 旅程的变化清单

- golden 文件：无变化。
- 断言与规格条款的逐项对应（断言、变化、原因、规格条款）：

| 断言或数据 | 变化 | 原因（规格条款） |
| --- | --- | --- |
| `test_ordered_content_and_move_are_separate_records` | `ROW_MOVED` 2→1；`position_changed_count` 2→1 | D1 骨架保留 before 侧较前的 gid2 与 gid1 之一，另一行被标为移动（D2）；位置变化只计入汇总（D3） |
| `test_ordered_move_only_has_no_content_update` | 两条 `ROW_MOVED` → 一条 | D2：一次移动只标出被移动的行 |
| `test_ordered_absolute_renumber_is_position_change_not_move` | 不再产生 `ORDERED_POSITION_CHANGED`；断言改为 `records == ()`、`position_changed_count == 2`、mode 为 SHIFT_REPAIRED | D3：删除记录种类，位置后移只计入汇总与 mode |
| F1 `move_only`（`test_history_compare_jobs.py`） | `(ROW_MOVED, ROW_MOVED)` → `(ROW_MOVED,)` | D2 |
| F1 `keyed_ignored_column` | 同上；被标为移动的是 gid2（两行并列，D1 规则保留 before 侧较前的 gid1） | D1 并列规则与 D2 |
| `_ordered_result_with_standard_and_moves`（`test_comparison_artifacts.py`） | 输入改为 4 行反转并修改首行内容；标准 1、有序 4 的断言不变 | D3：原输入的位置后移不再产生有序记录，有序记录数不足 4；断言意图（标准与有序合计超过每表上限）不变 |
| `test_publish_uses_independent_ordered_and_blank_artifacts` | 输入改为有序移动加空白变化；ORDERED 与 BLANK 两族的断言不变 | D3：原输入只剩位置后移，不再产生有序族记录 |
| compose `ordered-b`（`test_ordered_compare_compose.py`，断言不变） | 有序记录不含 POSITION；mode TAIL→SHIFT_REPAIRED | D3；经同一探针在 R0 与 V 上核对（`g8b-probe-R0.out` / `g8b-probe-V.out`） |

- compose 旅程（本机未运行，随权威 runner 执行，结果以 §8 的日志为准）：
  - `test_ordered_history_compare_compose_journey`：断言（ADDED、DELETED、MODIFIED 各 ≥ 1）代码未改且仍成立。结果变化（经 R0 与 V 的同一探针输出核对，`g8b-probe-R0.out` / `g8b-probe-V.out`）：`ordered-b`（gid5 的 `no` 1→2 且内容变化，gid7 删除，gid2 新增）的有序记录不再含 ORDERED_POSITION_CHANGED；`position_changed_count` 仍为 1；`table_processing_mode` 由 TAIL_SEGMENT 变为 SHIFT_REPAIRED（骨架位置变化优先于尾部段）。`ordered-a`（仅新增，无骨架位置变化）保持 TAIL_SEGMENT。
  - `test_ordered_submit_bisect_compose`：不断言有序记录种类，结果不变。
  - `test_history_compose_e2e`：不断言有序种类；摘要由运行时 oracle 计算，未硬编码。
- 比较事实与 digest 随记录集合变化，由 oracle 运行时复算，代码中无硬编码 digest 需要更新。

## 7. D1–D5 与停止条件逐项核对

- D1 ✓（§4.1）。D2 ✓（§4.2）。D3 ✓（§4.3；ORDERED_POSITION_CHANGED 删除）。D4 ✓（§4.4）。D5 ✓（提交 1）。
- 停止条件（规格 §6）：
  - 空白行字段比较、pseudo gid 分配、规范存储或摘要、Submit 判定：未改。范围中无 `storage_projection`、`application/submission`、`snapshot_materialization` 路径；空白字段仍被完全忽略。未触发。
  - 标准（非有序）比较：未改。`standard.py` 未动；`test_comparison_standard.py` 通过。未触发。
  - 新增 HTTP DTO 字段或前端可见的新记录种类：未新增字段，记录种类减少一个（ORDERED_POSITION_CHANGED）。`table_processing_mode` 只使用既有枚举值，但可见取值有变化（SHIFT_REPAIRED 此前在有序路径从未产生；仅空白变化的表此前为 None，现为 TAIL_SEGMENT），已记入 §6 与 §11。未触发新字段或新种类。
  - `import_rules` 增长或新增依赖：未触发。`import_rules` 为 3 / 0 / 14；新增的 `bisect` 为标准库。
  - 某场景无法在 D1–D4 下得到 §1 应有结果：未触发。六个场景全部得到应有结果（§3）。

## 8. V 的门禁记录

- 五包 ruff/mypy 与 `import_rules`（V，`g8b-gate-V-checks.log`）：五包 ruff 与 mypy 各 exit `0`；`import_rules` exit `0`，3 / 0 / 14。
- repository-service 镜像：`./vnext/scripts/build-repository-service-image.sh` 于 V 执行，exit `0`。日志 `g8b-gate-V-rs-image-build.log`，起止与身份记录 `g8b-gate-V-rs-image-build.summary`。镜像 `gateway-repository-service:local`，ID `sha256:9733a906e791f4150db4f4b2dbd10c947044a80356b408293d90709eb5d8f469`；labels `gateway.p2r1.build-input-revision=29f7dfd3c349f9943590765c2b90ca49e47f8eb3`、`gateway.p2r1.source-tree-sha256=sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f`（与 G3 相同：repository-service、contracts 与构建定义在 R0..V 中未变）。
- 权威 runner（attempt1）：`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，起止 HEAD 均为 `b42321e272`，起止 `git status` 均为空；runner 自身 exit code **`0`**。日志 `g8b-gate-V-run-tests-attempt1.log`，起止与 exit 记录 `g8b-gate-V-run-tests-attempt1.summary`。运行期间未提交、未重建或重新 tag 镜像。
- 批次结果：

| 批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed，耗时 1.41s |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend（全部，含 compose 旅程） | 2748 passed，1 warning（既有 StarletteDeprecationWarning），耗时 21:03；G3 为 2727，差 21 项为本步新增（§3 参数表 19 项与两个新测试函数） |
| repository_service（parallel，`-n 48`） | 1681 passed，1 skipped |
| repository_service（serial，`-n 0`） | 205 passed，1682 deselected |

日志中 FAILED、ERROR 与 Traceback 行数均为 0。

- provenance（`g8b-gate-V-compose-provenance-attempt1.json`，运行后复制）：compose project `ordered-bisect-b-2338803-baseline`；backend ``sha256:a6edaa61a216cfc1508036a3b980814bed9b9d8724487f62d0073b93864a2d3b``；worker ``sha256:7417c1589191b9dd10c7b1bc0be27742644cb14dba7ed3b42ebc5416634e7e6f``；repository-service ``sha256:9733a906e791f4150db4f4b2dbd10c947044a80356b408293d90709eb5d8f469``（与运行前构建的 RS 镜像一致，运行未重建）。
- `docker image inspect` 三镜像：`g8b-gate-V-image-inspect-attempt1.log`。backend、worker 的 labels 只含 compose project、service 与 version，无 source identity label（与 AGENTS.md 一致，按 carried 第 3 条处理）。

## 9. carried 判定（V → H）

在同一 worktree（`/home/dev/gdds-p5-g8b`）内、H 提交之后执行 `g8b-carried-check.sh b42321e2721bacda4f39bc33987e28fb787d9d19 g8b-gate-V-compose-provenance-attempt1.json g8b-carried-check-H`，日志 `g8b-carried-check-H.log`，结果见末行 `RESULT`。过程：

- (a) `git diff --name-only V H` 仅含本文件，且不含容器边界路径（Dockerfile、依赖锁、Compose、entrypoint、环境变量接线、healthcheck、Docker e2e 测试、harness 与其 support 模块）；
- (b) 在 H 上用 `build_context_digest.py identity` 重算 repository-service 身份，`build-input-revision` 与 `source-tree-sha256` 必须等于 RS 镜像 label；
- (c) backend、worker 在同一 worktree 中以 provenance 的 project 名连续重建两次，两次之间不运行任何测试；每次的 image ID 都必须等于 provenance 中运行容器的 image ID。

结果不写入本文件：判定在 H 提交之后执行，结果记录于 `g8b-carried-check-H.log` 末行 `RESULT`，并在实施方最终回复中报告（与 G3 相同的约定）。

## 10. 范围核对

- `git diff --name-only 392410b452..H`：V 的 8 个路径（§1）加本文件；H 提交后以该命令核对，结果见最终回复。
- `git diff --name-only V..H`：仅本文件（由 `g8b-carried-check-H-diff-names.txt` 记录）。
- 未改动：`AGENTS.md`、`testing-conventions.md`、治理修订计划、G8b 规格、执行计划、`formal/README.md`、G8a/G3 报告、Compose、Dockerfile、镜像构建脚本、依赖锁、`import_rules` 基线。

## 11. 已知缺口与待审核事项

1. **空白区间的 `table_processing_mode`**：仅空白区间变化时 mode 为 `ORDERED_TAIL_SEGMENT`，而 `ordered_extension.status` 仍为 `ORDERED_UNCHANGED`。可选：(a) 维持现状（本步采用）；(b) 空白变化不决定 mode，mode 为 None；(c) 同时把 ordered status 置为 CHANGED。请 owner 决定。
2. **并列与被标移动的行**（§4.1）：两行或同类小表中，被标为移动的可能是 before 侧较后、绝对位置未变的行。规则按规格 D1 字面实施，未改。
3. `contracts/risk.md:184` 只列出 `position_changed_count` 字段名，其语义（骨架行绝对位置变化）未改写；D5 未列该文件。
4. `position_changed_count` 包含一次移动造成的骨架行绝对 `no` 变化（S5 为 5）。这是按规格“骨架行中 no 改变的行数”的字面结果。
5. 真实数据未在本步运行。S2b 验收第 3 条的各类记录数量由 S2b 写入其 handoff。
6. 空串写法未加参数行（§4.4）。
7. compose 旅程未在本机运行；结果以权威 runner 日志为准（§8）。

## 12. 产物与日志

目录 `/home/dev/gdds-p5-closure-s1-gate-logs/`（worktree 外）：

- 依赖与范围：`g8b-uvlock-sha-R0.txt`、`g8b-uvlock-sha-now.txt`、`g8b-scope-R0-V.txt`、`g8b-prepare.log`。
- R0 基线：`g8b-baseline-R0/`（五包 ruff/mypy 逐包日志与 `import_rules` 结果）；`g8b-baseline-focused.log`（R0 上 focused 测试 201 passed）。
- 实施期间检查（与 V 内容相同）：`g8b-wip-2/`（五包检查目录）、`g8b-wip-2-backend-unit.log`（backend `-m unit` 2581 passed）。
- 门禁 V：`g8b-gate-V-rs-image-build.sh` 与 `.log` / `.summary`；`g8b-gate-run-tests.sh`；`g8b-gate-V-run-tests-attempt1.log` / `.summary`；`g8b-gate-V-compose-provenance-attempt1.json`；`g8b-gate-V-image-inspect-attempt1.log`；`g8b-gate-V-checks.log` 与逐包目录 `g8b-gate-V-checks/`。
- carried：`g8b-carried-check.sh`、`g8b-carried-check-H.log`、`g8b-carried-check-H-diff-names.txt`。
- 探针：`g8b-probe-scenarios.py`；`g8b-probe-V.out` 与 `g8b-probe-R0.out`（22 个场景，同一输入在 V 与 R0 上的对照）。
