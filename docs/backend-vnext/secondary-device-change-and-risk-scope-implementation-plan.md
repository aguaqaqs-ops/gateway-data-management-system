# 二次装置变化归属与风险范围实施计划

状态：与[设计](secondary-device-change-and-risk-scope-design.md)配套的可实施候选；当前只授权文档收口及一个 Sol xhigh 子agent独立设计审核。审核者不改文档或产品、不运行测试；协调者修订，原审复核同一finding。产品实施与部署另行授权。

## 1 输入和开工条件

- 源码基线：gw08-dual-env 的 0c34339a125d6ff5f0ccfe42af97603a47c7523d。文档独立提交后以完整SHA固定审核对象；实现启动时若源码前移，先核对受影响文件差异，不覆盖他人在途文件。
- 已定范围：十类测点表完整records；device_cfg保持原ALL_CHANGES/业务键；十一标准表普通增删不产风险；十表name-only LOW；局部/共享范围分离；删除值完整展示；尾部空点LOW、中间规则保守保留。
- 不待决的默认边界：不将device.description/point_name一起降LOW，不把中间未推移地址的空点进一步降级，不改审批/CAS/存储schema/资源预算。
- 现场实际pair与空点表是复现及退出证据缺口，不阻止明确语义的编码；未取得时相应实际故障闭环仍为UNKNOWN，不用synthetic通过代签。
- 前端实施前告知前端设计会话目的、涉及目录/Contract版本与验收范围；按AGENTS由其纳入审核调试。设计阶段无需写frontend/或发送未经授权的外部消息；开工协调渠道未明确时先准备准确告知文本，通过已有项目会话渠道完成。
- 当前设计及计划不直接改owning Contract；产品实施的第一包必须同步改正式Contract，防止候选设计被误当已实现合同。

## 2 工作包顺序与边界

| 包 | 输入与输出 | 前置 | 风险与退出条件 |
| --- | --- | --- | --- |
| P0 Contract与语义绑定 | 正式Contract、目标schema、规则参数、版本与复用测试计划 | 设计审核通过且产品实施获授权 | C；若需改事务/授权逻辑拆A/B包；版本身份有明确核对者 |
| P1 比较记录与风险 | 十表scope、增删排除/name规则、candidate key、空风险complete | P0 | C；纯增删可展示无风险、混合修改保留风险、跨表cache不串 |
| P2 归属与公共提示 | 新导航producer/validator、typed归约、registry变化与orphan动作数据 | P1 | C；无整表个人风险扩散、精确变化与未知风险可并存 |
| P3 前端消费 | v4 decoder、范围选择器、完整删除值、定义/未归属/公共风险入口 | P2且完成前端告知 | C；fixture与页面各状态一致，mock与真实贯通 |
| P4 有序空点 | 新tail bounds、Risk分类、cache输入 | P0；与P1共享风险接口变更串行合入 | C；边界/区间计数正确，旧配对负例不回退 |
| P5 最终候选核收 | focused结果、必要门禁/容器、最小真实范围、阶段总结 | P1–P4收敛 | 不清未决失败；Owner核收后才能另行部署 |

P1/P2可由同一新实施上下文承担两个内聚包，P3/P4各自新上下文；无固定前端角色要求。后端协调者、实施者、独审者按当前AGENTS模型和风险规则安排，不用旧交接角色。当前仅开启用户指定的一个设计审核agent，不递归扩队。

## 3 P0 具体变更

正式文档更新范围：contracts/business-navigation.md、risk.md、comparison.md、row-location.md、ordered-diff.md、comparison-bundle.md，以及table rules owning说明。明确basis新语义、risk_complete和membership完整性、公共提示、删除record值与context分工、blank间隙范围/变化计数。

新文档边界类型用pydantic strict/extra=forbid统一字节解码；逐行对象继续dataclass，不复制类型复检。扩展现有导航_Document子类，不为新字段再增加手写JSON形状解码器。前端保持同样严格的未知字段/必填/类型检查。

