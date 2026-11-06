//! Arrow business operations. No Python values, paths, or process-global pool.

use std::collections::{BTreeSet, HashSet};
use std::sync::Arc;

use arrow_array::{
    Array, ArrayRef, BinaryArray, BooleanArray, Float32Array, Float64Array, Int64Array,
    RecordBatch, RecordBatchOptions, StringArray, UInt64Array,
};
use arrow_schema::{Field, Schema};
use gateway_shared_kernel::{
    DeclaredType, canonicalize_identifier, unordered_row_hashes_content_digest,
};

use super::cells::{self, Cell, encoding_error, value_error};
use super::*;
use crate::table_access::SqlLogicalType;

/// Conservative local reservation. Temporary shared-encoder copies are checked
/// against retained allocations before the encoder is called, then released.
struct Working<'a> {
    options: BusinessKernelOptions<'a>,
    retained: usize,
}

impl Working<'_> {
    fn ensure(&self, extra: usize) -> Result<(), BusinessKernelError> {
        self.options.checkpoint()?;
        if self
            .retained
            .checked_add(extra)
            .is_none_or(|total| total > self.options.budgets.max_live_bytes)
        {
            return Err(resource_error(
                "business kernel live allocation budget exceeded",
            ));
        }
        Ok(())
    }
    fn reserve(&mut self, bytes: usize) -> Result<(), BusinessKernelError> {
        self.ensure(bytes)?;
        self.retained += bytes;
        Ok(())
    }
}

fn mul(a: usize, b: usize) -> Result<usize, BusinessKernelError> {
    a.checked_mul(b)
        .ok_or_else(|| resource_error("business kernel size overflow"))
}
fn add(a: usize, b: usize) -> Result<usize, BusinessKernelError> {
    a.checked_add(b)
        .ok_or_else(|| resource_error("business kernel size overflow"))
}

fn schema_error(message: impl Into<String>) -> BusinessKernelError {
    BusinessKernelError::new(BusinessKernelErrorKind::Schema, message)
}

fn validate_table(
    input: KernelTableInput<'_>,
    options: BusinessKernelOptions<'_>,
) -> Result<KernelTableInputFacts, BusinessKernelError> {
    let facts = preflight_table_input(input, options)?;
    if add(
        mul(facts.metadata_bytes, 4)?,
        mul(input.descriptor.columns.len(), 1024)?,
    )? > options.budgets.max_live_bytes
    {
        return Err(resource_error("descriptor allocation budget exceeded"));
    }
    if !input.descriptor.reader_ready {
        return Err(schema_error("table has no READY reader"));
    }
    let columns = &input.descriptor.columns;
    // Validate names without allocating an unbounded lookup table.
    for (index, column) in columns.iter().enumerate() {
        options.checkpoint()?;
        if column.ordinal != index
            || canonicalize_identifier(&column.canonical_name).map_err(encoding_error)?
                != column.canonical_name
        {
            return Err(schema_error("invalid canonical column name or ordinal"));
        }
        if columns[..index]
            .iter()
            .any(|other| other.canonical_name == column.canonical_name)
        {
            return Err(schema_error("duplicate canonical column name"));
        }
    }
    for batch in input.batches {
        for (column, (field, array)) in columns
            .iter()
            .zip(batch.schema().fields().iter().zip(batch.columns()))
        {
            options.checkpoint()?;
            if canonicalize_identifier(field.name()).map_err(encoding_error)?
                != column.canonical_name
                || !cells::accepts(column, array.data_type())
            {
                return Err(schema_error(
                    "Arrow name/type binding does not match descriptor",
                ));
            }
        }
    }
    Ok(facts)
}

fn workspace<'a>(
    input: KernelTableInput<'_>,
    options: BusinessKernelOptions<'a>,
) -> Result<(KernelTableInputFacts, Working<'a>), BusinessKernelError> {
    let facts = validate_table(input, options)?;
    let mut working = Working {
        options,
        retained: 0,
    };
    // Owned descriptors, batch/array references, reusable row cells and names.
    working.reserve(add(
        mul(facts.metadata_bytes, 4)?,
        mul(input.descriptor.columns.len(), 1024)?,
    )?)?;
    working.reserve(mul(
        input.batches.len(),
        add(256, mul(input.descriptor.columns.len(), 32)?)?,
    )?)?;
    Ok((facts, working))
}

fn indices(
    columns: &[ColumnDescriptor],
    names: &[String],
) -> Result<Vec<usize>, BusinessKernelError> {
    names
        .iter()
        .map(|name| {
            columns
                .iter()
                .position(|column| column.canonical_name == *name)
                .ok_or_else(|| schema_error(format!("unknown key column {name:?}")))
        })
        .collect()
}

