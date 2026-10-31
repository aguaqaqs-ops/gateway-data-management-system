//! Bounded JSON value validation for the frozen Table Access contract.
//!
//! Any JSON top-level value is allowed. Non-finite constants and numeric
//! overflow, nesting beyond 100, and unpaired surrogate escapes are rejected.
//! Raw control characters inside strings and a leading U+FEFF are rejected.
//! Validation is iterative so hostile nesting cannot recurse.

const fn is_json_ws(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r')
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Frame {
    Array,
    Object,
}

struct Reader<'a> {
    bytes: &'a [u8],
    pos: usize,
}

impl Reader<'_> {
    fn skip_ws(&mut self) {
        while self.pos < self.bytes.len() && is_json_ws(self.bytes[self.pos]) {
            self.pos += 1;
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.pos).copied()
    }

    fn eat(&mut self, token: &[u8]) -> bool {
        if self.bytes[self.pos..].starts_with(token) {
            self.pos += token.len();
            true
        } else {
            false
        }
    }

    fn string(&mut self) -> bool {
        // At the opening quote.
        self.pos += 1;
        while let Some(byte) = self.peek() {
            match byte {
                b'"' => {
                    self.pos += 1;
                    return true;
                }
                b'\\' => {
                    self.pos += 1;
                    match self.peek() {
                        Some(b'"' | b'\\' | b'/' | b'b' | b'f' | b'n' | b'r' | b't') => {
                            self.pos += 1
                        }
                        Some(b'u') => {
                            let Some(code_unit) = self.unicode_escape() else {
                                return false;
                            };
                            if (0xd800..=0xdbff).contains(&code_unit) {
                                if self.peek() != Some(b'\\')
                                    || self.bytes.get(self.pos + 1) != Some(&b'u')
                                {
                                    return false;
                                }
                                self.pos += 1;
                                let Some(low) = self.unicode_escape() else {
                                    return false;
                                };
                                if !(0xdc00..=0xdfff).contains(&low) {
                                    return false;
                                }
                            } else if (0xdc00..=0xdfff).contains(&code_unit) {
                                return false;
                            }
                        }
                        _ => return false,
                    }
                }
                0x00..=0x1f => return false,
                _ => self.pos += 1,
            }
        }
        false
    }

    /// Reads a `\\uXXXX` escape with the cursor positioned at `u`.
    fn unicode_escape(&mut self) -> Option<u16> {
        if self.peek() != Some(b'u') {
            return None;
        }
        self.pos += 1;
        let mut value = 0u16;
        for _ in 0..4 {
            let digit = (self.peek()? as char).to_digit(16)?;
            value = value.checked_mul(16)?.checked_add(digit as u16)?;
            self.pos += 1;
        }
        Some(value)
    }

    fn digits(&mut self) -> usize {
        let start = self.pos;
        while self.peek().is_some_and(|b| b.is_ascii_digit()) {
            self.pos += 1;
        }
        self.pos - start
    }

    /// `-?(0|[1-9]\d*)(\.\d+)?([eE][-+]?\d+)?`.
    fn number(&mut self) -> bool {
        let start = self.pos;
        if self.peek() == Some(b'-') {
            self.pos += 1;
        }
        match self.peek() {
            Some(b'0') => self.pos += 1,
            Some(b'1'..=b'9') => {
                self.digits();
            }
            _ => return false,
        }
        let mut floating = false;
        if self.peek() == Some(b'.')
            && self
                .bytes
                .get(self.pos + 1)
                .is_some_and(|b| b.is_ascii_digit())
        {
            floating = true;
            self.pos += 1;
            self.digits();
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            let saved = self.pos;
            self.pos += 1;
            floating = true;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.pos += 1;
            }
            if self.digits() == 0 {
                // The scanner backtracks; the `e` is then unexpected data.
                self.pos = saved;
                floating = false;
            }
        }
        if floating {
            let Ok(text) = std::str::from_utf8(&self.bytes[start..self.pos]) else {
                return false;
            };
            if !text.parse::<f64>().is_ok_and(f64::is_finite) {
                return false;
            }
        }
        true
    }

    /// One scalar, or the opening of a container (pushed onto `stack`).
    fn value_start(&mut self, stack: &mut Vec<Frame>) -> Option<bool> {
        match self.peek()? {
            b'"' => Some(self.string()),
            b'{' => {
                self.pos += 1;
                stack.push(Frame::Object);
                Some(true)
            }
            b'[' => {
                self.pos += 1;
                stack.push(Frame::Array);
                Some(true)
            }
            b'n' => Some(self.eat(b"null")),
            b't' => Some(self.eat(b"true")),
            b'f' => Some(self.eat(b"false")),
            b'-' | b'0'..=b'9' => Some(self.number()),
            _ => Some(false),
        }
    }
}

