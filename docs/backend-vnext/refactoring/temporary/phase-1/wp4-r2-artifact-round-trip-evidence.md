# WP4 R2 — Arrow IPC Write/Reopen + Identity Re-verification Evidence

状态：R2 component sign-off evidence

日期：2026-07-23

前置基线：[wp4-r1-artifact-api-evidence.md](wp4-r1-artifact-api-evidence.md)

Gate：`PR-CORRECTNESS`；非 `PR-NATIVE`

---

## 1. 结论与边界

**WP4 R2 Arrow IPC write/reopen and raw/semantic identity sign-off passed; ready to enter WP4 R3.**

本轮交付 capability-owned Arrow IPC stream writer/reader、fail-closed publish/reopen/verify pipeline、
`infrastructure.artifact_store.LocalArtifactStore` 与 Python `unordered_row_hashes_content_digest` /
`unordered_row_hashes_content_digest_from_sorted_row_buffer`（生产 bulk path；含 sort 的 `from_row_buffer` 仅测试）。

外部评审第一轮 8 条、第二轮 5 条 findings，以及最终复核发现的 1 条 Minor
error-sanitization finding 均已修复并重验。未发现未闭合 findings。

未实现 corrupt/truncated IPC 负向套件（WP4 R3）、facade→PyO3→Rust→ArtifactRef 全链路（WP4 R4）、`PR-NATIVE` gate。

## 2. R1 基线

| 项 | 值 |
| --- | --- |
| baseline | `9dcb7d25ddfac991561d175134afbe24d6349b0c` |
| subject | `fix(vnext): close WP4 R1 artifact API review` |
| `git merge-base --is-ancestor 9dcb7d25... HEAD` | exit 0 |

R1 evidence 历史 baseline/提交信息未修改。

## 3. HEAD、branch、worktree 与 patch identity

| 项 | 值 |
| --- | --- |
| implementation HEAD (pre-commit) | `9dcb7d25ddfac991561d175134afbe24d6349b0c` |
| branch | `main` |
| merge-base | baseline 本身 |
| worktree | R2 code/tests/shared-kernel/infrastructure + 本 evidence + 最终审核局部修复 |
| deterministic non-evidence patch SHA-256 | `da9ad61614c3fe9859db4a9358cb638222ae26e1ccd8722cc3c931b498c0e68d` |
| `git diff --check` | exit 0 |

Patch hash 使用 baseline 到 working tree 的 binary diff，排除本 evidence 文件。本文件不填写同一提交自身 SHA。

## 4. Authority 清单与冲突处理

| Authority | 审核结果 |
| --- | --- |
| `contract-taxonomy-and-ownership.md` §4.6 / §4.11 | IPC/verify 在 capability；`LocalArtifactStore` 在 infrastructure adapter |
| `architecture-and-refactoring-plan.md` §10 | `infrastructure/artifact_store/` ownership 已对齐 |
| `canonical-row-hash-compute-boundary.md` §5–§6 | IPC output schema 固定 `row_hash: fixed_size_binary(32) non-null` |
| 同上 §8 | `raw_sha256` vs `raw_content_digest` 分离；round-trip 必验 raw + semantic + table schema digest |
| `shared-canonical-encoding.md` §5 | `unordered_table_frame` + `DigestKind.RAW_CONTENT` |
| `implementation-stages.md` | R2 在 `PR-CORRECTNESS`；`PR-NATIVE` 仅 WP4 R4 |
| `wp3-wp5-checkout-plan.md` §5 | R3/R4 边界保持 defer |
| `wp4-r1-artifact-api-design.md` / evidence | 复用 caller-assigned `logical_ref`、无 manifest self-digest |

冲突处理：未修改 canonical encoding、normative vectors 或 R1 wire schema。未要求不同 chunking 产生相同 IPC raw bytes。

## 5. R2 交付物清单

| 路径 | 动作 |
| --- | --- |
| `vnext/shared_kernel/.../framing.py` | 新增 row-buffer framing/digest helpers（含 sorted-buffer 无重排序 path） |
| `vnext/shared_kernel/.../__init__.py` | 导出 |
| `vnext/shared_kernel/tests/test_unordered_row_hashes_digest.py` | 8 cases |
| `vnext/backend/.../canonical_row_hash_ipc.py` | IPC writer/reader/verify + publish 前 fail-closed + strict type authority |
| `vnext/backend/.../infrastructure/artifact_store/local_store.py` | `LocalArtifactStore` + `.manifest.jcs` sidecar + path containment 前置 |
| `vnext/backend/tests/test_canonical_row_hash_ipc.py` | 12 cases |
| `vnext/backend/tests/test_canonical_row_hash_artifact_roundtrip.py` | 11 collected cases |
| `vnext/backend/tests/test_local_artifact_store.py` | 11 cases |
| `vnext/backend/tests/test_architecture.py` | infrastructure ownership + bulk-path 边界（含 sorted-buffer 约束） |
| 本 evidence | 定稿 |

