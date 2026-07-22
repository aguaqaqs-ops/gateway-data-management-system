use gateway_compute_core::{ComputeFailure, ParsedRequest, parse_request};

pub fn minimal_request(fields_json: &str) -> Result<ParsedRequest, ComputeFailure> {
    let request = format!(
        r#"{{
  "request_schema_version": 1,
  "contract_binding": {{
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0"
  }},
  "canonical_encoding_version": 1,
  "arrow_mapping_schema_version": 1,
  "declared_table_schema": {{
    "fields": {fields_json}
  }}
}}"#
    );
    parse_request(request.as_bytes())
}

pub fn pretty_request(fields_json: &str) -> Result<ParsedRequest, ComputeFailure> {
    let request = format!(
        r#"{{
  "declared_table_schema" : {{ "fields" : {fields_json} }},
  "contract_binding" : {{
    "semantic_version" : "1.0.0",
    "contract_id" : "gateway-vnext.canonical-row-hash-compute-boundary"
  }},
  "request_schema_version" : 1,
  "canonical_encoding_version" : 1,
  "arrow_mapping_schema_version" : 1
}}"#
    );
    parse_request(request.as_bytes())
}
