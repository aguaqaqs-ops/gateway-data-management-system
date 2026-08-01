#![forbid(unsafe_code)]

mod support;

use std::sync::Arc;

use arrow_schema::{DataType, Field, Schema, TimeUnit};
use gateway_compute_core::{ComputeFailureCode, canonical_row_hashes_v2, parse_request};

use support::assert_envelope::{assert_envelope_fields, assert_failure_code};
use support::batch_reader::VecBatchReader;
use support::builders::{
    batch_with_fields, boolean_batch, duration_batch, empty_schema_batch, float64_batch,
    int8_batch, int32_batch, null_kind_batch, reorder_fields, string_batch, timestamp_batch,
    uint32_batch,
};
use support::error_reader::ErrorBatchReader;
use support::request::{minimal_request, pretty_request};
use support::runner::{run_err, run_ok};

#[test]
fn mixed_scalar_golden_direct_owner_path() -> Result<(), String> {
    let fields = r#"[
      {"name":"z_label","nullable":true,"semantic_type":{"kind":"string"}},
      {"name":"a_id","nullable":false,"semantic_type":{"kind":"signed-integer","bits":32}},
      {"name":"m_flag","nullable":true,"semantic_type":{"kind":"boolean"}},
      {"name":"amount","nullable":false,"semantic_type":{"kind":"decimal","precision":10,"scale":2}}
    ]"#;
    let batch = batch_with_fields(
        vec![
            Field::new("z_label", DataType::Utf8, true),
            Field::new("a_id", DataType::Int32, false),
            Field::new("m_flag", DataType::Boolean, true),
            Field::new("amount", DataType::Decimal128(10, 2), false),
        ],
        vec![
            Arc::new(StringArray::from(vec![
                Some("beta"),
                Some("alpha"),
                Some("beta"),
            ])),
            Arc::new(Int32Array::from(vec![Some(2), Some(1), Some(2)])),
            Arc::new(BooleanArray::from(vec![Some(true), None, Some(true)])),
            Arc::new(
                Decimal128Array::from(vec![Some(1_250), Some(-300), Some(1_250)])
                    .with_precision_and_scale(10, 2)
                    .map_err(|error| error.to_string())?,
            ),
        ],
    )
    .map_err(|error| error.to_string())?;
    let output = run_ok(fields, vec![batch])?;

    let expected_path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../fixtures/golden/canonical-row-hash/mixed-scalars/expected.json"
    );
    let expected: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(expected_path).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;
    let result: serde_json::Value =
        serde_json::from_slice(&output.result_jcs).map_err(|error| error.to_string())?;
    for key in ["row_count", "raw_content_digest", "table_schema_digest"] {
        if result.get(key) != expected.get(key) {
            return Err(format!("{key} differs from mixed scalar golden"));
        }
    }
    let actual_hashes = row_hash_column_bytes(&output.output_batches[0])?
        .into_iter()
        .map(|bytes| {
            bytes
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>()
        })
        .collect::<Vec<_>>();
    let expected_hashes = expected["sorted_row_hashes_hex"]
        .as_array()
        .ok_or_else(|| "expected sorted_row_hashes_hex array".to_string())?
        .iter()
        .map(|value| {
            value
                .as_str()
                .ok_or_else(|| "expected hash string".to_string())
                .map(str::to_owned)
        })
        .collect::<Result<Vec<_>, _>>()?;
    if actual_hashes != expected_hashes {
        return Err("row hashes differ from mixed scalar golden".to_string());
    }
    Ok(())
}

#[test]
fn empty_zero_field_table_succeeds() -> Result<(), String> {
    let output = run_ok(
        "[]",
        vec![empty_schema_batch(&[]).map_err(|e| e.to_string())?],
    )?;
    assert_eq!(output.output_batches[0].num_rows(), 0);
    assert!(String::from_utf8_lossy(&output.result_jcs).contains("\"row_count\":\"0\""));
    Ok(())
}

