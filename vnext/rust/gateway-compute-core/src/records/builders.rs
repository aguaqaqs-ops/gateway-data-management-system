//! Bounded Arrow builders for the three comparison-record families.

use std::sync::{Arc, Mutex};

use arrow_array::{Array, RecordBatch, make_array};
use arrow_array::builder::{
    ArrayBuilder, BinaryBuilder, BooleanBuilder, FixedSizeBinaryBuilder, Int64Builder,
    ListBuilder, StringBuilder, StructBuilder, make_builder,
};
use arrow_schema::{DataType, Field, Schema, SchemaRef};
use arrow_buffer::{BooleanBuffer, Buffer, NullBuffer};
use arrow_data::ArrayData;
use bytes::Bytes;
use gateway_shared_kernel::{DigestRef, canonicalize_jcs};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::comparison::{KernelContext, KernelLease};

use super::{CONTRACT_VERSION, METADATA_PREFIX, expected_fields, json_size};

pub(super) struct BoundedRow {
    pub(super) value: Value,
    pub(super) _scratch: KernelLease,
}

pub struct BuiltRecords {
    pub schema: SchemaRef,
    pub batches: Vec<RecordBatch>,
    pub record_count: usize,
    pub content_digest: DigestRef,
    _charge: Arc<OutputCharge>,
}

struct OutputCharge {
    lease: Mutex<KernelLease>,
    _external_owner: Option<Arc<dyn std::any::Any + Send + Sync>>,
}

/// Arrow's buffer retains this owner even after a batch is exported through
/// the C Stream and the original result handle is closed. No raw pointers or
/// custom deallocator are used by first-party code.
struct ChargedBuffer {
    original: Buffer,
    _charge: Arc<OutputCharge>,
}

impl AsRef<[u8]> for ChargedBuffer {
    fn as_ref(&self) -> &[u8] {
        self.original.as_slice()
    }
}

pub fn records_schema(family: &str, detail_policy: &str) -> Result<SchemaRef, String> {
    let schema_version = match family {
        "STANDARD" => "standard-records/v1",
        "ORDERED" => "ordered-records/v1",
        "BLANK" => "blank-records/v1",
        _ => return Err("unsupported records family".to_string()),
    };
    if !matches!(detail_policy, "COUNTS_ONLY" | "CHANGED_COLUMNS" | "FULL_BEFORE_AFTER_VALUES") {
        return Err("unsupported records detail policy".to_string());
    }
    let metadata = [
        ("family", family),
        ("schema_version", schema_version),
        ("row_diff_detail_policy", detail_policy),
        ("contract_version", CONTRACT_VERSION),
    ]
    .into_iter()
    .map(|(key, value)| (format!("{METADATA_PREFIX}{key}"), value.to_string()))
    .collect();
    Ok(Arc::new(Schema::new_with_metadata(expected_fields(family)?, metadata)))
}

