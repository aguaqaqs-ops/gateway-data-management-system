# Preview 热点归因与业务表专用并行设计

2026-11-13，设计稿，待独立技术审核。本文只完成源码分析和后续试验设计；未实现、未新增计时、未运行测试、未部署、未更改 N/M。方向来源见[业务表并行笔记](preview-business-parallelism-notes.md)。

## 1. 身份、证据与结论

分析对象固定为 `1ed28d1aacf98742d21f758018996453ef8128f4`。目标临时分支 `gw08-dual-env` 的 `852a735cb6` 只增加方向笔记，`1ed28d1..852a735cb6` 产品源码、依赖和配置均无差异；本文源码链接的行号对应该固定源码，不引用 main 的后续实现。文档待协调者提交，不推送。

证据入口为仓库外 `/home/dev/gdds-stage-exchange/gw08-preview-baseline-sol/REPORT.md`，原件为同目录 `mo/`、`full/` 的 `result.json`、`executions.json`、`containers.log` 及 `postflight.json`。这是 05 的普通 t4、已绑定当前 Rust 扩展的诊断基线。08 原扩展 `__build_input__` 为空，05 已重建绑定；不能称为 08 实际延迟。资源固定为 worker 2 CPU / 32 GiB、reserve 8 GiB、N1/M24 GiB、单 active；05 宿主硬件与 08 不等价。

**建议顺序：先以最小补充计时分开 materialize、checkpoint 恢复和 bundle 内部成本，再试验同次 bundle 执行内的读取/解码复用；业务表并行优先设计为 canonical IPC 或导出的单一阶段，只有对应热点被证实且资源档获准才实施。** comparison 本次占比较小，跨 pair 或整个 pipeline 并行不作为首个试验。不能预先承诺提速，也不能把重复调用数换算成重复耗时。

本文使用四种证据标记：**实测**是上述单次样本；**源码**是固定源码可直接观察的路径；**推断**需计时或实现验证；**待核**尚无完整数据或证明。各行的“归属”表示被哪个父窗口包含，不表示可以与子计时相加。

| 顶层窗口/指标 | MO 空 INITIAL → v1 | FULL 空 baseline、v1 → v2 | 证据与解释 |
| --- | ---: | ---: | --- |
| 受理至匹配结果可读 | 138.567 s | 226.154 s | 实测；各一次，0.5 s 轮询，未测浏览器 |
| materialize_inputs | 36.045 s | 61.664 s | 实测；包含 staging、解析、业务物化、规范投影/持久化、checkpoint |
| assemble_preview | 94.909 s | 155.216 s | 实测；包含恢复上一步、pair pipeline、bundle、ready/checkpoint |
| publish_preview | 6.504 s | 8.043 s | 实测；包含 checkpoint/state/closure 读取、核对及事务发布 |
| 非 step 时间 | 1.109 s | 1.231 s | 实测差值；不能视为 CPU 工作或优化上限 |
| parse / materialize hooks | 0.883 / 30.872 s | 1.690 / 51.667 s | 实测嵌套/累计 hook，不是顶层分区 |
| compare / risk / export / bundle | 2.772 / 21.703 / 15.967 / 39.741 s | 12.385 / 22.921 / 23.520 / 46.962 s | 实测嵌套；risk 含提取/规则/产物，export 不等于纯编码 |

三 step 合计 137.458 / 224.923 s；首 claim 与 step 间等待不是主要热点。旧 56/81 s 的输入 baseline、源码/存储/资源不同，不能据此判回退；2×t4 不是本输入。FULL 不能简单当成 MO 两倍：有两 pair，第二 pair SAME_PROJECT/DETAILED，含 operation 内复用，且两组未清 OS/page cache。

统计 quality 为 partial/counter_unavailable，observed_outcome unknown、revision 为空；成功与源码身份来自独立 operation/result 和结束 HEAD/扩展核对。resources 查询缺 step_id/attempt_count 得到 422，当前不具备完整资源曲线或无 OOM 的独立取证结论。原始限制继续有效。

## 2. 热点调用链与阶段归属

