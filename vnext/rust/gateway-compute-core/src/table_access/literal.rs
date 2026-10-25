//! SQL dump literal lexer (`_sql_values.parse_literal`).

use std::borrow::Cow;

use super::cursor::{Cursor, is_ascii_space};
use super::errors::{Fault, ParserDiagnosticCode as Code};

/// A lexed literal. String bodies borrow the source when they contain no
/// escapes or doubled quotes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Lit<'a> {
    Null,
    /// `TRUE` / `FALSE`, as the lowercase text the reference stores.
    Keyword(&'static str),
    /// ASCII numeric text, sign included.
    Number(&'a [u8]),
    /// `'...'` body after unescaping. Always valid UTF-8 for UTF-8 input.
    Str(Cow<'a, [u8]>),
    /// `X'..'` or `0x..`.
    Hex(Vec<u8>),
    /// `B'..'` or `0b..`: the bit text and its packed bytes.
    Bits {
        text: Cow<'a, [u8]>,
        raw: Vec<u8>,
    },
}

/// `Literal` errors are recoverable where the reference catches
/// `LiteralError`; `Halt` errors always stop the document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum LexError {
    Literal(Fault),
    Halt(Fault),
}

impl LexError {
    fn literal(code: Code, offset: usize, message: &'static str) -> Self {
        Self::Literal(Fault::new(code, offset, message))
    }
}

fn halt(fault: Fault) -> LexError {
    LexError::Halt(fault)
}

const fn escape_byte(escape: u8) -> u8 {
    match escape {
        b'n' => b'\n',
        b'r' => b'\r',
        b't' => b'\t',
        b'0' => 0x00,
        b'Z' => 0x1a,
        b'b' => 0x08,
        // `\\`, `\'`, `\"` and every other byte map to themselves.
        other => other,
    }
}

pub(crate) fn parse_literal<'a>(cursor: &mut Cursor<'a>) -> Result<Lit<'a>, LexError> {
    cursor.skip_ws_and_comments().map_err(halt)?;
    let start = cursor.pos;
    let Some(byte) = cursor.peek() else {
        return Err(LexError::literal(
            Code::MalformedSql,
            start,
            "expected literal",
        ));
    };
    if byte.is_ascii_alphabetic() {
        for (keyword, value) in [
            (&b"null"[..], None),
            (&b"true"[..], Some("true")),
            (&b"false"[..], Some("false")),
        ] {
            let saved = cursor.pos;
            if cursor.try_keyword(keyword).map_err(halt)? {
                return Ok(match value {
                    None => Lit::Null,
                    Some(text) => Lit::Keyword(text),
                });
            }
            cursor.pos = saved;
        }
        let saved = cursor.pos;
        if cursor.try_keyword(b"default").map_err(halt)? {
            return Err(LexError::literal(
                Code::IncompleteInsert,
                start,
                "DEFAULT in VALUES is not derived by the source dump parser",
            ));
        }
        cursor.pos = saved;
    }
    let next = cursor.peek_at(1);
    let prefixed = matches!(next, Some(b'x' | b'X' | b'b' | b'B'));
    if byte == b'\'' || matches!(byte, b'x' | b'X' | b'b' | b'B') || (byte == b'0' && prefixed) {
        return parse_quoted_or_prefixed(cursor);
    }
    if matches!(byte, b'+' | b'-' | b'.') || byte.is_ascii_digit() {
        return parse_number(cursor);
    }
    Err(LexError::literal(
        Code::MalformedSql,
        start,
        "unsupported SQL value expression",
    ))
}

