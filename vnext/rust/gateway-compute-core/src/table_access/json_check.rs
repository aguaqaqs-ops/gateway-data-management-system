//! Acceptance check equal to Python `json.loads(text)` succeeding.
//!
//! Python's decoder is more permissive than RFC 8259 in a few places that
//! matter for equivalence: `NaN`, `Infinity` and `-Infinity` are accepted,
//! lone surrogate escapes are accepted, and any top-level value is allowed.
//! Raw control characters inside strings are rejected (strict mode), and a
//! leading U+FEFF is rejected. Nesting is checked iteratively; the reference
//! raises an uncaught `RecursionError` on very deep nesting, which this check
//! does not reproduce.

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
                            self.pos += 1;
                            for _ in 0..4 {
                                if !self.peek().is_some_and(|b| b.is_ascii_hexdigit()) {
                                    return false;
                                }
                                self.pos += 1;
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

    fn digits(&mut self) -> usize {
        let start = self.pos;
        while self.peek().is_some_and(|b| b.is_ascii_digit()) {
            self.pos += 1;
        }
        self.pos - start
    }

    /// `-?(0|[1-9]\d*)(\.\d+)?([eE][-+]?\d+)?`, plus `-Infinity`.
    fn number(&mut self) -> bool {
        if self.peek() == Some(b'-') {
            self.pos += 1;
            if self.eat(b"Infinity") {
                return true;
            }
        }
        match self.peek() {
            Some(b'0') => self.pos += 1,
            Some(b'1'..=b'9') => {
                self.digits();
            }
            _ => return false,
        }
        if self.peek() == Some(b'.')
            && self
                .bytes
                .get(self.pos + 1)
                .is_some_and(|b| b.is_ascii_digit())
        {
            self.pos += 1;
            self.digits();
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            let saved = self.pos;
            self.pos += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.pos += 1;
            }
            if self.digits() == 0 {
                // The scanner backtracks; the `e` is then unexpected data.
                self.pos = saved;
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
            b'N' => Some(self.eat(b"NaN")),
            b'I' => Some(self.eat(b"Infinity")),
            b'-' | b'0'..=b'9' => Some(self.number()),
            _ => Some(false),
        }
    }
}

pub(crate) fn python_json_loads_accepts(text: &str) -> bool {
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
    if reader.value_start(&mut stack) != Some(true) {
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
    if reader.value_start(stack) != Some(true) {
        return false;
    }
    *just_opened = stack.len() > depth_before;
    true
}

#[cfg(test)]
mod tests {
    use super::python_json_loads_accepts as ok;

    #[test]
    fn matches_python_json_loads_acceptance() {
        for text in [
            "{}",
            "[]",
            "1",
            "-0",
            "1.5e+3",
            "\"a\"",
            " {\"a\": [1, 2, {\"b\": null}]} ",
            "NaN",
            "-Infinity",
            "Infinity",
            "\"\\ud800\"",
            "[true,false,null]",
            "1E5",
            "0.0",
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
        ] {
            assert!(!ok(text), "should reject {text:?}");
        }
    }
}
