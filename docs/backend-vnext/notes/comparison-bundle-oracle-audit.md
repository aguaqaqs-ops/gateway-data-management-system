# Comparison / Bundle Oracle Audit

本文记录旧实现中值得迁移的业务语义。旧实现只作为 oracle：可以借鉴规则、样例和失败场景，但不能成为 vNext runtime fallback，也不能把旧 bundle sidecar 或旧 Workbench payload shape 直接提升为正式 contract。

## Sources Inspected

| Source | Role in old implementation | Oracle value | Migration boundary |
| --- | --- | --- | --- |
| `gateway-data-management-system/backend/workbench/navigation.py` | 旧 Workbench sidebar、业务分组、转发通道、通讯规约、二次装置 tab 导航。 | 业务表归类、通道 key、label、tab family、resolution warnings。 | 迁移为 vNext business projection capability；不复用旧 sidebar DTO。 |
| `gateway-data-management-system/backend/workbench/secondary_device_projection.py` | 旧二次装置 projection 与 risk 聚合。 | `dev_addr` / `gid` identity、重复诊断、device/tab 风险聚合。 | 迁移为正式 projection/risk annotation 输出；不复用 preview bundle id/revision 字段。 |
| `gateway-data-management-system/backend/workbench/contracts.py` | 旧二次装置 identity index。 | device rows 按 `dev_addr` 建索引，`gid_by_dev_addr` 从 `device.gid` 派生，tab rows 支持 int/string 双 key 查找。 | 可迁移为 projection helper；保持 flow-neutral。 |
| `gateway-data-management-system/backend/workbench/table_labels.py` | 旧表显示名解析。 | `device` -> `装置总表`，`net_cfg` -> `网口配置表`；优先 metadata display name / SQL comment。 | 迁移为 display metadata policy；不绑定旧 table object。 |
| `gateway-data-management-system/backend/backend_vnext/capabilities/table_rules/registry.py` | 当前 vNext table rules。 | 已包含 IEC104 ordered families、protocol cfg pattern、device point tables、`net_cfg` key。 | 作为新实现落点和冲突检查基准。 |
| `gateway-data-management-system/backend/backend_vnext/capabilities/risk_evaluation/rules/ordered.py` | 当前 vNext ordered risk rule。 | ordered replacement、name update、content update、move/blank/degraded 语义。 | 后续 ordered/risk slice 继续补齐 parity 和性能。 |
| `docs/backend-vnext/contracts/ordered-diff.md` | ordered diff 旧语义迁移记录。 | IEC104 family、`gid/no`、pseudo blank、degraded/unsupported 对齐目标。 | 继续作为 ordered diff slice 的设计输入。 |

## Semantic Mapping

