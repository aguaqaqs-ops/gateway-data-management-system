//! Statement boundary scanner (`_sql_scan.iter_statements`).
//!
//! The scan is sequential because quote state depends on everything before
//! it. While scanning it records "split points": top-level commas (paren
//! depth 0, outside quotes and comments) at least `chunk_bytes` apart. In an
//! INSERT these commas separate value tuples, so the value parser can work on
//! the chunks between them in parallel.

use super::cursor::{
    Cursor, is_ascii_space, is_ident_continue, is_ws, starts_dash_comment, starts_with,
};
use super::errors::{ANSI_QUOTES_MESSAGE, Fault, PResult, VERSIONED_MESSAGE};

const ALLOWLIST_INNER_HEADS: [&[u8]; 7] = [
    b"set", b"create", b"insert", b"drop", b"lock", b"unlock", b"alter",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct StatementSpan {
    pub start: usize,
    pub end: usize,
    /// Offsets of top-level commas usable as chunk boundaries (ascending).
    pub splits: Vec<usize>,
}

/// Bytes that need attention outside quotes in a plain statement.
const fn special_table() -> [bool; 256] {
    let mut table = [false; 256];
    let specials: &[u8] = b"'`\"/-#;(),";
    let mut index = 0;
    while index < specials.len() {
        table[specials[index] as usize] = true;
        index += 1;
    }
    table
}

static SPECIAL: [bool; 256] = special_table();

pub(crate) struct Scanner<'a> {
    cursor: Cursor<'a>,
    chunk_bytes: usize,
    max_statement_bytes: usize,
}

impl<'a> Scanner<'a> {
    pub fn new(data: &'a [u8], chunk_bytes: usize, max_statement_bytes: usize) -> Self {
        Self {
            cursor: Cursor::new(data, 0, data.len()),
            chunk_bytes: chunk_bytes.max(1),
            max_statement_bytes,
        }
    }

    pub fn position(&self) -> usize {
        self.cursor.pos
    }

    pub fn next_statement(&mut self) -> PResult<Option<StatementSpan>> {
        self.skip_leading_trivia()?;
        if self.cursor.at_end() {
            return Ok(None);
        }
        let span = if starts_with(self.cursor.data, self.cursor.pos, self.cursor.end, b"/*!") {
            self.expand_versioned_statement()?
        } else {
            self.scan_plain_statement()?
        };
        if span.end - span.start > self.max_statement_bytes {
            return Err(Fault::resource("max_statement_bytes", span.start));
        }
        Ok(Some(span))
    }

    fn skip_leading_trivia(&mut self) -> PResult<()> {
        let cursor = &mut self.cursor;
        while cursor.pos < cursor.end {
            let byte = cursor.data[cursor.pos];
            if is_ws(byte) {
                cursor.pos += 1;
                continue;
            }
            if byte == b'-' && starts_dash_comment(cursor.data, cursor.pos, cursor.end) {
                cursor.skip_line_comment();
                continue;
            }
            if byte == b'#' {
                cursor.skip_line_comment();
                continue;
            }
            if starts_with(cursor.data, cursor.pos, cursor.end, b"/*!") {
                return Ok(());
            }
            if starts_with(cursor.data, cursor.pos, cursor.end, b"/*") {
                cursor.skip_block_comment()?;
                continue;
            }
            if byte == b';' {
                cursor.pos += 1;
                continue;
            }
            return Ok(());
        }
        Ok(())
    }

    fn expand_versioned_statement(&mut self) -> PResult<StatementSpan> {
        let cursor = &mut self.cursor;
        let start = cursor.pos;
        if cursor.pos + 3 >= cursor.end {
            return Err(Fault::malformed(start, "unclosed versioned comment"));
        }
        cursor.pos += 3;
        while cursor.pos < cursor.end && cursor.data[cursor.pos].is_ascii_digit() {
            cursor.pos += 1;
        }
        let inner_start = cursor.pos;
        let Some(close) = find_block_close(cursor.data, cursor.pos, cursor.end) else {
            return Err(Fault::malformed(start, "unclosed versioned comment"));
        };
        let inner = &cursor.data[inner_start..close];
        if !inner_is_allowlisted(inner) {
            return Err(Fault::unsupported(start, VERSIONED_MESSAGE));
        }
        cursor.pos = close + 2;
        while cursor.pos < cursor.end && is_ws(cursor.data[cursor.pos]) {
            cursor.pos += 1;
        }
        if cursor.peek() == Some(b';') {
            cursor.pos += 1;
        }
        Ok(StatementSpan {
            start: inner_start,
            end: close,
            splits: Vec::new(),
        })
    }

