# P5-5B-S3 Independent Review (Third, Independent — post-remediation re-verification)

日期：2026-09-15

结论：**reopen — 整改关闭了首轮两独立评审确认的 R1–R7 代码缺陷，但整改自身引入/遗留 4 项未关闭
问题（其中 2 项 P1）。S3 尚不能进入 S4**。

评审对象：当前 HEAD `33c14a92`（`fix(submit): remediate P5-5B-S3 import builder review findings`，
基线提交 `8618b21a`）。会话开始时工作区为 `669f1ca0` + 未提交 S3 改动，评审执行前该工作已按
8618b21a/33c14a92 落盘；评审时工作区仅剩本文档之外的未跟踪件
`p5-5b-s3-remediation-independent-review.md`（第二轮独立评审，非代码）。

输入关系：本评审不复制前两轮结论，对整改后树逐条重新独立复现。前两轮编号沿用：
`p5-5b-s3-independent-review.md`（首轮）、`p5-5b-s3-independent-review-2.md`（次轮独立，R1–R9）、
`p5-5b-s3-remediation-handoff.md`（整改交付）、`p5-5b-s3-remediation-independent-review.md`
（整改评审，F6–F9）。本评审新增编号 S3-H1…S3-H4，与整改评审 F6…F9 一一映射。
Reviewer 未修改 production、tests、lockfile 或依赖；全部复现脚本位于 `/tmp`（仓库外）。

## Findings

### S3-H1 / P1（= F6）— 真实 pinned artifact 入口仍无法发布：single-consumer reader 被双重消费

- Authority：[Submit design §7](p5-5b-submit-finalize-design.md) Preview-bound
  SnapshotTableArtifact consumer；`table_access` reader single-consumer/non-rewind 合同
  （`contracts.py:417-471`：close 后任何访问抛 `READER_CLOSED`）。
- Exact paths：`repository_import_artifact.py:79`（`_open_projection_inputs`）、
  `:101`（`project_storage`）、`:109`（`build_import_mutation_snapshots`）；
  `storage_projection/project.py:98-104`（finally 关闭全部输入 reader）；
  `storage_projection/import_replay.py:75,78`（`materialize_canonical_source_rows` 与
  `_bound_descriptor` 再次访问已关闭 reader，无 reopen）。
- 独立复现（本次执行 `/tmp/repro_s3b.py` Part-1）：`materialize_sql` +
  `MaterializationPolicy.ARTIFACTS_REQUIRED` + 自有 `InMemoryArtifactStore` 构造
  `unknown_widget(id INT PRIMARY KEY)` 一行合法 artifact（materialization COMPLETE，真实
  Parquet reader），经 application 入口 `SubmitImportPublicationAdapter.build_and_publish`
  （store-driven）调用。结果：

```text
SubmitImportPublicationError table reader descriptor failed
  caused by ImportReplayError table reader descriptor failed
  caused by _ProjectionFailed table reader descriptor failed
  caused by TableAccessError reader is closed
```

- 测试盲区仍在：`tests/support/storage_projection.py:39-51` 的
  `FakeSnapshotTableReader` 的 `close()` 仅置布尔，`descriptor`/`iter_rows` 不查 closed
  且可重复迭代；`test_submit_import_builder.py` 与
  `test_storage_projection_import_replay.py` 全部走 fake 输入，不覆盖真实 reader 生命周期。
- Business consequence：通过真实 pinned snapshot artifact 的正常 prepare 路径无法发布
  package（submit 可用性断崖）；H2 关闭前 S5 接线必然在此失败。
- Required closure：明确 owner reader 生命周期——每次消费前 `reopen()` 并在消费后 close，
  或单次合法读取同时保留 canonical rows 与投影输出。不得放宽真实 reader 合同。
- Unique test owner：consumer 入口归 `tests/test_submit_import_builder.py`；owner API
  生命周期归 `tests/test_storage_projection_import_replay.py`。
- Risk class：submit availability，P1。

### S3-H2 / P2（= F7）— Storage Projection 新增反向依赖 Mutation Planning，architecture gate 3 项失败

- Authority：[Execution plan §S3](p5-5b-submit-finalize-execution-plan.md) public dependency
  约束与 capability-gap reopen 要求；能力 DAG（Storage Projection 仅允许依赖
  Snapshot Materialization / Table Rules）；Mutation Planning leaf 禁 `dolt` token 门禁。