Rust workspace：无变更。

## 6. IPC writer/reader API 与 ownership

Capability module `gateway_backend.canonical_row_hash_ipc`：

| API | 职责 |
| --- | --- |
| `write_row_hash_ipc_stream` | `RecordBatchReader` → Arrow IPC stream bytes（strict schema + no null slots） |
| `open_row_hash_ipc_stream` | bytes → `RecordBatchReader` |
| `collect_row_hashes_from_ipc` | 测试辅助；生产 verify 走 row buffer |
| `verify_row_hashes_sorted_unsigned` | unsigned lexicographic sort 校验（测试） |
| `recompute_raw_content_digest` | list path（测试/兼容） |
| `table_schema_digest_from_declared_fields` | declared schema authority 重算 |
| `content_manifest_from_compute_result` | strict JCS + closed-field 解析 |
| `persist_canonical_row_hash_stream` | finalize → verify → generic `put_with_built_manifest` |
| `reopen_and_verify_canonical_row_hash_artifact` | fail-closed reopen pipeline |

Generic `artifacts/` 不 import `canonical_row_hash_ipc` 或 `canonical_row_hash_artifact`。

## 7. Exact Arrow output schema 检查证据

```python
CANONICAL_ROW_HASH_OUTPUT_SCHEMA = pa.schema([
    pa.field("row_hash", pa.binary(32), nullable=False),
])
```

- `media_type`：`application/vnd.apache.arrow.stream`
- 格式：Arrow IPC **stream**（`pa.ipc.new_stream` / `open_stream`）
- `Schema.equals(..., check_metadata=True)`：拒绝 schema/field metadata
- validity bitmap：拒绝 non-null field 内 null slot
- empty stream：零行但保留 schema

## 8. LocalArtifactStore physical layout 边界

- 位置：`gateway_backend.infrastructure.artifact_store`（**不**从 generic `artifacts` 导出）
- 构造：`artifact_root: Path`（**绝对路径**；`resolve()` 前拒绝 relative；不进 wire）
- 路径映射：`SHA-256(logical_ref)` → `{artifact_root}/{ab}/{cd}/{hex}`
- sidecar（private）：`{hex}.manifest.jcs` 持久化完整 manifest wire（含 content identity）
- collision：比对完整 manifest dict，拒绝 same logical_ref + different exact identity（含 same raw / different semantic）
- fresh instance：`locate` 从 sidecar 恢复 envelope
- 原子写：bytes + manifest sidecar 均 temp + `os.replace`
- path escape：`_validated_paths` 对 target/parent/sidecar 均 `_ensure_within_root` 后再 stat/read/write
- public filesystem/sidecar failures：映射为 sanitized `ManifestVerificationError`，不泄漏 root、临时文件名或 Python exception repr

## 9. write→store→ref→reopen→verify 数据流

```text
RecordBatchReader (compute output)
  → write_row_hash_ipc_stream (finalize bytes)
  → _verify_ipc_bytes_match_content_manifest (publish 前 fail-closed)
  → put_with_built_manifest (generic artifacts)
  → ArtifactRef envelope + .manifest.jcs sidecar
  → store.locate (exact ref + raw integrity + sidecar recovery)
  → _verify_ipc_bytes_match_content_manifest
  → compare envelope content_digest binding
```

`declared_table_schema_fields` 为**必填** authority 输入；`table_schema_digest` 不可跳过。

## 10. raw SHA 计算/复验

- `size_bytes` / `raw_sha256` 在 IPC stream finalize 之后对最终 bytes 计算
- `store.locate` 复验 `size_bytes` + `raw_sha256`
- semantic 相同不跳过 raw 校验

## 11. table_schema_digest / raw_content_digest 重算方式

- `raw_content_digest`：`unordered_row_hashes_content_digest_from_sorted_row_buffer`（生产 bulk path；已证明 sorted 后无重排序）
- `table_schema_digest`：`canonicalize_identifier` + JCS + `DigestKind.TABLE_SCHEMA`
- reopen/publish 均从 IPC row buffer 重算，不信任 manifest 重复字段

