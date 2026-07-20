# Canonical Row Hash Compute Boundary Contract

状态：正式设计（Accepted）

阶段：Phase 1 walking skeleton；Phase 3 production capability foundation

Contract ID：`gateway-vnext.canonical-row-hash-compute-boundary`

Owner：Canonical Row Hash capability

Semantic version：`1.0.0`

Request/result schema version：`1`

Arrow mapping schema version：`1`

Failure schema version：`1`

依赖：[`gateway-vnext.shared-canonical-encoding`](shared-canonical-encoding.md)，canonical encoding version `1`

工程约束：[Rust Safety and Performance Policy](../policies/rust-safety-and-performance-policy.md)

## 1. 范围与 ownership

本文拥有 `canonical_row_hashes_v1` capability 的 language-neutral request/result/failure、Arrow physical mapping、PyO3 coarse-grained call shape 和 row-hash artifact content schema。

本文不拥有：

- Canonical scalar/frame/row/table digest bytes；由 Shared Canonical Encoding 拥有。
- Generic `ArtifactRef` envelope、storage locator 和 retention；由 Artifacts 拥有。
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
7. 返回 sorted row-hash stream、table schema digest、row count 和 diagnostics。

Input row order、Arrow field order和 batch partition不改变 formal schema/content digest。Serial repeated execution必须逐 bytes确定。

## 3. `CanonicalTableRequest`

Canonical JCS shape：

```json
{
  "request_schema_version": 1,
  "contract_binding": {
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0"
  },
  "canonical_encoding_version": 1,
  "arrow_mapping_schema_version": 1,
  "declared_table_schema": {
    "fields": [
      {
        "name": "example",
        "nullable": true,
        "semantic_type": {"kind": "signed-integer", "bits": 64}
      }
    ]
  }
}
```

规则：

- 所有 object unknown/duplicate field fail closed。
- `fields[]` 是 authoring sequence；schema digest 和 row encoding按 CanonicalIdentifier UTF-8 bytes排序。
- `name` 必须经过 Shared Kernel canonicalization；empty/invalid/collision失败。
- `nullable=false` field 出现 null失败；`nullable=true` 不改变 non-null scalar tag。
- Semantic type descriptor复用 Canonical Encoding Normative Vector Schema 的关闭 union。
- Request 不携带 table/business/Workspace/Submission identity、provider、thread count、timeout、host path、resource limit 或 artifact locator。

`table_schema_digest` 使用 Shared Kernel semantic digest kind `table-schema`，payload 是按 canonical field name排序后的 declared schema JCS projection。

## 4. Arrow mapping schema v1

Declared semantic schema 是唯一 semantic authority；Arrow metadata不能扩展、覆盖或推断 semantic kind。Physical mapping：

| Canonical semantic kind | Arrow physical type |
| --- | --- |
| null | Declared nullable field 的 validity bitmap |
| boolean | `bool` |
| signed integer | 8/16/32/64-bit分别映射`int8/int16/int32/int64`；24-bit映射`int32`并额外校验24-bit范围 |
| unsigned integer | 8/16/32/64-bit分别映射`uint8/uint16/uint32/uint64`；24-bit映射`uint32`并额外校验24-bit范围 |
| decimal | precision 1–38使用`decimal128(p, s)`；39–76使用`decimal256(p, s)`；precision/scale必须与declared schema exact一致 |
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
  "result_schema_version": 1,
  "contract_binding": {
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0"
  },
  "canonical_encoding_version": 1,
  "arrow_mapping_schema_version": 1,
  "table_schema_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "row_count": "0",
  "raw_content_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "diagnostics": []
}
```

示例 digest 是 shape placeholder。`row_count` 是 canonical unsigned decimal string，避免 JSON safe-integer ceiling。Diagnostics 是 compact、sanitized、non-semantic；不进入 schema/content digest，不能携带 row payload、host path、stack或 provider-private object。

## 7. Failure contract

所有可恢复 deterministic failure 通过一个 versioned `ComputeFailureEnvelope` 映射：

```json
{
  "failure_schema_version": 1,
  "contract_binding": {
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0"
  },
  "code": "ARROW_SCHEMA_MISMATCH",
  "stage": "schema",
  "effect": "NONE",
  "retry_class": "NEVER",
  "diagnostics": []
}
```

Stage 关闭集：

```text
request | arrow-import | schema | canonicalize | compute | arrow-export
```

Stable code v1：

```text
COMPUTE_REQUEST_SCHEMA_INVALID
COMPUTE_CONTRACT_VERSION_UNSUPPORTED
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