fn row_cells<'a>(
    batch: &'a RecordBatch,
    row: usize,
    columns: &[ColumnDescriptor],
    working: &Working<'_>,
) -> Result<Vec<Cell<'a>>, BusinessKernelError> {
    let mut scratch = mul(columns.len(), 256)?;
    for (column, array) in columns.iter().zip(batch.columns()) {
        let cell = cells::read(array.as_ref(), row)?;
        scratch = add(
            scratch,
            cell.scratch_bytes(column)
                .ok_or_else(|| resource_error("cell scratch overflow"))?,
        )?;
    }
    working.ensure(mul(scratch, 4)?)?;
    batch
        .columns()
        .iter()
        .map(|array| cells::read(array.as_ref(), row))
        .collect()
}

fn table_digest(
    hashes: &[[u8; 32]],
    working: &Working<'_>,
) -> Result<[u8; 32], BusinessKernelError> {
    // Shared helper simultaneously copies/sorts hashes, builds frame, and
    // copies semantic preimage; allow Vec growth in all those allocations.
    working.ensure(add(mul(hashes.len(), 256)?, 1024)?)?;
    let result = unordered_row_hashes_content_digest(hashes).map_err(encoding_error)?;
    working.options.checkpoint()?;
    Ok(*result.raw_digest())
}

fn diagnostic(
    code: &str,
    message: impl Into<String>,
    table: &str,
    column: Option<&str>,
) -> KernelDiagnostic {
    KernelDiagnostic {
        code: code.to_owned(),
        message: message.into(),
        table: Some(table.to_owned()),
        column: column.map(str::to_owned),
        severity: KernelDiagnosticSeverity::Error,
    }
}

fn outcome<T>(
    output: Option<T>,
    diagnostics: Vec<KernelDiagnostic>,
    omitted: usize,
    options: BusinessKernelOptions<'_>,
) -> Result<KernelOutcome<T>, BusinessKernelError> {
    options.checkpoint()?;
    let mut bytes = 0;
    for diagnostic in &diagnostics {
        bytes = add(
            bytes,
            add(
                add(diagnostic.code.len(), diagnostic.message.len())?,
                add(
                    diagnostic.table.as_ref().map_or(0, String::len),
                    diagnostic.column.as_ref().map_or(0, String::len),
                )?,
            )?,
        )?;
    }
    if bytes > options.budgets.max_diagnostic_bytes {
        return Err(resource_error("diagnostic byte budget exceeded"));
    }
    Ok(KernelOutcome {
        output,
        diagnostics,
        omitted_diagnostic_count: omitted,
    })
}

