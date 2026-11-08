//! Python-owned Arrow C Streams for one storage table; no Python row graph.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use arrow_array::{ArrayRef, RecordBatch, RecordBatchReader};
use gateway_compute_core::comparison::{KernelContext, KernelLease};
use gateway_compute_core::sql_replay::{REPLAY_BYTES, SqlBatcher, SqlMutation, SqlStatement};
use gateway_compute_core::storage_mutation::{
    PatchAction, RowLocation, StorageSide, StorageTable, prepare_storage_table, sql_mutation_at,
    sql_row_upper,
};
use pyo3::exceptions::{
    PyInterruptedError, PyMemoryError, PyRuntimeError, PyTimeoutError, PyValueError,
};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyModule};
use pyo3_arrow::{PyRecordBatchReader, PySchema};

use crate::{
    CancelWatch, adapter_boundary, deadline_instant, python_adapter_control, register_cancel_probe,
    shared_parser_pool,
};

#[pyclass]
struct StorageOperation {
    context: Arc<KernelContext>,
    initial_budget: usize,
    owner: Mutex<Option<Arc<PythonChargeOwner>>>,
    _watch: CancelWatch,
    closed: AtomicBool,
    identity: usize,
}

struct PythonChargeOwner {
    charge: Mutex<Option<Py<PyAny>>>,
    python_retains_charge: bool,
}

impl Drop for PythonChargeOwner {
    fn drop(&mut self) {
        if let Ok(slot) = self.charge.get_mut()
            && let Some(charge) = slot.take()
            && !self.python_retains_charge
        {
            let _ = Python::try_attach(|py| {
                let _ = charge.bind(py).call_method0("close");
            });
        }
    }
}

#[pymethods]
impl StorageOperation {
    fn close(&self) -> PyResult<()> {
        if !self.closed.swap(true, Ordering::AcqRel) {
            self.context.seal();
            let mut owner = self
                .owner
                .lock()
                .map_err(|_| PyRuntimeError::new_err("storage charge lock poisoned"))?;
            *owner = None;
        }
        Ok(())
    }

    fn reconcile(&self, py: Python<'_>) -> PyResult<usize> {
        if self.closed.load(Ordering::Acquire) {
            return Err(PyValueError::new_err("storage operation closed"));
        }
        let used = self
            .initial_budget
            .checked_sub(self.context.remaining_bytes())
            .ok_or_else(|| PyRuntimeError::new_err("storage budget accounting overflow"))?;
        let owner = self
            .owner
            .lock()
            .map_err(|_| PyRuntimeError::new_err("storage charge lock poisoned"))?;
        let charge = owner
            .as_ref()
            .ok_or_else(|| PyValueError::new_err("storage operation closed"))?
            .charge
            .lock()
            .map_err(|_| PyRuntimeError::new_err("storage charge lock poisoned"))?;
        charge
            .as_ref()
            .ok_or_else(|| PyValueError::new_err("storage operation closed"))?
            .bind(py)
            .call_method1("shrink_to", (used,))?;
        Ok(used)
    }
}

#[pyclass]
struct StorageHandle {
    table: Option<StorageTable>,
    header_lease: Option<KernelLease>,
    owner: Option<Arc<PythonChargeOwner>>,
}

type StorageSummary = (
    usize,
    usize,
    Option<(usize, usize, usize)>,
    bool,
    bool,
    usize,
);

#[pymethods]
impl StorageHandle {
    fn summary(&self) -> PyResult<StorageSummary> {
        let table = self
            .table
            .as_ref()
            .ok_or_else(|| PyValueError::new_err("storage handle closed"))?;
        Ok((
            table.before_rows,
            table.after_rows,
            table
                .net_counts
                .map(|value| (value.inserted, value.updated, value.deleted)),
            table.before_validated,
            table.after_validated,
            table.patch_actions.len(),
        ))
    }

    fn close(&mut self) {
        self.table = None;
        self.header_lease = None;
        self.owner = None;
    }

