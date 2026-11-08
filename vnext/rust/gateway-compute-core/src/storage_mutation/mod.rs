//! One table's persisted Arrow view and bounded storage diff.
//!
//! The caller owns input backing. This module retains Arrow batch references,
//! JCS ordering keys, row locators and at most 1000 patch locators.

use std::sync::Arc;

use arrow_array::{
    Array, BinaryArray, LargeBinaryArray, LargeStringArray, RecordBatch, StringArray,
};
use arrow_schema::{DataType, SchemaRef};
use gateway_shared_kernel::{
    DeclaredType, NullScalar, RowField, TypedScalar, canonicalize_jcs, encode_row,
};
use serde_json::{Value, json};

use crate::comparison::kernel::{
    CanonicalBatchSide, KernelContext, KernelLease, sort_indices_checked,
    validate_canonical_batches,
};
use crate::comparison::ordered::{declared_type, encode_cell, scalar_type, typed_value};

const MAX_PATCH_LOCATORS: usize = 1000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StorageError(pub String);

impl std::fmt::Display for StorageError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for StorageError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RowLocation {
    pub batch: usize,
    pub row: usize,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct NetCounts {
    pub inserted: usize,
    pub updated: usize,
    pub deleted: usize,
}

impl NetCounts {
    pub fn changed(self) -> usize {
        self.inserted + self.updated + self.deleted
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PatchAction {
    Delete(RowLocation),
    Update(RowLocation, RowLocation),
    Insert(RowLocation),
}

pub struct StorageSide {
    pub schema: SchemaRef,
    pub batches: Vec<RecordBatch>,
    pub expected_rows: usize,
    pub retained_columns: Vec<String>,
}

struct IndexedRow {
    key: Vec<u8>,
    location: RowLocation,
    row_hash: Option<String>,
}

pub struct StorageTable {
    pub before: Option<StorageSide>,
    pub after: Option<StorageSide>,
    pub before_rows: usize,
    pub after_rows: usize,
    pub before_validated: bool,
    pub after_validated: bool,
    pub net_counts: Option<NetCounts>,
    pub patch_actions: Vec<PatchAction>,
    pub after_order: Vec<RowLocation>,
    _lease: KernelLease,
}

impl StorageTable {
    /// A rebuild or NOOP no longer needs the old Arrow owner or patch locators.
    pub fn discard_before(&mut self) -> Result<(), StorageError> {
        self.before = None;
        self.patch_actions = Vec::new();
        let retained = self
            .after_order
            .capacity()
            .checked_mul(std::mem::size_of::<RowLocation>())
            .and_then(|size| {
                size.checked_add(self.after.as_ref().map_or(Some(0), |side| {
                    side.batches
                        .capacity()
                        .checked_mul(std::mem::size_of::<RecordBatch>())
                })?)
            })
            .and_then(|size| size.checked_add(4096))
            .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
        self._lease.shrink_to(retained).map_err(mapped)
    }
}

fn invalid(message: &str) -> StorageError {
    StorageError(message.to_owned())
}
fn mapped(error: impl std::fmt::Display) -> StorageError {
    StorageError(error.to_string())
}

fn checked_rows(side: &StorageSide) -> Result<usize, StorageError> {
    validate_canonical_batches(&CanonicalBatchSide::new(
        Arc::clone(&side.schema),
        &side.batches,
    ))
    .map_err(mapped)?;
    let names: Vec<&str> = side
        .schema
        .fields()
        .iter()
        .map(|field| field.name().as_str())
        .collect();
    if names
        != side
            .retained_columns
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>()
    {
        return Err(invalid("STORAGE_COLUMN_BINDING_INVALID"));
    }
    if side
        .batches
        .iter()
        .any(|batch| batch.schema() != side.schema)
    {
        return Err(invalid("STORAGE_SCHEMA_MISMATCH"));
    }
    let count = side
        .batches
        .iter()
        .try_fold(0usize, |sum, batch| sum.checked_add(batch.num_rows()))
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    if count != side.expected_rows {
        return Err(invalid("STORAGE_ROW_COUNT_MISMATCH"));
    }
    Ok(count)
}

fn max_field_metadata_bytes(side: &StorageSide) -> Result<usize, StorageError> {
    side.schema.fields().iter().try_fold(0usize, |largest, field| {
        let bytes = field.metadata().iter().try_fold(0usize, |sum, (key, value)| {
            sum.checked_add(key.len())?.checked_add(value.len())
        }).ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
        Ok(largest.max(bytes))
    })
}

fn schema_parse_scratch_upper(side: &StorageSide) -> Result<usize, StorageError> {
    let names = side.schema.fields().iter().try_fold(0usize, |sum, field| {
        sum.checked_add(field.name().len())
    }).ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    max_field_metadata_bytes(side)?.checked_mul(64)
        .and_then(|size| size.checked_add(names.checked_mul(16)?))
        .and_then(|size| size.checked_add(side.schema.fields().len().checked_mul(4096)?))
        .and_then(|size| size.checked_add(4096))
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))
}

fn raw_value_bytes(
    array: &dyn Array,
    data_type: &DataType,
    row: usize,
) -> Result<usize, StorageError> {
    if array.is_null(row) {
        return Ok(0);
    }
    match data_type {
        DataType::Utf8 => Ok(array
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| invalid("STORAGE_CELL_UNSUPPORTED"))?
            .value(row)
            .len()),
        DataType::LargeUtf8 => Ok(array
            .as_any()
            .downcast_ref::<LargeStringArray>()
            .ok_or_else(|| invalid("STORAGE_CELL_UNSUPPORTED"))?
            .value(row)
            .len()),
        DataType::Binary => Ok(array
            .as_any()
            .downcast_ref::<BinaryArray>()
            .ok_or_else(|| invalid("STORAGE_CELL_UNSUPPORTED"))?
            .value(row)
            .len()),
        DataType::LargeBinary => Ok(array
            .as_any()
            .downcast_ref::<LargeBinaryArray>()
            .ok_or_else(|| invalid("STORAGE_CELL_UNSUPPORTED"))?
            .value(row)
            .len()),
        DataType::FixedSizeBinary(width) => {
            usize::try_from(*width).map_err(|_| invalid("RESOURCE_LIMIT_EXCEEDED"))
        }
        _ => Ok(128),
    }
}

