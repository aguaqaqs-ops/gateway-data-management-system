# 网络/串口通道表规则重构设计

状态：设计候选，待独立审核；本轮仅设计，不授权产品实现或测试执行。

适用分支：`gw08-dual-env`。Owner 来源：本会话确认的四项规则及后续澄清；最后澄清为 `dev103_9150 → nrts103`。
本设计是下一次代码实现的目标规格；当前生产行为仍以现行 Contract 与源码为准。实施时同步修改 owning Contracts，不保留旧路径。

## 1. 目标与业务规则

统一识别网络/串口通道、有序引用表、通讯规约配置表。新增串口与任意规约引用表支持；删除固定 IEC104 有序表名单、固定转发页签名称和 `_cfg/_dev_cfg` 导航限定。

### 1.1 配置行与通道键

| 注册表 | 通道字段 | 表名前缀 | 节点 key |
| --- | --- | --- | --- |
| net_cfg | board, link_no | b{board}_n{link_no}_ | protocol:b{board}_n{link_no} / channel:b{board}_n{link_no} |
| com_cfg | board, com_no | b{board}_c{com_no}_ | protocol:b{board}_c{com_no} / channel:b{board}_c{com_no} |

仅 `exe` 非空的行生成通讯规约子对象；NULL、空串、纯空白视为空。字符串 `exe.strip().casefold()` 用于匹配，不作数值到字符串强制转换。数字键为整数（不接受 bool），范围 `[0, 9007199254740991]`；非法键行不生成通道，原整表仍可访问。配置行不能从表名反向捏造。

同一逻辑侧同一键的重复行沿用规范整行排序键最小者；先筛 exe 非空，再选代表。前/当前侧分别选；前后集合合并，通道排序为网络在先、串口在后，各自按数值 board/通道号排序。标签优先当前代表，再前侧代表：`channel_desc`（无则通道前缀）加一个空格加 `protocol_name`（无则空），最后 strip。逻辑侧不存在不借对侧行制造本侧归属。

通讯规约组固定第一项为存在的 net_cfg 整表。com_cfg 任一逻辑侧存在至少一行 exe 非空（不要求键合法）时，固定第二项为 com_cfg 整表，显示名按表 COMMENT 的 current/before/name 回退；其他情况 com_cfg 保留 OTHER_TABLES。net_cfg 缺失时 com_cfg 是首个实际项，不插占位。固定项之后按上述通道排序。

### 1.2 唯一的通道表名解析

规范化标识符后 fullmatch `^b([0-9]+)_([nc])([0-9]+)_(.+)$`，数字允许多位，至少一个后缀字符。按整数值关联注册行（允许前导零，不按拼接字符串误失配）；数字超域不具备业务通道资格，整表进入 OTHER_TABLES。不支持负号、符号、空后缀。`n`/`c` 是键的一部分，绝不跨注册表认领。

表名是匹配输入，不拼接 shell、文件路径或未经引用的 SQL；所有表访问继续走实际 catalog 的精确名字。

### 1.3 有序引用表

有序属性 = 符合 §1.2 且本侧真实表 COMMENT 包含字面串 `引用表`。这完全替换固定 IEC104 名单；不要求 exe=iec104、tab_num>0，也不要求后缀与 exe 相符。

COMMENT 缺失/空白不命中；不能用回退的 display_name 判定。引用表页签名称为 COMMENT 将所有 `引用表` 替换为空再 strip，结果为空则回退实际表名。例如 `遥信引用表` → `遥信`；`双点遥信引用表` → `双点遥信`。这是按真实 COMMENT 输出，不保证它与历史固定名称文字完全相同；实施核对代表数据，差异报告不得修改 COMMENT 掩盖。

有序属性不依赖注册行是否存在。存在有效的同类型/同数字通道注册行时，归入 FORWARD_CHANNELS 对应通道的整表 tab；通道名称仍取 channel_desc，current→before→通道前缀。注册行要求 exe 非空。没有注册行时仍按有序语义比较，但作为 OTHER_TABLES 的整表访问，保留 CHANNEL_TABLE_UNCLAIMED 诊断（扩展至 n/c）。绝不因无法导航就改回普通比较。

### 1.4 普通规约表与映射

未命中引用表的通道表：先按 n/c、board、通道号精确找本侧有效注册行，再比较后缀是否以映射后的协议片段开头；不限定 `_cfg` / `_dev_cfg`，按 Owner 要求采用字面 startswith，不另加下划线边界。映射未命中时使用规范化 exe 本身；匹配不区分大小写。

