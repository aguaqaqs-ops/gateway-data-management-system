# 比较正确性与规则变化：旧实现对照记录

记录时间：2026-11-13。目的：为后续独立分析、设计和实施提供线索，**不是已完成移植或测试通过的结论**。当前人工联调分支 `/home/dev/gdds-gw08-dual-env`：`gw08-dual-env`，HEAD `b985a6496587e36014a7eea5349b3d807c562844`；下称“新代码”。另一代码库 `/home/dev/fasttest-mysql/gateway-data-management-system/backend`，其 Git HEAD `bb7ebbf7b1874c14c04bf257875df82ed05f65b9`，分支 `formal-contract-migration`，存在未提交修改；下称“旧参考”。尤其归档对齐文件是未跟踪的工作区内容，**必须读取工作区实物，不能只看 HEAD**。两库架构、规则、Contract 和缓存身份不同，不能直接复制实现或把旧测试结果作为新代码证据。

本记录基于代码和文档静态扫描，不在开发主机运行测试；仅为粗判，具体行为、证据和影响须后续在专用测试节点核实。已有人工联调现场及审核直接复用 Preview 的 Owner 新要求见 [人工联调问题记录](manual-integration-preview-review-findings.md)。该文件与本文件目前均为未提交新文件。

## 总览

| 项目 | 对新代码的初步判断 | 后续重点 |
| --- | --- | --- |
| 空基线整表降级 | 现场已发现实现路径不一致；强疑似缺陷，尚未隔离验证 | 修 History 单侧 reader 需求与单侧比较的矛盾，覆盖缓存冷热 |
| 复合信号字段增删误报 | 架构不同，尚不能证明同样误报或已经完整解决 | 按共有字段、公式、真实更新与增删验证端到端行为 |
| 12 类配置表 key | **部分不适用、部分待规则决策**：前缀通道类已有 key；未加前缀的 12 类目前属于 BROWSE_ONLY，不能机械改键 | 对照 owning Contract 先确认是否应成为比较表，核精确范围与优先级 |
| 无键表单侧/空表 | 单侧的底层路径已有新增/删除分支，但现场 History 有 reader 缺陷；两侧空表和无键/重复键需 focused 核查 | 构造空表 schema、未知非空与重复键矩阵 |
| 纯结构变化仅审计 | 未发现同等可见性判定及审计实现；当前明确将 schema-only 映射为 schema 变化及风险 | 需按 Owner 新要求设计和实现，尤其原始增删不可被 UPDATE_ONLY 掩盖 |
| 普通/有序摘要计数 | 新架构的 Rust facts、adapter 和 surface 已有计数字段，不宜直接移植旧 mapper | 用真实样本对 Preview/History 验证各计数和业务过滤 |
| FULL 归档状态衔接 | 新代码使用规范内容身份而非旧式 snapshot digest 与 Dolt commit 直接相等；原 bug 不可直接认定仍存在 | 核 canonical identity 是否符合所需业务等价，证据缺失和时间阻断语义 |
| 审核复用 Preview | 新需求，当前通过 History compare | 审核授权、生命周期与 FULL 多比较对语义需设计；不能代替修复 History |

## 1. 空基线整表错误降级

现场：CT110 单设备 A，t4 v1 MODIFIED_ONLY 提交 `sub-a003ffc4-07a5-4921-bcad-1653ba1bd7f7` 的 History 比较，空基线→提交，某次 312 张表中 264 张 `DEGRADED`，诊断 `TABLE_READER_UNAVAILABLE`（其中 144 张还带 `ORDERED_DIFF_UNSUPPORTED`），例如 `b1_n11_iec104_syx_list`。另一次 162 张；现场条件不同，不应推广为固定比例。Preview 相应表表现为整表新增。表产物和运行时信息见 [原始记录](manual-integration-preview-review-findings.md)。

代码路径：新 [History 行需求与导出缓存](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/application/history/compare_jobs.py:1062) 在导出缓存命中时不为导出补 reader；[_task_arrow_inputs](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/comparison/production.py:100) 对缺一侧任务返回空；而 [ordered 单侧判断](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py:48) 和 [standard 单侧判断](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:119) 对现存侧 reader 缺失返回降级。现场运行中 `production.py` 与 `compare_jobs.py` 两个源码文件 SHA256 与该工作区一致。证据支持两处前置条件不一致造成错误降级，但未做隔离因果验证。

