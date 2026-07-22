# WP3 R1 — Arrow / PyO3 详细设计

状态：WP3 R1 design evidence（**rev.3，待人工 re-review**）

日期：2026-07-22（rev.3）

适用：Phase 1 D3 通过后 → WP3 R2 实现入口

Authority：

- [Phase 1 Implementation Design and Delivery Plan](../../formal/plans/phase-1-implementation-design-and-delivery-plan.md)
- [Implementation Stages §4 Phase 1](../../formal/plans/implementation-stages.md)
- [Canonical Row Hash Compute Boundary](../../formal/contracts/canonical-row-hash-compute-boundary.md)（§4–§7；**§4 已于 2026-07-22 修正 decimal256 上界与 `null` physical mapping**，见 §11）
- [Shared Canonical Encoding](../../formal/contracts/shared-canonical-encoding.md)
- [Rust Safety and Performance Policy](../../formal/policies/rust-safety-and-performance-policy.md)
- [ADR 0001 Python/Rust Hybrid Compute Strategy](../../formal/adr/0001-python-rust-hybrid-compute-strategy.md)
- [WP3–WP5 Checkout 计划](wp3-wp5-checkout-plan.md)

前置完成：WP0–WP2 D3 checkpoint；normative vectors 125 cases；`gate.sh correctness` 通过。

## 1. 摘要

本文定义 Phase 1 WP3 首个正式 capability **`canonical_row_hashes_v1`** 的可实施设计，覆盖：

1. **JCS request/result/failure** 的解析、序列化与 stable code registry；
2. **Arrow mapping schema v1** 下每个 canonical scalar kind 的 physical type、nullability 规则与拒绝策略；
3. **`gateway-compute-core` / `gateway-compute-python` crate 边界** 与依赖图；
4. **PyO3 粗粒度调用形状**（一次 native call per stream、`RecordBatchReader` 统一、零 row materialization）；
5. **依赖与安全审计草稿**（供 WP3 R5 inventory 定稿）。

**语义 authority**：

- **Shared Kernel 拥有**：row frame、row hash、`raw-content` unordered table framing、scalar/identifier/JCS primitives。
- **Canonical Row Hash capability 拥有**：`table-schema` digest 的 **payload projection**（canonical field name 排序后的 declared schema JCS）；digest 计算复用 `DigestKind::TableSchema` + `semantic_digest`。
- compute boundary 只做 Arrow→`TypedScalar` 适配与 orchestration；**不得**复制 `raw-content` framing 或 digest domain 公式。

**Formal 一致性修正**：boundary §11 — `decimal256` 上界 **65**；semantic kind `null` → Arrow `DataType::Null`。

**本步交付物仅为设计**；R2 起再写 production 实现。Bootstrap `double_first_column` / `to_pylist()` 在 R2/R3 替换前可保留，但不得被新 formal API 引用。

### 1.1 WP3 R5 vs WP4 `PR-NATIVE` 分工（called-out）

| 范围 | WP3 R5（`native-kernel` component sign-off） | WP4 R4（首次正式 `gate.sh native` / `PR-NATIVE`） |
| --- | --- | --- |
| Rust core row hash / sort / table digest | ✅ | 回归 |
| PyO3 C Stream import/export、GIL release | ✅ | 回归 |
| Arrow mapping v1 全 kind 正向/负向 | ✅ component fixtures | 回归 + scenario matrix |
| Failure envelope / `effect=NONE` 映射 | ✅ | 回归 |
| Wheel smoke（maturin build） | ✅ 组件级 | release profile |
| **Arrow IPC write → ArtifactRef → reopen** | ❌ **deferred → WP4** | ✅ **必需** |
| raw IPC hash vs semantic `raw_content_digest` 分离验证 | ❌ deferred | ✅ |
| Scenario / harness / golden envelope | ❌ **deferred → WP5** | WP5 回归 |

WP3 R5 **不得**扩展 `gate.sh native` 或宣称已通过正式 `PR-NATIVE`（见 checkout 计划 §2–§3）。

---

## 2. 能力语义与处理流水线

固定步骤（与 boundary contract §2 对齐）：

```text
1. Fail-closed 解析 CanonicalTableRequest JCS（schema/version/closed object）
2. 校验 arrow_mapping_schema_version == 1
3. 计算 table_schema_digest（compute-core projection；§3.1.1）
4. Import Arrow stream → 逐 batch 校验 stream schema 一致性
5. Cross-check：declared_table_schema.fields ↔ Arrow field name/type/nullability（§5.2 precedence）
6. 逐行：Arrow column → TypedScalar → encode_row → raw row hash
7. 收集全部 row hash；unsigned lexicographic sort；保留 duplicate
8. raw_content_digest ← shared-kernel unordered-table helper（§3.1.2）
9. Export 排序后的 row_hash Arrow stream + 序列化 CanonicalTableResult JCS（canonicalize_jcs）
```

