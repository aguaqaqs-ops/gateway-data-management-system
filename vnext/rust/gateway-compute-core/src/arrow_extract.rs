use arrow_array::{
    Array, ArrayRef, BinaryArray, BooleanArray, Date32Array, Decimal128Array, Decimal256Array,
    DurationMicrosecondArray, Float32Array, Float64Array, Int8Array, Int16Array, Int32Array,
    Int64Array, RecordBatch, StringArray, TimestampMicrosecondArray, UInt8Array, UInt16Array,
    UInt32Array, UInt64Array,
};
use arrow_buffer::i256;
use arrow_schema::DataType;
use gateway_shared_kernel::{
    AnomalyScalar, DeclaredType, EncodedRow, LogicalLiteral, RawLogicalLiteral, RowField,
    TypedScalar, Utf8LogicalLiteral, canonicalize_jcs, normalize_logical_literal,
};

use crate::errors::{ComputeFailure, ComputeFailureCode};
use crate::request::{DeclaredSchemaField, canonical_field_name};
use crate::row_encode::encode_row_for_compute;

pub struct ColumnBinding {
    pub column_index: usize,
    pub field: DeclaredSchemaField,
}

pub fn build_column_bindings(
    batch: &RecordBatch,
    declared_fields: &[DeclaredSchemaField],
) -> Result<Vec<ColumnBinding>, ComputeFailure> {
    let mut bindings = Vec::with_capacity(declared_fields.len());
    for declared in declared_fields {
        let canonical = canonical_field_name(declared)?;
        let column_index = batch
            .schema()
            .fields()
            .iter()
            .position(|field| {
                canonical_field_name(&DeclaredSchemaField {
                    name: field.name().clone(),
                    nullable: field.is_nullable(),
                    declared_type: DeclaredType::null(),
                })
                .is_ok_and(|name| name == canonical)
            })
            .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ArrowSchemaMismatch))?;
        bindings.push((
            canonical,
            ColumnBinding {
                column_index,
                field: declared.clone(),
            },
        ));
    }
    bindings.sort_by(|(left, _), (right, _)| left.cmp(right));
    Ok(bindings.into_iter().map(|(_, binding)| binding).collect())
}

pub fn encode_row_at(
    batch: &RecordBatch,
    bindings: &[ColumnBinding],
    row_index: usize,
) -> Result<EncodedRow, ComputeFailure> {
    let mut fields = Vec::with_capacity(bindings.len());
    for binding in bindings {
        let array = batch.column(binding.column_index);
        let typed_value = extract_typed_scalar(
            &binding.field.declared_type,
            binding.field.nullable,
            array,
            row_index,
        )?;
        let canonical_name = canonical_field_name(&binding.field)?;
        fields.push(RowField {
            name: canonical_name,
            declared_type: binding.field.declared_type.clone(),
            typed_value,
        });
    }
    encode_row_for_compute(&fields)
}

fn extract_typed_scalar(
    declared_type: &DeclaredType,
    nullable: bool,
    array: &ArrayRef,
    row_index: usize,
) -> Result<TypedScalar, ComputeFailure> {
    if array.is_null(row_index) {
        if !nullable {
            return Err(ComputeFailure::new(
                ComputeFailureCode::CanonicalValueInvalid,
            ));
        }
        return Ok(TypedScalar::Null(gateway_shared_kernel::NullScalar));
    }

    if matches!(declared_type, DeclaredType::SourceLiteralAnomaly) {
        return extract_anomaly(array, row_index);
    }

    let literal = extract_logical_literal(declared_type, array, row_index)?;
    normalize_logical_literal(declared_type, &literal)
        .map(|normalized| normalized.typed_value)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))
}