## 12. logical/raw/semantic 分离证据

| 层 | 字段/来源 | R2 行为 |
| --- | --- | --- |
| logical | caller-assigned `logical_ref` | 不派生自 `raw_sha256` |
| raw | `size_bytes` + `raw_sha256` | IPC finalize bytes |
| semantic | `content_digest` + content manifest fields | `raw_content_digest` / `table_schema_digest` / `row_count` 从 content 重算并绑定 |

`test_different_store_roots_do_not_change_serialized_ref`：不同 `artifact_root` 不改变 serialized `ArtifactRef`。

## 13. location independence + path traversal 防护

- wire `ArtifactRef` / manifest 无 host path、`artifact_root`、`provider`
- `test_storage_path_is_derived_not_logical_ref`
- `test_locate_rejects_symlink_escape_target`

## 14. 正向/负向测试矩阵与真实计数

| 套件 | cases | 覆盖 |
| --- | --- | --- |
| `test_unordered_row_hashes_digest.py` | 8 | oracle、duplicate、permutation、sorted-buffer oracle |
| `test_canonical_row_hash_ipc.py` | 12 | empty/multi-batch/duplicate/metadata/null/publish reject/strict result/type authority |
| `test_canonical_row_hash_artifact_roundtrip.py` | 11 | round-trip、location independence、chunking、forged schema、publish reject |
| `test_local_artifact_store.py` | 11 | collision、fresh locate、same-raw/different-semantic、symlink、relative root、parent escape、sanitized filesystem errors |
| `test_architecture.py` (R2) | 3 | bulk path、infrastructure ownership、no stub |
| `test_artifact_store_port.py` | 6 | port contract |

Targeted artifact/IPC/store/architecture：**48 passed**。

Backend standalone pytest：**127 passed**；gate-equivalent pytest：**147 passed**。

Shared-kernel gate pytest：**139 passed**。

## 15. architecture / Rust 边界

- `test_compute_facade_does_not_reference_artifact_identity`：通过
- `test_artifacts_module_does_not_import_gateway_compute`：通过
- `test_local_artifact_store_lives_in_infrastructure_only`：通过
- `test_compute_python_extension_has_no_artifact_ref_types`：通过
- `test_rust_core_has_no_artifact_or_infrastructure_boundary`：通过
- `test_r2_ipc_module_avoids_bulk_python_materialization`：通过（生产 verify 使用 `from_sorted_row_buffer`，禁止 `from_row_buffer`）
- production extension test-hook exports：`[]`

Rust workspace：本轮无代码变更；architecture check 回归通过。

## 16. dependency/lock/license/advisory

- 无新增 production dependency
- `pyarrow==25.0.0`（locked，已有）
- Rust lockfile：无变更

| Lock file | SHA-256 |
| --- | --- |
| `vnext/backend/uv.lock` | `681a3f4e4b0ff0b4890761736f8dd35e8a84afaebc8cf2310ccf3221adde680c` |
| `vnext/shared_kernel/uv.lock` | `fe79bf4df1231bf308ad19614a0b5690ef1e5489a0b99d8194e8f363e36e4f74` |
| `vnext/rust/Cargo.lock` | `95cffeb249cec9bbdb96f6978bf8b4755819992a3f0f5953af7a7a82b8e3a544` |

## 17. 验证命令、exit code、计数

```bash
bash vnext/scripts/gate.sh correctness          # exit 0
bash vnext/scripts/gate.sh native               # exit 2 (expected)
cd vnext/backend && uv run pytest -q \
  tests/test_canonical_row_hash_ipc.py \
  tests/test_canonical_row_hash_artifact_roundtrip.py \
  tests/test_local_artifact_store.py \
  tests/test_architecture.py \
  tests/test_artifact_store_port.py              # 48 passed
cd vnext/shared_kernel && uv run pytest -q tests/test_unordered_row_hashes_digest.py  # 8 passed
cd vnext/backend && uv run pytest -q \
  ../rust/gateway-compute-python/tests/test_facade.py \
  ../rust/gateway-compute-python/tests/test_production_extension.py \
  tests/                                        # 147 passed
cd vnext/backend && uv run ruff check .         # exit 0
cd vnext/backend && uv run ruff format --check . # exit 0
cd vnext/backend && uv run mypy .               # exit 0
cd vnext/shared_kernel && uv run pytest -q      # 139 passed (gate)
cargo test --workspace --all-targets            # exit 0
```

