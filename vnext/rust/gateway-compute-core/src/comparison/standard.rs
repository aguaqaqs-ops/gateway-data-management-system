//! Standard and keyless row comparison over canonical Arrow batches.
//!
//! The result owns cheap `RecordBatch` clones (Arc-backed Arrow buffers) and
//! row locators. C can build Arrow records directly from those locators. No
//! Python row objects or whole-table JSON representation crosses this boundary.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::panic::AssertUnwindSafe;
use std::sync::Arc;

use arrow_array::{Array, RecordBatch};
use arrow_schema::SchemaRef;
use gateway_shared_kernel::{DigestKind, canonicalize_identifier, encode_uleb128, semantic_digest};

use super::kernel::{
    CanonicalBatchSide, KernelContext, KernelLease, sort_indices_checked,
    validate_canonical_batches,
};
use super::ordered::{OrderedCompareError, encode_cell};

const MAX_COLUMNS: usize = 2048;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StandardMode {
    Keyed,
    Keyless,
}

#[derive(Debug, Clone)]
pub struct StandardOptions {
    /// A's selected common columns, in canonical identifier form.
    pub selected_columns: Vec<String>,
    pub effective_key_before: Vec<String>,
    pub effective_key_current: Vec<String>,
    pub compare_excluded_columns: Vec<String>,
    pub incompatible_columns: Vec<String>,
    pub mode: StandardMode,
    pub emit_add_delete: bool,
    /// COLUMNS_ADDED compares the shared projection after compare exclusions.
    pub columns_added: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RowLocation {
    pub batch: usize,
    pub row: usize,
}

/// Resolve a retained row locator against canonical Arrow owners. C's builder
/// charges any copied output frame; this helper itself retains no backing.
pub fn canonical_cell_frame_at(
    batches: &[RecordBatch],
    location: RowLocation,
    column: &str,
) -> Result<Vec<u8>, OrderedCompareError> {
    let batch = batches
        .get(location.batch)
        .ok_or_else(|| OrderedCompareError::new("ROW_LOCATION_INVALID"))?;
    if location.row >= batch.num_rows() {
        return Err(OrderedCompareError::new("ROW_LOCATION_INVALID"));
    }
    let index = batch
        .schema()
        .fields()
        .iter()
        .position(|field| field.name() == column)
        .ok_or_else(|| OrderedCompareError::new("ROW_SHAPE_MISMATCH"))?;
    let field = batch.schema().field(index).clone();
    encode_cell(batch.column(index).as_ref(), location.row, &field).map(|cell| cell.frame)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum StandardKind {
    RowAdded,
    RowDeleted,
    RowModified,
    SchemaChange,
    TableDegraded,
}

impl StandardKind {
    pub fn contract_name(self) -> &'static str {
        match self {
            Self::RowAdded => "ROW_ADDED",
            Self::RowDeleted => "ROW_DELETED",
            Self::RowModified => "ROW_MODIFIED",
            Self::SchemaChange => "SCHEMA_CHANGE",
            Self::TableDegraded => "TABLE_DEGRADED",
        }
    }
}

#[derive(Debug, Clone)]
pub struct StandardRecordRef {
    pub kind: StandardKind,
    pub row_identity: Option<String>,
    pub before: Option<RowLocation>,
    pub current: Option<RowLocation>,
    /// FULL facts payload uses these columns and the referenced Arrow cells.
    pub value_columns: Vec<String>,
    pub changed_columns: Vec<String>,
    pub diagnostics: Vec<String>,
}

pub struct StandardComputation {
    /// These clones keep the Arrow backing valid after the caller's reader
    /// closes. The caller's unique input-owner charge remains pinned while a
    /// result exists; `_lease` charges only local frames/indexes/output refs.
    pub before_batches: Vec<RecordBatch>,
    pub current_batches: Vec<RecordBatch>,
    pub before_schema: SchemaRef,
    pub current_schema: SchemaRef,
    pub records: Vec<StandardRecordRef>,
    /// Facts and artifact use separate index views, even when equal for a
    /// particular standard table. C adds its full-value JCS tie breaker here.
    pub facts_order: Vec<usize>,
    pub artifact_order: Vec<usize>,
    pub row_added_count: usize,
    pub row_deleted_count: usize,
    pub row_modified_count: usize,
    pub suppressed_added_count: usize,
    pub suppressed_deleted_count: usize,
    /// Used only for COLUMNS_ADDED plus compare-excluded shared columns.
    /// Other ignored-content cases use the descriptor raw digest in Python.
    pub ignored_shared_content_changed: bool,
    _lease: KernelLease,
}

struct EncodedRow {
    location: RowLocation,
    frames: Vec<Vec<u8>>,
}

/// The caller schedules this table on its shared pool. This function creates
/// no threads and checks the operation's cancellation/deadline while scanning.
pub fn compare_standard_table(
    before: CanonicalBatchSide<'_>,
    current: CanonicalBatchSide<'_>,
    options: &StandardOptions,
    context: &Arc<KernelContext>,
) -> Result<StandardComputation, OrderedCompareError> {
    match std::panic::catch_unwind(AssertUnwindSafe(|| {
        compare_standard_table_inner(before, current, options, context)
    })) {
        Ok(result) => result,
        Err(_) => Err(OrderedCompareError::new("COMPARISON_INTERNAL_ERROR")),
    }
}

fn compare_standard_table_inner(
    before: CanonicalBatchSide<'_>,
    current: CanonicalBatchSide<'_>,
    options: &StandardOptions,
    context: &Arc<KernelContext>,
) -> Result<StandardComputation, OrderedCompareError> {
    context.check()?;
    let option_bytes = options
        .selected_columns
        .iter()
        .chain(&options.effective_key_before)
        .chain(&options.effective_key_current)
        .chain(&options.compare_excluded_columns)
        .chain(&options.incompatible_columns)
        .try_fold(4096usize, |total, name| {
            total.checked_add(name.len().saturating_mul(8).saturating_add(128))
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let options_lease = context.reserve(option_bytes)?;
    validate_canonical_batches(&before)?;
    validate_canonical_batches(&current)?;
    let before_schema = before.schema;
    let current_schema = current.schema;
    let before = before.batches;
    let current = current.batches;
    let columns = canonical_columns(&options.selected_columns)?;
    let excluded = canonical_columns(&options.compare_excluded_columns)?;
    let incompatible = canonical_columns(&options.incompatible_columns)?;
    let before_key = canonical_columns(&options.effective_key_before)?;
    let current_key = canonical_columns(&options.effective_key_current)?;
    validate_projection(&before_schema, &columns)?;
    validate_projection(&current_schema, &columns)?;
    if columns.len() > MAX_COLUMNS
        || before_key != current_key && options.mode == StandardMode::Keyed
    {
        return Err(OrderedCompareError::new("COMPARISON_POLICY_INVALID"));
    }
    if options.mode == StandardMode::Keyed
        && (before_key.is_empty() || before_key.iter().any(|name| !columns.contains(name)))
    {
        return Err(OrderedCompareError::new("COMPARISON_KEY_INVALID"));
    }
    drop(options_lease);
    let row_count = before
        .iter()
        .chain(current)
        .try_fold(0usize, |total, batch| total.checked_add(batch.num_rows()))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    // Arrow input backing is already charged once by the operation owner.
    // This reservation covers encoded frames (including variable-width copies),
    // row/index capacities and retained record locators. It happens before
    // reading a cell; extra record growth is charged before push below.
    let input_bytes = before
        .iter()
        .chain(current)
        .flat_map(RecordBatch::columns)
        .try_fold(0usize, |total, array| {
            let slice_bytes = array.to_data().get_slice_memory_size().ok()?;
            total.checked_add(slice_bytes)
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let row_overhead = columns
        .len()
        .checked_mul(80)
        .and_then(|bytes| bytes.checked_add(256))
        .and_then(|bytes| bytes.checked_mul(row_count))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let batch_overhead = before
        .len()
        .checked_add(current.len())
        .and_then(|count| count.checked_mul(std::mem::size_of::<RecordBatch>() + 128))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let scratch = input_bytes
        .checked_mul(3)
        .and_then(|bytes| bytes.checked_add(row_overhead))
        .and_then(|bytes| bytes.checked_add(batch_overhead))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let mut lease = context.reserve(scratch)?;
    let before_rows = read_rows(before, &columns, context)?;
    let current_rows = read_rows(current, &columns, context)?;
    let mut records = Vec::new();
    let (added, deleted, modified) = match options.mode {
        StandardMode::Keyed => compare_keyed(
            &before_rows,
            &current_rows,
            &columns,
            &before_key,
            &excluded,
            &incompatible,
            options.emit_add_delete,
            context,
            &mut lease,
            &mut records,
        )?,
        StandardMode::Keyless => compare_keyless(
            &before_rows,
            &current_rows,
            &columns,
            &excluded,
            options.columns_added,
            options.emit_add_delete,
            context,
            &mut lease,
            &mut records,
        )?,
    };
    let ignored_shared_content_changed =
        if options.columns_added && excluded.iter().any(|name| columns.contains(name)) {
            row_counts(&before_rows, &columns, &columns, context)?
                != row_counts(&current_rows, &columns, &columns, context)?
        } else {
            false
        };
    let facts_order = sort_indices_checked(&records, context, |left, right| {
        record_key(left).cmp(&record_key(right))
    })?;
    let artifact_order = facts_order.clone();
    let before_batches = before.to_vec();
    let current_batches = current.to_vec();
    let retained = retained_bytes(
        &before_batches,
        &current_batches,
        &records,
        &facts_order,
        &artifact_order,
    )?;
    lease.shrink_to(retained)?;
    Ok(StandardComputation {
        before_batches,
        current_batches,
        before_schema,
        current_schema,
        records,
        facts_order,
        artifact_order,
        row_added_count: added,
        row_deleted_count: deleted,
        row_modified_count: modified,
        suppressed_added_count: if options.emit_add_delete { 0 } else { added },
        suppressed_deleted_count: if options.emit_add_delete { 0 } else { deleted },
        ignored_shared_content_changed,
        _lease: lease,
    })
}

fn retained_bytes(
    before: &Vec<RecordBatch>,
    current: &Vec<RecordBatch>,
    records: &Vec<StandardRecordRef>,
    facts_order: &Vec<usize>,
    artifact_order: &Vec<usize>,
) -> Result<usize, OrderedCompareError> {
    let fixed = before
        .capacity()
        .checked_add(current.capacity())
        .and_then(|count| count.checked_mul(std::mem::size_of::<RecordBatch>()))
        .and_then(|bytes| {
            records
                .capacity()
                .checked_mul(std::mem::size_of::<StandardRecordRef>())
                .and_then(|part| bytes.checked_add(part))
        })
        .and_then(|bytes| {
            facts_order
                .capacity()
                .checked_add(artifact_order.capacity())
                .and_then(|count| count.checked_mul(std::mem::size_of::<usize>()))
                .and_then(|part| bytes.checked_add(part))
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    records
        .iter()
        .try_fold(fixed, |total, record| {
            let strings = record
                .value_columns
                .iter()
                .chain(&record.changed_columns)
                .chain(&record.diagnostics)
                .try_fold(
                    record.row_identity.as_ref().map_or(0, String::capacity),
                    |size, name| size.checked_add(name.capacity()),
                )?;
            let headers = record
                .value_columns
                .capacity()
                .checked_add(record.changed_columns.capacity())?
                .checked_add(record.diagnostics.capacity())?
                .checked_mul(std::mem::size_of::<String>())?;
            total.checked_add(strings)?.checked_add(headers)
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))
}

fn canonical_columns(input: &[String]) -> Result<Vec<String>, OrderedCompareError> {
    let mut result = Vec::with_capacity(input.len());
    let mut seen = BTreeSet::new();
    for name in input {
        let canonical = canonicalize_identifier(name)
            .map_err(|_| OrderedCompareError::new("COLUMN_NAME_INVALID"))?;
        if canonical != *name || !seen.insert(canonical.clone()) {
            return Err(OrderedCompareError::new("COLUMN_NAME_INVALID"));
        }
        result.push(canonical);
    }
    result.sort_by(|left, right| left.as_bytes().cmp(right.as_bytes()));
    Ok(result)
}

fn validate_projection(schema: &SchemaRef, columns: &[String]) -> Result<(), OrderedCompareError> {
    let mut available = BTreeSet::new();
    for field in schema.fields() {
        let name = canonicalize_identifier(field.name())
            .map_err(|_| OrderedCompareError::new("COLUMN_NAME_INVALID"))?;
        if !available.insert(name) {
            return Err(OrderedCompareError::new("COLUMN_NAME_INVALID"));
        }
    }
    if columns.iter().any(|name| !available.contains(name)) {
        return Err(OrderedCompareError::new("ROW_SHAPE_MISMATCH"));
    }
    Ok(())
}

fn read_rows(
    batches: &[RecordBatch],
    columns: &[String],
    context: &KernelContext,
) -> Result<Vec<EncodedRow>, OrderedCompareError> {
    let mut output = Vec::new();
    for (batch_index, batch) in batches.iter().enumerate() {
        context.check()?;
        let mut mapped = HashMap::new();
        for (index, field) in batch.schema().fields().iter().enumerate() {
            let name = canonicalize_identifier(field.name())
                .map_err(|_| OrderedCompareError::new("COLUMN_NAME_INVALID"))?;
            if mapped.insert(name, index).is_some() {
                return Err(OrderedCompareError::new("COLUMN_NAME_INVALID"));
            }
        }
        let indices = columns
            .iter()
            .map(|name| {
                mapped
                    .get(name)
                    .copied()
                    .ok_or_else(|| OrderedCompareError::new("ROW_SHAPE_MISMATCH"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        for row in 0..batch.num_rows() {
            if row % 1024 == 0 {
                context.check()?;
            }
            let mut frames = Vec::with_capacity(indices.len());
            for (column_index, index) in indices.iter().enumerate() {
                if column_index % 32 == 0 {
                    context.check()?;
                }
                let field = batch.schema().field(*index).clone();
                let frame = encode_cell(batch.column(*index).as_ref(), row, &field)?.frame;
                frames.push(frame);
            }
            output.push(EncodedRow {
                location: RowLocation {
                    batch: batch_index,
                    row,
                },
                frames,
            });
        }
    }
    Ok(output)
}

fn frame_for(
    row: &EncodedRow,
    selected: &[String],
    columns: &[String],
) -> Result<Vec<u8>, OrderedCompareError> {
    let mut frame = encode_uleb128(columns.len() as u64)
        .map_err(|_| OrderedCompareError::new("ROW_ENCODING_FAILED"))?;
    for name in columns {
        let index = selected
            .binary_search_by(|candidate| candidate.as_bytes().cmp(name.as_bytes()))
            .map_err(|_| OrderedCompareError::new("ROW_SHAPE_MISMATCH"))?;
        frame.extend(
            encode_uleb128(name.len() as u64)
                .map_err(|_| OrderedCompareError::new("ROW_ENCODING_FAILED"))?,
        );
        frame.extend_from_slice(name.as_bytes());
        frame.extend_from_slice(&row.frames[index]);
    }
    Ok(frame)
}

fn row_digest(frame: &[u8]) -> Result<String, OrderedCompareError> {
    semantic_digest(DigestKind::Row, frame)
        .map(|digest| digest.digest_ref().as_str().to_string())
        .map_err(|_| OrderedCompareError::new("DIGEST_FAILED"))
}

fn occurrence_digest(digest: &str, occurrence: usize) -> Result<String, OrderedCompareError> {
    if occurrence == 0 {
        return Ok(digest.to_string());
    }
    let mut payload = b"keyless-row-occurrence:v1\0".to_vec();
    payload.extend_from_slice(digest.as_bytes());
    payload.extend(
        encode_uleb128(occurrence as u64)
            .map_err(|_| OrderedCompareError::new("ROW_ENCODING_FAILED"))?,
    );
    row_digest(&payload)
}

/// Exact identity projection shared by comparison and final-file location.
fn keyless_identity_columns(
    selected: &[String],
    excluded: &[String],
    columns_added: bool,
) -> Vec<String> {
    selected
        .iter()
        .filter(|name| !columns_added || !excluded.contains(name))
        .cloned()
        .collect()
}

/// A single table/side scan. Occurrence state spans batch and row-group boundaries,
/// and is charged to the caller's operation context before each new key is retained.
/// No comparison is performed and no Arrow backing escapes a batch call.
pub struct StandardIdentityScanner {
    columns: Vec<String>,
    mode: StandardMode,
    counts: BTreeMap<String, usize>,
    context: Arc<KernelContext>,
    lease: KernelLease,
}

pub struct StandardIdentityBatch {
    pub identities: Vec<String>,
    pub canonical_order_keys: Vec<Vec<u8>>,
    _lease: KernelLease,
}

impl StandardIdentityScanner {
    pub fn new(
        options: &StandardOptions,
        context: &Arc<KernelContext>,
    ) -> Result<Self, OrderedCompareError> {
        let size = options
            .selected_columns
            .iter()
            .chain(&options.effective_key_before)
            .chain(&options.effective_key_current)
            .chain(&options.compare_excluded_columns)
            .try_fold(4096usize, |sum, name| {
                sum.checked_add(name.len().saturating_mul(8).saturating_add(128))
            })
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let lease = context.reserve(size)?;
        let selected = canonical_columns(&options.selected_columns)?;
        let excluded = canonical_columns(&options.compare_excluded_columns)?;
        let before = canonical_columns(&options.effective_key_before)?;
        let current = canonical_columns(&options.effective_key_current)?;
        if selected.len() > MAX_COLUMNS
            || (options.mode == StandardMode::Keyed
                && (before.is_empty()
                    || before != current
                    || before.iter().any(|name| !selected.contains(name))))
        {
            return Err(OrderedCompareError::new("COMPARISON_POLICY_INVALID"));
        }
        let columns = match options.mode {
            StandardMode::Keyed => before,
            StandardMode::Keyless => {
                keyless_identity_columns(&selected, &excluded, options.columns_added)
            }
        };
        Ok(Self {
            columns,
            mode: options.mode,
            counts: BTreeMap::new(),
            context: Arc::clone(context),
            lease,
        })
    }

    /// The input owner admits the decoded Arrow batch separately. This admission
    /// covers encoded cells, whole-row order keys, identities and their Python
    /// boundary copies until the next scan releases this returned batch.
    pub fn scan(
        &mut self,
        side: CanonicalBatchSide<'_>,
    ) -> Result<StandardIdentityBatch, OrderedCompareError> {
        self.context.check()?;
        let input_bytes = side
            .batches
            .iter()
            .flat_map(RecordBatch::columns)
            .try_fold(0usize, |sum, array| {
                sum.checked_add(array.to_data().get_slice_memory_size().ok()?)
            })
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let row_count = side
            .batches
            .iter()
            .try_fold(0usize, |sum, batch| sum.checked_add(batch.num_rows()))
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let size = side
            .schema
            .fields()
            .len()
            .checked_mul(160)
            .and_then(|n| n.checked_add(1024))
            .and_then(|n| n.checked_mul(row_count))
            .and_then(|n| n.checked_add(input_bytes.checked_mul(8)?))
            .and_then(|n| n.checked_add(8192))
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let lease = self.context.reserve(size)?;
        validate_canonical_batches(&side)?;
        validate_projection(&side.schema, &self.columns)?;
        let all = canonical_columns(
            &side
                .schema
                .fields()
                .iter()
                .map(|f| f.name().clone())
                .collect::<Vec<_>>(),
        )?;
        let rows = read_rows(side.batches, &all, &self.context)?;
        let mut identities = Vec::with_capacity(row_count);
        let mut canonical_order_keys = Vec::with_capacity(row_count);
        for row in &rows {
            self.context.check()?;
            let digest = row_digest(&frame_for(row, &all, &self.columns)?)?;
            let identity = if self.mode == StandardMode::Keyless {
                if !self.counts.contains_key(&digest) {
                    self.lease.grow(256 + digest.len() * 2)?;
                }
                let count = self.counts.entry(digest.clone()).or_default();
                let result = occurrence_digest(&digest, *count)?;
                *count = count
                    .checked_add(1)
                    .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
                result
            } else {
                digest
            };
            identities.push(identity);
            canonical_order_keys.push(frame_for(row, &all, &all)?);
        }
        Ok(StandardIdentityBatch {
            identities,
            canonical_order_keys,
            _lease: lease,
        })
    }
}

fn reserve_record(
    lease: &mut KernelLease,
    value_columns: &[String],
    changed_columns: &[String],
) -> Result<(), OrderedCompareError> {
    // Reserve the row identity, Vec capacities, String headers and text before
    // any of those output allocations take place. The scratch lease already
    // covers the temporary frame and iterator state used to find a change.
    let extra = value_columns
        .iter()
        .chain(changed_columns)
        .try_fold(512usize, |total, name| {
            total.checked_add(std::mem::size_of::<String>() + name.len())
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    lease.grow(extra)?;
    Ok(())
}

// Keep caller-owned control, lease and result vector explicit at this row boundary.
#[allow(clippy::too_many_arguments)]
fn compare_keyed(
    before: &[EncodedRow],
    current: &[EncodedRow],
    selected: &[String],
    key: &[String],
    excluded: &[String],
    incompatible: &[String],
    emit_add_delete: bool,
    context: &KernelContext,
    lease: &mut KernelLease,
    records: &mut Vec<StandardRecordRef>,
) -> Result<(usize, usize, usize), OrderedCompareError> {
    let before_index = key_index(before, selected, key, context)?;
    let current_index = key_index(current, selected, key, context)?;
    let mut added = 0;
    let mut deleted = 0;
    let mut modified = 0;
    for (frame, current_row) in &current_index {
        context.check()?;
        let Some(before_row) = before_index.get(frame) else {
            added += 1;
            if emit_add_delete {
                reserve_record(lease, selected, &[])?;
                records.push(StandardRecordRef {
                    kind: StandardKind::RowAdded,
                    row_identity: Some(row_digest(frame)?),
                    before: None,
                    current: Some(current_row.location),
                    value_columns: selected.to_vec(),
                    changed_columns: Vec::new(),
                    diagnostics: Vec::new(),
                });
            }
            continue;
        };
        let has_change = selected.iter().enumerate().any(|(index, name)| {
            !key.contains(name)
                && !excluded.contains(name)
                && !incompatible.contains(name)
                && before_row.frames[index] != current_row.frames[index]
        });
        if has_change {
            modified += 1;
            reserve_record(lease, selected, selected)?;
            let changed = selected
                .iter()
                .enumerate()
                .filter(|(index, name)| {
                    !key.contains(name)
                        && !excluded.contains(name)
                        && !incompatible.contains(name)
                        && before_row.frames[*index] != current_row.frames[*index]
                })
                .map(|(_, name)| name.clone())
                .collect::<Vec<_>>();
            records.push(StandardRecordRef {
                kind: StandardKind::RowModified,
                row_identity: Some(row_digest(frame)?),
                before: Some(before_row.location),
                current: Some(current_row.location),
                value_columns: changed.clone(),
                changed_columns: changed,
                diagnostics: Vec::new(),
            });
        }
    }
    for (frame, before_row) in &before_index {
        context.check()?;
        if !current_index.contains_key(frame) {
            deleted += 1;
            if emit_add_delete {
                reserve_record(lease, selected, &[])?;
                records.push(StandardRecordRef {
                    kind: StandardKind::RowDeleted,
                    row_identity: Some(row_digest(frame)?),
                    before: Some(before_row.location),
                    current: None,
                    value_columns: selected.to_vec(),
                    changed_columns: Vec::new(),
                    diagnostics: Vec::new(),
                });
            }
        }
    }
    Ok((added, deleted, modified))
}

fn key_index<'a>(
    rows: &'a [EncodedRow],
    selected: &[String],
    key: &[String],
    context: &KernelContext,
) -> Result<BTreeMap<Vec<u8>, &'a EncodedRow>, OrderedCompareError> {
    let mut index = BTreeMap::new();
    for (row_number, row) in rows.iter().enumerate() {
        if row_number % 1024 == 0 {
            context.check()?;
        }
        let frame = frame_for(row, selected, key)?;
        if index.insert(frame, row).is_some() {
            return Err(OrderedCompareError::new("DUPLICATE_EFFECTIVE_KEY"));
        }
    }
    Ok(index)
}

// Keep caller-owned control, lease and result vector explicit at this row boundary.
#[allow(clippy::too_many_arguments)]
fn compare_keyless(
    before: &[EncodedRow],
    current: &[EncodedRow],
    selected: &[String],
    excluded: &[String],
    columns_added: bool,
    emit_add_delete: bool,
    context: &KernelContext,
    lease: &mut KernelLease,
    records: &mut Vec<StandardRecordRef>,
) -> Result<(usize, usize, usize), OrderedCompareError> {
    let columns = keyless_identity_columns(selected, excluded, columns_added);
    let before_counts = row_counts(before, selected, &columns, context)?;
    let current_counts = row_counts(current, selected, &columns, context)?;
    let mut added = 0;
    let mut deleted = 0;
    for (identity, current_count) in &current_counts {
        let before_count = before_counts.get(identity).copied().unwrap_or_default();
        for occurrence in before_count..*current_count {
            context.check()?;
            added += 1;
            if emit_add_delete {
                reserve_record(lease, &[], &[])?;
                records.push(StandardRecordRef {
                    kind: StandardKind::RowAdded,
                    row_identity: Some(occurrence_digest(identity, occurrence)?),
                    before: None,
                    current: None,
                    value_columns: Vec::new(),
                    changed_columns: Vec::new(),
                    diagnostics: Vec::new(),
                });
            }
        }
    }
    for (identity, before_count) in &before_counts {
        let current_count = current_counts.get(identity).copied().unwrap_or_default();
        for occurrence in current_count..*before_count {
            context.check()?;
            deleted += 1;
            if emit_add_delete {
                reserve_record(lease, &[], &[])?;
                records.push(StandardRecordRef {
                    kind: StandardKind::RowDeleted,
                    row_identity: Some(occurrence_digest(identity, occurrence)?),
                    before: None,
                    current: None,
                    value_columns: Vec::new(),
                    changed_columns: Vec::new(),
                    diagnostics: Vec::new(),
                });
            }
        }
    }
    Ok((added, deleted, 0))
}

fn row_counts(
    rows: &[EncodedRow],
    selected: &[String],
    columns: &[String],
    context: &KernelContext,
) -> Result<BTreeMap<String, usize>, OrderedCompareError> {
    let mut counts = BTreeMap::<String, usize>::new();
    for (index, row) in rows.iter().enumerate() {
        if index % 1024 == 0 {
            context.check()?;
        }
        let digest = row_digest(&frame_for(row, selected, columns)?)?;
        let count = counts.entry(digest).or_default();
        *count = count
            .checked_add(1)
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    }
    Ok(counts)
}

fn record_key(record: &StandardRecordRef) -> (&'static str, Option<&str>, &[String]) {
    (
        record.kind.contract_name(),
        record.row_identity.as_deref(),
        &record.changed_columns,
    )
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::sync::atomic::AtomicBool;

    use arrow_array::{ArrayRef, Int64Array, RecordBatch, StringArray};
    use arrow_schema::{DataType, Field, Schema};
    use rayon::prelude::*;

    use super::*;
    use crate::comparison::ordered::{
        BlankProvenance, OrderedBatchPair, OrderedCompareOptions, compare_ordered_batches,
        summarize_unchanged_ordered_batches,
    };

    fn field(
        name: &str,
        sql: &str,
        logical: &str,
        kind: Option<&str>,
        data_type: DataType,
    ) -> Field {
        // S2b canonical IPC carries the SQL integer width in declared_type.
        let bits = if kind == Some("signed-integer") {
            assert_eq!(sql, "BIGINT");
            Some(64u8)
        } else {
            None
        };
        let declared = kind.map_or(serde_json::Value::Null, |kind| {
            serde_json::json!({
                "kind":kind,"bits":bits,"precision":null,"scale":null,"bit_width":null
            })
        });
        let labels = if logical == "set" {
            serde_json::json!(["a", "b"])
        } else {
            serde_json::Value::Null
        };
        let metadata = serde_json::json!({
            "declared_type":declared,"labels":labels,"logical_type":logical,"sql_type":sql
        });
        Field::new(name, data_type, true).with_metadata(HashMap::from([(
            "gdds.canonical_type".to_string(),
            metadata.to_string(),
        )]))
    }

    fn schema() -> SchemaRef {
        Arc::new(
            Schema::new(vec![
                field(
                    "id",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "name",
                    "VARCHAR(64)",
                    "standard",
                    Some("string"),
                    DataType::Utf8,
                ),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".to_string(),
                "1".to_string(),
            )])),
        )
    }

    fn batch(ids: &[i64], names: &[&str]) -> Result<RecordBatch, arrow_schema::ArrowError> {
        RecordBatch::try_new(
            schema(),
            vec![
                Arc::new(Int64Array::from(ids.to_vec())) as ArrayRef,
                Arc::new(StringArray::from(names.to_vec())) as ArrayRef,
            ],
        )
    }

    fn options(mode: StandardMode) -> StandardOptions {
        StandardOptions {
            selected_columns: vec!["name".to_string(), "id".to_string()],
            effective_key_before: vec!["id".to_string()],
            effective_key_current: vec!["id".to_string()],
            compare_excluded_columns: Vec::new(),
            incompatible_columns: Vec::new(),
            mode,
            emit_add_delete: true,
            columns_added: false,
        }
    }

    fn context() -> Arc<KernelContext> {
        Arc::new(KernelContext::new(
            16 * 1024 * 1024,
            Arc::new(AtomicBool::new(false)),
            None,
        ))
    }

    fn compare(
        before: &[RecordBatch],
        current: &[RecordBatch],
        policy: &StandardOptions,
        context: &Arc<KernelContext>,
    ) -> Result<StandardComputation, OrderedCompareError> {
        let before_schema = before
            .first()
            .map(RecordBatch::schema)
            .unwrap_or_else(schema);
        let current_schema = current
            .first()
            .map(RecordBatch::schema)
            .unwrap_or_else(schema);
        compare_standard_table(
            CanonicalBatchSide::new(before_schema, before),
            CanonicalBatchSide::new(current_schema, current),
            policy,
            context,
        )
    }

    #[test]
    fn identity_scanner_uses_comparison_projection_and_cross_batch_occurrences()
    -> Result<(), Box<dyn std::error::Error>> {
        for mode in [StandardMode::Keyed, StandardMode::Keyless] {
            for columns_added in [false, true] {
                let mut policy = options(mode);
                policy.columns_added = columns_added;
                policy.compare_excluded_columns = vec!["name".to_string()];
                let before = batch(&[1], &["same"])?;
                let current = batch(&[1, 1, 1, 1], &["same", "same", "same", "same"])?;
                let context = context();
                // Keyed comparison rejects duplicate keys; use a single modified
                // row there, and the third+ keyless copies for multiset identity.
                let current = if mode == StandardMode::Keyed {
                    batch(&[1, 2], &["same", "new"])?
                } else {
                    current
                };
                let compared = compare(
                    std::slice::from_ref(&before),
                    std::slice::from_ref(&current),
                    &policy,
                    &context,
                )?;
                let mut scanner = StandardIdentityScanner::new(&policy, &context)?;
                let mut scanned = Vec::new();
                for offset in 0..current.num_rows() {
                    let batch = current.slice(offset, 1);
                    let output = scanner.scan(CanonicalBatchSide::new(batch.schema(), &[batch]))?;
                    scanned.extend(output.identities.iter().cloned());
                    assert_eq!(output.canonical_order_keys.len(), 1);
                }
                let actual = compared
                    .records
                    .iter()
                    .filter_map(|r| r.row_identity.clone())
                    .collect::<BTreeSet<_>>();
                let expected = scanned.into_iter().skip(1).collect::<BTreeSet<_>>();
                assert_eq!(actual, expected);
                drop(scanner);
                drop(compared);
                assert_eq!(context.remaining_bytes(), 16 * 1024 * 1024);
            }
        }
        Ok(())
    }

    #[test]
    fn identity_scanner_charges_distinct_counts_and_honors_control()
    -> Result<(), Box<dyn std::error::Error>> {
        let cancelled = Arc::new(AtomicBool::new(false));
        let context = Arc::new(KernelContext::new(32 * 1024, Arc::clone(&cancelled), None));
        let mut scanner = StandardIdentityScanner::new(&options(StandardMode::Keyless), &context)?;
        let mut exhausted = false;
        for id in 0..1000 {
            let batch = batch(&[id], &["same"])?;
            match scanner.scan(CanonicalBatchSide::new(batch.schema(), &[batch])) {
                Ok(output) => drop(output),
                Err(error) => {
                    assert_eq!(error.to_string(), "RESOURCE_LIMIT_EXCEEDED");
                    exhausted = true;
                    break;
                }
            }
        }
        assert!(exhausted);
        cancelled.store(true, std::sync::atomic::Ordering::Relaxed);
        let batch = batch(&[1], &["same"])?;
        assert!(
            scanner
                .scan(CanonicalBatchSide::new(batch.schema(), &[batch]))
                .err()
                .is_some_and(|e| e.to_string() == "COMPARISON_CANCELLED")
        );
        drop(scanner);
        assert_eq!(context.remaining_bytes(), 32 * 1024);
        Ok(())
    }

    #[test]
    fn keyed_compares_shared_columns_across_batch_boundaries()
    -> Result<(), Box<dyn std::error::Error>> {
        let before = batch(&[1, 2], &["old", "same"])?;
        let current_a = batch(&[2], &["same"])?;
        let current_b = batch(&[1, 3], &["new", "third"])?;
        let context = context();
        let full = compare(
            std::slice::from_ref(&before),
            &[current_a.clone(), current_b.clone()],
            &options(StandardMode::Keyed),
            &context,
        )?;
        assert_eq!(
            (
                full.row_added_count,
                full.row_deleted_count,
                full.row_modified_count
            ),
            (1, 0, 1)
        );
        assert_eq!(
            full.facts_order
                .iter()
                .map(|&index| full.records[index].kind.contract_name())
                .collect::<Vec<_>>(),
            vec!["ROW_ADDED", "ROW_MODIFIED"]
        );
        let modified = full
            .records
            .iter()
            .find(|record| record.kind == StandardKind::RowModified)
            .ok_or("missing modified record")?;
        assert_eq!(modified.changed_columns, ["name"]);
        assert_eq!(modified.before, Some(RowLocation { batch: 0, row: 0 }));
        assert_eq!(modified.current, Some(RowLocation { batch: 1, row: 0 }));
        assert_eq!(full.facts_order, full.artifact_order);
        drop(full);
        assert_eq!(context.remaining_bytes(), 16 * 1024 * 1024);
        Ok(())
    }

    #[test]
    fn keyless_multiset_keeps_third_occurrence_and_reverse_delete()
    -> Result<(), Box<dyn std::error::Error>> {
        assert_eq!(
            occurrence_digest(
                "sha256:401578531a0add4dd48daa932190b0f1fff21f90cd2378a112c32199b1a80f39",
                2
            )?,
            "sha256:a30dfdfae0f29e7d4a7da411578d351fac59a100052dc8fd2135f6940f4ba2bb"
        );
        let two = batch(&[1, 1], &["a", "a"])?;
        let three_a = batch(&[1], &["a"])?;
        let three_b = batch(&[1, 1], &["a", "a"])?;
        let context = context();
        let added = compare(
            std::slice::from_ref(&two),
            &[three_a.clone(), three_b.clone()],
            &options(StandardMode::Keyless),
            &context,
        )?;
        assert_eq!(
            (
                added.row_added_count,
                added.row_deleted_count,
                added.row_modified_count
            ),
            (1, 0, 0)
        );
        assert_eq!(added.records[0].kind, StandardKind::RowAdded);
        let deleted = compare(
            &[three_a, three_b],
            &[two],
            &options(StandardMode::Keyless),
            &context,
        )?;
        assert_eq!(
            (
                deleted.row_added_count,
                deleted.row_deleted_count,
                deleted.row_modified_count
            ),
            (0, 1, 0)
        );
        assert_eq!(deleted.records[0].kind, StandardKind::RowDeleted);
        assert_eq!(
            added.records[0].row_identity,
            deleted.records[0].row_identity
        );
        Ok(())
    }

    #[test]
    fn excluded_shared_value_does_not_modify_keyed_row() -> Result<(), Box<dyn std::error::Error>> {
        let before = batch(&[1], &["old"])?;
        let current = batch(&[1], &["new"])?;
        let mut policy = options(StandardMode::Keyed);
        policy.compare_excluded_columns = vec!["name".to_string()];
        let result = compare(&[before], &[current], &policy, &context())?;
        assert_eq!(result.row_modified_count, 0);
        assert!(result.records.is_empty());
        Ok(())
    }

    #[test]
    fn columns_added_does_not_treat_nonshared_exclusion_as_hidden_content()
    -> Result<(), Box<dyn std::error::Error>> {
        let before = batch(&[1], &["old"])?;
        let current = batch(&[1], &["new"])?;
        let mut policy = options(StandardMode::Keyed);
        policy.columns_added = true;
        policy.compare_excluded_columns = vec!["future_only".to_string()];
        let result = compare(&[before], &[current], &policy, &context())?;
        assert_eq!(result.row_modified_count, 1);
        assert!(!result.ignored_shared_content_changed);
        Ok(())
    }

    #[test]
    fn present_zero_batch_table_is_distinct_from_missing_side()
    -> Result<(), Box<dyn std::error::Error>> {
        let current = batch(&[7], &["new"])?;
        let result = compare(&[], &[current], &options(StandardMode::Keyed), &context())?;
        assert_eq!((result.row_added_count, result.row_deleted_count), (1, 0));
        assert_eq!(result.records.len(), 1);
        assert_eq!(result.records[0].kind, StandardKind::RowAdded);
        let empty = compare(&[], &[], &options(StandardMode::Keyed), &context())?;
        assert_eq!((empty.row_added_count, empty.row_deleted_count), (0, 0));
        assert!(empty.records.is_empty());
        Ok(())
    }

    #[test]
    fn canonical_set_uses_frozen_sequence_frame_and_rejects_bad_order()
    -> Result<(), Box<dyn std::error::Error>> {
        let set_field = field("flags", "SET('a','b')", "set", None, DataType::Utf8);
        let values = StringArray::from(vec![Some("a,b"), Some(""), Some("b,a")]);
        let first = encode_cell(&values, 0, &set_field)?;
        // repository/sql-enum-set/v1/values.jsonl: declaration-order-members.
        assert_eq!(first.frame, vec![2, 3, 32, 1, b'a', 3, 32, 1, b'b']);
        assert_eq!(encode_cell(&values, 1, &set_field)?.frame, vec![0]);
        assert_eq!(
            encode_cell(&values, 2, &set_field)
                .err()
                .map(|error| error.code()),
            Some("SET_VALUE_INVALID")
        );
        Ok(())
    }

    #[test]
    fn canonical_metadata_and_resource_control_fail_before_rows()
    -> Result<(), Box<dyn std::error::Error>> {
        let valid = batch(&[1], &["a"])?;
        let wrong = RecordBatch::try_new(
            Arc::new(Schema::new(
                valid
                    .schema()
                    .fields()
                    .iter()
                    .map(|field| field.as_ref().clone())
                    .collect::<Vec<_>>(),
            )),
            valid.columns().to_vec(),
        )?;
        let policy = options(StandardMode::Keyed);
        assert_eq!(
            compare(&[wrong], std::slice::from_ref(&valid), &policy, &context())
                .err()
                .map(|error| error.code()),
            Some("CANONICAL_SCHEMA_REQUIRED")
        );
        let tiny = Arc::new(KernelContext::new(
            0,
            Arc::new(AtomicBool::new(false)),
            None,
        ));
        assert_eq!(
            compare(
                std::slice::from_ref(&valid),
                std::slice::from_ref(&valid),
                &policy,
                &tiny,
            )
            .err()
            .map(|error| error.code()),
            Some("RESOURCE_LIMIT_EXCEEDED")
        );
        let cancelled = Arc::new(AtomicBool::new(true));
        let stopped = Arc::new(KernelContext::new(1024 * 1024, cancelled, None));
        assert_eq!(
            compare(
                std::slice::from_ref(&valid),
                std::slice::from_ref(&valid),
                &policy,
                &stopped,
            )
            .err()
            .map(|error| error.code()),
            Some("COMPARISON_CANCELLED")
        );
        let expired = Arc::new(KernelContext::new(
            1024 * 1024,
            Arc::new(AtomicBool::new(false)),
            Some(std::time::Instant::now()),
        ));
        let no_rows = batch(&[], &[])?;
        assert_eq!(
            compare(
                std::slice::from_ref(&no_rows),
                std::slice::from_ref(&no_rows),
                &policy,
                &expired,
            )
            .err()
            .map(|error| error.code()),
            Some("COMPARISON_DEADLINE_EXCEEDED")
        );
        Ok(())
    }

    #[test]
    fn unchanged_ordered_reads_current_side_only() -> Result<(), Box<dyn std::error::Error>> {
        let schema = Schema::new(vec![
            field(
                "gid",
                "BIGINT",
                "standard",
                Some("signed-integer"),
                DataType::Int64,
            ),
            field(
                "no",
                "BIGINT",
                "standard",
                Some("signed-integer"),
                DataType::Int64,
            ),
            field(
                "name",
                "VARCHAR(64)",
                "standard",
                Some("string"),
                DataType::Utf8,
            ),
        ])
        .with_metadata(HashMap::from([(
            "gdds.canonical_mapping_version".to_string(),
            "1".to_string(),
        )]));
        let current = RecordBatch::try_new(
            Arc::new(schema),
            vec![
                Arc::new(Int64Array::from(vec![1, 2])) as ArrayRef,
                Arc::new(Int64Array::from(vec![1, 2])) as ArrayRef,
                Arc::new(StringArray::from(vec!["a", "b"])) as ArrayRef,
            ],
        )?;
        let mut policy = OrderedCompareOptions::new("t");
        policy.current_blank_provenance = BlankProvenance::SourceMissingStableKey;
        let summary = summarize_unchanged_ordered_batches(
            CanonicalBatchSide::new(current.schema(), std::slice::from_ref(&current)),
            &policy,
            &context(),
        )?;
        let slices = [current.slice(0, 1), current.slice(1, 1)];
        let split = summarize_unchanged_ordered_batches(
            CanonicalBatchSide::new(current.schema(), &slices),
            &policy,
            &context(),
        )?;
        assert_eq!(summary, split);
        let empty = summarize_unchanged_ordered_batches(
            CanonicalBatchSide::new(current.schema(), &[]),
            &policy,
            &context(),
        )?;
        assert_eq!(empty.row_count, 0);
        assert_eq!(empty.before_ordered_digest, empty.current_ordered_digest);
        assert_eq!(
            empty.before_occupancy_digest,
            empty.current_occupancy_digest
        );
        assert_eq!(
            summary.before_ordered_digest,
            summary.current_ordered_digest
        );
        assert_eq!(
            summary.before_occupancy_digest,
            summary.current_occupancy_digest
        );
        assert_eq!(summary.row_count, 2);
        Ok(())
    }

    #[test]
    fn ordered_locator_path_reuses_earliest_lis_tie() -> Result<(), Box<dyn std::error::Error>> {
        let schema = Arc::new(
            Schema::new(vec![
                field(
                    "gid",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "no",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "name",
                    "VARCHAR(64)",
                    "standard",
                    Some("string"),
                    DataType::Utf8,
                ),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".to_string(),
                "1".to_string(),
            )])),
        );
        let make =
            |gids: Vec<i64>, names: Vec<&str>| -> Result<RecordBatch, arrow_schema::ArrowError> {
                RecordBatch::try_new(
                    Arc::clone(&schema),
                    vec![
                        Arc::new(Int64Array::from(gids)) as ArrayRef,
                        Arc::new(Int64Array::from(vec![1, 2, 3])) as ArrayRef,
                        Arc::new(StringArray::from(names)) as ArrayRef,
                    ],
                )
            };
        let before = make(vec![1, 2, 3], vec!["a", "b", "c"])?;
        let current = make(vec![2, 1, 3], vec!["b", "a", "c"])?;
        let policy = OrderedCompareOptions::new("t");
        let result = compare_ordered_batches(
            OrderedBatchPair {
                before: Some(std::slice::from_ref(&before)),
                current: Some(std::slice::from_ref(&current)),
                before_schema: Some(before.schema()),
                current_schema: Some(current.schema()),
                options: &policy,
            },
            &context(),
        )?;
        assert!(result.facts_metadata.records.is_empty());
        assert!(result.facts_metadata.ordered_extension.records.is_empty());
        assert_eq!(
            result
                .facts_metadata
                .ordered_extension
                .summary
                .row_moved_count,
            1
        );
        let moved = result
            .ordered_records
            .iter()
            .filter(|record| record.kind == "ORDERED_ROW_MOVED")
            .collect::<Vec<_>>();
        assert_eq!(moved.len(), 1);
        assert_eq!(
            (moved[0].before_position, moved[0].current_position),
            (Some(2), Some(1))
        );
        assert_eq!(result.standard_records.len(), 0);
        Ok(())
    }

    #[test]
    fn shared_backing_slices_keep_the_same_budget_admission()
    -> Result<(), Box<dyn std::error::Error>> {
        let names = (0..32).map(|_| "x".repeat(1024)).collect::<Vec<_>>();
        let ids = (0..32).map(i64::from).collect::<Vec<_>>();
        let full = RecordBatch::try_new(
            schema(),
            vec![
                Arc::new(Int64Array::from(ids)) as ArrayRef,
                Arc::new(StringArray::from(names)) as ArrayRef,
            ],
        )?;
        let slices = (0..full.num_rows())
            .map(|row| full.slice(row, 1))
            .collect::<Vec<_>>();
        let budget = 512 * 1024;
        let unsplit = Arc::new(KernelContext::new(
            budget,
            Arc::new(AtomicBool::new(false)),
            None,
        ));
        let split = Arc::new(KernelContext::new(
            budget,
            Arc::new(AtomicBool::new(false)),
            None,
        ));
        let policy = options(StandardMode::Keyed);
        let one = compare(
            std::slice::from_ref(&full),
            std::slice::from_ref(&full),
            &policy,
            &unsplit,
        )?;
        let many = compare(&slices, &slices, &policy, &split)?;
        assert_eq!(one.row_modified_count, many.row_modified_count);
        assert_eq!(one.records.len(), many.records.len());
        drop(one);
        drop(many);
        assert_eq!(unsplit.remaining_bytes(), budget);
        assert_eq!(split.remaining_bytes(), budget);
        Ok(())
    }

    #[test]
    fn canonical_declared_type_must_match_sql_spelling() -> Result<(), Box<dyn std::error::Error>> {
        let bad_schema = Arc::new(
            Schema::new(vec![
                field(
                    "id",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "name",
                    "DECIMAL(10,0)",
                    "standard",
                    Some("string"),
                    DataType::Utf8,
                ),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".to_string(),
                "1".to_string(),
            )])),
        );
        let bad_batch = RecordBatch::try_new(
            bad_schema,
            vec![
                Arc::new(Int64Array::from(vec![1])) as ArrayRef,
                Arc::new(StringArray::from(vec!["1"])) as ArrayRef,
            ],
        )?;
        assert_eq!(
            compare(
                std::slice::from_ref(&bad_batch),
                std::slice::from_ref(&bad_batch),
                &options(StandardMode::Keyed),
                &context()
            )
            .err()
            .map(|error| error.code()),
            Some("CANONICAL_TYPE_INVALID"),
        );
        Ok(())
    }

    #[test]
    fn duplicate_effective_key_is_a_table_error_for_planner_degradation()
    -> Result<(), Box<dyn std::error::Error>> {
        let repeated = batch(&[1, 1], &["a", "b"])?;
        let single = batch(&[1], &["a"])?;
        assert_eq!(
            compare(
                &[repeated],
                &[single],
                &options(StandardMode::Keyed),
                &context(),
            )
            .err()
            .map(|error| error.code()),
            Some("DUPLICATE_EFFECTIVE_KEY"),
        );
        Ok(())
    }

    #[test]
    fn ordered_string_gid_or_no_uses_frozen_integer_diagnostic()
    -> Result<(), Box<dyn std::error::Error>> {
        for text_gid in [true, false] {
            let gid_type = if text_gid {
                DataType::Utf8
            } else {
                DataType::Int64
            };
            let no_type = if text_gid {
                DataType::Int64
            } else {
                DataType::Utf8
            };
            let schema = Arc::new(
                Schema::new(vec![
                    field(
                        "gid",
                        if text_gid { "VARCHAR(8)" } else { "BIGINT" },
                        "standard",
                        Some(if text_gid { "string" } else { "signed-integer" }),
                        gid_type,
                    ),
                    field(
                        "no",
                        if text_gid { "BIGINT" } else { "VARCHAR(8)" },
                        "standard",
                        Some(if text_gid { "signed-integer" } else { "string" }),
                        no_type,
                    ),
                ])
                .with_metadata(HashMap::from([(
                    "gdds.canonical_mapping_version".to_string(),
                    "1".to_string(),
                )])),
            );
            let gid: ArrayRef = if text_gid {
                Arc::new(StringArray::from(vec!["1"]))
            } else {
                Arc::new(Int64Array::from(vec![1]))
            };
            let no: ArrayRef = if text_gid {
                Arc::new(Int64Array::from(vec![1]))
            } else {
                Arc::new(StringArray::from(vec!["1"]))
            };
            let batch = RecordBatch::try_new(schema, vec![gid, no])?;
            let policy = OrderedCompareOptions::new("t");
            let result = compare_ordered_batches(
                OrderedBatchPair {
                    before: Some(std::slice::from_ref(&batch)),
                    current: Some(std::slice::from_ref(&batch)),
                    before_schema: Some(batch.schema()),
                    current_schema: Some(batch.schema()),
                    options: &policy,
                },
                &context(),
            )?;
            assert_eq!(result.facts_metadata.status, "DEGRADED");
            assert_eq!(
                result.facts_metadata.diagnostics,
                ["ORDERED_INTEGER_INVALID"]
            );
            assert_eq!(result.standard_records.len(), 1);
            assert_eq!(result.standard_records[0].kind, StandardKind::TableDegraded);
        }
        Ok(())
    }

    #[test]
    fn ordered_streaming_jcs_rejects_unsafe_absolute_position()
    -> Result<(), Box<dyn std::error::Error>> {
        let ordered_schema = Arc::new(
            Schema::new(vec![
                field(
                    "gid",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "no",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "name",
                    "VARCHAR(64)",
                    "standard",
                    Some("string"),
                    DataType::Utf8,
                ),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".to_string(),
                "1".to_string(),
            )])),
        );
        let make = |position| {
            RecordBatch::try_new(
                Arc::clone(&ordered_schema),
                vec![
                    Arc::new(Int64Array::from(vec![1])) as ArrayRef,
                    Arc::new(Int64Array::from(vec![position])) as ArrayRef,
                    Arc::new(StringArray::from(vec!["a"])) as ArrayRef,
                ],
            )
        };
        let safe = make((1_i64 << 53) - 1)?;
        let unsafe_position = make(1_i64 << 53)?;
        let policy = OrderedCompareOptions::new("t");
        let allowed = compare_ordered_batches(
            OrderedBatchPair {
                before: Some(std::slice::from_ref(&safe)),
                current: Some(std::slice::from_ref(&safe)),
                before_schema: Some(safe.schema()),
                current_schema: Some(safe.schema()),
                options: &policy,
            },
            &context(),
        )?;
        assert_eq!(allowed.facts_metadata.status, "UNCHANGED");
        assert_eq!(
            compare_ordered_batches(
                OrderedBatchPair {
                    before: Some(std::slice::from_ref(&safe)),
                    current: Some(std::slice::from_ref(&unsafe_position)),
                    before_schema: Some(safe.schema()),
                    current_schema: Some(unsafe_position.schema()),
                    options: &policy,
                },
                &context()
            )
            .err()
            .map(|error| error.code()),
            Some("CANONICAL_ENCODING_FAILED"),
        );
        Ok(())
    }

    #[test]
    fn ordered_zero_batch_wide_metadata_is_reserved_before_result()
    -> Result<(), Box<dyn std::error::Error>> {
        let ordered_schema = Arc::new(
            Schema::new(vec![
                field(
                    "gid",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "no",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".to_string(),
                "1".to_string(),
            )])),
        );
        let mut policy = OrderedCompareOptions::new("t");
        policy.schema_changes.before_only_columns = vec!["x".repeat(64 * 1024)];
        let small = Arc::new(KernelContext::new(
            32 * 1024,
            Arc::new(AtomicBool::new(false)),
            None,
        ));
        let pair = OrderedBatchPair {
            before: Some(&[]),
            current: Some(&[]),
            before_schema: Some(Arc::clone(&ordered_schema)),
            current_schema: Some(Arc::clone(&ordered_schema)),
            options: &policy,
        };
        assert_eq!(
            compare_ordered_batches(pair.clone(), &small)
                .err()
                .map(|error| error.code()),
            Some("RESOURCE_LIMIT_EXCEEDED"),
        );
        assert_eq!(small.remaining_bytes(), 32 * 1024);
        let large = Arc::new(KernelContext::new(
            2 * 1024 * 1024,
            Arc::new(AtomicBool::new(false)),
            None,
        ));
        let result = compare_ordered_batches(pair, &large)?;
        assert_eq!(result.facts_metadata.row_count_current, Some(0));
        drop(result);
        assert_eq!(large.remaining_bytes(), 2 * 1024 * 1024);
        Ok(())
    }

    #[test]
    fn ordered_batch_partitions_and_caller_pool_width_keep_semantic_result()
    -> Result<(), Box<dyn std::error::Error>> {
        let ordered_schema = Arc::new(
            Schema::new(vec![
                field(
                    "gid",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "no",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "name",
                    "VARCHAR(64)",
                    "standard",
                    Some("string"),
                    DataType::Utf8,
                ),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".to_string(),
                "1".to_string(),
            )])),
        );
        let make = |gids: Vec<i64>, names: Vec<&str>| {
            RecordBatch::try_new(
                Arc::clone(&ordered_schema),
                vec![
                    Arc::new(Int64Array::from(gids)) as ArrayRef,
                    Arc::new(Int64Array::from(vec![1, 2, 3, 4, 5])) as ArrayRef,
                    Arc::new(StringArray::from(names)) as ArrayRef,
                ],
            )
        };
        let before = make(vec![1, 2, 3, 4, 5], vec!["a", "b", "c", "d", "e"])?;
        let current = make(vec![2, 1, 3, 5, 4], vec!["b", "a", "c", "e", "d"])?;
        let policy = OrderedCompareOptions::new("t");
        let full = compare_ordered_batches(
            OrderedBatchPair {
                before: Some(std::slice::from_ref(&before)),
                current: Some(std::slice::from_ref(&current)),
                before_schema: Some(before.schema()),
                current_schema: Some(current.schema()),
                options: &policy,
            },
            &context(),
        )?;
        let expected = (
            full.facts_metadata.status.clone(),
            full.facts_metadata
                .ordered_extension
                .summary
                .row_moved_count,
            full.facts_metadata
                .ordered_extension
                .before_ordered_digest
                .clone(),
            full.facts_metadata
                .ordered_extension
                .current_ordered_digest
                .clone(),
            full.ordered_records
                .iter()
                .map(|item| {
                    (
                        item.kind,
                        item.row_identity.clone(),
                        item.before_position,
                        item.current_position,
                    )
                })
                .collect::<Vec<_>>(),
        );
        for width in [1, 4] {
            let pool = rayon::ThreadPoolBuilder::new().num_threads(width).build()?;
            for seed in 0usize..32 {
                let split = |batch: &RecordBatch, mut state: usize| {
                    let mut start = 0;
                    let mut output = Vec::new();
                    while start < batch.num_rows() {
                        state = state.wrapping_mul(1_103_515_245).wrapping_add(12_345);
                        let count = (1 + state % 3).min(batch.num_rows() - start);
                        output.push(batch.slice(start, count));
                        start += count;
                    }
                    output
                };
                let before_parts = split(&before, seed);
                let current_parts = split(&current, seed ^ 0x5a5a);
                let run_context = context();
                let result = pool.install(|| {
                    compare_ordered_batches(
                        OrderedBatchPair {
                            before: Some(&before_parts),
                            current: Some(&current_parts),
                            before_schema: Some(before.schema()),
                            current_schema: Some(current.schema()),
                            options: &policy,
                        },
                        &run_context,
                    )
                })?;
                let actual = (
                    result.facts_metadata.status.clone(),
                    result
                        .facts_metadata
                        .ordered_extension
                        .summary
                        .row_moved_count,
                    result
                        .facts_metadata
                        .ordered_extension
                        .before_ordered_digest
                        .clone(),
                    result
                        .facts_metadata
                        .ordered_extension
                        .current_ordered_digest
                        .clone(),
                    result
                        .ordered_records
                        .iter()
                        .map(|item| {
                            (
                                item.kind,
                                item.row_identity.clone(),
                                item.before_position,
                                item.current_position,
                            )
                        })
                        .collect::<Vec<_>>(),
                );
                assert_eq!(actual, expected);
            }
        }
        Ok(())
    }

