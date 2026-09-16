# P5-5B-S3 Remediation Independent Review

日期：2026-09-16

结论：**reopen — 原 findings 部分关闭，S3 尚不能进入 S4**。

评审对象：`33c14a92`（完整 SHA 见 verification record），相对 `8618b21a` 的整改。
评审开始时工作区干净。Reviewer 仅新增本文，未改 production、tests 或 dependencies。

## Findings

### S3-F6 / P1 — 真实 artifact 入口复用已关闭的 single-consumer reader

- Authority：[Submit design §7](p5-5b-submit-finalize-design.md) 的 Preview-bound
  SnapshotTableArtifact consumer；snapshot reader 的 single-consumer/non-rewind 合同。
- Exact paths：`repository_import_artifact.py:102–112`、
  `capabilities/storage_projection/import_replay.py:74–79`、`project.py:717–740`。
- Cause：`project_storage(projection_request)` 在 finally 关闭全部输入 reader；后续
  `build_import_mutation_snapshots` 将同一 request/item 交给
  `materialize_canonical_source_rows`。它调用 `_bound_descriptor` 和 `_iter_source_rows`，
  没有 reopen。真实 `ParquetBytesReader.descriptor/iter_rows` 会拒绝已关闭 reader。
- 独立复现：用既有 `tests.support.snapshot_materialization.materialize_sql` 和
  `publish_snapshot_table_artifact` 构造 `unknown_widget(id INT PRIMARY KEY)` 的一行合法
  artifact，将 manifest 的完整 ref 放入 `SnapshotTableBinding`，经 application
  `publish_prepare_import_package` 调用 adapter。materialization 为 COMPLETE，publication 为：

```text
SubmitImportPublicationError table reader descriptor failed
  caused by ImportReplayError table reader descriptor failed
  caused by _ProjectionFailed table reader descriptor failed
  caused by TableAccessError reader is closed
```

- Business consequence：通过真实 pinned artifact 的正常 prepare 路径无法发布 package。
  新增 fake-reader tests 不证明此路径：`FakeSnapshotTableReader.close()` 只设置布尔值，
  其 descriptor/iter_rows 不检查 closed，且可反复迭代。
- Required closure：明确 owner API 的 reader 生命周期，reopen 每次消费并正确 close，或在一次
  合法读取中保留 canonical materialization。不要通过放宽真实 reader 合同修复。
- Risk class：submit availability，P1。
- Unique test owner：consumer 入口由 `tests/test_submit_import_builder.py` 拥有；owner API
  生命周期由 `tests/test_storage_projection_import_replay.py` 拥有，不复制完整输入矩阵。
- Remediation paths：`repository_import_artifact.py`、`storage_projection/import_replay.py`、
  `storage_projection/project.py`、上述两份 owner tests、S3 docs。
- Focused retest：两份 owner + `test_snapshot_artifact_roundtrip.py` + projection integrity/core +
  package owner；Backend ruff/mypy。

### S3-F7 / P2 — Owner 重定位引入 capability 反向依赖，两项 architecture gate 回归

- Authority：[Execution plan §S3](p5-5b-submit-finalize-execution-plan.md) 的 public dependency
  和 capability-gap reopen 要求；现有 capability DAG 和 Mutation Planning leaf 门禁。
- Exact paths：`storage_projection/import_replay.py:15–35`、
  `mutation_planning/__init__.py:3–6`。
- 独立实测 `tests/test_architecture.py` 失败：
  - `test_capability_modules_respect_import_dag`：Storage Projection 只允许依赖
    Snapshot Materialization / Table Rules，新模块反向依赖 Mutation Planning；后者原本已依赖
    Storage Projection，所以这形成 owner 级循环。
  - `test_mutation_planning_source_stays_on_capability_leaf`：新 public export 引入
    `_dolt_renderer`，触发现有 forbidden `dolt` token 门禁。
- Business consequence：capability ownership 与原 DAG 不再成立；所报 focused 47 项未包含
  architecture owner，不能关闭本轮无边界扩张的交付要求。重定位 raw conversion 并不自动
  证明新的依赖方向被接受。