| Gate | 结果 |
| --- | --- |
| `PR-CORRECTNESS` | pass |
| `PR-NATIVE` | not implemented (exit 2) |

## 18. cleanup/hermeticity

- temp 文件 write failure 时 cleanup
- public filesystem read/write/init failure 使用 sanitized error，不暴露 host path 或 temp filename
- 测试使用 `tmp_path`；未提交生成 IPC bytes 为 fixture
- gate 后 production install 已恢复；source-tree 无 `.so` 污染

## 19. deferred：WP4 R3、R4、WP5

| 项 | 归属 |
| --- | --- |
| corrupt/truncated/mismatch IPC 完整负向套件 | WP4 R3 |
| facade → PyO3 → Rust → ArtifactRef → reopen 全链路 | WP4 R4 |
| `gate.sh native` / `PR-NATIVE` | WP4 R4 |
| WP5 scenario/runner/golden/container | WP5 |

## 20. unresolved findings

### 外部评审 findings — 第一轮（均已修复）

| ID | 等级 | 描述 | 修复 |
| --- | --- | --- | --- |
| EXT-F1 | Blocker | `table_schema_digest` 可跳过 | `declared_table_schema_fields` 必填；`_verify_ipc_bytes_match_content_manifest` 强制复验 |
| EXT-F2 | Major | publish 前未校验 semantic | `persist` 在 `put` 前调用共享 verify |
| EXT-F3 | Major | schema/null 未 fail-closed | `check_metadata=True` + validity bitmap 检查 |
| EXT-F4 | Major | fresh store 无 exact identity | `.manifest.jcs` sidecar 持久化完整 manifest；collision 比对 manifest dict |
| EXT-F5 | Major | 逐 row `bytes` materialization | row buffer + bulk digest helper |
| EXT-F6 | Major | LocalArtifactStore 在 generic artifacts | 迁移至 `infrastructure/artifact_store/` |
| EXT-F7 | Minor | compute result 解析不严格 | strict JCS + closed-field 校验 |
| EXT-F8 | Minor | evidence 不一致 | 本文件按重验结果重写 |

### 外部评审 findings — 第二轮（均已修复）

| ID | 等级 | 描述 | 修复 |
| --- | --- | --- | --- |
| EXT-F5-R2 | Major | sorted-buffer digest 仍重排序 | `encode_sorted_row_hashes_frame` + `unordered_row_hashes_content_digest_from_sorted_row_buffer`（`framing.py:258-296`）；IPC verify（`canonical_row_hash_ipc.py:257-260`）在 sort 证明后调用 |
| EXT-PATH-1 | Major | sidecar 在 containment 前读取 | `_validated_paths`（`local_store.py:127-133`）；`put`/`locate`/`_load_stored_ref` 均先校验 |
| EXT-PATH-2 | Major | relative `artifact_root` 依赖 cwd | `__init__` 在 `resolve()` 前拒绝非绝对路径（`local_store.py:27-30`） |
| EXT-TYPE-1 | Minor | version/nullable type coercion | `type(x) is int/bool/str`（`canonical_row_hash_ipc.py:125-131,160-186`） |
| EXT-EVID-1 | Minor | evidence 计数/哈希不准 | 本文件 §3/§14/§17 按重验结果更新 |

### 最终复核 finding（已修复）

| ID | 等级 | 描述 | 修复 |
| --- | --- | --- | --- |
| EXT-ERR-1 | Minor | Local store 的 filesystem `OSError` 可从 public API 泄漏 absolute root/临时文件名 | `put`/`locate`/root initialization 增加 sanitized error boundary；新增 read/write error 回归 |

### 未闭合

无。

## 21. 最终结论

WP4 R2 在 R1 基线 `9dcb7d25...` 上完成 Arrow IPC stream write/reopen、三层 identity 复验与
infrastructure `LocalArtifactStore`（含 manifest sidecar exact identity）。`PR-CORRECTNESS` gate 通过；`PR-NATIVE` 仍为 exit 2。

**WP4 R2 Arrow IPC write/reopen and raw/semantic identity sign-off passed; ready to enter WP4 R3.**

可以进入 WP4 R3；corrupt/truncated/mismatch IPC 负向套件属于 WP4 R3，facade → PyO3 → Rust → ArtifactRef → reopen 全链路及正式 `gate.sh native` / PR-NATIVE 仍在 WP4 R4。**不是** PR-NATIVE / Phase 1 complete。
