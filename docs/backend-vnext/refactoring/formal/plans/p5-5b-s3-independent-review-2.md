# P5-5B-S3 Independent Review (Second, Independent)

日期：2026-09-15

结论：**reopen - S3 未通过，不能进入 S4**。

评审对象：HEAD `669f1ca00845c8ef2e82beb55c0063acf3951017` 加当前工作区 S3 修改，
不是该 HEAD 的已提交内容。Reviewer 未修改 production、tests 或 lockfile；
全部复现脚本位于 `/tmp`（不在仓库内），评审结束后仓库工作区状态与本评审开始时一致。

与首轮独立评审（`p5-5b-s3-independent-review.md`，同日）的关系：本评审不复制其结论，
逐条独立复现后再下结论。首轮 S3-F1…S3-F5 在本评审中编号为 S3-R1…S3-R5，
全部得到独立复现确认（见§交叉验证）；本评审另新增 S3-R6…S3-R9。

## Findings

### S3-R1 / P1 - REBUILD_ALWAYS package 的 replay.sql 只含 INSERT，从任何 base state 都无法产生完整快照

- Authority：[Design §7](p5-5b-submit-finalize-design.md)（`builder_mutation_policy=REBUILD_ALWAYS`
  产生 owner-defined full rebuild；不启用 ADAPTIVE_PATCH）、
  [Execution plan §S3](p5-5b-submit-finalize-execution-plan.md)（消费 public capability 产生
  full rebuild；capability 缺口 reopen owner，不在 consumer 复制语义）。
- Exact path：`vnext/backend/src/gateway_backend/repository_import_artifact.py:274-328`。
  adapter 用 `_empty_manifest()`（`tables=()`、digest `sha256:0f*32`）构造 before-image，
  `before_tables=()`（:305），`MutationProjectionBinding.before/after_storage_projection_digest`
   fabrication 为 `sha256:00*32` / `sha256:01*32`（:282-288）。planner 因此只能看到
  「全部新行」，renderer 只产出 INSERT；无任何 CREATE TABLE、DROP、DELETE。
- 复现（本次独立执行，`SubmitImportPublicationAdapter.build_and_publish_from_inputs` +
  `net_cfg` 两行）：

```sql
INSERT INTO `net_cfg` (`board`, `link_no`) VALUES ('eth0', 1);
INSERT INTO `net_cfg` (`board`, `link_no`) VALUES ('eth1', 2);
```

  statement 集合仅 `{INSERT: 2}`；package manifest 声明 `net_cfg` 完整 schema 与
  `row_count=2`，但 replay 不建表、不清旧行。
- 执行端契约（独立核实）：`repository_service/versioned_import/command.py:145-178` 对
  package 只做结构校验（layout/size/digest），随后原样执行 `replay.sql` 语句序列；
  `verify_candidates`（`verification.py:75-127`）在 replay 之后做 STRUCTURAL/FULL_SCAN
  对 manifest 比对。服务自身全部 test fixture 的 replay.sql 均自带
  `CREATE TABLE ...` + `INSERT ...`（如 `tests/support/import_admission_crash_harness.py:44-48`、
  `import_admin_cli_harness.py:689-692`）——即服务契约要求 replay.sql 是自包含 DDL+DML。
- Business consequence：
  - 新仓库（base 无这些表）：`INSERT INTO net_cfg` 直接失败（表不存在）；
  - 已存在同表的仓库：全部主键 duplicate key 失败，或残留 base 中的陈旧行（无 DELETE）；
  - 即便某 base state 侥幸执行成功，`verify_import_candidate` 的 manifest 比对仍会失败。
  即：该 package 在任何 base state 下都无法成功应用；第一次 submit 必然失败，
  后续重建也永远不可达。REBUILD_ALWAYS 的核心契约（用完整规范状态重建表内容）未交付。
