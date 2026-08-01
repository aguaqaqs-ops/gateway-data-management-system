#![forbid(unsafe_code)]

pub mod adapter;
pub mod errors;

#[cfg(test)]
mod kernel_component_tests;

pub use adapter::canonical_row_hashes_v2_native;
pub use errors::{
    CanonicalValueError, ComputeError, ComputeRequestError, ResourceLimitError, failure_to_pyerr,
    register_exceptions,
};

use pyo3::prelude::*;

#[pyfunction]
fn _canonical_row_hashes_v2_native(
    py: Python<'_>,
    request_jcs: &[u8],
    input_stream: &Bound<'_, PyAny>,
) -> PyResult<(Py<PyAny>, Vec<u8>)> {
    canonical_row_hashes_v2_native(py, request_jcs, input_stream)
}

pub fn mount_pymodule(module: &Bound<'_, PyModule>) -> PyResult<()> {
    register_exceptions(module)?;
    module.add_function(wrap_pyfunction!(_canonical_row_hashes_v2_native, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}

#[cfg(test)]
mod smoke {
    use crate::ComputeRequestError;

    #[test]
    fn exception_type_is_linked() {
        assert!(!std::any::type_name::<ComputeRequestError>().is_empty());
    }
}