**确定性**：input row order、Arrow field order、batch partition 不改变 `table_schema_digest` 与 `raw_content_digest`；serial 重复执行逐 bytes 相同。

**空表**：zero row、zero field 均合法；empty stream 仍须提供 schema（可为 zero-field schema）。

---

## 3. JCS API 形状

### 3.0 Kernel 复用与 payload ownership（R2）

#### 3.0.1 `gateway-shared-kernel`（现有 + 一项新增）

| 能力 | 现有 / 新增 | 用途 |
| --- | --- | --- |
| `canonicalize_identifier` | 现有 | field name |
| `canonicalize_jcs` | 现有 | request/result/failure wire；table-schema payload bytes；anomaly envelope |
| `encode_typed_scalar` / `encode_row` | 现有 | 行编码 |
| `semantic_digest` | 现有 | `DigestKind::TableSchema`、`DigestKind::RawContent`（由各自 owner 调用） |
| **`unordered_row_hashes_content_digest`** | **R2 新增** | §3.1.2 `raw-content` framing（Shared Kernel payload owner） |

`unordered_row_hashes_content_digest` **不改变** WP0–WP2 normative vector bytes；R2 须增加与 Shared Contract §5 一致的 unit tests。

#### 3.0.2 `gateway-compute-core`（capability payload owner）

| 能力 | 位置 | 复用的 kernel primitive |
| --- | --- | --- |
| **`table_schema_digest` projection + digest** | `schema_digest.rs` | `canonicalize_identifier`、`canonicalize_jcs`、`semantic_digest(TableSchema, …)` |

**禁止**在 shared-kernel 新增 `table_schema_digest` helper 或 `TableSchemaField` DTO——该 payload 的 shape/排序由 Canonical Row Hash capability 拥有（[Shared Canonical Encoding §5](../../formal/contracts/shared-canonical-encoding.md) digest kind 表）。

### 3.1 `CanonicalTableRequest`（request_schema_version = 1）

Normative JCS object（unknown/duplicate field → `COMPUTE_REQUEST_SCHEMA_INVALID`）：

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
        "semantic_type": { "kind": "signed-integer", "bits": 64 }
      }
    ]
  }
}
```

| 字段 | 规则 | 失败 code / stage |
| --- | --- | --- |
| `request_schema_version` | 必须 `== 1` | `COMPUTE_REQUEST_SCHEMA_INVALID` / `request` |
| `contract_binding` | `contract_id` + `semantic_version` exact match | `COMPUTE_CONTRACT_VERSION_UNSUPPORTED` / `request` |
| `canonical_encoding_version` | 必须 `== 1` | `COMPUTE_CANONICAL_VERSION_UNSUPPORTED` / `request` |
| `arrow_mapping_schema_version` | 必须 `== 1` | `COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED` / `request` |
| `declared_table_schema.fields[]` | authoring sequence；digest/encoding 按 canonical field name UTF-8 排序 | 见 field rules |
| `fields[].name` | 经 `canonicalize_identifier`；empty/collision → fail | `CANONICAL_VALUE_INVALID` / `canonicalize` |
| `fields[].nullable` | `false` 且出现 null → fail | `CANONICAL_VALUE_INVALID` / `canonicalize` |
| `fields[].semantic_type` | 复用 normative vector schema 关闭 union | `COMPUTE_REQUEST_SCHEMA_INVALID` / `request` |

**Request 禁止携带**：table/business identity、provider、thread count、timeout、host path、artifact locator（boundary §3）。

#### 3.1.0 Request JCS 接收语义（固定，无二义）

```text
request bytes (UTF-8 JSON)
  → canonicalize_jcs（严格 JSON / I-JSON / duplicate-member 校验）
  → 使用返回的 canonical bytes 解析 closed DTO
