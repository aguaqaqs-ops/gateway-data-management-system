//! Byte cursor with the reference parser's whitespace, comment, keyword and
//! identifier rules (`_sql_scan.ByteCursor`).

use gateway_shared_kernel::{CanonicalErrorCode, canonicalize_identifier};

use super::errors::{
    ANSI_QUOTES_MESSAGE, Fault, PResult, ParserDiagnosticCode as Code, VERSIONED_MESSAGE,
};

/// Whitespace between tokens: TAB, LF, CR and SPACE only.
pub(crate) const fn is_ws(byte: u8) -> bool {
    matches!(byte, b'\t' | b'\n' | b'\r' | b' ')
}

pub(crate) const fn is_ident_start(byte: u8) -> bool {
    byte.is_ascii_alphabetic() || byte == b'_'
}

pub(crate) const fn is_ident_continue(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'$'
}

pub(crate) fn starts_with(data: &[u8], pos: usize, end: usize, token: &[u8]) -> bool {
    pos + token.len() <= end && data.get(pos..pos + token.len()) == Some(token)
}

/// `--` starts a comment only when followed by whitespace or the end.
pub(crate) fn starts_dash_comment(data: &[u8], pos: usize, end: usize) -> bool {
    if pos + 2 > end || data[pos] != b'-' || data[pos + 1] != b'-' {
        return false;
    }
    if pos + 2 == end {
        return true;
    }
    is_ws(data[pos + 2])
}

#[derive(Debug, Clone)]
pub(crate) struct Cursor<'a> {
    pub data: &'a [u8],
    pub pos: usize,
    pub end: usize,
}

impl<'a> Cursor<'a> {
    pub fn new(data: &'a [u8], start: usize, end: usize) -> Self {
        let end = end.min(data.len());
        Self {
            data,
            pos: start.min(end),
            end,
        }
    }

    pub fn at_end(&self) -> bool {
        self.pos >= self.end
    }

    pub fn peek(&self) -> Option<u8> {
        if self.pos >= self.end {
            None
        } else {
            Some(self.data[self.pos])
        }
    }

    pub fn peek_at(&self, offset: usize) -> Option<u8> {
        let index = self.pos + offset;
        if index >= self.end {
            None
        } else {
            Some(self.data[index])
        }
    }

    pub fn skip_ws_and_comments(&mut self) -> PResult<()> {
        while self.pos < self.end {
            let byte = self.data[self.pos];
            if is_ws(byte) {
                self.pos += 1;
                continue;
            }
            if byte == b'-' && starts_dash_comment(self.data, self.pos, self.end) {
                self.skip_line_comment();
                continue;
            }
            if byte == b'#' {
                self.skip_line_comment();
                continue;
            }
            if byte == b'/' {
                if starts_with(self.data, self.pos, self.end, b"/*!") {
                    return Err(Fault::unsupported(self.pos, VERSIONED_MESSAGE));
                }
                if starts_with(self.data, self.pos, self.end, b"/*") {
                    self.skip_block_comment()?;
                    continue;
                }
            }
            return Ok(());
        }
        Ok(())
    }

    /// Case-insensitive keyword match. Like the reference, whitespace and
    /// comments are consumed even when the keyword does not match.
    pub fn try_keyword(&mut self, keyword: &[u8]) -> PResult<bool> {
        self.skip_ws_and_comments()?;
        let length = keyword.len();
        if self.pos + length > self.end {
            return Ok(false);
        }
        if !self.data[self.pos..self.pos + length].eq_ignore_ascii_case(keyword) {
            return Ok(false);
        }
        let after = self.pos + length;
        if after < self.end && is_ident_continue(self.data[after]) {
            return Ok(false);
        }
        self.pos = after;
        Ok(true)
    }

    /// Returns `(display, canonical)`.
    pub fn parse_identifier(&mut self, max_code_points: usize) -> PResult<(String, String)> {
        self.skip_ws_and_comments()?;
        let start = self.pos;
        let display = match self.peek() {
            Some(b'`') => self.parse_backtick_identifier()?,
            Some(b'"') => return Err(Fault::unsupported(self.pos, ANSI_QUOTES_MESSAGE)),
            _ => self.parse_unquoted_identifier()?,
        };
        if display.chars().count() > max_code_points {
            return Err(Fault::resource("max_identifier_code_points", start));
        }
        let canonical = match canonicalize_identifier(&display) {
            Ok(value) => value,
            Err(error) => {
                let code = if error.code() == CanonicalErrorCode::IdentifierCollision {
                    Code::CanonicalIdentifierCollision
                } else {
                    Code::MalformedSql
                };
                return Err(Fault::new(code, start, error.message().to_string()));
            }
        };
        if canonical.is_empty() {
            return Err(Fault::malformed(start, "identifier must not be empty"));
        }
        Ok((display, canonical))
    }

    pub fn parse_table_name(&mut self, max_code_points: usize) -> PResult<(String, String)> {
        let mut name = self.parse_identifier(max_code_points)?;
        self.skip_ws_and_comments()?;
        if self.peek() == Some(b'.') {
            self.pos += 1;
            name = self.parse_identifier(max_code_points)?;
        }
        Ok(name)
    }

