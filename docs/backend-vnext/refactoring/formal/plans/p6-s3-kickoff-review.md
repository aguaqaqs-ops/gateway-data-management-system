# Phase 6 S3 kickoff 独立审核

2026-11-07；结论：**CHANGES_REQUIRED**。本轮有两项阻塞设计 finding（F1、F2）。这是详细设计与 kickoff 审核，不是实现、测试或阶段退出结论；尚无 S3 产品实施授权。

## 1. 固定对象与方法

- 固定候选：`67804647935ce3c1b215c25312e7a0c1ca8655f8`。本任务变更仅 `893164e73d11a7ba7d895128d90e66f913be9bcd` 和 `67804647935ce3c1b215c25312e7a0c1ca8655f8`，共七个文档路径。
- 设计起点：`5dde965a65`；起点与候选的 `vnext/` tree 均为 `56720104af34a1eb677336f57bdbc07444a56615`。以下代码定位均针对固定候选，不能用后来移动的 main 替代。
- 只读 detached worktree：`/home/dev/gdds-s3-review-67804647`，已准备既有 `legacy` 链接。静态读取源码、Contract、设计、决议、tag 注释和已有审核/交接记录；没有运行测试、编译、lint、容器、真实旅程或性能测量，没有连接或占用测试节点。
- 区间内的 `3503edf454`、`80e74d116c`、`5d9677b7b7`、`2c099a7c40`、`e8c45eb642` 为并行文档工作，不混入本轮变更结论。没有复核其远端测量原件。
- 已核 AGENTS、testing-conventions、比例化政策、Rust policy、P6 design/execution、相关 DC，及 S2b E 最终结论/tag、BE-a/d 联合退出末节与 FE3b 当前核对/交接文字。本报告只编辑并提交自己的报告路径；设计者同时进行的未提交修订不纳入本轮候选。

## 2. 阻塞 findings

### F1 — P1：单表预算异常后的 pair 计数被写成另一种行为

**位置：** `p6-s3-design.md:172`，以及 §5/§9.2 对保持原风险上限与降级行为的承诺。风险等级为现有派生风险结果的语义正确性；不涉及新信任域或恢复机制。

**源码证据：** `capabilities/risk_evaluation/_engine.py:145–158` 只有正常 `_evaluate_table` 返回后才执行 `total_annotations += len(outcome.annotations)`。`except _TableBudgetExceeded` 追加 `_degraded_table(...)`，不递增该计数。相反，诊断超限在 `_evaluate_table:202–207` 直接返回 degraded outcome，经正常返回分支计数。两条路径不能合并。`_degraded_table:581–608` 确实生成一个标注，但“有一个标注”不等于“原实现将其计入 pair cap”。

候选明确写“单表超限……并计入后续 pair 总数”，与上述控制流相反。`emit:214–222` 的上限先于等级过滤、同时触界 pair 优先等描述则与代码一致。

**具体场景：** 固定非超时、全部等级可见，table cap=2、pair cap=3；A 表产生三个 Emit，B 表两个，C 表一个。现实现 A 在第三项触发 table-budget 异常，输出一条 degraded，但累计仍为 0；B 后累计 2；C 的唯一项成功，最终保留这些 outcome。按候选文字把 A 的 degraded 计数后，B 后累计 3，C 的第一项触发 pair 超限，`_build_pair_degraded_without_annotations` 丢弃全部部分标注。结果、风险摘要、闭包及后续 surface digest 均可能改变。

**最小修复：** 写明正常返回与 `_TableBudgetExceeded` 异常分支的区别，逐分支保留当前计数和降级语义；同样涵盖 table wall-time 异常。A 节增加上述三表独立预期，以及诊断预检正常返回 degraded 的对照向量。若认为现实现应该修复，则须作为明确语义变更交 Owner，不能借 S3 实现替换暗改冻结基准。本报告推荐保留现行为。

### F2 — P2：跨表去重示例与完整身份冲突，FULL 变化任务命中没有源码依据

**位置：** `p6-s3-design.md:99` 的“相同任务在多个 pair 重复才是可靠命中场景”，与 `p6-design.md:525` 无条件写“两张同内容表 t1、t2……kernel=1（去重后）”。新增 Comparison Contract 同时要求保留 schema 内已有表名身份。

