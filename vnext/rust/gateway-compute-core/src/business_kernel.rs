//! Bounded Arrow business kernels for SQL materialization and canonical storage.
//!
//! Callers retain ownership of parsing, ruleset selection, XML/composite logic,
//! and small summary digests. These types describe the coarse-grained Arrow and
//! metadata boundary used by the three business operations.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

use arrow_array::{Array, RecordBatch};

use crate::table_access::{ColumnDescriptor, TableDescriptor};

/// Existing business diagnostics retain at most this many entries.
pub const BUSINESS_KERNEL_MAX_DIAGNOSTICS: usize = 1024;

/// Per-call bounds for one business-kernel operation.
///
/// `max_input_bytes` counts borrowed Arrow buffers conservatively. `max_live_bytes`
/// bounds allocations owned by the adapter and core while they are simultaneously
/// live. `max_output_bytes` counts every buffer retained by returned Arrow batches
/// and facts, including buffers shared with the input. Canonical IPC output has
/// its own `CanonicalIpcBudgets::max_output_bytes` limit.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BusinessKernelBudgets {
    /// Maximum columns in each input or output table.
    pub max_columns: usize,
    /// Maximum caller-provided Arrow record batches.
    pub max_batches: usize,
    /// Maximum rows in one table.
    pub max_rows: usize,
    /// Maximum UTF-8 bytes in bounded table, column, rule, label, and diagnostic metadata.
    pub max_metadata_bytes: usize,
    /// Maximum borrowed Arrow array bytes in the input.
    pub max_input_bytes: usize,
    /// Maximum adapter/core-owned live allocation estimate.
    pub max_live_bytes: usize,
    /// Maximum bytes retained by returned Arrow buffers and facts.
    pub max_output_bytes: usize,
    /// Maximum bytes retained by business diagnostic messages.
    pub max_diagnostic_bytes: usize,
}

/// Caller-owned cooperative cancellation and optional monotonic deadline.
#[derive(Debug, Clone, Copy, Default)]
pub struct BusinessKernelControl<'a> {
    /// Set by the caller to request cancellation.
    pub cancel: Option<&'a AtomicBool>,
    /// Absolute monotonic deadline. `None` means no fixed deadline.
    pub deadline: Option<Instant>,
}

/// Explicit local limits and controls for one business-kernel call.
#[derive(Debug, Clone, Copy)]
pub struct BusinessKernelOptions<'a> {
    pub budgets: BusinessKernelBudgets,
    pub control: BusinessKernelControl<'a>,
}

impl BusinessKernelOptions<'_> {
    /// Checks cooperative cancellation and the optional finite deadline.
    pub fn checkpoint(&self) -> Result<(), BusinessKernelError> {
        if self
            .control
            .cancel
            .is_some_and(|cancel| cancel.load(Ordering::Relaxed))
        {
            return Err(BusinessKernelError::new(
                BusinessKernelErrorKind::Cancelled,
                "business kernel cancelled",
            ));
        }
        if self
            .control
            .deadline
            .is_some_and(|deadline| Instant::now() >= deadline)
        {
            return Err(BusinessKernelError::new(
                BusinessKernelErrorKind::Deadline,
                "business kernel deadline elapsed",
            ));
        }
        Ok(())
    }
}

/// A bounded Arrow table supplied to a business kernel.
#[derive(Debug, Clone, Copy)]
pub struct KernelTableInput<'a> {
    pub descriptor: &'a TableDescriptor,
    pub batches: &'a [RecordBatch],
}

/// Whether SQL materialization may publish its raw-content digest.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MaterializationStage {
    Provisional,
    Final,
}

/// Small metadata already resolved by the Python materialization owner.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SqlMaterializationPlan {
    pub stage: MaterializationStage,
    /// Effective compare keys in their owner-defined order.
    pub effective_compare_key_columns: Vec<String>,
}

/// Row strategy selected by the existing StorageRuleView owner.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProjectionRowPolicy {
    Keyed,
    Keyless,
    OrderedGidNo,
}

