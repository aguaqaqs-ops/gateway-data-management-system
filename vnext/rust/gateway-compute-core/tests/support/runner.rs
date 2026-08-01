use gateway_compute_core::{ComputeFailure, canonical_row_hashes_v1};

use super::batch_reader::VecBatchReader;
use super::request::minimal_request;

pub fn run_ok(
    fields_json: &str,
    batches: Vec<arrow_array::RecordBatch>,
) -> Result<gateway_compute_core::CanonicalRowHashOutput, String> {
    let request = minimal_request(fields_json).map_err(|error| format!("{error:?}"))?;
    canonical_row_hashes_v1(&request, VecBatchReader::new(batches).into_boxed())
        .map_err(|error| format!("{error:?}"))
}

pub fn run_ok_reader(
    fields_json: &str,
    reader: Box<dyn arrow_array::RecordBatchReader + Send>,
) -> Result<gateway_compute_core::CanonicalRowHashOutput, String> {
    let request = minimal_request(fields_json).map_err(|error| format!("{error:?}"))?;
    canonical_row_hashes_v1(&request, reader).map_err(|error| format!("{error:?}"))
}

pub fn run_err(
    fields_json: &str,
    batches: Vec<arrow_array::RecordBatch>,
) -> Result<ComputeFailure, String> {
    let request = minimal_request(fields_json).map_err(|error| format!("{error:?}"))?;
    match canonical_row_hashes_v1(&request, VecBatchReader::new(batches).into_boxed()) {
        Ok(_) => Err("expected failure".to_string()),
        Err(error) => Ok(error),
    }
}

pub fn run_err_reader(
    fields_json: &str,
    reader: Box<dyn arrow_array::RecordBatchReader + Send>,
) -> Result<ComputeFailure, String> {
    let request = minimal_request(fields_json).map_err(|error| format!("{error:?}"))?;
    match canonical_row_hashes_v1(&request, reader) {
        Ok(_) => Err("expected failure".to_string()),
        Err(error) => Ok(error),
    }
}
