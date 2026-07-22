#![forbid(unsafe_code)]

mod support;

use gateway_compute_core::ComputeFailureCode;

use support::builders::{
    int8_batch, int16_batch, int32_batch, int64_batch, uint8_batch, uint16_batch, uint32_batch,
    uint64_batch,
};
use support::runner::{run_err, run_ok};

#[test]
fn signed_integer_width_positive_boundaries() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"signed-integer","bits":8}}]"#,
        vec![int8_batch("v", false, vec![Some(-128), Some(127)]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"signed-integer","bits":16}}]"#,
        vec![
            int16_batch("v", false, vec![Some(-32_768), Some(32_767)])
                .map_err(|e| e.to_string())?,
        ],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"signed-integer","bits":64}}]"#,
        vec![
            int64_batch("v", false, vec![Some(i64::MIN), Some(i64::MAX)])
                .map_err(|e| e.to_string())?,
        ],
    )?;
    Ok(())
}

#[test]
fn unsigned_integer_width_positive_boundaries() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"unsigned-integer","bits":8}}]"#,
        vec![uint8_batch("v", false, vec![Some(0), Some(255)]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"unsigned-integer","bits":16}}]"#,
        vec![uint16_batch("v", false, vec![Some(0), Some(65_535)]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"unsigned-integer","bits":24}}]"#,
        vec![uint32_batch("v", false, vec![Some(0), Some(16_777_215)]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"unsigned-integer","bits":64}}]"#,
        vec![uint64_batch("v", false, vec![Some(0), Some(u64::MAX)]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn signed_integer_null_slots_across_widths() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"signed-integer","bits":8}}]"#,
        vec![int8_batch("v", true, vec![None]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"signed-integer","bits":16}}]"#,
        vec![int16_batch("v", true, vec![None]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"signed-integer","bits":64}}]"#,
        vec![int64_batch("v", true, vec![None]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn unsigned_integer_null_slots_across_widths() -> Result<(), String> {
    run_ok(
        r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"unsigned-integer","bits":8}}]"#,
        vec![uint8_batch("v", true, vec![None]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"unsigned-integer","bits":16}}]"#,
        vec![uint16_batch("v", true, vec![None]).map_err(|e| e.to_string())?],
    )?;
    run_ok(
        r#"[{"name":"v","nullable":true,"semantic_type":{"kind":"unsigned-integer","bits":64}}]"#,
        vec![uint64_batch("v", true, vec![None]).map_err(|e| e.to_string())?],
    )?;
    Ok(())
}

#[test]
fn signed_integer_24bit_upper_overflow() -> Result<(), String> {
    let fields =
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"signed-integer","bits":24}}]"#;
    let failure = run_err(
        fields,
        vec![int32_batch("v", false, vec![Some(8_388_608)]).map_err(|e| e.to_string())?],
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::CanonicalValueInvalid,
    );
    Ok(())
}