**源码证据：** `snapshot_materialization/contracts.py:575–596` 的 `business_schema_digest_of` 将 canonical table name 放进摘要；`snapshot_materialization/_digest.py:100–109` 的 compare schema 也包含 canonical table。因此即使行内容和变更相同，t1/t2 不能满足本候选的完整 key。Preview FULL 在 `application/preview_jobs.py:1900–1911` 构造相邻 `baseline→initial`、`initial→modified`；History 在 `application/history/compare_jobs.py:888–891` 同样构造相邻节点 pair。对同名表，有向两侧完整身份要同时相等，通常要求 baseline=initial=modified；这不是一个可保证节省行比较的变化任务。

**影响：** 实施者无法同时满足“完整 schema 身份不得删字段”和旧示例固定一次 kernel 调用；据此建立计数断言会错判，或诱使实现削弱 key。也不能把原始 SQL 的同内容组估计直接报告成 S3 真实比较收益。

**最小修复：** 同步总设计例子与详细设计：只有完整任务 key 相同才复用；含表名 schema 的跨表例子保持 miss、kernel=2。不承诺正常 FULL 的变化任务存在命中；报告实际 hit/miss，零命中仍须正确。人工构造同 key 重复任务可证明复用机制，不能冒充生产收益。若未变化 ordered 单侧摘要确有相同输入/策略，可独立说明其任务 key 和复用范围。禁止为提升命中率静默重定义 schema/content 身份。若要坚持跨表 10–20% 的收益承诺，须另向 Owner 提出范围选择；本轮推荐保守完整身份方案，无需新建 nameless digest 协议。

## 3. 其余核查与实施约束

| 核查面 | 静态结论与依据 |
| --- | --- |
| standard/keyless/ordered | 三者共用编码/投影/预算的边界合理；现 Rust `comparison/mod.rs` 仅导出 ordered 原型，不能算 standard/keyless 已交付。Python `standard.py:611–698` 的 multiset occurrence、`row_encoding.py:315–348` 的身份及字段编码，与候选描述一致。`ordered.py:738–840,890–956` 的空白锚、LIS 并列与两种排序不能被统一排序替代。 |
| 三族 schema 与产物 | `comparison/artifacts.py:644–730` 的列序、nullable、Scalar struct/list、metadata 与设计相符；`:745–814` 在产物视图裁剪 detail；`:868–889` 使用 FULL 行作排序并构造独立 records JCS envelope。保持 1024 writer 分组、raw/content 分层及不能更新 golden 掩盖差异是必要约束。Rust `records.rs:34–89` 目前复制 raw、收集全量 JSON rows，确需替换，现原型不是有界 validator。 |
| facts JCS 与生命周期 | `row_encoding.py:585` 起的 table/record/ordered/blank payload 与 `standard.py:756` 起的 core/envelope 支持 §9.1 的三视图区分。Blank facts 的 entity_key_kind 不在公共 BLANK Parquet 列中；保留内部额外字段正确。core 直接包含 table payload，不能拼 table hash；summary 在 tables 前，保留有预算当前 pair 的 records 后重放是可行设计。此处没有声称 O(batch) 总驻留。 |
| 风险重放 | 保留被过滤 Emit、惰性迭代、完整成功才缓存、每次执行当前时间/取消检查，解决了直接缓存最终标注会改变 pair cap 的问题；仍须修 F1。命中必须重放原位置的验证步骤：`_engine.py:352–380` 的 closure 验证依赖当前 comparison/facts digest 与表绑定，不能把上次验证成功缓存成当前成功。诊断预检直接返回 degraded 也不能丢失。建议显式描述控制步骤或每次执行的验证，并加入“首次有效，命中时 closure 缺失/错 digest”的向量。 |
| 读取与 READY | 删除新写全份回读有 DC54 授权；put/flush/close、raw 身份、manifest/closure 与 READY 屏障须保留。应精确区分真实 consumer：`comparison/artifacts.py` 的 open/read/restore 执行 schema/count/content 校验；`benchmarks/bundle_tar.py` 确实调用 open，read 当前主要由测试消费。`bundle_assembly/_assembly.py:356–358` 校验成员 raw/ref，`surface_assembly/_assembly.py:216` 起校验风险文档，并未调用 records 全量 JCS validator。总设计关于 bundle 读取的概括需收窄；不以修文档为由强制每次下载新增整份 records 解码。 |
| 去重与预算 | §9.3 只保留已知后续用途、预算不足安全 miss、必要工作前可驱逐可重算缓存，避免缓存挤占导致新资源失败。`table_access/kernel.py` 已有共享 backing 预约，`table_access/native.py`/`snapshot_materialization/arrow.py` 已有 reader 生命周期；输出 Arc、索引、JCS、writer、风险和 FULL 驻留仍需实现前预约并在最后消费者释放。现 `pair_pipeline.py` 的整 operation Python envelope 应按设计替换，不能只改标签。N1/32–8–M24 不变。 |
| 删除与独立 consumer | DC78 清单可执行，前提是 A 确认所有 `.records`/extension/helper consumer。`comparison/replacement.py` 仍用小型 table payload helper；`risk_evaluation/_facts.py` 的 has_visible_change、_risk_scope、_ordered_unsupported 也直接读 records，不能只改 `_engine`。Submit 的 `infrastructure/repository_write/import_publication.py:271,300` 调用 mutation planner/render，属于独立 S4 consumer，不能随比较实现删除。 |
| FE/S4/S5/基准 | HTTP、tar、三族产物与 surface/bundle digest 冻结，FE3b 独立；不把 BE-a/d 或 S2b 技术 GO 当 S3 启动。S4 SQL/存储 diff、S5 持久缓存/History 回填没有混入。原基准资源不触碰，旧 t4 不能证明新比较算法。 |
| A–E/验证 | A 先固定语义与预期，B/C 后 D 接线，E 删除后集中验收；focused 与权威门禁分开，来源 V/H、同节点同 worktree carried、runner 失败停止、缓存离线与节点职责均明确。W3/W4/FULL/100% 压力在 S3 起测，S6 正式取证，统计和 N/M 口径明确；W2 不冒认行比较收益。没有发现要求新增恢复/安全平台的依据。 |