    fn scan_plain_statement(&mut self) -> PResult<StatementSpan> {
        let chunk_bytes = self.chunk_bytes;
        let cursor = &mut self.cursor;
        let data = cursor.data;
        let end = cursor.end;
        let start = cursor.pos;
        let mut splits = Vec::new();
        let mut last_split = start;
        let mut depth: i64 = 0;
        let mut pos = cursor.pos;
        while pos < end {
            let byte = data[pos];
            if !SPECIAL[usize::from(byte)] {
                pos += 1;
                continue;
            }
            match byte {
                b'\'' => {
                    pos = skip_single_quoted(data, pos + 1, end)
                        .ok_or_else(|| Fault::malformed(start, "unclosed quoted literal"))?;
                }
                b'`' => {
                    pos = skip_backtick_quoted(data, pos + 1, end)
                        .ok_or_else(|| Fault::malformed(start, "unclosed quoted literal"))?;
                }
                b'"' => return Err(Fault::unsupported(pos, ANSI_QUOTES_MESSAGE)),
                b'/' => {
                    if starts_with(data, pos, end, b"/*!") {
                        return Err(Fault::unsupported(pos, VERSIONED_MESSAGE));
                    }
                    if starts_with(data, pos, end, b"/*") {
                        cursor.pos = pos;
                        cursor.skip_block_comment()?;
                        pos = cursor.pos;
                    } else {
                        pos += 1;
                    }
                }
                b'-' => {
                    if starts_dash_comment(data, pos, end) {
                        cursor.pos = pos;
                        cursor.skip_line_comment();
                        pos = cursor.pos;
                    } else {
                        pos += 1;
                    }
                }
                b'#' => {
                    cursor.pos = pos;
                    cursor.skip_line_comment();
                    pos = cursor.pos;
                }
                b';' => {
                    cursor.pos = pos + 1;
                    return Ok(StatementSpan {
                        start,
                        end: pos,
                        splits,
                    });
                }
                b'(' => {
                    depth += 1;
                    pos += 1;
                }
                b')' => {
                    depth -= 1;
                    pos += 1;
                }
                b',' => {
                    if depth == 0 && pos - last_split >= chunk_bytes {
                        splits.push(pos);
                        last_split = pos;
                    }
                    pos += 1;
                }
                _ => pos += 1,
            }
        }
        cursor.pos = end;
        Ok(StatementSpan { start, end, splits })
    }
}

/// Position after the closing quote of a `'...'` literal whose body starts at
/// `pos`, or `None` when the quote is unclosed. Backslash escapes the next
/// byte; `''` is a literal quote.
fn skip_single_quoted(data: &[u8], mut pos: usize, end: usize) -> Option<usize> {
    while pos < end {
        let index = memchr::memchr2(b'\'', b'\\', &data[pos..end])?;
        pos += index;
        if data[pos] == b'\\' {
            pos += 2;
            continue;
        }
        if pos + 1 < end && data[pos + 1] == b'\'' {
            pos += 2;
            continue;
        }
        return Some(pos + 1);
    }
    None
}

/// Position after the closing backtick; `` `` `` is a literal backtick.
fn skip_backtick_quoted(data: &[u8], mut pos: usize, end: usize) -> Option<usize> {
    while pos < end {
        let index = memchr::memchr(b'`', &data[pos..end])?;
        pos += index;
        if pos + 1 < end && data[pos + 1] == b'`' {
            pos += 2;
            continue;
        }
        return Some(pos + 1);
    }
    None
}

fn find_block_close(data: &[u8], start: usize, end: usize) -> Option<usize> {
    if start >= end {
        return None;
    }
    memchr::memmem::find(&data[start..end], b"*/").map(|index| start + index)
}

fn inner_is_allowlisted(inner: &[u8]) -> bool {
    let mut index = 0;
    while index < inner.len() && is_ascii_space(inner[index]) {
        index += 1;
    }
    let stripped = &inner[index..];
    ALLOWLIST_INNER_HEADS.iter().any(|head| {
        stripped.len() >= head.len()
            && stripped[..head.len()].eq_ignore_ascii_case(head)
            && (stripped.len() == head.len()
                || !is_ident_continue(stripped[head.len()].to_ascii_lowercase()))
    })
}
