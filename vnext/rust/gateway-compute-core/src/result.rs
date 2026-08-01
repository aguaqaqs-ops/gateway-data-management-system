use gateway_shared_kernel::{DigestRef, SemanticDigest, canonicalize_jcs};
use serde::Serialize;

use crate::contract::BOUNDARY_VERSION;
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
        boundary_version: BOUNDARY_VERSION,
        table_schema_digest: table_schema_digest.digest_ref().as_str().to_string(),
        row_count: row_count.to_string(),
        raw_content_digest: raw_content_digest.digest_ref().as_str().to_string(),
    };
    let json = serde_json::to_vec(&envelope)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
    canonicalize_jcs(&json)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

#[derive(Debug, Serialize)]
struct SuccessEnvelope {
    boundary_version: u32,
    table_schema_digest: String,
    row_count: String,
    raw_content_digest: String,
}

#[allow(dead_code)]
fn digest_ref_wire(digest: &DigestRef) -> String {
    digest.as_str().to_string()
}
