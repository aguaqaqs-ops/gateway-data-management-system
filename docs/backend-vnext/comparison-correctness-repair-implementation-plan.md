# 比较正确性与审核结果复用修复实施计划

日期：2026-11-13。状态：**业务口径、角色分工和本任务审核模型例外已由 Owner 确认，待实施会话启动；本次文档补充不启动产品修改、测试或部署。**

本轮修复解决空基线 History 错误降级、12 类配置表缺少行级差异、纯结构变化的展示与审计，以及审核重复计算的问题。审核改为读取提交绑定的不可变 Preview 结果；History 继续提供独立的任意节点比较能力。

调查基线为测试分支 `gw08-dual-env` 的 `b985a6496587e36014a7eea5349b3d807c562844`，工作区 `/home/dev/gdds-gw08-dual-env`。本文开始编写时 HEAD 为 `be9591c017154df4f88d132078264325d869205c`，两者之间仅增加 Preview 优化方案文档，`vnext/`、`frontend/` 和部署源码未变。实施时重新固定候选提交及增量，不把调查基线直接当成未来实施基线。

依据：[讨论简报](../frontend-vnext/comparison-correctness-discussion-brief.md)、[源码与旧实现参考清单](../frontend-vnext/comparison-correctness-reference-inventory.md)、[人工联调记录](../frontend-vnext/manual-integration-preview-review-findings.md)，以及本次 Owner 两轮确认。现场记录支持单侧 reader 前置条件不一致的判断，隔离因果验证列入工作包 A；旧实现的通过结果不作为新代码证据。前三份调查材料目前为未跟踪文件，正式实施前应将必要的依据纳入提交，保留调查时的事实与限定。

## 已确认的业务决议

| 事项 | 本轮目标行为 |
| --- | --- |
| 单侧表 | 依据已校验的表描述信息生成整表新增或删除事实；整表可浏览由产物闭包保证，不为比较判定额外逐行读取 |
| 纯结构变化 | 严格证明共有业务值未变的纯增删列，对外按未变化展示，不输出对应 schema 风险，后台保存原始事实及审计 |
| FULL 审核 | 使用 Preview 原有的“基线→原始”和“原始→修改”两组比较；默认打开后者，分别统计，不增加第三组比较 |
| MODIFIED_ONLY 审核 | 使用 Preview 已有的“基线→修改”比较，原始侧复用基线 |
| 配置表 | 精确列出的 12 类未加前缀配置表升级为行级增删改比较，比较键为 `(page_no, no)`，存储键与比较键分别处理 |
| 重复比较键 | 存储合法但比较键无效时，该表比较降级并保留浏览；存储主键约束本身非法仍按现有规则失败 |
| 结果绑定与保留 | 审核读取提交绑定的不可变结果；审核 bundle 的完整闭包和后台审计随提交记录保留 |
| 结果缺失或损坏 | 明确报错，不自动创建 History 比较替代，不伪装成无变化 |
| 提交资格 | 仍由规范状态判断；页面可见变化数为零不额外禁止提交，规范状态相同时仍返回 `NO_CANONICAL_CHANGE` |
| 归档衔接 | 保持 canonical 内容身份及现有来源、时间校验；页面业务等价不自动合并归档状态 |

没有已部署使用方和迁移要求。需要变更 Contract、DTO、checkpoint、schema 或 digest 时，直接采用目标形态，同步 golden 与测试，不保留旧读写路径、别名或数据回填。

## 范围与风险

必做范围为上述四项修复及其受影响的规则、产物保护、授权、导航、摘要和前端读取。复合信号、普通与有序计数、无键空表按下文验证；仅在暴露本轮范围内的正确性缺陷时修复。归档仅回归既有判等和时间边界，不移植旧归档业务等价算法。

本轮不包含 Preview 性能优化、并行池扩展、资源档调整、归档新判等策略或通用审计平台。与 [Preview 优化计划](preview-optimization-plan.md) 分开实施；两者修改同一比较、bundle 或发布路径时，先核对实际增量，再验证组合后的最终候选。

