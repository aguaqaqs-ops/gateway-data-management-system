//! Typed scalar normalization and frame encoding.
//!
//! Formal production entries: [`normalize_logical_literal`], [`encode_typed_scalar`].
//! Typed-only normalization stays crate-internal.

use serde_json::{Map, Number, Value};

use crate::base64url::decode_base64url_strict;
use crate::errors::{CanonicalEncodingError, CanonicalErrorCode};
use crate::jcs::canonicalize_json_value;
use crate::types::{
    AnomalyScalar, BinaryScalar, BitScalar, BooleanScalar, DateScalar, DateTimeScalar,
    DecimalScalar, DeclaredType, EncodedScalar, Float32Scalar, Float64Scalar, LogicalLiteral,
    NormalizedScalar, NullScalar, RawLogicalLiteral, SignedIntegerScalar, StringScalar,
    TimeDurationScalar, TimestampScalar, TypedScalar, UnsignedIntegerScalar, Utf8LogicalLiteral,
};
use crate::uleb128::encode_uleb128;
use crate::unicode::{decode_utf8, validate_unicode_string};

const LEADING_ZERO_BUDGET: usize = 16;

const TAG_NULL: u8 = 0x00;
const TAG_BOOLEAN: u8 = 0x01;
const TAG_SIGNED_INTEGER: u8 = 0x10;
const TAG_UNSIGNED_INTEGER: u8 = 0x11;
const TAG_DECIMAL: u8 = 0x12;
const TAG_FLOAT32: u8 = 0x13;
const TAG_FLOAT64: u8 = 0x14;
const TAG_STRING: u8 = 0x20;
const TAG_BINARY: u8 = 0x21;
const TAG_DATE: u8 = 0x30;
const TAG_DATETIME: u8 = 0x31;
const TAG_TIMESTAMP: u8 = 0x32;
const TAG_TIME_DURATION: u8 = 0x33;
const TAG_ANOMALY: u8 = 0x7f;

/// Normalize a logical literal to typed value + payload + scalar frame.
pub fn normalize_logical_literal(
    declared_type: &DeclaredType,
    source: &LogicalLiteral,
) -> Result<NormalizedScalar, CanonicalEncodingError> {
    let typed = normalize_to_typed_scalar(declared_type, source)?;
    let encoded = encode_typed_scalar(declared_type, &typed)?;
    Ok(NormalizedScalar {
        typed_value: typed,
        payload: encoded.payload,
        scalar_frame: encoded.scalar_frame,
    })
}

/// Encode an already-typed scalar into payload and scalar frame.
pub fn encode_typed_scalar(
    declared_type: &DeclaredType,
    value: &TypedScalar,
) -> Result<EncodedScalar, CanonicalEncodingError> {
    if let Err(error) = declared_type.validate() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            error.to_string(),
        ));
    }
    assert_kind_match(declared_type, value)?;
    let payload = encode_payload(declared_type, value)?;
    let tag = tag_for(declared_type);
    let length = match u64::try_from(payload.len()) {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::Uleb128Overflow,
                "payload length exceeds ULEB128 maximum",
            ));
        }
    };
    let mut scalar_frame = Vec::with_capacity(1 + 10 + payload.len());
    scalar_frame.push(tag);
    scalar_frame.extend(encode_uleb128(length)?);
    scalar_frame.extend_from_slice(&payload);
    Ok(EncodedScalar {
        payload,
        scalar_frame,
    })
}

/// Normalize a logical literal into a typed scalar value (crate-internal).
pub(crate) fn normalize_to_typed_scalar(
    declared_type: &DeclaredType,
    source: &LogicalLiteral,
) -> Result<TypedScalar, CanonicalEncodingError> {
    if let Err(error) = declared_type.validate() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            error.to_string(),
        ));
    }
    match declared_type {
        DeclaredType::Null => normalize_null(source),
        DeclaredType::Boolean => Ok(TypedScalar::Boolean(BooleanScalar {
            value: parse_boolean_literal(source)?,
        })),
        DeclaredType::SignedInteger { bits } => {
            Ok(TypedScalar::SignedInteger(SignedIntegerScalar {
                decimal: normalize_integer_literal(literal_text(source)?, true, *bits)?,
            }))
        }
        DeclaredType::UnsignedInteger { bits } => {
            Ok(TypedScalar::UnsignedInteger(UnsignedIntegerScalar {
                decimal: normalize_integer_literal(literal_text(source)?, false, *bits)?,
            }))
        }
        DeclaredType::Decimal { precision, scale } => Ok(TypedScalar::Decimal(DecimalScalar {
            decimal: normalize_decimal_literal(literal_text(source)?, *precision, *scale)?,
        })),
        DeclaredType::Float32 => Ok(TypedScalar::Float32(Float32Scalar {
            bits_hex: normalize_float_literal(literal_text(source)?, 32)?,
        })),
        DeclaredType::Float64 => Ok(TypedScalar::Float64(Float64Scalar {
            bits_hex: normalize_float_literal(literal_text(source)?, 64)?,
        })),
        DeclaredType::String => {
            let text = literal_text(source)?;
            validate_unicode_string(text)?;
            Ok(TypedScalar::String(StringScalar {
                text: text.to_string(),
            }))
        }
        DeclaredType::Binary => Ok(TypedScalar::Binary(BinaryScalar {
            raw_bytes: literal_bytes(source)?.to_vec(),
        })),
        DeclaredType::Bit { bit_width } => {
            let raw = literal_bytes(source)?.to_vec();
            validate_bit_bytes(&raw, *bit_width)?;
            Ok(TypedScalar::Bit(BitScalar { raw_bytes: raw }))
        }
        DeclaredType::Date => Ok(TypedScalar::Date(DateScalar {
            text: canonicalize_date(literal_text(source)?)?,
        })),
        DeclaredType::DateTime => Ok(TypedScalar::DateTime(DateTimeScalar {
            text: canonicalize_datetime(literal_text(source)?)?,
        })),
        DeclaredType::Timestamp => Ok(TypedScalar::Timestamp(TimestampScalar {
            text: canonicalize_timestamp(literal_text(source)?)?,
        })),
        DeclaredType::TimeDuration => Ok(TypedScalar::TimeDuration(TimeDurationScalar {
            text: canonicalize_time_duration(literal_text(source)?)?,
        })),
        DeclaredType::SourceLiteralAnomaly => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "anomaly scalars are not produced from logical literals",
        )),
    }
}

fn normalize_null(source: &LogicalLiteral) -> Result<TypedScalar, CanonicalEncodingError> {
    match source {
        LogicalLiteral::Raw(RawLogicalLiteral { raw_bytes }) => {
            if !raw_bytes.is_empty() {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    "null raw literal must be empty",
                ));
            }
            Ok(TypedScalar::Null(NullScalar))
        }
        LogicalLiteral::Utf8(_) => {
            let text = literal_text(source)?;
            if !text.is_empty() && text != "null" {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    "null logical literal must be empty or 'null'",
                ));
            }
            Ok(TypedScalar::Null(NullScalar))
        }
    }
}