| net_cfg.exe | 匹配片段 |
| --- | --- |
| dev103 | nr103d |
| ht103 | nr103ht |
| ModbusNetDev | modbusnet |
| stdmdsNET | stdmds |
| DLL | dll3xx、dll495（两个均认领） |
| dev103_9150 | nrts103 |
| mach2Dev | mach2 |
| abb103Dev | abb103 |
| cagc | agc |

| com_cfg.exe | 匹配片段 |
| --- | --- |
| stdmdsCOM | stdmds |
| DLL | dll3xx、dll495（两个均认领） |

tab 取实际表 COMMENT，无则表名。点击通过 table_id 打开原整表；row_filter=null，不拼接/合并行。通道内按实际表名 UTF-8 排序，前后同名表只发布一个 tab。COMMENT 仅改变标签时不改变 tab key，使用实际表名作为 tab key。

这些映射只决定导航归属，不自动改变比较键。现有六种协议 `_cfg/_dev_cfg` 比较键规则保留；新增普通表未命中它们时按 DDL PK/keyless 兜底。不从 exe 或任意后缀推断 page_no/no/gid。

### 1.5 双侧与认领

普通比较使用当前侧存在的同名表的 COMMENT 决定该 pair 的有序属性与分组；当前表不存在才用前侧。当前 COMMENT 缺失不借前侧补成引用表。通道关联须在该表实际存在的侧验证；普通表可从前后注册行取得归属，前后协议改变时合并两侧候选，表只发布一次。同一表当前侧可归属时优先当前，只有前侧可归属时允许前侧。不得把本侧不存在的表当作匹配成功。

引用→普通、普通→引用使用当前模式；不同时向转发和规约组发布同一表。先确定 pair 有序属性，再做对应组归属，不能让前侧旧分类抢占当前新分类。DATASET_REPLACEMENT 每侧完全独立执行上述规则，标签/COMMENT/注册行不跨侧借用。

认领优先级沿用既有跳过/只快照/只浏览约束，再是注册表固定项、有序转发通道、装置分组、普通通讯规约、全局参数、OTHER_TABLES。通道表不会与现有装置精确表名相交；已认领表不再由 app_cfg 生成重复入口。未认领表保持唯一整表入口，不丢表。通道零 tab 时沿用现有后端空 item/前端隐藏语义。

## 2. 比较、规范化与 COMMENT 边界

### 2.1 单一解析 owner

Table Rules capability 拥有纯通道名解析和引用表条件。扩展现有规则输入，使表名、真实 table_comment、DDL 列与主键在 materialize/projection 和 comparison plan 可得。用同一个条件解析函数，Navigation 消费其结果，不复制正则或用 display_name 反推。

现有 TableRuleSelector 增加可选 `table_comment_contains`（本轮仅值 `引用表`）；selector 仍使用 REGEX+通道完整模式，匹配为名称 AND 注释。此字段进入规则正文和现有 ruleset digest，严格文档解码统一使用 pydantic strict/extra=forbid。删除旧九类 ordered selector，不建立两套候选。Skip 等高优先级规则保持；ordered 高于普通协议规则。

每侧 canonical projection 按该侧 COMMENT 决定存储策略；读取 committed canonical 以精确 manifest 的 storage view 为事实，不按 pair 当前模式重写已存表。pair 当前模式只控制本次比较与导航。

### 2.2 gid/no 与失败边界

完整引用表沿用 OrderedGidNo：稳定键 gid、位置 no、缺失稳定键的空行伪 gid、位置连续性、真实 gid 保留范围及既有 ordered/blank/risk 语义。禁止重写 Rust 算法来实现导航规则。

必须区分“引用表分类”和“能否规范化为有序存储”。当前 storage view 对缺 gid 会先报 KEY_MISSING，Rust projection 对缺 no/错误位置会报 ROW_INTEGRITY，不能泛称所有情形都可比较降级。

本轮目标：名称/注释命中但缺 gid 或 no 的表，规范化保留原列，采用 DDL_PRIMARY_KEY_OR_KEYLESS、ordered_policy=NONE 的存储 view；分类仍为 ORDERED，比较发布 ORDERED_REQUIRED_COLUMN_MISSING 的 DEGRADED/unsupported replay，不伪造缺列。有效 DDL 主键仍执行原完整性检查；有完整 gid/no 但行值非法、重复位置/真实 gid 等，沿用现有规范化拒绝，不把数据错误静默转为普通表。该缺列路径须在 owning Storage Projection / Comparison Contracts 明文更新。

