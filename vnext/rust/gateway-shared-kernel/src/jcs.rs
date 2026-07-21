//! Strict RFC 8785 JCS canonicalization with I-JSON and Unicode gates.
//!
//! Pipeline (typed stages; never classify by third-party error message text):
//! 1. strict UTF-8 decode
//! 2. grammar-aware first-party parse over the **entire** document:
//!    - only syntax failures abort the scan (`JCS_SYNTAX_INVALID`)
//!    - semantic issues are typed events (committed duplicate, Unicode order,
//!      NaN/OOR literals, float overflow); object duplicate commits only on
//!      successful close and only if not interrupted by mid-object NaN/OOR
//! 3. recursive Serde visitor constructs `Value` and detects duplicate members
//!    after complete key/value pairs (runs whenever the document is
//!    syntactically valid, including duplicate-only documents)
//! 4. stable-code classification after syntax success:
//!    committed/Serde duplicate → Unicode (traversal order) →
//!    first NaN/OOR literal event → float overflow → I-JSON tree → serialize
//! 5. RFC 8785 serialization via `serde_json_canonicalizer`

use std::cell::Cell;
use std::collections::BTreeSet;
use std::fmt;

use serde::de::{self, DeserializeSeed, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};

use crate::errors::{CanonicalEncodingError, CanonicalErrorCode};
use crate::unicode::{decode_utf8, is_unicode_noncharacter, validate_unicode_string};

const IJSON_MIN_SAFE_INTEGER: i64 = -(1 << 53) + 1;
const IJSON_MAX_SAFE_INTEGER: i64 = (1 << 53) - 1;
const IJSON_MAX_INTEGER_DIGITS: usize = 16;
/// Match `serde_json` default recursion budget (`remaining_depth = 128`).
const MAX_NESTING_DEPTH: usize = 128;

/// Canonicalize a complete JSON document from raw UTF-8 bytes.
pub fn canonicalize_jcs(json_utf8: &[u8]) -> Result<Vec<u8>, CanonicalEncodingError> {
    let text = decode_utf8(json_utf8)?;
    // Syntax must cover the whole document before any semantic stable code.
    let report = parse_document(text)?;
    let (value, findings) = match parse_with_serde_visitor(text) {
        Ok((value, serde_duplicate)) => {
            let mut findings = report.findings;
            // Serde visitor must observe duplicate documents (formal plan).
            // Only record when no earlier commit/literal event exists (so mid-object
            // OOR/NaN and earlier OOR still win over a later Serde duplicate).
            if serde_duplicate {
                findings.note_commit_or_literal(CanonicalErrorCode::JcsDuplicateMember);
            }
            (value, findings)
        }
        Err(_) => {
            // Serde rejects lone-surrogate / NaN / overflow lexemes; keep
            // first-party value + events for classification.
            (report.value, report.findings)
        }
    };
    apply_validation_stages(value, findings)
}

/// Canonicalize an already-parsed JSON-compatible value (crate-internal helper).
pub(crate) fn canonicalize_json_value(value: &Value) -> Result<Vec<u8>, CanonicalEncodingError> {
    validate_unicode_tree(value)?;
    validate_ijson_numbers(value)?;
    serialize_jcs(value)
}

fn apply_validation_stages(
    value: Value,
    findings: Findings,
) -> Result<Vec<u8>, CanonicalEncodingError> {
    // After whole-document syntax success, apply parse-order commit/literal
    // events first, then Unicode, then deferred float overflow.
    if let Some(code) = findings.first_commit_or_literal {
        return match code {
            CanonicalErrorCode::JcsDuplicateMember => Err(duplicate_member()),
            CanonicalErrorCode::JcsNumberOutOfRange => Err(number_out_of_range()),
            CanonicalErrorCode::JcsNonFiniteNumber => Err(non_finite()),
            other => Err(CanonicalEncodingError::with_message(
                other,
                "canonical validation failed",
            )),
        };
    }
    if let Some(code) = findings.first_unicode_error {
        return Err(unicode_stage_error(code));
    }
    validate_unicode_tree(&value)?;
    if findings.non_finite_float {
        return Err(non_finite());
    }
    validate_ijson_numbers(&value)?;
    serialize_jcs(&value)
}

fn unicode_stage_error(code: CanonicalErrorCode) -> CanonicalEncodingError {
    match code {
        CanonicalErrorCode::UnicodeNoncharacter => CanonicalEncodingError::with_message(
            CanonicalErrorCode::UnicodeNoncharacter,
            "string contains Unicode noncharacter",
        ),
        _ => CanonicalEncodingError::with_message(
            CanonicalErrorCode::InvalidUnicode,
            "string contains lone UTF-16 surrogate",
        ),
    }
}

fn serialize_jcs(value: &Value) -> Result<Vec<u8>, CanonicalEncodingError> {
    match serde_json_canonicalizer::to_vec(value) {
        Ok(bytes) => Ok(bytes),
        Err(_) => Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::InvalidUnicode,
            "JCS serialization rejected input",
        )),
    }
}

fn duplicate_member() -> CanonicalEncodingError {
    CanonicalEncodingError::with_message(
        CanonicalErrorCode::JcsDuplicateMember,
        "duplicate JSON member name",
    )
}

fn syntax_invalid() -> CanonicalEncodingError {
    CanonicalEncodingError::with_message(
        CanonicalErrorCode::JcsSyntaxInvalid,
        "input is not a valid JSON document",
    )
}

