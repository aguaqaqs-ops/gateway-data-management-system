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
    LargeStringArray, RecordBatch, StringArray, UInt8Array, UInt16Array, UInt32Array, UInt64Array,
};
use arrow_schema::{DataType, Field, SchemaRef};
use gateway_shared_kernel::{
    BinaryScalar, BitScalar, BooleanScalar, CollectionSemantics, DateScalar, DateTimeScalar,
    DecimalScalar, DeclaredType, DigestKind, Float32Scalar, Float64Scalar, NullScalar,
    SignedIntegerScalar, StringScalar, TimeDurationScalar, TimestampScalar, TypedScalar,
    UnsignedIntegerScalar, canonicalize_identifier, canonicalize_jcs, encode_collection,
    encode_typed_scalar, encode_uleb128, raw_blob_digest, semantic_digest,
};
use rayon::ThreadPool;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::sync::Arc;

use super::kernel::{
    CanonicalBatchSide, KernelContext, KernelLease, sort_indices_checked,
    validate_canonical_batches,
};
use super::standard::{RowLocation, StandardKind, StandardRecordRef};

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
    /// A's COLUMNS_ADDED evolution: compare the shared full row multiset for
    /// ignored content instead of interpreting a newly added column as change.
    pub columns_added: bool,
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
            columns_added: false,
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

#[derive(Clone)]
pub struct OrderedBatchPair<'a> {
    pub before: Option<&'a [RecordBatch]>,
    pub current: Option<&'a [RecordBatch]>,
    pub before_schema: Option<SchemaRef>,
    pub current_schema: Option<SchemaRef>,
    pub options: &'a OrderedCompareOptions,
}

pub struct OrderedKernelResult {
    /// Metadata only: row record payloads live in the three locator vectors.
    /// Consumers must replay locators plus retained Arrow cells for full facts.
    pub facts_metadata: OrderedCompareResult,
    /// Keeps canonical Arrow input owners valid for later C batch builders.
    pub before_batches: Vec<RecordBatch>,
    pub current_batches: Vec<RecordBatch>,
    pub before_schema: Option<SchemaRef>,
    pub current_schema: Option<SchemaRef>,
    pub standard_records: Vec<StandardRecordRef>,
    pub ordered_records: Vec<OrderedRecordRef>,
    pub blank_records: Vec<BlankRecordRef>,
    pub standard_facts_order: Vec<usize>,
    pub standard_artifact_order: Vec<usize>,
    pub ordered_facts_order: Vec<usize>,
    pub ordered_artifact_order: Vec<usize>,
    pub blank_facts_order: Vec<usize>,
    pub blank_artifact_order: Vec<usize>,
    _lease: KernelLease,
}

#[derive(Debug, Clone)]
pub struct OrderedRecordRef {
    pub kind: &'static str,
    pub semantic_kind: &'static str,
    pub entity_key_kind: &'static str,
    pub row_identity: String,
    pub before_position: Option<i64>,
    pub current_position: Option<i64>,
    pub before: Option<RowLocation>,
    pub current: Option<RowLocation>,
    pub value_columns: Vec<String>,
    pub changed_columns: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct BlankRecordRef {
    pub kind: &'static str,
    pub semantic_kind: &'static str,
    /// Private facts field; C must not emit it in BLANK Parquet.
    pub entity_key_kind: &'static str,
    pub interval: BlankInterval,
    pub before_occupancy: usize,
    pub current_occupancy: usize,
}

#[derive(Default)]
struct OrderedLocatorRecords {
    standard: Vec<StandardRecordRef>,
    ordered: Vec<OrderedRecordRef>,
    blank: Vec<BlankRecordRef>,
}

struct OrderedWork {
    facts: OrderedCompareResult,
    locators: OrderedLocatorRecords,
}

/// The planner has already proved both sides share the complete content and
/// schema identity. Only the current side is opened for these two digests.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnchangedOrderedSummary {
    pub before_ordered_digest: String,
    pub current_ordered_digest: String,
    pub before_occupancy_digest: String,
    pub current_occupancy_digest: String,
    pub row_count: usize,
}

pub fn summarize_unchanged_ordered_side(
    current: &RecordBatch,
    options: &OrderedCompareOptions,
    context: &Arc<KernelContext>,
) -> Result<UnchangedOrderedSummary, OrderedCompareError> {
    summarize_unchanged_ordered_batches(
        CanonicalBatchSide::new(current.schema(), std::slice::from_ref(current)),
        options,
        context,
    )
}

