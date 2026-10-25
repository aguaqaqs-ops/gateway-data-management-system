//! Literal to typed value conversion (`_sql_values.literal_to_cell`).
//!
//! INTEGER, FLOAT, DOUBLE and string-like columns use fast paths that follow
//! the Shared Kernel normalizer exactly (checked against it in tests). The
//! remaining types call `gateway_shared_kernel::normalize_logical_literal`.

use std::borrow::Cow;

use gateway_shared_kernel::{
    DeclaredType, LogicalLiteral, RawLogicalLiteral, TypedScalar, Utf8LogicalLiteral,
    normalize_logical_literal,
};

use super::columns::ColumnBuilder;
use super::cursor::python_strip;
use super::errors::{Fault, ParserDiagnosticCode as Code};
use super::json_check::python_json_loads_accepts;
use super::literal::Lit;
use super::model::{ColumnPlan, ValueKind};

const LEADING_ZERO_BUDGET: usize = 16;

/// Conversion failures: `Table` invalidates the table, `Document` stops the
/// document (the `max_field_bytes` budget).
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ConvError {
    Table(Fault),
    Document(Fault),
}

fn illegal(offset: usize, message: impl Into<Cow<'static, str>>) -> ConvError {
    ConvError::Table(Fault::illegal(offset, message))
}

pub(crate) fn convert_value(
    lit: &Lit<'_>,
    plan: &ColumnPlan,
    out: &mut ColumnBuilder,
    max_field_bytes: usize,
    offset: usize,
) -> Result<(), ConvError> {
    if matches!(lit, Lit::Null) {
        if !plan.nullable {
            return Err(illegal(offset, "NULL is not allowed for a NOT NULL column"));
        }
        out.push_null();
        return Ok(());
    }
    let internal = |fault: Fault| ConvError::Table(fault);
    match &plan.kind {
        ValueKind::Set => {
            let members = set_value(lit, plan, offset)?;
            out.push_bytes(members.as_bytes()).map_err(internal)
        }
        ValueKind::Unready => Err(illegal(offset, "value supplied for a non-ready column")),
        ValueKind::Enum => {
            let text = require_text(lit, offset)?;
            if !plan.label_set.contains(text.as_ref()) {
                return Err(illegal(offset, "ENUM value is not a declared label"));
            }
            check_unicode(&text, offset)?;
            out.push_bytes(text.as_bytes()).map_err(internal)
        }
        ValueKind::Json => {
            let text = require_text(lit, offset)?;
            if !python_json_loads_accepts(&text) {
                return Err(illegal(offset, "JSON value is not well-formed"));
            }
            check_unicode(&text, offset)?;
            out.push_bytes(text.as_bytes()).map_err(internal)
        }
        ValueKind::Binary => {
            let raw = require_bytes(lit);
            check_field_bytes(raw.len(), max_field_bytes, offset)?;
            out.push_bytes(&raw).map_err(internal)
        }
        ValueKind::Bit { width } => {
            let raw = bit_bytes(lit, *width, offset)?;
            check_field_bytes(raw.len(), max_field_bytes, offset)?;
            let declared = declared_or_internal(plan)?;
            let normalized = normalize_logical_literal(
                declared,
                &LogicalLiteral::Raw(RawLogicalLiteral { raw_bytes: raw }),
            )
            .map_err(|e| illegal(offset, e.message().to_string()))?;
            match normalized.typed_value {
                TypedScalar::Bit(bit) => out.push_bytes(&bit.raw_bytes).map_err(internal),
                _ => Err(ConvError::Table(unexpected_scalar())),
            }
        }
        kind => {
            let text = logical_text(lit, kind, offset)?;
            check_field_bytes(text.len(), max_field_bytes, offset)?;
            match kind {
                ValueKind::SignedInt { bits } => {
                    let value = normalize_integer(text.as_bytes(), true, *bits)
                        .map_err(|m| illegal(offset, m))?;
                    let value = i64::try_from(value)
                        .map_err(|_| illegal(offset, "integer outside declared width"))?;
                    out.push_i64(value).map_err(internal)
                }
                ValueKind::UnsignedInt { bits } => {
                    let value = normalize_integer(text.as_bytes(), false, *bits)
                        .map_err(|m| illegal(offset, m))?;
                    let value = u64::try_from(value)
                        .map_err(|_| illegal(offset, "integer outside declared width"))?;
                    out.push_u64(value).map_err(internal)
                }
                ValueKind::Float32 => {
                    let value = normalize_float32(&text).map_err(|m| illegal(offset, m))?;
                    out.push_f32(value).map_err(internal)
                }
                ValueKind::Float64 => {
                    let value = normalize_float64(&text).map_err(|m| illegal(offset, m))?;
                    out.push_f64(value).map_err(internal)
                }
                ValueKind::Str => {
                    check_unicode(&text, offset)?;
                    out.push_bytes(text.as_bytes()).map_err(internal)
                }
                _ => {
                    let declared = declared_or_internal(plan)?;
                    let typed = normalize_logical_literal(
                        declared,
                        &LogicalLiteral::Utf8(Utf8LogicalLiteral {
                            text: text.into_owned(),
                        }),
                    )
                    .map_err(|e| illegal(offset, e.message().to_string()))?
                    .typed_value;
                    push_typed(out, &typed).map_err(internal)
                }
            }
        }
    }
}

