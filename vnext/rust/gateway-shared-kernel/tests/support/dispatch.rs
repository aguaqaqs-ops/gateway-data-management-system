//! Vector operation dispatcher (test-only; mirrors Python `testing.dispatch`).

use gateway_shared_kernel::{
    AnomalyScalar, BinaryScalar, BitScalar, BooleanScalar, CanonicalEncodingError,
    CanonicalErrorCode, CollectionSemantics, DateScalar, DateTimeScalar, DecimalScalar,
    DeclaredType, DigestKind, Float32Scalar, Float64Scalar, LogicalLiteral, NullScalar,
    RawLogicalLiteral, RowField, SignedIntegerScalar, StringScalar, TimeDurationScalar,
    TimestampScalar, TypedScalar, UnsignedIntegerScalar, Utf8LogicalLiteral,
    canonicalize_identifier, canonicalize_jcs, encode_collection, encode_row, encode_typed_scalar,
    normalize_logical_literal, raw_blob_digest, semantic_digest,
};
use serde_json::{Map, Value};

use super::codec::{decode_base64url_strict, encode_base64url};
use super::validate_frame::validate_scalar_frame;

#[derive(Debug)]
pub struct DispatchMismatch {
    message: String,
}

impl std::fmt::Display for DispatchMismatch {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for DispatchMismatch {}

/// Execute one vector case and compare expected output or stable error code.
pub fn dispatch_case(case: &Value) -> Result<(), DispatchMismatch> {
    let operation = required_str(case, "operation")?;
    if case.get("expected_error").is_some() {
        let input = required_object(case, "input")?;
        let expected_code = case
            .get("expected_error")
            .and_then(Value::as_object)
            .and_then(|obj| obj.get("code"))
            .and_then(Value::as_str)
            .ok_or_else(|| dispatch_mismatch("invalid case: expected_error.code"))?;
        return dispatch_invalid(operation, input, expected_code);
    }

    let expected = required_object(case, "expected")?;
    let input = required_object(case, "input")?;
    let actual = compute_expected(operation, input).map_err(|error| {
        let case_id = case
            .get("case_id")
            .and_then(Value::as_str)
            .unwrap_or("<unknown>");
        dispatch_mismatch(format!(
            "case {case_id:?} compute failed: {error} ({})",
            error.stable_code()
        ))
    })?;
    if actual != *expected {
        let case_id = case
            .get("case_id")
            .and_then(Value::as_str)
            .unwrap_or("<unknown>");
        return Err(dispatch_mismatch(format!(
            "case {case_id:?} mismatch:\n  actual={actual:?}\n  expected={expected:?}"
        )));
    }
    Ok(())
}

/// Compute valid-case expected fields from logical input (generation parity).
pub fn compute_expected(
    operation: &str,
    input: &Map<String, Value>,
) -> Result<Map<String, Value>, CanonicalEncodingError> {
    match operation {
        "canonicalize-jcs" => {
            let json_utf8 = decode_field_base64url(input, "json_utf8_base64url")?;
            let out = canonicalize_jcs(&json_utf8)?;
            let mut expected = Map::new();
            expected.insert(
                "canonical_bytes_base64url".to_string(),
                Value::String(encode_base64url(&out)),
            );
            Ok(expected)
        }
        "normalize-logical-literal" => {
            let declared = parse_declared_type(required_object_value(input, "declared_type")?)?;
            let source = parse_logical_literal(required_object_value(input, "source")?)?;
            let normalized = normalize_logical_literal(&declared, &source)?;
            let mut expected = Map::new();
            expected.insert(
                "typed_value".to_string(),
                typed_value_to_json(&normalized.typed_value)?,
            );
            expected.insert(
                "payload_base64url".to_string(),
                Value::String(encode_base64url(&normalized.payload)),
            );
            expected.insert(
                "scalar_frame_base64url".to_string(),
                Value::String(encode_base64url(&normalized.scalar_frame)),
            );
            Ok(expected)
        }
        "encode-typed-scalar" => {
            let declared = parse_declared_type(required_object_value(input, "declared_type")?)?;
            let typed = parse_typed_value(required_object_value(input, "typed_value")?)?;
            let encoded = encode_typed_scalar(&declared, &typed)?;
            let mut expected = Map::new();
            expected.insert(
                "payload_base64url".to_string(),
                Value::String(encode_base64url(&encoded.payload)),
            );
            expected.insert(
                "scalar_frame_base64url".to_string(),
                Value::String(encode_base64url(&encoded.scalar_frame)),
            );
            Ok(expected)
        }
        "canonicalize-identifier" => {
            let identifier = required_str_value(input, "identifier")?;
            let canonical = canonicalize_identifier(identifier)?;
            let mut expected = Map::new();
            expected.insert(
                "canonical_utf8_base64url".to_string(),
                Value::String(encode_base64url(canonical.as_bytes())),
            );
            Ok(expected)
        }
        "encode-row" => {
            let fields_value = input
                .get("fields")
                .ok_or_else(|| type_mismatch("encode-row requires fields"))?;
            let fields_array = fields_value
                .as_array()
                .ok_or_else(|| type_mismatch("fields must be an array"))?;
            let mut fields = Vec::with_capacity(fields_array.len());
            for item in fields_array {
                let item_obj = item
                    .as_object()
                    .ok_or_else(|| type_mismatch("row field must be an object"))?;
                let name = required_str_value(item_obj, "name")?.to_string();
                let declared =
                    parse_declared_type(required_object_value(item_obj, "declared_type")?)?;
                let typed = parse_typed_value(required_object_value(item_obj, "typed_value")?)?;
                fields.push(RowField {
                    name,
                    declared_type: declared,
                    typed_value: typed,
                });
            }
            let encoded_row = encode_row(&fields)?;
            let mut expected = Map::new();
            expected.insert(
                "row_frame_base64url".to_string(),
                Value::String(encode_base64url(encoded_row.row_frame())),
            );
            expected.insert(
                "row_hash".to_string(),
                Value::String(encoded_row.digest_ref().as_str().to_string()),
            );
            Ok(expected)
        }
        "encode-collection" => {
            let semantics = parse_collection_semantics(required_str_value(input, "semantics")?)?;
            let encoded = if semantics == CollectionSemantics::KeyedCollection {
                let entries_value = input
                    .get("entries")
                    .ok_or_else(|| type_mismatch("keyed-collection requires entries"))?;
                let entries_array = entries_value
                    .as_array()
                    .ok_or_else(|| type_mismatch("entries must be an array"))?;
                let mut entries: Vec<(Vec<u8>, Vec<u8>)> = Vec::with_capacity(entries_array.len());
                for entry in entries_array {
                    let entry_obj = entry
                        .as_object()
                        .ok_or_else(|| type_mismatch("entry must be an object"))?;
                    let key = decode_field_base64url(entry_obj, "key_base64url")?;
                    let value = decode_field_base64url(entry_obj, "value_base64url")?;
                    entries.push((key, value));
                }
                let entry_refs: Vec<(&[u8], &[u8])> = entries
                    .iter()
                    .map(|(key, value)| (key.as_slice(), value.as_slice()))
                    .collect();
                encode_collection(semantics, None, Some(&entry_refs))?
            } else {
                let items_value = input
                    .get("items_base64url")
                    .ok_or_else(|| type_mismatch("collection requires items_base64url"))?;
                let items_array = items_value
                    .as_array()
                    .ok_or_else(|| type_mismatch("items_base64url must be an array"))?;
                let mut items: Vec<Vec<u8>> = Vec::with_capacity(items_array.len());
                for item in items_array {
                    let text = item
                        .as_str()
                        .ok_or_else(|| type_mismatch("items_base64url entries must be strings"))?;
                    items.push(decode_base64url_strict(text)?);
                }
                let item_refs: Vec<&[u8]> = items.iter().map(Vec::as_slice).collect();
                encode_collection(semantics, Some(&item_refs), None)?
            };
            let mut expected = Map::new();
            expected.insert(
                "collection_frame_base64url".to_string(),
                Value::String(encode_base64url(&encoded.collection_frame)),
            );
            Ok(expected)
        }
        "semantic-digest" => {
            let kind = parse_digest_kind(required_str_value(input, "digest_kind")?)?;
            let payload = decode_field_base64url(input, "canonical_payload_base64url")?;
            let digest = semantic_digest(kind, &payload)?;
            let mut expected = Map::new();
            expected.insert(
                "raw_hash_base64url".to_string(),
                Value::String(encode_base64url(digest.raw_digest())),
            );
            expected.insert(
                "digest_ref".to_string(),
                Value::String(digest.digest_ref().as_str().to_string()),
            );
            Ok(expected)
        }
        "raw-blob-digest" => {
            let raw = decode_field_base64url(input, "raw_bytes_base64url")?;
            let digest = raw_blob_digest(&raw)?;
            let mut expected = Map::new();
            expected.insert(
                "digest_ref".to_string(),
                Value::String(digest.as_str().to_string()),
            );
            Ok(expected)
        }
        "validate-scalar-frame" => {
            let frame = decode_field_base64url(input, "frame_base64url")?;
            validate_scalar_frame(&frame)?;
            Ok(Map::new())
        }
        other => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            format!("unsupported operation {other:?}"),
        )),
    }
}

