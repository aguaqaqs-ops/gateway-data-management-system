# P5 整体 exit 独立审核

- 结论：**定向修订**。
- 日期：2026-10-23。
- 审核对象：main @ `8ec03b5d75481c4cc2ffeb59d11befc7fa106233`（下称 M）；门禁提交 V = M；实现审查基线亦为 M。
- 范围：P5-5A–5E、S0–S5、G1–G13 的整体收口；不是重审各阶段。阶段报告仅作索引，以下判断以 M 的源码、测试、owning 文档和本次 ct108 门禁为准。
- 依据：P5 设计 §2A、§12、§13；收口设计 §1、§2、§9、§11–14、附录 A/B；执行计划 §1、§2、§8；S0 独立审核 §7.8；DC1–DC34；治理修订计划；ADR 0018–0021 及其上游 Contract；AGENTS.md、testing-conventions；结论采用 slice-design-execution-and-review-guide §6。
- 工作区：开发主机 `/home/dev/gdds-p5-exit-review`，分支 `p5-exit-review`，从 M 创建并建立 legacy 符号链接。测试只在 ct108 的 detached `/home/dev/gdds-p5-exit-gate` 执行，该 worktree 已删除；没有在主工作区操作源码、运行测试或提交。
- 路径简写：`F/` = `docs/backend-vnext/refactoring/formal/`；`P/` = `F/plans/`；`B/` = `vnext/backend/src/gateway_backend/`；`T/` = `vnext/backend/tests/`。文件行号均指 M，不指历史报告当时的树。

## 1. 结论摘要

结构收口、依赖边界、两组不可达模块的登记、真实链路测量及本次最终门禁成立，但**不能签署 P5 整体退出**。存在 **2 个阻塞项**：Preview 把投影的多项 typed 诊断缩成第一项且不标明输入侧，违反 DC14；ADDITIVE 激活后旧基线仍可 Preview 的指定权威测试缺失，S0-F1 的必达验收不能据阶段通过记录推定完成。另有 2 项非阻塞记录问题，见 EXIT-F3、EXIT-F4。

总体架构与规范状态模型成立，修正范围有限，不需要整体返工。全量 runner exit 0、五包静态检查通过、import_rules 为 **0 / 0 / 6**，证明现有测试通过，不能补足未覆盖的业务要求。本报告不授权下一阶段、发布、合并或打 tag。

## 2. Findings

### EXIT-F1：Preview 丢弃投影失败明细，DC14 未在业务边界落地

- 类型：**已证实缺陷**；是否阻塞：**是**。
- 位置：`B/application/preview_jobs.py:245`、`:594`、`:1033`、`:1244`、`:1991`；`T/test_storage_projection_core.py:398`。
- 依据：DC14；收口设计 §4.2（`:213`）要求整体 FAILED、一次给出全部失败表/列，FULL 的 INITIAL 失败须标明所在侧；ADR 0018；`F/contracts/business-lifecycle-and-state.md:154`。
- 触发场景与影响：同一上传有两个以上不受支持的列/表，或 FULL 的 INITIAL 侧投影失败。capability 已收集多个 `ProjectionDiagnostic`，但 `_materialize_uploaded_side` 只取 `projected.diagnostics[0]`，只把其 code/message 写入 `PreviewJobError`，不传递 table/column 明细。handler 再发布一个 message 最长 255 字符的 `OperationDiagnostic`。INITIAL/MODIFIED 调用未传入侧标识。因此 Preview 会 FAILED，却不能一次告知全部失败项，也不能可靠定位失败侧；用户必须反复修正上传。现有 capability 聚合测试不能证明业务边界交付了该信息。
- 最小修正方向：由 Workspace Preview Application 与 Storage Projection owner 保留已有有界 typed 诊断集合及 side，沿既有失败结果/诊断通道提供给调用者；不要只拼接第一条消息，也不要求新建 incident 或通用 evidence 平台。FULL 的遍历/短路策略须满足已接受的失败项与侧标识约定。
- 关闭标准：在 Preview 入口的唯一测试 owner 中，以共享参数表覆盖多表、多列失败及 FULL INITIAL/MODIFIED 定位；断言公开可读取的失败明细完整、稳定、有界，整体 FAILED、无 READY 结果/Repository effect；capability 原聚合测试保持。复审对照数据流确认诊断没有在异常、持久化或 DTO 映射处再次丢失。

### EXIT-F2：S0-F1 指定的“ADDITIVE 激活后旧基线仍可 Preview”缺少验收证据

- 类型：**待验证假设（明确要求的测试缺口，不是已证明运行时失败）**；是否阻塞：**是**。
- 位置：`P/p5-arch-closure-design.md:628`；`F/adr/0019-commit-canonical-metadata-authority.md` Required Verification；`T/test_preview_job_materialize.py:142`、`:180`、`:224`；`T/support/preview_job_harness.py:321`；`T/support/canonical_metadata.py:66`。
- 依据：S0-F1 关闭标准要求两个场景有唯一测试 owner；S0 审核 §7.8 明确 F1 不得延期。设计 §12 指定旧基线场景由 `test_preview_job_materialize.py` 负责，另一场景由 `test_submit_transactions.py` 负责。
- 触发场景与影响：已有 Submission 基线按规则 A 形成，ADDITIVE 激活规则 B 后新受理 Preview。M 中指定测试文件使用 harness 默认的当前规则生成基线 manifest，没有构造 A/B 不同的 provenance。全仓相关测试核对也未找到替代的完整 Preview 场景。`test_historical_manifest_versions_are_returned_as_provenance` 只证明解码；`test_preview_rejects_ruleset_change_before_each_step` 证明旧任务拒绝；`test_t1_rejects_preview_built_with_another_projection_ruleset` 证明旧 Preview 拒绝；三者均不能代替“新任务允许旧基线”。
- 实现判断：`B/application/canonical_metadata/binding.py:42` 保留历史 manifest provenance；`B/capabilities/comparison/pair_planning.py:33` 使用运行期比较规则，源码方向符合 DC10。没有据此宣称运行时必然失败，也没有把已有旧任务恢复拒绝误判为缺陷。缺口在于该高影响分支尚无要求的验收证明。
- 最小修正方向：在指定 owner 补一个代表性 A/B 规则测试，A 的非空 Submission 基线、B 的 ADDITIVE 变化、新任务冻结 B，经过生产 Preview 物化/组装接线完成比较；复用现有 fake Repository/metadata 支撑，不为此复制测试框架或引入全量真实数据重跑。
- 关闭标准：测试明确证明 commit provenance A 与运行期 B 不同，Preview 成功使用 B 的比较语义，旧基线仍可读取；现有 stale Preview/恢复失败测试保持通过。若已有等价测试，可提供明确 nodeid、不同规则的 fixture 构造与断言来关闭，不要求重复新增。

### EXIT-F3：Canonical Storage 的现行版本标头与正文、实现不一致

- 类型：**已证实缺陷（文档）**；是否阻塞：**否**。
- 位置：`F/contracts/canonical-storage-and-repository-boundary.md:13` 写 storage projection version `1`，同文 `:254` 写当前 `2`；`B/capabilities/table_rules/contracts.py:26` 为 `2`，Storage Projection contracts 引用该值。
- 依据：S2a 负零规范化 `26560b2595` 已改变规范字节并提升版本；收口设计附录 B.1 与 S2b 复审已记录原因。Contract semantic version `3.2.0` 与 projection version 是不同字段。
- 触发场景与影响：新读者从标头取得错误版本；源码、golden 与后续正文一致，未发现因此产生双读或错误发布，故不阻塞产品 exit。
- 最小修正方向：由 Table Rules / Storage Projection 文档 owner 在统一状态更新时把现行标头对齐 `2`，保留历史版本来源。
- 关闭标准：标头、版本沿革、常量一致，不把 DC29 误写成这次 projection version 提升的来源。本审核不修改 Contract。

### EXIT-F4：部分旧非阻塞观察仍只有“之后/deferred”，没有明确处置节点

- 类型：**非阻塞建议（遗留登记缺口）**；是否阻塞：**否**。
- 位置：`P/p5-arch-closure-g11-independent-review.md:82` R2-O3；`P/p5-5b-s8-handoff.md:203` Deferred register 中 occupancy-assertion-gap、private-process-access。
- 依据：本次 exit 要求带出项有 owner、理由、去向；M 中 `T/test_http_admission_shutdown_process.py:31` 仍仅标 serial；`T/test_submit_recovery.py:745` 的 T3 crash 用例仍无该项 post-crash occupancy 断言，restart 测试 `:918` 仍访问 `_process`。未找到后续明确接受删除、延期节点或重开条件的登记。
- 触发场景与影响：后续 focused `-m unit` 会包含子进程测试；测试维护建议与覆盖补充可能长期无人处理。完整 runner 不按 unit 筛选，本次均通过；这些观察不证明当前事务或恢复错误，不应升级成新强制测试矩阵。
- 最小修正方向：建议分别由 Backend 测试 owner、Submission 测试 owner 接受处置：补 marker、在下次该语义屏障修改时补断言/整理 harness，或明确接受现状并关闭。这里的 owner/节点是审核建议，不冒充已有 owner 决议。
- 关闭标准：统一 exit 记录明确上述三项各自的接受/延期/关闭决定及节点即可；无需仅为此重跑完整门禁。其他有明确 owner/重开条件的遗留见 §6，不重复报 finding。

## 3. 验收核对

### 3.1 P5 §2A.5 五项

| 验收项 | 结果 | M 上的证据与判定 |
| --- | --- | --- |
| 1 已确认边界、语义问题逐项收口 | **部分成立** | wire/private import/环/倒挂/包根归属已修；下表逐行核对。语义 DC14 与 S0-F1 指定验收仍有 EXIT-F1/F2，不能整体关闭。 |
| 2 契约执行边界、编排与 projection 占位 | **成立** | facade/contracts 叶子规则与实际消费者一致；占位删除；Application 共用 step/pair 模块；保留语义有 owner，见 §3.3。不是凭文件长度或阶段 tag 判断。 |
| 3 依赖、真实链路测量、Phase 6 输入 | **成立** | S5 仅新增 dev-only `blake3==1.0.10`；§3.6 记录测量、边界、容量差距与外推限制。产品路径从 S5 到 M 的 diff 为空，未重测。 |
| 4 语义回归与最终门禁 | **成立（现有测试范围内）** | M 上 fresh image、五包 ruff/mypy、全量 runner 5419 passed/1 host-only skipped；Compose 0 skipped。测试覆盖缺口独立列为 EXIT-F2，不用 exit 0 消除它。 |
| 5 baseline 清空或逐条 owning 登记 | **成立** | `IMPORT_RULE_BASELINE` 空、`RUNTIME_CYCLE_BASELINE` 空，仅两组 6 个不可达模块；ct108 `python -m tests.support.import_rules` 为 0/0/6；每个模块 owner/reason/reopen 见 §6.1。 |

### 3.2 §2A.4、§2A.4.1 逐行处置

以下“成立”指该行指定处置在 M 中成立，不代表整个 P5 通过。语义补充逐项接续在 §3.4，避免只引用阶段报告。