fn declared_or_internal(plan: &ColumnPlan) -> Result<&DeclaredType, ConvError> {
    plan.declared.as_ref().ok_or_else(|| {
        ConvError::Table(Fault::new(
            Code::ParserInternalError,
            0,
            "missing declared type",
        ))
    })
}

fn unexpected_scalar() -> Fault {
    Fault::new(Code::ParserInternalError, 0, "unexpected typed scalar kind")
}

fn push_typed(out: &mut ColumnBuilder, typed: &TypedScalar) -> Result<(), Fault> {
    match typed {
        TypedScalar::Boolean(value) => out.push_bool(value.value),
        TypedScalar::Decimal(value) => out.push_bytes(value.decimal.as_bytes()),
        TypedScalar::Date(value) => out.push_bytes(value.text.as_bytes()),
        TypedScalar::DateTime(value) => out.push_bytes(value.text.as_bytes()),
        TypedScalar::Timestamp(value) => out.push_bytes(value.text.as_bytes()),
        TypedScalar::TimeDuration(value) => out.push_bytes(value.text.as_bytes()),
        _ => Err(unexpected_scalar()),
    }
}

fn check_field_bytes(
    length: usize,
    max_field_bytes: usize,
    offset: usize,
) -> Result<(), ConvError> {
    if length > max_field_bytes {
        return Err(ConvError::Document(Fault::resource(
            "max_field_bytes",
            offset,
        )));
    }
    Ok(())
}

/// Shared Kernel string validation: no Unicode noncharacters (lone
/// surrogates cannot occur in Rust strings).
pub(crate) fn has_noncharacter(text: &str) -> bool {
    if text.is_ascii() {
        return false;
    }
    text.chars().any(|ch| {
        let cp = u32::from(ch);
        (0xFDD0..=0xFDEF).contains(&cp) || (cp & 0xFFFE) == 0xFFFE
    })
}

fn check_unicode(text: &str, offset: usize) -> Result<(), ConvError> {
    if has_noncharacter(text) {
        return Err(illegal(offset, "string contains Unicode noncharacter"));
    }
    Ok(())
}

fn require_text<'b>(lit: &'b Lit<'_>, offset: usize) -> Result<Cow<'b, str>, ConvError> {
    let bytes: &[u8] = match lit {
        Lit::Keyword(text) => return Ok(Cow::Borrowed(text)),
        Lit::Number(text) => text,
        Lit::Str(raw) => raw,
        Lit::Bits { text, .. } => text,
        Lit::Hex(raw) => {
            return std::str::from_utf8(raw)
                .map(Cow::Borrowed)
                .map_err(|_| illegal(offset, "binary literal is not UTF-8 text"));
        }
        Lit::Null => return Err(illegal(offset, "expected a text literal")),
    };
    std::str::from_utf8(bytes)
        .map(Cow::Borrowed)
        .map_err(|_| illegal(offset, "string literal is not strict UTF-8"))
}

fn require_bytes<'b>(lit: &'b Lit<'_>) -> Cow<'b, [u8]> {
    match lit {
        Lit::Str(raw) => Cow::Borrowed(raw),
        Lit::Hex(raw) => Cow::Borrowed(raw),
        Lit::Bits { raw, .. } => Cow::Borrowed(raw),
        Lit::Keyword(text) => Cow::Borrowed(text.as_bytes()),
        Lit::Number(text) => Cow::Borrowed(text),
        Lit::Null => Cow::Borrowed(&[]),
    }
}