pub fn summarize_unchanged_ordered_batches(
    current: CanonicalBatchSide<'_>,
    options: &OrderedCompareOptions,
    context: &Arc<KernelContext>,
) -> Result<UnchangedOrderedSummary, OrderedCompareError> {
    context.check()?;
    validate_canonical_batches(&current)?;
    if options.table_name.is_empty() || options.policy_version.is_empty() || options.max_rows == 0 {
        return Err(OrderedCompareError::new("ORDERED_POLICY_INVALID"));
    }
    if options.current_blank_provenance == BlankProvenance::Missing {
        return Err(OrderedCompareError::new("BLANK_PROVENANCE_MISSING"));
    }
    let selected = column_names_from_schema(&current.schema)?;
    if !selected.iter().any(|name| name == "gid") || !selected.iter().any(|name| name == "no") {
        return Err(OrderedCompareError::new("ORDERED_REQUIRED_COLUMN_MISSING"));
    }
    let input_bytes = current
        .batches
        .iter()
        .flat_map(RecordBatch::columns)
        .try_fold(0usize, |total, array| {
            let slice_bytes = array.to_data().get_slice_memory_size().ok()?;
            total.checked_add(slice_bytes)
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let row_count = current
        .batches
        .iter()
        .try_fold(0usize, |total, batch| total.checked_add(batch.num_rows()))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let row_overhead = row_count
        .checked_mul(selected.len().saturating_mul(80).saturating_add(512))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let reservation = input_bytes
        .checked_mul(3)
        .and_then(|size| size.checked_add(row_overhead))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let _lease = context.reserve(reservation)?;
    let side = read_side_batches(
        Some(current.batches),
        &selected,
        options.current_blank_provenance,
        options.max_rows,
        Some(context),
    )?;
    context.check()?;
    let digest_columns = resolved_digest_value_columns(options, &selected);
    let ordered = ordered_digest(
        &side.rows,
        &options.table_name,
        &options.policy_version,
        &digest_columns,
        Some(context),
    )?;
    context.check()?;
    let occupancy = occupancy_digest(&blank_gaps(&side.rows, None, Some(context))?, Some(context))?;
    Ok(UnchangedOrderedSummary {
        before_ordered_digest: ordered.clone(),
        current_ordered_digest: ordered,
        before_occupancy_digest: occupancy.clone(),
        current_occupancy_digest: occupancy,
        row_count,
    })
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OrderedCompareError {
    code: &'static str,
}

impl OrderedCompareError {
    pub(super) fn new(code: &'static str) -> Self {
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
    let batches = OrderedBatchPair {
        before: pair.before.map(std::slice::from_ref),
        current: pair.current.map(std::slice::from_ref),
        before_schema: pair.before.map(RecordBatch::schema),
        current_schema: pair.current.map(RecordBatch::schema),
        options: pair.options,
    };
    match std::panic::catch_unwind(AssertUnwindSafe(|| {
        compare_ordered_table_inner(&batches, None, None, false).map(|work| work.facts)
    })) {
        Ok(result) => result,
        Err(_) => Err(OrderedCompareError::new("ORDERED_INTERNAL_ERROR")),
    }
}

/// Production-oriented batch entry. It uses the caller's operation context
/// and rejects non-canonical Arrow metadata before looking at rows. The old
/// one-batch prototype above remains only for frozen differential fixtures.
pub fn compare_ordered_batches(
    pair: OrderedBatchPair<'_>,
    context: &Arc<KernelContext>,
) -> Result<OrderedKernelResult, OrderedCompareError> {
    match std::panic::catch_unwind(AssertUnwindSafe(|| {
        context.check()?;
        if pair.before.is_none() || pair.current.is_none() {
            return Err(OrderedCompareError::new("TABLE_LEVEL_SINGLE_SIDE_REQUIRED"));
        }
        let options = pair.options;
        let option_strings = std::iter::once(options.table_name.as_str())
            .chain(std::iter::once(options.policy_version.as_str()))
            .chain(options.policy_digest.iter().map(String::as_str))
            .chain(options.value_columns.iter().map(String::as_str))
            .chain(options.digest_value_columns.iter().map(String::as_str))
            .chain(options.compare_excluded_columns.iter().map(String::as_str))
            .chain(options.schema_changes.before_only_columns.iter().map(String::as_str))
            .chain(options.schema_changes.current_only_columns.iter().map(String::as_str))
            .chain(options.schema_changes.selected_columns.iter().map(String::as_str))
            .chain(options.schema_changes.effective_compare_key_before.iter().map(String::as_str))
            .chain(options.schema_changes.effective_compare_key_current.iter().map(String::as_str))
            .chain(options.schema_changes.incompatible_columns.iter().map(String::as_str))
            .chain(options.schema_changes.change_source.iter().map(String::as_str));
        let metadata_bytes = option_strings
            .try_fold(4096usize, |total, value| {
                total.checked_add(value.len().saturating_mul(8).saturating_add(128))
            })
            .and_then(|base| pair.before_schema.iter().chain(&pair.current_schema)
                .flat_map(|schema| schema.fields().iter())
                .try_fold(base, |total, field| {
                    let field_bytes = field.metadata().values()
                        .try_fold(field.name().len(), |size, value| size.checked_add(value.len()))?;
                    total.checked_add(field_bytes.saturating_mul(8).saturating_add(128))
                }))
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let metadata_lease = context.reserve(metadata_bytes)?;
        if let Some(before) = pair.before {
            let schema = pair
                .before_schema
                .as_ref()
                .ok_or_else(|| OrderedCompareError::new("CANONICAL_SCHEMA_REQUIRED"))?;
            validate_canonical_batches(&CanonicalBatchSide::new(Arc::clone(schema), before))?;
        }
        if let Some(current) = pair.current {
            let schema = pair
                .current_schema
                .as_ref()
                .ok_or_else(|| OrderedCompareError::new("CANONICAL_SCHEMA_REQUIRED"))?;
            validate_canonical_batches(&CanonicalBatchSide::new(Arc::clone(schema), current))?;
        }
        drop(metadata_lease);
        let mut batches = pair
            .before
            .into_iter()
            .flatten()
            .chain(pair.current.into_iter().flatten());
        let (input_bytes, rows, columns) = batches
            .try_fold((0usize, 0usize, 0usize), |(bytes, rows, columns), batch| {
                let bytes = batch.columns().iter().try_fold(bytes, |total, array| {
                    let slice_bytes = array.to_data().get_slice_memory_size().ok()?;
                    total.checked_add(slice_bytes)
                })?;
                Some((
                    bytes,
                    rows.checked_add(batch.num_rows())?,
                    columns.max(batch.num_columns()),
                ))
            })
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let frame_overhead = rows
            .checked_mul(columns.saturating_mul(32))
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        // The pinned Arrow backing is owned/charged by the caller. Local peak:
        // one encoded frame copy, one worst-case full-key/index copy, one
        // largest-row digest scratch allowance, plus row/LIS/gap structures.
        let encoded_frames = input_bytes
            .checked_add(frame_overhead)
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let index_keys = input_bytes
            .checked_add(rows.saturating_mul(128))
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let digest_scratch = input_bytes;
        let row_structures = rows
            .checked_mul(
                std::mem::size_of::<OrderedRow>()
                    .saturating_add(columns.saturating_mul(96))
                    .saturating_add(640),
            )
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let batch_count = pair
            .before
            .unwrap_or_default()
            .len()
            .checked_add(pair.current.unwrap_or_default().len())
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let batch_refs = batch_count
            .checked_mul(std::mem::size_of::<RecordBatch>() + 128)
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let reservation = encoded_frames
            .checked_add(index_keys)
            .and_then(|bytes| bytes.checked_add(digest_scratch))
            .and_then(|bytes| bytes.checked_add(row_structures))
            .and_then(|bytes| bytes.checked_add(batch_refs))
            .and_then(|bytes| bytes.checked_add(metadata_bytes))
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        let mut lease = context.reserve(reservation)?;
        let work = compare_ordered_table_inner(&pair, Some(context), Some(&mut lease), true)?;
        let standard_facts_order =
            sort_indices_checked(&work.locators.standard, context, |left, right| {
                left.kind
                    .contract_name()
                    .cmp(&right.kind.contract_name())
                    .then_with(|| left.row_identity.cmp(&right.row_identity))
                    .then_with(|| left.changed_columns.cmp(&right.changed_columns))
            })?;
        let standard_artifact_order = standard_facts_order.clone();
        let ordered_facts_order =
            sort_indices_checked(&work.locators.ordered, context, |left, right| {
                left.kind
                    .cmp(&right.kind)
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
            })?;
        let ordered_artifact_order =
            sort_indices_checked(&work.locators.ordered, context, |left, right| {
                left.kind
                    .cmp(&right.kind)
                    .then_with(|| left.row_identity.cmp(&right.row_identity))
                    .then_with(|| {
                        left.before_position
                            .unwrap_or_default()
                            .cmp(&right.before_position.unwrap_or_default())
                    })
                    .then_with(|| {
                        left.current_position
                            .unwrap_or_default()
                            .cmp(&right.current_position.unwrap_or_default())
                    })
            })?;
        let blank_facts_order: Vec<usize> = (0..work.locators.blank.len()).collect();
        let blank_keys = work
            .locators
            .blank
            .iter()
            .map(|record| blank_artifact_key(record, &pair.options.table_name))
            .collect::<Result<Vec<_>, _>>()?;
        let blank_artifact_order =
            sort_indices_checked(&blank_facts_order, context, |left, right| {
                let left = *left;
                let right = *right;
                work.locators.blank[left]
                    .kind
                    .cmp(&work.locators.blank[right].kind)
                    .then_with(|| blank_keys[left].cmp(&blank_keys[right]))
            })?;
        let OrderedWork { facts, locators } = work;
        let mut result = OrderedKernelResult {
            facts_metadata: facts,
            before_batches: pair.before.unwrap_or_default().to_vec(),
            current_batches: pair.current.unwrap_or_default().to_vec(),
            before_schema: pair.before_schema,
            current_schema: pair.current_schema,
            standard_records: locators.standard,
            ordered_records: locators.ordered,
            blank_records: locators.blank,
            standard_facts_order,
            standard_artifact_order,
            ordered_facts_order,
            ordered_artifact_order,
            blank_facts_order,
            blank_artifact_order,
            _lease: lease,
        };
        let retained = ordered_retained_bytes(&result)?;
        result._lease.shrink_to(retained)?;
        Ok(result)
    })) {
        Ok(result) => result,
        Err(_) => Err(OrderedCompareError::new("ORDERED_INTERNAL_ERROR")),
    }
}

fn ordered_retained_bytes(result: &OrderedKernelResult) -> Result<usize, OrderedCompareError> {
    // The preflight metadata reservation also covers this short temporary
    // serialization buffer before scratch is released. No row DTO is encoded.
    let facts_bytes = serde_json::to_vec(&result.facts_metadata)
        .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?
        .len();
    let batch_bytes = result
        .before_batches
        .capacity()
        .checked_add(result.current_batches.capacity())
        .and_then(|count| count.checked_mul(std::mem::size_of::<RecordBatch>()))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let record_headers = result
        .standard_records
        .capacity()
        .checked_mul(std::mem::size_of::<StandardRecordRef>())
        .and_then(|bytes| {
            result
                .ordered_records
                .capacity()
                .checked_mul(std::mem::size_of::<OrderedRecordRef>())
                .and_then(|part| bytes.checked_add(part))
        })
        .and_then(|bytes| {
            result
                .blank_records
                .capacity()
                .checked_mul(std::mem::size_of::<BlankRecordRef>())
                .and_then(|part| bytes.checked_add(part))
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let order_bytes = [
        result.standard_facts_order.capacity(),
        result.standard_artifact_order.capacity(),
        result.ordered_facts_order.capacity(),
        result.ordered_artifact_order.capacity(),
        result.blank_facts_order.capacity(),
        result.blank_artifact_order.capacity(),
    ]
    .into_iter()
    .try_fold(0usize, |total, count| {
        count
            .checked_mul(std::mem::size_of::<usize>())
            .and_then(|part| total.checked_add(part))
    })
    .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let standard_strings = result
        .standard_records
        .iter()
        .try_fold(0usize, |total, record| {
            record
                .value_columns
                .iter()
                .chain(&record.changed_columns)
                .chain(&record.diagnostics)
                .try_fold(
                    total.checked_add(record.row_identity.as_ref().map_or(0, String::capacity))?,
                    |sum, text| sum.checked_add(text.capacity()),
                )?
                .checked_add(
                    (record.value_columns.capacity()
                        + record.changed_columns.capacity()
                        + record.diagnostics.capacity())
                        * std::mem::size_of::<String>(),
                )
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let ordered_strings = result
        .ordered_records
        .iter()
        .try_fold(0usize, |total, record| {
            record
                .value_columns
                .iter()
                .chain(&record.changed_columns)
                .try_fold(
                    total.checked_add(record.row_identity.capacity())?,
                    |sum, text| sum.checked_add(text.capacity()),
                )?
                .checked_add(
                    (record.value_columns.capacity() + record.changed_columns.capacity())
                        * std::mem::size_of::<String>(),
                )
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    let blank_strings = result
        .blank_records
        .iter()
        .try_fold(0usize, |total, record| {
            total.checked_add(record.interval.interval_digest.capacity())
        })
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    facts_bytes
        .checked_mul(2)
        .and_then(|bytes| bytes.checked_add(batch_bytes))
        .and_then(|bytes| bytes.checked_add(record_headers))
        .and_then(|bytes| bytes.checked_add(order_bytes))
        .and_then(|bytes| bytes.checked_add(standard_strings))
        .and_then(|bytes| bytes.checked_add(ordered_strings))
        .and_then(|bytes| bytes.checked_add(blank_strings))
        .and_then(|bytes| bytes.checked_add(4096))
        .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))
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
pub(super) struct EncodedCell {
    pub(super) frame: Vec<u8>,
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
    location: RowLocation,
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
    pair: &OrderedBatchPair<'_>,
    context: Option<&KernelContext>,
    mut lease: Option<&mut KernelLease>,
    capture_locators: bool,
) -> Result<OrderedWork, OrderedCompareError> {
    let options = pair.options;
    if options.table_name.is_empty() || options.policy_version.is_empty() || options.max_rows == 0 {
        return Err(OrderedCompareError::new("ORDERED_POLICY_INVALID"));
    }
    if pair.before.is_none() && pair.current.is_none() {
        return Err(OrderedCompareError::new("TABLE_TASK_HAS_NO_SIDE"));
    }
    if pair.before.is_some() && options.before_blank_provenance == BlankProvenance::Missing {
        return Ok(degraded_result(pair, "BLANK_PROVENANCE_MISSING", capture_locators));
    }
    if pair.current.is_some() && options.current_blank_provenance == BlankProvenance::Missing {
        return Ok(degraded_result(pair, "BLANK_PROVENANCE_MISSING", capture_locators));
    }

    let before_columns = column_names_batches(pair.before_schema.as_ref(), pair.before)?;
    let current_columns = column_names_batches(pair.current_schema.as_ref(), pair.current)?;
    let selected = selected_columns(
        &before_columns,
        &current_columns,
        pair.before.is_some(),
        pair.current.is_some(),
    );
    if !selected.iter().any(|name| name == "gid") || !selected.iter().any(|name| name == "no") {
        return Ok(degraded_result(pair, "ORDERED_REQUIRED_COLUMN_MISSING", capture_locators));
    }
    if !options.schema_changes.incompatible_columns.is_empty() {
        return Ok(degraded_result(pair, "INCOMPATIBLE_SELECTED_COLUMNS", capture_locators));
    }
    let value_columns = resolved_value_columns(options, &selected);
    let digest_value_columns = resolved_digest_value_columns(options, &selected);
    let before = match read_side_batches(
        pair.before,
        &selected,
        options.before_blank_provenance,
        options.max_rows,
        context,
    ) {
        Ok(rows) => rows,
        Err(error) if is_control_or_resource(&error) => return Err(error),
        Err(error) => return Ok(degraded_result(pair, error.code(), capture_locators)),
    };
    let current = match read_side_batches(
        pair.current,
        &selected,
        options.current_blank_provenance,
        options.max_rows,
        context,
    ) {
        Ok(rows) => rows,
        Err(error) if is_control_or_resource(&error) => return Err(error),
        Err(error) => return Ok(degraded_result(pair, error.code(), capture_locators)),
    };

    let before_real = real_index(&before.rows, context)?;
    let current_real = real_index(&current.rows, context)?;
    check_context(context)?;
    let mut added_keys = Vec::new();
    for (index, key) in current_real.keys().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if !before_real.contains_key(key) {
            added_keys.push(key.clone());
        }
    }
    let mut deleted_keys = Vec::new();
    let mut common_keys = Vec::new();
    for (index, key) in before_real.keys().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if current_real.contains_key(key) {
            common_keys.push(key.clone());
        } else {
            deleted_keys.push(key.clone());
        }
    }

    let mut changed_by_key = BTreeMap::<Vec<u8>, Vec<String>>::new();
    for (index, key) in common_keys.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
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

    let mut common_keys_in_before_order = Vec::new();
    for (index, row) in before.rows.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if let Some(key) = row
            .stable_key
            .as_ref()
            .filter(|key| current_real.contains_key(*key))
        {
            common_keys_in_before_order.push(key.clone());
        }
    }
    let mut current_positions = Vec::with_capacity(common_keys_in_before_order.len());
    for (index, key) in common_keys_in_before_order.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        current_positions.push(current.rows[current_real[key]].position);
    }
    check_context(context)?;
    let backbone_indices = longest_increasing_backbone_with_control(&current_positions, context)?;
    let mut backbone = HashSet::new();
    for (index, pick) in backbone_indices.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if let Some(key) = common_keys_in_before_order.get(*pick) {
            backbone.insert(key.clone());
        }
    }
    let mut moved_keys = Vec::new();
    for (index, key) in common_keys.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if !backbone.contains(key) {
            moved_keys.push(key.clone());
        }
    }
    let mut position_changed_keys = HashSet::new();
    for (index, key) in backbone.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if before.rows[before_real[key]].position != current.rows[current_real[key]].position {
            position_changed_keys.insert(key.clone());
        }
    }

    let mut standard_records = Vec::new();
    let mut ordered_records = Vec::new();
    let mut locators = OrderedLocatorRecords::default();
    if options.include_add_delete_records {
        for (index, key) in added_keys.iter().enumerate() {
            if index % 1024 == 0 {
                check_context(context)?;
            }
            let row = &current.rows[current_real[key]];
            if capture_locators {
                reserve_locator(lease.as_deref_mut(), &selected, &value_columns)?;
                let identity = row
                    .stable_identity
                    .clone()
                    .ok_or_else(|| OrderedCompareError::new("ROW_IDENTITY_MISSING"))?;
                locators.standard.push(StandardRecordRef {
                    kind: StandardKind::RowAdded,
                    row_identity: Some(identity.clone()),
                    before: None,
                    current: Some(row.location),
                    value_columns: selected.clone(),
                    changed_columns: Vec::new(),
                    diagnostics: vec!["ORDERED_PROVIDER".to_string()],
                });
                locators.ordered.push(OrderedRecordRef {
                    kind: "ORDERED_ROW_ADDED",
                    semantic_kind: "DATA_INSERT",
                    entity_key_kind: "REAL_STABLE",
                    row_identity: identity,
                    before_position: None,
                    current_position: Some(row.position),
                    before: None,
                    current: Some(row.location),
                    value_columns: value_columns.clone(),
                    changed_columns: Vec::new(),
                });
            } else {
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
        }
        for (index, key) in deleted_keys.iter().enumerate() {
            if index % 1024 == 0 {
                check_context(context)?;
            }
            let row = &before.rows[before_real[key]];
            if capture_locators {
                reserve_locator(lease.as_deref_mut(), &selected, &value_columns)?;
                let identity = row
                    .stable_identity
                    .clone()
                    .ok_or_else(|| OrderedCompareError::new("ROW_IDENTITY_MISSING"))?;
                locators.standard.push(StandardRecordRef {
                    kind: StandardKind::RowDeleted,
                    row_identity: Some(identity.clone()),
                    before: Some(row.location),
                    current: None,
                    value_columns: selected.clone(),
                    changed_columns: Vec::new(),
                    diagnostics: vec!["ORDERED_PROVIDER".to_string()],
                });
                locators.ordered.push(OrderedRecordRef {
                    kind: "ORDERED_ROW_DELETED",
                    semantic_kind: "DATA_DELETE",
                    entity_key_kind: "REAL_STABLE",
                    row_identity: identity,
                    before_position: Some(row.position),
                    current_position: None,
                    before: Some(row.location),
                    current: None,
                    value_columns: value_columns.clone(),
                    changed_columns: Vec::new(),
                });
            } else {
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
    }

    for (index, (key, changed_columns)) in changed_by_key.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        let before_row = &before.rows[before_real[key]];
        let current_row = &current.rows[current_real[key]];
        let identity = before_row
            .stable_identity
            .as_deref()
            .ok_or_else(|| OrderedCompareError::new("ROW_IDENTITY_MISSING"))?;
        if capture_locators {
            reserve_locator(lease.as_deref_mut(), changed_columns, changed_columns)?;
            locators.standard.push(StandardRecordRef {
                kind: StandardKind::RowModified,
                row_identity: Some(identity.to_string()),
                before: Some(before_row.location),
                current: Some(current_row.location),
                value_columns: changed_columns.clone(),
                changed_columns: changed_columns.clone(),
                diagnostics: Vec::new(),
            });
            locators.ordered.push(OrderedRecordRef {
                kind: "ORDERED_ROW_MODIFIED",
                semantic_kind: "CONTENT_UPDATE",
                entity_key_kind: "REAL_STABLE",
                row_identity: identity.to_string(),
                before_position: Some(before_row.position),
                current_position: Some(current_row.position),
                before: Some(before_row.location),
                current: Some(current_row.location),
                value_columns: changed_columns.clone(),
                changed_columns: changed_columns.clone(),
            });
        } else {
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
    }

    for (index, key) in moved_keys.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        let before_row = &before.rows[before_real[key]];
        let current_row = &current.rows[current_real[key]];
        if capture_locators {
            reserve_locator(lease.as_deref_mut(), &[], &[])?;
            locators.ordered.push(OrderedRecordRef {
                kind: "ORDERED_ROW_MOVED",
                semantic_kind: "MOVE",
                entity_key_kind: "REAL_STABLE",
                row_identity: before_row
                    .stable_identity
                    .clone()
                    .ok_or_else(|| OrderedCompareError::new("ROW_IDENTITY_MISSING"))?,
                before_position: Some(before_row.position),
                current_position: Some(current_row.position),
                before: Some(before_row.location),
                current: Some(current_row.location),
                value_columns: Vec::new(),
                changed_columns: Vec::new(),
            });
        } else {
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
    }

    check_context(context)?;
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
    check_context(context)?;

    let blank = blank_extension(
        &options.table_name,
        &before.rows,
        &current.rows,
        &backbone,
        options.include_add_delete_records,
        capture_locators,
        lease.as_deref_mut(),
        context,
    )?;
    locators.blank = blank.locator_records;
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
        || !locators.ordered.is_empty()
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
    check_context(context)?;
    let before_digest = Some(ordered_digest(
        &before.rows,
        &options.table_name,
        &options.policy_version,
        &digest_value_columns,
        context,
    )?);
    check_context(context)?;
    let current_digest = Some(ordered_digest(
        &current.rows,
        &options.table_name,
        &options.policy_version,
        &digest_value_columns,
        context,
    )?);
    let content_changed = status == "UNCHANGED"
        && if options.columns_added {
            options.compare_excluded_columns.iter().any(|name| selected.contains(name))
                && ordered_shared_counts(&before.rows, &selected, context)?
                    != ordered_shared_counts(&current.rows, &selected, context)?
        } else {
            !options.compare_excluded_columns.is_empty() && options.raw_content_changed
        };

    Ok(OrderedWork {
        facts: OrderedCompareResult {
            format: ORDERED_COMPARE_FORMAT.to_string(),
            version: ORDERED_COMPARE_VERSION,
            table_name: options.table_name.clone(),
            status: status.to_string(),
            row_count_before: pair.before.map(side_row_count),
            row_count_current: pair.current.map(side_row_count),
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
        },
        locators,
    })
}

fn degraded_result(
    pair: &OrderedBatchPair<'_>,
    diagnostic: &'static str,
    capture_locators: bool,
) -> OrderedWork {
    let options = pair.options;
    let diagnostics = vec![diagnostic.to_string()];
    OrderedWork {
        facts: OrderedCompareResult {
            format: ORDERED_COMPARE_FORMAT.to_string(),
            version: ORDERED_COMPARE_VERSION,
            table_name: options.table_name.clone(),
            status: "DEGRADED".to_string(),
            row_count_before: pair.before.map(side_row_count),
            row_count_current: pair.current.map(side_row_count),
            row_added_count: 0,
            row_deleted_count: 0,
            row_modified_count: 0,
            suppressed_added_count: 0,
            suppressed_deleted_count: 0,
            content_changed: false,
            schema_changes: options.schema_changes.clone(),
            diagnostics: diagnostics.clone(),
            records: if capture_locators { Vec::new() } else { vec![StandardRecord {
                table_name: options.table_name.clone(),
                record_kind: "TABLE_DEGRADED".to_string(),
                row_identity: None,
                changed_columns: Vec::new(),
                before_values: Vec::new(),
                current_values: Vec::new(),
                field_changes: Vec::new(),
                diagnostics: diagnostics.clone(),
            }] },
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
        },
        locators: OrderedLocatorRecords {
            standard: if capture_locators { vec![StandardRecordRef {
                kind: StandardKind::TableDegraded,
                row_identity: None,
                before: None,
                current: None,
                value_columns: Vec::new(),
                changed_columns: Vec::new(),
                diagnostics: vec![diagnostic.to_string()],
            }] } else { Vec::new() },
            ..OrderedLocatorRecords::default()
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

fn ordered_shared_counts(
    rows: &[OrderedRow],
    selected: &[String],
    context: Option<&KernelContext>,
) -> Result<BTreeMap<String, usize>, OrderedCompareError> {
    let mut counts = BTreeMap::new();
    for (index, row) in rows.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        let mut frame = encode_uleb128(selected.len() as u64)
            .map_err(|_| OrderedCompareError::new("ROW_ENCODING_FAILED"))?;
        for name in selected {
            let cell = row.cells.get(name)
                .ok_or_else(|| OrderedCompareError::new("ROW_SHAPE_MISMATCH"))?;
            frame.extend(encode_uleb128(name.len() as u64)
                .map_err(|_| OrderedCompareError::new("ROW_ENCODING_FAILED"))?);
            frame.extend_from_slice(name.as_bytes());
            frame.extend_from_slice(&cell.frame);
        }
        let digest = semantic_digest(DigestKind::Row, &frame)
            .map_err(|_| OrderedCompareError::new("DIGEST_FAILED"))?;
        let count = counts.entry(digest.digest_ref().as_str().to_string()).or_insert(0usize);
        *count = count.checked_add(1)
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
    }
    Ok(counts)
}

fn real_index(
    rows: &[OrderedRow],
    context: Option<&KernelContext>,
) -> Result<BTreeMap<Vec<u8>, usize>, OrderedCompareError> {
    let mut result = BTreeMap::new();
    for (index, row) in rows.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if let Some(key) = &row.stable_key {
            result.insert(key.clone(), index);
        }
    }
    Ok(result)
}

fn reserve_locator(
    lease: Option<&mut KernelLease>,
    standard_columns: &[String],
    ordered_columns: &[String],
) -> Result<(), OrderedCompareError> {
    if let Some(lease) = lease {
        let bytes = standard_columns
            .iter()
            .chain(ordered_columns)
            .try_fold(768usize, |total, name| {
                (std::mem::size_of::<String>() + name.len())
                    .checked_mul(2)
                    .and_then(|part| total.checked_add(part))
            })
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        lease.grow(bytes)?;
    }
    Ok(())
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

fn column_names_from_schema(schema: &SchemaRef) -> Result<Vec<String>, OrderedCompareError> {
    if schema.fields().len() > MAX_ORDERED_COLUMNS {
        return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
    }
    let mut names = Vec::with_capacity(schema.fields().len());
    let mut seen = HashSet::with_capacity(schema.fields().len());
    for field in schema.fields() {
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

fn column_names_batches(
    schema: Option<&SchemaRef>,
    batches: Option<&[RecordBatch]>,
) -> Result<Vec<String>, OrderedCompareError> {
    let Some(batches) = batches else {
        return Ok(Vec::new());
    };
    let schema = schema.ok_or_else(|| OrderedCompareError::new("CANONICAL_SCHEMA_REQUIRED"))?;
    let names = column_names_from_schema(schema)?;
    for batch in batches {
        if batch.schema().as_ref() != schema.as_ref() {
            return Err(OrderedCompareError::new("ROW_SHAPE_MISMATCH"));
        }
    }
    Ok(names)
}

fn side_row_count(batches: &[RecordBatch]) -> usize {
    batches.iter().map(RecordBatch::num_rows).sum()
}

fn is_control_or_resource(error: &OrderedCompareError) -> bool {
    matches!(
        error.code(),
        "COMPARISON_CANCELLED" | "COMPARISON_DEADLINE_EXCEEDED" | "RESOURCE_LIMIT_EXCEEDED"
    )
}

fn check_context(context: Option<&KernelContext>) -> Result<(), OrderedCompareError> {
    if let Some(context) = context {
        context.check()?;
    }
    Ok(())
}

fn read_side_batches(
    batches: Option<&[RecordBatch]>,
    selected: &[String],
    blank_provenance: BlankProvenance,
    max_rows: usize,
    context: Option<&KernelContext>,
) -> Result<SideRows, OrderedCompareError> {
    let Some(batches) = batches else {
        return Ok(SideRows { rows: Vec::new() });
    };
    let mut rows = Vec::new();
    let mut positions = HashSet::new();
    let mut identities = HashSet::new();
    let mut encoded_bytes = 0usize;
    for (batch_index, batch) in batches.iter().enumerate() {
        if let Some(context) = context {
            context.check()?;
        }
        let side = read_side(Some(batch), selected, blank_provenance, max_rows, context)?;
        if rows
            .len()
            .checked_add(side.rows.len())
            .is_none_or(|count| count > max_rows)
        {
            return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
        }
        for (row_index, mut row) in side.rows.into_iter().enumerate() {
            if row_index % 1024 == 0 {
                check_context(context)?;
            }
            row.location.batch = batch_index;
            if !positions.insert(row.position) {
                return Err(OrderedCompareError::new("ORDER_KEY_DUPLICATE"));
            }
            if row
                .stable_key
                .as_ref()
                .is_some_and(|key| !identities.insert(key.clone()))
            {
                return Err(OrderedCompareError::new("ROW_IDENTITY_DUPLICATE"));
            }
            for cell in row.cells.values() {
                encoded_bytes = encoded_bytes
                    .checked_add(cell.frame.len())
                    .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
                if context.is_none() && encoded_bytes > MAX_ORDERED_TOTAL_ENCODED_BYTES {
                    return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
                }
            }
            rows.push(row);
        }
    }
    if let Some(context) = context {
        let order = sort_indices_checked(&rows, context, |left, right| {
            left.position.cmp(&right.position)
        })?;
        let mut slots: Vec<Option<OrderedRow>> = rows.into_iter().map(Some).collect();
        let mut sorted = Vec::with_capacity(slots.len());
        for (index, position) in order.into_iter().enumerate() {
            if index % 1024 == 0 {
                context.check()?;
            }
            sorted.push(
                slots[position]
                    .take()
                    .ok_or_else(|| OrderedCompareError::new("ORDERED_INTERNAL_ERROR"))?,
            );
        }
        Ok(SideRows { rows: sorted })
    } else {
        rows.sort_by_key(|row| row.position);
        Ok(SideRows { rows })
    }
}

fn read_side(
    batch: Option<&RecordBatch>,
    selected: &[String],
    blank_provenance: BlankProvenance,
    max_rows: usize,
    context: Option<&KernelContext>,
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
        if row_index % 1024 == 0 {
            if let Some(context) = context {
                context.check()?;
            }
        }
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
            (BlankProvenance::CanonicalPseudoGid, Some(_)) => {
                return Err(OrderedCompareError::new("CANONICAL_GID_INVALID"));
            }
            (BlankProvenance::SourceMissingStableKey, Some(_)) => {
                return Err(OrderedCompareError::new("SOURCE_GID_INVALID"));
            }
        };

        let mut cells = BTreeMap::new();
        for column in &value_columns {
            let index = *indices
                .get(column)
                .ok_or_else(|| OrderedCompareError::new("ROW_SHAPE_MISMATCH"))?;
            let field = fields.field(index);
            let cell = encode_cell(batch.column(index).as_ref(), row_index, field)?;
            if context.is_none() && cell.frame.len() > MAX_ORDERED_CELL_BYTES.saturating_add(16) {
                return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
            }
            total_encoded_bytes = total_encoded_bytes
                .checked_add(cell.frame.len())
                .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
            if context.is_none() && total_encoded_bytes > MAX_ORDERED_TOTAL_ENCODED_BYTES {
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
            location: RowLocation {
                batch: 0,
                row: row_index,
            },
            position,
            stable_key,
            stable_identity,
            blank,
            cells,
        });
    }
    if context.is_none() {
        rows.sort_by_key(|row| row.position);
    }
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

pub(super) fn encode_cell(
    array: &dyn Array,
    row: usize,
    field: &Field,
) -> Result<EncodedCell, OrderedCompareError> {
    if array.is_null(row) {
        return scalar_frame(DeclaredType::null(), TypedScalar::Null(NullScalar));
    }
    let spelling = scalar_type(field)?;
    if spelling
        .trim_start()
        .to_ascii_lowercase()
        .starts_with("set(")
    {
        return encode_set(array, row, field);
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

fn scalar_type(field: &Field) -> Result<String, OrderedCompareError> {
    if let Some(metadata) = field.metadata().get("gdds.canonical_type") {
        let value: Value = serde_json::from_str(metadata)
            .map_err(|_| OrderedCompareError::new("COLUMN_TYPE_INVALID"))?;
        return value
            .get("sql_type")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or_else(|| OrderedCompareError::new("COLUMN_TYPE_INVALID"));
    }
    Ok(field
        .metadata()
        .get("gdms.scalar_type")
        .cloned()
        .unwrap_or_else(|| format!("{:?}", field.data_type())))
}

pub(super) fn declared_type(
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

fn encode_set(
    array: &dyn Array,
    row: usize,
    field: &Field,
) -> Result<EncodedCell, OrderedCompareError> {
    let text = if let Some(strings) = array.as_any().downcast_ref::<StringArray>() {
        strings.value(row)
    } else if let Some(strings) = array.as_any().downcast_ref::<LargeStringArray>() {
        strings.value(row)
    } else {
        return Err(OrderedCompareError::new("SET_VALUE_INVALID"));
    };
    let canonical = field.metadata().get("gdds.canonical_type");
    let declaration = canonical
        .map(|metadata| serde_json::from_str::<Value>(metadata))
        .transpose()
        .map_err(|_| OrderedCompareError::new("COLUMN_TYPE_INVALID"))?;
    let labels = declaration
        .as_ref()
        .and_then(|value| value.get("labels"))
        .and_then(Value::as_array);
    let members: Vec<&str> = if text.is_empty() {
        Vec::new()
    } else {
        text.split(',').collect()
    };
    if members.iter().any(|member| member.is_empty()) {
        return Err(OrderedCompareError::new("SET_VALUE_INVALID"));
    }
    if let Some(labels) = labels {
        let mut previous = None;
        for member in &members {
            let position = labels
                .iter()
                .position(|label| label.as_str() == Some(*member))
                .ok_or_else(|| OrderedCompareError::new("SET_VALUE_INVALID"))?;
            if previous.is_some_and(|prior| position <= prior) {
                return Err(OrderedCompareError::new("SET_VALUE_INVALID"));
            }
            previous = Some(position);
        }
    }
    let mut encoded_items = Vec::with_capacity(members.len());
    for text in members {
        let item = encode_typed_scalar(
            &DeclaredType::string(),
            &TypedScalar::String(StringScalar {
                text: text.to_string(),
            }),
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

fn longest_increasing_backbone_with_control(
    positions: &[i64],
    context: Option<&KernelContext>,
) -> Result<Vec<usize>, OrderedCompareError> {
    if positions.is_empty() {
        return Ok(Vec::new());
    }
    let mut reach = vec![0usize; positions.len()];
    let mut tails = Vec::<i64>::new();
    for index in (0..positions.len()).rev() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
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
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if let Some(level) = levels.get_mut(length) {
            level.push(index);
        }
    }
    let mut chosen = Vec::with_capacity(longest);
    let mut previous = None;
    for length in (1..=longest).rev() {
        if length % 1024 == 0 {
            check_context(context)?;
        }
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
    check_context(context)?;
    Ok(chosen)
}

fn ordered_digest(
    rows: &[OrderedRow],
    table_name: &str,
    policy_version: &str,
    value_columns: &[String],
    context: Option<&KernelContext>,
) -> Result<String, OrderedCompareError> {
    let mut hasher = Sha256::new();
    hasher.update(b"{\"contract_version\":");
    hash_jcs_string(&mut hasher, policy_version)?;
    hasher.update(b",\"kind\":\"ordered-logical-digest\",\"rows\":[");
    for (index, row) in rows.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if index > 0 {
            hasher.update(b",");
        }
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
        hasher.update(b"{\"blank\":");
        hasher.update(if row.blank {
            b"true".as_slice()
        } else {
            b"false".as_slice()
        });
        hasher.update(b",\"content\":");
        hash_optional_jcs_string(&mut hasher, content.as_deref())?;
        hasher.update(b",\"position\":");
        hash_jcs_integer(&mut hasher, row.position)?;
        hasher.update(b",\"stable\":");
        hash_optional_jcs_string(&mut hasher, row.stable_identity.as_deref())?;
        hasher.update(b"}");
    }
    hasher.update(b"],\"table_name\":");
    hash_jcs_string(&mut hasher, table_name)?;
    hasher.update(b"}");
    Ok(format!("sha256:{}", hex(&hasher.finalize())))
}

fn hash_jcs_string(hasher: &mut Sha256, text: &str) -> Result<(), OrderedCompareError> {
    let bytes = serde_json::to_vec(text)
        .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
    let canonical = canonicalize_jcs(&bytes)
        .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
    hasher.update(canonical);
    Ok(())
}

fn hash_optional_jcs_string(
    hasher: &mut Sha256,
    text: Option<&str>,
) -> Result<(), OrderedCompareError> {
    if let Some(text) = text {
        hash_jcs_string(hasher, text)
    } else {
        hasher.update(b"null");
        Ok(())
    }
}

const IJSON_MAX_SAFE_INTEGER: i64 = (1_i64 << 53) - 1;

fn hash_jcs_integer(hasher: &mut Sha256, value: i64) -> Result<(), OrderedCompareError> {
    if !(-IJSON_MAX_SAFE_INTEGER..=IJSON_MAX_SAFE_INTEGER).contains(&value) {
        return Err(OrderedCompareError::new("CANONICAL_ENCODING_FAILED"));
    }
    hasher.update(value.to_string().as_bytes());
    Ok(())
}

fn hash_jcs_count(hasher: &mut Sha256, value: usize) -> Result<(), OrderedCompareError> {
    let value = i64::try_from(value)
        .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
    hash_jcs_integer(hasher, value)
}

fn blank_extension(
    table_name: &str,
    before_rows: &[OrderedRow],
    current_rows: &[OrderedRow],
    backbone: &HashSet<Vec<u8>>,
    include_records: bool,
    capture_locators: bool,
    mut lease: Option<&mut KernelLease>,
    context: Option<&KernelContext>,
) -> Result<BlankExtensionWork, OrderedCompareError> {
    let before_gaps = blank_gaps(before_rows, Some(backbone), context)?;
    let current_gaps = blank_gaps(current_rows, Some(backbone), context)?;
    let mut keys: BTreeSet<(Option<String>, Option<String>)> =
        before_gaps.keys().cloned().collect();
    keys.extend(current_gaps.keys().cloned());
    let mut records = Vec::new();
    let mut locator_records = Vec::new();
    let mut inserted_count = 0usize;
    let mut deleted_count = 0usize;
    for (index, key) in keys.into_iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        let before_gap = before_gaps.get(&key).copied();
        let current_gap = current_gaps.get(&key).copied();
        let before_count = before_gap.map_or(0, |gap| gap.count);
        let current_count = current_gap.map_or(0, |gap| gap.count);
        if before_count == current_count {
            continue;
        }
        if include_records && capture_locators {
            reserve_locator(lease.as_deref_mut(), &[], &[])?;
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
            if include_records && capture_locators {
                locator_records.push(BlankRecordRef {
                    kind: "BLANK_DELETE_INTERVAL",
                    semantic_kind: "BLANK_DELETE_INTERVAL",
                    entity_key_kind: "PSEUDO_BLANK",
                    interval,
                    before_occupancy: before_count,
                    current_occupancy: current_count,
                });
            } else if include_records {
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
            if include_records && capture_locators {
                locator_records.push(BlankRecordRef {
                    kind: "BLANK_INSERT_INTERVAL",
                    semantic_kind: "BLANK_INSERT_INTERVAL",
                    entity_key_kind: "PSEUDO_BLANK",
                    interval,
                    before_occupancy: before_count,
                    current_occupancy: current_count,
                });
            } else if include_records {
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
    let before_occupancy = blank_gaps(before_rows, None, context)?;
    let current_occupancy = blank_gaps(current_rows, None, context)?;
    Ok(BlankExtensionWork {
        summary: BlankSummary {
            interval_inserted_count: inserted_count,
            interval_deleted_count: deleted_count,
            blank_changed_count: inserted_count + deleted_count,
            degraded_count: 0,
        },
        before_digest: occupancy_digest(&before_occupancy, context)?,
        current_digest: occupancy_digest(&current_occupancy, context)?,
        records,
        locator_records,
    })
}

struct BlankExtensionWork {
    summary: BlankSummary,
    before_digest: String,
    current_digest: String,
    records: Vec<BlankRecord>,
    locator_records: Vec<BlankRecordRef>,
}

fn blank_gaps(
    rows: &[OrderedRow],
    anchors: Option<&HashSet<Vec<u8>>>,
    context: Option<&KernelContext>,
) -> Result<BTreeMap<(Option<String>, Option<String>), Gap>, OrderedCompareError> {
    let mut gaps = BTreeMap::new();
    let mut before_anchor: Option<String> = None;
    let mut count = 0usize;
    let mut start = 0i64;
    let mut end = 0i64;
    for (index, row) in rows.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
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
    Ok(gaps)
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
    context: Option<&KernelContext>,
) -> Result<String, OrderedCompareError> {
    let mut hasher = Sha256::new();
    hasher.update(b"[");
    for (index, (key, gap)) in gaps.iter().enumerate() {
        if index % 1024 == 0 {
            check_context(context)?;
        }
        if index > 0 {
            hasher.update(b",");
        }
        hasher.update(b"{\"after\":");
        hash_optional_jcs_string(&mut hasher, key.1.as_deref())?;
        hasher.update(b",\"before\":");
        hash_optional_jcs_string(&mut hasher, key.0.as_deref())?;
        hasher.update(b",\"count\":");
        hash_jcs_count(&mut hasher, gap.count)?;
        hasher.update(b"}");
    }
    hasher.update(b"]");
    Ok(format!("sha256:{}", hex(&hasher.finalize())))
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

fn blank_artifact_key(
    record: &BlankRecordRef,
    table_name: &str,
) -> Result<Vec<u8>, OrderedCompareError> {
    let digest = record
        .interval
        .interval_digest
        .strip_prefix("sha256:")
        .ok_or_else(|| OrderedCompareError::new("DIGEST_FAILED"))?;
    let row = json!({
        "table_name": table_name,
        "record_kind": record.kind,
        "semantic_kind": record.semantic_kind,
        "interval": {
            "before_start": record.interval.before_start,
            "before_end": record.interval.before_end,
            "current_start": record.interval.current_start,
            "current_end": record.interval.current_end,
            "row_count": record.interval.row_count,
            "interval_digest": {"bytes_hex": digest},
        },
        "before_occupancy": record.before_occupancy,
        "current_occupancy": record.current_occupancy,
        "diagnostics": [],
    });
    let bytes = serde_json::to_vec(&row)
        .map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))?;
    canonicalize_jcs(&bytes).map_err(|_| OrderedCompareError::new("CANONICAL_ENCODING_FAILED"))
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