身份改动按设计§8，具体文件：

- risk_evaluation/contracts.py：ruleset/rule v8、risk-model v5及新name rule/reason；_rules.py核参数；candidate key绑定所有新事实。
- business_navigation/contracts.py及前端model.ts：navigation v4；同时改diagnostics schema/文案。
- application/preview_jobs.py：job v5、assemble-state v11；workspace/preview.py在已有capability_contract_versions填写 `{risk_model: <version>, risk_ruleset_digest: <digest>, business_navigation: <version>}`；worker decoder核当前值，不接受仅传空map；该map属于服务器job语义，不加入调用方HTTP请求幂等指纹。结果使用入口由preview.operation_id读取已绑定且已核scope的OperationRecord.job_payload，校验其job/capability版本；不假定PreviewResult已有capability map，不为此增加DB列。provider_versions不为本问题滥增字段。
- application/history/contracts.py：job v3；compare_jobs.py：assemble-state v8。History既有accept fingerprint与reuse candidate都含job contract，更新相关预检及worker版本核对测试，不改其DB表结构。
- application/preview_binding.py、workspace/preview.py、history/compare.py、compare_bindings.py及结果reader：逐条核新作业、同键重试、跨键成功复用、checkpoint恢复、旧成功bundle读取。旧受理的幂等键不重新绑定到新作业：保持原指纹冲突/原操作语义；新请求不能以旧成功作业满足新版本。
- Preview无跨键READY复用选择，不新增这一机制。新键照常新建operation；同键同请求继续返回原operation，不因服务器版本改变产生新的幂等冲突，也不重绑定。既有Preview结果reader、T1/finalize和审核绑定入口核当前job/capability版本，旧结果走原PreviewBindingConflict/不可用错误，提示用新键重做Preview；不是只留给前端v4解码失败。History跨键复用则先核job contract，再走既有完整结果预检。未改READY闭包格式，避免额外轴。

P0退出：源码依据说明每条身份由谁计算、在哪里检查；参数/版本变更golden齐全。Preview HTTP请求request_fingerprint保持原preimage；capability map/job version只用于服务器执行与结果可用性。增加同键跨服务器版本仍指原operation、新键新operation、旧结果不能提交三条最小断言，不新增第二个请求指纹。

## 4 P1 具体变更

`capabilities/table_rules/registry.py`：十类scope→ALL_CHANGES；device_cfg保持现有值。同步contracts.py中相关固定规则约束；常量更名及引用/测试同步，不留旧别名。

`risk_evaluation/contracts.py/_rules.py/_engine.py`：使用设计§4规则params解析适用性；_default_rule允许显式params，除指定规则外不改severity。增删排除在任何COUNTS_ONLY或缺records兜底前执行；name-only逐条判定，普通修改不双发name与ROW_MODIFIED。新reason映射由前端P3消费。

`risk_evaluation/candidates.py`：单表facts_jcs加入standard_rule_applicability与ordered_tail_bounds；纯新增/删除空事件cache合法。`persistence.py`/evaluator replay接线沿用当前候选机制，不增加格式轴，改变key足以隔离旧输入。

`comparison/production.py`和records source：确认实际各入口detail_policy为FULL_BEFORE_AFTER_VALUES，完整增删值存在；不改已满足目标的Rust record生成器。不为展示牺牲真实counts或去掉ignored/excluded的已有定义。

退出断言：两个删除完整record和locator、suppressed=0、没有普通删除annotations；五个地址修改保留MEDIUM_HIGH。对纯增删表，attribution完整且局部变化EXACT；风险report可无此表条目，不为UI补UNKNOWN。

## 5 P2 具体变更

`business_navigation/contracts.py`：增加设计§5字段、两个新诊断码及交叉字段校验；导出类型由owner root统一提供。更新facts.fallback_reason职责，只在comparison/locator问题时fallback，另有风险与membership完整性。

