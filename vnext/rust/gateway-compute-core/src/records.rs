//! Comparison-record Arrow schema and streaming logical-content validation.
//!
//! The artifact store owns Parquet I/O and raw-byte identity. This module
//! validates decoded Arrow batches without collecting the records in a table.

#![allow(clippy::needless_pass_by_value)]

use std::collections::HashMap;

use arrow_array::{
    Array, ArrayRef, BinaryArray, BooleanArray, FixedSizeBinaryArray, Int64Array, ListArray,
    RecordBatch, StringArray, StructArray, UInt64Array,
};
use arrow_schema::{DataType, Field, Fields};
use gateway_shared_kernel::{DigestRef, canonicalize_jcs};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::sync::Arc;

mod builders;
mod cache;
mod facts;
mod source;
pub use builders::{BuiltRecords, charge_arrow_batches, restore_records_batches};
pub use cache::{NeutralFacts, facts_schema, export_facts_family, validate_facts_row, validate_cache_metadata};
pub use facts::{
    TableFactsInput, TableFactsSource, digest_facts_core, digest_facts_core_json,
    digest_table_fact, digest_table_fact_json,
};
pub use source::{
    build_blank_records, build_ordered_records, build_standard_records,
    build_standard_records_from_ordered,
};

/// Pre-parse bound for serde values, maps, vectors, strings and one JCS copy.
/// Structural tokens carry a fixed 256-byte allowance so many empty strings
/// are charged even when the source JSON itself is short.
pub fn json_metadata_upper(raw: &str) -> Result<usize, String> {
    let mut structural = 1usize;
    let mut quoted = false;
    let mut escaped = false;
    for byte in raw.bytes() {
        if quoted {
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                quoted = false;
            }
        } else if byte == b'"' {
            quoted = true;
            structural = structural
                .checked_add(1)
                .ok_or("metadata charge overflow")?;
        } else if matches!(byte, b'{' | b'}' | b'[' | b']' | b',' | b':') {
            structural = structural
                .checked_add(1)
                .ok_or("metadata charge overflow")?;
        }
    }
    raw.len()
        .checked_mul(8)
        .and_then(|size| {
            structural
                .checked_mul(256)
                .and_then(|tokens| size.checked_add(tokens))
        })
        .and_then(|size| size.checked_add(4096))
        .ok_or("metadata charge overflow".to_string())
}

struct CountingJsonWriter(usize);

