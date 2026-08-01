#![forbid(unsafe_code)]

mod support;

use gateway_compute_core::{ComputeFailureCode, parse_request};

#[test]
fn canonical_name_collision_rejected_at_parse() -> Result<(), String> {
    let request = br#"{"arrow_mapping_version":1,"boundary_version":2,"canonical_encoding_version":1,"declared_fields":[{"name":"A","nullable":false,"semantic_type":{"kind":"boolean"}},{"name":"a","nullable":false,"semantic_type":{"kind":"boolean"}}]}"#;
    match parse_request(request) {
        Err(error) if error.code == ComputeFailureCode::CanonicalValueInvalid => Ok(()),
        other => Err(format!("expected collision rejection, got {other:?}")),
    }
}