fn literal_text(source: &LogicalLiteral) -> Result<&str, CanonicalEncodingError> {
    match source {
        LogicalLiteral::Utf8(Utf8LogicalLiteral { text }) => {
            validate_unicode_string(text)?;
            Ok(text.as_str())
        }
        LogicalLiteral::Raw(RawLogicalLiteral { raw_bytes }) => decode_utf8(raw_bytes),
    }
}

fn literal_bytes(source: &LogicalLiteral) -> Result<&[u8], CanonicalEncodingError> {
    match source {
        LogicalLiteral::Raw(RawLogicalLiteral { raw_bytes }) => Ok(raw_bytes.as_slice()),
        LogicalLiteral::Utf8(Utf8LogicalLiteral { text }) => {
            validate_unicode_string(text)?;
            Ok(text.as_bytes())
        }
    }
}

fn parse_boolean_literal(source: &LogicalLiteral) -> Result<bool, CanonicalEncodingError> {
    match source {
        LogicalLiteral::Raw(RawLogicalLiteral { raw_bytes }) => match raw_bytes.as_slice() {
            [0x00] => Ok(false),
            [0x01] => Ok(true),
            _ => Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TypeMismatch,
                "boolean raw literal must be 0x00 or 0x01",
            )),
        },
        LogicalLiteral::Utf8(_) => {
            let text = literal_text(source)?;
            match text {
                "true" | "1" => Ok(true),
                "false" | "0" => Ok(false),
                _ => Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    "boolean logical literal must be true/false/0/1",
                )),
            }
        }
    }
}

fn max_integer_digits(bits: u8) -> usize {
    let ceil_log10 = match bits {
        8 => 3,
        16 => 5,
        24 => 8,
        32 => 10,
        64 => 20,
        _ => 0,
    };
    ceil_log10 + LEADING_ZERO_BUDGET
}

fn is_ascii_digits(text: &str) -> bool {
    !text.is_empty() && text.bytes().all(|b| b.is_ascii_digit())
}

fn normalize_integer_literal(
    text: &str,
    signed: bool,
    bits: u8,
) -> Result<String, CanonicalEncodingError> {
    if !is_integer_literal_form(text) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "integer literal must be optional ASCII sign plus digits",
        ));
    }
    let mut body = text;
    let mut negative = false;
    if let Some(rest) = body.strip_prefix('+') {
        body = rest;
    } else if let Some(rest) = body.strip_prefix('-') {
        if !signed {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::IntegerOutOfRange,
                "unsigned integer rejects negative literal",
            ));
        }
        negative = true;
        body = rest;
    }
    if !is_ascii_digits(body) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "integer literal must be decimal digits",
        ));
    }
    if body.len() > max_integer_digits(bits) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "integer literal exceeds lexical length budget",
        ));
    }
    let magnitude: u128 = match body.parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TypeMismatch,
                "integer literal is not convertible",
            ));
        }
    };
    let value = if negative {
        let mag = match i128::try_from(magnitude) {
            Ok(value) => value,
            Err(_) => {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::IntegerOutOfRange,
                    "integer outside declared width",
                ));
            }
        };
        match mag.checked_neg() {
            Some(value) => value,
            None => {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::IntegerOutOfRange,
                    "integer outside declared width",
                ));
            }
        }
    } else {
        match i128::try_from(magnitude) {
            Ok(value) => value,
            Err(_) => {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::IntegerOutOfRange,
                    "integer outside declared width",
                ));
            }
        }
    };
    if value == 0 {
        return Ok("0".to_string());
    }
    let (lo, hi) = integer_bounds(signed, bits);
    if value < lo || value > hi {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::IntegerOutOfRange,
            "integer outside declared width",
        ));
    }
    Ok(value.to_string())
}

fn is_integer_literal_form(text: &str) -> bool {
    let bytes = text.as_bytes();
    if bytes.is_empty() {
        return false;
    }
    let mut index = 0usize;
    if matches!(bytes[0], b'+' | b'-') {
        index = 1;
    }
    if index >= bytes.len() {
        return false;
    }
    bytes[index..].iter().all(|b| b.is_ascii_digit())
}

fn integer_bounds(signed: bool, bits: u8) -> (i128, i128) {
    if signed {
        let half = 1i128 << (bits - 1);
        (-half, half - 1)
    } else {
        (0, (1i128 << bits) - 1)
    }
}

fn normalize_decimal_literal(
    text: &str,
    precision: u8,
    scale: u8,
) -> Result<String, CanonicalEncodingError> {
    if !is_decimal_literal_form(text) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::DecimalInvalid,
            "decimal literal rejects non-ASCII or invalid form",
        ));
    }
    let mut negative = false;
    let mut body = text;
    if let Some(rest) = body.strip_prefix('-') {
        negative = true;
        body = rest;
    }
    let (integer_raw, frac_raw) = match body.split_once('.') {
        Some((integer_part, frac_part)) => (integer_part, frac_part),
        None => (body, ""),
    };
    let mut integer_part = if integer_raw.is_empty() {
        "0".to_string()
    } else {
        integer_raw.to_string()
    };
    let frac_part = frac_raw.to_string();
    if integer_part.len() + frac_part.len() > usize::from(precision) + LEADING_ZERO_BUDGET {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::DecimalInvalid,
            "decimal literal exceeds lexical length budget",
        ));
    }
    integer_part = strip_leading_zeros(&integer_part);
    let frac_trimmed = strip_trailing_zeros(&frac_part);
    if frac_trimmed.len() > usize::from(scale) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::DecimalInvalid,
            "decimal fractional digits exceed scale",
        ));
    }
    let int_digits = if integer_part == "0" {
        0
    } else {
        integer_part.len()
    };
    if int_digits > usize::from(precision - scale) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::DecimalInvalid,
            "decimal integer digits exceed precision-scale",
        ));
    }
    let canonical = if frac_trimmed.is_empty() {
        integer_part
    } else {
        format!("{integer_part}.{frac_trimmed}")
    };
    if canonical == "0" {
        return Ok("0".to_string());
    }
    if negative {
        Ok(format!("-{canonical}"))
    } else {
        Ok(canonical)
    }
}

fn is_decimal_literal_form(text: &str) -> bool {
    // -?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)
    let bytes = text.as_bytes();
    if bytes.is_empty() {
        return false;
    }
    let mut index = 0usize;
    if bytes[0] == b'-' {
        index = 1;
        if index >= bytes.len() {
            return false;
        }
    }
    if bytes[index] == b'.' {
        index += 1;
        if index >= bytes.len() {
            return false;
        }
        return bytes[index..].iter().all(|b| b.is_ascii_digit());
    }
    let mut saw_digit = false;
    while index < bytes.len() && bytes[index].is_ascii_digit() {
        saw_digit = true;
        index += 1;
    }
    if !saw_digit {
        return false;
    }
    if index == bytes.len() {
        return true;
    }
    if bytes[index] != b'.' {
        return false;
    }
    index += 1;
    if index >= bytes.len() {
        return false;
    }
    bytes[index..].iter().all(|b| b.is_ascii_digit())
}

