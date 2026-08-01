use gateway_compute_core::{ComputeFailure, ComputeFailureCode};
use serde_json::Value;

pub fn assert_failure_code(failure: &ComputeFailure, expected: ComputeFailureCode) {
    assert_eq!(failure.code, expected, "unexpected failure code");
}

pub fn assert_envelope_fields(
    failure: &ComputeFailure,
    expected: ComputeFailureCode,
) -> Result<(), String> {
    let wire = failure
        .to_envelope_jcs()
        .map_err(|error| format!("{error:?}"))?;
    let value: Value =
        serde_json::from_slice(&wire).map_err(|error| format!("invalid envelope json: {error}"))?;
    let object = value
        .as_object()
        .ok_or_else(|| "envelope must be object".to_string())?;
    assert_eq!(
        object.get("code").and_then(Value::as_str),
        Some(expected.as_str())
    );
    assert!(object.get("message").and_then(Value::as_str).is_some());
    assert_eq!(object.len(), 2);
    Ok(())
}
