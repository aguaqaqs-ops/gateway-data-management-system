//! Bounded Arrow builders for the three comparison-record families.

use std::sync::{Arc, Mutex};

use arrow_array::builder::{
    ArrayBuilder, BinaryBuilder, BooleanBuilder, FixedSizeBinaryBuilder, Int64Builder, ListBuilder,
    StringBuilder, StructBuilder, make_builder,
};
use arrow_array::{Array, RecordBatch, make_array};
use arrow_buffer::{BooleanBuffer, Buffer, NullBuffer};
use arrow_data::ArrayData;
use arrow_schema::{DataType, Field, Schema, SchemaRef};
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

const BUILDER_WORKSPACE_BYTES: usize = 512 * 1024;

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
    if !matches!(
        detail_policy,
        "COUNTS_ONLY" | "CHANGED_COLUMNS" | "FULL_BEFORE_AFTER_VALUES"
    ) {
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
    Ok(Arc::new(Schema::new_with_metadata(
        expected_fields(family)?,
        metadata,
    )))
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
    let schema = records_schema(family, detail_policy)?;
    // STANDARD is the widest fixed schema: 48 builder nodes. At 1024 slots,
    // each variable-width node starts with <= 4100 offset + 1024 value bytes;
    // the fixed identity starts with 32768 bytes. Headers/validity fit with
    // these in 512 KiB, held through each group reset. Row charges cover
    // later capacity growth before append.
    let mut lease = context.reserve(BUILDER_WORKSPACE_BYTES).map_err(|error| error.to_string())?;
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
        record_count = record_count
            .checked_add(1)
            .ok_or_else(|| "records count overflow".to_string())?;
        if record_count > max_records {
            return Err("records per-table limit exceeded".to_string());
        }
        let encoded_size = json_size(&row.value)?;
        let row_charge = encoded_size
            .checked_mul(3)
            .and_then(|size| {
                schema
                    .fields()
                    .len()
                    .checked_mul(1024)
                    .and_then(|headers| size.checked_add(headers))
            })
            .and_then(|size| size.checked_add(4096))
            .ok_or("records output budget overflow")?;
        if lease
            .charged_bytes()
            .checked_sub(BUILDER_WORKSPACE_BYTES)
            .ok_or("records builder charge underflow")?
            .checked_add(row_charge)
            .ok_or("records output budget overflow")?
            > max_output_bytes
        {
            return Err("records output budget exceeded".to_string());
        }
        lease.grow(row_charge).map_err(|error| error.to_string())?;
        if record_count != 1 {
            hasher.update(b",");
        }
        let encoded = serde_json::to_vec(&row.value).map_err(|error| error.to_string())?;
        hasher.update(canonicalize_jcs(&encoded).map_err(|error| error.to_string())?);
        let object = row
            .value
            .as_object()
            .ok_or_else(|| "records row must be an object".to_string())?;
        for (field, builder) in schema.fields().iter().zip(&mut builders) {
            let value = object
                .get(field.name())
                .ok_or_else(|| format!("records field {} is missing", field.name()))?;
            append_value(builder.as_mut(), field, value)?;
        }
        drop(row);
        batch_count += 1;
        if batch_count == 1024 {
            batches.push(finish_batch(Arc::clone(&schema), &mut builders)?);
            let retained = retained_charge(&batches, &schema)?;
            if retained > max_output_bytes || retained > lease.charged_bytes() {
                return Err("records output budget exceeded".to_string());
            }
            // Keep the finished physical buffers charged and reserve the next
            // builder's initial capacity before creating it. The former is
            // already covered by the per-row precharge above.
            let next = retained.checked_add(BUILDER_WORKSPACE_BYTES)
                .ok_or("records output budget overflow")?;
            if next > lease.charged_bytes() {
                lease.grow(next - lease.charged_bytes())
                    .map_err(|error| error.to_string())?;
            } else {
                lease.shrink_to(next).map_err(|error| error.to_string())?;
            }
            builders = new_builders(&schema);
            batch_count = 0;
        }
    }
    if batch_count != 0 {
        batches.push(finish_batch(Arc::clone(&schema), &mut builders)?);
    }
    let schema_version = schema
        .metadata()
        .get(&format!("{METADATA_PREFIX}schema_version"))
        .ok_or("records schema version is missing")?;
    hasher.update(b"],\"schema_version\":\"");
    hasher.update(schema_version.as_bytes());
    hasher.update(b"\"}");
    let content_digest =
        DigestRef::from_raw_digest(&hasher.finalize()).map_err(|error| error.to_string())?;
    let retained = retained_charge(&batches, &schema)?;
    if retained > max_output_bytes {
        return Err("records output budget exceeded".to_string());
    }
    if retained > lease.charged_bytes() {
        return Err("records physical output charge exceeded its precharge".to_string());
    }
    drop(builders);
    lease.shrink_to(retained).map_err(|error| error.to_string())?;
    // Rebinding retains another bounded set of headers, not a second payload.
    // The per-batch header allowance remains in the output lease.
    let charge = Arc::new(OutputCharge {
        lease: Mutex::new(lease),
        _external_owner: external_owner,
    });
    let batches = batches
        .into_iter()
        .map(|batch| charged_batch(batch, &charge))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(BuiltRecords {
        schema,
        batches,
        record_count,
        content_digest,
        _charge: charge,
    })
}

