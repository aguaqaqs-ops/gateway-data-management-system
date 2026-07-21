# WP2 R6 Normative Vector Publication

状态：WP2 R6 evidence（首次 normative vector publication）

日期：2026-07-21

适用：Phase 1 D3 / WP2 R6 — §6.2 首次 normative publication

Authority：`docs/backend-vnext/refactoring/formal/plans/phase-1-implementation-design-and-delivery-plan.md` §6.2

## 1. 发布摘要

| 项 | 值 |
| --- | --- |
| Normative root | `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/` |
| `vector_set_id` | `gateway-vnext.shared-kernel.canonical-encoding.v1` |
| `vector_set_schema_version` | `1` |
| `canonical_encoding_version` | `1` |
| `contract_binding` | `gateway-vnext.shared-canonical-encoding` / `1.0.0` |
| `vector_set_content_digest` | `sha256:a01eae14d8741cb9253fadc5dafa464afb70e5b1f85a51dd34e6df6b92f25afe` |
| 总 case 数 | 125（valid 83 + invalid 42） |
| Candidate marker | **未包含**（normative root 无 `CANDIDATE_PENDING_WP2_CONFIRMATION`） |

### 1.1 文件清单与 closure 元数据

| 文件 | `case_count` | `size_bytes` | `raw_sha256` |
| --- | ---: | ---: | --- |
| `digest.jsonl` | 17 | 5548 | `sha256:0aaa6be58b66cb961f7cf5f76643886b1db4019fd157017951f98541b6a6253d` |
| `invalid.jsonl` | 42 | 10689 | `sha256:6da2c3e52e4ced9767b0661726efce0ce6328b2e70a2de8635314d2a0a7d825a` |
| `jcs.jsonl` | 9 | 1872 | `sha256:4b8ce084d12d09afc829af4cf9f3bfe30e345f993b3a39235033a9278f28baa2` |
| `scalar.jsonl` | 57 | 21068 | `sha256:0f451a3af65ea41e0b72e6218851f9469ac6fc757ed47de57abd254855e29f72` |
| `vector-set.json` | — | 1360 | （manifest；digest 见上表 `vector_set_content_digest`） |

`files[]` manifest 顺序（path UTF-8 升序）：`digest.jsonl` → `invalid.jsonl` → `jcs.jsonl` → `scalar.jsonl`。

### 1.2 §5.4 补齐记录（P1 修复）

相较初稿，catalog 新增 4 个 invalid case（仍属首次 v1 publication）：

| `case_id` | 覆盖 family | `expected_error.code` |
| --- | --- | --- |
| `invalid.scalar.decimal.precision-exceeds` | decimal integer digits 超过 `precision-scale` | `CANONICAL_DECIMAL_INVALID` |
| `invalid.scalar.decimal.scale-exceeds` | decimal fractional digits 超过 `scale` | `CANONICAL_DECIMAL_INVALID` |
| `invalid.scalar.string.invalid-utf8` | scalar string raw logical literal invalid UTF-8 | `CANONICAL_INVALID_UTF8` |
| `invalid.scalar.string.noncharacter` | scalar string raw logical literal noncharacter | `CANONICAL_UNICODE_NONCHARACTER` |

## 2. §6.2 发布步骤执行记录

1. **Out-of-tree candidate 生成**：`uv run python -m gateway_shared_kernel.testing generate /tmp/...`（含 marker）
2. **Read-only validator**：schema、path、ordering、count、size、raw hash、closure digest 全部通过
3. **Python reference**：`validate` 逐 case dispatch 通过（125/125）
4. **Rust independent implementation**：`cargo test -p gateway-shared-kernel --all-targets` 对同一 candidate 通过
5. **人工 review checklist**：见 §5（待 reviewer sign-off）
6. **Reviewed patch**：5 个 normative 文件写入固定 root；**未执行 bless**
7. **消费路径切换**：`gate.sh` pin normative root；Rust conformance 默认读取 repository fixed root

## 3. 双端验证命令

### 3.1 Python validate（normative root）

```bash
cd vnext/shared_kernel
uv run python -m gateway_shared_kernel.testing validate \
  ../fixtures/vectors/shared-kernel/canonical-encoding/v1
```

结果：`vector set ok`（125 cases，closure + dispatch）

### 3.2 Rust conformance（normative root）

```bash
cd vnext/rust
export GATEWAY_SHARED_KERNEL_VECTOR_ROOT=../fixtures/vectors/shared-kernel/canonical-encoding/v1
cargo test --locked -p gateway-shared-kernel --all-targets
```