/// Materialize one READY SQL table. Duplicate effective keys warn and retain
/// every source row; a provisional table has no publishable content digest.
pub fn materialize_sql_table(
    input: KernelTableInput<'_>,
    plan: &SqlMaterializationPlan,
    pool: &rayon::ThreadPool,
    options: BusinessKernelOptions<'_>,
) -> Result<KernelOutcome<SqlMaterializationOutput>, BusinessKernelError> {
    pool.install(|| {
        let (facts, mut working) = workspace(input, options)?;
        let plan_bytes = plan
            .effective_compare_key_columns
            .iter()
            .try_fold(0usize, |total, name| add(total, name.len()))?;
        if add(facts.metadata_bytes, plan_bytes)? > options.budgets.max_metadata_bytes {
            return Err(resource_error("SQL plan metadata budget exceeded"));
        }
        working.reserve(mul(plan.effective_compare_key_columns.len(), 128)?)?;
        let keys = indices(
            &input.descriptor.columns,
            &plan.effective_compare_key_columns,
        )?;
        let gid = input
            .descriptor
            .columns
            .iter()
            .position(|column| column.canonical_name == "gid");
        working.reserve(mul(facts.row_count, 64)?)?;
        let mut hashes = Vec::with_capacity(facts.row_count);
        let mut seen = HashSet::new();
        let mut duplicate = false;
        for batch in input.batches {
            for row in 0..batch.num_rows() {
                options.checkpoint()?;
                let values = row_cells(batch, row, &input.descriptor.columns, &working)?;
                if let Some(index) = gid {
                    let parsed = cells::integer(values[index]).or_else(|| {
                        if let Cell::Text(text) = values[index] {
                            text.trim().parse::<i128>().ok()
                        } else {
                            None
                        }
                    });
                    if parsed.is_some_and(|value| (4_000_000_000..=4_294_967_295).contains(&value))
                    {
                        return outcome(
                            None,
                            vec![diagnostic(
                                "RESERVED_PSEUDO_GID",
                                "SQL source gid is in the reserved pseudo range",
                                &input.descriptor.canonical_name,
                                None,
                            )],
                            0,
                            options,
                        );
                    }
                }
                for (column, value) in input.descriptor.columns.iter().zip(&values) {
                    if !column.nullable && matches!(value, Cell::Null) {
                        return Err(value_error("non-nullable SQL cell is null"));
                    }
                }
                hashes.push(cells::row_hash(&input.descriptor.columns, &values)?);
                if !keys.is_empty() {
                    let retained_key_upper =
                        keys.iter()
                            .try_fold(mul(keys.len(), 256)?, |total, &index| {
                                add(
                                    total,
                                    values[index]
                                        .scratch_bytes(&input.descriptor.columns[index])
                                        .ok_or_else(|| resource_error("key scratch overflow"))?,
                                )
                            })?;
                    working.reserve(retained_key_upper)?;
                    let mut key = Vec::with_capacity(keys.len());
                    for &index in &keys {
                        key.push(cells::frame(
                            &input.descriptor.columns[index],
                            values[index],
                        )?);
                    }
                    if !seen.insert(key) {
                        duplicate = true;
                    }
                }
            }
        }
        let raw_content_digest = if plan.stage == MaterializationStage::Final {
            Some(table_digest(&hashes, &working)?)
        } else {
            None
        };
        if facts.input_bytes > options.budgets.max_output_bytes {
            return Err(resource_error("returned Arrow exceeds output byte budget"));
        }
        let mut diagnostics = Vec::new();
        if duplicate {
            let mut warning = diagnostic(
                "DUPLICATE_EFFECTIVE_KEY",
                "duplicate effective key rows were preserved",
                &input.descriptor.canonical_name,
                None,
            );
            warning.severity = KernelDiagnosticSeverity::Warning;
            diagnostics.push(warning);
        }
        outcome(
            Some(SqlMaterializationOutput {
                table: KernelArrowTable {
                    descriptor: input.descriptor.clone(),
                    batches: input.batches.to_vec(),
                    row_count: facts.row_count,
                },
                raw_content_digest,
                duplicate_effective_key: duplicate,
            }),
            diagnostics,
            0,
            options,
        )
    })
}

#[derive(Clone, Copy)]
struct Row {
    batch: usize,
    row: usize,
    gid: Option<u64>,
}

fn selected_cell<'a>(
    input: KernelTableInput<'a>,
    row: Row,
    source_index: usize,
) -> Result<Cell<'a>, BusinessKernelError> {
    if input.descriptor.columns[source_index].canonical_name == "gid" {
        if let Some(gid) = row.gid {
            return Ok(Cell::UInt(gid));
        }
    }
    cells::read(
        input.batches[row.batch].column(source_index).as_ref(),
        row.row,
    )
}