fn dispatch_invalid(
    operation: &str,
    input: &Map<String, Value>,
    expected_code: &str,
) -> Result<(), DispatchMismatch> {
    let result = if operation == "validate-scalar-frame" {
        let frame = decode_field_base64url(input, "frame_base64url").map_err(|error| {
            dispatch_mismatch(format!(
                "expected stable code {expected_code}, got decode error: {}",
                error.stable_code()
            ))
        })?;
        validate_scalar_frame(&frame).map(|_| ())
    } else {
        compute_expected(operation, input).map(|_| ())
    };

    match result {
        Ok(()) => Err(dispatch_mismatch(format!(
            "expected stable code {expected_code}, but operation succeeded"
        ))),
        Err(error) => {
            if error.stable_code() == expected_code {
                Ok(())
            } else {
                Err(dispatch_mismatch(format!(
                    "expected stable code {expected_code}, got {}",
                    error.stable_code()
                )))
            }
        }
    }
}

fn parse_declared_type(obj: &Map<String, Value>) -> Result<DeclaredType, CanonicalEncodingError> {
    let kind = required_str_value(obj, "kind")?;
    match kind {
        "null" => Ok(DeclaredType::null()),
        "boolean" => Ok(DeclaredType::boolean()),
        "signed-integer" => {
            let bits = required_u8(obj, "bits")?;
            DeclaredType::signed_integer(bits).map_err(type_mismatch_from_construction)
        }
        "unsigned-integer" => {
            let bits = required_u8(obj, "bits")?;
            DeclaredType::unsigned_integer(bits).map_err(type_mismatch_from_construction)
        }
        "decimal" => {
            let precision = required_u8(obj, "precision")?;
            let scale = required_u8(obj, "scale")?;
            DeclaredType::decimal(precision, scale).map_err(type_mismatch_from_construction)
        }
        "float32" => Ok(DeclaredType::float32()),
        "float64" => Ok(DeclaredType::float64()),
        "string" => Ok(DeclaredType::string()),
        "binary" => Ok(DeclaredType::binary()),
        "bit" => {
            let bit_width = required_u8(obj, "bit_width")?;
            DeclaredType::bit(bit_width).map_err(type_mismatch_from_construction)
        }
        "date" => Ok(DeclaredType::date()),
        "datetime" => Ok(DeclaredType::datetime()),
        "timestamp" => Ok(DeclaredType::timestamp()),
        "time-duration" => Ok(DeclaredType::time_duration()),
        "source-literal-anomaly" => Ok(DeclaredType::source_literal_anomaly()),
        other => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            format!("unknown declared type kind {other:?}"),
        )),
    }
}