fn strip_leading_zeros(text: &str) -> String {
    let trimmed = text.trim_start_matches('0');
    if trimmed.is_empty() {
        "0".to_string()
    } else {
        trimmed.to_string()
    }
}

fn strip_trailing_zeros(text: &str) -> String {
    text.trim_end_matches('0').to_string()
}

fn normalize_float_literal(text: &str, width: u8) -> Result<String, CanonicalEncodingError> {
    if !is_float_literal_form(text) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "float literal must match ASCII float grammar",
        ));
    }
    let digit_count = text.bytes().filter(|b| b.is_ascii_digit()).count();
    let max_digits = if width == 32 { 38 } else { 309 } + LEADING_ZERO_BUDGET;
    if digit_count > max_digits {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "float literal exceeds lexical length budget",
        ));
    }
    // Parse at the declared width so float32 is a single round-to-nearest
    // ties-to-even into binary32 (no binary64 intermediate).
    if width == 32 {
        let value: f32 = match text.parse() {
            Ok(value) => value,
            Err(_) => {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    "float literal is not numeric",
                ));
            }
        };
        float32_bits_hex(value)
    } else {
        let value: f64 = match text.parse() {
            Ok(value) => value,
            Err(_) => {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    "float literal is not numeric",
                ));
            }
        };
        float64_bits_hex(value)
    }
}

fn is_float_literal_form(text: &str) -> bool {
    // [+-]? ( [0-9]+ ('.' [0-9]*)? | '.' [0-9]+ ) ([eE][+-]?[0-9]+)?
    let bytes = text.as_bytes();
    if bytes.is_empty() {
        return false;
    }
    let mut index = 0usize;
    if matches!(bytes[0], b'+' | b'-') {
        index = 1;
        if index >= bytes.len() {
            return false;
        }
    }
    let significand_start = index;
    if bytes[index] == b'.' {
        index += 1;
        let frac_start = index;
        while index < bytes.len() && bytes[index].is_ascii_digit() {
            index += 1;
        }
        if index == frac_start {
            return false;
        }
    } else {
        let int_start = index;
        while index < bytes.len() && bytes[index].is_ascii_digit() {
            index += 1;
        }
        if index == int_start {
            return false;
        }
        if index < bytes.len() && bytes[index] == b'.' {
            index += 1;
            while index < bytes.len() && bytes[index].is_ascii_digit() {
                index += 1;
            }
        }
    }
    if index == significand_start {
        return false;
    }
    if index < bytes.len() && matches!(bytes[index], b'e' | b'E') {
        index += 1;
        if index < bytes.len() && matches!(bytes[index], b'+' | b'-') {
            index += 1;
        }
        let exp_start = index;
        while index < bytes.len() && bytes[index].is_ascii_digit() {
            index += 1;
        }
        if index == exp_start {
            return false;
        }
    }
    index == bytes.len()
}

fn float32_bits_hex(value: f32) -> Result<String, CanonicalEncodingError> {
    if !value.is_finite() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::FloatNonFinite,
            "float must be finite",
        ));
    }
    let mut bits = value.to_bits();
    if bits == 0x8000_0000 {
        bits = 0;
    }
    Ok(format!("{bits:08x}"))
}

fn float64_bits_hex(value: f64) -> Result<String, CanonicalEncodingError> {
    if !value.is_finite() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::FloatNonFinite,
            "float must be finite",
        ));
    }
    let mut bits = value.to_bits();
    if bits == 0x8000_0000_0000_0000 {
        bits = 0;
    }
    Ok(format!("{bits:016x}"))
}

pub(crate) fn validate_bit_bytes(raw: &[u8], bit_width: u8) -> Result<(), CanonicalEncodingError> {
    let expected_len = usize::from(bit_width).div_ceil(8);
    if raw.len() != expected_len {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "BIT payload length must be ceil(bit_width/8)",
        ));
    }
    let mut magnitude: u128 = 0;
    for byte in raw {
        magnitude = (magnitude << 8) | u128::from(*byte);
    }
    if magnitude >> bit_width != 0 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "BIT unused high bits must be zero",
        ));
    }
    Ok(())
}

fn canonicalize_date(text: &str) -> Result<String, CanonicalEncodingError> {
    let (year, month, day) = parse_date_parts(text)?;
    validate_civil_date(year, month, day)?;
    Ok(format!("{year:04}-{month:02}-{day:02}"))
}

fn canonicalize_datetime(text: &str) -> Result<String, CanonicalEncodingError> {
    let (date, time) = match text.split_once('T') {
        Some(parts) => parts,
        None => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "datetime must be YYYY-MM-DDTHH:MM:SS[.fraction]",
            ));
        }
    };
    let (year, month, day) = parse_date_parts(date)?;
    let (hour, minute, second, fraction) = parse_clock_with_fraction(time)?;
    validate_civil_date(year, month, day)?;
    validate_clock(hour, minute, second)?;
    let fraction_text = format_fraction(fraction);
    Ok(format!(
        "{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}{fraction_text}"
    ))
}

fn canonicalize_timestamp(text: &str) -> Result<String, CanonicalEncodingError> {
    let body = match text.strip_suffix('Z') {
        Some(body) => body,
        None => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "timestamp must be YYYY-MM-DDTHH:MM:SS[.fraction]Z",
            ));
        }
    };
    let (date, time) = match body.split_once('T') {
        Some(parts) => parts,
        None => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "timestamp must be YYYY-MM-DDTHH:MM:SS[.fraction]Z",
            ));
        }
    };
    let (year, month, day) = parse_date_parts(date)?;
    let (hour, minute, second, fraction) = parse_clock_with_fraction(time)?;
    validate_civil_date(year, month, day)?;
    validate_clock(hour, minute, second)?;
    let fraction_text = format_fraction(fraction);
    Ok(format!(
        "{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}{fraction_text}Z"
    ))
}

