# P5 架构收口 S2a handoff

## 1. 候选、区间与 worktree

- 阶段：S2a「规范快照与比较规则的能力层」。实现授权范围仅为 S2a。
- 独立 worktree：`/home/dev/gdds-p5-s2a`；分支：`p5-s2a`。
- 分支 base：`1c7398572f5477c983e0562efd020828a3653ba0`。
- 区间起点 `R0`：`p5-g8b-exit`，`3c3d71fed13b152e2f023e5bf22b0050c029d681`。
- 最后一个代码提交与门禁提交 `V`：`741d227991f8b76235a36649830f34b3920df6f0`。
- 候选 `H`：本 handoff 所在的最后一个文档提交；其 SHA 在实施者的审核提示词中填写。
- `R0..H` 内的审核方文档提交按提交区分：`e04a6eb041`（合并 G8b）、`57fb9b4dc8`（G8b exit 与 S2a 携带项记录）、`1c7398572f`（独立 worktree 形式与 G8b-F2 决议）。它们先于 S2a 实现分支的 base，不属于本阶段实现提交。
- 新 worktree 已建立 `legacy -> /home/dev/gateway-data-management-system/legacy` 符号链接；`./vnext/scripts/prepare-dev-dependencies.sh` 成功。五个 `uv.lock` 与 base 一致，SHA-256 如下：

  | 包 | SHA-256 |
  | --- | --- |
  | `shared_kernel` | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
  | `repository_contracts` | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
  | `repository_client` | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
  | `backend` | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
  | `repository_service` | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |

## 2. 内容项与提交

| S2a 项 | 提交 | 实施与 owner |
| --- | --- | --- |
| 1. table_rules | `396cfa2d28` | 增加 `ComparisonRuleView`、`ComparisonRuleSet`、`compare_excluded_columns` 与列处置校验；9 条 ordered 规则不再把 `no` 放入 `ignored_columns`。owner：`test_table_rules_comparison_view.py`、table-rules contracts/resolver tests。 |
| 2. snapshot_materialization | `c3a44e785b`, `52229dcfd0`, `f5073e792a` | 增加 business schema digest、canonical state digest、SET 解码和 descriptor 类型规范化（ordered `no` 为 NOT NULL）；Snapshot/Summary 编解码并入 contracts，合并 Preview/History 的 summary 构造。owner：`test_canonical_state_identity.py`、`test_snapshot_materialization_contracts.py`。 |
| 3. storage_projection | `937c7b4cb9` | 增加 `project_canonical_table_set`、`publish_canonicalization_manifest`，键类型与键列 NOT NULL 约束、一次收集全部失败诊断；`CanonicalizationManifest.contract_version` 写入 `3.1.0`，解码接受历史版本。owner：`test_storage_projection_core.py`、contracts/publication tests、真实 Dolt `test_canonical_snapshot_identity.py`。 |
| 4. comparison | `24db2eb802` | 使用运行期 `ComparisonRequest`/规则集；实现角色事实、按列名及有效键对齐、规则侧存储事实标注 schema 差异来源、business schema digest 一致才提前退出；移除流程词汇并将 `ComparisonTablePolicy` 收为内部类型。包含 G8b-F1 与 G8b-F3。owner：`test_comparison_rule_roles.py`、`test_comparison_planning.py`、standard/ordered tests。 |
| 5. surface_assembly | `d0c44c55f9` | surface 自有中性身份标注，不再导入 comparison 的 `IdentityStatus`；表级内容事实进入 Preview/Review 变化计数。owner：`test_surface_assembly.py`。 |
| 6. Application | `711870cf97` | Preview job payload 与 History 受理记录冻结运行期规则集 digest；每步执行前比较，分别以 `PREVIEW_RULESET_VERSION_MISMATCH`、`HISTORY_RULESET_VERSION_MISMATCH` 稳定失败。History control DB 直接改基线 schema；移除旧 policy/checkpoint 转换函数；更新 History compose oracle。包含 G3-F2、G3-F3。owner：`test_preview_job_worker.py`、`test_history_compare_jobs.py`（含恢复）、`test_history_compare_transactions.py`、`test_control_db_schema.py`（按表归属）。 |
| gate 修复 | `efa65ed077` | 按新 checkpoint 合同更新 Preview materialize checkpoint 的期望诊断，并增强 Compose operation timeout 诊断，便于区分终态失败与持续 RUNNING。 |
| gate 修复 | `741d227991` | Submit manifest 候选过滤排除 `comparison-ordered-*` 与 `comparison-blank-*` 工件；增加参数化覆盖。详见 §8。 |