| Domain | Old source | Old semantic rule | vNext current state | Target owner | Decision | Open questions |
| --- | --- | --- | --- | --- | --- | --- |
| Sidebar groups | `navigation.SIDEBAR_GROUPS` | 分组为 `forward_tables`、`secondary_device_list`、`communication_protocol_list`、`global_parameters`、`forward_table_group_info`、`unparsed_tables`，中文 label 分别为转发通道、二次装置列表、通讯规约列表、全局参数、转发通道分组信息、未解析表。 | 正式 surface 已有 table summary，但业务分组仍不完整。 | Business projection + surface assembly | 保留业务分组语义，改名为正式 projection group，不继承旧 sidebar payload shape。 | `forward_table_group_info` 是否仍需要独立一等分组，还是可并入 global/diagnostics，需要业务确认。 |
| Table group fallback | `sidebar_group_for_table` | 转发协议表归 forward；`device`/`device_*` 归 secondary；`project`/`prot_list`/`app_cfg` 归 global；`net_cfg`/`com_cfg`/`prot_right`/protocol cfg 归 communication；无法识别归 unparsed。 | vNext table rules 可识别大量表的 compare role，但不产出业务分组。 | Business projection | 保留分类规则，作为 projection 的 table-to-domain policy。 | `app_cfg` 派生目标表在正式 surface 中是否应展开为 global 子项。 |
| Forward channel key | `_index_net_cfg_rows` | 从 `net_cfg.board` 和 `net_cfg.link_no` 解析整数，stable key 为 `b{board}_n{link_no}`；重复 key 只取第一行；无法解析整数的行跳过。 | `TableRuleRegistry` 已把 `net_cfg` key 定为 `board, link_no`，忽略 `NO`。 | Business projection | 保留 key 规则和 int coercion；重复 key 应进入 diagnostics。 | 重复 key 是否需要阻断 projection，还是仅降级展示。 |
| Forward channel eligibility | `_forward_protocol_key_from_row` | `exe` 归一化后必须在 forward protocol registry 中；当前只有 `iec104`；`tab_num` 必须为正整数。 | vNext ordered families 覆盖 IEC104 表，但不从 `net_cfg` 生成 channel projection。 | Business projection | 保留 eligibility；`tab_num <= 0` 不显示 channel，并记录 oracle case。 | 是否支持非 IEC104 forward protocol 由业务数据确认后另开规则。 |
| Forward channel labels | `_build_forward_channel_descriptors` | label 优先 current `channel_desc`，其次 before `channel_desc`，否则 stable key。 | 无正式 projection label。 | Business projection | 保留为 `display_label` 派生规则。 | 是否需要同时暴露 board/link/protocol 字段给前端筛选。 |
| IEC104 forward tabs | `_FORWARD_TAB_LABELS` | `iec104_syx_list` 单点遥信，`iec104_dyx_list` 双点遥信，`iec104_yc_list` 遥测，`iec104_syk_list` 单点遥控，`iec104_dyk_list` 双点遥控，`iec104_yt_list` 遥调，`iec104_ym_list` 遥脉，`iec104_sc_list` 顺控，`iec104_yp_list` 遥步。表名为 `{stable_key}_{family}`。 | `IEC104_ORDERED_FAMILIES` 已一致；ordered rule 使用 `gid` 稳定 key、`no` 位置列。 | Table rules + business projection + ordered diff | 保留 family 与中文 label；把 label 放在 projection metadata，不放进 comparison core。 | 旧表中大小写不一致时是否需要 canonical display name。 |
| Communication protocol metadata | `_build_communication_protocol_sidebar_items` | `net_cfg` 自身作为 metadata tab；每个 channel 通过 `exe` 找 protocol cfg/dev_cfg 表。 | Protocol cfg pattern 已在 table rules 中；业务 projection 未做。 | Business projection | 保留 channel-level protocol projection；`net_cfg` 可作为 communication protocol metadata item。 | `com_cfg`、`prot_right` 在 protocol 视图中是否需要固定 metadata item。 |
| Protocol cfg candidates | `_communication_protocol_tab_candidates` | 按 current row 优先、before row 补充；segment 来自 `exe`；候选表为 `{stable_key}_{segment}_cfg` 与 `{stable_key}_{segment}_dev_cfg`；重复 segment 去重。 | vNext protocol patterns 支持 `iec104`、`iec61850c`、`nr103d`、`dev103`、`dev104`、`nbridge`。 | Business projection + table rules | 保留 candidate 生成规则；formal projection 只输出找到的 tabs 和 diagnostics。 | 当前 vNext pattern 同时支持 `dev103` 与 `nr103d`，alias 选择需统一。 |
| Protocol alias | `_PROTOCOL_TABLE_SEGMENT_ALIASES` | `dev103` 的实际表段映射为 `nr103d`。 | vNext registry 同时列出 `dev103` 与 `nr103d`。 | Table rules + business projection | 保留 `dev103 -> nr103d` 为 projection resolution alias；table rule 是否继续匹配两者由后续 contract slice 定。 | 是否存在真实 `b*_n*_dev103_cfg` 表；若没有可收敛 registry。 |
| Protocol resolution warnings | `_communication_protocol_resolution_warning` | 无 `exe` -> `MISSING_PROTOCOL_EXE`；候选表在 snapshot 中但 preview 不可见 -> `CANDIDATE_TABLE_NOT_PREVIEWABLE`；完全找不到 -> `CANDIDATE_TABLE_NOT_FOUND`。 | 正式 diagnostics 可承载 warnings，但 schema 未固定。 | Business projection diagnostics | 保留 warning 语义，改成正式 diagnostics code。 | `NOT_PREVIEWABLE` 在正式 bundle 中应指 surface policy 过滤，而不是 legacy preview。 |
| Global parameters | `_GLOBAL_PARAMETER_FIXED_TABLES` and `_build_global_parameter_sidebar_items` | 固定 `project` -> 工程参数，`prot_list` -> 规约配置；`app_cfg` 可作为 global item，并可通过 `table_cfg` 派生额外 global parameter item。 | vNext browse-only 包含 `project`、`prot_list`；`app_cfg` 有 explicit key。 | Business projection | 保留固定项；`app_cfg.table_cfg` 派生作为后续细化，不阻塞首版。 | 需要确认 `app_cfg` 派生表是否对正式 Workbench 仍高价值。 |
| Secondary device identity | `SECONDARY_DEVICE_IDENTITY_INDEX_SPECS` | `device` 用 `dev_addr`；`device_st/mx/co/sg/sp/cnt/sn/tap/other/disturb` 用 `dev_addr`；`device_cfg` 用 `gid`。 | vNext device point tables update-only by `gid`，`device_cfg` raw primary key；projection 未做。 | Business projection + table rules review | 保留 projection identity；comparison key 与 projection identity 可不同，但必须明确。 | device point tables 当前 compare key 用 `gid`，旧 projection 用 `dev_addr`，需在 Slice 2/3 明确 bridge。 |
| Secondary device label | `_secondary_device_item_label` | label 优先 current `description`，其次 before `description`，否则 `dev_addr`。 | 无正式 projection label。 | Business projection | 保留。 | 是否还有其它名称列如 `name` 需要 fallback。 |
| Secondary tab filtering | `build_secondary_device_sidebar_items` | 每个 device item 根据 `dev_addr` 或 `gid` 过滤 tab rows；没有 before/current row 的 tab 不显示；metadata-only rows 视为 unchanged。 | surface 支持 table records，但没有 device tab projection。 | Business projection | 保留为 projection tab rule；metadata-only 判定需重新定义，避免依赖旧 preview artifact。 | `metadata-only rows` 的正式判据需要从旧 tests 或真实数据补 oracle。 |
| Secondary projection duplicate diagnostics | `secondary_device_projection._device_duplicate_diagnostics` | duplicate `dev_addr` 跳过 device；duplicate `gid` 跳过 gid tab；输出 skipped devices/tabs diagnostics。 | 无正式 projection diagnostics。 | Business projection diagnostics | 保留诊断和跳过语义，但 code 改为正式大写枚举。 | duplicate 是否只影响 projection，还是也应影响 risk severity。 |
| Secondary risk aggregation | `secondary_device_projection._risk_summary` | 旧实现曾把 device table annotations 与 tab annotations 合并取最高风险。 | vNext formal projection 固定为风险拆分：普通 device item 只聚合自身业务 tabs；`device` 主表只属于 `metadata:device`。 | Risk annotations + business projection | 保留权重和 summary shape，但不把 metadata table 风险混入普通 device item。 | `UNKNOWN` 排在 `MEDIUM_LOW` 与 `MEDIUM_HIGH` 中间是否符合业务预期。 |
| Annotation matching | `secondary_device_projection._matching_annotations` | 支持 row、row_pair、positions、table-level annotation 匹配到 device/tab；未分配 table-level annotation 计数进入 diagnostics。 | vNext annotation artifact 有待收敛。 | Risk annotations | 保留匹配能力，简化成正式 row identity/position/table scope。 | ordered row 的 position 与 stable key 同时存在时优先级需确认。 |
| Table labels | `table_labels.table_display_label` | 优先 metadata display name，其次 SQL table comment，其次默认 label，最后 fallback。默认 `device`、`net_cfg`。 | vNext surface table display name 存在但策略可再明确。 | Surface assembly | 保留优先级；不要依赖旧 table object。 | SQL comment 提取是否应在 snapshot materialization 阶段统一落库。 |
| Ordered table families | old navigation + vNext registry | IEC104 ordered table 形如 `b\d+_n\d+_{family}`；稳定 key `gid`，position `no`，忽略列 `no`，artifact scope ordered semantic。 | 已在 `TableRuleRegistry` 和 ordered provider 中实现第一版。 | Ordered diff compute | 保留；后续处理 large 表 degraded 慢点和 records/risk 一致性。 | 大表 `DEGRADED records=0` 的耗时应在 ordered diff slice 单独处理。 |
| Ordered risk | `risk_evaluation/rules/ordered.py` | replacement、name-only update、content update、move/blank/unsupported/degraded 产生 ordered annotations。 | 当前已有第一版，但与旧 Workbench 展示未完全合流。 | Ordered diff + risk annotations | 保留正式 ruleset，后续用 oracle cases 验证中文业务展示。 | pseudo blank 的前端展示和风险级别需结合真实样本确认。 |
| Unparsed tables | `navigation._raw_table_sidebar_item` | 未被业务规则消费的 preview table 仍显示为 raw table，保留 display name、base table、change kind。 | formal surface 可展示普通 table summary。 | Surface assembly + frontend Workbench | 保留 unparsed fallback，但使用正式 table summary，不引入 old raw item shape。 | 是否需要对 skipped/browse-only 表展示 unparsed 入口。 |