#[test]
fn boolean_positive_and_null_slot() -> Result<(), String> {
    let fields = r#"[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]"#;
    let batch = boolean_batch("flag", true, vec![Some(true), None, Some(false)])
        .map_err(|e| e.to_string())?;
    let output = run_ok(fields, vec![batch])?;
    assert_eq!(output.output_batches[0].num_rows(), 3);
    Ok(())
}

#[test]
fn signed_integer_24bit_boundary_cases() -> Result<(), String> {
    let fields =
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"signed-integer","bits":24}}]"#;
    let ok_batch = int32_batch("v", false, vec![Some(-8_388_608), Some(8_388_607)])
        .map_err(|e| e.to_string())?;
    run_ok(fields, vec![ok_batch])?;

    let bad_low = int32_batch("v", false, vec![Some(-8_388_609)]).map_err(|e| e.to_string())?;
    let failure = run_err(fields, vec![bad_low])?;
    assert_failure_code(&failure, ComputeFailureCode::CanonicalValueInvalid);

    let bad_high = int32_batch("v", false, vec![Some(8_388_608)]).map_err(|e| e.to_string())?;
    let failure = run_err(fields, vec![bad_high])?;
    assert_failure_code(&failure, ComputeFailureCode::CanonicalValueInvalid);
    Ok(())
}

#[test]
fn unsigned_integer_24bit_max_is_valid() -> Result<(), String> {
    let fields =
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"unsigned-integer","bits":24}}]"#;
    run_ok(
        fields,
        vec![uint32_batch("v", false, vec![Some(16_777_215)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn unsigned_integer_24bit_overflow_is_canonical_invalid() -> Result<(), String> {
    let fields =
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"unsigned-integer","bits":24}}]"#;
    let failure = run_err(
        fields,
        vec![uint32_batch("v", false, vec![Some(16_777_216)]).map_err(|e| e.to_string())?],
    )?;
    assert_failure_code(&failure, ComputeFailureCode::CanonicalValueInvalid);
    Ok(())
}

#[test]
fn float_nonfinite_is_canonical_invalid() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"float64"}}]"#;
    let failure = run_err(
        fields,
        vec![float64_batch("v", false, vec![Some(f64::NAN)]).map_err(|e| e.to_string())?],
    )?;
    assert_failure_code(&failure, ComputeFailureCode::CanonicalValueInvalid);
    Ok(())
}

#[test]
fn schema_mismatch_int8_vs_boolean() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]"#;
    let failure = run_err(
        fields,
        vec![int8_batch("v", false, vec![Some(1)]).map_err(|e| e.to_string())?],
    )?;
    assert_failure_code(&failure, ComputeFailureCode::ArrowSchemaMismatch);
    assert_envelope_fields(&failure, ComputeFailureCode::ArrowSchemaMismatch)?;
    Ok(())
}

#[test]
fn unsupported_large_utf8_precedes_mismatch() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"binary"}}]"#;
    let array = arrow_array::LargeStringArray::from(vec![Some("x")]);
    let batch = batch_with_fields(
        vec![Field::new("v", DataType::LargeUtf8, false)],
        vec![Arc::new(array)],
    )
    .map_err(|error| error.to_string())?;
    let failure = run_err(fields, vec![batch])?;
    assert_failure_code(&failure, ComputeFailureCode::ArrowTypeUnsupported);
    Ok(())
}

#[test]
fn mismatch_utf8_vs_binary() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"binary"}}]"#;
    let failure = run_err(
        fields,
        vec![string_batch("v", false, vec![Some("x")]).map_err(|e| e.to_string())?],
    )?;
    assert_failure_code(&failure, ComputeFailureCode::ArrowSchemaMismatch);
    Ok(())
}