fn parse_logical_literal(
    obj: &Map<String, Value>,
) -> Result<LogicalLiteral, CanonicalEncodingError> {
    let kind = required_str_value(obj, "kind")?;
    match kind {
        "utf8-logical-literal" => Ok(LogicalLiteral::Utf8(Utf8LogicalLiteral {
            text: required_str_value(obj, "text")?.to_string(),
        })),
        "raw-logical-literal" => Ok(LogicalLiteral::Raw(RawLogicalLiteral {
            raw_bytes: decode_field_base64url(obj, "bytes_base64url")?,
        })),
        other => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            format!("unknown logical literal kind {other:?}"),
        )),
    }
}

fn parse_typed_value(obj: &Map<String, Value>) -> Result<TypedScalar, CanonicalEncodingError> {
    let kind = required_str_value(obj, "kind")?;
    match kind {
        "null" => Ok(TypedScalar::Null(NullScalar)),
        "boolean" => Ok(TypedScalar::Boolean(BooleanScalar {
            value: required_bool(obj, "value")?,
        })),
        "signed-integer" => Ok(TypedScalar::SignedInteger(SignedIntegerScalar {
            decimal: required_str_value(obj, "decimal")?.to_string(),
        })),
        "unsigned-integer" => Ok(TypedScalar::UnsignedInteger(UnsignedIntegerScalar {
            decimal: required_str_value(obj, "decimal")?.to_string(),
        })),
        "decimal" => Ok(TypedScalar::Decimal(DecimalScalar {
            decimal: required_str_value(obj, "decimal")?.to_string(),
        })),
        "float32" => Ok(TypedScalar::Float32(Float32Scalar {
            bits_hex: required_str_value(obj, "bits_hex")?.to_string(),
        })),
        "float64" => Ok(TypedScalar::Float64(Float64Scalar {
            bits_hex: required_str_value(obj, "bits_hex")?.to_string(),
        })),
        "string" => Ok(TypedScalar::String(StringScalar {
            text: required_str_value(obj, "text")?.to_string(),
        })),
        "binary" => Ok(TypedScalar::Binary(BinaryScalar {
            raw_bytes: decode_field_base64url(obj, "bytes_base64url")?,
        })),
        "bit" => Ok(TypedScalar::Bit(BitScalar {
            raw_bytes: decode_field_base64url(obj, "bytes_base64url")?,
        })),
        "date" => Ok(TypedScalar::Date(DateScalar {
            text: required_str_value(obj, "text")?.to_string(),
        })),
        "datetime" => Ok(TypedScalar::DateTime(DateTimeScalar {
            text: required_str_value(obj, "text")?.to_string(),
        })),
        "timestamp" => Ok(TypedScalar::Timestamp(TimestampScalar {
            text: required_str_value(obj, "text")?.to_string(),
        })),
        "time-duration" => Ok(TypedScalar::TimeDuration(TimeDurationScalar {
            text: required_str_value(obj, "text")?.to_string(),
        })),
        "source-literal-anomaly" => {
            let envelope = required_object_value(obj, "envelope")?;
            Ok(TypedScalar::Anomaly(AnomalyScalar {
                declared_type: parse_declared_type(required_object_value(
                    envelope,
                    "declared_type",
                )?)?,
                raw_base64url: required_str_value(envelope, "raw_base64url")?.to_string(),
                raw_encoding: required_str_value(envelope, "raw_encoding")?.to_string(),
                reason: required_str_value(envelope, "reason")?.to_string(),
            }))
        }
        other => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            format!("unknown typed value kind {other:?}"),
        )),
    }
}

