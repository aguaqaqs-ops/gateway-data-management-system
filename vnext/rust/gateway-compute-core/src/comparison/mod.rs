//! Comparison kernels over projection-ready Arrow data.
//!
//! The core owns no files. Callers provide canonical Arrow batches, a shared
//! operation budget/control context and their existing fixed Rayon pool.

#![forbid(unsafe_code)]

mod kernel;
mod ordered;
mod standard;

pub use kernel::{CanonicalBatchSide, KernelContext};
pub use standard::{
    RowLocation, StandardComputation, StandardKind, StandardMode, StandardOptions,
    StandardRecordRef, compare_standard_table,
};

pub use ordered::{
    BlankExtensionResult, BlankInterval, BlankProvenance, BlankRecord, BlankSummary,
    CanonicalValue, DEFAULT_MAX_ORDERED_ROWS, FieldChange, MAX_ORDERED_THREADS, OrderedBatchPair,
    OrderedCompareError, OrderedCompareOptions, OrderedCompareResult, OrderedExtensionResult,
    OrderedKernelResult, OrderedRecord, OrderedSummary, OrderedTablePair, SchemaChanges,
    StandardRecord, UnchangedOrderedSummary, build_ordered_pool, compare_ordered_batches,
    compare_ordered_table, compare_ordered_tables_parallel, summarize_unchanged_ordered_batches,
    summarize_unchanged_ordered_side,
};
