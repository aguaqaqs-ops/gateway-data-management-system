# WP4 R3 — Corrupt / Truncated / Mismatch IPC Negative Suite Evidence

状态：R3 component sign-off evidence（三轮外部审核修复后）

日期：2026-07-23

前置基线：[wp4-r2-artifact-round-trip-evidence.md](wp4-r2-artifact-round-trip-evidence.md)

Gate：`PR-CORRECTNESS`；非 `PR-NATIVE`

---

## 1. 结论与边界

**WP4 R3 corrupt/truncated/mismatch IPC negative suite sign-off passed; ready to enter WP4 R4.**

本轮在三轮外部审核修复后交付：

- 统一 sanitized IPC 读取路径（`_read_validated_ipc_batches` + EOS marker 校验）
- `open_row_hash_ipc_stream` eager validate（无 lazy 未包装 reader）
- 真实 multi-batch fixture（`build_true_multi_batch_ipc`）与精确截断边界
- corrupt / truncated / mismatch 负向套件 **56 cases**（`pytest --collect-only` 实测）
- 闭合全部外部审核 Major + Minor findings

未实现 facade→PyO3→Rust→ArtifactRef 全链路（WP4 R4）、正式 `gate.sh native` / `PR-NATIVE`、
WP5 scenario/runner/golden/container。

## 2. R2 基线

| 项 | 值 |
| --- | --- |
| baseline | `6310ee96e56d7a3942d0c8921dfe03069e2fdf4b` |
| subject | `fix(vnext): close WP4 R2 artifact round-trip review` |
| `git merge-base --is-ancestor 6310ee96... HEAD` | exit 0 |

R1/R2 evidence 历史 baseline/提交信息未修改。

## 3. HEAD、branch、worktree 与 patch identity

| 项 | 值 |
| --- | --- |
| implementation HEAD (pre-commit) | `6310ee96e56d7a3942d0c8921dfe03069e2fdf4b` |
| branch | `main` |
| merge-base | baseline 本身 |
| worktree | R3 code/tests + 本 evidence（未 commit） |
| `git diff --check` | exit 0 |

### 非 evidence 交付物 SHA-256（逐文件）

| 路径 | SHA-256 |
| --- | --- |
| `vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py` | `52fa4d3bff3a63ca28e624597130f5d89f3204e2acf02332adfddffe3c96d9d5` |
| `vnext/backend/tests/ipc_negative_fixtures.py` | `09bb17ecd24fc7e1631cece6a054fb5d730accecd48df2394910d960989195f0` |
| `vnext/backend/tests/test_canonical_row_hash_ipc_negative.py` | `8c081a2196eb38bc5d90ad3f1127a76d2ebc9e4fc596ac882d0c4f4d6c888073` |

### 组合 patch digest（含 untracked 测试文件）

```bash
{
  git diff 6310ee96 -- vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py
  git diff --no-index /dev/null vnext/backend/tests/ipc_negative_fixtures.py 2>/dev/null || true
  git diff --no-index /dev/null vnext/backend/tests/test_canonical_row_hash_ipc_negative.py 2>/dev/null || true
} | sha256sum
```

| 项 | 值 |
| --- | --- |
| deterministic non-evidence combined patch SHA-256 | `cee4f56872c880302ec21dc3ef7592c35986537c01507970a53d7f7cffe58456` |

## 4. Authority 清单与冲突处理

| Authority | 审核结果 |
| --- | --- |
| `contract-taxonomy-and-ownership.md` §4.6 / §4.11 | IPC/verify 仍在 capability；`LocalArtifactStore` 仍在 infrastructure |
| `architecture-and-refactoring-plan.md` §10 | ownership 未变 |
| `canonical-row-hash-compute-boundary.md` §6、§8–§10 | corrupt/truncated 确定性拒绝；raw vs semantic 分离保持 |
| `shared-canonical-encoding.md` §5 | semantic digest 路径未变 |
| `implementation-stages.md` | R3 在 `PR-CORRECTNESS`；`PR-NATIVE` defer WP4 R4 |
| `wp3-wp5-checkout-plan.md` §5 | R3 负向套件；R4 全链路 defer |
| `wp4-r1-artifact-api-design.md` / evidence | 无新 wire schema |
| `wp4-r2-artifact-round-trip-evidence.md` | 正向 round-trip 基线保留 |

冲突处理：未修改 canonical encoding v1、normative vectors、ArtifactRef wire schema 或 R1/R2 历史 evidence。

## 5. R3 交付物清单