fn typed_value_to_json(value: &TypedScalar) -> Result<Value, CanonicalEncodingError> {
    let object = match value {
        TypedScalar::Null(_) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("null".to_string()));
            map
        }
        TypedScalar::Boolean(boolean) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("boolean".to_string()));
            map.insert("value".to_string(), Value::Bool(boolean.value));
            map
        }
        TypedScalar::SignedInteger(integer) => {
            let mut map = Map::new();
            map.insert(
                "kind".to_string(),
                Value::String("signed-integer".to_string()),
            );
            map.insert(
                "decimal".to_string(),
                Value::String(integer.decimal.clone()),
            );
            map
        }
        TypedScalar::UnsignedInteger(integer) => {
            let mut map = Map::new();
            map.insert(
                "kind".to_string(),
                Value::String("unsigned-integer".to_string()),
            );
            map.insert(
                "decimal".to_string(),
                Value::String(integer.decimal.clone()),
            );
            map
        }
        TypedScalar::Decimal(decimal) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("decimal".to_string()));
            map.insert(
                "decimal".to_string(),
                Value::String(decimal.decimal.clone()),
            );
            map
        }
        TypedScalar::Float32(float) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("float32".to_string()));
            map.insert(
                "bits_hex".to_string(),
                Value::String(float.bits_hex.clone()),
            );
            map
        }
        TypedScalar::Float64(float) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("float64".to_string()));
            map.insert(
                "bits_hex".to_string(),
                Value::String(float.bits_hex.clone()),
            );
            map
        }
        TypedScalar::String(string) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("string".to_string()));
            map.insert("text".to_string(), Value::String(string.text.clone()));
            map
        }
        TypedScalar::Binary(binary) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("binary".to_string()));
            map.insert(
                "bytes_base64url".to_string(),
                Value::String(encode_base64url(&binary.raw_bytes)),
            );
            map
        }
        TypedScalar::Bit(bit) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("bit".to_string()));
            map.insert(
                "bytes_base64url".to_string(),
                Value::String(encode_base64url(&bit.raw_bytes)),
            );
            map
        }
        TypedScalar::Date(date) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("date".to_string()));
            map.insert("text".to_string(), Value::String(date.text.clone()));
            map
        }
        TypedScalar::DateTime(datetime) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("datetime".to_string()));
            map.insert("text".to_string(), Value::String(datetime.text.clone()));
            map
        }
        TypedScalar::Timestamp(timestamp) => {
            let mut map = Map::new();
            map.insert("kind".to_string(), Value::String("timestamp".to_string()));
            map.insert("text".to_string(), Value::String(timestamp.text.clone()));
            map
        }
        TypedScalar::TimeDuration(duration) => {
            let mut map = Map::new();
            map.insert(
                "kind".to_string(),
                Value::String("time-duration".to_string()),
            );
            map.insert("text".to_string(), Value::String(duration.text.clone()));
            map
        }
        TypedScalar::Anomaly(anomaly) => {
            let mut envelope = Map::new();
            envelope.insert(
                "declared_type".to_string(),
                declared_type_to_json(&anomaly.declared_type)?,
            );
            envelope.insert(
                "raw_base64url".to_string(),
                Value::String(anomaly.raw_base64url.clone()),
            );
            envelope.insert(
                "raw_encoding".to_string(),
                Value::String(anomaly.raw_encoding.clone()),
            );
            envelope.insert("reason".to_string(), Value::String(anomaly.reason.clone()));
            let mut map = Map::new();
            map.insert(
                "kind".to_string(),
                Value::String("source-literal-anomaly".to_string()),
            );
            map.insert("envelope".to_string(), Value::Object(envelope));
            map
        }
    };
    Ok(Value::Object(object))
}