fn logical_text<'b>(
    lit: &'b Lit<'_>,
    kind: &ValueKind,
    offset: usize,
) -> Result<Cow<'b, str>, ConvError> {
    let text = require_text(lit, offset)?;
    match kind {
        ValueKind::DateTime => Ok(Cow::Owned(sql_datetime_to_canonical(&text, false))),
        ValueKind::Timestamp => Ok(Cow::Owned(sql_datetime_to_canonical(&text, true))),
        _ => Ok(text),
    }
}

/// `YYYY-MM-DD HH:MM:SS[.f]` to the Shared Kernel spelling (`T`, and `Z`
/// for TIMESTAMP).
fn sql_datetime_to_canonical(text: &str, timestamp: bool) -> String {
    let mut converted = python_strip(text).to_string();
    if converted.contains(' ') && !converted.contains('T') {
        converted = converted.replacen(' ', "T", 1);
    }
    if timestamp && !converted.ends_with('Z') {
        converted.push('Z');
    }
    converted
}

fn set_value(lit: &Lit<'_>, plan: &ColumnPlan, offset: usize) -> Result<String, ConvError> {
    let text = require_text(lit, offset)?;
    if text.is_empty() {
        return Ok(String::new());
    }
    let mut seen: Vec<&str> = Vec::new();
    for member in text.split(',') {
        if !plan.label_set.contains(member) {
            return Err(illegal(
                offset,
                "SET value contains an undeclared or empty member",
            ));
        }
        if seen.contains(&member) {
            return Err(illegal(offset, "SET value contains duplicate members"));
        }
        seen.push(member);
    }
    let ordered: Vec<&str> = plan
        .labels
        .iter()
        .map(String::as_str)
        .filter(|label| seen.contains(label))
        .collect();
    Ok(ordered.join(","))
}

/// `_bit_bytes`: raw literals keep their bytes (re-padded to the width);
/// numbers and keywords are read as binary digits when they only contain
/// `0`/`1`, otherwise as decimal.
fn bit_bytes(lit: &Lit<'_>, width: u8, offset: usize) -> Result<Vec<u8>, ConvError> {
    let expected = usize::from(width).div_ceil(8);
    let raw = match lit {
        Lit::Str(raw) => Some(&raw[..]),
        Lit::Hex(raw) => Some(raw.as_slice()),
        Lit::Bits { raw, .. } => Some(raw.as_slice()),
        _ => None,
    };
    if let Some(raw) = raw {
        if raw.len() == expected {
            return Ok(raw.to_vec());
        }
        let significant: &[u8] = match raw.iter().position(|b| *b != 0) {
            Some(first) => &raw[first..],
            None => &[],
        };
        // The reference raises an uncaught OverflowError when it does not fit.
        if significant.len() > expected {
            return Err(illegal(
                offset,
                "BIT literal does not fit the declared width",
            ));
        }
        let mut out = vec![0u8; expected - significant.len()];
        out.extend_from_slice(significant);
        return Ok(out);
    }
    let text = require_text(lit, offset)?;
    let value: u128 = if !text.is_empty() && text.bytes().all(|b| b == b'0' || b == b'1') {
        let digits = text.trim_start_matches('0');
        if digits.len() > 128 {
            return Err(illegal(
                offset,
                "BIT literal does not fit the declared width",
            ));
        }
        u128::from_str_radix(if digits.is_empty() { "0" } else { digits }, 2)
            .map_err(|_| illegal(offset, "BIT literal is not convertible"))?
    } else {
        parse_python_int10(&text, offset)?
    };
    let bytes = value.to_be_bytes();
    let significant = bytes
        .iter()
        .position(|b| *b != 0)
        .map_or(&bytes[bytes.len()..], |first| &bytes[first..]);
    if significant.len() > expected {
        return Err(illegal(
            offset,
            "BIT literal does not fit the declared width",
        ));
    }
    let mut out = vec![0u8; expected - significant.len()];
    out.extend_from_slice(significant);
    Ok(out)
}