`application/business_presentation.py::RiskAttribution`：保留rows、global/table真实风险、待定位事件摘要与complete；仅对十一类共享标准表按target/coverage/reason分类，其他整表和ordered目标保持原路径；device风险走定义变化引用。所有保留map/list先计入operation memory，退出清空。observe新生成与replay共用；未知target保留等级到public，不丢弃。

`row_location/producer.py`与business_presentation接线：扩展现有prepare输出的operation-local上下文以消费device实际record两侧dev_addr；只读取真实snapshot/locator，不从只含changed columns的修改record猜未改地址。普通测点FilterRecord继承已有risk_level；另核未绑定风险identity并汇总为public。

`business_navigation/producer.py::devices`：

1. 现有registry扫描建立两侧合法谓词/owners及histogram；定义记录形成device_definition_changes。
2. 对每个FilterRecord，将变化/风险赋给各自实际侧owners；同页按record identity去重。modified数一次，迁入/迁出是子集；同一记录命中旧/新项不重复全局计数。
3. 无变化表/行满足身份复用资格时，histogram中count>0的值比较两侧owner集合，标记相关项membership_changed；仅声明集合差异，不保留逐行账本。
4. 根据变化/风险/membership各自完整性发布facts；typed table_scope与table_notices同源。summarize只取局部事实，独立完整性AND；不再回填table.risk_level。
5. 原有unsupported/missing/duplicate/orphan诊断与coverage等式保留。counts未知不写0；资源异常失败，不吞异常。

设备定义变化与风险来源均可从现有device表records定位，device_definition_changes只是已有事实引用，不新增审批对象。没有可验证device row identity或侧值时不猜关联，明确风险/归属不完整，整表来源仍可浏览。

退出断言：风险缺失但变化完整时change EXACT；风险已知部分保留；registry-only等量交换归属能识别；孤儿风险公共入口可达，非受影响装置无个人风险。

## 6 P3 具体变更

- features/view-model/model.ts：v4类型/严格decoder/引用与摘要验证；单一scope selector；navigationTabHasDifferences和risk过滤复用。replacement新数组为空。
- table-rows.ts：删除行值采用snapshot→record.before_values，context只作身份；逐侧类型核对与SQL NULL语义保留。旧无记录身份复用guard改为变化/身份完整，不依赖risk_complete；fallback仍禁止无依据复用。
- pages/ComparisonPage.tsx：tabChangeKind/tabRiskLevel、侧栏summary、表头/风险原因/本页统计全部消费scope selector；显示“局部未知”“整表风险”“待定位风险”正文。非个人公共提示不使用个人风险徽标。
- table-rows.ts::blankIntervalRows与intervalRiskAnnotation：停止按start+offset虚构空点行、按physical index+1认业务位置，以及将区域风险附到真实新增/删除有效行。每条blank record生成一条明确区间摘要（before/current范围、原row_count净差、方向、对应区间风险），进入差异/风险过滤与no定位；真实snapshot行保持真实内容，其ROW风险不变。同步BrowseRow kind/布局/搜索/折叠/导航器消费，摘要不计作业务行数，不伪造before数据。
- diagnostics.ts、risk-copy.ts：两个新诊断和STANDARD_NAME_UPDATE中文，不暴露路径；保留Debug原码。
- 定义变化入口与未归属浏览复用现有查看整表/本地筛选状态。URL加本地unassigned_side，清理与恢复必须保留pair/table/side边界，replacement不套跨侧选择。一个表的孤儿状态不串到下一表。
- 共享风险在默认风险筛选和隐藏空页签时仍能发现；公共入口列唯一table_id，点击显示整表及原因，不能让相关装置条目再次全染个人风险。

mock fixture来自同一次真实producer归档，不能手工拼与后端不一致的schema。UI截图1280/1920逐项对照草图；新公共提示/定义变化布局无既有草图时给Owner确认明确偏差，不冒称已对照通过。