每个代码提交后均执行五包 ruff/mypy、`import_rules` 和受影响的 focused tests；逐提交结果由对应提交与 focused 日志留档。`test_preview_job_assemble.py -k materialize_checkpoint` 在 checkpoint 诊断更新后为 5 passed。`test_ordered_history_compare_compose_journey` 在最终代码修复后单独复现通过，1 passed in 171.56s。完整、最终的 owner 验收以 §5 的 V 权威 runner 为准。

## 3. 路径预算与 import_rules

- S2a §3 的必改 B/T 路径已按内容项实施。条件路径 `infrastructure/repository_read/http_arrow.py` 未启用；`capabilities/table_access/sql.py` 未启用，因为现有 SQL parser 已识别普查中的类型。
- 预算外路径及理由：
  - Preview 的 HTTP 受理接线 `http/orchestration/preview_acceptance.py`、`http/routes/preview_operations.py` 与 `test_preview_http.py`：S1 的 HTTP-hosted Preview 入口需把实际运行期 comparison ruleset digest 传入 Application，才能在该入口冻结 digest 并验证 mismatch。
  - `capabilities/storage_projection/package.py`：补齐 storage projection 的公开 facade，供投影与发布入口使用 snapshot-materialization 所有的规范类型；未扩大导入基线。
  - `application/submission/contracts.py`、`test_submit_transactions.py`：由 V1 Compose 可复现故障触发，修复 Submit 把 comparison 工件误判为 snapshot manifest 的候选筛选。问题与修复过程见 §8。
- 控制库采用单一基线 schema：`infrastructure/control_db/schema.py` 直接加入 History acceptance 的 ruleset digest 列，不增加 migration；schema 测试由 `test_control_db_schema.py` 按表归属。
- `import_rules`：S2a base 前后为 **3 violations / 0 runtime cycles / 14 unreachable**；最终仍为 **3 / 0 / 14**，没有增加基线条目。命令：`cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules`。comparison architecture DAG 的 upstream 改为 `table_rules` 与 `snapshot_materialization`，这是 DAG 所有权更新，不是新增 import baseline 条目。

## 4. 比较语义、legacy oracle 与中间状态

### Legacy oracle（F8、DC16）

实现前核对了：

- `legacy/backend_vnext/capabilities/comparison/planner.py` 与 `engine.py`：BROWSE_ONLY 保留表级事实，返回 UNCHANGED 形态，不执行行级比较、不生成行记录。
- `legacy/backend_vnext/capabilities/surface_assembly/assembler.py`：BROWSE_ONLY 映射为 TABLE_BROWSE。
- `legacy/backend_vnext/capabilities/table_rules/semantic.py`：SNAPSHOT_ONLY 不进入详细比较（`enters_comparison=False`）。

S2a 测试冻结的 DC16 形态为：BROWSE_ONLY 和 SNAPSHOT_ONLY 的内容变化均能作为表级“内容已变化”事实呈现；两者不产生行级记录。schema 事实适用于所有存储角色。该差异是本阶段的事实形态扩充，与设计 §4.3/§4.5、Canonical Storage §7 一致；legacy oracle 未显示冲突，未触发设计 §14 停止条件 3。对应参数化角色 owner 为 `test_comparison_rule_roles.py`。

### 规则集、checkpoint 与表面事实

