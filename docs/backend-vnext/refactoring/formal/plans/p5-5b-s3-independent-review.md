# P5-5B-S3 Independent Review

日期：2026-09-15

结论：**reopen — S3 未通过，不能进入 S4**。

评审对象：HEAD `669f1ca00845c8ef2e82beb55c0063acf3951017` 加当前工作区 S3 修改，
不是该 HEAD 的已提交内容。Reviewer 未修改 production、tests 或 lockfile。

## Findings

### S3-F1 / P1 — REBUILD_ALWAYS package 实际只包含 INSERT

- Authority：[Submit design §7](p5-5b-submit-finalize-design.md)、
  [Execution plan §S3](p5-5b-submit-finalize-execution-plan.md)：消费 public capability，产生 full rebuild；
  capability 缺口须 reopen owner，不能在 consumer 复制语义。
- Exact path：`vnext/backend/src/gateway_backend/repository_import_artifact.py:281–315`。
- 复现：使用现有 `_build_input()` / `_projection_inputs()` 调用 adapter，解包得到：

```sql
INSERT INTO `net_cfg` (`board`, `link_no`) VALUES ('eth0', 1);
INSERT INTO `net_cfg` (`board`, `link_no`) VALUES ('eth1', 2);
```

`before_tables=()` 和 fabricated empty manifest 使 planner 只产生新行插入；renderer 不产生
建表、替换 schema 或清除旧行的 SQL。Repository Service 从 expected commit 创建 private ref，
随后直接执行 replay（`versioned_import/command.py`），不会依据 package manifest 建表或清空表。

- Business consequence：新表会因缺表失败；现有相同 key 会冲突；已删除的旧行无法消失；schema
  改动无法应用。当前 bytes determinism 测试通过不能证明 full rebuild。
- Risk class：Repository durable consistency / submit availability，P1。
- Required closure：先由 owning capability 确认并提供 public snapshot-rebuild 支持，或者指出可用的
  既有 public 入口；再修订 S3 adapter。不得直接在 consumer 增加第二套 rebuild 语义。
- Unique consumer test owner：`tests/test_submit_import_builder.py`，验证 replay 对应完整目标
  schema/rows，并覆盖新表、已有数据与删除行；capability 内部矩阵仍由原 owner 拥有。
- Remediation paths：owner reopen 前仅 `docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-*.md`；
  owner 收口后 S3 consumer 仅 `repository_import_artifact.py`、`test_submit_import_builder.py` 和 S3 docs。
- Focused retest：builder owner + package owner + affected capability owner，Backend ruff/mypy。

### S3-F2 / P1 — Ordered 表 replay 使用原始 gid，未使用 canonical allocation

- Authority：[Canonical Storage ordered identity](../contracts/canonical-storage-and-repository-boundary.md)、
  Submit design §7 的 owner-defined canonical projection。
- Exact path：`vnext/backend/src/gateway_backend/repository_import_artifact.py:355–390`。
- 复现：`b1_n1_iec104_syx_list`，列 `(gid INT nullable, no INT, value VARCHAR)`，
  输入 `(NULL, 1, 'x')`，projection 成功，但 package replay 为：

```sql
INSERT INTO `b1_n1_iec104_syx_list` (`gid`, `no`, `value`) VALUES (NULL, 1, 'x');
```

Storage Projection 已在 digest/order facts 中将空 gid 分配为 `4000000000`，并将 import schema
设为 `INT UNSIGNED NOT NULL`。adapter 却从 `_capture_projection_inputs` 的原始 rows 重新构造
after image，绕过该 canonical transform。

- Business consequence：package schema 和 replay 自相矛盾，合法空/零 gid 无法正确提交；多个
  blank gid 还可能被误判为重复 key。manifest 所描述的 canonical identity 没有进入持久数据。