| 原清单行 | 结果 | 处置位置与源码事实 |
| --- | --- | --- |
| §2A.4-1 业务 port 泄漏 VersionedOperation / wire | 成立 | `B/application/submission/ports.py:274` 使用业务结果；`B/infrastructure/repository_write/wire_codec.py:45` 构造请求 bytes、`:62` 映射 wire operation；`http.py:114` 发送同一请求证据。wire 归 adapter，不在 Submit job 编解码。 |
| §2A.4-2 HTTP/read adapter 导入 capability 私有实现 | 成立 | `B/application/workspace/upload_admission.py:8`、`:39` 使用 Source Package 公共入口；`B/infrastructure/repository_read/http_arrow.py` 使用 Snapshot 公共类型/协议，不再从 `_digest` 重建摘要；0 import violation。 |
| §2A.4-3 finalize/abort transaction 反向依赖 job helper | 成立 | `B/application/submission/artifact_release.py:14` 为用例内下层 owner，finalize/abort 消费它；无 runtime cycle。 |
| §2A.4-4 basename 豁免与漏检 | 成立 | `T/support/import_rules.py:314` 分类、`:353` 精确公共面、`:380` 运行时环；`:166` 区分 TYPE_CHECKING；`T/test_architecture.py:809`、`:825`、`:836` 为统一测试 owner。无按 basename/整层放行。 |
| §2A.4-5 nominal ref 基础层倒挂 | 成立 | `B/artifacts/nominal_refs.py` 不再依赖 Submission Domain；`B/application/submission/artifact_refs.py:12` 持有跨层转换，Backend 与 Repository ref 类型仍分开。 |
| §2A.4-6 canonicalization 根模块/Submit adapter 混放 | 成立 | 根模块删除；`B/infrastructure/repository_write/import_publication.py:114` 实现 publication port；media type 与 manifest 属 Storage Projection；`:283` 从冻结产物恢复投影，不重新按运行期规则投影。Rust row-hash 迁位并登记延期。 |
| §2A.4-7 契约公共面与执行实现区分 | 成立 | contracts 叶子门禁；`snapshot_materialization/contracts.py:575`、`:599` 的纯规范摘要及后续 codec 仍属类型/编码 owner；执行走 facade。未把纯 codec、validator 或 facade lazy import 当作架构缺陷。 |
| §2A.4-8 Preview/Submit 编排集中与 Comparison 流程词 | 成立 | `B/application/job_steps.py:25`、`:60`、`:71` 共享步骤胶水；`pair_pipeline.py:109`、`:175` 共用计算流程；Submission 自有 import_builder/transactions；ComparisonRequest 为快照/规则/模式/选项。保留大的 job 模块有用例恢复职责，不按行数强拆。 |
| §2A.4-9 comparison_projection/business_projection 占位 | 成立 | 两者删除；Table Rules 的 ComparisonRuleView 接实际 Preview/History 消费者；Project Identity 有生产调用；`T/test_architecture.py:214`、`:235` owner/DAG 同步。 |
| §2A.4.1-1 表策略无 owner、Preview/History 不一致 | 成立 | `B/capabilities/comparison/pair_planning.py:33`、`:87` 从运行期 Table Rules 派生视图；共同 pair pipeline；`T/test_table_rules_comparison_view.py:14`、`test_comparison_rule_roles.py:90`/`:126`。ADDITIVE 跨 provenance 的专门验收另见 EXIT-F2。 |
| §2A.4.1-2 step/summary codec 复制 | 成立 | job_steps 与 pair_pipeline 共享；Snapshot/Summary codec 归 snapshot_materialization/contracts；`T/test_canonical_state_identity.py:259` 验证 round-trip 与 schema 摘要。 |
| §2A.4.1-3 hidden summary 重建/双遍扫描 | 成立 | `B/application/canonical_metadata/binding.py:42` 从 manifest 绑定；`B/infrastructure/control_db/sqlite_commit_metadata.py:39` 按 repo/commit/scope 查询；`B/capabilities/snapshot_materialization/repository_ref.py:194` catalog、`:217` 单次逐表读取。P3-R3 正式取代标注与 ADR0019 已落文档。 |
| §2A.4.1-4 固定 SAME_PROJECT、替换/continuation 无生产者 | 成立 | `B/capabilities/project_identity/_rule.py:55` 真实评估；`pair_pipeline.py:93` 接线，替换模式实际产出 facts/risk/surface；身份确认由 Submit 收集，Archive 处置；无 continuation 或 ARCHIVE_REPLAY 假入口。 |
| §2A.4.1-5 HTTP 受理/组合根/持久适配器 | 成立 | `B/application/workspace/preview.py:75`、`application/history/compare.py:66` 受理；`bootstrap/composition.py:182` 装配 registry；History 持久读取归 infrastructure；`http/runtime.py` 已删除。 |
| §2A.4.1-6 Submission ports 跨域 UoW 枢纽 | 成立 | `B/application/control_transactions.py:15` 最小共享协议；workspace/submission/archive/history 各自 ports，bootstrap/control_db 组合；无 runtime cycle。 |
| §2A.4.1-7 Operations 私有 validator | 成立 | `B/operations/contracts.py:1053` 公共 `validate_json_structure`；消费者不绕入私有实现。 |
| §2A.4.1-8 cache/provider/synthetic/composite 不可达与 XML 忽略 | 成立 | cache/provider/占位/生产 synthetic 桩删除；composite、XML 经 Preview 业务物化到 canonical state；只剩 §6.1 已登记两组。 |
| §2A.4.1-9 compare_jobs/control_db basename 豁免 | 成立 | 同统一 import rules 与实跑 0/0/6；不以 `*_jobs.py` 或 transaction 通配替代旧豁免。 |
| 第二轮-1 上传原始域 vs 基线规范域 | 成立 | §3.4 R1；上传先业务物化再规范投影，Repository baseline canonical binding；规范同一性与同内容比较 owner 均通过。 |
| 第二轮-2 SKIP/SNAPSHOT_ONLY/BROWSE_ONLY/UPDATE_ONLY | 成立 | §3.4 R2；表级事实、schema facts 与 ordered 位置语义进入 shared pipeline。 |
| 第二轮-3 NO_CANONICAL_CHANGE 使用 bundle 且同步重物化 | 成立 | §3.4 R3；`B/application/submission/accept.py:264` 比较持久规范状态摘要；拒绝无变化不解析 main/重物化基线。 |
| 第二轮-4 hidden summary 当前版本掩盖历史版本 | 成立 | §3.4 R4；manifest 历史字段保留，解码不锁死当前常量；当前规则仍控制比较。新任务旧基线的验收缺口见 EXIT-F2。 |
| 第二轮-5 XML 不进入状态 | 成立 | §3.4 R5；composite 进入存储/比较/状态摘要，解析错误失败，缺失使用 EMPTY。 |
| S0 补充：SET 编码 | 成立 | §3.4 E-c，共享类型编码与真实 Dolt 往返。 |
| S0 补充：schema 未进入状态/提前退出 | 成立 | §3.4 E-e，business schema 与 manifest schema 各有 owner，列序区别明确。 |
| S0 补充：ordered no 忽略且结构冲突 | 成立 | §3.4 E-g，no 保留作位置结构，非 ignored。 |
| S0 补充：Submit 无法删表 | 成立 | §3.4 E-f，完整状态与 frozen expected parent 决定删表。 |
| S0 补充：初始基线不保证空 | 成立 | §3.4 E-h，读取后拒绝用户表，compose 默认空初始库。 |

### 3.3 实际消费者与保留的公开语义

| 保留面 | Owner、实际消费者和理由 | 结论 |
| --- | --- | --- |
| facade + contracts；纯 codec/validator/摘要 | 各 capability owner；Application/adapter 消费 typed 契约。Snapshot codec/digest 属规范表达，不运行 parser、Repository I/O 或本 owner 执行算法；facade 可 lazy 加载执行。 | 成立；contracts 叶子规则与 DAG 保留。 |
| Comparison 的 opaque pair_id | Comparison，供 Application 把结果关联到 pair；ADR0021 Decision 1 明确允许；`B/capabilities/comparison/contracts.py:932`。不携带 pair role/view/applicability/身份确认。 | 有 owner 与理由，不能把不透明关联 ID 当流程词汇违规。 |
| ProjectIdentityAssessment 与替换模式 | Project Identity 只依赖 Snapshot；Application 将三态评估转为 DETAILED/DATASET_REPLACEMENT，并映射 Surface 自有标注。Review 只读展示确认，Archive 要求处置。 | 不再是假公开面；S4 测试及本次 Compose 覆盖。 |
| HistoryIntegrityFailure、Operation integrity | History projection/cursor 一致性、Operations 权威 effect/CAS 的现有消费者；ADR0019 明确保留。 | hidden-summary incident 删除不等于删除这些语义。 |
| StorageRuleView / ComparisonRuleView | Table Rules；前者由投影/import 使用，后者由 Comparison 使用；各自 digest，运行期比较与历史存储 provenance 分离。 | 删除 projection 占位后 owning 文档/DAG 已对齐。 |
| ordered 空白行字段变化不比较，但内容仍存储 | Ordered Comparison / Table Rules；治理计划 G8 的 2026-10-11 owner 决议接受：空白行字段变化可使 Preview 无变化、规范内容摘要变化而 Submit 生成版本；空白行增删仍体现。 | 是显式接受的比较与存储语义区别，不能把所有 Preview UNCHANGED 一概等同 NO_CANONICAL_CHANGE。 |
| Rust row-hash 精确 ext:compute 边 | Backend Architecture；仅该 capability 单一 Rust production provider，contracts 本身不加载扩展。现在无生产 journey，登记 Phase 6。 | 精确放行有理由；不是整层豁免，不伪称已集成。 |
| external_target_sync 契约/参考执行器 | Mutation Planning；等待真实 external-target Contract 与消费者。 | 保留为登记延期，不列为已交付业务旅程。 |

### 3.4 设计 §2.1、§2.2 的语义缺陷与权威测试 owner

表中每个不变量列它的权威 owner；跨入口接线测试证明不同边界，不把同一不变量重复指定多个 owner。所有列出的 M 测试文件均在本次全量 runner 范围内。

| ID | 结果、实现位置 | 权威测试及其证明范围 |
| --- | --- | --- |
| R1 规范域不一致 | 成立；`B/application/preview_jobs.py:1172`、`:1239`、`:1254`；Repository 路径用 canonical binding | `T/test_comparison_canonical_domain.py:23::test_identical_uploaded_initial_and_repository_baseline_compare_unchanged`。两条路径 descriptor/内容往返同一性另由 `test_canonical_snapshot_identity.py:201::test_canonical_snapshot_identity` 唯一拥有。 |
| R2 角色语义失效 | 成立；comparison pair_planning/standard/ordered 消费 ComparisonRuleView | `T/test_comparison_rule_roles.py:90::test_non_record_roles_publish_content_change_facts_without_row_records`、`:108` 存在性、`:126` schema 参数表；视图派生归 `test_table_rules_comparison_view.py:14`。 |
| R3 无变化判定错误且过重 | 成立；`B/application/submission/accept.py:264` | `T/test_submit_transactions.py:2168::test_t1_rejects_no_canonical_change_without_main_resolve_or_writes`，以及 `:2203`、`:2288` 判定顺序；不再以 bundle 摘要或基线自比证明状态相等。 |
| R4 summary 双读/版本伪 provenance | 成立；repository_ref 单遍与 SQLite commit metadata | 协议 owner `T/test_repository_ref_materialization_protocol.py:104::test_materialize_loads_catalog_once`、`:127::test_catalog_row_count_mismatch_is_a_regular_failure`；元数据权威归 `test_commit_canonical_metadata.py:200` scope、`:292` digest/log/metric、`:328::test_historical_manifest_versions_are_returned_as_provenance`。新 Preview 对旧基线的激活场景不在这些测试范围内，见 EXIT-F2。 |
| R5 XML 忽略 | 成立；`preview_jobs.py:1195`–`:1229` 接业务物化；`snapshot_materialization/compose.py:89`、`:178` 派生 schema/长度 | capability 业务 owner `test_snapshot_materialization_business.py`；Preview 接线 owner `test_preview_job_materialize.py:249::test_invalid_logics_xml_fails_preview_with_public_diagnostic`、`:283::test_missing_logics_xml_materializes_stable_empty_source`；规范往返 owner 同 R1。 |
| R6 身份固定/替换无事实 | 成立；project_identity/_rule、pair_pipeline、Submission/Archive 接线 | `T/test_project_identity.py:164::test_identity_assessment_compares_complete_version_manager_entries`、`:223::test_project_identity_matches_between_sql_and_repository_materialization`；替换产物 owner `test_comparison_replacement.py:109`/`:128`/`:156`；确认与归档分别由 test_submit_transactions、test_archive_transactions 拥有。 |
| E-a 类型词表/降级描述符 | **部分成立**；类型扩充、keyless 决议与 capability 聚合已落实；Preview 聚合输出未落实 | `T/test_storage_projection_core.py:325::test_storage_vocabulary_accepts_observed_unsigned_float_and_datetime_types`、`:398::test_projection_collects_schema_failures_for_every_table_and_column`、`:836` keyless 不去重；业务边界 EXIT-F1。 |
| E-b TEXT/前缀/nullable key 与 JSON | 成立；投影拒绝不可索引键，键 NOT NULL；DC12 无 JSON 分支 | `T/test_storage_projection_core.py:365::test_key_columns_reject_storage_types_that_repository_cannot_index`、`:382::test_json_remains_fail_closed_without_dc12_evidence`；Dolt 往返由规范同一性 owner 验证已支持类型。 |
| E-c SET list 与 SqlSetValue 编码差异 | 成立；Snapshot scalar decoder 统一 | `T/test_snapshot_materialization_contracts.py:131::test_repository_set_decoding_uses_declared_label_order` 为纯编码 owner；真实传输归 canonical_snapshot_identity。 |
| E-d DDL descriptor/伪 gid/列序摘要 | 成立；规范 descriptor，列序无关 business identity | `T/test_storage_projection_core.py:196::test_canonical_table_projection_emits_canonical_descriptor_and_reader`；跨路径与伪 gid 往返归 canonical_snapshot_identity。 |
| E-e schema 缺失/F11 | 成立；`snapshot_materialization/contracts.py:575`、`:599`；`comparison/row_encoding.py:405` early exit 加 business schema；standard/ordered 同样处理 | `T/test_canonical_state_identity.py:172::test_business_schema_digest_tracks_business_definition` 参数表含空表增列、类型、长度、可空性、键序、列序；`:191` 状态摘要。comparison schema 来源由 `test_comparison_planning.py:172::test_schema_change_source_uses_only_persisted_rule_side_facts`、standard/ordered 既有 schema 测试覆盖。 |
| E-f 完整状态删表/启发式冻结 | 成立；`B/application/submission/import_builder.py:40` derive_removed_tables；T1 冻结闭包，prepare 读 frozen expected parent | `T/test_submit_prepare_removed_tables.py:95::test_prepare_removes_parent_tables_omitted_from_frozen_canonical_state` 三类 integration 参数；checkpoint 复用 owner `test_submit_job_prepare.py:445`。 |
| E-g ordered no 冲突 | 成立；Table Rules 结构列与 compare-excluded 校验分离 | `T/test_table_rules_comparison_view.py:14` 为规则 owner；ordered 算法既有测试消费此视图。 |
| E-h 非空 INITIAL | 成立；`B/capabilities/snapshot_materialization/repository_ref.py:202` 拒绝非零表 | Preview owner `T/test_preview_job_materialize.py:153::test_initial_baseline_rejects_repository_user_tables`；协议入口 owner `test_repository_ref_materialization_protocol.py:145` 不混成另一个业务判定。 |
| E-i import 渲染/发布职责与重新投影 | 成立；Storage Projection 拥有 schema/package；Mutation Planning 拥有 DML；`import_publication.py:145`、`:283` 组装冻结内容 | `T/test_submit_job_prepare.py:351::test_submit_prepare_recovers_from_frozen_t1_artifacts_after_ruleset_activation`；`test_submit_import_builder.py` 冻结 bytes/golden/激活测试，既有 Storage Projection/Mutation Planning 分别拥有各自编码断言。 |