- `ComparisonRequest` 携带运行期 `rule_set` 和 mode；比较结果以两侧实际规则侧存储事实标注 schema 差异来源，并按列名与有效键对齐。
- Preview 在受理时把 ruleset digest 冻结进 job payload；History 在受理记录中冻结 digest。Preview/History 每步执行前比对运行期 digest，恢复时不静默采用新规则。
- Preview 与 History 的 Snapshot/Summary document 编解码统一由 `snapshot_materialization.contracts` 提供。History materialize checkpoint 不再携带 `compare_binding_preimage`、`compare_binding_digest` 或 `table_policies`；该 checkpoint 保留序列化的 `sides`，assemble 从冻结的 ruleset 生成比较请求。旧的 `_project_table_policy`、`_policy_to_checkpoint_dict`、`_table_policies_from_checkpoint` 已删除。checkpoint 载荷变化是本阶段有意的合同变化，不做旧字段兼容。
- Preview 上传侧在 S2a 结束时仍物化为原始 snapshot；Preview 规范投影留给 S2b 的 R1。
- 非空基线 Preview 的表级事实或变化计数可能因 BROWSE_ONLY/SNAPSHOT_ONLY 内容事实、所有角色均可见的 schema 事实而变化；这些变化按新角色语义解释。History oracle 与空基线旅程的预期结果保持不变，最终 Compose 旅程通过。

## 5. 验收 owner 与实际命令

五包静态检查均通过，命令对每个包分别执行：

```bash
cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
```

