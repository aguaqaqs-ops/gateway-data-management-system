#![forbid(unsafe_code)]

use std::collections::HashMap;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{self, RecvTimeoutError, Sender};
use std::sync::{Arc, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use arrow_array::{RecordBatch, RecordBatchReader};
use arrow_schema::{ArrowError, Field, Schema};
use gateway_compute_core::table_access::{
    ColumnDescriptor, DeclaredTypeMetadata, ParsedTable, ParserBudgets, ParserDiagnosticCode,
    SqlParseOptions, SqlParseOutput, TableDescriptor, build_parser_pool, parse_sql_dump,
};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule};
use pyo3_arrow::PyRecordBatchReader;
use rayon::ThreadPool;

const CANCELLATION_POLL_INTERVAL: Duration = Duration::from_millis(10);

static PARSER_POOL: OnceLock<Result<ThreadPool, String>> = OnceLock::new();
static NEXT_CANCEL_WATCH: AtomicU64 = AtomicU64::new(1);
static CANCEL_MONITOR: OnceLock<Result<Sender<CancelMonitorCommand>, String>> = OnceLock::new();

enum CancelMonitorCommand {
    Watch(CancelWatchEntry),
    Unwatch(u64),
}

struct CancelWatchEntry {
    id: u64,
    probe: Py<PyAny>,
    cancelled: Arc<AtomicBool>,
    probe_failed: Arc<AtomicBool>,
}

struct CancelWatch {
    id: u64,
    cancelled: Arc<AtomicBool>,
    probe_failed: Arc<AtomicBool>,
    sender: &'static Sender<CancelMonitorCommand>,
}

impl Drop for CancelWatch {
    fn drop(&mut self) {
        let _ = self.sender.send(CancelMonitorCommand::Unwatch(self.id));
    }
}

fn run_cancel_monitor(receiver: mpsc::Receiver<CancelMonitorCommand>) {
    let mut watches = HashMap::<u64, CancelWatchEntry>::new();
    loop {
        match receiver.recv_timeout(CANCELLATION_POLL_INTERVAL) {
            Ok(CancelMonitorCommand::Watch(entry)) => {
                let _ = watches.insert(entry.id, entry);
            }
            Ok(CancelMonitorCommand::Unwatch(id)) => {
                let _ = watches.remove(&id);
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => return,
        }
        for entry in watches.values() {
            if entry.cancelled.load(Ordering::Relaxed) {
                continue;
            }
            let result = Python::try_attach(|py| {
                entry
                    .probe
                    .bind(py)
                    .call_method0("is_set")?
                    .extract::<bool>()
            });
            match result {
                Some(Ok(true)) => entry.cancelled.store(true, Ordering::Relaxed),
                Some(Ok(false)) => {}
                Some(Err(_)) => {
                    entry.probe_failed.store(true, Ordering::Relaxed);
                    entry.cancelled.store(true, Ordering::Relaxed);
                }
                None => entry.cancelled.store(true, Ordering::Relaxed),
            }
        }
    }
}

fn cancellation_sender() -> PyResult<&'static Sender<CancelMonitorCommand>> {
    let initialized = CANCEL_MONITOR.get_or_init(|| {
        let (sender, receiver) = mpsc::channel();
        thread::Builder::new()
            .name("gdms-parser-cancel-monitor".to_owned())
            .spawn(move || run_cancel_monitor(receiver))
            .map_err(|error| error.to_string())?;
        Ok(sender)
    });
    initialized.as_ref().map_err(|error| {
        PyRuntimeError::new_err(format!("parser cancellation monitor unavailable: {error}"))
    })
}

fn register_cancel_probe(py: Python<'_>, probe: &Py<PyAny>) -> PyResult<CancelWatch> {
    if probe.bind(py).call_method0("is_set")?.extract::<bool>()? {
        let cancelled = Arc::new(AtomicBool::new(true));
        return Ok(CancelWatch {
            id: 0,
            cancelled,
            probe_failed: Arc::new(AtomicBool::new(false)),
            sender: cancellation_sender()?,
        });
    }
    let sender = cancellation_sender()?;
    let id = NEXT_CANCEL_WATCH.fetch_add(1, Ordering::Relaxed);
    let cancelled = Arc::new(AtomicBool::new(false));
    let probe_failed = Arc::new(AtomicBool::new(false));
    sender
        .send(CancelMonitorCommand::Watch(CancelWatchEntry {
            id,
            probe: probe.clone_ref(py),
            cancelled: Arc::clone(&cancelled),
            probe_failed: Arc::clone(&probe_failed),
        }))
        .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
    Ok(CancelWatch {
        id,
        cancelled,
        probe_failed,
        sender,
    })
}

