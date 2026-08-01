use gateway_compute_core::{ComputeFailure, ParsedRequest, parse_request};

pub fn minimal_request(fields_json: &str) -> Result<ParsedRequest, ComputeFailure> {
    let request = format!(
        r#"{{
  "boundary_version": 2,
  "canonical_encoding_version": 1,
  "arrow_mapping_version": 1,
  "declared_fields": {fields_json}
}}"#
    );
    parse_request(request.as_bytes())
}

pub fn pretty_request(fields_json: &str) -> Result<ParsedRequest, ComputeFailure> {
    let request = format!(
        r#"{{
  "declared_fields" : {fields_json},
  "boundary_version" : 2,
  "canonical_encoding_version" : 1,
  "arrow_mapping_version" : 1
}}"#
    );
    parse_request(request.as_bytes())
}