fn declared_type_to_json(declared: &DeclaredType) -> Result<Value, CanonicalEncodingError> {
    let mut map = Map::new();
    map.insert(
        "kind".to_string(),
        Value::String(declared.kind_str().to_string()),
    );
    match declared {
        DeclaredType::SignedInteger { bits } | DeclaredType::UnsignedInteger { bits } => {
            map.insert("bits".to_string(), Value::Number((*bits).into()));
        }
        DeclaredType::Decimal { precision, scale } => {
            map.insert("precision".to_string(), Value::Number((*precision).into()));
            map.insert("scale".to_string(), Value::Number((*scale).into()));
        }
        DeclaredType::Bit { bit_width } => {
            map.insert("bit_width".to_string(), Value::Number((*bit_width).into()));
        }
        DeclaredType::Null
        | DeclaredType::Boolean
        | DeclaredType::Float32
        | DeclaredType::Float64
        | DeclaredType::String
        | DeclaredType::Binary
        | DeclaredType::Date
        | DeclaredType::DateTime
        | DeclaredType::Timestamp
        | DeclaredType::TimeDuration
        | DeclaredType::SourceLiteralAnomaly => {}
    }
    Ok(Value::Object(map))
}

fn parse_collection_semantics(value: &str) -> Result<CollectionSemantics, CanonicalEncodingError> {
    match value {
        "sequence" => Ok(CollectionSemantics::Sequence),
        "multiset" => Ok(CollectionSemantics::Multiset),
        "set" => Ok(CollectionSemantics::Set),
        "keyed-collection" => Ok(CollectionSemantics::KeyedCollection),
        other => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::CollectionSemanticsUnknown,
            format!("unknown collection semantics {other:?}"),
        )),
    }
}