    fn discard_before(&mut self) -> PyResult<()> {
        let table = self
            .table
            .as_mut()
            .ok_or_else(|| PyValueError::new_err("storage handle closed"))?;
        table
            .discard_before()
            .map_err(|error| PyMemoryError::new_err(error.to_string()))?;
        if let Some(lease) = &mut self.header_lease {
            let actual = retained_header_bytes(table)
                .ok_or_else(|| PyMemoryError::new_err("storage header charge overflow"))?;
            lease
                .shrink_to(actual)
                .map_err(|error| PyMemoryError::new_err(error.to_string()))?;
        }
        Ok(())
    }

    fn render(
        &mut self,
        py: Python<'_>,
        render_operation: Py<StorageOperation>,
        decision: &str,
        table_name: &str,
        operation_identity: usize,
    ) -> PyResult<StorageRender> {
        let (context, owner) = {
            let operation = render_operation.borrow(py);
            if operation.identity != operation_identity || operation.closed.load(Ordering::Acquire)
            {
                return Err(PyValueError::new_err(
                    "storage render operation identity invalid",
                ));
            }
            let owner = operation
                .owner
                .lock()
                .map_err(|_| PyRuntimeError::new_err("storage charge lock poisoned"))?
                .as_ref()
                .cloned()
                .ok_or_else(|| PyValueError::new_err("storage render operation closed"))?;
            (Arc::clone(&operation.context), owner)
        };
        let table = self
            .table
            .as_ref()
            .ok_or_else(|| PyValueError::new_err("storage handle closed"))?;
        if !matches!(decision, "PATCH_DML" | "REBUILD_TABLE" | "NOOP") {
            return Err(PyValueError::new_err("storage render decision invalid"));
        }
        if decision == "PATCH_DML"
            && (table.before.is_none()
                || table.net_counts.is_none()
                || table
                    .net_counts
                    .is_some_and(|counts| counts.changed() != table.patch_actions.len()))
        {
            return Err(PyValueError::new_err("storage patch locators unavailable"));
        }
        // Removed tables have no DML; their DROP belongs to the schema pass.
        // The complete Python render subbudget is charged before this fixed
        // native statement/chunk envelope, under the same active operation M.
        let render_lease = context
            .reserve(64 * 1024)
            .map_err(|error| storage_control_error(error.code()))?;
        let exported_lease = context
            .reserve(0)
            .map_err(|error| storage_control_error(error.code()))?;
        Ok(StorageRender {
            table: self.table.take(),
            header_lease: self.header_lease.take(),
            old_owner: self.owner.take(),
            render_owner: Some(owner),
            _render_operation: render_operation,
            context,
            render_lease: Some(render_lease),
            exported_lease: Some(exported_lease),
            copy_lease: None,
            decision: decision.to_owned(),
            table_name: table_name.to_owned(),
            phase: 0,
            scan_index: 0,
            rebuild_index: 0,
            batcher: None,
            queued: None,
            statements: VecDeque::new(),
            current: None,
            total_sql: 0,
        })
    }
}

#[pyclass]
struct StorageRender {
    table: Option<StorageTable>,
    header_lease: Option<KernelLease>,
    old_owner: Option<Arc<PythonChargeOwner>>,
    render_owner: Option<Arc<PythonChargeOwner>>,
    _render_operation: Py<StorageOperation>,
    context: Arc<KernelContext>,
    render_lease: Option<KernelLease>,
    exported_lease: Option<KernelLease>,
    copy_lease: Option<KernelLease>,
    decision: String,
    table_name: String,
    phase: u8,
    scan_index: usize,
    rebuild_index: usize,
    batcher: Option<SqlBatcher>,
    queued: Option<SqlMutation>,
    statements: VecDeque<SqlStatement>,
    current: Option<SqlStatement>,
    total_sql: usize,
}

impl StorageRender {
    fn reconcile_bytes(&mut self) -> Result<(), String> {
        let pending = self.batcher.as_ref().map_or(0, SqlBatcher::pending_bytes);
        let queued = self
            .statements
            .iter()
            .map(SqlStatement::pending_bytes)
            .sum::<usize>();
        let current = self.current.as_ref().map_or(0, SqlStatement::pending_bytes);
        let retained = (64 * 1024usize)
            .checked_add(pending.checked_mul(4).ok_or("RESOURCE_LIMIT_EXCEEDED")?)
            .and_then(|size| size.checked_add(queued.checked_mul(4)?))
            .and_then(|size| size.checked_add(current.checked_mul(4)?))
            .ok_or("RESOURCE_LIMIT_EXCEEDED")?;
        let lease = self.render_lease.as_mut().ok_or("STORAGE_RENDER_INVALID")?;
        if retained > lease.charged_bytes() {
            return Err("STORAGE_RENDER_UNDERCHARGED".into());
        }
        lease.shrink_to(retained).map_err(|error| error.to_string())
    }

