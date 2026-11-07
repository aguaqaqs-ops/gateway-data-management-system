//! Standard and keyless row comparison over canonical Arrow batches.
//!
//! The result owns cheap `RecordBatch` clones (Arc-backed Arrow buffers) and
//! row locators. C can build Arrow records directly from those locators. No
//! Python row objects or whole-table JSON representation crosses this boundary.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::panic::AssertUnwindSafe;
use std::sync::Arc;

use arrow_array::RecordBatch;
use gateway_shared_kernel::{DigestKind, canonicalize_identifier, encode_uleb128, semantic_digest};

use super::kernel::{KernelContext, KernelLease, validate_canonical_batches};
use super::ordered::{OrderedCompareError, encode_cell};

const MAX_COLUMNS: usize = 512;

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

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum StandardKind {
    RowAdded,
    RowDeleted,
    RowModified,
}

impl StandardKind {
    pub fn contract_name(self) -> &'static str {
        match self {
            Self::RowAdded => "ROW_ADDED",
            Self::RowDeleted => "ROW_DELETED",
            Self::RowModified => "ROW_MODIFIED",
        }
    }
}

#[derive(Debug, Clone)]
pub struct StandardRecordRef {
    pub kind: StandardKind,
    pub row_identity: String,
    pub before: Option<RowLocation>,
    pub current: Option<RowLocation>,
    /// FULL facts payload uses these columns and the referenced Arrow cells.
    pub value_columns: Vec<String>,
    pub changed_columns: Vec<String>,
}

