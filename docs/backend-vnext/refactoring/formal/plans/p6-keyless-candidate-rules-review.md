# Phase 6 keyless 表候选键与兜底规则讨论稿

> 状态：供 owner 与审核者讨论，不是已批准的 ruleset 决议，也不授权修改产品规则。
> 范围：汇总真实数据候选键普查，并记录 owner 对候选键、列判据兜底及 `forwardtable_*` 后续普查的补充意见。

## 1. 本次请审核的内容

1. 核对 8 份真实数据中 35 张 keyless 表的筛选范围、候选键统计和分组覆盖是否完整。
2. 评审拟议的逐表键、`BROWSE_ONLY` 处理以及低优先级的列存在自动选键规则。
3. 评审 `forwardtable_*` 的重复行/空点行后续普查，以及是否需要独立的 `KEYLESS_ORDERED` 存储类型。
4. 指出方案进入实现前还必须冻结的 Contract、manifest、比较、风险、golden 与 ruleset version 决策。

本稿中的业务规则均是讨论提案。除已有 DC29/DC16 外，不把下列新增内容记作 owner 已作出的最终决议。

## 2. 真实数据普查汇报

### 2.1 范围与方法

普查覆盖调试节点 `ct108-gw-dms-05` 上 t1–t4 的 v1、v2 共 8 份数据。使用现有 staging、解析、业务物化和规范投影；仅纳入规范投影后 `canonical_key_columns` 为空的表。忽略列不参与行列计数及候选键检查。业务单元格值没有写入 Git 中的报告。

运行记录、统计定义和逐表明细见[候选键普查报告](p6-keyless-candidate-census.md)。普查工具为[real_dump_keyless_census.py](../../../../../vnext/backend/benchmarks/real_dump_keyless_census.py)，提交 `e5840be32c06187c515f8ffc75ccc85291766baa`；backend Ruff、项目 mypy（486 个源码文件）和脚本定向 mypy 均通过。普查在 2026-10-26 运行完成；运行期间 `main` 正常推进，检查后确认普查涉及的脚本、规则、解析、物化、规范投影代码及数据包未变化。按 owner 指示未重跑。原始统计 JSON 和运行日志留在节点外日志目录，未提交。

### 2.2 整体结果

- 8 份数据合计纳入 35 个 keyless 表名；没有 DC29 清单以外的新表名。
- 22 张表有多个全局最小候选键；13 张表没有全局最小候选键；恰有一个全局最小候选键的表为 0。
- 5 张表在至少一份数据中有完全相同的重复行：`forwardtable_yc1`、`forwardtable_yc2`、`forwardtable_yk1`、`forwardtable_yt1`、`forwardtable_yx1`。
- 记录到 14 个只在部分数据集唯一的最小列组合；无含浮点列的全局候选键。
- 按当前 ruleset 类别，`forwardtable_*` 命中 `SNAPSHOT_ONLY`，`project` 命中 `BROWSE_ONLY`，其余普查表命中 raw-PK 兜底。普查表均以 keyless 规范键纳入。

候选键仅是“所测数据集中各键列非 NULL 且唯一”的统计事实，不单独证明业务身份。单行表和空表尤其不能据此确认自然键。

### 2.3 owner 提出的规则映射及数据覆盖

按本次提出的名称/列判据，35 张表均可归组。列存在判据是本轮规则提案，不等于普查已经证明这些列对所有未来数据都唯一且非空。