fn parse_number<'a>(cursor: &mut Cursor<'a>) -> Result<Lit<'a>, LexError> {
    let start = cursor.pos;
    if matches!(cursor.peek(), Some(b'+' | b'-')) {
        cursor.pos += 1;
    }
    let mut digits = 0usize;
    while cursor.peek().is_some_and(|b| b.is_ascii_digit()) {
        digits += 1;
        cursor.pos += 1;
    }
    if cursor.peek() == Some(b'.') {
        cursor.pos += 1;
        while cursor.peek().is_some_and(|b| b.is_ascii_digit()) {
            digits += 1;
            cursor.pos += 1;
        }
    }
    if matches!(cursor.peek(), Some(b'e' | b'E')) {
        cursor.pos += 1;
        if matches!(cursor.peek(), Some(b'+' | b'-')) {
            cursor.pos += 1;
        }
        let mut exponent = 0usize;
        while cursor.peek().is_some_and(|b| b.is_ascii_digit()) {
            exponent += 1;
            cursor.pos += 1;
        }
        if exponent == 0 {
            return Err(LexError::literal(
                Code::MalformedSql,
                start,
                "malformed numeric literal",
            ));
        }
    }
    if digits == 0 {
        return Err(LexError::literal(
            Code::MalformedSql,
            start,
            "malformed numeric literal",
        ));
    }
    Ok(Lit::Number(&cursor.data[start..cursor.pos]))
}

fn parse_quoted_or_prefixed<'a>(cursor: &mut Cursor<'a>) -> Result<Lit<'a>, LexError> {
    let start = cursor.pos;
    let byte = cursor.peek();
    let next = cursor.peek_at(1);
    if matches!(byte, Some(b'x' | b'X')) && next == Some(b'\'') {
        cursor.pos += 1;
        let quote_start = cursor.pos;
        let body = parse_quoted_bytes(cursor, false)?;
        return hex_body_to_bytes(&body).map(Lit::Hex).ok_or_else(|| {
            LexError::literal(Code::MalformedSql, quote_start, "malformed hex literal")
        });
    }
    if byte == Some(b'0') && matches!(next, Some(b'x' | b'X')) {
        cursor.pos += 2;
        let hex_start = cursor.pos;
        while cursor.peek().is_some_and(|b| b.is_ascii_hexdigit()) {
            cursor.pos += 1;
        }
        if cursor.pos == hex_start {
            return Err(LexError::literal(
                Code::MalformedSql,
                start,
                "malformed hex literal",
            ));
        }
        let digits = &cursor.data[hex_start..cursor.pos];
        return hex_digits_to_bytes(digits)
            .map(Lit::Hex)
            .ok_or_else(|| LexError::literal(Code::MalformedSql, start, "malformed hex literal"));
    }
    if matches!(byte, Some(b'b' | b'B')) && next == Some(b'\'') {
        cursor.pos += 1;
        let body = parse_quoted_bytes(cursor, true)?;
        if !body.is_ascii() {
            // The reference raises an uncaught UnicodeDecodeError here.
            return Err(LexError::literal(
                Code::MalformedSql,
                start,
                "bit literal is not ASCII",
            ));
        }
        if !body.iter().all(|b| matches!(b, b'0' | b'1')) {
            return Err(LexError::literal(
                Code::MalformedSql,
                start,
                "malformed bit literal",
            ));
        }
        let raw = bit_string_to_bytes(&body);
        return Ok(Lit::Bits { text: body, raw });
    }
    if byte == Some(b'0') && matches!(next, Some(b'b' | b'B')) {
        cursor.pos += 2;
        let bit_start = cursor.pos;
        while matches!(cursor.peek(), Some(b'0' | b'1')) {
            cursor.pos += 1;
        }
        if cursor.pos == bit_start {
            return Err(LexError::literal(
                Code::MalformedSql,
                start,
                "malformed bit literal",
            ));
        }
        let text = &cursor.data[bit_start..cursor.pos];
        let raw = bit_string_to_bytes(text);
        return Ok(Lit::Bits {
            text: Cow::Borrowed(text),
            raw,
        });
    }
    if byte == Some(b'\'') {
        let raw = parse_quoted_bytes(cursor, true)?;
        if std::str::from_utf8(&raw).is_err() {
            return Err(LexError::Literal(Fault::illegal(
                start,
                "string literal is not strict UTF-8",
            )));
        }
        return Ok(Lit::Str(raw));
    }
    Err(LexError::literal(
        Code::MalformedSql,
        start,
        "expected literal",
    ))
}

