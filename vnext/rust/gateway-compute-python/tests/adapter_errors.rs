#![forbid(unsafe_code)]

mod common;

use gateway_compute_core::{ComputeFailure, ComputeFailureCode};
use pyo3::prelude::*;
use pyo3::types::PyInt;

use common::{
    assert_envelope_exact, empty_arrow_stream, expected_envelope, is_exception_type, with_python,
};
use gw_compute::errors::failure_to_pyerr;

extern crate gateway_compute as gw_compute;

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
fn failure_to_pyerr_maps_row_hash_compute_failed() -> Result<(), String> {
    with_python(|py| {
        let failure = ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed);
        let err = failure_to_pyerr(py, failure);
        assert!(is_exception_type(py, &err, "ComputeError")?);
        assert_envelope_exact(
            py,
            err,
            &expected_envelope(ComputeFailureCode::RowHashComputeFailed)?,
        )?;
        Ok(())
    })
}

#[test]
fn failure_to_pyerr_maps_arrow_stream_export_failed() -> Result<(), String> {
    with_python(|py| {
        let failure = ComputeFailure::new(ComputeFailureCode::ArrowStreamExportFailed);
        let err = failure_to_pyerr(py, failure);
        assert!(is_exception_type(py, &err, "ComputeRequestError")?);
        assert_envelope_exact(
            py,
            err,
            &expected_envelope(ComputeFailureCode::ArrowStreamExportFailed)?,
        )?;
        Ok(())
    })
}

#[test]
fn native_maps_contract_version_unsupported() -> Result<(), String> {
    with_python(|py| {
        let request_jcs = br#"{"arrow_mapping_schema_version":1,"canonical_encoding_version":1,"contract_binding":{"contract_id":"x","semantic_version":"1.0.0"},"declared_table_schema":{"fields":[]},"request_schema_version":1}"#;
        let module = PyModule::import(py, "gateway_compute").map_err(|error| error.to_string())?;
        let func = module
            .getattr("_canonical_row_hashes_v1_native")
            .map_err(|error| error.to_string())?;
        let reader = empty_arrow_stream(py)?;
        let err = match func.call1((request_jcs, reader)) {
            Ok(_) => return Err("expected contract version failure".to_string()),
            Err(error) => error,
        };
        assert!(is_exception_type(py, &err, "ComputeRequestError")?);
        assert_envelope_exact(
            py,
            err,
            &expected_envelope(ComputeFailureCode::ComputeContractVersionUnsupported)?,
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