后续应先通过真实 History（而不只直接调用比较函数）覆盖冷/热导出缓存、有序/普通、空基线新增和删除；明确 descriptor、已校验整表 artifact 与 reader 的证明边界及内存成本，避免为整表增删引入不必要逐行扫描。核对失败和降级不能被掩盖。旧参考的单侧优先处理见 [旧比较引擎](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/comparison/engine.py) 和 [旧单测](/home/dev/fasttest-mysql/gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_skeleton.py)。

## 2. 复合信号虚装置字段增删误报

旧 [artifacts.py](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/composite_signal/artifacts.py:271) 的 `_changed_point_columns` 比较两侧 payload 共有字段，公式 digest、测点存在性单独判定；单侧字段仍在源表 schema facts 中。原始样本与测试见 [number1 核查](/home/dev/fasttest-mysql/docs/backend-vnext/notes/number1-comparison-correctness.md) 和 [样本 contract 测试](/home/dev/fasttest-mysql/gateway-data-management-system/backend/tests/backend_vnext/contract/test_number1_comparison_correctness.py)。

新实现不再沿用旧 artifacts 层： [table rules](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:97) 将 `point_payload_json` 纳入 ignored columns；[绑定](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/composite_signal/_bind.py:135) 仍生成 payload，公式 digest 单独存在；前端 [公式视图](/home/dev/gdds-gw08-dual-env/frontend/src/features/view-model/model.ts:723) 单独比较公式。忽略 payload 可能避免旧式新增字段误报，但**不能由此证明共有字段的真实更新、测点增删和虚装置导航均正确可见**；还需核对其从原始测点表比较事实汇合到业务导航和行展示的整个链路。建议按旧测试语义覆盖单侧增/删字段、共有字段变化、公式变化、测点增删，检查源表 schema facts 与虚装置显示，分别验证 Preview/History 和 Rust 路径。

## 3. 显式配置比较键

旧 [registry](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/table_rules/registry.py:72) 的 12 类为 `cnt_manage_cfg`、`iec101_cfg`、`iec104_cfg`、`iec104gw_cfg`、`iec61850c_cfg`、`jdxx_cfg`、`sc_cfg`、`scada_cfg`、`sg_manage_cfg`、`vqc_cfg`、`wave_cfg`、`wf_cfg`，明确 `(page_no, no)`；不是所有 `*_cfg`。前缀协议选择器另行定义。参考 [旧 key 回归](/home/dev/fasttest-mysql/gateway-data-management-system/backend/tests/backend_vnext/unit/test_option_cfg_comparison.py)。

新 [registry 列表](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:45) 将这 12 个未加前缀名字纳入 BROWSE_ONLY；[协议表规则](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:321) 已对匹配的 `bN_nN_..._cfg` 设 `(page_no, no)`；[规则测试](/home/dev/gdds-gw08-dual-env/vnext/backend/tests/test_table_rules_contracts.py:141) 明确验证未加前缀的 browse-only 类别。此处不只是缺 key，而涉及是否改变表的业务比较角色、存储投影、规则集与摘要。先逐表核真实数据、现行 owning Contract 与 selector precedence，再决定是否改变；不要推广到任意配置表或破坏当前 browse-only 语义。重复键必须继续降级。

## 4. 无比较键：新增/删除和两侧空表

旧 [engine.py](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/comparison/engine.py) 和 [comparison skeleton 测试](/home/dev/fasttest-mysql/gateway-data-management-system/backend/tests/backend_vnext/unit/test_comparison_skeleton.py) 可参考单侧优先、空表用 descriptor 判 schema、未知非空数据变化与重复键降级。

新 [standard.py](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:31) 先判断单侧并具备整表新增/删除，但上述 History reader 规划可能让实际调用返回降级；不能仅凭分支存在宣布已解决。两侧空表的无键 schema 判定是否在 metadata/native/cache 命中路径一致，静态扫描尚不足以判断。对未知非空表检查 [production.py](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/comparison/production.py:927) 的 keyless 策略与 Rust 路径，核实 schema 相同/不同、原始内容相同/不同、有效键重复及 UPDATE_ONLY；不得为了消除降级而猜测 key。

## 5. 仅结构变化：对外隐藏并保留审计

旧 [schema_visibility.py](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/comparison/schema_visibility.py)、[risk engine](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/risk_evaluation/engine.py)、[surface assembler](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/surface_assembly/assembler.py) 和 [schema_change_audit.py](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/flows/schema_change_audit.py) 是具体参考；详见 [规则与审计](/home/dev/fasttest-mysql/docs/backend-vnext/notes/schema-only-change-visibility.md) 及 [单测](/home/dev/fasttest-mysql/gateway-data-management-system/backend/tests/backend_vnext/unit/test_schema_change_visibility.py)。