| 路径 | 动作 | case 计数 |
| --- | --- | --- |
| `vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py` | EOS marker；`_read_validated_ipc_batches`；eager `open`；统一 collect 路径 | — |
| `vnext/backend/tests/ipc_negative_fixtures.py` | `build_true_multi_batch_ipc`；missing/field-metadata helpers；偏移常量 | — |
| `vnext/backend/tests/test_canonical_row_hash_ipc_negative.py` | corrupt / truncated / mismatch / positive controls | **56 collected** |
| 本 evidence | 三轮修复定稿 | — |

Rust workspace / lockfile：无变更。

## 6. 负向测试矩阵（完整，56 cases）

分项计数：A corrupt **12** + B truncated **14** + C mismatch **22** + E positive **8** = **56**。

### A. Corrupt IPC（12 cases）

| case_id | 测试函数 | 首败层 | 异常类型 | match 子串 |
| --- | --- | --- | --- | --- |
| corrupt-empty | `test_corrupt_ipc_rejected_at_decode[empty]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| corrupt-length-1 | `test_corrupt_ipc_rejected_at_decode[length-1]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| corrupt-random-garbage | `test_corrupt_ipc_rejected_at_decode[random-garbage]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| corrupt-flip-header-magic | `test_corrupt_ipc_rejected_at_decode[flip-header-magic]` | IPC decode | `CanonicalRowHashIpcError` | `invalid arrow ipc stream` |
| corrupt-flip-header-continuation | `test_corrupt_ipc_rejected_at_decode[flip-header-continuation]` | IPC decode | `CanonicalRowHashIpcError` | `invalid arrow ipc stream` |
| corrupt-flip-schema-message | `test_corrupt_ipc_rejected_at_decode[flip-schema-message]` | IPC decode | `CanonicalRowHashIpcError` | `invalid arrow ipc stream` |
| corrupt-flip-batch2-metadata | `test_corrupt_ipc_rejected_at_decode[flip-batch2-metadata]` | IPC decode / batch metadata | `CanonicalRowHashIpcError` | `invalid arrow ipc stream` |
| corrupt-flip-eos | `test_corrupt_ipc_rejected_at_decode[flip-eos]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| corrupt-append-garbage | `test_corrupt_ipc_rejected_at_decode[append-garbage]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| corrupt-concat-second-stream | `test_corrupt_ipc_rejected_at_decode[concat-second-stream]` | IPC decode | `CanonicalRowHashIpcError` | `invalid arrow ipc stream` |
| corrupt-schema-metadata | `test_corrupt_schema_metadata_ipc_rejected` | schema assert | `CanonicalRowHashIpcError` | `schema does not match` |
| corrupt-bit-flip-semantic | `test_bit_flip_decodable_ipc_fails_semantic_digest_not_raw_hash` | verify manifest | `CanonicalRowHashIpcError` | `raw_content_digest mismatch` |

### B. Truncated IPC（14 cases）

截断 fixture：`TRUNCATION_FIXTURE = build_true_multi_batch_ipc()`（2 batches / [1, 2] rows）。

| case_id | 测试函数 | 首败层 | 异常类型 | match 子串 |
| --- | --- | --- | --- | --- |
| trunc-length-0 | `test_truncated_ipc_fail_closed[length-0]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-length-1 | `test_truncated_ipc_fail_closed[length-1]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-header | `test_truncated_ipc_fail_closed[header-truncated]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-schema | `test_truncated_ipc_fail_closed[schema-truncated]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-schema-message | `test_truncated_ipc_fail_closed[schema-message-truncated]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-after-batch1 | `test_truncated_ipc_fail_closed[after-batch1-boundary]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-batch2-metadata | `test_truncated_ipc_fail_closed[batch2-metadata-truncated]` | IPC decode | `CanonicalRowHashIpcError` | `invalid arrow ipc stream` |
| trunc-batch2-body | `test_truncated_ipc_fail_closed[batch2-body-truncated]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-eos-removed-full | `test_truncated_ipc_fail_closed[eos-removed-full]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-eos-half-removed | `test_truncated_ipc_fail_closed[eos-half-removed]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-before-eos-byte | `test_truncated_ipc_fail_closed[before-eos-byte]` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-after-batch1-no-partial | `test_truncated_after_batch1_does_not_return_partial_rows` | EOS marker | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-open-boundary | `test_open_row_hash_ipc_stream_rejects_truncated_at_public_boundary` | EOS marker (eager open) | `CanonicalRowHashIpcError` | `missing end marker` |
| trunc-positive-control | `test_truncated_family_positive_control` | — | — | (pass) |

### C. Mismatch IPC / identity（22 cases）