```

- **不与原始输入 bytes 比较**；pretty spacing、key order 等非 canonical 但语义等价的 JSON **被接受**（canonicalize 后解析）。
- `canonicalize_jcs` 失败 → `COMPUTE_REQUEST_SCHEMA_INVALID` / `request`。
- **Result / failure 输出**：DTO serialize → UTF-8 JSON → `canonicalize_jcs` → wire bytes（同样不与中间 pretty form 比较）。

#### 3.1.1 `table_schema_digest`（compute-core `schema_digest.rs`）

Payload 构造（**不**进入 request JSON；**capability-owned projection**）：

1. 对 `declared_table_schema.fields` 中每个 field，将 `name` 替换为 `canonicalize_identifier(name)` 的 UTF-8 字符串（authoring name 仅用于报错上下文）。
2. 按 canonical name 的 UTF-8 bytes 升序排序 field 对象。
3. 每个 field 的 JCS projection：`{ "name", "nullable", "semantic_type" }`（`semantic_type` object 原样保留）。
4. `payload_jcs = canonicalize_jcs(serde_json::to_vec({"fields":[...sorted...]}))`。
5. `table_schema_digest = semantic_digest(DigestKind::TableSchema, &payload_jcs)` → wire `DigestRef`。

**compute-core 内部函数（草案，不进入 shared-kernel）**：

```rust
fn table_schema_digest(fields: &[DeclaredSchemaField]) -> Result<SemanticDigest, ComputeFailure>;
```

其中 `DeclaredSchemaField` 为 compute-core request DTO；identifier/canonicalize/digest **只调** shared-kernel primitives。

#### 3.1.2 `raw_content_digest`（shared-kernel `unordered_row_hashes_content_digest`）

与 [Shared Canonical Encoding §5](../../formal/contracts/shared-canonical-encoding.md) **同一公式**：

```text
unordered_table_frame = ULEB128(row_count) + sorted(raw 32-byte row hashes, unsigned lexicographic)
raw_content_digest    = semantic_digest(RawContent, unordered_table_frame)
```

**R2 shared-kernel 公开签名（草案）**：

```rust
/// Each element must be exactly 32 bytes (raw row hash). Helper sorts internally; duplicates retained.
pub fn unordered_row_hashes_content_digest(
    row_hashes: &[[u8; 32]],
) -> Result<SemanticDigest, CanonicalEncodingError>;
```

compute-core **禁止**自行拼接 ULEB128 或调用 `semantic_digest(RawContent, …)` 时传入非 helper 构造的 frame。

### 3.2 `CanonicalTableResult`（result_schema_version = 1）

```json
{
  "result_schema_version": 1,
  "contract_binding": {
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0"
  },
  "canonical_encoding_version": 1,
  "arrow_mapping_schema_version": 1,
  "table_schema_digest": "sha256:…",
  "row_count": "0",
  "raw_content_digest": "sha256:…",
  "diagnostics": []
}
```

| 字段 | 规则 |
| --- | --- |
| `row_count` | canonical unsigned decimal string（非 JSON number） |
| `table_schema_digest` | 与 request 派生值一致（成功路径） |
| `raw_content_digest` | `unordered_row_hashes_content_digest` 输出 |
| `diagnostics` | Phase 1 conformance **固定 `[]`**（见 §4.4） |

成功路径 core 返回 `(output_arrow_stream, result_jcs_bytes)`；`result_jcs_bytes = canonicalize_jcs(...)`。失败路径只返回 `ComputeFailureEnvelope` JCS（无 output stream）。

### 3.3 `ComputeFailureEnvelope`（failure_schema_version = 1）

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

#### 3.3.1 `effect=NONE` 边界

| 场景 | `effect` | `retry_class` | 说明 |
| --- | --- | --- | --- |
| Invalid request JCS / version / contract | `NONE` | `NEVER` | 无部分输出 |
| Arrow import / schema mismatch / unsupported type | `NONE` | `NEVER` | 无 row hash 输出 |
| Canonical value invalid（含 non-nullable null） | `NONE` | `NEVER` | 无部分 digest |
| Compute 阶段非输入类内部失败 | `NONE` | `NEVER` | `ROW_HASH_COMPUTE_FAILED`（§4.2） |
| Arrow export 失败 | `NONE` | `NEVER` | 已有 result 也不交付给 caller |
| Resource limit（内存上限等，R4 可选） | `NONE` | `SAFE_WITH_POLICY` | 仍无 semantic 副作用 |
| Caught native panic | `NONE` | `SAFE_WITH_POLICY` | `NATIVE_PANIC`；abort/segfault 不伪装为 envelope |

**Pure compute 始终 `effect=NONE`**（boundary §7）。Adapter **不得**静默 retry；`retry_class` 仅告知调用方 policy。

---

## 4. Stable failure code registry

### 4.1 Compute boundary codes（v1 关闭集）

| Code | Stage | 触发条件（摘要） |
| --- | --- | --- |
| `COMPUTE_REQUEST_SCHEMA_INVALID` | `request` | JCS 语法、closed object、缺字段、非法 `semantic_type` shape |
| `COMPUTE_CONTRACT_VERSION_UNSUPPORTED` | `request` | `contract_binding` 不匹配 |
| `COMPUTE_CANONICAL_VERSION_UNSUPPORTED` | `request` | `canonical_encoding_version != 1` |
| `COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED` | `request` | `arrow_mapping_schema_version != 1` |
| `ARROW_STREAM_IMPORT_FAILED` | `arrow-import` | C Stream / capsule 无法导入；`RecordBatchReader::next` 返回 `ArrowError`（§6.1 C） |
| `ARROW_TYPE_UNSUPPORTED` | `schema` | 实际 Arrow physical type 属于 §5.3 v1 **拒绝集** |
| `ARROW_SCHEMA_MISMATCH` | `schema` | 类型在 v1 支持集内，但与 declared mapping **不一致**（含 field 数/名/nullability、batch 间 schema 不等） |
| `CANONICAL_VALUE_INVALID` | `canonicalize` | 合法 Arrow 值在 canonical 编码阶段失败（§4.2） |
| `ROW_HASH_COMPUTE_FAILED` | `compute` | 非外部输入触发的内部失败（§4.2） |
| `RESOURCE_LIMIT_EXCEEDED` | `compute` | 显式资源策略触发（Phase 1 可选配置） |
| `ARROW_STREAM_EXPORT_FAILED` | `arrow-export` | 输出 C Stream 构建失败 |
| `NATIVE_PANIC` | `compute` | `catch_unwind` 捕获的意外 panic |

Stage 关闭集：`request | arrow-import | schema | canonicalize | compute | arrow-export`。

### 4.2 Failure 分类 precedence（固定，按序短路）

**Schema 阶段（§5.2）**：

```text
1. 若实际 Arrow DataType 属于 §5.3 拒绝集 → ARROW_TYPE_UNSUPPORTED
2. 否则若与 declared semantic mapping 不一致 → ARROW_SCHEMA_MISMATCH
```

示例：

| 情况 | Code |
| --- | --- |
| `timestamp[us, tz=America/New_York]` | `ARROW_TYPE_UNSUPPORTED`（non-UTC） |
| `timestamp[us, tz=UTC]` 但 declared `datetime` | `ARROW_SCHEMA_MISMATCH` |
| `large_utf8` | `ARROW_TYPE_UNSUPPORTED` |
| `utf8` 但 declared `binary` | `ARROW_SCHEMA_MISMATCH` |
| declared `signed-integer` bits=8，Arrow `int32` | `ARROW_SCHEMA_MISMATCH`（width 不匹配） |

**Canonicalize 阶段**：

- Arrow 值已通过 schema cross-check；`encode_typed_scalar` / `encode_row` / `canonicalize_jcs`（anomaly）返回的 **`CanonicalEncodingError` → `CANONICAL_VALUE_INVALID` / `canonicalize`**。
- 含：24-bit 越界、decimal precision 溢出、float nonfinite、BIT 高位、temporal 越界、invalid anomaly envelope、non-nullable null。

**Compute 阶段**：

- **`ROW_HASH_COMPUTE_FAILED`** 仅用于 **非用户输入语义** 的失败，例如：
  - `unordered_row_hashes_content_digest` 在合法 32-byte 输入上返回 unexpected error（内部 invariant）；
  - 输出 `fixed_size_binary(32)` batch 构建失败（非 schema 类）；
  - 其他无法归因于 request/Arrow 值/shared-kernel 编码的 core bug。
- **`CanonicalEncodingError` 不在 compute 阶段重新分类**；若在 digest helper 调用前已发生，应已在 canonicalize 阶段捕获。Helper 对合法输入不应产生 encoding error——若产生则 `ROW_HASH_COMPUTE_FAILED`。

**Import 阶段**（§6.1 C；**Safe Rust / safe pyo3-arrow only**）：

| 层 | 构造方式 | Code |
| --- | --- | --- |
| R2 core | 测试用 `RecordBatchReader` 在 `next()` 返回 `Err(ArrowError)` | `ARROW_STREAM_IMPORT_FAILED` |
| R3/R4 adapter | pyo3-arrow safe API：错误 Python 类型、无效/非 Arrow capsule | `ARROW_STREAM_IMPORT_FAILED` |
| WP4 | corrupt/truncated **Arrow IPC** bytes | **deferred**；不属于 WP3 C 类 |

**禁止** first-party 手工构造损坏 Arrow C ABI / capsule bytes（违反 unsafe 禁令）。

### 4.3 Python facade 异常投影（非 normative）

| Envelope | Python exception（建议） |
| --- | --- |
| `COMPUTE_*` / `ARROW_*` request & schema | `gateway_compute.ComputeRequestError` |
| `CANONICAL_VALUE_INVALID` | `gateway_compute.CanonicalValueError` |
| `ROW_HASH_COMPUTE_FAILED` / `NATIVE_PANIC` | `gateway_compute.ComputeError` |
| `RESOURCE_LIMIT_EXCEEDED` | `gateway_compute.ResourceLimitError` |

调试信息（`kernel_code`、field name、batch index）放在 exception **属性**上，**不**写入 envelope `diagnostics`（Phase 1）。

### 4.4 Conformance compare 规则（v1）

| 对象 | 比较范围 |
| --- | --- |
| 成功 `CanonicalTableResult` JCS | 全字段 exact bytes（`diagnostics` 恒 `[]`） |
| `ComputeFailureEnvelope` JCS | `failure_schema_version`、`contract_binding`、`code`、`stage`、`effect`、`retry_class`；**`diagnostics` 恒 `[]`** |
| Python exception type/message | **不参与** |
| Sorted row hashes | raw 32-byte 序列 exact |
| `table_schema_digest` / `raw_content_digest` | `DigestRef` exact |

---

## 5. Arrow mapping schema v1

**Declared semantic schema 是唯一 semantic authority**；Arrow field metadata、extension type、dictionary 不得扩展或覆盖 semantic kind（boundary §4）。

### 5.1 Mapping 矩阵

| Semantic kind | Declared constraints | Arrow physical type | Nullability |
| --- | --- | --- | --- |
| `null` | — | **`null`（`DataType::Null`）仅此一种** | 必须 `nullable=true`；所有行 null |
| `boolean` | — | `bool` | 与 declared 一致 |
| `signed-integer` | `bits` ∈ {8,16,24,32,64} | `int8/int16/int32/int64`；24→`int32` + range check | 与 declared 一致 |
| `unsigned-integer` | `bits` ∈ {8,16,24,32,64} | `uint8/uint16/uint32/uint64`；24→`uint32` + range check | 与 declared 一致 |
| `decimal` | `precision` 1–65, `scale` 0–30, `scale≤precision` | p≤38 → `decimal128(p,s)`；39–65 → `decimal256(p,s)`；**exact** p/s | 与 declared 一致 |
| `float32` | — | `float32` | 与 declared 一致 |
| `float64` | — | `float64` | 与 declared 一致 |
| `string` | — | `utf8`（**非** `large_utf8`） | 与 declared 一致 |
| `binary` | — | `binary`（**非** `large_binary`） | 与 declared 一致 |
| `bit` | `bit_width` 1–64 | `binary`，每值 `ceil(n/8)` bytes | 与 declared 一致 |
| `date` | — | `date32` | 与 declared 一致 |
| `datetime` | — | `timestamp[us]`，**无** timezone | 与 declared 一致 |
| `timestamp` | — | `timestamp[us, tz=UTC]`，timezone **exact UTC** | 与 declared 一致 |
| `time-duration` | — | `duration[us]` | 与 declared 一致 |
| `source-literal-anomaly` | — | `binary`，值为 schema-valid JCS anomaly envelope bytes | 与 declared 一致 |

#### 5.1.1 `null` semantic kind（闭合规则；与 boundary §4 对齐）

- Physical type **必须**为 Arrow `null`（`DataType::Null`）；`bool`/`int32`/temporal 等 **一律** `ARROW_SCHEMA_MISMATCH`。
- `nullable` 必须为 `true`；`nullable=false` → `ARROW_SCHEMA_MISMATCH`（schema 阶段）。
- `NullArray` 语义上恒全 null；无 values buffer；**无** separate non-null validity 分支。

#### 5.1.2 其他 kind 提取规则

- **Nullable non-null kind**：validity false → `TypedScalar::Null`；不改变 non-null scalar tag。
- **24-bit signed**：合法 `−8_388_608..=8_388_607`；否则 `CANONICAL_VALUE_INVALID`。
- **24-bit unsigned**：合法 `0..=16_777_215`；否则 `CANONICAL_VALUE_INVALID`。
- **Decimal**：unscaled integer → ASCII lexical → `DecimalScalar`；超出 declared precision → `CANONICAL_VALUE_INVALID`（非 lexical invalid）。
- **Float**：nonfinite → `CANONICAL_VALUE_INVALID`。
- **String**：Arrow `utf8` 已保证 valid UTF-8；kernel 侧仍走 string 路径。
- **BIT(n)**：byte len = `ceil(n/8)`；unused high bits 必须为 0。
- **Temporal**：component extract；`date`：`date32` 映射到 civil year `< 1` → `CANONICAL_VALUE_INVALID`；`datetime`/`timestamp`：可表达 `i64` μs 但超出 canonical civil/instant 范围 → `CANONICAL_VALUE_INVALID`；`time-duration` 上限 `838:59:59.999999`（MySQL TIME）。
- **Anomaly**：binary → `canonicalize_jcs` + envelope validation。

### 5.2 Cross-check 算法（stage=`schema`）

对每个 declared field（canonical name 匹配）：

1. Arrow stream schema 包含同名 field（canonical UTF-8 name exact）。
2. `nullable` exact match。
3. 按 §4.2 precedence：先判 §5.3 拒绝集 → `ARROW_TYPE_UNSUPPORTED`；再判 §5.1 mapping → 不一致则 `ARROW_SCHEMA_MISMATCH`。
4. Declared ↔ Arrow field **bijection**（无 extra/missing）。
5. 每个 batch schema **deep equal** stream schema。

**Arrow field order 不参与 semantic**；cross-check 只比较集合与映射，不比较 Arrow 列顺序。Row encoding 仍按 canonical field name 排序（shared-kernel `encode_row`）。

### 5.3 v1 明确拒绝（→ `ARROW_TYPE_UNSUPPORTED`）

```text
large_utf8 / large_binary
dictionary / union / list / fixed-size-list / struct / map
non-UTC timestamp timezone
millisecond / nanosecond temporal unit
Arrow extension type 作为 semantic authority
view types（若 Arrow 版本暴露）
```

### 5.4 Output Arrow schema（固定）

```text
row_hash: fixed_size_binary[32], nullable=false
```

Rows 按 raw hash bytes **unsigned lexicographic** 升序；duplicate 保留。Chunking 非 semantic。

---

## 6. 测试策略（R2/R4 实现）

Fixture 根：`vnext/fixtures/vectors/compute/canonical-row-hash/v1/`（**独立**于 normative canonical-encoding v1）。

### 6.1 Fixture 类别（A / B / C）

| 类别 | 含义 | 典型 code | WP3 构造方式 |
| --- | --- | --- | --- |
| **A — value boundary** | Schema cross-check 通过；值在 canonical 阶段失败或触边界 | `CANONICAL_VALUE_INVALID` | 合法 Arrow arrays |
| **B — schema** | Reader 可用；schema/type 与 declared 冲突 | `ARROW_SCHEMA_MISMATCH` / `ARROW_TYPE_UNSUPPORTED` | 合法 Arrow，错误 schema |
| **C — stream/import** | Reader/import 在 consume 前或 `next()` 失败 | `ARROW_STREAM_IMPORT_FAILED` | §4.2 Import 表；**非** corrupt IPC |

**禁止**在 A 类要求 Arrow 类型系统内不可表达的值（如 `Int8Array` 存 128、合法 `utf8` 存 invalid UTF-8、decimal “invalid lexical”）。

**Corrupt/truncated Arrow IPC** → **WP4** artifact 负向套件；不列入 WP3 fixture 根。

### 6.2 逐 kind 矩阵（A/B）

| Kind | A: positive / boundary | A: null | B: schema |
| --- | --- | --- | --- |
| `null` | 全 null | — | `nullable=false`；physical `int32` 而非 `null` |
| `boolean` | true/false | null slot | `int8` → `MISMATCH`；`large_utf8` → `UNSUPPORTED` |
| `signed-integer` | 0, −1, width max | null | 24-bit: **合法** `−8_388_608`/`8_388_607`；**非法** `−8_388_609`/`8_388_608` → A；declared 8 / Arrow `int32` → B |
| `unsigned-integer` | 0, max | null | 24-bit: `16_777_215` ok；`16_777_216` → A |
| `decimal` | zero; p=38/39; **p=65,s=30** | null | declared p/s ≠ Arrow p/s → B；unscaled 超 precision → A |
| `float32/64` | ±0, subnormal, max | null | NaN/Inf → A |
| `string` | ASCII, BMP, non-BMP | null | `large_utf8` → B (`UNSUPPORTED`) |
| `binary` | empty, leading zeros | null | `large_binary` → `UNSUPPORTED` |
| `bit` | n=1,8,9,64 | null | wrong byte len → A；`utf8` → B |
| `date` | leap day; **year 0 / negative epoch**（`date32` 可表达） | null | invalid civil → A；`timestamp` → B |
| `datetime` | μs; **civil 越界** `i64` μs（可表达） | null | `timestamp[us,UTC]` → B (`MISMATCH`) |
| `timestamp` | UTC instant; **instant 越界** `i64` μs | null | non-UTC tz → B (`UNSUPPORTED`) |
| `time-duration` | ±0; `838:59:59.999999` | null | `839:00:00` → A (`CANONICAL_VALUE_INVALID`; underlying kernel `CANONICAL_TIME_OUT_OF_RANGE`) |
| `anomaly` | valid envelope | null | malformed envelope → A；`utf8` → B |

### 6.3 确定性 fixture 族（mandatory）

- empty / one-row / multi-batch 同一语义表；
- **batch partition** 变化；
- **input row permutation** → 相同 `raw_content_digest`；
- **Arrow field order permutation**（列顺序不同、映射相同）→ 相同 row hash 与 digest；
- duplicate row hashes 保留；
- zero-field table；
- **serial repeated execution**：同一 request + input 连续执行 ≥2 次 → `result_jcs` bytes **逐字节相等**；sorted `row_hash` column bytes **逐字节相等**（含 multi-batch input）。

### 6.4 Oracle 分工

- R2/R4：**Rust core** + Arrow fixtures 为主；shared-kernel helpers 与 normative encoding vectors 回归；
- WP5 前 **不** 要求 Python 整表 reference oracle。

---

## 7. Crate 边界与模块设计

### 7.1 依赖图

```text
gateway-shared-kernel          (canonical primitives + raw-content helper; no Arrow/PyO3/fs)
        ↑
