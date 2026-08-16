# Repository ENUM/SET golden corpus (v1)

Format freeze for P2-R6-EXT-W1 Stage B. Semantic owner: Repository Service.
Content bytes follow Shared Canonical Encoding v1 string / sequence rules; no new
scalar tags.

Authority:

- [Repository Service §10.1](../../../../../../docs/backend-vnext/refactoring/formal/contracts/repository-service.md)
- [Shared Canonical Encoding §3.2](../../../../../../docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md)
- [Correctness Golden and Fixture §2.1](../../../../../../docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md)
- [ADR 0013](../../../../../../docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md)

## Files

| File | Operations |
| --- | --- |
| `normalize.jsonl` | `normalize-sql-type` |
| `values.jsonl` | `encode-enum-value`, `encode-set-value` |
| `invalid.jsonl` | `reject-malformed-type`, `reject-illegal-value` |

## Case shape

Every line is one JSON object:

```text
case_id
case_schema_version = 1
operation
input
expected | expected_error
```

`case_id` 使用稳定 kebab 分段，例如 `normalize.enum.ascii-labels`。
valid case 固定完整结果；invalid case 固定 `expected_error.code`。
bytes 字段使用无 padding base64url。只比较最终 digest 不算通过。
普通 CI 不 bless。本目录含 Stage D 填入的完整 v1 case：Repository 消费全部
operation；Shared Kernel Python/Rust 只消费 `values.jsonl` 的 encode 操作。

## Operations

### `normalize-sql-type`

```json
{
  "input": {"data_type": "ENUM", "column_type": "enum('a','b')"},
  "expected": {"normalized_sql_type": "ENUM('a','b')"}
}
```

### `encode-enum-value`

`input.sql_type` 必须已是 normalized spelling。`input.value` 为
`{"kind":"null"}` 或 `{"kind":"string","text":"..."}`。
`expected.scalar_frame_base64url` 是 Shared Kernel string 或 null frame。

### `encode-set-value`

`input.value` 为 `{"kind":"null"}`、`{"kind":"set-members","members":["..."]}`
或 `{"kind":"set-text","text":"a,b"}`。
非 null SET 的 content 单元格就是 `expected.sequence_frame_base64url` 本身，不再
外包 scalar tag。空 SET 长度为 0。null 使用 `expected.scalar_frame_base64url`
（null tag），不得写成空 sequence。

### `reject-malformed-type`

`expected_error.code` 必须为 `SQL_TYPE_MALFORMED`。

### `reject-illegal-value`

`expected_error.code` 必须为 `SQL_VALUE_ILLEGAL`。