impl std::io::Write for CountingJsonWriter {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.0 = self
            .0
            .checked_add(bytes.len())
            .ok_or_else(|| std::io::Error::other("records JSON size overflow"))?;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

pub fn json_size<T: serde::Serialize + ?Sized>(value: &T) -> Result<usize, String> {
    let mut writer = CountingJsonWriter(0);
    serde_json::to_writer(&mut writer, value).map_err(|error| error.to_string())?;
    Ok(writer.0)
}

pub fn standard_metadata_json(
    result: &crate::comparison::StandardComputation,
) -> Result<String, String> {
    serde_json::to_string(&json!({
        "row_added_count": result.row_added_count,
        "row_deleted_count": result.row_deleted_count,
        "row_modified_count": result.row_modified_count,
        "suppressed_added_count": result.suppressed_added_count,
        "suppressed_deleted_count": result.suppressed_deleted_count,
        "ignored_shared_content_changed": result.ignored_shared_content_changed,
        "record_count": result.records.len(),
    }))
    .map_err(|error| error.to_string())
}

pub fn ordered_metadata_json(
    result: &crate::comparison::OrderedKernelResult,
) -> Result<String, String> {
    serde_json::to_string(&result.facts_metadata).map_err(|error| error.to_string())
}

const METADATA_PREFIX: &str = "gateway-vnext.records.";
const CONTRACT_VERSION: &str = "backend-vnext/comparison-records/v1";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RecordsParquetSummary {
    pub family: String,
    pub schema_version: String,
    pub row_diff_detail_policy: String,
    pub record_count: usize,
    pub content_digest: DigestRef,
}

/// Incremental validator for one records family. The caller must keep the
/// Parquet reader open until `finish`, and only then expose the closure.
pub struct RecordsBatchValidator {
    family: String,
    schema_version: String,
    row_diff_detail_policy: String,
    expected_schema: arrow_schema::SchemaRef,
    hasher: Sha256,
    record_count: usize,
    max_records: usize,
    max_row_bytes: usize,
}

impl RecordsBatchValidator {
    pub fn new(
        schema: arrow_schema::SchemaRef,
        max_records: usize,
        max_row_bytes: usize,
    ) -> Result<Self, String> {
        let metadata = schema.metadata();
        let family = metadata_text(metadata, "family")?;
        let schema_version = metadata_text(metadata, "schema_version")?;
        let row_diff_detail_policy = metadata_text(metadata, "row_diff_detail_policy")?;
        if metadata_text(metadata, "contract_version")? != CONTRACT_VERSION {
            return Err("unsupported records Parquet contract version".to_string());
        }
        let expected_schema_version = match family.as_str() {
            "STANDARD" => "standard-records/v1",
            "ORDERED" => "ordered-records/v1",
            "BLANK" => "blank-records/v1",
            _ => return Err("unsupported records Parquet family".to_string()),
        };
        if schema_version != expected_schema_version {
            return Err("records Parquet schema version does not match family".to_string());
        }
        if !matches!(
            row_diff_detail_policy.as_str(),
            "COUNTS_ONLY" | "CHANGED_COLUMNS" | "FULL_BEFORE_AFTER_VALUES"
        ) {
            return Err("unsupported records Parquet detail policy".to_string());
        }
        validate_schema(&family, &schema)?;
        let mut hasher = Sha256::new();
        hasher.update(b"{\"family\":");
        hasher.update(json_string(&family)?);
        hasher.update(b",\"kind\":\"comparison-records-content\",\"row_diff_detail_policy\":");
        hasher.update(json_string(&row_diff_detail_policy)?);
        hasher.update(b",\"rows\":[");
        Ok(Self {
            family,
            schema_version,
            row_diff_detail_policy,
            expected_schema: schema,
            hasher,
            record_count: 0,
            max_records,
            max_row_bytes,
        })
    }

    pub fn push(&mut self, batch: &RecordBatch) -> Result<(), String> {
        self.push_checked(batch, || Ok(()))
    }

    pub fn push_checked(
        &mut self,
        batch: &RecordBatch,
        mut check: impl FnMut() -> Result<(), String>,
    ) -> Result<(), String> {
        check()?;
        validate_schema(&self.family, &batch.schema())?;
        if batch.schema().metadata() != self.expected_schema.metadata() {
            return Err("records Parquet batch metadata mismatch".to_string());
        }
        let next_count = self
            .record_count
            .checked_add(batch.num_rows())
            .ok_or_else(|| "records per-table limit exceeded".to_string())?;
        if next_count > self.max_records {
            return Err("records per-table limit exceeded".to_string());
        }
        for row in 0..batch.num_rows() {
            if row % 256 == 0 {
                check()?;
            }
            let row_upper = batch
                .columns()
                .iter()
                .try_fold(4096usize, |sum, array| {
                    let size = array.slice(row, 1).to_data().get_slice_memory_size().ok()?;
                    sum.checked_add(size)
                })
                .and_then(|size| size.checked_mul(16))
                .ok_or_else(|| "records JCS row budget overflow".to_string())?;
            if row_upper > self.max_row_bytes {
                return Err("records JCS row budget exceeded".to_string());
            }
            if self.record_count != 0 {
                self.hasher.update(b",");
            }
            let encoded =
                serde_json::to_vec(&batch_row(batch, row)?).map_err(|error| error.to_string())?;
            self.hasher
                .update(canonicalize_jcs(&encoded).map_err(|error| error.to_string())?);
            self.record_count += 1;
        }
        Ok(())
    }