- Required closure：owner 层裁定 canonical row materialization、planner orchestration 和
  Repository renderer 的位置；优先保持既有依赖方向。若确需改变 DAG/leaf contract，先在
  owning architecture authority 记录接受的调整，再更新权威测试。不能仅把新反向依赖加入
  allowlist，或通过字符串技巧绕过 token 检查。
- Risk class：architecture contract / release verification，P2，门禁阻塞。
- Unique test owner：既有 `tests/test_architecture.py`。
- Remediation paths：owner decision 前仅 S3 docs；decision 后由 owning authority 指定生产和
  architecture-test scope，不借本 finding 自动授权放宽架构测试。
- Focused retest：architecture owner + builder/replay owner + affected capability owners；五包 static。

### S3-F8 / P1 — Manifest read-back 只检查 raw SHA，semantic checkpoint binding 被删除

- Authority：Submit design §7 / §8.3 的 checkpoint 同时记录 manifest ref/digest 和 package
  ref/raw SHA；§10.1 要求 matching canonicalization manifest digest。
- Exact paths：`application/submission/contracts.py:90–98`、
  `application/submission/import_builder.py:45–66`、`repository_import_artifact.py:131–140`。
- Cause：R9 nominal ref 改造同时删除了 `canonicalization_manifest_digest`。这是 domain-separated
  semantic digest，不能被 `BackendArtifactRef.raw_sha256` 代替。reuse 仅验证 manifest bytes 的
  raw SHA，没有解码 owner manifest，也不核对 package 里声明的 semantic digest。
- 独立复现：同 store 发布两份内容不同的 manifest/package，把第一份 checkpoint 的
  manifest ref 换为第二份真实 manifest ref，保持第一份 package ref；reuse 返回 `replay=True`，
  但 package 与 durable manifest 的 semantic digest 分别为：

```text
package: sha256:829f994be7687d1839f7fb095540773da8e00b2e9ce99df26bcc58f206974f7e
manifest: sha256:3ce8366c011063b9a06dd17d1adb7fb87c9c1499f0f2cd3641dc957cb581e392
```

  正常第一份 durable manifest 的 raw SHA 为
  `sha256:8706d5eba6fe2784b32e50c6b0e9fa9b8dc76345dffb10fd830c1ace1ed9e840`，
  与上述第一份 semantic digest 不同。复现针对 trusted checkpoint 组装/接线错误，
  不引入同 euid 恶意攻击假设。
- Business consequence：不匹配的 package/provenance checkpoint 被当作合法恢复状态；S5 的
  matching result/T3 所需 semantic fact 不再直接存在于约定 checkpoint 中。
- Required closure：保留 semantic digest 与 nominal ref 的独立职责，发布时记录真实
  `publication.manifest_digest`；reuse 通过 owner decoder/read-back 验证语义绑定并拒绝
  不匹配组合，不重建或选择另一 package。application 通过 port 获得验证，保持无 capability
  import。若选择改变 frozen checkpoint schema，需明确 owning design closure。
- Risk class：durable checkpoint consistency / recovery，P1。
- Unique test owner：`tests/test_submit_import_builder.py`；owner manifest decoding 继续由现有
  package/projection tests 拥有，不复制编码矩阵。
- Remediation paths：submission `contracts.py` / `import_builder.py`、`repository_import_artifact.py`、
  `test_submit_import_builder.py`、S3 docs。
- Focused retest：builder owner + package owner + artifact boundary，Backend static。

### S3-F9 / P2 — Repository base identity 被错误要求等于 after snapshot identity

- Authority：[Storage Mutation contract §5](../contracts/storage-mutation-and-change-set.md) 分别
  定义 source identity 和 base repository commit/ref；Submit design §6–§7 区分 frozen Repository
  expected commit 与提交 snapshot。
- Exact path：`repository_import_artifact.py:221–222`；owner `import_replay.py:157–163` 同样以
  source digest 充当 base ref digest。
- 独立复现：保持 source digest 与 projection 一致，仅将 `repository_base_digest` 改为另一
  合法 SHA，publication 报 `repository_base_digest does not match projection manifest`。
  tests 将两字段设为同一个 dummy snapshot digest，掩盖了语义差别。
