# Phase 6 S1c 取证复核 3（ct108 2× t4 完整旅程停止）

状态：**停止原因是测量工具的核对缺陷，产品数据一致。** S1c 的核心验收已在本次运行中出现（2× t4 的 v1、v2 Submit 均无人工干预完成），但完整旅程尚未 exit 0。按第 4 节修正工具后，重跑一次完整旅程；1030b 对照可以先在本次运行的保留卷上进行。

## 1. 对象

- 取证合并提交 `78d8cf6727e05b810770a76ce9f51a38032217ef`：第一父为 S1c 候选 V=`3008d578cf`，第二父为工具提交 `20e6340526`（`p6-baseline`）。
- 节点 ct108（hostname `gw-dms-test`），project `s1c-v-3008-rerun-20e634`。运行时间 2026-10-31 03:04:04–05:44:35 UTC，exit 1。
- 日志 `/home/dev/gdds-p6-logs/s1c/ct108-2xt4-rerun-78d8cf6727/journey.log`，SHA256 `06750813…`（审核者在 ct108 上核对）；状态 `/home/dev/gdds-p6-logs/s1c/evidence/ct108-2xt4-rerun-78d8cf6727/{run.json,state.json}`。
- 保留卷：`s1c-v-3008-rerun-20e634_{backend-artifacts,backend-control,repository-service-data}`。1030b 卷未动。

## 2. 已通过的部分

| 步骤 | 结果 |
|---|---|
| backend/worker 镜像 | config digest 与全部 DiffID 与开发节点构建一致 |
| v1 Preview | SUCCEEDED，1733 s；631 表，全部为 changed |
| v1 Submit | SUCCEEDED，1446 s；`attempt_count=1`，`captured_session_count=1`，无人工恢复 |
| v1 repository-read | 通过（v1 中每个表都有逐表 artifact，工具的核对恰好成立） |
| repeat v1 Preview | SUCCEEDED，1424 s；0 changed |
| v2 Preview | SUCCEEDED，3374 s；631 表，64 changed |
| v2 Submit | SUCCEEDED，1307 s；`attempt_count=1`，`captured_session_count=1`，无人工恢复 |
| v2 repository-read | 失败：`synthetic Preview table count differs from its bundle closure` |

DC65 的目标行为已出现：等待 Repository 导入超过一个轮询窗口后经健康等待交接继续，没有消耗恢复会话，也没有人工干预。

## 3. 失败原因

- 失败位置：`real_dump_journey.py`（`p6-baseline`）中的 `_assert_synthetic_catalog_summary`。它把预览 bundle 的 `closure_entries` 中带 `table_name` 字段的条目去重计数，再与 Preview 汇总的 `table_count` 比较。
- 产品的 bundle closure 中有两类条目：
  - `SNAPSHOT_TABLE` 条目没有 `table_name` 字段，表名在 `table_bindings`（`pair_id`、`side`、`table_name`）中；相同内容的表快照会共享；
  - `RISK_ANNOTATION`、`RECORDS` 等逐表 artifact 带 `table_name`，只为有变化或有标注的表生成。
- 依据 `state.json` 中三份预览 manifest 的统计（审核者在 ct108 上只读计算）：

  | 预览 | `table_count` | 带 `table_name` 的去重表数（工具计数） | `SNAPSHOT_TABLE` 的 `side=current` 绑定表数 |
  |---|---|---|---|
  | v1 | 631 | 631 | 631 |
  | repeat v1 | 631 | 0 | 631 |
  | v2 | 631 | 50 | 631 |

- 结论：完整表集合在 `side=current` 的快照绑定中，三份预览都恰好是 631，与 `table_count` 一致，产品数据一致。工具把“有逐表 artifact 的表”当成“全部表”。v1 所有表都有变化，所以通过；v2 只有部分表有变化，于是失败。
- 这条核对是基准工具为合成 2× t4 新增的。此前的 401ed1 与 1030b 都停在 v1 Submit，v2 repository-read 的合成核对是第一次真正执行。
- v3-repository-read 使用同一函数（`third_preview_state`），修正前同样会失败。

## 4. 处置

1. **工具修正**（DC66 第 5 项常设授权，由基准会话在 `p6-baseline` 上另起提交）：
   - 期望表集合改为 `SNAPSHOT_TABLE` 条目的 `table_bindings` 中 `side == "current"` 的表名集合，要求其数量等于 `table_count`，并与 Repository Catalog 的表名集合相等；
   - 带 `table_name` 的逐表 artifact 只要求是该集合的子集；
   - v1、v2、v3 三处调用共用同一实现；
   - 补回归测试，覆盖三种形态：全部变化（v1）、零变化（repeat）、部分变化（v2）；
   - 05 focused 测试与五包静态检查通过后，再用本次 `state.json` 中的 v1、v2 manifest 只读验证新核对，结果应为 631。
2. **1030b 对照先行**：在本次运行保留卷的副本上，取 v1 Submit 的 Repository commit，按 DC66 修订第 1 项与 1030b 保留卷对照 Dolt 表哈希与 canonical state。原卷不写入。对照不一致时停止，交 owner。
3. **重跑完整旅程**：新的取证合并提交（V 加修正后的工具），在 ct108 跑一次 2× t4 完整旅程。
   - 本次运行没有设置 `checkpoint_before_steps`，所以无法按 DC66 第 3 项从 v2-repository-read 续跑。
   - 重跑时为写入步骤设置 checkpoint（至少 v1-submit、v2-preview、v2-submit、v3-preview、v3-submit），以后若再出现工具缺陷，可以从 checkpoint 续跑，不必整档重来。
   - 新 project 名，保留卷；exit 0 后对重跑的 v1 Submit 结果再做一次 1030b 对照，作为最终证据。
4. **保留**：本次运行的保留卷与日志作为诊断证据，保留到 S1c exit 合入之后再清理。

## 5. 结论

| 项 | 判定 |
|---|---|
| 产品 | 本次运行未发现产品问题。v1、v2 Submit 无人工干预完成；预览 bundle 的表集合与汇总一致 |
| 停止 | 正确。失败发生在被测对象运行之后，不属于 DC68 可重做的范围 |
| 下一步 | 按第 4 节修正工具、做 1030b 对照，再重跑一次完整旅程。重跑 exit 0 且对照一致后，S1c 证据齐全，交 owner 终审 |