## 7 P4 具体变更

application/pair_pipeline.py新增operation-local tail bounds准备函数，替代_ordered_position_maxima：先从实际ordered handle/records读取增删位置与数量（O(D)集合、预留内存），再复用原两侧扫描同时算max no与max保留有效no。canonical blank判定复用已有provenance/pseudo-gid范围校验入口；若不存在公开helper，新增owner root的薄入口，不在Risk复制parser/canonical算法。

接到RiskEvaluationInput.ordered_tail_bounds，所有构造器、tests、cache key更新，不保留旧字段别名。_emit_ordered_rows保持非空增删原判据读取max_position；_emit_blank_intervals读last_retained，按设计§7对整个空点间隙变化区域分级，count仍为occupancy差，不按range长度构造新计数。

完整性检查：实际增删位置数与summary一致、同侧位置唯一且存在、非空记录不落canonical blank；已退化/缺records/无canonical reader则complete=false，UNKNOWN。不能以缺输入当空表；true+null才表示无保留有效点。现有deadline/cancel/预算/reader关闭语义保持。

当前native blank区间不连续且可能跨非骨架有效行，风险端不切分区间。既有replacement partner校验与move/数量不等/绝对位置偶合负例必须保留。只有无法从现有records/reader取得所需事实时才提出最小Rust公开接口修改并复审；不预设重写比较算法。

## 8 测试矩阵及唯一owner

| ID | 断言 | 主要文件/owner |
| --- | --- | --- |
| V1 | 十表scope、cfg不变、键与excluded不变 | test_table_rules_contracts.py、test_table_rules_resolver.py |
| V2 | 纯增删零annotation且complete；name-only/混合/其他表/COUNTS_ONLY不误降 | test_risk_evaluation.py共享参数表；test_risk_contracts.py |
| V3 | 同facts/task的适用/非适用表不串cache；空事件replay；tail输入变化隔离 | test_risk_candidate_cache.py |
| V4 | 双侧归属、迁移、计数相等registry-only、孤儿/重复/NULL/超域/缺列 | test_business_navigation.py及现有导航测试模块共享参数表 |
| V5 | locator真实位置/旧值/context矛盾拒绝、无before完整删除值 | test_row_location.py；前端table-rows.test.ts各自边界 |
| V6 | typed scope与残余row identity不丢；变化EXACT+风险不完整；正常非筛选ordered ROW/ROW_PAIR/ROW_INTERVAL不新增装置待定位或不完整诊断 | business_navigation tests、test_business_presentation_flow.py |
| V7 | Tail判定：尾部追加/删除/已有空尾/全空/稀疏/新增点后缀/间隙内保留点/move | test_risk_evaluation.py及现有ordered fixture，复用旧负例 |
| V8 | v4decoder、summary/筛选/空页签/公共风险/定义与孤儿URL恢复 | model.test.ts、table-rows.test.ts、ComparisonPage相关测试 |
| V9 | 新旧job/checkpoint/成功复用身份；同键不改绑；权限/crossscope不回退 | 现有preview binding/history compare及job tests，最小反例 |
| V10 | 真实1→2与一个空点表；Preview/History相同pair；bundle/浏览器一致 | 受控真实旅程及frontend真实backend e2e |

实施时先用rg定位既有测试模块的真实文件名；上表owner不要求新建同名模块。纯逻辑参数化测试不引入Dolt init；有Dolt lifecycle加integration；定时预算测试serial并-n0。测试不以finding轮次命名，不重复跨层完整矩阵。V7/V8增加空点间隙跨非骨架有效行、稀疏no、occupancy差小于范围跨度的摘要断言：不虚构空点逐行变化、不将interval风险染到新增有效点、风险筛选仍能找到摘要。

### 8.1 执行与门禁