- 修复方向（owner 决策，须在 design/plan 层面裁定，不属 consumer 补丁）：
  向 planner 注入真实的 base 表状态（scope tables 在 checkpoint parent commit 的
  内容，由 S5 事务侧经 port 传入），或显式扩展 package/执行器契约使其按 manifest
  置换表内容。在 capability 层面补齐后重审。

### S3-R2 / P1 - 有序表 gid 绕过规范化分配：raw NULL gid 被 replay 进 NOT NULL 主键，canonical 身份失真

- Authority：storage projection owner 契约（GID_NO_V1 有序表 blank gid → pseudo gid
  规范化，canonicalization manifest 记录分配事实）、Design §7 full rebuild 语义。
- Exact path：`repository_import_artifact.py:331-367,370-420`。after-image 的行不是取自
  `projection.tables` 的规范化输出，而是由 adapter 用 `reader.reopen()` 重新读取的
  **raw source rows** 重建（`_rows_from_source_rows`），key 直接取 raw 列值，
  `_canonical_cell` 只映射 null/int-unsigned/signed/varchar。
- 复现（本次独立执行，`b1_n1_iec104_syx_list`，GID_NO_V1，行 (gid=5,no=1)、(gid=NULL,no=2)）：

```sql
INSERT INTO `b1_n1_iec104_syx_list` (`gid`, `no`, `value`) VALUES (5, 1, 'y');
INSERT INTO `b1_n1_iec104_syx_list` (`gid`, `no`, `value`) VALUES (NULL, 2, 'x');
```

  而 package manifest 声明 `gid INT UNSIGNED NOT NULL`（PK）。owner 投影为 NULL 行
  分配了 pseudo gid（规范 schema），replay 却写回 raw NULL：
  - NULL 写入 NOT NULL 主键被 dolt 严格模式拒绝；
  - 即使可写入，持久化数据与 manifest/canonicalization digest 不一致，T3 reconcile
    必失配；
  - 变体：NULL 行不在 raw key 序尾位时，`mutation_planning/contracts.py:613-614`
    「rows must use canonical key order」先于 replay 抛 ValueError（fail-closed 于另一层）。
- Business consequence：任何含 blank gid 的合法有序表数据要么损坏要么始终被拒，
  且 manifest 与 replay 自相矛盾——canonical identity（规范化 + pseudo gid 全部收益的
  载体）在 durable package 边界被破坏。

### S3-R3 / P1 - `vnext/backend/uv.lock` 被改写为内部镜像 registry；canonical lock 门禁失败；handoff 元数据失实

- Authority：AGENTS.md（pypi 模式同步须保持 lock 的 canonical PyPI identity；依赖变更须显式
  授权；提交前五包静态检查）；`test_canonical_lock_identity.py`（canonical registry 门禁）。
- Exact path：`vnext/backend/uv.lock`（工作区 diff 640 行）：registry 由
  `https://pypi.org/simple` 改写为 `http://192.168.233.184:3141/root/pypi/...`。
- 复现（本次独立执行）：全量 `pytest -m unit` 仅 2 项失败，均为 canonical lock 身份测试
  （`registry must be https://pypi.org/simple, got 'http://192.168.233.184:3141/...'`），
  其余 1904 passed。
- Handoff 失实：`uv_lock_in_diff: no`（Traceability）与 Explicit non-deliverables「No
  … lockfile … changes」均与事实相反；未列入 changed_paths。
- Business consequence：仓库 canonical 门禁被工作区状态破坏；任何按 lock 构建/同步的
  下游（Docker 构建、其他开发机）拿到非 canonical 身份。修复为机械恢复 canonical lock
  （或取得显式依赖变更授权），恢复后需重跑 canonical 门禁；handoff 元数据须更正。

### S3-R4 / P2 - ruleset 标记 SKIPPED/DROP 的表触发 KeyError，合法基线输入被拒

- Authority：table rules owner 契约（SKIP/DROP disposition 的表不进入投影输出）；
  Design §7（builder 面向完整 scope 输入）。