fn canonicalize_time_duration(text: &str) -> Result<String, CanonicalEncodingError> {
    let mut negative = false;
    let body = if let Some(rest) = text.strip_prefix('-') {
        negative = true;
        rest
    } else {
        text
    };
    let parts: Vec<&str> = body.split(':').collect();
    if parts.len() != 3 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "time duration lexical form invalid",
        ));
    }
    let hour_token = parts[0];
    if hour_token.len() < 2 || hour_token.len() > 3 || !is_ascii_digits(hour_token) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "time duration lexical form invalid",
        ));
    }
    if !is_ascii_digits(parts[1]) || parts[1].len() != 2 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "time duration lexical form invalid",
        ));
    }
    let (second_token, fraction) = match parts[2].split_once('.') {
        Some((seconds, frac)) => {
            if frac.is_empty() || frac.len() > 6 || !is_ascii_digits(frac) {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TemporalInvalid,
                    "time duration lexical form invalid",
                ));
            }
            (seconds, Some(frac))
        }
        None => (parts[2], None),
    };
    if !is_ascii_digits(second_token) || second_token.len() != 2 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "time duration lexical form invalid",
        ));
    }
    let hour: u32 = match hour_token.parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "time duration lexical form invalid",
            ));
        }
    };
    let minute: u32 = match parts[1].parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "time duration lexical form invalid",
            ));
        }
    };
    let second: u32 = match second_token.parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "time duration lexical form invalid",
            ));
        }
    };
    if minute > 59 || second > 59 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "time duration minute/second out of range",
        ));
    }
    if hour > 838 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TimeOutOfRange,
            "time duration exceeds 838 hours",
        ));
    }
    if hour <= 99 && hour_token.len() != 2 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "time duration 0-99 hours must use two digits",
        ));
    }
    if hour >= 100 && hour_token.len() != 3 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "time duration 100-838 hours must use three digits",
        ));
    }
    let fraction_text = format_fraction(fraction);
    if hour == 0 && minute == 0 && second == 0 && fraction_text.is_empty() {
        return Ok("00:00:00".to_string());
    }
    let hour_text = if hour <= 99 {
        format!("{hour:02}")
    } else {
        format!("{hour:03}")
    };
    let body = format!("{hour_text}:{minute:02}:{second:02}{fraction_text}");
    if negative {
        Ok(format!("-{body}"))
    } else {
        Ok(body)
    }
}

fn parse_date_parts(text: &str) -> Result<(i32, u32, u32), CanonicalEncodingError> {
    let parts: Vec<&str> = text.split('-').collect();
    if parts.len() != 3
        || parts[0].len() != 4
        || parts[1].len() != 2
        || parts[2].len() != 2
        || !parts.iter().all(|part| is_ascii_digits(part))
    {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "date must be YYYY-MM-DD",
        ));
    }
    let year: i32 = match parts[0].parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "date must be YYYY-MM-DD",
            ));
        }
    };
    let month: u32 = match parts[1].parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "date must be YYYY-MM-DD",
            ));
        }
    };
    let day: u32 = match parts[2].parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "date must be YYYY-MM-DD",
            ));
        }
    };
    Ok((year, month, day))
}

fn parse_clock_with_fraction(
    text: &str,
) -> Result<(u32, u32, u32, Option<&str>), CanonicalEncodingError> {
    let parts: Vec<&str> = text.split(':').collect();
    if parts.len() != 3 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "civil time out of range",
        ));
    }
    if parts[0].len() != 2
        || parts[1].len() != 2
        || !is_ascii_digits(parts[0])
        || !is_ascii_digits(parts[1])
    {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "civil time out of range",
        ));
    }
    let (second_token, fraction) = match parts[2].split_once('.') {
        Some((seconds, frac)) => {
            if frac.is_empty() || frac.len() > 6 || !is_ascii_digits(frac) {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TemporalInvalid,
                    "civil time out of range",
                ));
            }
            (seconds, Some(frac))
        }
        None => (parts[2], None),
    };
    if second_token.len() != 2 || !is_ascii_digits(second_token) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "civil time out of range",
        ));
    }
    let hour: u32 = match parts[0].parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "civil time out of range",
            ));
        }
    };
    let minute: u32 = match parts[1].parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "civil time out of range",
            ));
        }
    };
    let second: u32 = match second_token.parse() {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TemporalInvalid,
                "civil time out of range",
            ));
        }
    };
    Ok((hour, minute, second, fraction))
}

fn format_fraction(frac: Option<&str>) -> String {
    match frac {
        None => String::new(),
        Some(frac) => {
            let trimmed = frac.trim_end_matches('0');
            if trimmed.is_empty() {
                String::new()
            } else {
                format!(".{trimmed}")
            }
        }
    }
}

fn is_leap_year(year: i32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn days_in_month(year: i32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if is_leap_year(year) {
                29
            } else {
                28
            }
        }
        _ => 0,
    }
}

fn validate_civil_date(year: i32, month: u32, day: u32) -> Result<(), CanonicalEncodingError> {
    if year < 1 || !(1..=12).contains(&month) || day < 1 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "civil date out of range",
        ));
    }
    if day > days_in_month(year, month) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "civil date day invalid for month",
        ));
    }
    Ok(())
}

fn validate_clock(hour: u32, minute: u32, second: u32) -> Result<(), CanonicalEncodingError> {
    if hour > 23 || minute > 59 || second > 59 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "civil time out of range",
        ));
    }
    Ok(())
}

fn assert_kind_match(
    declared_type: &DeclaredType,
    value: &TypedScalar,
) -> Result<(), CanonicalEncodingError> {
    let matched = matches!(
        (declared_type, value),
        (DeclaredType::Null, TypedScalar::Null(_))
            | (DeclaredType::Boolean, TypedScalar::Boolean(_))
            | (
                DeclaredType::SignedInteger { .. },
                TypedScalar::SignedInteger(_)
            )
            | (
                DeclaredType::UnsignedInteger { .. },
                TypedScalar::UnsignedInteger(_)
            )
            | (DeclaredType::Decimal { .. }, TypedScalar::Decimal(_))
            | (DeclaredType::Float32, TypedScalar::Float32(_))
            | (DeclaredType::Float64, TypedScalar::Float64(_))
            | (DeclaredType::String, TypedScalar::String(_))
            | (DeclaredType::Binary, TypedScalar::Binary(_))
            | (DeclaredType::Bit { .. }, TypedScalar::Bit(_))
            | (DeclaredType::Date, TypedScalar::Date(_))
            | (DeclaredType::DateTime, TypedScalar::DateTime(_))
            | (DeclaredType::Timestamp, TypedScalar::Timestamp(_))
            | (DeclaredType::TimeDuration, TypedScalar::TimeDuration(_))
            | (DeclaredType::SourceLiteralAnomaly, TypedScalar::Anomaly(_))
    );
    if matched {
        Ok(())
    } else {
        Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "typed scalar kind does not match declared type",
        ))
    }
}

fn tag_for(declared_type: &DeclaredType) -> u8 {
    match declared_type {
        DeclaredType::Null => TAG_NULL,
        DeclaredType::Boolean => TAG_BOOLEAN,
        DeclaredType::SignedInteger { .. } => TAG_SIGNED_INTEGER,
        DeclaredType::UnsignedInteger { .. } => TAG_UNSIGNED_INTEGER,
        DeclaredType::Decimal { .. } => TAG_DECIMAL,
        DeclaredType::Float32 => TAG_FLOAT32,
        DeclaredType::Float64 => TAG_FLOAT64,
        DeclaredType::String => TAG_STRING,
        DeclaredType::Binary | DeclaredType::Bit { .. } => TAG_BINARY,
        DeclaredType::Date => TAG_DATE,
        DeclaredType::DateTime => TAG_DATETIME,
        DeclaredType::Timestamp => TAG_TIMESTAMP,
        DeclaredType::TimeDuration => TAG_TIME_DURATION,
        DeclaredType::SourceLiteralAnomaly => TAG_ANOMALY,
    }
}