`<package>` 依次为 `shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service`。权威入口命令为 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`；其 backend 子命令为 `../scripts/uv-consume.sh -C . run pytest -q`，repository_service 按 runner 规定分为 parallel 与 `-n 0` serial 两批。S2a §2 的下列 owner 全部在 V 的该次运行中通过：

| owner | 归属的验收范围 | 实际命令/结果 |
| --- | --- | --- |
| `test_table_rules_comparison_view.py`、table-rules contracts/resolver tests | ComparisonRuleView/RuleSet 派生、列处置、ordered `no` | backend runner；通过 |
| `test_canonical_state_identity.py`、`test_snapshot_materialization_contracts.py` | business schema/canonical state digest、SET 与类型规范化、共享 Snapshot/Summary contracts | backend runner；通过 |
| `test_canonical_snapshot_identity.py` | 真正 Repository Service + Dolt 往返，含 DC15 类型与 FLOAT | backend runner；integration owner 通过 |
| `test_storage_projection_core.py`、`test_storage_projection_contracts.py`、`test_storage_projection_publication.py` | canonical set、manifest、全部失败诊断、键约束及 manifest 版本 | backend runner；通过 |
| `test_comparison_rule_roles.py` | BROWSE_ONLY/SNAPSHOT_ONLY/UPDATE_ONLY/ordered、compare-excluded、表级内容与 schema 事实 | backend runner；通过 |
| `test_comparison_planning.py`、`test_comparison_standard.py`、`test_comparison_ordered.py` | 按列名/有效键对齐及 schema 来源；G8b-F1 参数行 | backend runner；通过 |
| `test_surface_assembly.py` | 表级内容事实与 Preview/Review 变化计数 | backend runner；通过 |
| `test_preview_job_worker.py`、`test_history_compare_jobs.py` | Preview/History digest mismatch 与激活后恢复失败，包括 materialize 前发生激活 | backend runner；通过 |
| `test_history_compare_transactions.py`、`test_control_db_schema.py` | History 受理时冻结 digest 与单一基线 schema | backend runner；通过 |
| `test_history_compose_e2e.py`、`test_ordered_compare_compose.py` | History oracle 新入口；History 与 ordered Compose journeys | backend runner；通过 |
| `test_preview_job_assemble.py -k materialize_checkpoint` | checkpoint 形状及稳定诊断更新 | `cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -q tests/test_preview_job_assemble.py -k materialize_checkpoint`；5 passed |
| `test_ordered_history_compare_compose_journey` | V1 故障修复后的完整有序 Submit/History 旅程 | `cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -q tests/test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey`；1 passed in 171.56s |

V 权威 runner 的批次结果：

| 批次 | 结果 |
| --- | --- |
| `shared_kernel` | 242 passed |
| `repository_contracts` | 152 passed |
| `repository_client` | 154 passed |
| `backend` | 2794 passed，1 条 Starlette/httpx deprecation warning，19:54.99 |
| `repository_service (parallel)` | 1681 passed, 1 skipped，15.08s |
| `repository_service (serial)` | 205 passed, 1682 deselected，344.36s |
| 总计 | 5228 passed, 1 skipped；权威 runner exit code 0 |

`test_canonical_snapshot_identity.py` 为真实 Dolt integration 测试，包含在 V 的 backend batch 中并通过；这满足 S2b 的门槛。

## 6. Golden、digest 与 Contract 变化

按新语义一次性更新了 9 个 golden 文件；没有新增 import baseline 项：

- Snapshot Materialization SQL 的 5 个 expected JSON：增加 per-table `business_schema_digest` 与 `canonical_state_digest`，并按新的规范 descriptor/state identity 更新 `snapshot_digest`。未知类型的 partial fixture 保留 fail-closed，失败表没有 canonical state digest。
- Storage Projection 的 `s5-durable-roundtrip/document.json`：manifest 写入版本更新为 `3.1.0`。
- Ruleset fixtures `s1-duplicate-selector`、`s1-net-cfg`、`s2-migrated-matrix`：输出新增 `compare_excluded_columns`；9 条 ordered 规则从 `ignored_columns` 移除 `no`；比较排除列由原 ignored 语义迁入新字段。错误与有效 fixture 都同步新合同。

digest 改变来源是 business schema digest 与 canonical state digest 正式进入 Snapshot/Summary identity，以及 descriptor 类型规范化/列处置合同变化；这些 golden 变化是 S2a 所有权切换的预期结果，不是未解释的行为漂移。History/Preview checkpoint 从旧的 table policy/compare-binding 派生载荷转为 side snapshots 加运行期 ruleset digest 冻结；其载荷变化已在 §4 记录。

## 7. DC12、DC14、DC15 与 DC16

- **DC12 未触发**：census `dc12_json_columns_present=false`。JSON 继续 fail-closed，不改 LONGTEXT 存储映射；storage projection version 保持不变。若后续真实数据普查出现 JSON 列，按设计 §14 与 DC27 重开存储类型及 storage projection version 判断。
- **DC15 已触发**：8 份 census 的 storage column type 总计为 `INT UNSIGNED` 6018、`TINYINT UNSIGNED` 2438、`SMALLINT UNSIGNED` 224、`FLOAT` 422、`DATETIME` 64；此外 `ENUM` 3049、`INT` 686、`SET` 8、`TEXT` 414、`TINYINT` 96、`VARCHAR` 6709；`dc15_unknown_sql_types=[]`。S2a 类型词表扩展并经真实 Dolt 同一性 owner 往返。FLOAT 的真实往返通过，没有落入设计 §14 停止条件 2。
- **DC14**：storage projection 失败诊断一次收集并返回全部可复现失败，owner 为 `test_storage_projection_core.py`，V runner 通过。
- **DC16**：事实形态与 legacy 核对结论见 §4；角色测试冻结表级事实并确认无行记录。

## 8. G8b/G3 携带项与门禁修复过程

| 携带项 | 处置 |
| --- | --- |
| G8b-F1 | `comparison/ordered.py` 的 `ordered_extension.status` 当且仅当 `table_processing_mode` 非空时为 CHANGED；`test_comparison_ordered.py` 参数表覆盖尾部只增删空白行。 |
| G8b-F3 | `contracts/risk.md` 的 `position_changed_count` 说明引用 R5 §8；仅计 skeleton rows，不含 moved rows。 |
| G3-F2 | `test_provisioned_scope_seed.py` 注释改为“前三行在批次校验阶段失败，后两行在写入阶段失败并依赖回滚”；仅改注释，预算外路径。 |
| G3-F3 | 设计 §10 删除“新增列允许旧行为空”；保留单一基线 schema 的直接修改规则。 |

第一次完整门禁在 `V1=711870cf97f831db7fdfd5e7c810b7603f8211fc` 运行，exit code 1；日志：`/home/dev/gdds-p5-closure-s1-gate-logs/s2a-gate-711870cf97.log`。该轮 backend 为 2782 passed、5 failed；4 个是 Preview checkpoint 新错误诊断后的旧期望，提交 `efa65ed077` 同步测试和 Compose timeout 诊断。另一个 `test_ordered_history_compare_compose_journey` 可复现失败：`comparison-ordered-*` Parquet 工件被 Submit 当成 snapshot manifest，worker step 1 超时并保持 RUNNING。提交 `741d227991` 将 ordered/blank comparison artifact 前缀从 snapshot manifest 候选中过滤；独立 Compose 复现通过，1 passed in 171.56s。没有用定向重跑替代最终门禁。

最终门禁 `V=741d227991f8b76235a36649830f34b3920df6f0` 的日志：`/home/dev/gdds-p5-closure-s1-gate-logs/s2a-gate-741d227991.log`。V1/V2 的 Compose provenance 与镜像检查记录分别位于同目录下 `s2a-v1-last-compose-provenance.json`、`s2a-v1-provenance-and-images.log`、`s2a-v2-last-compose-provenance.json`、`s2a-v2-provenance-and-images.log`。

## 9. 镜像、V→H carried 与 clean 状态

V2 在 clean worktree 上执行：

1. preflight 于 `2026-10-11T16:30:09Z` 完成：`git status` clean、`pgrep -x dolt` 无结果、无带 Compose project label 的容器、8000 端口无 listener。
2. `./vnext/scripts/build-repository-service-image.sh` 于 `16:30:19Z` 开始，exit 0，于 `16:30:25Z` 完成。
3. `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` 于 `16:32:07Z` 开始，结束于 `16:58:08Z`；起止 HEAD 均为 V，起止 status 均 clean，runner 自身 exit code 0。运行期间未修改 worktree、提交或清理 Docker。
4. provenance project：`ordered-bisect-b-3454106-baseline`。V 的 image revision/source-tree：

   | 镜像 | provenance image ID | 标签/身份 |
   | --- | --- | --- |
   | backend | `sha256:887130ce8961661cb4721600a5bf298534efb85a13c7df22eac30257414cb812` | Compose project `ordered-bisect-b-3454106-baseline` |
   | worker | `sha256:5170755501378bb30f4168855a3bf5d9046ff24f8d48b823e6c5c7e998c69264` | Compose project `ordered-bisect-b-3454106-baseline` |
   | repository-service | `sha256:7f4fdcc30177c56e76c3cbe07a25a003a84df24c0d0aeb78753b4c6736dd821a` | `org.opencontainers.image.revision=741d227991f8b76235a36649830f34b3920df6f0`; build-input revision `29f7dfd3c349f9943590765c2b90ca49e47f8eb3`; source-tree `sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f`; lock label `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |

   `python3 vnext/repository_service/tests/support/build_context_digest.py identity` at V returned candidate SHA `741d227991f8b76235a36649830f34b3920df6f0`, build-input revision `29f7dfd3c349f9943590765c2b90ca49e47f8eb3`, source-tree `sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f`.