| case_id | 测试函数 | 首败层 | 异常类型 | match 子串 |
| --- | --- | --- | --- | --- |
| mismatch-unsorted | `test_unsorted_row_hashes_rejected` | sort verify | `CanonicalRowHashIpcError` | `sorted unsigned lexicographic` |
| mismatch-field-name | `test_schema_field_name_mismatch_rejected` | schema assert | `CanonicalRowHashIpcError` | `schema does not match` |
| mismatch-missing-field | `test_schema_missing_field_rejected` | schema assert | `CanonicalRowHashIpcError` | `schema does not match` |
| mismatch-field-metadata | `test_schema_field_metadata_rejected` | schema assert | `CanonicalRowHashIpcError` | `schema does not match` |
| mismatch-physical-type | `test_schema_physical_type_mismatch_rejected` | schema assert | `CanonicalRowHashIpcError` | `schema does not match` |
| mismatch-nullable | `test_schema_nullable_mismatch_rejected` | schema assert | `CanonicalRowHashIpcError` | `schema does not match` |
| mismatch-null-slot | `test_null_slot_rejected` | validity bitmap | `CanonicalRowHashIpcError` | `must not contain null` |
| mismatch-extra-field | `test_extra_field_rejected` | schema assert | `CanonicalRowHashIpcError` | `schema does not match` |
| mismatch-publish-row-count | `test_publish_row_count_mismatch_rejects_before_put` | publish verify | `CanonicalRowHashIpcError` | `row_count mismatch` |
| mismatch-publish-schema-digest | `test_publish_table_schema_digest_mismatch_rejects_before_put` | publish verify | `CanonicalRowHashIpcError` | `table_schema_digest mismatch` |
| mismatch-publish-semantic-digest | `test_publish_raw_content_digest_mismatch_rejects_before_put` | publish verify | `CanonicalRowHashIpcError` | `raw_content_digest mismatch` |
| mismatch-publish-local-store-clean | `test_publish_reject_leaves_local_store_clean` | publish verify | `CanonicalRowHashIpcError` | `row_count mismatch` |
| mismatch-reopen-semantic | `test_reopen_raw_content_digest_mismatch_after_raw_integrity` | reopen verify | `CanonicalRowHashIpcError` | `raw_content_digest mismatch` |
| mismatch-reopen-envelope-digest | `test_reopen_envelope_content_digest_mismatch` | envelope verify | `CanonicalRowHashIpcError` | `envelope content_digest mismatch` |
| mismatch-reopen-media-type | `test_reopen_media_type_mismatch` | envelope verify | `CanonicalRowHashIpcError` | `media_type mismatch` |
| mismatch-reopen-declared-schema | `test_reopen_declared_schema_mismatch` | reopen verify | `CanonicalRowHashIpcError` | `table_schema_digest mismatch` |
| mismatch-reopen-raw-sha256-ref | `test_reopen_raw_sha256_mismatch_at_store_layer` | store locate | `ManifestVerificationError` | `stored artifact identity mismatch` |
| mismatch-reopen-size-bytes | `test_reopen_size_bytes_mismatch_at_capability_layer` | capability verify | `CanonicalRowHashIpcError` | `located size_bytes mismatch` |
| mismatch-local-tamper-disk | `test_local_store_tamper_after_persist_rejects_reopen` | store locate | `ManifestVerificationError` | `stored raw_sha256 mismatch` |
| mismatch-sidecar-identity | `test_local_store_fresh_instance_sidecar_identity_mismatch` | store locate | `ManifestVerificationError` | `stored artifact identity mismatch` |
| mismatch-semantic-isolation | `test_same_raw_bytes_different_semantic_identity_isolated` | reopen verify | `CanonicalRowHashIpcError` | `raw_content_digest mismatch` |
| mismatch-schema-digest-recompute | `test_declared_schema_digest_independent_recompute` | — | — | (pass) |

### E. Positive controls（8 cases）

| case_id | 测试函数 | 首败层 | 异常类型 | match 子串 |
| --- | --- | --- | --- | --- |
| positive-empty | `test_positive_empty_stream_accepted` | — | — | (pass) |
| positive-one-batch | `test_positive_one_batch_accepted` | — | — | (pass) |
| positive-multi-batch | `test_positive_multi_batch_accepted` | — | — | (pass) |
| positive-exact-framing-offsets | `test_true_multi_batch_fixture_offsets_are_exact` | — | — | schema=128；batch1=304；batch2/EOS前=512 |
| positive-duplicates | `test_positive_duplicate_row_hashes_preserved` | — | — | (pass) |
| positive-sorted | `test_positive_sorted_hashes_accepted` | — | — | (pass) |
| positive-chunking-digest | `test_positive_chunking_differs_raw_bytes_same_semantic_digest` | — | — | (pass) |
| positive-compute-fixture | `test_positive_fixture_family_opens_before_mutations` | — | — | (pass) |

