#![forbid(unsafe_code)]

use std::collections::HashMap;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{self, RecvTimeoutError, Sender};
use std::sync::{Arc, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use arrow_array::{ArrayRef, RecordBatch, RecordBatchReader};
use arrow_schema::{ArrowError, Field, Schema};
use gateway_compute_core::canonical_ipc::{
    CanonicalIpcBudgets, CanonicalIpcControl, CanonicalIpcError, CanonicalIpcErrorKind,
    CanonicalIpcOptions, encode_v1,
};
use gateway_compute_core::table_access::{
    ColumnDescriptor, DeclaredTypeMetadata, ParsedTable, ParserBudgets, ParserDiagnosticCode,
    SqlLogicalType, SqlParseOptions, SqlParseOutput, TableDescriptor, build_parser_pool,
    parse_sql_dump,
};
use gateway_shared_kernel::DeclaredType;
use pyo3::exceptions::{
    PyInterruptedError, PyMemoryError, PyRuntimeError, PyTimeoutError, PyValueError,
};
use pyo3::prelude::*;
use pyo3::types::{
    PyAny, PyBool, PyBytes, PyDict, PyInt, PyList, PyModule, PyString, PyStringMethods,
};
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

#[derive(Clone, Copy)]
struct CanonicalDescriptorPreflight {
    labels: usize,
    descriptor_storage_upper_bytes: usize,
    string_cache_upper_bytes: usize,
}

#[derive(Debug)]
enum CanonicalAdapterError {
    Core(CanonicalIpcError),
    Resource(String),
    Cancelled,
    Deadline,
    Stream(String),
}

impl From<CanonicalIpcError> for CanonicalAdapterError {
    fn from(error: CanonicalIpcError) -> Self {
        Self::Core(error)
    }
}

fn required_item<'py>(object: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    object
        .get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("missing required field {key}")))
}

fn required_bounded_python_string(
    object: &Bound<'_, PyDict>,
    key: &str,
    max_characters: usize,
) -> PyResult<String> {
    let value = required_item(object, key)?;
    let value = value
        .cast::<PyString>()
        .map_err(|_| PyValueError::new_err(format!("{key} must be a string")))?;
    if value.len() > max_characters {
        return Err(PyValueError::new_err(format!(
            "{key} exceeds the supported enum spelling length"
        )));
    }
    Ok(value.to_str()?.to_owned())
}

fn required_preflighted_python_string(object: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    let value = required_item(object, key)?;
    let value = value
        .cast::<PyString>()
        .map_err(|_| PyValueError::new_err(format!("{key} must be a string")))?;
    Ok(value.to_str()?.to_owned())
}

fn required_python_bool(object: &Bound<'_, PyDict>, key: &str) -> PyResult<bool> {
    let value = required_item(object, key)?;
    if !value.is_instance_of::<PyBool>() {
        return Err(PyValueError::new_err(format!("{key} must be a bool")));
    }
    value.extract::<bool>()
}

fn required_usize(object: &Bound<'_, PyDict>, key: &str) -> PyResult<usize> {
    let value = required_item(object, key)?;
    if value.is_instance_of::<PyBool>() || value.cast::<PyInt>().is_err() {
        return Err(PyValueError::new_err(format!("{key} must be a non-negative integer")));
    }
    value.extract::<usize>().map_err(|_| {
        PyValueError::new_err(format!("{key} must be a non-negative integer in range"))
    })
}