fn non_finite() -> CanonicalEncodingError {
    CanonicalEncodingError::with_message(
        CanonicalErrorCode::JcsNonFiniteNumber,
        "JSON number must be finite",
    )
}

fn number_out_of_range() -> CanonicalEncodingError {
    CanonicalEncodingError::with_message(
        CanonicalErrorCode::JcsNumberOutOfRange,
        "JSON integer outside I-JSON safe range",
    )
}

#[derive(Clone, Copy, Default)]
struct Findings {
    /// First committed-duplicate or NaN/OOR literal in parse order.
    first_commit_or_literal: Option<CanonicalErrorCode>,
    /// First Unicode-stage failure in document/string traversal order.
    first_unicode_error: Option<CanonicalErrorCode>,
    non_finite_float: bool,
}

impl Findings {
    fn note_commit_or_literal(&mut self, code: CanonicalErrorCode) {
        if self.first_commit_or_literal.is_none() {
            self.first_commit_or_literal = Some(code);
        }
    }
}

struct ObjectFrame {
    had_duplicate: bool,
    /// Mid-object NaN/OOR must prevent committing duplicate for this frame
    /// and all currently open ancestors.
    interrupted: bool,
}

struct ParseReport {
    value: Value,
    findings: Findings,
}

fn parse_document(text: &str) -> Result<ParseReport, CanonicalEncodingError> {
    let mut parser = Parser::new(text);
    parser.skip_whitespace();
    if parser.is_eof() {
        return Err(syntax_invalid());
    }
    let value = parser.parse_value(0)?;
    parser.skip_whitespace();
    if !parser.is_eof() {
        return Err(syntax_invalid());
    }
    Ok(ParseReport {
        value,
        findings: Findings {
            first_commit_or_literal: parser.first_commit_or_literal,
            first_unicode_error: parser.first_unicode_error,
            non_finite_float: parser.non_finite_float,
        },
    })
}

struct Parser<'a> {
    input: &'a str,
    bytes: &'a [u8],
    index: usize,
    object_stack: Vec<ObjectFrame>,
    first_commit_or_literal: Option<CanonicalErrorCode>,
    first_unicode_error: Option<CanonicalErrorCode>,
    non_finite_float: bool,
}

impl<'a> Parser<'a> {
    fn new(input: &'a str) -> Self {
        Self {
            input,
            bytes: input.as_bytes(),
            index: 0,
            object_stack: Vec::new(),
            first_commit_or_literal: None,
            first_unicode_error: None,
            non_finite_float: false,
        }
    }

    fn note_number_literal_error(&mut self, code: CanonicalErrorCode) {
        if self.first_commit_or_literal.is_none() {
            self.first_commit_or_literal = Some(code);
        }
        for frame in &mut self.object_stack {
            frame.interrupted = true;
        }
    }

    fn note_duplicate_committed(&mut self) {
        if self.first_commit_or_literal.is_none() {
            self.first_commit_or_literal = Some(CanonicalErrorCode::JcsDuplicateMember);
        }
    }