Preview 与 History 共用 canonical materialization、运行期 ComparisonRuleView 和 pair pipeline；Submit 使用 Preview 已冻结的 canonical closure/manifest，`NO_CANONICAL_CHANGE` 比较同一 business schema/content 状态摘要。普通同规则路径及真实链路的一致性成立；不能据此扩大为“所有激活/失败分支已验收”，EXIT-F1/F2 明确限制了该结论。

**S0 不得延期的四项：**

| S0 项 | M 的处置与结论 |
| --- | --- |
| F1 规则激活/provenance | 源码、Contract 方向已改；旧 Preview 拒绝、旧任务恢复失败、Submit frozen products 测试存在；ADDITIVE 新 Preview 旧基线缺验收，**部分成立、阻塞 EXIT-F2**，没有延期到 Phase 6。 |
| F3 T1 冻结/expected parent/删表 | 上述 E-f/E-i、Submit artifact protection、prepare binding tests；**成立**。 |
| F4 上游 Contract 先行修订 | §3.5 逐条文档已经落地，历史正文有取代说明；**成立**。现行版本标头偏差另列非阻塞 EXIT-F3，不据此否定所有上游修订。 |
| F11 schema/state/early exit | 上述 E-e 与 canonical identity tests；**成立**。列序不属业务状态，但 manifest schema 仍保持 DDL 列序，两者未混用。 |

### 3.5 ADR、设计 §11 与附录 A/B 的逐文档核对

| 修订入口 / owner | M 处置位置 | 与实现一致性、是否仍有未修订项 |
| --- | --- | --- |
| ADR0018；Snapshot/Table Rules/Storage Projection/Comparison | `F/adr/0018-canonical-domain-comparison-and-comparison-rule-view.md` Accepted；规范域、视图、角色、type/schema/column-order 条款 | 主体实现一致；DC14 应执行的条款未被源码兑现（EXIT-F1），不是缺少 Contract 文本。 |
| ADR0019；Snapshot/Submission/History | `F/adr/0019-commit-canonical-metadata-authority.md` Decision 1–7、Required Verification | manifest authority、单遍、INITIAL、stale/recovery、incident 收缩一致；验证缺口 EXIT-F2。Consequences 的 migration 旧文已有 G3 supersession 注释。 |
| ADR0020；Project Identity/Application | `F/adr/0020-project-identity-and-dataset-replacement-in-p5.md`；project_identity、Submission confirmations、Archive identity subject | 已实现三态、首次 NOT_APPLICABLE、不同项目不可改判、两个确认独立、Review 只读与归档处置。 |
| ADR0021；Comparison/Application | `F/adr/0021-flow-neutral-comparison-entry.md:29`；ComparisonRequest、pair_pipeline | 已删除 flow/view/continuation 输入；保留 opaque pair_id 有明确依据。 |
| §11 P3-R3 hidden summary；Snapshot | `P/p3-capability-foundation-design.md:154` | 已按规则加 ADR0019 取代标注；不改写历史正文。 |
| §11 P3-R4 列处置；Table Rules | `P/p3-r4-storage-projection-design.md:164`、`:236` | ADR0018/DC29 取代标注存在；no/compare-excluded/keyless 与实现一致。 |
| §11 P3-R5 identity/流程词；Comparison | `P/p3-r5-comparison-design.md:5`、`:79`、`:100`、`:143`、`:184` | 已按 ADR0018/0020/0021 标注取代；不是仍需维持旧 continuation。 |
| 附录 A.1 INITIAL；Lifecycle | `F/contracts/business-lifecycle-and-state.md` §1A.2；repository_ref INITIAL 检查 | 已并入；非空初始库不受支持。 |
| 附录 A.2 Preview 绑定/规范域/DC14/XML | 同 Contract `:144`、`:153`、`:157` | 已并入；仅 DC14 实现不符（EXIT-F1）。 |
| 附录 A.3 状态摘要/stale/双确认/T1 完整状态 | 同 Contract §3（`:175` 起）；accept/accept_transaction、prepare | 已并入；源码冻结、摘要判定与删除语义一致。 |
| 附录 A.4 Review 只读确认 | 同 Contract `:222`；Review 投影/HTTP schema | 已并入；没有新增 Review 再确认交互。 |
| 附录 A.5 Archive 身份异常 | 同 Contract `:243`；archive/audit、test_archive_transactions | 已并入；选定 Submission 的确认需肯定处置。 |
| 附录 A.6 History 运行期比较 | 同 Contract §6；History compare 与 pair pipeline | 已并入；节点 manifest 是存储 provenance，比较用当前规则。 |
| B.1 Canonical Storage §2/§4/版本 | `F/contracts/canonical-storage-and-repository-boundary.md:37`、`:54`、§4、`:245`、`:254` | 视图、列角色、两种 schema digest 与 3.2.0/DC29 均已并入；**未同步标头 :13**，EXIT-F3 非阻塞。DC12 未触发，但负零修复使 projection version 为 2。 |
| B.2 Ruleset Activation §1/§5；Ruleset/Application | `F/contracts/ruleset-activation-and-migration.md:23`、`:77` | drain/restart、纯计算 mismatch 失败、effect 用 frozen products 均已并入；DC23 取代早期“§5 无需修订”意见。 |
| B.3 ADR0016 与 Operation Lifecycle；Operations | ADR0016 状态下有 ADR0019 范围澄清；`F/contracts/operation-lifecycle-and-integrity.md:75` | 普通读取/自有 manifest 损坏不造 incident，T3 回显/CAS 歧义仍强保护；实现与测试一致。 |
| B.4 Taxonomy §4.4/§4.6/§5/§13；Architecture/各 owner | `F/contracts/contract-taxonomy-and-ownership.md:195`、`:398`、`:651`，artifact owner 表 | DAG 更新、projection/hidden summary owner 删除、ComparisonRuleView/ProjectIdentity 新 owner、旧 Phase1A 注释存在；缓存归属保留不代表已落地 cache consumer。 |
| B.5 P5 §2A.2/§2A.4/§6.1；Application/Architecture | `P/p5-business-vertical-slices-design.md:155`、`:199`、§6.1 | 已改规范公共面、adapter 归位及 XML 非可选；过期授权状态另列 §7。 |
| B.6 Architecture §7.1/§7.2/§9.1/§10/§13 | `F/architecture/architecture-and-refactoring-plan.md:350`、`:377`、§9.1、`:596`、§13 | 目标 DAG/目录/规则视图已修订，test_architecture owner/DAG 同步；进度文本过期另列 §7。 |
| §11 5E §6.6；History | `P/p5-5e-history-compare-design.md:326` | incident/ack/v6 的取代标注存在；M 删除其实现，保留 HistoryIntegrityFailure 与 Operations integrity。 |

未发现附录 A/B 或 §11 的整个必改条款尚未并入。未完成的现行标头修订见 EXIT-F3；历史文档不是因保留旧正文就构成缺陷，取代标注优先。非 formal 的 `docs/backend-vnext/capabilities/snapshot-materialization.md:78`、`:352` 仍讲 hidden summary，宜补来源/取代提示（§7），不能用它反向恢复已撤销机制。

### 3.6 依赖、S5 测量与产品覆盖

S5 相对 `p5-s4-exit` 的依赖清单只有 Backend dev group 新增 `blake3==1.0.10`（`vnext/backend/pyproject.toml:38` 及锁）；没有新增 production 依赖。G11 的 `pytest-xdist==3.8.0` 是更早经治理授权的 dev 依赖，不冒充 S5 新增。各包静态与锁受控消费通过；没有在本审核改依赖或锁。

`P/p5-arch-closure-s5-handoff.md` §8–§11 交付了完整旅程与 DC32 分段/逐表/基本吞吐输入：18 个场景、17,435 条 coverage 记录（11,907 measured、5,519 shared、9 N/A），用户可见时间、operation terminal 与核对完成区分；Submit parent/child、outer/inner 不重复相加。S5 最终门禁 V 为 `55a8b810249649b403339d406cd2b5744feb7863`，其完整真实 journey 沿用 `b79844ddc2` 的许可与差异范围见 S5 最终复审；本次只读 handoff/源码，不读取外部真实数据或重算其测量。

| 已交付证据 | 数值与解释 |
| --- | --- |
| t4 Preview 终态 | v1 1684.782 s；同内容重传 1463.686 s；低变化 v2 1477.774 s（changed 26/312）。不把 result GET 后核对时间当终态。 |
| B 层成本 | 独立 capability 测量的 parse 140.498 s、business materialization 211.540 s、projection/digest 218.977 s、projected snapshot write 153.334 s；边界不同，不能相加替代 operation wall。 |
| Repository / 转换 | 312 次逐表 Arrow read 合计 51.847 s，Arrow→Python 1.492 s；未按行发 Repository 请求。 |
| Submit 成本 | v1/v2 non-overlap 337.281/334.758 s；adapter outer 373.980/369.456 s，不能再加内层。真实 RS import 79/83 s、各使用 2/3 个会话，是另一测量边界。 |
| 容量差距 | 2×t4 线性估算 3369.564 s（56.16 分钟），较 600 s 多 2769.564 s，约 5.62 倍。**没有实测 2×**；单点、变化比例、缓存、并发、CPU/I/O 限制外推。DC31/DC32 要求 Phase 6 先测下界再定目标，不是 P5 性能失败阈值。 |
| 字节余量 | replay SQL 2×外推 v1/v2 为 101,132,094/101,145,128 B，低于 200 MiB，余 108,583,106/108,570,072 B；Catalog 572,274 B，低于 2 MiB，余 1,524,878 B。容量不能由这些单点余量保证。 |
| Phase 6 输入 | parser/native Arrow、business/canonical digest/artifact row handling、重复/低变化逐表复用、ordered/standard CPU 与表级并发、Submit planning/render/Repository 边界分别优化。无性能平台或生产 BLAKE3 依赖承诺。 |