- Exact paths：`storage_projection/import_replay.py:15-35`（公开导入
  `mutation_planning`，并经 `_digest` 私有模块跨界）vs 既有方向
  `mutation_planning/_planner.py:30`、`mutation_planning/contracts.py:21`
  （已依赖 `storage_projection.contracts`）→ owner 级循环；
  `mutation_planning/__init__.py:8-11` re-export `_dolt_renderer`，触发 leaf 禁 `dolt` token。
- 独立实测（本次执行）：
  - `pytest -m unit tests/test_architecture.py`（隔离运行）：**3 failed**
    - `test_capability_modules_respect_import_dag`：`import_replay.py may not import
      capability mutation_planning; allowed upstream: ['snapshot_materialization',
      'table_rules']`
    - `test_capability_contracts_are_importable`：循环导入，部分初始化模块
      （import-order 依赖：在 9-file battery 与大 suite 中因前序模块先加载而通过，隔离必败——
      该不稳定本身即 owner 级循环的症状）
    - `test_mutation_planning_source_stays_on_capability_leaf`：`__init__.py contains
      forbidden token dolt`
  - 9-file focused battery：`2 failed, 138 passed`（DAG + leaf）。
  - 全量 unit：`2 failed, 1909 passed, 115 deselected`，失败即上述 2 项确定性失败。
- 交付证据缺口：整改 handoff 的 verification record（"47 passed" battery）不含
  `test_architecture.py`，因此该回归未进入交付证据面；`changed_paths` 列入了
  `mutation_planning/__init__.py` 与 `storage_projection/__init__.py` 的改动，但没有任何
  owning architecture authority 记录接受 DAG/leaf contract 调整。
- Business consequence：capability ownership 与 DAG 不成立；S4/S5 构建、容器构建与
  architecture gate 必然阻塞；整改评审据此已判 architecture: fail。
- Required closure：owner 层裁定 canonical row materialization 与 Repository renderer 的
  归属（优先恢复既有依赖方向：raw conversion/renderer 留在 Mutation Planning 或下沉
  shared kernel），如确需改 DAG/leaf 先由 owning architecture authority 记录再改权威测试；
  禁止 allowlist 加白或 token 规避。
- Unique test owner：既有 `tests/test_architecture.py`。
- Risk class：architecture contract / release verification，P2，门禁阻塞。

### S3-H3 / P1（= F8）— Checkpoint semantic binding 仍未恢复：reuse 只验 raw SHA，跨内容组合被接受

- Authority：Submit design §7 / §8.3（checkpoint 同时记录 manifest ref/digest 与 package
  ref/raw SHA）、§10.1（matching canonicalization manifest digest）。
- Exact paths：`application/submission/contracts.py:89-117`
  （`PrepareImportCheckpoint` 仅 `canonicalization_manifest_ref: BackendArtifactRef` +
  `backend_import_artifact_ref` + `package_raw_sha256`，**无 semantic digest 字段**）；
  `application/submission/import_builder.py:36-60`（reuse 仅比较两段 read-back 的 raw SHA）。
- Cause：R9 整改把 manifest 侧从「bare id + semantic digest」换为 nominal
  `BackendArtifactRef`（ref 表示本身正确，`nominal_refs.py` 往返保真），同时删除了
  `canonicalization_manifest_digest`；`raw_sha256` 是 bedding-layer 字节 SHA，与 owner
  canonical re-encode 的 semantic digest 是不同语义域（同一份 manifest 二者即不同，见复现
  输出 raw `8706...` vs semantic `829f...`），不能被前者代替。
- 独立复现（本次执行 `/tmp/repro_s3b.py` Part-2，同 store 两行/三行 net_cfg 分别发布 A/B，
  `dataclasses.replace` 将 A checkpoint 的 `canonicalization_manifest_ref` 换为 B 的真实 ref，
  保留 A 的 package ref/raw SHA 与相同 `input_closure_digest`）：

```text
manifest A semantic digest: sha256:829f994be7687d1839f7fb095540773da8e00b2e9ce99df26bcc58f206974f7e
manifest B semantic digest: sha256:de16aed9c0286296bc53e3e01ef47886544a19958c3092800569b23a09a3f364
raw SHA A: sha256:8706d5eba6fe2784b32e50c6b0e9fa9b8dc76345dffb10fd830c1ace1ed9e840
raw SHA B: sha256:9878d54c5647645495857016f6db08e19a4e6a2512259b4b0c8505f332633887
UNEXPECTED-ACCEPT: reuse returned replay=True
```

  两份 durable manifest 内容不同、raw SHA 不同、semantic digest 不同，reuse 仍判定可复用。
- Business consequence：package↔manifest 错配的 checkpoint 被当作合法恢复状态进入 T3
  matching；S5 匹配所需的 semantic fact 不存在于约定 checkpoint 中。属
  durable checkpoint consistency 缺陷（trusted 接线/组装错配，不引入同 euid 恶意假设）。
