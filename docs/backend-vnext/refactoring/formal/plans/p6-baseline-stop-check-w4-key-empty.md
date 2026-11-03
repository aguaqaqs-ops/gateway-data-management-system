# Phase 6 重建对照基准：W4/S4/H1 v2 Preview `KEY_EMPTY` 停止复核

- 结论：**测量工具的生成缺陷，不是产品缺陷。** W4 生成器给源数据中的空表补一行时，在字符串 key 列写入空字符串。产品拒绝空字符串 key，这是 P3-R4 起就有的既有规则，处置正确。W4 10%、100% 两份输入都作废，W4、W4-FULL、W4-STRESS 都要等新输入。修正工具，并把 W4 输入的程序验收扩大到全表规范投影，重新生成后从头重跑 W4/S4/H1。不需要新的 owner 决议（DC66 第 5 项）。
- 日期：2026-11-03。
- 对象：
  - ct108 project `p6bw4s4h120261103a`，HEAD `fc8e7b1e7a`（生成工具 `195cf377a4`）。
  - 证据目录 `/home/dev/gdds-p6-logs/baseline/scenarios/ct108-w4s4h1-20261103a/`。
  - handoff 提交 `8b8c4481a8`。
- 依据：DC66 第 3、5 项；DC68；[W4 停止复核](p6-baseline-stop-check-w4.md)；[2× 身份停止复核](p6-baseline-stop-check-2x-identity.md)。

## 1. 核对结果

| 项 | 结果 |
| --- | --- |
| 运行 | 2026-11-03 15:54:24–17:54:02Z，runner exit 1。<br>v1 全流程与 repeat-v1 通过；v2 Workspace、Upload 通过；v2 Preview 的 operation 为 `FAILED`。<br>审核者在 ct108 重算 launcher、launch、resources、input-provenance、run.json、state.json、postflight、image-identity 的 SHA256，与 handoff 一致 |
| 身份与输入 | V′ 镜像身份 MATCH；运行后输入来源 MATCH。v2 上传的是 W4 10% 包 `a79bb463…`，与期望清单一致 |
| 失败详情 | 审核者在保留卷 `p6bw4s4h120261103a_backend-control` 的副本上只读查询 `operation_records`。<br>Preview 的 `materialize_inputs` step 失败，8 条 `KEY_EMPTY`，`side=MODIFIED`，`omitted_count=0`：<br>`forwardtbl_lst_cs`、`forwardtbl_lst_dz`、`forwardtbl_lst_qt`、`forwardtbl_lst_ym` 的 `tbname`；<br>`nr103ht_dev_list`、`nr103ht_dev_list__x2`、`nr103ht_ykytbs_list`、`nr103ht_ykytbs_list__x2` 的 `col_name` |
| 节点 | 无容器、无旅程进程；占用标记已释放；三卷保留；磁盘剩余 217 GiB |

## 2. 根因：空表的补充行在 key 列写入空字符串

- **12 张表在源数据中为空。** 失败的 8 张表，加上 `forwardtbl_lst_{cs,dz,qt,ym}__x2`，在 2× 源中都是 0 行。生成摘要（`input-summary.json` 的 `w4_10pct.tables`）对这 12 张表都记为 `before=0, inserted=1`。
- **补充行写入空字符串。** `_make_w4` 对空表调用 `_default_row` 补一行。`_default_row` 只对可空、未受保护的列写 `NULL`；受保护的字符串列一律写 `''`，key 列正是受保护列。
- **产品按规则拒绝。** 产品的规范投影（`storage_projection/project.py` `_row_key`）对 key 中的 `NULL` 判 `KEY_NULL`，对空字符串判 `KEY_EMPTY`。
  - 失败的 8 张表，key 都含字符串列：`forwardtbl_lst_*` 的表规则 key 是 `tbname`；`nr103ht_*` 及其 `__x2` 副本的 key 含 `col_name`。
  - `forwardtbl_lst_*__x2` 不匹配原表规则，也没有主键，是 keyless 表，所以通过。
  - 审核者在 ct108 用生成器自己的解析与规则解析，逐表统计 2× v1、2× v2、W4 10% 三份 SQL 中 key 含空字符串的行，只输出计数。全部 638 张表中只有 W4 10% 的这 8 张表各 1 行；2× v1/v2 为 0。`forwardtbl_lst_*` 的 `tbname` 可空，但作为受保护列也被写成 `''`；改写成 `NULL` 也会被判 `KEY_NULL`。