| 窗口 | 固定源码路径 | 已知与尚未解释的边界 |
| --- | --- | --- |
| materialize 输入准备 | [handler:621](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L621) → [_materialize_all_sides:1136](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L1136) | 源码：FULL 按 INITIAL、MODIFIED 顺序物化；再按 changed canonical tables 取得 baseline，不是三个整侧无条件重做。 |
| 上传侧 | [_materialize_uploaded_side:1539](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L1539) → [stage_operation_source:90](../../vnext/backend/src/gateway_backend/application/kernel_execution.py#L90) → parse_arrow_sql → [materialize_business_snapshot:102](../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/compose.py#L102) → [规范投影:30](../../vnext/backend/src/gateway_backend/capabilities/storage_projection/arrow.py#L30) → [materialize_canonical_snapshot:129](../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/materialize.py#L129) | 源码：压缩包及 SQL/XML bytes 有预算生命周期；业务物化包含 catalog/composite，不能把每张源表孤立并行后跳过依赖。实测 uploaded projection MO 2.503 s、FULL 2.482+2.484 s；materialize hook 余下成本未拆开。 |
| canonical 表持久化 | [publish_canonical_tables:491](../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/artifact.py#L491) → [CanonicalTableStore](../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/canonical_store.py) | 源码：逐表 lookup；命中仍 open/inspect，miss 编码 IPC；再写 manifest。输出 reader 在同次执行内复用已验证 Arrow，不立刻全量重新打开持久 IPC。这是已有优化，不能再次把它算成待消除开销。 |
| materialize 尾部 | [handler:699](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L699) → serialize sides → state artifact → prepare_step_checkpoint → [pinned_checkpoint_builder:25](../../vnext/backend/src/gateway_backend/application/job_steps.py#L25) | 源码：canonical JSON 状态、envelope、refs 与保护一并发布；现成 materialize hook 不覆盖该段全部成本，具体秒数待核。 |
| assemble 起始恢复 | [handler:781](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L781) → [_materialized_preview_inputs_from_checkpoint:2748](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L2748) → [_bound_from_side_document:2949](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L2949) | 源码：即使是正常 successor，也从 durable checkpoint 恢复每侧表 artifact，核 closure、manifest、storage facts、state digest 和 configuration；MO initial 明确复用 baseline。此段属于 assemble，不属于原 materialize step；不能把所有 assemble 残差归给 records。 |
| pair 计划/身份 | [_assemble_preview:1964](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L1964) → declare_pair_comparison_session → [_run_pair_pipeline:2148](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L2148) | 源码：pair 当前顺序执行；声明 dedup request 时做身份评估，run_preview_pair_pipeline 又评估并发布 identity artifact。同输入的纯评估可能复用，但尚未计时，预计不是当前首要判断依据。 |
| comparison → records | [pair_pipeline:308](../../vnext/backend/src/gateway_backend/application/pair_pipeline.py#L308) → plan_comparison → [compare_plan_native:1016](../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L1016) → [records 发布:406](../../vnext/backend/src/gateway_backend/application/pair_pipeline.py#L406) | 源码：compare、seal、records publication 分属不同边界；有 operation 本地与 persistent 去重、native handle 生命周期。实测 compare 2.772/12.385 s 不等于全部 records/Arrow 转换耗时。 |
| risk / export / presentation / surface | [pair_pipeline:428](../../vnext/backend/src/gateway_backend/application/pair_pipeline.py#L428) → [evaluate_risk:239](../../vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_engine.py#L239) → [_surface_table_artifacts:528](../../vnext/backend/src/gateway_backend/application/pair_pipeline.py#L528) → [export_snapshot_table_parquet:122](../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/client_parquet.py#L122) → publish_business_presentation → assemble_surface | 源码：risk 含 extraction、规则、annotations/report/closure 发布；export 包括命中验证、转换、排序、压缩、scratch、hash/put；presentation/locator 另有工作。不能把 risk21.7 s 全叫规则 CPU，也不能把 export16 s 全叫磁盘 I/O。 |
| bundle | [assemble 调用:2090](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L2090) → [assemble_operation_bundle:167](../../vnext/backend/src/gateway_backend/application/kernel_execution.py#L167) → [assemble_bundle:94](../../vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py#L94) | 实测 39.741/46.962 s；源码：surface artifacts 验证、source refs 规划/JSON 改写、surface 改写、manifest/closure 序列化、put+回读、validate_bundle；尚无内部互斥分段秒数。 |
| assemble 尾部 | [handler:863](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L863) → prepare_ready_closure → assemble-state artifact → checkpoint/pin | 源码：ready closure 先 verify 全 refs，再 JCS/build/put；属于 assemble，bundle hook 结束后仍有工作。 |
| publish | [handler:927](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L927) → load checkpoint/state → load_ready_closure → build result → [_atomic_publish_preview:1016](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L1016) | 源码：再次 refresh_control/cancel，然后第二次 load_ready_closure，最后 lease publish_operation；builder 内检查 workspace/head 漂移、指针/保护迁移、终局 CAS。实测 6.504/8.043 s 不是数据库事务的已测耗时。 |

现有 `@timed` 直接把调用时长累计到 stage，见 [metrics:48](../../vnext/backend/src/gateway_backend/statistics/metrics.py#L48)；业务 materialize 与其他调用可嵌套。多线程时这些累计时长更不能当 operation wall time，后续设计必须同时保留父窗口和各任务 wall time。

## 3. 重复读取、序列化与校验：复用界线

### 3.1 已观察路径

| 候选 | 源码事实 | 可复用的最小范围；保留保障 |
| --- | --- | --- |
| bundle source 读/验 | [_plan_artifacts:559](../../vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py#L559) 先 locate，再 `_verify_store_bytes` hash raw、再次 locate/字节比较；JSON 另 decode、canonicalize 对照、rewrite、再次 canonicalize | 同次规划已经按完整 ArtifactRef 去重。可研究让一次经过 exact-ref/size/raw SHA 校验的读取同时服务 JSON 解码及依赖提取；不同 ref 的同名 ID不能复用。JSON rewrite 后 raw 与 ref 会变，必须重新计算并校验。 |
| bundle final 读/验 | [写后回读:227](../../vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py#L227)，[validate_bundle:295](../../vnext/backend/src/gateway_backend/capabilities/bundle_assembly/_assembly.py#L295) 又读取 manifest/closure，每 entry locate 后调用同 helper 再 locate；surface 后续再 decode | 存在同次执行多遍读取/解码。计划阶段证明 source 有效、写后证明 target 有效、final 证明闭包整体可重放，职责不同。先区分每段 bytes/time，再合并同一阶段的 exact read；保留完整 final raw 验证、semantic/closure digest、嵌套 ref coverage、surface link 等核对。不能用内存生成成功替代落盘读回。 |
| publish ready closure | [handler:990](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L990) 与 [atomic helper:1079](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L1079) 各调用 [load_ready_closure:471](../../vnext/backend/src/gateway_backend/application/checkpoints.py#L471)，每次 decode 并 [verify_artifact_refs:331](../../vnext/backend/src/gateway_backend/application/checkpoints.py#L331) | 可能复用的是同一次 handler 已解码的 closure/document、精确 refs 和 binding 结论；是否可合并全 refs 再读要另证保护窗口。第二次前有 refresh_control/cancel，不把它当无条件冗余。恢复/重试必须重新读取并验证，不能继承前次执行内存信任。 |
| checkpoint 恢复 | [恢复函数:2748](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L2748) 打开各表及 manifest，再比较 canonical closure bytes、storage facts、state digest；[ArtifactReadHandle:133](../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/canonical_store.py#L133) 有映射/inspect/读者预算 | 恢复防 persisted 内容与 checkpoint 绑定不符，不因生产者刚成功便删。若单次恢复里相同精确 ref 多次打开，可研究复用已验证不可变 backing、保留独立 reader；先量清成本。跨 step 暂存活对象会改变当前生命周期，不列首个试验。 |
| export cache 命中 | [lookup:45](../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/client_parquet.py#L45) 读取缓存全 bytes 并验 footer/schema/行数/layout/repository；[surface table map:537](../../vnext/backend/src/gateway_backend/application/pair_pipeline.py#L537) 已允许完整 prevalidated exports | 命中不是零成本。可在同次 operation 用已有精确内容键复用 export ref/已验证 metadata；不同 pair 的表名、展示名不等于同内容。不能跳布局、writer-version、repository、行数核对，也不永久缓存 bundle/surface。普通详细 pair 的 surface closure 主要使用已发布 refs，不据 replacement/include_all 的特殊路径断言本次又导出一遍。 |
| identity 评估 | [dedup request:2028](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L2028) 与 [pair:183](../../vnext/backend/src/gateway_backend/application/pair_pipeline.py#L183) 对同 pair 做 assessment | 可传递同输入、同 before_table_set 的不可变 assessment，pair 仍负责发布/绑定；这是独立小优化候选，耗时未知，不据调用次数安排优先级。 |

[LocalArtifactStore.locate:389](../../vnext/backend/src/gateway_backend/infrastructure/artifact_store/local_store.py#L389) 经 `read_exact` 已核 stored exact ref、安全普通文件、size/raw SHA；`_verify_store_bytes:786` 又显式 hash 和再次 locate。重复 raw hash/文件读取是源码事实，是否主导 wall time仍是推断。port 与所有生产/测试实现的保证须先对照，不能只针对 Local 实现把 capability 的完整性职责悄悄删掉。

### 3.2 同次执行复用的信任范围

1. 只以完整 ArtifactRef（ID、media type、size、raw SHA）及当前 store/scope 为键；不新增只算不核对的 digest、版本或持久状态。引用改写后的 ref 为新对象，不能继承 source 的验证结论。
2. 复用范围最多是一个同步 capability 调用，或一个已证明连续保护的 handler 成功路径；不跨 lease、claim、恢复、worker 重启、operation 或下载请求。公开下载仍执行其 owning Contract 的独立预检。
3. [checkpoint pin builder](../../vnext/backend/src/gateway_backend/application/job_steps.py#L25) 在 checkpoint CAS 同一事务登记 extra refs；assemble 包括 ready closure 与完整 ready refs。publish 必须在 lease 仍有效时，将保护原子迁到 `current-preview` 并释放 step owner，见 [_persist_preview_business_state:1083](../../vnext/backend/src/gateway_backend/application/preview_jobs.py#L1083)。pin 保留对象，不证明对象从未损坏；refresh/cancel/drift/lease 判断仍在现位置执行。
4. 若要把两个“当前可读”核对合成一次，必须证明该窗口内 cooperative cleanup/repair 不会移除或替换对象。现有 [read_session port](../../vnext/backend/src/gateway_backend/artifacts/store.py#L71) 和[本机实现:51](../../vnext/backend/src/gateway_backend/infrastructure/artifact_store/local_store.py#L51) 对 cleanup 持共享借用；[bundle Contract](contracts/comparison-bundle.md) 说明 root SH/cleanup EX 的协作边界。可按现有有序 root 借用规则包住一个短调用，不把借用扩成跨 step/长期持有。调用所用 port 是否具有该能力、嵌套读/写与 canonical repair 的锁序，须实现前核对；不能假设一个 Protocol 自动拥有它。
5. read session 只证明协作清理排他，不承诺硬件/外部破坏不发生。持久边界仍做落盘完整 raw 校验，首次读发现缺失/损坏仍 fail closed；不把过去验证缓存当作永远可读证据。若 owning Contract 要求两个不同时点的独立可读性，就保留两次读取，只复用 decode/metadata。
6. 所有复用 bytes/AST/refs 都计入 M。bundle 已有 [publication staging 预约:167](../../vnext/backend/src/gateway_backend/application/kernel_execution.py#L167)；优先复用其已持有 bytes，避免再保留一份 raw 或把内存扩大换取表面提速。失败/取消/异常必须释放调用内 memo/read session，不能进入下一次 attempt。

因此“publish 两次调用”目前是待核优化点，不是已证可删除 finding。首轮不跨 step 复用 materialized readers，不改 control DB/schema、checkpoint 形状、HTTP DTO、digest 或发布事务。

## 4. 最小补充计时计划（仅设计）

**首轮只测A的两个已有调用点及父bundle窗口**：`_plan_artifacts` 中 `locate → _verify_store_bytes`，以及 `validate_bundle` 中每entry的相同组合。保留现有bundle elapsed；两处分别记录 locate次数/字节/elapsed、unique refs、显式hash字节/elapsed，按JSON/binary聚合。子计时含在父窗口内，不相加；一次locate内部hash也是其子项。该轮只决定重复读/验是否值得优化，不要求全链路插桩。

将来获准后，用固定新提交、原输入摘要、05同条件新仓库/空INITIAL、原N1/M24和离线绑定扩展，先做MO一份普通t4；只在修改两pair共享时补FULL。不要提前扩2×t4或参数矩阵。每阶段结束输出一条有界汇总，使用monotonic elapsed和既有operation/step/attempt归属；不逐行日志、不改统计API、不记录业务行或凭据。使用现有资源接口时带正确step_id/attempt_count，资源不可用继续报告限制。

若首轮显示A贡献不足，再按证据**择一**启用下列计时组；这是后续定位菜单，不是首轮必做清单：

| 条件 | 下一组最小边界 | 计数 |
| --- | --- | --- |
| materialize仍主导 | business SQL/catalog/composite、projection、canonical lookup+inspect/encode+put、checkpoint尾部 | side、resolved family、真实rows、Arrow/IPC bytes、命中；先聚合，再只看最慢候选类型的少量表 |
| assemble非bundle残差显著 | checkpoint/state恢复、table open/inspect、canonical closure/manifest/facts binding、ready/checkpoint尾部 | unique/总refs、bytes、正常successor/resume；恢复与原物化step分开 |
| pair产物主导 | records publication、risk已有extraction/rules/publication入口、export命中验证/编码/put、presentation/locator/surface | pair、已产生的changed_rows、refs/bytes；不重计现有hook |
| bundle首轮不足以解释39.7/47s | JSON decode/rewrite/JCS、put、写后readback、final semantic/closure验证 | JSON/binary bytes及calls；在递归入口统一归属 |
| publish需定位 | envelope/state；两次closure各自read/decode/ref verify；refresh/cancel；事务head/pin/CAS | 两次closure编号、unique refs/bytes、终局；不把6.5/8s全认作DB耗时 |

父段独占时间只能扣除互斥子段；多通道时同时报告operation wall、每任务wall与并发峰值，累计task seconds不等于端到端时间。新增观测的成本要记录。性能结论另按选中输入/资源档做成对重复并报告散布/缓存状态，不能用本轮单样本直接定新代码提升。

## 5. 业务表分类与真实数量边界

分类使用现有规则解析结果，不创建平行的业务规则注册表。`resolve_table_rule` 的优先级、static role、key/ordered policy 和实际 schema 一起决定可用专用路径，见 [resolver:45](../../vnext/backend/src/gateway_backend/capabilities/table_rules/resolver.py#L45)、[registry](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py)。名字只用于命中既有 selector；不据“像某种表”新造业务语义。

| 已有语义组 | 确认依据 | 并行注意事项 |
| --- | --- | --- |
| 九类 IEC104 ORDERED_DIFF 实例 | [registry:107](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py#L107)：`iec104_{syx,dyx,yc,syk,dyk,yt,ym,sc,yp}_list`，完整 selector `^b\d+_n\d+_<family>$`；[ordered record:227](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py#L227) 绑定 GID_NO_V1、gid stable key、no position | 同一类型的不同 b/n 实例可枚举；整表 comparison 的 gid/no、blank/move/LIS及风险语义不能按任意行区间拆开。各 family 的列/行宽仍各自测量。 |
| 装置测点 STANDARD 精确组 | [DEVICE_POINT_UPDATE_ONLY:83](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py#L83)：device_st/mx/co/sg/sp/cnt/sn/tap/other/disturb；[规则:269](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py#L269) gid 与 UPDATE_ONLY | 已知语义组，不表示全部是本输入大表；受 composite catalog 下游依赖，不直接把 source/business compose全拆为独立 pipeline。 |
| device_cfg、协议 option/device cfg、普通精确表 | [registry:244](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py#L244) 与 resolver | 各自 key/忽略列/作用域不同；metadata确认后可复用通用正确路径，第一版不为它们一律开启专用通道。 |
| composite_signal_point 与普通 device浏览 | [registry:96](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py#L96)、[compose:102](../../vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/compose.py#L102)、[bundle Contract](contracts/comparison-bundle.md) | composite依赖源表/catalog/XML；presentation与locator有两侧行序绑定。先保留原依赖屏障，不凭表数量多就并发其生成。 |
| SKIP / SNAPSHOT_ONLY / BROWSE_ONLY / raw PK fallback | [registry:30](../../vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py#L30) 与优先级表 | 按 owning规则保留其行为；未命中专用类型仍走既有路径。不能为了并行改变 skipped/浏览/比较范围。 |

**实测范围**：当前侧 MO 312 表/246,794 行，FULL 312 表/246,874 行，最大表54,150行。`pair_table` 收集有100条和10 KiB双上限，见 [metrics:110](../../vnext/backend/src/gateway_backend/statistics/metrics.py#L110)；[序列化总预算](../../vnext/backend/src/gateway_backend/infrastructure/statistics/collection.py#L62)还可进一步截断。现有两个 `executions.json` 的可见 `metrics.tables` 各只有43条，MO总312/FULL总624条，不能用它完整排名。可见 `b1_n11_iec104_syx_list`、n12、n13各9,822行，只证明这些实例存在；不证明它们是全部大表或54,150行最大表所属类型。FULL保留条目偏向第一pair，不能推断第二pair的变化分布。

**实施前待核**：从本次已产生的 parsed/summary/manifest（若现有保留制品可读）或获准最小计时运行的 metadata，一次枚举每侧完整实例清单；按 resolved family列出数量、真实 rows、schema/columns、Arrow/IPC/export字节、pair变化行与阶段成本。当前证据未包含该完整清单，不擅自到08或05读业务根来补证。无需为盘点重解析SQL；总行数来自真实 descriptor/metadata，不来自最大主键、GID、文件行号或当前处理游标。进度 `processed_rows/total_rows` 仅用于同任务估剩余，不替代总数。

## 6. operation 内少量专用执行通道

### 6.1 第一版边界与依赖

第一版只选一个已测热点 capability 和一个确认成本集中的业务类型，不同时重构所有阶段。预处理时依据同一 ruleset 动态列出实例，不硬编码设备实例数；表数只改变有限待处理列表。沿用现有共享 N 原生 pool，不建设跨 operation队列、独立服务、持久task表或另一个通用线程池。

```text
staging/parse → source descriptors + owned Arrow
             → SQL business tables → catalog/XML/composite屏障
             → canonical projection → canonical IPC表任务 → ordered snapshot/manifest
checkpoint/pin → restore/binding验证
             → pair plan → per-table comparison → records seal/publication
             → risk + table exports → presentation/locator → surface
             → bundle dependency rewrite → final raw/closure验证 → ready checkpoint
             → fresh control/head checks → atomic publish/protection迁移
```

两条可选落点：

- **canonical IPC专用表任务**：同侧 projection已成功后，以一张完整规范表的 owned Arrow输入、descriptor及既有canonical key为边界；lookup/命中验证和注册由串行owner处理。miss的IPC编码、hash等纯计算在受限通道中完成，返回有界IPC bytes/ref候选；owner按既有store/pin流程落盘并组manifest。所有表完成且诊断归并后再建snapshot；不把projection/business compose的跨表规则移入任务。若编码不是实际主成本则不选它。
- **单侧 client export专用表任务**：每个唯一layout/repository/writer-key至多一个生产者，输入独立reopen reader；任务覆盖该完整表的no排序/转换/Parquet写入scratch，完成后owner登记export cache并按表序建surface。沿用当前cache精确键和共享别名。PyArrow/转换线程与GIL、scratch/store并发条件须先证明，不能把Python线程数直接当CPU通道数。

comparison、risk、records、presentation、bundle保持原阶段屏障。comparison当前多个table共享一个mutable native records operation及session；risk的pair annotation预算、规则顺序与降级输出跨表累计；bundle JSON有嵌套ref依赖。这些均不适合首轮“提交整张表pipeline到线程池”。未来若拓展，须分别给各 owner证明与测试，不能从本方案自动获得授权。

### 6.2 估重与完成补位

每个实例只携带已知的小型字段：规范表序index、family、side/pair、rows、available bytes、cache命中状态、估计工作和峰值预约。列表在进入该阶段前固定；同一完整内容键在operation内合并计算，但保留各逻辑表的绑定。

初始排序使用该类型真实工作量：物化/IPC用 `rows` 加已知Arrow bytes；比较若以后获准用 `before_rows + current_rows`；export用实际输出前可得的rows/Arrow bytes；records/risk只有比较完成后才可加 `changed_rows`。最初缺标定系数时，同类按rows降序、bytes次序、规范index打破平局；这只是估优先级，不能当峰值证明。不额外比较/解析以获得估重输入。

owner持有简单的排序列表和最多K个在途slot。通道空闲时，从列表选最大的**当前能通过内存准入**任务；不满足则看后续更小任务，完成即补位。若大任务因其他在途占用持续无法入场，停止新增小任务、等待当前任务释放后先运行它，避免尾部饿死。只有单任务且空闲预算仍不足时，才按原capability资源失败/降级语义处理，不能等待不存在的释放或扩大M。

第一版不逐行调参、不迁移在途任务。仅在表完成时，用同family的实际elapsed/rows/bytes及峰值修正尚未启动任务的估重；最小版本先固定系数也成立。较小表的固定开销明显时可串行小批处理，批内仍保留原表顺序，不让小表提交开销淹没节省。

### 6.3 CPU上限与嵌套并行

设获准产品计算并发为N，实际cgroup quota/cpuset可用容量为C，业务通道小上限为Ksmall。CPU执行slot上限为 `K ≤ min(Ksmall, N, C的保守整数容量, 任务数)`；C不足1时至少保留一个串行通道并受quota节流，不能向下取整成永不执行。Ksmall初次正式试验最多2个，且只是设计候选，不是当前配置变更。

**当前N1保持K=1**，worker2CPU也不自动给业务计算2核。N是计算上限，内存M与测试worker数各自独立。当前可研究减少重复工作；若计时证明I/O等待显著，可另设计一个有界I/O预取/写后验证重叠，但CPU/hash/JCS/压缩都计入同一个N，不能给“I/O通道”偷放计算线程。本稿不启用该重叠。

[PyO3进程pool:150](../../vnext/rust/gateway-compute-python/src/lib.rs#L150) 初始化后固定线程数，并拒绝请求不同N；[canonical IPC:1776](../../vnext/rust/gateway-compute-core/src/canonical_ipc.rs#L1776) 已在同pool按列并行。后续表间任务必须使用这一个有界pool，表内按列任务也回到同pool，不为每表创建N线程、操作中重配pool或fork子进程。需要从列并行转为表优先时，只在该专用native入口内改变工作提交顺序。PyArrow/Parquet或第三方内部线程须纳入C/N核对；若不能限制，先保留串行，不通过环境全局改配置来声称满足预算。

### 6.4 内存准入、所有权与数据访问

保持worker envelope32 GiB、reserve8 GiB、M24 GiB。行宽、变长payload、排序/索引、两侧输入、输出重写与records放大分别计量，不以字段数相近假定行宽相同。

令 `L` 为当前实际保留并已预约的共享输入/metadata/cache/output，`E_i` 为任务i的新增峰值（独立reader/batch、sort/index、codec/writer scratch、native输出、写入overlap），`G` 为本阶段owner合并/发布空间。只有 `L + ΣE_inflight + E_new + G ≤ M` 才启动；与已用预算重叠的backing只计一次。E来自该capability已有保守上界并在真实字节/最坏变长字段上标定，不用平均RSS代替。输出留存从任务预约移交owner，只释放临时部分；不能完成就释放全部、却仍保留输出对象。K受内存进一步下调。

当前 [OperationMemoryBudget/KernelExecutionContext](../../vnext/backend/src/gateway_backend/capabilities/table_access/kernel.py) 的dict/counter、ContextVar、ExitStack及lifetime没有提供线程安全子任务协议；[ComparisonTaskSession](../../vnext/backend/src/gateway_backend/capabilities/comparison/production.py#L141)同样可变。**不得直接copy_context后把同一context/budget/cache/reader/LeaseSession提交给多个Python线程，也不得给每个任务一份M。** GIL不能作为线程安全或CPU预算证明。

推荐所有预算、cache查写、control refresh、manifest/diagnostics合并和保护事务均由单一Python owner执行；专用native任务只拿已获准、独立的owned Arrow batches/不可变descriptor、任务硬上界和只读stop信号，不访问Python预算或DB/cache。现有独立reader可由owner串行reopen/取批；跨线程传输前由native/Arrow owning契约证明所有权，不能直接共享一个游标或仍借用的stream。

**B目前是条件性native专用接口设计，尚不具备可直接实施的生命周期证明。** 若选中B，需要一处窄的operation-local原生任务桥：owner准入并提交至既有N pool；完成项经有界出口交回owner，owner落盘/移交输出/释放临时预约后补位。出口容量不超过K，返回输出的预算在提交时已预约；出口满则不再派发，不累积所有表结果bytes。它只服务所选capability/业务类型，没有通用任务接口/持久状态机；需在后续实施设计审核明确Arrow所有权、submit/completion/close及有界出口协议后才能开工。若现有adapter无法证明安全传输或无法及时交还输出，先用K=1或小批串行交回，不以扩大framework解决；完成补位的桥接/生命周期设计须在实施审核中具体核收。

### 6.5 控制、失败与释放

owner维持原lease/control检查与续租。工作中沿现有native check点读取同一个只读cancel/drain/loss信号；不能从任务线程调用LeaseSession或共享DB transaction。取消、drain、lease lost和业务错误沿原 [cooperative stop映射](../../vnext/backend/src/gateway_backend/application/kernel_execution.py#L128)分类，不把drain伪造为用户cancel。

停止时先禁止补位并发stop；等待已启动native任务退出/交回借用，关闭reader/scratch/任务handles、归还预约，再由owner发布cancel/释放drain或上抛lease lost。旧lease未清空任务前不能返回让下个operation借到它的内存/句柄。不得在线程仍使用对象时close父ExitStack；关闭操作必须幂等。

普通单表可降级错误保留原语义，按原表序归并诊断/omitted_count；operation级资源错误、panic、损坏ref、control停止按既有级别终止。并发完成先后不能决定“第一个业务诊断”或pair预算耗尽位置。失败前已经持久化的派生产物不发布为READY，由原保护/TTL和scratch机制收尾；不新增整包清理，也不移除他人产物。

### 6.6 确定性合并与极端偏斜

每张表任务以既有规范index回填结果，不按完成顺序append。表/记录顺序、ordered gid/no/blank/move语义、comparison facts、risk规则/编号与annotation上限、locator最终导出行序、bundle logical_path/ref rewrite与closure排序均保持owning Contract。新增并发实现的纯调度顺序不进入digest；不为保旧digest删除完整性输入。

manifest timestamp/随机snapshot/artifact ID等本来非确定的字段按现有语义比较；同bytes应复用既有精确ref，若新ID导致JSON raw传递变化则解释该边界。确定性验证以规范payload/digest及引用绑定为准，不能笼统要求每次运行的所有opaque ID逐字相同。

表间并行的下界受最大任务支配：在资源允许且忽略开销时，阶段耗时也至少是 `max(最大任务耗时, 总CPU工作/N, 串行依赖路径)`；若只有一张超大表，调度无法让它变小。先保留它独占通道/内存并大表先行。后续表内优化必须针对该类型：canonical编码在全表canonical顺序已确定后可沿既有batch/列处理；export的no排序、comparison的key全局唯一性、ordered LIS/blank interval/move不允许任意按行区间切开。全局顺序/重复key检查及跨块摘要合并未证明前不拆表；不把增加K当作偏斜解决方案。

## 7. 方案比较、首个试验与验证范围

| 方案 | 可覆盖成本 | 代价/风险 | 选择 |
| --- | --- | --- | --- |
| A 同次bundle exact read/解码结果复用，保留持久边界验证 | 已测bundle39.741/46.962 s中的重复读取/hash/JCS部分；N1也可能减少工作 | 必须证明同scope/ref/保护/read-session；不能假设全部bundle可省 | **首个条件性实现试验**，先计时定位，再只合并一处同阶段读取；其他边界不动 |
| B 一类业务表的canonical IPC或export阶段少量通道 | 已测materialize/export中可独立的逐表工作，减少多实例尾部等待 | 需要安全native任务桥、峰值预约、输入/输出生命周期和获准N档；现N1无CPU并行收益依据 | 第二步；由计时决定二者其一，不同时开多层并行 |
| C 整个pair/完整表pipeline并行 | 理论覆盖更多阶段 | 共享native/session、risk全pair限额、composite依赖、records发布及M叠加，FULL仅两pair；N1不增加计算能力 | 不推荐首轮 |

**A的具体试验边界**：先测 `_plan_artifacts` 中 `locate → _verify_store_bytes` 和 `validate_bundle` 中每entry的相同组合。选择贡献较大的一处，把“读取并校验后返回raw”作为单一内部步骤，使该段的decode/rewrite/validation消费同一份已校验raw，避免调用者先读一次、helper又读一次。source进入时仍做完整size/raw SHA与引用闭合，target写后及final闭包仍独立完整读回；所有store、测试double的exact-read保证及变更检测语义先核对。若第二次读承载owning Contract要求的不同时点检测，则该读不合并，最多复用decode/metadata，或放弃A。不是全局memoized store，不缓存“verified forever”，也不顺带删publish第二次验证。

能节约多少只由新增计时的独占重复部分、读写介质、JCS占比和保留验证决定。39.741/46.962 s是整个bundle窗口，不是A可消除上限的承诺。类似地，仅优化comparison即使其耗时全消失也只涉及当前2.772/12.385 s累计指标的一部分，且不可据此精确推出端到端收益。B须量出同类任务数量、各表工作、最大任务和准入等待后才预测上限；内存或N使K=1时不预期CPU提速。

后续实现获准后的比例化验证建议如下；本稿未执行这些检查：

1. **A的正确性**：复用现有 [bundle测试](../../vnext/backend/tests/test_bundle_assembly.py) 与 [checkpoint/closure测试](../../vnext/backend/tests/test_operation_checkpoint_contracts.py)，重点嵌套ref rewrite、shared/alias绑定、source损坏/缺失、destination失败、source/target变更、final semantic/closure tamper、cancel与预算不足；新用例只覆盖此次合并读取引入的边界和释放，不为每个helper镜像造测试。若触及publish，另跑 [publish成功/取消/漂移](../../vnext/backend/tests/test_preview_job_publish.py) 与恢复/lease/pin保护场景。只改bundle内部逻辑且未触容器边界时不因此无条件扩全runner或重建全部镜像，按实际改动遵守仓库门禁规则。
2. **B的正确性**：一份代表family的差分/contract向量验证原路径与新路径；数量0/1/少于K/多于K、动态设备数、大表先行/完成补位、一个超大表、同内容别名、宽变长字段、预算刚好/不足/输出留存、取消/drain/loss/失败中间退出；打乱完成顺序仍同规范结果/digest/诊断/locator。验证CPU总线程cap、无共享reader游标、无超M预约和无残留owner。原生adapter变更按AGENTS强制重建绑定扩展，并选对应Rust/backend focused与所需权威包；不在开发主机运行。
3. **性能**：A先用相同空INITIAL MO、同节点同资源/缓存控制条件成对比较，报告受理至可读、父段独占耗时、实际read/hash/JCS bytes/calls及CPU/内存/scratch；改动涉及两pair复用再补FULL。B先在原N1/K1验证调度开销，再在明确授权的一个N>1固定档比较同输入的串行/少量通道，分列资源成本，不把增核收益归于算法。重复次数依据噪声及结论需要决定，保留所有样本，不以最好一次作结论。真实数据扩展、最终门禁和容器门禁按实际改动与Owner确认范围执行。

## 8. 独审需要核收的关键问题

- A合并的究竟是同一读取职责，还是删掉一个时点的损坏/缺失检测；完整final raw/semantic/ref闭合保障是否保留，port与真实store/测试double保证是否一致。
- 同lease复用的pin保护/read-session窗口、取消/漂移/lease退出和cleanup/repair锁序是否能闭合；恢复仍从durable内容重新验证。
- 业务类型依据为现有resolved规则；完整实例/rows/bytes/耗时待核不能被43条截断列表替代，首个专用类型不能预先凭表名指定。
- B没有直接并发共享现有ContextVar/budget/ExitStack/cache/native operation；任务桥、借用、输出保留与停止等待是否真正在同M/N内。
- 规范结果合并、risk全pair预算、ordered全表语义和locator行序是否会被完成次序改变；单表偏斜明确保留边界。
- 当前仅设计稿。产品、N1/M24、05固定测量、08服务与main均未因本文改变；首次实施与资源档需要后续明确授权。
