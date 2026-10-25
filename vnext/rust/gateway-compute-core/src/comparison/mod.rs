//! Comparison kernels over projection-ready Arrow data.
//!
//! V1 adds only the IEC104 `gid` / `no` ordered prototype. The core owns no
//! files; callers provide Arrow batches and a fixed Rayon pool.

#![forbid(unsafe_code)]

mod ordered;

pub use ordered::{
    BlankExtensionResult, BlankInterval, BlankProvenance, BlankRecord, BlankSummary,
    CanonicalValue, DEFAULT_MAX_ORDERED_ROWS, FieldChange, MAX_ORDERED_THREADS,
    OrderedCompareError, OrderedCompareOptions, OrderedCompareResult, OrderedExtensionResult,
    OrderedRecord, OrderedSummary, OrderedTablePair, SchemaChanges, StandardRecord,
    build_ordered_pool, compare_ordered_table, compare_ordered_tables_parallel,
};
