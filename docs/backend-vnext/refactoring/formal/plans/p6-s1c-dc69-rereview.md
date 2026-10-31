# Phase 6 S1c：DC69 修复的针对性复审

状态：**通过。** 可以按 DC69 第 2 项开始取证。

## 1. 对象

- 原候选 V=`3008d578cf`；新代码候选 V'=`ebd1b60a3f`（提交 `19727b1502`、`ebd1b60a3f`），handoff H=`0d032ff13b`，分支 `p6-s1c-impl`，clean，未推送。
- `V..V'` 代码差异 4 个文件（`_changeset.py`、`recovery.py` 与两份测试），其余为 handoff。

## 2. 核对

| 项 | 结果 |
|---|---|
| 修复 | `_patch_mutations` 分别收集 DELETE、UPDATE、INSERT，组内仍按 `key_bytes_for_ordering` 排序，按三组顺序输出；`_rebuild_mutations` 未改。与 `validate_change_set_ordering` 的阶段与组内口径一致 |
| 权威测试 | `test_patch_mutation_closure_orders_mixed_row_changes_by_operation_phase`：主键按字节序为 `0`、`1` 的两行 UPDATE，`399` 一行 DELETE，`400` 一行 INSERT。修复前输出 UPDATE、UPDATE、DELETE，会命中同一 ValueError；修复后断言校验通过、三组的顺序与行镜像、渲染 DML 顺序，并固定新的 change-set 与 closure digest。只有这一个测试，没有同义重复 |
| 日志 | 兜底分支加 `_LOGGER.exception`；worker 启动时 `logging.basicConfig(level=INFO)`，堆栈会进入 worker 日志。diagnostic 仍为 `pure-recompute handler raised <类型>`，测试断言异常正文不进入 diagnostic |
| 05 验证 | 审核者在 05 核对：worktree HEAD 为 V'，clean；focused 167 passed（`c7b9436f…`）；五包静态检查（`31e08b48…`）；修复后的最小复现（`56190283…`）。SHA256 与 handoff 一致 |
| DC68 记录 | 首次环境同步因 PATH 缺 Rust 工具链，在运行测试前退出，修正后重做；日志保留。符合 DC68 |

## 3. 观察（不阻塞）

- 权威测试手工构造 `StorageMutationPlan` 与 `TableMutationDecision`，经 `build_change_set_closure` 进入，没有走 planner 的表级选择。DC69 的提示词允许这个入口，ct108 三节点旅程会在真实数据上覆盖整条路径。
- 渲染 DML 的断言 `"0" in statements[1]` 偏弱，前面已有逐项的行镜像断言，不影响结论。

## 4. 下一步

按 DC69 第 2 项取证：
1. 开发节点预构建 V' 的 backend/worker 镜像，按 config digest 与全部 DiffID 核对后传到 04、05、ct108。
2. 04 跑六包权威 runner。
3. 05 跑 t1。
4. ct108 跑一次 2× t4 三节点完整旅程，并做两项只读对照。
