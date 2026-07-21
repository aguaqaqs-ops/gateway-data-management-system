# Canonical Encoding Normative Vector Schema

状态：正式设计（Accepted）

阶段：Phase 1 实现；Phase 1–9 持续执行

Contract ID：`gateway-vnext.canonical-encoding-vector-schema`

Owner：Shared Kernel

Vector-set schema version：`1`

Semantic version：`1.0.0`

依赖：[`gateway-vnext.shared-canonical-encoding`](shared-canonical-encoding.md)，canonical encoding version `1`

## 1. 范围

本文唯一拥有 canonical encoding normative vector 的 manifest、JSONL case envelope、test-only input representation、closure digest 和 stable error-code schema。Canonical bytes、scalar tag、framing 与 digest 算法仍由 Shared Canonical Encoding Contract 唯一拥有。

Vector schema 是 test-only oracle schema，不是 production API、PyO3 DTO、Repository wire contract 或通用 scalar decoder。

## 2. 根目录与固定 closure

```text
vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/
  vector-set.json
  jcs.jsonl
  scalar.jsonl
  digest.jsonl
  invalid.jsonl
```

`vector-set.json` 的 `files[]` 必须且只能声明上述四个 JSONL 文件，按 path UTF-8 bytes 升序排列。每个 JSONL 文件：

- UTF-8、LF line ending，最后一行也以 LF 结束。
- 每行是独立、schema-valid 的 JCS object；禁止空行和 comment。
- Case 按 `case_id` ASCII bytes 升序；`case_id` 在整个 vector set 内唯一。
- Raw file integrity 使用直接 SHA-256；semantic closure identity 使用本文第 4 节的 domain-separated digest。

## 3. `vector-set.json` schema

```json
{
  "vector_set_schema_version": 1,
  "vector_set_id": "gateway-vnext.shared-kernel.canonical-encoding.v1",
  "owner": "shared-kernel",
  "contract_binding": {
    "contract_id": "gateway-vnext.shared-canonical-encoding",
    "semantic_version": "1.0.0"
  },
  "canonical_encoding_version": 1,
  "files": [
    {
      "path": "digest.jsonl",
      "media_type": "application/x-ndjson",
      "case_schema_id": "gateway-vnext.canonical-encoding.digest-case.v1",
      "case_count": 1,
      "size_bytes": 1,
      "raw_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    },
    {
      "path": "invalid.jsonl",
      "media_type": "application/x-ndjson",
      "case_schema_id": "gateway-vnext.canonical-encoding.invalid-case.v1",
      "case_count": 1,
      "size_bytes": 1,
      "raw_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    },
    {
      "path": "jcs.jsonl",
      "media_type": "application/x-ndjson",
      "case_schema_id": "gateway-vnext.canonical-encoding.jcs-case.v1",
      "case_count": 1,
      "size_bytes": 1,
      "raw_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    },
    {
      "path": "scalar.jsonl",
      "media_type": "application/x-ndjson",
      "case_schema_id": "gateway-vnext.canonical-encoding.scalar-case.v1",
      "case_count": 1,
      "size_bytes": 1,
      "raw_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    }
  ],
  "vector_set_content_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}
```

示例中的 count、size 和 digest 是 shape placeholder，不是 normative value。字段规则：

| Field | Rule |
| --- | --- |
| `vector_set_schema_version` | JSON integer，必须为 `1`。 |
| `vector_set_id` | 固定为 contract/version 对应 stable ID。 |
| `owner` | 固定为 `shared-kernel`。 |
| `contract_binding` | 必须逐字段匹配 Shared Canonical Encoding v1。 |
| `canonical_encoding_version` | 必须为 `1`，并与目录 `v1` 一致。 |
| `files[].path` | 单 segment relative POSIX path；不得 escape、symlink 或重复。 |
| `case_count`、`size_bytes` | 非负 I-JSON safe integer；必须与实际文件一致。 |
| `raw_sha256` | `sha256:` + 64 lowercase hex，直接覆盖 raw JSONL bytes。 |
| `vector_set_content_digest` | 第 4 节定义的 semantic digest。 |

所有 object `additionalProperties=false`；unknown/missing/duplicate field fail closed。

## 4. Vector-set content digest

计算 projection：

1. Schema validate `vector-set.json`，暂不比较 `vector_set_content_digest`。
2. 校验四个 JSONL 的 path、size、raw SHA-256、case count、case schema和 case ordering。
3. 从 vector-set object 移除 `vector_set_content_digest`。
4. 对剩余 object 生成 JCS bytes。
5. 使用 Shared Canonical Encoding semantic digest kind `vector-set`：

```text
vector_set_content_digest = semantic_digest("vector-set", JCS(projected_vector_set))
```

由于 projection 已包含每个 JSONL 的 direct raw hash，digest 覆盖完整 closure 且不存在自引用。`vector-set.json` 自身不声明自己的 raw hash。

## 5. Common case envelope

每行都包含：

```text
case_schema_version: 1
case_id: lower dot/kebab stable ID
operation: file-specific closed enum
input: operation-discriminated object
expected or expected_error: exactly one
```

