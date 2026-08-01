use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

use arrow_array::RecordBatch;
use arrow_array::RecordBatchReader;
use arrow_schema::{ArrowError, Schema};
use gateway_compute_core::{
    ComputeFailure, ComputeFailureCode, canonical_row_hashes_v2, parse_request,
};
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatchReader;

use crate::errors::failure_to_pyerr;

#[cfg(test)]
pub mod test_hooks {
    use std::cell::RefCell;
    use std::sync::mpsc::{Receiver, Sender};
    use std::time::Duration;

    thread_local! {
        static PANIC_STAGE: std::cell::Cell<u8> = const { std::cell::Cell::new(AdapterStage::None as u8) };
        static HOLD_STAGE: std::cell::Cell<u8> = const { std::cell::Cell::new(AdapterStage::None as u8) };
        static HOLD_SETUP: RefCell<Option<HoldSetup>> = const { RefCell::new(None) };
    }

    struct HoldSetup {
        stage: AdapterStage,
        entered_tx: Sender<()>,
        release_rx: Receiver<()>,
    }

    pub const HOLD_RELEASE_TIMEOUT: Duration = Duration::from_secs(5);

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    #[repr(u8)]
    pub enum AdapterStage {
        None = 0,
        Import = 1,
        Parse = 2,
        Compute = 3,
        Export = 4,
    }

    pub fn set_panic_stage(stage: AdapterStage) {
        PANIC_STAGE.with(|cell| cell.set(stage as u8));
    }

    pub fn clear_panic_stage() {
        PANIC_STAGE.with(|cell| cell.set(AdapterStage::None as u8));
    }

    pub fn set_hold(stage: AdapterStage, entered_tx: Sender<()>, release_rx: Receiver<()>) {
        HOLD_STAGE.with(|cell| cell.set(stage as u8));
        HOLD_SETUP.with(|cell| {
            *cell.borrow_mut() = Some(HoldSetup {
                stage,
                entered_tx,
                release_rx,
            });
        });
    }

    pub fn clear_hold() {
        HOLD_STAGE.with(|cell| cell.set(AdapterStage::None as u8));
        HOLD_SETUP.with(|cell| *cell.borrow_mut() = None);
    }

    pub fn hold_is_clear() -> bool {
        HOLD_STAGE.with(|cell| cell.get() == AdapterStage::None as u8)
            && HOLD_SETUP.with(|cell| cell.borrow().is_none())
    }

    pub(crate) fn maybe_panic(stage: AdapterStage) {
        let active = PANIC_STAGE.with(|cell| cell.get());
        if active == stage as u8 {
            #[allow(clippy::panic)]
            {
                panic!("deliberate test panic at {stage:?}");
            }
        }
    }

    pub(crate) fn maybe_hold(stage: AdapterStage) {
        let active = HOLD_STAGE.with(|cell| cell.get());
        if active != stage as u8 {
            return;
        }
        HOLD_SETUP.with(|cell| {
            let mut setup = cell.borrow_mut();
            let Some(setup) = setup.as_mut() else {
                #[allow(clippy::panic)]
                {
                    panic!("hold stage {stage:?} active but no setup installed");
                }
            };
            if setup.stage != stage {
                return;
            }
            if setup.entered_tx.send(()).is_err() {
                #[allow(clippy::panic)]
                {
                    panic!("hold stage {stage:?} controller dropped before enter signal");
                }
            }
            match setup.release_rx.recv_timeout(HOLD_RELEASE_TIMEOUT) {
                Ok(()) => {}
                Err(error) => {
                    #[allow(clippy::panic)]
                    {
                        panic!("hold stage {stage:?} not released within timeout: {error}");
                    }
                }
            }
        });
    }
}

#[cfg(test)]
use test_hooks::AdapterStage;

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
        #[cfg(test)]
        {
            test_hooks::maybe_panic(AdapterStage::Import);
            test_hooks::maybe_hold(AdapterStage::Import);
        }
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
        #[cfg(test)]
        {
            test_hooks::maybe_panic(AdapterStage::Export);
            test_hooks::maybe_hold(AdapterStage::Export);
        }
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
        #[cfg(test)]
        {
            test_hooks::maybe_panic(AdapterStage::Parse);
            test_hooks::maybe_hold(AdapterStage::Parse);
        }
        let request = parse_request(request_jcs)?;
        #[cfg(test)]
        {
            test_hooks::maybe_panic(AdapterStage::Compute);
            test_hooks::maybe_hold(AdapterStage::Compute);
        }
        canonical_row_hashes_v2(&request, boxed_reader).map(|output| {
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

pub fn canonical_row_hashes_v2_native(
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
pub(crate) fn test_invoke_hold_only(stage: AdapterStage) {
    test_hooks::maybe_hold(stage);
}

#[cfg(test)]
pub(crate) fn test_invoke_import_hold_probe(
    py: Python<'_>,
    input_stream: &Bound<'_, PyAny>,
) -> Result<Box<dyn RecordBatchReader + Send>, ComputeFailure> {
    import_arrow_stream(py, input_stream)
}

#[cfg(test)]
pub(crate) fn test_invoke_compute_panic_probe(
    request_jcs: &[u8],
    boxed_reader: Box<dyn RecordBatchReader + Send>,
) -> Result<Vec<u8>, ComputeFailure> {
    detached_parse_and_compute(request_jcs, boxed_reader).map(|(_reader, result_jcs)| result_jcs)
}

#[cfg(test)]
pub(crate) fn test_invoke_export_hold_probe(
    py: Python<'_>,
    result_jcs: Vec<u8>,
) -> Result<(Py<PyAny>, Vec<u8>), ComputeFailure> {
    export_arrow_stream(py, OutputBatchReader::new(vec![]), result_jcs)
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
