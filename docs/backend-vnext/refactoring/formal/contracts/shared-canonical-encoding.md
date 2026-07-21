# Shared Canonical Encoding Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 1 实现

Contract ID：`gateway-vnext.shared-canonical-encoding`

Owner：Shared Kernel

Canonical encoding version：`1`

Semantic version：`1.0.0`

## 1. 范围与版本轴

`canonical_encoding_version` 作为一个 bundle 同时固定 canonical JSON、typed scalar frame、identifier、row/collection framing 和 semantic digest。v1 不允许调用方混搭这些子层版本。Python Backend、Rust compute core 与 Repository Service 必须逐字节一致。

本 contract 不拥有 SQL parser 的 type alias/timezone policy、业务 anomaly reason、table rules、use-case error code 或 artifact content schema。

## 2. Canonical JSON

JSON-compatible DTO、manifest 和 digest payload 使用 RFC 8785 JCS。输入必须是 I-JSON：UTF-8、唯一 member name、合法 Unicode、有限 binary64 number。Property 按 JCS UTF-16 code unit 排序；array 保持原顺序；不输出空白，不执行 Unicode normalization。

JSON integer 限于 `[-(2^53)+1, (2^53)-1]`。`uint64`、高精度 decimal、binary 和 table temporal 必须使用 schema-declared string/typed representation。NaN、Infinity、duplicate key、lone surrogate、Unicode noncharacter 和 unknown field fail closed。Pretty JSON 在 equality/digest 前必须 schema validate 并转为 JCS bytes。

JCS 输入在严格 UTF-8 解码后必须是语法合法的 JSON text。语法非法（截断、非法 token、trailing garbage 等）稳定失败为 `CANONICAL_JCS_SYNTAX_INVALID`；不得映射为 `CANONICAL_INVALID_UNICODE`。Duplicate member、I-JSON number 越界与 non-finite 仍使用既有 JCS number/duplicate codes。

## 3. Typed scalar frame

```text
scalar_frame = tag:u8 || payload_length:minimal-ULEB128 || payload
```

ULEB128 必须最短；规范最大 payload length 为 `2^63-1`，实现可用更低资源上限。Unknown/reserved tag、truncation、overflow 和 non-minimal ULEB128 都失败。Frame 是 digest preimage，不是通用 public wire/storage format。

| Tag | Kind | Canonical payload |
| --- | --- | --- |
| `0x00` | null | empty |
| `0x01` | boolean | one byte `00`/`01` |
| `0x10` | signed integer | 8-byte big-endian two's complement |
| `0x11` | unsigned integer | 8-byte big-endian unsigned |
| `0x12` | decimal | canonical ASCII decimal |
| `0x13` | float32 | 4-byte IEEE-754 big-endian bits |
| `0x14` | float64 | 8-byte IEEE-754 big-endian bits |
| `0x20` | string | canonical valid UTF-8 bytes |
| `0x21` | binary/`BIT(n)` | raw bytes，保留 leading zero bits |
| `0x30` | date | `YYYY-MM-DD` |
| `0x31` | datetime | `YYYY-MM-DDTHH:MM:SS[.fraction]` |
| `0x32` | timestamp | `YYYY-MM-DDTHH:MM:SS[.fraction]Z` |
| `0x33` | time duration | `[-]HH:MM:SS[.fraction]` |
| `0x7f` | source literal anomaly | JCS anomaly envelope |

v1 tag 分区（fail-closed）：

```text
assigned tags     = table above
unassigned 0x00..=0x7F  -> CANONICAL_SCALAR_TAG_RESERVED
0x80..=0xFF             -> CANONICAL_SCALAR_TAG_UNKNOWN
```

其余 tag 在 v1 不得自行占用；实现不得发明未登记分区。

Integer 由 column schema 校验 width/signedness；`+`、leading zero 和 `-0` 归一为同一数值，越界失败。Decimal 禁止 exponent/`+`，删除冗余整数 leading zero 和小数 trailing zero，小于 1 时补整数 `0`，负零为 `0`；precision/scale 属于 schema digest，不进入 value payload。Float 按声明宽度 round-to-nearest ties-to-even；float32 先舍入为 binary32；负零变正零，subnormal 保留，NaN/Infinity 失败。