## 7. 生产代码加固（二轮）

| 变更 | 理由 |
| --- | --- |
| `_assert_ipc_stream_eos_marker` | 拒绝无 `0x00000000` 尾标记的 stream（修复 MAJ-001 fail-open） |
| `_read_validated_ipc_batches` | 统一 EOS → decode → batch validate → `tell()==len` 路径 |
| `open_row_hash_ipc_stream` eager `from_batches` | 公共边界不 lazy 泄漏 `OSError`/`ArrowInvalid`（MAJ-002） |
| `_collect_row_hash_buffer_from_ipc` 复用 validated 路径 | verify/collect 与 open 共享 sanitized 边界 |
| `collect_row_hashes_from_ipc` docstring | 标明走 production validate 路径（MIN-006） |

## 8. dependency / lock identity

无新依赖；lockfile 无变更。

| Lock file | SHA-256 |
| --- | --- |
| `vnext/backend/uv.lock` | `681a3f4e4b0ff0b4890761736f8dd35e8a84afaebc8cf2310ccf3221adde680c` |
| `vnext/shared_kernel/uv.lock` | `fe79bf4df1231bf308ad19614a0b5690ef1e5489a0b99d8194e8f363e36e4f74` |
| `vnext/rust/Cargo.lock` | `95cffeb249cec9bbdb96f6978bf8b4755819992a3f0f5953af7a7a82b8e3a544` |

## 9. 验证命令、exit code、计数

```bash
git diff --check                                              # exit 0
bash vnext/scripts/gate.sh correctness                        # exit 0
bash vnext/scripts/gate.sh native                             # exit 2 (expected)

cd vnext/backend
# EOS fail-open 探针（修复后应 REJECT）
PYTHONPATH=tests uv run python -c "
from ipc_negative_fixtures import build_true_multi_batch_ipc
from gateway_backend.canonical_row_hash_ipc import collect_row_hashes_from_ipc, CanonicalRowHashIpcError
f = build_true_multi_batch_ipc()
try:
    collect_row_hashes_from_ipc(f.raw_bytes[:-8])
    raise SystemExit('FAIL: eos removal accepted')
except CanonicalRowHashIpcError:
    print('OK: eos removal rejected')
"                                                            # OK: eos removal rejected

uv run --offline --no-sync pytest -q --collect-only \
  tests/test_canonical_row_hash_ipc_negative.py               # 56 collected
uv run --offline --no-sync pytest -q \
  tests/test_canonical_row_hash_ipc_negative.py               # 56 passed
uv run --offline --no-sync pytest -q \
  tests/test_canonical_row_hash_ipc_negative.py \
  tests/test_canonical_row_hash_ipc.py \
  tests/test_canonical_row_hash_artifact_roundtrip.py \
  tests/test_local_artifact_store.py \
  tests/test_artifact_store_port.py \
  tests/test_architecture.py                                  # 104 passed

uv run --offline --no-sync pytest -q                          # 183 passed
uv run --offline --no-sync ruff check .                       # exit 0
uv run --offline --no-sync ruff format --check .              # exit 0
uv run --offline --no-sync mypy .                             # exit 0

cd ../shared_kernel
uv run --offline --no-sync pytest -q                          # 139 passed

cd ../rust
cargo fmt --all --check                                       # exit 0
cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings  # exit 0
cargo test --locked --offline --workspace --all-targets         # exit 0
cargo build --locked --offline --workspace --release          # exit 0
```

| Gate | 结果 |
| --- | --- |
| `PR-CORRECTNESS` | pass（203 backend gate tests incl. extension） |
| `PR-NATIVE` | not implemented (exit 2) |

## 10. cleanup / hermeticity

- 测试使用 `tmp_path`；无 committed IPC binary fixtures
- publish 拒绝经 spy / `LocalArtifactStore` 证明无 artifact 残留
- gate 后 production install 已恢复；source-tree 无 `.so` 污染
- lockfile 无无说明变化

## 11. findings register

### 实现期处置（R3-IMPL-*）

