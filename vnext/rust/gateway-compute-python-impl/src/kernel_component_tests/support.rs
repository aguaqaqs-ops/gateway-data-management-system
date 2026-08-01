#![allow(clippy::expect_used)]

use std::sync::Once;

use gateway_compute_core::ComputeFailureCode;
use pyo3::prelude::*;
use pyo3::types::PyAnyMethods;

use crate::mount_pymodule;

static PYTHON_INIT: Once = Once::new();

pub fn ensure_python() {
    PYTHON_INIT.call_once(|| {
        Python::initialize();
        let site_packages = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../backend/.venv/lib/python3.14/site-packages");
        Python::attach(|py| -> PyResult<()> {
            if site_packages.exists() {
                let site = site_packages.to_string_lossy().to_string();
                let sys = PyModule::import(py, "sys")?;
                let path = sys.getattr("path")?;
                path.call_method1("insert", (0, site))?;
            }
            let module = PyModule::new(py, "gateway_compute")?;
            mount_pymodule(&module)?;
            py.import("sys")?
                .getattr("modules")?
                .set_item("gateway_compute", module)?;
            Ok(())
        })
        .expect("python test module init");
    });
}

pub fn with_python<F>(f: F) -> Result<(), String>
where
    F: for<'py> FnOnce(Python<'py>) -> Result<(), String>,
{
    ensure_python();
    Python::attach(f)
}

pub fn gil_boundary_serial_lock() -> Result<std::sync::MutexGuard<'static, ()>, String> {
    static GIL_BOUNDARY_SERIAL: std::sync::Mutex<()> = std::sync::Mutex::new(());
    GIL_BOUNDARY_SERIAL
        .lock()
        .map_err(|error| format!("gil boundary serial lock poisoned: {error}"))
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

pub fn golden_envelope(code: ComputeFailureCode) -> &'static [u8] {
    match code {
        ComputeFailureCode::ComputeRequestSchemaInvalid => {
            br#"{"code":"COMPUTE_REQUEST_SCHEMA_INVALID","message":"compute request schema is invalid"}"#
        }
        ComputeFailureCode::ComputeBoundaryVersionUnsupported => {
            br#"{"code":"COMPUTE_BOUNDARY_VERSION_UNSUPPORTED","message":"compute boundary version is unsupported"}"#
        }
        ComputeFailureCode::ComputeCanonicalVersionUnsupported => {
            br#"{"code":"COMPUTE_CANONICAL_VERSION_UNSUPPORTED","message":"canonical encoding version is unsupported"}"#
        }
        ComputeFailureCode::ComputeArrowMappingVersionUnsupported => {
            br#"{"code":"COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED","message":"Arrow mapping version is unsupported"}"#
        }
        ComputeFailureCode::ArrowStreamImportFailed => {
            br#"{"code":"ARROW_STREAM_IMPORT_FAILED","message":"Arrow stream import failed"}"#
        }
        ComputeFailureCode::ArrowTypeUnsupported => {
            br#"{"code":"ARROW_TYPE_UNSUPPORTED","message":"Arrow type is unsupported"}"#
        }
        ComputeFailureCode::ArrowSchemaMismatch => {
            br#"{"code":"ARROW_SCHEMA_MISMATCH","message":"input Arrow schema does not match declared fields"}"#
        }
        ComputeFailureCode::CanonicalValueInvalid => {
            br#"{"code":"CANONICAL_VALUE_INVALID","message":"canonical value is invalid"}"#
        }
        ComputeFailureCode::RowHashComputeFailed => {
            br#"{"code":"ROW_HASH_COMPUTE_FAILED","message":"canonical row hash computation failed"}"#
        }
        ComputeFailureCode::ResourceLimitExceeded => {
            br#"{"code":"RESOURCE_LIMIT_EXCEEDED","message":"compute resource limit exceeded"}"#
        }
        ComputeFailureCode::ArrowStreamExportFailed => {
            br#"{"code":"ARROW_STREAM_EXPORT_FAILED","message":"Arrow stream export failed"}"#
        }
        ComputeFailureCode::NativePanic => {
            br#"{"code":"NATIVE_PANIC","message":"native compute panicked"}"#
        }
    }
}

pub fn golden_exception_type(code: ComputeFailureCode) -> &'static str {
    match code {
        ComputeFailureCode::CanonicalValueInvalid => "CanonicalValueError",
        ComputeFailureCode::RowHashComputeFailed | ComputeFailureCode::NativePanic => {
            "ComputeError"
        }
        ComputeFailureCode::ResourceLimitExceeded => "ResourceLimitError",
        _ => "ComputeRequestError",
    }
}

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
    let failure: Vec<u8> = value
        .getattr("failure_jcs")
        .map_err(|error: PyErr| error.to_string())?
        .extract()
        .map_err(|error: PyErr| error.to_string())?;
    if failure != golden_envelope(code) {
        return Err(format!(
            "failure mismatch:\nexpected: {}\ngot: {}",
            String::from_utf8_lossy(golden_envelope(code)),
            String::from_utf8_lossy(&failure)
        ));
    }
    Ok(())
}

pub fn minimal_empty_request_jcs() -> &'static [u8] {
    br#"{"arrow_mapping_version":1,"boundary_version":2,"canonical_encoding_version":1,"declared_fields":[]}"#
}
