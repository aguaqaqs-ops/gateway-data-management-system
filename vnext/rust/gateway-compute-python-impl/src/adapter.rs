use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

use arrow_array::RecordBatch;
use arrow_array::RecordBatchReader;
use arrow_schema::{ArrowError, Schema};
use gateway_compute_core::{
    ComputeFailure, ComputeFailureCode, canonical_row_hashes_v1, parse_request,
};
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatchReader;

use crate::errors::failure_to_pyerr;

fn run_with_panic_boundary<F, T>(f: F) -> Result<T, ComputeFailure>
where
    F: FnOnce() -> Result<T, ComputeFailure>,
{
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(result) => result,
        Err(_) => Err(ComputeFailure::new(ComputeFailureCode::NativePanic)),
    }
}

fn import_arrow_stream(
    _py: Python<'_>,
    input_stream: &Bound<'_, PyAny>,
) -> Result<Box<dyn RecordBatchReader + Send>, ComputeFailure> {
    run_with_panic_boundary(|| {
        PyRecordBatchReader::extract(input_stream.as_borrowed())
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::ArrowStreamImportFailed))
            .and_then(|reader| {
                reader
                    .into_reader()
                    .map_err(|_| ComputeFailure::new(ComputeFailureCode::ArrowStreamImportFailed))
            })
    })
}

fn export_arrow_stream(
    py: Python<'_>,
    reader: OutputBatchReader,
    result_jcs: Vec<u8>,
) -> Result<(Py<PyAny>, Vec<u8>), ComputeFailure> {
    run_with_panic_boundary(|| {
        PyRecordBatchReader::new(Box::new(reader))
            .into_pyarrow(py)
            .map(|output| (output.unbind(), result_jcs))
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::ArrowStreamExportFailed))
    })
}

fn detached_parse_and_compute(
    request_jcs: &[u8],
    boxed_reader: Box<dyn RecordBatchReader + Send>,
) -> Result<(OutputBatchReader, Vec<u8>), ComputeFailure> {
    run_with_panic_boundary(|| {
        let request = parse_request(request_jcs)?;
        canonical_row_hashes_v1(&request, boxed_reader).map(|output| {
            (
                OutputBatchReader::new(output.output_batches),
                output.result_jcs,
            )
        })
    })
}

struct OutputBatchReader {
    schema: Arc<Schema>,
    batches: Vec<RecordBatch>,
    index: usize,
}

impl OutputBatchReader {
    fn new(batches: Vec<RecordBatch>) -> Self {
        let schema = batches
            .first()
            .map(RecordBatch::schema)
            .unwrap_or_else(|| Arc::new(Schema::empty()));
        Self {
            schema,
            batches,
            index: 0,
        }
    }
}

impl RecordBatchReader for OutputBatchReader {
    fn schema(&self) -> Arc<Schema> {
        self.schema.clone()
    }
}

impl Iterator for OutputBatchReader {
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

pub fn canonical_row_hashes_v1_native(
    py: Python<'_>,
    request_jcs: &[u8],
    input_stream: &Bound<'_, PyAny>,
) -> PyResult<(Py<PyAny>, Vec<u8>)> {
    let boxed_reader = match import_arrow_stream(py, input_stream) {
        Ok(reader) => reader,
        Err(failure) => return Err(failure_to_pyerr(py, failure)),
    };
    let request_jcs_owned = request_jcs.to_vec();

    let detached_result =
        py.detach(|| detached_parse_and_compute(&request_jcs_owned, boxed_reader));

    match detached_result {
        Ok((reader, result_jcs)) => match export_arrow_stream(py, reader, result_jcs) {
            Ok(result) => Ok(result),
            Err(failure) => Err(failure_to_pyerr(py, failure)),
        },
        Err(failure) => Err(failure_to_pyerr(py, failure)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[allow(clippy::panic)]
    #[allow(clippy::unwrap_used)]
    fn run_with_panic_boundary_catches_panic_as_native_panic() {
        let result = run_with_panic_boundary(|| -> Result<(), ComputeFailure> {
            panic!("deliberate test panic");
        });
        assert_eq!(result.unwrap_err().code, ComputeFailureCode::NativePanic);
    }
}
