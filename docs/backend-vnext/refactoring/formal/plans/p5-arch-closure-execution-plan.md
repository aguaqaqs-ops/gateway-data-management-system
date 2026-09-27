# P5 架构收口执行计划

状态：**ACCEPTED — S0 文档（r4）由 repository owner 于 2026-09-27 接受；实现未授权**

日期：2026-09-27（r4 与接受）；r2、r3 为 2026-09-26；r1 为 2026-09-25

Owner：Backend vNext Architecture

入口：[Entry Brief](p5-arch-closure-s0-entry-brief.md) → [详细设计](p5-arch-closure-design.md) → 本文

审核与决议：[S0 独立审核报告](p5-arch-closure-s0-independent-docs-review.md)、
r2 独立复审（[第一份](p5-arch-closure-s0-independent-rereview.md)、[第二份](p5-arch-closure-s0-independent-rereview-2.md)）、
r3 独立复审（[第一份](p5-arch-closure-s0-independent-rereview-r3.md)、[第二份](p5-arch-closure-s0-independent-rereview-r3-2.md)）、
[r4 独立核对](p5-arch-closure-s0-independent-rereview-r4.md)、[S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md)、[修订处置表](p5-arch-closure-s0-revision-disposition.md)

B=`vnext/backend/src/gateway_backend/`，T=`vnext/backend/tests/`。本文写未来命令与期望证据；实际结果写入
各阶段 handoff。

## 1. 执行形态

```text
S0 文档、独立审核与复审
  -> [前置：P5-5E slice exit pass]
  -> S1 kickoff（合入主线、漂移复核、真实数据普查）
  -> S1  结构修复（行为不变）
  -> S2a 规范快照与比较规则的能力层（W3 入口、ComparisonRuleView、编码与摘要、规范投影入口、真实 Dolt 同一性）
  -> S2b 切换到规范域（Preview/Submit/History 接入、commit 规范元数据、DC9）
  -> S3  composite_signal 接入
  -> S4  项目身份与数据替换
  -> S5  清理、测量与收口验收
  -> P5 整体 exit review（另行进行，不由本计划签署）
```

阶段顺序依据：

- S1 先理顺重复编排与边界，并以“golden、digest 与 checkpoint 载荷不变”作为回归基准，这样后续语义变更只需改一处；
- S2a 交付能力层的构件与真实 Dolt 同一性 owner，它是 S2b 切换的门槛（DC21）；S2b 再把 Preview、Submit、History 切到规范域；
- S2 是 S3/S4 的地基，两者都依赖规范快照与去流程化后的 comparison 入口；
- S3 先于 S4：静默丢失（R5）比无法识别误传（R6）更严重，而且 S3 的改动面更小。

每阶段结束交独立审核，S2a 与 S2b 分别审核（DC21）。审核结论按
[纵切指南 §6](../guides/slice-design-execution-and-review-guide.md) 给出；未通过不进入下一阶段。
F1、F3、F4、F11 对应的修复不得作为普通延期项带入 P5 exit（审核报告 §7.8）。

## 2. 阶段定义

### S0 — 文档入口、独立审核与复审

- 交付：Entry Brief、详细设计（附录 A：Business Lifecycle 3.1.0 候选；附录 B：其他上游修订候选）、本计划、
  ADR 0018–0021（2026-09-27 起 Accepted）、P5 §2A.4.1 第二轮补充；审核报告、两份 r2 与两份 r3 复审报告、owner 决议记录与修订处置表。
- 审核对象：r1 在 `3e5d5807e5` 接受独立审核（结论：定向修订）；r2 在 `5858eaaa08` 接受两份独立复审（结论均为定向修订）；
  r3 在 `ffba1138ef` 接受两份独立复审（结论分别为通过与定向修订）；r4（`2f38b301a6`）按两份报告的全部 findings 修订，
  其差异经独立核对（`b4e50ce4a0`）判为通过；repository owner 于 2026-09-27 接受。
  代码事实基线 `2172369803`。
- 接受（已完成，2026-09-27，repository owner 决定；r4 差异核对通过），按 Entry Brief §5：
  - ADR 0018–0021 状态改为 Accepted；
  - 附录 A 并入 Business Lifecycle 并升至 3.1.0；附录 B 各候选并入对应文档（Canonical Storage 升至 3.1.0、
    Canonical Storage §4 的摘要说明、Ruleset Activation §1 与 §5、ADR 0016 与 Operation Lifecycle §4、
    Contract Taxonomy §4.4/§4.6/§5/§13、P5 §2A.2/§6.1/§2A.4、Architecture §7.1/§7.2/§9.1/§10/§13）；
    P3-R3/R4/R5 设计与 5E §6.6 加“由 ADR 00xx 取代”标注；
  - 以上以单独的 docs 提交完成；上游文档加注“实现随收口 S1–S5 交付，交付前现行源码仍按原版本行为运行”；
  - 实现授权另行给出。

### S1 kickoff（5E slice exit 之后）

