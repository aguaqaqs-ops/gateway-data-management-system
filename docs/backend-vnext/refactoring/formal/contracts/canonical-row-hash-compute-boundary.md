# Canonical Row Hash Compute Boundary Contract

状态：正式设计（Accepted）

阶段：Phase 1 walking skeleton；Phase 3 production capability foundation

Contract ID：`gateway-vnext.canonical-row-hash-compute-boundary`

Owner：Canonical Row Hash capability

Semantic version：`1.0.0`

Boundary version：`1`

Arrow mapping schema version：`1`

依赖：[`gateway-vnext.shared-canonical-encoding`](shared-canonical-encoding.md)，canonical encoding version `1`

工程约束：[Rust Safety and Performance Policy](../policies/rust-safety-and-performance-policy.md)

## 1. 范围与 ownership

本文拥有`canonical_row_hashes_v1` capability的language-neutral
request/result/failure、Arrow physical mapping、PyO3 coarse-grained call shape和
row-hash artifact content schema。Canonical row/content bytes仍使用Shared
Canonical Encoding v1。

本文不拥有：

- Canonical scalar/frame/row/table digest bytes；由 Shared Canonical Encoding 拥有。
- Backend `BackendArtifactRef` envelope、storage locator和retention policy；由
  Artifacts拥有。
- Python/Rust provider selection、Operation scheduling、Repository transport 或业务 table rules。
- Projection、comparison、records、Parquet 或 cache schema。

## 2. Capability semantics

```text
canonical_row_hashes_v1
  input: CanonicalTableRequest JCS bytes + Arrow RecordBatch stream
  output: sorted row-hash Arrow stream + CanonicalTableResult JCS bytes
```

固定步骤：

1. Fail-closed validate request schema/version和 Arrow mapping version。
2. Cross-check declared semantic table schema 与 Arrow field name/type/nullability。
3. 按 Shared Canonical Encoding v1 canonicalize identifier/scalar 并生成每行 `row_frame`。
4. 计算 raw 32-byte row hash。
5. 按 raw bytes unsigned lexicographic sort，保留 duplicate row hash。
6. 按 Shared Contract unordered table framing计算 `raw_content_digest`。
7. 返回 sorted row-hash stream、table schema digest、row count 和 raw content digest。

Input row order、Arrow field order和 batch partition不改变 formal schema/content digest。Serial repeated execution必须逐 bytes确定。

## 3. `CanonicalTableRequest`

Canonical JCS shape：

```json
{
  "boundary_version": 1,
  "canonical_encoding_version": 1,
  "arrow_mapping_version": 1,
  "declared_fields": [
    {
      "name": "example",
      "nullable": true,
      "semantic_type": {"kind": "signed-integer", "bits": 64}
    }
  ]
}
```

规则：

- 所有 object unknown/duplicate field fail closed。
- `boundary_version`、`canonical_encoding_version`和`arrow_mapping_version`必须为
  当前支持值；不重复携带contract ID或semantic version。
- `declared_fields[]`是authoring sequence；schema digest和row encoding按
  CanonicalIdentifier UTF-8 bytes排序。
- `name` 必须经过 Shared Kernel canonicalization；empty/invalid/collision失败。
- `nullable=false` field 出现 null失败；`nullable=true` 不改变 non-null scalar tag。
- Semantic type descriptor使用Shared Canonical Encoding定义的关闭union。
- Request 不携带 table/business/Workspace/Submission identity、provider、thread count、timeout、host path、resource limit 或 artifact locator。

`table_schema_digest`使用Shared Kernel semantic digest kind`table-schema`，payload
是按canonical field name排序后的declared fields JCS projection。

## 4. Arrow mapping schema v1

Declared semantic schema 是唯一 semantic authority；Arrow metadata不能扩展、覆盖或推断 semantic kind。Physical mapping：

