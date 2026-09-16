# P5-5B-S3 Independent Review 5

日期：2026-09-16

结论：**changes_required — H1–H5 已关闭，但 S3 仍有两项 identity/public-boundary finding，暂不能进入 S4**。

评审对象：HEAD `33c14a92d68fc5a35a21460c917da3206f5b148a` 加当前工作区 round-2/H5
整改；工作区候选尚未提交。Reviewer 仅新增本文，未修改 production、tests、lockfile 或依赖。

## Findings

### S3-J1 / P2 — `repository_base_digest` 仍是死输入，planner 持久身份错误使用 source digest

- Authority：[Storage Mutation contract §5](../contracts/storage-mutation-and-change-set.md) 将
  `source_identity` 与 `base_repository_commit/ref` 定义为不同事实；Submit design §6–§7 区分
  submitted snapshot 与 frozen Repository base。前轮 R8/H4 要求删除无用字段，或让它绑定正确
  base identity。
- Exact path：`vnext/backend/src/gateway_backend/repository_import_artifact.py` 的
  `_render_import_mutation_dml`。它没有接收 `PrepareImportBuildInput.repository_base_digest`，而是：

```python
repository_base=MutationRepositoryBase(
    base_repository_ref_digest=manifest.source_artifact_digest,
)
```

- 独立复现：令 build input 的 repository base 为 `sha256:cc…cc`，source 为
  `sha256:11…11`，publication 成功；拦截 `plan_storage_mutation` request 后，planner 收到的
  base 为 `sha256:11…11`，等于 source，不是 caller frozen base。新增测试只证明两字段可以不同，
  没有证明正确 base 到达 planner。
- Business consequence：Mutation Planning identity/closure 使用错误的 base repository fact；
  S5 若信任该 builder 输入，无法获得可用于 matching/recovery 的原 base identity。当前 closure
  只在内存中用于生成 DML，所以没有既存 durable orphan，但这不关闭 input contract 漂移。
- Required closure：若 full rebuild DML 不需要 repository base，删除该 build-input 字段并明确
  planner identity 不作为 Submit checkpoint/evidence；若保留字段，则把其 `DigestRef` 传给
  `MutationRepositoryBase`，并由 owner test 捕获 planning input。不要重新要求它等于 source digest。
- Unique test owner：`tests/test_submit_import_builder.py`；可以通过 fake/monkeypatch planner 捕获
  request，不增加 change-set 组合矩阵。
- Allowed remediation paths：`application/submission/contracts.py`、
  `repository_import_artifact.py`、`test_submit_import_builder.py`、S3 docs；若改变 Mutation Planning
  contract，再回 owner authority，不在 consumer 内扩张。
- Focused retest：builder owner + mutation import-replay owner + Backend static。

### S3-J2 / P2 — Consumer 仍依赖 capability 私有模块，违反 S3 public-dependency boundary

- Authority：[Execution plan §S3](p5-5b-submit-finalize-execution-plan.md)：
  `storage_projection/**` 与 `mutation_planning/**` 只能作为 public dependency；capability 有缺口则
  reopen owner，consumer 不复制语义。
- Exact paths：
  - `repository_import_artifact.py:29` 从
    `mutation_planning._dolt_renderer` 导入 renderer/capability；
  - `repository_import_artifact.py:61` 从 `storage_projection._digest` 导入 semantic digest helper；
  - `tests/test_mutation_planning_import_replay.py` 反向导入 consumer 私有函数
    `repository_import_artifact._render_import_mutation_dml`，使 capability owner test 依赖 application
    adapter 的内部实现。
- Evidence：round-2 删除 `mutation_planning.__init__` 的 renderer export 后 architecture gate 变绿，
  但 consumer 改为直接导入 `_dolt_renderer`，绕过了 public surface。Storage manifest decoder 已在
  public owner 路径验证并返回 `manifest_digest`，consumer 无需私有 `_digest` 重算。
- Business consequence：S3 的 adapter 依赖未承诺的内部模块；renderer 重命名/重构可在 public
  contracts 不变时破坏 Submit。测试所有权也被倒置，Mutation Planning owner test 无法脱离
  Backend consumer 私有 orchestration 运行。
- Required closure：在 owning capability 中提供不违反 leaf/DAG contract 的 public composition
  surface，或将 consumer orchestration 改为只消费现有 public results。manifest semantic 校验使用
  public decoder 返回的 validated digest。不要修改 architecture allowlist、用字符串规避 leaf gate，
  或继续从 application private function 证明 capability owner invariant。
- Unique test owners：`tests/test_architecture.py` 证明 DAG/public boundary；
  `tests/test_mutation_planning_import_replay.py` 只证明 Mutation Planning owner 行为；
  `tests/test_submit_import_builder.py` 证明 consumer composition。
- Allowed remediation paths：owner decision 指定的最小 capability public surface、
  `repository_import_artifact.py`、上述 owner tests、S3 docs。若没有可用 public surface，保持
  capability reopen，不在 S3 consumer 复制 renderer/planner 语义。
- Focused retest：architecture + 三个 owner tests + five-package static。

## Prior finding re-verification

| Finding | Result |
| --- | --- |
| H1 real artifact reader lifecycle | closed；真实 `ARTIFACTS_REQUIRED` Parquet → store-driven build 测试通过，二次 reader 明确 reopen/finally close |
| H2 capability DAG cycle | closed；architecture tests pass，Storage Projection 不再反向依赖 Mutation Planning |
| H3 semantic checkpoint binding | closed；semantic digest 恢复，stored manifest 与 package 两侧均核对 |
| H4 invalid base==source equality | partial；错误 equality 已删除，但正确 base 未进入 planner，见 J1 |
| H5 legacy reader-reuse test | closed；第二次 projection 使用 reopened readers，全量 unit 通过 |
| R1–R7 behavior | retained；focused owner battery 通过，未发现 lock/closure/helper 回归 |

## Verification

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit \
  tests/test_architecture.py tests/test_submit_import_builder.py \
  tests/test_mutation_planning_import_replay.py tests/test_storage_projection_import_replay.py \
  tests/test_submit_artifact_protection.py tests/test_repository_import_artifact_package.py \
  tests/test_artifact_boundary.py tests/test_canonical_lock_identity.py \
  tests/test_storage_projection_integrity.py
# 114 passed in 1.96s

./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit
# 1915 passed, 115 deselected, 1 warning in 69.29s
```

五包均通过受控 `ruff check .` 与 `mypy`：Backend 341、Shared Kernel 34、Repository
Contracts 15、Repository Client 26、Repository Service 198 source files。`git diff --check` 通过。
未跑 integration、权威 runner 或 Docker；本轮 diff 是 Python/tests/docs，未触碰 lock/image/deploy
边界，且已有确定的 review findings。

```yaml
stage: P5-5B-S3-independent-review-5
candidate_head: 33c14a92d68fc5a35a21460c917da3206f5b148a
reviewed_scope: HEAD + uncommitted round-2/H5 remediation
verdict: changes_required
findings: [S3-J1, S3-J2]
focused_unit: pass_114
backend_unit: pass_1915
five_package_static: pass
canonical_lock_identity: pass
architecture: pass
authoritative_runner: not_run
container_rebuild_required: no_for_this_iteration
container_gate_for_current_head: not_claimed
implementation_authority_unchanged: true
next_step: finding-scoped identity/public-boundary remediation, then light independent re-review
```