按[比例化保障政策](refactoring/formal/policies/proportional-assurance-and-risk-based-verification-policy.md)，最高风险为 A：读取提交结果涉及跨工作区授权，审核与提交依赖不可变来源绑定。保护移交属于 B 类持久流程；比较、缓存与派生产物主要为 C/D 类。关键保障集中在当前权限、exact scope、结果绑定、事务内保护移交、已有审批 CAS，以及缺损不能被误判为正常结果。复用现有 ArtifactStore、closure 和 protection，不建立新服务、通用引用计数或持久审计状态机。

## 角色分工与逐节开启规则

### 本任务审核模型例外

Owner 于 2026-11-13 明确允许本任务使用 Terra 协调、Sol high 实施、Sol xhigh/max 审核。此为本任务对 [AGENTS](../../AGENTS.md) 中“独审须使用与实施者不同的模型家族”及默认 Astra 审核安排的例外，只适用于本计划，不修改全仓规则或 Preview 优化任务的编组。Sol high 与 Sol xhigh/max 属于同一模型家族，审核记录必须如实标注；不同推理档不等于跨模型家族独审。无需再次为这一已确认例外请求许可，也不默认增加一轮 Astra 审核。

例外只调整审核模型，新上下文、只读固定候选、原审复审、必要门禁和最终全范围核收继续执行。为满足 Owner 逐小节换人的要求，A–D 每节都安排审核，不按 C/D 风险省略本任务已要求的逐节审核；风险等级仍由实际后果决定，不因角色配置统一抬高。

### 职责与模型

| 角色 | 模型与推理档 | 职责 |
| --- | --- | --- |
| 持续协调者 | `gpt-6.1-terra` / high | 全程维护范围、固定基线、文件与节点归属、实际风险、任务交接、阶段日志；触发必要门禁，核收每节及最终结果；不代签审核 |
| 每小节实施者 | `gpt-6.1-sol` / high，新上下文 | 细化本节接口与 Contract，实施产品及测试、执行 focused 与必要静态检查，形成固定提交，修复本节 finding，收尾本人资源 |
| 每小节审核者 | `gpt-6.1-sol` / 默认 xhigh，复杂判断可 max，新上下文 | 在只读 detached worktree 审查本节固定提交、相关 Contract 与关键证据，列出 finding、未测限制和结论；不改产品，不重复启动测试 |
| 集中验收实施者 | `gpt-6.1-sol` / high，新上下文 | 汇总 A–D 的最终候选，补齐跨包贯通和必要验证，核原始证据与资源收尾；产品缺陷优先交原作者修复 |
| 最终全范围审核者 | `gpt-6.1-sol` / 默认 xhigh，复杂判断可 max，新上下文 | 审核 A–D 全部变更、跨包不变量及集中验收结果，不以逐节通过替代最终核收 |

不设置专职测试 agent；实施者负责其运行，现有脚本执行确定性检查和门禁。模型不可用时报告具体角色阻塞，不静默替换模型、继承错误推理档或声称已切换当前会话模型。

### 每小节如何开启

这里的小节指可独立交付的 A、B、C、D 工作包和 E 集中验收。若实施时将 C、D 拆为 C1/C2、D1/D2 等独立交付包，每个拆包也分别新建实施者与审核者；不因文档中的每个说明性小标题再建角色。