    fn is_eof(&self) -> bool {
        self.index >= self.bytes.len()
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.index).copied()
    }

    fn bump(&mut self) {
        if self.index < self.bytes.len() {
            self.index += 1;
        }
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.bump();
        }
    }

    fn parse_value(&mut self, depth: usize) -> Result<Value, CanonicalEncodingError> {
        match self.peek() {
            Some(b'n') => {
                self.expect_literal(b"null")?;
                Ok(Value::Null)
            }
            Some(b't') => {
                self.expect_literal(b"true")?;
                Ok(Value::Bool(true))
            }
            Some(b'f') => {
                self.expect_literal(b"false")?;
                Ok(Value::Bool(false))
            }
            Some(b'N') => {
                self.expect_literal(b"NaN")?;
                self.note_number_literal_error(CanonicalErrorCode::JcsNonFiniteNumber);
                Ok(Value::Null)
            }
            Some(b'I') => {
                self.expect_literal(b"Infinity")?;
                self.note_number_literal_error(CanonicalErrorCode::JcsNonFiniteNumber);
                Ok(Value::Null)
            }
            Some(b'"') => Ok(Value::String(self.parse_string_for_value()?)),
            Some(b'[') => self.parse_array(depth),
            Some(b'{') => self.parse_object(depth),
            Some(b'-') => self.parse_negative_or_number(),
            Some(b'0'..=b'9') => self.parse_number(false),
            _ => Err(syntax_invalid()),
        }
    }

    fn expect_literal(&mut self, literal: &[u8]) -> Result<(), CanonicalEncodingError> {
        for expected in literal {
            match self.peek() {
                Some(byte) if byte == *expected => self.bump(),
                _ => return Err(syntax_invalid()),
            }
        }
        Ok(())
    }

    fn parse_negative_or_number(&mut self) -> Result<Value, CanonicalEncodingError> {
        self.bump(); // '-'
        match self.peek() {
            Some(b'I') => {
                self.expect_literal(b"Infinity")?;
                self.note_number_literal_error(CanonicalErrorCode::JcsNonFiniteNumber);
                Ok(Value::Null)
            }
            Some(b'0'..=b'9') => self.parse_number(true),
            _ => Err(syntax_invalid()),
        }
    }

    fn parse_array(&mut self, depth: usize) -> Result<Value, CanonicalEncodingError> {
        if depth >= MAX_NESTING_DEPTH {
            return Err(syntax_invalid());
        }
        self.bump(); // '['
        self.skip_whitespace();
        let mut items = Vec::new();
        if self.peek() == Some(b']') {
            self.bump();
            return Ok(Value::Array(items));
        }
        loop {
            items.push(self.parse_value(depth + 1)?);
            self.skip_whitespace();
            match self.peek() {
                Some(b',') => {
                    self.bump();
                    self.skip_whitespace();
                    if self.peek() == Some(b']') {
                        return Err(syntax_invalid());
                    }
                }
                Some(b']') => {
                    self.bump();
                    break;
                }
                _ => return Err(syntax_invalid()),
            }
        }
        Ok(Value::Array(items))
    }

    fn parse_object(&mut self, depth: usize) -> Result<Value, CanonicalEncodingError> {
        if depth >= MAX_NESTING_DEPTH {
            return Err(syntax_invalid());
        }
        self.bump(); // '{'
        self.skip_whitespace();
        self.object_stack.push(ObjectFrame {
            had_duplicate: false,
            interrupted: false,
        });
        let mut pairs = Vec::new();
        // UTF-16 code-unit identity: Rust String cannot hold lone surrogates, so
        // duplicate detection must not use lossy String keys.
        let mut seen: BTreeSet<Vec<u16>> = BTreeSet::new();
        if self.peek() == Some(b'}') {
            self.bump();
            self.object_stack.pop();
            return Ok(Value::Object(Map::new()));
        }
        loop {
            if self.peek() != Some(b'"') {
                return Err(syntax_invalid());
            }
            let (key_units, key_for_value) = self.parse_string_key()?;
            self.skip_whitespace();
            if self.peek() != Some(b':') {
                return Err(syntax_invalid());
            }
            self.bump();
            self.skip_whitespace();
            let value = self.parse_value(depth + 1)?;
            if !seen.insert(key_units)
                && let Some(frame) = self.object_stack.last_mut()
            {
                frame.had_duplicate = true;
            }
            pairs.push((key_for_value, value));
            self.skip_whitespace();
            match self.peek() {
                Some(b',') => {
                    self.bump();
                    self.skip_whitespace();
                    if self.peek() == Some(b'}') {
                        return Err(syntax_invalid());
                    }
                }
                Some(b'}') => {
                    self.bump();
                    // Commit only after successful close, and only if this object
                    // was not interrupted by mid-member NaN/OOR (formal contract:
                    // whole-document syntax is checked before semantic codes).
                    if let Some(frame) = self.object_stack.pop()
                        && frame.had_duplicate
                        && !frame.interrupted
                    {
                        self.note_duplicate_committed();
                    }
                    break;
                }
                _ => return Err(syntax_invalid()),
            }
        }
        let mut object = Map::new();
        for (key, value) in pairs {
            object.insert(key, value);
        }
        Ok(Value::Object(object))
    }

    fn parse_number(&mut self, negative: bool) -> Result<Value, CanonicalEncodingError> {
        let start = if negative { self.index - 1 } else { self.index };

        match self.peek() {
            Some(b'0') => {
                self.bump();
                if matches!(self.peek(), Some(b'0'..=b'9')) {
                    return Err(syntax_invalid());
                }
            }
            Some(b'1'..=b'9') => {
                self.bump();
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.bump();
                }
            }
            _ => return Err(syntax_invalid()),
        }

        let mut is_float = false;
        if self.peek() == Some(b'.') {
            is_float = true;
            self.bump();
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(syntax_invalid());
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.bump();
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            is_float = true;
            self.bump();
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.bump();
            }
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(syntax_invalid());
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.bump();
            }
        }

        let lexeme = &self.input[start..self.index];
        if is_float {
            match lexeme.parse::<f64>() {
                Ok(value) if value.is_finite() => match Number::from_f64(value) {
                    Some(number) => Ok(Value::Number(number)),
                    None => {
                        self.non_finite_float = true;
                        Ok(Value::Null)
                    }
                },
                Ok(_) => {
                    self.non_finite_float = true;
                    Ok(Value::Null)
                }
                Err(_) => Err(syntax_invalid()),
            }
        } else {
            match parse_integer_lexeme(lexeme) {
                Ok(int_value) => Ok(Value::Number(Number::from(int_value))),
                Err(error) if error.code() == CanonicalErrorCode::JcsNumberOutOfRange => {
                    self.note_number_literal_error(CanonicalErrorCode::JcsNumberOutOfRange);
                    Ok(Value::Null)
                }
                Err(error) => Err(error),
            }
        }
    }

    fn parse_string_for_value(&mut self) -> Result<String, CanonicalEncodingError> {
        let (_units, text) = self.parse_string_key()?;
        Ok(text)
    }

    /// Parse a JSON string into UTF-16 units (for key identity) and a Rust `String`
    /// for the `Value` tree. Lone surrogates are preserved in `units` and recorded
    /// as a finding; the `String` uses U+FFFD placeholders so the tree stays valid.
    fn parse_string_key(&mut self) -> Result<(Vec<u16>, String), CanonicalEncodingError> {
        self.bump(); // opening quote
        let mut units = Vec::new();
        let mut text = String::new();
        loop {
            match self.peek() {
                None => return Err(syntax_invalid()),
                Some(b'"') => {
                    self.bump();
                    return Ok((units, text));
                }
                Some(b'\\') => {
                    self.bump();
                    self.parse_escape_into(&mut units, &mut text)?;
                }
                Some(byte) if byte < 0x20 => return Err(syntax_invalid()),
                Some(_) => {
                    let rest = &self.input[self.index..];
                    match rest.chars().next() {
                        Some(ch) => {
                            self.index += ch.len_utf8();
                            units.extend(ch.encode_utf16(&mut [0; 2]).iter().copied());
                            text.push(ch);
                            self.note_unicode_scalar(u32::from(ch));
                        }
                        None => return Err(syntax_invalid()),
                    }
                }
            }
        }
    }

    fn parse_escape_into(
        &mut self,
        units: &mut Vec<u16>,
        text: &mut String,
    ) -> Result<(), CanonicalEncodingError> {
        match self.peek() {
            Some(b'"') => {
                self.bump();
                units.push(u16::from(b'"'));
                text.push('"');
                Ok(())
            }
            Some(b'\\') => {
                self.bump();
                units.push(u16::from(b'\\'));
                text.push('\\');
                Ok(())
            }
            Some(b'/') => {
                self.bump();
                units.push(u16::from(b'/'));
                text.push('/');
                Ok(())
            }
            Some(b'b') => {
                self.bump();
                units.push(0x0008);
                text.push('\u{0008}');
                Ok(())
            }
            Some(b'f') => {
                self.bump();
                units.push(0x000c);
                text.push('\u{000c}');
                Ok(())
            }
            Some(b'n') => {
                self.bump();
                units.push(u16::from(b'\n'));
                text.push('\n');
                Ok(())
            }
            Some(b'r') => {
                self.bump();
                units.push(u16::from(b'\r'));
                text.push('\r');
                Ok(())
            }
            Some(b't') => {
                self.bump();
                units.push(u16::from(b'\t'));
                text.push('\t');
                Ok(())
            }
            Some(b'u') => {
                self.bump();
                let unit = self.read_hex4()?;
                if (0xD800..=0xDBFF).contains(&unit) {
                    // Only consume a following `\uXXXX` when it is a trailing surrogate.
                    if let Some(low) = self.peek_unicode_escape_unit() {
                        if (0xDC00..=0xDFFF).contains(&low) {
                            self.consume_unicode_escape()?;
                            let combined = 0x10000
                                + (((u32::from(unit) - 0xD800) << 10) | (u32::from(low) - 0xDC00));
                            match char::from_u32(combined) {
                                Some(ch) => {
                                    units.extend(ch.encode_utf16(&mut [0; 2]).iter().copied());
                                    text.push(ch);
                                    self.note_unicode_scalar(u32::from(ch));
                                    Ok(())
                                }
                                None => {
                                    self.note_lone_surrogate();
                                    units.push(unit);
                                    units.push(low);
                                    text.push('\u{FFFD}');
                                    Ok(())
                                }
                            }
                        } else {
                            self.note_lone_surrogate();
                            units.push(unit);
                            text.push('\u{FFFD}');
                            Ok(())
                        }
                    } else {
                        self.note_lone_surrogate();
                        units.push(unit);
                        text.push('\u{FFFD}');
                        Ok(())
                    }
                } else if (0xDC00..=0xDFFF).contains(&unit) {
                    self.note_lone_surrogate();
                    units.push(unit);
                    text.push('\u{FFFD}');
                    Ok(())
                } else {
                    match char::from_u32(u32::from(unit)) {
                        Some(ch) => {
                            units.push(unit);
                            text.push(ch);
                            self.note_unicode_scalar(u32::from(unit));
                            Ok(())
                        }
                        None => {
                            self.note_lone_surrogate();
                            units.push(unit);
                            text.push('\u{FFFD}');
                            Ok(())
                        }
                    }
                }
            }
            _ => Err(syntax_invalid()),
        }
    }

    fn note_lone_surrogate(&mut self) {
        if self.first_unicode_error.is_none() {
            self.first_unicode_error = Some(CanonicalErrorCode::InvalidUnicode);
        }
    }

    fn note_unicode_scalar(&mut self, codepoint: u32) {
        if self.first_unicode_error.is_some() {
            return;
        }
        if (0xD800..=0xDFFF).contains(&codepoint) {
            self.first_unicode_error = Some(CanonicalErrorCode::InvalidUnicode);
        } else if is_unicode_noncharacter(codepoint) {
            self.first_unicode_error = Some(CanonicalErrorCode::UnicodeNoncharacter);
        }
    }

    fn peek_unicode_escape_unit(&self) -> Option<u16> {
        if self.peek() != Some(b'\\') {
            return None;
        }
        if self.bytes.get(self.index + 1).copied() != Some(b'u') {
            return None;
        }
        if self.index + 6 > self.bytes.len() {
            return None;
        }
        let mut value = 0u16;
        for offset in 2..6 {
            let byte = self.bytes[self.index + offset];
            let nibble = match byte {
                b'0'..=b'9' => u16::from(byte - b'0'),
                b'a'..=b'f' => u16::from(byte - b'a') + 10,
                b'A'..=b'F' => u16::from(byte - b'A') + 10,
                _ => return None,
            };
            value = (value << 4) | nibble;
        }
        Some(value)
    }

    fn consume_unicode_escape(&mut self) -> Result<(), CanonicalEncodingError> {
        self.bump(); // '\'
        self.bump(); // 'u'
        let _ = self.read_hex4()?;
        Ok(())
    }

    fn read_hex4(&mut self) -> Result<u16, CanonicalEncodingError> {
        let mut value = 0u16;
        for _ in 0..4 {
            let byte = match self.peek() {
                Some(byte) => byte,
                None => return Err(syntax_invalid()),
            };
            let nibble = match byte {
                b'0'..=b'9' => u16::from(byte - b'0'),
                b'a'..=b'f' => u16::from(byte - b'a') + 10,
                b'A'..=b'F' => u16::from(byte - b'A') + 10,
                _ => return Err(syntax_invalid()),
            };
            self.bump();
            value = (value << 4) | nibble;
        }
        Ok(value)
    }
}