Invalid request/schema/value使用 `retry_class=NEVER`；resource/native transient分类可以是 `SAFE_WITH_POLICY`。Pure compute始终 `effect=NONE`，但自动 retry仍由调用方 policy决定，adapter不得静默重试。

Python exception class只是 facade projection，不是 normative contract。Caught Rust panic映射为 `NATIVE_PANIC`。Allocator abort、segfault或无法捕获的 process termination不能伪装为普通 envelope；由 worker/process evidence记录，production takeover属于后续 Operation阶段。

## 8. Artifact content boundary

Canonical Row Hash capability拥有 `CanonicalRowHashesArtifact` content：

- Media type：`application/vnd.apache.arrow.stream`。
- Arrow schema：第 6 节 fixed schema。
- Semantic content identity：`raw_content_digest`。
- Associated schema identity：`table_schema_digest`。
- Canonical/Arrow mapping version markers必须保存。

Artifacts owner创建 generic `ArtifactRef`；Rust core/adapter不接收 locator/filesystem/object-store，也不创建 ref。Python facade/ArtifactStore：

```text
Rust Arrow stream
  -> Arrow IPC stream writer
  -> ArtifactStore / ArtifactRef
  -> reopen and verify raw bytes
  -> decode schema/sorted row hashes
  -> recompute semantic digest
```

IPC direct `raw_sha256` 和 semantic `raw_content_digest` 必须分离。Provider、PyArrow/Rust版本或 batch chunking造成不同 IPC bytes时，不构成 semantic mismatch；除非未来 artifact owner另外发布 exact IPC byte contract。

ArtifactRef/manifest不得保存 host path。Round-trip必须验证 size、raw hash、Arrow schema、sorted row hashes、table schema digest和semantic content digest；只验证文件存在不算通过。

## 9. Phase 1 structural performance evidence

Phase 1 不设 numeric throughput/latency gate，但必须证明：

- One native call consumes multi-batch stream。
- Python row/list/dict materialization count为零。
- Rust compute/sort/digest主区间释放 GIL。
- Empty/one/multi-batch、batch partition、field/input row permutation产生同一 formal result。
- Memory evidence分离 input buffers、row-hash vector/sort和output IPC materialization；不声称 constant memory。
- Invalid schema、unsupported type、panic、digest mismatch、corrupt/truncated artifact分类确定。

Timeout/cancel API、Rayon、SIMD、external sort、Parquet、numeric benefit claim和独立 Rust worker/service不属于 Phase 1 contract。

## 10. Classification 与验收

Module public：是。Persisted：Result metadata可进入 artifact manifest；row hashes通过 artifact持久化。Wire：JCS bytes + Arrow C Stream/PyCapsule；不建立网络 wire。

验收：

- Python reference与Rust provider对所有 Arrow mapping fixtures得到相同 schema digest、sorted row hashes和content digest。
- Full Shared Kernel vectors先于 capability conformance通过。
- Formal native path不存在 Python row materialization或第二个 object-graph entrypoint。
- Failure envelope、GIL release和artifact recovery通过 dedicated native lane。
- Rust core不依赖 PyO3、Python、filesystem或ArtifactStore；PyO3 adapter单向依赖 core。
