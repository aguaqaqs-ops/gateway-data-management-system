//! Owned Arrow C Stream entry point for records artifact validation.

use std::any::Any;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use arrow_array::{RecordBatch, RecordBatchReader};
use arrow_schema::{ArrowError, SchemaRef};
use gateway_compute_core::comparison::{
    CanonicalBatchSide, KernelContext, OrderedBatchPair, OrderedKernelResult,
    ParsedComparisonPolicy, StandardComputation, compare_ordered_batches, compare_standard_table,
    parse_comparison_policy, summarize_unchanged_ordered_batches,
};
use gateway_compute_core::{
    BuiltRecords, RecordsBatchValidator, TableFactsInput, build_blank_records,
    build_ordered_records, build_standard_records, build_standard_records_from_ordered,
    digest_facts_core_json, digest_table_fact_json, json_metadata_upper, json_size,
    ordered_metadata_json, standard_metadata_json,
};
use pyo3::exceptions::{
    PyInterruptedError, PyMemoryError, PyRuntimeError, PyTimeoutError, PyValueError,
};
use pyo3::prelude::*;
use pyo3::types::{PyList, PyModule, PyString};
use pyo3_arrow::PyRecordBatchReader;

use crate::{
    CancelWatch, adapter_boundary, deadline_instant, python_adapter_control, register_cancel_probe,
    shared_parser_pool,
};

enum ComparisonResult {
    Standard(StandardComputation),
    Ordered(OrderedKernelResult),
}

struct PythonChargeOwner {
    charge: Mutex<Option<Py<PyAny>>>,
    _parent: Option<Arc<PythonChargeOwner>>,
}

impl PythonChargeOwner {
    fn shrink_to(&self, py: Python<'_>, retained_bytes: usize) -> PyResult<()> {
        let slot = self
            .charge
            .lock()
            .map_err(|_| PyRuntimeError::new_err("comparison charge lock poisoned"))?;
        let charge = slot.as_ref().ok_or_else(closed_handle)?;
        charge
            .bind(py)
            .call_method1("shrink_to", (retained_bytes,))?;
        Ok(())
    }
}

#[pyclass]
struct ComparisonOperation {
    context: Arc<KernelContext>,
    initial_budget_bytes: usize,
    active: Arc<AtomicUsize>,
    owner: Option<Arc<PythonChargeOwner>>,
    watch: Arc<CancelWatch>,
    deadline: Option<Instant>,
}

#[pymethods]
impl ComparisonOperation {
    fn close(&mut self) {
        self.owner = None;
    }

    fn seal(&self, py: Python<'_>) -> PyResult<usize> {
        if self.active.load(Ordering::Acquire) != 0 {
            return Err(PyValueError::new_err(
                "comparison operation has active native work",
            ));
        }
        self.context.seal();
        self.reconcile_retained(py)
    }

    fn reconcile_retained(&self, py: Python<'_>) -> PyResult<usize> {
        if !self.context.is_sealed() {
            return Err(PyValueError::new_err("comparison operation is not sealed"));
        }
        let owner = self.owner.as_ref().ok_or_else(closed_handle)?;
        let retained = self
            .initial_budget_bytes
            .checked_sub(self.context.remaining_bytes())
            .ok_or_else(|| PyRuntimeError::new_err("comparison budget accounting overflow"))?;
        owner.shrink_to(py, retained)?;
        Ok(retained)
    }
}

struct OperationUse(Arc<AtomicUsize>);

impl OperationUse {
    fn begin(context: &KernelContext, active: &Arc<AtomicUsize>) -> PyResult<Self> {
        if context.is_sealed() {
            return Err(PyValueError::new_err("comparison operation is sealed"));
        }
        active.fetch_add(1, Ordering::AcqRel);
        Ok(Self(Arc::clone(active)))
    }
}

