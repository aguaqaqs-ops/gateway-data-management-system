# P5 架构收口执行计划

状态：**ACCEPTED — S0 文档（r4）由 repository owner 于 2026-09-27 接受；实现未授权**

当前状态（2026-10-24）：**执行完成**。S1–S5 与治理修订 G1–G13 已完成并合入 `main`；P5 整体 exit review 经两轮修复与复审，于 2026-10-24 终审通过，附注 tag `p5-exit`（[exit review](p5-exit-review.md)、[修复 handoff](p5-exit-fix-handoff.md)、[治理修订计划](p5-arch-closure-post-s1-governance-plan.md) §3 第 13 项）。上一行“实现未授权”是 S0 接受时的状态；下文各节保留当时的计划与授权记录。

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
  -> [前置：真实数据格式保真（`@saved_cs_client`、`Digital value`、XML 深度；S1 合入后、S2a kickoff 前，治理修订计划 G2，见 §8.5）]
  -> [前置：control DB 基线 schema（治理修订计划 G3）；有序比较的骨架、移动与位置变化（G8b）]
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
3. 按设计 §2（R1–R6、E-a…E-i）复核 E 级事实，并对照新 HEAD 复核 §3 路径预算（已知漂移见 §8.6）；若有偏离，先修订设计对应
   章节再开工。
