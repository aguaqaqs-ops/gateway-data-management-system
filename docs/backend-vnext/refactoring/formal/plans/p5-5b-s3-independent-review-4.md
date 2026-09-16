# P5-5B-S3 Independent Review (Fourth, Independent — round-2 remediation re-verification)

日期：2026-09-15

结论：**reopen — 第三轮评审的 H1–H4 在本树逐条独立复验全部关闭，但整改自身引入 1 项 P2
未关闭问题（既有 unit 测试回归 + 交付证据缺全量 unit）。unit 门禁红，S3 尚不能进入 S4**。

评审对象：当前 HEAD `33c14a92`（`fix(submit): remediate P5-5B-S3 import builder review findings`）
加工作区未提交的 round-2 整改改动（10 个修改文件 + 3 个新文件；`fix` handoff 声明
`remediation_commit: pending`，评审时未见新提交）。

输入关系：本评审不复制第三轮结论，对整改后树逐条重新独立复现。文档链：
`p5-5b-s3-independent-review.md`（首轮）、`-2.md`（次轮，R1–R9）、`-3.md`（第三轮，S3-H1…H4）、
`p5-5b-s3-remediation-handoff.md`（round-1 整改）、`p5-5b-s3-remediation-independent-review.md`
（整改评审，F6–F9）、`p5-5b-s3-remediation-round2-handoff.md`（本轮输入）。本评审新增编号
S3-H5；P3 观察记为 S3-O1…O3，不构成 reopen。Reviewer 未修改 production、tests、lockfile
或依赖；全部复现脚本位于 `/tmp`（仓库外）。

## Findings

### S3-H5 / P2（新增）— fail-closed fake reader 使既有 integrity 测试回归；handoff 证据缺全量 unit

- Authority：H1 关闭要求本身（round-2 handoff H1 行：`FakeSnapshotTableReader` 在 closed 后对
  `descriptor`/`iter_rows` 抛 `READER_CLOSED`）；`project_storage` reader 消费合同
  （`storage_projection/project.py:98-104`：调用结束后 finally 关闭全部输入 reader，
  consumer 如需再次读取必须 `reopen()`）。
- Exact paths：`tests/support/storage_projection.py:36-44`（closed check）；失败测试
  `tests/test_storage_projection_integrity.py:448-457`（`test_manifest_digest_is_independent_of_table_input_order`：
  一次性构造两个 table input，随后用**同一组 reader 对象**以不同表序调用 `project_storage` 两次，
  第二次调用消费已关闭 reader）。
- 独立实测（本次全量 unit，`pytest -m unit`）：`1 failed, 1914 passed, 115 deselected, 69.02s`，
  唯一失败即本项：

```text
FAILED tests/test_storage_projection_integrity.py::test_manifest_digest_is_independent_of_table_input_order
  AssertionError: assert <ProjectionStatus.FAILED: 'FAILED'> is <ProjectionStatus.COMPLETE: 'COMPLETE'>
  diagnostics: ROW_INTEGRITY/ERROR 'table reader descriptor failed' (unknown_widget)
```

  本评审复现脚本 P4 也独立撞到同一合同（`project_storage` 后以原 request 调
  `build_import_projection_snapshots` → `READER_CLOSED`），而新 owner 测试
  （`test_mutation_planning_import_replay.py:66-75`）与 adapter
  （`repository_import_artifact.py:_reopen_projection_inputs`）均以 `reader.reopen()` 为第二次
  读取供源——只有该 legacy 测试仍依赖旧 fake 的宽松行为。
- 影响面判定：非产品语义回归。生产 consumer 不重用已消费 reader（adapter 每次
  `_open_projection_inputs` 新开、二次消费前 reopen）；受影响的只是测试 fake 的合同收紧后
  的一个未迁移用例。
- Business consequence：unit 门禁红 → 按 S2/S3 既有 gate 规则（全量 unit 绿为收口条件）S3
  不能进 S4；且该回归未进入 round-2 handoff 证据面（见下）。
- 交付记录缺口：round-2 handoff 的 verification record 仅含 9-file battery（`94 passed`）与
  backend ruff/mypy，**未跑全量 unit**。round-3 handoff 恰好以逐面数字补齐过同类风险
  （“全量 unit 仅 architecture 2 项失败…其余 1909 项通过”），round-2 未保持同一证据面，
  回归因此漏出。
- Required closure：仅需测试侧修复——第二次 `project_storage` 调用改用已 reopen/重建的 reader
  （`tests/test_storage_projection_integrity.py:457` 一行量），不得放宽 fake 的 closed 合同
  （那是 H1 的关闭要求）；handoff 补充全量 unit 数字。无 production 代码改动。
- Unique test owner：`tests/test_storage_projection_integrity.py`。
- Risk class：test-infrastructure regression + gate，P2。

### 非阻塞观察（P3，不 reopen，收口时一并处置）