    pub fn finish(mut self) -> Result<RecordsParquetSummary, String> {
        self.hasher.update(b"],\"schema_version\":");
        self.hasher.update(json_string(&self.schema_version)?);
        self.hasher.update(b"}");
        let digest = self.hasher.finalize();
        let content_digest =
            DigestRef::from_raw_digest(&digest).map_err(|error| error.to_string())?;
        Ok(RecordsParquetSummary {
            family: self.family,
            schema_version: self.schema_version,
            row_diff_detail_policy: self.row_diff_detail_policy,
            record_count: self.record_count,
            content_digest,
        })
    }
}

fn json_string(value: &str) -> Result<Vec<u8>, String> {
    let encoded = serde_json::to_vec(value).map_err(|error| error.to_string())?;
    canonicalize_jcs(&encoded).map_err(|error| error.to_string())
}

fn metadata_text(metadata: &HashMap<String, String>, name: &str) -> Result<String, String> {
    metadata
        .get(&format!("{METADATA_PREFIX}{name}"))
        .cloned()
        .ok_or_else(|| format!("records Parquet metadata is missing {name}"))
}

fn validate_schema(family: &str, schema: &arrow_schema::Schema) -> Result<(), String> {
    let expected = expected_fields(family)?;
    if schema.fields().len() != expected.len() {
        return Err("records Parquet schema fields do not match family".to_string());
    }
    for (actual, expected) in schema.fields().iter().zip(expected.iter()) {
        if actual.name() != expected.name()
            || actual.is_nullable() != expected.is_nullable()
            || actual.data_type() != expected.data_type()
        {
            return Err(format!(
                "records Parquet field {} does not match expected {:?}, got {:?}",
                actual.name(),
                expected,
                actual
            ));
        }
    }
    Ok(())
}

pub(crate) fn expected_fields(family: &str) -> Result<Vec<Field>, String> {
    let scalar = DataType::Struct(Fields::from(vec![
        Field::new("kind", DataType::Utf8, false),
        Field::new("text", DataType::Utf8, true),
        Field::new("raw_bytes", DataType::Binary, true),
        Field::new("boolean", DataType::Boolean, true),
        Field::new(
            "items",
            DataType::List(Arc::new(Field::new("item", DataType::Utf8, true))),
            true,
        ),
        Field::new("anomaly_json", DataType::Binary, true),
    ]));
    let value = DataType::Struct(Fields::from(vec![
        Field::new("column_name", DataType::Utf8, false),
        Field::new("value", scalar.clone(), false),
    ]));
    let values = DataType::List(Arc::new(Field::new("item", value.clone(), true)));
    let field_change = DataType::Struct(Fields::from(vec![
        Field::new("column_name", DataType::Utf8, false),
        Field::new("before_value", scalar.clone(), true),
        Field::new("current_value", scalar, true),
    ]));
    let field_changes = DataType::List(Arc::new(Field::new("item", field_change, true)));
    let common = [
        Field::new("table_name", DataType::Utf8, false),
        Field::new("record_kind", DataType::Utf8, false),
        Field::new("row_identity", DataType::FixedSizeBinary(32), true),
        Field::new(
            "changed_columns",
            DataType::List(Arc::new(Field::new("item", DataType::Utf8, true))),
            false,
        ),
        Field::new("before_values", values.clone(), false),
        Field::new("current_values", values, false),
        Field::new(
            "diagnostics",
            DataType::List(Arc::new(Field::new("item", DataType::Utf8, true))),
            false,
        ),
    ];
    match family {
        "STANDARD" => Ok(vec![
            common[0].clone(),
            common[1].clone(),
            common[2].clone(),
            common[3].clone(),
            common[4].clone(),
            common[5].clone(),
            Field::new("field_changes", field_changes, false),
            common[6].clone(),
        ]),
        "ORDERED" => Ok(vec![
            common[0].clone(),
            common[1].clone(),
            Field::new("semantic_kind", DataType::Utf8, false),
            Field::new("entity_key_kind", DataType::Utf8, false),
            common[2].clone(),
            Field::new("before_position", DataType::Int64, true),
            Field::new("current_position", DataType::Int64, true),
            common[3].clone(),
            common[4].clone(),
            common[5].clone(),
            common[6].clone(),
        ]),
        "BLANK" => {
            let interval = DataType::Struct(Fields::from(vec![
                Field::new("before_start", DataType::Int64, true),
                Field::new("before_end", DataType::Int64, true),
                Field::new("current_start", DataType::Int64, true),
                Field::new("current_end", DataType::Int64, true),
                Field::new("row_count", DataType::Int64, false),
                Field::new("interval_digest", DataType::FixedSizeBinary(32), true),
            ]));
            Ok(vec![
                common[0].clone(),
                common[1].clone(),
                Field::new("semantic_kind", DataType::Utf8, false),
                Field::new("interval", interval, false),
                Field::new("before_occupancy", DataType::Int64, false),
                Field::new("current_occupancy", DataType::Int64, false),
                common[6].clone(),
            ])
        }
        _ => Err("unsupported records Parquet family".to_string()),
    }
}

fn batch_row(batch: &RecordBatch, row: usize) -> Result<Value, String> {
    let mut object = Map::new();
    for (index, field) in batch.schema().fields().iter().enumerate() {
        object.insert(field.name().clone(), array_value(batch.column(index), row)?);
    }
    Ok(Value::Object(object))
}

fn array_value(array: &ArrayRef, row: usize) -> Result<Value, String> {
    if array.is_null(row) {
        return Ok(Value::Null);
    }
    match array.data_type() {
        DataType::Boolean => Ok(Value::Bool(
            array
                .as_any()
                .downcast_ref::<BooleanArray>()
                .ok_or_else(|| "boolean array downcast failed".to_string())?
                .value(row),
        )),
        DataType::Utf8 => Ok(Value::String(
            array
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or_else(|| "string array downcast failed".to_string())?
                .value(row)
                .to_string(),
        )),
        DataType::Binary => Ok(bytes_value(
            array
                .as_any()
                .downcast_ref::<BinaryArray>()
                .ok_or_else(|| "binary array downcast failed".to_string())?
                .value(row),
        )),
        DataType::FixedSizeBinary(_) => Ok(bytes_value(
            array
                .as_any()
                .downcast_ref::<FixedSizeBinaryArray>()
                .ok_or_else(|| "fixed binary array downcast failed".to_string())?
                .value(row),
        )),
        DataType::Int64 => Ok(json!(
            array
                .as_any()
                .downcast_ref::<Int64Array>()
                .ok_or_else(|| "int64 array downcast failed".to_string())?
                .value(row)
        )),
        DataType::UInt64 => Ok(json!(
            array
                .as_any()
                .downcast_ref::<UInt64Array>()
                .ok_or_else(|| "uint64 array downcast failed".to_string())?
                .value(row)
        )),
        DataType::List(_) => {
            let list = array
                .as_any()
                .downcast_ref::<ListArray>()
                .ok_or_else(|| "list array downcast failed".to_string())?;
            let values = list.value(row);
            let mut result = Vec::with_capacity(values.len());
            for index in 0..values.len() {
                result.push(array_value(&values, index)?);
            }
            Ok(Value::Array(result))
        }
        DataType::Struct(_) => {
            let structure = array
                .as_any()
                .downcast_ref::<StructArray>()
                .ok_or_else(|| "struct array downcast failed".to_string())?;
            let mut result = Map::new();
            for (index, field) in structure.fields().iter().enumerate() {
                result.insert(
                    field.name().clone(),
                    array_value(structure.column(index), row)?,
                );
            }
            Ok(Value::Object(result))
        }
        other => Err(format!("unsupported records Parquet Arrow type: {other:?}")),
    }
}

fn bytes_value(bytes: &[u8]) -> Value {
    json!({"bytes_hex": hex_encode(bytes)})
}

fn hex_encode(bytes: &[u8]) -> String {
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        result.push_str(&format!("{byte:02x}"));
    }
    result
}