- Exact path：`repository_import_artifact.py:349-354`：`_mutation_snapshots_from_captured`
  对每个 captured snapshot 表无条件查 `manifest_by_name[item.canonical_table]`；
  投影输出不含被 skip 的表 → `KeyError`。
- 复现（本次独立执行）：默认 migrated ruleset 的 `DEFAULT_SKIPPED_TABLE_NAMES` 含
  `device_model_table`（SKIP disposition，registry.py）；把该表放进 snapshot 输入直接
  得到 `KeyError: 'device_model_table'`。即官方自带 ruleset 的一条基线路径即被拒。
- Business consequence：含 skipped 表的合法快照无法提交；错误形态为未捕获 KeyError
  而非 typed SubmitImportPublicationError。

### S3-R5 / P2 - owner 投影判 COMPLETE 后 adapter 拒绝 SET 单元格，replay 转换窄于输入面

- Authority：storage projection owner 契约（SET 列支持投影并判 COMPLETE）。
- Exact path：`repository_import_artifact.py:411-420`：`_canonical_cell` 仅在
  NullScalar / 整型 / StringScalar 之外 raise。
- 复现（本次独立执行）：`net_cfg` 增加 SET 列（`set_cell({'a','b'})`）→ 投影
  COMPLETE，随后 `SubmitImportPublicationError: unsupported snapshot cell for mutation replay`。
- Business consequence：任何含 SET 类型业务列的规范表无法走 REBUILD 路径；
  owner 判 COMPLETE、consumer 拒收的层级错配，属 consumer 转换覆盖不足（与 R1/R2
  同一根因簇：after-image 从 raw 行自定义转换而非消费 owner 规范化输出）。

### S3-R6 / P2（本轮新增）- 每次正常 publish 额外写入一个 persistent、无引用、含伪造 binding 的 change-set-closure artifact

- Authority：Design §7 交付面为「canonicalization manifest + import package 两个 pinned
  artifacts」；orphan 边界设计（class-C 无引用字节仅限 crash 残留）；handoff invariant
  「manifest-first then package-second publication order」。
- Exact path：`repository_import_artifact.py:309` `plan_storage_mutation(request,
  artifact_store=store)` → `mutation_planning/_planner.py` 在 request 携带 store 时调用
  `publish_change_set_closure`（`_artifacts.py:24-48`，内容寻址
  `change-set-closure-<digest16>`）；adapter 丢弃 `result.published_closure`，
  closure ref 不进入 `PrepareImportCheckpoint`、不进入 protection、不进入 T3 matching。
- 复现（本次独立执行）：单次 `build_and_publish_from_inputs` 后 store 恰有 3 个 artifact：
  `change-set-closure-f80888b89a8a8b41`、`r4-manifest-…`、`r4-package-…`；closure 先于
  manifest 写入，且无任何 checkpoint/保护引用它。其 durable 字节中
  `ChangeSetManifest.storage_projection_digest` 即 R1 引用的伪造 binding
  （`before=sha256:00*32`、`after=sha256:01*32`，`_changeset.py:48-60` 直接落盘）。
- Business consequence：happy-path 系统性孤儿（非 crash 残留）；持久化字节声称
  不存在的投影 state；实际发布顺序为 closure→manifest→package，与声明的发布顺序
  invariant 相悖；日后 external change-set 消费者若从同 store 读取到该 artifact，
  其 binding 与真实投影必失配。

### S3-R7 / P2（本轮新增）- 保护事务 helper 与 S2 已提交 owner 逻辑三重重复，handoff 证据行归属错误

- Authority：Proportional Assurance policy（每个不变量只有一个权威 owner/测试 owner）；
  clean-cutover 惯例（迁移调用方、删除被取代实现）。