- **S3-O1 — DML 编排的投影绑定仍为自洽但语义空心的 stub。**
  `repository_import_artifact.py:_render_import_mutation_dml` 构造
  `MutationProjectionBinding(before_storage_projection_digest=manifest.manifest_digest,
  after_storage_projection_digest=manifest.manifest_digest, ...)`——同一投影 digest 声称
  `before_tables=()` 与完整 `after_tables` 两个不同内容。closure 纯内存（package 恰 2 条目，
  本次已复验），不落地，故影响限于 DML 渲染输入；真实 identity 绑定属 S5（round-2 handoff
  R7 延期声明）的一部分，收口时与 S5 identity 一并处理。
- **S3-O2 — key 排序规则双份编码。** `storage_projection/import_replay.py:_key_bytes_for_ordering`
  与 `mutation_planning/_digest.py:key_bytes_for_ordering` 各自实现同一条排序规则；mutation 侧
  稳定重排为最终权威，storage 侧排序冗余。后续单一 owner 收敛候选。
- **S3-O3 — application 层跨包私有 import。** leaf token 门禁禁止
  `mutation_planning/__init__.py` 暴露 `_dolt_renderer`（token `dolt`），adapter 遂直接
  `from gateway_backend.capabilities.mutation_planning._dolt_renderer import ...`。架构门禁
  （token + DAG）未显式禁止该形态，但模块私有重命名会静默击穿 application 集成层；S5 规划
  renderer 公共面时一并裁定。

## 原 H1–H4 独立复验（本评审自行重跑，非照抄 round-2 handoff）

| 原 finding | 本评审结论 | 独立复现/证据 |
| --- | --- | --- |
| S3-H1 / P1 reader 双重消费 | **closed** | `/tmp/repro_s3c.py` P1：真实 Parquet artifact（`materialize_sql` + `ARTIFACTS_REQUIRED`）经 store 驱动入口 `build_and_publish` 发布成功，`replay.sql` = `DROP TABLE IF EXISTS` + `CREATE TABLE` + `INSERT`（含 SET 列）；P5：`project_storage` 消费后原 reader `closed=True`，reopened reader 供源出 2 行 INSERT，closed fake 对 `descriptor()` 抛 `READER_CLOSED`；真实路径 reopen 由 `repository_import_artifact.py:140`（`_reopen_projection_inputs`）、`:157-161`（finally close）实现 |
| S3-H2 / P2 能力反向依赖 | **closed** | `mutation_planning/*.py` 全量 grep `dolt` token：0 命中；新 `mutation_planning/import_replay.py` 仅 import `storage_projection.contracts`（允许的上游方向，`test_architecture.py:111`）与本包 `_digest`/`contracts`；`storage_projection/import_replay.py` 无 mutation_planning import；`__init__.py` re-export 与 gate 一致（gate 文件未改动）；全量 unit 中 architecture 全部通过（唯一失败为 H5 非 architecture） |
| S3-H3 / P1 checkpoint 缺 semantic binding | **closed** | checkpoint 恢复 `canonicalization_manifest_digest` 字段（`submission/contracts.py:94`，非空校验）；publish 侧记录语义 digest 且经重算自证（`publish.py:233-241`）；`verify_checkpoint_semantic_binding` 双向校验（stored manifest 语义 digest + package 绑定 digest）。P2 复现三 permutations 全拒：B-manifest/A-checkpoint 与 A-manifest/B-digest → `checkpoint semantic manifest digest does not match stored manifest`；B-manifest/B-digest/A-package → `package manifest digest does not match checkpoint semantic digest`；未篡改 checkpoint 控制组 `replay=True` 不受过度拒绝 |
| S3-H4 / P2 base digest 错误 equality | **closed** | `_assert_projection_identity`（`repository_import_artifact.py:351-361`）仅校验 `source_artifact_digest`；P3：`repository_base_digest="sha256:cc…"` 独立于 source，发布成功并记录语义 digest |

## R1–R7 回归形态再验（DML 拆分后的形状完整性）

| 项 | 结论 | 证据 |
| --- | --- | --- |
| R1 full rebuild 形状 | 保持 | P1/P4：`DROP` + `CREATE` + `INSERT` 顺序完整 |
| R2 ordered NULL gid | 保持 | P4：NULL gid 渲染 `4000000000`（`GID_PSEUDO_MIN`），INSERT 按 key 升序（`(2,2,'y')` 先于 `(4000000000,1,'x')`） |
| R3 uv.lock | 保持 | 本轮 diff 无 uv.lock（`git diff HEAD -- vnext/backend/uv.lock` 空）；canonical lock identity 测试全过 |
| R4 skipped 表 | 保持 | `net_cfg` + `device_model_table`（migrated ruleset SKIP）发布成功：import 仅 `['net_cfg']`，replay.sql 无 device 表 DDL/DML |
| R5 SET/ENUM 列 | 保持 | P4：`SET('x','y')` 列渲染 `VALUES ('x,y', 1)`（按 codec label 序）|
| R6 closure 孤儿 | 保持 | P4：store 恰 2 条目（`r4-manifest-*`、`r4-package-*`），无 `change-set-closure-*` |
| R7 保护 helper 重复 | 保持 | `promote_finalize_artifact_protection` 等 3 helper 在 src 全仓 0 匹配 |

