#![forbid(unsafe_code)]
#![allow(dead_code)]

use std::sync::{Arc, Once};

use arrow_array::{RecordBatch, RecordBatchReader};
use arrow_schema::{ArrowError, Schema};
use gateway_compute_core::{ComputeFailure, ComputeFailureCode};
use pyo3::prelude::*;
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

pub fn expected_envelope(code: ComputeFailureCode) -> Result<Vec<u8>, String> {
    ComputeFailure::new(code)
        .to_envelope_jcs()
        .map_err(|failure| format!("{failure:?}"))
}

pub fn assert_envelope_exact(
    py: Python<'_>,
    py_err: PyErr,
    expected_jcs: &[u8],
) -> Result<(), String> {
    let value = py_err.value(py);
    let envelope: Vec<u8> = value
        .getattr("envelope_jcs")
        .map_err(|error: PyErr| error.to_string())?
        .extract()
        .map_err(|error: PyErr| error.to_string())?;
    if envelope.is_empty() {
        return Err("envelope_jcs must be non-empty".to_string());
    }
    if !envelope
        .windows(16)
        .any(|window| window == br#""diagnostics":[]"#)
    {
        return Err("envelope must contain diagnostics=[]".to_string());
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
    br#"{"arrow_mapping_schema_version":1,"canonical_encoding_version":1,"contract_binding":{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary","semantic_version":"1.0.0"},"declared_table_schema":{"fields":[]},"request_schema_version":1}"#
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