1. 把本分支合入 5E exit 后的主线。（已完成，2026-09-27：合并提交 `d116843188`；此后主线为 `main`。）
2. 运行 `python -m tests.support.import_rules`，记录 S4 期间基线的变化。
3. 按设计 §2（R1–R6、E-a…E-i）复核 E 级事实；若有偏离，先修订设计对应章节再开工。
4. 真实数据普查（DC22）：
   - 数据按[决议记录 §4](p5-arch-closure-s0-owner-decisions.md#4-真实数据存放建议)存放，脚本经
     `GATEWAY_REAL_DUMP_ROOT` 定位，脚本放在 `vnext/backend/benchmarks/`（不进入生产包）；
   - 对 4 份 dump 只读执行 staging、业务物化（SQL 与 `logics.xml`）与规则解析，输出只含结构统计，写入
     `$GATEWAY_REAL_DUMP_ROOT/census/`；
   - handoff 记录：dataset ID、SHA-256、规模、表数、总行数；存储表（非 SKIP）的列类型分布；词表外类型、
     无键表、重复键、可空键列、JSON 列的清单；`version_manager.saved_time` 的实际类型；`logics.xml` 的解析结果；
   - 发现的问题提炼为最小的合成 golden，不复制行数据。
5. 按普查结果落定条件决议：存储表中有 JSON 列 → S2a 以 LONGTEXT 实现（DC12），否则 JSON 保持 fail-closed 并
   登记重开条件；存储表中有词表外类型 → S2a 扩充类型词表（DC15）。决定写入 handoff。任一类型无法无损往返 Dolt 时
   按设计 §14 第 2 项停止。

### S1 — 结构修复（行为不变）

- 目标：关闭设计 §9 标为 S1 的项。
- 行为约束：golden、业务 digest、checkpoint 载荷、HTTP DTO 与 compose 旅程结果均不变。受影响的测试只改导入路径、
  不改断言；§3 列出的死代码测试随被删模块一起删除。
- 验收（可由 `import_rules` 机械核对）：
  - 违例基线只剩：A2 的 `infrastructure.repository_read.http_arrow` 两条（`private` → `snapshot_materialization._digest`、
    `capability-surface` → `snapshot_materialization.scalar_encoding`），以及 A6 的
    `unowned-root-module gateway_backend.repository_import_artifact`；三条都在 S2b 关闭。
  - 运行时环基线为空。
  - 不可达基线只剩：
    - composite 与 XML 模块（`snapshot_materialization._catalog`、`snapshot_materialization.compose`、
      `table_access._xml_parser`、`table_access.xml`），S3 关闭；
    - `external_target_sync` 三个模块，在 owning 设计中登记延期；
    - canonical row hash 模块：`capabilities.canonical_row_hash.contracts` 与 `compute`、`canonical_row_hash_ipc`
      移入后的新模块名。改名导致的基线条目替换在同一 diff 中给出理由，并登记 Phase 6 延期。
  - `compute` 移入 capability 后依赖 Rust 扩展 `gateway_compute`（`ext:compute`）。import 规则精确放行
    `capability:canonical_row_hash → ext:compute`（DC26），因此迁移不新增 layer 违例；放行在同一 diff 中说明。
    S1 按预算完成迁移与放行后运行 `import_rules`，输出须与上列条目一致（第二份复审以临时副本模拟过只迁移、不放行的情形）。
  - backend unit、integration、serial 全绿；五包 ruff、mypy 通过。
  - bootstrap 组合改动涉及进程装配，因此在阶段末重建 current HEAD 镜像并运行既有 compose 旅程，
    结果与 5E exit 一致。
  - synthetic job 与 external effect 桩移出生产包后，worker 集成测试改为由测试侧注入。这是装配变化，不改断言，在
    handoff 中说明。

### S2a — 规范快照与比较规则的能力层

- 目标：设计 §4.1–§4.5 的能力层部分、§4.7（History 规则集冻结）、§6（W3）、§9 job 模块复制行的 S2a 部分。
- 前置：S1 exit pass；S1 kickoff 普查结果已记录，DC12、DC15 已按普查落定。
- 内容：
  1. table_rules：`compare_excluded_columns` 与列处置校验；9 条 ordered 规则去掉 `ignored_columns` 中的 `no`；
     `ComparisonRuleView` 与 `ComparisonRuleSet`；
  2. snapshot_materialization：business schema digest 与 canonical state digest；SET 解码；规范 descriptor 的类型规范化（含 ordered `no` NOT NULL）；
     Snapshot/Summary 编解码并入 contracts（Preview 与 History 两份 `_summary_payload` 合并，checkpoint 载荷随之变化，
     在 handoff 记录）；
  3. storage_projection：`project_canonical_table_set`、`publish_canonicalization_manifest`；存储约束（不可作键的类型、
     键列 NOT NULL）；失败诊断一次收集全部（DC14）；按普查结果实施 DC12、DC15（触发 DC12 时按 DC27 在 handoff 中写明
     storage projection version 的处理）；CanonicalizationManifest 的 `contract_version` 升至 `3.1.0`，解码接受历史版本
     （读取与写入分开校验）；
  4. comparison：新的 `ComparisonRequest`（运行期 `rule_set`、`mode`）；角色语义，含 DC16 的表级“内容已变化”事实与
     compare-excluded；按列名与有效键对齐，并只依据两侧规则侧存储事实标记 schema 差异来源（Canonical Storage §7，设计 §4.5）；提前退出要求
     business schema digest 相等；schema 事实适用于所有存储角色；删除流程词汇；`ComparisonTablePolicy` 降为内部类型；
  5. surface_assembly：自有的中性身份标注类型，不再从 comparison 导入 `IdentityStatus`；表级内容事实计入变化计数；
  6. Application：Preview 与 History 传入运行期规则集；两者都在受理时冻结运行期规则集 digest（Preview 写入 job payload，
     DC24；History 写入受理记录，需 control DB migration），每步执行前比较，不同即稳定失败
     （`PREVIEW_RULESET_VERSION_MISMATCH`、`HISTORY_RULESET_VERSION_MISMATCH`）；删除 `_project_table_policy`、
     `_policy_to_checkpoint_dict`、`_table_policies_from_checkpoint`，compose harness 中的 History oracle 随入口改写一起更新。
- 中间状态：S2a 结束时 Preview 上传侧仍是原始快照，R1 在 S2b 才修复；handoff 记录这一点。阶段之间不对外发布。
- 验收：
  - 设计 §12 的以下 owner 通过：`test_canonical_snapshot_identity.py`（integration，真实 Dolt，S2b 的门槛）、
    `test_canonical_state_identity.py`、`test_snapshot_materialization_contracts.py`、`test_table_rules_comparison_view.py`、
    `test_comparison_rule_roles.py`、`test_surface_assembly.py`（内容事实可见）、`test_comparison_planning.py`（对齐与来源标记参数表）、
    `test_storage_projection_core.py`，以及 `test_preview_job_worker.py`、`test_history_compare_jobs.py` 中的恢复用例
    （Preview 含受理后、materialize 前发生激活的情形）；
  - `BROWSE_ONLY`/`SNAPSHOT_ONLY` 的事实形态先与 legacy oracle 核对后再冻结测试（F8、DC16）；
  - golden 与 digest 按新语义一次性更新，更新理由写入 handoff；
  - 导入基线不新增条目；
  - 阶段末重建 current HEAD 镜像并运行既有 compose 旅程。History 旅程与空基线旅程的预期结果不变；非空基线上的 Preview
    可能因角色语义与 schema 事实而变化（R1 仍存在），有变化时在 handoff 说明原因，不作为验收失败。

### S2b — 切换到规范域、commit 规范元数据与 DC9

- 目标：设计 §4.6、§4.8、§5（W2，含 §5.5 的 DC9 与 DC19）、§10；关闭 A2 中 `http_arrow` 两条与 A6 中的 adapter。
- 前置：S2a exit pass，其中真实 Dolt 同一性 owner 通过。
- 内容：
  1. Preview：上传侧改为规范投影；PreviewResult 持久化规范表集合闭包、manifest、两侧规范状态摘要、投影规则集 digest；
     INITIAL 恒为空的断言（`INITIAL_BASELINE_NOT_EMPTY`）；
  2. AcceptSubmit：陈旧判定（含投影规则集 digest 与运行期不同）；`NO_CANONICAL_CHANGE` 由两侧规范状态摘要判定；删除
     基线自比流水线及其端口与适配器；T1 冻结闭包与 manifest、按闭包转移保护；删除 T1 与 prepare 的启发式；
  3. prepare：读取冻结闭包与 manifest；经 `RepositoryParentCatalogPort` 读取冻结 expected parent 的表目录并得出
     `removed_tables`；publication adapter 迁入 infrastructure；包进入 prepare checkpoint，重试复用；
  4. Repository 读取：`canonical_binding` 由 `CommitCanonicalMetadataPort` 提供（manifest digest 不符时稳定失败，DC25）；
     单遍读取；删除 hidden summary；`REPOSITORY_ROW_COUNT_MISMATCH` 为普通失败；HTTP Arrow adapter 只负责传输；
  5. DC9 删除清单（设计 §5.5，含 History 受理阻断与 HTTP 中的 integrity DTO 映射；保留 `HistoryIntegrityFailure`）；
     DC19 的读取不一致处置；
  6. control DB migration 与 HTTP 变更（设计 §10）；
  7. compose harness 改为不预导入基线数据（DC17）。
- 验收：
  - 设计 §12 的以下 owner 通过：`test_comparison_canonical_domain.py`（阶段门槛）、
    `test_repository_ref_materialization_protocol.py`、`test_preview_job_materialize.py`（ADDITIVE 激活、INITIAL 断言）、
    `test_submit_transactions.py`（陈旧拒绝、`NO_CANONICAL_CHANGE`）、`test_commit_canonical_metadata.py`（键与 scope、
    manifest digest、历史版本）、`test_submit_artifact_protection.py`、`test_submit_prepare_removed_tables.py`（integration，
    删表三种情形）、`test_submit_job_prepare.py`（unit，包 checkpoint 复用）、control DB migration 测试；
  - `NO_CANONICAL_CHANGE` 的不变量只由 `test_submit_transactions.py` 证明：`test_submit_http.py` 只保留 HTTP 错误映射，
    `test_production_wiring.py` 只保留接线断言，`test_preview_job_assemble.py` 与 `test_submit_application.py` 中的重复断言删除；
  - DC9 相关代码、路由、表、测试与测试支撑钩子已删除，OpenAPI 测试同步更新；ADR 0016 的 Operation integrity 测试不变且通过；
  - 导入基线：违例与运行时环基线为空；不可达基线只剩 S3 的 composite 与 XML 模块和已登记延期项；
  - compose：
    - 扩展旅程“提交 X → 审核 → 归档 → 再次上传 X”，Preview 全表 UNCHANGED，受理返回 `NO_CANONICAL_CHANGE`；
    - 规则表（显式键、存储丢弃列、ordered）在非空基线上的 Preview 不降级；
    - 用户删表后提交；未归档 sibling 在 main 上新增表后，下一个 Submit 成功并删除该表；
    - 全部旅程的 INITIAL 为空提交；History ordered 旅程结果不变，或在 handoff 说明变化原因；
    - 阶段末重建镜像；
  - 真实数据（DC22，关闭 F7）：4 份 dump 经主机侧脚本与公开 HTTP 接口完成 Preview → Submit → History；同一项目前后版本
    完成完整链路；结果按决议记录 §4 写入 handoff。

### S3 — composite_signal 接入

- 目标：设计 §8（W5）与 §4.4 中的 composite 规则变更。
- 内容：Preview 上传侧改用 `materialize_business_snapshot`；`logics.xml` 失败处置（DC8）；
  `composite_signal_point.source_table` 改为 `VARCHAR(64)` 并校验来源表名长度（DC20）；composite 规则变更。
- 验收：
  - composite 的 golden（规则变更后的规范形态）通过；
  - `test_canonical_snapshot_identity.py` 加入 `composite_signal_point`，并经真实 Dolt 导入验证（审核报告 §6 第 5 项）；
  - compose 旅程“仅修改 `logics.xml`”在 Preview 中可见，Submit 后进入 Repository，History 中可比较；
  - 无效 `logics.xml` 使 Preview FAILED 并给出明确诊断；
  - 不可达基线中 composite 与 XML 模块移除；
  - 带 `logics.xml` 的真实 dump 在 Preview → Submit → History 中通过；
  - 阶段末重建镜像。

### S4 — 项目身份与数据替换

- 目标：设计 §7（W4）。
- 验收：
  - 身份规则 v1 用合成夹具覆盖旧验收矩阵的判定类别：同项目、不同项目、排除 `no`、缺表、空表、没有非 `no` 列、列集合不一致；
    投影侧与 Repository 侧对同一内容得出相同 assessment；
  - 初始空基线的 pair 为 `NOT_APPLICABLE`，首次提交不需要确认；
  - 替换事实、比较级风险；Application 向 surface 传入两侧 `table_artifacts`，bundle 导出两侧快照；
  - 受理：输入边界（数量、重复 action、action 枚举、digest 格式、理由按 Submission 领域与 Review 相同的规则 → 422）用共享参数表覆盖；
    缺失 → 409 REQUIRED；多余或摘要不符 → 409 MISMATCH；判定顺序；指纹与重放；授权与 exact scope 先于重放，撤权或
    scope 不符的重放被拒（`test_submit_transactions.py` 补用例）；
  - Archive 身份异常处置与 StartArchive 校验；
  - Business Lifecycle 3.1.0 的身份相关条款实现完毕；
  - compose 旅程：跨项目上传 → 替换 Preview → 带确认提交 → 审核 → 带理由处置 → 归档；另加 `UNVERIFIABLE` 分支与
    FULL 混合模式（基线 pair 为替换、initial→modified 为详细比较）；
  - 真实数据：同一项目前后版本预期为 `SAME_PROJECT`，不同项目之间预期为 `DIFFERENT_PROJECT`；结果不符时在 handoff 记录并交 owner 判断；
  - 阶段末重建镜像。

### S5 — 清理、测量与收口验收

- 处置不可达基线：删除，或在 owning 设计中登记延期（owner、理由、重开条件）；登记后的条目保留在基线中并加注释。
  预期只剩 `external_target_sync` 与 canonical row hash 两组登记延期项。
- 文档：逐条核对 S0 接受时并入的 Contract 与设计文本和最终实现一致；实现中发现的偏差走 owner 修订，不在收口中静默改写。
- 按设计 §13 完成代表性链路测量，形成 Phase 6 候选列表；测量脚本只放在 `vnext/backend/benchmarks/`。
- 最终门禁：fresh 构建 current HEAD 镜像；全部 compose 旅程 0 skipped；`./vnext/scripts/run-tests.sh` 全量；五包静态检查；
  真实数据链路在最终候选上重跑一次（主机侧）。
- 交付 `pass_recommended` 与证据包；按 [P5 §2A.5](p5-business-vertical-slices-design.md) 逐项对照，由独立验收记录收口结论。

## 3. 路径预算

“必改”是阶段目标所必需的路径；“条件”只有在出现可复现缺口时才启用，启用时须在 handoff 中说明。新增文件名是建议，
实施可以调整命名，但须在 handoff 中说明并保持 owner 不变。不使用整层通配：只改导入路径的测试，由被迁移模块的导入方
决定，清单写入 handoff，这类改动不得修改断言。

### S1

- 必改（B）：
  - A1：`application/submission/ports.py`、`application/submit_jobs.py`；`infrastructure/repository_write/{http,abort_evidence,__init__}.py`，
    新增 `infrastructure/repository_write/wire_codec.py`；
  - A2：新增 `application/workspace/upload_admission.py`；`http/orchestration/{source_package_admission,multipart_upload,multipart_stream}.py`；
    `capabilities/source_package_staging/{__init__,contracts,staging}.py`（公开的受限成员枚举入口）；
  - A3：`application/submission/{abort_transaction,finalize_transaction}.py`，新增 `application/submission/artifact_release.py`；
  - A5：`domain/submission/models.py`、`artifacts/nominal_refs.py`，新增 `application/submission/artifact_refs.py`；
  - A6：删除 `canonicalization_manifest.py`、`canonicalization_cells.py`；删除 `repository_import_artifact.py` 中只被测试使用的
    `build_repository_import_package`、`write_repository_import_package`；`compute.py`、`canonical_row_hash_ipc.py` 移入
    `capabilities/canonical_row_hash/`（import 规则的精确放行见 S1 必改（T），DC26）；`synthetic_w2.py` 移至 T/support；
    `infrastructure/repository_write/http.py` 改从 storage_projection contracts 取媒体类型；
  - A7：`capabilities/{composite_signal,table_rules,snapshot_materialization}/contracts.py` 及各自 `__init__.py`；
  - A8：`application/{preview_jobs,submit_jobs}.py`、`application/history/compare_jobs.py`；
  - A9 / N-dead：删除 `cache/`、`capabilities/comparison/provider.py`（`capabilities/comparison/__init__.py` 去掉 provider 导出）、
    `capabilities/snapshot_materialization/cache.py`、`capabilities/{comparison_projection,business_projection}/`；
    `application/{synthetic_jobs,external_effect_stub}.py` 移至 T/support，`bootstrap/operation_worker.py` 去掉对应装配；
  - N-http-composition：新增 `bootstrap/composition.py`；`bootstrap/{operation_worker,http_server}.py`、`app.py`；`http/runtime.py`
    迁出后删除；`application/job_definitions.py`（job registry 由 Application 构建）；
  - N-http-bypass：`http/history_reader.py` 移至 `infrastructure/control_db/history_reader.py`；`http/dependencies.py`、
    `http/orchestration/preview_acceptance.py`、`http/schemas/{history,constraints}.py`；
  - N-infra-usecase：`infrastructure/control_db/sqlite_history_compare.py`、`infrastructure/repository_write/abort_evidence.py`；
    `application/history/{compare_bindings,contracts}.py`、`application/submission/{abort,contracts}.py`；
  - N-operations-private：`operations/contracts.py`、`application/{checkpoints,payloads}.py`；
  - Preview/History 受理用例：`application/workspace/preview.py`、`application/history/compare.py`；
    `http/orchestration/{preview_acceptance,history_compare}.py`；
  - job 模块复制（step plumbing 与 pair 流水线骨架，不改 checkpoint 载荷）：新增 `application/job_steps.py`、
    `application/pair_pipeline.py`；`application/{preview_jobs,submit_jobs}.py`、`application/history/compare_jobs.py`；
  - UoW 枢纽：新增 `application/control_transactions.py`（共享的最小控制事务协议）与 `application/workspace/ports.py`；
    `application/submission/ports.py`、`application/archive/ports.py`、`application/history/ports.py`；
    `infrastructure/control_db/database.py`；
  - N-cycles：`application/{job_definitions,payloads}.py`；`capabilities/comparison/{standard,ordered}.py`，新增共享行编码模块；
    `domain/submission/{models,policies}.py`；`http/{auth,dependencies}.py`；
    `infrastructure/control_db/{database,sqlite_baseline,sqlite_mapping}.py`。
- 必改（T）：
  - `test_architecture.py`（删除两个占位 owner 与对应 DAG 边；facade 规则；`IMPORT_RULE_SHAPES` 增加
    `capability:canonical_row_hash → ext:compute` 的放行；按新路径读取 compute 与 IPC 文件，更新禁止前缀表）、
    `architecture_baseline.py`；
  - `tests/support/import_rules.py`：精确放行 `capability:canonical_row_hash → ext:compute`（DC26），只对该 owner 生效；
  - 删除：`test_canonicalization_manifest.py`、`test_comparison_cache.py`、`test_snapshot_artifact_cache.py`；
  - `test_comparison_batch_boundary.py` 删除两个 provider 用例，保留批读取用例；`test_repository_import_artifact_package.py`
    删除与 identity package 的等价断言，可复现性与 ustar 断言保留；
  - `test_synthetic_w2.py`、`test_operation_job_synthetic.py`、`test_operation_job_recovery.py`、`test_operation_effect_reconcile.py`、
    `test_operation_worker_integration.py` 随 synthetic 模块迁移更新导入；T/support 接收 synthetic 模块；
  - `test_canonical_row_hash.py` 随模块迁移更新导入；
  - 其余只改导入路径的测试按上文规则确定。
- 条件：Rust 架构检查中的 Python 路径断言。

### S2a

- 必改（B）：
  - `capabilities/table_rules/{contracts,resolver,registry,__init__}.py`；
  - `capabilities/snapshot_materialization/{contracts,_digest,scalar_encoding,sql_declared_types,repository_ref,artifact,__init__}.py`；
  - `capabilities/storage_projection/{contracts,project,view,_digest,publish,__init__}.py`；
  - `capabilities/comparison/{contracts,pair_planning,standard,ordered,artifacts,__init__}.py`；
  - `capabilities/surface_assembly/{contracts,_assembly}.py`；
  - `application/preview_jobs.py`、`application/pair_pipeline.py`（S1 新增）、`application/workspace/preview.py`
    （Preview 受理冻结规则集 digest）、`application/history/{compare_jobs,compare,compare_bindings,contracts,errors}.py`；
  - `infrastructure/control_db/{migrations,sqlite_history_compare}.py`（History 受理冻结规则集 digest）；
  - `bootstrap/composition.py`、`http/dependencies.py`、`http/routes/history.py`，以及 `http/orchestration/history_compare.py`（或 S1 后承接其 DTO 映射的 HTTP 模块）：注入运行期规则集 digest，替代 History 受理使用的 `table_ruleset_version`。快照物化请求中的同名字段不在本项范围内。
- 必改（T）：
  - 新增：`test_canonical_snapshot_identity.py`（integration）、`test_canonical_state_identity.py`、
    `test_table_rules_comparison_view.py`、`test_comparison_rule_roles.py`；
  - 更新：`test_snapshot_materialization_contracts.py`、`test_snapshot_materialization_sql.py`、
    `test_snapshot_materialization_status.py`、`test_repository_ref_materialization_digest.py`、`test_table_rules_contracts.py`、
    `test_table_rules_resolver.py`、`test_storage_projection_core.py`、`test_storage_projection_contracts.py`、
    `test_storage_projection_publication.py`、`test_comparison_planning.py`、`test_comparison_standard.py`、
    `test_comparison_ordered.py`、`test_comparison_blank.py`、`test_comparison_records.py`、`test_comparison_artifacts.py`、
    `test_surface_assembly.py`、`test_surface_contracts.py`、`test_risk_contracts.py`、`test_risk_evaluation.py`、
    `test_preview_job_assemble.py`、`test_preview_job_payload.py`、`test_preview_job_worker.py`、`test_preview_application.py`、
    `test_history_compare_jobs.py`、`test_history_compare_transactions.py`、`test_workspace_control_db_migrations.py`、
    `test_architecture.py`（comparison 的上游改为 table_rules 与 snapshot_materialization）；
  - compose：`test_history_compose_e2e.py`、`test_ordered_compare_compose.py`（不再导入 `_table_policies_from_checkpoint`，
    也不再读取 checkpoint 中的 `table_policies`）；
  - T/support：`table_rules.py`、`table_rules_legacy_oracle.py`、`snapshot_materialization.py`、`storage_projection.py`、
    `history_compare_job_harness.py`、`history_compare_oracle.py`、`history_compare_checkpoint_tamper.py`、`preview_job_harness.py`、
    `submit_job_harness.py`（integration owner 复用其 Repository Service 启动）、`compose_gate_harness.py`（History oracle
    脚本改用新入口）、`http_workspace_harness.py` 与 `http_shutdown_harness.py`（注入运行期规则集 digest，替代
    `table_ruleset_version`）。
- 条件：`infrastructure/repository_read/http_arrow.py`（仅当 SET 解码修复需要同步 hidden summary 重建路径；该路径在 S2b 删除）；
  `capabilities/table_access/sql.py`（仅当普查发现的类型需要 SQL 解析支持）。

### S2b

- 必改（B）：
  - `capabilities/storage_projection/{import_replay,package,publish,__init__}.py`（`render_import_schema_sql` 与 `removed_tables`；
    adapter 所需的 facade 导出）；`capabilities/mutation_planning/{import_replay,__init__}.py`（DML 输入改为规范表行）；
  - `capabilities/snapshot_materialization/{contracts,repository_ref,__init__}.py`（`canonical_binding`、单遍读取、删除
    `read_hidden_summary`/`HiddenFinalSummary`/`HIDDEN_SUMMARY_*`、`REPOSITORY_ROW_COUNT_MISMATCH`、`snapshot_id` 派生、
    删除 `MaterializationDiagnostic.expected_digest_ref/observed_digest_ref`）；
  - `infrastructure/repository_read/http_arrow.py`（只负责传输）；新增 `infrastructure/repository_read/parent_catalog.py`
    （`RepositoryParentCatalogPort` 实现）；
  - 新增 `infrastructure/repository_write/import_publication.py`（adapter 迁入），删除 `repository_import_artifact.py`；
  - 新增 `infrastructure/control_db/sqlite_commit_metadata.py`（`CommitCanonicalMetadataPort` 实现）；
  - `application/preview_jobs.py`、`application/pair_pipeline.py`；`application/workspace/contracts.py`；
  - `application/submission/{accept,accept_transaction,contracts,ports,errors,import_builder,__init__}.py`、`application/submit_jobs.py`；
  - `application/history/{compare_jobs,compare,contracts,errors,ports}.py`（`application/history/compare.py` 删除受理阻断）；
  - `domain/workspace/models.py`、`domain/submission/{models,policies}.py`；
  - `infrastructure/control_db/{migrations,sqlite_workspace,sqlite_submission,sqlite_history_compare,database}.py`；
  - `bootstrap/{composition,operation_worker}.py`（新 port 接线；删除 `HttpBaselineCanonicalDigestPort`）；
  - `http/orchestration/submit_acceptance.py`、`http/dependencies.py`（删除 `FailClosedBaselineCanonicalDigestPort`）、
    `http/routes/{history,operations}.py`、`http/schemas/{operation,history,preview}.py`、`http/wiring.py`（`PRODUCTION_OPENAPI_PATHS`）、
    `http/errors.py`；`http/orchestration/history_compare.py`（或 S1 后承接其 DTO 映射的 HTTP 模块，删除 integrity DTO 读取与
    错误映射）；删除 `http/orchestration/history_integrity.py`。
- 必改（T）：
  - 新增：`test_comparison_canonical_domain.py`、`test_commit_canonical_metadata.py`（unit）、
    `test_submit_prepare_removed_tables.py`（integration）；
  - 删除：`test_history_compare_integrity.py`、`test_repository_ref_materialization_hidden_summary.py`；
  - 迁移：`test_repository_import_artifact_diagnostics.py` 随 adapter 迁移改名为 `test_submit_import_publication.py`；
  - 更新：`test_repository_ref_materialization_protocol.py`、`test_repository_ref_materialization_digest.py`、
    `test_repository_import_artifact_package.py`、`test_preview_job_materialize.py`、`test_preview_job_assemble.py`、
    `test_preview_job_publish.py`、`test_preview_job_worker.py`、`test_preview_job_payload.py`、`test_preview_application.py`、
    `test_submit_transactions.py`、`test_submit_application.py`、`test_submit_http.py`、`test_submit_artifact_protection.py`、
    `test_submit_job_prepare.py`、`test_submit_job_payload.py`、`test_submit_import_builder.py`、`test_submit_recovery.py`、
    `test_archive_concurrency.py`、`test_backend_readiness.py`、`test_production_wiring.py`、`test_history_compare_jobs.py`、
    `test_history_compare_transactions.py`、`test_history_http.py`、`test_operation_http.py`、`test_artifact_staging_conformance.py`、
    `test_http_openapi.py`、`test_workspace_control_db_migrations.py`、`test_submit_control_db_migrations.py`；
  - T/support：`repository_ref_materialization.py`、`history_compare_job_harness.py`、`preview_job_harness.py`、
    `submit_job_harness.py`、`http_workspace_harness.py`、`compose_gate_harness.py`（默认不预导入）、`upload_http_packages.py`；
  - compose：`test_submit_compose_e2e.py`、`test_archive_compose_e2e.py`、`test_history_compose_e2e.py`、
    `test_ordered_compare_compose.py`、`test_ordered_submit_bisect_compose.py`、`test_review_compose_e2e.py`（INITIAL 改为空提交后的种子方式）。
- 条件：`capabilities/snapshot_materialization/scalar_encoding.py`（仅当单遍读取暴露出 S2a 未覆盖的解码差异）；
  `infrastructure/repository_read/__init__.py`；`test_sqlite_submit_repository.py`、`test_submit_domain.py`、
  `test_workspace_domain.py`、`test_preview_read_http.py`（仅当新增的 PreviewResult/SubmitAttempt 字段在领域模型中为必填）。

### S3

- 必改（B）：`capabilities/table_rules/registry.py`（composite 规则）；`capabilities/snapshot_materialization/{compose,materialize,__init__}.py`
  （`source_table VARCHAR(64)` 与长度校验；业务物化的公开入口）；`application/preview_jobs.py` 或 `application/pair_pipeline.py`（业务物化接入）。
- 必改（T）：`test_snapshot_materialization_business.py`、`test_preview_job_materialize.py`、`test_storage_projection_core.py`、
  `test_canonical_snapshot_identity.py`、`test_table_rules_contracts.py`；T/support 的 `composite_signal.py`、`upload_http_packages.py`、
  `compose_gate_harness.py`；compose：`test_submit_compose_e2e.py`、`test_history_compose_e2e.py`（`logics.xml` 旅程）。
- 条件：`capabilities/composite_signal/contracts.py`（仅当来源表名长度校验需要 composite 契约配合）。

### S4

- 必改（B）：
  - 新增 `capabilities/project_identity/{__init__,contracts,_rule}.py`；
  - `capabilities/comparison/{contracts,pair_planning,__init__}.py`，新增 `capabilities/comparison/replacement.py`；
  - `capabilities/risk_evaluation/{contracts,_rules,_engine}.py`；`capabilities/surface_assembly/{contracts,_assembly}.py`；
    `capabilities/bundle_assembly/_assembly.py`（双侧导出，如需）；
  - `application/preview_jobs.py`、`application/pair_pipeline.py`、`application/workspace/contracts.py`；
  - `application/submission/{accept,accept_transaction,contracts,errors,review,review_contracts}.py`；
  - `domain/workspace/models.py`、`domain/submission/{models,policies,review}.py`（`domain/submission/review.py` 的理由规则提取为 Submission 领域共享校验，Review 行为不变）、`domain/archive/models.py`；
  - `application/archive/{queries,start,contracts,audit}.py`、`application/history/projection.py`；
  - `infrastructure/control_db/{migrations,sqlite_workspace,sqlite_submission,sqlite_archive,sqlite_review}.py`；
  - `http/schemas/{submit,preview,archive,review,history}.py`、`http/errors.py`、`http/orchestration/{submit_acceptance,archive,review}.py`、
    `http/routes/{submit_attempts,preview_results}.py`。
- 必改（T）：
  - 新增：`test_project_identity.py`、`test_comparison_replacement.py`；
  - 更新：`test_architecture.py`（project_identity owner 与 DAG 边）、`test_risk_contracts.py`、`test_surface_assembly.py`、
    `test_bundle_assembly.py`、`test_preview_job_assemble.py`、`test_preview_job_materialize.py`、`test_submit_transactions.py`、
    `test_submit_http.py`、`test_http_openapi.py`、`test_archive_transactions.py`、`test_history_projection.py`、
    `test_workspace_control_db_migrations.py`、`test_submit_control_db_migrations.py`、`test_archive_control_db_migrations.py`；
  - compose：`test_archive_compose_e2e.py`（跨项目、`UNVERIFIABLE`、FULL 混合模式）。
- 条件：`test_review_transactions.py`（仅当 Review 读取面的身份展示需要事务层配合）。

### S5

- 必改：不可达模块处置涉及的路径；`architecture_baseline.py`；owning 文档（仅限与实现的核对偏差）。
- 条件：测量脚本只放在 `vnext/backend/benchmarks/`，不进入生产包。

## 4. 测试归属与比例化

- 唯一 owner 见设计 §12；同一不变量不在多处重复证明。
- 同构错误使用模块级参数表：确认的输入边界与业务错误、规则集校验、F11 的 schema 变化类别、标量编码。
- 纯规则、解析与规范投影测试不引入 Dolt；真实 Dolt 只用于 integration 与 compose（AGENTS）。
- 新增持久事实（PreviewResult 规范绑定与身份结论、Attempt 冻结的闭包与 manifest、身份确认、Archive 身份异常事件）属于
  权威 A 类：覆盖事务、幂等、重放与并发代表点，沿用 5B/5C/5D 的测试模式，不建立全故障点矩阵。
- 删除机制时同时删除其 mock、fixture 与探针（比例化政策 §6.2），见 S2b 的 T/support 清单。

## 5. 命令草案

```bash
# 五包静态（提交前必跑）
for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done

# 导入边界现状
cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules

# 阶段 focused（按阶段替换文件集）
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -m unit -q
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -m integration -q

# S1 kickoff 普查与 S2b 起的真实数据链路（主机侧，不进入 CI）
GATEWAY_REAL_DUMP_ROOT=/home/dev/gateway-real-dumps \
  vnext/scripts/uv-consume.sh -C vnext/backend run python benchmarks/real_dump_census.py

# 阶段末与 S5 权威全量
./vnext/scripts/run-tests.sh
```

compose 旅程的运行方式、镜像重建与 provenance 记录沿用
[testing-conventions](../../../testing-conventions.md) 与 5D/5E 的 §6.3 最小格式。普查与测量脚本名为建议，实施时在 handoff 记录实际名称。

## 6. 镜像重建判定

| 阶段 | 是否重建 | 理由 |
| --- | --- | --- |
| S1 kickoff | 否 | 只做合入、复核与主机侧只读普查；普查脚本不进入生产包与镜像 |
| S1 | 是 | 进程组合（bootstrap、worker、HTTP 装配）改动，需要证明启动、装配与旅程不变 |
| S2a | 是 | 阶段退出；control DB migration 在启动时执行；需证明既有旅程结果不变 |
| S2b | 是 | compose harness、旅程与 HTTP DTO 改变；control DB migration；阶段退出 |
| S3 | 是 | 新增 compose 旅程 |
| S4 | 是 | 新增 compose 旅程与 HTTP DTO |
| S5 | 是（fresh） | 最终候选不得用旧镜像证明 |

Dockerfile、依赖锁与 Compose 预期不变；真实数据不挂载进容器（DC22）。如需修改镜像边界，按 AGENTS.md 的镜像规则执行并记录。

## 7. 停止规则

设计 §14 任一停止条件出现时，暂停当前阶段，在 handoff 记录触发事实并交 owner 处理；不得以兼容代码、
Application 特判或新增基线条目绕过。
