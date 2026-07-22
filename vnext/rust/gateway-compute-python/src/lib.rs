#![forbid(unsafe_code)]

pub use gateway_compute_impl::{
    CanonicalValueError, ComputeError, ComputeRequestError, ResourceLimitError, adapter, errors,
    mount_pymodule,
};
use pyo3::prelude::*;

#[pymodule]
pub fn gateway_compute(module: &Bound<'_, PyModule>) -> PyResult<()> {
    mount_pymodule(module)
}