- Risk class：canonical identity / durable consistency，P1。
- Required closure：使用 owning capability 提供的 canonical row/image public contract；若目前不能
  获得，先 reopen owner。不能在 adapter 复制 pseudo-gid allocation。当前对 `_digest` 和
  `_dolt_renderer` 的 private imports 也应随 public 支持收口。
- Unique consumer test owner：`tests/test_submit_import_builder.py`；验证合法 ordered 输入生成的
  replay 与 projection 的 gid/order facts 一致，不复制 allocation 的完整组合矩阵。
- Remediation paths：同 S3-F1；任何 capability 修改必须在 owner reopen 中另行授权。
- Focused retest：builder owner + `test_storage_projection_integrity.py` + package owner，Backend static。

### S3-F3 / P1 — Backend lockfile 被 ambient index 改写，交付记录漏报

- Authority：仓库 AGENTS 的受控 uv 消费规则、S2 canonical lock closure、Execution plan §8
  的依赖/lockfile stop/reopen 条件。
- Exact path：`vnext/backend/uv.lock:12` 起；handoff 的 `uv_lock_in_diff: no`、changed paths 和
  container reason 均未反映此差异。
- 复现：`test_canonical_lock_identity.py` 返回 **2 failed, 3 passed**，首个错误为
  `annotated-doc: registry must be https://pypi.org/simple`。当前 registry/artifact URL 指向
  `http://192.168.233.184:3141/root/pypi/`。
- Business consequence：依赖消费身份不再满足 canonical guard；干净环境依赖内网来源，既有
  权威测试入口会失败。锁文件也触发 image/dependency 验证边界，原 handoff 的 no-rebuild
  理由不能用于当前工作区。
- Risk class：dependency reproducibility / delivery gate，P1。
- Required closure：若是未授权消费漂移，撤销该 lockfile 差异，保持原 canonical lock；若确为
  有意依赖变更，则先 reopen dependency authority。修正 handoff 的真实 changed paths、命令和
  验证记录，后续使用 `uv-consume.sh`。
- Unique test owner：既有 `tests/test_canonical_lock_identity.py`；不新增镜像身份测试矩阵。
- Remediation paths：仅 `vnext/backend/uv.lock` 的 canonical 恢复及 S3 docs；有意 lock 更新需另行授权。
- Focused retest：canonical lock owner + S3 focused；必要的 current-candidate container gate 见下文。

### S3-F4 / P2 — 输入含规则跳过的表时，成功 projection 后抛 KeyError

- Authority：Canonical Storage 的 table omit/skip 规则和 Submit design §7 的 public projection 消费。
- Exact path：`vnext/backend/src/gateway_backend/repository_import_artifact.py:349–354`。
- 复现：现有 `net_cfg` 输入加 `device_model_table(id INT PRIMARY KEY)` 一行；projection 正确
  省略该表，adapter 随后抛出 `KeyError: 'device_model_table'`。
- Cause：循环遍历所有 captured inputs，却假设每个表都出现在成功 projection manifest 中。
- Business consequence：包含被明确跳过表的合法 snapshot 集合无法发布 import package。
- Risk class：submit availability，P2。
- Required closure：以成功 projection 选中的表为 consumer 范围，尊重 owner 的 omitted-table 结果。
- Unique test owner：`tests/test_submit_import_builder.py`；一个 selected + omitted 输入行为用例。
- Remediation paths：`repository_import_artifact.py`、`test_submit_import_builder.py`、S3 docs。
- Focused retest：builder owner + package owner，Backend static。

### S3-F5 / P2 — 合法 SET cell 在 projection 成功后被 consumer 拒绝

- Authority：[Canonical Storage ENUM/SET encoding](../contracts/canonical-storage-and-repository-boundary.md)
  和 Submit design §7 的 owner-defined canonical projection。