fn arrow_table(
    input: KernelTableInput<'_>,
    columns: &[CanonicalProjectionColumn],
    rows: &[Row],
    name: &str,
    primary_key: &[String],
    working: &mut Working<'_>,
) -> Result<KernelArrowTable, BusinessKernelError> {
    let mut estimated = mul(columns.len(), add(1024, mul(rows.len(), 24)?)?)?;
    for column in columns {
        let source_index = column
            .source_index
            .ok_or_else(|| schema_error("missing source column"))?;
        for &row in rows {
            working.options.checkpoint()?;
            match selected_cell(input, row, source_index)? {
                Cell::Text(text) => estimated = add(estimated, mul(text.len(), 4)?)?,
                Cell::Binary(bytes) => estimated = add(estimated, mul(bytes.len(), 4)?)?,
                _ => {}
            }
        }
    }
    if estimated > working.options.budgets.max_output_bytes {
        return Err(resource_error("returned Arrow exceeds output byte budget"));
    }
    working.reserve(mul(estimated, 2)?)?;
    let mut arrays = Vec::<ArrayRef>::with_capacity(columns.len());
    let mut descriptors = Vec::with_capacity(columns.len());
    for (ordinal, column) in columns.iter().enumerate() {
        working.options.checkpoint()?;
        let index = column
            .source_index
            .ok_or_else(|| schema_error("missing source column"))?;
        let values = rows
            .iter()
            .map(|&row| selected_cell(input, row, index))
            .collect::<Result<Vec<_>, _>>()?;
        macro_rules! array {
            ($ty:ty, $variant:ident) => {
                Arc::new(<$ty>::from_iter(values.iter().map(|cell| {
                    if let Cell::$variant(value) = cell {
                        Some(*value)
                    } else {
                        None
                    }
                }))) as ArrayRef
            };
        }
        use DeclaredType as D;
        let array: ArrayRef = match column.descriptor.declared_type.as_ref() {
            Some(D::SignedInteger { .. }) => array!(Int64Array, Int),
            Some(D::UnsignedInteger { .. }) => Arc::new(UInt64Array::from_iter(values.iter().map(
                |cell| match cell {
                    Cell::UInt(value) => Some(*value),
                    Cell::Int(value) => u64::try_from(*value).ok(),
                    _ => None,
                },
            ))),
            Some(D::Boolean) => array!(BooleanArray, Bool),
            Some(D::Float32) => Arc::new(Float32Array::from_iter(values.iter().map(|cell| {
                if let Cell::F32(value) = cell {
                    Some(if *value == 0.0 { 0.0 } else { *value })
                } else {
                    None
                }
            }))),
            Some(D::Float64) => Arc::new(Float64Array::from_iter(values.iter().map(|cell| {
                if let Cell::F64(value) = cell {
                    Some(if *value == 0.0 { 0.0 } else { *value })
                } else {
                    None
                }
            }))),
            Some(D::Binary | D::Bit { .. }) => {
                Arc::new(BinaryArray::from_iter(values.iter().map(|cell| {
                    if let Cell::Binary(value) = cell {
                        Some(*value)
                    } else {
                        None
                    }
                })))
            }
            _ => {
                let text = values
                    .iter()
                    .map(|cell| match cell {
                        Cell::Null => Ok(None),
                        Cell::Text(text)
                            if column.descriptor.logical_type == SqlLogicalType::Set =>
                        {
                            cells::set_members(text, &column.descriptor)
                                .map(|members| Some(members.join(",")))
                        }
                        Cell::Text(text) => Ok(Some((*text).to_owned())),
                        _ => Err(value_error("output text cell has wrong type")),
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                Arc::new(StringArray::from_iter(text))
            }
        };
        arrays.push(array);
        let mut descriptor = column.descriptor.clone();
        descriptor.ordinal = ordinal;
        descriptors.push(descriptor);
    }
    let schema = Arc::new(Schema::new(
        descriptors
            .iter()
            .zip(&arrays)
            .map(|(column, array)| {
                Field::new(
                    &column.canonical_name,
                    array.data_type().clone(),
                    column.nullable,
                )
            })
            .collect::<Vec<_>>(),
    ));
    working.options.checkpoint()?;
    let batch = RecordBatch::try_new_with_options(
        schema,
        arrays,
        &RecordBatchOptions::new().with_row_count(Some(rows.len())),
    )
    .map_err(|error| BusinessKernelError::new(BusinessKernelErrorKind::Arrow, error.to_string()))?;
    let actual = batch.columns().iter().try_fold(0usize, |total, array| {
        add(total, array.get_array_memory_size())
    })?;
    if actual > working.options.budgets.max_output_bytes {
        return Err(resource_error("returned Arrow exceeds output byte budget"));
    }
    Ok(KernelArrowTable {
        descriptor: TableDescriptor {
            display_name: name.to_owned(),
            canonical_name: name.to_owned(),
            columns: descriptors,
            primary_key: primary_key.to_vec(),
            reader_ready: true,
        },
        batches: vec![batch],
        row_count: rows.len(),
    })
}

/// Validate all ordinary device/point identity cells before retaining only the
/// facts needed by the Python composite binder. Identity cardinality stays there.
pub fn filter_catalog(
    input: CatalogFilterInput<'_>,
    pool: &rayon::ThreadPool,
    options: BusinessKernelOptions<'_>,
) -> Result<KernelOutcome<CatalogFilterOutput>, BusinessKernelError> {
    pool.install(|| {
        options.checkpoint()?;
        let mut result = CatalogFilterOutput { source_device_row_count: 0, matching_devices: None, special_points: Vec::new() };
        let mut remaining = options;
        let tables = input.device_table.into_iter().map(|table| (true, table)).chain(input.point_tables.iter().map(|named| (false, named.table)));
        for (device, table) in tables {
            let (facts, mut working) = workspace(table, remaining)?;
            let names = if device { ["gid", "dev_addr", "description"] } else { ["gid", "dev_addr", "name"] };
            let indexes = names.iter().map(|name| table.descriptor.columns.iter().position(|column| column.canonical_name == *name)).collect::<Option<Vec<_>>>();
            let Some(indexes) = indexes else { return outcome(None, vec![diagnostic("CATALOG_UNAVAILABLE", "catalog table is missing required columns", &table.descriptor.canonical_name, None)], 0, options); };
            working.reserve(mul(facts.row_count, 64)?)?;
            let mut selected = Vec::with_capacity(facts.row_count);
            for (batch_index, batch) in table.batches.iter().enumerate() {
                for row in 0..batch.num_rows() {
                    remaining.checkpoint()?;
                    let addr = cells::read(batch.column(indexes[1]).as_ref(), row)?;
                    let addr_value = cells::integer(addr);
                    if !matches!(addr, Cell::Null) && addr_value.is_none() { return outcome(None, vec![diagnostic("CATALOG_UNAVAILABLE", "column 'dev_addr' must be an integer", &table.descriptor.canonical_name, None)], 0, options); }
                    let matching = addr_value == Some(65532);
                    if device || matching {
                        let gid = cells::read(batch.column(indexes[0]).as_ref(), row)?;
                        let text = cells::read(batch.column(indexes[2]).as_ref(), row)?;
                        if cells::integer(gid).is_none() || (device && addr_value.is_none()) || !matches!(text, Cell::Text(_)) {
                            return outcome(None, vec![diagnostic("CATALOG_UNAVAILABLE", "catalog identity columns must have non-null integer/text values", &table.descriptor.canonical_name, None)], 0, options);
                        }
                        if matching && (!device || matches!(text, Cell::Text("复合信号虚装置"))) { selected.push(Row { batch: batch_index, row, gid: None }); }
                    }
                }
            }
            let columns: Vec<_> = table.descriptor.columns.iter().enumerate().map(|(index, descriptor)| CanonicalProjectionColumn { source_index: Some(index), descriptor: descriptor.clone() }).collect();
            let filtered = arrow_table(table, &columns, &selected, &table.descriptor.canonical_name, &table.descriptor.primary_key, &mut working)?;
            let used = filtered.batches.iter().flat_map(RecordBatch::columns).try_fold(0usize, |total, array| add(total, array.get_array_memory_size()))?;
            remaining.budgets.max_output_bytes = remaining.budgets.max_output_bytes.checked_sub(used).ok_or_else(|| resource_error("catalog output budget exceeded"))?;
            remaining.budgets.max_live_bytes = remaining.budgets.max_live_bytes.checked_sub(working.retained).ok_or_else(|| resource_error("catalog live budget exceeded"))?;
            remaining.budgets.max_input_bytes = remaining.budgets.max_input_bytes.checked_sub(facts.input_bytes).ok_or_else(|| resource_error("catalog input budget exceeded"))?;
            if device { result.source_device_row_count = facts.row_count; result.matching_devices = Some(filtered); } else { result.special_points.push(filtered); }
        }
        outcome(Some(result), Vec::new(), 0, options)
    })
}

struct Diagnostics<'a> {
    entries: Vec<KernelDiagnostic>,
    omitted: usize,
    bytes: usize,
    options: BusinessKernelOptions<'a>,
}

impl Diagnostics<'_> {
    fn push(&mut self, diagnostic: &KernelDiagnostic) -> Result<(), BusinessKernelError> {
        self.options.checkpoint()?;
        if self.entries.len() >= BUSINESS_KERNEL_MAX_DIAGNOSTICS {
            self.omitted = add(self.omitted, 1)?;
            return Ok(());
        }
        let bytes = add(
            add(diagnostic.code.len(), diagnostic.message.len())?,
            add(
                diagnostic.table.as_ref().map_or(0, String::len),
                diagnostic.column.as_ref().map_or(0, String::len),
            )?,
        )?;
        let total = add(self.bytes, bytes)?;
        if total > self.options.budgets.max_diagnostic_bytes
            || add(mul(total, 4)?, mul(self.entries.len() + 1, 256)?)?
                > self.options.budgets.max_live_bytes
        {
            return Err(resource_error("diagnostic allocation budget exceeded"));
        }
        self.entries.push(diagnostic.clone());
        self.bytes = total;
        Ok(())
    }
    fn error(
        &mut self,
        code: &str,
        message: &str,
        table: &str,
        column: Option<&str>,
    ) -> Result<(), BusinessKernelError> {
        self.push(&diagnostic(code, message, table, column))
    }
}