显式 env 可用于 candidate 人工验证；未设置 env 时 `vector_conformance.rs` 直接解析 repository fixed normative root（`paths::normative_vector_root()`），**不再**调用 Python generator。

结果：109 tests passed（含 `rust_vector_conformance_matches_normative_root`）

### 3.3 Gate correctness

```bash
cd vnext && ./scripts/gate.sh correctness
```

结果：`correctness gate passed`

**Rust 相对路径说明**：`GATEWAY_SHARED_KERNEL_VECTOR_ROOT=../fixtures/vectors/...` 在 `cd vnext/rust` 后导出时，`cargo test` 的 cwd 为 member crate；`vector_root.rs` 在 cwd 解析失败后回退到 Rust workspace root（`vnext/rust`）重试。

## 4. Case 清单（按 bucket）

### `digest.jsonl` (17 cases)

- `digest.collection.keyed.sorted` — valid — `encode-collection`
- `digest.collection.multiset.duplicates` — valid — `encode-collection`
- `digest.collection.sequence.fixed` — valid — `encode-collection`
- `digest.collection.set.unique` — valid — `encode-collection`
- `digest.identifier.ascii-fold` — valid — `canonicalize-identifier`
- `digest.raw-blob.payload` — valid — `raw-blob-digest`
- `digest.row.empty` — valid — `encode-row`
- `digest.row.mixed-fields-permuted-a` — valid — `encode-row`
- `digest.row.mixed-fields-permuted-b` — valid — `encode-row`
- `digest.semantic.domain.collection-item` — valid — `semantic-digest`
- `digest.semantic.domain.raw-content` — valid — `semantic-digest`
- `digest.semantic.domain.row` — valid — `semantic-digest`
- `digest.semantic.domain.scenario-fixture` — valid — `semantic-digest`
- `digest.semantic.domain.scenario-input` — valid — `semantic-digest`
- `digest.semantic.domain.table-schema` — valid — `semantic-digest`
- `digest.semantic.domain.vector-set` — valid — `semantic-digest`
- `digest.semantic.row-empty-frame` — valid — `semantic-digest`

### `invalid.jsonl` (42 cases)

- `invalid.digest.collection.keyed-duplicate` — invalid — `CANONICAL_COLLECTION_DUPLICATE_KEY`
- `invalid.digest.collection.set-duplicate` — invalid — `CANONICAL_COLLECTION_DUPLICATE_ITEM`
- `invalid.digest.identifier.collision` — invalid — `CANONICAL_IDENTIFIER_COLLISION`
- `invalid.digest.identifier.empty` — invalid — `CANONICAL_IDENTIFIER_EMPTY`
- `invalid.frame.boolean-length` — invalid — `CANONICAL_FRAME_LENGTH_INVALID`
- `invalid.frame.empty` — invalid — `CANONICAL_FRAME_TRUNCATED`
- `invalid.frame.tag-reserved` — invalid — `CANONICAL_SCALAR_TAG_RESERVED`
- `invalid.frame.tag-unknown` — invalid — `CANONICAL_SCALAR_TAG_UNKNOWN`
- `invalid.frame.trailing-bytes` — invalid — `CANONICAL_FRAME_LENGTH_INVALID`
- `invalid.frame.truncated-payload` — invalid — `CANONICAL_FRAME_TRUNCATED`
- `invalid.frame.uleb128.non-minimal` — invalid — `CANONICAL_ULEB128_NON_MINIMAL`
- `invalid.frame.uleb128.overflow` — invalid — `CANONICAL_ULEB128_OVERFLOW`
- `invalid.jcs.duplicate-member` — invalid — `CANONICAL_JCS_DUPLICATE_MEMBER`
- `invalid.jcs.infinity` — invalid — `CANONICAL_JCS_NON_FINITE_NUMBER`
- `invalid.jcs.invalid-utf8` — invalid — `CANONICAL_INVALID_UTF8`
- `invalid.jcs.nan` — invalid — `CANONICAL_JCS_NON_FINITE_NUMBER`
- `invalid.jcs.noncharacter` — invalid — `CANONICAL_UNICODE_NONCHARACTER`
- `invalid.jcs.number-out-of-range` — invalid — `CANONICAL_JCS_NUMBER_OUT_OF_RANGE`
- `invalid.jcs.surrogate` — invalid — `CANONICAL_INVALID_UNICODE`
- `invalid.jcs.syntax` — invalid — `CANONICAL_JCS_SYNTAX_INVALID`
- `invalid.scalar.anomaly.invalid-base64url` — invalid — `CANONICAL_ANOMALY_INVALID`
- `invalid.scalar.bit.unused-high-bit` — invalid — `CANONICAL_TYPE_MISMATCH`
- `invalid.scalar.date.invalid` — invalid — `CANONICAL_TEMPORAL_INVALID`
- `invalid.scalar.decimal.exponent` — invalid — `CANONICAL_DECIMAL_INVALID`
- `invalid.scalar.decimal.plus` — invalid — `CANONICAL_DECIMAL_INVALID`
- `invalid.scalar.decimal.precision-exceeds` — invalid — `CANONICAL_DECIMAL_INVALID`
- `invalid.scalar.decimal.scale-exceeds` — invalid — `CANONICAL_DECIMAL_INVALID`
- `invalid.scalar.float32.nonfinite` — invalid — `CANONICAL_FLOAT_NON_FINITE`
- `invalid.scalar.float64.nonfinite` — invalid — `CANONICAL_FLOAT_NON_FINITE`
- `invalid.scalar.signed-integer.16.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.signed-integer.24.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.signed-integer.32.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.signed-integer.64.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.signed-integer.8.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.string.invalid-utf8` — invalid — `CANONICAL_INVALID_UTF8`
- `invalid.scalar.string.noncharacter` — invalid — `CANONICAL_UNICODE_NONCHARACTER`
- `invalid.scalar.time-duration.out-of-range` — invalid — `CANONICAL_TIME_OUT_OF_RANGE`
- `invalid.scalar.unsigned-integer.16.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.unsigned-integer.24.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.unsigned-integer.32.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.unsigned-integer.64.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`
- `invalid.scalar.unsigned-integer.8.overflow` — invalid — `CANONICAL_INTEGER_OUT_OF_RANGE`

