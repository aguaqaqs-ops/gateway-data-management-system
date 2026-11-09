//! Owned Arrow C Stream entry point for records artifact validation.

use std::any::Any;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use arrow_array::builder::{FixedSizeBinaryBuilder, ListBuilder, StringBuilder};
use arrow_array::{Array, FixedSizeBinaryArray, ListArray, RecordBatch, RecordBatchReader, StringArray};
use arrow_schema::{ArrowError, DataType, Field, Schema, SchemaRef};
use gateway_compute_core::comparison::{
    CanonicalBatchSide, KernelContext, KernelLease, OrderedBatchPair, OrderedKernelResult,
    ParsedComparisonPolicy, StandardComputation, StandardKind, StandardRecordRef,
    compare_ordered_batches, compare_standard_table, parse_comparison_policy,
    summarize_unchanged_ordered_batches,
};
use gateway_compute_core::{
    BuiltRecords, NeutralFacts, RecordsBatchValidator, TableFactsInput, TableFactsSource, build_blank_records,
    export_facts_family, facts_schema, restore_records_batches, validate_cache_metadata,
    build_ordered_records, build_standard_records, build_standard_records_from_ordered,
    charge_arrow_batches, digest_facts_core_json, digest_table_fact_json, json_metadata_upper,
    json_size, ordered_metadata_json, standard_metadata_json,
};
use pyo3::exceptions::{
    PyInterruptedError, PyMemoryError, PyOSError, PyRuntimeError, PyTimeoutError, PyValueError,
};
use pyo3::prelude::*;
use pyo3::types::{PyList, PyModule, PyString};
use pyo3_arrow::PyRecordBatchReader;

use crate::{
    CancelWatch, adapter_boundary, deadline_instant, python_adapter_control, register_cancel_probe,
    shared_parser_pool,
};

// A handle owns one result. Keeping the bounded ordered value in this Arc
// avoids a second heap allocation that would outlive the native parse lease.
#[allow(clippy::large_enum_variant)]
enum ComparisonResult {
    Standard(StandardComputation),
    Ordered(OrderedKernelResult),
    Restored {
        metadata_json: String,
        facts: NeutralFacts,
    },
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
    operation_identity: Option<usize>,
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

    fn require_operation(&self, operation_identity: usize) -> PyResult<()> {
        if self.operation_identity != Some(operation_identity) || self.owner.is_none() {
            return Err(PyValueError::new_err("comparison phase belongs to another operation"));
        }
        if self.context.is_sealed() { return Err(PyValueError::new_err("comparison operation is sealed")); }
        python_adapter_control(&self.watch, self.deadline)
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
            let _ = Python::try_attach(|py| {
                let _ = charge.bind(py).call_method0("close");
            });
        }
    }
}

#[pyclass]
struct ComparisonRecordsHandle {
    result: Option<Arc<ComparisonResult>>,
    standard: Option<BuiltRecords>,
    ordered: Option<BuiltRecords>,
    blank: Option<BuiltRecords>,
    risk_batches: Option<Vec<RecordBatch>>,
    cache_facts: Option<NeutralFacts>,
    cache_metadata: Option<String>,
    cache_created_risk: bool,
    _cache_metadata_lease: Option<KernelLease>,
    _schema_lease: Option<KernelLease>,
    context: Arc<KernelContext>,
    active: Arc<AtomicUsize>,
    owner: Option<Arc<PythonChargeOwner>>,
    _watch: Arc<CancelWatch>,
    operation_identity: Option<usize>,
    phase_timings: (f64, f64, f64),
}

#[pymethods]
impl ComparisonRecordsHandle {
    fn require_operation(&self, operation_identity: usize) -> PyResult<()> {
        if self.operation_identity != Some(operation_identity) || self.owner.is_none() {
            return Err(PyValueError::new_err("comparison table belongs to another operation"));
        }
        self.context.check().map_err(|error| comparison_error(error.to_string()))
    }

    fn phase_timings(&self) -> (f64, f64, f64) {
        self.phase_timings
    }