## Manual Oracle Cases

| Case | Input shape | Expected old semantic | vNext migration target |
| --- | --- | --- | --- |
| IEC104 channel with rows | `net_cfg(board=1, link_no=7, exe=iec104, tab_num=9, channel_desc=通道A)` and `b1_n7_iec104_syx_list` exists. | sidebar group `forward_tables` has item `forward_channel:b1_n7`, label `通道A`, tab `单点遥信` pointing to `b1_n7_iec104_syx_list`。 | Business projection emits forward channel with board=1/link=7/protocol=iec104 and IEC104 family tabs. |
| Disabled forward channel | same `net_cfg` but `tab_num <= 0`。 | no forward channel item. | Projection omits channel and may emit diagnostic if useful; no comparison behavior change. |
| Protocol current/before switch | before `exe=dev103`, current `exe=iec104` for same `b1_n7`。 | candidate tabs prefer current `b1_n7_iec104_cfg/dev_cfg` and also include before alias `b1_n7_nr103d_cfg/dev_cfg` if current segment differs. | Protocol projection resolves both candidate groups with explicit `source_side` diagnostics. |
| Missing protocol exe | `net_cfg` row has board/link but no parseable `exe`。 | warning `MISSING_PROTOCOL_EXE` with board/link and empty candidates. | Formal diagnostics code `MISSING_PROTOCOL_EXE`; no tab projection. |
| Candidate non-previewable | protocol candidate table exists in snapshot but is absent from preview/surface. | warning `CANDIDATE_TABLE_NOT_PREVIEWABLE`。 | Formal diagnostics should say candidate filtered/excluded by surface policy, without legacy preview wording. |
| Secondary device with tabs | `device(dev_addr=10, gid=100, description=保护A)` plus rows in `device_st(dev_addr=10)` and `device_cfg(gid=100)`。 | secondary device item `dev_addr:10`, label `保护A`, tabs 状态类 and 装置配置 with corresponding row filters. | Secondary device projection emits device key, identity values, display label and tab refs/filters. |
| Duplicate `dev_addr` | two `device` rows share `dev_addr=10`。 | projection skips that device and reports duplicate diagnostic. | Formal projection emits duplicate diagnostic and avoids attaching ambiguous risk/tab rows. |
| Duplicate `gid` | multiple device rows map to same `gid` or tab identity collision. | `gid` tabs can be skipped with `duplicate_gid` diagnostic. | Formal projection keeps device if `dev_addr` is unique, but marks affected gid tabs skipped. |
| Ordered replacement | IEC104 table has delete+insert at same `no` with same/changed `gid` context. | ordered risk can classify replacement instead of unrelated delete/insert. | Ordered diff records and risk annotations expose `ORDERED_REPLACEMENT` style semantic. |
| Ordered degraded table | Large IEC104 table cannot produce stable ordered replay. | old/new path should explain degraded/unsupported reason and avoid misleading row records. | Ordered diff slice must emit explicit `degrade_reason`, bounded work, and visible diagnostics. |
| Unparsed business table | table does not match any business group. | shown under `unparsed_tables` with raw table label. | Formal surface table list keeps it accessible as unparsed/ordinary table. |