fn row_scratch(
    side: &StorageSide,
    batch: &RecordBatch,
    row: usize,
    context: &Arc<KernelContext>,
) -> Result<KernelLease, StorageError> {
    let mut raw = 0usize;
    let mut names = 0usize;
    for (column, field) in side.schema.fields().iter().enumerate() {
        names = names
            .checked_add(field.name().len())
            .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
        raw = raw
            .checked_add(raw_value_bytes(
                batch.column(column).as_ref(),
                field.data_type(),
                row,
            )?)
            .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    }
    // Per row: typed scalar and Value copies (<=4x raw), escaped JSON/JCS
    // streams (each <=6x raw, with allocator spare capacity), parsed JCS
    // graph and output. 64x covers all simultaneously live intermediates.
    let metadata = max_field_metadata_bytes(side)?;
    let upper = raw
        .checked_mul(64)
        // SET and declared-type validation parse one field declaration at a
        // time. A dense labels array can use far more than its JSON byte len.
        .and_then(|size| size.checked_add(metadata.checked_mul(64)?))
        .and_then(|size| size.checked_add(names.checked_mul(16)?))
        .and_then(|size| size.checked_add(side.schema.fields().len().checked_mul(4096)?))
        .and_then(|size| size.checked_add(4096))
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    context.reserve(upper).map_err(mapped)
}

fn key_payload_bytes(
    side: &StorageSide,
    key_columns: &[String],
    context: &Arc<KernelContext>,
) -> Result<usize, StorageError> {
    let mut total = 0usize;
    for name in key_columns {
        let column = side.schema.index_of(name).map_err(mapped)?;
        let field = side.schema.field(column);
        for batch in &side.batches {
            let array = batch.column(column);
            for row in 0..batch.num_rows() {
                if row % 1024 == 0 {
                    context.check().map_err(mapped)?;
                }
                total = total
                    .checked_add(raw_value_bytes(array.as_ref(), field.data_type(), row)?)
                    .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
            }
        }
    }
    Ok(total)
}

fn validate_cells(side: &StorageSide, context: &Arc<KernelContext>) -> Result<(), StorageError> {
    for batch in &side.batches {
        for row in 0..batch.num_rows() {
            if row % 1024 == 0 {
                context.check().map_err(mapped)?;
            }
            let _scratch = row_scratch(side, batch, row, context)?;
            for column in 0..batch.num_columns() {
                if column % 32 == 0 {
                    context.check().map_err(mapped)?;
                }
                let field = side.schema.field(column);
                // Decode every persisted cell, including those outside a key
                // and every unchanged/rebuild row. SET membership and finite
                // float rules live in the shared canonical encoder.
                let _cell =
                    encode_cell(batch.column(column).as_ref(), row, field).map_err(mapped)?;
            }
        }
    }
    Ok(())
}