gateway-compute-core           (row-hash kernel; Arrow-rs only)
        ↑
gateway-compute-python         (PyO3 + pyo3-arrow adapter)
        ↑
gateway_backend / tests        (facade consumer; Phase 1 walking skeleton)
```

**硬约束**：

| Crate | 允许 | 禁止 |
| --- | --- | --- |
| `gateway-compute-core` | `gateway-shared-kernel`；`arrow-*`（safe API）；`serde`/`serde_json`/`thiserror` | `pyo3`、`pyo3-arrow`、filesystem、`ArtifactStore`、network；**复制 unordered framing** |
| `gateway-compute-python` | `gateway-compute-core`、`pyo3`、`pyo3-arrow` | 直接调用 `gateway-shared-kernel`；业务逻辑复制 |
| `gateway-shared-kernel` | 新增 `unordered_row_hashes_content_digest` only | 不反向依赖 compute；不引入 Arrow/PyO3；**不**拥有 `table-schema` projection |

`gateway-architecture-check` 在 R2 扩展：core 无 PyO3/fs；python 不 bypass core。

### 7.2 `gateway-compute-core` 模块与公开 API（R2）

```text
src/
  lib.rs
  request.rs
  result.rs
  schema_digest.rs   # table-schema payload projection (capability owner)
  arrow_mapping.rs
  arrow_extract.rs
  pipeline.rs
  errors.rs
