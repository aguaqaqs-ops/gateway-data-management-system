//! Replacement-period differential bridge. E removes this module.
//! The production comparison route never calls it.

use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use arrow_array::{Array, RecordBatch, RecordBatchReader};
use arrow_schema::SchemaRef;
use gateway_compute_core::comparison::{
    KernelContext, OrderedCompareError, comparison_probe_json,
};
use pyo3::exceptions::{PyInterruptedError, PyMemoryError, PyTimeoutError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyModule;
use pyo3_arrow::PyRecordBatchReader;

fn comparison_error(error: OrderedCompareError) -> PyErr {
    match error.code() {
        "RESOURCE_LIMIT_EXCEEDED" => PyMemoryError::new_err(error.to_string()),
        "COMPARISON_CANCELLED" => PyInterruptedError::new_err(error.to_string()),
        "COMPARISON_DEADLINE_EXCEEDED" => PyTimeoutError::new_err(error.to_string()),
        _ => PyValueError::new_err(error.to_string()),
    }
}

fn read_stream(stream: PyRecordBatchReader) -> PyResult<(SchemaRef, Vec<RecordBatch>)> {
    let schema = stream.schema_ref()?;
    let reader: Box<dyn RecordBatchReader + Send> = stream.into_reader()?;
    let batches = reader.collect::<Result<Vec<_>, _>>()
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    Ok((schema, batches))
}

/// Conservative test-side logical slice estimate. The production caller owns
/// the unique pinned backing charge; this probe never participates in D's
/// operation charge or acts as evidence of its lifetime contract.
fn input_slice_upper(before: &[RecordBatch], current: &[RecordBatch]) -> PyResult<usize> {
    before.iter().chain(current).flat_map(RecordBatch::columns)
        .try_fold(0usize, |sum, array| {
            sum.checked_add(array.to_data().get_slice_memory_size().ok()?)
        })
        .ok_or_else(|| PyMemoryError::new_err("input slice estimate overflow"))
}

#[pyfunction]
fn _s3_compare_probe(
    kind: &str,
    before_stream: PyRecordBatchReader,
    current_stream: PyRecordBatchReader,
    policy_json: &str,
) -> PyResult<String> {
    let (before_schema, before) = read_stream(before_stream)?;
    let (current_schema, current) = read_stream(current_stream)?;
    let input_bytes = input_slice_upper(&before, &current)?;
    let remaining = (24usize * 1024 * 1024 * 1024)
        .checked_sub(input_bytes)
        .ok_or_else(|| PyMemoryError::new_err("canonical input exceeds probe budget"))?;
    let context = Arc::new(KernelContext::new(
        remaining, Arc::new(AtomicBool::new(false)), None,
    ));
    comparison_probe_json(
        kind, before_schema, &before, current_schema, &current, policy_json, &context,
    ).map_err(comparison_error)
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(_s3_compare_probe, module)?)?;
    Ok(())
}