fn base64url(raw: &[u8]) -> String {
    const DIGITS: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut text = String::with_capacity(raw.len().div_ceil(3) * 4);
    for chunk in raw.chunks(3) {
        let value = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        text.push(DIGITS[((value >> 18) & 63) as usize] as char);
        text.push(DIGITS[((value >> 12) & 63) as usize] as char);
        if chunk.len() > 1 {
            text.push(DIGITS[((value >> 6) & 63) as usize] as char);
        }
        if chunk.len() > 2 {
            text.push(DIGITS[(value & 63) as usize] as char);
        }
    }
    text
}

fn cell_value(
    batch: &RecordBatch,
    row: usize,
    column: usize,
) -> Result<(DeclaredType, TypedScalar, Value), StorageError> {
    let field = batch.schema().field(column).clone();
    let array = batch.column(column);
    if array.is_null(row) {
        return Ok((
            DeclaredType::null(),
            TypedScalar::Null(NullScalar),
            json!({"kind":"null"}),
        ));
    }
    let spelling = scalar_type(&field).map_err(mapped)?;
    let normalized = spelling.trim_start().to_ascii_lowercase();
    let declared = if normalized.starts_with("set(")
        || normalized.starts_with("enum(")
        || normalized == "json"
    {
        DeclaredType::string()
    } else {
        declared_type(&spelling, field.data_type()).map_err(mapped)?
    };
    let typed = typed_value(array.as_ref(), row, &declared).map_err(mapped)?;
    let document = match &typed {
        TypedScalar::Null(_) => json!({"kind":"null"}),
        TypedScalar::Boolean(value) => json!({"kind":"boolean","value":value.value}),
        TypedScalar::SignedInteger(value) => {
            json!({"kind":"signed-integer","decimal":value.decimal})
        }
        TypedScalar::UnsignedInteger(value) => {
            json!({"kind":"unsigned-integer","decimal":value.decimal})
        }
        TypedScalar::Decimal(value) => json!({"kind":"decimal","decimal":value.decimal}),
        TypedScalar::Float32(value) => json!({"kind":"float32","bits_hex":
            if value.bits_hex == "80000000" { "00000000" } else { &value.bits_hex }}),
        TypedScalar::Float64(value) => json!({"kind":"float64","bits_hex":
            if value.bits_hex == "8000000000000000" { "0000000000000000" } else { &value.bits_hex }}),
        TypedScalar::String(value) => json!({"kind":"string","text":value.text}),
        TypedScalar::Binary(value) => {
            json!({"kind":"binary","bytes_base64url":base64url(&value.raw_bytes)})
        }
        TypedScalar::Bit(value) => {
            json!({"kind":"bit","bytes_base64url":base64url(&value.raw_bytes)})
        }
        TypedScalar::Date(value) => json!({"kind":"date","text":value.text}),
        TypedScalar::DateTime(value) => json!({"kind":"datetime","text":value.text}),
        TypedScalar::Timestamp(value) => json!({"kind":"timestamp","text":value.text}),
        TypedScalar::TimeDuration(value) => json!({"kind":"time-duration","text":value.text}),
        TypedScalar::Anomaly(_) => return Err(invalid("STORAGE_CELL_UNSUPPORTED")),
    };
    Ok((declared, typed, document))
}

fn key_at(
    side: &StorageSide,
    location: RowLocation,
    key_columns: &[String],
    context: &Arc<KernelContext>,
) -> Result<Vec<u8>, StorageError> {
    let batch = &side.batches[location.batch];
    let _scratch = row_scratch(side, batch, location.row, context)?;
    let mut columns = key_columns.to_vec();
    columns.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    let mut document = Vec::<Value>::with_capacity(columns.len());
    for name in &columns {
        let index = side.schema.index_of(name).map_err(mapped)?;
        let (_, _, value) = cell_value(batch, location.row, index)?;
        if value.get("kind").and_then(Value::as_str) == Some("null") {
            return Err(invalid("STORAGE_KEY_NULL"));
        }
        document.push(json!({"column":name,"value":value}));
    }
    canonicalize_jcs(&serde_json::to_vec(&document).map_err(mapped)?).map_err(mapped)
}