4. 真实数据普查（DC22）：
   - 数据的实际布局见 §8.3；其余按[决议记录 §4](p5-arch-closure-s0-owner-decisions.md#4-真实数据存放建议)执行，脚本经
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
  - 不可达基线共 **14 项**，按真实符号级可达性记录：
    - S3 composite 业务入口尚无可达调用方的 4 个模块（`composite_signal._ast`、`_bind`、`_digest`、`materialize`），
      以及 snapshot compose/catalog 与 XML parser 的 4 个模块（`snapshot_materialization._catalog`、
      `snapshot_materialization.compose`、`table_access._xml_parser`、`table_access.xml`）；这 8 项均由 S3 关闭；
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
     DC24；History 写入受理记录，需修改 control DB 基线 schema），每步执行前比较，不同即稳定失败
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
  6. control DB 基线 schema 修改与 HTTP 变更（设计 §10）；
  7. compose harness 改为不预导入基线数据（DC17）。
  8. **自 S1 延期（owner 2026-09-27）**：Preview/History 受理用例下沉至 Application，HTTP 仅 DTO 映射与准入（设计 §9 S1、§3 预算）。
  9. **自 S1 延期（owner 2026-09-27）**：workspace/archive/history 各自声明控制事务 port，组合在 bootstrap/infrastructure（UoW 枢纽拆分）。
  10. **自 S1 延期（owner 2026-09-27）**：Preview/Submit/History 三 job 共享 step plumbing（`pinned_checkpoint_builder` 等），checkpoint 载荷不变。
  11. **DC29（owner 2026-10-12，真实数据停止后）**：无主键表的兜底规则——SNAPSHOT_ONLY、BROWSE_ONLY 与 raw-PK 兜底规则使用
      `DDL_PRIMARY_KEY_OR_KEYLESS`；keyless 存储保留重复行、整表重写；比较用 `FULL_ROW_DIGEST_SET_DIFF`；Preview 表级只读提示
      `KEYLESS_FALLBACK`；Canonical Storage 升 `3.2.0`（决议记录 §12）。
  12. **DC31（owner 2026-10-15，t4 真实数据暂停后）**：`GetVersionedCatalog` 上限按 t4 实测的 4 倍确定，响应超限改为不可重试的
      `RESPONSE_LIMIT_EXCEEDED`（`GetOperation` 同样改用该错误码）；Preview、History 比较等读取类步骤的仓库读取错误分临时性与确定性两类，
      都以 `FAILED` 加 diagnostic 终态，worker 不因 handler 异常退出，重启后接管过期租约（决议记录 §14）。
- 验收：
  - 设计 §12 的以下 owner 通过：`test_comparison_canonical_domain.py`（阶段门槛）、
    `test_repository_ref_materialization_protocol.py`、`test_preview_job_materialize.py`（ADDITIVE 激活、INITIAL 断言）、
    `test_submit_transactions.py`（陈旧拒绝、`NO_CANONICAL_CHANGE`）、`test_commit_canonical_metadata.py`（键与 scope、
    manifest digest、历史版本）、`test_submit_artifact_protection.py`、`test_submit_prepare_removed_tables.py`（integration，
    删表三种情形）、`test_submit_job_prepare.py`（unit，包 checkpoint 复用）、control DB schema 测试（按表归属）；
  - `NO_CANONICAL_CHANGE` 的不变量只由 `test_submit_transactions.py` 证明：`test_submit_http.py` 只保留 HTTP 错误映射，
    `test_production_wiring.py` 只保留接线断言，`test_preview_job_assemble.py` 与 `test_submit_application.py` 中的重复断言删除；
  - DC9 相关代码、路由、表、测试与测试支撑钩子已删除，OpenAPI 测试同步更新；ADR 0016 的 Operation integrity 测试不变且通过；
  - 导入基线：违例与运行时环基线为空；不可达基线为 14 项，包含 S3 的 8 个模块与已登记延期项；
  - compose：
    - 扩展旅程“提交 X → 审核 → 归档 → 再次上传 X”，Preview 全表 UNCHANGED，受理返回 `NO_CANONICAL_CHANGE`；
    - 规则表（显式键、存储丢弃列、ordered）在非空基线上的 Preview 不降级；
    - 用户删表后提交；未归档 sibling 在 main 上新增表后，下一个 Submit 成功并删除该表；
    - 全部旅程的 INITIAL 为空提交；History ordered 旅程结果不变，或在 handoff 说明变化原因；
    - 阶段末重建镜像；
  - 真实数据（DC22，关闭 F7）：4 份 dump 经主机侧脚本与公开 HTTP 接口完成 Preview → Submit → History；同一项目前后版本
    完成完整链路；结果按决议记录 §4 写入 handoff。IEC104 有序表（含空白 gid 的表，治理修订计划 G8 决议）另须满足：
    1. Submit 后规范存储中 pseudo 段的行数与 census 一致（t1 各 4，t2 3,056 / 2,674，t3 各 9,858，t4 12,676 / 12,688）；
    2. 同一份 dump Submit 后再上传：这些表 Preview 无变化，Submit 返回 `NO_CANONICAL_CHANGE`；
    3. 同项目 v1→v2：这些表不降级；空白记录只反映各骨架区间空白行数的净变化，真实行的增删与移动不产生空白记录，一次移动不把其他行标为移动（依赖 G8b）；各类记录数量写入 handoff；
    4. 空白行字段的变化不显示，是接受的行为。
  - DC29（无主键表）：
    - unit：规则合法性（三类规则使用新策略，`device_cfg` 与显式键规则不变）、投影（源 DDL 有/无主键两种情形，重复行保留，内容摘要与行序无关）、
      比较（内容相同为 UNCHANGED、改一行为一删一增、表状态不为 DEGRADED 且无 `KEY_DEGRADED` 风险、主键出现或消失归 `SOURCE_SCHEMA`）各有参数表；
    - 真实 Dolt：同一性 owner `test_canonical_snapshot_identity.py` 增加一张含完全相同重复行的 keyless 表，写入并读回后行数与规范状态摘要一致；
    - compose：“提交 X → 审核 → 归档 → 再次上传 X”旅程的输入含一张 keyless 兜底表（含重复行），再次上传时该表 UNCHANGED；另有一次改动使该表显示一删一增；
    - 真实数据：t1–t4 不再因 `KEY_MISSING` 失败；各档 keyless 兜底表的数量与表名写入 handoff，重传时这些表 UNCHANGED；
    - 此前能投影成功的表，规范字节与内容摘要不变（golden 只因规则集与 manifest 的规则事实变化而更新，逐项说明）。
  - DC31（Catalog 与读取失败）：
    - Repository Service：上限常量、`RESPONSE_LIMIT_EXCEEDED` 与 Contract 文本一致；超限与未超限各一个用例；t3、t4 Catalog 离线估算字节数与取值写入 handoff；
      取证运行记录的各档 Catalog 实际字节数写入 handoff，上限不低于 t4 实际值的 3 倍（决议记录 §14 第一部分第 2 条）；
    - backend：故障注入参数表——Catalog 确定性错误 → operation `FAILED` 且公开 diagnostic 可见；临时性错误 → 重试后成功，或预算用尽后 `FAILED`；
      `RepositoryClientError` 不再落入 `UNCLASSIFIED`；handler 异常不使 worker 进程退出；
    - compose：Preview 进行中终止 worker，operation 最终进入终态；
    - 停止 handoff 中“重启后未重新领取、operation 保持 `RUNNING`”的路径已由 focused 测试复现并修复，handoff 写明。
  - 性能（DC30，经 DC31 修订；决议记录 §13、§14）：A 层——t1–t4 每个 operation 都在保护超时内进入终态，全程走完；B 层——按规模比例与墙钟/CPU 对比记录，
    疑似结构性的慢登记到 S5，不在 P5 修（使 A 层无法满足时除外）；C 层——handoff 给出各档各步的墙钟与 CPU 时间，只记录不判定。
  - 对照基准（DC31）：handoff 按档、按版本记录可经公开接口取得的结果事实（规范状态摘要、Preview 表级状态计数、Submit 结果、History 记录总数与 bundle / surface 摘要），
    不含行数据，作为 Phase 6 改写的正确性对照。

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
- 内容：按设计 §7.1–§7.7 实施；本节只列验收，路径见 §3。
- 验收：
  - 身份规则 v1 用合成夹具覆盖旧验收矩阵的判定类别：同项目、不同项目、排除 `no`、缺表、空表、没有非 `no` 列、列集合不一致；
    投影侧与 Repository 侧对同一内容得出相同 assessment；
  - 初始空基线的 pair 为 `NOT_APPLICABLE`，首次提交不需要确认；
  - 替换事实、比较级风险；Application 向 surface 传入两侧 `table_artifacts`，bundle 导出两侧快照；
  - 受理：输入边界（数量、重复 action、action 枚举、digest 格式、理由按 Submission 领域共享校验的多行模式 → 422，DC28）用共享参数表覆盖；
    缺失 → 409 REQUIRED；多余或摘要不符 → 409 MISMATCH；判定顺序；指纹与重放；授权与 exact scope 先于重放，撤权或
    scope 不符的重放被拒（`test_submit_transactions.py` 补用例）；
  - Archive 身份异常处置与 StartArchive 校验；
  - Business Lifecycle 3.1.0 的身份相关条款实现完毕；
  - compose 旅程：跨项目上传 → 替换 Preview → 带确认提交 → 审核 → 带理由处置 → 归档；另加 `UNVERIFIABLE` 分支与
    FULL 混合模式（基线 pair 为替换、initial→modified 为详细比较）；
  - 真实数据：同一项目前后版本预期为 `SAME_PROJECT`，不同项目之间预期为 `DIFFERENT_PROJECT`；结果不符时在 handoff 记录并交 owner 判断。
    范围（DC33）：t1–t3 完整运行；t4 只运行 v1 提交与 v2 Preview；`DIFFERENT_PROJECT` 用小档之间的跨档上传验证；不运行 t4 的重传 Preview 与 History；
  - 阶段末重建镜像。

### S5 — 清理、测量与收口验收

- 处置不可达基线：删除，或在 owning 设计中登记延期（owner、理由、重开条件）；登记后的条目保留在基线中并加注释。
  预期只剩 `external_target_sync` 与 canonical row hash 两组登记延期项。
- 文档：逐条核对 S0 接受时并入的 Contract 与设计文本和最终实现一致；实现中发现的偏差走 owner 修订，不在收口中静默改写。
- 按设计 §13 完成代表性链路测量，形成 Phase 6 候选列表；测量脚本只放在 `vnext/backend/benchmarks/`。汇总 S2b 起各阶段 C 层记录，
  列出登记到 S5 的 B 层问题（P5 不修，进入 Phase 6 候选，DC31）；按业务容量目标（约 t4 的 2 倍，Preview 10 分钟内，Phase 6 的退出目标）
  以 t4 实测外推并报告差距，写明外推的局限，并核对目标规模下 replay SQL 字节数与 Catalog 字节数的余量（DC30、DC31，决议记录 §13、§14）。
- **测量范围扩展（DC32，决议记录 §15；Phase 6 规划讨论稿 V2）**：
  - 阶段分段：Preview、Submit、History 的每一步拆到解析与物化、规范投影与表摘要、基线读取（RS I/O 与 Arrow → Python 转换分开）、比较、风险与 surface、
    artifact 写入、mutation planning 与回放、Repository 导入与提交，各段记录墙钟与 CPU；至少覆盖 t4 的 v1 / 重传 v1 / v2 Preview、v1 / v2 Submit 与 History，t1–t3 至少覆盖 v2 Preview；
  - 逐表成本：每张表、每个阶段的墙钟与线程 CPU，以及行数、列数、比较角色、是否 ordered、记录数、本次是否有变化；完整明细放在外部授权目录，handoff 给出按角色与行数区间的分布和耗时最高的表；
  - 基本操作吞吐：包解压、现有 SQL 解析、Arrow → Python 转换、现有摘要与 SHA-256 / BLAKE2b / BLAKE3、Arrow IPC 写入与内存映射读取、RS 逐表 Arrow 读取、同样规范数据直接导入 Dolt；只授权在 backend dev group 增加 `blake3`（条件见决议记录 §15 第三部分），不授权其他依赖；
  - 每个 operation 分别记录用户可见时间与完成时间；条件允许时按同一口径测一次旧实现的 t4 Preview，做不到时说明原因，不阻塞 S5；
  - 测量在进程内调用生产 capability 入口完成，不为测量改动产品代码；确需在产品代码内计时的，用不提交的临时补丁（G11b 先例）。测量是调试运行，不改变 S5 的通过条件，但结果是必交物。
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

### S2b — S1 复审延期路径（owner 2026-09-27；与 §8.5 S2b.0 对齐）

S1 结构修订未改 checkpoint 载荷与 golden 断言；下列路径在 handoff §3 登记延期，**必在 S2b 关闭或按条件启用**：

- `http/orchestration/preview_acceptance.py` — Preview 受理从 HTTP 下沉至 Application/workspace 用例。
- `application/workspace/{preview,ports}.py` — 受理编排与 workspace 端口拆分（UoW 枢纽按 owner 细化）。
- `application/archive/ports.py` — archive 侧 control 事务协议与 workspace/submission 对齐。
- `application/control_transactions.py` — 共享 control 事务面按 Preview/Submit/History owner 拆分。
- `application/job_steps.py` — 三 job 共享 step plumbing（`pinned_checkpoint_builder` 已在 S1 删除，仅保留 helper）。
- Preview/History 受理下沉、UoW 按 owner 拆分、三 job 共享 step plumbing — 与 §8.5 S2b.0 同一收口批次。

### S2a

- 必改（B）：
  - `capabilities/table_rules/{contracts,resolver,registry,__init__}.py`；
  - `capabilities/snapshot_materialization/{contracts,_digest,scalar_encoding,sql_declared_types,repository_ref,artifact,__init__}.py`；
  - `capabilities/storage_projection/{contracts,project,view,_digest,publish,__init__}.py`；
  - `capabilities/comparison/{contracts,pair_planning,standard,ordered,artifacts,__init__}.py`；
  - `capabilities/surface_assembly/{contracts,_assembly}.py`；
  - `application/preview_jobs.py`、`application/pair_pipeline.py`（S1 新增）、`application/workspace/preview.py`
    （Preview 受理冻结规则集 digest）、`application/history/{compare_jobs,compare,compare_bindings,contracts,errors}.py`；
  - `infrastructure/control_db/{schema,sqlite_history_compare}.py`（History 受理冻结规则集 digest）；
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
    `test_history_compare_jobs.py`、`test_history_compare_transactions.py`、`test_control_db_schema.py`（按表归属）、
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
  - `infrastructure/control_db/{schema,sqlite_workspace,sqlite_submission,sqlite_history_compare,database}.py`；
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
    `test_http_openapi.py`、`test_control_db_schema.py`（按表归属）；
  - T/support：`repository_ref_materialization.py`、`history_compare_job_harness.py`、`preview_job_harness.py`、
    `submit_job_harness.py`、`http_workspace_harness.py`、`compose_gate_harness.py`（默认不预导入）、`upload_http_packages.py`；
  - compose：`test_submit_compose_e2e.py`、`test_archive_compose_e2e.py`、`test_history_compose_e2e.py`、
    `test_ordered_compare_compose.py`、`test_ordered_submit_bisect_compose.py`、`test_review_compose_e2e.py`（INITIAL 改为空提交后的种子方式）。
- S2a 携带（2026-10-12，S2a 独立审核 S2a-F1、S2a-F2）：浮点负零归一所需的规范化路径（`capabilities/storage_projection/project.py`
  或 `capabilities/snapshot_materialization/scalar_encoding.py`，二者择一）；测试 `test_canonical_snapshot_identity.py`、`test_canonical_state_identity.py`。
- 真实数据链路（DC22）：新增主机侧脚本 `vnext/backend/benchmarks/real_dump_journey.py`（与 `real_dump_census.py` 同目录，不进入生产包与镜像），
  经公开 HTTP 接口驱动 Preview → Submit → History；可复用 `tests/support/compose_gate_harness.py` 的栈启动与认证。
- DC29（2026-10-12，决议记录 §12）：`capabilities/table_rules/{contracts,registry}.py`（新策略、三类规则、合法性校验、规则集版本）；
  `capabilities/storage_projection/{contracts,view,project}.py`（键解析、keyless 路径、manifest `3.2.0`）；
  `capabilities/comparison/{pair_planning,standard}.py`（keyless 兜底表的比较策略）；Preview 表级提示所需的 surface 或 DTO 路径
  （与 `http/schemas/preview.py` 合计最小集合，handoff 记录）；测试 `test_table_rules_contracts.py`、`test_table_rules_resolver.py`、
  `test_storage_projection_core.py`、`test_comparison_standard.py`、`test_canonical_snapshot_identity.py`、`test_http_openapi.py`；
  `vnext/fixtures/golden/storage-projection/` 中随规则事实变化的文件；compose 输入 `tests/support/upload_http_packages.py` 与承载
  再次上传旅程的 compose 测试文件。
- DC31（2026-10-15，决议记录 §14）：`vnext/repository_contracts`（wire 上限常量、错误码常量与导出）；`vnext/repository_service` 的
  `versioned_read/wire.py` 与 GetOperation 的响应上限路径、OpenAPI 与相关测试；`vnext/repository_client`（错误码映射，按需）；
  `docs/backend-vnext/refactoring/formal/contracts/repository-service.md`（上限与错误码）；backend `infrastructure/repository_read/http_arrow.py`
  与读取错误的分类路径、`operations/` 中 worker 异常与过期租约接管的修复路径（最小集合，handoff 记录）；对应 focused 测试与一条 Compose 旅程。
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
  - `domain/workspace/models.py`、`domain/submission/{models,policies,review}.py`（`domain/submission/review.py` 的理由规则提取为 Submission 领域共享校验，身份确认理由使用多行模式，Review 行为不变，DC28）、`domain/archive/models.py`；
  - `application/archive/{queries,start,contracts,audit}.py`、`application/history/projection.py`；
  - `infrastructure/control_db/{schema,sqlite_workspace,sqlite_submission,sqlite_archive,sqlite_review}.py`；
  - `http/schemas/{submit,preview,archive,review,history}.py`、`http/errors.py`、`http/orchestration/{submit_acceptance,archive,review}.py`、
    `http/routes/{submit_attempts,preview_results}.py`。
- 必改（T）：
  - 新增：`test_project_identity.py`、`test_comparison_replacement.py`；
  - 更新：`test_review_domain.py`（共享理由校验的两种模式，DC28）、`test_architecture.py`（project_identity owner 与 DAG 边）、`test_risk_contracts.py`、`test_surface_assembly.py`、
    `test_bundle_assembly.py`、`test_preview_job_assemble.py`、`test_preview_job_materialize.py`、`test_submit_transactions.py`、
    `test_submit_http.py`、`test_http_openapi.py`、`test_archive_transactions.py`、`test_history_projection.py`、
    `test_control_db_schema.py`（按表归属）；
  - compose：`test_archive_compose_e2e.py`（跨项目、`UNVERIFIABLE`、FULL 混合模式）。
- 条件：`test_review_transactions.py`（仅当 Review 读取面的身份展示需要事务层配合）。

### S5

- 必改：不可达模块处置涉及的路径；`architecture_baseline.py`；owning 文档（仅限与实现的核对偏差）。
- 条件：测量脚本只放在 `vnext/backend/benchmarks/`，不进入生产包；其测试放在 `tests/test_real_dump_*.py`（DC32）。不为测量改动产品代码。

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
| S2a | 是 | 阶段退出；control DB 基线 schema 变更（启动时结构不符即拒绝）；需证明既有旅程结果不变 |
| S2b | 是 | compose harness、旅程与 HTTP DTO 改变；control DB 基线 schema 变更；阶段退出 |
| S3 | 是 | 新增 compose 旅程 |
| S4 | 是 | 新增 compose 旅程与 HTTP DTO |
| S5 | 是（fresh） | 最终候选不得用旧镜像证明 |

Dockerfile、依赖锁与 Compose 预期不变；真实数据不挂载进容器（DC22）。如需修改镜像边界，按 AGENTS.md 的镜像规则执行并记录。

## 7. 停止规则

设计 §14 任一停止条件出现时，暂停当前阶段，在 handoff 记录触发事实并交 owner 处理；不得以兼容代码、
Application 特判或新增基线条目绕过。经 owner 明确批准的测量语义纠错可以更正起始基线；必须记录旧值、新值、工具语义变化与延期归属，
且不能掩盖新增的真实违例或运行时环。S1-F4 的 10→14 更正由 [S0 owner decisions](p5-arch-closure-s0-owner-decisions.md) §10 明确批准：
包级 facade 扩展改为按实际导入的 wrapper 符号展开，4 个 composite 模块归属 S3。该批准只修正测量口径；后续实现仍遵守只减不增。

## 8. 阶段推进约定

2026-09-27 由 repository owner 同意。目的是让每个阶段只凭一段简短提示词即可推进；本节不改变 §2 的验收与 §3 的预算。

### 8.1 授权、提交与阶段边界

2026-10-10 owner 同意改为主线开发（[治理修订计划](p5-arch-closure-post-s1-governance-plan.md) G1）：项目是全新项目，没有并行的使用方，阶段分支的主要成本是与 `main` 的同步和提交身份。S1 按原流程在 `p5-closure/s1` 实施并 `--no-ff` 合入（tag `p5-s1-exit`）；S2a 及之后的阶段按本节执行。

- 实现授权由 owner 按阶段给出，一次授权可以覆盖多个阶段；无论授权范围多大，阶段审核未通过都不进入下一阶段。
- 阶段实施直接提交到 `main`，在主工作区进行。只有确需并行的工作才开短期分支，完成后尽快合回 `main`。
  例外：main 同时接收其他对话的文档提交时，门禁运行期间主工作区会被写入。因此 G3、G8b 与 S2a 起的各阶段在独立 worktree `/home/dev/gdds-p5-<阶段>`
  与短期分支 `p5-<阶段>` 上实施，分支从 kickoff 时的 `main` 切出，不 merge/rebase `main`；门禁、carried 判定与审核复核都在该 worktree 内；
  审核通过后由审核方把报告提交快进到分支、在其上打 tag，再以 `--no-ff` 并入 `main`（见 G3 规格 §6）。新建的 linked worktree 需要先建 `legacy` 符号链接（AGENTS.md）。
  区间仍以上一阶段 tag 为起点；tag 与分支起点之间只有审核方的文档提交，审核时按提交区分。
- 阶段边界用附注 tag `p5-s<N>-exit` 标记，指向记录了通过结论的审核报告提交。审核对象是提交区间 `<上一阶段 tag>..<候选 SHA>`（S2a 的起点为 G2、G3、G8b 依次审核通过后的最后一个 tag，即 `p5-g8b-exit`；G2 自己的区间起点为 `p5-s1-exit`）；复审对象是 `<上次候选 SHA>..<新候选 SHA>`。
- 按 §8.4、§8.5 的子步推进，每个子步至少一个提交（提交信息形如 `refactor(p5-closure-s2a): ...`）。每个子步结束运行
  `import_rules` 与受影响的 focused 测试；`import_rules` 的输出只减不增，改名导致的条目替换在同一提交中说明。
  若 owner 批准修正错误的可达性测量，handoff 必须同时记录原计数、修正后的计数、语义依据与延期阶段；这只更正起始测量基线，
  更正后的后续实现仍遵守只减不增。S1-F4 的 10→14 是该类修正，且 4 项均明确归属 S3。
- 权威 runner 与容器门禁遵守 [AGENTS.md](../../../../../AGENTS.md)“跑测试”的运行前提和“镜像身份等价”：门禁提交 `V` 必须是已提交的 clean worktree；
  运行期间不在该 worktree 中写入任何文件，也不提交、不重建镜像；同一主机上整机单飞。handoff 与审核报告都在测试结束后写入。
- 实现者完成全部代码提交并在 `V` 上通过门禁后，最后一个提交只加 handoff（只改文档，不改变镜像构建上下文），即候选 `H`。
  审核对象是 `H`；实现者在最终回复中给出按 §8.7 填好的审核提示词，其中写明 `H`、`V` 与区间起点。
  `V → H` 的容器门禁结果按 AGENTS.md 沿用（`carried`），判定日志写在 worktree 外。
  例外（DC30）：V 与 H 之间允许只改 `vnext/backend/benchmarks/` 与 `tests/test_real_dump_*.py` 的提交，见 §8.9。
- 审核在新对话中进行，审核者不参与该阶段的实现。审核者在只读 detached worktree 中工作（`git worktree add --detach /home/dev/gdds-review-s<N>[-r<k>] <H>`），
  结束后删除；不在主工作区运行测试，避免与实施互相写入。报告按 §8.8 的模板写入 `plans/p5-arch-closure-s<N>-independent-review.md`
  （复审为 `plans/p5-arch-closure-s<N>-independent-rereview-<k>.md`），作为单独的纯文档提交，在审核 worktree 中提交后以
  `git merge --ff-only` 快进到 `main`（`main` 已前进时改为 cherry-pick 该提交）。审核者不修改代码、测试与 handoff，不推送。
- 结论为定向修订时，实现侧在 `main` 上追加修订提交，并在 handoff 末尾增加修订一节（逐项对应 finding）；最终回复给出按 §8.7
  填好的复审提示词。复审在新对话中进行，只核对修订差异与原 finding 的关闭情况。
- 审核通过后，由 owner（或 owner 授权的审核对话）在报告提交上打 `p5-s<N>-exit` tag；不推送，除非 owner 另行授权。
- 审核按阶段进行（§1），只审本阶段差异与 handoff；S5 另按 P5 §2A.5 做整体验收。

### 8.2 handoff

- 路径：`plans/p5-arch-closure-s<N>-handoff.md`；S1 kickoff 的记录写在 S1 handoff 的第一节。
- 最小内容：base 与 HEAD；子步与提交的对照；路径预算偏差（启用的条件路径及理由、文件改名）；`import_rules` 前后对照；
  验收 owner 及实际命令与结果；镜像重建记录（按 [testing-conventions](../../../testing-conventions.md) 的模板记录 image
  revision 与 source tree，延期时写明延期到哪个节点）；阶段之间的中间状态与延期项；停止条件（设计 §14）是否触发；
  请 reviewer 重点核对的内容。
- 区间与候选：handoff 记录 `range_start`（上一阶段 tag）、实现 HEAD（最后一个代码提交）、门禁提交 `V` 与候选 `H`；门禁在 `V` 上执行，`H` 只比 `V` 多 handoff 等文档。镜像记录按 testing-conventions 的模板填写，沿用时写 `carried` 及判定依据。
- 最后一节为“审核提示词”：按 §8.7 的审核模板填好除 `H` 之外的全部字段；“必须核查”取自 §2 本阶段的验收、§3 的
  本阶段预算、§8.4/§8.5 的保留项，以及上面列出的请 reviewer 重点核对的内容。
- 真实数据只记录 dataset ID、SHA-256、规模与结构统计（决议记录 §4）。
- 有真实数据运行的阶段，handoff 附各档各步的墙钟与 CPU 时间表，并写明 A、B 层核对结论（DC30）；调试期间的运行只概述次数与发现，不作为证据。

### 8.3 真实数据的实际布局

owner 于 2026-09-27 提供的数据位于 `$GATEWAY_REAL_DUMP_ROOT`（本机为 `/home/dev/gateway-real-dumps`），与决议记录 §4 的建议
布局不同：

```text
<tier>/<tier>-<n>/        # 原始工程目录；tier 为 small_cut、small、medium、large，每档 n = 1、2
  sql/dbcfg.sql
  comps/logic/logics.xml  # 其余文件不属于上传包
```

- 普查脚本按生产上传包的布局（`sql/dbcfg.sql`、`comps/logic/logics.xml`）确定性地打包为 TAR_GZ，写入 `$GATEWAY_REAL_DUMP_ROOT/packages/`，
  并生成 `$GATEWAY_REAL_DUMP_ROOT/datasets.json`（字段按决议记录 §4）。原始目录只读，不改名、不移动。
- dataset ID 映射：`small_cut` → t1、`small` → t2、`medium` → t3、`large` → t4；`-1`、`-2` 映射为 v1、v2。
- **Owner 确认（2026-10-10，决议 §10）**：同一规模档的 `-1`、`-2` 是同一项目的 v1、v2；不同规模档代表不同项目，不跨档配对。
  `datasets.json` 中每档 v2 的 `pair_of` 指向同档 v1；S2b 的同项目链路与 S4 的 `SAME_PROJECT`/`DIFFERENT_PROJECT` 预期以此为准。
- 目录权限按决议记录 §4 收紧为 700/600（2026-09-27 为 775/664），由 owner 执行。

### 8.4 S1 子步

每个子步都不改变行为，测试只改导入路径、不改断言（§2 S1）。

1. **S1.1 死代码**：A9 / N-dead，连同 §3 列出的测试删除。
2. **S1.2 包根模块**：A6。删除重复的 manifest 与 cells 模块；`compute`、`canonical_row_hash_ipc` 移入
   `capabilities/canonical_row_hash/`，同时加入 DC26 的精确放行；`synthetic_w2.py` 移至 T/support。
3. **S1.3 私有导入与 facade**：A1、A2、A3、A5、A7。
4. **S1.4 装配与越层**：N-http-composition、N-http-bypass、N-infra-usecase、N-operations-private，以及 Preview/History 受理用例。
   `bootstrap/operation_worker.py` 中 `build_worker_runtime` 的 `read_uow_factory`、`now_factory` 注入参数保留（`0d9d0d9dc5`
   新增，`test_submit_job_prepare.py` 使用）。
5. **S1.5 UoW 枢纽与环**：UoW 枢纽、N-cycles；结束时运行时环基线为空。
6. **S1.6 job 模块复制**：A8，新增 `application/job_steps.py`、`application/pair_pipeline.py`；checkpoint 载荷不变。
7. **S1.7 阶段门禁**：`import_rules` 输出与 §2 S1 验收一致；`./vnext/scripts/run-tests.sh` 全量；五包静态检查；重建镜像并
   运行既有 compose 旅程。

### 8.5 S2b 子步

0. **S2b.0 自 S1 延期项（owner 2026-09-27）**：关闭设计 §9 中未在 S1 完成的 Preview/History 受理下沉、UoW 枢纽拆分、三 job 共享 step plumbing；关闭标准与 S1 审核报告 S1-F3 一致（Application 受理、各域 port、共享 step helper 或等效结构）。
1. **S2b.1 commit 规范元数据**：`CommitCanonicalMetadataPort`、`sqlite_commit_metadata.py` 与 control DB 基线 schema 直接修改；测试按表归属。
2. **S2b.2 Repository 读取**：`canonical_binding`、单遍读取、删除 hidden summary、`REPOSITORY_ROW_COUNT_MISMATCH`；
   `http_arrow.py` 只负责传输（关闭 A2 的两条）。
3. **S2b.3 Preview**：上传侧规范投影；PreviewResult 持久化规范绑定；INITIAL 恒空断言。
4. **S2b.4 AcceptSubmit**：陈旧判定与 `NO_CANONICAL_CHANGE`；T1 冻结闭包与 manifest、按闭包转移保护；删除基线自比流水线与
   T1 启发式。
5. **S2b.5 prepare**：读取冻结闭包与 manifest；`RepositoryParentCatalogPort` 与 `removed_tables`；adapter 迁入 infrastructure
   （关闭 A6 的 adapter 条目）；包进入 prepare checkpoint。扩展 checkpoint 时同步更新允许的键集合，并保留 `0d9d0d9dc5` 的
   语义：checkpoint 的 attempt 绑定与 payload 不符时终止为 FAILED。
6. **S2b.6 DC9 与 HTTP**：设计 §5.5 的删除清单与 DC19；control DB 基线 schema 直接修改（测试按表归属）与 HTTP/OpenAPI 变更（设计 §10）。
7. **S2b.7 旅程与门禁**：compose harness 不预导入（DC17）与 §2 S2b 的旅程；真实数据链路；全量与镜像。
8. **S2b.8 无主键表兜底（DC29，owner 2026-10-12）**：在真实数据停止后追加，先于新的门禁提交 V 完成；内容见 §2 S2b 内容 11 与验收。
9. **S2b.9 Catalog 上限与读取失败终态（DC31，owner 2026-10-15）**：在 t4 真实数据暂停后追加，先于门禁提交 V 完成；内容见 §2 S2b 内容 12 与验收。

**S1 与 S2a 之间的真实数据格式保真前置（owner 2026-10-10，治理修订计划 G2）**：在 `main` 上依次修复 `table_access` 放行 mysqldump `@saved_cs_client`、composite AST 的 `Digital` 属性改为小写 `value`、按 8 份 `logics.xml` 的实测深度确定 `max_xml_depth`，并以诊断模式重跑普查更新 census JSON；独立审核后再启动 S2a kickoff。原 2026-09-27 的 parser 修复分支方案（`p5-closure/s1-parser`）由此取代。

S2a、S3、S4 按 §2 的内容顺序推进，不再细分。

### 8.6 开工前复核（2026-09-27）

- 代码相对文档基线 `2172369803` 的漂移只有 `0d9d0d9dc5`（prepare checkpoint 绑定修复）与 `4339a4c6ad` 的测试补充，共 5 个文件：
  `application/submission/errors.py`、`application/submit_jobs.py`、`bootstrap/operation_worker.py`、T/support 的
  `submit_job_harness.py`、`test_submit_job_prepare.py`。设计没有引用其中改动的符号；对实施的影响已写入 §8.4 第 4 项与
  §8.5 第 5 项。
- `import_rules` 在 `main` 上的输出与 `architecture_baseline.py` 一致（违例 54、运行时环 8、不可达 16），S4 与 prepare 修复
  期间没有新增条目。
- 真实数据已就位（§8.3），普查可以执行。
- 基线验证（代码与 `465b53746a` 相同）：`GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` 中 shared_kernel 242、
  repository_contracts 152、repository_client 154、backend 2705、repository_service 并行 1678（1 skipped）全部通过；
  repository_service 串行批次 197 通过、8 个 compose 用例因运行期间工作区有未提交的文档改动报 `worktree is dirty`
  （provenance 要求干净工作区），在 `028b957c26` 的干净工作区单独重跑 8 个全部通过。五包 ruff、mypy 通过。
  `0d9d0d9dc5` 的镜像重建仍延期到 S1 阶段末（S1 本身要求重建）。
- S1 kickoff 在 S1 的 base 上重新确认以上结果，并写入 S1 handoff。

### 8.7 提示词模板

尖括号内为占位符。实施者在最终回复中填好审核或复审提示词。`<R0>` 为区间起点（上一阶段 tag；G2 为 `p5-s1-exit`，S2a 为 `p5-g2-exit` 或 G3 的 tag）。

实施：

```text
按 docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-execution-plan.md 执行 S<N>（实现授权范围：S<N>）。
区间起点 <R0>；直接在 main 上实施（主工作区），按 §8 推进。门禁提交 V 与候选 H 按 §8.1、AGENTS.md 处理；
完成后写 handoff，并在最终回复中按 §8.7 给出填好的审核提示词。
```

审核：

```text
任务：独立审核 P5 架构收口 S<N>。你没有参与 S<N> 的实现；按
docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：main @ <H>（门禁提交 V = <V>，实现 HEAD <实现 HEAD>），区间 <R0>..<H>。只审该区间的差异。
  在只读 detached worktree 中工作：git worktree add --detach /home/dev/gdds-review-s<N> <H>；不在主工作区运行测试或写入。
权威依据：plans/p5-arch-closure-execution-plan.md（§2 S<N>、§3 S<N>、§8）、plans/p5-arch-closure-design.md（<本阶段章节>、§12、§14）、
  ADR 0018–0021、AGENTS.md；实现方记录 plans/p5-arch-closure-s<N>-handoff.md。
必须核查：
  <逐条列出：§2 本阶段验收、§3 本阶段预算、§8.4/§8.5 的保留项、handoff 请 reviewer 重点核对的内容>
验证：在审核 worktree 中自己运行五包 ruff/mypy 与 `import_rules`；核对 V 的门禁日志（起止 HEAD、clean status、runner exit code、
  镜像 provenance），并按 AGENTS.md“镜像身份等价”复核 V → H 的 `carried` 判定。不接受旧镜像或其他工作区的结果。
  不要求重跑全量 runner；若需要重跑，按 AGENTS.md 的运行前提在已提交的 clean worktree 上整机单飞执行。
交付：按执行计划 §8.8 写 plans/p5-arch-closure-s<N>-independent-review.md，作为单独的纯文档提交，快进合入 main；
  除该报告外不修改任何文件；不推送，不打 tag。
审核允许结论：通过 / 定向修订 / 整体返工。
```

复审：

```text
任务：独立复审 P5 架构收口 S<N> 的修订。你没有参与 S<N> 的实现与修订；按纵切指南 §7 复审。
审核对象：main @ <新 H>（门禁提交 V = <V>）；上次审核对象 @ <上次 H>，报告 plans/p5-arch-closure-s<N>-independent-review.md
  （或上一份复审报告）。只核对 <上次 H>..<新 H> 的修订差异、原 finding 的关闭情况与改动传播；已关闭且未受影响的问题不重开。
验证：修订涉及的 focused 测试；修订触碰 §6 的镜像边界时，核对新的门禁与镜像记录，沿用结果时复核 `carried` 判定。
  在只读 detached worktree 中工作，不在主工作区写入。
交付：按执行计划 §8.8 写 plans/p5-arch-closure-s<N>-independent-rereview-<k>.md，作为单独的纯文档提交，快进合入 main；
  除该报告外不修改任何文件；不推送，不打 tag。
审核允许结论：通过 / 定向修订 / 整体返工。
```

### 8.8 审核报告模板

```markdown
# P5 架构收口 S<N> 独立审核（复审时写“第 <k> 次复审”）

- 结论：**通过 / 定向修订 / 整体返工**
- 日期：<YYYY-MM-DD>
- 审核对象：main @ `<H>`（门禁提交 V `<SHA>`，实现 HEAD `<SHA>`），区间 `<R0>..<H>`
- 依据：执行计划 §2 S<N>、§3 S<N>、§8；设计 <章节>；handoff

## 1. 结论摘要

<两到五句：阶段目标是否达成，阻塞项数量，是否可以打阶段 tag 并进入下一阶段>

## 2. Findings

每项一个小节；没有 finding 时写“无”。

### <编号，例如 S1-F1>：<一句话标题>

- 类型：已证实缺陷 / 待验证假设 / 非阻塞建议；是否阻塞：是 / 否
- 位置：<文件:行 或 提交>
- 依据：<计划、设计、Contract 条款或源码事实>
- 触发场景与影响：<具体输入或状态 → 错误结果>
- 最小修正方向：
- 关闭标准：<复审时如何判定已关闭>

## 3. 验收核对

| 验收项（执行计划 §2 S<N>） | 结果 | 证据 |
| --- | --- | --- |

## 4. 实际执行的检查

| 检查 | 命令 | 结果 |
| --- | --- | --- |

## 5. 验证限制与剩余前置

<未能验证的内容及原因；进入下一阶段前须满足的条件；延期项及其节点>

## 6. 复审记录（仅复审）

| 原 finding | 关闭情况 | 依据 |
| --- | --- | --- |
```

### 8.9 调试与取证（DC30，owner 2026-10-14）

- 调试：只跑 focused 测试与出问题的那一段真实数据；可在未提交的 worktree 上运行；不跑完整 runner；这些运行不作为证据，
  日志可写到 `/home/dev/gdds-p5-closure-s1-gate-logs/<阶段>-debug-*`。真实数据的调试同样遵守整机单飞（Dolt 进程、Compose 栈、8000 端口）。
- 节点分工（DC36，2026-10-24 生效）：调试在调试节点 `ct108-gw-dms-05`；权威 runner、容器门禁与 carried 在门禁节点 `ct108-gw-dms-04`；
  Phase 6 性能测量与真实数据 t4 在参考节点 `ct108-gw-dms`，t1–t3 在调试节点。各节点分别满足单飞与运行前提；日志开头记录 `hostname` 与起止时间。
- 取证：调试收敛后，在最终 V 上完整运行权威 runner 一次，并在同一 V 上运行真实数据一次（preflight 与日志要求同 §8.1、AGENTS.md）。
  DC36 起二者可在不同节点上并行；为减少门禁失败时的浪费，可在门禁的并行批次通过后再启动真实数据。
  真实数据的范围由阶段改动面决定，在阶段 kickoff 时写明，阶段退出前由 owner 确认；S3 为新 V 上的 t4 完整与 t1 冒烟、t2/t3 沿用 `f73deee604`（owner 2026-10-17，治理修订计划 §3 第 9 项），S5 最终候选为完整 t1–t4，S4 见 §2 S4，2026-10-20 停止后的修订见治理修订计划 §3 第 11 项（DC33，治理修订计划 G12）。
  权威 runner 中闭包未变化的包，按治理修订计划 G12 第 1 项与 [testing-conventions.md](../../../testing-conventions.md) 的来源 V 规则沿用结果；S5 最终门禁仍运行全部包。
  闭包 manifest 包括该包实际 uv 环境的内容摘要（排除由锁定源码和解释器派生的 Python bytecode）及有效
  Hypothesis storage directory 和包内 `.pytest_cache` 的内容摘要；Hypothesis Unicode JSON gzip 以解压后的 payload 摘要。比较和来源 V 条件见 [AGENTS.md「跑测试」](../../../../../AGENTS.md) 与
  [testing-conventions.md](../../../testing-conventions.md)。
  按包沿用遵循[治理修订计划 G12 第 1 项](p5-arch-closure-post-s1-governance-plan.md)及
  [testing-conventions.md](../../../testing-conventions.md)，其中 backend/RS 的 Compose 闭包还比较有效 build 设置、镜像选择、本机 image ID，以及 Docker context 内 tracked 路径和祖先目录的本机权限模式。
  取证失败且需要改产品代码：回到调试，收敛后形成新的 V 再取证一次。
- V 之后、H 之前只改 `vnext/backend/benchmarks/` 与 `tests/test_real_dump_*.py`（不进入镜像）：门禁结果沿用；在最终提交上补跑这两个测试文件与五包静态检查，
  重跑真实数据；carried 照常在同一 worktree 判定；handoff 列出 V 之后的这些提交。
- 真实数据脚本：支持只跑某一档、从指定步骤开始、开发模式保留栈；每一步完成即核对；事件带时间戳并记录各容器 cgroup `cpu.stat`；
  先跑 t1，t1 通过后再跑 t2–t4；核对走公开 HTTP 接口，不在容器内执行核对代码；保护超时按 DC30。