    fn action(&mut self) -> Result<Option<SqlMutation>, String> {
        let Some(table) = self.table.as_ref() else {
            return Ok(None);
        };
        if self.decision == "NOOP" {
            return Ok(None);
        }
        let choice: Option<(&str, RowLocation, &StorageSide)> = if self.decision == "REBUILD_TABLE"
        {
            let Some(&location) = table.after_order.get(self.rebuild_index) else {
                return Ok(None);
            };
            self.rebuild_index += 1;
            Some((
                "INSERT",
                location,
                table.after.as_ref().ok_or("STORAGE_AFTER_MISSING")?,
            ))
        } else {
            loop {
                if self.phase >= 3 {
                    break None;
                }
                let mut found = None;
                while let Some(action) = table.patch_actions.get(self.scan_index) {
                    self.scan_index += 1;
                    found = match (self.phase, action) {
                        (0, PatchAction::Delete(location)) => Some((
                            "DELETE",
                            *location,
                            table.before.as_ref().ok_or("STORAGE_BEFORE_MISSING")?,
                        )),
                        (1, PatchAction::Update(_, location)) => Some((
                            "UPDATE",
                            *location,
                            table.after.as_ref().ok_or("STORAGE_AFTER_MISSING")?,
                        )),
                        (2, PatchAction::Insert(location)) => Some((
                            "INSERT",
                            *location,
                            table.after.as_ref().ok_or("STORAGE_AFTER_MISSING")?,
                        )),
                        _ => None,
                    };
                    if found.is_some() {
                        break;
                    }
                }
                if found.is_some() {
                    break found;
                }
                self.phase += 1;
                self.scan_index = 0;
            }
        };
        let Some((operation, location, side)) = choice else {
            return Ok(None);
        };
        let upper =
            sql_row_upper(side, location, &table.key_columns).map_err(|error| error.to_string())?;
        self.render_lease
            .as_mut()
            .ok_or("STORAGE_RENDER_INVALID")?
            .grow(upper)
            .map_err(|error| error.to_string())?;
        let mut result =
            sql_mutation_at(side, location, &table.key_columns, operation, &self.context)
                .map_err(|error| error.to_string())?;
        result.canonical_table.clone_from(&self.table_name);
        Ok(Some(result))
    }

    fn fill(&mut self) -> Result<bool, String> {
        while self.statements.is_empty() {
            self.context.check().map_err(|error| error.to_string())?;
            let next = if let Some(value) = self.queued.take() {
                Some(value)
            } else {
                self.action()?
            };
            let Some(mutation) = next else {
                let finished = if let Some(batcher) = &mut self.batcher {
                    batcher.finish().map_err(|error| error.to_string())?
                } else {
                    None
                };
                if let Some(statement) = finished {
                    self.queue_statement(statement)?;
                }
                self.batcher = None;
                return Ok(!self.statements.is_empty());
            };
            if self
                .batcher
                .as_ref()
                .is_some_and(|batcher| batcher.operation() != mutation.operation)
            {
                let finished = if let Some(batcher) = &mut self.batcher {
                    batcher.finish().map_err(|error| error.to_string())?
                } else {
                    None
                };
                if let Some(statement) = finished {
                    self.queue_statement(statement)?;
                }
                self.batcher = None;
                self.queued = Some(mutation);
                continue;
            }
            if self.batcher.is_none() {
                self.batcher = Some(
                    SqlBatcher::with_cap(
                        &mutation,
                        REPLAY_BYTES
                            .checked_sub(self.total_sql)
                            .ok_or("RESOURCE_EXCEEDED")?,
                    )
                    .map_err(|error| error.to_string())?,
                );
            }
            for statement in self
                .batcher
                .as_mut()
                .ok_or("STORAGE_RENDER_INVALID")?
                .push(&mutation, &self.context)
                .map_err(|error| error.to_string())?
            {
                self.queue_statement(statement)?;
            }
            self.reconcile_bytes()?;
        }
        Ok(true)
    }