fn shared_parser_pool(threads: usize) -> PyResult<&'static ThreadPool> {
    if !(1..=gateway_compute_core::table_access::MAX_PARSER_THREADS).contains(&threads) {
        return Err(PyValueError::new_err(format!(
            "parser threads must be in 1..={}, got {threads}",
            gateway_compute_core::table_access::MAX_PARSER_THREADS
        )));
    }
    let result =
        PARSER_POOL.get_or_init(|| build_parser_pool(threads).map_err(|error| error.to_string()));
    let pool = result.as_ref().map_err(|error| {
        PyRuntimeError::new_err(format!("parser thread pool unavailable: {error}"))
    })?;
    if pool.current_num_threads() != threads {
        return Err(PyValueError::new_err(format!(
            "parser pool was initialized with {} threads; requested {threads}",
            pool.current_num_threads()
        )));
    }
    Ok(pool)
}

fn deadline_instant(py: Python<'_>, deadline: Option<f64>) -> PyResult<Option<Instant>> {
    let Some(deadline) = deadline else {
        return Ok(None);
    };
    if !deadline.is_finite() {
        return Err(PyValueError::new_err(
            "deadline_monotonic must be a finite float or None",
        ));
    }
    let time = PyModule::import(py, "time")?;
    let now = time.getattr("monotonic")?.call0()?.extract::<f64>()?;
    let remaining = (deadline - now).max(0.0);
    let duration = Duration::try_from_secs_f64(remaining)
        .map_err(|_| PyValueError::new_err("deadline_monotonic is outside the supported range"))?;
    Instant::now()
        .checked_add(duration)
        .map(Some)
        .ok_or_else(|| PyValueError::new_err("deadline_monotonic is outside the supported range"))
}

fn budget_value(object: &Bound<'_, PyAny>, field: &str, default: usize) -> PyResult<usize> {
    match object.getattr(field) {
        Ok(value) => value.extract::<usize>(),
        Err(error) if error.is_instance_of::<pyo3::exceptions::PyAttributeError>(object.py()) => {
            Ok(default)
        }
        Err(error) => Err(error),
    }
}

fn parser_budgets(py: Python<'_>, object: Option<&Py<PyAny>>) -> PyResult<ParserBudgets> {
    let defaults = ParserBudgets::default();
    let Some(object) = object else {
        return Ok(defaults);
    };
    let object = object.bind(py);
    Ok(ParserBudgets {
        max_sql_source_bytes: budget_value(
            object,
            "max_sql_source_bytes",
            defaults.max_sql_source_bytes,
        )?,
        max_statement_bytes: budget_value(
            object,
            "max_statement_bytes",
            defaults.max_statement_bytes,
        )?,
        max_tables_per_source: budget_value(
            object,
            "max_tables_per_source",
            defaults.max_tables_per_source,
        )?,
        max_columns_per_table: budget_value(
            object,
            "max_columns_per_table",
            defaults.max_columns_per_table,
        )?,
        max_identifier_code_points: budget_value(
            object,
            "max_identifier_code_points",
            defaults.max_identifier_code_points,
        )?,
        max_rows_per_table: budget_value(
            object,
            "max_rows_per_table",
            defaults.max_rows_per_table,
        )?,
        max_rows_per_source: budget_value(
            object,
            "max_rows_per_source",
            defaults.max_rows_per_source,
        )?,
        max_field_bytes: budget_value(object, "max_field_bytes", defaults.max_field_bytes)?,
        max_insert_tuple_bytes: budget_value(
            object,
            "max_insert_tuple_bytes",
            defaults.max_insert_tuple_bytes,
        )?,
        max_enum_set_sql_type_bytes: budget_value(
            object,
            "max_enum_set_sql_type_bytes",
            defaults.max_enum_set_sql_type_bytes,
        )?,
        max_diagnostics: budget_value(object, "max_diagnostics", defaults.max_diagnostics)?,
        max_diagnostic_message_bytes: budget_value(
            object,
            "max_diagnostic_message_bytes",
            defaults.max_diagnostic_message_bytes,
        )?,
        max_diagnostics_total_bytes: budget_value(
            object,
            "max_diagnostics_total_bytes",
            defaults.max_diagnostics_total_bytes,
        )?,
    })
}