v1 owner-declared numeric width固定为：signed/unsigned integer `8 | 16 | 24 | 32 | 64` bits；MySQL decimal precision `1..=65`、scale `0..=30`且`scale <= precision`；`BIT(n)` width `1..=64`。范围依据[MySQL DECIMAL characteristics](https://dev.mysql.com/doc/refman/8.4/en/precision-math-decimal-characteristics.html)与[MySQL numeric type syntax](https://dev.mysql.com/doc/refman/8.4/en/numeric-type-syntax.html)。这些是logical declared-type校验边界；Arrow provider可表达的更宽物理类型不会自动扩大canonical logical range。

String 不 trim、case-fold 或 normalize；非法 UTF-8、surrogate/noncharacter 不可静默替换。Binary 原样保存。

`DATE/DATETIME` 是 civil value；`DATETIME` 不转 UTC。`TIMESTAMP` encoder 只接受已解析 UTC instant，不读取机器 timezone/tzdb。`TIME` 是可负、可超过 24 小时的 MySQL duration（上限 838 小时）；0–99 hours 使用两位，100–838 使用三位，negative zero 变正零。Fraction 最多六位、去尾零，全零则省略。zero/incomplete date、leap second 和越界值只能成为 owner 允许的 anomaly 或 hard failure。Application/operation timestamp 不使用 table scalar tag，其 public contract 使用 RFC 3339 UTC instant。

v1 anomaly envelope 是闭合 object，恰好包含以下四个字段且 `additionalProperties` 禁止：

| Field | Rule |
| --- | --- |
| `declared_type` | 完整 DeclaredType descriptor object（与 vector schema `declaredType` 同形），不得用裸字符串；须保留 integer bits、decimal precision/scale、BIT width。 |
| `raw_base64url` | 无 padding base64url；字符集合法、不含 `=`、长度可解码，且 decode 后再 encode 与原串逐字符相等。 |
| `raw_encoding` | 非空 Unicode 字符串。 |
| `reason` | 非空 Unicode 字符串；stable owner-defined reason。 |

整个 envelope 必须是严格 JSON-compatible tree（仅 `null` / `bool` / 有限 number / `string` / `array` / `object`；object key 必须是 string）。非法嵌套或宿主非 JSON 类型稳定失败为 `CANONICAL_ANOMALY_INVALID`。Raw bytes 是 SQL unquote/unescape 后、type coercion 前的 logical literal；原始 SQL token 由 SourcePackageArtifact 保存。扩展字段留给后续 canonical encoding / vector-schema 版本，v1 不得接受未知字段。

### 3.1 Logical literal grammar（语言中立）

`normalize-logical-literal` 的 UTF-8 / raw logical literal 在 type coercion 前必须满足本节 grammar。实现不得以宿主 `float()`、`isdigit()`、`\d` 或 locale-aware API 作为 grammar authority；必须使用显式 ASCII 规则。所有 digit 只能是 ASCII `0-9`；禁止任何 whitespace、underscore、全角数字或其他 Unicode Nd。

| Kind | UTF-8 literal 允许集 | Raw literal 允许集 | Lexical failure code |
| --- | --- | --- | --- |
| `null` | 恰好 `""` 或 `null` | 恰好空 bytes | `CANONICAL_TYPE_MISMATCH` |
| `boolean` | 恰好 `true` / `false` / `0` / `1`（大小写敏感） | 恰好单字节 `0x00` / `0x01` | `CANONICAL_TYPE_MISMATCH` |
| signed/unsigned integer | 可选前导 `+`/`-`（unsigned 禁止 `-`），其后为 ASCII digits；允许 leading zero；禁止空白与 `_` | 与 UTF-8 相同（先严格 UTF-8 解码） | 空/非 digit → `CANONICAL_TYPE_MISMATCH`；越界 → `CANONICAL_INTEGER_OUT_OF_RANGE` |
| `decimal` | 可选前导 `-`；整数与可选小数点分数；禁止 `+`、exponent、空白与 `_` | 同上 | `CANONICAL_DECIMAL_INVALID` |
| `float32` / `float64` | 见下方 float grammar | 同上 | grammar 失败 → `CANONICAL_TYPE_MISMATCH`；NaN/Infinity/overflow-to-nonfinite → `CANONICAL_FLOAT_NON_FINITE` |
| temporal kinds | 既有 textual form，且所有 digit 为 ASCII `0-9` | 同上 | `CANONICAL_TEMPORAL_INVALID` 或 `CANONICAL_TIME_OUT_OF_RANGE` |

Float grammar（整段匹配，无前后空白）：

```text
float_literal =
  [+-]? (
      [0-9]+ ('.' [0-9]*)?
    | '.' [0-9]+
  )
  ([eE][+-]?[0-9]+)?
```

Float 解析后按声明宽度 round-to-nearest ties-to-even。若舍入/packing 后变为非有限（含超出 binary32/binary64 有限范围），稳定失败为 `CANONICAL_FLOAT_NON_FINITE`；v1 不另增 float-range code。Integer/decimal/float 在解析前施加资源上限：digit 主体长度不得超过声明宽度所需最大十进制位数加上固定 leading-zero budget（实现固定为 16）；超长 → 对应 `TYPE_MISMATCH` / `DECIMAL_INVALID` / `TYPE_MISMATCH`。

Typed encoder 入口必须校验底层宿主值的精确运行时类型（例如 boolean 必须是语言布尔，不得接受整数 `1`）；失败映射 `CANONICAL_TYPE_MISMATCH`。

## 4. CanonicalIdentifier

Parser 先负责 identifier unquote。Shared Kernel 只把 ASCII `A-Z` 映射到 `a-z`；不 trim，不 Unicode case-fold/normalize。空值、非法 Unicode 和 canonical collision 失败。Row field 按 canonical identifier UTF-8 bytes 的 unsigned lexicographic order 排序；不得与 JCS UTF-16 property ordering 混用。

## 5. Digest 与 framing

Semantic digest：

```text
preimage = ASCII("gateway-vnext:<digest-kind>:v1\0") || canonical_payload
digest   = SHA256(preimage)
wire     = "sha256:" || lowercase_hex(digest)
```

`digest-kind` 使用 lower-kebab-case registry。组合 digest 使用 child raw 32-byte hash，不使用 wire hex。Raw blob integrity 仍是直接 SHA-256(raw bytes)，不加 semantic prefix；`raw-content` 与 `business-content` 永远分域，不能复用 DigestRef。

v1 已登记的基础与 Phase 1 executable-contract digest kind：

| Digest kind | Payload owner / purpose |
| --- | --- |
| `row` | Shared Kernel canonical row frame。 |
| `raw-content` | Shared Kernel unordered row-hash multiset。 |
| `collection-item` | Shared Kernel collection item framing。 |
| `vector-set` | Shared Kernel canonical-encoding vector closure。 |
| `table-schema` | Canonical Row Hash capability declared semantic schema。 |
| `scenario-input` | Conformance Harness scenario input projection/closure。 |
| `scenario-fixture` | Conformance Harness complete fixture projection/closure。 |

新 kind 必须由 payload semantic owner 提议、由 Shared Kernel登记；不得以未登记字符串临时计算正式 DigestRef。

```text
row_frame =
  ULEB128(field_count) +
  each field in canonical identifier order:
    ULEB128(name_length) + name_utf8 + scalar_frame

row_hash = SHA256(domain("row") + row_frame)

unordered_table_frame =
  ULEB128(row_count) + sorted(raw row_hash bytes)

raw_content_digest =
  SHA256(domain("raw-content") + unordered_table_frame)
```

Unordered table 对 field/input row order 不敏感，保留 duplicate row hashes。Ordered `no`/sequence 由 ordered owner 的 ordering digest 表达。

其中 `domain(kind)` 是本节 semantic prefix bytes。Collection framing 为：

```text
framed_item = ULEB128(item_length) + item_bytes
item_hash   = SHA256(domain("collection-item") + framed_item)

sequence_frame =
  ULEB128(item_count) + framed_item... in declared order

multiset_or_set_frame =
  ULEB128(item_count) + sorted(raw item_hash bytes)

keyed_collection_frame =
  ULEB128(entry_count) + entries sorted by key bytes:
    ULEB128(key_length) + key_bytes +
    ULEB128(value_length) + value_bytes
```

Collection owner 必须显式选择：

- `sequence`：count + length-framed items，保留顺序。
- `multiset`：排序 raw item hash，保留重复。
- `set`：同上，但重复 item hash 失败。
- `keyed-collection`：按 key bytes 的 unsigned lexicographic order 排序 length-framed key/value，重复 key 失败。

Keyed collection 的 key/value 以及 sequence/multiset/set 的 item 均为 **opaque bytes**：

- Semantic owner 必须在调用 Shared Kernel 之前完成所需 canonicalization。
- Shared Kernel 不执行 CanonicalIdentifier fold、JCS、Unicode 校验或其他 normalization，也不要求 key/value/item 为合法 UTF-8。
- 空 key、空 value、空 item 默认允许；若业务 owner 禁止，应在调用前验证。
- 判重与排序只比较原始 key bytes（或 item hash），不做语义解释。

Collection framing 本身不产生 collection-level `DigestRef`。若 owner 需要对 `collection_frame` 做 semantic digest，必须另行调用 `semantic_digest`，使用 owner 已登记的 `DigestKind`，并以确定的 frame bytes 作为 payload（向量中应引用或复制该 frame，而不是在验证时临时调用 `encode_collection` 生成 digest 输入）。

Serializer 不根据宿主语言容器类型猜测 semantics。

## 6. Normative vectors

唯一跨语言向量根：

```text
vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/
  vector-set.json
  jcs.jsonl
  scalar.jsonl
  digest.jsonl
  invalid.jsonl
```

`vector-set.json`、四类 JSONL case、test-only logical/typed scalar representation、closure digest和stable invalid code的唯一 schema authority是 [Canonical Encoding Normative Vector Schema](canonical-encoding-normative-vector-schema.md)。Case 使用稳定 `case_id`；valid case固定canonical bytes/digest，invalid case只固定stable error code。Python、Rust、Repository必须直接消费同一向量并比较完整bytes；只比较最终digest不算通过。

Test-only scalar representation不得成为production FFI contract。Canonical Row Hash capability如何把Arrow physical value映射到本文logical scalar，由其owning compute-boundary contract版本化；Arrow metadata不得反向改写本文语义。

普通 CI 不生成或 bless vectors。Generator 只产 candidate diff；关键 bytes 经人工审查及至少两个独立实现验证。v1 已有 case 的 bytes、digest 或 success/error classification 改变必须发布 v2；由既有规则唯一推导的新增 case可保留 v1。

## 7. Classification

Module public：是。Persisted：作为 version/digest marker 被持久化。Wire：JCS/Arrow/Parquet owner schema；scalar frame 本身为 none。

任一规范 byte 改变都升级 `canonical_encoding_version` 并说明既有 artifact/cache/digest 的失效或重算策略。Provider implementation version 不参与 semantic digest。

## 8. 验收标准

- Python、Rust、Repository 逐字节通过全部 valid/invalid normative vectors。
- 覆盖 JCS 非 BMP ordering、数值 extrema、Unicode/binary、temporal/anomaly、row/collection、ULEB128 invalid 和 digest domain separation。
- Property/fuzz tests 补充而不替代静态 vectors。
- 同一 logical input 在不同语言、串并行模式和进程重启后得到相同 bytes/DigestRef。
- 公共 API 不暴露 scalar frame 通用 decoder，owner wire schema 继续校验资源限制。

## 9. 关联文档

- [Canonical Encoding Normative Vector Schema](canonical-encoding-normative-vector-schema.md)
- [Canonical Row Hash Compute Boundary](canonical-row-hash-compute-boundary.md)
- [Fixture Oracle and Conformance](fixture-oracle-and-conformance.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [ADR 0005](../adr/0005-shared-canonical-encoding.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