```

**公开 API（Rust，无 PyO3）**：

```rust
use arrow_array::RecordBatchReader;

pub fn parse_request(request_jcs: &[u8]) -> Result<ParsedRequest, ComputeFailure>;

/// `input` is the arrow-rs `RecordBatchReader` trait object; adapter provides impl from C Stream.
pub fn canonical_row_hashes_v1(
    request: &ParsedRequest,
    input: Box<dyn RecordBatchReader + Send>,
) -> Result<CanonicalRowHashOutput, ComputeFailure>;
```

- **选用 `Box<dyn RecordBatchReader + Send>`**（`arrow-array` 标准 trait），**不**暴露 crate-local stream trait；避免跨 crate 可实现性歧义。
- **单元测试**：`Vec<RecordBatch>` + 小型 `struct BatchReader { ... }` 实现 `RecordBatchReader`。
- **Adapter（R3）**：`gateway-compute-python` 内 `struct StreamReader(Box<dyn RecordBatchReader + Send>)` 或由 `pyo3_arrow::PyRecordBatchReader` 转为 `Box<dyn RecordBatchReader + Send>` 再传入 core（具体转换在 R3 evidence 记录；R1 只要求类型边界明确）。

**Pipeline 禁止项**：不得本地构造 `ULEB128(row_count)||sorted_hashes`；必须调用 `unordered_row_hashes_content_digest`。

### 7.3 `gateway-compute-python`（R3）

**Native**：

```text
canonical_row_hashes_v1(request_jcs: bytes, input_stream_capsule) -> tuple[output_capsule, result_jcs: bytes]
```

**Python facade**：

```python
def canonical_row_hashes_v1(
    request_jcs: bytes,
    data: pa.RecordBatch | pa.Table | pa.RecordBatchReader,
) -> tuple[pa.RecordBatchReader, bytes]:
    reader = _as_record_batch_reader(data)