fn extract_logical_literal(
    declared_type: &DeclaredType,
    array: &ArrayRef,
    row_index: usize,
) -> Result<LogicalLiteral, ComputeFailure> {
    match declared_type {
        DeclaredType::Null => Ok(LogicalLiteral::Utf8(Utf8LogicalLiteral {
            text: "null".to_string(),
        })),
        DeclaredType::Boolean => {
            let array = array
                .as_any()
                .downcast_ref::<BooleanArray>()
                .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
            Ok(LogicalLiteral::Raw(RawLogicalLiteral {
                raw_bytes: vec![u8::from(array.value(row_index))],
            }))
        }
        DeclaredType::SignedInteger { bits } => match *bits {
            8 => {
                let array = downcast_int8(array)?;
                Ok(utf8_literal(array.value(row_index).to_string()))
            }
            16 => {
                let array = downcast_int16(array)?;
                Ok(utf8_literal(array.value(row_index).to_string()))
            }
            24 | 32 => {
                let array = downcast_int32(array)?;
                Ok(utf8_literal(array.value(row_index).to_string()))
            }
            64 => {
                let array = downcast_int64(array)?;
                Ok(utf8_literal(array.value(row_index).to_string()))
            }
            _ => Err(ComputeFailure::new(
                ComputeFailureCode::RowHashComputeFailed,
            )),
        },
        DeclaredType::UnsignedInteger { bits } => match *bits {
            8 => {
                let array = downcast_uint8(array)?;
                Ok(utf8_literal(array.value(row_index).to_string()))
            }
            16 => {
                let array = downcast_uint16(array)?;
                Ok(utf8_literal(array.value(row_index).to_string()))
            }
            24 | 32 => {
                let array = downcast_uint32(array)?;
                Ok(utf8_literal(array.value(row_index).to_string()))
            }
            64 => {
                let array = downcast_uint64(array)?;
                Ok(utf8_literal(array.value(row_index).to_string()))
            }
            _ => Err(ComputeFailure::new(
                ComputeFailureCode::RowHashComputeFailed,
            )),
        },
        DeclaredType::Decimal {
            precision: _,
            scale,
        } => match array.data_type() {
            DataType::Decimal128(_, _) => {
                let array = array
                    .as_any()
                    .downcast_ref::<Decimal128Array>()
                    .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
                Ok(utf8_literal(format_decimal_i128(
                    array.value(row_index),
                    *scale,
                )))
            }
            DataType::Decimal256(_, _) => {
                let array = array
                    .as_any()
                    .downcast_ref::<Decimal256Array>()
                    .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
                Ok(utf8_literal(format_decimal_i256(
                    array.value(row_index),
                    *scale,
                )))
            }
            _ => Err(ComputeFailure::new(
                ComputeFailureCode::RowHashComputeFailed,
            )),
        },
        DeclaredType::Float32 => {
            let array = downcast_float32(array)?;
            let value = array.value(row_index);
            if !value.is_finite() {
                return Err(ComputeFailure::new(
                    ComputeFailureCode::CanonicalValueInvalid,
                ));
            }
            Ok(utf8_literal(format_float32(value)))
        }
        DeclaredType::Float64 => {
            let array = downcast_float64(array)?;
            let value = array.value(row_index);
            if !value.is_finite() {
                return Err(ComputeFailure::new(
                    ComputeFailureCode::CanonicalValueInvalid,
                ));
            }
            Ok(utf8_literal(format_float64(value)))
        }
        DeclaredType::String => {
            let array = downcast_string(array)?;
            Ok(utf8_literal(array.value(row_index).to_string()))
        }
        DeclaredType::Binary | DeclaredType::Bit { .. } => {
            let array = downcast_binary(array)?;
            Ok(LogicalLiteral::Raw(RawLogicalLiteral {
                raw_bytes: array.value(row_index).to_vec(),
            }))
        }
        DeclaredType::Date => {
            let array = downcast_date32(array)?;
            Ok(utf8_literal(days_to_date(array.value(row_index))?))
        }
        DeclaredType::DateTime => {
            let array = downcast_timestamp(array)?;
            Ok(utf8_literal(micros_to_datetime(array.value(row_index))?))
        }
        DeclaredType::Timestamp => {
            let array = downcast_timestamp(array)?;
            Ok(utf8_literal(micros_to_timestamp(array.value(row_index))?))
        }
        DeclaredType::TimeDuration => {
            let array = downcast_duration(array)?;
            Ok(utf8_literal(micros_to_duration(array.value(row_index))?))
        }
        DeclaredType::SourceLiteralAnomaly => Err(ComputeFailure::new(
            ComputeFailureCode::RowHashComputeFailed,
        )),
    }
}

const ANOMALY_ENVELOPE_KEYS: &[&str] =
    &["declared_type", "raw_base64url", "raw_encoding", "reason"];