| Canonical semantic kind | Arrow physical type |
| --- | --- |
| null | `null`（Arrow `DataType::Null`）；`nullable` 必须为 `true`；semantic kind `null` 列所有行均为 null |
| boolean | `bool` |
| signed integer | 8/16/32/64-bit分别映射`int8/int16/int32/int64`；24-bit映射`int32`并额外校验24-bit范围 |
| unsigned integer | 8/16/32/64-bit分别映射`uint8/uint16/uint32/uint64`；24-bit映射`uint32`并额外校验24-bit范围 |
| decimal | precision 1–38使用`decimal128(p, s)`；39–65使用`decimal256(p, s)`；precision/scale必须与declared schema exact一致；logical precision 上限 65 与 [Shared Canonical Encoding](shared-canonical-encoding.md) 对齐 |
| float32 / float64 | `float32 | float64` |
| string | `utf8` |
| binary | `binary` |
| `BIT(n)` | `binary` + declared `bit_width`；每值恰为`ceil(n/8)` bytes，未使用的最高bits为零，保留leading zero bits |
| date | `date32` |
| datetime civil | `timestamp[us]`，timezone absent |
| timestamp instant | `timestamp[us, UTC]`，timezone exact `UTC` |
| time duration | `duration[us]` |
| source literal anomaly | `binary`，内容为 schema-valid JCS anomaly envelope bytes |

v1 明确拒绝：

```text
large_utf8 / large_binary
dictionary / union / list / fixed-size-list / struct / map
non-UTC timestamp timezone
millisecond/nanosecond temporal mapping
Arrow extension type as semantic authority
```

Empty stream必须仍提供 schema。Zero row、zero field table均合法并按 Shared Contract framing产生确定 digest。每个 batch 的 schema必须与 stream schema一致。

## 5. PyO3/Arrow call contract

Formal native entrypoint：

```text
canonical_row_hashes_v1(
  request_jcs: bytes,
  input: Arrow C Stream
) -> (
  output: Arrow C Stream,
  result_jcs: bytes
)
```

约束：

- Python facade 可以接受 PyArrow `RecordBatch | Table | RecordBatchReader`，但 native call 前统一为 `RecordBatchReader`。
- `RecordBatch` 使用单 batch reader view；`Table` 使用保留 chunks 的 `to_reader()`；禁止自动 `combine_chunks()`。
- Production bulk path 不接受任意 Python generator/iterator producer。
- 一次 native call消费一条 table stream；不逐 row/scalar/column跨 FFI。
- Input/output 使用 owned Arrow C Stream transfer；禁止 `to_pylist`、`to_pydict`、Python row iterator或 Python-side scalar normalization。
- Rust 在 capsule/schema import后释放 GIL，stream consumption、encoding、hash/sort/digest期间保持 detached；导出 Python Arrow object时重新取得 GIL。
- Input buffers可以零拷贝导入；row-hash output必然分配。Contract 不声称全路径 zero-copy，copy/materialization必须可观测。
- Single-batch convenience不是第二个 native overload或 semantic contract。

Batch sizing、thread count和 resource policy由 execution config拥有，不进入 request、result或 semantic digest。

## 6. Output Arrow schema 与 result

Output stream schema固定：

```text
row_hash: fixed_size_binary(32), non-null
```

Rows 按 raw hash bytes升序，duplicate保留。Chunking不是 semantic；consumer不得用 IPC batch boundary参与 equality。

`CanonicalTableResult`：

```json
{
  "boundary_version": 1,
  "table_schema_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "row_count": "0",
  "raw_content_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}
```

示例digest是shape placeholder。`row_count`是canonical unsigned decimal string，避免
JSON safe-integer ceiling。Result不携带diagnostics、contract binding或重复的
canonical/Arrow mapping version；provider diagnostics属于普通日志或exception
details，不参与业务result。

Golden直接比较sorted row hashes、`row_count`、`table_schema_digest`和
`raw_content_digest`。不建立golden envelope、`canonical-table-result` wrapper
digest或fixture self-digest。

## 7. Failure contract

所有可恢复deterministic failure映射为最小`ComputeFailure`：

```json
{
  "code": "ARROW_SCHEMA_MISMATCH",
  "message": "input Arrow schema does not match declared fields",
  "details": {}
}
```

Stable code：

```text
COMPUTE_REQUEST_SCHEMA_INVALID
COMPUTE_BOUNDARY_VERSION_UNSUPPORTED
COMPUTE_CANONICAL_VERSION_UNSUPPORTED
COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED
ARROW_STREAM_IMPORT_FAILED
ARROW_SCHEMA_MISMATCH
ARROW_TYPE_UNSUPPORTED
CANONICAL_VALUE_INVALID
ROW_HASH_COMPUTE_FAILED
RESOURCE_LIMIT_EXCEEDED
ARROW_STREAM_EXPORT_FAILED
NATIVE_PANIC
```

