#![forbid(unsafe_code)]

mod common;

use gateway_compute_core::ComputeFailureCode;
use pyo3::types::{PyAnyMethods, PyInt};

use common::{assert_golden_envelope, empty_arrow_stream, with_python};
use gw_compute::errors::failure_to_pyerr;

extern crate gateway_compute as gw_compute;

fn map_all_failure_codes() -> [ComputeFailureCode; 12] {
    [
        ComputeFailureCode::ComputeRequestSchemaInvalid,
        ComputeFailureCode::ComputeBoundaryVersionUnsupported,
        ComputeFailureCode::ComputeCanonicalVersionUnsupported,
        ComputeFailureCode::ComputeArrowMappingVersionUnsupported,
        ComputeFailureCode::ArrowStreamImportFailed,
        ComputeFailureCode::ArrowTypeUnsupported,
        ComputeFailureCode::ArrowSchemaMismatch,
        ComputeFailureCode::CanonicalValueInvalid,
        ComputeFailureCode::RowHashComputeFailed,
        ComputeFailureCode::ResourceLimitExceeded,
        ComputeFailureCode::ArrowStreamExportFailed,
        ComputeFailureCode::NativePanic,
    ]
}

#[test]
fn failure_to_pyerr_maps_all_stable_codes_to_independent_goldens() -> Result<(), String> {
    with_python(|py| {
        for code in map_all_failure_codes() {
            let failure = gateway_compute_core::ComputeFailure::new(code);
            let err = failure_to_pyerr(py, failure);
            assert_golden_envelope(py, err, code)?;
        }
        Ok(())
    })
}

#[test]
fn native_maps_boundary_version_unsupported() -> Result<(), String> {
    with_python(|py| {
        let request_jcs = br#"{"arrow_mapping_version":1,"boundary_version":1,"canonical_encoding_version":1,"declared_fields":[]}"#;
        let module = pyo3::types::PyModule::import(py, "gateway_compute")
            .map_err(|error| error.to_string())?;
        let func = module
            .getattr("_canonical_row_hashes_v2_native")
            .map_err(|error| error.to_string())?;
        let reader = empty_arrow_stream(py)?;
        let err = match func.call1((request_jcs, reader)) {
            Ok(_) => return Err("expected boundary version failure".to_string()),
            Err(error) => error,
        };
        assert_golden_envelope(
            py,
            err,
            ComputeFailureCode::ComputeBoundaryVersionUnsupported,
        )
    })
}

#[test]
fn native_rejects_non_arrow_input() -> Result<(), String> {
    with_python(|py| {
        let module = pyo3::types::PyModule::import(py, "gateway_compute")
            .map_err(|error| error.to_string())?;
        let func = module
            .getattr("_canonical_row_hashes_v2_native")
            .map_err(|error| error.to_string())?;
        let bogus = PyInt::new(py, 42);
        let err = match func.call1((b"{}", bogus)) {
            Ok(_) => return Err("expected import failure".to_string()),
            Err(error) => error,
        };
        assert_golden_envelope(py, err, ComputeFailureCode::ArrowStreamImportFailed)
    })
}