fn extract_anomaly(array: &ArrayRef, row_index: usize) -> Result<TypedScalar, ComputeFailure> {
    let bytes = downcast_binary(array)?.value(row_index);
    let canonical = canonicalize_jcs(bytes)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?;
    let root: serde_json::Value = serde_json::from_slice(&canonical)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?;
    let object = root
        .as_object()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?;
    validate_exact_object_keys(object, ANOMALY_ENVELOPE_KEYS)?;
    let declared_type = parse_anomaly_declared_type(
        object
            .get("declared_type")
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?,
    )?;
    let raw_base64url = object
        .get("raw_base64url")
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?
        .to_string();
    let raw_encoding = object
        .get("raw_encoding")
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?
        .to_string();
    let reason = object
        .get("reason")
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?
        .to_string();
    Ok(TypedScalar::Anomaly(AnomalyScalar {
        declared_type,
        raw_base64url,
        raw_encoding,
        reason,
    }))
}

fn validate_exact_object_keys(
    object: &serde_json::Map<String, serde_json::Value>,
    allowed: &[&str],
) -> Result<(), ComputeFailure> {
    if object.len() != allowed.len() {
        return Err(ComputeFailure::new(
            ComputeFailureCode::CanonicalValueInvalid,
        ));
    }
    for key in allowed {
        if !object.contains_key(*key) {
            return Err(ComputeFailure::new(
                ComputeFailureCode::CanonicalValueInvalid,
            ));
        }
    }
    for key in object.keys() {
        if !allowed.contains(&key.as_str()) {
            return Err(ComputeFailure::new(
                ComputeFailureCode::CanonicalValueInvalid,
            ));
        }
    }
    Ok(())
}

fn anomaly_declared_type_keys(kind: &str) -> Result<&'static [&'static str], ComputeFailure> {
    Ok(match kind {
        "null"
        | "boolean"
        | "float32"
        | "float64"
        | "string"
        | "binary"
        | "date"
        | "datetime"
        | "timestamp"
        | "time-duration"
        | "source-literal-anomaly" => &["kind"],
        "signed-integer" | "unsigned-integer" => &["kind", "bits"],
        "decimal" => &["kind", "precision", "scale"],
        "bit" => &["kind", "bit_width"],
        _ => {
            return Err(ComputeFailure::new(
                ComputeFailureCode::CanonicalValueInvalid,
            ));
        }
    })
}

fn parse_anomaly_declared_type(
    object: &serde_json::Map<String, serde_json::Value>,
) -> Result<DeclaredType, ComputeFailure> {
    let kind = object
        .get("kind")
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?;
    validate_exact_object_keys(object, anomaly_declared_type_keys(kind)?)?;
    let declared = match kind {
        "null" => DeclaredType::null(),
        "boolean" => DeclaredType::boolean(),
        "signed-integer" => DeclaredType::signed_integer(required_u8(object, "bits")?)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?,
        "unsigned-integer" => DeclaredType::unsigned_integer(required_u8(object, "bits")?)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?,
        "decimal" => DeclaredType::decimal(
            required_u8(object, "precision")?,
            required_u8(object, "scale")?,
        )
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?,
        "float32" => DeclaredType::float32(),
        "float64" => DeclaredType::float64(),
        "string" => DeclaredType::string(),
        "binary" => DeclaredType::binary(),
        "bit" => DeclaredType::bit(required_u8(object, "bit_width")?)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?,
        "date" => DeclaredType::date(),
        "datetime" => DeclaredType::datetime(),
        "timestamp" => DeclaredType::timestamp(),
        "time-duration" => DeclaredType::time_duration(),
        "source-literal-anomaly" => DeclaredType::source_literal_anomaly(),
        _ => {
            return Err(ComputeFailure::new(
                ComputeFailureCode::CanonicalValueInvalid,
            ));
        }
    };
    declared
        .validate()
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?;
    Ok(declared)
}

fn required_u8(
    object: &serde_json::Map<String, serde_json::Value>,
    key: &str,
) -> Result<u8, ComputeFailure> {
    object
        .get(key)
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| u8::try_from(value).ok())
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))
}

fn utf8_literal(text: String) -> LogicalLiteral {
    LogicalLiteral::Utf8(Utf8LogicalLiteral { text })
}

