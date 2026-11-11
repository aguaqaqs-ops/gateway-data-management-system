//! Comparison kernels over projection-ready Arrow data.
//!
//! The core owns no files. Callers provide canonical Arrow batches, a shared
//! operation budget/control context and their existing fixed Rayon pool.

#![forbid(unsafe_code)]

pub(crate) mod kernel;
pub(crate) mod ordered;
mod policy;
mod standard;

pub use kernel::{CanonicalBatchSide, KernelContext, KernelLease};
pub use policy::{ParsedComparisonPolicy, parse_comparison_policy};
pub use standard::{
    RowLocation, StandardComputation, StandardIdentityBatch, StandardIdentityScanner, StandardKind, StandardMode, StandardOptions,
    StandardRecordRef, canonical_cell_frame_at, compare_standard_table,
};

pub use ordered::{
    BlankExtensionResult, BlankInterval, BlankProvenance, BlankRecord, BlankSummary,
    CanonicalValue, DEFAULT_MAX_ORDERED_ROWS, FieldChange, ORDERED_COMPARE_FORMAT,
    ORDERED_COMPARE_VERSION, OrderedBatchPair, OrderedCompareError, OrderedCompareOptions,
    OrderedCompareResult, OrderedExtensionResult, OrderedKernelResult, OrderedRecord,
    OrderedSummary, SchemaChanges, StandardRecord, UnchangedOrderedSummary,
    compare_ordered_batches, summarize_unchanged_ordered_batches,
};
