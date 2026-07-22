#![forbid(unsafe_code)]
#![allow(clippy::assertions_on_constants)]

mod support;

use std::sync::Arc;

use arrow_buffer::i256;
use arrow_schema::{DataType, Field};
use gateway_compute_core::ComputeFailureCode;

use support::builders::{decimal128_batch, decimal256_batch};
use support::runner::{run_err, run_ok};

fn parse_i256(text: &str) -> i256 {
    match i256::from_string(text) {
        Some(value) => value,
        None => {
            assert!(false, "i256 parse failed for {text}");
            i256::ZERO
        }
    }
}

#[test]
fn decimal_p38_boundary() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"decimal","precision":38,"scale":2}}]"#;
    let max = (1_i128 << 126) - 1;
    run_ok(
        fields,
        vec![decimal128_batch("v", false, 38, 2, vec![Some(max)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn decimal_p39_positive_large_unscaled() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"decimal","precision":39,"scale":0}}]"#;
    let value = parse_i256("100000000000000000000000000000000000000");
    run_ok(
        fields,
        vec![decimal256_batch("v", false, 39, 0, vec![Some(value)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn decimal_p65_s30_negative() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"decimal","precision":65,"scale":30}}]"#;
    let value = -parse_i256("123456789012345678901234567890");
    run_ok(
        fields,
        vec![decimal256_batch("v", false, 65, 30, vec![Some(value)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn decimal_precision_overflow_is_canonical_invalid() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"decimal","precision":5,"scale":2}}]"#;
    let failure = run_err(
        fields,
        vec![decimal128_batch("v", false, 5, 2, vec![Some(9_999_999)]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}

#[test]
fn decimal256_would_have_silently_zeroed_before_fix() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"decimal","precision":39,"scale":0}}]"#;
    let value = parse_i256("340282366920938463463374607431768211456");
    let output = run_ok(
        fields,
        vec![decimal256_batch("v", false, 39, 0, vec![Some(value)]).map_err(|e| e.to_string())?],
    )?;
    if output.output_batches[0].num_rows() != 1 {
        return Err("expected one row hash".to_string());
    }
    Ok(())
}

#[test]
fn decimal_nullable_null_slot() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"decimal","precision":5,"scale":2}}]"#;
    run_ok(
        fields,
        vec![decimal128_batch("v", true, 5, 2, vec![None]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn decimal_schema_mismatch_precision() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"decimal","precision":5,"scale":2}}]"#;
    let batch = support::builders::batch_with_fields(
        vec![Field::new("v", DataType::Decimal128(6, 2), false)],
        vec![Arc::new(
            arrow_array::Decimal128Array::from(vec![Some(100_i128)])
                .with_precision_and_scale(6, 2)
                .map_err(|e| e.to_string())?,
        )],
    )
    .map_err(|e| e.to_string())?;
    let failure = run_err(fields, vec![batch])?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::ArrowSchemaMismatch,
    );
    Ok(())
}

#[test]
fn decimal256_i256_min_is_canonical_invalid() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"decimal","precision":65,"scale":0}}]"#;
    let failure = run_err(
        fields,
        vec![
            decimal256_batch("v", false, 65, 0, vec![Some(i256::MIN)])
                .map_err(|e| e.to_string())?,
        ],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}