    fn close(&mut self) {
        self.result = None;
        self.standard = None;
        self.ordered = None;
        self.blank = None;
        self.risk_batches = None;
        self.cache_facts = None;
        self.cache_metadata = None;
        self.cache_created_risk = false;
        self._cache_metadata_lease = None;
        self._schema_lease = None;
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
            ComparisonResult::Restored { metadata_json, .. } => metadata_json.len(),
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
            ComparisonResult::Restored { metadata_json, .. } => Ok(metadata_json.clone()),
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
                    neutral: None,
                },
                ComparisonResult::Ordered(result) => TableFactsInput {
                    metadata_json: &raw,
                    standard: None,
                    ordered: Some(result),
                    neutral: None,
                },
                ComparisonResult::Restored { facts, .. } => TableFactsInput {
                    metadata_json: &raw,
                    standard: None,
                    ordered: None,
                    neutral: Some(facts),
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

    /// Materialize only Risk's standard kind, identity and changed columns in
    /// facts order. The three artifact families have a different sort contract.
    fn prepare_risk_batches(&mut self) -> PyResult<()> {
        if self.risk_batches.is_some() {
            return Ok(());
        }
        let _use = OperationUse::begin(&self.context, &self.active)?;
        let result = self.result.as_ref().ok_or_else(closed_handle)?;
        let (records, order) = match result.as_ref() {
            ComparisonResult::Standard(value) => (&value.records, &value.facts_order),
            ComparisonResult::Ordered(value) => {
                (&value.standard_records, &value.standard_facts_order)
            }
            ComparisonResult::Restored { .. } => {
                return Err(PyValueError::new_err("restored risk view missing"));
            }
        };
        let mut upper = 4096usize;
        for index in order {
            let record = &records[*index];
            upper = upper
                .checked_add(1024)
                .and_then(|size| {
                    size.checked_add(
                        record
                            .row_identity
                            .as_ref()
                            .map_or(0, String::len)
                            .saturating_mul(8),
                    )
                })
                .and_then(|size| {
                    size.checked_add(
                        record
                            .changed_columns
                            .iter()
                            .map(String::len)
                            .sum::<usize>()
                            .saturating_mul(8),
                    )
                })
                .ok_or_else(|| PyMemoryError::new_err("risk view size overflow"))?;
        }
        let lease = self
            .context
            .reserve(upper)
            .map_err(|error| comparison_error(error.to_string()))?;
        let schema = risk_schema();
        let mut batches = Vec::new();
        for chunk in order.chunks(1024) {
            self.context
                .check()
                .map_err(|error| comparison_error(error.to_string()))?;
            let mut kinds = StringBuilder::new();
            let mut identities = FixedSizeBinaryBuilder::with_capacity(chunk.len(), 32);
            let mut changes = ListBuilder::new(StringBuilder::new());
            for index in chunk {
                let record = &records[*index];
                kinds.append_value(record.kind.contract_name());
                if let Some(identity) = &record.row_identity {
                    identities
                        .append_value(digest_bytes(identity)?)
                        .map_err(|error| PyValueError::new_err(error.to_string()))?;
                } else {
                    identities.append_null();
                }
                for column in &record.changed_columns {
                    changes.values().append_value(column);
                }
                changes.append(true);
            }
            batches.push(
                RecordBatch::try_new(
                    Arc::clone(&schema),
                    vec![
                        Arc::new(kinds.finish()),
                        Arc::new(identities.finish()),
                        Arc::new(changes.finish()),
                    ],
                )
                .map_err(|error| PyValueError::new_err(error.to_string()))?,
            );
        }
        let external: Arc<dyn Any + Send + Sync> =
            self.owner.as_ref().ok_or_else(closed_handle)?.clone();
        self.risk_batches =
            Some(charge_arrow_batches(batches, lease, external).map_err(comparison_error)?);
        Ok(())
    }

    fn risk_record_batches(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let batches = self
            .risk_batches
            .as_ref()
            .ok_or_else(|| PyValueError::new_err("risk view was not prepared before seal"))?;
        let schema = risk_schema();
        let reader = BatchVecReader {
            schema,
            batches: batches.iter().cloned().collect(),
        };
        let bridge = Py::new(py, PyRecordBatchReader::new(Box::new(reader)))?;
        Ok(py
            .import("pyarrow")?
            .getattr("RecordBatchReader")?
            .call_method1("from_stream", (bridge,))?
            .unbind())
    }

    /// Optional neutral facts are prepared before phase sealing. A failed
    /// reservation never changes the completed business result.
    fn prepare_cache_views(&mut self, py: Python<'_>, max_row_bytes: usize) -> PyResult<()> {
        if self.cache_facts.is_some() { return Ok(()); }
        if self.risk_batches.is_none() { self.cache_created_risk = true; }
        self.prepare_risk_batches()?;
        let _use = OperationUse::begin(&self.context, &self.active)?;
        let result = self.result.as_ref().ok_or_else(closed_handle)?.clone();
        let estimate = match result.as_ref() {
            ComparisonResult::Standard(_) => 4096,
            ComparisonResult::Ordered(value) => {
                json_size(&value.facts_metadata).map_err(comparison_error)?
            }
            ComparisonResult::Restored { metadata_json, .. } => metadata_json.len(),
        };
        let metadata_lease = self
            .context
            .reserve(estimate.saturating_mul(16).saturating_add(65536))
            .map_err(|error| comparison_error(error.to_string()))?;
        let metadata = match result.as_ref() {
            ComparisonResult::Standard(value) => standard_metadata_json(value),
            ComparisonResult::Ordered(value) => ordered_metadata_json(value),
            ComparisonResult::Restored { metadata_json, .. } => Ok(metadata_json.clone()),
        }
        .map_err(PyValueError::new_err)?;
        let context = Arc::clone(&self.context);
        let owner: Arc<dyn Any + Send + Sync> =
            self.owner.as_ref().ok_or_else(closed_handle)?.clone();
        let facts = py
            .detach(|| {
                let metadata = serde_json::json!({"table_name": "neutral"});
                let source = match result.as_ref() {
                    ComparisonResult::Standard(value) => TableFactsSource {
                        metadata: &metadata,
                        standard: Some(value),
                        ordered: None,
                        neutral: None,
                    },
                    ComparisonResult::Ordered(value) => TableFactsSource {
                        metadata: &metadata,
                        standard: None,
                        ordered: Some(value),
                        neutral: None,
                    },
                    ComparisonResult::Restored { facts, .. } => TableFactsSource {
                        metadata: &metadata,
                        standard: None,
                        ordered: None,
                        neutral: Some(facts),
                    },
                };
                Ok::<NeutralFacts, String>(NeutralFacts {
                    standard: export_facts_family(
                        &source,
                        "STANDARD",
                        max_row_bytes,
                        &context,
                        owner.clone(),
                    )?,
                    ordered: export_facts_family(
                        &source,
                        "ORDERED",
                        max_row_bytes,
                        &context,
                        owner.clone(),
                    )?,
                    blank: export_facts_family(&source, "BLANK", max_row_bytes, &context, owner)?,
                })
            })
            .map_err(comparison_error)?;
        self.cache_facts = Some(facts);
        self.cache_metadata = Some(metadata);
        self._cache_metadata_lease = Some(metadata_lease);
        Ok(())
    }

    fn cache_metadata_json(&self) -> PyResult<&str> {
        self.cache_metadata
            .as_deref()
            .ok_or_else(|| PyValueError::new_err("neutral metadata not prepared"))
    }

    fn discard_cache_views(&mut self) {
        if self.cache_created_risk { self.risk_batches = None; }
        self.cache_created_risk = false;
        self.cache_facts = None;
        self.cache_metadata = None;
        self._cache_metadata_lease = None;
    }

    fn facts_batches(&self, py: Python<'_>, family: &str) -> PyResult<Py<PyAny>> {
        let facts = self
            .cache_facts
            .as_ref()
            .ok_or_else(|| PyValueError::new_err("neutral facts not prepared"))?;
        export_batches(
            py,
            facts_schema(),
            facts.family(family).map_err(PyValueError::new_err)?,
        )
    }

    fn cache_family_names(&self) -> Vec<&str> {
        [
            ("STANDARD", &self.standard),
            ("ORDERED", &self.ordered),
            ("BLANK", &self.blank),
        ]
        .into_iter()
        .filter_map(|(family, built)| built.as_ref().map(|_| family))
        .collect()
    }

    fn neutral_record_batches(&self, py: Python<'_>, family: &str) -> PyResult<Py<PyAny>> {
        let built = match family {
            "STANDARD" => self.standard.as_ref(),
            "ORDERED" => self.ordered.as_ref(),
            "BLANK" => self.blank.as_ref(),
            _ => return Err(PyValueError::new_err("unknown family")),
        }
        .ok_or_else(closed_handle)?;
        let schema = Arc::new(Schema::new_with_metadata(
            built
                .schema
                .fields()
                .iter()
                .skip(1)
                .cloned()
                .collect::<Vec<_>>(),
            built.schema.metadata().clone(),
        ));
        let batches = built
            .batches
            .iter()
            .map(|batch| {
                RecordBatch::try_new(
                    Arc::clone(&schema),
                    batch.columns().iter().skip(1).cloned().collect(),
                )
            })
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        export_batches(py, schema, &batches)
    }

    fn is_sealed(&self) -> bool {
        self.context.is_sealed()
    }
}

fn export_batches(
    py: Python<'_>,
    schema: SchemaRef,
    batches: &[RecordBatch],
) -> PyResult<Py<PyAny>> {
    let reader = BatchVecReader {
        schema,
        batches: batches.iter().cloned().collect(),
    };
    let bridge = Py::new(py, PyRecordBatchReader::new(Box::new(reader)))?;
    Ok(py
        .import("pyarrow")?
        .getattr("RecordBatchReader")?
        .call_method1("from_stream", (bridge,))?
        .unbind())
}

fn closed_handle() -> PyErr {
    PyValueError::new_err("comparison records handle is closed")
}

fn risk_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("record_kind", DataType::Utf8, false),
        Field::new("row_identity", DataType::FixedSizeBinary(32), true),
        Field::new(
            "changed_columns",
            DataType::List(Arc::new(Field::new("item", DataType::Utf8, true))),
            false,
        ),
    ]))
}