## Initial Migration Conclusions

- 转发通道、通讯规约和二次装置应成为 vNext business projection capability，而不是前端或 bundle loader 内的 table-name heuristics。
- `ComparisonSurface` 应承载 projection refs / summaries / diagnostics；row diff artifact 继续只表达 diff records，不承担业务导航推断。
- Risk annotation 需要同时支持 table scope、row scope、row-pair scope 和 projection aggregation；projection aggregation 不能反向修改 core risk facts。
- `dev103 -> nr103d` 是业务解析 alias，应在 projection/table rule 层明确，避免前端猜测。
- `device` projection identity 与 comparison key rule 不是同一概念；后续 Slice 2/3 必须把 “compare key” 和 “business identity” 分开命名。
- Upload preview sidecar 的当前存在只代表前端预览尚未完成 formal data-surface cleanup，不应影响 history compare formal bundle。
- Risk annotation baseline 已收敛为正式 vNext contract：risk facts 直接消费 comparison
  `row_change_stats` 与正式 records artifact；UPDATE_ONLY suppressed insert/delete、空 hidden table
  和 `BUSINESS_EQUIVALENT` 不生成 risk annotation。
- 旧 risk engine 仅作为语义 oracle：standard insert/delete/update、device point name/content update、
  ordered move/interval/replacement、degraded unknown 等 reason/severity 被迁入 vNext ruleset；
  不复用旧 preview bundle sidecar 或旧 Workbench risk payload。