fn optional_u8(object: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<u8>> {
    let value = required_item(object, key)?;
    if value.is_none() {
        return Ok(None);
    }
    if value.is_instance_of::<PyBool>() || value.cast::<PyInt>().is_err() {
        return Err(PyValueError::new_err(format!(
            "{key} must be an integer or None"
        )));
    }
    let value = value.extract::<usize>().map_err(|_| {
        PyValueError::new_err(format!("{key} must be a non-negative integer in range"))
    })?;
    u8::try_from(value)
        .map(Some)
        .map_err(|_| PyValueError::new_err(format!("{key} is outside the supported range")))
}

fn checked_add_with_limit(
    current: usize,
    additional: usize,
    limit: usize,
    label: &str,
) -> PyResult<usize> {
    let total = current
        .checked_add(additional)
        .ok_or_else(|| PyMemoryError::new_err(format!("{label} size overflow")))?;
    if total > limit {
        return Err(PyMemoryError::new_err(format!("{label} budget exceeded")));
    }
    Ok(total)
}

fn canonical_budgets(object: &Bound<'_, PyDict>) -> PyResult<CanonicalIpcBudgets> {
    Ok(CanonicalIpcBudgets {
        max_rows: required_usize(object, "max_rows")?,
        max_columns: required_usize(object, "max_columns")?,
        max_descriptor_bytes: required_usize(object, "max_descriptor_bytes")?,
        max_input_batches: required_usize(object, "max_input_batches")?,
        max_input_bytes: required_usize(object, "max_input_bytes")?,
        max_output_bytes: required_usize(object, "max_output_bytes")?,
        max_codec_peak_bytes: required_usize(object, "max_codec_peak_bytes")?,
    })
}

fn descriptor_preflight(
    columns: &Bound<'_, PyList>,
    budgets: CanonicalIpcBudgets,
    watch: &CancelWatch,
    deadline: Option<Instant>,
) -> PyResult<CanonicalDescriptorPreflight> {
    let column_count = columns.len();
    if column_count > budgets.max_columns {
        return Err(PyMemoryError::new_err(
            "canonical IPC column limit exceeded",
        ));
    }
    let mut descriptor_characters = 0_usize;
    let mut cache_characters = 0_usize;
    let mut cached_string_count = 0_usize;
    let mut fixed_descriptor_bytes = 0_usize;
    let mut labels_total = 0_usize;
    for index in 0..column_count {
        python_adapter_control(watch, deadline)?;
        let item = columns.get_item(index)?;
        let column = item
            .cast::<PyDict>()
            .map_err(|_| PyValueError::new_err("each column descriptor must be a dict"))?;
        for key in ["canonical_name", "sql_type"] {
            let value = required_item(column, key)?;
            let value = value
                .cast::<PyString>()
                .map_err(|_| PyValueError::new_err(format!("{key} must be a string")))?;
            let characters = value.len();
            descriptor_characters = descriptor_characters
                .checked_add(characters)
                .ok_or_else(|| PyMemoryError::new_err("canonical descriptor size overflow"))?;
            cache_characters = cache_characters
                .checked_add(characters)
                .ok_or_else(|| PyMemoryError::new_err("canonical string cache size overflow"))?;
            cached_string_count = cached_string_count
                .checked_add(1)
                .ok_or_else(|| PyMemoryError::new_err("canonical string count overflow"))?;
        }
        fixed_descriptor_bytes = fixed_descriptor_bytes
            .checked_add(128)
            .ok_or_else(|| PyMemoryError::new_err("canonical descriptor size overflow"))?;
        let logical_type = required_item(column, "logical_type")?;
        let logical_type = logical_type
            .cast::<PyString>()
            .map_err(|_| PyValueError::new_err("logical_type must be a string"))?;
        if logical_type.len() > 8 {
            return Err(PyValueError::new_err("logical_type spelling is too long"));
        }
        cache_characters = cache_characters
            .checked_add(logical_type.len())
            .ok_or_else(|| PyMemoryError::new_err("canonical string cache size overflow"))?;
        cached_string_count = cached_string_count
            .checked_add(1)
            .ok_or_else(|| PyMemoryError::new_err("canonical string count overflow"))?;
        let declared = required_item(column, "declared_type")?;
        if !declared.is_none() {
            let declared = declared
                .cast::<PyDict>()
                .map_err(|_| PyValueError::new_err("declared_type must be a dict or None"))?;
            let kind = required_item(declared, "kind")?;
            let kind = kind
                .cast::<PyString>()
                .map_err(|_| PyValueError::new_err("declared_type.kind must be a string"))?;
            if kind.len() > 32 {
                return Err(PyValueError::new_err("declared_type.kind spelling is too long"));
            }
            cache_characters = cache_characters
                .checked_add(kind.len())
                .ok_or_else(|| PyMemoryError::new_err("canonical string cache size overflow"))?;
            cached_string_count = cached_string_count
                .checked_add(1)
                .ok_or_else(|| PyMemoryError::new_err("canonical string count overflow"))?;
        }
        let labels = required_item(column, "labels")?;
        if !labels.is_none() {
            let labels = labels
                .cast::<PyList>()
                .map_err(|_| PyValueError::new_err("labels must be a list or None"))?;
            let label_count = labels.len();
            let label_slots = label_count
                .checked_mul(std::mem::size_of::<String>())
                .ok_or_else(|| PyMemoryError::new_err("canonical label size overflow"))?;
            fixed_descriptor_bytes = fixed_descriptor_bytes
                .checked_add(label_slots)
                .ok_or_else(|| PyMemoryError::new_err("canonical descriptor size overflow"))?;
            if descriptor_characters
                .checked_add(fixed_descriptor_bytes)
                .is_none_or(|minimum| minimum > budgets.max_descriptor_bytes)
            {
                return Err(PyMemoryError::new_err(
                    "canonical IPC descriptor byte limit exceeded",
                ));
            }
            labels_total = labels_total
                .checked_add(label_count)
                .ok_or_else(|| PyMemoryError::new_err("canonical label count overflow"))?;
            for label_index in 0..label_count {
                python_adapter_control(watch, deadline)?;
                let label = labels.get_item(label_index)?;
                let label = label
                    .cast::<PyString>()
                    .map_err(|_| PyValueError::new_err("each label must be a string"))?;
                let characters = label.len();
                descriptor_characters = descriptor_characters
                    .checked_add(characters)
                    .ok_or_else(|| PyMemoryError::new_err("canonical descriptor size overflow"))?;
                cache_characters = cache_characters
                    .checked_add(characters)
                    .ok_or_else(|| PyMemoryError::new_err("canonical string cache size overflow"))?;
                cached_string_count = cached_string_count
                    .checked_add(1)
                    .ok_or_else(|| PyMemoryError::new_err("canonical string count overflow"))?;
            }
        }
    }
    let minimum_descriptor_bytes = descriptor_characters
        .checked_add(fixed_descriptor_bytes)
        .ok_or_else(|| PyMemoryError::new_err("canonical descriptor size overflow"))?;
    if minimum_descriptor_bytes > budgets.max_descriptor_bytes {
        return Err(PyMemoryError::new_err(
            "canonical IPC descriptor byte limit exceeded",
        ));
    }
    let descriptor_utf8_upper = descriptor_characters
        .checked_mul(4)
        .and_then(|value| value.checked_add(fixed_descriptor_bytes))
        .ok_or_else(|| PyMemoryError::new_err("canonical descriptor size overflow"))?;
    let string_cache_upper = cache_characters
        .checked_mul(4)
        .and_then(|value| value.checked_add(cached_string_count))
        .ok_or_else(|| PyMemoryError::new_err("canonical string cache size overflow"))?;
    let column_storage = column_count
        .checked_mul(std::mem::size_of::<ColumnDescriptor>())
        .ok_or_else(|| PyMemoryError::new_err("canonical descriptor storage overflow"))?;
    let descriptor_storage_upper_bytes = descriptor_utf8_upper
        .checked_add(column_storage)
        .ok_or_else(|| PyMemoryError::new_err("canonical descriptor storage overflow"))?;
    let preflight_owned_upper_bytes = descriptor_storage_upper_bytes
        .checked_add(string_cache_upper)
        .ok_or_else(|| PyMemoryError::new_err("canonical descriptor storage overflow"))?;
    if preflight_owned_upper_bytes > budgets.max_codec_peak_bytes {
        return Err(PyMemoryError::new_err(
            "canonical IPC descriptor exceeds codec peak budget",
        ));
    }
    let mut exact_descriptor_bytes = fixed_descriptor_bytes;
    for index in 0..column_count {
        python_adapter_control(watch, deadline)?;
        let item = columns.get_item(index)?;
        let column = item
            .cast::<PyDict>()
            .map_err(|_| PyValueError::new_err("each column descriptor must be a dict"))?;
        for key in ["canonical_name", "sql_type"] {
            let value = required_item(column, key)?;
            let value = value
                .cast::<PyString>()
                .map_err(|_| PyValueError::new_err(format!("{key} must be a string")))?;
            exact_descriptor_bytes = checked_add_with_limit(
                exact_descriptor_bytes,
                value.to_str()?.len(),
                budgets.max_descriptor_bytes,
                "canonical IPC descriptor",
            )?;
        }
        let labels = required_item(column, "labels")?;
        if !labels.is_none() {
            let labels = labels
                .cast::<PyList>()
                .map_err(|_| PyValueError::new_err("labels must be a list or None"))?;
            for label_index in 0..labels.len() {
                python_adapter_control(watch, deadline)?;
                let label = labels.get_item(label_index)?;
                let label = label
                    .cast::<PyString>()
                    .map_err(|_| PyValueError::new_err("each label must be a string"))?;
                exact_descriptor_bytes = checked_add_with_limit(
                    exact_descriptor_bytes,
                    label.to_str()?.len(),
                    budgets.max_descriptor_bytes,
                    "canonical IPC descriptor",
                )?;
            }
        }
    }
    let _ = exact_descriptor_bytes;
    Ok(CanonicalDescriptorPreflight {
        labels: labels_total,
        descriptor_storage_upper_bytes,
        string_cache_upper_bytes: string_cache_upper,
    })
}

fn actual_descriptor_storage_bytes(
    columns: &[ColumnDescriptor],
    column_capacity: usize,
) -> PyResult<usize> {
    let mut total = column_capacity
        .checked_mul(std::mem::size_of::<ColumnDescriptor>())
        .ok_or_else(|| PyMemoryError::new_err("canonical descriptor storage overflow"))?;
    for column in columns {
        total = total
            .checked_add(column.canonical_name.capacity())
            .and_then(|value| value.checked_add(column.sql_type.capacity()))
            .ok_or_else(|| PyMemoryError::new_err("canonical descriptor storage overflow"))?;
        if let Some(labels) = &column.labels {
            total = total
                .checked_add(
                    labels
                        .capacity()
                        .checked_mul(std::mem::size_of::<String>())
                        .ok_or_else(|| {
                            PyMemoryError::new_err("canonical label storage overflow")
                        })?,
                )
                .ok_or_else(|| PyMemoryError::new_err("canonical descriptor storage overflow"))?;
            for label in labels {
                total = total.checked_add(label.capacity()).ok_or_else(|| {
                    PyMemoryError::new_err("canonical label storage overflow")
                })?;
            }
        }
    }
    Ok(total)
}

fn parse_declared_type(value: &Bound<'_, PyAny>) -> PyResult<Option<DeclaredType>> {
    if value.is_none() {
        return Ok(None);
    }
    let object = value
        .cast::<PyDict>()
        .map_err(|_| PyValueError::new_err("declared_type must be a dict or None"))?;
    let kind = required_bounded_python_string(object, "kind", 32)?;
    let bits = optional_u8(object, "bits")?;
    let precision = optional_u8(object, "precision")?;
    let scale = optional_u8(object, "scale")?;
    let bit_width = optional_u8(object, "bit_width")?;
    let declared = match kind.as_str() {
        "null" => DeclaredType::null(),
        "boolean" => DeclaredType::boolean(),
        "signed-integer" => DeclaredType::signed_integer(bits.ok_or_else(|| {
            PyValueError::new_err("signed integer declared_type requires bits")
        })?)
        .map_err(|error| PyValueError::new_err(error.to_string()))?,
        "unsigned-integer" => DeclaredType::unsigned_integer(bits.ok_or_else(|| {
            PyValueError::new_err("unsigned integer declared_type requires bits")
        })?)
        .map_err(|error| PyValueError::new_err(error.to_string()))?,
        "decimal" => DeclaredType::decimal(
            precision.ok_or_else(|| {
                PyValueError::new_err("decimal declared_type requires precision")
            })?,
            scale.ok_or_else(|| PyValueError::new_err("decimal declared_type requires scale"))?,
        )
        .map_err(|error| PyValueError::new_err(error.to_string()))?,
        "float32" => DeclaredType::float32(),
        "float64" => DeclaredType::float64(),
        "string" => DeclaredType::string(),
        "binary" => DeclaredType::binary(),
        "bit" => DeclaredType::bit(bit_width.ok_or_else(|| {
            PyValueError::new_err("BIT declared_type requires bit_width")
        })?)
        .map_err(|error| PyValueError::new_err(error.to_string()))?,
        "date" => DeclaredType::date(),
        "datetime" => DeclaredType::datetime(),
        "timestamp" => DeclaredType::timestamp(),
        "time-duration" => DeclaredType::time_duration(),
        "source-literal-anomaly" => DeclaredType::source_literal_anomaly(),
        _ => return Err(PyValueError::new_err("unknown declared_type kind")),
    };
    declared
        .validate()
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    let expected = ColumnDescriptor {
        display_name: String::new(),
        canonical_name: String::new(),
        ordinal: 0,
        sql_type: String::new(),
        logical_type: SqlLogicalType::Standard,
        declared_type: Some(declared.clone()),
        nullable: false,
        labels: None,
    }
    .declared_type_metadata()
    .ok_or_else(|| PyValueError::new_err("declared_type metadata is missing"))?;
    if expected.kind != kind
        || expected.bits != bits
        || expected.precision != precision
        || expected.scale != scale
        || expected.bit_width != bit_width
    {
        return Err(PyValueError::new_err(
            "declared_type fields do not match the declared kind",
        ));
    }
    Ok(Some(declared))
}

fn parse_column_descriptor(
    value: &Bound<'_, PyDict>,
    ordinal: usize,
    watch: &CancelWatch,
    deadline: Option<Instant>,
) -> PyResult<ColumnDescriptor> {
    let canonical_name = required_preflighted_python_string(value, "canonical_name")?;
    let sql_type = required_preflighted_python_string(value, "sql_type")?;
    let logical_type = match required_bounded_python_string(value, "logical_type", 8)?.as_str() {
        "standard" => SqlLogicalType::Standard,
        "json" => SqlLogicalType::Json,
        "enum" => SqlLogicalType::Enum,
        "set" => SqlLogicalType::Set,
        "unknown" => SqlLogicalType::Unknown,
        _ => return Err(PyValueError::new_err("unknown SQL logical_type")),
    };
    let declared = required_item(value, "declared_type")?;
    let declared_type = parse_declared_type(&declared)?;
    let nullable = required_python_bool(value, "nullable")?;
    let labels_value = required_item(value, "labels")?;
    let labels = if labels_value.is_none() {
        None
    } else {
        let input_labels = labels_value
            .cast::<PyList>()
            .map_err(|_| PyValueError::new_err("labels must be a list or None"))?;
        let mut labels = Vec::new();
        labels.try_reserve_exact(input_labels.len()).map_err(|_| {
            PyMemoryError::new_err("canonical IPC label allocation failed")
        })?;
        for index in 0..input_labels.len() {
            python_adapter_control(watch, deadline)?;
            let label = input_labels.get_item(index)?;
            let label = label
                .cast::<PyString>()
                .map_err(|_| PyValueError::new_err("each label must be a string"))?;
            labels.push(label.to_str()?.to_owned());
        }
        Some(labels)
    };
    Ok(ColumnDescriptor {
        display_name: String::new(),
        canonical_name,
        ordinal,
        sql_type,
        logical_type,
        declared_type,
        nullable,
        labels,
    })
}

fn parse_column_descriptors(
    columns: &Bound<'_, PyList>,
    preflight: CanonicalDescriptorPreflight,
    watch: &CancelWatch,
    deadline: Option<Instant>,
) -> PyResult<Vec<ColumnDescriptor>> {
    let mut parsed = Vec::new();
    parsed
        .try_reserve_exact(columns.len())
        .map_err(|_| PyMemoryError::new_err("canonical IPC descriptor allocation failed"))?;
    let mut labels_seen = 0_usize;
    for index in 0..columns.len() {
        python_adapter_control(watch, deadline)?;
        let item = columns.get_item(index)?;
        let column = item
            .cast::<PyDict>()
            .map_err(|_| PyValueError::new_err("each column descriptor must be a dict"))?;
        let descriptor = parse_column_descriptor(column, index, watch, deadline)?;
        labels_seen = labels_seen
            .checked_add(descriptor.labels.as_ref().map_or(0, Vec::len))
            .ok_or_else(|| PyMemoryError::new_err("canonical label count overflow"))?;
        parsed.push(descriptor);
    }
    if labels_seen != preflight.labels {
        return Err(PyRuntimeError::new_err(
            "canonical IPC descriptor changed during conversion",
        ));
    }
    Ok(parsed)
}

fn adapter_control(
    cancel: &AtomicBool,
    deadline: Option<Instant>,
) -> Result<(), CanonicalAdapterError> {
    if cancel.load(Ordering::Relaxed) {
        return Err(CanonicalAdapterError::Cancelled);
    }
    if deadline.is_some_and(|deadline| Instant::now() >= deadline) {
        return Err(CanonicalAdapterError::Deadline);
    }
    Ok(())
}

fn python_adapter_control(watch: &CancelWatch, deadline: Option<Instant>) -> PyResult<()> {
    if watch.probe_failed.load(Ordering::Relaxed) {
        return Err(PyRuntimeError::new_err(
            "canonical IPC cancellation probe failed",
        ));
    }
    if watch.cancelled.load(Ordering::Relaxed) {
        return Err(PyInterruptedError::new_err(
            "canonical IPC encoding cancelled",
        ));
    }
    if deadline.is_some_and(|deadline| Instant::now() >= deadline) {
        return Err(PyTimeoutError::new_err(
            "canonical IPC encoding deadline elapsed",
        ));
    }
    Ok(())
}

fn consume_arrow_stream(
    mut reader: Box<dyn RecordBatchReader + Send>,
    descriptor_owned_bytes: usize,
    budgets: CanonicalIpcBudgets,
    cancel: &AtomicBool,
    deadline: Option<Instant>,
) -> Result<Vec<RecordBatch>, CanonicalAdapterError> {
    let mut batches = Vec::new();
    let mut input_rows = 0_usize;
    let mut input_bytes = 0_usize;
    let mut batch_array_metadata_bytes = 0_usize;
    loop {
        adapter_control(cancel, deadline)?;
        let next = reader.next();
        adapter_control(cancel, deadline)?;
        let Some(batch) = next else {
            break;
        };
        let batch = batch.map_err(|error| CanonicalAdapterError::Stream(error.to_string()))?;
        if batch.num_columns() > budgets.max_columns {
            return Err(CanonicalAdapterError::Resource(
                "canonical IPC batch column limit exceeded".into(),
            ));
        }
        let next_batch_count = batches
            .len()
            .checked_add(1)
            .ok_or_else(|| CanonicalAdapterError::Resource("input batch count overflow".into()))?;
        if next_batch_count > budgets.max_input_batches {
            return Err(CanonicalAdapterError::Resource(
                "canonical IPC input batch limit exceeded".into(),
            ));
        }
        let next_rows = input_rows
            .checked_add(batch.num_rows())
            .ok_or_else(|| CanonicalAdapterError::Resource("input row count overflow".into()))?;
        if next_rows > budgets.max_rows {
            return Err(CanonicalAdapterError::Resource(
                "canonical IPC row limit exceeded".into(),
            ));
        }
        let batch_bytes = batch.columns().iter().try_fold(0_usize, |total, array| {
            total.checked_add(array.get_array_memory_size()).ok_or_else(|| {
                CanonicalAdapterError::Resource("input array byte count overflow".into())
            })
        })?;
        adapter_control(cancel, deadline)?;
        input_bytes = input_bytes
            .checked_add(batch_bytes)
            .ok_or_else(|| CanonicalAdapterError::Resource("input byte count overflow".into()))?;
        if input_bytes > budgets.max_input_bytes {
            return Err(CanonicalAdapterError::Resource(
                "canonical IPC input byte limit exceeded".into(),
            ));
        }
        let arrays_metadata = batch
            .num_columns()
            .checked_mul(std::mem::size_of::<ArrayRef>())
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("record batch metadata overflow".into())
            })?;
        let next_array_metadata = batch_array_metadata_bytes
            .checked_add(arrays_metadata)
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("record batch metadata overflow".into())
            })?;
        let next_capacity = if batches.len() == batches.capacity() {
            batches.len().checked_add(1).ok_or_else(|| {
                CanonicalAdapterError::Resource("record batch capacity overflow".into())
            })?
        } else {
            batches.capacity()
        };
        let batch_vector_bytes = next_capacity
            .checked_mul(std::mem::size_of::<RecordBatch>())
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("record batch storage overflow".into())
            })?;
        let adapter_live = descriptor_owned_bytes
            .checked_add(batch_vector_bytes)
            .and_then(|value| value.checked_add(next_array_metadata))
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("adapter live byte estimate overflow".into())
            })?;
        if adapter_live > budgets.max_codec_peak_bytes {
            return Err(CanonicalAdapterError::Resource(
                "canonical IPC input batches exceed codec peak budget".into(),
            ));
        }
        if batches.len() == batches.capacity() {
            batches.try_reserve_exact(1).map_err(|_| {
                CanonicalAdapterError::Resource("record batch allocation failed".into())
            })?;
        }
        let actual_vector_bytes = batches
            .capacity()
            .checked_mul(std::mem::size_of::<RecordBatch>())
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("record batch storage overflow".into())
            })?;
        let actual_adapter_live = descriptor_owned_bytes
            .checked_add(actual_vector_bytes)
            .and_then(|value| value.checked_add(next_array_metadata))
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("adapter live byte estimate overflow".into())
            })?;
        if actual_adapter_live > budgets.max_codec_peak_bytes {
            return Err(CanonicalAdapterError::Resource(
                "canonical IPC input batches exceed codec peak budget".into(),
            ));
        }
        batches.push(batch);
        input_rows = next_rows;
        batch_array_metadata_bytes = next_array_metadata;
    }
    drop(reader);
    Ok(batches)
}