| 拟议处理 | 当前普查命中的表 | 数量 | 观察与限制 |
| --- | --- | ---: | --- |
| 显式指定 `comm_user_data` 键为 `data_key` | `comm_user_data` | 1 | 有记录的数据集均为单行；`data_key` 和 `data_val` 都是统计候选。选 `data_key` 是业务语义选择。 |
| `forwardtable_*` 空点/重复行专项处理 | `forwardtable_yc1`、`forwardtable_yc2`、`forwardtable_yk1`、`forwardtable_yt1`、`forwardtable_yx1`、`forwardtable_yx2` | 6 | 前 5 张至少一份数据有完全重复行；普查报告未检查单元格值，无法确认重复行是否为空点行。 |
| `forwardtbl_lst_*` 使用 `tbname` | `forwardtbl_lst_cs`、`forwardtbl_lst_dz`、`forwardtbl_lst_qt`、`forwardtbl_lst_ym`、`forwardtbl_lst_yc`、`forwardtbl_lst_yk`、`forwardtbl_lst_yt`、`forwardtbl_lst_yx` | 8 | 实际前缀是 `forwardtbl_lst_`。有行的 4 个系列中，`tbname` 均为全局最小候选键；另 4 个系列在现有 8 份数据中均为空。 |
| 显式指定 `mms_rp_cdc_index` 键为 `idx` | `mms_rp_cdc_index` | 1 | t4 v1/v2 各 42 行；`idx` 与 `cdc` 都是全局最小候选键。 |
| 显式指定 `(no, page_no)`，并按 `BROWSE_ONLY` 处理 | `iec61850c_cfg`、`jdxx_cfg` | 2 | 两列存在；报告列出的全局最小候选中有单列 `no`，没有将二列组列为最小键。选择二列组是有意的业务规则。 |
| 其余同时含 `no` 与 `page_no` 的已发现表，按名称列举并按 `BROWSE_ONLY` 处理 | `cnt_manage_cfg`、`dev104_cfg`、`iec101_cfg`、`iec104_cfg`、`iec104gw_cfg`、`nbridge_cfg`、`nr103d_cfg`、`nr103ht_cfg`、`project`、`sc_cfg`、`scada_cfg`、`sg_manage_cfg`、`sntp_cfg`、`vqc_cfg`、`wave_cfg`、`wf_cfg` | 16 | 合计 18 张表（连同前一组）。`cnt_manage_cfg`、`nr103ht_cfg`、`wf_cfg` 当前无行；`vqc_cfg`、`wave_cfg` 的最小候选中有单列 `no`，仍按约定选二列组。`project` 已是 `BROWSE_ONLY`。 |
| 对 keyless 表中同时含 `board` 与 `link_no` 的表使用该组合 | `out_time_cfg` | 1 | 现有数据全部为空，无法从行数据验证唯一性。 |
| **覆盖合计** | 以上各组，`project` 只计一次 | **35** | 未发现未归组的普查表。 |

`net_cfg` 不在本次 keyless 普查范围，现有 exact 规则已经使用 `(board, link_no)`。未来列判据兜底不得覆盖更高优先级的显式规则。

## 3. 讨论中的目标规则

### 3.1 已知表的逐表/逐系列意图

1. `comm_user_data`：使用 `data_key`。
2. `forwardtable_yc1`、`forwardtable_yc2`、`forwardtable_yk1`、`forwardtable_yt1`、`forwardtable_yx1`、`forwardtable_yx2`：暂不由本普查确认键；先对 `forwardtable_*` 做专项普查，查清重复行与空点行关系。
3. `forwardtbl_lst_*`：使用 `tbname`。空表系列按 owner 的语义判据指定，不把“当前没有重复”当作数据验证证据。
4. `mms_rp_cdc_index`：使用 `idx`。
5. `iec61850c_cfg`、`jdxx_cfg` 及第 2.3 节列出的其余 `(no, page_no)` 表：希望与 `project` 一样按 `BROWSE_ONLY` 处理。
6. `out_time_cfg` 及未来符合条件的 keyless 表：使用 `(board, link_no)`。

第 5 项同时要求显式存储键和 `BROWSE_ONLY` 行为；这是当前规则模型尚不能直接表达的组合，详见第 4 节。第 3、4 项的新增显式键会把当前 keyless 规范身份改为 keyed 规范身份。