- Exact path：
  - `import_builder.py:89-130` `promote_finalize_artifact_protection` 与
    `finalize_transaction.py:185-224` `_transfer_finalize_protection` **逐字节等价**
    （含伪造的 source refs：`application/octet-stream` / `size_bytes=0` / 全零 raw_sha ——
    S2 既有实现即此形态，S3 照抄延续）；
  - `import_builder.py:53-87` `transfer_preview_protection_to_attempt`（含私有
    `_assert_preview_protection_matches` :193-…）与 `accept_transaction.py:208-212,316-330,338-356`
    的已提交内联 pin+clear+断言重复；
  - `import_builder.py:131-141` `clear_attempt_artifact_protection` 与
    `abort_transaction.py:128-131` 已提交清理重复。
  全部 helper 在生产代码中零调用方（grep 全仓：调用方仅 `test_submit_artifact_protection.py`）。
- Handoff 证据归属错误：证据矩阵「Pin transfer / release」行的
  `test_accept_transaction_transfers_preview_pins_to_attempt` 标注为
  「T1 accept harness: preview pins move to attempt」，但该测试调用的是
  `accept_submit_transaction`（S2 已提交、本次 diff 未改动），从未执行 S3 代码；
  invariant「pin transfer preview→attempt and terminal promote/clear helpers」
  的真实 S3 交付物（其自身 helper）只有孤立直测（`test_transfer_preview_protection_to_attempt_moves_exact_refs`）
  作为证据。
- Business consequence：同一 invariant 存在两个实现 + 两套测试 owner；S5 若「wiring
  S3 helpers」，必须指明删除 S2 哪份复制，否则长期双份漂移风险；伪造 metadata
  的 promote 形态被再次固化。属交付结构与证据完整性缺陷，不直接改变运行时行为。

### S3-R8 / P3（本轮新增）- `PrepareImportBuildInput.source_artifact_digest` / `repository_base_digest` 为死字段

- Exact path：`contracts.py` 新增协议字段；`repository_import_artifact.py:289-297`
  规划输入取 `projection.manifest.source_artifact_digest`（两处复用）与
  projection 派生值，两个 build-input 字段从未读取。调用方可传任意值而不被察觉。
- 建议：删除或改为对 projection 派生值做一致性校验（防 S5 接线时误传）。

### S3-R9 / P3（本轮新增）- checkpoint 对 manifest/package 的表示不对称

- Exact path：`contracts.py`：`PrepareImportCheckpoint.canonicalization_manifest_ref: str`
  （bare artifact id）+ digest；package 侧为完整 `BackendArtifactRef`。
  read-back 复用（`reuse_prepare_import_checkpoint`）只对 package 证明完整 ref 往返；
  manifest 仅 id+digest，后续需按固定 namespace 重建 ref，未被测试覆盖。
- 建议：统一为 `BackendArtifactRef`，或在 reuse 路径对 manifest 做 read-back 证明。

## 已复核且不构成 finding 的项

- `artifacts/nominal_refs.py`：名义类型严格（`type(...) is`），`ArtifactRef` ↔
  `BackendArtifactRef` 往返保真，跨类型替换负矩阵覆盖（2 行参数表）；`artifacts` 包边界
  architecture 测试通过。`repository_artifact_ref_from_upload_response` 不校验三 metadata ——
  响应交叉核对属 UploadArtifact（S5）职责，符合 Design 唯一转换边界划分。
- 「manifest-first then package-second + read-back 校验」在 owner 代码
  (`capabilities/storage_projection/publish.py:167-214`) 真实存在且被复用；但注意 R6：
  adapter 实际发布顺序是 closure→manifest→package。
- 「pre-checkpoint orphan bytes 不改变 published identity」「checkpoint reuse fail-closed」
  两条 handoff invariant 有对应测试且本次全量 unit 中通过。
- S3 代码无任何 Repository wire 调用（grep 确认无 repository_client/http 依赖）；
  `import_builder.py` 依赖面限于 ports + artifacts + domain（无 capabilities 导入）。