struct SingleBatchReader {
    schema: Arc<Schema>,
    batch: Option<RecordBatch>,
}

impl Iterator for SingleBatchReader {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        self.batch.take().map(Ok)
    }
}

impl RecordBatchReader for SingleBatchReader {
    fn schema(&self) -> Arc<Schema> {
        Arc::clone(&self.schema)
    }
}

fn declared_type_object(
    py: Python<'_>,
    declared: Option<DeclaredTypeMetadata>,
) -> PyResult<Py<PyAny>> {
    let Some(declared) = declared else {
        return Ok(py.None());
    };
    let value = PyDict::new(py);
    value.set_item("kind", declared.kind)?;
    value.set_item("bits", declared.bits)?;
    value.set_item("precision", declared.precision)?;
    value.set_item("scale", declared.scale)?;
    value.set_item("bit_width", declared.bit_width)?;
    Ok(value.into_any().unbind())
}

fn table_stream(py: Python<'_>, table: &ParsedTable) -> PyResult<Option<Py<PyAny>>> {
    let Some(arrays) = &table.columns else {
        return Ok(None);
    };
    let fields = table
        .descriptor
        .columns
        .iter()
        .zip(arrays)
        .map(|(column, array)| {
            Field::new(
                column.display_name.as_str(),
                array.data_type().clone(),
                column.nullable,
            )
        })
        .collect::<Vec<_>>();
    let schema = Arc::new(Schema::new(fields));
    let batch = RecordBatch::try_new(Arc::clone(&schema), arrays.clone()).map_err(|error| {
        PyRuntimeError::new_err(format!("parser Arrow output is invalid: {error}"))
    })?;
    let reader = SingleBatchReader {
        schema,
        batch: Some(batch),
    };
    PyRecordBatchReader::new(Box::new(reader))
        .into_pyarrow(py)
        .map(|stream| Some(stream.unbind()))
}

fn add_column(
    py: Python<'_>,
    target: &Bound<'_, PyList>,
    column: &ColumnDescriptor,
) -> PyResult<()> {
    let value = PyDict::new(py);
    value.set_item("display_name", column.display_name.as_str())?;
    value.set_item("canonical_name", column.canonical_name.as_str())?;
    value.set_item("ordinal", column.ordinal)?;
    value.set_item("sql_type", column.sql_type.as_str())?;
    value.set_item("logical_type", column.logical_type.as_str())?;
    value.set_item(
        "declared_type",
        declared_type_object(py, column.declared_type_metadata())?,
    )?;
    value.set_item("nullable", column.nullable)?;
    value.set_item("labels", column.labels.as_ref())?;
    target.append(value)
}

fn add_table(
    py: Python<'_>,
    target: &Bound<'_, pyo3::types::PyList>,
    table: &ParsedTable,
) -> PyResult<()> {
    let value = PyDict::new(py);
    let descriptor: &TableDescriptor = &table.descriptor;
    value.set_item("display_name", descriptor.display_name.as_str())?;
    value.set_item("canonical_name", descriptor.canonical_name.as_str())?;
    value.set_item("primary_key", &descriptor.primary_key)?;
    value.set_item("reader_ready", descriptor.reader_ready)?;
    value.set_item("row_count", table.row_count)?;
    let columns = PyList::empty(py);
    for column in &descriptor.columns {
        add_column(py, &columns, column)?;
    }
    value.set_item("columns", columns)?;
    value.set_item("arrow_stream", table_stream(py, table)?)?;
    target.append(value)
}