| 小节 | 开启与交接 | 放行前必须具备 |
| --- | --- | --- |
| A 单侧降级 | Terra 固定起始提交，新建实施者 A；复现与修复形成候选后新建审核者 A | 实际 History 编排复现与针对性修复证据，原始失败保留，普通/有序与缓存边界已核收 |
| B 配置表 | A 核收后，以其固定提交为输入，新建实施者 B；候选就绪后新建审核者 B | 12 类白名单、存储与比较键分别处理、增删改和降级边界，以及 owning Contract 同步 |
| C 结构审计 | B 核收后，新建实施者 C；候选就绪后新建审核者 C | 隐藏证据、审计闭包、缓存恢复、风险/展示/导航/计数一致性；证据不足不隐藏 |
| D 审核复用 | C 核收后，新建实施者 D；候选就绪后新建审核者 D | 提交绑定、授权、保护移交、终态保留、FULL/MO 页面行为及前端衔接 |
| E 集中验收 | A–D 核收后，新建集中验收实施者 E；固定最终候选和必要证据后新建最终全范围审核者 E | 本文验证范围、必要包/容器/前端门禁、已确认真实范围、全部未决 finding 处理及最终交付 |

每节按“实施与 focused → 固定已提交候选 → 新审核者审查 → 原实施者修复 → 原审核者复审 → Terra 核收”推进。常规实现、范围内细化、修复、复审及必要验证连续执行，不在每节末重复请求 Owner 批准。必须提前审查的 Contract/授权/事务设计，可由本节新审核者先审，再由同一审核者审核实现；不另开一轮重复角色。

创建子角色时显式指定 `model` 和 `reasoning_effort`，使用 `fork_turns="none"`。任务单提供本计划、本节目标、固定完整 SHA 与父提交、前置依赖、允许写入路径、已确认决议、测试断言/运行归属和交接目录。审核者自行阅读候选代码、Contract 和原始证据，不把作者摘要当审核结论，也不复制实施者整段推理上下文。

下一小节必须使用新实施者和新审核者，不让前一节角色直接更名承接。已存在的 finding 仍由原作者修复、原审核者复审，不为复审另换“更容易通过”的审核者。E 发现跨包问题时由 Terra 指派实际原作者修复，E 审核者核对最终修订及受影响证据；对先前未关闭的 finding 继续保留原审责任。

最多四个活跃 agent，常态为 Terra 加本节实施者和审核者；旧角色完成交接后结束或保持非活跃，修复时按需唤回，不让已完成小节常驻占槽。若外层主会话也占槽，计入总数。不得为“每节新人”递归扩队；模型槽位与测试进程数量分别管理，同节点仍遵守唯一执行与占用规则。

启动时由指定的 Terra high 主协调会话承担职责；若开启提示词的会话实际不是指定模型，先安排明确的 Terra 协调入口，不能靠文字自称已换模型。Prompt 和审核意见等过程材料放仓库外，启动提示词位于 [实施会话启动提示词](/home/dev/gdds-stage-exchange/gw08-comparison-correctness/prompts/start-implementation.md)。

## 工作包 A 修复单侧表错误降级

先经 History 实际编排路径隔离复现：单侧表的导出缓存命中后无需为导出加载 reader，但比较实现仍以 reader 缺失返回 `TABLE_READER_UNAVAILABLE`。普通和有序表都要覆盖，不能仅调用底层比较函数证明修复。

统一需求规划与执行前置条件：在表身份、存在性、schema、行数已按对应来源校验后，单侧比较直接输出 `ADDED_TABLE` 或 `DELETED_TABLE`。比较不生成逐行新增、删除记录，也不为该表强制生成 ordered/blank extension。整表导出和浏览仍完成现有绑定、内容及 closure 校验；导出缺失且无法恢复时，保留真实错误，不因比较成功跳过交付完整性。

重点接点：

- `vnext/backend/src/gateway_backend/capabilities/comparison/production.py`：`_task_arrow_inputs`、`comparison_row_demands`、`_compare_task_native`。
- `vnext/backend/src/gateway_backend/capabilities/comparison/standard.py` 与 `ordered.py`：单侧元数据路径。
- `vnext/backend/src/gateway_backend/application/history/compare_jobs.py`：`_ensure_history_demands_once`、导出缓存与 committed table access。
- surface、risk 和 bundle 中整表浏览与表级计数的既有消费者。