## 已复核且不构成 finding 的项

- `artifacts/nominal_refs.py` 名义转换与 `assert_*` 互斥矩阵：本轮 diff 未触及，维持前轮结论。
- 新边界 DTO `ImportReplayKeyedRow`（`storage_projection/contracts.py:487`/`:499`）：mutation 合同
  既为 dict-cell 形态（`mutation_planning/contracts.py:43` `CanonicalCellValue = dict[str, object]`），
  类型→dict 的 seam 放在持有类型标量的 storage 侧（`_mutation_cell`，SET/ENUM 映射与拒值在此），
  方向与归属正确。
- 测试所有权迁移干净：`test_storage_projection_import_replay.py` 降为 schema-only owner
  （并断言 schema SQL 不含 `INSERT`），DML/完整 replay 不变量移入新
  `test_mutation_planning_import_replay.py`（DROP+CREATE+INSERT、ordered gid、SET 三条不变量
  逐条保真迁移）；每个不变量单一 owner 维持。
- 无 Repository wire 调用、无 Dolt 子进程/网络副作用于复现路径；无新增 trust domain/helper；
  无 generic refcount/GC 或 sidecar/tombstone 扩张（比例化保障边界维持）。
- `PackageError`/`ManifestVerificationError`/`SubmitImportPublicationError` 均为 `ValueError`
  系，port 异常经 `reuse_prepare_import_checkpoint` 统一映射为 `SubmitImportBuilderError`，无泄漏路径。

## 实测验证记录

```bash
# 全量 unit（唯一失败 = S3-H5）
cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync pytest -q -m unit
# 1 failed (test_storage_projection_integrity.py::test_manifest_digest_is_independent_of_table_input_order),
# 1914 passed, 115 deselected, 69.02s

# 五包静态（本评审 5/5 全跑，handoff 仅声明 backend-only，此处补齐）
cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync ruff check .          # pass
cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync mypy                 # 341 files pass
cd vnext/repository_service && ... ruff check . / mypy                               # pass / 198 files
cd vnext/repository_client && ...                                                    # pass / 26 files
cd vnext/repository_contracts && ...                                                 # pass / 15 files
cd vnext/shared_kernel && ...                                                        # pass / 34 files
```

复现脚本：`/tmp/repro_s3c.py`（仓库外，一次性，非交付物）：P1 真实 Parquet 入口 +
P2 checkpoint 三 permutations 伪造 + P3 独立 base digest + P4 DML 形状（ordered gid / SET /
store 条目计数）+ P5 reader 生命周期；另有一次性 skip-table 检查（import 表集合 +
无 device DDL）。全部 in-memory artifact + 真实 Parquet reader，无外部状态。

## Review decision record

```yaml
stage: P5-5B-S3-independent-review-4
candidate_head: 33c14a92
baseline_commit: 8618b21a
reviewed_scope: HEAD 33c14a92 + 工作区未提交 round-2 整改（10 改 + 3 新，含 2 个新 src 文件与 1 个新测试文件）
reviewer_modified_repository: no
verdict: reopen
blocking_findings: none_p1
non_blocking_p2:
  - S3-H5   # 既有 integrity 测试回归（fail-closed fake 后未迁移）+ handoff 证据缺全量 unit
observations_p3: [S3-O1, S3-O2, S3-O3]
closed_this_round: [S3-H1, S3-H2, S3-H3, S3-H4]
regression_shape_reverified: [R1, R2, R3, R4, R5, R6, R7]
five_package_static: pass（ruff 5/5；mypy backend 341 / repository_service 198 / repository_client 26 / repository_contracts 15 / shared_kernel 34）
canonical_lock_identity: pass
architecture: pass（全量 unit 内 architecture 全绿；leaf token 0 命中；DAG 方向已还原）
authoritative_runner: not_run（本轮仅 backend 面改动；其余包未触碰且 canonical 门禁绿）
container_rebuild_required: no_for_this_python_only_iteration
container_reason: 本轮 diff 仅 Python/tests/docs，uv.lock 无差异，未触碰 image/deployment/runtime boundary
container_gate_for_current_head: not_claimed
last_verified_repository_image_id: sha256:b44a67a7fe6260293ce80ad5e94ee3ba8d65a6c9d16494255c9585807a837a44（S2 记录，未重跑）
last_verified_source_tree: 33c14a92 + 未提交 round-2 整改工作区
container_deferred_to: corrected final candidate before stage-ready claim；S6/S8 final slice gates 仍强制
reopen_required:
  - 测试侧单点修复：test_storage_projection_integrity.py 第二次 project_storage 调用改用
    reopen/重建 reader（不放宽 fake closed 合同）
  - handoff 证据面补齐全量 unit 数字（保持 round-3 起的记录标准）
  - S3-O1…O3 不阻塞，随 S5 收口或后续清理处理
implementation_authority_unchanged: true
next_step: H5 单点修复 + 全量 unit 绿 + 证据补齐后，可走轻量再确认（无需全量重开评审）
```