fn add_diagnostic(
    py: Python<'_>,
    target: &Bound<'_, PyList>,
    diagnostic: &gateway_compute_core::table_access::ParserDiagnostic,
) -> PyResult<()> {
    let value = PyDict::new(py);
    value.set_item("code", diagnostic.code.as_str())?;
    value.set_item("byte_offset", diagnostic.byte_offset)?;
    value.set_item("message", diagnostic.message.as_str())?;
    value.set_item("table", diagnostic.table.as_deref())?;
    value.set_item("column", diagnostic.column.as_deref())?;
    target.append(value)
}

fn parse_output_object(py: Python<'_>, output: &SqlParseOutput) -> PyResult<Py<PyAny>> {
    if let Some(diagnostic) = output.diagnostics.iter().find(|diagnostic| {
        matches!(
            diagnostic.code,
            ParserDiagnosticCode::ParserInternalError | ParserDiagnosticCode::InvalidSourceEncoding
        )
    }) {
        return error_envelope(
            py,
            diagnostic.code.as_str(),
            &diagnostic.message,
            diagnostic.byte_offset,
        );
    }
    let value = PyDict::new(py);
    value.set_item("kind", "result")?;
    value.set_item("status", output.status.as_str())?;
    let tables = PyList::empty(py);
    for table in &output.tables {
        add_table(py, &tables, table)?;
    }
    value.set_item("tables", tables)?;
    let diagnostics = PyList::empty(py);
    for diagnostic in &output.diagnostics {
        add_diagnostic(py, &diagnostics, diagnostic)?;
    }
    value.set_item("diagnostics", diagnostics)?;
    Ok(value.into_any().unbind())
}

fn error_envelope(
    py: Python<'_>,
    code: &str,
    message: &str,
    byte_offset: usize,
) -> PyResult<Py<PyAny>> {
    let value = PyDict::new(py);
    value.set_item("kind", "error")?;
    value.set_item("code", code)?;
    value.set_item("message", message)?;
    value.set_item("byte_offset", byte_offset)?;
    Ok(value.into_any().unbind())
}

fn adapter_boundary<T>(operation: impl FnOnce() -> PyResult<T>) -> Result<PyResult<T>, ()> {
    catch_unwind(AssertUnwindSafe(operation)).map_err(|_| ())
}

fn parse_sql_inner(
    py: Python<'_>,
    sql_utf8: &[u8],
    cancel_probe: Py<PyAny>,
    deadline_monotonic: Option<f64>,
    pool_threads: usize,
    budgets: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let pool = shared_parser_pool(pool_threads)?;
    let deadline = deadline_instant(py, deadline_monotonic)?;
    let budgets = parser_budgets(py, budgets.as_ref())?;
    let watch = register_cancel_probe(py, &cancel_probe)?;
    let cancel = Arc::clone(&watch.cancelled);
    let options = SqlParseOptions {
        budgets,
        cancel: Some(cancel.as_ref()),
        deadline,
        ..SqlParseOptions::default()
    };
    let output = py.detach(|| parse_sql_dump(sql_utf8, &options, pool));
    if watch.probe_failed.load(Ordering::Relaxed) {
        return Err(PyRuntimeError::new_err("parser cancellation probe failed"));
    }
    parse_output_object(py, &output)
}

#[pyfunction]
#[pyo3(signature = (sql_utf8, cancel_probe, deadline_monotonic=None, pool_threads=1, budgets=None))]
fn _parse_sql_native(
    py: Python<'_>,
    sql_utf8: &[u8],
    cancel_probe: Py<PyAny>,
    deadline_monotonic: Option<f64>,
    pool_threads: usize,
    budgets: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    match adapter_boundary(|| {
        parse_sql_inner(
            py,
            sql_utf8,
            cancel_probe,
            deadline_monotonic,
            pool_threads,
            budgets,
        )
    }) {
        Ok(result) => result,
        Err(()) => error_envelope(py, "PARSER_INTERNAL_ERROR", "parser adapter panicked", 0),
    }
}

const BUILD_INPUT: &str = match option_env!("GATEWAY_RUST_BUILD_INPUT") {
    Some(value) => value,
    None => "",
};

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(_parse_sql_native, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add("__build_input__", BUILD_INPUT)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::adapter_boundary;

    #[test]
    #[allow(clippy::panic)]
    fn ffi_boundary_turns_a_panic_into_a_caught_result() {
        let result = adapter_boundary::<()>(|| panic!("test panic"));
        assert!(result.is_err());
    }
}