完成标准：同一比较对、同一规则下，冷/热导出缓存得到一致的表级语义；表不存在与存在但零行可区分；单侧无键表不因缺少行比较键误降级；真实缺损仍能诊断。整表行数与逐行 diff 数分开，不能把整表新增伪造为 N 条 `ROW_ADDED`。

## 工作包 B 升级配置表行级比较

精确名单如下，不扩展为任意 `*_cfg`：

```text
cnt_manage_cfg  iec101_cfg   iec104_cfg  iec104gw_cfg
iec61850c_cfg   jdxx_cfg     sc_cfg      scada_cfg
sg_manage_cfg  vqc_cfg      wave_cfg    wf_cfg
```

将这 12 类表移出 `BROWSE_ONLY`，使用标准行级比较、`ALL_CHANGES` 和显式比较键 `(page_no, no)`。保留原有列保留和存储规则，行增删改进入 records、风险、surface、业务导航及计数；值变化可定位到对应页面和序号。前缀协议选项表已有的规则继续独立生效，核对 selector 优先级，避免残留 browse-only 规则覆盖新配置。

存储仍使用原有的 DDL 主键或无键策略，比较单独使用 `(page_no, no)`。当前 `table_rules/contracts.py` 限制了这一规则组合；应同步修订 owning Contract 和校验约束，以明确范围表达两种键的职责，不直接复用会把比较键提升为存储主键的 `_explicit_standard_record` 默认配置，也不引入另一套表规则注册表。

两侧存在且需要按键比较时，缺列、无效键值、重复比较键不得被猜键或去重掩盖；按既有比较诊断降级。若原 DDL 存储主键本身非法，继续在物化阶段失败。单侧表和双侧空表按各自语义处理，不为新规则统一强加非空行比较前提。

重点接点为 `capabilities/table_rules/registry.py`、`contracts.py`、`resolver.py`，以及 `capabilities/storage_projection/view.py` 和 native 比较输入。逐表核对实际样本的列声明与数据；没有样本覆盖的表必须保留小型 Contract 向量，不能把一张表的真实验证写成全部 12 类均已验证。

完成标准：12 类表逐项命中新角色和双字段比较键；同一个 `no` 出现在不同 `page_no` 时不会碰撞；合法存储中的重复比较键只使比较降级；非白名单表和既有前缀规则没有被泛化改变。

## 工作包 C 统一结构变化展示与审计

### 判定条件

统一业务判定由后端比较与展示策略拥有，供风险、surface、导航和变化统计消费，前端不另做一套隐藏算法。不得仅检查 `SCHEMA_ONLY_CHANGED` 名称：只浏览表的元数据路径也可能用此状态表达尚未证明内容相等的变化。默认零计数、缺少 records 或过滤后零计数均不是判等证据。

允许只审计的条件必须同时成立：

1. 两侧表均存在，行数已知且相等，没有比较失败、降级或不兼容共有字段；整表新增、删除和数据集替换不适用。
2. 变化限于列的新增、删除，共有列类型兼容，比较键未变化；同时增删列仍须满足这些条件，不推断重命名映射。纯类型变更等场景继续按原 Contract 处理。
3. 非空表具有有效比较键及共有可比较字段，并有实际比较产生的共有业务值相等证据。原始增、删、改必须为零，`UPDATE_ONLY` 抑制的真实增删必须计入判断；不能把未计算字段的默认零当成证据。
4. 两侧均为空时，允许通过已绑定 descriptor 证明没有行变化，无需为此猜测行比较键；明确的键变化和类型不兼容仍不隐藏。
5. 有序表还须没有移动、位置或空白区间变化；不能用内容更新数为零隐藏其他有序语义变化。
6. 既有 `content_changed` 及其他真实内容证据已经被解释，共有业务内容或必须展示的保留字段确实变化时不能被结构策略覆盖。

优先复用 native 比较和已有 projection 证据；需补充共有列判等时，沿既有 Rust 与行需求路径生成最小证据，遵守内存、取消和 deadline。不得复制 Python 比较算法，或为仍只浏览的表普遍生成行级展示。