impl Drop for OperationUse {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

impl Drop for PythonChargeOwner {
    fn drop(&mut self) {
        if let Ok(slot) = self.charge.get_mut()
            && let Some(charge) = slot.take()
        {
            let _ = Python::try_attach(|py| charge.bind(py).call_method0("close"));
        }
    }
}

#[pyclass]
struct ComparisonRecordsHandle {
    result: Option<Arc<ComparisonResult>>,
    standard: Option<BuiltRecords>,
    ordered: Option<BuiltRecords>,
    blank: Option<BuiltRecords>,
    context: Arc<KernelContext>,
    active: Arc<AtomicUsize>,
    owner: Option<Arc<PythonChargeOwner>>,
    _watch: Arc<CancelWatch>,
}

#[pymethods]
impl ComparisonRecordsHandle {
    fn close(&mut self) {
        self.result = None;
        self.standard = None;
        self.ordered = None;
        self.blank = None;
        self.owner = None;
    }

    fn metadata_json(&self, py: Python<'_>) -> PyResult<Py<PyString>> {
        let _use = OperationUse::begin(&self.context, &self.active)?;
        let result = self.result.as_ref().ok_or_else(closed_handle)?;
        let estimated = match result.as_ref() {
            ComparisonResult::Standard(_) => 4096,
            ComparisonResult::Ordered(result) => {
                json_size(&result.facts_metadata).map_err(comparison_error)?
            }
        };
        let charge = estimated
            .checked_mul(3)
            .and_then(|size| size.checked_add(4096))
            .ok_or_else(|| PyMemoryError::new_err("comparison metadata budget overflow"))?;
        let _scratch = self
            .context
            .reserve(charge)
            .map_err(|error| comparison_error(error.to_string()))?;
        let raw = match result.as_ref() {
            ComparisonResult::Standard(result) => standard_metadata_json(result),
            ComparisonResult::Ordered(result) => ordered_metadata_json(result),
        }
        .map_err(PyValueError::new_err)?;
        Ok(PyString::new(py, &raw).unbind())
    }

    fn table_fact_digest(
        &self,
        py: Python<'_>,
        metadata_json: &str,
        max_jcs_row_bytes: usize,
    ) -> PyResult<String> {
        let _use = OperationUse::begin(&self.context, &self.active)?;
        let result = self.result.as_ref().ok_or_else(closed_handle)?.clone();
        let context = Arc::clone(&self.context);
        let _metadata_copy = context
            .reserve(json_metadata_upper(metadata_json).map_err(comparison_error)?)
            .map_err(|error| comparison_error(error.to_string()))?;
        let raw = metadata_json.to_string();
        py.detach(|| {
            let input = match result.as_ref() {
                ComparisonResult::Standard(result) => TableFactsInput {
                    metadata_json: &raw,
                    standard: Some(result),
                    ordered: None,
                },
                ComparisonResult::Ordered(result) => TableFactsInput {
                    metadata_json: &raw,
                    standard: None,
                    ordered: Some(result),
                },
            };
            digest_table_fact_json(input, max_jcs_row_bytes, &context)
        })
        .map(|digest| digest.to_string())
        .map_err(comparison_error)
    }

    fn record_batches(&self, py: Python<'_>, family: &str) -> PyResult<Py<PyAny>> {
        let built = match family {
            "STANDARD" => self.standard.as_ref(),
            "ORDERED" => self.ordered.as_ref(),
            "BLANK" => self.blank.as_ref(),
            _ => return Err(PyValueError::new_err("unknown records family")),
        }
        .ok_or_else(closed_handle)?;
        let reader = BatchVecReader {
            schema: Arc::clone(&built.schema),
            batches: built.batches.iter().cloned().collect(),
        };
        let bridge = Py::new(py, PyRecordBatchReader::new(Box::new(reader)))?;
        let pyarrow = py.import("pyarrow")?;
        let exported = pyarrow
            .getattr("RecordBatchReader")?
            .call_method1("from_stream", (bridge,))?;
        Ok(exported.unbind())
    }

    fn family_summary(&self, family: &str) -> PyResult<(usize, String)> {
        let built = match family {
            "STANDARD" => self.standard.as_ref(),
            "ORDERED" => self.ordered.as_ref(),
            "BLANK" => self.blank.as_ref(),
            _ => return Err(PyValueError::new_err("unknown records family")),
        }
        .ok_or_else(closed_handle)?;
        Ok((built.record_count, built.content_digest.to_string()))
    }