- Exact path：`vnext/backend/src/gateway_backend/repository_import_artifact.py:407–420`。
- 复现：`net_cfg(board VARCHAR, link_no INT, flags SET('a','b'))`，一行
  `('eth0', 1, SqlSetValue(members=('a',)))`。public `project_storage` 返回 `COMPLETE`，
  adapter 返回 `SubmitImportPublicationError: unsupported snapshot cell for mutation replay`。
- Cause：`_canonical_cell` 只处理 null/integer/string；snapshot 的合法 SET cell 是 `SqlSetValue`。
- Business consequence：带 SET 列的合法数据无法提交；consumer 的自制 conversion 缩窄了 owner
  已接受的数据范围。
- Risk class：supported-input compatibility / submit availability，P2。
- Required closure：与 S3-F2 一并确认 canonical row/image public 支持，保留 owner 的 SET
  规范化语义；若需要扩展 capability，先 reopen owner。
- Unique consumer test owner：`tests/test_submit_import_builder.py`，验证 supported SET 输入可生成
  对应 replay；不复制 owner 的 SET 编码组合矩阵。
- Remediation paths：同 S3-F1/S3-F2。
- Focused retest：builder owner + existing projection/package owners，Backend static。

## Verification

全部使用受控入口，未更新锁文件：

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit \
  tests/test_submit_import_builder.py tests/test_repository_import_artifact_package.py \
  tests/test_submit_artifact_protection.py tests/test_artifact_boundary.py
# 37 passed in 0.76s

./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit \
  tests/test_canonical_lock_identity.py
# 2 failed, 3 passed in 0.20s
```

五包 `ruff check .` 和 `mypy` 均通过（每包使用 `uv-consume.sh run --no-sync`）。
`git diff --check` 通过。未跑全量权威 runner、真实 Dolt/Repository 或 Docker；以上 SQL
问题通过解包复现和现有 Repository execution path 确认，未宣称真实 effect gate 已运行。

现有 builder tests 全部调用 `build_and_publish_from_inputs`，未覆盖 application
`publish_prepare_import_package` → `build_and_publish` → 真实 SnapshotTableArtifact reopen
路径。整改后的 consumer owner 应至少覆盖该入口，而不是继续只以 injected fake reader 证明交付。
handoff 的 orphan 用例和 deterministic-ref 描述也应与实际断言对齐：目前重复 build 分配不同
artifact ID，测试验证的是复用已发布 checkpoint，不能将其描述为两次 build 的 ref 相同。

## Authority and container record

```yaml
stage: P5-5B-S3-independent-review
candidate_head: 669f1ca00845c8ef2e82beb55c0063acf3951017
candidate_is_dirty_worktree: true
s2_entry_authority: pass
review_decision: reopen
findings: [S3-F1, S3-F2, S3-F3, S3-F4, S3-F5]
five_package_static: pass
focused_s3: pass
canonical_lock_identity: fail
authoritative_runner: not_run
container_rebuild_required: yes_for_current_worktree
container_reason: backend uv.lock differs; dependency/image build input boundary touched
container_gate_for_current_head: deferred
last_verified_image_revision: 2da4d71f3c8090cfac08390cfe5f3fb79fd305f4 (reported by S2 review, not rerun)
last_verified_source_tree: not_recorded_here
last_verified_repository_image_id: sha256:b44a67a7fe6260293ce80ad5e94ee3ba8d65a6c9d16494255c9585807a837a44 (S2 record)
deferred_to: remediation final candidate before claiming S3 ready; reassess trigger after canonical lock restoration
reopen_required:
  - owning public capability support for complete snapshot rebuild and canonical row/image conversion
  - dependency authority only if lockfile change is intentional
implementation_authority_unchanged: true
next_step: owner capability closure and finding-scoped remediation, then independent re-review
```

没有发现 generic refcount/GC、新 trust-domain/helper 或 Repository wire 调用扩张。accept/finalize
事务 wiring 留至 S5 的说明不作为本次 finding；本次阻塞来自已交付 builder 的具体行为和 lock 漂移。