fn downcast_int8(array: &ArrayRef) -> Result<&Int8Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<Int8Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_int16(array: &ArrayRef) -> Result<&Int16Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<Int16Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_int32(array: &ArrayRef) -> Result<&Int32Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<Int32Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_int64(array: &ArrayRef) -> Result<&Int64Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<Int64Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_uint8(array: &ArrayRef) -> Result<&UInt8Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<UInt8Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_uint16(array: &ArrayRef) -> Result<&UInt16Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<UInt16Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_uint32(array: &ArrayRef) -> Result<&UInt32Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<UInt32Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_uint64(array: &ArrayRef) -> Result<&UInt64Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<UInt64Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_float32(array: &ArrayRef) -> Result<&Float32Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<Float32Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_float64(array: &ArrayRef) -> Result<&Float64Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_string(array: &ArrayRef) -> Result<&StringArray, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_binary(array: &ArrayRef) -> Result<&BinaryArray, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<BinaryArray>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_date32(array: &ArrayRef) -> Result<&Date32Array, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<Date32Array>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_timestamp(array: &ArrayRef) -> Result<&TimestampMicrosecondArray, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<TimestampMicrosecondArray>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn downcast_duration(array: &ArrayRef) -> Result<&DurationMicrosecondArray, ComputeFailure> {
    array
        .as_any()
        .downcast_ref::<DurationMicrosecondArray>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

fn format_decimal_i128(unscaled: i128, scale: u8) -> String {
    format_decimal_from_signed_decimal_string(&unscaled.to_string(), scale)
}

fn format_decimal_i256(unscaled: i256, scale: u8) -> String {
    format_decimal_from_signed_decimal_string(&unscaled.to_string(), scale)
}

fn format_decimal_from_signed_decimal_string(text: &str, scale: u8) -> String {
    if let Some(magnitude) = text.strip_prefix('-') {
        format_decimal_from_magnitude_digits(true, magnitude, scale)
    } else {
        format_decimal_from_magnitude_digits(false, text, scale)
    }
}

fn format_decimal_from_magnitude_digits(negative: bool, digits: &str, scale: u8) -> String {
    let trimmed = digits.trim_start_matches('0');
    let magnitude = if trimmed.is_empty() { "0" } else { trimmed };
    let is_zero = magnitude == "0";

    if scale == 0 {
        let body = magnitude.to_string();
        return if negative && !is_zero {
            format!("-{body}")
        } else {
            body
        };
    }

    let scale_usize = usize::from(scale);
    let padded = if magnitude.len() <= scale_usize {
        format!("{:0>width$}", magnitude, width = scale_usize + 1)
    } else {
        magnitude.to_string()
    };
    let split = padded.len() - scale_usize;
    let (integer, fraction) = padded.split_at(split);
    let integer = if integer.is_empty() { "0" } else { integer };
    let fraction_trimmed = fraction.trim_end_matches('0');
    let canonical = if fraction_trimmed.is_empty() {
        integer.to_string()
    } else {
        format!("{integer}.{fraction_trimmed}")
    };
    if negative && !is_zero {
        format!("-{canonical}")
    } else {
        canonical
    }
}

fn format_float32(value: f32) -> String {
    if value == 0.0 && value.is_sign_negative() {
        "-0".to_string()
    } else {
        value.to_string()
    }
}

fn format_float64(value: f64) -> String {
    if value == 0.0 && value.is_sign_negative() {
        "-0".to_string()
    } else {
        value.to_string()
    }
}

fn days_to_date(days: i32) -> Result<String, ComputeFailure> {
    civil_from_days(i64::from(days))
        .map(|(year, month, day)| format!("{year:04}-{month:02}-{day:02}"))
}

fn micros_to_datetime(micros: i64) -> Result<String, ComputeFailure> {
    let (year, month, day, hour, minute, second, micro) = civil_from_micros(micros)?;
    let fraction = format_fraction(micro);
    Ok(format!(
        "{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}{fraction}"
    ))
}

fn micros_to_timestamp(micros: i64) -> Result<String, ComputeFailure> {
    let (year, month, day, hour, minute, second, micro) = civil_from_micros(micros)?;
    let fraction = format_fraction(micro);
    Ok(format!(
        "{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}{fraction}Z"
    ))
}

fn micros_to_duration(micros: i64) -> Result<String, ComputeFailure> {
    let negative = micros < 0;
    let abs = micros.unsigned_abs();
    let total_seconds = abs / 1_000_000;
    let micro = (abs % 1_000_000) as u32;
    let seconds = (total_seconds % 60) as u32;
    let minutes = ((total_seconds / 60) % 60) as u32;
    let hours = (total_seconds / 3600) as u32;
    let fraction = if micro == 0 {
        String::new()
    } else {
        let raw = format!(".{micro:06}");
        raw.trim_end_matches('0').to_string()
    };
    let body = format!("{hours:02}:{minutes:02}:{seconds:02}{fraction}");
    if negative {
        Ok(format!("-{body}"))
    } else {
        Ok(body)
    }
}

fn format_fraction(micro: u32) -> String {
    if micro == 0 {
        String::new()
    } else {
        let raw = format!(".{micro:06}");
        raw.trim_end_matches('0').to_string()
    }
}

type CivilParts = (i32, u32, u32, u32, u32, u32, u32);

fn civil_from_micros(micros: i64) -> Result<CivilParts, ComputeFailure> {
    let days = micros.div_euclid(86_400_000_000);
    let day_micros = micros.rem_euclid(86_400_000_000);
    let (year, month, day) = civil_from_days(days)?;
    let total_seconds = (day_micros / 1_000_000) as u32;
    let micro = (day_micros % 1_000_000) as u32;
    let hour = total_seconds / 3600;
    let minute = (total_seconds % 3600) / 60;
    let second = total_seconds % 60;
    Ok((year, month, day, hour, minute, second, micro))
}

fn civil_from_days(days: i64) -> Result<(i32, u32, u32), ComputeFailure> {
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    let year = y + if month <= 2 { 1 } else { 0 };
    if year < 1 {
        return Err(ComputeFailure::new(
            ComputeFailureCode::CanonicalValueInvalid,
        ));
    }
    Ok((year as i32, month as u32, day as u32))
}

mod tests {
    #![allow(clippy::assertions_on_constants)]
    #[test]
    fn decimal_formatting_matches_simple_values() {
        assert_eq!(super::format_decimal_i128(12345, 2), "123.45");
        assert_eq!(super::format_decimal_i128(-12345, 2), "-123.45");
        assert_eq!(super::format_decimal_i128(0, 2), "0");
    }

    #[test]
    fn decimal256_large_magnitude_preserves_digits() {
        let value = match arrow_buffer::i256::from_string("100000000000000000000000000000000000000")
        {
            Some(value) => value,
            None => {
                assert!(false, "i256 parse failed");
                return;
            }
        };
        assert_eq!(
            super::format_decimal_i256(value, 0),
            "100000000000000000000000000000000000000"
        );
    }

    #[test]
    fn non_nullable_null_slot_rejected_at_extract() {
        use std::sync::Arc;
        let array = Arc::new(arrow_array::BooleanArray::from(vec![None])) as arrow_array::ArrayRef;
        match super::extract_typed_scalar(
            &gateway_shared_kernel::DeclaredType::boolean(),
            false,
            &array,
            0,
        ) {
            Err(error) => assert_eq!(
                error.code,
                crate::errors::ComputeFailureCode::CanonicalValueInvalid
            ),
            Ok(_) => assert!(false, "non-nullable null must be rejected"),
        }
    }

    #[test]
    fn date_year_zero_day_is_canonical_invalid() {
        let failure_day = (-800_000..0).find(|days| {
            matches!(
                super::days_to_date(*days),
                Err(error) if error.code == crate::errors::ComputeFailureCode::CanonicalValueInvalid
            )
        });
        let Some(failure_day) = failure_day else {
            assert!(false, "expected some day to map to invalid civil year");
            return;
        };
        assert!(failure_day < 0);
    }

    #[test]
    fn decimal256_i256_min_formats_without_panic() {
        let text = super::format_decimal_i256(arrow_buffer::i256::MIN, 0);
        assert!(text.starts_with('-'));
    }

    #[test]
    fn decimal256_negative_large_magnitude() {
        let value = match arrow_buffer::i256::from_string("99999999999999999999999999999999999999")
        {
            Some(value) => -value,
            None => {
                assert!(false, "i256 parse failed");
                return;
            }
        };
        assert_eq!(
            super::format_decimal_i256(value, 0),
            "-99999999999999999999999999999999999999"
        );
    }
}
