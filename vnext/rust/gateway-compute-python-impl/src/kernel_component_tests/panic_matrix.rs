use std::sync::Arc;

use arrow_array::{RecordBatch, RecordBatchReader};
use arrow_schema::{ArrowError, Schema};
use gateway_compute_core::ComputeFailureCode;
use pyo3::prelude::*;
use pyo3::types::PyInt;

use crate::adapter::test_hooks::{self, AdapterStage};
use crate::adapter::{self, test_invoke_compute_panic_probe, test_invoke_export_hold_probe};
use crate::errors::failure_to_pyerr;

use super::support::{assert_golden_envelope, minimal_empty_request_jcs, with_python};

struct EmptyBatchReader {
    schema: Arc<Schema>,
    done: bool,
}

impl EmptyBatchReader {
    fn new() -> Self {
        Self {
            schema: Arc::new(Schema::empty()),
            done: false,
        }
    }
}

impl RecordBatchReader for EmptyBatchReader {
    fn schema(&self) -> Arc<Schema> {
        self.schema.clone()
    }
}

impl Iterator for EmptyBatchReader {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.done {
            return None;
        }
        self.done = true;
        Some(Ok(RecordBatch::new_empty(self.schema.clone())))
    }
}

fn call_native(
    py: Python<'_>,
    request_jcs: &[u8],
    input_stream: &Bound<'_, PyAny>,
) -> Result<Result<(), PyErr>, String> {
    let err = match adapter::canonical_row_hashes_v2_native(py, request_jcs, input_stream) {
        Ok(_) => return Ok(Ok(())),
        Err(error) => error,
    };
    Ok(Err(err))
}

#[test]
fn import_panic_maps_to_native_panic() -> Result<(), String> {
    test_hooks::set_panic_stage(AdapterStage::Import);
    let result = with_python(|py| {
        let bogus = PyInt::new(py, 42);
        let err = match call_native(py, minimal_empty_request_jcs(), &bogus)? {
            Ok(()) => return Err("expected import panic".to_string()),
            Err(error) => error,
        };
        assert_golden_envelope(py, err, ComputeFailureCode::NativePanic)
    });
    test_hooks::clear_panic_stage();
    result
}

#[test]
fn compute_panic_maps_to_native_panic() -> Result<(), String> {
    test_hooks::set_panic_stage(AdapterStage::Compute);
    let failure = match test_invoke_compute_panic_probe(
        minimal_empty_request_jcs(),
        Box::new(EmptyBatchReader::new()),
    ) {
        Err(failure) => failure,
        Ok(_) => return Err("expected compute panic".to_string()),
    };
    test_hooks::clear_panic_stage();
    if failure.code != ComputeFailureCode::NativePanic {
        return Err(format!("expected NativePanic, got {:?}", failure.code));
    }
    with_python(|py| {
        let err = failure_to_pyerr(py, failure);
        assert_golden_envelope(py, err, ComputeFailureCode::NativePanic)
    })
}

#[test]
fn export_panic_maps_to_native_panic() -> Result<(), String> {
    test_hooks::set_panic_stage(AdapterStage::Export);
    let result = with_python(|py| {
        let failure = match test_invoke_export_hold_probe(py, Vec::new()) {
            Err(failure) => failure,
            Ok(_) => return Err("expected export panic".to_string()),
        };
        let err = failure_to_pyerr(py, failure);
        assert_golden_envelope(py, err, ComputeFailureCode::NativePanic)
    });
    test_hooks::clear_panic_stage();
    result
}