- Business projection 已接入正式 surface/bundle：projection payload 按 pair 写入 bundle，
  surface 只保留 refs/summaries。后续前端 Workbench 应读取正式 projection artifact，
  不再在组件内复刻旧 table-name/sidebar heuristics。

## Large -> Large-1 Oracle Difference Findings

实际业务数据 `business_large/large -> business_large/large-1` 已通过
`gateway-data-management-system/backend/tools/comparison_oracle_compare.py` 曾用于对比历史
`FormalTableCompareEngine` oracle 与 vNext comparison core；临时运行产物已清理，本文只保留结论摘要。

### Coverage

- table union 为 292，common table 为 137。
- 155 张表只出现在 vNext 结果中，未出现在历史 oracle 结果中；这些表属于空 unchanged surface visibility 分类。
- 这些表在 vNext 中均为 `UNCHANGED` 且没有 row records。差异更像 coverage/surface policy，而不是 core diff correctness bug。
- 后续 formal surface 需要明确空表、unchanged 表、unparsed 表是否展示；不应为了贴合旧 preview 直接缩小 vNext core 覆盖。
- 已落地策略：空 unchanged 表不从 comparison core 删除，而是在 formal surface visibility 阶段内部过滤；
  默认 `surface.tables` 仅保留可见表，`hidden_tables` 与 hidden count 不再作为正式前端统计展示。