#[test]
fn unsupported_non_utc_timestamp() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"timestamp"}}]"#;
    let array = arrow_array::TimestampMicrosecondArray::from(vec![Some(0_i64)])
        .with_timezone("America/New_York".to_string());
    let batch = batch_with_fields(
        vec![Field::new(
            "v",
            DataType::Timestamp(TimeUnit::Microsecond, Some("America/New_York".into())),
            false,
        )],
        vec![Arc::new(array)],
    )
    .map_err(|error| error.to_string())?;
    let failure = run_err(fields, vec![batch])?;
    assert_failure_code(&failure, ComputeFailureCode::ArrowTypeUnsupported);
    Ok(())
}

#[test]
fn mismatch_timestamp_utc_vs_datetime() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"datetime"}}]"#;
    let failure = run_err(
        fields,
        vec![timestamp_batch("v", false, vec![Some(0)]).map_err(|e| e.to_string())?],
    )?;
    assert_failure_code(&failure, ComputeFailureCode::ArrowSchemaMismatch);
    Ok(())
}

#[test]
fn null_kind_requires_null_physical_type() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"null"}}]"#;
    let failure = run_err(
        fields,
        vec![int32_batch("v", true, vec![None]).map_err(|e| e.to_string())?],
    )?;
    assert_failure_code(&failure, ComputeFailureCode::ArrowSchemaMismatch);
    Ok(())
}

#[test]
fn null_kind_positive() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"null"}}]"#;
    run_ok(
        fields,
        vec![null_kind_batch("v", 2).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn time_duration_out_of_range() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"time-duration"}}]"#;
    // 839 hours in microseconds
    let micros = 839_i64 * 3_600_000_000;
    let failure = run_err(
        fields,
        vec![duration_batch("v", false, vec![Some(micros)]).map_err(|e| e.to_string())?],
    )?;
    assert_failure_code(&failure, ComputeFailureCode::CanonicalValueInvalid);
    Ok(())
}

#[test]
fn stream_import_failure_on_next() -> Result<(), String> {
    let request =
        minimal_request(r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]"#)
            .map_err(|error| format!("{error:?}"))?;
    let schema = Arc::new(Schema::new(vec![Field::new("v", DataType::Boolean, false)]));
    let failure =
        match canonical_row_hashes_v2(&request, ErrorBatchReader::new(schema).into_boxed()) {
            Ok(_) => return Err("expected import failure".to_string()),
            Err(error) => error,
        };
    assert_failure_code(&failure, ComputeFailureCode::ArrowStreamImportFailed);
    Ok(())
}

#[test]
fn request_pretty_json_is_accepted() -> Result<(), String> {
    let request =
        pretty_request(r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]"#)
            .map_err(|error| format!("{error:?}"))?;
    let output = canonical_row_hashes_v2(
        &request,
        VecBatchReader::new(vec![
            boolean_batch("v", false, vec![Some(true)]).map_err(|e| e.to_string())?,
        ])
        .into_boxed(),
    )
    .map_err(|error| format!("{error:?}"))?;
    assert!(!output.result_jcs.is_empty());
    Ok(())
}

#[test]
fn input_row_permutation_preserves_digest() -> Result<(), String> {
    let fields = r#"[{"name":"a","nullable":false,"semantic_type":{"kind":"signed-integer","bits":32}},
           {"name":"b","nullable":false,"semantic_type":{"kind":"signed-integer","bits":32}}]"#;
    let batch_a = support::builders::batch_with_fields(
        vec![
            Field::new("a", DataType::Int32, false),
            Field::new("b", DataType::Int32, false),
        ],
        vec![
            Arc::new(Int32Array::from(vec![Some(1), Some(2)])),
            Arc::new(Int32Array::from(vec![Some(10), Some(20)])),
        ],
    )
    .map_err(|error| error.to_string())?;
    let batch_b = support::builders::batch_with_fields(
        vec![
            Field::new("a", DataType::Int32, false),
            Field::new("b", DataType::Int32, false),
        ],
        vec![
            Arc::new(Int32Array::from(vec![Some(2), Some(1)])),
            Arc::new(Int32Array::from(vec![Some(20), Some(10)])),
        ],
    )
    .map_err(|error| error.to_string())?;
    let out_a = run_ok(fields, vec![batch_a])?;
    let out_b = run_ok(fields, vec![batch_b])?;
    if out_a.result_jcs != out_b.result_jcs {
        return Err("row permutation changed digest".to_string());
    }
    Ok(())
}

