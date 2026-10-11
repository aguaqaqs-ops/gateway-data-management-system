# P5 架构收口 G8b（有序比较的骨架、移动与位置变化）独立审核

- 结论：**通过**
- 日期：2026-10-11
- 审核对象：`p5-g8b` @ `43d5d44fdf6dda86d2d4192f4096c5dbd5b90e54`（H；门禁提交 V = 实现 HEAD = `b42321e2721bacda4f39bc33987e28fb787d9d19`），区间 `392410b452..43d5d44fdf`（分支只含实施方提交）。
  H 由首个 handoff 提交 `dfabb6aca9` amend 而来（只补 handoff 的逐断言映射），carried 在 `43d5d44fdf` 上重做过；我复核的是最终的 H。
- 依据：G8b 规格（§1 表格、§3 D1–D5、§6 停止条件、§7 验收）；治理修订计划 G8（owner 决议）；执行计划 §2 S2b 真实数据验收第 3 条；R5 比较设计 §8–§9；AGENTS.md「镜像身份等价」；
  handoff `plans/p5-arch-closure-g8b-handoff.md`。
- 审核在只读 detached worktree `/home/dev/gdds-review-g8b`（H）中进行；carried 复核在实施 worktree `/home/dev/gdds-p5-g8b` 中只做一次 backend/worker 重建，期间没有运行测试，HEAD 与 `git status`（clean）前后不变。

## 1. 结论摘要

G8b 的目标达成：两侧共有的真实行按最长递增子序列确定骨架，一次移动只标出被移动的行；`ORDERED_POSITION_CHANGED` 已删除，骨架行的位置后移只进入
`position_changed_count` 与 `ORDERED_SHIFT_REPAIRED`；空白区间以骨架行为边界，真实行的新增、删除、移动不再产生空白记录；空白行字段与写法仍不参与比较。
我自行构造了 12 个场景直接运行比较（不只读测试），规格 §1 表格的 6 个场景全部得到“应有结果”。V 上权威 runner exit 0，V → H 只改 handoff，carried 在同一 worktree 复现成立。
没有阻塞项；三项非阻塞问题（G8b-F1 至 G8b-F3）建议并入 S2a 处理。可以在本报告提交上打 `p5-g8b-exit`，它是 S2a 的区间起点。

## 2. Findings

### G8b-F1：只在尾部增删空白行时，`ordered_extension.status` 与 `table_processing_mode` 不一致

- 类型：已证实缺陷（表级事实自相矛盾）；是否阻塞：否
- 位置：`capabilities/comparison/ordered.py` `_build_fact`（`ordered_changed` 不含空白变化，`_processing_mode` 的 `segment` 含 `blank_changed`）。
- 依据：探针“两行真实行后追加一个空白行”：表 `MODIFIED`，`blank_extension` `ORDERED_CHANGED` 并有 1 条 `BLANK_INSERT_INTERVAL`，
  但 `ordered_extension.status` 为 `ORDERED_UNCHANGED` 而 `table_processing_mode` 为 `ORDERED_TAIL_SEGMENT`。按能力文档的分类表，空白区间变化属于 tail/shift 分类，mode 的取值本身合理。
  空白插入引起位置后移时，`ordered_changed` 因 `position_changed_keys` 为真而一致，矛盾只出现在“尾部空白增删、无位置后移”这一种情况。实施方已在 handoff 中提出。
- 触发场景与影响：消费方若按 `ordered_extension.status` 过滤，会把带 mode 的表当作未变化；当前 surface 只读取 mode 与汇总计数，不读该状态，没有可见错误。
- 最小修正方向：规定 `ordered_extension.status` 为 `CHANGED` 当且仅当 `table_processing_mode` 非空（即空白变化也计入有序事实），补一行参数表。
- 关闭标准：参数表断言两者一致。处理时机：S2a 修改 comparison 时一并完成，不单独开修订轮。