### `jcs.jsonl` (9 cases)

- `jcs.number.negative-zero` — valid — `canonicalize-jcs`
- `jcs.number.safe-integer-max` — valid — `canonicalize-jcs`
- `jcs.number.safe-integer-min` — valid — `canonicalize-jcs`
- `jcs.number.threshold-1e20-decimal` — valid — `canonicalize-jcs`
- `jcs.number.threshold-1e21-scientific` — valid — `canonicalize-jcs`
- `jcs.object.ascii-key-order` — valid — `canonicalize-jcs`
- `jcs.object.bmp-key-order` — valid — `canonicalize-jcs`
- `jcs.object.non-bmp-key-order` — valid — `canonicalize-jcs`
- `jcs.string.escaping` — valid — `canonicalize-jcs`

### `scalar.jsonl` (57 cases)

- `scalar.anomaly.valid-envelope` — valid — `encode-typed-scalar`
- `scalar.binary.empty` — valid — `encode-typed-scalar`
- `scalar.binary.leading-zero` — valid — `encode-typed-scalar`
- `scalar.bit.width-1` — valid — `encode-typed-scalar`
- `scalar.bit.width-64` — valid — `encode-typed-scalar`
- `scalar.bit.width-8` — valid — `encode-typed-scalar`
- `scalar.bit.width-9` — valid — `encode-typed-scalar`
- `scalar.boolean.true` — valid — `normalize-logical-literal`
- `scalar.date.leap-day` — valid — `normalize-logical-literal`
- `scalar.datetime.fraction` — valid — `normalize-logical-literal`
- `scalar.decimal.boundary-65-30` — valid — `normalize-logical-literal`
- `scalar.decimal.canonical-zero` — valid — `normalize-logical-literal`
- `scalar.decimal.leading-trailing-zero` — valid — `normalize-logical-literal`
- `scalar.float32.finite-max` — valid — `normalize-logical-literal`
- `scalar.float32.negative-zero` — valid — `normalize-logical-literal`
- `scalar.float32.rounding-boundary` — valid — `normalize-logical-literal`
- `scalar.float32.subnormal` — valid — `encode-typed-scalar`
- `scalar.float32.zero` — valid — `normalize-logical-literal`
- `scalar.float64.finite-max` — valid — `encode-typed-scalar`
- `scalar.float64.negative-zero` — valid — `normalize-logical-literal`
- `scalar.float64.rounding-boundary` — valid — `normalize-logical-literal`
- `scalar.float64.subnormal` — valid — `normalize-logical-literal`
- `scalar.float64.zero` — valid — `normalize-logical-literal`
- `scalar.frame.uleb128.length-127` — valid — `encode-typed-scalar`
- `scalar.frame.uleb128.length-128` — valid — `encode-typed-scalar`
- `scalar.null.empty` — valid — `normalize-logical-literal`
- `scalar.signed-integer.16.max` — valid — `normalize-logical-literal`
- `scalar.signed-integer.16.min` — valid — `normalize-logical-literal`
- `scalar.signed-integer.24.max` — valid — `normalize-logical-literal`
- `scalar.signed-integer.24.min` — valid — `normalize-logical-literal`
- `scalar.signed-integer.32.max` — valid — `normalize-logical-literal`
- `scalar.signed-integer.32.min` — valid — `normalize-logical-literal`
- `scalar.signed-integer.64.max` — valid — `normalize-logical-literal`
- `scalar.signed-integer.64.min` — valid — `normalize-logical-literal`
- `scalar.signed-integer.8.max` — valid — `normalize-logical-literal`
- `scalar.signed-integer.8.min` — valid — `normalize-logical-literal`
- `scalar.signed-integer.leading-plus` — valid — `normalize-logical-literal`
- `scalar.signed-integer.negative-zero` — valid — `normalize-logical-literal`
- `scalar.string.empty` — valid — `encode-typed-scalar`
- `scalar.string.multibyte` — valid — `encode-typed-scalar`
- `scalar.string.non-bmp` — valid — `encode-typed-scalar`
- `scalar.time-duration.hours-100` — valid — `normalize-logical-literal`
- `scalar.time-duration.hours-838` — valid — `normalize-logical-literal`
- `scalar.time-duration.hours-99` — valid — `normalize-logical-literal`
- `scalar.time-duration.negative-zero` — valid — `normalize-logical-literal`
- `scalar.time-duration.zero` — valid — `normalize-logical-literal`
- `scalar.timestamp.fraction` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.16.max` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.16.min` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.24.max` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.24.min` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.32.max` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.32.min` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.64.max` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.64.min` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.8.max` — valid — `normalize-logical-literal`
- `scalar.unsigned-integer.8.min` — valid — `normalize-logical-literal`


## 5. 人工 review checklist（§6.2 step 5）

- [ ] Case 新增范围与 catalog seeds（`gateway_shared_kernel.testing.cases.catalog`）一致，无 skip/extra
- [ ] Valid case（83）：完整 intermediate bytes / digest 已目视确认
- [ ] Invalid case（42）：stable error code 分类正确，含 §5.4 decimal precision/scale 与 scalar text Unicode families
- [ ] Manifest closure（count / size / raw SHA-256 / `vector_set_content_digest`）可离线重算
- [ ] Normative root **无** `CANDIDATE_PENDING_WP2_CONFIRMATION` marker
- [ ] Generator 仍拒绝 overwrite normative root（`test_rejects_normative_vector_root`）
- [ ] Tracked worktree 无 ephemeral candidate 泄漏、无 bless 入口
- [ ] Rust conformance 未设置 env 时读取 fixed normative root，不自动生成 candidate

## 6. Gate 与 Rust conformance 变更

`vnext/scripts/gate.sh` correctness 模式：

- **移除**：`mktemp` + ephemeral `generate` + `trap cleanup`
- **新增**：normative root 存在性检查 + Python `validate` normative root
- **导出**：`GATEWAY_SHARED_KERNEL_VECTOR_ROOT="${VNEXT_ROOT}/fixtures/vectors/shared-kernel/canonical-encoding/v1"`

`vector_conformance.rs`：

- 测试重命名为 `rust_vector_conformance_matches_normative_root`
- `EnvNotSet` → `paths::normative_vector_root()`（repository fixed root）
- 显式 env → 用于 candidate 人工验证；错误路径 fail closed
- **移除** Rust conformance 内的 Python candidate 自动生成

## 7. Generator 保护确认

- `paths.NORMATIVE_VECTOR_ROOT` 保护保持有效：`generate` 拒绝写入 `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/`
- 无 `--bless`、无 CI 自动覆盖 normative vectors 入口
- Normative 文件通过 reviewed patch 手工复制（排除 marker），非 generator 直写

## 8. 不在本步范围

- Repository consumer（§6.3）— 留 R7
- Arrow / PyO3 / `gateway-compute-core` 接入
- 修改已发布 v1 case 的 expected bytes（需 v2 流程）
