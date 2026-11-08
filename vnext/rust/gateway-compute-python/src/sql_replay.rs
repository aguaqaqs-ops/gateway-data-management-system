//! Explicit, GIL-detached SQL replay entrypoints. The Python capability
//! owners reserve same-operation conversion and output bytes before calling.

use std::sync::Arc;

use gateway_compute_core::comparison::KernelContext;
use gateway_compute_core::sql_replay::{SqlError, render_json_mutations, render_json_schema};
use pyo3::exceptions::{PyInterruptedError, PyRuntimeError, PyTimeoutError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyModule};

use crate::{adapter_boundary, deadline_instant, python_adapter_control, register_cancel_probe, shared_parser_pool};

fn sql_error(error: SqlError) -> PyErr {
    match error.0 {
        "COMPARISON_CANCELLED" => PyInterruptedError::new_err("SQL rendering cancelled"),
        "COMPARISON_DEADLINE_EXCEEDED" => PyTimeoutError::new_err("SQL rendering deadline elapsed"),
        "RESOURCE_EXCEEDED" => PyValueError::new_err(error.0),
        _ => PyValueError::new_err(error.0),
    }
}

fn render(
    py: Python<'_>, input: Py<PyBytes>, max_bytes: usize,
    cancel_probe: Py<PyAny>, deadline_monotonic: Option<f64>, pool_threads: usize,
    schema: bool,
) -> PyResult<Py<PyBytes>> {
    let result = adapter_boundary(|| {
        shared_parser_pool(Some(pool_threads))?;
        let deadline = deadline_instant(py, deadline_monotonic)?;
        let watch = register_cancel_probe(py, &cancel_probe)?;
        python_adapter_control(&watch, deadline)?;
        // The FFI input copy and the Rust graph are reserved by the caller.
        let payload = input.bind(py).as_bytes().to_vec();
        let context = Arc::new(KernelContext::new(max_bytes, Arc::clone(&watch.cancelled), deadline));
        let output = py.detach(|| {
            if schema { render_json_schema(&payload, max_bytes, &context) }
            else { render_json_mutations(&payload, max_bytes, &context) }
        });
        let output = output.map_err(sql_error)?;
        context.check().map_err(|error| sql_error(SqlError(error.code())))?;
        Ok(PyBytes::new(py, &output).unbind())
    });
    match result {
        Ok(output) => output,
        Err(()) => Err(PyRuntimeError::new_err("SQL rendering panicked")),
    }
}

#[pyfunction]
fn _render_change_set_native(
    py: Python<'_>, input: Py<PyBytes>, max_bytes: usize,
    cancel_probe: Py<PyAny>, deadline_monotonic: Option<f64>, pool_threads: usize,
) -> PyResult<Py<PyBytes>> {
    render(py, input, max_bytes, cancel_probe, deadline_monotonic, pool_threads, false)
}

#[pyfunction]
fn _render_storage_schema_native(
    py: Python<'_>, input: Py<PyBytes>, max_bytes: usize,
    cancel_probe: Py<PyAny>, deadline_monotonic: Option<f64>, pool_threads: usize,
) -> PyResult<Py<PyBytes>> {
    render(py, input, max_bytes, cancel_probe, deadline_monotonic, pool_threads, true)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(_render_change_set_native, module)?)?;
    module.add_function(wrap_pyfunction!(_render_storage_schema_native, module)?)?;
    Ok(())
}
