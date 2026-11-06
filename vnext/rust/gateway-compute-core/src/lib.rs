#![forbid(unsafe_code)]

pub mod comparison;
pub mod canonical_ipc;
mod records;
pub mod table_access;

pub use records::{RecordsParquetSummary, read_records_parquet_v1};
