//! IEC104 `gid` / `no` ordered comparison prototype (GID_NO_V1).
//!
//! Inputs are projection-ready Arrow batches. The implementation is table-local;
//! `compare_ordered_tables_parallel` assigns tables to a caller-owned fixed pool.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fmt;
use std::panic::AssertUnwindSafe;

use arrow_array::{
    Array, BinaryArray, BooleanArray, Decimal128Array, Decimal256Array, FixedSizeBinaryArray,
    Float32Array, Float64Array, Int8Array, Int16Array, Int32Array, Int64Array, LargeBinaryArray,
    LargeStringArray, ListArray, RecordBatch, StringArray, UInt8Array, UInt16Array, UInt32Array,
    UInt64Array,
};
use arrow_schema::{DataType, Field};
use gateway_shared_kernel::{
    BinaryScalar, BitScalar, BooleanScalar, CollectionSemantics, DateScalar, DateTimeScalar,
    DecimalScalar, DeclaredType, DigestKind, Float32Scalar, Float64Scalar, NullScalar,
    SignedIntegerScalar, StringScalar, TimeDurationScalar, TimestampScalar, TypedScalar,
    UnsignedIntegerScalar, canonicalize_identifier, canonicalize_jcs, encode_collection,
    encode_typed_scalar, raw_blob_digest, semantic_digest,
};
use rayon::ThreadPool;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const ORDERED_COMPARE_FORMAT: &str = "gateway.comparison.ordered-canonical";
pub const ORDERED_COMPARE_VERSION: u32 = 1;
pub const ORDERED_DIFF_CONTRACT_VERSION: &str = "backend-vnext/ordered-diff/v2";
pub const BLANK_COMPARISON_CONTRACT_VERSION: &str = "backend-vnext/comparison-blank/v1";
pub const GID_REAL_MIN: i128 = 1;
pub const GID_REAL_MAX: i128 = 3_999_999_999;
pub const GID_PSEUDO_MIN: i128 = 4_000_000_000;
pub const GID_PSEUDO_MAX: i128 = 4_294_967_295;
pub const DEFAULT_MAX_ORDERED_ROWS: usize = 2_000_000;
pub const MAX_ORDERED_THREADS: usize = 256;
const MAX_ORDERED_COLUMNS: usize = 512;
const MAX_ORDERED_CELL_BYTES: usize = 4 * 1024 * 1024;
const MAX_ORDERED_TOTAL_ENCODED_BYTES: usize = 256 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlankProvenance {
    Missing,
    SourceMissingStableKey,
    CanonicalPseudoGid,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SchemaChanges {
    pub before_only_columns: Vec<String>,
    pub current_only_columns: Vec<String>,
    pub selected_columns: Vec<String>,
    pub effective_compare_key_before: Vec<String>,
    pub effective_compare_key_current: Vec<String>,
    pub effective_compare_key_changed: bool,
    pub incompatible_columns: Vec<String>,
    pub change_source: Option<String>,
}

impl Default for SchemaChanges {
    fn default() -> Self {
        Self {
            before_only_columns: Vec::new(),
            current_only_columns: Vec::new(),
            selected_columns: Vec::new(),
            effective_compare_key_before: vec!["gid".to_string()],
            effective_compare_key_current: vec!["gid".to_string()],
            effective_compare_key_changed: false,
            incompatible_columns: Vec::new(),
            change_source: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct OrderedCompareOptions {
    pub table_name: String,
    /// Reference ordered policy version; participates in the ordered digest.
    pub policy_version: String,
    pub policy_digest: Option<String>,
    /// Resolved common business columns, excluding `gid`, `no`, and ignored fields.
    pub value_columns: Vec<String>,
    /// Ordered logical digest columns as frozen in the ordered policy. Unlike
    /// value comparison, this list is not reduced by compare-excluded columns.
    pub digest_value_columns: Vec<String>,
    pub compare_excluded_columns: Vec<String>,
    pub include_add_delete_records: bool,
    pub schema_changed: bool,
    pub raw_content_changed: bool,
    pub schema_changes: SchemaChanges,
    pub before_blank_provenance: BlankProvenance,
    pub current_blank_provenance: BlankProvenance,
    pub max_rows: usize,
}

impl OrderedCompareOptions {
    pub fn new(table_name: impl Into<String>) -> Self {
        Self {
            table_name: table_name.into(),
            policy_version: "ordered-runtime-v1".to_string(),
            policy_digest: None,
            value_columns: Vec::new(),
            digest_value_columns: Vec::new(),
            compare_excluded_columns: Vec::new(),
            include_add_delete_records: true,
            schema_changed: false,
            raw_content_changed: false,
            schema_changes: SchemaChanges::default(),
            before_blank_provenance: BlankProvenance::SourceMissingStableKey,
            current_blank_provenance: BlankProvenance::SourceMissingStableKey,
            max_rows: DEFAULT_MAX_ORDERED_ROWS,
        }
    }
}

pub struct OrderedTablePair<'a> {
    pub before: Option<&'a RecordBatch>,
    pub current: Option<&'a RecordBatch>,
    pub options: &'a OrderedCompareOptions,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OrderedCompareError {
    code: &'static str,
}

impl OrderedCompareError {
    fn new(code: &'static str) -> Self {
        Self { code }
    }

    pub fn code(&self) -> &'static str {
        self.code
    }
}

impl fmt::Display for OrderedCompareError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code)
    }
}