fn encode_canonical_ipc_inner(
    py: Python<'_>,
    columns: Bound<'_, PyList>,
    arrow_stream: PyRecordBatchReader,
    cancel_probe: Py<PyAny>,
    deadline_monotonic: Option<f64>,
    pool_threads: usize,
    budgets_object: Bound<'_, PyDict>,
) -> PyResult<Py<PyBytes>> {
    let pool = shared_parser_pool(pool_threads)?;
    let deadline = deadline_instant(py, deadline_monotonic)?;
    let budgets = canonical_budgets(&budgets_object)?;
    let watch = register_cancel_probe(py, &cancel_probe)?;
    python_adapter_control(&watch, deadline)?;
    let preflight = descriptor_preflight(&columns, budgets, &watch, deadline)?;
    python_adapter_control(&watch, deadline)?;
    let descriptors = parse_column_descriptors(&columns, preflight, &watch, deadline)?;
    python_adapter_control(&watch, deadline)?;
    let descriptor_storage_bytes =
        actual_descriptor_storage_bytes(&descriptors, descriptors.capacity())?;
    if descriptor_storage_bytes > preflight.descriptor_storage_upper_bytes {
        return Err(PyRuntimeError::new_err(
            "canonical IPC descriptor estimate was not conservative",
        ));
    }
    let descriptor_owned_bytes = descriptor_storage_bytes
        .checked_add(preflight.string_cache_upper_bytes)
        .ok_or_else(|| PyMemoryError::new_err("canonical descriptor storage overflow"))?;
    if descriptor_owned_bytes > budgets.max_codec_peak_bytes {
        return Err(PyMemoryError::new_err(
            "canonical IPC descriptor exceeds codec peak budget",
        ));
    }
    let reader = arrow_stream.into_reader()?;
    let cancel = Arc::clone(&watch.cancelled);
    let string_cache_upper_bytes = preflight.string_cache_upper_bytes;
    let result = py.detach(move || {
        adapter_control(cancel.as_ref(), deadline)?;
        let batches = consume_arrow_stream(
            reader,
            descriptor_owned_bytes,
            budgets,
            cancel.as_ref(),
            deadline,
        )?;
        let input_batch_owned_bytes = batches
            .iter()
            .try_fold(0_usize, |total, batch| {
                let column_refs = batch
                    .num_columns()
                    .checked_mul(std::mem::size_of::<ArrayRef>())?;
                total
                    .checked_add(std::mem::size_of::<RecordBatch>())?
                    .checked_add(column_refs)
            })
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("record batch storage overflow".into())
            })?;
        let vector_bytes = batches
            .capacity()
            .checked_mul(std::mem::size_of::<RecordBatch>())
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("record batch storage overflow".into())
            })?;
        let adapter_live = descriptor_owned_bytes
            .checked_add(input_batch_owned_bytes)
            .and_then(|value| value.checked_add(vector_bytes))
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("adapter live byte estimate overflow".into())
            })?;
        if adapter_live > budgets.max_codec_peak_bytes {
            return Err(CanonicalAdapterError::Resource(
                "canonical IPC adapter exceeds codec peak budget".into(),
            ));
        }
        let mut core_budgets = budgets;
        core_budgets.max_codec_peak_bytes -= adapter_live;
        let encoded = encode_v1(
            &descriptors,
            &batches,
            pool,
            CanonicalIpcOptions {
                budgets: core_budgets,
                control: CanonicalIpcControl {
                    cancel: Some(cancel.as_ref()),
                    deadline,
                },
            },
        )?;
        drop(batches);
        drop(descriptors);
        let transfer_peak = encoded
            .capacity()
            .checked_add(encoded.len())
            .and_then(|value| value.checked_add(128))
            .and_then(|value| value.checked_add(string_cache_upper_bytes))
            .ok_or_else(|| {
                CanonicalAdapterError::Resource("Python bytes transfer size overflow".into())
            })?;
        if transfer_peak > budgets.max_codec_peak_bytes {
            return Err(CanonicalAdapterError::Resource(
                "Python bytes transfer exceeds codec peak budget".into(),
            ));
        }
        Ok(encoded)
    });
    if watch.probe_failed.load(Ordering::Relaxed) {
        return Err(PyRuntimeError::new_err(
            "canonical IPC cancellation probe failed",
        ));
    }
    let encoded = result.map_err(|error| match error {
        CanonicalAdapterError::Core(error) => match error.kind() {
            CanonicalIpcErrorKind::Schema
            | CanonicalIpcErrorKind::Value
            | CanonicalIpcErrorKind::Ipc => PyValueError::new_err(error.to_string()),
            CanonicalIpcErrorKind::Resource => PyMemoryError::new_err(error.to_string()),
            CanonicalIpcErrorKind::Cancelled => {
                PyInterruptedError::new_err(error.to_string())
            }
            CanonicalIpcErrorKind::Deadline => PyTimeoutError::new_err(error.to_string()),
        },
        CanonicalAdapterError::Resource(message) => PyMemoryError::new_err(message),
        CanonicalAdapterError::Cancelled => {
            PyInterruptedError::new_err("canonical IPC encoding cancelled")
        }
        CanonicalAdapterError::Deadline => {
            PyTimeoutError::new_err("canonical IPC encoding deadline elapsed")
        }
        CanonicalAdapterError::Stream(message) => {
            PyValueError::new_err(format!("Arrow C Stream read failed: {message}"))
        }
    })?;
    Ok(PyBytes::new(py, &encoded).unbind())
}

#[pyfunction]
#[pyo3(signature = (columns, arrow_stream, cancel_probe, budgets, deadline_monotonic=None, pool_threads=1))]
fn _encode_canonical_ipc_native(
    py: Python<'_>,
    columns: Bound<'_, PyList>,
    arrow_stream: PyRecordBatchReader,
    cancel_probe: Py<PyAny>,
    budgets: Bound<'_, PyDict>,
    deadline_monotonic: Option<f64>,
    pool_threads: usize,
) -> PyResult<Py<PyBytes>> {
    match adapter_boundary(|| {
        encode_canonical_ipc_inner(
            py,
            columns,
            arrow_stream,
            cancel_probe,
            deadline_monotonic,
            pool_threads,
            budgets,
        )
    }) {
        Ok(result) => result,
        Err(()) => Err(PyRuntimeError::new_err("canonical IPC adapter panicked")),
    }
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
    module.add_function(wrap_pyfunction!(_encode_canonical_ipc_native, module)?)?;
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