fn supported_projection_column(column: &ColumnDescriptor) -> bool {
    if matches!(
        column.logical_type,
        SqlLogicalType::Enum | SqlLogicalType::Set
    ) {
        return column.labels.is_some();
    }
    if column.logical_type != SqlLogicalType::Standard {
        return false;
    }
    match column.declared_type.as_ref() {
        Some(DeclaredType::SignedInteger { bits }) => matches!(bits, 8 | 16 | 24 | 32 | 64),
        Some(DeclaredType::UnsignedInteger { bits }) => matches!(bits, 8 | 16 | 32),
        Some(
            DeclaredType::Float32
            | DeclaredType::Float64
            | DeclaredType::String
            | DeclaredType::DateTime,
        ) => true,
        _ => false,
    }
}

fn ordered_integer(cell: Cell<'_>, blank: bool) -> Result<Option<u64>, BusinessKernelError> {
    if matches!(cell, Cell::Null | Cell::Text("")) {
        return Ok(None);
    }
    let value =
        cells::integer(cell).ok_or_else(|| value_error("ordered integer cell is not numeric"))?;
    let value = u64::try_from(value)
        .map_err(|_| value_error("ordered integer cell must not be negative"))?;
    if blank && value == 0 {
        Ok(None)
    } else {
        Ok(Some(value))
    }
}

