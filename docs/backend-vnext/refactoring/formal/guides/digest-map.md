# Gateway VNext 摘要（Digest）体系一页说明

> **状态：** P2 正式指南（基于 `B′` 全量审计与 `P1` 只写不读字段清理后定稿；不另起 P4 别名统一或合并）。
> **代码基线：** `main` `e5bfd7c46e1e0966051955e47308cb6c33ca8962`（`P1` 提交后；源审计基准见 [identity-and-digests.md](../../../identity-and-digests.md) 与 [execution-plan §2/§8.7](../plans/p7-backend-remediation-execution-plan.md#第-4-批试点与核对)）。
> **实盘统计：** 六大职责域共计 **53 种**（6 + 11 + 7 + 14 + 9 + 6）摘要/指纹机制，对应 `vnext/backend/src/gateway_backend/` 中 **116 个** `*_digest` / `*_digests` 字段与键名（`B′` 基线 127 项经 `P1` 清除 11 项只写不读字段：`snapshot_ledger_digest`、`sql_digest`、`xml_source_digest`、`source_digests`、`catalog_digest`、`schema_facts_digest`、`entry_manifest_digest`、`source_package_digest`、`package_manifest_digest`、`required_entries_manifest_digest`、`ledger_digest`）。未发现生产重算/核对消费者者实写 **`未知/待决定`**（共 **7 项**）。

---

## 1. Artifact 字节寻址（6 种）

| 摘要种类 | 覆盖内容 | 计算者（文件 / 函数） | 核对者（文件 / 函数） | 防什么 |
| --- | --- | --- | --- | --- |
| 通用原始字节 SHA-256（`raw_sha256`） | 本地 ArtifactStore 对象及解包文档原始字节 | `artifacts/store.py:put_with_built_ref`；`artifacts/digest.py:raw_sha256_from_bytes` | `artifacts/store.py:_verify_raw`；`local_store.py:_read_exact`；`computation_cache.py:528`；`import_builder.py:154`；`row_location/inputs.py:94`；`source_package_staging/staging.py:138`（`expected_required_sql_digest`） | 防本地磁盘静默损坏、截断或跨工件误指向 |
| 内容寻址 Artifact ID（`a1:<loc>:<kind>:<hex>`） | `location`、`kind` 与内容/身份载荷的确定性 JCS SHA-256 | `artifacts/location.py:build_artifact_id` | `artifacts/location.py:parse_artifact_id`（格式）；各 store `put`/`locate` 寻址一致 | 防工件路径冲突与未授权猜测标识 |
| 快照表 Parquet 工件内容摘要（`artifact_content_digest`） | 表描述符、列元数据与行布局/内容的规范 JCS | `capabilities/snapshot_materialization/artifact.py:artifact_content_digest_of` | `artifact.py:419,484,761`（打开及校验工件时重算比对） | 防持久化 Parquet 表工件与声明元数据脱节 |
| 导出表布局缓存键（`row_layout_digest`） | 表描述符、源列与有序元数据的规范 JCS | `capabilities/snapshot_materialization/artifact.py:row_layout_digest_of` | `sqlite_snapshot_export_cache.py:66,147`；`client_parquet.py:198` | 防结构/有序编码变化后误命中旧 Parquet 导出缓存 |
| 比较记录分段与闭包摘要（`records_manifest_digest` / `closure_manifest_digest`） | 比较记录分区 manifest 与闭包的规范 JSON 字节 | `capabilities/comparison/artifacts.py:491,578,716` | `comparison/artifacts.py:140,166,280`；`comparison/contracts.py:317` | 防比较明细记录文件缺失、篡改或闭包跨表混用 |
| 风险标注工件与闭包摘要（`content_digest` / `manifest_digest` / `closure_manifest_digest`） | 单表风险标注 JSON、manifest 与闭包清单字节 | `capabilities/risk_evaluation/_artifacts.py:120,128,184` | `risk_evaluation/_artifacts.py:210,232,234` | 防风险标注侧车工件丢失或字节不一致 |

## 2. 表快照与 Schema 的身份（11 种）

| 摘要种类 | 覆盖内容 | 计算者（文件 / 函数） | 核对者（文件 / 函数） | 防什么 |
| --- | --- | --- | --- | --- |
| 规范化行哈希（`row_content_hash` / `row_digest`） | 单行 ULEB128 列名与强类型标量帧的域分离语义摘要 | `snapshot_materialization/_digest.py:row_content_hash`；Rust `business_kernel/cells.rs:311` | 由上层 `raw_content_digest_of` 聚合核对（无独立单行外部核对者） | 防行内列类型/空值/边界混淆导致的跨行碰撞 |
| 表原始行内容无序集合摘要（`raw_content_digest`） | 全表 `row_content_hash` 的无序多重集 XOR/加法同态摘要 | `snapshot_materialization/_digest.py:raw_content_digest_of`；Rust `operations.rs:table_digest` | `canonical_metadata/table_access.py:296,382`；`comparison/task_input.py:379`；入 `snapshot_digest_of` | 防表行内容增删改（保留重复行计数、忽略行物理顺序） |
| 比较 Schema 摘要（`compare_schema_digest`） | 规范表名、排序列名与 compare key 列名 | `snapshot_materialization/_digest.py:compare_schema_digest` | 参与 `snapshot_digest_of` 与 `task_input.py`（无独立重算核对者） | 防仅比较列集合/主键变更被静默忽略 |
| 业务 Schema 摘要（`business_schema_digest`） | 业务可见列名、逻辑类型、可空性与声明类型 | `snapshot_materialization/contracts.py:business_schema_digest_of` | `business_presentation.py:450`；`table_access.py:235`；入 `snapshot_digest_of` | 防列类型或业务结构变更被当作纯内容一致 |
| 快照总摘要（`snapshot_digest`） | 阶段、解析器/规则/编码版本、全表摘要与复合逻辑源码摘要 | `snapshot_materialization/_digest.py:snapshot_digest_of` | `repository_ref.py:485`（回读校验）；`preview_jobs/checkpoint.py:696`；`compare_jobs/checkpoint.py:356`；`review_result.py:73,199` | 防快照任一侧表集合、版本或逻辑定义漂移 |
| 快照纯原始状态摘要（`raw_state_digest`） | 排序表名、行数与 `raw_content_digest`（不含 schema） | `snapshot_materialization/_digest.py:raw_state_digest_of` | **`未知/待决定`**（仅测试与 golden 覆盖，生产未读） | 设计意图：独立度量原始行数据变化而不受 schema 影响 |
| 规范化业务状态摘要（`canonical_state_digest`） | 规范化表中对业务有意义的行内容摘要集合 | `snapshot_materialization/contracts.py:canonical_state_digest_of` | `preview_jobs/checkpoint.py:204,206,545-551`；`submission/accept.py:270` | 防“无实质业务变化（如仅注释/未投影列变化）”被误判为可提交变更 |
| 规范化表 Schema 摘要（`schema_digest` / `canonical_schema_digest`） | 列类型/可空性与主键序列的规范 JCS SHA-256 | `storage_projection/_digest.py:compute_schema_digest`（另 `import_publication.py:1022` 重复） | `storage_projection/publish.py:384`；`pair_pipeline.py:942`；`table_access.py:383` | 防投影后物理表 schema 与 manifest 声明不一致 |
| 规范化清单总摘要（`canonicalization_manifest_digest`） | 域前缀 + contract/storage 版本、规则集、源工件与全表清单 | `storage_projection/_digest.py:compute_manifest_digest` | `storage_projection/publish.py:96,309`；`package.py:177`；`native.py:179`；`import_publication.py:736`；`checkpoint.py:510,537`；`finalize.py:52` | 防导入/物化跨阶段 canonical manifest 被替换或损坏 |
| 规范化表缓存键（`CanonicalTableKey.table_digest`） | 规范化表的唯一内容寻址标识 | `capabilities/storage_projection/`（写入 `canonical_table_cache`） | `application/canonical_metadata/table_access.py:296` | 防规范化缓存表与当前 commit 元数据内容不一致 |
| 复合逻辑源码与公式摘要（`composite_logic_source_digest` / `formula_digest`） | `logics.xml` 原始字节；单条公式 AST 规范 JCS | `composite_signal/contracts.py:107`；`_digest.py:formula_digest_of` | `composite_logic_source_digest` 由 `contracts.py:88,93` 及 `snapshot_digest_of` 核对；`formula_digest` 核对者 **`未知/待决定`** | 防复合逻辑源码变更漏算（`formula_digest` 暴露给展示模型） |

## 3. 规则集与配置的身份（7 种）

| 摘要种类 | 覆盖内容 | 计算者（文件 / 函数） | 核对者（文件 / 函数） | 防什么 |
| --- | --- | --- | --- | --- |
| 表规则集摘要（`ruleset_digest`） | `TableRulesetSnapshot` 全部表/列/投影/比较规则规范文档 | `capabilities/table_rules/contracts.py:compute_ruleset_digest` | `table_rules/contracts.py:599,603`；`preview_jobs/assemble.py:198`；`checkpoint.py:511`；`accept.py`（staleness） | 防预览、提交、历史比较之间规则集版本或内容不一致 |
| 单表比较规则视图摘要（`comparison_rule_digest`） | 解析后的单表比较排除列、key 策略与有序规则文档 | `capabilities/table_rules/resolver.py:resolve_comparison_rule_view` | `comparison/pair_planning.py:141,165,172`（进入缓存 `task_digest`） | 防单表比较规则变化后误复用旧表比较缓存 |
| 存储投影规则视图摘要（`storage_rule_digest`） | 单表规范主键、保留/丢弃列、结构列与有序策略 | `storage_projection/_digest.py:compute_storage_rule_digest`（`import_publication.py:988` 重复） | **`未知/待决定`**（写入 surface 与 checkpoint，生产未见重算核对） | 设计意图：记录并绑定单表投影规则（当前仅透传暴露） |
| 风险规则集摘要（`risk_ruleset_digest`） | `RiskRulesetSnapshot` 规则与严重性策略文档 | `capabilities/risk_evaluation/contracts.py:compute_risk_ruleset_digest` | `risk_evaluation/contracts.py:476-480`；入 `risk_evaluation_digest_payload` | 防风险规则集文档与评估结果绑定不一致 |
| 部署存储与资源配置摘要（`storage_digest` / `resource_digest`） | 部署路径配置、环境/组标识及资源预算文档 | `deployment_config.py:_configuration_digest` | `bootstrap/deployment_identity.py:compare_configuration`；`provisioning/registration.py:56`；`repository_identity.py:35` | 防 BE/Worker 以不匹配的存储根目录或资源配置启动 |
| 入口幂等请求指纹（5 路） | 上传 / Preview / History Compare / Submit / Review 请求规范载荷 | `workspace/contracts.py:91,119`；`history/compare_bindings.py:67`；`submission/contracts.py:370`；`review_contracts.py:55` | 各用例受理入口重放检验（`workspace/services.py`、`history/compare.py:413`、`accept.py:125,171`、`review.py:173`） | 防同一 `Idempotency-Key` 被不同请求参数重放覆盖 |
| 业务配置事实摘要（`ConfigurationFacts.facts_digest`） | 前后双侧内容身份（`canonical_state_digest` + 规则/版本）与生成时间 | `domain/configuration_facts.py:facts_digest` | `archive/integrity.py:141`；`manual_close.py:208`；`submit_jobs/payload.py:306` | 防归档/提交链路中对配置内容与生成时间事实的篡改 |

## 4. 比较、风险、Surface、Bundle 等结果的身份（14 种）

| 摘要种类 | 覆盖内容 | 计算者（文件 / 函数） | 核对者（文件 / 函数） | 防什么 |
| --- | --- | --- | --- | --- |
| 表比较核心事实摘要（`facts_core_digest`） | 全部表级差异事实核心语义（剥离可裁剪展示/明细策略） | `comparison/standard.py:259`；`replacement.py:61`；Rust `records/facts.rs:digest_facts_core` | `comparison/artifacts.py:709`；`surface_assembly/_assembly.py:298`；`risk_evaluation/_engine.py:1242` | 防比较结果与明细闭包/风险评估/Surface 之间跨结果错配 |
| 单表比较事实与审计摘要（`table_fact_digest`） | 单表变更状态、schema 变更、行数统计、记录/扩展摘要 | `comparison/row_encoding.py:_with_table_digest`；Rust `records/facts.rs:digest_table_fact` | **`未知/待决定`**（`comparison_audit.py:115,125` 仅校验非空并落盘，读回未重算） | 设计意图：绑定隐藏结构变更表级事实到结构审计工件 |
| 单 pair 比较结果总摘要（`comparison_digest`） | 合同/算法版本、规则集摘要、前后快照摘要与 `facts_core_digest` | `comparison/standard.py:289`；`replacement.py:87` | `comparison_audit.py:221`；`history/results.py:496`；`review_result.py:74`；`bundle_assembly/_digest.py:74` | 防 pair 级比较事实与展示/审阅/归档/审计脱节 |
| 表比较缓存任务与扩展指纹（5 项） | `TableComparisonTask` 语义投影（剥离显示名）、有序/空白扩展与缓存视图字节 | `comparison/task_input.py:build_table_task_identity`；`cache_codec.py:112,134`；Rust `ordered.rs` | `artifacts/computation_cache.py:143`；`cache_codec.py:199,295`；`control_db/computation_cache.py:151,236` | 防比较缓存跨版本/跨规则/跨参数误命中或缓存字节损坏 |
| 项目身份评估摘要（`assessment_digest`） | schema/rule 版本、前后快照摘要、状态、条目集摘要与诊断 | `capabilities/project_identity/_rule.py:106` | `preview_jobs/assemble.py:1101`；`preview_binding.py:58-60` | 防项目身份判定结论被替换或与 Preview 结果脱钩 |
| Preview 身份评估集合摘要（`identity_assessment_set_digest`） | 全部 pair 的 `(pair_id, applicability, status, assessment_digest)` 列表 | `application/preview_jobs/assemble.py:_identity_assessment_set_digest` | `assemble.py:990`；`preview_binding.py:50`；`submission/accept.py:295`；`archive/queries.py:384-385` | 防提交/归档时遗漏或篡改任意 pair 的身份评估状态 |
| Preview 规范化业务状态摘要（`preview_canonical_business_digest`） | Preview 最终 `modified_canonical_state_digest` | `application/submission/contracts.py:preview_canonical_business_digest` | `application/submission/accept.py:268-270` | 防在无实际规范化业务变化时产生空提交 |
| 单表风险摘要（`compute_risk_table_digest`） | 单表风险明细与标注清单摘要 | `risk_evaluation/contracts.py:compute_risk_table_digest`（`_engine` 未直接调，payload 内联计算 @ `L1361`） | **`未知/待决定`**（仅导出，生产未见独立核对者） | 设计意图：单表风险语义寻址 |
| 风险评估摘要（`risk_evaluation_digest`） | 风险合同/模型/规则集版本、选项、总体及全表风险摘要 | `risk_evaluation/contracts.py:compute_risk_evaluation_digest` | `risk_evaluation/contracts.py:1204,1212`；`surface_assembly/_assembly.py:321`；`history/results.py:544`；`review_result.py:77`（注：仅字段一致性比对，未重算核对） | 防风险评估/报告/标注闭包/Surface/Bundle 之间结果错位 |
| 风险报告摘要（`compute_risk_report_digest`） | `RiskReport`（`evaluation_digest`、总览、全表与选项） | `risk_evaluation/contracts.py:compute_risk_report_digest` | **`未知/待决定`**（仅定义并导出，生产未调用） | 设计意图：独立风险报告指纹（当前未接入主链） |
| 风险表候选缓存键（`RiskCandidateInputV1.task_digest`） | `comparison_task_digest`、facts/ruleset/options/policy JCS | `capabilities/risk_evaluation/candidates.py:task_digest` | `risk_evaluation/candidates.py:363` | 防风险候选事件缓存跨规则/选项误命中 |
| 展示 Surface 摘要（`surface_digest`） | Surface 合同版本、比较/风险/项目身份摘要与全部表投影 | `capabilities/surface_assembly/_digest.py:compute_surface_digest` | `surface_assembly/_assembly.py:229`；`bundle_assembly/_assembly.py:394`；`transport.py:222` | 防展示层 JSON 与底层比较/风险结果不一致 |
| Bundle 与闭包清单摘要（`bundle_digest` 等 3 项） | Bundle 语义 manifest（`bundle_digest`）与传输 tar 工件闭包（`closure_digest`） | `bundle_assembly/_digest.py:compute_bundle_digest`、`closure_digest` | `bundle_assembly/_assembly.py:298,300,361,385`；`transport.py:124`；`history/results.py:323,573`；`review_result.py:94`；前端 `posix-tar.ts:449` | 防离线 tar 下载包被篡改、缺件或前后端结果错配 |
| Preview READY 闭包绑定摘要（`preview_ready_closure_digest`） | `PreviewResult` 全量事实（版本、7 digest、canonical、身份、comparison pairs、bundle） | `application/preview_binding.py:derive_preview_ready_closure_digest` | `accept.py:264`；`accept_transaction.py:473`；`finalize_transaction.py:361`；`review_result.py:197` | 防 Preview 受理/入库/审阅读取期间任一绑定产物漂移或篡改 |

## 5. 把人工决定绑定到所见内容（9 种）

| 摘要种类 | 覆盖内容 | 计算者（文件 / 函数） | 核对者（文件 / 函数） | 防什么 |
| --- | --- | --- | --- | --- |
| 审核操作绑定请求指纹 | `submission_id`、决策动作、说明与所见 Preview/Assessment 身份 | `application/submission/review_contracts.py:compute_review_apply_request_fingerprint` | `application/submission/review.py:173` | 防审核人员针对已变化或错配的提交结果执行批准/驳回 |
| Submit 受理绑定请求指纹 | `workspace_id`、`preview_result_id`、`source_digest`、`snapshot_digest`、身份确认摘要等 | `application/submission/contracts.py:compute_new_accept_fingerprint`、`compute_replay_accept_fingerprint` | `application/submission/accept.py:125,171,381` | 防 Submit 在不同 Preview 状态或不同确认集合下误重放 |
| 归档候选单条摘要（`candidate_digest`） | 单个已批准 submission 的完整来源、基线、内容、manifest 与审阅序列 | `application/archive/contracts.py:compute_candidate_digest`（`snapshot.py:311` 包装） | `application/archive/integrity.py:180`（经 `compute_candidate_set_digest` 间接校验） | 防候选提交在生成归档计划前被修改或跨提交替换 |
| 归档候选集合摘要（`candidate_set_digest`） | 范围、基线、业务规则、`baseline_facts_digest` 与排序后的全量候选 | `application/archive/contracts.py:compute_candidate_set_digest` | `archive/audit.py:142,265`；`archive/integrity.py:180`；前端 `journeys.ts:460,499` | 防确认/发起归档期间出现新候选或基线漂移（不可逆操作守门） |
| 归档选定候选主题摘要（`selection_subject_digest`） | `candidate_set_digest`、`selected_submission_id`、`expected_candidate_digest` | `application/archive/contracts.py:compute_selection_subject_digest` | `archive/integrity.py:113`；`archive/contracts.py:629`；`archive/audit.py:146` | 防人工确认绑定到错误的“待归档主候选” |
| 归档异常主题摘要（3 类 `subject_digest`） | 兄弟排除 / 项目身份例外 / 业务冲突异常的精确因果载荷 | `archive/contracts.py:compute_anomaly_subject_digest`、`compute_identity_exception_subject_digest`；`queries.py:437` | `archive/contracts.py:541`；`archive/integrity.py:233`；`archive/audit.py:294` | 防人工异常处置被错绑到不同异常事件 |
| 归档确认请求指纹 | 范围、基线版本、`candidate_set_digest`、`subject_digest`、动作与操作者 | `application/archive/contracts.py:compute_confirmation_request_fingerprint` | `application/archive/audit.py:108` | 防归档确认事件重放篡改 |
| 归档异常处置请求指纹 | 范围、基线版本、候选集、`subject_digest`、目标候选与处置动作 | `application/archive/contracts.py:compute_resolution_request_fingerprint` | `application/archive/audit.py:227` | 防归档异常处置事件重放篡改 |
| 归档发起与手工闭环请求指纹 | `candidate_set_digest`、选定候选、确认/处置序列引用或闭环事实 | `application/archive/contracts.py:compute_start_request_fingerprint`、`compute_close_request_fingerprint` | `archive/start.py:100`；`archive/integrity.py:88`；`archive/manual_close.py:85,227` | 防最终执行不可逆归档或手工闭环时与人工所见不一致 |

## 6. 变更计划与外部写入的身份（6 种）

| 摘要种类 | 覆盖内容 | 计算者（文件 / 函数） | 核对者（文件 / 函数） | 防什么 |
| --- | --- | --- | --- | --- |
| 变更计划身份摘要（`mutation_plan_identity_digest`） | 基线 commit、源身份、投影绑定、目标能力与阈值策略 | `capabilities/mutation_planning/contracts.py:compute_mutation_plan_identity_digest` | `mutation_planning/contracts.py:569`（`StorageMutationPlan.__post_init__`） | 防变更计划与其输入前提（基线/投影/策略）脱节 |
| 变更行级摘要（`row_digest` / `before_row_digest`） | 行主键与列值（或行图像）的规范字节摘要 | `mutation_planning/_digest.py:43,52`；`external_target_sync/_ledger_digest.py:72` | `external_target_sync/_reference_executor.py:304,312`（测试参考执行器内校验） | 防外部目标在应用前发生行级漂移（CAS 前置条件） |
| 变更集摘要（`change_set_digest`） | 规范排序后的 `mutations` 序列 JCS SHA-256 | `capabilities/mutation_planning/contracts.py:compute_change_set_digest` | `contracts.py:743`；`external_target_sync/_reference_executor.py:77,163,244` | 防变更命令序列内容或顺序被篡改与重复执行 |
| 变更集闭包摘要（`ChangeSetClosure.closure_digest`） | `manifest`（含表汇总、阈值与投影绑定）+ `mutations` | `capabilities/mutation_planning/contracts.py:compute_change_set_closure_digest` | `contracts.py:757`；`mutation_planning/_artifacts.py:34,62,68` | 防持久化变更集闭包与 manifest 脱节 |
| Replay 渲染器能力摘要（`capability_digest`） | 方言与支持操作/单元类型白名单 | `mutation_planning/_repository_replay_renderer.py:compute_repository_replay_capability_digest` | `_repository_replay_renderer.py:130` 做 `RendererCapabilityDeclaration` 等值比较（未重算） | 防渲染器与变更集目标能力不匹配 |
| 参考执行器检查点摘要（`compute_reference_executor_checkpoint_digest`） | `ReferenceExecutorCheckpoint` 文档 JCS | `capabilities/external_target_sync/contracts.py:279` | **`未知/待决定`**（仅导出，生产与测试均未核对） | 设计意图：参考执行器崩溃恢复检查点指纹 |

---

## 7. 待决线索与口径备注（不在本指南擅自合并或猜补）

- **P1 清理边界与保留项：** `P1` 已清除 11 项只写不读字段；`raw_state_digest`（第 2 类，`snapshot.md` Contract 与 5 个 golden 绑定）与通道规则保留目录 `capabilities/risk_evaluation/contracts.py:1288` 中的 `comparison_facts_digest`（生产未调用 `to_document()`）保留现状；`PreviewResultDigests.input_digest` 仍与 `source_digest` 同值写入并进入 `preview_ready_closure_digest`。
- **同输入重复实现线索：** `infrastructure/repository_write/import_publication.py:988,1022` 与 `capabilities/storage_projection/_digest.py:21,36`（`compute_storage_rule_digest`、`compute_schema_digest`）同构；`XmlSourceInput.document_content_digest` 冗余字段 `xml_source_digest` 已随 `P1` 清除。
- **未重算核对或生产未接线摘要：** 除上表 7 项 **`未知/待决定`**（`raw_state_digest`、`formula_digest`、`storage_rule_digest`、`table_fact_digest`、`compute_risk_table_digest`、`compute_risk_report_digest`、`compute_reference_executor_checkpoint_digest`）外，`risk_evaluation_digest` 与 `capability_digest` 当前仅有字段等值对比而无重算核对；第 6 类 `external_target_sync` 仍按 `P5-S0` 决议保持生产不可达（`_ledger_digest.py:compute_ledger_digest` 仅由测试 `test_external_target_executor.py` 调用）。
- **新增摘要要求：** 按 [AGENTS.md](../../../../../AGENTS.md)，后续新增 digest、ID、版本常量或状态枚举须明确防什么与由谁核对；只计算不核对的不加。