V→H carried 核验按 `testing-conventions.md` 在同一 worktree 完成，记录于 `/home/dev/gdds-p5-closure-s1-gate-logs/s2a-v2-carried-final-H.log`：H 上 `build_context_digest.py identity` 的 build-input revision `29f7dfd3c349f9943590765c2b90ca49e47f8eb3` 与 source-tree `sha256:2c92331c021958fc4ea425973e59695195f88397e1a39e42572cb3e874f5ff5f` 均匹配 V 的 RS labels；candidate SHA 随 handoff commit 变化，按规则不比较 `org.opencontainers.image.revision`。使用 provenance project `ordered-bisect-b-3454106-baseline` 执行相同的 `docker compose -f vnext/deploy/compose.yaml build backend worker`，exit 0；重建后的 backend `sha256:887130ce8961661cb4721600a5bf298534efb85a13c7df22eac30257414cb812` 与 worker `sha256:5170755501378bb30f4168855a3bf5d9046ff24f8d48b823e6c5c7e998c69264` 均与 V provenance 相同。两项条件通过，V→H 容器门禁判定为 **carried**。RS label 与三镜像完整信息见 `s2a-v2-provenance-and-images.log`；backend/worker 重建过程见 carried log。

## 10. 停止条件、剩余边界与审核重点