    /// Returns `(start, end)` where `data[start] == '('` and `data[end - 1] == ')'`.
    pub fn take_balanced_paren(&mut self) -> PResult<(usize, usize)> {
        self.skip_ws_and_comments()?;
        let start = self.pos;
        if self.peek() != Some(b'(') {
            return Err(Fault::malformed(self.pos, "expected '('"));
        }
        let mut depth: usize = 0;
        let mut quote: Option<u8> = None;
        let mut escape = false;
        while self.pos < self.end {
            let byte = self.data[self.pos];
            if let Some(q) = quote {
                if escape {
                    escape = false;
                    self.pos += 1;
                    continue;
                }
                if byte == b'\\' && q == b'\'' {
                    escape = true;
                    self.pos += 1;
                    continue;
                }
                if byte == q {
                    if self.peek_at(1) == Some(q) {
                        self.pos += 2;
                        continue;
                    }
                    quote = None;
                }
                self.pos += 1;
                continue;
            }
            match byte {
                b'\'' | b'`' => {
                    quote = Some(byte);
                    self.pos += 1;
                    continue;
                }
                b'"' => return Err(Fault::unsupported(self.pos, ANSI_QUOTES_MESSAGE)),
                b'/' if starts_with(self.data, self.pos, self.end, b"/*!") => {
                    return Err(Fault::unsupported(self.pos, VERSIONED_MESSAGE));
                }
                b'/' if starts_with(self.data, self.pos, self.end, b"/*") => {
                    self.skip_block_comment()?;
                    continue;
                }
                b'-' if starts_dash_comment(self.data, self.pos, self.end) => {
                    self.skip_line_comment();
                    continue;
                }
                b'#' => {
                    self.skip_line_comment();
                    continue;
                }
                b'(' => depth += 1,
                b')' => {
                    depth = depth.saturating_sub(1);
                    self.pos += 1;
                    if depth == 0 {
                        return Ok((start, self.pos));
                    }
                    continue;
                }
                _ => {}
            }
            self.pos += 1;
        }
        Err(Fault::malformed(start, "unclosed parenthesis"))
    }

    pub fn skip_line_comment(&mut self) {
        let window = &self.data[self.pos..self.end];
        match memchr::memchr2(b'\n', b'\r', window) {
            Some(index) => self.pos += index,
            None => self.pos = self.end,
        }
    }

    pub fn skip_block_comment(&mut self) -> PResult<()> {
        let start = self.pos;
        self.pos += 2;
        while self.pos + 1 < self.end {
            if self.data[self.pos] == b'*' && self.data[self.pos + 1] == b'/' {
                self.pos += 2;
                return Ok(());
            }
            self.pos += 1;
        }
        Err(Fault::malformed(start, "unclosed block comment"))
    }

    fn parse_unquoted_identifier(&mut self) -> PResult<String> {
        match self.peek() {
            Some(byte) if is_ident_start(byte) => {}
            _ => return Err(Fault::malformed(self.pos, "expected identifier")),
        }
        let start = self.pos;
        self.pos += 1;
        while self.pos < self.end && is_ident_continue(self.data[self.pos]) {
            self.pos += 1;
        }
        // The identifier bytes are ASCII by construction.
        Ok(String::from_utf8_lossy(&self.data[start..self.pos]).into_owned())
    }

    fn parse_backtick_identifier(&mut self) -> PResult<String> {
        let start = self.pos;
        self.pos += 1;
        let mut raw: Vec<u8> = Vec::new();
        let mut piece_start = self.pos;
        while self.pos < self.end {
            match memchr::memchr(b'`', &self.data[self.pos..self.end]) {
                None => break,
                Some(index) => self.pos += index,
            }
            raw.extend_from_slice(&self.data[piece_start..self.pos]);
            if self.peek_at(1) == Some(b'`') {
                raw.push(b'`');
                self.pos += 2;
                piece_start = self.pos;
                continue;
            }
            self.pos += 1;
            return String::from_utf8(raw)
                .map_err(|_| Fault::malformed(start, "identifier is not strict UTF-8"));
        }
        Err(Fault::malformed(start, "unclosed quoted identifier"))
    }
}

/// `bytes.isspace()` in Python: SPACE, TAB, LF, CR, VT and FF.
pub(crate) const fn is_ascii_space(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
}

/// `str.isspace()` in Python, used by `str.strip()` and `str.split()`.
pub(crate) fn is_python_space(ch: char) -> bool {
    ch.is_whitespace() || matches!(ch, '\u{1c}'..='\u{1f}')
}

/// `str.strip()` with no arguments.
pub(crate) fn python_strip(text: &str) -> &str {
    text.trim_matches(is_python_space)
}

/// `" ".join(text.split())`.
pub(crate) fn python_collapse_ws(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for (index, part) in text
        .split(is_python_space)
        .filter(|p| !p.is_empty())
        .enumerate()
    {
        if index > 0 {
            out.push(' ');
        }
        out.push_str(part);
    }
    out
}