/// `int(text, 10)` for the texts the lexer can produce (sign plus digits);
/// fractions and exponents are not convertible. Negative values are rejected
/// (the reference raises an uncaught OverflowError for them).
fn parse_python_int10(text: &str, offset: usize) -> Result<u128, ConvError> {
    let (negative, body) = match text.as_bytes().first() {
        Some(b'+') => (false, &text[1..]),
        Some(b'-') => (true, &text[1..]),
        _ => (false, text),
    };
    if body.is_empty() || !body.bytes().all(|b| b.is_ascii_digit()) {
        return Err(illegal(offset, "BIT literal is not convertible"));
    }
    let digits = body.trim_start_matches('0');
    if digits.is_empty() {
        return Ok(0);
    }
    if negative {
        return Err(illegal(offset, "BIT literal is negative"));
    }
    if digits.len() > 39 {
        return Err(illegal(
            offset,
            "BIT literal does not fit the declared width",
        ));
    }
    digits
        .parse::<u128>()
        .map_err(|_| illegal(offset, "BIT literal does not fit the declared width"))
}

fn max_integer_digits(bits: u8) -> usize {
    // ceil(bits * log10(2)) for the allowed widths, plus the leading-zero budget.
    let base = match bits {
        8 => 3,
        16 => 5,
        24 => 8,
        32 => 10,
        _ => 20,
    };
    base + LEADING_ZERO_BUDGET
}

/// Shared Kernel integer normalization; returns the numeric value.
pub(crate) fn normalize_integer(text: &[u8], signed: bool, bits: u8) -> Result<i128, &'static str> {
    let (sign, body) = match text.first() {
        Some(b'+') => (1i128, &text[1..]),
        Some(b'-') => (-1i128, &text[1..]),
        _ => (1i128, text),
    };
    if body.is_empty() || !body.iter().all(u8::is_ascii_digit) {
        return Err("integer literal must be optional ASCII sign plus digits");
    }
    if sign < 0 && !signed {
        return Err("unsigned integer rejects negative literal");
    }
    if body.len() > max_integer_digits(bits) {
        return Err("integer literal exceeds lexical length budget");
    }
    let mut magnitude: i128 = 0;
    for digit in body {
        magnitude = magnitude * 10 + i128::from(digit - b'0');
    }
    let value = sign * magnitude;
    if value == 0 {
        return Ok(0);
    }
    let (low, high) = if signed {
        (-(1i128 << (bits - 1)), (1i128 << (bits - 1)) - 1)
    } else {
        (0, (1i128 << bits) - 1)
    };
    if value < low || value > high {
        return Err("integer outside declared width");
    }
    Ok(value)
}

/// `[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?`
fn is_float_literal_form(bytes: &[u8]) -> bool {
    let mut index = 0;
    if matches!(bytes.first(), Some(b'+' | b'-')) {
        index = 1;
    }
    let int_start = index;
    while index < bytes.len() && bytes[index].is_ascii_digit() {
        index += 1;
    }
    let int_digits = index - int_start;
    if index < bytes.len() && bytes[index] == b'.' {
        index += 1;
        let frac_start = index;
        while index < bytes.len() && bytes[index].is_ascii_digit() {
            index += 1;
        }
        if int_digits == 0 && index == frac_start {
            return false;
        }
    } else if int_digits == 0 {
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

fn float_precheck(text: &str, max_digits: usize) -> Result<(), &'static str> {
    if !is_float_literal_form(text.as_bytes()) {
        return Err("float literal must match ASCII float grammar");
    }
    if text.bytes().filter(u8::is_ascii_digit).count() > max_digits + LEADING_ZERO_BUDGET {
        return Err("float literal exceeds lexical length budget");
    }
    Ok(())
}

/// Shared Kernel float32: one round-to-nearest into binary32; `-0` to `+0`.
pub(crate) fn normalize_float32(text: &str) -> Result<f32, &'static str> {
    float_precheck(text, 38)?;
    let value: f32 = text.parse().map_err(|_| "float literal is not numeric")?;
    if !value.is_finite() {
        return Err("float must be finite");
    }
    Ok(if value == 0.0 { 0.0 } else { value })
}

pub(crate) fn normalize_float64(text: &str) -> Result<f64, &'static str> {
    float_precheck(text, 309)?;
    let value: f64 = text.parse().map_err(|_| "float literal is not numeric")?;
    if !value.is_finite() {
        return Err("float must be finite");
    }
    Ok(if value == 0.0 { 0.0 } else { value })
}

#[cfg(test)]
mod tests {
    use super::*;
    use gateway_shared_kernel::TypedScalar;
    use proptest::prelude::*;