ct108 `04-postflight-provenance.log` 中以下 diff **输出为空且 quiet 校验 exit 0**：

```bash
git diff --stat p5-s5-exit..HEAD -- \
  'vnext/*/src/**' 'vnext/rust/**' 'vnext/deploy/**' \
  ':(glob)**/Dockerfile*' ':(glob)**/uv.lock' \
  ':(glob)**/Cargo.lock' ':(glob)**/pyproject.toml'
```

故 S5 真实数据证据仍覆盖 M 产品代码；没有触发“产品变化即停”的条件。`b93748c04e..M -- vnext AGENTS.md` 也为空，但旧 V worktree 已删除，本次没有利用它声明 carried。

## 4. 实际执行的检查

### 4.1 环境、顺序与日志

专用节点通过 `ssh -o BatchMode=yes ct108-gw-dms` 连接。以 bundle（基于 ct108 main `0af39a22f6`，正引用 `p5-exit-review`）经 scp/fetch 同步 M，没有通过 GitHub，没有移动 ct108 main。detached gate worktree HEAD 始终 M，并建立 legacy 链接。

实际测试环境：umask 022；`HOME=/root`、`LC_ALL=C.UTF-8`、`PATH=/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`、`TMPDIR=/home/dev/gdds-test-tmp`、`GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`；未设置 `UV_CACHE_DIR`、`GATEWAY_TEST_PACKAGES`、`HYPOTHESIS_STORAGE_DIRECTORY`、`GATEWAY_TEST_BASETEMP`。runner 自己逐包设置 Hypothesis 路径；全量时 `GATEWAY_TEST_WORKERS=48`。

全部日志位于 ct108 **`/home/dev/gdds-p5-closure-s1-gate-logs/p5-exit/`**，目录 700，文件显式 chmod 600。日志记 umask、起止 HEAD、起止 status、exit code；清理日志在删除前记录末次 HEAD/status，再记录 remove 的 exit code。测试期间没有写源码、提交或手工重打镜像 tag。

| 顺序 / 日志 | 命令或检查 | 实际结果 |
| --- | --- | --- |
| `01-preflight-static.log` | clean M；按进程名 `pgrep -x dolt`；`docker ps -aq`；`docker compose ls --all --format json`；`ss -H -ltn 'sport = :8000'` | 无 Dolt、无任何容器、Compose `[]`、端口空闲；legacy/TMPDIR 存在。 |
| 同日志 | 五包各自 `../scripts/uv-consume.sh -C . run ruff check .` 与 `run mypy` | ruff 全通过；mypy shared_kernel 34、repository_contracts 15、repository_client 26、backend 486、repository_service 200 个文件，无错误。 |
| 同日志 | Backend 目录 `../scripts/uv-consume.sh -C . run python -m tests.support.import_rules` | import 0、runtime cycle 0、unreachable 6；仅 §6.1 两组。exit 0，起止 M/clean。 |
| `02-build-rs.log` | `./vnext/scripts/build-repository-service-image.sh`；identity helper；docker labels 断言 | fresh M build 成功；candidate、revision、build-input/source-tree 核对一致；exit 0，起止 M/clean。 |
| `03-runner.log` | 再核 preflight；`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` | 所有包实际运行、无 carried；runner exit 0，起止 M/clean。完整计数见下。 |
| `04-postflight-provenance.log` | Dolt/容器/Compose/8000、worktree、Hypothesis、镜像 identity、provenance、S5 产品 diff、prepare 修复祖先 | 全通过；无残留包目录，产品 diff 空。exit 0，起止 M/clean。 |
| `05-cleanup.log` | `git worktree remove /home/dev/gdds-p5-exit-gate` | exit 0，路径已不存在；日志保留，未删除镜像/缓存。 |

无实际门禁检查失败，没有调试或重跑。bundle 创建时把 raw SHA 改为可打包的命名正引用属于同步准备；不作为测试失败、测试重跑或 carried 证据。

### 4.2 runner 与 Compose 跳过核对

| 包 / 批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend parallel | 2897 passed，48 warnings |
| backend serial | 39 passed，2897 deselected，1 warning；1587.40 s |
| repository_service parallel | 1730 passed，**1 skipped** |
| repository_service serial | 205 passed，1731 deselected；593.00 s |
| 合计 | **5419 passed，1 skipped；runner exit 0** |

唯一 skipped 对应 `vnext/repository_service/tests/test_p2_r1_target_cgroup_smoke.py:11::test_target_container_has_real_delegated_cgroup`，skipif 条件是 `GATEWAY_P2R1_TARGET_CONTAINER != "1"`，理由为 “runs only inside the delegated target container”。本次 host 环境未设置该变量，runner 不为 host pytest 设置它。定位依据是 M 的确定性 skip 条件、实际环境及整个并行批次只有 1 skipped；runner 的简略输出没有逐条 skip nodeid，所以这里明确给出关联方法，不声称日志打印了 nodeid。该文件不是 Compose journey。

实际 Compose 文件都进入 serial 批次，两个 serial 批次均 **0 skipped**：Backend 的 `test_archive_compose_e2e.py`、`test_backend_http_container_gate.py`、`test_history_compose_e2e.py`、`test_ordered_compare_compose.py`、`test_ordered_submit_bisect_compose.py`、`test_review_compose_e2e.py`、`test_submit_compose_e2e.py`；Repository Service 的 `test_compose_lifecycle_negative_probes.py`、`test_import_compose_e2e.py`、`test_versioned_read_compose_e2e.py`。未再单独重跑这些旅程。

runner 起始逐包 storage 为不存在；退出统一清理。postflight 五个 `<TMPDIR>/gateway-runner-hypothesis/<包名>` 均不存在，storage root 下没有子项；worktree clean。没有把测试后重新产生的缓存作为可沿用状态。

### 4.3 镜像身份、provenance 与 prepare checkpoint 延期关闭

| 项 | 实际值 |
| --- | --- |
| RS `org.opencontainers.image.revision` / identity candidate | `8ec03b5d75481c4cc2ffeb59d11befc7fa106233` |
| RS build-input-revision | `b93748c04e63be4eeece66cb5abaadf13fd7b6d3` |
| RS source-tree-sha256 | `sha256:b24fa92dbbb59d00617eec838a22ca947fa98fe42fab996770aa9b9e20f7f15c` |
| RS image ID | `sha256:55cdb23e64a24527f5f1b0fd1bc74abcebe4284c32ff70839307639cc268c10f` |
| 最后一份 Backend Compose provenance 的 backend image | `sha256:e210ffc4815b83f785d4cedea5acf05b93d0c3ff794d2f2806a943d3fdb690c4` |
| 同 provenance 的 worker image | `sha256:2ed299dc7018bdd75f1c2329bb33653f006ee722c8710514dc9c4a7f9ce13eaf` |

build-input 指向 G13 V 是身份算法的产品输入结果，并不表示复用了旧门禁。RS 实际在 M 重建；backend/worker 由本次 runner 的 Compose harness 构建并核对运行镜像。`T/support/compose_gate_harness.py:602` 在持久化 provenance 时核对 RS labels，后续函数核对 running backend/worker image。默认 provenance 文件只保留最后一个 journey 的快照，本次将其内容收入 `04` 日志；没有把这份快照冒充所有 journey 的独立明细，全部旅程的通过证据在 `03`。

`git merge-base --is-ancestor 0d9d0d9dc5 M` 在 ct108 返回 0。该 prepare checkpoint 修复进入后续 S2b 的重建与容器验收（S2b handoff 的 checkpoint 修订记录），且本次 M 再次 fresh build/full runner，明确覆盖现行代码。`T/test_submit_job_prepare.py:643::test_prepare_checkpoint_payload_binding_mismatch_aborts_prepared_attempt`、`:687::test_prepare_checkpoint_schema_mismatch_retains_occupancy`、`:726::test_prepare_checkpoint_payload_binding_mismatch_worker_aborts_and_allows_reaccept` 在全量范围内；P5 §13 旧“容器门禁仍延期”已不成立，不再带出。

日志 SHA-256（便于定位本次证据，不新建 evidence 机制）：

| 日志 | SHA-256 |
| --- | --- |
| 01 | `88c52cad0a8e186f9d2a6d6d22d51f35289df718284750b4002d94d579e751cd` |
| 02 | `39550bdb5358a2d77464dc3f3f20bbdd966af8ab194c77d6d3ee324eb141833a` |
| 03 | `3f275d8c7e384dc00a2197474ac9a98bf0a35f0171de5ffcc5690441b037db01` |
| 04 | `6c0716b04db3c0f45168b23473654011385f9e768c1358dba27773acdc52e039` |
| 05 | `efa231a7ae84d940a178ed9fe1224d93e947388e57ecc114dd3e42c3a4f4ed9d` |

## 5. 验证限制与剩余前置

- 只有 EXIT-F1、EXIT-F2 是本次整体 exit 的阻塞前置；不能把它们登记到 Phase 6 后宣布通过。修订后按影响面复审及最终候选门禁规则验收，本审核未改代码、未复现新测试或自行修正 Contract。
- 真实数据不读取、不解包、不重跑。测量结论依据 M 上 S5 最终 handoff/复审、测量代码边界和产品 diff 覆盖；不声称独立重算原始数据。没有把旧环境“约 60 秒”与本次 operation terminal 作可比性能结论。
- 当前单 host、单 worker、受控同 euid 信任域不变。没有把假设的同 euid 恶意换名、多 worker 或 HA 场景扩成 P5 验收要求。
- 测试门禁不能证明缺失的测试要求，源码审查也不能冒充 ADDITIVE 场景的运行证据。EXIT-F1 为确定的数据流丢失，EXIT-F2 为验收证据缺口，二者性质不同。
- 本报告提交是唯一 tracked 变更；不推送、不打 tag、不合并，不动源码/测试/Contract/ADR/治理正文，不触碰 `refs/codex/...` 或 `refs/archive/...`。G10 已有清理不重复执行；本次只移除新建的 ct108 gate worktree。

## 6. P5 之后的遗留汇总

本节区分已经关闭、owner 明确接受的设计选择、真正延期及缺少处置的建议；不是把所有历史“非阻塞”自动变成待办。EXIT-F1/F2 是 P5 内修订，不列入允许带出的遗留。

### 6.1 六个不可达模块逐条登记

权威登记为 `P/p5-arch-closure-design.md:565`–`:570`，基线为 `T/architecture_baseline.py:22`；本次 import_rules 实测一致。

| 模块（`gateway_backend.capabilities.` 前缀） | Owner | 理由 | 去向 / 重开条件 |
| --- | --- | --- | --- |
| `canonical_row_hash.contracts` | Backend vNext Architecture | 无生产 journey consumer，保留 Rust 计算边界 | Phase 6 选择真实 workload 接入，或确认新的生产 consumer。 |
| `canonical_row_hash.compute` | Backend vNext Architecture | 同组单一 Rust provider，暂未接业务链 | 同上；不得仅为消除不可达数字接假 caller。 |
| `canonical_row_hash.canonical_row_hash_ipc` | Backend vNext Architecture | 同组绑定实现随 owner 保留 | 同上；启用时复用 canonical/golden 与性能验证。 |
| `external_target_sync.contracts` | Mutation Planning | 无已接受生产 external-target journey | 接受 external-target Contract 且有明确生产 consumer 后重开。 |
| `external_target_sync._ledger_digest` | Mutation Planning | 该目标流程尚无 producer/consumer | 同上。 |
| `external_target_sync._reference_executor` | Mutation Planning | 参考执行器不等于生产集成 | 同上。 |

### 6.2 S5、治理与阶段审核的未关闭事项