fn encode_payload(
    declared_type: &DeclaredType,
    value: &TypedScalar,
) -> Result<Vec<u8>, CanonicalEncodingError> {
    match (declared_type, value) {
        (DeclaredType::Null, TypedScalar::Null(_)) => Ok(Vec::new()),
        (DeclaredType::Boolean, TypedScalar::Boolean(BooleanScalar { value })) => {
            Ok(vec![u8::from(*value)])
        }
        (DeclaredType::SignedInteger { bits }, TypedScalar::SignedInteger(value)) => {
            let number = require_canonical_int(&value.decimal, true, *bits)?;
            let narrowed = match i64::try_from(number) {
                Ok(value) => value,
                Err(_) => {
                    return Err(CanonicalEncodingError::with_message(
                        CanonicalErrorCode::IntegerOutOfRange,
                        "integer outside declared width",
                    ));
                }
            };
            Ok(narrowed.to_be_bytes().to_vec())
        }
        (DeclaredType::UnsignedInteger { bits }, TypedScalar::UnsignedInteger(value)) => {
            let number = require_canonical_int(&value.decimal, false, *bits)?;
            let narrowed = match u64::try_from(number) {
                Ok(value) => value,
                Err(_) => {
                    return Err(CanonicalEncodingError::with_message(
                        CanonicalErrorCode::IntegerOutOfRange,
                        "integer outside declared width",
                    ));
                }
            };
            Ok(narrowed.to_be_bytes().to_vec())
        }
        (
            DeclaredType::Decimal { precision, scale },
            TypedScalar::Decimal(DecimalScalar { decimal }),
        ) => {
            let canonical = normalize_decimal_literal(decimal, *precision, *scale)?;
            if canonical != *decimal {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::DecimalInvalid,
                    "decimal typed value is not canonical",
                ));
            }
            encode_ascii_payload(&canonical)
        }
        (DeclaredType::Float32, TypedScalar::Float32(Float32Scalar { bits_hex })) => {
            encode_float_bits(bits_hex, 32)
        }
        (DeclaredType::Float64, TypedScalar::Float64(Float64Scalar { bits_hex })) => {
            encode_float_bits(bits_hex, 64)
        }
        (DeclaredType::String, TypedScalar::String(StringScalar { text })) => {
            validate_unicode_string(text)?;
            Ok(text.as_bytes().to_vec())
        }
        (DeclaredType::Binary, TypedScalar::Binary(BinaryScalar { raw_bytes })) => {
            Ok(raw_bytes.clone())
        }
        (DeclaredType::Bit { bit_width }, TypedScalar::Bit(BitScalar { raw_bytes })) => {
            validate_bit_bytes(raw_bytes, *bit_width)?;
            Ok(raw_bytes.clone())
        }
        (DeclaredType::Date, TypedScalar::Date(DateScalar { text })) => {
            encode_ascii_payload(&require_canonical_temporal(text, canonicalize_date)?)
        }
        (DeclaredType::DateTime, TypedScalar::DateTime(DateTimeScalar { text })) => {
            encode_ascii_payload(&require_canonical_temporal(text, canonicalize_datetime)?)
        }
        (DeclaredType::Timestamp, TypedScalar::Timestamp(TimestampScalar { text })) => {
            encode_ascii_payload(&require_canonical_temporal(text, canonicalize_timestamp)?)
        }
        (DeclaredType::TimeDuration, TypedScalar::TimeDuration(TimeDurationScalar { text })) => {
            encode_ascii_payload(&require_canonical_temporal(
                text,
                canonicalize_time_duration,
            )?)
        }
        (DeclaredType::SourceLiteralAnomaly, TypedScalar::Anomaly(anomaly)) => {
            encode_anomaly_envelope(anomaly)
        }
        _ => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "unsupported typed scalar",
        )),
    }
}

fn require_canonical_int(
    decimal: &str,
    signed: bool,
    bits: u8,
) -> Result<i128, CanonicalEncodingError> {
    let normalized = normalize_integer_literal(decimal, signed, bits)?;
    if normalized != decimal {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "integer typed value must be canonical decimal",
        ));
    }
    match normalized.parse::<i128>() {
        Ok(value) => Ok(value),
        Err(_) => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "integer typed value must be canonical decimal",
        )),
    }
}

fn require_canonical_temporal(
    text: &str,
    canon: fn(&str) -> Result<String, CanonicalEncodingError>,
) -> Result<String, CanonicalEncodingError> {
    let canonical = canon(text)?;
    if canonical != text {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TemporalInvalid,
            "temporal typed value is not canonical",
        ));
    }
    Ok(text.to_string())
}

fn encode_ascii_payload(text: &str) -> Result<Vec<u8>, CanonicalEncodingError> {
    if !text.is_ascii() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "payload text must be ASCII",
        ));
    }
    Ok(text.as_bytes().to_vec())
}

fn encode_float_bits(bits_hex: &str, width: u8) -> Result<Vec<u8>, CanonicalEncodingError> {
    let expected_len = if width == 32 { 8 } else { 16 };
    if bits_hex.len() != expected_len || !bits_hex.bytes().all(is_lowercase_hex) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::TypeMismatch,
            "float bits_hex must be lowercase hex of declared width",
        ));
    }
    let bits = match u64::from_str_radix(bits_hex, 16) {
        Ok(value) => value,
        Err(_) => {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::TypeMismatch,
                "float bits_hex must be lowercase hex of declared width",
            ));
        }
    };
    if width == 32 {
        let narrowed = bits as u32;
        let value = f32::from_bits(narrowed);
        if !value.is_finite() {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::FloatNonFinite,
                "float32 bits are non-finite",
            ));
        }
        let mut out_bits = narrowed;
        if out_bits == 0x8000_0000 {
            out_bits = 0;
        }
        Ok(out_bits.to_be_bytes().to_vec())
    } else {
        let value = f64::from_bits(bits);
        if !value.is_finite() {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::FloatNonFinite,
                "float64 bits are non-finite",
            ));
        }
        let mut out_bits = bits;
        if out_bits == 0x8000_0000_0000_0000 {
            out_bits = 0;
        }
        Ok(out_bits.to_be_bytes().to_vec())
    }
}

fn is_lowercase_hex(byte: u8) -> bool {
    byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
}

