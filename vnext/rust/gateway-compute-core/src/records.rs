//! Language-neutral reader for S5 comparison-record Parquet artifacts.
//!
//! Publication remains owned by the Python artifact store.  This module only validates the public
//! Parquet schema and recomputes the logical records content digest from Arrow values.

#![allow(clippy::needless_pass_by_value)]

use std::collections::HashMap;

use arrow_array::{
    Array, ArrayRef, BinaryArray, BooleanArray, FixedSizeBinaryArray, Int64Array, ListArray,
    RecordBatch, StringArray, StructArray, UInt64Array,
};
use arrow_schema::{DataType, Field, Fields};
use bytes::Bytes;
use gateway_shared_kernel::{DigestRef, canonicalize_jcs, raw_blob_digest};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde_json::{Map, Value, json};
use std::sync::Arc;

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

pub fn read_records_parquet_v1(raw: &[u8]) -> Result<RecordsParquetSummary, String> {
    if raw.is_empty() {
        return Err("records Parquet is empty".to_string());
    }
    let builder = ParquetRecordBatchReaderBuilder::try_new(Bytes::copy_from_slice(raw))
        .map_err(|error| format!("records Parquet open failed: {error}"))?;
    let schema = builder.schema().clone();
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

    let reader = builder
        .with_batch_size(1024)
        .build()
        .map_err(|error| format!("records Parquet reader build failed: {error}"))?;
    let mut rows = Vec::new();
    for batch in reader {
        let batch = batch.map_err(|error| format!("records Parquet batch failed: {error}"))?;
        for row in 0..batch.num_rows() {
            rows.push(batch_row(&batch, row)?);
        }
    }
    let payload = json!({
        "kind": "comparison-records-content",
        "family": family,
        "schema_version": schema_version,
        "row_diff_detail_policy": row_diff_detail_policy,
        "rows": rows,
    });
    let json = serde_json::to_vec(&payload).map_err(|error| error.to_string())?;
    let canonical = canonicalize_jcs(&json).map_err(|error| error.to_string())?;
    let content_digest = raw_blob_digest(&canonical).map_err(|error| error.to_string())?;
    Ok(RecordsParquetSummary {
        family,
        schema_version,
        row_diff_detail_policy,
        record_count: rows.len(),
        content_digest,
    })
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

fn expected_fields(family: &str) -> Result<Vec<Field>, String> {
    let scalar = DataType::Struct(Fields::from(vec![
        Field::new("kind", DataType::Utf8, false),
        Field::new("text", DataType::Utf8, true),
        Field::new("raw_bytes", DataType::Binary, true),
        Field::new("boolean", DataType::Boolean, true),
        Field::new(
            "items",
            DataType::List(Arc::new(Field::new("element", DataType::Utf8, true))),
            true,
        ),
        Field::new("anomaly_json", DataType::Binary, true),
    ]));
    let value = DataType::Struct(Fields::from(vec![
        Field::new("column_name", DataType::Utf8, false),
        Field::new("value", scalar.clone(), false),
    ]));
    let values = DataType::List(Arc::new(Field::new("element", value.clone(), true)));
    let field_change = DataType::Struct(Fields::from(vec![
        Field::new("column_name", DataType::Utf8, false),
        Field::new("before_value", scalar.clone(), true),
        Field::new("current_value", scalar, true),
    ]));
    let field_changes = DataType::List(Arc::new(Field::new("element", field_change, true)));
    let common = [
        Field::new("table_name", DataType::Utf8, false),
        Field::new("record_kind", DataType::Utf8, false),
        Field::new("row_identity", DataType::FixedSizeBinary(32), true),
        Field::new(
            "changed_columns",
            DataType::List(Arc::new(Field::new("element", DataType::Utf8, true))),
            false,
        ),
        Field::new("before_values", values.clone(), false),
        Field::new("current_values", values, false),
        Field::new(
            "diagnostics",
            DataType::List(Arc::new(Field::new("element", DataType::Utf8, true))),
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

#[cfg(test)]
mod tests {
    use base64::Engine;

    use super::read_records_parquet_v1;

    #[test]
    fn empty_payload_is_rejected_before_reader_creation() {
        assert!(read_records_parquet_v1(&[]).is_err());
    }

    #[test]
    fn python_standard_vector_has_the_same_logical_digest() -> Result<(), String> {
        assert_python_vector(
            include_str!("../../../fixtures/vectors/comparison/records/standard-v1.parquet.b64"),
            "STANDARD",
            "standard-records/v1",
            1,
            "sha256:22bfb26abb0aaeb3d279cdae0614d2733bebbd8cdf8021cfa6751c690db561d4",
        )
    }

    #[test]
    fn python_ordered_vector_has_the_same_logical_digest() -> Result<(), String> {
        assert_python_vector(
            include_str!("../../../fixtures/vectors/comparison/records/ordered-v1.parquet.b64"),
            "ORDERED",
            "ordered-records/v1",
            1,
            "sha256:887e686f96583a28c31f82788608ebd10491b80eb98dc9ab2ada7389ec50468b",
        )
    }

    #[test]
    fn python_blank_vector_has_the_same_logical_digest() -> Result<(), String> {
        assert_python_vector(
            include_str!("../../../fixtures/vectors/comparison/records/blank-v1.parquet.b64"),
            "BLANK",
            "blank-records/v1",
            2,
            "sha256:5f7d095129a4fdbeba84392206fa857740ecdca6b466f9cc8177d2264bf9c17a",
        )
    }

    fn assert_python_vector(
        encoded: &str,
        family: &str,
        schema_version: &str,
        record_count: usize,
        expected_digest: &str,
    ) -> Result<(), String> {
        let raw = base64::engine::general_purpose::STANDARD
            .decode(encoded.trim())
            .map_err(|error| format!("golden Parquet vector must be valid base64: {error}"))?;
        let summary = read_records_parquet_v1(&raw)
            .map_err(|error| format!("Python vector must be readable: {error}"))?;
        assert_eq!(summary.family, family);
        assert_eq!(summary.schema_version, schema_version);
        assert_eq!(summary.row_diff_detail_policy, "FULL_BEFORE_AFTER_VALUES");
        assert_eq!(summary.record_count, record_count);
        assert_eq!(summary.content_digest.as_str(), expected_digest);
        Ok(())
    }
}