| 带出项 | Owner / 理由 | 去向、M 核对及状态 |
| --- | --- | --- |
| DC31 B 层与 DC32 容量/Phase 6 候选 | Phase 6 Architecture + 对应 capability owners；P5 正确性通过，结构/常数性能需测量决定 | §3.6 六类候选；`P/p5-arch-closure-s5-handoff.md:403` 起。先测下界再定容量目标；没有承诺现状达到 10 分钟。 |
| 重要 keyless 表是否应定义自然键 | Table Rules + 业务 owner；DC29 保留完整 multiset，不替用户去重 | Owner decisions §12：部署前业务评估；若决定存储键变更，走 owning Contract/storage-breaking 规则。不是 P5 临时补 key。 |
| JSON、新协议/软件版本 | Storage Projection / 数据协议 owner；DC12 当前未发现 JSON，DC22 仅已选样本 | 真实输入出现 JSON 重开 DC12/DC27；新的协议族/版本重跑普查与相关验收，设计 §14。 |
| S3-F2 durable terminal 后 `completed.wait()` 无界 | Operations/Bootstrap；终态已提交但 drain/后续排队可能延迟；部署 180 s 后强制终止 | `B/operations/worker_runtime.py:361` 与 S3 审核 §2/§6；治理计划 §3 第9项接受现状。需要强制 drain 上限时另行授权，不能宣称本次消除了无界等待。 |
| S2b R1-O2 startup 活租约阻断依赖 single worker | Operations/Deployment；当前前提成立 | S2b 复审 §3；Phase 6 若采用多 worker，先重开租约/启动归属判断，不能直接扩副本。 |
| G8a-F1 未扫描却报告 ordered_projection COMPLETE | census 工具 owner；已有完整扫描数字未受影响，但诊断模式失败输入会误报 | `vnext/backend/benchmarks/real_dump_census.py:605` 仍只看 diagnostic_mode/failed_count。原处置为下次 census 使用前修；M 未关闭，保留该节点，不把空明细当成功。原建议 reader 缺失/列缺失两分支参数覆盖亦随工具 owner 处理。 |
| G8b-F2 tie 时绝对 no 未变也可能标 moved | Ordered Comparison owner；相同最优 backbone 的确定性选择 | 治理计划 §3 G8b 记录保留该规则（`:319` 附近）；是 owner 接受的语义折中，不是未修 bug；若业务要求唯一绝对位置解释，重开算法/Contract。 |
| G6b 跨 worktree carried 不可直接复核 | Build/Architecture owner；权限和非 Git context 属输入 | owner 2026-10-11 选 C（计划 `:121`），DC34 后用同 worktree manifest，不比 containerd image ID。本次旧 worktree 删除，按任务明确选择 fresh。再次因跨 worktree 多跑全量已触及原重新评估条件，统一 exit 时应回到 owner 评估 A；本审核无权自行实施 label 方案。 |
| G11 R2-O2 三项 SQLite 并发测试隐含 5 s busy_timeout | Backend 测试 owner；两次阶段门禁及本次通过，不等于无时序依赖 | 原审核 `:81` 已给条件：出现不稳定就移回 serial；登记重开条件成立。 |
| G11 R2-O3 子进程测试误归 unit | 未找到后续明确处置节点；建议 Backend 测试 owner | `T/test_http_admission_shutdown_process.py:31` 仍 serial-only；EXIT-F4，建议下次 marker 整理接受/修订。 |
| G11b-O2 服务端 operation 耗时归因未实测 | Test Infrastructure / 性能诊断；旧门禁轮询时间不能断言全是异步执行 | 保留为下次门禁性能分析的测量限制，非产品容量证据；不以 S5 产品 import 测量冒充当时所有测试服务端测量。 |
| G11b-O3 两路 Compose 并发优化 | Build/Test Infrastructure + repository owner；预计收益小且涉及端口/锁/URL | 保持当前串行，须 owner 另立步骤才实施；不是退出前置。 |
| S2b R1-O3 可选 ADDED/REMOVED 表数对照 | 真实链路测量 owner；未观测的差值不能猜作事实 | 原处置为 S5 或后续真实数据核对；M 的 S5 handoff 未明确关闭该具体差值解释，保留到下一次相关真实链路复核，不重跑本次。 |
| S5 最终 DC32 主日志漏记 umask | 取证执行 owner；历史字段缺失无法事后补证 | S5 复审 §6.2 已接受非阻塞；保留限制，后续启动打印实际值。本次五份日志均记 0022，不能反推旧进程 umask。 |
| 5A 历史 LXC IPv6 黑洞路由 | 测试节点运维 owner；环境问题，不是产品兼容需求 | 仅复发时由节点运维处理；当前 gate 成功，无理由重新改网络。 |
| 5B S7-O1 PRE_REQUEST cross-owner | Submission / Operations；原报告已接受跨 owner 的终态路径 | 保留既有 abort code 约束，属于接受的设计，不新增迁移工作。 |
| 5B S7-O4 abort helper 未导出 `__all__` | Submission Application；当前仅内部消费者 | `B/application/submission/__init__.py` 未提升为 facade；需新增外部公共消费者时重新评估，否则保持内部 owner。 |
| 5B occupancy-assertion-gap / private-process-access | 建议 Submission 测试 owner；旧表只有 deferred，无明确节点 | 当前源码仍在；EXIT-F4。补测试建议不等于已证明 occupancy 错误，也不要求独立安全框架。 |
| 5B shutdown-no-caller | Submission 测试 harness owner；`RepositoryServiceClient.shutdown` 是测试生命周期支撑，无 production caller 是正常边界 | 维持测试支撑用途；只有明确生产 graceful contract 需求才重开。 |
| 5B Repository restart owner 范围 | Submission 拥有 hard-kill 持久性/Backend 消费；Repository Service 拥有服务 startup/graceful lifecycle | 保留既有 owner 分工；本次 RS serial/lifecycle 通过，不要求在 Submit 再复制完整服务恢复测试。 |

已关闭、不再带出的阶段前置：S1 import/私有访问与 composite 接线前置由后续实现和 0/0/6 关闭；G2/G8a 的 legacy 链接已进入 AGENTS 并在本次建立；G3 baseline、S2a 类型/负零、S2b 活租约/取消/公开诊断均有现行代码和测试；G11 R2-O1/G11b 的身份规则经 G12/DC34 落地；G12-F1 runner 自重建镜像使 manifest 失配的根因由 S4 修复；S4-F2 无 consumer 累计预算分支由 S5 删除并显式 import polling budget；S5-F1/F2/F3 修订及其剩余 G10 前置由 G13/G10 完成。5B `defer_operation_terminal` 已有生产 caller（`B/application/submit_jobs.py:2357`、`:2415`），不再保留“无 caller”待办。5A Compose build network 已有 `vnext/deploy/compose.yaml:6` 等接线。5C/5D/5E 的阶段门禁不是本次仍待补的门禁；prepare checkpoint 延期已按 §4.3 关闭。

### 6.3 P5 设计 §12 deferred / reopen 逐条

| 原项 | 当前处置、owner 与去向 |
| --- | --- |
| exact HTTP paths / DTO names | 已在各 Slice 的 HTTP routes/schemas 落地，HTTP/Application owner；本次 OpenAPI/HTTP tests 通过，不再延期。 |
| permission 字符串 | 已落地 Domain/Application 权限检查，例如 `B/domain/workspace/policies.py:41`、`application/history/queries.py:27`；各业务 owner，非开放待定项。 |
| History cursor/page shape | 已落地 `B/http/routes/history.py:72` 与 `application/history/queries.py:25`，History owner；权限/scope/cursor 测试通过。 |
| 固定 TTL 数值 | 已落地 `B/settings.py:19`（unprotected cleanup TTL 86400 s）及相应用例策略；Artifacts/Deployment owner，后续生产调优需按 protection 边界处理。 |
| UI 节点渲染 | Frontend owner；Backend 已供 History/Review/Archive 事实，UI 不在 P5 Backend 退出范围；去向 frontend-vnext 交付。 |
| production-path 容量记录 | S5 已交付记录；达到容量目标与实现优化进入 Phase 6，见 DC31/DC32。 |
| Legacy persistence / Dolt cutover | Repository/Architecture owner；独立未来产品决定。新项目无兼容/迁移目标，不能借此在 P5 建双读。 |
| online ruleset migration | Table Rules/Storage Projection + Operations owner；未来 STORAGE_BREAKING migration 用例，按 Ruleset Activation Contract 重开。 |
| external event consumer | Integration/Application owner；出现真实消费方后单独设计；不是预建 outbox/broker 的授权。 |
| HA / 外部 DB | Architecture/Operations owner；未来部署需求决议，先重开当前 single-host SQLite 事务模型。 |
| 一个 device 多 active project | Workspace/Mapping owner；需求出现即重开 Business Lifecycle scope/映射 Contract。 |
| Upload 要解析 SQL、初始化 Baseline 或写 Repository | Workspace/Source Package owner；重开 Upload admission 边界，当前仍只 admission，Preview 才物化。 |
| Preview 超过固定三步或持久 per-table workflow | Workspace/Operations owner；先重开 JobDefinition/恢复 Contract，Phase 6 优化不自动获得此授权。 |
| Archive 合并 candidate、移动 ref 或产生 commit | Archive/Repository owner；先重开 Archive 无新 effect 的 Contract。 |
| rejected/withdrawn history 删除、rewrite 或跨 scope 读 | History/Security owner；先重开不可变历史与授权边界。 |
| 真 integration-event consumer、多 host writer、HA、broker、外部事务参与者 | Architecture/Operations/相应 Application owner；独立跨服务/事务决定，不能从 P5 exit 推导授权。 |
| business Baseline 与 Repository main 无法保持独立 | Submission/Archive/Repository owner；必须重开两者身份/推进规则，不将 main 偷换成业务 Baseline。 |

以上 §12 的 owner 按现行 owning Contract 职责列出，都是条件重开，不代表后续实现已授权。没有额外未登记的生产功能延期；明确找不到接受节点的旧测试建议已经列入 EXIT-F4。

## 7. 需要更新的状态文本

本节**只列出，不修改**。统一更新由终审方处理；由于本次结论为定向修订，不能将任何入口提前写成“P5 exit pass”。

| 位置 | 过期内容 / 更新方向 |
| --- | --- |
| `P/p5-arch-closure-s0-entry-brief.md:3`、`:155` | “实现未授权”仅是 S0 历史时点；增加当前 S1–S5/G1–G13 已结束、本次整体审核定向修订的状态入口，保留历史授权记录。 |
| `P/p5-arch-closure-execution-plan.md:3`、`:64` | S0/实现待授权状态与后续已完成记录并存；标明当前执行结束、整体 exit 尚有 EXIT-F1/F2。 |
| `P/p5-arch-closure-design.md:3` | 当前状态行仍停在设计接受/未授权；补完成与整体审核链接，不改写设计当时事实。 |
| `P/p5-business-vertical-slices-design.md:245`、§13 `:526` 起 | 下一步仍是 S1 kickoff；更新为整体审核修订。`0d9d0d9dc5` 容器门禁“仍延期”改为已被后续及 M fresh 门禁覆盖（§4.3）。 |
| `F/README.md:71`、`:105`、`:171` 起 | P5/5D/5E 的阶段进度或未授权描述过期；统一链接 Slice exit、S5/G13 与本报告，避免把 Slice pass 当整体 pass。 |
| `F/architecture/architecture-and-refactoring-plan.md:20` 起 | 总纲 P5 进度仍停在早期 5B/5D；更新当前阶段事实。技术 DAG 的修订已落地，不必重写。 |
| `F/contracts/canonical-storage-and-repository-boundary.md:13`、`:249` 附近 | 当前 projection version 标头应为 2（EXIT-F3）；发布实施语态可同步标明已落地，保留版本历史原因。 |
| `docs/backend-vnext/capabilities/snapshot-materialization.md:78`、`:352` | 旧 hidden summary 说明仍无就地提示；补 ADR0019/正式 P3-R3 取代入口，不能改回旧权威模型。 |
| 收口设计 §1 DC 总览、DC26/§9 的“选项”标签 | §1 表止于 DC27，DC28–34 在 owner decisions/后续治理；可补索引。DC26 的精确 Rust 绑定许可与“选项3”不可达延期是两个层次，当前表述宜澄清，不能写成还保留 import violation。 |
| 治理计划 G10 旧清理待办 / §3 第13项 | 当前完成事实以 `:556` 起的 2026-10-23 记录为准；入口标明已完成，不重复执行清理，也不修改历史执行清单。 |
| 旧 5B/G11 deferred register | 按 §6 与 EXIT-F4 更新已关闭 caller 观察、明确剩余建议的 owner/节点；不能把全表历史 deferred 原样带入 P5 后。 |
| G6b 重新评估条件 | 本次因原 gate worktree 已删而 fresh 全量，需在 exit 记录中交 owner 重新评估 A/C；本次已完成的 fresh gate 有效，不以该评估为追加门禁前置。 |

## 8. DC 与治理项核对表

