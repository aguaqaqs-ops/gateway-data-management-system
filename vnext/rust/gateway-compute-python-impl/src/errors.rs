use gateway_compute_core::{ComputeFailure, ComputeFailureCode};
use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// Canonical JCS bytes for `ROW_HASH_COMPUTE_FAILED`; used when live serialization fails.
const ROW_HASH_COMPUTE_FAILED_FAILURE_JCS: &[u8] =
    br#"{"code":"ROW_HASH_COMPUTE_FAILED","message":"canonical row hash computation failed"}"#;

create_exception!(
    gateway_compute,
    ComputeRequestError,
    PyException,
    "Request or Arrow schema/import failure."
);
create_exception!(
    gateway_compute,
    CanonicalValueError,
    PyException,
    "Canonical value could not be encoded."
);
create_exception!(
    gateway_compute,
    ComputeError,
    PyException,
    "Row hash compute failed."
);
create_exception!(
    gateway_compute,
    ResourceLimitError,
    PyException,
    "Compute resource limit exceeded."
);

pub fn register_exceptions(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    module.add("ComputeRequestError", py.get_type::<ComputeRequestError>())?;
    module.add("CanonicalValueError", py.get_type::<CanonicalValueError>())?;
    module.add("ComputeError", py.get_type::<ComputeError>())?;
    module.add("ResourceLimitError", py.get_type::<ResourceLimitError>())?;
    Ok(())
}

pub fn failure_to_pyerr(py: Python<'_>, failure: ComputeFailure) -> PyErr {
    let (envelope_jcs, failure) = envelope_for_pyerr(failure);
    let code = failure.code.as_str();
    let message = failure.code.message();

    let py_err = match failure.code {
        ComputeFailureCode::CanonicalValueInvalid => CanonicalValueError::new_err(code),
        ComputeFailureCode::RowHashComputeFailed | ComputeFailureCode::NativePanic => {
            ComputeError::new_err(code)
        }
        ComputeFailureCode::ResourceLimitExceeded => ResourceLimitError::new_err(code),
        _ => ComputeRequestError::new_err(code),
    };

    attach_failure_attrs(py, &py_err, &envelope_jcs, code, message);
    py_err
}

fn envelope_for_pyerr(failure: ComputeFailure) -> (Vec<u8>, ComputeFailure) {
    match failure.to_envelope_jcs() {
        Ok(envelope_jcs) => (envelope_jcs, failure),
        Err(_) => (
            ROW_HASH_COMPUTE_FAILED_FAILURE_JCS.to_vec(),
            ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed),
        ),
    }
}

pub fn import_stream_failure(py: Python<'_>) -> PyErr {
    failure_to_pyerr(
        py,
        ComputeFailure::new(ComputeFailureCode::ArrowStreamImportFailed),
    )
}

pub fn export_stream_failure(py: Python<'_>) -> PyErr {
    failure_to_pyerr(
        py,
        ComputeFailure::new(ComputeFailureCode::ArrowStreamExportFailed),
    )
}

fn attach_failure_attrs(
    py: Python<'_>,
    py_err: &PyErr,
    envelope_jcs: &[u8],
    code: &str,
    message: &str,
) {
    let value = py_err.value(py);
    let _ = value.setattr("failure_jcs", PyBytes::new(py, envelope_jcs));
    let _ = value.setattr("code", code);
    let _ = value.setattr("message", message);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[allow(clippy::panic)]
    fn static_fallback_envelope_matches_live_serialization() {
        let live =
            match ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed).to_envelope_jcs() {
                Ok(bytes) => bytes,
                Err(failure) => panic!("live envelope: {failure:?}"),
            };
        assert_eq!(live.as_slice(), ROW_HASH_COMPUTE_FAILED_FAILURE_JCS);
    }

    #[test]
    #[allow(clippy::panic)]
    fn static_fallback_envelope_is_non_empty_and_closed() {
        assert!(!ROW_HASH_COMPUTE_FAILED_FAILURE_JCS.is_empty());
        match std::str::from_utf8(ROW_HASH_COMPUTE_FAILED_FAILURE_JCS) {
            Ok(text) => {
                assert!(text.contains("ROW_HASH_COMPUTE_FAILED"));
                assert!(text.contains("\"message\":"));
                assert!(!text.contains("contract_binding"));
            }
            Err(error) => panic!("utf8: {error}"),
        }
    }
}
