//! Records views directly over B's retained Arrow batches and row locators.

use std::collections::HashSet;
use std::sync::Arc;

use arrow_array::{Array, LargeStringArray, RecordBatch, StringArray};
use gateway_shared_kernel::{TypedScalar, canonicalize_jcs};
use serde_json::{Value, json};

use crate::comparison::{
    KernelContext, OrderedKernelResult, RowLocation, StandardComputation, StandardRecordRef,
};
use crate::comparison::kernel::sort_indices_checked;
use crate::comparison::ordered::{scalar_type, declared_type, typed_value};

use super::builders::{BuiltRecords, build_records_arrow};

struct SortEntry {
    index: usize,
    kind: String,
    identity: String,
    before_position: i64,
    current_position: i64,
    full_jcs: Vec<u8>,
}

/// Build STANDARD from B's facts-order locators, including its degraded branch.
/// No Python records or JSON bulk input enters this path.
pub fn build_standard_records(
    table_name: &str,
    result: &StandardComputation,
    detail_policy: &str,
    max_records: usize,
    max_sort_bytes: usize,
    max_output_bytes: usize,
    context: &Arc<KernelContext>,
    external_owner: Option<Arc<dyn std::any::Any + Send + Sync>>,
) -> Result<BuiltRecords, String> {
    build_family(
        "STANDARD", result.records.len(), detail_policy, max_records,
        max_sort_bytes, max_output_bytes, context, external_owner,
        |index, detail| {
            standard_row(table_name, &result.records[index], &result.before_batches,
                &result.current_batches, detail)
        },
    )
}

pub fn build_standard_records_from_ordered(
    table_name: &str,
    result: &OrderedKernelResult,
    detail_policy: &str,
    max_records: usize,
    max_sort_bytes: usize,
    max_output_bytes: usize,
    context: &Arc<KernelContext>,
    external_owner: Option<Arc<dyn std::any::Any + Send + Sync>>,
) -> Result<BuiltRecords, String> {
    build_family(
        "STANDARD", result.standard_records.len(), detail_policy, max_records,
        max_sort_bytes, max_output_bytes, context, external_owner,
        |index, detail| {
            standard_row(table_name, &result.standard_records[index], &result.before_batches,
                &result.current_batches, detail)
        },
    )
}

pub fn build_ordered_records(
    table_name: &str,
    result: &OrderedKernelResult,
    detail_policy: &str,
    max_records: usize,
    max_sort_bytes: usize,
    max_output_bytes: usize,
    context: &Arc<KernelContext>,
    external_owner: Option<Arc<dyn std::any::Any + Send + Sync>>,
) -> Result<BuiltRecords, String> {
    build_family(
        "ORDERED", result.ordered_records.len(), detail_policy, max_records,
        max_sort_bytes, max_output_bytes, context, external_owner,
        |index, detail| {
            let record = &result.ordered_records[index];
            let full = detail == "FULL_BEFORE_AFTER_VALUES";
            Ok(json!({
                "table_name": table_name,
                "record_kind": record.kind,
                "semantic_kind": record.semantic_kind,
                "entity_key_kind": record.entity_key_kind,
                "row_identity": digest_bytes(Some(&record.row_identity))?,
                "before_position": record.before_position,
                "current_position": record.current_position,
                "changed_columns": if detail == "COUNTS_ONLY" { &[][..] } else { &record.changed_columns },
                "before_values": if full { values_at(&result.before_batches, record.before, &record.value_columns)? } else { Vec::new() },
                "current_values": if full { values_at(&result.current_batches, record.current, &record.value_columns)? } else { Vec::new() },
                "diagnostics": [],
            }))
        },
    )
}

pub fn build_blank_records(
    table_name: &str,
    result: &OrderedKernelResult,
    detail_policy: &str,
    max_records: usize,
    max_sort_bytes: usize,
    max_output_bytes: usize,
    context: &Arc<KernelContext>,
    external_owner: Option<Arc<dyn std::any::Any + Send + Sync>>,
) -> Result<BuiltRecords, String> {
    build_family(
        "BLANK", result.blank_records.len(), detail_policy, max_records,
        max_sort_bytes, max_output_bytes, context, external_owner,
        |index, _| {
            let record = &result.blank_records[index];
            Ok(json!({
                "table_name": table_name,
                "record_kind": record.kind,
                "semantic_kind": record.semantic_kind,
                "interval": {
                    "before_start": record.interval.before_start,
                    "before_end": record.interval.before_end,
                    "current_start": record.interval.current_start,
                    "current_end": record.interval.current_end,
                    "row_count": record.interval.row_count,
                    "interval_digest": digest_bytes(Some(&record.interval.interval_digest))?,
                },
                "before_occupancy": record.before_occupancy,
                "current_occupancy": record.current_occupancy,
                "diagnostics": [],
            }))
        },
    )
}