### 展示与事实

保留原始比较事实和 schema 变化信息，统一派生对外的未变化展示，取消被隐藏结构变化对应的 schema 风险、变化标记及统计贡献。表仍可浏览。同步核对 `content_changed` 的消费，避免 surface 随后又将同一表改回 UPDATED；不删除其他真实行风险、诊断或有序变化。

现行 [Comparison Contract](contracts/comparison.md) 已规定 `COLUMNS_ADDED` 按共有列比较且不展示新增列；本轮保持其兼容 ENUM/SET 演进规则，不把所有 `COLUMNS_ADDED` 分类无条件视为无变化。对满足上述条件的删列或同时增删列补齐一致语义。证据不足时保持原有可见变化或降级，不能为减少提示放宽判等。

页面无变化不改变规范数据保存：若规范状态与基线不同，仍可提交当前完整组态；规范状态相同才按现有 `NO_CANONICAL_CHANGE` 拒绝。schema 隐藏也不修改归档来源图的 canonical 身份和时间事实。

### 审计与生命周期

审计采用现有 ArtifactStore 的后台产物，并至少关联：比较双方的内容身份、pair、comparison digest、适用规则身份、原始表事实、被隐藏列变化、判等依据和隐藏原因。记录可追溯的事实与小型证据，不额外复制整表数据。审计不加入前端下载 bundle、风险 annotations 或普通页面 diagnostics。

后台 ready closure 纳入审计引用及其完整性与保护范围；发布隐藏后的成功结果前必须写入并校验审计，缺失或损坏不能静默发布。比较缓存命中时也要恢复足够依据，并确保当前结果关联的审计已存在；不通过强制禁用缓存规避一致性要求。

未提交 Preview、独立 History 的审计随其原有结果保留策略管理。形成 Submission 后，相关审计与审核 bundle 一起转为提交所有的保护；工作区复用、退回、撤回或归档关闭不释放这些仍供查阅的产物。保护与提交记录同寿命，不给全部临时计算中间件无限保留期。

完成标准：满足条件的表在各页面、导航、风险和摘要中一致表现为无变化；原始事实可追溯；冷/热比较缓存的语义和审计依据一致；所有拒绝隐藏的边界均保留对应真实变化或诊断。

## 工作包 D 审核读取提交绑定结果

### 不可变绑定与保护移交

复用 Submission 已有的 `preview_result_id` 和 PreviewResult 不可变关系表达审核来源。实施时将绑定检查落实到 repository、提交、Preview、bundle ref/digest、两组或一组 pair 身份及后台审计，不能只存一个可由客户端替换的 URL，也不再创建一份同义权威结果。

AcceptSubmit 在既有事务中校验并冻结所需结果与闭包；Submit finalize 在同一事务中建立提交所有的审核 bundle 完整闭包和审计保护，再释放 Attempt/临时保护，避免完成时丢失引用。失败、重放和重启恢复沿既有事务与幂等边界处理，终止的 Attempt 不留下无消费者的永久保护。

当前 `_transfer_finalize_protection` 主要保留 source-package 和 canonicalization-manifest，不能仅凭 `preview_result_id` 仍存在就认定 bundle 受保护。检查 REJECT、WITHDRAW、StartArchive、CLOSE_NOT_ARCHIVED 及 cleanup 的所有保护释放接点，保留提交审核结果，仍按既有规则释放工作区占用与当前指针。

### 授权读取

增加按 submission 定位结果摘要及 bundle 的只读用例，复用现有 bundle 下载与校验能力。服务端先执行当前业务权限和 exact device/project/repository/目标提交校验，再解析结果。参考现有 Review 查询：`review_submission` 可读取授权 scope 内提交；只有 `withdraw_own_submission` 时沿用本人提交的读取范围。未知目标和越权目标沿用现有隐藏规则，不能借新入口读他人或跨 scope 数据。