impl std::error::Error for OrderedCompareError {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CanonicalValue {
    pub column: String,
    pub type_marker: u8,
    pub frame_hex: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct StandardRecord {
    pub table_name: String,
    pub record_kind: String,
    pub row_identity: Option<String>,
    pub changed_columns: Vec<String>,
    pub before_values: Vec<CanonicalValue>,
    pub current_values: Vec<CanonicalValue>,
    pub field_changes: Vec<FieldChange>,
    pub diagnostics: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FieldChange {
    pub table_name: String,
    pub row_identity: String,
    pub column: String,
    pub before: CanonicalValue,
    pub current: CanonicalValue,
    pub change_kind: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct OrderedRecord {
    pub table_name: String,
    pub record_kind: String,
    pub semantic_kind: String,
    pub entity_key_kind: String,
    pub row_identity: String,
    pub before_position: Option<i64>,
    pub current_position: Option<i64>,
    pub changed_columns: Vec<String>,
    pub before_values: Vec<CanonicalValue>,
    pub current_values: Vec<CanonicalValue>,
    pub diagnostics: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct BlankInterval {
    pub before_start: Option<i64>,
    pub before_end: Option<i64>,
    pub current_start: Option<i64>,
    pub current_end: Option<i64>,
    pub row_count: usize,
    pub interval_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct BlankRecord {
    pub table_name: String,
    pub record_kind: String,
    pub semantic_kind: String,
    pub entity_key_kind: String,
    pub interval: BlankInterval,
    pub before_occupancy: usize,
    pub current_occupancy: usize,
    pub diagnostics: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct OrderedCompareResult {
    pub format: String,
    pub version: u32,
    pub table_name: String,
    pub status: String,
    pub row_count_before: Option<usize>,
    pub row_count_current: Option<usize>,
    pub row_added_count: usize,
    pub row_deleted_count: usize,
    pub row_modified_count: usize,
    pub suppressed_added_count: usize,
    pub suppressed_deleted_count: usize,
    pub content_changed: bool,
    pub schema_changes: SchemaChanges,
    pub diagnostics: Vec<String>,
    pub records: Vec<StandardRecord>,
    pub ordered_extension: OrderedExtensionResult,
    pub blank_extension: BlankExtensionResult,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct OrderedExtensionResult {
    pub contract_version: String,
    pub status: String,
    pub summary: OrderedSummary,
    pub before_ordered_digest: Option<String>,
    pub current_ordered_digest: Option<String>,
    pub replay_guarantee: String,
    pub table_processing_mode: Option<String>,
    pub policy_digest: Option<String>,
    pub diagnostics: Vec<String>,
    pub records: Vec<OrderedRecord>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct OrderedSummary {
    pub row_added_count: usize,
    pub row_deleted_count: usize,
    pub row_modified_count: usize,
    pub row_moved_count: usize,
    pub position_changed_count: usize,
    pub degraded_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct BlankExtensionResult {
    pub contract_version: String,
    pub status: String,
    pub summary: BlankSummary,
    pub before_occupancy_digest: Option<String>,
    pub current_occupancy_digest: Option<String>,
    pub replay_guarantee: String,
    pub diagnostics: Vec<String>,
    pub records: Vec<BlankRecord>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct BlankSummary {
    pub interval_inserted_count: usize,
    pub interval_deleted_count: usize,
    pub blank_changed_count: usize,
    pub degraded_count: usize,
}

impl OrderedCompareResult {
    /// Test-only normalized facts encoding. It contains record values as hex
    /// scalar frames; callers must keep real-data files private and off Git.
    pub fn canonical_bytes(&self) -> Result<Vec<u8>, OrderedCompareError> {
        let value = serde_json::to_value(self)
            .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
        let json_bytes = serde_json::to_vec(&value)
            .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
        let canonical = canonicalize_jcs(&json_bytes)
            .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
        let len = u32::try_from(canonical.len())
            .map_err(|_| OrderedCompareError::new("CANONICAL_SIZE_EXCEEDED"))?;
        let mut output = Vec::with_capacity(12 + canonical.len());
        output.extend_from_slice(b"GDMSOCF1");
        output.extend_from_slice(&len.to_be_bytes());
        output.extend_from_slice(&canonical);
        Ok(output)
    }

    pub fn summary_json(&self) -> Result<Value, OrderedCompareError> {
        let canonical = self.canonical_bytes()?;
        let json = canonical
            .get(12..)
            .ok_or_else(|| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
        serde_json::from_slice(json)
            .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))
    }
}

/// Compare one table. Unexpected panics are contained at this public core boundary.
pub fn compare_ordered_table(
    pair: OrderedTablePair<'_>,
) -> Result<OrderedCompareResult, OrderedCompareError> {
    match std::panic::catch_unwind(AssertUnwindSafe(|| compare_ordered_table_inner(pair))) {
        Ok(result) => result,
        Err(_) => Err(OrderedCompareError::new("ORDERED_INTERNAL_ERROR")),
    }
}

/// Compare a set of table pairs with the caller-owned fixed Rayon pool.
/// Results are returned in canonical table-name order, independent of scheduling.
pub fn compare_ordered_tables_parallel(
    pairs: &[OrderedTablePair<'_>],
    pool: &ThreadPool,
) -> Result<Vec<OrderedCompareResult>, OrderedCompareError> {
    let work = || {
        let mut results = pairs
            .par_iter()
            .map(|pair| {
                compare_ordered_table(OrderedTablePair {
                    before: pair.before,
                    current: pair.current,
                    options: pair.options,
                })
            })
            .collect::<Vec<_>>();
        let mut output = Vec::with_capacity(results.len());
        for result in results.drain(..) {
            output.push(result?);
        }
        output.sort_by(|left, right| left.table_name.cmp(&right.table_name));
        if output
            .windows(2)
            .any(|pair| pair[0].table_name == pair[1].table_name)
        {
            return Err(OrderedCompareError::new("DUPLICATE_TABLE_NAME"));
        }
        Ok(output)
    };
    match std::panic::catch_unwind(AssertUnwindSafe(|| pool.install(work))) {
        Ok(result) => result,
        Err(_) => Err(OrderedCompareError::new("ORDERED_INTERNAL_ERROR")),
    }
}

/// Builds a bounded fixed-size pool. The caller owns and reuses it.
pub fn build_ordered_pool(threads: usize) -> Result<ThreadPool, OrderedCompareError> {
    if !(1..=MAX_ORDERED_THREADS).contains(&threads) {
        return Err(OrderedCompareError::new("THREAD_COUNT_INVALID"));
    }
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .thread_name(|index| format!("gdms-ordered-{index}"))
        .build()
        .map_err(|_| OrderedCompareError::new("THREAD_POOL_BUILD_FAILED"))
}

#[derive(Debug, Clone)]
struct EncodedCell {
    frame: Vec<u8>,
}

impl EncodedCell {
    fn canonical_value(&self, column: &str) -> CanonicalValue {
        CanonicalValue {
            column: column.to_string(),
            type_marker: self.frame.first().copied().unwrap_or_default(),
            frame_hex: hex(&self.frame),
        }
    }
}

#[derive(Debug, Clone)]
struct OrderedRow {
    position: i64,
    stable_key: Option<Vec<u8>>,
    stable_identity: Option<String>,
    blank: bool,
    cells: BTreeMap<String, EncodedCell>,
}

#[derive(Debug, Clone, Copy)]
struct Gap {
    count: usize,
    start: i64,
    end: i64,
}

#[derive(Debug, Clone)]
struct SideRows {
    rows: Vec<OrderedRow>,
}

fn compare_ordered_table_inner(
    pair: OrderedTablePair<'_>,
) -> Result<OrderedCompareResult, OrderedCompareError> {
    let options = pair.options;
    if options.table_name.is_empty() || options.policy_version.is_empty() || options.max_rows == 0 {
        return Err(OrderedCompareError::new("ORDERED_POLICY_INVALID"));
    }
    if pair.before.is_none() && pair.current.is_none() {
        return Err(OrderedCompareError::new("TABLE_TASK_HAS_NO_SIDE"));
    }
    if pair.before.is_some() && options.before_blank_provenance == BlankProvenance::Missing {
        return Ok(degraded_result(pair, "BLANK_PROVENANCE_MISSING"));
    }
    if pair.current.is_some() && options.current_blank_provenance == BlankProvenance::Missing {
        return Ok(degraded_result(pair, "BLANK_PROVENANCE_MISSING"));
    }

    let before_columns = column_names(pair.before)?;
    let current_columns = column_names(pair.current)?;
    let selected = selected_columns(
        &before_columns,
        &current_columns,
        pair.before.is_some(),
        pair.current.is_some(),
    );
    if !selected.iter().any(|name| name == "gid") || !selected.iter().any(|name| name == "no") {
        return Ok(degraded_result(pair, "ORDERED_REQUIRED_COLUMN_MISSING"));
    }
    if !options.schema_changes.incompatible_columns.is_empty() {
        return Ok(degraded_result(pair, "INCOMPATIBLE_SELECTED_COLUMNS"));
    }
    let value_columns = resolved_value_columns(options, &selected);
    let digest_value_columns = resolved_digest_value_columns(options, &selected);
    let before = match read_side(
        pair.before,
        &selected,
        options.before_blank_provenance,
        options.max_rows,
    ) {
        Ok(rows) => rows,
        Err(error) => return Ok(degraded_result(pair, error.code())),
    };
    let current = match read_side(
        pair.current,
        &selected,
        options.current_blank_provenance,
        options.max_rows,
    ) {
        Ok(rows) => rows,
        Err(error) => return Ok(degraded_result(pair, error.code())),
    };

    let before_real = real_index(&before.rows);
    let current_real = real_index(&current.rows);
    let added_keys: Vec<Vec<u8>> = current_real
        .keys()
        .filter(|key| !before_real.contains_key(*key))
        .cloned()
        .collect();
    let deleted_keys: Vec<Vec<u8>> = before_real
        .keys()
        .filter(|key| !current_real.contains_key(*key))
        .cloned()
        .collect();
    let common_keys: Vec<Vec<u8>> = before_real
        .keys()
        .filter(|key| current_real.contains_key(*key))
        .cloned()
        .collect();

    let mut changed_by_key = BTreeMap::<Vec<u8>, Vec<String>>::new();
    for key in &common_keys {
        let before_row = &before.rows[before_real[key]];
        let current_row = &current.rows[current_real[key]];
        let changed: Vec<String> = value_columns
            .iter()
            .filter(|column| {
                before_row.cells.get(*column).map(|cell| &cell.frame)
                    != current_row.cells.get(*column).map(|cell| &cell.frame)
            })
            .cloned()
            .collect();
        if !changed.is_empty() {
            changed_by_key.insert(key.clone(), changed);
        }
    }

    let common_keys_in_before_order: Vec<Vec<u8>> = before
        .rows
        .iter()
        .filter_map(|row| {
            row.stable_key
                .as_ref()
                .filter(|key| current_real.contains_key(*key))
                .cloned()
        })
        .collect();
    let current_positions: Vec<i64> = common_keys_in_before_order
        .iter()
        .map(|key| current.rows[current_real[key]].position)
        .collect();
    let backbone_indices = longest_increasing_backbone(&current_positions);
    let backbone: HashSet<Vec<u8>> = backbone_indices
        .iter()
        .filter_map(|index| common_keys_in_before_order.get(*index).cloned())
        .collect();
    let moved_keys: Vec<Vec<u8>> = common_keys
        .iter()
        .filter(|key| !backbone.contains(*key))
        .cloned()
        .collect();
    let position_changed_keys: HashSet<Vec<u8>> = backbone
        .iter()
        .filter(|key| {
            before.rows[before_real[*key]].position != current.rows[current_real[*key]].position
        })
        .cloned()
        .collect();

    let mut standard_records = Vec::new();
    let mut ordered_records = Vec::new();
    if options.include_add_delete_records {
        for key in &added_keys {
            let row = &current.rows[current_real[key]];
            standard_records.push(standard_record(
                &options.table_name,
                "ROW_ADDED",
                row,
                Some(&selected),
                None,
                Vec::new(),
                vec!["ORDERED_PROVIDER".to_string()],
            ));
            ordered_records.push(ordered_record(OrderedRecordSpec {
                table_name: &options.table_name,
                record_kind: "ORDERED_ROW_ADDED",
                semantic_kind: "DATA_INSERT",
                row_identity: row.stable_identity.as_deref(),
                before_position: None,
                current_position: Some(row.position),
                changed_columns: Vec::new(),
                before_values: Vec::new(),
                current_values: values(row, &value_columns),
            })?);
        }
        for key in &deleted_keys {
            let row = &before.rows[before_real[key]];
            standard_records.push(standard_record(
                &options.table_name,
                "ROW_DELETED",
                row,
                None,
                Some(&selected),
                Vec::new(),
                vec!["ORDERED_PROVIDER".to_string()],
            ));
            ordered_records.push(ordered_record(OrderedRecordSpec {
                table_name: &options.table_name,
                record_kind: "ORDERED_ROW_DELETED",
                semantic_kind: "DATA_DELETE",
                row_identity: row.stable_identity.as_deref(),
                before_position: Some(row.position),
                current_position: None,
                changed_columns: Vec::new(),
                before_values: values(row, &value_columns),
                current_values: Vec::new(),
            })?);
        }
    }

    for (key, changed_columns) in &changed_by_key {
        let before_row = &before.rows[before_real[key]];
        let current_row = &current.rows[current_real[key]];
        let identity = before_row
            .stable_identity
            .as_deref()
            .ok_or_else(|| OrderedCompareError::new("ROW_IDENTITY_MISSING"))?;
        let field_changes: Vec<FieldChange> = changed_columns
            .iter()
            .map(|column| {
                let before_cell = before_row
                    .cells
                    .get(column)
                    .ok_or_else(|| OrderedCompareError::new("ROW_SHAPE_MISMATCH"))?;
                let current_cell = current_row
                    .cells
                    .get(column)
                    .ok_or_else(|| OrderedCompareError::new("ROW_SHAPE_MISMATCH"))?;
                Ok(FieldChange {
                    table_name: options.table_name.clone(),
                    row_identity: identity.to_string(),
                    column: column.clone(),
                    before: before_cell.canonical_value(column),
                    current: current_cell.canonical_value(column),
                    change_kind: "UPDATE".to_string(),
                })
            })
            .collect::<Result<_, OrderedCompareError>>()?;
        let before_values = values(before_row, changed_columns);
        let current_values = values(current_row, changed_columns);
        standard_records.push(StandardRecord {
            table_name: options.table_name.clone(),
            record_kind: "ROW_MODIFIED".to_string(),
            row_identity: Some(identity.to_string()),
            changed_columns: changed_columns.clone(),
            before_values: before_values.clone(),
            current_values: current_values.clone(),
            field_changes,
            diagnostics: Vec::new(),
        });
        ordered_records.push(ordered_record(OrderedRecordSpec {
            table_name: &options.table_name,
            record_kind: "ORDERED_ROW_MODIFIED",
            semantic_kind: "CONTENT_UPDATE",
            row_identity: Some(identity),
            before_position: Some(before_row.position),
            current_position: Some(current_row.position),
            changed_columns: changed_columns.clone(),
            before_values,
            current_values,
        })?);
    }

    for key in &moved_keys {
        let before_row = &before.rows[before_real[key]];
        let current_row = &current.rows[current_real[key]];
        ordered_records.push(ordered_record(OrderedRecordSpec {
            table_name: &options.table_name,
            record_kind: "ORDERED_ROW_MOVED",
            semantic_kind: "MOVE",
            row_identity: before_row.stable_identity.as_deref(),
            before_position: Some(before_row.position),
            current_position: Some(current_row.position),
            changed_columns: Vec::new(),
            before_values: Vec::new(),
            current_values: Vec::new(),
        })?);
    }

    standard_records.sort_by(|left, right| {
        left.record_kind
            .cmp(&right.record_kind)
            .then_with(|| left.row_identity.cmp(&right.row_identity))
            .then_with(|| left.changed_columns.cmp(&right.changed_columns))
    });
    ordered_records.sort_by(|left, right| {
        left.record_kind
            .cmp(&right.record_kind)
            .then_with(|| {
                left.current_position
                    .or(left.before_position)
                    .unwrap_or_default()
                    .cmp(
                        &right
                            .current_position
                            .or(right.before_position)
                            .unwrap_or_default(),
                    )
            })
            .then_with(|| left.row_identity.cmp(&right.row_identity))
    });

    let blank = blank_extension(
        &options.table_name,
        &before.rows,
        &current.rows,
        &backbone,
        options.include_add_delete_records,
    )?;
    let added_count = added_keys.len();
    let deleted_count = deleted_keys.len();
    let modified_count = changed_by_key.len();
    let moved_count = moved_keys.len();
    let position_changed_count = position_changed_keys.len();
    let segment_changed =
        added_count > 0 || deleted_count > 0 || blank.summary.blank_changed_count > 0;
    let mode = if moved_count > 0 {
        Some("ORDERED_REORDER_COMPLEX")
    } else if position_changed_count > 0 {
        Some("ORDERED_SHIFT_REPAIRED")
    } else if segment_changed && modified_count == 0 {
        Some("ORDERED_TAIL_SEGMENT")
    } else if modified_count > 0 {
        Some("ORDERED_LOCAL_PATCH")
    } else {
        None
    };
    let ordered_changed = !ordered_records.is_empty()
        || added_count > 0
        || deleted_count > 0
        || position_changed_count > 0;
    let blank_changed = blank.summary.blank_changed_count > 0;
    let status = if pair.before.is_none() {
        "ADDED_TABLE"
    } else if pair.current.is_none() {
        "DELETED_TABLE"
    } else if ordered_changed || blank_changed {
        "MODIFIED"
    } else if options.schema_changed {
        "SCHEMA_ONLY_CHANGED"
    } else {
        "UNCHANGED"
    };
    let before_digest = Some(ordered_digest(
        &before.rows,
        &options.table_name,
        &options.policy_version,
        &digest_value_columns,
    )?);
    let current_digest = Some(ordered_digest(
        &current.rows,
        &options.table_name,
        &options.policy_version,
        &digest_value_columns,
    )?);
    let content_changed = status == "UNCHANGED"
        && !options.compare_excluded_columns.is_empty()
        && options.raw_content_changed;

    Ok(OrderedCompareResult {
        format: ORDERED_COMPARE_FORMAT.to_string(),
        version: ORDERED_COMPARE_VERSION,
        table_name: options.table_name.clone(),
        status: status.to_string(),
        row_count_before: pair.before.map(RecordBatch::num_rows),
        row_count_current: pair.current.map(RecordBatch::num_rows),
        row_added_count: added_count,
        row_deleted_count: deleted_count,
        row_modified_count: modified_count,
        suppressed_added_count: if options.include_add_delete_records {
            0
        } else {
            added_count
        },
        suppressed_deleted_count: if options.include_add_delete_records {
            0
        } else {
            deleted_count
        },
        content_changed,
        schema_changes: options.schema_changes.clone(),
        diagnostics: Vec::new(),
        records: standard_records,
        ordered_extension: OrderedExtensionResult {
            contract_version: ORDERED_DIFF_CONTRACT_VERSION.to_string(),
            status: if mode.is_some() {
                "ORDERED_CHANGED"
            } else {
                "ORDERED_UNCHANGED"
            }
            .to_string(),
            summary: OrderedSummary {
                row_added_count: added_count,
                row_deleted_count: deleted_count,
                row_modified_count: modified_count,
                row_moved_count: moved_count,
                position_changed_count,
                degraded_count: 0,
            },
            before_ordered_digest: before_digest,
            current_ordered_digest: current_digest,
            replay_guarantee: "EXACT".to_string(),
            table_processing_mode: mode.map(str::to_string),
            policy_digest: options.policy_digest.clone(),
            diagnostics: Vec::new(),
            records: ordered_records,
        },
        blank_extension: BlankExtensionResult {
            contract_version: BLANK_COMPARISON_CONTRACT_VERSION.to_string(),
            status: if blank.summary.blank_changed_count > 0 {
                "ORDERED_CHANGED"
            } else {
                "ORDERED_UNCHANGED"
            }
            .to_string(),
            summary: blank.summary,
            before_occupancy_digest: Some(blank.before_digest),
            current_occupancy_digest: Some(blank.current_digest),
            replay_guarantee: "EXACT".to_string(),
            diagnostics: Vec::new(),
            records: blank.records,
        },
    })
}

fn degraded_result(pair: OrderedTablePair<'_>, diagnostic: &'static str) -> OrderedCompareResult {
    let options = pair.options;
    let diagnostics = vec![diagnostic.to_string()];
    OrderedCompareResult {
        format: ORDERED_COMPARE_FORMAT.to_string(),
        version: ORDERED_COMPARE_VERSION,
        table_name: options.table_name.clone(),
        status: "DEGRADED".to_string(),
        row_count_before: pair.before.map(RecordBatch::num_rows),
        row_count_current: pair.current.map(RecordBatch::num_rows),
        row_added_count: 0,
        row_deleted_count: 0,
        row_modified_count: 0,
        suppressed_added_count: 0,
        suppressed_deleted_count: 0,
        content_changed: false,
        schema_changes: options.schema_changes.clone(),
        diagnostics: diagnostics.clone(),
        records: vec![StandardRecord {
            table_name: options.table_name.clone(),
            record_kind: "TABLE_DEGRADED".to_string(),
            row_identity: None,
            changed_columns: Vec::new(),
            before_values: Vec::new(),
            current_values: Vec::new(),
            field_changes: Vec::new(),
            diagnostics: diagnostics.clone(),
        }],
        ordered_extension: OrderedExtensionResult {
            contract_version: ORDERED_DIFF_CONTRACT_VERSION.to_string(),
            status: "ORDERED_DEGRADED".to_string(),
            summary: OrderedSummary {
                row_added_count: 0,
                row_deleted_count: 0,
                row_modified_count: 0,
                row_moved_count: 0,
                position_changed_count: 0,
                degraded_count: 1,
            },
            before_ordered_digest: None,
            current_ordered_digest: None,
            replay_guarantee: "UNSUPPORTED".to_string(),
            table_processing_mode: Some("DEGRADED".to_string()),
            policy_digest: options.policy_digest.clone(),
            diagnostics: diagnostics.clone(),
            records: Vec::new(),
        },
        blank_extension: BlankExtensionResult {
            contract_version: BLANK_COMPARISON_CONTRACT_VERSION.to_string(),
            status: "ORDERED_DEGRADED".to_string(),
            summary: BlankSummary {
                interval_inserted_count: 0,
                interval_deleted_count: 0,
                blank_changed_count: 0,
                degraded_count: 1,
            },
            before_occupancy_digest: None,
            current_occupancy_digest: None,
            replay_guarantee: "UNSUPPORTED".to_string(),
            diagnostics,
            records: Vec::new(),
        },
    }
}

fn selected_columns(
    before: &[String],
    current: &[String],
    has_before: bool,
    has_current: bool,
) -> Vec<String> {
    let left: BTreeSet<&str> = before.iter().map(String::as_str).collect();
    let right: BTreeSet<&str> = current.iter().map(String::as_str).collect();
    if has_before && has_current {
        left.intersection(&right)
            .map(|name| (*name).to_string())
            .collect()
    } else {
        left.union(&right).map(|name| (*name).to_string()).collect()
    }
}

fn resolved_value_columns(options: &OrderedCompareOptions, selected: &[String]) -> Vec<String> {
    let excluded: HashSet<&str> = options
        .compare_excluded_columns
        .iter()
        .map(String::as_str)
        .collect();
    let candidate = if options.value_columns.is_empty() {
        selected
            .iter()
            .filter(|name| name.as_str() != "gid" && name.as_str() != "no")
            .cloned()
            .collect::<Vec<_>>()
    } else {
        options.value_columns.clone()
    };
    candidate
        .into_iter()
        .filter(|name| !excluded.contains(name.as_str()))
        .collect()
}

fn resolved_digest_value_columns(
    options: &OrderedCompareOptions,
    selected: &[String],
) -> Vec<String> {
    if !options.digest_value_columns.is_empty() {
        return options.digest_value_columns.clone();
    }
    selected
        .iter()
        .filter(|name| name.as_str() != "gid" && name.as_str() != "no")
        .cloned()
        .collect()
}

fn real_index(rows: &[OrderedRow]) -> BTreeMap<Vec<u8>, usize> {
    rows.iter()
        .enumerate()
        .filter_map(|(index, row)| row.stable_key.as_ref().map(|key| (key.clone(), index)))
        .collect()
}

fn standard_record(
    table_name: &str,
    kind: &str,
    row: &OrderedRow,
    current_columns: Option<&[String]>,
    before_columns: Option<&[String]>,
    changed_columns: Vec<String>,
    diagnostics: Vec<String>,
) -> StandardRecord {
    let before_values = before_columns.map_or_else(Vec::new, |columns| values(row, columns));
    let current_values = current_columns.map_or_else(Vec::new, |columns| values(row, columns));
    StandardRecord {
        table_name: table_name.to_string(),
        record_kind: kind.to_string(),
        row_identity: row.stable_identity.clone(),
        changed_columns,
        before_values,
        current_values,
        field_changes: Vec::new(),
        diagnostics,
    }
}

struct OrderedRecordSpec<'a> {
    table_name: &'a str,
    record_kind: &'a str,
    semantic_kind: &'a str,
    row_identity: Option<&'a str>,
    before_position: Option<i64>,
    current_position: Option<i64>,
    changed_columns: Vec<String>,
    before_values: Vec<CanonicalValue>,
    current_values: Vec<CanonicalValue>,
}

fn ordered_record(spec: OrderedRecordSpec<'_>) -> Result<OrderedRecord, OrderedCompareError> {
    Ok(OrderedRecord {
        table_name: spec.table_name.to_string(),
        record_kind: spec.record_kind.to_string(),
        semantic_kind: spec.semantic_kind.to_string(),
        entity_key_kind: "REAL_STABLE".to_string(),
        row_identity: spec
            .row_identity
            .ok_or_else(|| OrderedCompareError::new("ROW_IDENTITY_MISSING"))?
            .to_string(),
        before_position: spec.before_position,
        current_position: spec.current_position,
        changed_columns: spec.changed_columns,
        before_values: spec.before_values,
        current_values: spec.current_values,
        diagnostics: Vec::new(),
    })
}

fn values(row: &OrderedRow, columns: &[String]) -> Vec<CanonicalValue> {
    columns
        .iter()
        .filter_map(|column| {
            row.cells
                .get(column)
                .map(|cell| cell.canonical_value(column))
        })
        .collect()
}

fn column_names(batch: Option<&RecordBatch>) -> Result<Vec<String>, OrderedCompareError> {
    let Some(batch) = batch else {
        return Ok(Vec::new());
    };
    if batch.num_columns() > MAX_ORDERED_COLUMNS {
        return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
    }
    let mut names = Vec::with_capacity(batch.num_columns());
    let mut seen = HashSet::with_capacity(batch.num_columns());
    for field in batch.schema().fields() {
        let name = canonicalize_identifier(field.name())
            .map_err(|_| OrderedCompareError::new("COLUMN_NAME_INVALID"))?;
        if !seen.insert(name.clone()) {
            return Err(OrderedCompareError::new("COLUMN_NAME_DUPLICATE"));
        }
        names.push(name);
    }
    names.sort();
    Ok(names)
}

fn read_side(
    batch: Option<&RecordBatch>,
    selected: &[String],
    blank_provenance: BlankProvenance,
    max_rows: usize,
) -> Result<SideRows, OrderedCompareError> {
    let Some(batch) = batch else {
        return Ok(SideRows { rows: Vec::new() });
    };
    if batch.num_rows() > max_rows {
        return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
    }
    let fields = batch.schema();
    let mut indices = HashMap::<String, usize>::with_capacity(fields.fields().len());
    for (index, field) in fields.fields().iter().enumerate() {
        let name = canonicalize_identifier(field.name())
            .map_err(|_| OrderedCompareError::new("COLUMN_NAME_INVALID"))?;
        indices.insert(name, index);
    }
    let gid_index = *indices
        .get("gid")
        .ok_or_else(|| OrderedCompareError::new("ROW_IDENTITY_MISSING"))?;
    let no_index = *indices
        .get("no")
        .ok_or_else(|| OrderedCompareError::new("ORDER_KEY_MISSING"))?;
    let mut rows = Vec::with_capacity(batch.num_rows());
    let mut positions = HashSet::with_capacity(batch.num_rows());
    let mut identities = HashSet::with_capacity(batch.num_rows());
    let mut total_encoded_bytes = 0usize;
    let mut value_columns = selected.to_vec();
    if !value_columns.iter().any(|name| name == "gid") {
        value_columns.push("gid".to_string());
    }
    if !value_columns.iter().any(|name| name == "no") {
        value_columns.push("no".to_string());
    }
    value_columns.sort();

    for row_index in 0..batch.num_rows() {
        let no_array = batch.column(no_index);
        let position = read_integer(no_array.as_ref(), row_index)?
            .ok_or_else(|| OrderedCompareError::new("ORDER_KEY_MISSING"))?;
        let position =
            i64::try_from(position).map_err(|_| OrderedCompareError::new("ORDER_KEY_INVALID"))?;
        if position < 1 {
            return Err(OrderedCompareError::new("ORDER_KEY_MISSING"));
        }
        if !positions.insert(position) {
            return Err(OrderedCompareError::new("ORDER_KEY_DUPLICATE"));
        }

        let gid_array = batch.column(gid_index);
        let gid = read_integer(gid_array.as_ref(), row_index)?;
        let blank = match (blank_provenance, gid) {
            (BlankProvenance::SourceMissingStableKey, None | Some(0)) => true,
            (BlankProvenance::SourceMissingStableKey, Some(value))
                if (GID_REAL_MIN..=GID_REAL_MAX).contains(&value) =>
            {
                false
            }
            (BlankProvenance::SourceMissingStableKey, Some(value))
                if (GID_PSEUDO_MIN..=GID_PSEUDO_MAX).contains(&value) =>
            {
                return Err(OrderedCompareError::new("SOURCE_RESERVED_PSEUDO_GID"));
            }
            (BlankProvenance::CanonicalPseudoGid, Some(value))
                if (GID_PSEUDO_MIN..=GID_PSEUDO_MAX).contains(&value) =>
            {
                true
            }
            (BlankProvenance::CanonicalPseudoGid, Some(value))
                if (GID_REAL_MIN..=GID_REAL_MAX).contains(&value) =>
            {
                false
            }
            (BlankProvenance::CanonicalPseudoGid, None | Some(0)) => {
                return Err(OrderedCompareError::new(
                    "CANONICAL_BLANK_PROVENANCE_INVALID",
                ));
            }
            (BlankProvenance::Missing, _) => {
                return Err(OrderedCompareError::new("BLANK_PROVENANCE_MISSING"));
            }
            (_, Some(_)) => return Err(OrderedCompareError::new("SOURCE_GID_INVALID")),
        };

        let mut cells = BTreeMap::new();
        for column in &value_columns {
            let index = *indices
                .get(column)
                .ok_or_else(|| OrderedCompareError::new("ROW_SHAPE_MISMATCH"))?;
            let field = fields.field(index);
            let cell = encode_cell(batch.column(index).as_ref(), row_index, field)?;
            if cell.frame.len() > MAX_ORDERED_CELL_BYTES.saturating_add(16) {
                return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
            }
            total_encoded_bytes = total_encoded_bytes
                .checked_add(cell.frame.len())
                .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
            if total_encoded_bytes > MAX_ORDERED_TOTAL_ENCODED_BYTES {
                return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
            }
            cells.insert(column.clone(), cell);
        }
        let gid_cell = cells
            .get("gid")
            .ok_or_else(|| OrderedCompareError::new("ROW_IDENTITY_MISSING"))?;
        let (stable_key, stable_identity) = if blank {
            (None, None)
        } else {
            if !identities.insert(gid_cell.frame.clone()) {
                return Err(OrderedCompareError::new("ROW_IDENTITY_DUPLICATE"));
            }
            let mut row_frame = vec![1, 3, b'g', b'i', b'd'];
            row_frame.extend_from_slice(&gid_cell.frame);
            let digest = semantic_digest(DigestKind::Row, &row_frame)
                .map_err(|_| OrderedCompareError::new("DIGEST_FAILED"))?;
            (
                Some(gid_cell.frame.clone()),
                Some(digest.digest_ref().as_str().to_string()),
            )
        };
        rows.push(OrderedRow {
            position,
            stable_key,
            stable_identity,
            blank,
            cells,
        });
    }
    rows.sort_by_key(|row| row.position);
    Ok(SideRows { rows })
}

fn read_integer(array: &dyn Array, row: usize) -> Result<Option<i128>, OrderedCompareError> {
    if array.is_null(row) {
        return Ok(None);
    }
    let value = if let Some(values) = array.as_any().downcast_ref::<StringArray>() {
        let text = values.value(row);
        if text.is_empty() {
            return Ok(None);
        }
        text.parse::<i128>()
            .map_err(|_| OrderedCompareError::new("ORDERED_INTEGER_INVALID"))?
    } else if let Some(values) = array.as_any().downcast_ref::<LargeStringArray>() {
        let text = values.value(row);
        if text.is_empty() {
            return Ok(None);
        }
        text.parse::<i128>()
            .map_err(|_| OrderedCompareError::new("ORDERED_INTEGER_INVALID"))?
    } else if let Some(values) = array.as_any().downcast_ref::<Int8Array>() {
        i128::from(values.value(row))
    } else if let Some(values) = array.as_any().downcast_ref::<Int16Array>() {
        i128::from(values.value(row))
    } else if let Some(values) = array.as_any().downcast_ref::<Int32Array>() {
        i128::from(values.value(row))
    } else if let Some(values) = array.as_any().downcast_ref::<Int64Array>() {
        i128::from(values.value(row))
    } else if let Some(values) = array.as_any().downcast_ref::<UInt8Array>() {
        i128::from(values.value(row))
    } else if let Some(values) = array.as_any().downcast_ref::<UInt16Array>() {
        i128::from(values.value(row))
    } else if let Some(values) = array.as_any().downcast_ref::<UInt32Array>() {
        i128::from(values.value(row))
    } else if let Some(values) = array.as_any().downcast_ref::<UInt64Array>() {
        i128::from(values.value(row))
    } else {
        return Err(OrderedCompareError::new("ORDERED_INTEGER_INVALID"));
    };
    Ok(Some(value))
}

fn encode_cell(
    array: &dyn Array,
    row: usize,
    field: &Field,
) -> Result<EncodedCell, OrderedCompareError> {
    if array.is_null(row) {
        return scalar_frame(DeclaredType::null(), TypedScalar::Null(NullScalar));
    }
    let spelling = scalar_type(field);
    if spelling
        .trim_start()
        .to_ascii_lowercase()
        .starts_with("set(")
    {
        return encode_set(array, row);
    }
    let declared = declared_type(&spelling, field.data_type())?;
    let typed = typed_value(array, row, &declared)?;
    scalar_frame(declared, typed)
}

fn scalar_frame(
    declared: DeclaredType,
    typed: TypedScalar,
) -> Result<EncodedCell, OrderedCompareError> {
    let encoded = encode_typed_scalar(&declared, &typed)
        .map_err(|_| OrderedCompareError::new("SCALAR_TYPE_MISMATCH"))?;
    Ok(EncodedCell {
        frame: encoded.scalar_frame,
    })
}

fn scalar_type(field: &Field) -> String {
    field
        .metadata()
        .get("gdms.scalar_type")
        .cloned()
        .unwrap_or_else(|| format!("{:?}", field.data_type()))
}

fn declared_type(
    spelling: &str,
    data_type: &DataType,
) -> Result<DeclaredType, OrderedCompareError> {
    let normalized = spelling.trim().to_ascii_lowercase();
    let base = normalized
        .split(|character: char| !character.is_ascii_alphanumeric())
        .find(|part| !part.is_empty())
        .unwrap_or_default();
    let unsigned = normalized.contains("unsigned") || normalized.contains("zerofill");
    let integer_bits = match base {
        "tinyint" => Some(8),
        "smallint" => Some(16),
        "mediumint" => Some(24),
        "int" | "integer" => Some(32),
        "bigint" => Some(64),
        _ => None,
    };
    if let Some(bits) = integer_bits {
        return if unsigned {
            DeclaredType::unsigned_integer(bits)
                .map_err(|_| OrderedCompareError::new("SCALAR_TYPE_UNKNOWN"))
        } else {
            DeclaredType::signed_integer(bits)
                .map_err(|_| OrderedCompareError::new("SCALAR_TYPE_UNKNOWN"))
        };
    }
    match base {
        "bool" | "boolean" => Ok(DeclaredType::boolean()),
        "float" => Ok(DeclaredType::float32()),
        "double" | "real" => Ok(DeclaredType::float64()),
        "decimal" | "numeric" => {
            let (precision, scale) = numeric_parameters(&normalized).unwrap_or((10, 0));
            DeclaredType::decimal(precision, scale)
                .map_err(|_| OrderedCompareError::new("SCALAR_TYPE_UNKNOWN"))
        }
        "bit" => {
            let (width, _) = numeric_parameters(&normalized).unwrap_or((1, 0));
            DeclaredType::bit(width).map_err(|_| OrderedCompareError::new("SCALAR_TYPE_UNKNOWN"))
        }
        "binary" | "varbinary" | "tinyblob" | "blob" | "mediumblob" | "longblob" => {
            Ok(DeclaredType::binary())
        }
        "date" => Ok(DeclaredType::date()),
        "datetime" => Ok(DeclaredType::datetime()),
        "timestamp" => Ok(DeclaredType::timestamp()),
        "time" => Ok(DeclaredType::time_duration()),
        _ => match data_type {
            DataType::Boolean => Ok(DeclaredType::boolean()),
            DataType::Binary | DataType::LargeBinary | DataType::FixedSizeBinary(_) => {
                Ok(DeclaredType::binary())
            }
            DataType::Float32 => Ok(DeclaredType::float32()),
            DataType::Float64 => Ok(DeclaredType::float64()),
            DataType::Int8 | DataType::Int16 | DataType::Int32 | DataType::Int64 => {
                let bits = match data_type {
                    DataType::Int8 => 8,
                    DataType::Int16 => 16,
                    DataType::Int32 => 32,
                    _ => 64,
                };
                DeclaredType::signed_integer(bits)
                    .map_err(|_| OrderedCompareError::new("SCALAR_TYPE_UNKNOWN"))
            }
            DataType::UInt8 | DataType::UInt16 | DataType::UInt32 | DataType::UInt64 => {
                let bits = match data_type {
                    DataType::UInt8 => 8,
                    DataType::UInt16 => 16,
                    DataType::UInt32 => 32,
                    _ => 64,
                };
                DeclaredType::unsigned_integer(bits)
                    .map_err(|_| OrderedCompareError::new("SCALAR_TYPE_UNKNOWN"))
            }
            _ => Ok(DeclaredType::string()),
        },
    }
}

fn numeric_parameters(spelling: &str) -> Option<(u8, u8)> {
    let start = spelling.find('(')? + 1;
    let end = spelling[start..].find(')')? + start;
    let parts: Vec<&str> = spelling[start..end].split(',').map(str::trim).collect();
    let first = parts.first()?.parse::<u8>().ok()?;
    let second = if let Some(text) = parts.get(1) {
        text.parse::<u8>().ok()?
    } else {
        0
    };
    Some((first, second))
}

fn typed_value(
    array: &dyn Array,
    row: usize,
    declared: &DeclaredType,
) -> Result<TypedScalar, OrderedCompareError> {
    match declared {
        DeclaredType::Null => Ok(TypedScalar::Null(NullScalar)),
        DeclaredType::Boolean => {
            let value = if let Some(values) = array.as_any().downcast_ref::<BooleanArray>() {
                values.value(row)
            } else {
                match cell_text(array, row)?.as_str() {
                    "true" | "1" => true,
                    "false" | "0" => false,
                    _ => return Err(OrderedCompareError::new("SCALAR_TYPE_MISMATCH")),
                }
            };
            Ok(TypedScalar::Boolean(BooleanScalar { value }))
        }
        DeclaredType::SignedInteger { .. } => Ok(TypedScalar::SignedInteger(SignedIntegerScalar {
            decimal: integer_text(array, row)?,
        })),
        DeclaredType::UnsignedInteger { .. } => {
            Ok(TypedScalar::UnsignedInteger(UnsignedIntegerScalar {
                decimal: integer_text(array, row)?,
            }))
        }
        DeclaredType::Decimal { scale, .. } => Ok(TypedScalar::Decimal(DecimalScalar {
            decimal: decimal_text(array, row, *scale)?,
        })),
        DeclaredType::Float32 => {
            let bits_hex = if let Some(values) = array.as_any().downcast_ref::<Float32Array>() {
                format!("{:08x}", values.value(row).to_bits())
            } else {
                cell_text(array, row)?
            };
            Ok(TypedScalar::Float32(Float32Scalar { bits_hex }))
        }
        DeclaredType::Float64 => {
            let bits_hex = if let Some(values) = array.as_any().downcast_ref::<Float64Array>() {
                format!("{:016x}", values.value(row).to_bits())
            } else {
                cell_text(array, row)?
            };
            Ok(TypedScalar::Float64(Float64Scalar { bits_hex }))
        }
        DeclaredType::String => Ok(TypedScalar::String(StringScalar {
            text: cell_text(array, row)?,
        })),
        DeclaredType::Binary => Ok(TypedScalar::Binary(BinaryScalar {
            raw_bytes: binary_value(array, row)?,
        })),
        DeclaredType::Bit { .. } => Ok(TypedScalar::Bit(BitScalar {
            raw_bytes: binary_value(array, row)?,
        })),
        DeclaredType::Date => Ok(TypedScalar::Date(DateScalar {
            text: cell_text(array, row)?,
        })),
        DeclaredType::DateTime => Ok(TypedScalar::DateTime(DateTimeScalar {
            text: cell_text(array, row)?,
        })),
        DeclaredType::Timestamp => Ok(TypedScalar::Timestamp(TimestampScalar {
            text: cell_text(array, row)?,
        })),
        DeclaredType::TimeDuration => Ok(TypedScalar::TimeDuration(TimeDurationScalar {
            text: cell_text(array, row)?,
        })),
        DeclaredType::SourceLiteralAnomaly => Err(OrderedCompareError::new("SCALAR_TYPE_UNKNOWN")),
    }
}

fn integer_text(array: &dyn Array, row: usize) -> Result<String, OrderedCompareError> {
    let value = read_integer(array, row)?
        .ok_or_else(|| OrderedCompareError::new("ORDERED_INTEGER_INVALID"))?;
    Ok(value.to_string())
}

fn cell_text(array: &dyn Array, row: usize) -> Result<String, OrderedCompareError> {
    if let Some(values) = array.as_any().downcast_ref::<StringArray>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<LargeStringArray>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<Int8Array>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<Int16Array>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<Int32Array>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<Int64Array>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<UInt8Array>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<UInt16Array>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<UInt32Array>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<UInt64Array>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<BooleanArray>() {
        return Ok(values.value(row).to_string());
    }
    if let Some(values) = array.as_any().downcast_ref::<Float32Array>() {
        return Ok(format!("{:08x}", values.value(row).to_bits()));
    }
    if let Some(values) = array.as_any().downcast_ref::<Float64Array>() {
        return Ok(format!("{:016x}", values.value(row).to_bits()));
    }
    Err(OrderedCompareError::new("SCALAR_VALUE_INVALID"))
}

fn decimal_text(array: &dyn Array, row: usize, scale: u8) -> Result<String, OrderedCompareError> {
    if let Some(values) = array.as_any().downcast_ref::<Decimal128Array>() {
        return Ok(scaled_integer(values.value(row).to_string(), scale));
    }
    if let Some(values) = array.as_any().downcast_ref::<Decimal256Array>() {
        return Ok(scaled_integer(values.value(row).to_string(), scale));
    }
    cell_text(array, row)
}

fn scaled_integer(mut integer: String, scale: u8) -> String {
    if scale == 0 {
        return integer;
    }
    let negative = integer.starts_with('-');
    if negative {
        integer.remove(0);
    }
    let scale = usize::from(scale);
    if integer.len() <= scale {
        let padding = "0".repeat(scale + 1 - integer.len());
        integer = format!("{padding}{integer}");
    }
    let split = integer.len() - scale;
    let fraction = integer.split_off(split);
    if negative {
        format!("-{integer}.{fraction}")
    } else {
        format!("{integer}.{fraction}")
    }
}

fn binary_value(array: &dyn Array, row: usize) -> Result<Vec<u8>, OrderedCompareError> {
    if let Some(values) = array.as_any().downcast_ref::<BinaryArray>() {
        return Ok(values.value(row).to_vec());
    }
    if let Some(values) = array.as_any().downcast_ref::<LargeBinaryArray>() {
        return Ok(values.value(row).to_vec());
    }
    if let Some(values) = array.as_any().downcast_ref::<FixedSizeBinaryArray>() {
        return Ok(values.value(row).to_vec());
    }
    Err(OrderedCompareError::new("SCALAR_VALUE_INVALID"))
}

fn encode_set(array: &dyn Array, row: usize) -> Result<EncodedCell, OrderedCompareError> {
    let list = array
        .as_any()
        .downcast_ref::<ListArray>()
        .ok_or_else(|| OrderedCompareError::new("SET_VALUE_INVALID"))?;
    let values = list.value(row);
    let mut encoded_items = Vec::with_capacity(values.len());
    for index in 0..values.len() {
        if values.is_null(index) {
            return Err(OrderedCompareError::new("SET_VALUE_INVALID"));
        }
        let text = if let Some(strings) = values.as_any().downcast_ref::<StringArray>() {
            strings.value(index).to_string()
        } else if let Some(strings) = values.as_any().downcast_ref::<LargeStringArray>() {
            strings.value(index).to_string()
        } else {
            return Err(OrderedCompareError::new("SET_VALUE_INVALID"));
        };
        let item = encode_typed_scalar(
            &DeclaredType::string(),
            &TypedScalar::String(StringScalar { text }),
        )
        .map_err(|_| OrderedCompareError::new("SET_VALUE_INVALID"))?;
        encoded_items.push(item.scalar_frame);
    }
    let slices: Vec<&[u8]> = encoded_items.iter().map(Vec::as_slice).collect();
    let encoded = encode_collection(CollectionSemantics::Sequence, Some(&slices), None)
        .map_err(|_| OrderedCompareError::new("SET_VALUE_INVALID"))?;
    Ok(EncodedCell {
        frame: encoded.collection_frame,
    })
}

fn longest_increasing_backbone(positions: &[i64]) -> Vec<usize> {
    if positions.is_empty() {
        return Vec::new();
    }
    let mut reach = vec![0usize; positions.len()];
    let mut tails = Vec::<i64>::new();
    for index in (0..positions.len()).rev() {
        let value = -positions[index];
        let slot = tails.partition_point(|tail| *tail < value);
        if slot == tails.len() {
            tails.push(value);
        } else if let Some(tail) = tails.get_mut(slot) {
            *tail = value;
        }
        reach[index] = slot + 1;
    }
    let longest = reach.iter().copied().max().unwrap_or_default();
    let mut levels = vec![Vec::<usize>::new(); longest.saturating_add(1)];
    for (index, length) in reach.iter().copied().enumerate() {
        if let Some(level) = levels.get_mut(length) {
            level.push(index);
        }
    }
    let mut chosen = Vec::with_capacity(longest);
    let mut previous = None;
    for length in (1..=longest).rev() {
        let Some(candidates) = levels.get(length) else {
            break;
        };
        let slot =
            candidates.partition_point(|index| previous.is_some_and(|prior| *index <= prior));
        let Some(pick) = candidates.get(slot).copied() else {
            break;
        };
        chosen.push(pick);
        previous = Some(pick);
    }
    chosen
}

fn ordered_digest(
    rows: &[OrderedRow],
    table_name: &str,
    policy_version: &str,
    value_columns: &[String],
) -> Result<String, OrderedCompareError> {
    let mut output_rows = Vec::with_capacity(rows.len());
    for row in rows {
        let content = if row.blank {
            None
        } else {
            let mut frame = Vec::new();
            for column in value_columns {
                if let Some(cell) = row.cells.get(column) {
                    frame.extend_from_slice(&cell.frame);
                }
            }
            let digest = semantic_digest(DigestKind::Row, &frame)
                .map_err(|_| OrderedCompareError::new("DIGEST_FAILED"))?;
            Some(digest.digest_ref().as_str().to_string())
        };
        output_rows.push(json!({
            "stable": row.stable_identity.as_deref(),
            "position": row.position,
            "blank": row.blank,
            "content": content,
        }));
    }
    let payload = json!({
        "kind": "ordered-logical-digest",
        "contract_version": policy_version,
        "table_name": table_name,
        "rows": output_rows,
    });
    raw_digest_json(&payload)
}

fn blank_extension(
    table_name: &str,
    before_rows: &[OrderedRow],
    current_rows: &[OrderedRow],
    backbone: &HashSet<Vec<u8>>,
    include_records: bool,
) -> Result<BlankExtensionWork, OrderedCompareError> {
    let before_gaps = blank_gaps(before_rows, Some(backbone));
    let current_gaps = blank_gaps(current_rows, Some(backbone));
    let mut keys: BTreeSet<(Option<String>, Option<String>)> =
        before_gaps.keys().cloned().collect();
    keys.extend(current_gaps.keys().cloned());
    let mut records = Vec::new();
    let mut inserted_count = 0usize;
    let mut deleted_count = 0usize;
    for key in keys {
        let before_gap = before_gaps.get(&key).copied();
        let current_gap = current_gaps.get(&key).copied();
        let before_count = before_gap.map_or(0, |gap| gap.count);
        let current_count = current_gap.map_or(0, |gap| gap.count);
        if before_count == current_count {
            continue;
        }
        let selected_count = current_gap.map_or(before_count, |gap| gap.count);
        let interval = BlankInterval {
            before_start: before_gap.map(|gap| gap.start),
            before_end: before_gap.map(|gap| gap.end),
            current_start: current_gap.map(|gap| gap.start),
            current_end: current_gap.map(|gap| gap.end),
            row_count: current_count.abs_diff(before_count),
            interval_digest: interval_digest(&key, selected_count)?,
        };
        if before_count > current_count {
            deleted_count += 1;
            if include_records {
                records.push(BlankRecord {
                    table_name: table_name.to_string(),
                    record_kind: "BLANK_DELETE_INTERVAL".to_string(),
                    semantic_kind: "BLANK_DELETE_INTERVAL".to_string(),
                    entity_key_kind: "PSEUDO_BLANK".to_string(),
                    interval,
                    before_occupancy: before_count,
                    current_occupancy: current_count,
                    diagnostics: Vec::new(),
                });
            }
        } else {
            inserted_count += 1;
            if include_records {
                records.push(BlankRecord {
                    table_name: table_name.to_string(),
                    record_kind: "BLANK_INSERT_INTERVAL".to_string(),
                    semantic_kind: "BLANK_INSERT_INTERVAL".to_string(),
                    entity_key_kind: "PSEUDO_BLANK".to_string(),
                    interval,
                    before_occupancy: before_count,
                    current_occupancy: current_count,
                    diagnostics: Vec::new(),
                });
            }
        }
    }
    let before_occupancy = blank_gaps(before_rows, None);
    let current_occupancy = blank_gaps(current_rows, None);
    Ok(BlankExtensionWork {
        summary: BlankSummary {
            interval_inserted_count: inserted_count,
            interval_deleted_count: deleted_count,
            blank_changed_count: inserted_count + deleted_count,
            degraded_count: 0,
        },
        before_digest: occupancy_digest(&before_occupancy)?,
        current_digest: occupancy_digest(&current_occupancy)?,
        records,
    })
}

struct BlankExtensionWork {
    summary: BlankSummary,
    before_digest: String,
    current_digest: String,
    records: Vec<BlankRecord>,
}

fn blank_gaps(
    rows: &[OrderedRow],
    anchors: Option<&HashSet<Vec<u8>>>,
) -> BTreeMap<(Option<String>, Option<String>), Gap> {
    let mut gaps = BTreeMap::new();
    let mut before_anchor: Option<String> = None;
    let mut count = 0usize;
    let mut start = 0i64;
    let mut end = 0i64;
    for row in rows {
        if row.blank {
            if count == 0 {
                start = row.position;
            }
            count += 1;
            end = row.position;
            continue;
        }
        let stable_key = row.stable_key.as_ref();
        let is_anchor = anchors.is_none_or(|set| stable_key.is_some_and(|key| set.contains(key)));
        if !is_anchor {
            continue;
        }
        let after_anchor = row.stable_identity.clone();
        if count > 0 {
            gaps.insert(
                (before_anchor.clone(), after_anchor.clone()),
                Gap { count, start, end },
            );
        }
        before_anchor = after_anchor;
        count = 0;
    }
    if count > 0 {
        gaps.insert((before_anchor, None), Gap { count, start, end });
    }
    gaps
}

fn interval_digest(
    key: &(Option<String>, Option<String>),
    count: usize,
) -> Result<String, OrderedCompareError> {
    raw_digest_json(&json!({
        "before": key.0.as_deref(),
        "after": key.1.as_deref(),
        "count": count,
    }))
}

fn occupancy_digest(
    gaps: &BTreeMap<(Option<String>, Option<String>), Gap>,
) -> Result<String, OrderedCompareError> {
    let payload: Vec<Value> = gaps
        .iter()
        .map(|(key, gap)| {
            json!({
                "before": key.0.as_deref(),
                "after": key.1.as_deref(),
                "count": gap.count,
            })
        })
        .collect();
    raw_digest_json(&Value::Array(payload))
}

fn raw_digest_json(value: &Value) -> Result<String, OrderedCompareError> {
    let encoded = serde_json::to_vec(value)
        .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
    let canonical = canonicalize_jcs(&encoded)
        .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
    let digest =
        raw_blob_digest(&canonical).map_err(|_| OrderedCompareError::new("DIGEST_FAILED"))?;
    Ok(digest.as_str().to_string())
}

fn hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len().saturating_mul(2));
    for byte in bytes {
        output.push(char::from(HEX[usize::from(byte >> 4)]));
        output.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    output
}

#[cfg(test)]
mod tests;