/// Build exact Arrow schema from a stream of one-row objects. The iterator is
/// evaluated once, in logical artifact order; no whole-table row collection is
/// made. The caller owns the row sort, duplicate check, and output budget.
pub fn build_records_arrow(
    family: &str,
    detail_policy: &str,
    rows: impl IntoIterator<Item = Result<BoundedRow, String>>,
    max_records: usize,
    max_output_bytes: usize,
    context: &Arc<KernelContext>,
    external_owner: Option<Arc<dyn std::any::Any + Send + Sync>>,
) -> Result<BuiltRecords, String> {
    let mut lease = context.reserve(0).map_err(|error| error.to_string())?;
    let schema = records_schema(family, detail_policy)?;
    let mut batches = Vec::new();
    let mut builders = new_builders(&schema);
    let mut record_count = 0usize;
    let mut batch_count = 0usize;
    let mut hasher = Sha256::new();
    hasher.update(b"{\"family\":\"");
    hasher.update(family.as_bytes());
    hasher.update(b"\",\"kind\":\"comparison-records-content\",\"row_diff_detail_policy\":\"");
    hasher.update(detail_policy.as_bytes());
    hasher.update(b"\",\"rows\":[");
    for row in rows {
        context.check().map_err(|error| error.to_string())?;
        let row = row?;
        record_count = record_count.checked_add(1)
            .ok_or_else(|| "records count overflow".to_string())?;
        if record_count > max_records {
            return Err("records per-table limit exceeded".to_string());
        }
        let encoded_size = json_size(&row.value)?;
        let row_charge = encoded_size.checked_mul(3)
            .and_then(|size| schema.fields().len().checked_mul(1024)
                .and_then(|headers| size.checked_add(headers)))
            .and_then(|size| size.checked_add(4096))
            .ok_or("records output budget overflow")?;
        if lease.charged_bytes().checked_add(row_charge)
            .ok_or("records output budget overflow")? > max_output_bytes {
            return Err("records output budget exceeded".to_string());
        }
        lease.grow(row_charge).map_err(|error| error.to_string())?;
        if record_count != 1 { hasher.update(b","); }
        let encoded = serde_json::to_vec(&row.value).map_err(|error| error.to_string())?;
        hasher.update(canonicalize_jcs(&encoded).map_err(|error| error.to_string())?);
        let object = row.value.as_object().ok_or_else(|| "records row must be an object".to_string())?;
        for (field, builder) in schema.fields().iter().zip(&mut builders) {
            let value = object.get(field.name())
                .ok_or_else(|| format!("records field {} is missing", field.name()))?;
            append_value(builder.as_mut(), field, value)?;
        }
        drop(row);
        batch_count += 1;
        if batch_count == 1024 {
            batches.push(finish_batch(Arc::clone(&schema), &mut builders)?);
            builders = new_builders(&schema);
            batch_count = 0;
            lease.shrink_to(retained_charge(&batches, &schema)?)
                .map_err(|error| error.to_string())?;
        }
    }
    if batch_count != 0 {
        batches.push(finish_batch(Arc::clone(&schema), &mut builders)?);
    }
    let schema_version = schema.metadata().get(&format!("{METADATA_PREFIX}schema_version"))
        .ok_or("records schema version is missing")?;
    hasher.update(b"],\"schema_version\":\"");
    hasher.update(schema_version.as_bytes());
    hasher.update(b"\"}");
    let content_digest = DigestRef::from_raw_digest(&hasher.finalize())
        .map_err(|error| error.to_string())?;
    let retained = retained_charge(&batches, &schema)?;
    if retained > max_output_bytes {
        return Err("records output budget exceeded".to_string());
    }
    // Rebinding retains another bounded set of headers, not a second payload.
    // The per-batch header allowance remains in the output lease.
    let charge = Arc::new(OutputCharge { lease: Mutex::new(lease), _external_owner: external_owner });
    let batches = batches.into_iter().map(|batch| charged_batch(batch, &charge))
        .collect::<Result<Vec<_>, _>>()?;
    charge.lease.lock().map_err(|_| "records charge lock poisoned".to_string())?
        .shrink_to(retained).map_err(|error| error.to_string())?;
    Ok(BuiltRecords { schema, batches, record_count, content_digest, _charge: charge })
}

fn retained_charge(batches: &[RecordBatch], schema: &Schema) -> Result<usize, String> {
    let data = batches.iter().flat_map(RecordBatch::columns).try_fold(0usize, |sum, array| {
        sum.checked_add(array.to_data().get_slice_memory_size().ok()?)
    }).ok_or("records output size overflow")?;
    let headers = batches.len().checked_mul(schema.fields().len())
        .and_then(|count| count.checked_mul(512))
        .and_then(|size| size.checked_add(if batches.is_empty() { 0 } else { 4096 }))
        .ok_or("records output header overflow")?;
    data.checked_add(headers).ok_or("records output retained overflow".to_string())
}

fn charged_batch(batch: RecordBatch, charge: &Arc<OutputCharge>) -> Result<RecordBatch, String> {
    let schema = batch.schema();
    let columns = batch.columns().iter().map(|array| {
        let data = attach_charge(array.to_data(), charge)?;
        Ok(make_array(data))
    }).collect::<Result<Vec<_>, String>>()?;
    RecordBatch::try_new(schema, columns).map_err(|error| error.to_string())
}