所有产品测试、lint、编译、构建、mock/真实e2e/截图在五节点池内。按testing-conventions执行入口、网络缓存、长测及FD7章节，执行时核空闲/进程/端口并mkdir原子占用，只释放本人标记。手工命令日志放 `/home/dev/gdds-stage-exchange/secondary-device-risk-scope/`，记录节点、完整SHA、起止、exit、输入与资源身份；TMPDIR用磁盘真实目录，legacy链接按规则准备。依赖不变不重新选依赖；uv统一uv-consume.sh，离线前提不足先停止。

focused命令在节点clean已提交worktree执行，例如：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest tests/test_risk_evaluation.py tests/test_risk_candidate_cache.py -m 'not serial' -n 4
./vnext/scripts/uv-consume.sh -C vnext/backend run pytest <本包相关测试> -m 'serial and not parallel_safe' -n 0
```

第一行只是P1/P4示例，按已有marker与真实测试名选择，不盲目全模块并行。如果改Rust，在节点运行rustfmt/clippy并强制重装gateway-compute-python后才跑backend focused；CARGO_TARGET_DIR在worktree外。代码提交前五Python包ruff/mypy必跑，均在占用节点；前端入口为frontend/scripts/run-tests.sh，真实后端独立入口带必填session且不外层重复占用。

最终受影响门禁在开发端触发 `scripts/run-stage-gate.py <full-sha> --packages <按当前闭包确定列表> --purpose stage --session <唯一会话>`；脚本查表决定沿用/容器重建，不手算carried，不手工建固定门禁树。门禁closure会涉及Rust/backend及相关包，由脚本权威表确认。不把focused等同阶段通过；项目最终/S5/release/production仍必须相应purpose六包fresh，本工作包不擅自宣称其为最终项目门禁。

P1–P4不改容器边界时集中容器验证可记deferred，阶段最终HEAD需绑定结果。若实际改Docker/entrypoint/环境接线等，先读触发式重建并做必要最小验证，不用deferred关闭正确性finding。长测由持续协调者等待退出及必要低频核查，不让审核者常驻监视。

### 8.2 真实范围与性能

先只读定位原pair，记录事实/records/locator/annotations/navigation/diagnostics的引用关系与实际软件身份；拿不到则相应复现结论UNKNOWN。池内隔离导入两份真实输入一次，检查device_mx的7条记录、34/9234/65532和一个未受影响装置，再做同pair History与浏览器最小贯通。实际空点表未提供时，先完成V7小向量，原故障退出仍待证据。

08不属测试池，不在其运行focused/构建；部署、重置、导入及修改共享设备须另有授权和真实资源协调。只读现有结果优先，不为取证默认重跑全旅程。

正常真实旅程顺带记录已有步骤耗时、records/locator/bundle大小与注解数量，不新增profiling系统。高增删数量本身不授权大规模测量；发现明显回退或预算不足时提出一个代表样本、同节点/配置的一次有限对照方案及Owner可接受界限。当前不设未经Owner确认的百分比SLA，也不承诺没有退化。

## 9 审核和交付

设计审核在只读detached worktree，固定文档候选SHA；审核意见、提示词和finding原件在仓库外交接区，正文不复制原始运行日志。Sol xhigh核对源码与文档可实施性，重点：缺失载荷、完整性语义、风险漏报/扩散、cache输入、tail区间单位、版本复用及比例化。不得扩大业务/验收范围或运行测试。

协调者本人修订两份文档，原审复核同一finding；无未决阻塞finding方可声明“设计审核收口”。后续代码实施仍按P0–P5执行，设计审核不代替代码独审、门禁和真实范围核收。

交付：设计、实施计划、固定文档提交；交接区追加阶段日志与审核原件引用。文档只做差异、链接和源码依据检查，不启动五包ruff/mypy或产品测试。阶段退出才入库一页人读总结，结论、偏差、遗留与门禁引用齐全；不抄机器hash清单进总结。不推送、不改写已审提交、不清理他人资源。审核worktree在finding关闭、无消费者且clean后回收，不force。
