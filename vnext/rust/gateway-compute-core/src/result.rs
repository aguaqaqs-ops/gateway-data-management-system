use gateway_shared_kernel::{DigestRef, SemanticDigest, canonicalize_jcs};
use serde::Serialize;

use crate::contract::{
    ARROW_MAPPING_SCHEMA_VERSION, CANONICAL_ENCODING_VERSION, CONTRACT_ID, RESULT_SCHEMA_VERSION,
    SEMANTIC_VERSION,
};
use crate::errors::{ComputeFailure, ComputeFailureCode};

#[derive(Debug, Clone)]
pub struct CanonicalRowHashOutput {
    pub output_batches: Vec<arrow_array::RecordBatch>,
    pub result_jcs: Vec<u8>,
}

pub fn serialize_success_result(
    table_schema_digest: &SemanticDigest,
    row_count: u64,
    raw_content_digest: &SemanticDigest,
) -> Result<Vec<u8>, ComputeFailure> {
    let envelope = SuccessEnvelope {
        result_schema_version: RESULT_SCHEMA_VERSION,
        contract_binding: ContractBinding {
            contract_id: CONTRACT_ID.to_string(),
            semantic_version: SEMANTIC_VERSION.to_string(),
        },
        canonical_encoding_version: CANONICAL_ENCODING_VERSION,
        arrow_mapping_schema_version: ARROW_MAPPING_SCHEMA_VERSION,
        table_schema_digest: table_schema_digest.digest_ref().as_str().to_string(),
        row_count: row_count.to_string(),
        raw_content_digest: raw_content_digest.digest_ref().as_str().to_string(),
        diagnostics: Vec::<String>::new(),
    };
    let json = serde_json::to_vec(&envelope)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
    canonicalize_jcs(&json)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

#[derive(Debug, Serialize)]
struct SuccessEnvelope {
    result_schema_version: u32,
    contract_binding: ContractBinding,
    canonical_encoding_version: u32,
    arrow_mapping_schema_version: u32,
    table_schema_digest: String,
    row_count: String,
    raw_content_digest: String,
    diagnostics: Vec<String>,
}

#[derive(Debug, Serialize)]
struct ContractBinding {
    contract_id: String,
    semantic_version: String,
}

#[allow(dead_code)]
fn digest_ref_wire(digest: &DigestRef) -> String {
    digest.as_str().to_string()
}