- Required closure：发布时把真实 `canonicalized manifest semantic digest` 记录进 checkpoint
  （frozen schema 变更需 owning design closure），reuse 通过 owner decoder 解码 read-back
  manifest 并验证 semantic 绑定（含 package 内声明绑定）；application 经 port 获取验证，
  保持无 capability import。
- Unique test owner：`tests/test_submit_import_builder.py`（owner 解码矩阵不复制）。
- Risk class：durable checkpoint consistency / recovery，P1。

### S3-H4 / P2（= F9）— `repository_base_digest` 被错误要求等于 after-snapshot source identity

- Authority：[Storage Mutation contract §5](../contracts/storage-mutation-and-change-set.md)
  区分 source identity 与 base repository commit/ref；Submit design §6–§7 区分 frozen
  Repository expected commit 与提交 snapshot。
- Exact path：`repository_import_artifact.py:210-222` `_assert_projection_identity`（对
  `build_input.source_artifact_digest` 与 `repository_base_digest` 均与
  `projection.manifest.source_artifact_digest`（after-snapshot 值）断言相等）；
  owner `storage_projection/import_replay.py:138-141` 同形（以 source digest 充当 base
  ref digest）。
- 独立复现（本次执行 `/tmp/repro_s3b.py` Part-3）：source digest 与 projection 一致，
  仅将 `repository_base_digest` 改为另一合法 SHA：

```text
SubmitImportPublicationError: repository_base_digest does not match projection manifest
```

- 测试盲区：`test_submit_import_builder.py` 的 helper 将两字段设为同一 dummy digest，
  掩盖差别。
- Business consequence：S5 传入真实独立的 base identity 时正常提交被拒；若在 S5 侧改传
  source digest 绕过，则接口声称的 repository base binding 失真——两种处理都错的结构性缺陷。
- Required closure：full snapshot rebuild 不需要该输入则删除字段与 equality；需要则由
  caller 提供正确 frozen base identity 并做真实绑定校验，不从 after-source manifest 证明它。
- Unique test owner：`tests/test_submit_import_builder.py`。
- Risk class：consumer integration compatibility / identity correctness，P2。

## 原 findings 独立复验（本评审自行重跑，非照抄整改评审）

| 原 finding | 本评审结论 | 独立复现/证据 |
| --- | --- | --- |
| R1/F1 full rebuild 只 INSERT | **closed** | 复现 `replay.sql` = `DROP TABLE IF EXISTS` + `CREATE TABLE` + `INSERT`；`render_repository_import_replay_sql`（`import_replay.py:96-111`）先 schema DDL 后 planner DML，consumer 不再伪造 empty before manifest |
| R2/F2 ordered gid 未规范化 | **closed（injected 路径）**；真实路径仍被 H1 阻塞 | NULL gid 行 replay 为 `gid=4000000000`（`GID_PSEUDO_MIN`），NOT NULL PK 无 NULL 值，行序保持 |
| R3/F3 uv.lock 漂移 | **closed** | `git diff HEAD -- vnext/backend/uv.lock` 无差异；`test_canonical_lock_identity.py` 5/5 通过 |
| R4/F4 skipped 表 KeyError | **closed** | 输入含 `device_model_table`（migrated ruleset SKIP）+ `net_cfg`，发布成功，package 仅含 `net_cfg`，无未捕获异常（`import_replay.py:66-73` 仅迭代 manifest 表） |
| R5/F5 SET cell 被拒 | **closed（injected 路径）** | SET 列 replay 为 `SET('x','y')` NOT NULL 列 + 逗号文本值，发布成功 |
| R6 closure 孤儿 artifact | **closed** | 单次 publish 后 store 恰 2 条目（`r4-manifest-*`、`r4-package-*`），无 `change-set-closure-*`；`plan_storage_mutation` 不再随 store 发布 closure |
| R7 保护 helper 三重重复 | **closed** | `promote_finalize_artifact_protection` / `transfer_preview_protection_to_attempt` / `clear_attempt_artifact_protection` 在 src 全仓 0 匹配；`import_builder.py` 仅余 `pin_prepare_import_artifacts`；S5 接线延期已在 handoff Notes 声明 |
| R8 死字段 | 未关闭，形态为 H4 | 字段被读取但引入错误 equality |
| R9 checkpoint 不对称 / nominal ref | 未关闭，形态为 H3 | nominal ref 表示已正确（`nominal_refs.py` 严格类型 + 往返保真，边界测试通过）；semantic binding 缺失 |