/// One normalized retained output column and its source Arrow column.
///
/// `descriptor` is produced by the existing Python projection owner after its
/// SQL type normalization and whitelist checks. `source_index` may be absent
/// only when a precomputed schema diagnostic already explains the missing
/// source column; the core still validates every present Arrow binding.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonicalProjectionColumn {
    pub source_index: Option<usize>,
    pub descriptor: ColumnDescriptor,
}

/// Narrow projection metadata derived from a validated StorageRuleView.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonicalProjectionPlan {
    pub materialization_stage: MaterializationStage,
    pub canonical_table: String,
    /// Row count from the bound SnapshotTableDescriptor; the core compares it
    /// with the actual Arrow input row count before returning a projection.
    pub expected_source_row_count: usize,
    /// Retained columns in the canonical output schema order.
    pub columns: Vec<CanonicalProjectionColumn>,
    /// Canonical key columns in the StorageRuleView's strict order.
    pub canonical_key_columns: Vec<String>,
    pub structural_columns: Vec<String>,
    pub row_policy: ProjectionRowPolicy,
    /// True only for an already canonicalized projection input that may contain
    /// a previously allocated pseudo gid.
    pub canonicalized_input: bool,
    /// Existing Python-owned rule/type/schema diagnostics, in owner order.
    /// Arrow binding and row-level validity are still checked by the core.
    pub schema_diagnostics: Vec<KernelDiagnostic>,
    pub omitted_schema_diagnostic_count: usize,
}

/// A named point table supplied to the catalog filter.
#[derive(Debug, Clone, Copy)]
pub struct NamedKernelTableInput<'a> {
    pub table_name: &'a str,
    pub table: KernelTableInput<'a>,
}

/// Inputs to catalog filtering. Special address and description are fixed by
/// the Composite Signal Contract rather than caller-configurable values.
#[derive(Debug, Clone, Copy)]
pub struct CatalogFilterInput<'a> {
    pub device_table: Option<KernelTableInput<'a>>,
    pub point_tables: &'a [NamedKernelTableInput<'a>],
}

/// Facts established while checking an input table against explicit limits.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct KernelTableInputFacts {
    pub row_count: usize,
    pub input_bytes: usize,
    pub metadata_bytes: usize,
}

/// An Arrow table returned by a business-kernel operation.
#[derive(Debug, Clone)]
pub struct KernelArrowTable {
    pub descriptor: TableDescriptor,
    pub batches: Vec<RecordBatch>,
    pub row_count: usize,
}

/// SQL materialization facts; provisional results intentionally have no raw digest.
#[derive(Debug, Clone)]
pub struct SqlMaterializationOutput {
    pub table: KernelArrowTable,
    pub raw_content_digest: Option<[u8; 32]>,
    /// Duplicate compare keys are a warning and do not discard source rows.
    pub duplicate_effective_key: bool,
}

/// Filtered Arrow facts consumed by the existing Python composite binder.
#[derive(Debug, Clone)]
pub struct CatalogFilterOutput {
    pub source_device_row_count: usize,
    pub matching_devices: Option<KernelArrowTable>,
    pub special_points: Vec<KernelArrowTable>,
}

/// Canonical projected table and small digest/count facts.
#[derive(Debug, Clone)]
pub struct CanonicalProjectionOutput {
    pub table: KernelArrowTable,
    pub raw_content_digest: [u8; 32],
    pub gid_real_count: Option<usize>,
    pub gid_pseudo_count: Option<usize>,
}

/// Failure classes for local resource/control and Arrow boundary errors.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BusinessKernelErrorKind {
    Schema,
    Value,
    Resource,
    Cancelled,
    Deadline,
    Arrow,
}

/// A non-business-diagnostic failure from a business-kernel operation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BusinessKernelError {
    kind: BusinessKernelErrorKind,
    message: String,
}

impl BusinessKernelError {
    pub fn new(kind: BusinessKernelErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }

    pub const fn kind(&self) -> BusinessKernelErrorKind {
        self.kind
    }

    pub fn message(&self) -> &str {
        &self.message
    }
}

