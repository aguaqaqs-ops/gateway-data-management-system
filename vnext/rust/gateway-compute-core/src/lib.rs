#![forbid(unsafe_code)]

mod arrow_extract;
mod arrow_mapping;
mod contract;
mod errors;
mod pipeline;
mod request;
mod result;
mod row_encode;
mod schema_digest;

pub use errors::{ComputeFailure, ComputeFailureCode};
pub use pipeline::canonical_row_hashes_v1;
pub use request::{DeclaredSchemaField, ParsedRequest, parse_request};
pub use result::CanonicalRowHashOutput;