| ID | 描述 | 处置 |
| --- | --- | --- |
| R3-IMPL-1 | PyArrow trailing garbage | `BufferReader.tell()` 检查 |
| R3-IMPL-2 | PyArrow 异常泄漏 | 包装为 `CanonicalRowHashIpcError` |
| R3-IMPL-3 | corrupt flip 中途失败 | 统一走 `reject_ipc_bytes` |
| R3-IMPL-4 | `ValueError` handler 遮蔽 `CanonicalRowHashIpcError` | except 顺序修正 |
| R3-IMPL-5 | EOS 移除仍接受全部 rows | `_assert_ipc_stream_eos_marker` + validated read |
| R3-IMPL-6 | lazy open 泄漏底层异常 | eager `_read_validated_ipc_batches` + `from_batches` |

### 外部审核 findings — 首轮 Major（已修复）

| ID | 等级 | 描述 | 修复 |
| --- | --- | --- | --- |
| R3-MAJ-001 | Major | null slot 未抵达 validity bitmap 层 | `build_validity_bitmap_null_slot_ipc` + `must not contain null` |
| R3-MAJ-002 | Major | 缺少 raw_sha256 ref-forgery 负例 | `test_reopen_raw_sha256_mismatch_at_store_layer` |

### 外部审核 findings — 二轮（全部闭合）

| ID | 等级 | 描述 | 修复 |
| --- | --- | --- | --- |
| R3-EXT-MAJ-001 | Major | 截断 fail-open；假 multi-batch fixture | EOS marker + `build_true_multi_batch_ipc` + 精确截断用例 |
| R3-EXT-MAJ-002 | Major | `open` 边界 lazy 泄漏 | eager validated `open_row_hash_ipc_stream` |
| R3-EXT-MAJ-003 | Major | evidence 不真实 | 本 evidence 重写 + 真实 hash/计数 |
| R3-EXT-MIN-001 | Minor | missing field / field metadata / corrupt match / offset / local store clean | 新增/更新对应测试与 fixture helpers |

### 外部审核 findings — 首轮 Minor（已闭合或并入 EXT-MIN-001）

| ID | 摘要 | 处置 |
| --- | --- | --- |
| R3-MIN-001 | missing field 负例 | `test_schema_missing_field_rejected` |
| R3-MIN-002 | corrupt `match=` | 参数化 `pytest.param(..., match=...)` |
| R3-MIN-003 | lazy open trailing | eager validate（R3-EXT-MAJ-002） |
| R3-MIN-004 | multi-batch 精确截断 | `TRUNCATION_FIXTURE` + `after_batch1_offset` |
| R3-MIN-005 | publish LocalArtifactStore 清洁性 | `test_publish_reject_leaves_local_store_clean` |
| R3-MIN-006 | `collect_row_hashes_from_ipc` docstring | 生产 docstring 更新 |

### 外部审核 findings — 三轮（审核者局部修复，全部闭合）

| ID | 等级 | 原问题 | 审核者修复与回归 |
| --- | --- | --- | --- |
| R3-EXT2-MIN-001 | Minor | `after_schema_offset` / `after_batch1_offset` 把临时单流 EOS 计入，所谓精确边界晚 8 bytes；batch2 body 标签实际为 metadata | `_two_batch_ipc_offsets` 从独立 PyArrow reader 的 `tell()` 记录真实 `128/304/512`；新增 `test_true_multi_batch_fixture_offsets_are_exact`；修正 mutation 标签、schema truncation offset 与 metadata 首败分类 |
| R3-EXT2-MIN-002 | Minor | 逐文件与组合 patch SHA 已过期 | 按最终非 evidence 文件重算逐文件 SHA 与组合 patch SHA `cee4f568...` |

## 12. unresolved findings

（无）

## 13. deferred：WP4 R4、WP5

| 项 | 归属 |
| --- | --- |
| facade → PyO3 → Rust → ArtifactRef → reopen 全链路 | WP4 R4 |
| `gate.sh native` / `PR-NATIVE` | WP4 R4 |
| WP5 scenario/runner/golden/container | WP5 |

## 14. 最终结论

WP4 R3 在 R2 基线 `6310ee96...` 上完成 corrupt/truncated/mismatch IPC 负向套件、
统一 sanitized IPC 读取、三轮审核 Major/Minor 全部闭合。`PR-CORRECTNESS` gate 通过；`PR-NATIVE` 仍为 exit 2。

**WP4 R3 corrupt/truncated/mismatch IPC negative suite sign-off passed; ready to enter WP4 R4.**

可以进入 WP4 R4；facade → PyO3 → Rust → ArtifactRef → reopen 全链路及正式 `gate.sh native` / PR-NATIVE 仍在 WP4 R4。**不是** PR-NATIVE / Phase 1 complete。
