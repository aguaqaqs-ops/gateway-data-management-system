use gateway_compute_core::double_nullable_i64;
use pyo3::exceptions::{PyOverflowError, PyTypeError};
use pyo3::prelude::*;

#[pyfunction]
fn double_first_column(py: Python<'_>, batch: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let column = batch.call_method1("column", (0,))?;
    let values: Vec<Option<i64>> = column.call_method0("to_pylist")?.extract()?;
    let doubled = py
        .detach(|| double_nullable_i64(&values))
        .map_err(|error| PyOverflowError::new_err(error.to_string()))?;
    let pyarrow = py.import("pyarrow")?;
    let array = pyarrow.call_method1("array", (doubled,))?;
    let names = batch.getattr("schema")?.getattr("names")?;
    pyarrow
        .getattr("RecordBatch")?
        .call_method1("from_arrays", (vec![array], names))
        .map(|result| result.unbind())
        .map_err(|error| PyTypeError::new_err(error.to_string()))
}

#[pymodule]
fn gateway_compute(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(double_first_column, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