    fn queue_statement(&mut self, statement: SqlStatement) -> Result<(), String> {
        self.total_sql = self
            .total_sql
            .checked_add(statement.complete_len())
            .ok_or("RESOURCE_EXCEEDED")?;
        if self.total_sql > REPLAY_BYTES {
            return Err("RESOURCE_EXCEEDED".into());
        }
        self.statements.push_back(statement);
        Ok(())
    }

    fn next_bytes(&mut self) -> Result<Option<Vec<u8>>, String> {
        self.context.check().map_err(|error| error.to_string())?;
        if self.table.is_none() {
            return Ok(None);
        }
        loop {
            if let Some(current) = &mut self.current {
                let upper = current.next_chunk_upper();
                if upper > 0 {
                    self.copy_lease = Some(
                        self.context
                            .reserve(upper)
                            .map_err(|error| error.to_string())?,
                    );
                    self.exported_lease
                        .as_mut()
                        .ok_or("STORAGE_RENDER_INVALID")?
                        .grow(upper)
                        .map_err(|error| error.to_string())?;
                    return current
                        .next_chunk(&self.context)
                        .map_err(|error| error.to_string());
                }
                self.current = None;
            }
            if self.queued.is_none() {
                self.reconcile_bytes()?;
            }
            if !self.fill()? {
                return Ok(None);
            }
            self.current = self.statements.pop_front();
        }
    }
}

#[pymethods]
impl StorageRender {
    fn next_chunk(&mut self, py: Python<'_>) -> PyResult<Option<Py<PyBytes>>> {
        let result = match adapter_boundary(|| py.detach(|| self.next_bytes())) {
            Ok(Ok(Some(bytes))) => Ok(Some(PyBytes::new(py, &bytes).unbind())),
            Ok(Ok(None)) => Ok(None),
            Ok(Err(error)) if error == "RESOURCE_LIMIT_EXCEEDED" => {
                Err(PyMemoryError::new_err(error))
            }
            Ok(Err(error)) if error == "RESOURCE_EXCEEDED" => Err(PyValueError::new_err(error)),
            Ok(Err(error)) if error == "COMPARISON_CANCELLED" => {
                Err(PyInterruptedError::new_err(error))
            }
            Ok(Err(error)) if error == "COMPARISON_DEADLINE_EXCEEDED" => {
                Err(PyTimeoutError::new_err(error))
            }
            Ok(Err(error)) => Err(PyValueError::new_err(error)),
            Err(()) => Err(PyRuntimeError::new_err("storage SQL rendering panicked")),
        };
        self.copy_lease = None;
        result
    }

    fn close(&mut self) {
        self.table = None;
        self.header_lease = None;
        self.old_owner = None;
        self.batcher = None;
        self.queued = None;
        self.statements = VecDeque::new();
        self.current = None;
        self.render_lease = None;
        self.exported_lease = None;
        self.copy_lease = None;
        self.render_owner = None;
    }
}

fn header_upper(columns: usize, names_bytes: usize) -> Option<usize> {
    let per_batch = std::mem::size_of::<RecordBatch>()
        .checked_add(columns.checked_mul(std::mem::size_of::<ArrayRef>())?)?
        .checked_add(128)?;
    // One lookahead batch may be produced while detecting an over-limit stream.
    4097usize
        .checked_mul(per_batch)?
        .checked_add(names_bytes.checked_mul(8)?)?
        .checked_add(512)
}

fn storage_control_error(code: &str) -> PyErr {
    match code {
        "COMPARISON_CANCELLED" => PyInterruptedError::new_err("storage operation cancelled"),
        "COMPARISON_DEADLINE_EXCEEDED" => {
            PyTimeoutError::new_err("storage operation deadline elapsed")
        }
        _ => PyMemoryError::new_err(code.to_owned()),
    }
}