    fn is_sealed(&self) -> bool {
        self.context.is_sealed()
    }
}

fn closed_handle() -> PyErr {
    PyValueError::new_err("comparison records handle is closed")
}

fn comparison_error(error: String) -> PyErr {
    if error.contains("RESOURCE_LIMIT_EXCEEDED") || error.contains("budget exceeded") {
        PyMemoryError::new_err(error)
    } else if error.contains("COMPARISON_CANCELLED") {
        PyInterruptedError::new_err(error)
    } else if error.contains("COMPARISON_DEADLINE_EXCEEDED") {
        PyTimeoutError::new_err(error)
    } else {
        PyValueError::new_err(error)
    }
}

struct BatchVecReader {
    schema: SchemaRef,
    batches: VecDeque<RecordBatch>,
}

impl Iterator for BatchVecReader {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        self.batches.pop_front().map(Ok)
    }
}

impl RecordBatchReader for BatchVecReader {
    fn schema(&self) -> SchemaRef {
        Arc::clone(&self.schema)
    }
}

fn read_stream(
    py: Python<'_>,
    stream: PyRecordBatchReader,
    context: &Arc<KernelContext>,
    total_input_bytes: &mut usize,
    max_input_bytes: usize,
) -> PyResult<(SchemaRef, Vec<RecordBatch>)> {
    let schema = stream.schema_ref()?;
    let mut reader = stream.into_reader()?;
    let mut input_bytes = *total_input_bytes;
    let batches = py
        .detach(|| {
            let mut batches = Vec::new();
            let mut rows = 0usize;
            loop {
                context.check().map_err(|error| error.to_string())?;
                let Some(batch) = reader.next() else { break };
                let batch = batch.map_err(|error| error.to_string())?;
                if batches.len() >= 4096 {
                    return Err("RESOURCE_LIMIT_EXCEEDED: too many input batches".to_string());
                }
                rows = rows
                    .checked_add(batch.num_rows())
                    .ok_or_else(|| "RESOURCE_LIMIT_EXCEEDED: input rows overflow".to_string())?;
                if rows > 10_000_000 {
                    return Err("RESOURCE_LIMIT_EXCEEDED: too many input rows".to_string());
                }
                let batch_bytes = batch
                    .columns()
                    .iter()
                    .try_fold(512usize, |sum, array| {
                        sum.checked_add(array.to_data().get_slice_memory_size().ok()?)
                    })
                    .ok_or_else(|| "RESOURCE_LIMIT_EXCEEDED: input size overflow".to_string())?;
                input_bytes = input_bytes
                    .checked_add(batch_bytes)
                    .ok_or_else(|| "RESOURCE_LIMIT_EXCEEDED: input size overflow".to_string())?;
                if input_bytes > max_input_bytes {
                    return Err("RESOURCE_LIMIT_EXCEEDED: input owner charge exceeded".to_string());
                }
                batches.push(batch);
            }
            context.check().map_err(|error| error.to_string())?;
            Ok::<Vec<RecordBatch>, String>(batches)
        })
        .map_err(comparison_error)?;
    *total_input_bytes = input_bytes;
    Ok((schema, batches))
}