    #[test]
    fn shared_context_parallel_table_tasks_match_one_worker()
    -> Result<(), Box<dyn std::error::Error>> {
        let keyed_before = batch(&[1, 2], &["old", "same"])?;
        let keyed_current = batch(&[2, 3], &["same", "new"])?;
        let keyless_before = batch(&[1, 1, 2], &["a", "a", "b"])?;
        let keyless_current = batch(&[1, 2, 2], &["a", "b", "b"])?;
        let ordered_schema = Arc::new(
            Schema::new(vec![
                field(
                    "gid",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "no",
                    "BIGINT",
                    "standard",
                    Some("signed-integer"),
                    DataType::Int64,
                ),
                field(
                    "name",
                    "VARCHAR(64)",
                    "standard",
                    Some("string"),
                    DataType::Utf8,
                ),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".to_string(),
                "1".to_string(),
            )])),
        );
        let ordered_batch = |gids: Vec<i64>, names: Vec<&str>| {
            RecordBatch::try_new(
                Arc::clone(&ordered_schema),
                vec![
                    Arc::new(Int64Array::from(gids)) as ArrayRef,
                    Arc::new(Int64Array::from(vec![1, 2, 3, 4])) as ArrayRef,
                    Arc::new(StringArray::from(names)) as ArrayRef,
                ],
            )
        };
        let ordered_before = ordered_batch(vec![1, 2, 3, 4], vec!["a", "b", "c", "d"])?;
        let ordered_current = ordered_batch(vec![4, 3, 2, 1], vec!["d", "c", "b", "a"])?;
        let mut ordered_options = OrderedCompareOptions::new("t");
        ordered_options.value_columns = vec!["name".to_string()];
        ordered_options.digest_value_columns = ordered_options.value_columns.clone();
        let jobs = (0..12usize).collect::<Vec<_>>();
        let run = |threads| -> Result<Vec<String>, Box<dyn std::error::Error>> {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()?;
            let shared = context();
            let signatures = pool.install(|| {
                jobs.par_iter()
                    .map(|job| -> Result<String, OrderedCompareError> {
                        if *job % 3 == 2 {
                            let result = compare_ordered_batches(
                                OrderedBatchPair {
                                    before: Some(std::slice::from_ref(&ordered_before)),
                                    current: Some(std::slice::from_ref(&ordered_current)),
                                    before_schema: Some(ordered_before.schema()),
                                    current_schema: Some(ordered_current.schema()),
                                    options: &ordered_options,
                                },
                                &shared,
                            )?;
                            Ok(format!(
                                "{:?}",
                                (
                                    &result.facts_metadata.status,
                                    &result.facts_metadata.ordered_extension.summary,
                                    &result.facts_metadata.blank_extension.summary,
                                    &result
                                        .facts_metadata
                                        .ordered_extension
                                        .before_ordered_digest,
                                    &result
                                        .facts_metadata
                                        .ordered_extension
                                        .current_ordered_digest,
                                    &result.ordered_records,
                                    &result.blank_records,
                                )
                            ))
                        } else {
                            let (before, current, mode) = if *job % 3 == 0 {
                                (&keyed_before, &keyed_current, StandardMode::Keyed)
                            } else {
                                (&keyless_before, &keyless_current, StandardMode::Keyless)
                            };
                            let result = compare(
                                std::slice::from_ref(before),
                                std::slice::from_ref(current),
                                &options(mode),
                                &shared,
                            )?;
                            Ok(format!(
                                "{:?}",
                                (
                                    result.row_added_count,
                                    result.row_deleted_count,
                                    result.row_modified_count,
                                    &result.records,
                                    &result.facts_order,
                                    &result.artifact_order,
                                )
                            ))
                        }
                    })
                    .collect::<Result<Vec<_>, _>>()
            })?;
            assert_eq!(shared.remaining_bytes(), 16 * 1024 * 1024);
            Ok(signatures)
        };
        assert_eq!(run(1)?, run(4)?);
        Ok(())
    }
}