### 3.2 低优先级列存在兜底

owner 提议在已有规则完成匹配后增加列存在自动选键逻辑，优先保留现有 exact、regex、ordered、protocol、browse/snapshot 等规则的处理。一个待审核的解释顺序是：

1. 先按当前 ruleset 解析并应用已命中的规则；不得由列判据覆盖已有显式规则。
2. 进入 raw-PK fallback 后，保留既有源 DDL 主键行为；仅当源 DDL 无主键、原路径将 keyless 时，才尝试列存在判据。
3. 若同时存在 `(board, link_no)` 与 `(no, page_no)`，按审核确认的固定优先顺序选择；若两组都不完整，则保持 keyless。
4. 对候选组做全表 NULL 与重复键验证。验证通过时选作键；遇到 NULL 或重复键时回退到 keyless，并触发一个额外处理调用。
5. 额外处理调用目前只描述为扩展点；是否在本阶段实现告警、调用失败是否影响导入、调用粒度和诊断字段均待审核。诊断不应携带业务单元格值。

需要审核确认第 2 步是否为本意，并确定第 3–5 步的确定性行为。由于按数据有效性回退会使同一表在不同快照间从 keyed 切换到 keyless，manifest 身份、比较对齐与风险语义必须有明确 Contract，不能作为隐含分支处理。

### 3.3 `forwardtable_*` 与 `KEYLESS_ORDERED` 候选类型

owner 提议接下来对 `forwardtable_*` 做专项普查确认，并把相关特殊情况作为 `KEYLESS_ORDERED` 类型的候选。该名称仅是提案，不是现有 ruleset 类型。

专项普查建议保持输出只含表名、列名、类型/状态分类与计数，不导出任何单元格值，至少确认：

- 完全相同重复行是否由业务定义的空点行造成；空点行由哪些列状态定义，是否存在非空字段不同但业务上同为空点的情况；
- 每份数据、每个 v1/v2 对的空点行计数、重复行计数与 schema 差异；
- 空点行拟规范化、保留 multiplicity、生成身份，还是仅在比较中作特殊处理；
- 如果顺序需要保留，顺序来源和稳定性是什么；输入排序变化是否改变 canonical identity；
- 表变化在 Preview/Review 中仍是表级内容事实，还是另增其他事实；是否完全不产生行级记录与风险。

当前 `forwardtable_*` 规范投影有 `gid`，但没有 `no`。既有 `ORDERED_DIFF` 要求 `gid` 身份键与 `no` 位置列；其 blank-row 处理不等于通用去重。因此 `KEYLESS_ORDERED` 如有必要，应明确为独立存储/比较语义，不直接套用现有 `ORDERED_DIFF`。

## 4. 与现有规则和 Contract 的关系