    fn kernel(declared: &DeclaredType, text: &str) -> Option<TypedScalar> {
        normalize_logical_literal(
            declared,
            &LogicalLiteral::Utf8(Utf8LogicalLiteral {
                text: text.to_string(),
            }),
        )
        .ok()
        .map(|n| n.typed_value)
    }

    fn check_integer(text: &str, signed: bool, bits: u8) {
        let declared = if signed {
            DeclaredType::signed_integer(bits)
        } else {
            DeclaredType::unsigned_integer(bits)
        };
        let Ok(declared) = declared else {
            return;
        };
        let fast = normalize_integer(text.as_bytes(), signed, bits)
            .ok()
            .map(|v| v.to_string());
        let slow = kernel(&declared, text).and_then(|typed| match typed {
            TypedScalar::SignedInteger(v) => Some(v.decimal),
            TypedScalar::UnsignedInteger(v) => Some(v.decimal),
            _ => None,
        });
        assert_eq!(fast, slow, "integer {text:?} signed={signed} bits={bits}");
    }

    fn check_float(text: &str) {
        let fast32 = normalize_float32(text)
            .ok()
            .map(|v| format!("{:08x}", v.to_bits()));
        let slow32 = kernel(&DeclaredType::float32(), text).and_then(|t| match t {
            TypedScalar::Float32(v) => Some(v.bits_hex),
            _ => None,
        });
        assert_eq!(fast32, slow32, "float32 {text:?}");
        let fast64 = normalize_float64(text)
            .ok()
            .map(|v| format!("{:016x}", v.to_bits()));
        let slow64 = kernel(&DeclaredType::float64(), text).and_then(|t| match t {
            TypedScalar::Float64(v) => Some(v.bits_hex),
            _ => None,
        });
        assert_eq!(fast64, slow64, "float64 {text:?}");
    }

    #[test]
    fn fast_paths_match_kernel_on_edge_cases() {
        for text in [
            "0",
            "-0",
            "+0",
            "00",
            "127",
            "128",
            "-128",
            "-129",
            "255",
            "256",
            "+5",
            "-",
            "",
            "1.0",
            "1e3",
            "9223372036854775807",
            "9223372036854775808",
            "-9223372036854775808",
            "18446744073709551615",
            "18446744073709551616",
            "000000000000000000001",
            "0000000000000000000000000000000000001",
            "１",
        ] {
            for bits in [8u8, 16, 24, 32, 64] {
                check_integer(text, true, bits);
                check_integer(text, false, bits);
            }
        }
        for text in [
            "0",
            "-0",
            "-0.0",
            "0.0e5",
            "1.",
            ".5",
            "-.5",
            "+1",
            "1e38",
            "3.4028235e38",
            "3.5e38",
            "1e-46",
            "1e-40",
            "1e308",
            "1e309",
            "2.5e-324",
            "1.7976931348623157e308",
            "1e",
            ".",
            "1.5E+3",
            "nan",
            "inf",
            "0x1p3",
            "1_0",
        ] {
            check_float(text);
        }
    }

    proptest! {
        #![proptest_config(ProptestConfig { cases: 2048, failure_persistence: None, rng_seed: proptest::test_runner::RngSeed::Fixed(0x5636), ..ProptestConfig::default() })]

        #[test]
        fn integer_fast_path_matches_kernel(text in "[+-]?[0-9]{0,40}", signed in any::<bool>(), bits_index in 0usize..5) {
            let bits = [8u8, 16, 24, 32, 64][bits_index];
            check_integer(&text, signed, bits);
        }

        #[test]
        fn float_fast_path_matches_kernel(text in "[+-]?[0-9]{0,20}(\\.[0-9]{0,20})?([eE][+-]?[0-9]{1,3})?") {
            check_float(&text);
        }
    }

    #[test]
    fn datetime_spelling_follows_reference() {
        assert_eq!(
            sql_datetime_to_canonical("2024-01-02 03:04:05", false),
            "2024-01-02T03:04:05"
        );
        assert_eq!(
            sql_datetime_to_canonical(" 2024-01-02 03:04:05.10\u{1f}", true),
            "2024-01-02T03:04:05.10Z"
        );
        assert_eq!(
            sql_datetime_to_canonical("2024-01-02T03:04:05Z", true),
            "2024-01-02T03:04:05Z"
        );
    }
}