fn attach_charge(data: ArrayData, charge: &Arc<OutputCharge>) -> Result<ArrayData, String> {
    let buffers = data.buffers().iter().map(|buffer| charged_buffer(buffer, charge)).collect();
    let nulls = data.nulls().map(|nulls| {
        NullBuffer::new(BooleanBuffer::new(
            charged_buffer(nulls.buffer(), charge), nulls.offset(), nulls.len()
        ))
    });
    let children = data.child_data().iter().cloned()
        .map(|child| attach_charge(child, charge))
        .collect::<Result<Vec<_>, _>>()?;
    data.into_builder().buffers(buffers).nulls(nulls).child_data(children)
        .build().map_err(|error| error.to_string())
}

fn charged_buffer(buffer: &Buffer, charge: &Arc<OutputCharge>) -> Buffer {
    Buffer::from(Bytes::from_owner(ChargedBuffer {
        original: buffer.clone(), _charge: Arc::clone(charge),
    }))
}

fn new_builders(schema: &Schema) -> Vec<Box<dyn ArrayBuilder>> {
    schema.fields().iter().map(|field| make_builder(field.data_type(), 1024)).collect()
}

fn finish_batch(schema: SchemaRef, builders: &mut [Box<dyn ArrayBuilder>]) -> Result<RecordBatch, String> {
    let columns = builders.iter_mut().map(|builder| builder.finish()).collect();
    RecordBatch::try_new(schema, columns).map_err(|error| error.to_string())
}

fn append_value(builder: &mut dyn ArrayBuilder, field: &Field, value: &Value) -> Result<(), String> {
    if value.is_null() && !field.is_nullable() {
        return Err(format!("records field {} cannot be null", field.name()));
    }
    match field.data_type() {
        DataType::Utf8 => {
            let builder = downcast::<StringBuilder>(builder)?;
            if let Some(text) = value.as_str() { builder.append_value(text); }
            else if value.is_null() { builder.append_null(); }
            else { return Err("records string value has wrong type".to_string()); }
        }
        DataType::Binary => {
            let builder = downcast::<BinaryBuilder>(builder)?;
            if value.is_null() { builder.append_null(); }
            else { builder.append_value(bytes_value(value)?); }
        }
        DataType::FixedSizeBinary(width) => {
            let builder = downcast::<FixedSizeBinaryBuilder>(builder)?;
            if value.is_null() { builder.append_null(); }
            else {
                let bytes = bytes_value(value)?;
                if bytes.len() != usize::try_from(*width).map_err(|error| error.to_string())? {
                    return Err("records fixed binary width mismatch".to_string());
                }
                builder.append_value(bytes).map_err(|error| error.to_string())?;
            }
        }
        DataType::Boolean => {
            let builder = downcast::<BooleanBuilder>(builder)?;
            if let Some(boolean) = value.as_bool() { builder.append_value(boolean); }
            else if value.is_null() { builder.append_null(); }
            else { return Err("records boolean value has wrong type".to_string()); }
        }
        DataType::Int64 => {
            let builder = downcast::<Int64Builder>(builder)?;
            if let Some(integer) = value.as_i64() { builder.append_value(integer); }
            else if value.is_null() { builder.append_null(); }
            else { return Err("records integer value has wrong type".to_string()); }
        }
        DataType::List(element) => {
            let builder = downcast::<ListBuilder<Box<dyn ArrayBuilder>>>(builder)?;
            if let Some(items) = value.as_array() {
                for item in items {
                    append_value(builder.values().as_mut(), element, item)?;
                }
                builder.append(true);
            } else if value.is_null() { builder.append(false); }
            else { return Err("records list value has wrong type".to_string()); }
        }
        DataType::Struct(fields) => {
            let builder = downcast::<StructBuilder>(builder)?;
            let object = value.as_object();
            if object.is_none() && !value.is_null() {
                return Err("records struct value has wrong type".to_string());
            }
            for (index, child) in fields.iter().enumerate() {
                // A null *parent* struct masks its children. Keep physically
                // non-null child fields valid (notably Scalar.kind) while the
                // parent validity bit carries the semantic null.
                let placeholder = masked_child_value(child);
                let child_value = if let Some(object) = object {
                    object.get(child.name()).ok_or_else(||
                        format!("records field {} is missing", child.name()))?
                } else { &placeholder };
                append_value(builder.field_builders_mut()[index].as_mut(), child, child_value)?;
            }
            builder.append(object.is_some());
        }
        other => return Err(format!("unsupported records Arrow type {other:?}")),
    }
    Ok(())
}