- **缺陷由来已久。** `_default_row` 的这个写法从 S1b（`p6-s1b-exit`）就有。W4 输入此前从未经过产品 Preview：S1b 只运行了生成器，上一次 W4 运行在第一个 operation 之前就因 census 停止。
- **两份 W4 输入都受影响。** W4 100% 对同样 12 张表补了同样的行，所以 W4、W4-FULL、W4-STRESS 用现有输入都会在同一位置失败。2× 输入不补行，不受影响；已完成的 2× 场景有效。

## 3. 为什么程序验收没有拦住

- 上次复核建议把 census COMPLETE 作为生成后验收（[W4 停止复核](p6-baseline-stop-check-w4.md) §5 第 1 项），实施方已经照做。但 census 的规范投影只对 `composite_signal_point` 一张表运行（`real_dump_census.py` 中 `project_canonical_table_set(selected_table_set, ...)`）。其余 638 张表只核对 business materialization 与 ordered 投影，不经过 key 规范化。所以 census COMPLETE 不能保证 Preview 的 `materialize_inputs` 通过。
- 这是审核方建议的验收范围不足。实施方按产品失败停止正确：失败发生在被测对象运行之后，DC68 的重做不适用。

## 4. 处置建议

1. **修正工具**（DC66 第 5 项，只改 `vnext/backend/benchmarks/` 及其测试）：
   - `_default_row` 对 key 列（表规则 compare key，没有时取主键）中的字符串列写非空值，例如 `_fresh_values` 的第一个候选值；非 key 列保持现状。
   - focused 测试：一张 key 为字符串列的空表，W4 补充行通过 `project_canonical_table_set`。表规则 key（含可空列）与主键两种情形各一例。
   - 在 05 运行 focused 测试与五包 ruff/mypy。
2. **扩大 W4 输入的程序验收**：
   - 生成每份 W4 输入后，对全部表运行与 Preview `materialize_inputs` 相同的路径：business materialization 加全表 `project_canonical_table_set`。要求状态 COMPLETE、诊断为 0，否则生成失败。
   - 2× v1/v2 也跑一次，作为对照，预期通过。
   - 这项检查放在生成器或 census 中，在 Compose 启动之前完成。
3. **重新生成**到新的输入根，例如 `w4-generator-correction-20261104a`。
   - 保留现有验收：2× SHA256 等于已接受值，census COMPLETE，重复生成一致，逐表计数，期望输入清单。
   - `20261103a` 保留为无效输入证据，不覆盖。
   - 验收全部由程序给出，满足后直接继续，不另设 owner 检查点。
4. **从头重跑 W4/S4/H1**，使用新的 project 名与新的期望清单。
   - 不从本次 checkpoint 续跑：`v2-preview` checkpoint 已含错误输入的上传；更早的 checkpoint 要换期望清单，来源链变复杂。省下的约 1.5 小时不值得。
   - 本次 v1 各步计时只作为证据保留，不作为测量结果。
5. **场景顺序**：
   - H2 三节点与 H3 不依赖 W4 输入，可以现在继续。
   - 生成器修正在开发节点和 05 进行；重新生成在 ct108 上，安排在两个场景之间，不与测量重叠。
   - 新输入通过验收后，依次运行 W4/S4/H1、W4-FULL、W4-STRESS。
6. **清理**：`p6bw4s4h120261103a` 的三卷在 handoff 记下卷摘要后删除；evidence 目录与 checkpoints 保留到基准终审。
7. **handoff**：记录根因、修正提交、`20261103a` 的作废原因，并重新估算剩余时间。重新生成约 8 小时，加剩余场景。估计超过 48 小时就停下交 owner。
