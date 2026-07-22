#![forbid(unsafe_code)]

mod common;

use std::sync::Arc;

use arrow_array::RecordBatch;
use arrow_array::RecordBatchReader;
use arrow_array::StringArray;
use arrow_schema::{ArrowError, DataType, Field, Schema};
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatchReader;

use common::{minimal_empty_request_jcs, with_python};

struct MultiBatchReader {
    schema: Arc<Schema>,
    batches: Vec<RecordBatch>,
    index: usize,
}

impl MultiBatchReader {
    fn large_string_batches(batch_count: usize, rows_per_batch: usize) -> Result<Self, String> {
        let schema = Arc::new(Schema::new(vec![Field::new("v", DataType::Utf8, false)]));
        let mut batches = Vec::with_capacity(batch_count);
        for batch_index in 0..batch_count {
            let owned: Vec<String> = (0..rows_per_batch)
                .map(|row| format!("batch-{batch_index}-row-{row}"))
                .collect();
            let refs: Vec<&str> = owned.iter().map(String::as_str).collect();
            let array = StringArray::from(refs);
            let batch = RecordBatch::try_new(schema.clone(), vec![Arc::new(array)])
                .map_err(|error| error.to_string())?;
            batches.push(batch);
        }
        Ok(Self {
            schema,
            batches,
            index: 0,
        })
    }
}

impl RecordBatchReader for MultiBatchReader {
    fn schema(&self) -> Arc<Schema> {
        self.schema.clone()
    }
}

impl Iterator for MultiBatchReader {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.index >= self.batches.len() {
            return None;
        }
        let batch = self.batches[self.index].clone();
        self.index += 1;
        Some(Ok(batch))
    }
}

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

static GIL_PROBE_PROGRESS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static GIL_PROBE_STOP: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

#[test]
fn concurrent_python_thread_makes_progress_during_native_compute() -> Result<(), String> {
    use std::sync::atomic::Ordering;
    use std::thread;

    GIL_PROBE_PROGRESS.store(0, Ordering::SeqCst);
    GIL_PROBE_STOP.store(false, Ordering::SeqCst);

    let probe = thread::spawn(|| {
        while !GIL_PROBE_STOP.load(Ordering::SeqCst) {
            Python::attach(|_py| {
                GIL_PROBE_PROGRESS.fetch_add(1, Ordering::SeqCst);
            });
        }
    });

    let compute_result = with_python(|py| {
        let request_jcs = br#"{"arrow_mapping_schema_version":1,"canonical_encoding_version":1,"contract_binding":{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary","semantic_version":"1.0.0"},"declared_table_schema":{"fields":[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]},"request_schema_version":1}"#;
        let reader = MultiBatchReader::large_string_batches(8, 256)?;
        let stream = PyRecordBatchReader::new(Box::new(reader))
            .into_pyarrow(py)
            .map_err(|error| error.to_string())?;
        let module = PyModule::import(py, "gateway_compute").map_err(|error| error.to_string())?;
        let func = module
            .getattr("_canonical_row_hashes_v1_native")
            .map_err(|error| error.to_string())?;
        func.call1((request_jcs, stream))
            .map(|_| ())
            .map_err(|error| error.to_string())
    });

    GIL_PROBE_STOP.store(true, Ordering::SeqCst);
    probe
        .join()
        .map_err(|_| "gil probe thread panicked".to_string())?;
    compute_result?;

    let progress = GIL_PROBE_PROGRESS.load(Ordering::SeqCst);
    if progress < 1_000 {
        return Err(format!(
            "expected concurrent GIL progress during detached compute, got {progress}"
        ));
    }
    Ok(())
}

#[test]
fn empty_table_native_call_completes_under_attach() -> Result<(), String> {
    with_python(|py| {
        let stream = PyRecordBatchReader::new(Box::new(EmptyBatchReader::new()))
            .into_pyarrow(py)
            .map_err(|error| error.to_string())?;
        let module = PyModule::import(py, "gateway_compute").map_err(|error| error.to_string())?;
        let func = module
            .getattr("_canonical_row_hashes_v1_native")
            .map_err(|error| error.to_string())?;
        func.call1((minimal_empty_request_jcs(), stream))
            .map(|_| ())
            .map_err(|error| error.to_string())
    })
}
