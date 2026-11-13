# 比较正确性与旧实现参考：讨论摘要

2026-11-13，供新会话讨论。详细源码、样本及证据见 [比较正确性参考清单](comparison-correctness-reference-inventory.md)，现场及 Preview 复用需求见 [人工联调问题记录](manual-integration-preview-review-findings.md)。以下为静态对照与一次联调观察；除已直接核实的代码结构和现场结果外，均不是新代码已通过测试的结论。

新代码：`/home/dev/gdds-gw08-dual-env`，分支 `gw08-dual-env`，调查时 HEAD `b985a6496587e36014a7eea5349b3d807c562844`。旧参考：`/home/dev/fasttest-mysql/gateway-data-management-system/backend`，HEAD `bb7ebbf7b1874c14c04bf257875df82ed05f65b9`；包含未提交修改，归档对齐文件 `backend_vnext/api/formal_alignment.py` 未跟踪，讨论时需保留并读取工作区实物。

## 一、新架构已有方案：优先验证，不直接移植旧实现

| 事项 | 已核实的现状 | 尚须验证的边界 |
| --- | --- | --- |
| 归档状态衔接 | 新架构用 canonical 内容身份和规则版本构造状态图，独立处理生成时间，不走旧实现把上传 snapshot digest 与 Dolt commit ID 直接比较的路径。见 [Preview 身份](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/application/preview_jobs.py:1246)、[归档校验](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/application/archive/business_validation.py:65)。 | 这解决了旧问题的标识类型错配，**尚未证明**所有 FULL 场景正确。规范内容相同与旧方案“按业务规则等价”是否应视为同一状态、证据不足和时间异常如何处理，需要按现行 Contract 讨论。旧参考见 [归档验证](/home/dev/fasttest-mysql/docs/backend-vnext/notes/archive-content-alignment-verification.md)。 |
| 差异摘要 | 新 Rust 普通和有序比较已产生表级增删改数，经 native adapter 传给 surface，旧 mapper 字段名错配的补丁不能直接套用。见 [ordered](/home/dev/gdds-gw08-dual-env/vnext/rust/gateway-compute-core/src/comparison/ordered.rs:1351)、[surface](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py:410)。 | 用旧 number1 样本或等价 oracle 核 Preview、History 和前端；核 `UPDATE_ONLY` 业务计数、raw 增删以及移动、位置、空白区间。当前不能仅凭字段存在说计数已正确。 |
| 前缀协议配置表键 | 新代码已对匹配的 `bN_nN_..._cfg` 通道选项表指定 `(page_no, no)`，见 [协议规则](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:321)。 | 逐项核 selector 实际覆盖与重复键行为；不要推广到所有 `*_cfg`。未加前缀的 12 类是另一项业务角色问题，见下。 |
| 无键表的单侧分支 | 新比较层已有整表新增/删除分支，设计方向与旧实现一致，见 [standard.py](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:31)。 | History 现场仍可能错误降级，因此不能把已有分支等同于端到端正确；两侧空表的结构变化及未知非空、重复键路径也要验证。 |

## 二、需要讨论并参考旧实现修改的事项

1. **空基线整表错误降级：优先作为疑似实现缺陷处理。** 现场一次 History 结果 312 张表中 264 张降级，诊断为 `TABLE_READER_UNAVAILABLE`；Preview 对应表为新增。当前读取需求规划对缺一侧的任务不请求 reader，但单侧比较要求现存侧 reader，导出缓存命中时由此可能出现错误降级。代码与现场支持该判断，尚需隔离测试验证。讨论应确定如何统一读取前置条件、保证冷/热缓存与普通/有序表一致，避免不必要的整表逐行读取。具体调用链见 [详细清单第 1 节](comparison-correctness-reference-inventory.md)。

2. **仅结构变化的展示与审计：讨论采用旧业务规则及其 Contract。** 旧参考对严格证明共有业务值不变的纯增删列保留原始 `SCHEMA_ONLY_CHANGED`，对外不显示变化及 schema 风险，同时保存可追溯审计。新 surface 与风险处理目前仍呈现结构变化，未发现等价审计。讨论适用范围、审计生命周期、规则版本和对现有 Contract/digest/golden 的影响；不能仅在前端隐藏。尤其 `UPDATE_ONLY` 即使过滤原始增删，也不能把它们当成无变化；失败、降级、缺 key、证据不足及整表增删都不得误隐藏。旧参考见 [规则说明](/home/dev/fasttest-mysql/docs/backend-vnext/notes/schema-only-change-visibility.md) 和 [判定代码](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/comparison/schema_visibility.py)。

3. **审核直接使用 Preview 结果：Owner 已提出后续方向。** 当前每次进入审核会新建 History 比较；需求是改为使用与提交绑定的 Preview 结果。讨论不可变结果绑定、审核者跨工作区授权、保留/清理及失效处理。FULL 上传的 Preview 包含“基线→原始”和“原始→修改”，并不天然等同当前审核的“基线→提交”；须先确定审核应展示哪些比较对。此项不能代替修复 History 本身。

4. **未加前缀的 12 类配置表：先决定业务角色，再决定 key。** 旧实现对其显式指定 `(page_no, no)`；新架构把这些未加前缀表列为 `BROWSE_ONLY`。若仍仅浏览，简单移植比较键无意义；若需要参与业务差异，则涉及角色、投影、规则身份和风险语义。逐表对照真实数据及 owning Contract，保留白名单和重复键降级，不泛化到所有配置表。参考 [旧 registry](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/table_rules/registry.py:72)、[新 registry](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:45)。

## 三、证据不足：先验证再决定是否修改

- **复合信号虚装置**：旧实现只比较两侧共有 payload 字段，并独立识别公式变化、测点增删；新代码忽略复合表 `point_payload_json`，公式单独比较，架构不同。需确认源测点表的真实字段更新、测点增删和公式变化仍通过导航及展示完整可见，同时单侧增删字段不误报。不能仅因忽略 payload 就断言已解决。参考 [旧实现](/home/dev/fasttest-mysql/gateway-data-management-system/backend/backend_vnext/capabilities/composite_signal/artifacts.py:271)、[新规则](/home/dev/gdds-gw08-dual-env/vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:97)。
- **无键且两侧为空的表**：需验证 descriptor 的结构变化是否在 metadata、native 和缓存路径一致；未知有数据表发生变化且无有效 key 时仍应降级，重复键也不得被掩盖。旧 [number1 核查](/home/dev/fasttest-mysql/docs/backend-vnext/notes/number1-comparison-correctness.md) 可作为语义参考。
- **归档业务等价**：新 canonical 身份避免旧标识错配，但忽略列或 browse-only 数据差异是否允许归档衔接，是独立业务决策；不要直接把旧实现的 `SUMMARY_FACT_MISSING` 名称或判等策略移入新架构。

建议新会话先逐项确认上述业务语义和优先级，再制定实现与测试范围。旧报告中的通过结果只证明旧代码与旧样本，不能作为新代码证据；新测试按本仓库规则在专用节点的 clean 已提交 worktree 执行。本摘要未引入产品代码修改。