/// Body of a `'...'` literal starting at the opening quote. With `escapes`,
/// backslash escapes are decoded; `''` always means one quote.
fn parse_quoted_bytes<'a>(
    cursor: &mut Cursor<'a>,
    escapes: bool,
) -> Result<Cow<'a, [u8]>, LexError> {
    let start = cursor.pos;
    if cursor.peek() != Some(b'\'') {
        return Err(LexError::literal(
            Code::MalformedSql,
            start,
            "expected quoted literal",
        ));
    }
    cursor.pos += 1;
    let data = cursor.data;
    let end = cursor.end;
    let mut owned: Option<Vec<u8>> = None;
    let mut piece_start = cursor.pos;
    while cursor.pos < end {
        let window = &data[cursor.pos..end];
        let found = if escapes {
            memchr::memchr2(b'\'', b'\\', window)
        } else {
            memchr::memchr(b'\'', window)
        };
        let Some(index) = found else {
            break;
        };
        cursor.pos += index;
        if data[cursor.pos] == b'\'' {
            if cursor.pos + 1 < end && data[cursor.pos + 1] == b'\'' {
                let buffer = owned.get_or_insert_with(Vec::new);
                buffer.extend_from_slice(&data[piece_start..cursor.pos]);
                buffer.push(b'\'');
                cursor.pos += 2;
                piece_start = cursor.pos;
                continue;
            }
            let body = match owned {
                None => Cow::Borrowed(&data[piece_start..cursor.pos]),
                Some(mut buffer) => {
                    buffer.extend_from_slice(&data[piece_start..cursor.pos]);
                    Cow::Owned(buffer)
                }
            };
            cursor.pos += 1;
            return Ok(body);
        }
        // Backslash escape.
        let buffer = owned.get_or_insert_with(Vec::new);
        buffer.extend_from_slice(&data[piece_start..cursor.pos]);
        cursor.pos += 1;
        if cursor.pos >= end {
            return Err(LexError::literal(
                Code::MalformedSql,
                start,
                "unclosed string",
            ));
        }
        buffer.push(escape_byte(data[cursor.pos]));
        cursor.pos += 1;
        piece_start = cursor.pos;
    }
    cursor.pos = end;
    Err(LexError::literal(
        Code::MalformedSql,
        start,
        "unclosed string",
    ))
}