impl std::fmt::Display for BusinessKernelError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{:?}: {}", self.kind, self.message)
    }
}

impl std::error::Error for BusinessKernelError {}

/// Severity of a typed business diagnostic returned in a [`KernelOutcome`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KernelDiagnosticSeverity {
    Warning,
    Error,
}

/// Stable diagnostic facts from SQL materialization, catalog filtering, or projection.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct KernelDiagnostic {
    pub code: String,
    pub message: String,
    pub table: Option<String>,
    pub column: Option<String>,
    pub severity: KernelDiagnosticSeverity,
}

/// A business result whose value is absent when any fatal diagnostic was found.
///
/// The owning capability's 1024-entry cap and omitted-count behavior are fixed;
/// the caller cannot widen or lower the cap through a resource option.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct KernelOutcome<T> {
    pub output: Option<T>,
    pub diagnostics: Vec<KernelDiagnostic>,
    pub omitted_diagnostic_count: usize,
}

/// Checks metadata and borrowed Arrow input before an operation begins collecting rows.
///
/// Metadata is counted from existing descriptors before any adapter-side copies.
/// Arrow memory is deliberately counted even when buffers may be shared elsewhere.
pub fn preflight_table_input(
    input: KernelTableInput<'_>,
    options: BusinessKernelOptions<'_>,
) -> Result<KernelTableInputFacts, BusinessKernelError> {
    options.checkpoint()?;

    let descriptor = input.descriptor;
    if descriptor.columns.len() > options.budgets.max_columns {
        return Err(resource_error("business kernel column budget exceeded"));
    }
    if input.batches.len() > options.budgets.max_batches {
        return Err(resource_error("business kernel batch budget exceeded"));
    }

    let mut metadata_bytes = 0usize;
    add_metadata(&mut metadata_bytes, descriptor.display_name.len())?;
    add_metadata(&mut metadata_bytes, descriptor.canonical_name.len())?;
    for column in &descriptor.columns {
        add_metadata(&mut metadata_bytes, column.display_name.len())?;
        add_metadata(&mut metadata_bytes, column.canonical_name.len())?;
        add_metadata(&mut metadata_bytes, column.sql_type.len())?;
        if let Some(labels) = &column.labels {
            for label in labels {
                add_metadata(&mut metadata_bytes, label.len())?;
            }
        }
    }
    for key in &descriptor.primary_key {
        add_metadata(&mut metadata_bytes, key.len())?;
    }
    if metadata_bytes > options.budgets.max_metadata_bytes {
        return Err(resource_error("business kernel metadata budget exceeded"));
    }

    let mut row_count = 0usize;
    let mut input_bytes = 0usize;
    for batch in input.batches {
        options.checkpoint()?;
        if batch.num_columns() != descriptor.columns.len() {
            return Err(BusinessKernelError::new(
                BusinessKernelErrorKind::Schema,
                "Arrow batch column count does not match table descriptor",
            ));
        }
        row_count = row_count
            .checked_add(batch.num_rows())
            .ok_or_else(|| resource_error("business kernel row count overflow"))?;
        for array in batch.columns() {
            input_bytes = input_bytes
                .checked_add(array.get_array_memory_size())
                .ok_or_else(|| resource_error("business kernel input byte count overflow"))?;
        }
        if row_count > options.budgets.max_rows {
            return Err(resource_error("business kernel row budget exceeded"));
        }
        if input_bytes > options.budgets.max_input_bytes {
            return Err(resource_error("business kernel input byte budget exceeded"));
        }
    }

    options.checkpoint()?;
    Ok(KernelTableInputFacts {
        row_count,
        input_bytes,
        metadata_bytes,
    })
}

fn add_metadata(total: &mut usize, length: usize) -> Result<(), BusinessKernelError> {
    *total = total
        .checked_add(length)
        .ok_or_else(|| resource_error("business kernel metadata size overflow"))?;
    Ok(())
}

fn resource_error(message: impl Into<String>) -> BusinessKernelError {
    BusinessKernelError::new(BusinessKernelErrorKind::Resource, message)
}