```

失败：抛出带 **完整 envelope JCS**（`diagnostics=[]`）的 exception；调试字段见 §4.3。

---

## 8. PyO3 / Arrow 调用形状

### 8.1 一次 native call 与 GIL 区间

```text
[GIL attached]  facade: _as_record_batch_reader
[GIL attached]  pyo3-arrow: import C Stream → PyRecordBatchReader / RecordBatchReader
[GIL detached]  py.detach(|| compute_core::canonical_row_hashes_v1(...))
                ├─ stream consume
                ├─ schema cross-check
                ├─ encode_row / row hashes
                ├─ unordered_row_hashes_content_digest (shared-kernel)
                └─ 构造 Rust 侧 output RecordBatchReader
[GIL attached]  pyo3-arrow: export output C Stream / PyRecordBatchReader
[GIL attached]  facade: 返回 pa.RecordBatchReader
```

`Python::detach` 在 closure 返回时 **自动 re-attach**（[PyO3 0.29 `Python::detach`](https://docs.rs/pyo3/0.29.0/pyo3/marker/struct.Python.html#method.detach)）。Export 与构建 Python `RecordBatchReader` **在 detached 区间之外**。

禁止：per-row/column/scalar FFI；`to_pylist()` / `to_pydict()` / generator producer。

### 8.2 `RecordBatchReader` 统一

```python
def _as_record_batch_reader(data: pa.RecordBatch | pa.Table | pa.RecordBatchReader) -> pa.RecordBatchReader:
    if isinstance(data, pa.RecordBatchReader):
        return data
    if isinstance(data, pa.RecordBatch):
        return pa.RecordBatchReader.from_batches(data.schema, [data])
    if isinstance(data, pa.Table):
        return data.to_reader()  # 禁止 combine_chunks()
    raise TypeError(...)