fn parse_integer_lexeme(lexeme: &str) -> Result<i64, CanonicalEncodingError> {
    if lexeme.is_empty() {
        return Err(syntax_invalid());
    }
    let digits = match lexeme.strip_prefix('-') {
        Some(rest) => rest,
        None => lexeme,
    };
    if digits.is_empty() || digits.bytes().any(|b| !b.is_ascii_digit()) {
        return Err(syntax_invalid());
    }
    if digits.len() > IJSON_MAX_INTEGER_DIGITS {
        return Err(number_out_of_range());
    }
    let value: i64 = match lexeme.parse() {
        Ok(value) => value,
        Err(_) => return Err(number_out_of_range()),
    };
    if !(IJSON_MIN_SAFE_INTEGER..=IJSON_MAX_SAFE_INTEGER).contains(&value) {
        return Err(number_out_of_range());
    }
    Ok(value)
}

fn parse_with_serde_visitor(text: &str) -> Result<(Value, bool), CanonicalEncodingError> {
    let duplicate = Cell::new(false);
    let mut de = serde_json::Deserializer::from_str(text);
    let value = CanonicalValue {
        duplicate: &duplicate,
        depth: 0,
    }
    .deserialize(&mut de)
    .map_err(|_| syntax_invalid())?;
    de.end().map_err(|_| syntax_invalid())?;
    Ok((value, duplicate.get()))
}

