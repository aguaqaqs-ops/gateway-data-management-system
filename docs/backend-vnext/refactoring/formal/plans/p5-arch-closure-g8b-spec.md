# P5 架构收口 G8b：有序比较的骨架、移动与位置变化

日期：2026-10-11

状态：**已实施并通过独立审核（2026-10-11，tag `p5-g8b-exit`）**。owner 已决议（2026-10-11）：G8b 作为独立一步；`ORDERED_POSITION_CHANGED` 聚合；只改空白行字段的上传接受现状。§3 的 D1–D4 细节由审核方按决议补出，owner 已确认（2026-10-11）。
顺序：G3 审核通过并并入 `main` 之后、S2a 之前。

关联：[治理修订计划](p5-arch-closure-post-s1-governance-plan.md) G8（决议）；[R5 比较设计](p3-r5-comparison-design.md) §8–§9；
[G8a 独立审核](p5-arch-closure-g8a-independent-review.md)；`vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py`。

## 1. 背景与目标

owner 确认的有序表空白行语义（与 R5 §9 一致）：

- 空白行（`gid` 为 NULL、0 或空串）没有业务意义；字段变化不比较；三种写法等价，物理存储可以归一化（现已统一为 pseudo gid）；
- 空白行的新增、删除必须体现，否则真实行的位置变化看起来像大范围漂移；
- 不要求精确位置：一段空白行内新增一行，显示在该段的任何位置都可以。

审核方用合成数据直接运行现有比较（未读真实数据）发现两处实现偏离 R5，一处展示问题：

| 场景 | 应有结果 | 现有结果 |
| --- | --- | --- |
| 删掉两段空白之间的一个真实行 | 无空白记录 | 2 条空白删除 + 1 条空白插入 |
| 在空白段中间插入一个真实行 | 无空白记录 | 1 条删除 + 2 条插入 |
| 真实行移到别处，空白行未动 | 无空白记录 | 1 条删除 + 1 条插入 |
| 在空白段之后追加一个真实行 | 无空白记录 | 1 条删除 + 1 条插入 |
| 6 个真实行中把第 1 行移到末尾 | 1 条 MOVED | 6 条 MOVED |
| 顶部插入 1 个空白行，后面 5 个真实行 | 1 条空白插入 | 1 条空白插入 + 5 条 POSITION_CHANGED |

原因：

1. 空白区间以“每一侧最近的真实行”为边界（`_blank_runs`、`_blank_anchor`），而 R5 §9 规定按 real-row backbone 划分；真实行在空白段旁边增删或移动，就被算成空白行增删。
2. 移动判定把两侧共有行的序列逐位置比较（`_build_fact` 的 `moved_keys`），一次移动会把中间所有行标为移动。legacy 用最长递增子序列确定不动的骨架。
3. 每个因插入、删除而位置后移的真实行都产生一条 `ORDERED_POSITION_CHANGED`，真实表上会有数千条。

目标：比较只报告真实发生的变化。空白记录只反映各骨架区间内空白行数的净变化；一次移动只标出被移动的行；插入、删除引起的位置后移只以表级汇总体现。

非目标：不改空白行字段的比较方式（继续完全忽略）；不改 pseudo gid 的分配（按空白行在 `no` 顺序中的先后编号）；
不改规范存储、规范内容摘要与 Submit 判定（只改了空白行字段的上传：Preview 无变化，Submit 照常生成新版本，owner 接受）；不改标准（非有序）比较。

## 2. 现状要点

- `_read_ordered_rows` 按 `no` 排序，空白行 `blank=True`，真实行带 `stable_key` 与 `stable_identity`（只对 `gid` 列取摘要）。
- `_build_fact`：真实行按 `stable_key` 求新增、删除、修改；`moved_keys` 逐位置比较；`position_changed_keys` 逐行产生记录；`_processing_mode` 从不返回 `SHIFT_REPAIRED`。
- `_blank_extension`：两侧各自求空白段，以 `(before_anchor, after_anchor)` 为键比较行数；`before/current_occupancy_digest` 是各侧自身的空白分布摘要。
- `ORDERED_POSITION_CHANGED` 的消费方只有记录本身；`OrderedSummary.position_changed_count` 被 `row_encoding.py` 与 `surface_assembly/_assembly.py` 读取。没有 HTTP DTO 枚举或前端引用该记录种类。

## 3. 设计决定

**D1 骨架（backbone）。** 两侧都存在的真实行，按 before 侧的 `no` 顺序排列，取其 current 侧位置序列的最长递增子序列，子序列中的行构成骨架。
有多个最长子序列时取确定的一个：按 before 顺序逐个比较，优先保留 before 侧位置较前的行（实现须确定、与输入顺序以外的因素无关，并用测试固定）。
复杂度不高于 O(n log n)，不引入候选枚举或时间预算。