pair 普通→有序时，旧侧可能不是 canonical ordered；只有两侧（单侧任务则存在侧）具备已验证 OrderedGidNo provenance 才允许 ordered native 路径。否则保留表与浏览，发布 ORDERED_INPUT_NOT_CANONICAL 的 DEGRADED/unsupported replay，不基于旧侧普通 gid 猜空行。有序→普通走当前标准策略，保留两侧原 storage facts 与 effective keys；不回写旧规范化数据，不为一次比较重建历史快照。

### 2.3 COMMENT 的身份影响

原始 table/column COMMENT 继续存于 frozen manifest presentation；不把所有展示文本塞入行内容摘要。列注释和仅措辞变化仍不改变 raw rows。新增真正参与语义的是“该侧是否引用表”和相应 resolved storage/comparison policy。

必须逐点绑定：

1. Upload：解析得到 presentation 后才能分类/投影；`storage_projection/arrow.py` 传入同侧 comment，storage view 按列决定可用存储策略。
2. Repository：catalog 尚无 comment 时不能用名字猜。`application/canonical_metadata/table_access.py` 的 committed manifest exact loader 提供同 commit presentation 与 storage facts；缺元数据不能借最新版本或联网查表。`_runtime_binding_from_provider` 等 name-only 调用全部收口到 manifest 事实或在 metadata 可得后解析。
3. BoundSnapshotInput / plan 增加完整 frozen presentation（若沿用 side manifest ref，则 materialize 时解出），pair planner 明确 descriptor 不存在返回 None，不再为缺失侧生成虚拟 rule view。resolved policy 把有序分类、所选侧与每侧实际 storage/provenance绑定进现有 per-table semantic projection。
4. Preview compare-binding 和 History materialize 后的 compare-binding 保存实际解析后的规则；accept 短事务只冻结版本，不在事务内读 Repository/COMMENT。checkpoint 恢复核对当前规则/载荷版本与 manifest 引用，不能仅从表名重算。
5. `comparison/task_input.py` semantic_jcs、operation 内去重、持久 table cache、canonical table cache、metadata early-exit 都核对 resolved 规则及实际 storage view/provenance。身份相同才可命中；canonical cache 还须绑定当前 presentation 的 manifest 身份，不能返回旧 COMMENT。有序判定翻转必须 miss/重算；只改标签允许复用纯比较，但 assemble 必须用当前 frozen metadata 重建导航。
6. Submit 的 no-change/复用路径必须包含 manifest/presentation 是否变化：COMMENT 改变有序判定时不得因 raw rows 相同跳过；仅标签变化也必须保存新 COMMENT，History 才能还原。提交导出/replay 必须保留新表 COMMENT，existing submit idempotency/事务/CAS不变。

不新增独立 COMMENT digest 或导航缓存。利用现有 manifest digest、ruleset digest、storage_rule_digest、comparison_rule_digest、semantic task key 与 artifact closure；实施中有现成同义绑定时复用。

### 2.4 版本与解码

实施提交统一升级现有规则文档 contract（新增 selector 字段，解码器核对）、ruleset 内容版本（resolver/runtime binding 核对）、storage projection 版本（防止旧规范化结果复用，manifest loader 核对），以及 Preview/History 对应 materialize/assemble checkpoint 格式（state decoder 核对）。目标数字由实施基线当前值递增，不在设计中新建轴。Comparison/Navigation wire 形状无需变化时不升它们的版本；新增诊断码加入既有诊断表与前端通用显示核对。

所有受影响文档字段从字节解码用 pydantic strict、extra=forbid；逐行对象仍用静态类型。全新项目直接更新目标 schema、golden 与 fixture，不建迁移、旧 selector alias、旧缓存兼容或双读。旧数据重建/重新上传，既有证据保留。

## 3. 实施范围与包边界

风险 B：规则会改变可恢复的 Preview/History/Submit 工作流与持久快照解释，需逐包独审；Submit 权威写入本身不增新机制，受影响绑定做针对性负向验证。