- 设计 §14 停止条件均未触发：DC15 类型经 Dolt 同一性验证（包括 FLOAT）；legacy oracle 与 BROWSE_ONLY/SNAPSHOT_ONLY 事实形态无冲突；未要求 Preview 暂停交互、非运行期规则、旧部署兼容、预置初始数据或 Review 阶段独立交互；未发现需要重开的协议族/软件版本。
- S2a 明确不改 Preview 上传侧规范投影（R1），在 S2b 实施；本阶段不对外发布。
- 请审核方重点核对：全部 S2a §2 owner 与 §3 路径预算；legacy oracle/DC16；History/Preview 运行期 ruleset digest 冻结和两个 mismatch failure code；真实 Dolt DC15 往返（含 FLOAT）；checkpoint 载荷变化；R1 中间状态；G8b-F1/F3、G3-F2/F3 四项携带；golden/digest 更新理由；V 门禁日志、镜像 provenance 与 V→H carried 判定。

## 审核提示词

```text
任务：独立审核 P5 架构收口 S2a。你没有参与 S2a 实现；按
docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：p5-s2a @ <H>（门禁提交 V = 741d227991f8b76235a36649830f34b3920df6f0，实现 HEAD 同 V），区间
p5-g8b-exit (3c3d71fed13b152e2f023e5bf22b0050c029d681)..<H>。区间中的审核方文档提交
e04a6eb041（合并 G8b）、57fb9b4dc8（G8b exit/handoff）、1c7398572f（独立 worktree 形式/G8b-F2 决议）按提交区分。
在只读 detached worktree 中工作：git worktree add --detach /home/dev/gdds-review-s2a <H>；随后建立
ln -s /home/dev/gateway-data-management-system/legacy /home/dev/gdds-review-s2a/legacy。
不在实现 worktree 或主工作区运行测试或写入。

权威依据：执行计划 §2 S2a、§3 S2a、§8；设计 §4.1–§4.5、§4.7、§6（W3）、§9 job 模块复制行的 S2a 部分、§12、§14；
ADR 0018–0021；Canonical Storage §2、§7；Ruleset Activation §1、§5；AGENTS.md；本 handoff。

必须核查：S2a §2 列出的全部 owner 与实际命令/结果；§3 必改和条件路径及预算偏差；BROWSE_ONLY/SNAPSHOT_ONLY legacy oracle 与 DC16；
Preview/History 受理时 ruleset digest 冻结、每步检查和 PREVIEW_RULESET_VERSION_MISMATCH / HISTORY_RULESET_VERSION_MISMATCH；
DC15 类型扩充的真实 Dolt 往返（含 FLOAT）；CanonicalizationManifest 3.1.0 读写版本规则；checkpoint 载荷变化；Preview R1 中间状态；
G8b-F1、G8b-F3、G3-F2、G3-F3 四项携带；golden/digest 更新理由；V 的完整门禁日志和三镜像 provenance；V→H carried 的重算与重建证据。

验证：审核 worktree 中运行五包 ruff/mypy 与 import_rules；核对 V 日志中的起止 HEAD、clean status、runner exit code；
按 AGENTS.md/testing-conventions.md 独立复核 carried。不要以旧镜像或其他 worktree 结果替代。

交付：按执行计划 §8.8 写 plans/p5-arch-closure-s2a-independent-review.md，作为独立纯文档提交；审核 worktree 提交后
快进到 p5-s2a，由审核方在报告提交上打 p5-s2a-exit，再以 --no-ff 并入 main；不推送。
审核结论：通过 / 定向修订 / 整体返工。
```