### G8b-F2：最长子序列并列时，被标为移动的可能是绝对位置未变的行

- 类型：非阻塞建议（规格规则的已知后果）；是否阻塞：否
- 位置：`_backbone_indices` 的并列规则（规格 D1：before 侧下标字典序最小者）。
- 依据：探针“3 行整体反转”（A、B、C → C、B、A）：最长子序列长度为 1，按规则保留 A，报告 B、C 两行移动、`position_changed_count` 为 1；
  其中 B 的绝对位置没有变。实现与规格 D1 一致，结果确定、可重现；owner 已确认不要求精确位置。
- 最小修正方向：如需更直观，可把并列规则改为“先保留绝对位置不变的行，再按 before 顺序”，需同时保证 O(n log n) 与确定性；属于规格层面的选择，由 owner 决定，不要求在本步修改。
- 关闭标准：owner 决定保留现规则，或按新规则修改并补参数表。

### G8b-F3：风险契约中 `position_changed_count` 的语义未随 D3 更新

- 类型：非阻塞建议（文档）；是否阻塞：否
- 位置：`docs/backend-vnext/contracts/risk.md` 第 184 行。
- 依据：该文件列出 `position_changed_count`，但未写明它现在只计骨架行、不含移动行；规格 D5 没有把该文件列入改写范围，实施方按范围未改。
- 最小修正方向：S2a 涉及风险或比较文档时，改为引用 R5 §8。

## 3. 验收核对

| 验收项（G8b 规格 §7） | 结果 | 证据 |
| --- | --- | --- |
| §1 表格全部场景得到“应有结果” | 通过 | 审核探针（§4）：删除空白段之间的真实行 → 只有 1 条 `ROW_DELETED`，无空白记录，`SHIFT_REPAIRED`；空白段内插入真实行 → 1 条 `ROW_ADDED`，无空白记录；真实行移走 → 1 条 `ROW_MOVED`，无空白记录；空白段后追加真实行 → 1 条 `ROW_ADDED`，`TAIL_SEGMENT`；6 行中第 1 行移到末尾 → 1 条 `ROW_MOVED`；顶部插入空白行 → 1 条 `BLANK_INSERT_INTERVAL`、无有序记录、`position_changed_count` 5、`SHIFT_REPAIRED`。实施方的参数表 `BACKBONE_OUTCOMES` 覆盖同样 6 行与另外 13 行。 |
| 不再产生 `ORDERED_POSITION_CHANGED`；计数与 mode 按 D3 | 通过（G8b-F1 为边界情形） | 枚举值删除；`src`、`tests` 与现行契约文档中无残留（只剩治理计划中的历史叙述）。mode 判定顺序：移动 → `REORDER_COMPLEX`，位置后移 → `SHIFT_REPAIRED`，只有增删（含空白）且无内容修改 → `TAIL_SEGMENT`，有内容修改 → `LOCAL_PATCH`；“尾部新增加内容修改”记为 `LOCAL_PATCH`，与能力文档“不引发 position shift 的局部变更”一致。 |
| 空白行字段与写法仍被忽略；标准比较未变 | 通过 | 探针“只改空白行字段并互换 0/NULL”→ 表 `UNCHANGED`；标准比较代码（`standard.py`）不在区间内。 |
| 五包 ruff/mypy、`import_rules` 3 / 0 / 14；V 上 runner exit 0；provenance 与 carried | 通过 | 见 §4。 |
| golden 变化逐项说明 | 通过 | `vnext/fixtures/golden` 无比较事实，未改；既有断言的 4 处改动（`test_history_compare_jobs.py` 两处 `ROW_MOVED ×2 → ×1`、`test_comparison_artifacts.py` 两个 fixture 的输入）在 handoff §6 逐项对应到 D2、D3，断言意图未变。compose `ordered-b` 旅程断言未改，mode 由 `TAIL_SEGMENT` 变为 `SHIFT_REPAIRED`（原输入的位置后移不再产生记录），runner 中通过。 |
| 文档（D5） | 通过 | R5 §8–§9 写明骨架、并列规则、移动、位置后移的汇总方式与以骨架为边界的空白区间、各侧 occupancy digest 不随配对变化；`contracts/ordered-diff.md` 与 `capabilities/ordered-diff-compute.md` 改为引用 R5，并去掉了与 R5 不一致的“blank signature”表述。 |
| 停止条件（规格 §6） | 未触发 | 无规范存储、摘要、Submit 判定、标准比较、HTTP DTO 或前端可见记录种类的变化；`import_rules` 未增长，无新依赖；6 个场景都在 D1–D4 下得到应有结果。 |