#[test]
fn field_order_permutation_is_invariant() -> Result<(), String> {
    let fields = r#"[{"name":"a","nullable":false,"semantic_type":{"kind":"string"}},
           {"name":"b","nullable":false,"semantic_type":{"kind":"string"}}]"#;
    let batch = batch_with_fields(
        vec![
            Field::new("a", DataType::Utf8, false),
            Field::new("b", DataType::Utf8, false),
        ],
        vec![
            Arc::new(StringArray::from(vec![Some("x")])),
            Arc::new(StringArray::from(vec![Some("y")])),
        ],
    )
    .map_err(|error| error.to_string())?;
    let permuted = reorder_fields(&batch, &[1, 0]).map_err(|e| e.to_string())?;
    let out_a = run_ok(fields, vec![batch])?;
    let out_b = run_ok(fields, vec![permuted])?;
    if out_a.result_jcs != out_b.result_jcs {
        return Err("field permutation changed digest".to_string());
    }
    Ok(())
}

#[test]
fn serial_execution_is_byte_identical_single_batch() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]"#;
    let batch =
        string_batch("v", false, vec![Some("alpha"), Some("beta")]).map_err(|e| e.to_string())?;
    let first = run_ok(fields, vec![batch.clone()])?;
    let second = run_ok(fields, vec![batch])?;
    if first.result_jcs != second.result_jcs {
        return Err("result_jcs differ across serial runs".to_string());
    }
    let first_bytes = row_hash_column_bytes(&first.output_batches[0])?;
    let second_bytes = row_hash_column_bytes(&second.output_batches[0])?;
    if first_bytes != second_bytes {
        return Err("row hash column differs across serial runs".to_string());
    }
    Ok(())
}

#[test]
fn serial_execution_is_byte_identical_multi_batch() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]"#;
    let batches = vec![
        string_batch("v", false, vec![Some("alpha")]).map_err(|e| e.to_string())?,
        string_batch("v", false, vec![Some("beta"), Some("gamma")]).map_err(|e| e.to_string())?,
    ];
    let first = run_ok(fields, batches.clone())?;
    let second = run_ok(fields, batches)?;
    if first.result_jcs != second.result_jcs {
        return Err("multi-batch result_jcs differ across serial runs".to_string());
    }
    let first_bytes = row_hash_column_bytes(&first.output_batches[0])?;
    let second_bytes = row_hash_column_bytes(&second.output_batches[0])?;
    if first_bytes != second_bytes {
        return Err("multi-batch row hash column differs across serial runs".to_string());
    }
    Ok(())
}

#[test]
fn failure_codes_for_request_versions() -> Result<(), String> {
    let bad_boundary = br#"{"arrow_mapping_version":1,"boundary_version":1,"canonical_encoding_version":1,"declared_fields":[]}"#;
    match parse_request(bad_boundary) {
        Err(error) if error.code == ComputeFailureCode::ComputeBoundaryVersionUnsupported => {}
        other => return Err(format!("unexpected boundary parse result: {other:?}")),
    }

    let bad_canonical = br#"{"arrow_mapping_version":1,"boundary_version":2,"canonical_encoding_version":2,"declared_fields":[]}"#;
    match parse_request(bad_canonical) {
        Err(error) if error.code == ComputeFailureCode::ComputeCanonicalVersionUnsupported => {}
        other => return Err(format!("unexpected canonical parse result: {other:?}")),
    }

    let bad_mapping = br#"{"arrow_mapping_version":2,"boundary_version":2,"canonical_encoding_version":1,"declared_fields":[]}"#;
    match parse_request(bad_mapping) {
        Err(error) if error.code == ComputeFailureCode::ComputeArrowMappingVersionUnsupported => {}
        other => return Err(format!("unexpected mapping parse result: {other:?}")),
    }

    let bad_schema = br#"{"arrow_mapping_version":1,"boundary_version":2,"canonical_encoding_version":1,"declared_fields":[],"unknown":1}"#;
    match parse_request(bad_schema) {
        Err(error) if error.code == ComputeFailureCode::ComputeRequestSchemaInvalid => {}
        other => return Err(format!("unexpected schema parse result: {other:?}")),
    }
    Ok(())
}