fn masked_child_value(field: &Field) -> Value {
    match field.data_type() {
        DataType::Utf8 => Value::String(String::new()),
        DataType::Binary => serde_json::json!({"bytes_hex": ""}),
        DataType::FixedSizeBinary(width) => serde_json::json!({
            "bytes_hex": "00".repeat(usize::try_from(*width).unwrap_or(0))
        }),
        DataType::Boolean => Value::Bool(false),
        DataType::Int64 => serde_json::json!(0),
        DataType::List(_) => Value::Array(Vec::new()),
        DataType::Struct(fields) => Value::Object(fields.iter().map(|child| (
            child.name().clone(), masked_child_value(child)
        )).collect()),
        _ => Value::Null,
    }
}

fn downcast<T: ArrayBuilder + 'static>(builder: &mut dyn ArrayBuilder) -> Result<&mut T, String> {
    builder.as_any_mut().downcast_mut::<T>()
        .ok_or_else(|| "records Arrow builder type mismatch".to_string())
}

fn bytes_value(value: &Value) -> Result<Vec<u8>, String> {
    let hex = value.get("bytes_hex").and_then(Value::as_str)
        .ok_or_else(|| "records binary value must contain bytes_hex".to_string())?;
    if hex.len() % 2 != 0 || !hex.is_ascii() {
        return Err("records bytes_hex is invalid".to_string());
    }
    (0..hex.len()).step_by(2).map(|index| {
        u8::from_str_radix(&hex[index..index + 2], 16)
            .map_err(|error| error.to_string())
    }).collect()
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::AtomicBool;

    use arrow_array::{Array, ListArray, StringArray, StructArray};
    use serde_json::json;

    use super::*;

    #[test]
    fn nullable_parent_struct_and_sql_null_scalar_remain_distinct() {
        let context = Arc::new(KernelContext::new(
            16 * 1024 * 1024, Arc::new(AtomicBool::new(false)), None,
        ));
        let starting = context.remaining_bytes();
        let sql_null = json!({
            "kind": "null", "text": null, "raw_bytes": null,
            "boolean": null, "items": null, "anomaly_json": null,
        });
        let row = json!({
            "table_name": "t", "record_kind": "ROW_MODIFIED",
            "row_identity": {"bytes_hex": "00".repeat(32)},
            "changed_columns": ["value"],
            "before_values": [], "current_values": [],
            "field_changes": [{
                "column_name": "value", "before_value": null,
                "current_value": sql_null,
            }],
            "diagnostics": [],
        });
        let built = build_records_arrow(
            "STANDARD", "FULL_BEFORE_AFTER_VALUES", [Ok(BoundedRow {
                value: row,
                _scratch: context.reserve(4096).expect("row scratch"),
            })], 1,
            1024 * 1024, &context, None,
        ).expect("build nullable field change");
        let batch = built.batches[0].clone();
        let changes = batch.column(6).as_any().downcast_ref::<ListArray>().expect("changes");
        let values = changes.values();
        let change = values.as_any().downcast_ref::<StructArray>().expect("change struct");
        let before = change.column(1).as_any().downcast_ref::<StructArray>().expect("before");
        let current = change.column(2).as_any().downcast_ref::<StructArray>().expect("current");
        assert!(before.is_null(0));
        assert!(!current.is_null(0));
        assert_eq!(
            current.column(0).as_any().downcast_ref::<StringArray>().expect("kind").value(0),
            "null",
        );
        drop(built);
        assert!(context.remaining_bytes() < starting);
        drop(batch);
        assert_eq!(context.remaining_bytes(), starting);
    }
}