fn build_family(
    family: &str,
    count: usize,
    detail_policy: &str,
    max_records: usize,
    max_sort_bytes: usize,
    max_output_bytes: usize,
    context: &Arc<KernelContext>,
    external_owner: Option<Arc<dyn std::any::Any + Send + Sync>>,
    row: impl Fn(usize, &str) -> Result<Value, String>,
) -> Result<BuiltRecords, String> {
    if count > max_records {
        return Err("records per-table limit exceeded".to_string());
    }
    let _sort_lease = context.reserve(max_sort_bytes).map_err(|error| error.to_string())?;
    let mut entries = Vec::with_capacity(count);
    let mut actual_sort_bytes = 0usize;
    for index in 0..count {
        context.check().map_err(|error| error.to_string())?;
        let full = row(index, "FULL_BEFORE_AFTER_VALUES")?;
        let encoded = serde_json::to_vec(&full).map_err(|error| error.to_string())?;
        let full_jcs = canonicalize_jcs(&encoded).map_err(|error| error.to_string())?;
        actual_sort_bytes = actual_sort_bytes.checked_add(full_jcs.len() * 2 + 256)
            .ok_or_else(|| "records sort budget overflow".to_string())?;
        if actual_sort_bytes > max_sort_bytes {
            return Err("records sort budget exceeded".to_string());
        }
        entries.push(SortEntry {
            index,
            kind: text_field(&full, "record_kind")?.to_string(),
            identity: full.get("row_identity").and_then(|value| value.get("bytes_hex"))
                .and_then(Value::as_str).unwrap_or("").to_string(),
            before_position: int_field(&full, "before_position"),
            current_position: int_field(&full, "current_position"),
            full_jcs,
        });
    }
    let order = sort_indices_checked(&entries, context, |left, right| {
        left.kind.cmp(&right.kind)
            .then_with(|| left.identity.cmp(&right.identity))
            .then_with(|| left.before_position.cmp(&right.before_position))
            .then_with(|| left.current_position.cmp(&right.current_position))
            .then_with(|| left.full_jcs.cmp(&right.full_jcs))
    }).map_err(|error| error.to_string())?;
    let mut seen = HashSet::with_capacity(count);
    let rows = order.into_iter().map(|slot| {
        context.check().map_err(|error| error.to_string())?;
        let value = row(entries[slot].index, detail_policy)?;
        let encoded = canonicalize_jcs(&serde_json::to_vec(&value)
            .map_err(|error| error.to_string())?).map_err(|error| error.to_string())?;
        if !seen.insert(encoded) {
            return Err("records family contains duplicate logical rows".to_string());
        }
        Ok(value)
    });
    build_records_arrow(family, detail_policy, rows, max_records, max_output_bytes, context, external_owner)
}

fn standard_row(
    table_name: &str,
    record: &StandardRecordRef,
    before: &[RecordBatch],
    current: &[RecordBatch],
    detail: &str,
) -> Result<Value, String> {
    let full = detail == "FULL_BEFORE_AFTER_VALUES";
    let changes = if full {
        record.changed_columns.iter().map(|column| {
            Ok(json!({
                "column_name": column,
                "before_value": scalar_at(before, record.before, column)?,
                "current_value": scalar_at(current, record.current, column)?,
            }))
        }).collect::<Result<Vec<_>, String>>()?
    } else { Vec::new() };
    Ok(json!({
        "table_name": table_name,
        "record_kind": record.kind.contract_name(),
        "row_identity": digest_bytes(record.row_identity.as_deref())?,
        "changed_columns": if detail == "COUNTS_ONLY" { &[][..] } else { &record.changed_columns },
        "before_values": if full { values_at(before, record.before, &record.value_columns)? } else { Vec::new() },
        "current_values": if full { values_at(current, record.current, &record.value_columns)? } else { Vec::new() },
        "field_changes": changes,
        "diagnostics": record.diagnostics,
    }))
}

fn values_at(
    batches: &[RecordBatch],
    location: Option<RowLocation>,
    columns: &[String],
) -> Result<Vec<Value>, String> {
    let Some(location) = location else { return Ok(Vec::new()) };
    columns.iter().map(|column| {
        Ok(json!({"column_name": column, "value": scalar_at(batches, Some(location), column)?}))
    }).collect()
}