### 8.1 DC1–DC34

“已实现”同时要求源码/测试或消费者事实；“已写入文档”用于范围和条件决议。条件未触发不记成已实现其备选分支。

| 决议 | 状态 / 最终分支 | M 位置与核对 |
| --- | --- | --- |
| DC1 | 已实现；规范域 + ComparisonRuleView | preview_jobs:1239、pair_planning:33；§3.4 R1/R2；placeholder 删除。 |
| DC2 | 已实现；manifest authority，无 hidden table/readback | canonical_metadata/binding:42、sqlite_commit_metadata:39、repository_ref:194；ADR0019/P3-R3 取代。 |
| DC3 | 已实现；三态、Submit 两个独立确认 | project_identity/_rule:55；test_project_identity:164；test_submit_transactions 的身份确认参数表、`:1812` 复制；Archive identity resolution。 |
| DC4 | 已实现；XML/composite 进入业务物化 | preview_jobs:1195；snapshot_materialization/compose:89；test_canonical_snapshot_identity:201 包含 composite。 |
| DC5 | 已实现；comparison 去流程化 | comparison/contracts:932；ADR0021:29；pair_pipeline 负责流程映射，opaque pair_id 合法。 |
| DC6 | 已实现；单一 schema，早期 migration 说法被 G3 取代 | control_db/schema；test_control_db_schema:123、:145、:272；AGENTS；已有部署要保留数据时重开。 |
| DC7 | 已实现；INITIAL pair NOT_APPLICABLE | pair_pipeline:150，初始基线零表；Project Identity 与初始 Compose 旅程。 |
| DC8 | 已实现；坏 XML 导致 FAILED | test_preview_job_materialize:249；业务物化不是可选 XML 降级。 |
| DC9 | 已实现；删除 History compare incident，保留其他 integrity | ADR0019 Decision7、5E设计:326；HistoryIntegrityFailure 及 Operation integrity 仍有消费者。 |
| DC10 | 实现方向与文档已落地，验收部分成立 | 历史 binding 与运行期 pair_planning 分离；缺指定 ADDITIVE Preview 证据，EXIT-F2。早期“Ruleset §5 不改”由 DC23 取代。 |
| DC11 | 已实现；旧 Preview 拒绝、旧纯计算恢复失败、Submit 冻结继续 | test_submit_transactions:1979；test_preview_job_worker:80；test_history_compare_jobs:452；test_submit_job_prepare:351。 |
| DC12 | 已写入文档并实现最终 **无 JSON → fail-closed** 分支 | S2a handoff:118 普查结论；test_storage_projection_core:382。没有实施 LONGTEXT JSON；出现真实 JSON 再重开。 |
| DC13 | 已实现；列序不属业务状态 | snapshot_materialization/contracts.py:575、:599；test_canonical_state_identity:172，manifest schema 仍保留 DDL 列序。 |
| DC14 | **部分实现，阻塞** | storage_projection 聚合成立，Preview 仅取第一项且无 side；EXIT-F1。 |
| DC15 | 已触发并实现扩充 | S2a handoff:119；unsigned TINYINT/SMALLINT、FLOAT、DATETIME 等观察类型；core:325 与 canonical identity Dolt 往返。 |
| DC16 | 已实现；只存不比内容变化可见 | test_comparison_rule_roles:90、:126；surface assembly 表级变化计数。 |
| DC17 | 已实现；INITIAL 恒空 | preview materialize:153、repository protocol:145；非空初始库 fail closed。 |
| DC18 | 已实现；完整状态，按 frozen expected parent 删表 | import_builder:40；test_submit_prepare_removed_tables:95；T1 canonical closure。 |
| DC19 | 已实现；读取不一致普通失败 | repository_ref protocol:127；test_history_compare_jobs:399；不创建 durable incident。 |
| DC20 | 已实现；source_table VARCHAR(64) | snapshot_materialization/compose:89、:178；composite golden、规范往返。 |
| DC21 | 已写入并执行；S2a/S2b 分开 | 执行计划 §2、两份 handoff/独立审核及 `p5-s2a-exit`、`p5-s2b-exit`。本次不以 tag 替代语义核对。 |
| DC22 | 已写入并交付指定样本范围 | S5 handoff §8–§11，t1–t4 配对/XML链路；新协议/版本重开；本次产品 diff 空，不读真实数据。 |
| DC23 | 已写入并实现，取代 DC10 早期文档意见 | Ruleset Activation:23、:77；Submit frozen 继续，Preview/History mismatch 失败。 |
| DC24 | 已实现；受理冻结 digest、逐步检查 | application/workspace/preview:222；test_preview_job_worker:80 覆盖 materialize 前与后续步骤。 |
| DC25 | 已实现；manifest digest 不符诊断/日志/指标 | sqlite_commit_metadata:132、:161、:176；test_commit_canonical_metadata:292；无 incident。 |
| DC26 | 已实现绑定归位/精确 ext 许可；不可达登记 Phase 6 | import_rules:84；设计 §9 A6 及延期表；contracts 不加载 compute。绑定位置已决，不可达延期仍在，见 §6.1。 |
| DC27 | 条件未触发；与 DC12 同无 JSON 分支 | S2a handoff、设计附录 B.1；最终 projection version 2 来自负零修复，与 JSON/DC29 无关；标头 EXIT-F3。 |
| DC28 | 已实现；Submission 理由共享且多行/单行模式分离 | `B/domain/submission/reasons.py`；`T/test_review_domain.py:521` 控制字符参数表，`test_submit_http.py:169` 输入边界。 |
| DC29 | 已实现并修订 Contract3.2.0 | DDL_PRIMARY_KEY_OR_KEYLESS、multiset 不去重；core:836/:876，canonical identity 包含重复行；P3-R4:236；生产自然键评估见 §6。 |
| DC30 | 已写入并执行；部分被后续决议取代 | 执行计划 §8.9；调试与取证分开。B 层“发现即修”被 DC31 改为登记；真实数据范围/按包沿用由 DC33 细化。 |
| DC31 | 已实现 A 层与边界，B 层登记 | Catalog 2 MiB/稳定 RESPONSE_LIMIT_EXCEEDED，Preview公开失败 test_preview_job_materialize:362；R5/Submit恢复；S5 §11 登记 B 层到 Phase6。 |
| DC32 | 已交付测量与文档 | S5 §9–§11 18场景、逐表与两时钟、非重叠成本；容量差距/外推限制；Phase6先测下界再定目标。 |
| DC33 | 已实现工具/规则；本次全量实际运行 | test_input_closure.py、run-tests.sh、AGENTS/testing-conventions；来源必须实际运行的 V。M 不 carried、全部包运行，真实数据按用户明确免重跑范围。 |
| DC34 | 已写入并执行；ct108、同 worktree manifest | AGENTS 与治理 G12/G6b；不比 containerd image ID。本次原 V worktree 已删，M fresh build/full gate，未跨 worktree 宣称等价。 |

### 8.2 G1–G13（含子项）

| 治理项 | 状态、owner 决定与 M 证据 |
| --- | --- |
| G1 主线/阶段工作区流程 | 已落文档并执行；执行计划 §8、AGENTS。历史阶段临时分支例外有记录；本次审核分支由用户明确授权，不改 main。 |
| G2 parser/Digital/XML 与普查闭合 | 已完成；S2a 前置已满足。SQL SET allowlist、Digital 值映射、XML 深度边界有 M parser/composite 测试；G2 handoff/复审只作线索，本次全量也运行。 |
| G3 单一 control DB baseline | 已完成；schema 与代码不符拒启动，不迁移、不双读；test_control_db_schema 与 AGENTS DC6。 |
| G4 可选普查 SQL fallback 扩展 | **未实施，最终不适用**；owner 计划明确为可选，只有 G2 后仍有业务快照失败才考虑扩展。G2 handoff:10/:58 记录剩余失败在 SQL parser，fallback 无法取得 table set；修订后 :237 记录八份均恢复且 G4 不适用。是按已授权条件作出的实施处置，不声称另有独立 owner 表决。 |
| G5 AGENTS 主线规则与审核隔离 | 已落文档；与 G1 对齐主线、tag、独立审核工作区。本次本地独立 review、ct108 detached gate，运行期间 clean。 |
| G6 Hypothesis 不进入 Docker context | 已完成；`vnext/.dockerignore` 排除缓存。身份可复现性没有由此完全解决，另按 G6b/DC34。 |
| G6b 可选 backend/worker source identity | **owner 2026-10-11 选 C，不实施 A/B**；同 worktree 规则保留。后由 DC34 改用 manifest 而非 image ID。此次触及重新评估条件，列 §6/§7；本次 fresh gate 已满足用户要求。 |
| G7 client e2e 镜像叠层 | 已完成；harness 区分 dependency/base 与 final image，不把 final 自己当 base；本次 runner 依候选 identity 构建属预期，未手工 rmi/tag。 |
| G8 重复有效键决议 | owner 2026-10-11 确认真实 gid 重复动机不成立；保留 gid 身份/no 位置，不加 no 为规则键、不去重。空白行字段不比较但存储、增删体现的取舍明确接受；由 G8a 给事实、G8b 修算法。 |
| G8a 普查口径 | 已完成既定修订；空白 gid 不算真实重复，单次 reader；M 测试覆盖。G8a-F1 状态误报仍存在，作为既有非阻塞工具项明确带出（§6）。 |
| G8b ordered 配对 | 已完成；确定性 backbone/位置摘要与规则；owner 接受 tie moved 行为，见治理 §3 记录与 §6。 |
| G9 文档与事实纠正 | 已完成该轮指定范围，治理 §3 已登记；不能推论所有后续状态文本自动更新，仍有 §7 清单及 EXIT-F3。 |
| G10 清理 | **已完成**，以治理计划 §3 第13项 `:556` 起的 2026-10-23 记录及 M 为准；G13 关闭其第4/6/7项，第2项 TMPDIR 前提已满足。没有重复操作旧 worktree/ref/image 清理。 |
| G11 backend xdist | 已完成，授权 dev-only pytest-xdist；runner parallel/serial 分拆实际运行。原小幅收益不影响验收；R2-O2 条件带出，R2-O3 见 EXIT-F4。 |
| G11b Compose identity/门禁耗时 | 已完成必须项；RS build-input/source-tree 精确绑定，backend/worker 采用后续 DC34。O2 是测量归因限制，O3 并发优化保持未授权，见 §6。 |
| G12 按包输入闭包/来源V/ct108 | 已完成并由 S4 修复 F1；manifest 含环境、工具、有效缓存与 Docker 输入；本次 runner 先 sync 后 manifest、完整五包实际运行，未靠不合格来源 carried。 |
| G13 secret 权限、pytest cache、TMPDIR、Hypothesis | 已完成，V=b93748c04e，最终记录在治理 §3 第13项与 `P/p5-g13-handoff.md`。当前 M 与该 V 的 vnext/AGENTS 相同；本次 fresh runner 证明正常 022 路径、五包 cache 隔离与退出清理。原 077/失败后沿用/新 worktree 沿用验收只引用该阶段已记录范围，未冒充本次另测。 |

G1–G13 的完成记录与本次两个业务/验收 finding 不冲突：治理门禁可以全部通过，而既有测试仍漏掉 Contract 要求。整体结论因此保持 **定向修订，2 个阻塞项**。

## 9. 第一次复审（2026-10-24）

### 9.1 结论与固定对象

- 结论：**定向修订；剩余 1 个阻塞项，EXIT-F1 未完全关闭**。EXIT-F2 已关闭，EXIT-F4 已按修复与 owner 决议关闭；EXIT-F3 仍为已安排统一状态更新的非阻塞文档项。
- 审核对象 H：`ddd1b2a1cf50eb046243b66bea0c69022b25330c`；门禁提交 V：`88ba238a88af23eea00ee0d15dae504d6731dd95`；复审区间：`85ebfb9a95..H`。本节行号指 H。
- 依据：原报告 EXIT-F1/F2/F4 关闭标准；`458b40fbea` 上治理计划 §3 第13项末尾的 owner 决议；H 的 `p5-exit-fix-handoff.md`；现行 Business Lifecycle §2、Operation Lifecycle §6.2；执行计划 §8 与 AGENTS/testing-conventions。§1–§8 保留为初审历史记录，本节为本次复审结论。
- 开发主机在独立 detached `/home/dev/gdds-p5-exit-rereview` 审查 H，并建立 legacy 链接；没有在实施工作区写源码。独立 carried 与唯一新增的合成边界检查只在 ct108 原 V runner 的 `/home/dev/gdds-p5-exit-fix`、HEAD=H、clean 状态下执行。
- 没有读取真实数据、运行 DC32、重建镜像或重跑完整 runner。复审检查出现失败后立即停止，未调试、未修代码、未重跑；只完成此复审记录。

