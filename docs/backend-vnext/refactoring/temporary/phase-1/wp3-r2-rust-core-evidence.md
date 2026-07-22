# WP3 R2 — Rust Core `canonical_row_hashes_v1` Evidence

状态：R2 implementation evidence（post-audit remediation, round 2）

日期：2026-07-22

Authority：

- [WP3 R1 Arrow/PyO3 设计](wp3-r1-arrow-pyo3-design.md)（rev.3.1）
- [Canonical Row Hash Compute Boundary](../../formal/contracts/canonical-row-hash-compute-boundary.md)
- [Shared Canonical Encoding](../../formal/contracts/shared-canonical-encoding.md)
- [WP3–WP5 Checkout 计划](wp3-wp5-checkout-plan.md) §8

Gate：**`PR-CORRECTNESS`**（`vnext/scripts/gate.sh correctness`）；**非** `PR-NATIVE` / `gate.sh native`

## 摘要

完成 WP3 R2 纯 Rust `canonical_row_hashes_v1` kernel，并按两轮审核结论修复 Blocking/Major 项：

- `gateway-shared-kernel` 新增 `unordered_row_hashes_content_digest`（Shared Contract §5 raw-content framing）；checked `u64::try_from` length conversion
- `gateway-compute-core` 实现 request/result/failure JCS、schema digest、Arrow mapping/extract、pipeline；入口读取 `RecordBatchReader::schema()` 并 per-batch deep equal
- Decimal256 基于 signed decimal 字符串格式化（`strip_prefix('-')`，无算术取负 / 无 `u128` 窄化）
- Nullable null slot 在 **compute-core** `row_encode.rs` 做 encoding-only 适配（`DeclaredType::Null`）后委托 `encode_row`；**未**修改 shared-kernel scalar/row API
- Anomaly envelope / declared_type closed-object 校验
- `ParsedRequest` 封装 + digest 绑定 re-validate + canonical name collision 拒绝
- Integration tests 拆分为 6 个 suite；fixture README 与真实覆盖对齐
- `gateway-architecture-check` 使用 `cargo metadata` 真实 package `name` 检查依赖边界

Bootstrap `double_nullable_i64` **保留**（R3 处理）。

## API 对照（R1 §3.0）

| 能力 | Owner | R2 状态 |
| --- | --- | --- |
| `unordered_row_hashes_content_digest` | shared-kernel | ✅ 新增导出 |
| `table_schema_digest` projection | compute-core `schema_digest.rs` | ✅ + collision reject |
| `parse_request` / `canonical_row_hashes_v1` | compute-core | ✅ `Box<dyn RecordBatchReader + Send>` |
| Nullable null slot (`0x00` tag) | compute-core `row_encode.rs` | ✅ encoding-only `DeclaredType::Null` + `encode_row` |
| `raw_content_digest` 本地 ULEB128 framing | — | ❌ 禁止（只调 kernel helper） |

## 变更清单（文件级）

### gateway-shared-kernel

- `src/framing.rs` — `unordered_row_hashes_content_digest` + checked length + unit tests
- `src/lib.rs` — 导出

### gateway-compute-core

- `src/{contract,errors,request,schema_digest,result,arrow_mapping,arrow_extract,row_encode,pipeline}.rs`
- `tests/canonical_row_hash.rs` — core A/B/C + determinism
- `tests/decimal256.rs` — decimal matrix incl. `i256::MIN`
- `tests/matrix_kinds.rs` — per-kind A/B matrix
- `tests/matrix_widths.rs` — integer width / null-slot matrix
- `tests/schema_reader.rs` — reader schema authority
- `tests/request_binding.rs` — collision at parse
- `tests/support/*` — batch reader（含 `SchemaOnlyReader`）、builders、runner

### gateway-architecture-check

- `src/lib.rs` — `cargo metadata` dependency boundaries on package `name` + unit tests

### Fixtures

- `vnext/fixtures/vectors/compute/canonical-row-hash/v1/README.md`

## 验证命令与结果

```bash
cd vnext/rust
cargo fmt --check
cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings
cargo test --locked --offline --workspace --all-targets
cargo build --locked --offline --workspace --release
cd ../scripts && ./gate.sh correctness
```

`gateway-compute-core` 测试计数（2026-07-22 round 2）：

| Suite | Integration |
| --- | ---: |
| `canonical_row_hash.rs` | 22 |
| `matrix_kinds.rs` | 24 |
| `matrix_widths.rs` | 5 |
| `decimal256.rs` | 8 |
| `schema_reader.rs` | 6 |
| `request_binding.rs` | 1 |
| **小计** | **66** |
| lib unit tests | 12 |
| **合计** | **78** |

## 人工 review checklist

- [x] R1 §3.0：仅 shared-kernel 新增 unordered digest helper；row encoding 复用 `encode_row`
- [x] R2 closed DTO：`ParsedRequest` 私有字段 + digest re-validate
- [x] R3 canonical collision 在 parse/digest 阶段拒绝
- [x] R4 reader schema authority、global rejection、view/extension、metadata deep equality
- [x] R5 decimal256 无 silent loss；`i256::MIN` 不 panic；row encoding 无本地复制
- [x] R6 empty stream、sorted output、checked count、固定 output schema
- [x] R7 mandatory matrix：width/subnormal/sort/multi-batch serial/nullable-null 覆盖
- [x] R8 architecture gate 使用 package `name`；rename 不绕过禁令
- [x] Normative shared-kernel fixture SHA 未变
- [x] `gate.sh correctness` 全绿

## Deferred 项

| 项 | 归属 | 说明 |
| --- | --- | --- |
| PyO3 / Python facade | WP3 R3 | 不在 R2 范围 |
| Arrow C Stream adapter | WP3 R3 | 不在 R2 范围 |
| Artifact IPC / corrupt stream fixtures | WP4 | R1 §6.1 明确 defer |
| Scenario YAML / golden envelopes | WP5 | Checkout plan |
| Formal `PR-NATIVE` / `gate.sh native` | WP4 R4 | 首次 native gate |
| `bootstrap double_nullable_i64` 移除 | WP3 R3 | R2 保留 |

## 审核项映射（remediation）

| Finding | 修复 |
| --- | --- |
| Decimal256 silent zero | `format_decimal_from_signed_decimal_string` + tests |
| `i256::MIN` panic | 字符串取符号；integration `CANONICAL_VALUE_INVALID` |
| Duplicated row encoding | `row_encode.rs` 仅做 nullable-null 输入适配后调用 `encode_row` |
| Reader schema / empty stream | `input.schema()` authority + `SchemaOnlyReader` tests |
| R7 matrix gaps | 6 integration suites + unit tests |
| Schema precedence / view / extension | `scan_schema_rejections` + deep `schemas_equal` |
| Anomaly fail open | closed-object validation |
| ParsedRequest / collision | private fields + `validate_digest_binding` |
| Unchecked length cast | `u64::try_from` in framing + pipeline（compute-core 无本地 row ULEB128） |
| Architecture rename bypass | check package `name` not local alias |
| SK scalar scope | 完整回滚；nullable null 仅在 compute `row_encode.rs` 输入适配 |
| Output batch error code | `ROW_HASH_COMPUTE_FAILED` |