fn row_hash_at(
    side: &StorageSide,
    location: RowLocation,
    context: &Arc<KernelContext>,
) -> Result<String, StorageError> {
    let batch = &side.batches[location.batch];
    let _scratch = row_scratch(side, batch, location.row, context)?;
    let mut fields = Vec::with_capacity(side.retained_columns.len());
    for (column, name) in side.retained_columns.iter().enumerate() {
        let (declared_type, typed_value, _) = cell_value(batch, location.row, column)?;
        // Mutation row hashes use the long-standing PersistedRowImage mapping,
        // whose integer/decimal/BIT declared types are derived from the cell
        // document rather than the source SQL column width.
        let declared_type = match &typed_value {
            TypedScalar::SignedInteger(_) => DeclaredType::signed_integer(32).map_err(mapped)?,
            TypedScalar::UnsignedInteger(_) => {
                DeclaredType::unsigned_integer(32).map_err(mapped)?
            }
            TypedScalar::Decimal(value) => {
                let text = value.decimal.strip_prefix('-').unwrap_or(&value.decimal);
                let (integer, fraction) = text.split_once('.').unwrap_or((text, ""));
                let precision = u8::try_from(integer.len() + fraction.len())
                    .map_err(mapped)?
                    .max(1);
                let scale = u8::try_from(fraction.len()).map_err(mapped)?;
                DeclaredType::decimal(precision, scale).map_err(mapped)?
            }
            TypedScalar::Bit(_) => DeclaredType::bit(8).map_err(mapped)?,
            _ => declared_type,
        };
        fields.push(RowField {
            name: name.clone(),
            declared_type,
            typed_value,
        });
    }
    Ok(encode_row(&fields)
        .map_err(mapped)?
        .digest_ref()
        .as_str()
        .to_owned())
}

fn indexed_rows(
    side: &StorageSide,
    key_columns: &[String],
    keyless_hash: bool,
    context: &Arc<KernelContext>,
) -> Result<Vec<IndexedRow>, StorageError> {
    let mut rows = Vec::with_capacity(side.expected_rows);
    for (batch_index, batch) in side.batches.iter().enumerate() {
        for row in 0..batch.num_rows() {
            if row % 1024 == 0 {
                context.check().map_err(mapped)?;
            }
            let location = RowLocation {
                batch: batch_index,
                row,
            };
            let key = key_at(side, location, key_columns, context)?;
            let row_hash = if keyless_hash {
                Some(row_hash_at(side, location, context)?)
            } else {
                None
            };
            rows.push(IndexedRow {
                key,
                location,
                row_hash,
            });
        }
    }
    Ok(rows)
}

fn row_equal(
    before: &StorageSide,
    old: RowLocation,
    after: &StorageSide,
    new: RowLocation,
    context: &Arc<KernelContext>,
) -> Result<bool, StorageError> {
    let before_batch = &before.batches[old.batch];
    let after_batch = &after.batches[new.batch];
    let _before_scratch = row_scratch(before, before_batch, old.row, context)?;
    let _after_scratch = row_scratch(after, after_batch, new.row, context)?;
    for column in 0..before.retained_columns.len() {
        if column % 32 == 0 {
            context.check().map_err(mapped)?;
        }
        let before_field = before.schema.field(column);
        let after_field = after.schema.field(column);
        let old_cell = encode_cell(before_batch.column(column).as_ref(), old.row, before_field)
            .map_err(mapped)?;
        let new_cell = encode_cell(after_batch.column(column).as_ref(), new.row, after_field)
            .map_err(mapped)?;
        if old_cell.frame != new_cell.frame {
            return Ok(false);
        }
    }
    Ok(true)
}

