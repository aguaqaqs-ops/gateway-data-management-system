# Canonical Row Hash compute fixtures (v1)

WP3 R2 fixture root for `gateway-compute-core` integration tests.

## Scope

- Independent from `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/`
- Arrow batches are built programmatically in Rust tests (`gateway-compute-core/tests/`)
- Case metadata for A/B/C classification is documented here; executable coverage lives in integration tests

## Categories

| Class | Meaning | Example codes |
| --- | --- | --- |
| A | Schema passes; canonical value boundary | `CANONICAL_VALUE_INVALID` |
| B | Arrow legal but schema/type conflict | `ARROW_SCHEMA_MISMATCH`, `ARROW_TYPE_UNSUPPORTED` |
| C | Stream import failure | `ARROW_STREAM_IMPORT_FAILED` |

## Covered in R2 tests (post-audit remediation)

Integration suites:

| File | Focus |
| --- | --- |
| `tests/canonical_row_hash.rs` | Core A/B/C, determinism, failure codes |
| `tests/decimal256.rs` | Decimal p=38/39/65, overflow, schema mismatch |
| `tests/matrix_kinds.rs` | BIT, float, temporal, anomaly, view/extension, duplicates, sort |
| `tests/matrix_widths.rs` | Signed/unsigned integer widths, null slots, 24-bit bounds |
| `tests/schema_reader.rs` | Zero-batch reader, batch schema mismatch, multi-batch |
| `tests/request_binding.rs` | Canonical name collision at parse |

Unit tests in `src/` cover decimal256 formatting, non-nullable null extract, digest binding, date civil bounds.

**Test counts:** 66 integration + 11 unit = 77 total (`gateway-compute-core`).

### R1 §6.2 kind matrix

All 15 semantic kinds have dedicated positive and/or negative coverage (not smoke-only).

### R1 §6.3 determinism families

- empty / zero-batch reader / multi-batch partition
- input row permutation + Arrow field order permutation
- duplicate row hashes retained
- serial byte-identical execution

## Deferred

- Corrupt Arrow IPC fixtures → WP4
- Scenario YAML / golden envelopes → WP5