### 9.2 原 finding 关闭情况

| 原 finding | 关闭情况 | H 上的依据 |
| --- | --- | --- |
| EXIT-F1 全部投影失败明细与 side | **部分关闭，仍阻塞** | `B/application/preview_jobs.py:1089` 遍历 FULL 两侧；`:1323` 把投影诊断映射为带 side/table/column 的明细；`:2129` 写入 terminal Operation/Step。Operations v2、SQLite JSON blob、HTTP mapper 接线成立，现有多表/多列/双侧/101项测试通过；但上游 1024 项截断没有计入新 `omitted_count`，见 §9.3。 |
| EXIT-F2 ADDITIVE 新 Preview 读取旧基线 | **已关闭** | `T/test_preview_job_materialize.py::test_additive_ruleset_previews_nonempty_baseline_from_older_manifest` 构造非空基线 A 的 manifest；B 保留 A 全部规则并追加 exact BROWSE_ONLY 规则，A/B digest 不同。新任务冻结 B，经生产 materialize 与 assemble handler 成功；旧基线仍 pinned，上传 manifest 为 B；实际 pair pipeline 的新表事实为 ADDED_TABLE、content_changed=true、无 records_ref，验证 B 的语义。观测包装调用原 pipeline，并非替换其结果。既有 stale Preview、跨激活恢复拒绝测试未被删除或放宽。 |
| EXIT-F3 Canonical Storage projection version 标头 | **非阻塞，待统一更新** | H 未修改该标头；owner 在 `458b40fbea` 明确交审核方在 exit 状态更新时订正为 2。本次复审不提前修改 Contract 或签署 exit。 |
| EXIT-F4 / G11 R2-O3 | **已关闭** | `T/test_http_admission_shutdown_process.py:31` 同时标 integration/serial；V 的 unit collect 为 3 deselected / 0 selected。pytest exit 5 是该空选择检查的预期结果，不是失败 runner。完整 runner 仍实际执行这 3 项。 |
| EXIT-F4 / occupancy-assertion-gap、private-process-access | **已按 owner 决议关闭** | `458b40fbea` 的治理计划 §3 第13项明确接受现状；重开条件为下次修改 T3 崩溃屏障或 Repository restart harness。无需为了关闭旧建议新增测试矩阵；这不是宣称两处代码已经改动。 |

修订的合理部分已核对：`OperationDiagnosticDetail` 的字段、排序、100 项上限及 omitted_count 配对校验属于既有 Operations owner；Operation/Step document version 提升为 v2，未加入旧版兼容分支。SQLite store 继续以 `to_document()`/parser 读写原 JSON blob；新增文件型 DB 关闭后重开测试确实回读 Operation 与 Step 明细。HTTP Operation 与 History diagnostic schema/mapper 同步，OpenAPI 结构断言存在。未新增独立 artifact、incident 状态机或生产依赖。

### 9.3 EXIT-R1-F1：上游诊断截断未计入 omitted_count（EXIT-F1 未完全关闭）

- 类型：**已证实缺陷**；是否阻塞：**是**。这是原 EXIT-F1 的边界遗漏，不把它另计成第二个未关闭阻塞项。
- 位置：
  - `B/capabilities/storage_projection/contracts.py:49`：`MAX_DIAGNOSTICS = 1024`；
  - `B/capabilities/storage_projection/project.py:807`：只把剩余容量内的诊断追加到结果，后续失败诊断丢弃；`:220` 的 canonical 结果还有一次最多 1024 项的截断；
  - `B/application/preview_jobs.py:247`：只计算收到的明细超过 100 的数量；`:1118` 起的两侧汇总只累加这些已知数量，无法计入 capability 先前丢掉的条目；
  - `F/contracts/operation-lifecycle-and-integrity.md:137` 附近：omitted_count 记录“未列出的总项数”；owner 决议要求 FULL 汇总全部投影失败，最多列 100 项，其余计数。
- 依据：原 DC14、EXIT-F1 及 `458b40fbea` 的有界明细决议。已有 capability 1024 上限可以保留；问题是新增的“总项数”契约不能把上游截断当成从未发生。
- 触发场景与影响：MODIFIED_ONLY 上传三张合成表，每表 400 个不受支持的 DECIMAL 列，另有一个合法 INT 主键；每表 401 列，低于 parser 的 512 列上限。生产 Preview materialize handler 实际识别投影失败，公开 Operation 最终为 FAILED，但输出只有 100 条 details、omitted_count=924，概要称共 1024 项。实际有 1200 个失败列，正确的省略数应为 1100；176 项在上游被静默丢弃。用户收到错误的失败总数，不能据“已列 + 已省略”判断完整失败范围。
- 独立复现：在 H 的 ct108 clean worktree 复用现有 Preview harness 和纯合成 SQL，经生产 handler、SQLite store、`operation_to_response` 读取公开结果；没有 mock projection，没有真实 Dolt/Compose/真实数据。日志 `independent-diagnostic-boundary-20261024.log`：

  ```text
  SYNTHETIC_INPUT tables=3 unsupported_columns_per_table=400 expected_total=1200
  OPERATION_STATUS= FAILED
  PUBLIC_LISTED= 100
  PUBLIC_OMITTED= 924
  PUBLIC_ACCOUNTED= 1024
  AssertionError: 1200 failures require 100 listed + 1100 omitted; upstream cap lost failures
  END_HEAD=ddd1b2a1cf50eb046243b66bea0c69022b25330c
  END_STATUS=
  EXIT_CODE=1
  ```

- 最小修正方向：在现有投影结果链中保留有界列表，并透传上游已省略计数/完整诊断计数，再与 Operation 100 项截断及 FULL 两侧计数合并。无需保存无上限列表、增加失败 artifact 或另建 evidence 机制。若选择改变“精确总数”语义，须由 owner 明确修订当前承诺，不能继续输出貌似精确的 1024。
- 关闭标准：在 Preview 唯一测试 owner 的现有共享参数表中增加超过 capability 1024 上限的合成输入，断言公开 `len(details) + omitted_count` 等于完整失败数、列表不超过 100、排序与 side 保持、整体 FAILED 且无 READY/Repository effect；两侧计数的合并同时核对。现有 101 项测试只能证明 Operation 自身的上限，不能证明跨 capability 上限的累计。
- 停止记录：该检查 exit 1 后停止所有进一步测试、carried 和门禁操作。没有修改或重跑失败检查，也未尝试其他边界输入；下述 carried 是失败发生前已完成的独立复算。

### 9.4 提交范围、停止记录与真实数据适用性

`85ebfb9a95..V` 为 16 个文件，生产改动集中于 Preview 失败诊断、Operations 契约及 HTTP 输出接线；另有相应测试、两份 Contract 文本与 benchmark 的调用适配。`V..H` **只改 handoff**（87 行），没有测试、源码、镜像输入或锁变化。

`75946afda3..88ba238a88` 确实只改三文件：benchmark 给 `_materialize_uploaded_side` 传 MODIFIED side，OpenAPI 测试将 items 收窄为 dict 后读取 `$ref`，F2 测试删除无效 type-ignore。未改变计时边界、投影成功产物或 F2 场景。Handoff 已保留早期 debug focused 失败和“focused 先于静态”的顺序偏差，并明确那些结果不作 V 证据。独立读取的 V 静态日志、focused 日志与后续门禁记录均对应新 V；没有将旧失败候选的结果拼成通过证据。

本轮产品 diff 不为空，因此不能沿用初审“从 S5 到 M 产品 diff 为空”的论证。真实数据免重跑的依据是 `458b40fbea` 中本轮 owner/DC33 明确批准：修订限投影失败信息、成功路径业务语义不变；benchmark 补 side 不改成功路径测量口径。没有据此宣称修复已在真实失败数据上验证；§9.3 是额外合成验收中发现的缺陷，不否定 S5 已交付的成功旅程测量。

### 9.5 门禁原始记录与独立 carried

日志根目录为 ct108 `/home/dev/gdds-p5-closure-s1-gate-logs/p5-exit-fix/`，目录 700，日志/manifest 文件 600。以下是对原始日志的独立核对，不冒充本次重新运行全量。

| 检查 | 结果与日志 |
| --- | --- |
| V 五包 Ruff/mypy、import_rules | 全通过；mypy 34/15/26/486/200 个文件，import_rules 0/0/6。`static-import-rules-88ba238a-20261023.log` 起止 V，exit 0。 |
| V focused 全文件 | 845 passed，exit 0；`focused-88ba238a-20261023.log`。DC32 对应文件为 synthetic 测试，不是重新测量。 |
| R2-O3 unit collect | 3 deselected、0 selected；`r2-o3-unit-collect-88ba238a-20261023.log`。 |
| V preflight / fresh RS | 无 Dolt、容器、Compose、8000 listener，clean；build 脚本实际执行，fresh image 与 candidate revision、build-input/source-tree/lock labels 相符；`preflight-88ba238a-20261023.log`、`fresh-rs-build-88ba238a-20261023.log`。 |
| V 权威全量 | shared_kernel 242、repository_contracts 152、repository_client 154；backend parallel 2912、serial 39；RS parallel 1730 + 1 skipped、serial 205。共 **5434 passed、1 skipped，runner exit 0**，起止 V/clean；`full-runner-88ba238a-20261023.log`。 |
| Compose / skipped | 两个 serial 批次均 0 skipped；唯一 skipped 仍为未修改的 host-only delegated target-container cgroup smoke，RS 测试及 runner 筛选未改。未重跑 Compose 或另跑 skip 诊断。 |
| V postflight | clean、无 Dolt/容器/Compose/8000 listener，五包 Hypothesis 目录不存在，root 为空，RS labels 匹配；`postflight-88ba238a-20261023.log`。 |
| 实施方 H carried | `h2-carried-final-20261023.log` 固定最终 H，五包可沿用，起止 H/clean，exit 0；不是只停留在较早 handoff 提交。 |
| **复审方独立 carried** | `independent-carried-20261024.log`：从 V runner 原文逐包解析 JSON，确认与保存的 V manifests 完全相等；在原 runner 同一 worktree、HEAD=H 重算五包当前 manifest 并 compare，**全部可沿用、changed_components=[]**；RS labels 匹配，起止 H/clean，exit 0。 |
| **复审方新增边界检查** | `independent-diagnostic-boundary-20261024.log`：§9.3 合成场景 exit 1；起止 H/clean。随后停止，不以此前 runner 成功掩盖此失败。 |

独立 carried 使用原 V 的 umask 022、HOME/LC_ALL/PATH/TMPDIR 与 skip-lock-assert 设置，未设置 UV_CACHE_DIR/GATEWAY_TEST_PACKAGES/GATEWAY_TEST_BASETEMP；manifest 时逐包显式设定 V runner 相同的 Hypothesis 路径并确认不存在。当前 manifest 与 compare 存于 `independent-review-20261024/`，均在 worktree 外。该复算发生在新增边界检查之前，不把其结果表述为失败检查后的再次 carried。

| 包 | 独立复算的 V/H 相同 total_digest |
| --- | --- |
| shared_kernel | `630927157f24e0aaddab1a98199d19cd8f979246181f958f1075f5c76cedbb5f` |
| repository_contracts | `a7025c2aeee34e562739bbff0af3e1cd4d7cc3b524baa56e5b95ec05b50d5425` |
| repository_client | `ac29d6e19391d9deca18bfe43994766627183312c211314550363e9945270885` |
| backend | `e738203b9d7dbca9ca579151919564cd58d1ee287f30b668b8106456542cc816` |
| repository_service | `b80d22fd57ee5af0f6f8843c2541034b1ab00ccb9474ff61c4b5759ff32e59b3` |

RS image 为 `sha256:22cd13dfa799bec4c8f20547dae051c211d1d050c02ddf3aac4f51781429c979`；build-input revision 为 `b93748c04e63be4eeece66cb5abaadf13fd7b6d3`，source-tree 为 `sha256:b24fa92dbbb59d00617eec838a22ca947fa98fe42fab996770aa9b9e20f7f15c`。revision label 保留 V，H 重算两个身份 label 一致；image ID 仅记录，不作为跨构建等价条件。backend/worker 由同 worktree backend manifest 判定，未跨 worktree 重算替代原输入。