#[pyfunction]
#[pyo3(signature = (remaining_bytes, operation_charge, cancel_probe, deadline_monotonic=None))]
fn _begin_comparison_operation_native(
    py: Python<'_>,
    remaining_bytes: usize,
    operation_charge: Py<PyAny>,
    cancel_probe: Py<PyAny>,
    deadline_monotonic: Option<f64>,
) -> PyResult<ComparisonOperation> {
    match adapter_boundary(|| {
        shared_parser_pool(None)?;
        let owner = Arc::new(PythonChargeOwner {
            charge: Mutex::new(Some(operation_charge)),
            _parent: None,
        });
        let deadline = deadline_instant(py, deadline_monotonic)?;
        let watch = Arc::new(register_cancel_probe(py, &cancel_probe)?);
        python_adapter_control(&watch, deadline)?;
        Ok(ComparisonOperation {
            context: Arc::new(KernelContext::new(
                remaining_bytes,
                Arc::clone(&watch.cancelled),
                deadline,
            )),
            initial_budget_bytes: remaining_bytes,
            active: Arc::new(AtomicUsize::new(0)),
            owner: Some(owner),
            watch,
            deadline,
        })
    }) {
        Ok(result) => result,
        Err(()) => Err(PyRuntimeError::new_err(
            "comparison operation adapter panicked",
        )),
    }
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (operation, kind, table_name, before_stream, current_stream, policy_json, detail_policy, max_records, max_sort_bytes, max_output_bytes, max_input_bytes, owner_charge))]
fn _compare_records_native(
    py: Python<'_>,
    operation: PyRef<'_, ComparisonOperation>,
    kind: &str,
    table_name: &str,
    before_stream: PyRecordBatchReader,
    current_stream: PyRecordBatchReader,
    policy_json: &str,
    detail_policy: &str,
    max_records: usize,
    max_sort_bytes: usize,
    max_output_bytes: usize,
    max_input_bytes: usize,
    owner_charge: Py<PyAny>,
) -> PyResult<ComparisonRecordsHandle> {
    match adapter_boundary(|| {
        let pool = shared_parser_pool(None)?;
        let parent = operation.owner.as_ref().ok_or_else(closed_handle)?.clone();
        let context = Arc::clone(&operation.context);
        let active = Arc::clone(&operation.active);
        let _use = OperationUse::begin(&context, &active)?;
        let watch = Arc::clone(&operation.watch);
        let deadline = operation.deadline;
        let owner = Arc::new(PythonChargeOwner {
            charge: Mutex::new(Some(owner_charge)),
            _parent: Some(parent),
        });
        python_adapter_control(&watch, deadline)?;
        let policy =
            parse_comparison_policy(kind, policy_json, &context).map_err(PyValueError::new_err)?;
        let mut input_bytes = 0;
        let (before_schema, before) = read_stream(
            py,
            before_stream,
            &context,
            &mut input_bytes,
            max_input_bytes,
        )?;
        let (current_schema, current) = read_stream(
            py,
            current_stream,
            &context,
            &mut input_bytes,
            max_input_bytes,
        )?;
        let external: Arc<dyn Any + Send + Sync> = owner.clone();
        let output = py
            .detach(|| {
                pool.install(|| match policy {
                    ParsedComparisonPolicy::Standard(options) => {
                        let result = compare_standard_table(
                            CanonicalBatchSide::new(before_schema, &before),
                            CanonicalBatchSide::new(current_schema, &current),
                            &options,
                            &context,
                        )
                        .map_err(|error| error.to_string())?;
                        let standard = build_standard_records(
                            table_name,
                            &result,
                            detail_policy,
                            max_records,
                            max_sort_bytes,
                            max_output_bytes,
                            &context,
                            Some(external),
                        )?;
                        Ok((ComparisonResult::Standard(result), standard, None, None))
                    }
                    ParsedComparisonPolicy::Ordered(options) => {
                        let result = compare_ordered_batches(
                            OrderedBatchPair {
                                before: Some(&before),
                                current: Some(&current),
                                before_schema: Some(before_schema),
                                current_schema: Some(current_schema),
                                options: &options,
                            },
                            &context,
                        )
                        .map_err(|error| error.to_string())?;
                        let standard = build_standard_records_from_ordered(
                            table_name,
                            &result,
                            detail_policy,
                            max_records,
                            max_sort_bytes,
                            max_output_bytes,
                            &context,
                            Some(external.clone()),
                        )?;
                        let ordered = build_ordered_records(
                            table_name,
                            &result,
                            detail_policy,
                            max_records,
                            max_sort_bytes,
                            max_output_bytes,
                            &context,
                            Some(external.clone()),
                        )?;
                        let blank = build_blank_records(
                            table_name,
                            &result,
                            detail_policy,
                            max_records,
                            max_sort_bytes,
                            max_output_bytes,
                            &context,
                            Some(external),
                        )?;
                        Ok((
                            ComparisonResult::Ordered(result),
                            standard,
                            Some(ordered),
                            Some(blank),
                        ))
                    }
                })
            })
            .map_err(comparison_error)?;
        python_adapter_control(&watch, deadline)?;
        Ok(ComparisonRecordsHandle {
            result: Some(Arc::new(output.0)),
            standard: Some(output.1),
            ordered: output.2,
            blank: output.3,
            context,
            active,
            owner: Some(owner),
            _watch: watch,
        })
    }) {
        Ok(result) => result,
        Err(()) => Err(PyRuntimeError::new_err(
            "comparison records adapter panicked",
        )),
    }
}