读取不得要求目标仍为工作区 current preview 或仍有 active occupancy。现有工作区 Preview 接口继续执行原 owner scope，不为审核者放宽该接口的全局权限。当前会话每次请求都鉴权，不因本地 OPFS 已缓存就跳过服务器授权和结果身份核对。

bundle 缺失、损坏或与提交绑定不一致时，明确区分不可用与完整性错误；前端提供重新读取能力，不自动新建比较。已有测试数据缺少新绑定时按目标 schema 及测试环境重建约定处理，不增加旧审核 History 回退路径。

### 页面与审核动作

审核页取消创建、轮询 History compare 的主路径，按提交读取固定 bundle，复用已有本地安装、完整性校验、表格和公式浏览能力。FULL 展示两个原有 pair，默认“原始→修改”；各 pair 的风险、导航、表数和行数分别展示，不相加成所谓净变化。MODIFIED_ONLY 展示已有单 pair。

审核通过、退回和撤回继续作用于整个 Submission，不引入逐 pair 审批状态。基线、规则或工作区后来变化不重算旧结果；审批是否可执行仍检查最新权限、review version、基线及既有 CAS。历史节点任意比较继续走独立 History 用例，允许按该用例的现行规则生成新结果。

重点接点为 `application/submission/accept_transaction.py`、`finalize_transaction.py`、review 查询与权限、workspace PreviewResult 读取、control DB 的 submission/workspace/protection 适配器、HTTP review/bundle orchestration，以及 `frontend/src/pages/ComparisonPage.tsx` 和相关 API、路由与 view-model。后端改动 `frontend/` 前按 AGENTS 通知前端设计会话，纳入相应前端审核；本计划不建立新的前端固定角色安排。

完成标准：提交后、重复打开、刷新、换审核者以及工作区复用后均读取同一绑定结果，不创建比较任务；退回、撤回、归档关闭后仍可按当前授权查阅；越权、缺损和错误绑定不能被缓存或 fallback 掩盖。

## Contract 与身份调整

在各工作包产品修改前或同一提交中同步 owning Contract，保证以下约定一致：

| owner | 必须同步的语义 |
| --- | --- |
| [Comparison](contracts/comparison.md) 与 [comparison-compute](capabilities/comparison-compute.md) | 单侧元数据前提、共有字段判等证据、原始与受抑制计数、有序变化边界 |
| [ADR 0018](refactoring/formal/adr/0018-canonical-domain-comparison-and-comparison-rule-view.md) 及 table rules/storage contracts | 12 类角色与比较键，存储键独立性，只存不比内容事实与结构隐藏的交互 |
| [Comparison Surface](contracts/comparison-surface.md)、risk 与 business navigation owner | 统一对外变化、风险与计数，保留原始事实及表浏览 |
| [Comparison Bundle](contracts/comparison-bundle.md)、Preview READY/closure | 前端交付闭包与后台审计引用的各自范围，缺损与发布语义 |
| [Business Lifecycle](refactoring/formal/contracts/business-lifecycle-and-state.md) 及 Submit/Review/cleanup owner | 提交绑定结果、授权读取、保护移交与终态保留，规范状态提交资格不变 |
| [前端 kickoff](../frontend-vnext/frontend-kickoff.md) 与 OpenAPI | 将审核使用 History 的旧约定更新为提交绑定 Preview；FULL 双 pair、错误展示、摘要与下载接口 |

逐项列出真正受影响的规则版本、algorithm/cache identity、DTO/checkpoint 和 digest preimage。比较、风险或展示语义变化后，缓存身份必须由实际消费者核对，旧缓存不能被静默恢复为新语义。能复用现有规则身份时不增加独立版本轴；任何新增 ID、digest 或版本必须说明防止何种错配、由谁检查。