`case_id` 一经发布不因文件重排、实现语言或 provider 变化而复用。Valid case 位于 `jcs.jsonl | scalar.jsonl | digest.jsonl` 并只允许 `expected`；invalid case 只位于 `invalid.jsonl` 并只允许 `expected_error`。

所有 arbitrary bytes 使用无 padding base64url。DigestRef 使用 `sha256:` lowercase hex。不得保存 Python/Rust type name、exception、stack、host path 或实现入口。

## 6. `jcs.jsonl`

Operation 只有 `canonicalize-jcs`：

```json
{
  "case_schema_version": 1,
  "case_id": "jcs.object.non-bmp-key-order",
  "operation": "canonicalize-jcs",
  "input": {
    "json_utf8_base64url": "ZXhhbXBsZQ"
  },
  "expected": {
    "canonical_bytes_base64url": "ZXhhbXBsZQ"
  }
}
```

Input 是完整 JSON document UTF-8 bytes，而不是预先解析的宿主对象，从而保留 duplicate member、number lexeme 和 invalid Unicode/encoding case 的可表达性。Valid output 必须比较完整 JCS bytes。

## 7. `scalar.jsonl`

Operation 是：

```text
normalize-logical-literal
encode-typed-scalar
```

### 7.1 Declared type descriptor

`declared_type.kind` 是关闭枚举：

```text
null | boolean
signed-integer | unsigned-integer
decimal | float32 | float64
string | binary | bit
date | datetime | timestamp | time-duration
source-literal-anomaly
```

Conditional fields：

- Integer：`bits: 8 | 16 | 24 | 32 | 64`；只用于 width/range validation，payload仍为固定 8 bytes。
- Decimal：`precision` 为 `1..=65`、`scale` 为 `0..=30`且`scale <= precision`，镜像 Shared Canonical Encoding v1 的owner-declared MySQL range。
- Bit：`bit_width` 为 `1..=64`，镜像 Shared Canonical Encoding v1 的`BIT(n)` range。
- 其余 kind 禁止额外 type field。

### 7.2 Test-only source union

`normalize-logical-literal` 使用：

```json
{"kind": "utf8-logical-literal", "text": "+001"}
```

或：

```json
{"kind": "raw-logical-literal", "bytes_base64url": "AAE"}
```

它表示 SQL unquote/unescape 后、type coercion 前的 logical literal；原 SQL token 不进入 vector input。UTF-8/raw literal 的语言中立 grammar、允许集与 stable failure code 由 [Shared Canonical Encoding](shared-canonical-encoding.md) §3.1 唯一拥有；vector schema 不得另行放宽。

### 7.3 Typed value union

`encode-typed-scalar` 与 normalization 的 `expected.typed_value` 共用关闭 union：

| Kind | Value field |
| --- | --- |
| `null` | 无。 |
| `boolean` | `value: true | false`。 |
| `signed-integer` / `unsigned-integer` | `decimal` canonical或待 encode decimal string。 |
| `decimal` | `decimal` string。 |
| `float32` / `float64` | `bits_hex`，分别 8/16 lowercase hex chars。 |
| `string` | `text`。 |
| `binary` / `bit` | `bytes_base64url`。 |
| `date` / `datetime` / `timestamp` / `time-duration` | `text`，使用 Shared Contract 的 language-neutral typed textual form。 |
| `source-literal-anomaly` | 闭合 `envelope` object，shape 由 Shared Canonical Encoding v1 与本文 `anomalyEnvelope` schema 固定（四字段、`additionalProperties=false`、`declared_type` 为完整 DeclaredType descriptor）。 |

Typed representation只用于 oracle input；production Arrow mapping 由 Canonical Row Hash Compute Boundary 拥有。

### 7.4 Scalar valid case

```json
{
  "case_schema_version": 1,
  "case_id": "scalar.signed-integer.leading-plus",
  "operation": "normalize-logical-literal",
  "input": {
    "declared_type": {"kind": "signed-integer", "bits": 32},
    "source": {"kind": "utf8-logical-literal", "text": "+001"}
  },
  "expected": {
    "typed_value": {"kind": "signed-integer", "decimal": "1"},
    "payload_base64url": "AAAAAAAAAAE",
    "scalar_frame_base64url": "EAgAAAAAAAAAAQ"
  }
}
```

`normalize-logical-literal` 必须返回 `typed_value`、payload 和完整 frame；`encode-typed-scalar` 返回 payload 和完整 frame。实现必须逐 bytes 比较两层输出。

## 8. `digest.jsonl`

Operation 关闭集：

```text
canonicalize-identifier
encode-row
encode-collection
semantic-digest
raw-blob-digest
```

Operation shape：