#[pyfunction]
fn _summarize_unchanged_ordered_native(
    py: Python<'_>,
    operation: PyRef<'_, ComparisonOperation>,
    current_stream: PyRecordBatchReader,
    policy_json: &str,
    max_input_bytes: usize,
    input_owner_charge: Py<PyAny>,
) -> PyResult<(String, String, String, String, usize)> {
    match adapter_boundary(|| {
        let pool = shared_parser_pool(None)?;
        let parent = operation.owner.as_ref().ok_or_else(closed_handle)?.clone();
        let input_owner = Arc::new(PythonChargeOwner {
            charge: Mutex::new(Some(input_owner_charge)),
            _parent: Some(parent),
        });
        let context = Arc::clone(&operation.context);
        let _use = OperationUse::begin(&context, &operation.active)?;
        let watch = Arc::clone(&operation.watch);
        let deadline = operation.deadline;
        python_adapter_control(&watch, deadline)?;
        let options = match parse_comparison_policy("ordered", policy_json, &context)
            .map_err(PyValueError::new_err)?
        {
            ParsedComparisonPolicy::Ordered(options) => options,
            ParsedComparisonPolicy::Standard(_) => {
                return Err(PyValueError::new_err("ordered policy required"));
            }
        };
        let mut input_bytes = 0;
        let (schema, batches) = read_stream(
            py,
            current_stream,
            &context,
            &mut input_bytes,
            max_input_bytes,
        )?;
        let summary = py
            .detach(|| {
                pool.install(|| {
                    summarize_unchanged_ordered_batches(
                        CanonicalBatchSide::new(schema, &batches),
                        &options,
                        &context,
                    )
                    .map_err(|error| error.to_string())
                })
            })
            .map_err(comparison_error)?;
        python_adapter_control(&watch, deadline)?;
        drop(input_owner);
        Ok((
            summary.before_ordered_digest,
            summary.current_ordered_digest,
            summary.before_occupancy_digest,
            summary.current_occupancy_digest,
            summary.row_count,
        ))
    }) {
        Ok(result) => result,
        Err(()) => Err(PyRuntimeError::new_err(
            "unchanged ordered adapter panicked",
        )),
    }
}

#[pyfunction]
fn _facts_core_digest_native(
    py: Python<'_>,
    operation: PyRef<'_, ComparisonOperation>,
    handles: Bound<'_, PyList>,
    metadata_jsons: Bound<'_, PyList>,
    algorithm_version: &str,
    summary_json: &str,
    max_jcs_row_bytes: usize,
) -> PyResult<String> {
    if handles.len() != metadata_jsons.len() {
        return Err(PyValueError::new_err(
            "facts tables and metadata must align",
        ));
    }
    if operation.owner.is_none() {
        return Err(closed_handle());
    }
    let mut results = Vec::<Arc<ComparisonResult>>::new();
    let mut metadata = Vec::<String>::new();
    let context = Arc::clone(&operation.context);
    let _use = OperationUse::begin(&context, &operation.active)?;
    let mut metadata_upper = json_metadata_upper(summary_json).map_err(comparison_error)?;
    for raw in metadata_jsons.iter() {
        let raw = raw.downcast::<PyString>()?.to_str()?;
        metadata_upper = metadata_upper
            .checked_add(json_metadata_upper(raw).map_err(comparison_error)?)
            .ok_or_else(|| PyMemoryError::new_err("facts metadata budget overflow"))?;
    }
    metadata_upper = metadata_upper
        .checked_add(
            handles
                .len()
                .checked_mul(128)
                .ok_or_else(|| PyMemoryError::new_err("facts handle budget overflow"))?,
        )
        .ok_or_else(|| PyMemoryError::new_err("facts metadata budget overflow"))?;
    let _metadata_copy = context
        .reserve(metadata_upper)
        .map_err(|error| comparison_error(error.to_string()))?;
    for (handle, raw) in handles.iter().zip(metadata_jsons.iter()) {
        let handle = handle.extract::<PyRef<'_, ComparisonRecordsHandle>>()?;
        let result = handle.result.as_ref().ok_or_else(closed_handle)?.clone();
        if !Arc::ptr_eq(&context, &handle.context) {
            return Err(PyValueError::new_err(
                "facts tables must share one operation",
            ));
        }
        results.push(result);
        metadata.push(raw.extract::<String>()?);
    }
    let algorithm_version = algorithm_version.to_string();
    let summary_json = summary_json.to_string();
    py.detach(|| {
        let inputs = results
            .iter()
            .zip(&metadata)
            .map(|(result, raw)| match result.as_ref() {
                ComparisonResult::Standard(result) => TableFactsInput {
                    metadata_json: raw,
                    standard: Some(result),
                    ordered: None,
                },
                ComparisonResult::Ordered(result) => TableFactsInput {
                    metadata_json: raw,
                    standard: None,
                    ordered: Some(result),
                },
            })
            .collect::<Vec<_>>();
        digest_facts_core_json(
            &algorithm_version,
            &summary_json,
            &inputs,
            max_jcs_row_bytes,
            &context,
        )
    })
    .map(|digest| digest.to_string())
    .map_err(comparison_error)
}

