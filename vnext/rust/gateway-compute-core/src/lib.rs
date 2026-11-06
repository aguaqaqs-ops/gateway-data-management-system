#![forbid(unsafe_code)]

pub mod canonical_ipc;
pub mod business_kernel;
pub mod comparison;
mod records;
pub mod table_access;

pub use records::{RecordsParquetSummary, read_records_parquet_v1};
