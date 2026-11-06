//! Coarse Arrow C Stream boundary for the three bounded business operations.

use super::*;
use arrow_array::RecordBatchIterator;
use gateway_compute_core::business_kernel::{
    BusinessKernelBudgets, BusinessKernelControl, BusinessKernelError, BusinessKernelErrorKind,
    BusinessKernelOptions, CanonicalProjectionColumn, CanonicalProjectionPlan, CatalogFilterInput,
    KernelArrowTable, KernelDiagnostic, KernelDiagnosticSeverity, KernelOutcome, KernelTableInput,
    MaterializationStage, NamedKernelTableInput, ProjectionRowPolicy, SqlMaterializationPlan,
    filter_catalog, materialize_sql_table, project_canonical_table,
};

#[derive(Clone, Copy)]
enum Operation {
    Sql,
    Projection,
    Catalog,
}

fn business_budgets(object: &Bound<'_, PyDict>) -> PyResult<BusinessKernelBudgets> {
    Ok(BusinessKernelBudgets {
        max_columns: required_usize(object, "max_columns")?,
        max_batches: required_usize(object, "max_batches")?,
        max_rows: required_usize(object, "max_rows")?,
        max_metadata_bytes: required_usize(object, "max_metadata_bytes")?,
        max_input_bytes: required_usize(object, "max_input_bytes")?,
        max_live_bytes: required_usize(object, "max_live_bytes")?,
        max_output_bytes: required_usize(object, "max_output_bytes")?,
        max_diagnostic_bytes: required_usize(object, "max_diagnostic_bytes")?,
    })
}

fn codec_budgets(budgets: BusinessKernelBudgets) -> CanonicalIpcBudgets {
    CanonicalIpcBudgets {
        max_columns: budgets.max_columns,
        max_rows: budgets.max_rows,
        max_descriptor_bytes: budgets.max_metadata_bytes,
        max_input_batches: budgets.max_batches,
        max_input_bytes: budgets.max_input_bytes,
        max_output_bytes: budgets.max_output_bytes,
        max_codec_peak_bytes: budgets.max_live_bytes,
    }
}

/// Count Unicode cache upper bounds and object/vector overhead before copying
/// any Python metadata. Only Arrow stream objects are excluded from metadata.
fn metadata_preflight(
    value: &Bound<'_, PyAny>,
    bytes: &mut usize,
    budgets: BusinessKernelBudgets,
    depth: usize,
    watch: &CancelWatch,
    deadline: Option<Instant>,
) -> PyResult<()> {
    python_adapter_control(watch, deadline)?;
    if depth > 12 {
        return Err(PyValueError::new_err(
            "business metadata nesting exceeds limit",
        ));
    }
    *bytes = checked_add_with_limit(*bytes, 128, budgets.max_metadata_bytes, "business metadata")?;
    if let Ok(string) = value.cast::<PyString>() {
        let upper = string
            .len()?
            .checked_mul(4)
            .ok_or_else(|| PyMemoryError::new_err("metadata string overflow"))?;
        *bytes = checked_add_with_limit(
            *bytes,
            upper,
            budgets.max_metadata_bytes,
            "business metadata",
        )?;
    } else if let Ok(list) = value.cast::<PyList>() {
        for item in list.iter() {
            metadata_preflight(&item, bytes, budgets, depth + 1, watch, deadline)?;
        }
    } else if let Ok(dict) = value.cast::<PyDict>() {
        for (key, item) in dict.iter() {
            metadata_preflight(&key, bytes, budgets, depth + 1, watch, deadline)?;
            let key = key
                .cast::<PyString>()
                .map_err(|_| PyValueError::new_err("metadata keys must be strings"))?;
            if key.to_str()? != "arrow_stream" {
                metadata_preflight(&item, bytes, budgets, depth + 1, watch, deadline)?;
            }
        }
    } else if !value.is_none()
        && !value.is_instance_of::<PyBool>()
        && !value.is_instance_of::<PyInt>()
    {
        return Err(PyValueError::new_err(
            "business metadata contains an unsupported value",
        ));
    }
    if bytes
        .checked_mul(8)
        .is_none_or(|size| size > budgets.max_live_bytes)
    {
        return Err(PyMemoryError::new_err(
            "business metadata exceeds live budget",
        ));
    }
    Ok(())
}