- `canonicalize-identifier`：input `identifier`；expected `canonical_utf8_base64url`。
- `encode-row`：input `fields[]`，每项为 `name + typed scalar input`；expected `row_frame_base64url + row_hash`。
- `encode-collection`：input `semantics: sequence | multiset | set | keyed-collection` 和对应 base64url item/key/value；expected 仅 `collection_frame_base64url`。Collection-level digest 不在本 operation 输出。
- `semantic-digest`：input `digest_kind + canonical_payload_base64url`；expected `raw_hash_base64url + digest_ref`。若 payload 是某条 `encode-collection`（或 `encode-row`）的 frame，case 必须引用或复制那条 case 已固定的 frame bytes，不得在验证运行时调用 encoder 生成 digest 输入。
- `raw-blob-digest`：input `raw_bytes_base64url`；expected `digest_ref`，使用直接 SHA-256，不加 semantic prefix。

Row fields 可以按任意 input order 提供；expected 必须证明 CanonicalIdentifier ordering。Multiset/set item input order可以任意；sequence 保留 input order。Duplicate 的保留/拒绝由 Shared Contract collection semantics 决定。Keyed key/value 与 collection item 均为 opaque bytes（见 Shared Canonical Encoding Contract）。

## 9. `invalid.jsonl` 与 error registry

Invalid case 复用对应 valid operation 的 `input` shape，只保存：

```json
{
  "case_schema_version": 1,
  "case_id": "invalid.scalar.uleb128.non-minimal",
  "operation": "validate-scalar-frame",
  "input": {"frame_base64url": "gAA"},
  "expected_error": {"code": "CANONICAL_ULEB128_NON_MINIMAL"}
}
```

Invalid-only operation额外包含 `validate-scalar-frame`。v1 stable code registry：

```text
CANONICAL_INVALID_UTF8
CANONICAL_INVALID_UNICODE
CANONICAL_UNICODE_NONCHARACTER
CANONICAL_JCS_SYNTAX_INVALID
CANONICAL_JCS_DUPLICATE_MEMBER
CANONICAL_JCS_NUMBER_OUT_OF_RANGE
CANONICAL_JCS_NON_FINITE_NUMBER
CANONICAL_IDENTIFIER_EMPTY
CANONICAL_IDENTIFIER_COLLISION
CANONICAL_TYPE_MISMATCH
CANONICAL_INTEGER_OUT_OF_RANGE
CANONICAL_DECIMAL_INVALID
CANONICAL_FLOAT_NON_FINITE
CANONICAL_TEMPORAL_INVALID
CANONICAL_TIME_OUT_OF_RANGE
CANONICAL_ANOMALY_INVALID
CANONICAL_SCALAR_TAG_UNKNOWN
CANONICAL_SCALAR_TAG_RESERVED
CANONICAL_FRAME_TRUNCATED
CANONICAL_ULEB128_NON_MINIMAL
CANONICAL_ULEB128_OVERFLOW
CANONICAL_FRAME_LENGTH_INVALID
CANONICAL_COLLECTION_SEMANTICS_UNKNOWN
CANONICAL_COLLECTION_DUPLICATE_ITEM
CANONICAL_COLLECTION_DUPLICATE_KEY
```

错误 message、host exception class、parser library error 和 stack 不属于 normative output。多个条件同时非法时，由 operation schema 声明的 validation order 选择唯一 code；每个 invalid case 应尽量只触发一个原因。

`validate-scalar-frame` 的 unknown/reserved tag 分区由 Shared Canonical Encoding Contract 拥有：

```text
unassigned 0x00..=0x7F -> CANONICAL_SCALAR_TAG_RESERVED
0x80..=0xFF            -> CANONICAL_SCALAR_TAG_UNKNOWN
```

Vector-set / JSONL closure 必须在 schema validation 前以 strict JSON loader 拒绝 duplicate member；不得依赖宿主 `json.loads` 的 last-wins 行为。

## 10. Validation order

固定顺序：

```text
case envelope/schema
  -> operation/input discriminant
  -> declared type/schema
  -> encoding/Unicode
  -> lexical/typed value
  -> canonical payload/frame
  -> framing/collection invariants
  -> expected bytes/digest
```

Vector case 本身 schema/closure 非法属于 Conformance Harness validation failure，不产生上表 Shared Kernel error code，也不能作为被测实现的 expected invalid result。

## 11. Change governance

- 普通 CI 只读执行，不生成、不修改、不 bless。
- Generator 只输出 candidate tree/diff。
- Candidate 必须通过 schema/closure validation、人工 byte review、Python/Rust 两个独立实现。
- 修改既有 v1 case 的 expected bytes、digest 或 success/error classification必须发布 canonical encoding v2/vector root v2。
- 由 v1 既有规则唯一推导的新增 case可以加入 v1，但不得改变既有 `case_id`。
- Repository Service 必须直接发现并逐 case消费同一 vector root；可以复用 Shared Kernel Python package，不复制第三套 Python algorithm。

## 12. Classification 与验收

Module public：是。Persisted：Git normative fixture。Wire：JCS JSON + canonical JSONL；test-only。

验收：

- Vector-set 和每个 case 可离线 fail-closed 校验。
- Python、Rust、Repository consumer 具有完全相同 case ID coverage，zero skip。
- Valid case逐 bytes 比较；invalid case逐 stable code 比较。
- Python/Rust 是两份独立实现；Repository 直接消费但不要求第三份算法。
- Property/fuzz tests 只能补充，不替代 static vectors。