/// Build at most one table's index. `diff` is false for a forced rebuild or a
/// metadata-only before side; those paths have unknown net counts.
pub fn prepare_storage_table(
    before: Option<StorageSide>,
    after: Option<StorageSide>,
    before_rows: usize,
    key_columns: &[String],
    diff: bool,
    context: Arc<KernelContext>,
) -> Result<StorageTable, StorageError> {
    context.check().map_err(mapped)?;
    // Canonical schema validation parses field JSON before row/index work.
    // Only one field's serde graph is live at a time; reserve before parsing.
    let before_schema_upper = before.as_ref().map_or(Ok(0), schema_parse_scratch_upper)?;
    let after_schema_upper = after.as_ref().map_or(Ok(0), schema_parse_scratch_upper)?;
    let schema_upper = before_schema_upper.max(after_schema_upper);
    let schema_scratch = context.reserve(schema_upper).map_err(mapped)?;
    let after_rows = after.as_ref().map_or(Ok(0), checked_rows)?;
    if let Some(side) = &before {
        if checked_rows(side)? != before_rows {
            return Err(invalid("STORAGE_ROW_COUNT_MISMATCH"));
        }
    }
    drop(schema_scratch);
    let before_validated = before.is_some();
    let after_validated = after.is_some();
    if diff && (before.is_none() || after.is_none() || key_columns.is_empty()) {
        return Err(invalid("STORAGE_DIFF_INPUT_INVALID"));
    }
    // Charge index capacity, stable-sort scratch, JCS keys and bounded action
    // refs before any vector growth. Arrow backing is charged by the caller.
    let indexed_count = (if diff { before_rows } else { 0 })
        .checked_add(after_rows)
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    let key_payload = after
        .as_ref()
        .map_or(Ok(0), |side| key_payload_bytes(side, key_columns, &context))?
        .checked_add(if diff {
            before
                .as_ref()
                .map_or(Ok(0), |side| key_payload_bytes(side, key_columns, &context))?
        } else {
            0
        })
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    let key_names = key_columns
        .iter()
        .try_fold(0usize, |sum, name| sum.checked_add(name.len()))
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    let key_per_row = key_columns
        .len()
        .checked_mul(192)
        .and_then(|size| size.checked_add(key_names.checked_mul(16)?))
        .and_then(|size| size.checked_add(256))
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    let rowhash_name_scratch = after.as_ref().map_or(Ok(0usize), |side| {
        side.retained_columns
            .iter()
            .try_fold(0usize, |sum, name| sum.checked_add(name.len()))
            .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))
    })?;
    let hash_per_row = if key_columns.is_empty() {
        after
            .as_ref()
            .map_or(0, |side| side.retained_columns.len())
            .checked_mul(256)
            .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?
    } else {
        0
    };
    let index_upper = indexed_count
        .checked_mul(key_per_row)
        // Only variable-width key values survive the row. Their JCS escapes
        // can expand to six bytes per raw byte; 16x includes Vec spare space.
        .and_then(|size| size.checked_add(key_payload.checked_mul(16)?))
        .and_then(|size| size.checked_add(after_rows.checked_mul(hash_per_row)?))
        .and_then(|size| size.checked_add(rowhash_name_scratch.checked_mul(8)?))
        .and_then(|size| {
            size.checked_add(MAX_PATCH_LOCATORS * std::mem::size_of::<PatchAction>() + 64 * 1024)
        })
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    let mut lease = context.reserve(index_upper).map_err(mapped)?;
    if let Some(side) = &before {
        validate_cells(side, &context)?;
    }
    if let Some(side) = &after {
        validate_cells(side, &context)?;
    }
    let mut after_index = if let Some(side) = &after {
        indexed_rows(side, key_columns, key_columns.is_empty(), &context)?
    } else {
        Vec::new()
    };
    let after_sort = sort_indices_checked(&after_index, &context, |a, b| {
        a.key.cmp(&b.key).then_with(|| a.row_hash.cmp(&b.row_hash))
    })
    .map_err(mapped)?;
    let mut after_order = Vec::with_capacity(after_rows);
    for &index in &after_sort {
        after_order.push(after_index[index].location);
    }
    if !key_columns.is_empty() {
        for pair in after_sort.windows(2) {
            if after_index[pair[0]].key == after_index[pair[1]].key {
                return Err(invalid("STORAGE_KEY_DUPLICATE"));
            }
        }
    }
    let mut net_counts = None;
    let mut patch_actions = Vec::new();
    if diff {
        let old = before
            .as_ref()
            .ok_or_else(|| invalid("STORAGE_DIFF_INPUT_INVALID"))?;
        let new = after
            .as_ref()
            .ok_or_else(|| invalid("STORAGE_DIFF_INPUT_INVALID"))?;
        let before_index = indexed_rows(old, key_columns, false, &context)?;
        let before_sort = sort_indices_checked(&before_index, &context, |a, b| a.key.cmp(&b.key))
            .map_err(mapped)?;
        for pair in before_sort.windows(2) {
            if before_index[pair[0]].key == before_index[pair[1]].key {
                return Err(invalid("STORAGE_KEY_DUPLICATE"));
            }
        }
        let mut counts = NetCounts::default();
        let (mut i, mut j) = (0, 0);
        while i < before_sort.len() || j < after_sort.len() {
            if (i + j) % 1024 == 0 {
                context.check().map_err(mapped)?;
            }
            let old_row = before_sort.get(i).map(|&slot| &before_index[slot]);
            let new_row = after_sort.get(j).map(|&slot| &after_index[slot]);
            match (old_row, new_row) {
                (Some(a), Some(b)) if a.key == b.key => {
                    if !row_equal(old, a.location, new, b.location, &context)? {
                        counts.updated += 1;
                        if counts.changed() <= MAX_PATCH_LOCATORS {
                            patch_actions.push(PatchAction::Update(a.location, b.location));
                        }
                    }
                    i += 1;
                    j += 1;
                }
                (Some(a), Some(b)) if a.key < b.key => {
                    counts.deleted += 1;
                    if counts.changed() <= MAX_PATCH_LOCATORS {
                        patch_actions.push(PatchAction::Delete(a.location));
                    }
                    i += 1;
                }
                (Some(_), Some(b)) => {
                    counts.inserted += 1;
                    if counts.changed() <= MAX_PATCH_LOCATORS {
                        patch_actions.push(PatchAction::Insert(b.location));
                    }
                    j += 1;
                }
                (Some(a), None) => {
                    counts.deleted += 1;
                    if counts.changed() <= MAX_PATCH_LOCATORS {
                        patch_actions.push(PatchAction::Delete(a.location));
                    }
                    i += 1;
                }
                (None, Some(b)) => {
                    counts.inserted += 1;
                    if counts.changed() <= MAX_PATCH_LOCATORS {
                        patch_actions.push(PatchAction::Insert(b.location));
                    }
                    j += 1;
                }
                (None, None) => break,
            }
        }
        net_counts = Some(counts);
    }
    // The index keys and merge-sort vectors are no longer needed after facts
    // and action locators have been retained.
    drop(after_index);
    drop(after_sort);
    let retained_before = if diff { before } else { None };
    let before_batch_bytes = retained_before.as_ref().map_or(Some(0), |side| {
        side.batches
            .capacity()
            .checked_mul(std::mem::size_of::<RecordBatch>())
    });
    let after_batch_bytes = after.as_ref().map_or(Some(0), |side| {
        side.batches
            .capacity()
            .checked_mul(std::mem::size_of::<RecordBatch>())
    });
    let retained = after_order
        .capacity()
        .checked_mul(std::mem::size_of::<RowLocation>())
        .and_then(|size| {
            size.checked_add(
                patch_actions
                    .capacity()
                    .checked_mul(std::mem::size_of::<PatchAction>())?,
            )
        })
        .and_then(|size| size.checked_add(before_batch_bytes?))
        .and_then(|size| size.checked_add(after_batch_bytes?))
        .and_then(|size| size.checked_add(4096))
        .ok_or_else(|| invalid("RESOURCE_LIMIT_EXCEEDED"))?;
    if retained > index_upper {
        return Err(invalid("RESOURCE_LIMIT_EXCEEDED"));
    }
    lease.shrink_to(retained).map_err(mapped)?;
    context.check().map_err(mapped)?;
    Ok(StorageTable {
        before: retained_before,
        after,
        before_rows,
        after_rows,
        before_validated,
        after_validated,
        net_counts,
        patch_actions,
        after_order,
        _lease: lease,
    })
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::sync::atomic::AtomicBool;

    use arrow_array::{ArrayRef, Float32Array, Int64Array, RecordBatch, StringArray, UInt64Array};
    use arrow_schema::{DataType, Field, Schema};
    use gateway_shared_kernel::{DeclaredType, RowField, StringScalar, TypedScalar, encode_row};

    use super::*;

    fn field(name: &str, sql_type: &str, kind: &str, physical: DataType) -> Field {
        let bits = if kind == "signed-integer" || kind == "unsigned-integer" {
            Some(32)
        } else {
            None
        };
        Field::new(name, physical, false).with_metadata(HashMap::from([(
            "gdds.canonical_type".to_owned(),
            json!({"declared_type":{"kind":kind,"bits":bits,"precision":null,"scale":null,"bit_width":null},
                   "labels":null,"logical_type":"standard","sql_type":sql_type}).to_string(),
        )]))
    }

    fn side(ids: &[i64], names: &[&str]) -> Result<StorageSide, Box<dyn std::error::Error>> {
        let schema = Arc::new(
            Schema::new(vec![
                field("id", "INT", "signed-integer", DataType::Int64),
                field("name", "VARCHAR(64)", "string", DataType::Utf8),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".into(),
                "1".into(),
            )])),
        );
        let batch = RecordBatch::try_new(
            Arc::clone(&schema),
            vec![
                Arc::new(Int64Array::from(ids.to_vec())) as ArrayRef,
                Arc::new(StringArray::from(names.to_vec())) as ArrayRef,
            ],
        )?;
        Ok(StorageSide {
            schema,
            batches: vec![batch],
            expected_rows: ids.len(),
            retained_columns: vec!["id".into(), "name".into()],
        })
    }

    fn context() -> Arc<KernelContext> {
        Arc::new(KernelContext::new(
            64 * 1024 * 1024,
            Arc::new(AtomicBool::new(false)),
            None,
        ))
    }

    #[test]
    fn long_escaped_cell_rejects_before_encoding_when_scratch_exceeds_m()
    -> Result<(), Box<dyn std::error::Error>> {
        let control_chars = "\0".repeat(65_536);
        let side = side(&[1], &[control_chars.as_str()])?;
        let budget = 3 * 1024 * 1024;
        let control = Arc::new(KernelContext::new(
            budget,
            Arc::new(AtomicBool::new(false)),
            None,
        ));
        let result = prepare_storage_table(
            None,
            Some(side),
            0,
            &["name".into()],
            false,
            Arc::clone(&control),
        );
        assert_eq!(
            result.err().map(|error| error.0),
            Some("RESOURCE_LIMIT_EXCEEDED".into())
        );
        assert_eq!(control.remaining_bytes(), budget);
        Ok(())
    }

    #[test]
    fn large_set_declaration_rejects_before_parsing_and_returns_its_lease()
    -> Result<(), Box<dyn std::error::Error>> {
        let labels: Vec<String> = (0..64)
            .map(|number| format!("label_{number:02}_{}", "x".repeat(240)))
            .collect();
        let sql_type = format!("SET({})", labels.iter()
            .map(|label| format!("'{label}'"))
            .collect::<Vec<_>>().join(","));
        assert!(sql_type.len() < 64 * 1024);
        let set_field = Field::new("choices", DataType::Utf8, false).with_metadata(HashMap::from([(
            "gdds.canonical_type".to_owned(),
            json!({"declared_type":null,"labels":labels,"logical_type":"set","sql_type":sql_type}).to_string(),
        )]));
        let schema = Arc::new(Schema::new(vec![set_field]).with_metadata(HashMap::from([(
            "gdds.canonical_mapping_version".into(), "1".into(),
        )])));
        let batch = RecordBatch::try_new(Arc::clone(&schema), vec![
            Arc::new(StringArray::from(vec![""])) as ArrayRef,
        ])?;
        let side = StorageSide { schema, batches: vec![batch], expected_rows: 1,
            retained_columns: vec!["choices".into()] };
        let budget = schema_parse_scratch_upper(&side)? + 64 * 1024;
        let control = Arc::new(KernelContext::new(budget, Arc::new(AtomicBool::new(false)), None));
        let result = prepare_storage_table(None, Some(side), 0, &[], false, Arc::clone(&control));
        assert_eq!(result.err().map(|error| error.0), Some("RESOURCE_LIMIT_EXCEEDED".into()));
        assert_eq!(control.remaining_bytes(), budget);
        Ok(())
    }

    #[test]
    fn persisted_keyed_diff_counts_one_update_for_a_changed_image()
    -> Result<(), Box<dyn std::error::Error>> {
        let result = prepare_storage_table(
            Some(side(&[1, 2], &["old", "same"])?),
            Some(side(&[2, 1, 3], &["same", "new", "insert"])?),
            2,
            &["id".into()],
            true,
            context(),
        )?;
        assert_eq!(
            result.net_counts,
            Some(NetCounts {
                inserted: 1,
                updated: 1,
                deleted: 0
            })
        );
        assert_eq!(result.patch_actions.len(), 2);
        Ok(())
    }

    #[test]
    fn duplicate_storage_key_is_rejected_before_any_action()
    -> Result<(), Box<dyn std::error::Error>> {
        let result = prepare_storage_table(
            None,
            Some(side(&[1, 1], &["a", "b"])?),
            0,
            &["id".into()],
            false,
            context(),
        );
        assert_eq!(
            result.err().map(|error| error.0),
            Some("STORAGE_KEY_DUPLICATE".into())
        );
        Ok(())
    }

    #[test]
    fn keyless_sort_hash_comes_from_shared_row_encoding() -> Result<(), Box<dyn std::error::Error>>
    {
        let side = side(&[1, 1], &["a", "b"])?;
        let first = row_hash_at(&side, RowLocation { batch: 0, row: 0 }, &context())?;
        let expected = encode_row(&[
            RowField {
                name: "name".into(),
                declared_type: DeclaredType::string(),
                typed_value: TypedScalar::String(StringScalar { text: "a".into() }),
            },
            RowField {
                name: "id".into(),
                declared_type: DeclaredType::signed_integer(32)?,
                typed_value: TypedScalar::SignedInteger(
                    gateway_shared_kernel::SignedIntegerScalar {
                        decimal: "1".into(),
                    },
                ),
            },
        ])?;
        assert_eq!(first, expected.digest_ref().as_str());
        let result = prepare_storage_table(None, Some(side), 0, &[], false, context())?;
        assert_eq!(result.after_order.len(), 2);
        assert!(result.net_counts.is_none());
        Ok(())
    }

    #[test]
    fn ordered_gid_is_key_and_no_remains_a_persisted_value()
    -> Result<(), Box<dyn std::error::Error>> {
        let schema = Arc::new(
            Schema::new(vec![
                field("gid", "INT UNSIGNED", "unsigned-integer", DataType::UInt64),
                field("no", "INT", "signed-integer", DataType::Int64),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".into(),
                "1".into(),
            )])),
        );
        let make = |no: i64| -> Result<StorageSide, arrow_schema::ArrowError> {
            let batch = RecordBatch::try_new(
                Arc::clone(&schema),
                vec![
                    Arc::new(UInt64Array::from(vec![4_000_000_001])) as ArrayRef,
                    Arc::new(Int64Array::from(vec![no])) as ArrayRef,
                ],
            )?;
            Ok(StorageSide {
                schema: Arc::clone(&schema),
                batches: vec![batch],
                expected_rows: 1,
                retained_columns: vec!["gid".into(), "no".into()],
            })
        };
        let result = prepare_storage_table(
            Some(make(1)?),
            Some(make(2)?),
            1,
            &["gid".into()],
            true,
            context(),
        )?;
        assert_eq!(
            result.net_counts,
            Some(NetCounts {
                inserted: 0,
                updated: 1,
                deleted: 0
            })
        );
        Ok(())
    }

    #[test]
    fn full_diff_counts_past_locator_limit_without_retaining_more_actions()
    -> Result<(), Box<dyn std::error::Error>> {
        let ids: Vec<i64> = (0..1001).collect();
        let old_names = vec!["old"; 1001];
        let new_names = vec!["new"; 1001];
        let result = prepare_storage_table(
            Some(side(&ids, &old_names)?),
            Some(side(&ids, &new_names)?),
            1001,
            &["id".into()],
            true,
            context(),
        )?;
        assert_eq!(
            result.net_counts,
            Some(NetCounts {
                inserted: 0,
                updated: 1001,
                deleted: 0
            })
        );
        assert_eq!(result.patch_actions.len(), 1000);
        Ok(())
    }

    #[test]
    fn jcs_key_order_is_decimal_text_not_numeric_order() -> Result<(), Box<dyn std::error::Error>> {
        let result = prepare_storage_table(
            None,
            Some(side(&[2, 10], &["two", "ten"])?),
            0,
            &["id".into()],
            false,
            context(),
        )?;
        assert_eq!(
            result.after_order,
            vec![
                RowLocation { batch: 0, row: 1 },
                RowLocation { batch: 0, row: 0 }
            ]
        );
        Ok(())
    }

    #[test]
    fn negative_zero_and_positive_zero_have_equal_persisted_frames()
    -> Result<(), Box<dyn std::error::Error>> {
        let schema = Arc::new(
            Schema::new(vec![
                field("id", "INT", "signed-integer", DataType::Int64),
                field("measure", "FLOAT", "float32", DataType::Float32),
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".into(),
                "1".into(),
            )])),
        );
        let make = |value: f32| -> Result<StorageSide, arrow_schema::ArrowError> {
            let batch = RecordBatch::try_new(
                Arc::clone(&schema),
                vec![
                    Arc::new(Int64Array::from(vec![1])) as ArrayRef,
                    Arc::new(Float32Array::from(vec![value])) as ArrayRef,
                ],
            )?;
            Ok(StorageSide {
                schema: Arc::clone(&schema),
                batches: vec![batch],
                expected_rows: 1,
                retained_columns: vec!["id".into(), "measure".into()],
            })
        };
        let result = prepare_storage_table(
            Some(make(-0.0)?),
            Some(make(0.0)?),
            1,
            &["id".into()],
            true,
            context(),
        )?;
        assert_eq!(result.net_counts, Some(NetCounts::default()));
        Ok(())
    }

    #[test]
    fn rebuild_validates_nonkey_set_members_before_claiming_identity()
    -> Result<(), Box<dyn std::error::Error>> {
        let set_field = Field::new("members", DataType::Utf8, false).with_metadata(HashMap::from([(
            "gdds.canonical_type".into(),
            json!({"declared_type":null,"labels":["allowed"],"logical_type":"set","sql_type":"SET('allowed')"}).to_string(),
        )]));
        let schema = Arc::new(
            Schema::new(vec![
                field("id", "INT", "signed-integer", DataType::Int64),
                set_field,
            ])
            .with_metadata(HashMap::from([(
                "gdds.canonical_mapping_version".into(),
                "1".into(),
            )])),
        );
        let batch = RecordBatch::try_new(
            Arc::clone(&schema),
            vec![
                Arc::new(Int64Array::from(vec![1])) as ArrayRef,
                Arc::new(StringArray::from(vec!["outside"])) as ArrayRef,
            ],
        )?;
        let side = StorageSide {
            schema,
            batches: vec![batch],
            expected_rows: 1,
            retained_columns: vec!["id".into(), "members".into()],
        };
        let result = prepare_storage_table(None, Some(side), 0, &["id".into()], false, context());
        assert_eq!(
            result.err().map(|error| error.0),
            Some("SET_VALUE_INVALID".into())
        );
        Ok(())
    }
}
