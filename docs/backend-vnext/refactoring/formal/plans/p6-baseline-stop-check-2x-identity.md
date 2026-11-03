# Phase 6 重建对照基准：W4 重新生成后 2× 输入身份停止复核

- 结论：**生成工具缺陷，不是产品问题，也不是输入数据变化。** W4 修正（`1495aac33c`）把特殊点表的 `name`、`dev_addr` 加入共用的受保护列，而 2× 生成 `make_2x` 也用这份列表挑选第二份副本要扰动的列，于是 2× v1/v2 跟着变了。W4 修正本身有效：新输入三个根的全部数据集 census 都是 COMPLETE。修正工具，让 2× 输出与已接受包逐字节相同，然后重新生成；不需要新的 owner 决议。
- 日期：2026-11-03。
- 对象：ct108 输入根 `/home/dev/gdds-p6-logs/baseline/input/w4-generator-correction-20261102c`（工具 HEAD `28229aedf7`），handoff 提交 `4cda5bf159`。
- 依据：DC66 第 5 项；DC66 澄清第 1 项（2× 不变，程序验收）；[W4 停止复核](p6-baseline-stop-check-w4.md)。

## 1. 核对结果

审核者在 ct108 只读比较三个输入根中 2× v1/v2 包内 `dbcfg.sql` 的逐表摘要，只输出表名：

| 比较 | v1 | v2 |
| --- | --- | --- |
| 已接受 `1ed24d38f0` 对 20261102b（修正前代码 `d7ca40162c`） | 639 张表全部相同 | 639 张表全部相同 |
| 已接受 `1ed24d38f0` 对 20261102c（修正后代码 `28229aedf7`） | 8 张不同 | 8 张不同 |

不同的 8 张都是特殊点表的第二份副本：`device_st__x2`、`device_mx__x2`、`device_co__x2`、`device_sg__x2`、`device_sp__x2`、`device_cnt__x2`、`device_sn__x2`、`device_tap__x2`。第一份副本和其余表没有变化。

20261102c 三个根（2×、W4 10%、W4 100%）的 census 中，8 个数据集的 materialization 与 ordered projection 都是 COMPLETE。

## 2. 根因

- `make_2x` 对每张非空表调用 `_mutator_for`，在第一个不受保护的列上扰动第二份副本的全部行。
- `1495aac33c` 为解决 W4 中 “duplicate special point name ''”，在共用的 `_protected_columns` 中对 `SPECIAL_POINT_TABLES` 加入 `name`、`dev_addr`。2× 因此在这 8 张表上改选了别的列。
- 2× 第二份副本的表名带 `__x2` 后缀，产品不把它们当作特殊点表，原先扰动 `name` 并无问题。已接受的 2× 输入有效，已完成的 2× 场景不受影响。
- W4 两档的 v1 都是 2× v1，W4 v2 也由 2× 包派生，所以 20261102c 的 W4 输入同样作废。

## 3. 为什么程序验收没有拦住

- 生成器的重复生成检查只比较同一次运行的两次输出，代码改变后两次输出依然一致。
- 审核者的 `check-baseline-inputs.py` 只核对包与本次生成摘要一致，不核对与已接受输入相同。它适合首次输入验收，不适合重新生成。实施方按 DC66 澄清第 1 项另外做了程序比较，发现不符后停止，处置正确。

## 4. 处置建议

1. **修正工具**（DC66 第 5 项，只改 `vnext/backend/benchmarks/` 及其测试）：特殊点列保护只作用于 W4 的变异与插入，`make_2x` 恢复修正前的列选择。focused 测试：同一份含特殊点表的输入，2× 第二份副本的扰动列与修正前相同；W4 仍不改动特殊点的 `name`、`dev_addr`。在 05 运行 focused 测试与五包 ruff/mypy。
2. **把 2× 身份写进生成器验收**：生成 2× 后立即读取 `input/1ed24d38f0/input-summary.json` 中的 `2x_t4_v1`、`2x_t4_v2` SHA256 与新包比较，不符就失败，不再继续生成 W4 与 census。
3. **重新生成**到新的输入根，例如 `w4-generator-correction-20261103a`；20261102b、20261102c 保留为无效输入证据，不覆盖 `1ed24d38f0`。验收全部由程序给出：2× SHA256 等于已接受值、全部 census COMPLETE、重复生成一致、逐表 W4 计数、期望输入清单。满足后直接继续，不另设 owner 检查点。
4. **handoff**：记录本次根因、修正提交、20261102c 的作废原因，并更新剩余估计。重新生成约 8 小时；超过 48 小时停止阈值时停下交 owner。
