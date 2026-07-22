#![forbid(unsafe_code)]

mod support;

use gateway_compute_core::{ComputeFailureCode, parse_request};

#[test]
fn canonical_name_collision_rejected_at_parse() -> Result<(), String> {
    let request = br#"{"request_schema_version":1,"contract_binding":{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary","semantic_version":"1.0.0"},"canonical_encoding_version":1,"arrow_mapping_schema_version":1,"declared_table_schema":{"fields":[{"name":"A","nullable":false,"semantic_type":{"kind":"boolean"}},{"name":"a","nullable":false,"semantic_type":{"kind":"boolean"}}]}}"#;
    match parse_request(request) {
        Err(error) if error.code == ComputeFailureCode::CanonicalValueInvalid => Ok(()),
        other => Err(format!("expected collision rejection, got {other:?}")),
    }
}