fn retained_header_bytes(table: &StorageTable) -> Option<usize> {
    let mut total = 4096usize;
    for side in table.before.iter().chain(table.after.iter()) {
        total = total.checked_add(
            side.batches
                .capacity()
                .checked_mul(std::mem::size_of::<RecordBatch>())?,
        )?;
        for batch in &side.batches {
            total = total
                .checked_add(
                    batch
                        .num_columns()
                        .checked_mul(std::mem::size_of::<ArrayRef>())?,
                )?
                .checked_add(128)?;
        }
    }
    Some(total)
}

#[pyfunction]
fn _begin_storage_operation_native(
    py: Python<'_>,
    remaining_bytes: usize,
    operation_charge: Py<PyAny>,
    cancel_probe: Py<PyAny>,
    deadline_monotonic: Option<f64>,
    pool_threads: usize,
    operation_identity: usize,
    python_retains_charge: bool,
) -> PyResult<StorageOperation> {
    match adapter_boundary(|| {
        shared_parser_pool(Some(pool_threads))?;
        let deadline = deadline_instant(py, deadline_monotonic)?;
        let watch = register_cancel_probe(py, &cancel_probe)?;
        python_adapter_control(&watch, deadline)?;
        Ok(StorageOperation {
            context: Arc::new(KernelContext::new(
                remaining_bytes,
                Arc::clone(&watch.cancelled),
                deadline,
            )),
            initial_budget: remaining_bytes,
            owner: Mutex::new(Some(Arc::new(PythonChargeOwner {
                charge: Mutex::new(Some(operation_charge)),
                python_retains_charge,
            }))),
            _watch: watch,
            closed: AtomicBool::new(false),
            identity: operation_identity,
        })
    }) {
        Ok(result) => result,
        Err(()) => Err(PyRuntimeError::new_err(
            "storage operation initialization panicked",
        )),
    }
}

type StreamInput = Option<(Box<dyn RecordBatchReader + Send>, usize, Vec<String>)>;

fn into_stream(
    stream: Option<PyRecordBatchReader>,
    schema: Option<PySchema>,
    expected_rows: usize,
    columns: Vec<String>,
) -> PyResult<StreamInput> {
    match (stream, schema) {
        (None, None) => Ok(None),
        (Some(stream), Some(schema)) => {
            let reader = stream.into_reader()?;
            if reader.schema() != schema.into_inner() {
                return Err(PyValueError::new_err(
                    "storage Arrow stream schema does not match explicit schema",
                ));
            }
            Ok(Some((reader, expected_rows, columns)))
        }
        _ => Err(PyValueError::new_err(
            "storage Arrow stream and explicit schema must be paired",
        )),
    }
}

fn consume_stream(
    input: StreamInput,
    context: &KernelContext,
) -> Result<Option<StorageSide>, String> {
    let Some((reader, expected_rows, retained_columns)) = input else {
        return Ok(None);
    };
    let schema = reader.schema();
    let mut batches = Vec::new();
    let mut count = 0usize;
    for next in reader {
        context.check().map_err(|error| error.to_string())?;
        if batches.len() >= 4096 {
            return Err("RESOURCE_LIMIT_EXCEEDED".into());
        }
        let batch = next.map_err(|error| error.to_string())?;
        count = count
            .checked_add(batch.num_rows())
            .ok_or("RESOURCE_LIMIT_EXCEEDED")?;
        if count > expected_rows {
            return Err("STORAGE_ROW_COUNT_MISMATCH".into());
        }
        batches.push(batch);
    }
    context.check().map_err(|error| error.to_string())?;
    if count != expected_rows {
        return Err("STORAGE_ROW_COUNT_MISMATCH".into());
    }
    Ok(Some(StorageSide {
        schema,
        batches,
        expected_rows,
        retained_columns,
    }))
}

#[pyfunction]
#[pyo3(signature = (operation, before_stream, before_schema, before_rows, before_columns,
                    after_stream, after_schema, after_rows, after_columns, key_columns, diff,
                    operation_identity))]