#[test]
fn multi_kind_matrix_smoke() -> Result<(), String> {
    let fields = r#"[
      {"name":"b","nullable":true,"semantic_type":{"kind":"boolean"}},
      {"name":"i","nullable":false,"semantic_type":{"kind":"signed-integer","bits":32}},
      {"name":"u","nullable":false,"semantic_type":{"kind":"unsigned-integer","bits":32}},
      {"name":"s","nullable":false,"semantic_type":{"kind":"string"}},
      {"name":"bin","nullable":false,"semantic_type":{"kind":"binary"}},
      {"name":"d","nullable":false,"semantic_type":{"kind":"decimal","precision":5,"scale":2}},
      {"name":"f32","nullable":false,"semantic_type":{"kind":"float32"}},
      {"name":"dt","nullable":false,"semantic_type":{"kind":"date"}},
      {"name":"dur","nullable":false,"semantic_type":{"kind":"time-duration"}}
    ]"#;
    let batch = batch_with_fields(
        vec![
            Field::new("b", DataType::Boolean, true),
            Field::new("i", DataType::Int32, false),
            Field::new("u", DataType::UInt32, false),
            Field::new("s", DataType::Utf8, false),
            Field::new("bin", DataType::Binary, false),
            Field::new("d", DataType::Decimal128(5, 2), false),
            Field::new("f32", DataType::Float32, false),
            Field::new("dt", DataType::Date32, false),
            Field::new("dur", DataType::Duration(TimeUnit::Microsecond), false),
        ],
        vec![
            Arc::new(BooleanArray::from(vec![Some(true)])),
            Arc::new(Int32Array::from(vec![Some(42)])),
            Arc::new(UInt32Array::from(vec![Some(7)])),
            Arc::new(StringArray::from(vec![Some("hi")])),
            Arc::new(BinaryArray::from(vec![Some(b"\x01\x02".as_slice())])),
            Arc::new(
                Decimal128Array::from(vec![Some(12_345_i128)])
                    .with_precision_and_scale(5, 2)
                    .map_err(|error| error.to_string())?,
            ),
            Arc::new(Float32Array::from(vec![Some(1.5)])),
            Arc::new(Date32Array::from(vec![Some(0)])),
            Arc::new(DurationMicrosecondArray::from(vec![Some(1_000_000)])),
        ],
    )
    .map_err(|error| error.to_string())?;
    run_ok(fields, vec![batch])?;
    Ok(())
}

fn row_hash_column_bytes(batch: &arrow_array::RecordBatch) -> Result<Vec<Vec<u8>>, String> {
    use arrow_array::Array;
    let array = batch
        .column(0)
        .as_any()
        .downcast_ref::<arrow_array::FixedSizeBinaryArray>()
        .ok_or_else(|| "expected fixed size binary output".to_string())?;
    let mut out = Vec::with_capacity(array.len());
    for row in 0..array.len() {
        out.push(array.value(row).to_vec());
    }
    Ok(out)
}

use arrow_array::{
    BinaryArray, BooleanArray, Date32Array, Decimal128Array, DurationMicrosecondArray,
    Float32Array, Int32Array, StringArray, UInt32Array,
};