#[pyfunction]
#[pyo3(signature = (arrow_stream, max_records, max_batch_bytes, cancel_probe, deadline_monotonic=None))]
fn _validate_records_batches_native(
    py: Python<'_>,
    arrow_stream: PyRecordBatchReader,
    max_records: usize,
    max_batch_bytes: usize,
    cancel_probe: Py<PyAny>,
    deadline_monotonic: Option<f64>,
) -> PyResult<(String, String, String, usize, String)> {
    match adapter_boundary(|| {
        shared_parser_pool(None)?;
        if max_records == 0 || max_batch_bytes == 0 {
            return Err(PyValueError::new_err("records budgets must be positive"));
        }
        let deadline = deadline_instant(py, deadline_monotonic)?;
        let watch = register_cancel_probe(py, &cancel_probe)?;
        python_adapter_control(&watch, deadline)?;
        let schema = arrow_stream.schema_ref()?;
        let mut reader = arrow_stream.into_reader()?;
        let result = py.detach(|| {
            let mut validator = RecordsBatchValidator::new(schema, max_records, max_batch_bytes)?;
            let check = || {
                if watch.cancelled.load(Ordering::Relaxed) {
                    return Err("COMPARISON_CANCELLED".to_string());
                }
                if deadline.is_some_and(|end: Instant| Instant::now() >= end) {
                    return Err("COMPARISON_DEADLINE_EXCEEDED".to_string());
                }
                Ok(())
            };
            loop {
                check()?;
                let Some(batch) = reader.next() else { break };
                let batch =
                    batch.map_err(|error| format!("records Arrow batch failed: {error}"))?;
                let bytes = batch
                    .columns()
                    .iter()
                    .try_fold(0usize, |sum, array| {
                        sum.checked_add(array.to_data().get_slice_memory_size().ok()?)
                    })
                    .ok_or_else(|| "RESOURCE_LIMIT_EXCEEDED".to_string())?;
                if bytes > max_batch_bytes {
                    return Err("RESOURCE_LIMIT_EXCEEDED".to_string());
                }
                validator.push_checked(&batch, || check())?;
            }
            check()?;
            validator.finish()
        });
        python_adapter_control(&watch, deadline)?;
        let summary = result.map_err(|error| match error.as_str() {
            "COMPARISON_CANCELLED" => PyInterruptedError::new_err(error),
            "COMPARISON_DEADLINE_EXCEEDED" => PyTimeoutError::new_err(error),
            "RESOURCE_LIMIT_EXCEEDED" => PyMemoryError::new_err(error),
            _ => PyValueError::new_err(error),
        })?;
        Ok((
            summary.family,
            summary.schema_version,
            summary.row_diff_detail_policy,
            summary.record_count,
            summary.content_digest.to_string(),
        ))
    }) {
        Ok(result) => result,
        Err(()) => Err(PyRuntimeError::new_err(
            "records validation adapter panicked",
        )),
    }
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<ComparisonOperation>()?;
    module.add_class::<ComparisonRecordsHandle>()?;
    module.add_function(wrap_pyfunction!(
        _begin_comparison_operation_native,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(_compare_records_native, module)?)?;
    module.add_function(wrap_pyfunction!(
        _summarize_unchanged_ordered_native,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(_facts_core_digest_native, module)?)?;
    module.add_function(wrap_pyfunction!(_validate_records_batches_native, module)?)?;
    Ok(())
}