新 [surface](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py:462) 目前把 `SCHEMA_ONLY_CHANGED` 映射为 `SCHEMA_CHANGED`；[risk engine](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_engine.py:557) 也处理该事实。静态搜索未找到旧策略等价的审计产物。初判需要明确设计及修改，不只是 UI 隐藏：保留 raw facts、正确调整 surface/风险/导航统计并持久化可追溯审计，处理缓存命中及规则身份变更。仅两侧存在、行数相等、有效 key 未变、无失败降级，且有充分共有字段相等证据时适用；非空表须有效 key 和可比较字段。raw 增删即使被 UPDATE_ONLY 过滤也不可隐藏，不能用缺 records 或过滤后零计数作充分证据。Contract、digest、golden 和审计生命周期需同步设计。

## 6. 普通与有序差异摘要

旧 [surface assembler](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/surface_assembly/assembler.py:380) 将 ordered summary 提供为表级统计，旧 preview mapper 的修复和数据口径见 [计数说明](/home/dev/fasttest-mysql/docs/backend-vnext/notes/diff-summary-counts-and-history-compare-testing.md)。number1 `b1_n2` 至 `b1_n7_iec104_syx_list` 参考期望各 `+2 / 修改55 / -2`；移动、位置、空白区间不计为内容更新。

新 Rust [ordered.rs](/home/dev/gdds-gw08-dual-env/vnext/rust/gateway-compute-core/src/comparison/ordered.rs:1351) 和 [standard.rs](/home/dev/gdds-gw08-dual-env/vnext/rust/gateway-compute-core/src/comparison/standard.rs:285) 已填充表级 row counts；[native adapter](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/comparison/native.py:238) 与 [surface assembler](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py:410) 已传递这些字段。初判旧字段名称不一致的直接缺陷不宜照搬；但这不是端到端通过证明。后续用同数据核 Preview 和 History bundle、前端读数及 UPDATE_ONLY（业务计数优先、raw 增删受抑制时仍可审计）、移动/位置/空白不混入内容更新，并检查单侧整表计数约定。

## 7. FULL 归档状态衔接（旧参考未提交）

旧参考 [formal_alignment.py](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/api/formal_alignment.py) 是未跟踪文件，其他相关 [formal_state_store.py](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/api/formal_state_store.py) 与测试是未提交修改；详见 [旧验证记录](/home/dev/fasttest-mysql/docs/backend-vnext/notes/archive-content-alignment-verification.md)。旧错误把上传 snapshot digest 与 Dolt commit ID 直接比较；修复先按 SQL/XML 及规则建立内容身份，必要时业务比较，证据不足或降级报 `SUMMARY_FACT_MISSING`，时间检查独立。

新 [preview_jobs.py](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/application/preview_jobs.py:1246) 使用 canonical state digest、projection rules digest/版本和 scalar encoding 形成内容身份；[business_validation.py](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/application/archive/business_validation.py:65) 以两侧 `content_identity` 图判连通，生成时间单独判断。故旧的不同类型字符串直接比较并非当前同一路径，不应直接移植。尚需核：相同 SQL/XML 的 FULL 往返身份、忽略列或 BROWSE_ONLY 导致的业务等价是否应被视为相同、规则版本不同/缺少证据或失败时的具体语义、节点 proof 与同批次前驱、时间缺失/倒挂。当前 canonical 精确身份与旧“必要时比较业务等价”并不必然等价；先对照现行 Contract 和 Owner 要求，不把旧 `SUMMARY_FACT_MISSING` 名称机械映射到新诊断。

## 后续工作建议

先固定两个仓库实际源码（含旧工作区未提交文件）、样本、规则集、版本及 Contract；建立需求与新代码/旧参考/测试矩阵。优先复现空基线单侧降级，再验证虚装置和摘要；规则角色、schema-only 隐藏/审计、归档业务等价与 Preview 结果授权分别形成设计决策。数据集 number1 的旧报告计数仅是参考 oracle，需核对样本与规则身份。所有 focused 与真实数据测试依本仓库 AGENTS 在专用节点、clean 已提交 worktree 上执行；本次未运行测试或更改产品代码。

面向后续讨论的分类与决策问题见 [比较正确性讨论摘要](comparison-correctness-discussion-brief.md)。