fn validate_risk_projection(batches: &[RecordBatch], context: &Arc<KernelContext>) -> PyResult<()> {
    for batch in batches {
        context.check().map_err(|error| comparison_error(error.to_string()))?;
        let _scratch = context.reserve(batch.get_array_memory_size().saturating_mul(4).saturating_add(4096))
            .map_err(|error| comparison_error(error.to_string()))?;
        let kinds = batch.column(0).as_any().downcast_ref::<StringArray>().ok_or_else(closed_handle)?;
        let identities = batch.column(1).as_any().downcast_ref::<FixedSizeBinaryArray>().ok_or_else(closed_handle)?;
        let columns = batch.column(2).as_any().downcast_ref::<ListArray>().ok_or_else(closed_handle)?;
        for row in 0..batch.num_rows() {
            if row % 256 == 0 { context.check().map_err(|error| comparison_error(error.to_string()))?; }
            if kinds.is_null(row) || columns.is_null(row) {
                return Err(PyValueError::new_err("neutral risk required value is null"));
            }
            let kind = kinds.value(row);
            if !matches!(kind, "ROW_ADDED" | "ROW_DELETED" | "ROW_MODIFIED" | "SCHEMA_CHANGE" | "TABLE_DEGRADED")
                || (matches!(kind, "ROW_ADDED" | "ROW_DELETED" | "ROW_MODIFIED") && identities.is_null(row)) {
                return Err(PyValueError::new_err("neutral risk kind/identity is invalid"));
            }
            let values = columns.value(row);
            let names = values.as_any().downcast_ref::<StringArray>().ok_or_else(closed_handle)?;
            let mut seen = std::collections::HashSet::new();
            for index in 0..names.len() {
                if names.is_null(index) { return Err(PyValueError::new_err("neutral risk changed column is null")); }
                let name = names.value(index);
                let canonical = gateway_shared_kernel::canonicalize_identifier(name)
                    .map_err(|error| PyValueError::new_err(error.to_string()))?;
                if canonical != name || !seen.insert(name) { return Err(PyValueError::new_err("neutral risk changed column is invalid")); }
            }
        }
    }
    Ok(())
}