### Ordered SYX

- 12 张 `b1_n*_iec104_syx_list` 是共同表差异的主体：
  `b1_n3`、`b1_n4`、`b1_n7`、`b1_n8`、`b1_n11`、`b1_n12`、
  `b1_n13`、`b1_n14`、`b1_n15`、`b1_n16`、`b1_n17`、`b1_n18`。
- 旧实现对每张表输出相同语义 records：
  `BLANK_INSERT_INTERVAL=1`、`DATA_INSERT=5`、`MOVE=3`，并且旧 planner replay exact。
- vNext 对每张表输出 `DEGRADED`，reason 为 `ORDERED_AMBIGUOUS_MOVE_PLAN`。
- 当前差异假设：旧实现有 backbone planner 路径，可以在 topology core size 12、position changed 7 的场景选择 3 个 move keys；vNext 当前 single-move 判据过窄，把可解释的 syx 大表误判为 degraded。
- 后续 ordered slice 应迁入干净的 backbone planner capability 或等价 planner，而不是把这个 case 用特殊表名补丁绕过。
- 已落地方向：vNext ordered planner 在 unique single-move 失败后启用预算内 backbone candidate planner；候选唯一且 replay exact 时输出正式 ordered records，无法唯一选择或 replay 失败时仍 degraded。

### Device CFG

- `device_cfg` 是唯一非 ordered 的共同表差异：旧实现 `UNCHANGED`，vNext `MODIFIED`，records 为
  `DELETE=258`、`INSERT=258`。
- raw primary key `no` 在 before/current 各自唯一，但两侧完全不匹配，因此按 raw PK 会产生全量 delete/insert。
- `gid` 在 before/current 的 distinct set 一致，但只有 6 个 distinct value 且两侧都有重复，单独使用 `gid` 不能形成唯一 compare key。
- 当前候选原因：
  - `RAW_PRIMARY_KEY_UNSTABLE_BUT_GID_MATCHES`：`no` 更像导入/展示序号，不适合作业务 identity。
  - `UPDATE_ONLY_UNMATCHED_ROWS_EMITTED`：vNext 当前 update-only 表对 unmatched rows 仍输出 delete/insert，旧实现可能压制或视为业务等价。
  - `GID_DUPLICATES_REQUIRE_BUSINESS_IDENTITY_POLICY`：`device_cfg` 需要显式业务 identity 规则，可能是 `gid` 加辅助列，或 projection-level equivalent digest。
- 后续 device slice 应先定义正式 compare identity/update-only 语义，再修改 table rule；不要直接把旧输出 `UNCHANGED` 硬编码为目标。
- 已落地处理：`device_cfg` 通过通用 `UPDATE_ONLY` artifact scope 处理，不再做表名特例。
  vNext 在 raw primary key churn 只产生 insert/delete 时抑制这些 row records，并用
  `BUSINESS_EQUIVALENT` 表达 raw 有变化但业务 diff 为空；旧 oracle 的 `UNCHANGED`
  与 vNext 的 `BUSINESS_EQUIVALENT` 在报告中归类为 `UPDATE_ONLY_SCOPE_EQUIVALENT`。

## Characterization Tests

本 slice 暂不新增 characterization tests。原因是当前目标是固定迁移语义和后续拆分边界；旧 Workbench 模块依赖 preview bundle shape，贸然把旧 payload 放进测试容易把旧 DTO 固化为新 contract。

后续如果需要测试 oracle，建议新增小型 fixture，只断言纯业务规则：

- `net_cfg -> b{board}_n{link}` channel parse。
- IEC104 family label mapping。
- `dev103 -> nr103d` candidate table generation。
- secondary device `dev_addr` / `gid` projection identity。
- duplicate `dev_addr` / `gid` diagnostics。

这些测试应落在 vNext projection capability 的新实现上，而不是依赖旧 Workbench runtime。