## 已复核且不构成 finding 的项

- `artifacts/nominal_refs.py` 名义转换与 `assert_*` 互斥矩阵维持前两轮结论（本次 diff 未触及）。
- 全量 unit 仅 architecture 2 项失败（见 H2），其余 1909 项通过；9-file focused battery
  （builder、replay、artifact protection、package、boundary、canonical lock、projection
  core/integrity、architecture）138 项通过、2 项失败（均为 architecture，归 H2）。
- 五包静态本次实测全过（backend mypy 339 source files），整改 handoff `five_package_static:
  deferred` 按本记录补齐为 pass。
- 无 Repository wire 调用、无 Dolt/进程/网络副作用于复现路径；无新增 trust domain/helper。
- 无 generic refcount/GC 或 sidecar/tombstone 扩张（比例化保障边界维持）。

## 实测验证记录

```bash
# 聚焦 battery（含 architecture 与 canonical lock）
cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync pytest -q -m unit \
  tests/test_submit_import_builder.py tests/test_storage_projection_import_replay.py \
  tests/test_submit_artifact_protection.py tests/test_repository_import_artifact_package.py \
  tests/test_artifact_boundary.py tests/test_canonical_lock_identity.py \
  tests/test_storage_projection_core.py tests/test_storage_projection_integrity.py \
  tests/test_architecture.py
# 2 failed（architecture DAG + leaf token）, 138 passed, 1.85s

# architecture 隔离运行（暴露 import-order 依赖循环）
cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync pytest -q -m unit tests/test_architecture.py
# 3 failed（+ test_capability_contracts_are_importable 循环导入）, 40 passed

# 全量 unit
cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync pytest -q -m unit
# 2 failed（同上 2 项）, 1909 passed, 115 deselected, 71.10s

# 五包静态
cd vnext/<p> && ../scripts/uv-consume.sh -C . run --no-sync ruff check .   # 5/5 pass
cd vnext/<p> && ../scripts/uv-consume.sh -C . run --no-sync mypy           # 5/5 pass（backend 339 files）
```

复现脚本：`/tmp/repro_s3b.py`（仓库外，一次性，非交付物）：Part-1 真实 artifact F6 复现、
Part-2 伪造 checkpoint F8 复现、Part-3 独立 base identity F9 复现、Part-4 R1/R2/R4/R5 SQL
形态与 store 条目计数。全部 in-memory artifact + 真实 Parquet reader，无外部状态。

## Review decision record

```yaml
stage: P5-5B-S3-independent-review-3
candidate_head: 33c14a92
baseline_commit: 8618b21a
reviewed_scope: current HEAD (S3 remediation) + working tree (untracked review docs only)
reviewer_modified_repository: no
verdict: reopen
blocking_findings:
  - S3-H1   # P1 真实 artifact 入口 reader 双重消费
  - S3-H3   # P1 checkpoint semantic binding 缺失
non_blocking_p2:
  - S3-H2   # architecture gate 3 项失败（门禁阻塞）
  - S3-H4   # repository base identity 错误 equality
closed_this_round: [R1, R2(injected), R3, R4, R5(injected), R6, R7]
five_package_static: pass
canonical_lock_identity: pass
architecture: fail
authoritative_runner: not_run
container_rebuild_required: no_for_this_python_only_iteration
container_reason: 本轮评审未改任何生产代码；S3 全部改动为 Python/tests/docs，canonical lock 已恢复，未触碰 image/deployment/runtime boundary
container_gate_for_current_head: not_claimed
last_verified_repository_image_id: sha256:b44a67a7fe6260293ce80ad5e94ee3ba8d65a6c9d16494255c9585807a837a44 (S2 reported, not rerun)
last_verified_source_tree: 33c14a92 (current HEAD, remediation)
container_deferred_to: corrected final candidate before stage-ready claim; S6/S8 final slice gates 仍强制
reopen_required:
  - owning capability：reader 生命周期（H1）与 canonical rows/renderer 归属 + DAG/leaf
    contract 裁定（H2），须先修订 owning authority 再改代码/权威测试
  - owning design：checkpoint semantic binding（H3，frozen schema 变更）与
    repository base identity 语义（H4）
implementation_authority_unchanged: true
delivery_record_gaps:
  - 整改 handoff R8/R9 行描述（"validates repository_base_digest"、"read-back verifies
    manifest bytes"）相对 H4/H3 实际语义乐观，收口时须更正
  - 整改 handoff verification record 未含 test_architecture.py，H2 回归因此漏出交付证据面
next_step: finding-scoped remediation + owning architecture/design closure，然后再次独立评审
```