- Business consequence：S5 传入真实、独立的 base identity 时正常提交被拒；如为绕过此 guard
  改传 source digest，则接口声称的 repository base binding 失真。
- Required closure：full snapshot rebuild 不需要该输入时删除字段及错误 equality；需要时使用
  正确 frozen base identity，不从 after-source manifest 证明它。R8 的“删除或验证”建议不授权
  把不同事实强制设为相同。
- Risk class：consumer integration compatibility / identity correctness，P2。
- Unique test owner：`tests/test_submit_import_builder.py`。
- Remediation paths：submission `contracts.py`、`repository_import_artifact.py`、owner reopen 后的
  `storage_projection/import_replay.py`、builder owner、S3 docs。
- Focused retest：builder/replay owner，Backend static。

## 原 findings closure

| 原 finding | 本次结论 |
| --- | --- |
| F1/R1 full rebuild | DDL+DML 已出现；整体 closure 未通过，见 F6/F7 |
| F2/R2 ordered gid | fake-input canonical allocation 正确；真实 artifact 路径未通过，见 F6 |
| F3/R3 lock identity | closed；当前 canonical gate 通过，lock 与 `669f1ca0` 无差异 |
| F4/R4 omitted tables | closed 于 injected-input 路径；不再按全部 inputs 查 manifest |
| F5/R5 SET | injected-input 路径已支持；真实 artifact 路径仍受 F6 阻塞 |
| R6 closure orphan | closed；planner 不再接收 store，不发布额外 closure |
| R7 helper duplication | closed 于 S3；重复 transfer/promote/clear helpers 删除，S5 接线仍明确延期 |
| R8 dead fields | 未关闭；读取字段引入错误 equality，见 F9 |
| R9 manifest nominal ref/read-back | nominal representation 已改；semantic binding 未通过，见 F8 |

## Verification record

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit \
  tests/test_submit_import_builder.py tests/test_storage_projection_import_replay.py \
  tests/test_submit_artifact_protection.py tests/test_repository_import_artifact_package.py \
  tests/test_artifact_boundary.py tests/test_canonical_lock_identity.py \
  tests/test_storage_projection_core.py tests/test_storage_projection_integrity.py \
  tests/test_architecture.py
# 2 failed, 138 passed in 1.84s
```

两项失败均为 architecture tests；用户列出的 focused selection 内全部用例通过。
五包经受控 `run --no-sync ruff check .` / `run --no-sync mypy` 全部通过，Backend 339 source files。
补充复现均为 in-memory artifact/真实 Parquet reader，无 Dolt/process/network effect。

未跑全量权威 runner 或 Docker。已存在确定失败，不用扩大测试替代整改。

```yaml
stage: P5-5B-S3-remediation-independent-review
baseline_commit: 8618b21a
candidate_commit: 33c14a92d68fc5a35a21460c917da3206f5b148a
review_start_worktree: clean
verdict: reopen
findings: [S3-F6, S3-F7, S3-F8, S3-F9]
five_package_static: pass
canonical_lock_identity: pass
architecture: fail
authoritative_runner: not_run
container_rebuild_required: no_for_this_python_only_iteration
container_reason: diff is Python/tests/docs; canonical lock unchanged; no image/deployment/runtime boundary touched
container_gate_for_current_head: deferred
last_verified_image_revision: 2da4d71f3c8090cfac08390cfe5f3fb79fd305f4 (S2 reported evidence, not rerun)
last_verified_source_tree: not_recorded_here
last_verified_repository_image_id: sha256:b44a67a7fe6260293ce80ad5e94ee3ba8d65a6c9d16494255c9585807a837a44 (S2 reported)
container_deferred_to: corrected final candidate before stage-ready claim, per AGENTS; S6/S8 final slice gates remain mandatory
reopen_required:
  - owning capability DAG / canonical rows / renderer composition closure
implementation_authority_unchanged: true
next_step: finding-scoped remediation and owning architecture closure, then independent re-review
```

整改 handoff 的 `remediation_commit: pending` 及旧 handoff 的历史 invariant/checkpoint 描述应在
收口时绑定真实整改 SHA 并标明历史记录；这属于交付记录完善，不另建生产机制或测试。