1. `^forwardtable_.*$` 当前命中 `SNAPSHOT_ONLY`；`project` 当前命中 `BROWSE_ONLY`；其余 census 表命中 raw-PK fallback。DC29 允许这三类规则在没有 DDL 主键时以 keyless 存储。[现有 registry](../../../../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py) [DC29](p5-arch-closure-s0-owner-decisions.md#dc29-无主键表的兜底规则)
2. `SNAPSHOT_ONLY` 与 `BROWSE_ONLY` 都不产生行级比较记录/风险；DC16 仍要求变化以表级事实可见。因此“只存、不做行级 diff/risk”与“不产生任何变化事实”是不同要求，需在 `forwardtable_*` 专项普查后确认。
3. 当前规则校验限制 `SNAPSHOT_ONLY`、`BROWSE_ONLY` 使用 `DDL_PRIMARY_KEY_OR_KEYLESS` 且禁止比较键；`BROWSE_ONLY` 选择器为 exact。若第 3.1 节第 5 项要求 BROWSE_ONLY 同时存显式 `(no, page_no)`，须将 canonical storage key 与 comparison key 解耦，或改变角色/规则约定。[角色规则校验](../../../../../vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py)
4. selector 目前是 `EXACT`、`REGEX`、`FALLBACK`，不按 schema 列集合匹配。列存在兜底属于规则语义扩展；应明确其适用在 raw-PK fallback 内部、已有源 DDL 主键之下，并定义 key pair 冲突优先级。[selector 类型](../../../../../vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py)
5. 将当前 keyless 表改成 explicit keyed 会改变 `canonical_key_columns`，属于 `STORAGE_BREAKING`。keyless Contract 要求完整保留重复行，不去重；如 forwardtable 空行策略要删除或合并行，需要明确这是语义修订而非普通键规则调整。[Canonical Storage Contract](../contracts/canonical-storage-and-repository-boundary.md) [DC29](p5-arch-closure-s0-owner-decisions.md#dc29-无主键表的兜底规则)
6. DC50 已要求重要 keyless 表的自然键业务评估在 S1b kickoff 之前完成。本次 owner 补充是在这项业务评估中新增的候选方向；最终规则、角色和 golden 仍需审核与 owner 确认后再写入决议和实现计划。[DC50](p6-s0-owner-decisions.md#dc50-phase-6-阶段结构与前置验证任务)

## 5. 请审核者与 owner 讨论确认

1. **BROWSE_ONLY 的显式存储键**：第 2.3 节 18 张含 `(no, page_no)` 的表都按名称登记为 BROWSE_ONLY；是否还要把该二列组作为 canonical storage key？若是，是否接受扩展 Contract/manifest，使存储键与比较键分离？`project` 是否沿用相同键？
2. **未来新表的处理角色**：列存在 fallback 命中的新表只自动选择键，还是也自动归入 BROWSE_ONLY？已知表按名称列为 BROWSE_ONLY、未来表仍沿 raw-PK fallback 的 STANDARD_DIFF，会产生相同列判据但不同比较语义。
3. **键组选择与验证**：当两组候选列同时存在时的优先级；源 DDL 主键优先级；NULL/重复时 keyless 回退的有效范围；无效时追加调用的行为、失败语义与稳定诊断。
4. **数据有效性导致的身份切换**：同一表某个快照键有效、另一个快照键无效时，是否接受 keyed/keyless 存储身份变化；如何对齐比较、呈现状态、触发审核/告警，并避免误当普通 schema 变化。
5. **`KEYLESS_ORDERED` Contract**：专项普查后是否需要该类型；其顺序来源、空点定义、重复行保留/规范化、摘要、表级事实和与现有 `ORDERED_DIFF` 的边界。
6. **DC29/S1b 落点**：确认后需更新哪些 owner 决议、Canonical Storage/Ruleset Contract、ruleset version/digest、storage projection version、golden 与测试。启用 explicit key 或更改空行规范是否改变 storage projection version，应按最终规范字节影响另行判定。

## 6. 建议的评审结论格式

审核完成后按下表记录，不在本稿中预填结论：

| 事项 | owner 决定 | Contract / 决议落点 | 验证与 golden | 状态 |
| --- | --- | --- | --- | --- |
| 已知逐表显式键 | 待确认 | 待确认 | 待确认 | 讨论中 |
| `(no, page_no)` 表的 BROWSE_ONLY 与 storage key | 待确认 | 待确认 | 待确认 | 讨论中 |
| 列存在 fallback 的适用条件和优先级 | 待确认 | 待确认 | 待确认 | 讨论中 |
| NULL/重复键回退及额外调用 | 待确认 | 待确认 | 待确认 | 讨论中 |
| `forwardtable_*` 专项普查及空点语义 | 待普查并确认 | 待确认 | 待确认 | 待处理 |
| 是否引入 `KEYLESS_ORDERED` | 待确认 | 待确认 | 待确认 | 讨论中 |

本稿与候选键普查报告均不修改生产规则，不作“应补键”的最终判断，不推送任何提交。
