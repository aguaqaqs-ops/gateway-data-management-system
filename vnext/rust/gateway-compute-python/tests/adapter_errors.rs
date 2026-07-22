#![forbid(unsafe_code)]

use std::sync::Once;

use gateway_compute_core::{ComputeFailure, ComputeFailureCode};
use pyo3::prelude::*;
use pyo3::types::PyInt;

extern crate gateway_compute as gw_compute;

use gw_compute::errors::failure_to_pyerr;
use gw_compute::gateway_compute;

static PYTHON_INIT: Once = Once::new();

fn ensure_python() {
    PYTHON_INIT.call_once(|| {
        pyo3::append_to_inittab!(gateway_compute);
        Python::initialize();
    });
}

fn with_python<F>(f: F) -> Result<(), String>
where
    F: for<'py> FnOnce(Python<'py>) -> Result<(), String>,
{
    ensure_python();
    Python::attach(f)
}

fn is_exception_type(py: Python<'_>, err: &PyErr, type_name: &str) -> Result<bool, String> {
    let module = PyModule::import(py, "gateway_compute").map_err(|error| error.to_string())?;
    let exc_type = module
        .getattr(type_name)
        .map_err(|error| error.to_string())?;
    err.value(py)
        .is_instance(&exc_type)
        .map_err(|error| error.to_string())
}

fn expected_envelope(code: ComputeFailureCode) -> Result<Vec<u8>, String> {
    ComputeFailure::new(code)
        .to_envelope_jcs()
        .map_err(|failure| format!("{failure:?}"))
}

fn assert_envelope_exact(py: Python<'_>, py_err: PyErr, expected_jcs: &[u8]) -> Result<(), String> {
    let value = py_err.value(py);
    let envelope: Vec<u8> = value
        .getattr("envelope_jcs")
        .map_err(|error: PyErr| error.to_string())?
        .extract()
        .map_err(|error: PyErr| error.to_string())?;
    if envelope != expected_jcs {
        return Err(format!(
            "envelope mismatch:\nexpected: {}\ngot: {}",
            String::from_utf8_lossy(expected_jcs),
            String::from_utf8_lossy(&envelope)
        ));
    }
    Ok(())
}

#[test]
fn failure_to_pyerr_maps_request_schema_invalid() -> Result<(), String> {
    with_python(|py| {
        let failure = ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid);
        let err = failure_to_pyerr(py, failure);
        assert!(is_exception_type(py, &err, "ComputeRequestError")?);
        assert_envelope_exact(
            py,
            err,
            &expected_envelope(ComputeFailureCode::ComputeRequestSchemaInvalid)?,
        )?;
        Ok(())
    })
}

#[test]
fn failure_to_pyerr_maps_canonical_value_invalid() -> Result<(), String> {
    with_python(|py| {
        let failure = ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid);
        let err = failure_to_pyerr(py, failure);
        assert!(is_exception_type(py, &err, "CanonicalValueError")?);
        assert_envelope_exact(
            py,
            err,
            &expected_envelope(ComputeFailureCode::CanonicalValueInvalid)?,
        )?;
        Ok(())
    })
}

#[test]
fn failure_to_pyerr_maps_resource_limit_exceeded() -> Result<(), String> {
    with_python(|py| {
        let failure = ComputeFailure::new(ComputeFailureCode::ResourceLimitExceeded);
        let err = failure_to_pyerr(py, failure);
        assert!(is_exception_type(py, &err, "ResourceLimitError")?);
        assert_envelope_exact(
            py,
            err,
            &expected_envelope(ComputeFailureCode::ResourceLimitExceeded)?,
        )?;
        Ok(())
    })
}

#[test]
fn failure_to_pyerr_maps_native_panic() -> Result<(), String> {
    with_python(|py| {
        let failure = ComputeFailure::new(ComputeFailureCode::NativePanic);
        let err = failure_to_pyerr(py, failure);
        assert!(is_exception_type(py, &err, "ComputeError")?);
        assert_envelope_exact(
            py,
            err,
            &expected_envelope(ComputeFailureCode::NativePanic)?,
        )?;
        Ok(())
    })
}

#[test]
fn native_rejects_non_arrow_input() -> Result<(), String> {
    with_python(|py| {
        let module = PyModule::import(py, "gateway_compute").map_err(|error| error.to_string())?;
        let func = module
            .getattr("_canonical_row_hashes_v1_native")
            .map_err(|error| error.to_string())?;
        let bogus = PyInt::new(py, 42);
        let err = match func.call1((b"{}", bogus)) {
            Ok(_) => return Err("expected import failure".to_string()),
            Err(error) => error,
        };
        assert!(is_exception_type(py, &err, "ComputeRequestError")?);
        assert_envelope_exact(
            py,
            err,
            &expected_envelope(ComputeFailureCode::ArrowStreamImportFailed)?,
        )?;
        Ok(())
    })
}
