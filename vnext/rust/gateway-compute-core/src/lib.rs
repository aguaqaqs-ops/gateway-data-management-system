#![forbid(unsafe_code)]

mod arrow_extract;
mod arrow_mapping;
pub mod comparison;
mod contract;
mod errors;
mod pipeline;
mod records;
mod request;
mod result;
mod row_encode;
mod schema_digest;
pub mod table_access;

pub use errors::{ComputeFailure, ComputeFailureCode};
pub use pipeline::canonical_row_hashes_v1;
pub use records::{RecordsParquetSummary, read_records_parquet_v1};
pub use request::{DeclaredSchemaField, ParsedRequest, parse_request};
pub use result::CanonicalRowHashOutput;
