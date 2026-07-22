#![forbid(unsafe_code)]

mod support;

use std::collections::HashMap;
use std::sync::Arc;

use arrow_array::{BooleanArray, StringArray};
use arrow_schema::{DataType, Field, TimeUnit};
use gateway_compute_core::ComputeFailureCode;

use support::builders::{
    batch_with_fields, binary_batch, date32_batch, datetime_batch, float32_batch, float64_batch,
    string_batch, timestamp_batch,
};
use support::runner::{run_err, run_ok};

#[test]
fn bit_width_8_and_9_positive() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"bit","bit_width":8}}]"#,
        vec![binary_batch("v", false, vec![Some(&[0xAB])]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"bit","bit_width":9}}]"#,
        vec![binary_batch("v", false, vec![Some(&[0x01, 0xFF])]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn bit_wrong_byte_length_is_canonical_invalid() -> Result<(), String> {
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"bit","bit_width":8}}]"#,
        vec![binary_batch("v", false, vec![Some(&[])]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}

#[test]
fn bit_nonzero_high_bits_is_canonical_invalid() -> Result<(), String> {
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"bit","bit_width":9}}]"#,
        vec![binary_batch("v", false, vec![Some(&[0x02, 0x00])]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}

#[test]
fn bit_width_1_and_64() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"bit","bit_width":1}}]"#;
    run_ok(
        fields,
        vec![binary_batch("v", false, vec![Some(&[0b0000_0001])]).map_err(|e| e.to_string())?],
    )?;

    let fields64 =
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"bit","bit_width":64}}]"#;
    run_ok(
        fields64,
        vec![
            binary_batch("v", false, vec![Some(&[0, 0, 0, 0, 0, 0, 0, 1])])
                .map_err(|e| e.to_string())?,
        ],
    )?;
    Ok(())
}

#[test]
fn bit_null_slot() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"bit","bit_width":8}}]"#,
        vec![binary_batch("v", true, vec![None]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn float32_positive_zero_subnormal_and_negative_zero() -> Result<(), String> {
    let subnormal = f32::from_bits(1);
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"float32"}}]"#,
        vec![
            float32_batch("v", false, vec![Some(0.0), Some(-0.0), Some(subnormal)])
                .map_err(|e| e.to_string())?,
        ],
    )?;
    Ok(())
}

#[test]
fn float64_negative_zero() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"float64"}}]"#,
        vec![float64_batch("v", false, vec![Some(-0.0)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn float32_infinity_is_canonical_invalid() -> Result<(), String> {
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"float32"}}]"#,
        vec![float32_batch("v", false, vec![Some(f32::INFINITY)]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}

#[test]
fn date_year_zero_is_canonical_invalid() -> Result<(), String> {
    let failure_day = (-800_000..0).find(|days| {
        let Ok(batch) = date32_batch("v", false, vec![Some(*days)]) else {
            return false;
        };
        matches!(
            run_err(
                r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"date"}}]"#,
                vec![batch],
            ),
            Ok(failure) if failure.code == ComputeFailureCode::CanonicalValueInvalid
        )
    });
    let failure_day =
        failure_day.ok_or_else(|| "no date32 day produced CANONICAL_VALUE_INVALID".to_string())?;
    assert!(failure_day < 0);
    Ok(())
}

#[test]
fn datetime_positive_micros() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"datetime"}}]"#,
        vec![datetime_batch("v", false, vec![Some(0)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn timestamp_positive_utc() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"timestamp"}}]"#,
        vec![timestamp_batch("v", false, vec![Some(0)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn datetime_out_of_range_micros() -> Result<(), String> {
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"datetime"}}]"#,
        vec![datetime_batch("v", false, vec![Some(i64::MAX)]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}

#[test]
fn timestamp_out_of_range_micros() -> Result<(), String> {
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"timestamp"}}]"#,
        vec![timestamp_batch("v", false, vec![Some(i64::MAX)]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}

#[test]
fn time_duration_upper_bound_ok() -> Result<(), String> {
    let micros = 838_i64 * 3_600_000_000 + 59 * 60_000_000 + 59_000_000 + 999_999;
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"time-duration"}}]"#,
        vec![
            support::builders::duration_batch("v", false, vec![Some(micros)])
                .map_err(|e| e.to_string())?,
        ],
    )?;
    Ok(())
}

#[test]
fn anomaly_valid_envelope() -> Result<(), String> {
    let envelope = br#"{"declared_type":{"kind":"date"},"raw_base64url":"YmFk","raw_encoding":"utf8","reason":"owner-reason"}"#;
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"source-literal-anomaly"}}]"#,
        vec![binary_batch("v", false, vec![Some(envelope)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn anomaly_unknown_root_field_fail_closed() -> Result<(), String> {
    let envelope = br#"{"declared_type":{"kind":"date"},"raw_base64url":"YmFk","raw_encoding":"utf8","reason":"owner-reason","extra":1}"#;
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"source-literal-anomaly"}}]"#,
        vec![binary_batch("v", false, vec![Some(envelope)]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}

#[test]
fn anomaly_unknown_declared_type_field_fail_closed() -> Result<(), String> {
    let envelope = br#"{"declared_type":{"kind":"date","extra":1},"raw_base64url":"YmFk","raw_encoding":"utf8","reason":"owner-reason"}"#;
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"source-literal-anomaly"}}]"#,
        vec![binary_batch("v", false, vec![Some(envelope)]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}

#[test]
fn duplicate_row_hashes_retained() -> Result<(), String> {
    let output = run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]"#,
        vec![string_batch("v", false, vec![Some("x"), Some("x")]).map_err(|e| e.to_string())?],
    )?;
    if output.output_batches[0].num_rows() != 2 {
        return Err("expected duplicate hashes retained".to_string());
    }
    let bytes = row_hash_column_bytes(&output.output_batches[0])?;
    if bytes[0] != bytes[1] {
        return Err("duplicate rows should produce identical hashes".to_string());
    }
    Ok(())
}