```

### 8.3 内存

- Input buffers 可零拷贝导入；row-hash output **必然分配**。
- R4：GIL 探针 + 确认无 `to_pylist` 调用。

---

## 9. 依赖与安全审计草稿（R5 定稿输入）

### 9.1 版本锁定

| 组件 | 版本 | Lock identity |
| --- | --- | --- |
| Rust toolchain | stable **1.97.0** | `rust-toolchain.toml` / CI pin |
| `pyo3` | **0.29.0** | `vnext/rust/Cargo.lock` |
| `pyo3-arrow` | **0.19.0** | 同上 |
| `arrow-*` | **59.1.0** | 同上（与 pyo3-arrow 对齐） |
| Python | **3.14.6** | `vnext/shared_kernel/.python-version` |
| `pyarrow` | **25.0.0** | `vnext/backend/uv.lock` |
| `maturin` | **1.14.1** | `gateway-compute-python/pyproject.toml` |

### 9.2 新增 crate 依赖（draft）

**gateway-compute-core**：`gateway-shared-kernel`、`arrow-schema`、`arrow-array`、`arrow-buffer`、`arrow-data`、`serde`、`serde_json`、`thiserror`。

**gateway-compute-python**：`gateway-compute-core`、`pyo3`、`pyo3-arrow`。

### 9.3 R5 审计 checklist（由草稿升级为 evidence 表）

| 项 | R5 必填 |
| --- | --- |
| 用途 + lock identity | 每个 dependency 一行 |
| Safe API 边界 | first-party 仅经 reviewed safe surface |
| Third-party unsafe 事实 | arrow/pyo3 内部；first-party `forbid(unsafe_code)` |
| 维护状态 | crates.io 最近发布日期 / 活跃度 |
| Advisory | **`cargo audit`**（或 repo 等价工具）命令 + **数据库 git rev / 时间戳** 写入 evidence |
| License | 逐 crate SPDX；与 proprietary workspace 兼容性 |
| Proc-macro / build script | `pyo3-build-config`、`serde_derive` 行为记录 |
| 替代方案 | 例如「纯 Python reference 整表路径」**不**替代 production kernel |
| 回退路径 | 禁用 adapter；core + Arrow fixtures 仍可测 |

---

## 10. Deferred

| 项 | 目标 WP |
| --- | --- |
| Artifact IPC round-trip / `ArtifactRef` | WP4 |
| `gate.sh native` / 正式 `PR-NATIVE` | WP4 R4 |
| Scenario / harness / golden | WP5 |
| Normative canonical-encoding vector 变更 | — |
| Rayon / SIMD / external sort | Phase 3+ |

---

## 11. R2 实现入口清单（re-review 签核后）

1. **shared-kernel**：实现并测试 `unordered_row_hashes_content_digest`（§3.1.2）**仅此一项新增**。
2. **compute-core**：`schema_digest.rs` 实现 `table_schema_digest` projection（§3.1.1）；`Cargo.toml` 接入 shared-kernel + pinned `arrow-*`。
3. 实现 §3.1.0 request JCS 语义 + result/failure wire + §4 failure precedence + §5 extract/cross-check。
4. `canonical_row_hashes_v1(..., Box<dyn RecordBatchReader + Send>)`；`raw_content_digest` **只调** shared-kernel helper。
5. Arrow fixtures §6（含 A temporal boundary、serial determinism、C 类 safe import/stream errors）；architecture-check 扩展。
6. **不**改 `gate.sh native`；`correctness` 全绿。
7. Bootstrap `double_*` 暂留。

---

## 12. 人工 review checklist（rev.3）

- [ ] **A1** — Request JCS：**canonicalize 后解析**（§3.1.0）；result/failure wire；failure precedence；`diagnostics=[]`。
- [ ] **A2** — 15 kinds；`null` = `DataType::Null` 与 formal boundary §4/§11 一致；decimal 39–65。
- [ ] **A3** — `raw-content` → shared-kernel helper only；`table-schema` projection → compute-core；kernel primitives 复用清单正确。
- [ ] **A4** — `Box<dyn RecordBatchReader + Send>`；crate 边界清晰。
- [ ] **A5** — GIL attached/detached/export（§8.1）。
- [ ] **A6** — A/B/C 分类与 Safe Rust 构造；temporal boundary；field permutation；serial byte equality。
- [ ] **A7** — WP3 R5 vs WP4 `PR-NATIVE` 分工。
- [ ] **A8** — 版本/lock；R5 审计字段。

**Reviewer sign-off**：________________ 日期：________

---

## 13. 变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-07-22 | 初稿 |
| 2026-07-22 rev.2 | decimal 65；unordered helper；failure precedence；GIL；RecordBatchReader API；null 闭合；A/B/C；diagnostics |
| 2026-07-22 rev.3 | `table-schema` payload 回归 compute-core；request JCS 语义固定；formal `null` mapping；C 类 Safe Rust；temporal + serial determinism |
| 2026-07-22 rev.3.1 | §6.2 time-duration：`839:00:00` expected code 改为 `CANONICAL_VALUE_INVALID`（非 kernel code 直出） |