只在形状或 preimage 规则确实改变时修改对应 contract version；语义产物改变时重新生成其 digest/golden，不强行维持旧摘要。新增或修改持久文档解码采用严格 pydantic 并禁止多余字段，行计算对象保持现有合适的轻量类型。control DB 需要新增绑定字段时直接修改单一基线 schema，旧本地测试 DB 的处理在执行时按仓库约定明确记录，不自动迁移或擅自清理联调数据。

## 验证范围与唯一测试责任

下表是实施后的验收范围，不是当前通过记录。复用既有 owner；同构用例用模块级共享参数表，其他层只加必要贯通用例，避免把整张矩阵重复到多个层。

| 范围与主要测试 owner | 必须验证的业务屏障 |
| --- | --- |
| A：`test_history_compare_jobs.py`、`test_history_metadata_materialization.py` | 普通/有序、单侧新增/删除、存在空表、导出缓存冷/热；通过真实编排证明 reader 需求与执行一致；缺损仍失败或可诊断 |
| B：`test_table_rules_contracts.py`、`test_table_rules_comparison_view.py`、storage projection tests | 12 类精确命中、同 no 不同 page、行增删改、重复/无效比较键、原 DDL 键非法；非白名单与前缀 selector 回归；存储约束没有被意外提升 |
| C：比较策略 owner 与 `test_comparison_cache.py` | 增列、删列、同时增删列、双侧空表；共有值变化、类型不兼容、键变化/缺键/重复键、证据未知、UPDATE_ONLY raw 增删、只浏览表默认零计数、有序移动/位置/空白均不能误隐藏；缓存恢复有足够证据 |
| C：`test_risk_evaluation.py`、`test_surface_assembly.py`、`test_business_navigation.py` | 同一判定贯通风险、surface、导航与计数；表可浏览，`content_changed` 不把已证明的纯结构变化重新显示；保留其他真实风险 |
| C/D：审计与 `test_submit_artifact_protection.py`、`test_submit_finalize.py` | 审计存在且可回溯、缓存命中不漏审计；finalize 原子移交、合法重放/恢复、失败 Attempt 收尾，以及终态/cleanup 不删提交结果 |
| D：`test_review_http.py`、`test_review_transactions.py` 与新只读用例 owner | 授权审核者、本人只读、他人/跨 scope/未知对象、缺损/错误绑定；新读取不依赖 current pointer；原审批基线/version/CAS 语义保持 |
| D：前端 ComparisonPage/API 与 bundle/view-model tests | FULL 双 pair 默认视图、MO 单 pair、分对统计、刷新与重复打开不创建 History；本地缓存按新摘要和授权绑定读取；缺损不会显示空结果 |
| 回归：`test_comparison_s3_e_live_semantics.py` 等既有 native/比较 owner | 标准/有序增删改计数、移动/位置/空白不混入内容修改；UPDATE_ONLY 业务口径与 raw/受抑制计数可解释 |
| 回归：复合信号和公式既有 owner | 单侧字段增删不误报，共有字段真实更新、公式变化、测点增删经源表、虚装置导航和浏览完整可见；Preview/History 均贯通 |
| 回归：无键表既有比较 owner | 双侧空表 schema 同/不同路径一致；未知非空变化无有效键时按现行 Contract 降级；已定义的合法 keyless 策略不被统一改成失败 |
| 回归：Submit/归档既有 owner | 可见零变化但规范状态不同仍可提交；规范状态相同仍拒绝；隐藏 schema 和业务等价不改变 canonical 来源衔接与时间校验 |

普通比较数值断言应核对现有 `row_added_count`、`row_deleted_count` 与 suppressed 字段的真实含义，不能套用旧字段名或误将原始数再次相加。整表行数与逐行 diff 数分开验证。

真实数据建议采用最小范围，在执行启动时按 DC33/DC98 固定并由 Owner 确认：

