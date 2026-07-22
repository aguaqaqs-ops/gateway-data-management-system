use std::sync::Arc;

use arrow_array::{
    ArrayRef, BinaryArray, BooleanArray, Date32Array, Decimal128Array, Decimal256Array,
    DurationMicrosecondArray, Float32Array, Float64Array, Int8Array, Int16Array, Int32Array,
    Int64Array, NullArray, RecordBatch, StringArray, TimestampMicrosecondArray, UInt8Array,
    UInt16Array, UInt32Array, UInt64Array,
};
use arrow_buffer::i256;
use arrow_schema::{ArrowError, DataType, Field, Schema, TimeUnit};

pub fn batch_with_fields(
    fields: Vec<Field>,
    columns: Vec<ArrayRef>,
) -> Result<RecordBatch, ArrowError> {
    let schema = Arc::new(Schema::new(fields));
    RecordBatch::try_new(schema, columns)
}

pub fn boolean_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<bool>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Boolean, nullable)],
        vec![Arc::new(BooleanArray::from(values))],
    )
}

pub fn int8_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<i8>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Int8, nullable)],
        vec![Arc::new(Int8Array::from(values))],
    )
}

pub fn int16_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<i16>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Int16, nullable)],
        vec![Arc::new(Int16Array::from(values))],
    )
}

pub fn int64_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<i64>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Int64, nullable)],
        vec![Arc::new(Int64Array::from(values))],
    )
}

pub fn uint8_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<u8>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::UInt8, nullable)],
        vec![Arc::new(UInt8Array::from(values))],
    )
}

pub fn uint16_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<u16>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::UInt16, nullable)],
        vec![Arc::new(UInt16Array::from(values))],
    )
}

pub fn uint64_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<u64>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::UInt64, nullable)],
        vec![Arc::new(UInt64Array::from(values))],
    )
}

pub fn int32_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<i32>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Int32, nullable)],
        vec![Arc::new(Int32Array::from(values))],
    )
}

pub fn uint32_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<u32>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::UInt32, nullable)],
        vec![Arc::new(UInt32Array::from(values))],
    )
}

pub fn float64_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<f64>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Float64, nullable)],
        vec![Arc::new(Float64Array::from(values))],
    )
}

pub fn float32_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<f32>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Float32, nullable)],
        vec![Arc::new(Float32Array::from(values))],
    )
}

pub fn string_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<&str>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Utf8, nullable)],
        vec![Arc::new(StringArray::from(values))],
    )
}

pub fn binary_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<&[u8]>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Binary, nullable)],
        vec![Arc::new(BinaryArray::from(values))],
    )
}

pub fn null_kind_batch(name: &str, len: usize) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Null, true)],
        vec![Arc::new(NullArray::new(len))],
    )
}

pub fn date32_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<i32>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(name, DataType::Date32, nullable)],
        vec![Arc::new(Date32Array::from(values))],
    )
}

pub fn datetime_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<i64>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(
            name,
            DataType::Timestamp(TimeUnit::Microsecond, None),
            nullable,
        )],
        vec![Arc::new(TimestampMicrosecondArray::from(values))],
    )
}

pub fn timestamp_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<i64>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(
            name,
            DataType::Timestamp(TimeUnit::Microsecond, Some("UTC".into())),
            nullable,
        )],
        vec![Arc::new(
            TimestampMicrosecondArray::from(values).with_timezone("UTC".to_string()),
        )],
    )
}

pub fn duration_batch(
    name: &str,
    nullable: bool,
    values: Vec<Option<i64>>,
) -> Result<RecordBatch, ArrowError> {
    batch_with_fields(
        vec![Field::new(
            name,
            DataType::Duration(TimeUnit::Microsecond),
            nullable,
        )],
        vec![Arc::new(DurationMicrosecondArray::from(values))],
    )
}

pub fn decimal128_batch(
    name: &str,
    nullable: bool,
    precision: u8,
    scale: i8,
    values: Vec<Option<i128>>,
) -> Result<RecordBatch, ArrowError> {
    let array = Decimal128Array::from(values).with_precision_and_scale(precision, scale)?;
    batch_with_fields(
        vec![Field::new(
            name,
            DataType::Decimal128(precision, scale),
            nullable,
        )],
        vec![Arc::new(array)],
    )
}

pub fn decimal256_batch(
    name: &str,
    nullable: bool,
    precision: u8,
    scale: i8,
    values: Vec<Option<i256>>,
) -> Result<RecordBatch, ArrowError> {
    let array = Decimal256Array::from(values).with_precision_and_scale(precision, scale)?;
    batch_with_fields(
        vec![Field::new(
            name,
            DataType::Decimal256(precision, scale),
            nullable,
        )],
        vec![Arc::new(array)],
    )
}

pub fn reorder_fields(batch: &RecordBatch, order: &[usize]) -> Result<RecordBatch, ArrowError> {
    let schema = batch.schema();
    let fields = order
        .iter()
        .map(|index| schema.field(*index).clone())
        .collect::<Vec<_>>();
    let columns = order
        .iter()
        .map(|index| batch.column(*index).clone())
        .collect::<Vec<_>>();
    batch_with_fields(fields, columns)
}

pub fn empty_schema_batch(
    request_fields: &[(&str, DataType, bool)],
) -> Result<RecordBatch, ArrowError> {
    if request_fields.is_empty() {
        return Ok(RecordBatch::new_empty(Arc::new(Schema::empty())));
    }
    let fields = request_fields
        .iter()
        .map(|(name, data_type, nullable)| Field::new(*name, data_type.clone(), *nullable))
        .collect::<Vec<_>>();
    let columns = request_fields
        .iter()
        .map(|(_, data_type, nullable)| empty_array_for_type(data_type, *nullable))
        .collect::<Vec<_>>();
    batch_with_fields(fields, columns)
}

fn empty_array_for_type(data_type: &DataType, nullable: bool) -> ArrayRef {
    let _ = nullable;
    match data_type {
        DataType::Null => Arc::new(NullArray::new(0)),
        DataType::Boolean => Arc::new(BooleanArray::from(Vec::<Option<bool>>::new())),
        DataType::Int32 => Arc::new(Int32Array::from(Vec::<Option<i32>>::new())),
        DataType::Utf8 => Arc::new(StringArray::from(Vec::<Option<&str>>::new())),
        _ => Arc::new(NullArray::new(0)),
    }
}
