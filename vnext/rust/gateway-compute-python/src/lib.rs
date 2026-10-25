#![forbid(unsafe_code)]

pub use gateway_compute_impl::{
    CanonicalValueError, ComputeError, ComputeRequestError, ResourceLimitError, adapter, errors,
    mount_pymodule,
};
use pyo3::prelude::*;

/// Build input identity recorded at compile time. The authoritative test runner sets
/// `GATEWAY_RUST_BUILD_INPUT` to the `vnext/rust` Git tree id and checks the installed
/// extension against the current commit; other builds leave it empty.
const BUILD_INPUT: &str = match option_env!("GATEWAY_RUST_BUILD_INPUT") {
    Some(value) => value,
    None => "",
};

#[pymodule]
pub fn gateway_compute(module: &Bound<'_, PyModule>) -> PyResult<()> {
    mount_pymodule(module)?;
    module.add("__build_input__", BUILD_INPUT)
}