fn projection_failure<T>(
    code: &str,
    error: impl std::fmt::Display,
    plan: &CanonicalProjectionPlan,
    options: BusinessKernelOptions<'_>,
) -> Result<KernelOutcome<T>, BusinessKernelError> {
    outcome(
        None,
        vec![diagnostic(
            code,
            error.to_string(),
            &plan.canonical_table,
            None,
        )],
        0,
        options,
    )
}

/// Canonicalize retained Arrow columns, validate key/ordered identity, hash
/// every row, and establish the fixed IPC physical ordering.
pub fn project_canonical_table(
    input: KernelTableInput<'_>,
    plan: &CanonicalProjectionPlan,
    pool: &rayon::ThreadPool,
    options: BusinessKernelOptions<'_>,
) -> Result<KernelOutcome<CanonicalProjectionOutput>, BusinessKernelError> {
    pool.install(|| {
        let (facts, mut working) = workspace(input, options)?;
        let mut plan_metadata = plan.canonical_table.len();
        for column in &plan.columns {
            plan_metadata = add(
                plan_metadata,
                add(
                    add(
                        column.descriptor.canonical_name.len(),
                        column.descriptor.display_name.len(),
                    )?,
                    column.descriptor.sql_type.len(),
                )?,
            )?;
            for label in column.descriptor.labels.iter().flatten() {
                plan_metadata = add(plan_metadata, label.len())?;
            }
        }
        for name in plan
            .canonical_key_columns
            .iter()
            .chain(&plan.structural_columns)
        {
            plan_metadata = add(plan_metadata, name.len())?;
        }
        if plan.columns.len() > options.budgets.max_columns
            || add(facts.metadata_bytes, plan_metadata)? > options.budgets.max_metadata_bytes
        {
            return Err(resource_error("projection plan metadata budget exceeded"));
        }
        working.reserve(add(mul(plan_metadata, 4)?, mul(plan.columns.len(), 1024)?)?)?;
        let mut diagnostics = Diagnostics {
            entries: Vec::new(),
            omitted: plan.omitted_schema_diagnostic_count,
            bytes: 0,
            options,
        };
        for diagnostic in &plan.schema_diagnostics {
            diagnostics.push(diagnostic)?;
        }
        if plan.materialization_stage != MaterializationStage::Final {
            diagnostics.error(
                "BINDING_INVALID",
                "projected tables require FINAL materialization",
                &plan.canonical_table,
                None,
            )?;
        }
        if input.descriptor.canonical_name != plan.canonical_table {
            diagnostics.error(
                "BINDING_INVALID",
                "canonical table name differs from source binding",
                &plan.canonical_table,
                None,
            )?;
        }
        for (index, column) in plan.columns.iter().enumerate() {
            options.checkpoint()?;
            let name = column.descriptor.canonical_name.as_str();
            if plan.columns[..index]
                .iter()
                .any(|other| other.descriptor.canonical_name == name)
            {
                diagnostics.error(
                    "UNSUPPORTED_TABLE",
                    "duplicate retained column",
                    &plan.canonical_table,
                    Some(name),
                )?;
            }
            match column
                .source_index
                .and_then(|index| input.descriptor.columns.get(index))
            {
                Some(source) if source.canonical_name == name => {}
                _ => diagnostics.error(
                    "UNSUPPORTED_TABLE",
                    "retained column is missing from source descriptor",
                    &plan.canonical_table,
                    Some(name),
                )?,
            }
            if !supported_projection_column(&column.descriptor) {
                diagnostics.error(
                    "UNSUPPORTED_TABLE",
                    "column scalar_type is not supported",
                    &plan.canonical_table,
                    Some(name),
                )?;
            }
        }
        if plan.row_policy == ProjectionRowPolicy::Keyed && plan.canonical_key_columns.is_empty() {
            diagnostics.error(
                "UNSUPPORTED_TABLE",
                "keyed projection requires a canonical key",
                &plan.canonical_table,
                None,
            )?;
        }
        for name in plan
            .canonical_key_columns
            .iter()
            .chain(&plan.structural_columns)
        {
            if !plan
                .columns
                .iter()
                .any(|column| column.descriptor.canonical_name == *name)
            {
                diagnostics.error(
                    "UNSUPPORTED_TABLE",
                    "key or structural column is not retained",
                    &plan.canonical_table,
                    Some(name),
                )?;
            }
        }
        for name in &plan.canonical_key_columns {
            if let Some(column) = plan
                .columns
                .iter()
                .find(|column| column.descriptor.canonical_name == *name)
            {
                let token = column.descriptor.sql_type.trim().to_ascii_uppercase();
                let base = token.split(['(', ' ']).next().unwrap_or("");
                if matches!(
                    base,
                    "JSON"
                        | "TINYTEXT"
                        | "TEXT"
                        | "MEDIUMTEXT"
                        | "LONGTEXT"
                        | "TINYBLOB"
                        | "BLOB"
                        | "MEDIUMBLOB"
                        | "LONGBLOB"
                ) {
                    diagnostics.error(
                        "UNSUPPORTED_TABLE",
                        "canonical key column type cannot be indexed by Repository storage",
                        &plan.canonical_table,
                        Some(name),
                    )?;
                }
            }
        }
        if !diagnostics.entries.is_empty() || diagnostics.omitted != 0 {
            return outcome(None, diagnostics.entries, diagnostics.omitted, options);
        }
        if facts.row_count != plan.expected_source_row_count {
            return projection_failure(
                "ROW_INTEGRITY",
                "row count does not match the source descriptor",
                plan,
                options,
            );
        }
        working.reserve(mul(facts.row_count, 384)?)?;
        let mut rows = Vec::with_capacity(facts.row_count);
        for (batch, values) in input.batches.iter().enumerate() {
            for row in 0..values.num_rows() {
                options.checkpoint()?;
                rows.push(Row {
                    batch,
                    row,
                    gid: None,
                });
            }
        }
        let mut real_count = None;
        let mut pseudo_count = None;
        if plan.row_policy == ProjectionRowPolicy::OrderedGidNo {
            let gid_index = input
                .descriptor
                .columns
                .iter()
                .position(|column| column.canonical_name == "gid");
            let no_index = input
                .descriptor
                .columns
                .iter()
                .position(|column| column.canonical_name == "no");
            let (Some(gid_index), Some(no_index)) = (gid_index, no_index) else {
                return projection_failure(
                    "ROW_INTEGRITY",
                    "ordered table requires gid and no columns",
                    plan,
                    options,
                );
            };
            let mut ordered = Vec::with_capacity(rows.len());
            let mut nos = BTreeSet::new();
            let mut real = BTreeSet::new();
            for row in rows {
                options.checkpoint()?;
                let no = ordered_integer(selected_cell(input, row, no_index)?, false);
                let no = match no {
                    Ok(Some(value)) if value > 0 => value,
                    Ok(_) => {
                        return projection_failure(
                            "ROW_INTEGRITY",
                            "ordered no is missing",
                            plan,
                            options,
                        );
                    }
                    Err(error) => return projection_failure("ROW_INTEGRITY", error, plan, options),
                };
                if !nos.insert(no) {
                    return projection_failure(
                        "ROW_INTEGRITY",
                        "ordered no is not unique",
                        plan,
                        options,
                    );
                }
                let gid = match ordered_integer(selected_cell(input, row, gid_index)?, true) {
                    Ok(value) => value,
                    Err(error) => return projection_failure("ROW_INTEGRITY", error, plan, options),
                };
                if let Some(gid) = gid {
                    if gid > 4_294_967_295 || (gid >= 4_000_000_000 && !plan.canonicalized_input) {
                        return projection_failure(
                            "ROW_INTEGRITY",
                            "source gid is outside the real range or in the reserved pseudo range",
                            plan,
                            options,
                        );
                    }
                    if gid < 4_000_000_000 && !real.insert(gid) {
                        return projection_failure(
                            "KEY_DUPLICATE",
                            "canonical key is not unique",
                            plan,
                            options,
                        );
                    }
                }
                ordered.push((no, gid, row));
            }
            if nos.iter().copied().ne(1..=facts.row_count as u64) {
                return projection_failure(
                    "ROW_INTEGRITY",
                    "ordered no must be the continuous range 1..N",
                    plan,
                    options,
                );
            }
            options.checkpoint()?;
            ordered.sort_unstable_by_key(|item| item.0);
            options.checkpoint()?;
            let mut next_pseudo = 4_000_000_000u64;
            rows = Vec::with_capacity(ordered.len());
            for (_, gid, mut row) in ordered {
                options.checkpoint()?;
                let gid = match gid {
                    None => {
                        let value = next_pseudo;
                        next_pseudo += 1;
                        value
                    }
                    Some(value) if value >= 4_000_000_000 => {
                        if value != next_pseudo {
                            return projection_failure(
                                "ROW_INTEGRITY",
                                "canonical pseudo gid does not match ordered allocation",
                                plan,
                                options,
                            );
                        }
                        next_pseudo += 1;
                        value
                    }
                    Some(value) => value,
                };
                if gid > 4_294_967_295 {
                    return projection_failure(
                        "ROW_INTEGRITY",
                        "pseudo gid range is exhausted",
                        plan,
                        options,
                    );
                }
                row.gid = Some(gid);
                rows.push(row);
            }
            real_count = Some(real.len());
            pseudo_count = Some((next_pseudo - 4_000_000_000) as usize);
        }
        let descriptors: Vec<_> = plan
            .columns
            .iter()
            .map(|column| column.descriptor.clone())
            .collect();
        let key_indexes = indices(&descriptors, &plan.canonical_key_columns)?;
        let mut hashes = Vec::with_capacity(rows.len());
        let mut prepared = Vec::with_capacity(rows.len());
        for row in rows {
            options.checkpoint()?;
            let mut scratch = mul(descriptors.len(), 512)?;
            for column in &plan.columns {
                let index = column
                    .source_index
                    .ok_or_else(|| schema_error("missing source column"))?;
                scratch = add(
                    scratch,
                    selected_cell(input, row, index)?
                        .scratch_bytes(&column.descriptor)
                        .ok_or_else(|| resource_error("projection scratch overflow"))?,
                )?;
            }
            working.ensure(mul(scratch, 4)?)?;
            let values: Vec<_> = plan
                .columns
                .iter()
                .map(|column| {
                    selected_cell(
                        input,
                        row,
                        column
                            .source_index
                            .ok_or_else(|| schema_error("missing source column"))?,
                    )
                })
                .collect::<Result<_, _>>()?;
            let mut key = Vec::new();
            if plan.row_policy == ProjectionRowPolicy::Keyed {
                working.reserve(mul(scratch, 2)?)?;
                for &index in &key_indexes {
                    match values[index] {
                        Cell::Null => {
                            return projection_failure(
                                "KEY_NULL",
                                "canonical key contains null",
                                plan,
                                options,
                            );
                        }
                        Cell::Text("") => {
                            return projection_failure(
                                "KEY_EMPTY",
                                "canonical key contains an empty string",
                                plan,
                                options,
                            );
                        }
                        _ if descriptors[index].logical_type == SqlLogicalType::Set => {
                            return projection_failure(
                                "UNSUPPORTED_TABLE",
                                "key cell is not a typed scalar",
                                plan,
                                options,
                            );
                        }
                        _ => {}
                    }
                    match cells::frame(&descriptors[index], values[index]) {
                        Ok(frame) => key.push(frame),
                        Err(error) => {
                            return projection_failure("UNSUPPORTED_TABLE", error, plan, options);
                        }
                    }
                }
            }
            for (column, value) in descriptors.iter().zip(&values) {
                if !column.nullable && matches!(value, Cell::Null) {
                    return projection_failure(
                        "UNSUPPORTED_TABLE",
                        "non-nullable retained cell is null",
                        plan,
                        options,
                    );
                }
            }
            let hash = match cells::row_hash(&descriptors, &values) {
                Ok(hash) => hash,
                Err(error) => return projection_failure("UNSUPPORTED_TABLE", error, plan, options),
            };
            hashes.push(hash);
            prepared.push((key, hash, row));
        }
        options.checkpoint()?;
        match plan.row_policy {
            ProjectionRowPolicy::Keyed => prepared.sort_unstable_by(|a, b| a.0.cmp(&b.0)),
            ProjectionRowPolicy::Keyless => prepared.sort_unstable_by_key(|item| item.1),
            ProjectionRowPolicy::OrderedGidNo => prepared.sort_unstable_by_key(|item| item.2.gid),
        }
        options.checkpoint()?;
        if plan.row_policy == ProjectionRowPolicy::Keyed
            && prepared.windows(2).any(|pair| pair[0].0 == pair[1].0)
        {
            return projection_failure(
                "KEY_DUPLICATE",
                "canonical key is not unique",
                plan,
                options,
            );
        }
        let raw_content_digest = table_digest(&hashes, &working)?;
        let rows: Vec<_> = prepared.iter().map(|item| item.2).collect();
        let table = arrow_table(
            input,
            &plan.columns,
            &rows,
            &plan.canonical_table,
            &plan.canonical_key_columns,
            &mut working,
        )?;
        outcome(
            Some(CanonicalProjectionOutput {
                table,
                raw_content_digest,
                gid_real_count: real_count,
                gid_pseudo_count: pseudo_count,
            }),
            Vec::new(),
            0,
            options,
        )
    })
}
