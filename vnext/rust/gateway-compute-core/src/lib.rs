#![forbid(unsafe_code)]

pub mod business_kernel;
pub mod canonical_ipc;
pub mod comparison;
mod records;
pub mod storage_mutation;
pub mod sql_replay;
pub mod table_access;

pub use records::{
    BuiltRecords, RecordsBatchValidator, RecordsParquetSummary, TableFactsInput, TableFactsSource,
    build_blank_records, build_ordered_records, build_standard_records,
    build_standard_records_from_ordered, charge_arrow_batches, digest_facts_core,
    digest_facts_core_json, digest_table_fact, digest_table_fact_json, json_metadata_upper,
    json_size, ordered_metadata_json, standard_metadata_json,
};