fn encode_anomaly_envelope(anomaly: &AnomalyScalar) -> Result<Vec<u8>, CanonicalEncodingError> {
    // Unicode stage first over the whole structured envelope (matches Python
    // `_assert_json_compatible_tree` before field semantic constraints).
    validate_unicode_string(&anomaly.raw_base64url)?;
    validate_unicode_string(&anomaly.raw_encoding)?;
    validate_unicode_string(&anomaly.reason)?;

    if let Err(error) = anomaly.declared_type.validate() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::AnomalyInvalid,
            error.to_string(),
        ));
    }
    if anomaly.raw_encoding.is_empty() || anomaly.reason.is_empty() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::AnomalyInvalid,
            "anomaly raw_encoding/reason must be non-empty",
        ));
    }
    decode_base64url_strict(&anomaly.raw_base64url)?;

    let mut object = Map::new();
    object.insert(
        "declared_type".to_string(),
        declared_type_to_json(&anomaly.declared_type)?,
    );
    object.insert(
        "raw_base64url".to_string(),
        Value::String(anomaly.raw_base64url.clone()),
    );
    object.insert(
        "raw_encoding".to_string(),
        Value::String(anomaly.raw_encoding.clone()),
    );
    object.insert("reason".to_string(), Value::String(anomaly.reason.clone()));
    canonicalize_json_value(&Value::Object(object))
}