**D2 移动。** 两侧共有、但不在骨架中的真实行记为 `ORDERED_ROW_MOVED`（一条移动只标出被移动的行）。`row_moved_count` 等于这些行数。

**D3 位置变化聚合。** 删除 `OrderedRecordKind.POSITION_CHANGED` 及其记录。骨架行中 `no` 改变的行数仍记入 `OrderedSummary.position_changed_count`（不含移动行），
作为表级汇总；有这类行且没有移动时，`table_processing_mode` 为 `ORDERED_SHIFT_REPAIRED`（中间插入或删除引起的整体后移）；
只有尾部新增、删除时为 `ORDERED_TAIL_SEGMENT`；有移动时为 `ORDERED_REORDER_COMPLEX`；只有内容修改时为 `ORDERED_LOCAL_PATCH`。实施者按这四种情形核对 `_processing_mode`，判定依据写进测试参数表。

**D4 空白区间。** 空白段的边界改为骨架行：两侧都以“最近的骨架行”为锚点，不在骨架中的真实行（新增、删除、移动）对空白分段透明。
每个锚点对内比较两侧空白行数，净增记一条 `BLANK_INSERT_INTERVAL`，净减记一条 `BLANK_DELETE_INTERVAL`，`row_count` 为差值；区间位置取该锚点对内首末空白行的位置（不要求精确到行）。
`before/current_occupancy_digest` 保持为各侧自身的空白分布摘要，不随配对变化。空白行字段与空白写法继续不参与比较。

**D5 文档。** R5 设计 §8 删去 `ORDERED_POSITION_CHANGED` 记录，改为“位置后移只计入表级汇总与 `ORDERED_SHIFT_REPAIRED`”；§8–§9 写明骨架按最长递增子序列确定、空白区间以骨架行为边界。
旧文档 `docs/backend-vnext/contracts/ordered-diff.md` 与 `docs/backend-vnext/capabilities/ordered-diff-compute.md` 中列出 `ORDERED_POSITION_CHANGED` 或“blank signature”的地方，改为引用 R5 §8–§9，不重写其余内容。

## 4. 范围

- `capabilities/comparison/ordered.py`（`_build_fact`、`_blank_runs`、`_blank_anchor`、`_blank_extension`、`_processing_mode`）；`capabilities/comparison/contracts.py`（删除 `POSITION_CHANGED` 枚举值）；
  受影响的 `row_encoding.py`、`surface_assembly/_assembly.py` 只在需要时调整；
- 测试：`tests/test_comparison_ordered.py` 增加 §1 表格全部场景的模块级参数表，另加：空白段内增删、空白与真实行混合增删、多个最长子序列时的确定选择、
  `table_processing_mode` 四种情形；既有断言随 D3 更新；
- golden 与 compose 旅程：有序比较的事实、摘要或 golden 若变化，按项目前提直接更新，并在 handoff 逐项说明原因（S2b 的“History ordered 旅程结果不变，或在 handoff 说明变化原因”同样适用）；
- 文档按 D5。

## 5. 提交与门禁

形态同 G3（规格 §6）：独立 worktree `/home/dev/gdds-p5-g8b` 与短期分支 `p5-g8b`，从 R0 切出（R0 为 G3 并入 `main` 且审核方文档更新之后的 HEAD）；新 worktree 先建 `legacy` 符号链接。

1. `docs(p5-g8b)`：D5 文档改写；
2. `fix(p5-g8b)`：D1–D4 实现与测试；
3. 门禁提交 V 为最后一个非 handoff 提交：改动 `backend/src`，在 V 上重建并完整运行权威 runner；H 只改 handoff，carried 在同一 worktree 判定；
4. 独立审核通过后在报告提交上打 `p5-g8b-exit`，并入 `main`；S2a 的区间起点改为 `p5-g8b-exit`。

## 6. 停止条件

- 需要改变空白行字段的比较、pseudo gid 分配、规范存储或摘要、Submit 判定；
- 需要改变标准（非有序）比较的行为；
- 新增 HTTP DTO 字段或前端可见的新记录种类；
- `import_rules` 增长或需要新增依赖；
- 某个场景无法在 D1–D4 下得到 §1 表格的“应有结果”。

## 7. 验收

- §1 表格全部场景得到“应有结果”，由参数表证明；
- 不再产生 `ORDERED_POSITION_CHANGED` 记录，`position_changed_count` 与 `table_processing_mode` 按 D3；
- 五包 ruff/mypy、`import_rules` 3 / 0 / 14；V 上权威 runner exit 0，provenance 与 carried 记录齐全；golden 变化逐项说明；
- 独立审核通过。

## 8. 与 DC22 的关系

S2b 的真实数据验收（执行计划 §2 S2b）对有序表的第 3 条预期依赖本步：同项目 v1→v2 中，空白记录只反映空白行数的净变化，真实行的增删和移动不产生空白记录，一次移动不把其他行标为移动。