#[test]
fn utf8_view_type_is_unsupported() -> Result<(), String> {
    let array = arrow_array::StringViewArray::from(vec![Some("x")]);
    let batch = batch_with_fields(
        vec![Field::new("v", DataType::Utf8View, false)],
        vec![Arc::new(array)],
    )
    .map_err(|e| e.to_string())?;
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]"#,
        vec![batch],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::ArrowTypeUnsupported,
    );
    Ok(())
}

#[test]
fn extension_metadata_is_unsupported() -> Result<(), String> {
    let mut metadata = HashMap::new();
    metadata.insert("ARROW:extension:name".to_string(), "uuid".to_string());
    let field = Field::new("v", DataType::Utf8, false).with_metadata(metadata);
    let batch = batch_with_fields(
        vec![field],
        vec![Arc::new(StringArray::from(vec![Some("x")]))],
    )
    .map_err(|e| e.to_string())?;
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]"#,
        vec![batch],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::ArrowTypeUnsupported,
    );
    Ok(())
}

#[test]
fn schema_metadata_mismatch_between_batches() -> Result<(), String> {
    let field_a = Field::new("v", DataType::Boolean, false);
    let mut metadata = HashMap::new();
    metadata.insert("note".to_string(), "a".to_string());
    let field_b = Field::new("v", DataType::Boolean, false).with_metadata(metadata);
    let batch_a = batch_with_fields(
        vec![field_a],
        vec![Arc::new(BooleanArray::from(vec![Some(true)]))],
    )
    .map_err(|e| e.to_string())?;
    let batch_b = batch_with_fields(
        vec![field_b],
        vec![Arc::new(BooleanArray::from(vec![Some(false)]))],
    )
    .map_err(|e| e.to_string())?;
    let reader = support::batch_reader::VecBatchReader::new(vec![batch_a, batch_b]).into_boxed();
    let failure = support::runner::run_err_reader(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]"#,
        reader,
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::ArrowSchemaMismatch,
    );
    Ok(())
}

#[test]
fn unsupported_precedes_field_count_mismatch() -> Result<(), String> {
    let array = arrow_array::LargeStringArray::from(vec![Some("x")]);
    let batch = batch_with_fields(
        vec![Field::new("v", DataType::LargeUtf8, false)],
        vec![Arc::new(array)],
    )
    .map_err(|e| e.to_string())?;
    let failure = run_err(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}},
           {"name":"w","nullable":false,"semantic_type":{"kind":"string"}}]"#,
        vec![batch],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::ArrowTypeUnsupported,
    );
    Ok(())
}

#[test]
fn nullable_null_slots_across_semantic_kinds() -> Result<(), String> {
    run_ok(
        r#"[{"name":"b","nullable":true,"semantic_type":{"kind":"boolean"}},
           {"name":"s","nullable":true,"semantic_type":{"kind":"string"}},
           {"name":"i","nullable":true,"semantic_type":{"kind":"signed-integer","bits":32}},
           {"name":"d","nullable":true,"semantic_type":{"kind":"decimal","precision":5,"scale":2}},
           {"name":"bit","nullable":true,"semantic_type":{"kind":"bit","bit_width":8}},
           {"name":"dt","nullable":true,"semantic_type":{"kind":"date"}},
           {"name":"dur","nullable":true,"semantic_type":{"kind":"time-duration"}}]"#,
        vec![
            support::builders::batch_with_fields(
                vec![
                    Field::new("b", DataType::Boolean, true),
                    Field::new("s", DataType::Utf8, true),
                    Field::new("i", DataType::Int32, true),
                    Field::new("d", DataType::Decimal128(5, 2), true),
                    Field::new("bit", DataType::Binary, true),
                    Field::new("dt", DataType::Date32, true),
                    Field::new("dur", DataType::Duration(TimeUnit::Microsecond), true),
                ],
                vec![
                    Arc::new(BooleanArray::from(vec![None])),
                    Arc::new(StringArray::from(vec![None::<&str>])),
                    Arc::new(arrow_array::Int32Array::from(vec![None])),
                    Arc::new(
                        arrow_array::Decimal128Array::from(vec![None])
                            .with_precision_and_scale(5, 2)
                            .map_err(|e| e.to_string())?,
                    ),
                    Arc::new(arrow_array::BinaryArray::from(vec![None::<&[u8]>])),
                    Arc::new(arrow_array::Date32Array::from(vec![None])),
                    Arc::new(arrow_array::DurationMicrosecondArray::from(vec![None])),
                ],
            )
            .map_err(|e| e.to_string())?,
        ],
    )?;
    Ok(())
}

#[test]
fn output_row_hashes_sorted_unsigned_lexicographic() -> Result<(), String> {
    let output = run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]"#,
        vec![
            string_batch(
                "v",
                false,
                vec![Some("charlie"), Some("alpha"), Some("bravo")],
            )
            .map_err(|e| e.to_string())?,
        ],
    )?;
    let hashes = row_hash_column_bytes(&output.output_batches[0])?;
    let mut sorted = hashes.clone();
    sorted.sort();
    if hashes != sorted {
        return Err("output row hashes are not unsigned lexicographic sorted".to_string());
    }
    let schema = output.output_batches[0].schema();
    assert_eq!(schema.field(0).name(), "row_hash");
    assert_eq!(schema.field(0).data_type(), &DataType::FixedSizeBinary(32));
    assert!(!schema.field(0).is_nullable());
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