## 4. 实际执行的检查

| 检查 | 命令或方法 | 结果 |
| --- | --- | --- |
| 审核者构造的场景 | 以 `tests/test_comparison_ordered.py` 的 SQL 物化辅助函数构造 12 组前后快照，直接运行 `compare_plan` | 规格 §1 的 6 个场景符合；另有空白段内 3→4（1 条空白插入、`SHIFT_REPAIRED`）、只改空白字段与写法（无变化）、尾部追加空白行（G8b-F1）、3 行反转（G8b-F2）、删除锚点行同时删除空白行（1 条 `ROW_DELETED` + 1 条空白删除）、完全相同（无变化） |
| D1 实现 | 读 `_backbone_indices` | 逆序耐心排序求每个下标起的最长长度，再按长度逐级取第一个可用下标，得到字典序最小的最长子序列；O(n log n)，无候选枚举与时间预算 |
| D4 实现 | 读 `_blank_gaps`、`_blank_extension` | 锚点只取骨架行；`anchors=None` 时每个真实行都是锚点，用于各侧 occupancy digest，与配对无关 |
| 五包 ruff 与 mypy | 各包 `uv-consume.sh run ruff check .` / `run mypy` | 全部 0 / 0 |
| `import_rules` | `tests/architecture_baseline.py` 三个基线计数 | 3 / 0 / 14 |
| focused 测试 | `test_comparison_ordered.py`、`test_comparison_artifacts.py`、`test_history_compare_jobs.py`、`test_architecture.py`、`test_surface_assembly.py` | 166 passed |
| V 的门禁记录 | `g8b-gate-V-run-tests-attempt1.summary`、runner 日志、provenance | runner exit 0；起止 HEAD 均为 V，status 为空；六个批次 242 / 152 / 154 / 2,748 / 1,681 + 1 skipped / 205 passed；日志无 FAILED 或 Traceback |
| carried 复核 | 在 `/home/dev/gdds-p5-g8b`：`git diff --name-only V H`；`build_context_digest.py identity`；以 project 名 `ordered-bisect-b-2338803-baseline` 执行一次 `docker compose build backend worker` | (a) 只有 handoff；(b) H 上的 identity（`29f7dfd3…`、`sha256:2c92331c…`）与 RS 镜像 label 相等；(c) backend `sha256:a6edaa61…`、worker `sha256:7417c158…` 与 provenance 相同。carried 成立 |

## 5. 验证限制与剩余前置

- 我没有重跑全量 runner；门禁结果取自实施方在 V 上的完整运行日志，并复核了日志、provenance 与 carried。
- RS 镜像 ID（`sha256:9733a906…`）与 G3 不同，但 build-input 与 source-tree label 相同；按 AGENTS 第 3 条，带 label 的镜像以 label 判定身份，ID 不同不影响结论。
- 真实数据上的效果（执行计划 §2 S2b 真实数据验收第 3 条）在 S2b 的 DC22 链路中验证，本步只用合成数据。
- G8b-F1、G8b-F3 并入 S2a；G8b-F2 由 owner 决定是否调整规则。
- 合并：`p5-g8b` 以 `--no-ff` 合并提交并入 `main`（`main` 若已被其他对话前进）；S2a 的区间起点为 `p5-g8b-exit`。