pub struct StandardComputation {
    /// These clones keep the Arrow backing valid after the caller's reader
    /// closes. The caller's unique input-owner charge remains pinned while a
    /// result exists; `_lease` charges only local frames/indexes/output refs.
    pub before_batches: Vec<RecordBatch>,
    pub current_batches: Vec<RecordBatch>,
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
    before: &[RecordBatch],
    current: &[RecordBatch],
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
    before: &[RecordBatch],
    current: &[RecordBatch],
    options: &StandardOptions,
    context: &Arc<KernelContext>,
) -> Result<StandardComputation, OrderedCompareError> {
    context.check()?;
    validate_canonical_batches(before)?;
    validate_canonical_batches(current)?;
    let columns = canonical_columns(&options.selected_columns)?;
    let excluded = canonical_columns(&options.compare_excluded_columns)?;
    let incompatible = canonical_columns(&options.incompatible_columns)?;
    let before_key = canonical_columns(&options.effective_key_before)?;
    let current_key = canonical_columns(&options.effective_key_current)?;
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
            total.checked_add(array.get_buffer_memory_size())
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let row_overhead = columns
        .len()
        .checked_mul(80)
        .and_then(|bytes| bytes.checked_add(256))
        .and_then(|bytes| bytes.checked_mul(row_count))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let scratch = input_bytes
        .checked_mul(2)
        .and_then(|bytes| bytes.checked_add(row_overhead))
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
    let ignored_shared_content_changed = if options.columns_added && !excluded.is_empty() {
        row_counts(&before_rows, &columns, &columns, context)?
            != row_counts(&current_rows, &columns, &columns, context)?
    } else {
        false
    };
    let mut facts_order: Vec<usize> = (0..records.len()).collect();
    facts_order
        .sort_by(|left, right| record_key(&records[*left]).cmp(&record_key(&records[*right])));
    let artifact_order = facts_order.clone();
    Ok(StandardComputation {
        before_batches: before.to_vec(),
        current_batches: current.to_vec(),
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
            for index in &indices {
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

fn push_record(
    records: &mut Vec<StandardRecordRef>,
    lease: &mut KernelLease,
    record: StandardRecordRef,
) -> Result<(), OrderedCompareError> {
    let extra = 256usize
        .checked_add(record.row_identity.len())
        .and_then(|size| {
            size.checked_add(record.value_columns.iter().map(String::len).sum::<usize>())
        })
        .and_then(|size| {
            size.checked_add(
                record
                    .changed_columns
                    .iter()
                    .map(String::len)
                    .sum::<usize>(),
            )
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    lease.grow(extra)?;
    records.push(record);
    Ok(())
}

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
                push_record(
                    records,
                    lease,
                    StandardRecordRef {
                        kind: StandardKind::RowAdded,
                        row_identity: row_digest(frame)?,
                        before: None,
                        current: Some(current_row.location),
                        value_columns: selected.to_vec(),
                        changed_columns: Vec::new(),
                    },
                )?;
            }
            continue;
        };
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
        if !changed.is_empty() {
            modified += 1;
            push_record(
                records,
                lease,
                StandardRecordRef {
                    kind: StandardKind::RowModified,
                    row_identity: row_digest(frame)?,
                    before: Some(before_row.location),
                    current: Some(current_row.location),
                    value_columns: changed.clone(),
                    changed_columns: changed,
                },
            )?;
        }
    }
    for (frame, before_row) in &before_index {
        context.check()?;
        if !current_index.contains_key(frame) {
            deleted += 1;
            if emit_add_delete {
                push_record(
                    records,
                    lease,
                    StandardRecordRef {
                        kind: StandardKind::RowDeleted,
                        row_identity: row_digest(frame)?,
                        before: Some(before_row.location),
                        current: None,
                        value_columns: selected.to_vec(),
                        changed_columns: Vec::new(),
                    },
                )?;
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
    let columns = if columns_added {
        selected
            .iter()
            .filter(|name| !excluded.contains(*name))
            .cloned()
            .collect::<Vec<_>>()
    } else {
        selected.to_vec()
    };
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
                push_record(
                    records,
                    lease,
                    StandardRecordRef {
                        kind: StandardKind::RowAdded,
                        row_identity: occurrence_digest(identity, occurrence)?,
                        before: None,
                        current: None,
                        value_columns: Vec::new(),
                        changed_columns: Vec::new(),
                    },
                )?;
            }
        }
    }
    for (identity, before_count) in &before_counts {
        let current_count = current_counts.get(identity).copied().unwrap_or_default();
        for occurrence in current_count..*before_count {
            context.check()?;
            deleted += 1;
            if emit_add_delete {
                push_record(
                    records,
                    lease,
                    StandardRecordRef {
                        kind: StandardKind::RowDeleted,
                        row_identity: occurrence_digest(identity, occurrence)?,
                        before: None,
                        current: None,
                        value_columns: Vec::new(),
                        changed_columns: Vec::new(),
                    },
                )?;
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

fn record_key(record: &StandardRecordRef) -> (&'static str, &str, &[String]) {
    (
        record.kind.contract_name(),
        &record.row_identity,
        &record.changed_columns,
    )
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::sync::atomic::AtomicBool;

    use arrow_array::{ArrayRef, Int64Array, RecordBatch, StringArray};
    use arrow_schema::{DataType, Field, Schema};

    use super::*;
    use crate::comparison::ordered::{
        BlankProvenance, OrderedCompareOptions, summarize_unchanged_ordered_side,
    };

    fn field(
        name: &str,
        sql: &str,
        logical: &str,
        kind: Option<&str>,
        data_type: DataType,
    ) -> Field {
        let declared = kind.map_or(serde_json::Value::Null, |kind| {
            serde_json::json!({
                "kind":kind,"bits":null,"precision":null,"scale":null,"bit_width":null
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

    fn batch(ids: &[i64], names: &[&str]) -> Result<RecordBatch, arrow_schema::ArrowError> {
        let schema = Schema::new(vec![
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
        )]));
        RecordBatch::try_new(
            Arc::new(schema),
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

    #[test]
    fn keyed_compares_shared_columns_across_batch_boundaries()
    -> Result<(), Box<dyn std::error::Error>> {
        let before = batch(&[1, 2], &["old", "same"])?;
        let current_a = batch(&[2], &["same"])?;
        let current_b = batch(&[1, 3], &["new", "third"])?;
        let context = context();
        let full = compare_standard_table(
            &[before.clone()],
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
            full.records
                .iter()
                .map(|record| record.kind.contract_name())
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
        let added = compare_standard_table(
            &[two.clone()],
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
        let deleted = compare_standard_table(
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
        let result = compare_standard_table(&[before], &[current], &policy, &context())?;
        assert_eq!(result.row_modified_count, 0);
        assert!(result.records.is_empty());
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
            compare_standard_table(&[wrong], &[valid.clone()], &policy, &context())
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
            compare_standard_table(&[valid.clone()], &[valid.clone()], &policy, &tiny)
                .err()
                .map(|error| error.code()),
            Some("RESOURCE_LIMIT_EXCEEDED")
        );
        let cancelled = Arc::new(AtomicBool::new(true));
        let stopped = Arc::new(KernelContext::new(1024 * 1024, cancelled, None));
        assert_eq!(
            compare_standard_table(&[valid.clone()], &[valid], &policy, &stopped)
                .err()
                .map(|error| error.code()),
            Some("COMPARISON_CANCELLED")
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
        let summary = summarize_unchanged_ordered_side(&current, &policy, &context())?;
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
}