- 静态检查（本次实测，5 包全过）：backend ruff + mypy（337 files）、shared_kernel、
  repository_contracts、repository_client、repository_service 均 pass。
  handoff 声称的 `five_package_static: deferred` 如按本记录补齐即为 pass。
- `test_artifact_boundary.py` 保留既有 canonical row hash reopen owner（未删改），
  新增名义 ref 用例为追加。

## 交叉验证（vs 首轮独立评审 S3-F1…F5）

| 首轮 finding | 本评审 | 独立复现结果 |
| --- | --- | --- |
| S3-F1 只 INSERT 无 DDL/清行 | S3-R1 | 确认，并补充执行端契约证据（command.py 只执行语句、服务自 fixture 均 DDL+DML、verify 后置比对在任何 base state 下必失败） |
| S3-F2 ordered gid 未规范化 | S3-R2 | 确认（完整复现 SQL：NULL 写入 NOT NULL PK；manifest 与 replay 自相矛盾） |
| S3-F3 uv.lock 漂移 | S3-R3 | 确认（640 行 diff、内部 registry、canonical 门禁 2 项失败、handoff 元数据失实） |
| S3-F4 skipped 表 KeyError | S3-R4 | 确认（官方默认 ruleset 的 `device_model_table` 即触发） |
| S3-F5 SET cell 被拒 | S3-R5 | 确认（投影 COMPLETE 后 consumer 拒收） |
| —（首轮未覆盖） | S3-R6 | closure 孤儿 artifact + 伪造 binding 落盘（新增） |
| —（首轮未覆盖） | S3-R7 | 保护 helper 三重重复 + 证据行归属错误（新增） |
| —（首轮未覆盖） | S3-R8/R9 | 死字段、checkpoint 不对称（新增，P3） |

## 实测验证记录

```bash
# 聚焦（handoff 命令，复核）
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_submit_import_builder.py tests/test_repository_import_artifact_package.py \
  tests/test_submit_artifact_protection.py tests/test_artifact_boundary.py
# 37 passed

# 全量 unit（本评审追加）
cd vnext/backend && uv run pytest -q -m unit
# 2 failed（仅 canonical lock 身份两项，成因 S3-R3）, 1904 passed, 115 deselected

# 静态（5 包，本评审追加，含 handoff 延期的 four non-backend packages）
cd vnext/<p> && ../scripts/uv-consume.sh -C . run ruff check .   # 5/5 pass
cd vnext/<p> && ../scripts/uv-consume.sh -C . run mypy           # 5/5 pass
```

复现脚本：`/tmp/repro_s3.py`（仓库外，一次性，非交付物）。

## Review decision record

```yaml
candidate_head: 669f1ca00845c8ef2e82beb55c0063acf3951017
reviewed_scope: HEAD + working-tree S3 changes (uncommitted)
reviewer_modified_repository: no
verdict: reopen
blocking_findings:
  - S3-R1  # P1 full-rebuild 语义缺失
  - S3-R2  # P1 canonical 身份失真
  - S3-R3  # P1 canonical lock 门禁 + handoff 元数据
non_blocking_p2:
  - S3-R4
  - S3-R5
  - S3-R6
  - S3-R7
non_blocking_p3:
  - S3-R8
  - S3-R9
container_gate_for_current_head: not_applicable  # 纯 Python/tests/docs，未触碰 image 边界；lock 恢复与 S3 修复候选 HEAD 仍按 AGENTS 规则在最终候选时重建验证
reopen_required:
  - owning public capability: 对 REBUILD_ALWAYS 的完整语义（真实 base 状态注入或
    manifest 驱动表置换契约）与 COMPLETE 面全单元格覆盖（SET 等）及 skipped 表语义
  - dependency authority: 恢复 canonical uv.lock（或显式依赖变更授权）
  - delivery structure: 保护 helper 去重（指明 S2 复制的删除归宿）、handoff 证据行重述
next_step: owner capability closure + finding-scoped 修复后独立复审
implementation_authority_unchanged: true
```