fn retained_charge(batches: &[RecordBatch], schema: &Schema) -> Result<usize, String> {
    let data = batches
        .iter()
        .flat_map(RecordBatch::columns)
        .try_fold(0usize, |sum, array| {
            // The final Bytes owner retains the original Arrow allocation,
            // whose capacity can exceed its logical slice length. Measure it
            // before charged_batch replaces buffers with external owners.
            sum.checked_add(array.to_data().get_array_memory_size())
        })
        .ok_or("records output size overflow")?;
    let headers = batches
        .len()
        .checked_mul(schema.fields().len())
        .and_then(|count| count.checked_mul(512))
        .and_then(|size| size.checked_add(if batches.is_empty() { 0 } else { 4096 }))
        .ok_or("records output header overflow")?;
    data.checked_add(headers)
        .ok_or("records output retained overflow".to_string())
}

fn charged_batch(batch: RecordBatch, charge: &Arc<OutputCharge>) -> Result<RecordBatch, String> {
    let schema = batch.schema();
    let columns = batch
        .columns()
        .iter()
        .map(|array| {
            let data = attach_charge(array.to_data(), charge)?;
            Ok(make_array(data))
        })
        .collect::<Result<Vec<_>, String>>()?;
    RecordBatch::try_new(schema, columns).map_err(|error| error.to_string())
}

fn attach_charge(data: ArrayData, charge: &Arc<OutputCharge>) -> Result<ArrayData, String> {
    let buffers = data
        .buffers()
        .iter()
        .map(|buffer| charged_buffer(buffer, charge))
        .collect();
    let nulls = data.nulls().map(|nulls| {
        NullBuffer::new(BooleanBuffer::new(
            charged_buffer(nulls.buffer(), charge),
            nulls.offset(),
            nulls.len(),
        ))
    });
    let children = data
        .child_data()
        .iter()
        .cloned()
        .map(|child| attach_charge(child, charge))
        .collect::<Result<Vec<_>, _>>()?;
    data.into_builder()
        .buffers(buffers)
        .nulls(nulls)
        .child_data(children)
        .build()
        .map_err(|error| error.to_string())
}

fn charged_buffer(buffer: &Buffer, charge: &Arc<OutputCharge>) -> Buffer {
    Buffer::from(Bytes::from_owner(ChargedBuffer {
        original: buffer.clone(),
        _charge: Arc::clone(charge),
    }))
}

fn new_builders(schema: &Schema) -> Vec<Box<dyn ArrayBuilder>> {
    schema
        .fields()
        .iter()
        .map(|field| make_builder(field.data_type(), 1024))
        .collect()
}

fn finish_batch(
    schema: SchemaRef,
    builders: &mut [Box<dyn ArrayBuilder>],
) -> Result<RecordBatch, String> {
    let columns = builders
        .iter_mut()
        .map(|builder| builder.finish())
        .collect();
    RecordBatch::try_new(schema, columns).map_err(|error| error.to_string())
}

fn append_value(
    builder: &mut dyn ArrayBuilder,
    field: &Field,
    value: &Value,
) -> Result<(), String> {
    append_value_with_limit(builder, field, value, i32::MAX as usize)
}