const fn hex_value(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

/// `0x` digits (hex only): an odd count gets a leading zero.
fn hex_digits_to_bytes(digits: &[u8]) -> Option<Vec<u8>> {
    let mut padded = Vec::with_capacity(digits.len() + 1);
    if digits.len() % 2 == 1 {
        padded.push(b'0');
    }
    padded.extend_from_slice(digits);
    from_hex(&padded)
}

/// `X'..'` body: ASCII, odd length gets a leading `0`, then `bytes.fromhex`.
fn hex_body_to_bytes(body: &[u8]) -> Option<Vec<u8>> {
    if !body.is_ascii() {
        return None;
    }
    let mut padded = Vec::with_capacity(body.len() + 1);
    if body.len() % 2 == 1 {
        padded.push(b'0');
    }
    padded.extend_from_slice(body);
    from_hex(&padded)
}

/// Python `bytes.fromhex`: ASCII whitespace between byte pairs is skipped.
fn from_hex(text: &[u8]) -> Option<Vec<u8>> {
    let mut out = Vec::with_capacity(text.len() / 2);
    let mut index = 0;
    while index < text.len() {
        if is_ascii_space(text[index]) {
            index += 1;
            continue;
        }
        let high = hex_value(text[index])?;
        let low = hex_value(*text.get(index + 1)?)?;
        out.push(high << 4 | low);
        index += 2;
    }
    Some(out)
}

/// `int(bits, 2).to_bytes(max(1, ceil(len/8)), "big")`; empty gives `b"\0"`.
pub(crate) fn bit_string_to_bytes(bits: &[u8]) -> Vec<u8> {
    if bits.is_empty() {
        return vec![0];
    }
    let length = bits.len().div_ceil(8).max(1);
    let mut out = vec![0u8; length];
    let pad = length * 8 - bits.len();
    for (index, bit) in bits.iter().enumerate() {
        if *bit == b'1' {
            let position = pad + index;
            out[position / 8] |= 0x80 >> (position % 8);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lex(text: &str) -> Result<Lit<'_>, LexError> {
        let mut cursor = Cursor::new(text.as_bytes(), 0, text.len());
        parse_literal(&mut cursor)
    }

    #[test]
    fn strings_borrow_without_escapes_and_decode_escapes() {
        assert_eq!(lex("'abc'"), Ok(Lit::Str(Cow::Borrowed(&b"abc"[..]))));
        assert_eq!(
            lex(r"'a\nb\'c''d\%'"),
            Ok(Lit::Str(Cow::Owned(b"a\nb'c'd%".to_vec())))
        );
        assert_eq!(
            lex(r"'\0\Z\b\t\r\\'"),
            Ok(Lit::Str(Cow::Owned(b"\0\x1a\x08\t\r\\".to_vec())))
        );
    }

    #[test]
    fn hex_and_bit_literals() {
        assert_eq!(lex("x'4142'"), Ok(Lit::Hex(b"AB".to_vec())));
        assert_eq!(lex("X'141'"), Ok(Lit::Hex(vec![0x01, 0x41])));
        // Whitespace counts toward the odd-length padding, as in the reference.
        assert_eq!(lex("x' 4142 '"), Ok(Lit::Hex(b"AB".to_vec())));
        assert!(matches!(lex("x'41 42'"), Err(LexError::Literal(_))));
        assert_eq!(lex("0xABC"), Ok(Lit::Hex(vec![0x0a, 0xbc])));
        assert_eq!(
            lex("b'101'"),
            Ok(Lit::Bits {
                text: Cow::Borrowed(&b"101"[..]),
                raw: vec![5]
            })
        );
        assert_eq!(
            lex("0b000000001"),
            Ok(Lit::Bits {
                text: Cow::Borrowed(&b"000000001"[..]),
                raw: vec![0, 1]
            })
        );
        assert_eq!(
            lex("b''"),
            Ok(Lit::Bits {
                text: Cow::Borrowed(&b""[..]),
                raw: vec![0]
            })
        );
        assert!(matches!(lex("b'12'"), Err(LexError::Literal(_))));
        assert!(matches!(lex("x'4'z"), Ok(Lit::Hex(_))));
        assert!(matches!(lex("0x"), Err(LexError::Literal(_))));
    }

    #[test]
    fn keywords_numbers_and_rejects() {
        assert_eq!(lex("NULL"), Ok(Lit::Null));
        assert_eq!(lex(" True"), Ok(Lit::Keyword("true")));
        assert_eq!(lex("-1.5e-3"), Ok(Lit::Number(b"-1.5e-3")));
        assert_eq!(lex(".5"), Ok(Lit::Number(b".5")));
        assert!(
            matches!(lex("DEFAULT"), Err(LexError::Literal(f)) if f.code == Code::IncompleteInsert)
        );
        assert!(
            matches!(lex("_binary 'a'"), Err(LexError::Literal(f)) if f.code == Code::MalformedSql)
        );
        assert!(matches!(lex("1e"), Err(LexError::Literal(_))));
        assert!(matches!(lex("-"), Err(LexError::Literal(_))));
        assert!(matches!(lex("/*!40000 1 */"), Err(LexError::Halt(_))));
        assert!(matches!(lex("'abc"), Err(LexError::Literal(_))));
        assert!(matches!(lex("NULLX"), Err(LexError::Literal(_))));
    }
}
