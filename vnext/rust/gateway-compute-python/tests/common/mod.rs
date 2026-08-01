#![forbid(unsafe_code)]
#![allow(dead_code)]

mod failure_goldens;

use std::sync::{Arc, Once};

use arrow_array::{RecordBatch, RecordBatchReader};
use arrow_schema::{ArrowError, Schema};
use gateway_compute_core::ComputeFailureCode;
use pyo3::prelude::*;
use pyo3::types::PyAnyMethods;
use pyo3_arrow::PyRecordBatchReader;

extern crate gateway_compute as gw_compute;

use gw_compute::gateway_compute;

static PYTHON_INIT: Once = Once::new();

pub fn ensure_python() {
    PYTHON_INIT.call_once(|| {
        pyo3::append_to_inittab!(gateway_compute);
        Python::initialize();
        let site_packages = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../backend/.venv/lib/python3.14/site-packages");
        if site_packages.exists() {
            let site = site_packages.to_string_lossy().to_string();
            let _ = Python::attach(|py| -> PyResult<()> {
                let sys = PyModule::import(py, "sys")?;
                let path = sys.getattr("path")?;
                path.call_method1("insert", (0, site))?;
                Ok(())
            });
        }
    });
}

pub fn with_python<F>(f: F) -> Result<(), String>
where
    F: for<'py> FnOnce(Python<'py>) -> Result<(), String>,
{
    ensure_python();
    Python::attach(f)
}

pub fn is_exception_type(py: Python<'_>, err: &PyErr, type_name: &str) -> Result<bool, String> {
    let module = PyModule::import(py, "gateway_compute").map_err(|error| error.to_string())?;
    let exc_type = module
        .getattr(type_name)
        .map_err(|error| error.to_string())?;
    err.value(py)
        .is_instance(&exc_type)
        .map_err(|error| error.to_string())
}

pub use failure_goldens::{golden_envelope, golden_exception_type};

pub fn assert_golden_envelope(
    py: Python<'_>,
    py_err: PyErr,
    code: ComputeFailureCode,
) -> Result<(), String> {
    assert!(is_exception_type(py, &py_err, golden_exception_type(code))?);
    let value = py_err.value(py);
    let observed_code: String = value
        .getattr("code")
        .map_err(|error: PyErr| error.to_string())?
        .extract()
        .map_err(|error: PyErr| error.to_string())?;
    if observed_code != code.as_str() {
        return Err(format!(
            "expected code {}, got {observed_code}",
            code.as_str()
        ));
    }
    assert_envelope_exact(py, py_err, golden_envelope(code))
}

pub fn assert_envelope_exact(
    py: Python<'_>,
    py_err: PyErr,
    expected_jcs: &[u8],
) -> Result<(), String> {
    let value = py_err.value(py);
    let envelope: Vec<u8> = value
        .getattr("failure_jcs")
        .map_err(|error: PyErr| error.to_string())?
        .extract()
        .map_err(|error: PyErr| error.to_string())?;
    if envelope.is_empty() {
        return Err("failure_jcs must be non-empty".to_string());
    }
    if envelope != expected_jcs {
        return Err(format!(
            "envelope mismatch:\nexpected: {}\ngot: {}",
            String::from_utf8_lossy(expected_jcs),
            String::from_utf8_lossy(&envelope)
        ));
    }
    Ok(())
}

pub fn minimal_empty_request_jcs() -> &'static [u8] {
    br#"{"arrow_mapping_version":1,"boundary_version":1,"canonical_encoding_version":1,"declared_fields":[]}"#
}

pub struct EmptyBatchReader {
    schema: Arc<Schema>,
    done: bool,
}

impl EmptyBatchReader {
    pub fn new() -> Self {
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

pub fn empty_arrow_stream(py: Python<'_>) -> Result<pyo3::Py<pyo3::PyAny>, String> {
    PyRecordBatchReader::new(Box::new(EmptyBatchReader::new()))
        .into_pyarrow(py)
        .map(|value| value.unbind())
        .map_err(|error| error.to_string())
}