fn declared_type_to_json(declared_type: &DeclaredType) -> Result<Value, CanonicalEncodingError> {
    let mut object = Map::new();
    object.insert(
        "kind".to_string(),
        Value::String(declared_type.kind_str().to_string()),
    );
    match declared_type {
        DeclaredType::SignedInteger { bits } | DeclaredType::UnsignedInteger { bits } => {
            object.insert("bits".to_string(), Value::Number(Number::from(*bits)));
        }
        DeclaredType::Decimal { precision, scale } => {
            object.insert(
                "precision".to_string(),
                Value::Number(Number::from(*precision)),
            );
            object.insert("scale".to_string(), Value::Number(Number::from(*scale)));
        }
        DeclaredType::Bit { bit_width } => {
            object.insert(
                "bit_width".to_string(),
                Value::Number(Number::from(*bit_width)),
            );
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
    Ok(Value::Object(object))
}

#[cfg(test)]
mod tests {
    use super::{normalize_to_typed_scalar, validate_bit_bytes};
    use crate::errors::CanonicalErrorCode;
    use crate::types::{
        DeclaredType, LogicalLiteral, RawLogicalLiteral, TypedScalar, Utf8LogicalLiteral,
    };

    fn utf8(text: &str) -> LogicalLiteral {
        LogicalLiteral::Utf8(Utf8LogicalLiteral {
            text: text.to_string(),
        })
    }

    fn raw(bytes: &[u8]) -> LogicalLiteral {
        LogicalLiteral::Raw(RawLogicalLiteral {
            raw_bytes: bytes.to_vec(),
        })
    }

    fn expect_code(
        result: Result<TypedScalar, crate::errors::CanonicalEncodingError>,
        code: CanonicalErrorCode,
    ) -> Result<(), String> {
        match result {
            Ok(_) => Err(format!("expected {code}, got Ok")),
            Err(error) if error.code() == code => Ok(()),
            Err(error) => Err(format!("expected {code}, got {}", error.code())),
        }
    }

    #[test]
    fn signed_integer_leading_plus_and_bounds() -> Result<(), String> {
        let declared = DeclaredType::signed_integer(32).map_err(|e| e.to_string())?;
        match normalize_to_typed_scalar(&declared, &utf8("+001")).map_err(|e| e.to_string())? {
            TypedScalar::SignedInteger(value) => assert_eq!(value.decimal, "1"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        let narrow = DeclaredType::signed_integer(8).map_err(|e| e.to_string())?;
        normalize_to_typed_scalar(&narrow, &utf8("127")).map_err(|e| e.to_string())?;
        expect_code(
            normalize_to_typed_scalar(&narrow, &utf8("128")),
            CanonicalErrorCode::IntegerOutOfRange,
        )?;
        Ok(())
    }

    #[test]
    fn unsigned_rejects_negative() -> Result<(), String> {
        let declared = DeclaredType::unsigned_integer(16).map_err(|e| e.to_string())?;
        match normalize_to_typed_scalar(&declared, &utf8("+00042")).map_err(|e| e.to_string())? {
            TypedScalar::UnsignedInteger(value) => assert_eq!(value.decimal, "42"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        expect_code(
            normalize_to_typed_scalar(&declared, &utf8("-1")),
            CanonicalErrorCode::IntegerOutOfRange,
        )?;
        Ok(())
    }

    #[test]
    fn decimal_canonical_and_rejects_plus() -> Result<(), String> {
        let declared = DeclaredType::decimal(10, 2).map_err(|e| e.to_string())?;
        match normalize_to_typed_scalar(&declared, &utf8("-0.00")).map_err(|e| e.to_string())? {
            TypedScalar::Decimal(value) => assert_eq!(value.decimal, "0"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        let trimmed = DeclaredType::decimal(5, 2).map_err(|e| e.to_string())?;
        match normalize_to_typed_scalar(&trimmed, &utf8("001.2300")).map_err(|e| e.to_string())? {
            TypedScalar::Decimal(value) => assert_eq!(value.decimal, "1.23"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        expect_code(
            normalize_to_typed_scalar(&declared, &utf8("+1.0")),
            CanonicalErrorCode::DecimalInvalid,
        )?;
        expect_code(
            normalize_to_typed_scalar(&trimmed, &utf8("1.234")),
            CanonicalErrorCode::DecimalInvalid,
        )?;
        Ok(())
    }

    #[test]
    fn float_negative_zero_and_grammar() -> Result<(), String> {
        let f32_type = DeclaredType::float32();
        match normalize_to_typed_scalar(&f32_type, &utf8("-0.0")).map_err(|e| e.to_string())? {
            TypedScalar::Float32(value) => assert_eq!(value.bits_hex, "00000000"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        expect_code(
            normalize_to_typed_scalar(&f32_type, &utf8("nan")),
            CanonicalErrorCode::TypeMismatch,
        )?;
        expect_code(
            normalize_to_typed_scalar(&f32_type, &utf8("3.5e38")),
            CanonicalErrorCode::FloatNonFinite,
        )?;
        expect_code(
            normalize_to_typed_scalar(&f32_type, &utf8(" 1.5 ")),
            CanonicalErrorCode::TypeMismatch,
        )?;
        expect_code(
            normalize_to_typed_scalar(&f32_type, &utf8("1_0")),
            CanonicalErrorCode::TypeMismatch,
        )?;

        let f64_type = DeclaredType::float64();
        match normalize_to_typed_scalar(&f64_type, &utf8("1.5")).map_err(|e| e.to_string())? {
            TypedScalar::Float64(value) => assert_eq!(value.bits_hex, "3ff8000000000000"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        Ok(())
    }

    #[test]
    fn float32_direct_binary32_rounding_not_via_binary64() -> Result<(), String> {
        // These decimals sit between adjacent binary32 values such that a single
        // round-to-nearest-ties-to-even into binary32 differs from
        // round-to-binary64-then-cast-to-binary32 (double rounding).
        let f32_type = DeclaredType::float32();
        match normalize_to_typed_scalar(&f32_type, &utf8("1.000000059604644775390626"))
            .map_err(|e| e.to_string())?
        {
            TypedScalar::Float32(value) => assert_eq!(value.bits_hex, "3f800001"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        match normalize_to_typed_scalar(&f32_type, &utf8("1.000000178813934326171874"))
            .map_err(|e| e.to_string())?
        {
            TypedScalar::Float32(value) => assert_eq!(value.bits_hex, "3f800001"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        Ok(())
    }

    #[test]
    fn boolean_null_string_binary_bit() -> Result<(), String> {
        let boolean = DeclaredType::boolean();
        match normalize_to_typed_scalar(&boolean, &utf8("false")).map_err(|e| e.to_string())? {
            TypedScalar::Boolean(value) => assert!(!value.value),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        match normalize_to_typed_scalar(&boolean, &raw(&[0x01])).map_err(|e| e.to_string())? {
            TypedScalar::Boolean(value) => assert!(value.value),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        expect_code(
            normalize_to_typed_scalar(&boolean, &utf8("yes")),
            CanonicalErrorCode::TypeMismatch,
        )?;

        match normalize_to_typed_scalar(&DeclaredType::null(), &utf8("null"))
            .map_err(|e| e.to_string())?
        {
            TypedScalar::Null(_) => {}
            other => return Err(format!("unexpected typed value: {other:?}")),
        }

        match normalize_to_typed_scalar(&DeclaredType::string(), &utf8("hi"))
            .map_err(|e| e.to_string())?
        {
            TypedScalar::String(value) => assert_eq!(value.text, "hi"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }

        match normalize_to_typed_scalar(&DeclaredType::binary(), &raw(&[0x00, 0xff]))
            .map_err(|e| e.to_string())?
        {
            TypedScalar::Binary(value) => assert_eq!(value.raw_bytes, vec![0x00, 0xff]),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }

        let bit = DeclaredType::bit(9).map_err(|e| e.to_string())?;
        match normalize_to_typed_scalar(&bit, &raw(&[0x01, 0x00])).map_err(|e| e.to_string())? {
            TypedScalar::Bit(value) => assert_eq!(value.raw_bytes, vec![0x01, 0x00]),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        expect_code(
            normalize_to_typed_scalar(&bit, &raw(&[0x02, 0x00])),
            CanonicalErrorCode::TypeMismatch,
        )?;
        match validate_bit_bytes(&[0x02, 0x00], 9) {
            Err(error) if error.code() == CanonicalErrorCode::TypeMismatch => {}
            other => {
                return Err(format!(
                    "validate_bit_bytes must yield TYPE_MISMATCH, got: {other:?}"
                ));
            }
        }
        Ok(())
    }

    #[test]
    fn temporal_paths() -> Result<(), String> {
        match normalize_to_typed_scalar(&DeclaredType::date(), &utf8("2024-02-29"))
            .map_err(|e| e.to_string())?
        {
            TypedScalar::Date(value) => assert_eq!(value.text, "2024-02-29"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        expect_code(
            normalize_to_typed_scalar(&DeclaredType::date(), &utf8("2023-02-29")),
            CanonicalErrorCode::TemporalInvalid,
        )?;
        expect_code(
            normalize_to_typed_scalar(&DeclaredType::date(), &utf8("２０２４-０１-０２")),
            CanonicalErrorCode::TemporalInvalid,
        )?;

        match normalize_to_typed_scalar(
            &DeclaredType::datetime(),
            &utf8("2024-01-02T03:04:05.120000"),
        )
        .map_err(|e| e.to_string())?
        {
            TypedScalar::DateTime(value) => assert_eq!(value.text, "2024-01-02T03:04:05.12"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        match normalize_to_typed_scalar(
            &DeclaredType::timestamp(),
            &utf8("2024-01-02T03:04:05.000000Z"),
        )
        .map_err(|e| e.to_string())?
        {
            TypedScalar::Timestamp(value) => assert_eq!(value.text, "2024-01-02T03:04:05Z"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }

        let duration = DeclaredType::time_duration();
        match normalize_to_typed_scalar(&duration, &utf8("-00:00:00")).map_err(|e| e.to_string())? {
            TypedScalar::TimeDuration(value) => assert_eq!(value.text, "00:00:00"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        match normalize_to_typed_scalar(&duration, &utf8("838:00:00")).map_err(|e| e.to_string())? {
            TypedScalar::TimeDuration(value) => assert_eq!(value.text, "838:00:00"),
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        expect_code(
            normalize_to_typed_scalar(&duration, &utf8("839:00:00")),
            CanonicalErrorCode::TimeOutOfRange,
        )?;
        expect_code(
            normalize_to_typed_scalar(&duration, &utf8("099:00:00")),
            CanonicalErrorCode::TemporalInvalid,
        )?;
        Ok(())
    }

    #[test]
    fn anomaly_and_fullwidth_integer_rejected() -> Result<(), String> {
        expect_code(
            normalize_to_typed_scalar(&DeclaredType::source_literal_anomaly(), &utf8("x")),
            CanonicalErrorCode::TypeMismatch,
        )?;
        let declared = DeclaredType::signed_integer(32).map_err(|e| e.to_string())?;
        expect_code(
            normalize_to_typed_scalar(&declared, &utf8("１２")),
            CanonicalErrorCode::TypeMismatch,
        )?;
        Ok(())
    }

    #[test]
    fn declared_type_construction_guards() -> Result<(), String> {
        assert!(DeclaredType::decimal(10, 11).is_err());
        assert!(DeclaredType::signed_integer(7).is_err());
        assert!(DeclaredType::bit(0).is_err());
        assert!(DeclaredType::SignedInteger { bits: 7 }.validate().is_err());
        assert!(DeclaredType::decimal(65, 30).is_ok());
        assert_eq!(DeclaredType::null().kind_str(), "null");
        let signed24 = DeclaredType::signed_integer(24).map_err(|e| e.to_string())?;
        assert_eq!(signed24.kind_str(), "signed-integer");
        Ok(())
    }

    #[test]
    fn normalize_logical_literal_emits_payload_and_frame() -> Result<(), String> {
        use super::normalize_logical_literal;
        use crate::types::SignedIntegerScalar;

        let declared = DeclaredType::signed_integer(32).map_err(|e| e.to_string())?;
        let result =
            normalize_logical_literal(&declared, &utf8("+001")).map_err(|e| e.to_string())?;
        match result.typed_value {
            TypedScalar::SignedInteger(SignedIntegerScalar { decimal }) => {
                assert_eq!(decimal, "1");
            }
            other => return Err(format!("unexpected typed value: {other:?}")),
        }
        assert_eq!(result.payload, [0, 0, 0, 0, 0, 0, 0, 1]);
        assert_eq!(result.scalar_frame, [0x10, 0x08, 0, 0, 0, 0, 0, 0, 0, 1]);
        Ok(())
    }

    #[test]
    fn encode_null_boolean_string_and_kind_mismatch() -> Result<(), String> {
        use super::encode_typed_scalar;
        use crate::types::{BinaryScalar, BooleanScalar, NullScalar, StringScalar};

        let null = encode_typed_scalar(&DeclaredType::null(), &TypedScalar::Null(NullScalar))
            .map_err(|e| e.to_string())?;
        assert_eq!(null.payload, Vec::<u8>::new());
        assert_eq!(null.scalar_frame, vec![0x00, 0x00]);

        let boolean = encode_typed_scalar(
            &DeclaredType::boolean(),
            &TypedScalar::Boolean(BooleanScalar { value: true }),
        )
        .map_err(|e| e.to_string())?;
        assert_eq!(boolean.payload, vec![0x01]);
        assert_eq!(boolean.scalar_frame, vec![0x01, 0x01, 0x01]);

        let text = encode_typed_scalar(
            &DeclaredType::string(),
            &TypedScalar::String(StringScalar {
                text: "hi".to_string(),
            }),
        )
        .map_err(|e| e.to_string())?;
        assert_eq!(text.payload, b"hi");
        assert_eq!(text.scalar_frame, b"\x20\x02hi");

        match encode_typed_scalar(
            &DeclaredType::boolean(),
            &TypedScalar::Binary(BinaryScalar {
                raw_bytes: vec![0x00],
            }),
        ) {
            Err(error) if error.code() == CanonicalErrorCode::TypeMismatch => {}
            other => {
                return Err(format!(
                    "kind mismatch must be TYPE_MISMATCH, got {other:?}"
                ));
            }
        }
        Ok(())
    }

    #[test]
    fn encode_bit_and_anomaly_envelope() -> Result<(), String> {
        use super::encode_typed_scalar;
        use crate::types::{AnomalyScalar, BitScalar};

        let bit = DeclaredType::bit(9).map_err(|e| e.to_string())?;
        let ok = encode_typed_scalar(
            &bit,
            &TypedScalar::Bit(BitScalar {
                raw_bytes: vec![0x01, 0x00],
            }),
        )
        .map_err(|e| e.to_string())?;
        assert_eq!(ok.payload, vec![0x01, 0x00]);
        assert_eq!(ok.scalar_frame[0], 0x21);

        match encode_typed_scalar(
            &bit,
            &TypedScalar::Bit(BitScalar {
                raw_bytes: vec![0x02, 0x00],
            }),
        ) {
            Err(error) if error.code() == CanonicalErrorCode::TypeMismatch => {}
            other => {
                return Err(format!(
                    "BIT high bits must be TYPE_MISMATCH, got {other:?}"
                ));
            }
        }

        let anomaly_type = DeclaredType::source_literal_anomaly();
        let encoded = encode_typed_scalar(
            &anomaly_type,
            &TypedScalar::Anomaly(AnomalyScalar {
                declared_type: DeclaredType::date(),
                raw_base64url: "YmFk".to_string(),
                raw_encoding: "utf8".to_string(),
                reason: "owner-reason".to_string(),
            }),
        )
        .map_err(|e| e.to_string())?;
        assert_eq!(encoded.scalar_frame[0], 0x7f);
        assert!(encoded.payload.starts_with(b"{"));
        assert_eq!(
            encoded.payload,
            br#"{"declared_type":{"kind":"date"},"raw_base64url":"YmFk","raw_encoding":"utf8","reason":"owner-reason"}"#
        );

        match encode_typed_scalar(
            &anomaly_type,
            &TypedScalar::Anomaly(AnomalyScalar {
                declared_type: DeclaredType::date(),
                raw_base64url: "A".to_string(),
                raw_encoding: "utf8".to_string(),
                reason: "x".to_string(),
            }),
        ) {
            Err(error) if error.code() == CanonicalErrorCode::AnomalyInvalid => Ok(()),
            other => Err(format!(
                "invalid base64url must be ANOMALY_INVALID, got {other:?}"
            )),
        }
    }

    #[test]
    fn anomaly_unicode_stage_precedes_field_semantics() -> Result<(), String> {
        use super::encode_typed_scalar;
        use crate::types::AnomalyScalar;

        let anomaly_type = DeclaredType::source_literal_anomaly();
        let noncharacter = "\u{FFFF}".to_string();

        // raw_base64url noncharacter must not be shadowed by base64 alphabet failure.
        match encode_typed_scalar(
            &anomaly_type,
            &TypedScalar::Anomaly(AnomalyScalar {
                declared_type: DeclaredType::date(),
                raw_base64url: noncharacter.clone(),
                raw_encoding: "utf8".to_string(),
                reason: "owner-reason".to_string(),
            }),
        ) {
            Err(error) if error.code() == CanonicalErrorCode::UnicodeNoncharacter => {}
            other => {
                return Err(format!(
                    "raw_base64url noncharacter must be UNICODE_NONCHARACTER, got {other:?}"
                ));
            }
        }

        // raw_encoding noncharacter must not be shadowed by empty reason.
        match encode_typed_scalar(
            &anomaly_type,
            &TypedScalar::Anomaly(AnomalyScalar {
                declared_type: DeclaredType::date(),
                raw_base64url: "YmFk".to_string(),
                raw_encoding: noncharacter.clone(),
                reason: String::new(),
            }),
        ) {
            Err(error) if error.code() == CanonicalErrorCode::UnicodeNoncharacter => {}
            other => {
                return Err(format!(
                    "raw_encoding noncharacter must beat empty reason, got {other:?}"
                ));
            }
        }

        // raw_encoding noncharacter must not be shadowed by invalid declared_type.
        match encode_typed_scalar(
            &anomaly_type,
            &TypedScalar::Anomaly(AnomalyScalar {
                declared_type: DeclaredType::SignedInteger { bits: 7 },
                raw_base64url: "YmFk".to_string(),
                raw_encoding: noncharacter,
                reason: "owner-reason".to_string(),
            }),
        ) {
            Err(error) if error.code() == CanonicalErrorCode::UnicodeNoncharacter => Ok(()),
            other => Err(format!(
                "raw_encoding noncharacter must beat invalid declared_type, got {other:?}"
            )),
        }
    }

    #[test]
    fn encode_rejects_non_canonical_typed_decimal_and_temporal() -> Result<(), String> {
        use super::encode_typed_scalar;
        use crate::types::{DateScalar, DecimalScalar};

        let decimal = DeclaredType::decimal(10, 2).map_err(|e| e.to_string())?;
        match encode_typed_scalar(
            &decimal,
            &TypedScalar::Decimal(DecimalScalar {
                decimal: "01.00".to_string(),
            }),
        ) {
            Err(error) if error.code() == CanonicalErrorCode::DecimalInvalid => {}
            other => {
                return Err(format!(
                    "non-canonical decimal must be DECIMAL_INVALID, got {other:?}"
                ));
            }
        }

        match encode_typed_scalar(
            &DeclaredType::date(),
            &TypedScalar::Date(DateScalar {
                text: "2024-1-2".to_string(),
            }),
        ) {
            Err(error) if error.code() == CanonicalErrorCode::TemporalInvalid => Ok(()),
            other => Err(format!(
                "non-canonical date must be TEMPORAL_INVALID, got {other:?}"
            )),
        }
    }
}