`message`必须sanitized；`details`可选且由code解释。Pure compute没有外部effect，
不再重复返回`effect=NONE`、stage或retry class。是否重试由caller policy决定，
adapter不得静默重试。

Python exception class只是facade projection，不是normative contract。Caught Rust
panic映射为`NATIVE_PANIC`。Allocator abort、segfault或无法捕获的process
termination不能伪装为普通failure；production takeover属于后续Operation阶段。

## 8. Artifact content boundary

Canonical Row Hash capability拥有 `CanonicalRowHashesArtifact` content：

- Media type：`application/vnd.apache.arrow.stream`。
- Arrow schema：第 6 节 fixed schema。
- Semantic content identity：`raw_content_digest`。
- Associated schema identity：`table_schema_digest`。

Artifacts owner创建minimal `BackendArtifactRef`；Rust core/adapter不接收
locator/filesystem/object-store，也不创建ref：

```text
artifact_id
media_type
size_bytes
raw_sha256
```

Capability result或content manifest保存`raw_content_digest`、
`table_schema_digest`和所需boundary version。Retention与physical access是
ArtifactStore/business policy，不进入ref identity。

Python facade/ArtifactStore：

```text
Rust Arrow stream
  -> Arrow IPC stream writer
  -> ArtifactStore / BackendArtifactRef
  -> ordinary reopen verifies size/raw SHA and Arrow schema
```

IPC direct`raw_sha256`和semantic`raw_content_digest`必须分离。Provider、
PyArrow/Rust版本或batch chunking造成不同IPC bytes时，不构成semantic mismatch。
BackendArtifactRef不得保存host path。

发布路径和golden/integration必须验证size、raw hash、Arrow schema、sorted row
hashes、table schema digest和semantic content digest。普通reopen不再次遍历全部
row hashes；完整semantic recompute只用于测试、诊断或明确不可信边界。

## 9. Structural engineering checks

普通tests必须证明：

- One native call consumes multi-batch stream。
- Python row/list/dict materialization count为零。
- Rust compute/sort/digest主区间释放 GIL。
- Empty/one/multi-batch、batch partition、field/input row permutation产生同一 formal result。
- Invalid schema、unsupported type、panic、digest mismatch、corrupt/truncated artifact分类确定。

不生成memory breakdown、component evidence或phase sign-off。Timeout/cancel API、
Rayon、SIMD、external sort、Parquet、numeric benefit claim和独立Rust
worker/service不属于本boundary。

## 10. Classification 与验收

Module public：是。Persisted：Result metadata可进入 artifact manifest；row hashes通过 artifact持久化。Wire：JCS bytes + Arrow C Stream/PyCapsule；不建立网络 wire。

验收：

- Python reference与Rust provider对保留golden得到相同schema digest、sorted row
  hashes和content digest。
- Full Shared Kernel golden corpus先于capability test通过。
- Formal native path不存在 Python row materialization或第二个 object-graph entrypoint。
- Minimal failure、GIL release和artifact round-trip通过普通native tests。
- Rust core不依赖 PyO3、Python、filesystem或ArtifactStore；PyO3 adapter单向依赖 core。
- 普通artifact reopen验证raw integrity和固定schema，不默认全量semantic rehash。

## 11. Change control

| 日期 | 变更 | 理由 |
| --- | --- | --- |
| 2026-07-22 | §4 decimal Arrow mapping：`decimal256` precision 上界由 `76` 修正为 **`65`** | Formal 内部一致性：与 Shared Canonical Encoding owner-declared decimal precision `1..=65` 及现有 `DeclaredType` 校验边界对齐；不改变 WP0–WP2 已验收 canonical scalar bytes |
| 2026-07-22 | §4 semantic kind `null`：physical type 明确为 Arrow `DataType::Null`（闭合集） | WP3 R1 设计收敛：原“validity bitmap”表述与 `null` kind 混用且未闭合 physical type；non-`null` kind 的 nullable slot 仍由各 physical type 的 validity bitmap 表达（§3 `nullable` 规则） |
| 2026-07-31 | Boundary v2、minimal failure/ArtifactRef和ordinary reopen | ADR 0010 Phase 0–1 proportional simplification；canonical scalar/row/content bytes不变 |
| 2026-08-01 | 首发 Canonical Row Hash v1 重基线 | 当前没有外部 consumer 或 durable compatibility 义务；删除 pre-baseline fallback，canonical scalar/row/content bytes不变 |
