use arrow_array::RecordBatch;
use arrow_array::RecordBatchReader;
use arrow_schema::{ArrowError, Schema};
use pyo3::prelude::*;
use pyo3::types::PyAnyMethods;
use pyo3_arrow::PyRecordBatchReader;
use std::sync::Arc;
use std::thread;

use crate::adapter::test_hooks::{self, AdapterStage};
use crate::adapter::{self, test_invoke_export_hold_probe, test_invoke_import_hold_probe};

use super::gil_00_python_thread::run_python_thread_progress_suite;
use super::gil_controller::{GilExpectation, probe_stage};
use super::support::{gil_boundary_serial_lock, minimal_empty_request_jcs, with_python};

struct EmptyBatchReader {
    schema: Arc<Schema>,
    done: bool,
}

impl EmptyBatchReader {
    fn new() -> Self {
        Self {
            schema: Arc::new(Schema::empty()),
            done: false,
        }
    }
}

impl RecordBatchReader for EmptyBatchReader {
    fn schema(&self) -> Arc<Schema> {
        self.schema.clone()
    }
}

impl Iterator for EmptyBatchReader {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.done {
            return None;
        }
        self.done = true;
        Some(Ok(RecordBatch::new_empty(self.schema.clone())))
    }
}

fn call_native_empty(py: Python<'_>, request_jcs: &[u8], stream: Py<PyAny>) -> Result<(), String> {
    let bound = stream.bind(py);
    adapter::canonical_row_hashes_v2_native(py, request_jcs, bound)
        .map(|_| ())
        .map_err(|error| error.to_string())
}

fn kernel_component_gil_boundaries_inner() -> Result<(), String> {
    with_python(|py| {
        let stream = PyRecordBatchReader::new(Box::new(EmptyBatchReader::new()))
            .into_pyarrow(py)
            .map_err(|error| error.to_string())?
            .unbind();
        let bound = stream.bind(py);
        probe_stage(
            py,
            AdapterStage::Import,
            GilExpectation::AttachedBlocksProgress,
            || {
                test_invoke_import_hold_probe(py, bound)
                    .map(|_| ())
                    .map_err(|error| format!("{error:?}"))
            },
        )
    })?;

    for (stage, label) in [
        (AdapterStage::Parse, "detached parse"),
        (AdapterStage::Compute, "detached compute"),
    ] {
        with_python(|py| {
            let stream = PyRecordBatchReader::new(Box::new(EmptyBatchReader::new()))
                .into_pyarrow(py)
                .map_err(|error| error.to_string())?
                .unbind();
            probe_stage(py, stage, GilExpectation::DetachedAllowsProgress, || {
                call_native_empty(py, minimal_empty_request_jcs(), stream.clone_ref(py))
            })
            .map_err(|error| format!("{label}: {error}"))
        })?;
    }

    with_python(|py| {
        probe_stage(
            py,
            AdapterStage::Export,
            GilExpectation::AttachedBlocksProgress,
            || {
                test_invoke_export_hold_probe(py, Vec::new())
                    .map(|_| ())
                    .map_err(|error| format!("{error:?}"))
            },
        )
    })?;

    with_python(|py| {
        let stream = PyRecordBatchReader::new(Box::new(EmptyBatchReader::new()))
            .into_pyarrow(py)
            .map_err(|error| error.to_string())?;
        let module = PyModule::import(py, "gateway_compute").map_err(|error| error.to_string())?;
        let func = module
            .getattr("_canonical_row_hashes_v2_native")
            .map_err(|error| error.to_string())?;
        func.call1((minimal_empty_request_jcs(), stream))
            .map(|_| ())
            .map_err(|error| error.to_string())
    })?;

    test_hooks::clear_hold();
    test_hooks::clear_panic_stage();
    with_python(|py| {
        py.import("gc")
            .map_err(|error| error.to_string())?
            .call_method0("collect")
            .map_err(|error| error.to_string())?;
        Ok(())
    })?;
    Ok(())
}

#[test]
fn kernel_component_gil_boundaries_low_concurrency() -> Result<(), String> {
    let _guard = gil_boundary_serial_lock()?;
    run_python_thread_progress_suite()?;
    for run in 0..3 {
        kernel_component_gil_boundaries_inner()
            .map_err(|error| format!("low-concurrency gil boundary run {run} failed: {error}"))?;
        thread::yield_now();
    }
    // Lifecycle: real probe_stage path after stage hit + work error must join worker.
    with_python(|py| {
        let result = super::gil_controller::probe_stage(
            py,
            AdapterStage::Import,
            super::gil_controller::GilExpectation::AttachedBlocksProgress,
            || {
                crate::adapter::test_invoke_hold_only(AdapterStage::Import);
                Err("deliberate post-hit work failure".to_string())
            },
        );
        match result {
            Err(error) if error.contains("deliberate post-hit work failure") => {
                if !test_hooks::hold_is_clear() {
                    return Err("hold not cleared after real-path work failure".to_string());
                }
                Ok(())
            }
            Err(error) => Err(format!("unexpected probe_stage error: {error}")),
            Ok(()) => Err("expected probe_stage to fail after stage hit".to_string()),
        }
    })?;
    Ok(())
}