fn strings(object: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<String>> {
    let values = required_item(object, key)?;
    let values = values
        .cast::<PyList>()
        .map_err(|_| PyValueError::new_err(format!("{key} must be a list")))?;
    values
        .iter()
        .map(|value| {
            value
                .cast::<PyString>()
                .map_err(|_| PyValueError::new_err("metadata name must be a string"))?
                .to_str()
                .map(str::to_owned)
        })
        .collect()
}

fn table_descriptor(
    object: &Bound<'_, PyDict>,
    budgets: BusinessKernelBudgets,
    watch: &CancelWatch,
    deadline: Option<Instant>,
) -> PyResult<TableDescriptor> {
    let columns = required_item(object, "columns")?;
    let columns = columns
        .cast::<PyList>()
        .map_err(|_| PyValueError::new_err("columns must be a list"))?;
    let preflight = descriptor_preflight(columns, codec_budgets(budgets), watch, deadline)?;
    let mut parsed = parse_column_descriptors(columns, preflight, watch, deadline)?;
    for (index, column) in parsed.iter_mut().enumerate() {
        python_adapter_control(watch, deadline)?;
        let metadata = columns.get_item(index)?;
        let metadata = metadata
            .cast::<PyDict>()
            .map_err(|_| PyValueError::new_err("column must be a dict"))?;
        column.display_name = match metadata.get_item("display_name")? {
            Some(value) => value.extract::<String>()?,
            None => column.canonical_name.clone(),
        };
        if let Some(ordinal) = metadata.get_item("ordinal")? {
            column.ordinal = ordinal.extract::<usize>()?;
        }
    }
    Ok(TableDescriptor {
        display_name: required_preflighted_python_string(object, "display_name")?,
        canonical_name: required_preflighted_python_string(object, "canonical_name")?,
        columns: parsed,
        primary_key: strings(object, "primary_key")?,
        reader_ready: required_python_bool(object, "reader_ready")?,
    })
}

fn stage(object: &Bound<'_, PyDict>) -> PyResult<MaterializationStage> {
    match required_preflighted_python_string(object, "stage")?.as_str() {
        "FINAL" => Ok(MaterializationStage::Final),
        "PROVISIONAL" => Ok(MaterializationStage::Provisional),
        _ => Err(PyValueError::new_err("unknown materialization stage")),
    }
}

fn projection_plan(
    object: &Bound<'_, PyDict>,
    budgets: BusinessKernelBudgets,
    watch: &CancelWatch,
    deadline: Option<Instant>,
) -> PyResult<CanonicalProjectionPlan> {
    let columns = required_item(object, "columns")?;
    let columns = columns
        .cast::<PyList>()
        .map_err(|_| PyValueError::new_err("projection columns must be a list"))?;
    let preflight = descriptor_preflight(columns, codec_budgets(budgets), watch, deadline)?;
    let descriptors = parse_column_descriptors(columns, preflight, watch, deadline)?;
    let mut projected = Vec::with_capacity(descriptors.len());
    for (index, mut descriptor) in descriptors.into_iter().enumerate() {
        let column = columns.get_item(index)?;
        let column = column
            .cast::<PyDict>()
            .map_err(|_| PyValueError::new_err("projection column must be a dict"))?;
        let source_index = required_item(column, "source_index")?;
        descriptor.display_name = match column.get_item("display_name")? {
            Some(value) => value.extract::<String>()?,
            None => descriptor.canonical_name.clone(),
        };
        let source_index = if source_index.is_none() {
            None
        } else {
            Some(required_usize(column, "source_index")?)
        };
        projected.push(CanonicalProjectionColumn {
            source_index,
            descriptor,
        });
    }
    let diagnostic_objects = required_item(object, "schema_diagnostics")?;
    let diagnostic_objects = diagnostic_objects
        .cast::<PyList>()
        .map_err(|_| PyValueError::new_err("schema_diagnostics must be a list"))?;
    if diagnostic_objects.len() > 1024 {
        return Err(PyValueError::new_err("schema diagnostics exceed fixed cap"));
    }
    let mut diagnostics = Vec::with_capacity(diagnostic_objects.len());
    for diagnostic in diagnostic_objects.iter() {
        python_adapter_control(watch, deadline)?;
        let diagnostic = diagnostic
            .cast::<PyDict>()
            .map_err(|_| PyValueError::new_err("diagnostic must be a dict"))?;
        let optional_string = |key| -> PyResult<Option<String>> {
            let value = required_item(diagnostic, key)?;
            if value.is_none() {
                Ok(None)
            } else {
                value.extract().map(Some)
            }
        };
        diagnostics.push(KernelDiagnostic {
            code: required_preflighted_python_string(diagnostic, "code")?,
            message: required_preflighted_python_string(diagnostic, "message")?,
            table: optional_string("table")?,
            column: optional_string("column")?,
            severity: KernelDiagnosticSeverity::Error,
        });
    }
    Ok(CanonicalProjectionPlan {
        materialization_stage: stage(object)?,
        canonical_table: required_preflighted_python_string(object, "canonical_table")?,
        expected_source_row_count: required_usize(object, "expected_source_row_count")?,
        columns: projected,
        canonical_key_columns: strings(object, "canonical_key_columns")?,
        structural_columns: strings(object, "structural_columns")?,
        row_policy: match required_preflighted_python_string(object, "row_policy")?.as_str() {
            "KEYED" => ProjectionRowPolicy::Keyed,
            "KEYLESS" => ProjectionRowPolicy::Keyless,
            "ORDERED_GID_NO" => ProjectionRowPolicy::OrderedGidNo,
            _ => return Err(PyValueError::new_err("unknown projection row policy")),
        },
        canonicalized_input: required_python_bool(object, "canonicalized_input")?,
        schema_diagnostics: diagnostics,
        omitted_schema_diagnostic_count: required_usize(object, "omitted_schema_diagnostic_count")?,
    })
}

fn business_error(error: BusinessKernelError) -> PyErr {
    match error.kind() {
        BusinessKernelErrorKind::Resource => PyMemoryError::new_err(error.to_string()),
        BusinessKernelErrorKind::Cancelled => PyInterruptedError::new_err(error.to_string()),
        BusinessKernelErrorKind::Deadline => PyTimeoutError::new_err(error.to_string()),
        _ => PyValueError::new_err(error.to_string()),
    }
}

fn stream_error(error: CanonicalAdapterError) -> BusinessKernelError {
    match error {
        CanonicalAdapterError::Resource(message) => {
            BusinessKernelError::new(BusinessKernelErrorKind::Resource, message)
        }
        CanonicalAdapterError::Cancelled => BusinessKernelError::new(
            BusinessKernelErrorKind::Cancelled,
            "business stream cancelled",
        ),
        CanonicalAdapterError::Deadline => BusinessKernelError::new(
            BusinessKernelErrorKind::Deadline,
            "business stream deadline elapsed",
        ),
        CanonicalAdapterError::Stream(message) => {
            BusinessKernelError::new(BusinessKernelErrorKind::Arrow, message)
        }
        CanonicalAdapterError::Core(error) => {
            BusinessKernelError::new(BusinessKernelErrorKind::Arrow, error.to_string())
        }
    }
}

struct NativeOutput {
    tables: Vec<KernelArrowTable>,
    digest: Option<[u8; 32]>,
    duplicate: bool,
    source_device_row_count: Option<usize>,
    real: Option<usize>,
    pseudo: Option<usize>,
}

fn output_transfer_preflight(
    outcome: &KernelOutcome<NativeOutput>,
    operation: Operation,
    budgets: BusinessKernelBudgets,
    owned_metadata: usize,
    watch: &CancelWatch,
    deadline: Option<Instant>,
) -> PyResult<()> {
    let mut retained = 2048usize;
    let mut arrow_bytes = 0usize;
    let mut add = |bytes| -> PyResult<()> {
        retained = checked_add_with_limit(
            retained,
            bytes,
            budgets.max_output_bytes,
            "business output facts",
        )?;
        Ok(())
    };
    for diagnostic in &outcome.diagnostics {
        python_adapter_control(watch, deadline)?;
        let strings = diagnostic
            .code
            .len()
            .checked_add(diagnostic.message.len())
            .and_then(|bytes| bytes.checked_add(diagnostic.table.as_ref().map_or(0, String::len)))
            .and_then(|bytes| bytes.checked_add(diagnostic.column.as_ref().map_or(0, String::len)))
            .ok_or_else(|| PyMemoryError::new_err("diagnostic transfer overflow"))?;
        add(strings
            .checked_mul(8)
            .and_then(|bytes| bytes.checked_add(1024))
            .ok_or_else(|| PyMemoryError::new_err("diagnostic transfer overflow"))?)?;
    }
    if let Some(output) = &outcome.output {
        for table in &output.tables {
            python_adapter_control(watch, deadline)?;
            add(2048)?;
            for column in &table.descriptor.columns {
                let strings = column
                    .canonical_name
                    .len()
                    .checked_add(column.display_name.len())
                    .and_then(|bytes| bytes.checked_add(column.sql_type.len()))
                    .ok_or_else(|| PyMemoryError::new_err("column transfer overflow"))?;
                add(strings
                    .checked_mul(8)
                    .and_then(|bytes| bytes.checked_add(2048))
                    .ok_or_else(|| PyMemoryError::new_err("column transfer overflow"))?)?;
                for label in column.labels.iter().flatten() {
                    add(label
                        .len()
                        .checked_mul(8)
                        .and_then(|bytes| bytes.checked_add(128))
                        .ok_or_else(|| PyMemoryError::new_err("label transfer overflow"))?)?;
                }
            }
            for name in std::iter::once(&table.descriptor.display_name)
                .chain(std::iter::once(&table.descriptor.canonical_name))
                .chain(&table.descriptor.primary_key)
            {
                add(name
                    .len()
                    .checked_mul(8)
                    .and_then(|bytes| bytes.checked_add(128))
                    .ok_or_else(|| PyMemoryError::new_err("table transfer overflow"))?)?;
            }
            for batch in &table.batches {
                for array in batch.columns() {
                    arrow_bytes = arrow_bytes
                        .checked_add(array.get_array_memory_size())
                        .ok_or_else(|| {
                            PyMemoryError::new_err("Arrow output byte count overflow")
                        })?;
                }
            }
        }
    }
    // SQL returns shared input buffers. Projection/catalog own rebuilt arrays.
    // Both count for returned-output bytes; only the latter add owned live data.
    let owned_arrow = if matches!(operation, Operation::Sql) {
        0
    } else {
        arrow_bytes
    };
    if retained
        .checked_add(arrow_bytes)
        .is_none_or(|bytes| bytes > budgets.max_output_bytes)
        || retained
            .checked_mul(2)
            .and_then(|bytes| bytes.checked_add(owned_metadata))
            .and_then(|bytes| bytes.checked_add(owned_arrow))
            .is_none_or(|bytes| bytes > budgets.max_live_bytes)
    {
        return Err(PyMemoryError::new_err(
            "Python business output conversion exceeds live/output budget",
        ));
    }
    python_adapter_control(watch, deadline)
}

fn output_object(
    py: Python<'_>,
    outcome: KernelOutcome<NativeOutput>,
    watch: &CancelWatch,
    deadline: Option<Instant>,
) -> PyResult<Py<PyAny>> {
    let result = PyDict::new(py);
    let diagnostics = PyList::empty(py);
    for diagnostic in outcome.diagnostics {
        python_adapter_control(watch, deadline)?;
        let value = PyDict::new(py);
        value.set_item("code", diagnostic.code)?;
        value.set_item("message", diagnostic.message)?;
        value.set_item("table", diagnostic.table)?;
        value.set_item("column", diagnostic.column)?;
        value.set_item(
            "severity",
            if diagnostic.severity == KernelDiagnosticSeverity::Error {
                "ERROR"
            } else {
                "WARNING"
            },
        )?;
        diagnostics.append(value)?;
    }
    result.set_item("diagnostics", diagnostics)?;
    result.set_item("omitted_diagnostic_count", outcome.omitted_diagnostic_count)?;
    let Some(output) = outcome.output else {
        result.set_item("output", py.None())?;
        python_adapter_control(watch, deadline)?;
        return Ok(result.into_any().unbind());
    };
    let value = PyDict::new(py);
    value.set_item(
        "raw_content_digest",
        output.digest.map(|digest| {
            format!(
                "sha256:{}",
                digest
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect::<String>()
            )
        }),
    )?;
    value.set_item("duplicate_effective_key", output.duplicate)?;
    value.set_item("source_device_row_count", output.source_device_row_count)?;
    value.set_item("gid_real_count", output.real)?;
    value.set_item("gid_pseudo_count", output.pseudo)?;
    let tables = PyList::empty(py);
    for table in output.tables {
        python_adapter_control(watch, deadline)?;
        let metadata = PyDict::new(py);
        metadata.set_item("display_name", &table.descriptor.display_name)?;
        metadata.set_item("canonical_name", &table.descriptor.canonical_name)?;
        metadata.set_item("primary_key", &table.descriptor.primary_key)?;
        metadata.set_item("reader_ready", true)?;
        metadata.set_item("row_count", table.row_count)?;
        let columns = PyList::empty(py);
        for column in &table.descriptor.columns {
            python_adapter_control(watch, deadline)?;
            add_column(py, &columns, column)?;
        }
        metadata.set_item("columns", columns)?;
        let schema = table
            .batches
            .first()
            .map(RecordBatch::schema)
            .ok_or_else(|| PyRuntimeError::new_err("business output has no Arrow batch"))?;
        let reader = RecordBatchIterator::new(table.batches.into_iter().map(Ok), schema);
        metadata.set_item(
            "arrow_stream",
            PyRecordBatchReader::new(Box::new(reader)).into_pyarrow(py)?,
        )?;
        tables.append(metadata)?;
        python_adapter_control(watch, deadline)?;
    }
    value.set_item("tables", tables)?;
    result.set_item("output", value)?;
    python_adapter_control(watch, deadline)?;
    Ok(result.into_any().unbind())
}

fn native_inner(
    py: Python<'_>,
    operation: Operation,
    tables: Bound<'_, PyList>,
    plan: Bound<'_, PyDict>,
    budgets: Bound<'_, PyDict>,
    (cancel_probe, deadline_monotonic, pool_threads): (Py<PyAny>, Option<f64>, usize),
) -> PyResult<Py<PyAny>> {
    let pool = shared_parser_pool(pool_threads)?;
    let deadline = deadline_instant(py, deadline_monotonic)?;
    let budgets = business_budgets(&budgets)?;
    let watch = register_cancel_probe(py, &cancel_probe)?;
    python_adapter_control(&watch, deadline)?;
    let max_tables = if matches!(operation, Operation::Catalog) {
        11
    } else {
        1
    };
    if tables.len() > max_tables
        || (!matches!(operation, Operation::Catalog) && tables.len() != 1)
    {
        return Err(PyValueError::new_err(
            "business operation table/stream count is invalid",
        ));
    }
    let mut metadata_bytes = 0;
    metadata_preflight(
        tables.as_any(),
        &mut metadata_bytes,
        budgets,
        0,
        &watch,
        deadline,
    )?;
    metadata_preflight(
        plan.as_any(),
        &mut metadata_bytes,
        budgets,
        0,
        &watch,
        deadline,
    )?;
    let owned_metadata = metadata_bytes
        .checked_mul(8)
        .ok_or_else(|| PyMemoryError::new_err("metadata size overflow"))?;
    let mut descriptors = Vec::with_capacity(tables.len());
    let mut readers = Vec::with_capacity(tables.len());
    for table in tables.iter() {
        python_adapter_control(&watch, deadline)?;
        descriptors.push(table_descriptor(
            table
                .cast::<PyDict>()
                .map_err(|_| PyValueError::new_err("table metadata must be a dict"))?,
            budgets,
            &watch,
            deadline,
        )?);
        let last = descriptors
            .last()
            .ok_or_else(|| PyRuntimeError::new_err("table descriptor absent"))?;
        if descriptors[..descriptors.len() - 1]
            .iter()
            .any(|previous| previous.canonical_name == last.canonical_name)
        {
            return Err(PyValueError::new_err("business input repeats a table name"));
        }
        let stream = required_item(table.cast::<PyDict>().map_err(|_| PyValueError::new_err("table metadata must be a dict"))?, "arrow_stream")?;
        readers.push(stream.extract::<PyRecordBatchReader>()?.into_reader()?);
    }
    let sql_plan = if matches!(operation, Operation::Sql) {
        Some(SqlMaterializationPlan {
            stage: stage(&plan)?,
            effective_compare_key_columns: strings(&plan, "effective_compare_key_columns")?,
        })
    } else {
        None
    };
    let projection_plan = if matches!(operation, Operation::Projection) {
        Some(projection_plan(&plan, budgets, &watch, deadline)?)
    } else {
        None
    };
    let cancel = Arc::clone(&watch.cancelled);
    let outcome = py.detach(move || {
        let mut core_budgets = budgets;
        core_budgets.max_live_bytes = core_budgets
            .max_live_bytes
            .checked_sub(owned_metadata)
            .ok_or_else(|| {
                BusinessKernelError::new(
                    BusinessKernelErrorKind::Resource,
                    "adapter metadata exceeds live budget",
                )
            })?;
        let mut batches = Vec::with_capacity(readers.len());
        let mut remaining = codec_budgets(core_budgets);
        let mut synthesized = 0usize;
        let mut adapter_batches_owned = 0usize;
        for reader in readers {
            let schema = reader.schema();
            let header_upper = schema
                .fields()
                .len()
                .checked_mul(1024)
                .and_then(|bytes| bytes.checked_add(512))
                .ok_or_else(|| {
                    BusinessKernelError::new(
                        BusinessKernelErrorKind::Resource,
                        "empty Arrow header estimate overflow",
                    )
                })?;
            if schema.fields().len() > remaining.max_columns
                || header_upper > remaining.max_codec_peak_bytes
            {
                return Err(BusinessKernelError::new(
                    BusinessKernelErrorKind::Resource,
                    "Arrow schema exceeds adapter limits",
                ));
            }
            let mut schema_bytes = 0usize;
            for field in schema.fields() {
                schema_bytes = schema_bytes
                    .checked_add(field.name().len())
                    .ok_or_else(|| {
                        BusinessKernelError::new(
                            BusinessKernelErrorKind::Resource,
                            "Arrow schema metadata overflow",
                        )
                    })?;
                for (key, value) in field.metadata() {
                    schema_bytes = schema_bytes
                        .checked_add(key.len())
                        .and_then(|bytes| bytes.checked_add(value.len()))
                        .ok_or_else(|| {
                            BusinessKernelError::new(
                                BusinessKernelErrorKind::Resource,
                                "Arrow schema metadata overflow",
                            )
                        })?;
                }
            }
            if schema_bytes > remaining.max_descriptor_bytes {
                return Err(BusinessKernelError::new(
                    BusinessKernelErrorKind::Resource,
                    "Arrow schema metadata exceeds limit",
                ));
            }
            let mut batch =
                consume_arrow_stream(reader, owned_metadata, remaining, cancel.as_ref(), deadline)
                    .map_err(stream_error)?;
            let rows = batch
                .iter()
                .try_fold(0usize, |total, batch| total.checked_add(batch.num_rows()))
                .ok_or_else(|| {
                    BusinessKernelError::new(
                        BusinessKernelErrorKind::Resource,
                        "aggregate row count overflow",
                    )
                })?;
            remaining.max_rows = remaining.max_rows.checked_sub(rows).ok_or_else(|| {
                BusinessKernelError::new(
                    BusinessKernelErrorKind::Resource,
                    "aggregate row budget exceeded",
                )
            })?;
            let actual_batches = batch.len();
            if batch.is_empty() {
                // Preserve a zero-batch reader's actual schema for core
                // binding checks. Only the equivalent core cap counts this
                // generated empty batch; real consumption retains its cap.
                batch.push(RecordBatch::new_empty(schema));
                synthesized += 1;
            }
            let current_owned = batch
                .iter()
                .try_fold(header_upper, |total, batch| {
                    total
                        .checked_add(std::mem::size_of::<RecordBatch>())
                        .and_then(|bytes| {
                            batch
                                .num_columns()
                                .checked_mul(std::mem::size_of::<ArrayRef>())
                                .and_then(|columns| bytes.checked_add(columns))
                        })
                })
                .and_then(|bytes| {
                    batch
                        .capacity()
                        .checked_mul(std::mem::size_of::<RecordBatch>())
                        .and_then(|vectors| bytes.checked_add(vectors))
                })
                .ok_or_else(|| {
                    BusinessKernelError::new(
                        BusinessKernelErrorKind::Resource,
                        "adapter batch storage overflow",
                    )
                })?;
            adapter_batches_owned = adapter_batches_owned
                .checked_add(current_owned)
                .ok_or_else(|| {
                    BusinessKernelError::new(
                        BusinessKernelErrorKind::Resource,
                        "aggregate adapter storage overflow",
                    )
                })?;
            remaining.max_codec_peak_bytes = remaining
                .max_codec_peak_bytes
                .checked_sub(current_owned)
                .ok_or_else(|| {
                    BusinessKernelError::new(
                        BusinessKernelErrorKind::Resource,
                        "aggregate adapter storage exceeds live budget",
                    )
                })?;
            let bytes = batch
                .iter()
                .flat_map(RecordBatch::columns)
                .try_fold(0usize, |total, array| {
                    total.checked_add(array.get_array_memory_size())
                })
                .ok_or_else(|| {
                    BusinessKernelError::new(
                        BusinessKernelErrorKind::Resource,
                        "input byte count overflow",
                    )
                })?;
            remaining.max_input_bytes =
                remaining
                    .max_input_bytes
                    .checked_sub(bytes)
                    .ok_or_else(|| {
                        BusinessKernelError::new(
                            BusinessKernelErrorKind::Resource,
                            "aggregate input budget exceeded",
                        )
                    })?;
            remaining.max_input_batches = remaining
                .max_input_batches
                .checked_sub(actual_batches)
                .ok_or_else(|| {
                BusinessKernelError::new(
                    BusinessKernelErrorKind::Resource,
                    "aggregate batch budget exceeded",
                )
            })?;
            batches.push(batch);
        }
        core_budgets.max_batches = core_budgets
            .max_batches
            .checked_add(synthesized)
            .ok_or_else(|| {
                BusinessKernelError::new(
                    BusinessKernelErrorKind::Resource,
                    "equivalent empty batch count overflow",
                )
            })?;
        core_budgets.max_live_bytes = core_budgets
            .max_live_bytes
            .checked_sub(adapter_batches_owned)
            .ok_or_else(|| {
                BusinessKernelError::new(
                    BusinessKernelErrorKind::Resource,
                    "adapter batches exceed live budget",
                )
            })?;
        let inputs: Vec<_> = descriptors
            .iter()
            .zip(&batches)
            .map(|(descriptor, batches)| KernelTableInput {
                descriptor,
                batches,
            })
            .collect();
        let options = BusinessKernelOptions {
            budgets: core_budgets,
            control: BusinessKernelControl {
                cancel: Some(cancel.as_ref()),
                deadline,
            },
        };
        let map = |tables, digest, duplicate, count, real, pseudo| NativeOutput {
            tables,
            digest,
            duplicate,
            source_device_row_count: count,
            real,
            pseudo,
        };
        let result = match operation {
            Operation::Sql => {
                let plan = sql_plan.as_ref().ok_or_else(|| {
                    BusinessKernelError::new(BusinessKernelErrorKind::Schema, "SQL plan absent")
                })?;
                let result = materialize_sql_table(inputs[0], plan, pool, options)?;
                KernelOutcome {
                    output: result.output.map(|output| {
                        map(
                            vec![output.table],
                            output.raw_content_digest,
                            output.duplicate_effective_key,
                            None,
                            None,
                            None,
                        )
                    }),
                    diagnostics: result.diagnostics,
                    omitted_diagnostic_count: result.omitted_diagnostic_count,
                }
            }
            Operation::Projection => {
                let plan = projection_plan.as_ref().ok_or_else(|| {
                    BusinessKernelError::new(
                        BusinessKernelErrorKind::Schema,
                        "projection plan absent",
                    )
                })?;
                let result = project_canonical_table(inputs[0], plan, pool, options)?;
                KernelOutcome {
                    output: result.output.map(|output| {
                        map(
                            vec![output.table],
                            Some(output.raw_content_digest),
                            false,
                            None,
                            output.gid_real_count,
                            output.gid_pseudo_count,
                        )
                    }),
                    diagnostics: result.diagnostics,
                    omitted_diagnostic_count: result.omitted_diagnostic_count,
                }
            }
            Operation::Catalog => {
                let device = inputs
                    .iter()
                    .find(|input| input.descriptor.canonical_name == "device")
                    .copied();
                let points: Vec<_> = inputs
                    .iter()
                    .filter(|input| input.descriptor.canonical_name != "device")
                    .map(|input| NamedKernelTableInput {
                        table_name: &input.descriptor.canonical_name,
                        table: *input,
                    })
                    .collect();
                let result = filter_catalog(
                    CatalogFilterInput {
                        device_table: device,
                        point_tables: &points,
                    },
                    pool,
                    options,
                )?;
                KernelOutcome {
                    output: result.output.map(|output| {
                        map(
                            output
                                .matching_devices
                                .into_iter()
                                .chain(output.special_points)
                                .collect(),
                            None,
                            false,
                            Some(output.source_device_row_count),
                            None,
                            None,
                        )
                    }),
                    diagnostics: result.diagnostics,
                    omitted_diagnostic_count: result.omitted_diagnostic_count,
                }
            }
        };
        options.checkpoint()?;
        Ok::<_, BusinessKernelError>(result)
    });
    if watch.probe_failed.load(Ordering::Relaxed) {
        return Err(PyRuntimeError::new_err(
            "business cancellation probe failed",
        ));
    }
    let outcome = outcome.map_err(business_error)?;
    python_adapter_control(&watch, deadline)?;
    output_transfer_preflight(
        &outcome,
        operation,
        budgets,
        owned_metadata,
        &watch,
        deadline,
    )?;
    output_object(py, outcome, &watch, deadline)
}

macro_rules! entry {
    ($name:ident, $operation:ident) => {
        #[pyfunction]
        #[pyo3(signature = (tables, plan, cancel_probe, budgets, deadline_monotonic=None, pool_threads=1))]
        fn $name(py: Python<'_>, tables: Bound<'_, PyList>, plan: Bound<'_, PyDict>, cancel_probe: Py<PyAny>, budgets: Bound<'_, PyDict>, deadline_monotonic: Option<f64>, pool_threads: usize) -> PyResult<Py<PyAny>> {
            match adapter_boundary(|| native_inner(py, Operation::$operation, tables, plan, budgets, (cancel_probe, deadline_monotonic, pool_threads))) { Ok(result) => result, Err(()) => Err(PyRuntimeError::new_err("business kernel adapter panicked")) }
        }
    };
}
entry!(_sql_materialize_native, Sql);
entry!(_canonical_project_native, Projection);
entry!(_catalog_filter_native, Catalog);

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(_sql_materialize_native, module)?)?;
    module.add_function(wrap_pyfunction!(_canonical_project_native, module)?)?;
    module.add_function(wrap_pyfunction!(_catalog_filter_native, module)?)?;
    Ok(())
}
