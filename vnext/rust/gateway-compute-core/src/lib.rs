#![forbid(unsafe_code)]

pub mod comparison;
mod records;
pub mod table_access;

pub use records::{RecordsParquetSummary, read_records_parquet_v1};