fn append_value_with_limit(
    builder: &mut dyn ArrayBuilder,
    field: &Field,
    value: &Value,
    max_offset: usize,
) -> Result<(), String> {
    if value.is_null() && !field.is_nullable() {
        return Err(format!("records field {} cannot be null", field.name()));
    }
    match field.data_type() {
        DataType::Utf8 => {
            let builder = downcast::<StringBuilder>(builder)?;
            if let Some(text) = value.as_str() {
                ensure_offset_growth(builder.values_slice().len(), text.len(), max_offset)?;
                builder.append_value(text);
            } else if value.is_null() {
                builder.append_null();
            } else {
                return Err("records string value has wrong type".to_string());
            }
        }
        DataType::Binary => {
            let builder = downcast::<BinaryBuilder>(builder)?;
            if value.is_null() {
                builder.append_null();
            } else {
                let bytes_hex = value
                    .get("bytes_hex")
                    .and_then(Value::as_str)
                    .ok_or("records binary value must contain bytes_hex")?;
                ensure_offset_growth(
                    builder.values_slice().len(),
                    bytes_hex.len() / 2,
                    max_offset,
                )?;
                builder.append_value(bytes_value(value)?);
            }
        }
        DataType::FixedSizeBinary(width) => {
            let builder = downcast::<FixedSizeBinaryBuilder>(builder)?;
            if value.is_null() {
                builder.append_null();
            } else {
                let bytes = bytes_value(value)?;
                if bytes.len() != usize::try_from(*width).map_err(|error| error.to_string())? {
                    return Err("records fixed binary width mismatch".to_string());
                }
                builder
                    .append_value(bytes)
                    .map_err(|error| error.to_string())?;
            }
        }
        DataType::Boolean => {
            let builder = downcast::<BooleanBuilder>(builder)?;
            if let Some(boolean) = value.as_bool() {
                builder.append_value(boolean);
            } else if value.is_null() {
                builder.append_null();
            } else {
                return Err("records boolean value has wrong type".to_string());
            }
        }
        DataType::Int64 => {
            let builder = downcast::<Int64Builder>(builder)?;
            if let Some(integer) = value.as_i64() {
                builder.append_value(integer);
            } else if value.is_null() {
                builder.append_null();
            } else {
                return Err("records integer value has wrong type".to_string());
            }
        }
        DataType::List(element) => {
            let builder = downcast::<ListBuilder<Box<dyn ArrayBuilder>>>(builder)?;
            if let Some(items) = value.as_array() {
                ensure_offset_growth(builder.values_ref().len(), items.len(), max_offset)?;
                for item in items {
                    append_value_with_limit(builder.values().as_mut(), element, item, max_offset)?;
                }
                builder.append(true);
            } else if value.is_null() {
                builder.append(false);
            } else {
                return Err("records list value has wrong type".to_string());
            }
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
                    object
                        .get(child.name())
                        .ok_or_else(|| format!("records field {} is missing", child.name()))?
                } else {
                    &placeholder
                };
                append_value_with_limit(
                    builder.field_builders_mut()[index].as_mut(),
                    child,
                    child_value,
                    max_offset,
                )?;
            }
            builder.append(object.is_some());
        }
        other => return Err(format!("unsupported records Arrow type {other:?}")),
    }
    Ok(())
}

fn ensure_offset_growth(current: usize, additional: usize, limit: usize) -> Result<(), String> {
    if current
        .checked_add(additional)
        .is_none_or(|next| next > limit)
    {
        return Err("records Arrow offset budget exceeded".to_string());
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
        DataType::Struct(fields) => Value::Object(
            fields
                .iter()
                .map(|child| (child.name().clone(), masked_child_value(child)))
                .collect(),
        ),
        _ => Value::Null,
    }
}

fn downcast<T: ArrayBuilder + 'static>(builder: &mut dyn ArrayBuilder) -> Result<&mut T, String> {
    builder
        .as_any_mut()
        .downcast_mut::<T>()
        .ok_or_else(|| "records Arrow builder type mismatch".to_string())
}