struct CanonicalValue<'a> {
    duplicate: &'a Cell<bool>,
    depth: usize,
}

impl<'de> DeserializeSeed<'de> for CanonicalValue<'_> {
    type Value = Value;

    fn deserialize<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(CanonicalVisitor {
            duplicate: self.duplicate,
            depth: self.depth,
        })
    }
}

struct CanonicalVisitor<'a> {
    duplicate: &'a Cell<bool>,
    depth: usize,
}

impl<'de> Visitor<'de> for CanonicalVisitor<'_> {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_bool<E: de::Error>(self, value: bool) -> Result<Self::Value, E> {
        Ok(Value::Bool(value))
    }

    fn visit_i64<E: de::Error>(self, value: i64) -> Result<Self::Value, E> {
        Ok(Value::Number(Number::from(value)))
    }

    fn visit_u64<E: de::Error>(self, value: u64) -> Result<Self::Value, E> {
        Ok(Value::Number(Number::from(value)))
    }

    fn visit_f64<E: de::Error>(self, value: f64) -> Result<Self::Value, E> {
        if !value.is_finite() {
            return Err(de::Error::custom("non-finite number"));
        }
        Number::from_f64(value)
            .map(Value::Number)
            .ok_or_else(|| de::Error::custom("non-finite number"))
    }

    fn visit_str<E: de::Error>(self, value: &str) -> Result<Self::Value, E> {
        Ok(Value::String(value.to_owned()))
    }

    fn visit_string<E: de::Error>(self, value: String) -> Result<Self::Value, E> {
        Ok(Value::String(value))
    }

    fn visit_none<E: de::Error>(self) -> Result<Self::Value, E> {
        Ok(Value::Null)
    }

    fn visit_unit<E: de::Error>(self) -> Result<Self::Value, E> {
        Ok(Value::Null)
    }

    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
        if self.depth >= MAX_NESTING_DEPTH {
            return Err(de::Error::custom("nesting too deep"));
        }
        let mut items = Vec::new();
        while let Some(item) = seq.next_element_seed(CanonicalValue {
            duplicate: self.duplicate,
            depth: self.depth + 1,
        })? {
            items.push(item);
        }
        Ok(Value::Array(items))
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
        if self.depth >= MAX_NESTING_DEPTH {
            return Err(de::Error::custom("nesting too deep"));
        }
        let mut seen = BTreeSet::new();
        let mut object = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            let value = map.next_value_seed(CanonicalValue {
                duplicate: self.duplicate,
                depth: self.depth + 1,
            })?;
            // Duplicate only after a complete key/value pair (matches Python hook).
            if !seen.insert(key.clone()) {
                self.duplicate.set(true);
            } else {
                object.insert(key, value);
            }
        }
        Ok(Value::Object(object))
    }
}

fn validate_unicode_tree(value: &Value) -> Result<(), CanonicalEncodingError> {
    match value {
        Value::String(text) => validate_unicode_string(text),
        Value::Array(items) => {
            for item in items {
                validate_unicode_tree(item)?;
            }
            Ok(())
        }
        Value::Object(map) => {
            for (key, item) in map {
                validate_unicode_string(key)?;
                validate_unicode_tree(item)?;
            }
            Ok(())
        }
        Value::Null | Value::Bool(_) | Value::Number(_) => Ok(()),
    }
}

fn validate_ijson_numbers(value: &Value) -> Result<(), CanonicalEncodingError> {
    match value {
        Value::Number(number) => validate_ijson_number(number),
        Value::Array(items) => {
            for item in items {
                validate_ijson_numbers(item)?;
            }
            Ok(())
        }
        Value::Object(map) => {
            for item in map.values() {
                validate_ijson_numbers(item)?;
            }
            Ok(())
        }
        Value::Null | Value::Bool(_) | Value::String(_) => Ok(()),
    }
}