#[allow(clippy::too_many_arguments)]
fn _prepare_storage_table_native(
    py: Python<'_>,
    operation: Py<StorageOperation>,
    before_stream: Option<PyRecordBatchReader>,
    before_schema: Option<PySchema>,
    before_rows: usize,
    before_columns: Vec<String>,
    after_stream: Option<PyRecordBatchReader>,
    after_schema: Option<PySchema>,
    after_rows: usize,
    after_columns: Vec<String>,
    key_columns: Vec<String>,
    diff: bool,
    operation_identity: usize,
) -> PyResult<StorageHandle> {
    let (context, is_closed, owner) = {
        let owner = operation.borrow(py);
        if owner.identity != operation_identity {
            return Err(PyValueError::new_err("storage operation identity mismatch"));
        }
        let charge_owner = owner
            .owner
            .lock()
            .map_err(|_| PyRuntimeError::new_err("storage charge lock poisoned"))?
            .as_ref()
            .cloned()
            .ok_or_else(|| PyValueError::new_err("storage operation closed"))?;
        (
            Arc::clone(&owner.context),
            owner.closed.load(Ordering::Acquire),
            charge_owner,
        )
    };
    if is_closed {
        return Err(PyValueError::new_err("storage operation closed"));
    }
    let before_present = before_stream.is_some();
    let after_present = after_stream.is_some();
    let names_bytes = before_columns
        .iter()
        .chain(after_columns.iter())
        .try_fold(0usize, |sum, name| sum.checked_add(name.len()))
        .ok_or_else(|| PyMemoryError::new_err("storage metadata charge overflow"))?;
    let header_budget = (if before_present {
        header_upper(before_columns.len(), names_bytes)
    } else {
        Some(0)
    })
    .and_then(|left| {
        left.checked_add(if after_present {
            header_upper(after_columns.len(), names_bytes)?
        } else {
            0
        })
    })
    .and_then(|size| size.checked_add(4096))
    .ok_or_else(|| PyMemoryError::new_err("storage header charge overflow"))?;
    let mut header_lease = context
        .reserve(header_budget)
        .map_err(|error| storage_control_error(error.code()))?;
    let before = into_stream(before_stream, before_schema, before_rows, before_columns)?;
    let after = into_stream(after_stream, after_schema, after_rows, after_columns)?;
    let result = adapter_boundary(|| {
        Ok(py.detach(|| {
            let before = consume_stream(before, &context)?;
            let after = consume_stream(after, &context)?;
            if after
                .as_ref()
                .is_some_and(|side| side.expected_rows != after_rows)
            {
                return Err("STORAGE_ROW_COUNT_MISMATCH".to_owned());
            }
            prepare_storage_table(before, after, before_rows, &key_columns, diff, context)
                .map_err(|error| error.to_string())
        }))
    });
    match result {
        Ok(Ok(Ok(table))) => {
            let actual = retained_header_bytes(&table)
                .ok_or_else(|| PyMemoryError::new_err("storage header charge overflow"))?;
            if actual > header_budget {
                return Err(PyMemoryError::new_err(
                    "storage header charge underestimated",
                ));
            }
            header_lease
                .shrink_to(actual)
                .map_err(|error| PyMemoryError::new_err(error.to_string()))?;
            let handle = StorageHandle {
                table: Some(table),
                header_lease: Some(header_lease),
                owner: Some(owner),
            };
            if let Err(error) = operation.borrow(py).reconcile(py) {
                drop(handle);
                return Err(error);
            }
            Ok(handle)
        }
        Ok(Ok(Err(error))) if error == "RESOURCE_LIMIT_EXCEEDED" => {
            Err(PyMemoryError::new_err(error))
        }
        Ok(Ok(Err(error))) if error == "COMPARISON_CANCELLED" => {
            Err(PyInterruptedError::new_err("storage operation cancelled"))
        }
        Ok(Ok(Err(error))) if error == "COMPARISON_DEADLINE_EXCEEDED" => Err(
            PyTimeoutError::new_err("storage operation deadline elapsed"),
        ),
        Ok(Ok(Err(error))) => Err(PyValueError::new_err(error)),
        Ok(Err(error)) => Err(error),
        Err(()) => Err(PyRuntimeError::new_err(
            "storage table preparation panicked",
        )),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<StorageOperation>()?;
    module.add_class::<StorageHandle>()?;
    module.add_class::<StorageRender>()?;
    module.add_function(wrap_pyfunction!(_begin_storage_operation_native, module)?)?;
    module.add_function(wrap_pyfunction!(_prepare_storage_table_native, module)?)?;
    Ok(())
}
