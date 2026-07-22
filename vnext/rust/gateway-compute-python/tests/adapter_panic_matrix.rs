#![forbid(unsafe_code)]

mod common;

use arrow_array::{RecordBatch, RecordBatchReader};
use arrow_schema::{ArrowError, Schema};
use gateway_compute_core::ComputeFailureCode;
use gateway_compute_impl::adapter::{
    self, test_invoke_compute_panic_probe, test_invoke_export_panic_probe,
};
use gateway_compute_impl::errors::failure_to_pyerr;
use gateway_compute_impl::test_probes::{self, PanicStage};
use pyo3::prelude::*;
use pyo3::types::PyInt;
use std::sync::Arc;

use common::{
    assert_envelope_exact, expected_envelope, is_exception_type, minimal_empty_request_jcs,
    with_python,
};

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
    let err = match adapter::canonical_row_hashes_v1_native(py, request_jcs, input_stream) {
        Ok(_) => return Ok(Ok(())),
        Err(error) => error,
    };
    Ok(Err(err))
}

fn assert_native_panic(py: Python<'_>, err: PyErr) -> Result<(), String> {
    if !is_exception_type(py, &err, "ComputeError")? {
        let code: Option<String> = err
            .value(py)
            .getattr("code")
            .ok()
            .and_then(|value| value.extract().ok());
        return Err(format!(
            "expected ComputeError for NATIVE_PANIC, code={code:?}, err={err}"
        ));
    }
    let code: String = err
        .value(py)
        .getattr("code")
        .map_err(|error: PyErr| error.to_string())?
        .extract()
        .map_err(|error: PyErr| error.to_string())?;
    if code != "NATIVE_PANIC" {
        return Err(format!("expected NATIVE_PANIC, got {code}"));
    }
    assert_envelope_exact(
        py,
        err,
        &expected_envelope(ComputeFailureCode::NativePanic)?,
    )
}

#[test]
fn import_panic_maps_to_native_panic() -> Result<(), String> {
    test_probes::set_panic_stage(PanicStage::Import);
    let result = with_python(|py| {
        let bogus = PyInt::new(py, 42);
        let err = match call_native(py, minimal_empty_request_jcs(), &bogus)? {
            Ok(()) => return Err("expected import panic".to_string()),
            Err(error) => error,
        };
        assert_native_panic(py, err)
    });
    test_probes::clear_panic_stage();
    result
}

#[test]
fn compute_panic_maps_to_native_panic() -> Result<(), String> {
    test_probes::set_panic_stage(PanicStage::Compute);
    let failure = match test_invoke_compute_panic_probe(
        minimal_empty_request_jcs(),
        Box::new(EmptyBatchReader::new()),
    ) {
        Err(failure) => failure,
        Ok(_) => return Err("expected compute panic".to_string()),
    };
    test_probes::clear_panic_stage();
    if failure.code != ComputeFailureCode::NativePanic {
        return Err(format!("expected NativePanic, got {:?}", failure.code));
    }
    with_python(|py| {
        let err = failure_to_pyerr(py, failure);
        assert_native_panic(py, err)
    })
}

#[test]
fn export_panic_maps_to_native_panic() -> Result<(), String> {
    test_probes::set_panic_stage(PanicStage::Export);
    let result = with_python(|py| {
        let failure = match test_invoke_export_panic_probe(py, Vec::new()) {
            Err(failure) => failure,
            Ok(_) => return Err("expected export panic".to_string()),
        };
        let err = failure_to_pyerr(py, failure);
        assert_native_panic(py, err)
    });
    test_probes::clear_panic_stage();
    result
}