fn validate_ijson_number(number: &Number) -> Result<(), CanonicalEncodingError> {
    if let Some(int) = number.as_i64() {
        if !(IJSON_MIN_SAFE_INTEGER..=IJSON_MAX_SAFE_INTEGER).contains(&int) {
            return Err(number_out_of_range());
        }
        return Ok(());
    }
    if let Some(uint) = number.as_u64() {
        if uint > IJSON_MAX_SAFE_INTEGER as u64 {
            return Err(number_out_of_range());
        }
        return Ok(());
    }
    if let Some(float) = number.as_f64() {
        if !float.is_finite() {
            return Err(non_finite());
        }
        return Ok(());
    }
    Err(number_out_of_range())
}

#[cfg(test)]
mod tests {
    use super::canonicalize_jcs;
    use crate::errors::CanonicalErrorCode;

    #[test]
    fn object_key_order_and_no_whitespace() -> Result<(), String> {
        let out = canonicalize_jcs(br#"{"b":1,"a":2}"#).map_err(|e| e.to_string())?;
        assert_eq!(out, br#"{"a":2,"b":1}"#);
        Ok(())
    }

    #[test]
    fn array_preserves_order() -> Result<(), String> {
        let out = canonicalize_jcs(b"[3,1,2]").map_err(|e| e.to_string())?;
        assert_eq!(out, b"[3,1,2]");
        Ok(())
    }

    #[test]
    fn non_bmp_key_order() -> Result<(), String> {
        let raw = "{\"\u{1F600}\":1,\"a\":2}".as_bytes();
        let out = canonicalize_jcs(raw).map_err(|e| e.to_string())?;
        assert_eq!(out, b"{\"a\":2,\"\xf0\x9f\x98\x80\":1}");
        Ok(())
    }

    #[test]
    fn negative_zero_float_normalizes() -> Result<(), String> {
        let out = canonicalize_jcs(b"-0.0").map_err(|e| e.to_string())?;
        assert_eq!(out, b"0");
        Ok(())
    }

    #[test]
    fn safe_integer_extrema() -> Result<(), String> {
        assert_eq!(
            canonicalize_jcs(b"9007199254740991").map_err(|e| e.to_string())?,
            b"9007199254740991"
        );
        assert_eq!(
            canonicalize_jcs(b"-9007199254740991").map_err(|e| e.to_string())?,
            b"-9007199254740991"
        );
        Ok(())
    }

    #[test]
    fn rejects_invalid_utf8() -> Result<(), String> {
        match canonicalize_jcs(b"\xff") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::InvalidUtf8);
                Ok(())
            }
            Ok(_) => Err("invalid utf8 must fail".to_string()),
        }
    }

    #[test]
    fn committed_duplicate_wins_over_later_immediate_errors() -> Result<(), String> {
        let cases = [
            (
                br#"[{"a":1,"a":2},9007199254740992]"#.as_slice(),
                CanonicalErrorCode::JcsDuplicateMember,
            ),
            (
                br#"[{"a":1,"a":2},NaN]"#.as_slice(),
                CanonicalErrorCode::JcsDuplicateMember,
            ),
            (
                br#"{"outer":{"a":1,"a":2},"x":9007199254740992}"#.as_slice(),
                CanonicalErrorCode::JcsDuplicateMember,
            ),
            (
                br#"[1e400,{"a":1,"a":2}]"#.as_slice(),
                CanonicalErrorCode::JcsDuplicateMember,
            ),
        ];
        for (input, expected) in cases {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(error.code(), expected, "input={input:?}");
                }
                Ok(_) => return Err(format!("must fail for {input:?}")),
            }
        }
        Ok(())
    }

    #[test]
    fn trailing_syntax_wins_over_nested_duplicate() -> Result<(), String> {
        // Formal contract: trailing comma/garbage → SYNTAX_INVALID (over Python oracle).
        for input in [
            br#"[{"a":1,"a":2},]"#.as_slice(),
            br#"[{"a":1,"a":2}]x"#,
            br#"{"a":1,"a":2}x"#,
        ] {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(
                        error.code(),
                        CanonicalErrorCode::JcsSyntaxInvalid,
                        "input={input:?}"
                    );
                }
                Ok(_) => return Err(format!("must be syntax invalid: {input:?}")),
            }
        }
        Ok(())
    }

    #[test]
    fn unclosed_object_duplicate_does_not_override_member_errors() -> Result<(), String> {
        let cases = [
            (
                br#"{"a":1,"a":2,"b":9007199254740992}"#.as_slice(),
                CanonicalErrorCode::JcsNumberOutOfRange,
            ),
            (
                br#"{"a":1,"a":2,"b":NaN}"#.as_slice(),
                CanonicalErrorCode::JcsNonFiniteNumber,
            ),
            (
                br#"[9007199254740992,{"a":1,"a":2}]"#.as_slice(),
                CanonicalErrorCode::JcsNumberOutOfRange,
            ),
            (
                br#"{"x":9007199254740992,"outer":{"a":1,"a":2}}"#.as_slice(),
                CanonicalErrorCode::JcsNumberOutOfRange,
            ),
        ];
        for (input, expected) in cases {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(error.code(), expected, "input={input:?}");
                }
                Ok(_) => return Err(format!("must fail for {input:?}")),
            }
        }
        Ok(())
    }

    #[test]
    fn rejects_duplicate_member() -> Result<(), String> {
        match canonicalize_jcs(br#"{"a":1,"a":2}"#) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsDuplicateMember);
                Ok(())
            }
            Ok(_) => Err("duplicate must fail".to_string()),
        }
    }

    #[test]
    fn malformed_duplicate_key_is_syntax_invalid() -> Result<(), String> {
        match canonicalize_jcs(br#"{"a":1,"a"}"#) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsSyntaxInvalid);
                Ok(())
            }
            Ok(_) => Err("malformed member must be syntax invalid".to_string()),
        }
    }

    #[test]
    fn duplicate_after_incomplete_object_is_syntax_invalid() -> Result<(), String> {
        for input in [br#"{"a":1,"a":2,}"#.as_slice(), br#"{"a":1,"a":2,"b"}"#] {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(
                        error.code(),
                        CanonicalErrorCode::JcsSyntaxInvalid,
                        "input={input:?}"
                    );
                }
                Ok(_) => return Err(format!("must be syntax invalid: {input:?}")),
            }
        }
        Ok(())
    }

    #[test]
    fn rejects_huge_integer_without_float_rounding() -> Result<(), String> {
        for input in [
            b"18446744073709551616".as_slice(),
            b"12345678901234567890123456789012345678901",
        ] {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(
                        error.code(),
                        CanonicalErrorCode::JcsNumberOutOfRange,
                        "input={input:?}"
                    );
                }
                Ok(bytes) => {
                    return Err(format!(
                        "huge integer must not silently round, got {}",
                        String::from_utf8_lossy(&bytes)
                    ));
                }
            }
        }
        Ok(())
    }

    #[test]
    fn nan_in_structurally_invalid_context_is_syntax() -> Result<(), String> {
        for input in [br#"{"x",NaN}"#.as_slice(), b"[1,,NaN]"] {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(
                        error.code(),
                        CanonicalErrorCode::JcsSyntaxInvalid,
                        "input={input:?}"
                    );
                }
                Ok(_) => return Err(format!("must be syntax invalid: {input:?}")),
            }
        }
        Ok(())
    }

    #[test]
    fn rejects_integer_out_of_ijson_range() -> Result<(), String> {
        match canonicalize_jcs(b"9007199254740992") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsNumberOutOfRange);
                Ok(())
            }
            Ok(_) => Err("out of range must fail".to_string()),
        }
    }

    #[test]
    fn rejects_nan_and_infinity() -> Result<(), String> {
        for input in [
            b"NaN".as_slice(),
            b"Infinity",
            b"-Infinity",
            br#"{"a":NaN}"#,
        ] {
            match canonicalize_jcs(input) {
                Err(error) => assert_eq!(error.code(), CanonicalErrorCode::JcsNonFiniteNumber),
                Ok(_) => return Err(format!("non-finite must fail for {input:?}")),
            }
        }
        Ok(())
    }

    #[test]
    fn rejects_surrogate_escape() -> Result<(), String> {
        match canonicalize_jcs(b"\"\\uD800\"") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::InvalidUnicode);
                Ok(())
            }
            Ok(_) => Err("surrogate must fail".to_string()),
        }
    }

    #[test]
    fn rejects_noncharacter() -> Result<(), String> {
        match canonicalize_jcs(b"\"\\uFFFF\"") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::UnicodeNoncharacter);
                Ok(())
            }
            Ok(_) => Err("noncharacter must fail".to_string()),
        }
    }

    #[test]
    fn syntax_invalid_not_unicode() -> Result<(), String> {
        match canonicalize_jcs(b"{") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsSyntaxInvalid);
                Ok(())
            }
            Ok(_) => Err("truncated must be syntax invalid".to_string()),
        }
    }

    #[test]
    fn idempotent_on_canonical_output() -> Result<(), String> {
        let first =
            canonicalize_jcs(br#"{"z":true,"a":[1,2],"m":null}"#).map_err(|e| e.to_string())?;
        let second = canonicalize_jcs(&first).map_err(|e| e.to_string())?;
        assert_eq!(first, second);
        Ok(())
    }

    #[test]
    fn rejects_leading_zero_integer() -> Result<(), String> {
        match canonicalize_jcs(b"01") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsSyntaxInvalid);
                Ok(())
            }
            Ok(_) => Err("leading zero must be syntax invalid".to_string()),
        }
    }

    #[test]
    fn accepts_large_finite_float_lexemes() -> Result<(), String> {
        for input in [
            b"1e20".as_slice(),
            b"1e21",
            b"9007199254740992.0",
            b"1.0e16",
            b"1.5e20",
        ] {
            let out = canonicalize_jcs(input).map_err(|error| {
                format!(
                    "float lexeme must succeed for {}: {}",
                    String::from_utf8_lossy(input),
                    error.code()
                )
            })?;
            assert!(!out.is_empty(), "input={input:?}");
        }
        match canonicalize_jcs(b"9007199254740992") {
            Err(error) => assert_eq!(error.code(), CanonicalErrorCode::JcsNumberOutOfRange),
            Ok(_) => return Err("integer lexeme must remain out of range".to_string()),
        }
        Ok(())
    }

    #[test]
    fn deferred_semantic_errors_do_not_shadow_trailing_syntax() -> Result<(), String> {
        for input in [
            b"1e400x".as_slice(),
            b"[1e400,]",
            b"\"\\uD800\"x",
            b"[\"\\uD800\",]",
        ] {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(
                        error.code(),
                        CanonicalErrorCode::JcsSyntaxInvalid,
                        "input={input:?}"
                    );
                }
                Ok(_) => return Err(format!("must be syntax invalid: {input:?}")),
            }
        }
        match canonicalize_jcs(b"1e400") {
            Err(error) => assert_eq!(error.code(), CanonicalErrorCode::JcsNonFiniteNumber),
            Ok(_) => return Err("1e400 must be non-finite".to_string()),
        }
        match canonicalize_jcs(b"\"\\uD800\"") {
            Err(error) => assert_eq!(error.code(), CanonicalErrorCode::InvalidUnicode),
            Ok(_) => return Err("lone surrogate must be invalid unicode".to_string()),
        }
        match canonicalize_jcs(b"9007199254740992x") {
            Err(error) => assert_eq!(error.code(), CanonicalErrorCode::JcsSyntaxInvalid),
            Ok(_) => return Err("integer+trailing garbage must be syntax invalid".to_string()),
        }
        Ok(())
    }

    #[test]
    fn multi_fault_uses_fixed_stage_priority() -> Result<(), String> {
        let cases = [
            (
                br#"[1e400,"\uD800"]"#.as_slice(),
                CanonicalErrorCode::InvalidUnicode,
            ),
            (
                br#"[1e400,"\uFFFF"]"#.as_slice(),
                CanonicalErrorCode::UnicodeNoncharacter,
            ),
            (
                br#"{"a":1e400,"a":2}"#.as_slice(),
                CanonicalErrorCode::JcsDuplicateMember,
            ),
            (
                br#"{"a":"\uD800","a":2}"#.as_slice(),
                CanonicalErrorCode::JcsDuplicateMember,
            ),
        ];
        for (input, expected) in cases {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(error.code(), expected, "input={input:?}");
                }
                Ok(_) => return Err(format!("must fail for {input:?}")),
            }
        }
        Ok(())
    }

    #[test]
    fn unicode_stage_uses_document_traversal_order() -> Result<(), String> {
        let cases = [
            (
                br#""\uFFFF\uD800""#.as_slice(),
                CanonicalErrorCode::UnicodeNoncharacter,
            ),
            (
                br#""\uD800\uFFFF""#.as_slice(),
                CanonicalErrorCode::InvalidUnicode,
            ),
            (
                br#"["\uFFFF","\uD800"]"#.as_slice(),
                CanonicalErrorCode::UnicodeNoncharacter,
            ),
            (
                br#"["\uD800","\uFFFF"]"#.as_slice(),
                CanonicalErrorCode::InvalidUnicode,
            ),
            (
                br#"{"a":"\uFFFF","b":"\uD800"}"#.as_slice(),
                CanonicalErrorCode::UnicodeNoncharacter,
            ),
            (
                br#"{"a":"\uD800","b":"\uFFFF"}"#.as_slice(),
                CanonicalErrorCode::InvalidUnicode,
            ),
            (
                br#"{"b":"\uD800","a":"\uFFFF"}"#.as_slice(),
                CanonicalErrorCode::InvalidUnicode,
            ),
        ];
        for (input, expected) in cases {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(error.code(), expected, "input={input:?}");
                }
                Ok(_) => return Err(format!("must fail for {input:?}")),
            }
        }
        Ok(())
    }

    #[test]
    fn lone_surrogate_keys_do_not_fabricate_duplicate() -> Result<(), String> {
        let cases = [
            br#"{"\uD800":1,"":2}"#.as_slice(),
            br#"{"\uD800":1,"\uD801":2}"#,
            br#"{"\uDC00":1,"":2}"#,
        ];
        for input in cases {
            match canonicalize_jcs(input) {
                Err(error) => {
                    assert_eq!(
                        error.code(),
                        CanonicalErrorCode::InvalidUnicode,
                        "input={input:?}"
                    );
                }
                Ok(_) => return Err(format!("must be invalid unicode: {input:?}")),
            }
        }
        match canonicalize_jcs(br#"{"\uD800":1,"\uD800":2}"#) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsDuplicateMember);
                Ok(())
            }
            Ok(_) => Err("identical surrogate keys must be duplicate".to_string()),
        }
    }

    #[test]
    fn nesting_limit_returns_typed_error_not_abort() -> Result<(), String> {
        let allowed = {
            let mut bytes = Vec::new();
            bytes.extend(std::iter::repeat_n(b'[', 127));
            bytes.push(b'1');
            bytes.extend(std::iter::repeat_n(b']', 127));
            bytes
        };
        canonicalize_jcs(&allowed)
            .map_err(|error| format!("127 nested arrays must succeed: {}", error.code()))?;

        let too_deep = {
            let mut bytes = Vec::new();
            bytes.extend(std::iter::repeat_n(b'[', 50_000));
            bytes.push(b'1');
            bytes.extend(std::iter::repeat_n(b']', 50_000));
            bytes
        };
        match canonicalize_jcs(&too_deep) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsSyntaxInvalid);
                Ok(())
            }
            Ok(_) => Err("50k nested arrays must fail with typed syntax error".to_string()),
        }
    }

    #[test]
    fn null_nan_suffix_is_syntax_invalid() -> Result<(), String> {
        match canonicalize_jcs(b"nullNaN") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsSyntaxInvalid);
                Ok(())
            }
            Ok(_) => Err("nullNaN must be syntax invalid".to_string()),
        }
    }

    #[test]
    fn float_overflow_is_non_finite() -> Result<(), String> {
        match canonicalize_jcs(b"1e400") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::JcsNonFiniteNumber);
                Ok(())
            }
            Ok(_) => Err("1e400 must be non-finite".to_string()),
        }
    }
}