fn bytes_value(value: &Value) -> Result<Vec<u8>, String> {
    let hex = value
        .get("bytes_hex")
        .and_then(Value::as_str)
        .ok_or_else(|| "records binary value must contain bytes_hex".to_string())?;
    if hex.len() % 2 != 0 || !hex.is_ascii() {
        return Err("records bytes_hex is invalid".to_string());
    }
    (0..hex.len())
        .step_by(2)
        .map(|index| {
            u8::from_str_radix(&hex[index..index + 2], 16).map_err(|error| error.to_string())
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::AtomicBool;

    use arrow_array::{Array, ListArray, StringArray, StructArray};
    use serde_json::json;

    use super::*;

    #[test]
    fn nullable_parent_struct_and_sql_null_scalar_remain_distinct() -> Result<(), String> {
        let context = Arc::new(KernelContext::new(
            16 * 1024 * 1024,
            Arc::new(AtomicBool::new(false)),
            None,
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
            "STANDARD",
            "FULL_BEFORE_AFTER_VALUES",
            [Ok(BoundedRow {
                value: row,
                _scratch: context.reserve(4096).map_err(|error| error.to_string())?,
            })],
            1,
            1024 * 1024,
            &context,
            None,
        )?;
        let batch = built.batches[0].clone();
        let changes = batch
            .column(6)
            .as_any()
            .downcast_ref::<ListArray>()
            .ok_or("changes")?;
        let values = changes.values();
        let change = values
            .as_any()
            .downcast_ref::<StructArray>()
            .ok_or("change struct")?;
        let before = change
            .column(1)
            .as_any()
            .downcast_ref::<StructArray>()
            .ok_or("before")?;
        let current = change
            .column(2)
            .as_any()
            .downcast_ref::<StructArray>()
            .ok_or("current")?;
        assert!(before.is_null(0));
        assert!(!current.is_null(0));
        assert_eq!(
            current
                .column(0)
                .as_any()
                .downcast_ref::<StringArray>()
                .ok_or("kind")?
                .value(0),
            "null",
        );
        let logical = batch.columns().iter().try_fold(0usize, |sum, array| {
            sum.checked_add(array.to_data().get_slice_memory_size().ok()?)
        }).ok_or("logical size overflow")?;
        let retained = built._charge.lease.lock()
            .map_err(|_| "charge lock poisoned")?.charged_bytes();
        assert!(retained > logical);
        drop(built);
        assert!(context.remaining_bytes() < starting);
        drop(batch);
        assert_eq!(context.remaining_bytes(), starting);
        Ok(())
    }

    #[test]
    fn variable_width_offsets_reject_before_arrow_builder_growth() -> Result<(), String> {
        let string = Field::new("text", DataType::Utf8, false);
        let mut string_builder = StringBuilder::new();
        append_value_with_limit(&mut string_builder, &string, &json!("abc"), 3)?;
        assert!(
            append_value_with_limit(&mut string_builder, &string, &json!("d"), 3)
                .err()
                .ok_or("string offset must fail")?
                .contains("offset budget")
        );
        assert_eq!(string_builder.values_slice(), b"abc");

        let binary = Field::new("raw", DataType::Binary, false);
        let mut binary_builder = BinaryBuilder::new();
        append_value_with_limit(
            &mut binary_builder,
            &binary,
            &json!({"bytes_hex": "000102"}),
            3,
        )?;
        assert!(
            append_value_with_limit(&mut binary_builder, &binary, &json!({"bytes_hex": "03"}), 3)
                .err()
                .ok_or("binary offset must fail")?
                .contains("offset budget")
        );
        assert_eq!(binary_builder.values_slice(), &[0, 1, 2]);

        let element = Arc::new(Field::new("item", DataType::Utf8, true));
        let list = Field::new("items", DataType::List(element), false);
        let mut list_builder = make_builder(list.data_type(), 1);
        append_value_with_limit(list_builder.as_mut(), &list, &json!(["a", "b"]), 3)?;
        assert!(
            append_value_with_limit(list_builder.as_mut(), &list, &json!(["c", "d"]), 3)
                .err()
                .ok_or("list offset must fail")?
                .contains("offset budget")
        );
        let child_count = list_builder
            .as_any_mut()
            .downcast_mut::<ListBuilder<Box<dyn ArrayBuilder>>>()
            .ok_or("list builder")?
            .values_ref()
            .len();
        assert_eq!(child_count, 2);

        let nested_element = Arc::new(Field::new("item", DataType::Utf8, true));
        let nested_child = Arc::new(Field::new("item", DataType::List(nested_element), true));
        let nested = Field::new("nested", DataType::List(nested_child), false);
        let mut nested_builder = make_builder(nested.data_type(), 1);
        append_value_with_limit(
            nested_builder.as_mut(),
            &nested,
            &json!([["a", "b", "c"]]),
            3,
        )?;
        assert!(
            append_value_with_limit(nested_builder.as_mut(), &nested, &json!([["d"]]), 3)
                .err()
                .ok_or("nested offset must fail")?
                .contains("offset budget")
        );
        Ok(())
    }

    #[test]
    fn retained_charge_uses_original_buffer_capacity() -> Result<(), String> {
        let schema = Schema::new(vec![Field::new("text", DataType::Utf8, false)]);
        let mut builder = StringBuilder::with_capacity(1, 1024);
        builder.append_value("x");
        let batch = RecordBatch::try_new(
            Arc::new(schema.clone()), vec![Arc::new(builder.finish())]
        ).map_err(|error| error.to_string())?;
        let data = batch.column(0).to_data();
        let logical = data.get_slice_memory_size().map_err(|error| error.to_string())?;
        let physical = data.get_array_memory_size();
        assert!(physical > logical + 1024);
        assert!(retained_charge(&[batch], &schema)? >= physical);
        Ok(())
    }

    #[test]
    fn fixed_family_builder_initial_capacity_fits_precharge() -> Result<(), String> {
        for family in ["STANDARD", "ORDERED", "BLANK"] {
            let schema = records_schema(family, "FULL_BEFORE_AFTER_VALUES")?;
            let mut builders = new_builders(&schema);
            let empty = finish_batch(Arc::clone(&schema), &mut builders)?;
            assert!(retained_charge(&[empty], &schema)? <= BUILDER_WORKSPACE_BYTES);
        }
        Ok(())
    }
}