- 已知 t4 v1 MODIFIED_ONLY 空基线场景，针对普通/有序代表表核冷/热 History 和提交后的审核读取；复用现有输入，不为此默认运行完整 t4 旅程或改写待审现场。
- number1 或经核对的等价真实 FULL 样本，验证配置表、结构审计、摘要与复合信号。记录输入摘要和适用规则，旧报告的 `+2/修改55/-2` 等数字只有在样本和语义一致时才作为 oracle。
- 一条代表性的提交到审核贯通链路，覆盖两组比较、跨工作区审核、重复打开及一种终态后的保留。其余终态矩阵由低成本事务/保护测试承担。

已有 focused、真实数据或容器用例能覆盖同一行为时不重复运行。正确性验收不附带性能提速承诺，不安排默认全档容量旅程、预热重复采样或细粒度 profiling。

## 执行与收尾

启动时重新读取适用的 AGENTS、[测试约定](testing-conventions.md)及[阶段门禁说明](../../scripts/README.md)，确认实际源码、未提交文件归属、节点与离线制品条件。Owner 已确认本任务角色和模型例外；本次只交付计划补充与开启提示词，产品实施及必要节点测试在后续实施会话实际收到开启指令后执行。联调环境变更、推送和合回主线不包含在默认启动范围内。

实施顺序为 A → B → C → D → E 集中验收。A 先保留失败复现，再修复并验证；B 固定角色与键语义后，C 对这些规则及其余表统一落实结构审计；D 接入修正后的结果。各节及独立拆包按上文新建实施者和审核者，内聚修改可在本节形成小提交，不合并 A–D 的角色责任。前端仍按当前审核安排核收。过程材料和原始证据放 `/home/dev/gdds-stage-exchange/gw08-comparison-correctness/`，不把机器日志复制进设计文档。

所有测试、编译、lint、构建、截图和 e2e 均在专用测试节点执行，使用 clean、已提交 worktree，期间不写被测树。遵守节点用途、实际有效占用、原子取标记、获准 LAN 传输与离线缓存规则；手工运行设置适用的 `TMPDIR`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true` 并使用受控 uv 入口。Rust 变化后跑 backend focused 前强制重装扩展并核对 build input。日志放 worktree 外，保留节点、起止 HEAD/UTC、exit code 与摘要。

包含产品改动的提交完成 AGENTS 规定的五个 Python 包 ruff/mypy；改 Rust 时完成 fmt/clippy 等必需检查，均在专用节点执行。调试测试只跑受影响 focused 范围。最终后端候选通过 `scripts/run-stage-gate.py <full-sha> --packages backend --session <session>` 触发阶段门禁；实际修改 Rust 时纳入 `rust`，其他包按真实改动与闭包确定。是否实跑或沿用、是否重建容器由门禁判定，不手工创建 carried 来源。项目最终或发布验收另按相应 purpose 强制六包，不以本次阶段结果替代。

前端变更通过独立 `frontend/scripts/run-tests.sh`，真实 backend e2e 使用 `frontend/scripts/run-real-backend-e2e.sh` 及必需 session；不并入后端 runner。按既有要求在 1280/1920 宽度检查审核两组视图、表状态、风险和禁用原因。截图及日志写 worktree 外并记录摘要。

涉及保护生命周期的实际容器用例和新增审核读取贯通在最终候选集中验收，不因每包交接重复构建。失败保留原始记录，停止该次及依赖验收，修正后新开运行；不得用改预期、旧结果或优化实验报告覆盖失败。

执行完成必须满足：

- 本文已确认行为全部落实到 owning Contract、代码及有意义的测试；被替代的审核 History 自动创建路径删除。
- 实际候选提交、受影响包门禁、适用容器门禁、前端结果与已确认真实范围均有可核对来源，未知不写通过。
- FULL/MO 审核结果绑定稳定，所有提交终态保留所需结果与审计，存储/比较键职责和 schema 隐藏边界没有被放宽。
- 不改写调查原件、不清理他人资源或已有待审联调数据；本人运行资源与节点占用按实际收尾释放。
- 退出形成一页总结，写实际改动、设计偏差和遗留项，通过引用指向阶段交接区原始结果。推送、合回主线和部署仍按后续明确安排执行。