上表是设计静态可行性判断，不是实现 PASS。A 节的 consumer 清单和独立向量仍是待交付物，不因本表列出示例而视为已完成。

## 4. 证据边界与下一步

S2b `p6-s2b-exit` 注释明确实际 V=`a6876d560050285321fd9f62942d590a03f35d64`、最终 H=`3580e6649f4b0819156f7f560670b3deee237f42`、独审 `9220f3cdecba7df3e50fec00d77d1dd9efb0f678`；本轮仅核已有记录，不重签其远端证据。BE-a/d 最新联合退出记录已完成，不能复用历史 pending 文字阻塞 kickoff。

本轮容器记录：current HEAD=`67804647935ce3c1b215c25312e7a0c1ca8655f8`；rebuild required=no（仅设计/Contract 文档与只读审核）；current container gate=`not-applicable`（本轮设计审核）。最后已有验证产品来源为 BE-a/d `49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`、source tree=`56720104af34a1eb677336f57bdbc07444a56615`，引用其既有退出记录；没有对本候选执行 carried，不声称当前 HEAD 容器 PASS。S3 产品 Rust/FFI 接入及阶段最终候选按既定规则在 04 实际构建/验证，不能沿用本报告替代。

残余未知包括：真实 W3/W4/FULL/压力资源与耗时、1024 分组后的 Parquet raw 字节一致性、实际命中率、当前 pair 的最大 Arrow 驻留与风险候选费用、最终 DC33 范围及 CT108 可用安排。它们应由 A–E 及阶段退出证据解决；目前无实测，不预写通过。

请设计者修订 F1/F2、澄清上表已指出的 consumer/重放边界后提交新固定候选；独审只复核该固定增量及其影响。只有完成复审才可给 `READY_FOR_OWNER`；最终范围与实施启动仍由 Owner 决定。本报告不授权产品改动、推送或 tag。

## 5. 固定 d49bb126 复审