fn parse_digest_kind(value: &str) -> Result<DigestKind, CanonicalEncodingError> {
    for kind in DigestKind::all() {
        if kind.as_str() == value {
            return Ok(*kind);
        }
    }
    Err(CanonicalEncodingError::with_message(
        CanonicalErrorCode::TypeMismatch,
        format!("unknown digest kind {value:?}"),
    ))
}

fn decode_field_base64url(
    obj: &Map<String, Value>,
    field: &str,
) -> Result<Vec<u8>, CanonicalEncodingError> {
    let text = required_str_value(obj, field)?;
    decode_base64url_strict(text)
}

fn required_object<'a>(
    value: &'a Value,
    field: &str,
) -> Result<&'a Map<String, Value>, DispatchMismatch> {
    value
        .get(field)
        .and_then(Value::as_object)
        .ok_or_else(|| dispatch_mismatch(format!("case missing object field {field:?}")))
}

fn required_object_value<'a>(
    obj: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a Map<String, Value>, CanonicalEncodingError> {
    obj.get(field)
        .and_then(Value::as_object)
        .ok_or_else(|| type_mismatch(format!("missing object field {field:?}")))
}

fn required_str<'a>(value: &'a Value, field: &str) -> Result<&'a str, DispatchMismatch> {
    value
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| dispatch_mismatch(format!("case missing string field {field:?}")))
}

fn required_str_value<'a>(
    obj: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a str, CanonicalEncodingError> {
    obj.get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| type_mismatch(format!("missing string field {field:?}")))
}

fn required_bool(obj: &Map<String, Value>, field: &str) -> Result<bool, CanonicalEncodingError> {
    obj.get(field)
        .and_then(Value::as_bool)
        .ok_or_else(|| type_mismatch(format!("missing bool field {field:?}")))
}

fn required_u8(obj: &Map<String, Value>, field: &str) -> Result<u8, CanonicalEncodingError> {
    let number = obj
        .get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| type_mismatch(format!("missing integer field {field:?}")))?;
    u8::try_from(number).map_err(|_| type_mismatch(format!("field {field:?} out of u8 range")))
}

fn type_mismatch(message: impl Into<String>) -> CanonicalEncodingError {
    CanonicalEncodingError::with_message(CanonicalErrorCode::TypeMismatch, message)
}

fn type_mismatch_from_construction(
    error: gateway_shared_kernel::TypeConstructionError,
) -> CanonicalEncodingError {
    CanonicalEncodingError::with_message(CanonicalErrorCode::TypeMismatch, error.to_string())
}

fn dispatch_mismatch(message: impl Into<String>) -> DispatchMismatch {
    DispatchMismatch {
        message: message.into(),
    }
}