| 包 | 改动与 owning 文件 | 必须交付 |
| --- | --- | --- |
| A 语义与 materialize | table_rules/{contracts,registry,resolver}.py；storage_projection/{arrow,view,contracts}.py；snapshot materialize 与 canonical metadata exact loader | 条件唯一解析、缺列策略、注释传递、manifest/版本/严格解码；同步 table presentation、storage、snapshot、comparison Contracts |
| B pair/恢复/缓存/提交 | comparison/{contracts,pair_planning,task_input}.py；application/{preview_jobs,pair_pipeline,history/*}；canonical table cache；submit_jobs 与 import/export | 当前侧规则、provenance guard、真实绑定、cache miss/early-exit、重启/Submit 保留 COMMENT |
| C 导航与产物 | business_navigation/{contracts,producer}.py；application/business_presentation.py；pair row demands；presentation fixture generator | com_cfg 行/最小列需求、统一归属/映射/顺序、诊断、覆盖全部表；保持预算/cancel/deadline |
| D 集中核收 | Contracts、golden、fixture、必要前端核对 | Preview/History/Submit→History贯通、实际页面核对、门禁/总结 |

包 A/B 的函数签名与文档同步落地，不保留缺少 comment 的默认参数让生产路径静默走旧规则。每包新实施上下文；A/B 可以合为一个内聚提交避免不可运行的中间状态。实现前先做调用点枚举，特别覆盖 History、Repo-ref、upload、compose、cache hit、submit no-change，作为包交付清单。

前端预计不改 wire 和产品代码，页签显示消费后端标签即可；如 fixture/scripts/源码需要修改 frontend/，按 AGENTS 先告知前端设计会话目的与范围，再由前端安排审核。本轮不发送未经授权的外部消息。

## 4. 验证方案

以下是实现阶段必需验证，不是本轮已测。纯逻辑不建 Dolt；同构输入用共享参数表；资源及门禁遵守 [测试规范](testing-conventions.md)。

| 行为屏障 | 权威测试 owner / 最小场景 |
| --- | --- |
| 通道名/映射/规则 | table_rules 参数表：n/c、多位/前导零/超域、空后缀、注释命中/缺失、全部两套映射、错误 board/通道/类型不认领、DLL 双匹配、字面 startswith |
| 有序存储/降级 | storage projection + ordered tests：通用 n/c 真实 gid/伪 gid/移动；缺 gid/no 保留+降级；错误值拒绝；不重复穷举旧 Rust 算法 |
| pair 与缓存 | pair planning/task cache tests：双侧属性翻转、当前 COMMENT 空/表删除、单侧有序、相同行不同有序属性 miss、标签变化复用比较却重建导航、非 canonical 旧侧降级、无效 provenance 禁止 metadata early-exit |
| 归属与标签 | business_navigation 参数表：net/com 固定项、com 全空/混合、exe 空白、重复配置、n/c 同号隔离、引用优先、任意非 cfg 后缀、COMMENT 回退、仅一侧存在/协议变更、无通道引用表、不重复认领及集合覆盖、sg_cfg 新规则 |
| 行需求接线 | pair pipeline focused：com_cfg 必须真实读到 board/com_no/exe/channel_desc/protocol_name，metadata/未变化/缓存命中路径不漏读；ordered rows 需求不因导航零读取 shortcut 消失 |
| 恢复与持久化 | Preview/History focused：materialize 后重启使用同 frozen metadata；旧 checkpoint 拒绝；Submit 行不变但 COMMENT 更新后 Repo-ref/History 可还原，raw rows 相同不能误判无变化；现有 CAS/idempotency 仍成立 |
| 产物与消费 | 真实 producer golden、bundle decode：net/com混合、DLL、属性翻转、replacement、空组、缺列降级；前端显示 COMMENT tab、串口固定项、点击对应真实表与诊断 |

focused 调试收敛后，在 clean 已提交最终候选上用 `scripts/run-stage-gate.py` 按实际 backend/shared/contracts 依赖闭包选包，容器结果由脚本绑定到 HEAD；不默认六包 fresh。Rust 改动才加 fmt/clippy/扩展重装。代码提交按 AGENTS 在专用节点完成五 Python 包 ruff/mypy；所有测试/构建/截图均在节点池原子占用后执行。

最小真实范围建议：一对含 net_cfg 与 com_cfg 的同项目 SQL，覆盖一张 n 引用表、一张 c 引用表和一个新增映射普通表；实际样本不具备时用现有输入的受控派生 fixture做产品验证，真实未覆盖项写 unknown。集中 Preview、一次 Submit→History 及页面页签核对；不默认完整真实旅程/性能采样。具体真实输入与范围按 AGENTS 在实施 kickoff/退出由 Owner 确认，当前设计不假称真实验收已授权/已通过。

## 5. 设计就绪标准

规则、边界、绑定、失败、包依赖和验证 owner 可直接转为任务；独立审核所有阻塞 finding 由原审复审关闭；不存在待 Owner 决定的核心语义。设计审核通过仅表示具备代码实施条件，产品通过仍以实施独审、门禁和集中验收为准。