### 9.6 剩余前置与处置边界

先关闭 §9.3 的精确计数缺口，再复审 EXIT-F1；当前不能宣布 P5 整体退出。原 §6 的两组不可达模块、Phase 6 性能项与其余已登记重开条件未受本轮改动影响，不重开已成立的架构收口；§7 的状态文本更新及 EXIT-F3 仍留给统一 exit 状态更新。

本轮仅追加此报告，初审原文不改；报告提交从 H 派生，不改实施分支或 main。未推送、合并、rebase 或打 tag；未清理实施方仍需用于下一轮的 ct108 worktree、镜像、缓存或已有证据。

## 10. 第二次复审（2026-10-24）

### 10.1 结论与对象

- 结论：**通过；阻塞项 0**。EXIT-F1 及其第一次复审遗漏 EXIT-R1-F1 已关闭；EXIT-F2、EXIT-F4 的关闭结论保持。EXIT-F3 仍是 owner 已安排在统一 exit 状态更新中处理的非阻塞标头订正，不作为本次通过的隐藏前置。
- 审核对象 H：`8cfc518598cc5b34cc64bd53839568909a69a1d4`；门禁提交 V：`6badf722c9e8e243e7802bb37ae1afe8893d4872`；复审代码区间：`ddd1b2a1cf..H`，对应上一份复审报告提交 `e9f80f8acc` 的 §9.3。上一复审报告没有合入实施分支，本报告逐字保留该提交的 §1–§9，再追加本节，不把它误写成 H 已包含的提交。
- 依据：§9.3 关闭标准、原 DC14/EXIT-F1、`458b40fbea` 中的 owner 决议、H 的修复 handoff、AGENTS/testing-conventions 与执行计划 §8。仅核对本轮差异、原 finding 及改动传播；初审其他成立项不重新展开。
- 本地审核在独立 detached `/home/dev/gdds-p5-exit-rereview-2`、HEAD=H 进行，已建 legacy 链接。独立运行检查只在 ct108 原 V runner 的 `/home/dev/gdds-p5-exit-fix`、HEAD=H、clean 状态下完成。

综合初审、第一次复审和本轮结果，P5 整体 exit 的阻塞性缺口已消除，整体收口验收成立。§6 的已登记延期与重开条件仍保留；本次通过不表示 Phase 6 容量目标已达成，也不代替后续统一状态更新、打 tag、合并或发布动作。

### 10.2 Finding 关闭与源码核对

| 项 | 结论 | H 上的证据 |
| --- | --- | --- |
| capability 1024 项截断计数 | 已修复 | `B/capabilities/storage_projection/contracts.py:391`、`:428` 为两种 result 增加必传 `omitted_diagnostic_count`；`:523` 校验非负整数、COMPLETE 为 0、正省略数须已有 1024 项。没有用默认 0 掩盖旧构造点。 |
| 逐表、前置失败与 canonical 合并 | 已修复 | `project.py:270` 的 `_retain_diagnostics` 保持列表有界并返回本次省略量；`:822` 计算前置失败截断；`:845` 逐表累加；`:224` 同时加入上游省略数及 canonical 合并截断；`:250` 处理 canonical 组装失败。两个 canonical FAILED 返回点带真实累计值，不再静默切片。 |
| Preview 单侧及 FULL 总数 | 已修复 | `B/application/preview_jobs.py:1335` 概要采用收到条目数加上游省略数；`:1366` 透传给 PreviewJobError；`:267` 再加 Operation 100 项截断；`:1122` 起 FULL 合并两侧已保留条目和省略数。没有重复计数或把上游截断当成零。 |
| 成功/取消路径传播 | 无成功语义回归证据 | COMPLETE 构造明确传 0，包括 `B/infrastructure/repository_write/import_publication.py:414` 的冻结导入结果；manifest、canonical bytes、投影内容与 import 渲染未改变。取消/超时仍返回专属单条诊断，不承诺统计未完成扫描的全部失败；未扩大扫描或引入无界列表。 |
| 权威行为测试 | 关闭标准满足 | `T/test_preview_job_materialize.py` 的现有 `PROJECTION_FAILURE_CASES` 新增 MODIFIED_ONLY 1200 项和 FULL 2400 项；生产 handler → control DB 重读 → HTTP mapper，检查完整总数、100 项上限、side/排序、FAILED、无 READY/assemble/Repository effect。原 101 项与 ADDITIVE 用例保留。两种 result 的非法计数由 `test_storage_projection_contracts.py::test_projection_results_validate_omitted_diagnostic_count` 共享参数表验证。 |
| EXIT-F2 / EXIT-F4 | 保持已关闭 | 本轮未改变 A/B 规则测试的业务构造和成功断言，正式 focused 与 full runner 包含它；R2-O3 仍为 integration/serial，unit collect 0 selected。其余两项旧观察的 owner 接受决定不变。 |

明细选择与顺序已核对：capability 按处理顺序保留前 1024 条，Operation 对保留集稳定排序后取前 100；FULL 再合并两侧。它保证已列条目有序、数量有界、完整失败总数精确，**不承诺列出全部失败中全局排序最小的 100 条**。Handoff 明确了这个区别，与 owner 的有界明细和排序要求相容。

**新增 findings：无。** EXIT-R1-F1 是原 EXIT-F1 的最后一处遗漏，本轮关闭后不再保留为阻塞或延期项。

### 10.3 独立重验原失败场景

复审方在 ct108 的 H 上再次构造纯合成 SQL，复用既有 Preview harness，但自行从生产 handler、SQLite store 和 `operation_to_response` 读取并断言实际公开结果；没有 mock projection，也未使用真实数据或真实 Repository effect。除原 MODIFIED_ONLY 3×400 外，同次检查增加 FULL 两侧各 3×400，未写入新的测试文件。

| 输入 | 公开 details | 公开 omitted_count | 已列 + 省略 | 其他断言 |
| --- | ---: | ---: | ---: | --- |
| MODIFIED_ONLY，3 表 × 400 失败列 | 100 | **1100** | **1200** | FAILED；明细排序稳定、side=MODIFIED；概要计数 1200；无 READY closure / Repository operation effect。 |
| FULL，两侧各 3 表 × 400 失败列 | 100 | **2300** | **2400** | FAILED；保留的明细 side=INITIAL、排序稳定；概要计数 2400；无 READY closure / Repository operation effect。 |

日志：`independent-diagnostic-boundary-r2-20261024.log`，起止 HEAD 均 H、worktree clean、exit 0。合成表每张包含 400 个失败列和合法 INT 主键，共 401 列，未越过 parser 的 512 列限制。结束后的 Dolt/容器/Compose/8000 检查为空，runner Hypothesis root 为空；临时合成产物已随测试临时目录清理。上次 100+924 的错误结果被直接纠正，不只是换了断言或文字说明。

### 10.4 验证来源、停止记录与 carried

`573b2c0d12..V` 确实只有 `T/test_preview_job_materialize.py` 一行：在求和前断言 `omitted_count is not None`；未使用 ignore/cast，未改变求和值或业务预期。`ddd1b2a1cf..V` 为 7 个文件、178 additions/27 deletions；`V..H` 只有 handoff 85 行。此前 508 项 focused 属调试、不作为验收；mypy 停止后已在新 V 从五包静态检查重新开始。没有把调试结果或较早候选的成功结果拼入当前 V。

ct108 日志根目录仍为 `/home/dev/gdds-p5-closure-s1-gate-logs/p5-exit-fix/`。原始验收日志均已独立读取核对，以下全量/focused 结果为 V 的实际运行，本次未重复执行整套门禁。

| 检查 | 结果 / 日志 |
| --- | --- |
| V 五包 Ruff/mypy、import_rules | 全通过；mypy 34/15/26/486/200 文件；0/0/6。`static-import-rules-6badf722c9-20261024.log`。 |
| V 正式 focused 全文件 | 631 passed；包含 Preview/Operations/control DB/HTTP/Storage Projection/import/prepare 等受影响完整文件，另单列 MODIFIED_ONLY 3×400 用例 1 passed。`focused-6badf722c9-20261024.log`。 |
| V R2-O3 | 3 deselected / 0 selected；pytest 预期 exit 5，检查脚本 exit 0。`r2-o3-unit-collect-6badf722c9-20261024.log`。 |
| V preflight / fresh RS / postflight | clean V，未发现 Dolt、容器、Compose 或端口占用；正式构建脚本成功，revision/identity/labels 匹配；结束五包 Hypothesis 目录不存在。`preflight-6badf722c9-20261024.log`、`fresh-rs-build-6badf722c9-20261024.log`、`postflight-6badf722c9-20261024.log`。 |
| V 全量 runner | **5439 passed，1 skipped，exit 0**：242/152/154；backend 2917 parallel +39 serial；RS 1730 parallel +205 serial。起止 V/clean。`full-runner-6badf722c9-20261024.log`。 |
| Compose / skipped | 两个 serial 批次均 0 skipped；唯一 skipped 为未改动的 host-only target-container cgroup smoke，与原定位相同。没有补跑 Compose 或重复定位已确定的 skip。 |
| 实施方最终 H carried | `h2-carried-final-6badf722c9-20261024.log` 固定最终 H，五包可沿用，exit 0；不是仅 H1 的结果。 |
| 复审方独立 carried | `independent-carried-r2-20261024.log`：从 V runner 原文逐包解析 manifest，确认与 `v-manifests-6badf722c9/` 保存文件完全相等；在同一个原 runner worktree、HEAD=H 重算 current 并 compare，五包全部可沿用、changed_components=[]、exit 0。 |
| 复审方独立边界检查 | §10.3 两个场景实际通过，起止 H/clean、exit 0；`independent-diagnostic-boundary-r2-20261024.log`。 |

独立 carried 使用 umask 022、原 HOME/LC_ALL/PATH/TMPDIR/skip-lock-assert 环境，逐包设置原 runner 的 Hypothesis 路径并确认目录不存在；未设置 UV_CACHE_DIR、GATEWAY_TEST_PACKAGES 或 GATEWAY_TEST_BASETEMP。日志显式 600，current/compare 目录 `independent-review-r2-20261024/` 为 700，文件 600，全部位于 worktree 外。

| 包 | 独立确认 V/H 相等的 total_digest |
| --- | --- |
| shared_kernel | `630927157f24e0aaddab1a98199d19cd8f979246181f958f1075f5c76cedbb5f` |
| repository_contracts | `a7025c2aeee34e562739bbff0af3e1cd4d7cc3b524baa56e5b95ec05b50d5425` |
| repository_client | `ac29d6e19391d9deca18bfe43994766627183312c211314550363e9945270885` |
| backend | `145ce59abb434326c79994e5254f0beb41974610584d30544dd4113dbba34387` |
| repository_service | `8bf2f982abbadcafe27498a2f32e79b81e7800919ffe83de13fb2d6a21483c33` |

RS image 为 `sha256:ed8c0d7bbf9e0c49ece0783fcf108d03fbfcaffc8cd56e626917f65c1d49dc41`，revision label 为 V；H 重算 build-input `b93748c04e63be4eeece66cb5abaadf13fd7b6d3`、source-tree `sha256:b24fa92dbbb59d00617eec838a22ca947fa98fe42fab996770aa9b9e20f7f15c` 与镜像 labels 相同，uv-lock label 与当前锁 SHA 相同。Image ID 仅记录，不作等价判据；backend/worker 依同 worktree backend manifest 判定。

### 10.5 收尾与保留事项

本轮未改成功路径 canonical/manifest/import 业务语义、依赖锁或部署边界；真实数据不重跑依据仍为 `458b40fbea` 的本轮 DC33 授权及实际改动范围，不以“产品 diff 为空”代替该判断。没有读取真实数据、运行 DC32 或新增性能结论。

原 §6 的六个不可达模块、Phase 6 性能候选、已登记延期与重开条件继续有效；EXIT-F3 及 §7 状态文本由终审方统一更新，不能把历史“实现未授权/仍待 kickoff”当成当前事实。本轮只提交审核报告，保留初审与第一次复审历史；未修改源码、测试、Contract、ADR 或治理正文，未推送、合并、rebase、打 tag，也未清理实施方的 worktree、镜像或缓存。