fn digest_bytes(value: &str) -> PyResult<[u8; 32]> {
    let text = value.strip_prefix("sha256:").unwrap_or(value);
    if text.len() != 64 || !text.is_ascii() {
        return Err(PyValueError::new_err("risk row identity is not SHA256"));
    }
    let mut output = [0u8; 32];
    for (index, slot) in output.iter_mut().enumerate() {
        *slot = u8::from_str_radix(&text[index * 2..index * 2 + 2], 16)
            .map_err(|_| PyValueError::new_err("risk row identity has invalid hex"))?;
    }
    Ok(output)
}

fn comparison_error(error: String) -> PyErr {
    if error.contains("RESOURCE_LIMIT_EXCEEDED") || error.contains("budget exceeded") {
        PyMemoryError::new_err(error)
    } else if error.contains("COMPARISON_CANCELLED")
        || error.contains("operation control stopped compute")
    {
        PyInterruptedError::new_err(error)
    } else if error.contains("COMPARISON_DEADLINE_EXCEEDED")
        || error.contains("operation compute deadline elapsed")
    {
        PyTimeoutError::new_err(error)
    } else if error.contains("COMPARISON_INTERNAL_ERROR") {
        PyRuntimeError::new_err(error)
    } else if error.starts_with("COMPARISON_INPUT_READ_ERROR:") {
        PyOSError::new_err(error)
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
                let batch =
                    batch.map_err(|error| format!("COMPARISON_INPUT_READ_ERROR:{error}"))?;
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
fn _comparison_format_versions_native() -> (&'static str, u32, &'static str) {
    (gateway_compute_core::comparison::ORDERED_COMPARE_FORMAT,
     gateway_compute_core::comparison::ORDERED_COMPARE_VERSION,
     gateway_compute_core::canonical_ipc::CANONICAL_MAPPING_VERSION)
}

#[pyfunction]
#[pyo3(signature = (remaining_bytes, operation_charge, cancel_probe, deadline_monotonic=None, operation_identity=None))]
fn _begin_comparison_operation_native(
    py: Python<'_>,
    remaining_bytes: usize,
    operation_charge: Py<PyAny>,
    cancel_probe: Py<PyAny>,
    deadline_monotonic: Option<f64>,
    operation_identity: Option<usize>,
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
            operation_identity,
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
        let read_started = Instant::now();
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
        let input_read_seconds = read_started.elapsed().as_secs_f64();
        let external: Arc<dyn Any + Send + Sync> = owner.clone();
        let schema_diagnostics = py
            .import("json")?
            .call_method1("loads", (policy_json,))?
            .call_method1("get", ("schema_diagnostics",))?
            .extract::<Option<Vec<String>>>()?
            .unwrap_or_default();
        let output = py
            .detach(|| {
                pool.install(|| match policy {
                    ParsedComparisonPolicy::Standard(options) => {
                        let compare_started = Instant::now();
                        let mut result = compare_standard_table(
                            CanonicalBatchSide::new(before_schema, &before),
                            CanonicalBatchSide::new(current_schema, &current),
                            &options,
                            &context,
                        )
                        .map_err(|error| error.to_string())?;
                        let compare_seconds = compare_started.elapsed().as_secs_f64();
                        let records_started = Instant::now();
                        let schema_lease = if schema_diagnostics.is_empty() {
                            None
                        } else {
                            let upper = schema_diagnostics
                                .iter()
                                .try_fold(4096usize, |size, item| {
                                    size.checked_add(item.len().saturating_mul(8))
                                })
                                .and_then(|size| {
                                    size.checked_add(
                                        options
                                            .selected_columns
                                            .iter()
                                            .map(String::len)
                                            .sum::<usize>()
                                            .saturating_mul(8),
                                    )
                                })
                                .ok_or("schema record budget overflow")?;
                            let lease =
                                context.reserve(upper).map_err(|error| error.to_string())?;
                            result.records.push(StandardRecordRef {
                                kind: StandardKind::SchemaChange,
                                row_identity: None,
                                before: None,
                                current: None,
                                value_columns: Vec::new(),
                                changed_columns: options.selected_columns.clone(),
                                diagnostics: schema_diagnostics.clone(),
                            });
                            result.facts_order = (0..result.records.len()).collect();
                            result.facts_order.sort_by(|left, right| {
                                let left = &result.records[*left];
                                let right = &result.records[*right];
                                (
                                    left.kind.contract_name(),
                                    left.row_identity.as_deref(),
                                    &left.changed_columns,
                                )
                                    .cmp(&(
                                        right.kind.contract_name(),
                                        right.row_identity.as_deref(),
                                        &right.changed_columns,
                                    ))
                            });
                            result.artifact_order = result.facts_order.clone();
                            Some(lease)
                        };
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
                        Ok((
                            ComparisonResult::Standard(result),
                            standard,
                            None,
                            None,
                            schema_lease,
                            compare_seconds,
                            records_started.elapsed().as_secs_f64(),
                        ))
                    }
                    ParsedComparisonPolicy::Ordered(options) => {
                        let compare_started = Instant::now();
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
                        let compare_seconds = compare_started.elapsed().as_secs_f64();
                        let records_started = Instant::now();
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
                            None,
                            compare_seconds,
                            records_started.elapsed().as_secs_f64(),
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
            risk_batches: None,
            cache_facts: None,
            cache_metadata: None, cache_created_risk: false, _cache_metadata_lease: None,
            _schema_lease: output.4,
            context,
            active,
            owner: Some(owner),
            _watch: watch,
            operation_identity: operation.operation_identity,
            phase_timings: (input_read_seconds, output.5, output.6),
        })
    }) {
        Ok(result) => result,
        Err(()) => Err(PyRuntimeError::new_err(
            "comparison records adapter panicked",
        )),
    }
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn _restore_comparison_table_native(
    py: Python<'_>, operation: PyRef<'_, ComparisonOperation>, operation_identity: usize, table_name: &str, kind: &str,
    metadata_json: &str, detail_policy: &str, family_names: Vec<String>,
    facts_streams: Bound<'_, PyList>, artifact_streams: Bound<'_, PyList>,
    risk_stream: PyRecordBatchReader, max_records: usize, max_row_bytes: usize,
    max_input_bytes: usize, owner_charge: Py<PyAny>,
) -> PyResult<ComparisonRecordsHandle> {
    match adapter_boundary(|| {
        operation.require_operation(operation_identity)?;
        if facts_streams.len() != 3 || family_names.len() != artifact_streams.len()
            || family_names.len() > 3 {
            return Err(PyValueError::new_err("cache families/streams mismatch"));
        }
        let parent = operation.owner.as_ref().ok_or_else(closed_handle)?.clone();
        let context = Arc::clone(&operation.context);
        let _use = OperationUse::begin(&context, &operation.active)?;
        let owner = Arc::new(PythonChargeOwner {
            charge: Mutex::new(Some(owner_charge)),
            _parent: Some(parent),
        });
        let external: Arc<dyn Any + Send + Sync> = owner.clone();
        python_adapter_control(&operation.watch, operation.deadline)?;
        let metadata_lease = context
            .reserve(json_metadata_upper(metadata_json).map_err(comparison_error)?)
            .map_err(|error| comparison_error(error.to_string()))?;
        let metadata: serde_json::Value = serde_json::from_str(metadata_json)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        if !metadata.is_object() {
            return Err(PyValueError::new_err("neutral metadata must be an object"));
        }
        let mut input_bytes = 0;
        let mut facts = Vec::new();
        for stream in facts_streams.iter() {
            let (schema, batches) = read_stream(
                py,
                stream.extract()?,
                &context,
                &mut input_bytes,
                max_input_bytes,
            )?;
            if schema.as_ref() != facts_schema().as_ref() {
                return Err(PyValueError::new_err("neutral facts schema mismatch"));
            }
            let lease = context
                .reserve(batches.len().saturating_mul(4096))
                .map_err(|error| comparison_error(error.to_string()))?;
            facts.push(
                charge_arrow_batches(batches, lease, external.clone()).map_err(comparison_error)?,
            );
        }
        let mut facts_iter = facts.into_iter();
        let neutral = NeutralFacts {
            standard: facts_iter.next().ok_or_else(closed_handle)?,
            ordered: facts_iter.next().ok_or_else(closed_handle)?,
            blank: facts_iter.next().ok_or_else(closed_handle)?,
        };
        py.detach(|| neutral.validate(max_records, max_row_bytes, &context)).map_err(comparison_error)?;
        let counts = [neutral.standard.iter().map(RecordBatch::num_rows).sum(),
            neutral.ordered.iter().map(RecordBatch::num_rows).sum(), neutral.blank.iter().map(RecordBatch::num_rows).sum()];
        validate_cache_metadata(kind, &metadata, counts).map_err(PyValueError::new_err)?;
        let expected_families: &[&str] = if kind == "ordered" { &["STANDARD", "ORDERED", "BLANK"] } else { &["STANDARD"] };
        if !family_names.iter().map(String::as_str).eq(expected_families.iter().copied()) {
            return Err(PyValueError::new_err("native cache family closure mismatch"));
        }
        let (schema, risk) = read_stream(py, risk_stream, &context, &mut input_bytes, max_input_bytes)?;
        if schema.as_ref() != risk_schema().as_ref() || risk.iter().any(|batch| batch.num_rows() > 1024) {
            return Err(PyValueError::new_err("neutral risk schema/batch mismatch"));
        }
        validate_risk_projection(&risk, &context)?;
        let standard_count: usize = neutral.standard.iter().map(RecordBatch::num_rows).sum();
        if risk.iter().map(RecordBatch::num_rows).sum::<usize>() != standard_count {
            return Err(PyValueError::new_err("neutral risk/facts counts mismatch"));
        }
        let risk_lease = context
            .reserve(risk.len().saturating_mul(4096))
            .map_err(|error| comparison_error(error.to_string()))?;
        let risk =
            charge_arrow_batches(risk, risk_lease, external.clone()).map_err(comparison_error)?;
        let mut standard = None;
        let mut ordered = None;
        let mut blank = None;
        for (family, stream) in family_names.iter().zip(artifact_streams.iter()) {
            let (input_schema, batches) = read_stream(py, stream.extract()?, &context, &mut input_bytes, max_input_bytes)?;
            let expected = neutral.family(family).map_err(PyValueError::new_err)?.iter().map(RecordBatch::num_rows).sum::<usize>();
            let restored = py.detach(|| restore_records_batches(
                family, detail_policy, table_name, batches, max_records, max_row_bytes,
                &context, external.clone(),
            )).map_err(comparison_error)?;
            let expected_schema = Schema::new_with_metadata(restored.schema.fields().iter().skip(1).cloned().collect::<Vec<_>>(), restored.schema.metadata().clone());
            if input_schema.as_ref() != &expected_schema { return Err(PyValueError::new_err("neutral artifact schema mismatch")); }
            if restored.record_count != expected { return Err(PyValueError::new_err("neutral artifact/facts counts mismatch")); }
            let slot = match family.as_str() {
                "STANDARD" => &mut standard,
                "ORDERED" => &mut ordered,
                "BLANK" => &mut blank,
                _ => return Err(PyValueError::new_err("unknown neutral family")),
            };
            if slot.is_some() {
                return Err(PyValueError::new_err("duplicate neutral family"));
            }
            *slot = Some(restored);
        }
        if standard.is_none()
            || (ordered.is_none() && !neutral.ordered.is_empty())
            || (blank.is_none() && !neutral.blank.is_empty())
        {
            return Err(PyValueError::new_err("missing neutral family"));
        }
        python_adapter_control(&operation.watch, operation.deadline)?;
        Ok(ComparisonRecordsHandle {
            result: Some(Arc::new(ComparisonResult::Restored { metadata_json: metadata_json.to_string(), facts: neutral })),
            standard, ordered, blank, risk_batches: Some(risk), cache_facts: None,
            cache_metadata: None, cache_created_risk: false, _cache_metadata_lease: None,
            _schema_lease: Some(metadata_lease), context,
            active: Arc::clone(&operation.active), owner: Some(owner), _watch: Arc::clone(&operation.watch),
            operation_identity: operation.operation_identity, phase_timings: (0.0, 0.0, 0.0),
        })
    }) {
        Ok(result) => result,
        Err(()) => Err(PyRuntimeError::new_err(
            "comparison restore adapter panicked",
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
    let mut results = Vec::<Option<Arc<ComparisonResult>>>::new();
    let mut metadata = Vec::<String>::new();
    let context = Arc::clone(&operation.context);
    let _use = OperationUse::begin(&context, &operation.active)?;
    let mut metadata_upper = json_metadata_upper(summary_json).map_err(comparison_error)?;
    for raw in metadata_jsons.iter() {
        let raw = raw.cast::<PyString>()?;
        let raw = raw.to_str()?;
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
        if !handle.is_none() {
            let handle = handle.extract::<PyRef<'_, ComparisonRecordsHandle>>()?;
            let result = handle.result.as_ref().ok_or_else(closed_handle)?.clone();
            let same_phase = Arc::ptr_eq(&context, &handle.context);
            let same_operation = operation.operation_identity.is_some()
                && operation.operation_identity == handle.operation_identity;
            if !same_phase && !(same_operation && handle.context.is_sealed()) {
                return Err(PyValueError::new_err(
                    "facts tables must share the active phase or a sealed source phase",
                ));
            }
            results.push(Some(result));
        } else {
            results.push(None);
        }
        metadata.push(raw.extract::<String>()?);
    }
    let algorithm_version = algorithm_version.to_string();
    let summary_json = summary_json.to_string();
    py.detach(|| {
        let inputs = results
            .iter()
            .zip(&metadata)
            .map(|(result, raw)| match result.as_deref() {
                Some(ComparisonResult::Standard(result)) => TableFactsInput {
                    metadata_json: raw,
                    standard: Some(result),
                    ordered: None,
                    neutral: None,
                },
                Some(ComparisonResult::Ordered(result)) => TableFactsInput {
                    metadata_json: raw,
                    standard: None,
                    ordered: Some(result),
                    neutral: None,
                },
                Some(ComparisonResult::Restored { facts, .. }) => TableFactsInput {
                    metadata_json: raw,
                    standard: None,
                    ordered: None,
                    neutral: Some(facts),
                },
                None => TableFactsInput {
                    metadata_json: raw,
                    standard: None,
                    ordered: None,
                    neutral: None,
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
                validator.push_checked(&batch, &check)?;
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
    module.add_function(wrap_pyfunction!(_comparison_format_versions_native, module)?)?;
    module.add_class::<ComparisonRecordsHandle>()?;
    module.add_function(wrap_pyfunction!(
        _begin_comparison_operation_native,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(_compare_records_native, module)?)?;
    module.add_function(wrap_pyfunction!(_restore_comparison_table_native, module)?)?;
    module.add_function(wrap_pyfunction!(
        _summarize_unchanged_ordered_native,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(_facts_core_digest_native, module)?)?;
    module.add_function(wrap_pyfunction!(_validate_records_batches_native, module)?)?;
    Ok(())
}