fn scalar_at(
    batches: &[RecordBatch],
    location: Option<RowLocation>,
    column: &str,
) -> Result<Value, String> {
    let Some(location) = location else { return Ok(Value::Null) };
    let batch = batches.get(location.batch).ok_or("records row location invalid")?;
    if location.row >= batch.num_rows() {
        return Err("records row location invalid".to_string());
    }
    let index = batch.schema().fields().iter().position(|field| field.name() == column)
        .ok_or_else(|| "records column is missing".to_string())?;
    let field = batch.schema().field(index).clone();
    let array = batch.column(index);
    if array.is_null(location.row) {
        return Ok(scalar_object("null", Value::Null, Value::Null, Value::Null, Value::Null, Value::Null));
    }
    let spelling = scalar_type(&field).map_err(|error| error.to_string())?;
    if spelling.trim_start().to_ascii_lowercase().starts_with("set(") {
        let text = if let Some(values) = array.as_any().downcast_ref::<StringArray>() {
            values.value(location.row)
        } else if let Some(values) = array.as_any().downcast_ref::<LargeStringArray>() {
            values.value(location.row)
        } else { return Err("records SET Arrow type mismatch".to_string()) };
        let items: Vec<&str> = if text.is_empty() { Vec::new() } else { text.split(',').collect() };
        return Ok(scalar_object("set", Value::Null, Value::Null, Value::Null, json!(items), Value::Null));
    }
    let declared = declared_type(&spelling, field.data_type()).map_err(|error| error.to_string())?;
    let typed = typed_value(array.as_ref(), location.row, &declared)
        .map_err(|error| error.to_string())?;
    let empty = Value::Null;
    match typed {
        TypedScalar::Null(_) => Ok(scalar_object("null", empty.clone(), empty.clone(), empty.clone(), empty.clone(), empty)),
        TypedScalar::Boolean(value) => Ok(scalar_object("boolean", Value::Null, Value::Null, json!(value.value), Value::Null, Value::Null)),
        TypedScalar::SignedInteger(value) => Ok(text_scalar("signed-integer", value.decimal)),
        TypedScalar::UnsignedInteger(value) => Ok(text_scalar("unsigned-integer", value.decimal)),
        TypedScalar::Decimal(value) => Ok(text_scalar("decimal", value.decimal)),
        TypedScalar::Float32(value) => Ok(text_scalar("float32", if value.bits_hex == "80000000" { "00000000".to_string() } else { value.bits_hex })),
        TypedScalar::Float64(value) => Ok(text_scalar("float64", if value.bits_hex == "8000000000000000" { "0000000000000000".to_string() } else { value.bits_hex })),
        TypedScalar::String(value) => Ok(text_scalar("string", value.text)),
        TypedScalar::Binary(value) => Ok(raw_scalar("binary", &value.raw_bytes)),
        TypedScalar::Bit(value) => Ok(raw_scalar("bit", &value.raw_bytes)),
        TypedScalar::Date(value) => Ok(text_scalar("date", value.text)),
        TypedScalar::DateTime(value) => Ok(text_scalar("datetime", value.text)),
        TypedScalar::Timestamp(value) => Ok(text_scalar("timestamp", value.text)),
        TypedScalar::TimeDuration(value) => Ok(text_scalar("time-duration", value.text)),
        TypedScalar::Anomaly(_) => Err("records source anomaly requires canonical envelope".to_string()),
    }
}

fn scalar_object(kind: &str, text: Value, raw_bytes: Value, boolean: Value, items: Value, anomaly_json: Value) -> Value {
    json!({"kind": kind, "text": text, "raw_bytes": raw_bytes, "boolean": boolean,
        "items": items, "anomaly_json": anomaly_json})
}

fn text_scalar(kind: &str, text: String) -> Value {
    scalar_object(kind, json!(text), Value::Null, Value::Null, Value::Null, Value::Null)
}

fn raw_scalar(kind: &str, bytes: &[u8]) -> Value {
    scalar_object(kind, Value::Null, json!({"bytes_hex": hex_bytes(bytes)}), Value::Null, Value::Null, Value::Null)
}

fn digest_bytes(value: Option<&str>) -> Result<Value, String> {
    let Some(value) = value else { return Ok(Value::Null) };
    let hex = value.strip_prefix("sha256:").ok_or("records digest prefix is invalid")?;
    if hex.len() != 64 || !hex.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) {
        return Err("records digest hex is invalid".to_string());
    }
    Ok(json!({"bytes_hex": hex}))
}

fn hex_bytes(bytes: &[u8]) -> String {
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        use std::fmt::Write;
        let _ = write!(&mut result, "{byte:02x}");
    }
    result
}

fn text_field<'a>(value: &'a Value, name: &str) -> Result<&'a str, String> {
    value.get(name).and_then(Value::as_str)
        .ok_or_else(|| format!("records {name} is missing"))
}

fn int_field(value: &Value, name: &str) -> i64 {
    value.get(name).and_then(Value::as_i64).unwrap_or(0)
}