pub(crate) fn valid_json_value(text: &str) -> bool {
    if text.starts_with('\u{feff}') {
        return false;
    }
    let mut reader = Reader {
        bytes: text.as_bytes(),
        pos: 0,
    };
    let mut stack: Vec<Frame> = Vec::new();
    reader.skip_ws();
    // Read the first value.
    let depth_before = stack.len();
    if reader.value_start(&mut stack) != Some(true) || stack.len() > 100 {
        return false;
    }
    let mut just_opened = stack.len() > depth_before;
    while let Some(frame) = stack.last().copied() {
        reader.skip_ws();
        if just_opened {
            just_opened = false;
            // Empty container?
            let close = if frame == Frame::Array { b']' } else { b'}' };
            if reader.peek() == Some(close) {
                reader.pos += 1;
                stack.pop();
                continue;
            }
            if !read_member(&mut reader, frame, &mut stack, &mut just_opened) {
                return false;
            }
            continue;
        }
        // After a member: `,` or the closer.
        let close = if frame == Frame::Array { b']' } else { b'}' };
        match reader.peek() {
            Some(byte) if byte == close => {
                reader.pos += 1;
                stack.pop();
            }
            Some(b',') => {
                reader.pos += 1;
                reader.skip_ws();
                if !read_member(&mut reader, frame, &mut stack, &mut just_opened) {
                    return false;
                }
            }
            _ => return false,
        }
    }
    reader.skip_ws();
    reader.pos == reader.bytes.len()
}

/// Reads one array element or one `"key": value` pair; a nested container
/// is only opened (its members are read by the caller's loop).
fn read_member(
    reader: &mut Reader<'_>,
    frame: Frame,
    stack: &mut Vec<Frame>,
    just_opened: &mut bool,
) -> bool {
    if frame == Frame::Object {
        if reader.peek() != Some(b'"') || !reader.string() {
            return false;
        }
        reader.skip_ws();
        if reader.peek() != Some(b':') {
            return false;
        }
        reader.pos += 1;
        reader.skip_ws();
    }
    let depth_before = stack.len();
    if reader.value_start(stack) != Some(true) || stack.len() > 100 {
        return false;
    }
    *just_opened = stack.len() > depth_before;
    true
}

#[cfg(test)]
mod tests {
    use super::valid_json_value as ok;

    #[test]
    fn accepts_contract_json_values() {
        for text in [
            "{}",
            "[]",
            "1",
            "-0",
            "1.5e+3",
            "\"a\"",
            " {\"a\": [1, 2, {\"b\": null}]} ",
            "\"\\ud83d\\ude00\"",
            "[true,false,null]",
            "1E5",
            "0.0",
            "1e308",
            "1e-4000",
            "1234567890123456789012345678901234567890",
        ] {
            assert!(ok(text), "should accept {text:?}");
        }
        for text in [
            "",
            " ",
            "{",
            "[1,]",
            "{\"a\":1,}",
            "01",
            "1.",
            ".5",
            "+1",
            "1e",
            "\"\\x\"",
            "\"a\u{1}\"",
            "\u{feff}1",
            "[1 2]",
            "{1:2}",
            "nul",
            "tru",
            "-",
            "\"abc",
            "1 2",
            "{\"a\" 1}",
            "NaN",
            "-Infinity",
            "Infinity",
            "1e400",
            "\"\\ud800\"",
            "\"\\udc00\"",
        ] {
            assert!(!ok(text), "should reject {text:?}");
        }
        assert!(ok(&format!("{}0{}", "[".repeat(100), "]".repeat(100))));
        assert!(!ok(&format!("{}0{}", "[".repeat(101), "]".repeat(101))));
    }
}