2026-11-07；本轮结论：**READY_FOR_OWNER**。首轮对 `6780464793` 的 `CHANGES_REQUIRED` 保持历史原文；本结论仅针对修订候选 **`d49bb126b664af4b09097aee1a6f0b1bf58c9496`** 的 S3 设计与 kickoff。无剩余阻塞 finding，不等于产品实施启动、代码通过、性能达标或阶段退出。

复审在新 detached worktree `/home/dev/gdds-s3-review-d49bb126` 进行，固定候选 clean，`legacy` 链接已准备。实际修订只有 d49bb126 的四个文档：Risk Contract、P6 总设计、S3 详细设计、S3 kickoff；`vnext/` tree 仍为 `56720104af34a1eb677336f57bdbc07444a56615`。两候选之间另有本人首轮报告 `1a62eeff44` 和并行基准文档 `78d737abac`，后者不混入复审结论。没有测试、编译、lint、容器、远端或基准资源操作。

| 首轮项 | 独立复核与处置 |
| --- | --- |
| F1/P1 | **关闭。** S3 §9.2 与 Risk Contract 明确 `_TableBudgetExceeded`（含 table wall-time）异常只追加 degraded、不累加 total；诊断预检的正常返回则累加。重新核 `_engine.py:145–158,202–207,214–238`，文字与控制流一致。kickoff §7.1 的 table cap2/pair cap3、A3/B2/C1 向量及诊断预检对照，按源码手工追踪分别得到 A 后0/B后2/C后3与A后1/B后3/C触发pair降级；没有执行该向量，不记测试 PASS。 |
| F2/P2 | **关闭。** 总设计 §16.2 现给含表名 schema 的 t1/t2 两次 kernel；S3 §5 明确相邻 FULL 变化任务不保证重复、真实0命中合法、不得套用原10–20%收益。复核 Preview 的 baseline→initial/initial→modified 与 History 的相邻 pair，限制正确。人工重复 key 仅证明机制；单侧 ordered 摘要使用独立 task_kind，不能计作行比较收益。完整 schema/scope 身份没有削弱。 |
| closure 命中与直接 degraded 分支 | **澄清完成。** §9.2 要求序列包含 `CheckRecordsClosure` 等原位置控制步骤，每次按当前 pair 的 comparison/facts digest 与 table 绑定验证；不能复用旧验证结论。诊断预检每次先执行，过滤 Emit 保留。对照 `_engine.py:334–380`，这没有将 closure 检查提前到原上限分支之外，亦未把检查从命中路径删除。 |
| §9.4 consumer 与读取边界 | **澄清完成。** 全 src/benchmark/Rust 符号检索确认 `benchmarks/bundle_tar.py:97` 调用完整 records validator；`read_records_artifact` 未见其他生产业务 consumer，旧 Rust reader 仅自身向量调用及公开导出。replacement 保留无 records 的独立 envelope；surface 使用小 facts/closure entries；bundle 自有 raw/ref 校验没有冒称 records 内容校验。新增文字不要求每次下载整份解码，也未添加 S5 缓存路径。实际 adapter 测试仍是后续交付条件。 |

潜在回归复核：本增量没有改变 §9.1 的完整 facts JCS payload/summary 前序约束、三族产物 schema/raw golden、§9.3 的有预算保留与安全 miss、N1/32–8–M24、DC78 删除边界或 A–E 授权次序。增加 task_kind 是区分现有行比较与单侧摘要的内部 key 条件，不是新增持久协议或更改业务 digest。没有发现新的实质矛盾。

本轮容器记录：current HEAD=`d49bb126b664af4b09097aee1a6f0b1bf58c9496`；rebuild required=no（仅四个文档修订）；current container gate=`not-applicable`（kickoff 设计复审）。最后已有验证产品/source-tree 仍按 §4 的 BE-a/d 来源引用；本轮没有执行 carried，也没有宣称当前文档候选容器 PASS。产品接入与最终门禁仍在授权后的实施阶段办理。

剩余工作是 Owner 确认实施范围及启动，再由 A–E 交付独立向量、完整 consumer/API 移交、实现与实际验证。§4 所列真实性能、raw 字节、命中率、最大驻留、最终 DC33 范围与节点安排仍未知；此次复审没有把这些未知改记通过。当前不需要为关闭本轮 findings 再增加 nameless 身份、缓存框架或恢复机制。
