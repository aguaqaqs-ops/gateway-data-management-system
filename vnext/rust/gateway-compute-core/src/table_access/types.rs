//! Dump-side SQL type normalization (`_sql_types.map_sql_type`).
//!
//! The reference uses Python regular expressions; this is a hand-written
//! equivalent for the shapes they accept. `\s` and `str.strip()` follow
//! Python's Unicode whitespace; keyword matching is ASCII case-insensitive.

use gateway_shared_kernel::DeclaredType;

use super::cursor::{is_python_space, python_collapse_ws};
use super::errors::ParserDiagnosticCode as Code;

const MAX_ENUM_MEMBERS: usize = 65535;
const MAX_SET_MEMBERS: usize = 64;
const MAX_LABEL_SCALARS: usize = 255;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SqlLogicalType {
    Standard,
    Json,
    Enum,
    Set,
    Unknown,
}

impl SqlLogicalType {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Standard => "standard",
            Self::Json => "json",
            Self::Enum => "enum",
            Self::Set => "set",
            Self::Unknown => "unknown",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct MappedSqlType {
    pub sql_type: String,
    pub logical_type: SqlLogicalType,
    pub declared_type: Option<DeclaredType>,
    pub labels: Option<Vec<String>>,
    pub error: Option<Code>,
}

pub(crate) fn map_sql_type(raw_type: &str, max_enum_set_bytes: usize) -> MappedSqlType {
    if raw_type.is_empty() {
        return unknown("");
    }
    let stripped = strip_charset_collate(raw_type);
    match classify_enum_set(&stripped, max_enum_set_bytes) {
        EnumSet::Malformed => {
            return MappedSqlType {
                sql_type: bounded_unknown_spelling(&stripped),
                logical_type: SqlLogicalType::Unknown,
                declared_type: None,
                labels: None,
                error: Some(Code::SqlTypeMalformed),
            };
        }
        EnumSet::Valid {
            kind,
            labels,
            normalized,
        } => {
            return if kind == "ENUM" {
                MappedSqlType {
                    sql_type: normalized,
                    logical_type: SqlLogicalType::Enum,
                    declared_type: Some(DeclaredType::string()),
                    labels: Some(labels),
                    error: None,
                }
            } else {
                MappedSqlType {
                    sql_type: normalized,
                    logical_type: SqlLogicalType::Set,
                    declared_type: None,
                    labels: Some(labels),
                    error: None,
                }
            };
        }
        EnumSet::Other => {}
    }
    let collapsed = python_collapse_ws(&replace_zerofill(&stripped));
    if collapsed.is_empty() {
        return unknown("");
    }
    if !is_printable_ascii(&collapsed) {
        return MappedSqlType {
            sql_type: bounded_unknown_spelling(&stripped),
            logical_type: SqlLogicalType::Unknown,
            declared_type: None,
            labels: None,
            error: Some(Code::SqlTypeMalformed),
        };
    }
    let mut upper = strip_integer_display(&collapsed.to_ascii_uppercase());
    match upper.as_str() {
        "INTEGER" => upper = "INT".to_string(),
        "INTEGER UNSIGNED" => upper = "INT UNSIGNED".to_string(),
        "BOOL" => upper = "BOOLEAN".to_string(),
        _ => {}
    }
    if let Some(known) = map_known(&upper) {
        return known;
    }
    if is_malformed_known_family(&upper) {
        return MappedSqlType {
            sql_type: upper,
            logical_type: SqlLogicalType::Unknown,
            declared_type: None,
            labels: None,
            error: Some(Code::SqlTypeMalformed),
        };
    }
    unknown(&upper)
}

fn standard(sql_type: impl Into<String>, declared: Option<DeclaredType>) -> Option<MappedSqlType> {
    let declared = declared?;
    Some(MappedSqlType {
        sql_type: sql_type.into(),
        logical_type: SqlLogicalType::Standard,
        declared_type: Some(declared),
        labels: None,
        error: None,
    })
}

fn unknown(sql_type: &str) -> MappedSqlType {
    let spelling = bounded_unknown_spelling(sql_type);
    MappedSqlType {
        sql_type: if spelling.is_empty() {
            "UNKNOWN".to_string()
        } else {
            spelling
        },
        logical_type: SqlLogicalType::Unknown,
        declared_type: None,
        labels: None,
        error: Some(Code::UnknownSqlType),
    }
}

fn bounded_unknown_spelling(sql_type: &str) -> String {
    let collapsed = python_collapse_ws(sql_type);
    if collapsed.is_empty() || !is_printable_ascii(&collapsed) {
        return "UNKNOWN".to_string();
    }
    collapsed.to_ascii_uppercase()
}

fn is_printable_ascii(text: &str) -> bool {
    !text.is_empty() && text.bytes().all(|byte| (0x20..=0x7e).contains(&byte))
}

fn integer_bits(name: &str) -> Option<u8> {
    match name {
        "TINYINT" => Some(8),
        "SMALLINT" => Some(16),
        "MEDIUMINT" => Some(24),
        "INT" => Some(32),
        "BIGINT" => Some(64),
        _ => None,
    }
}

fn is_text_type(name: &str) -> bool {
    matches!(
        name,
        "CHAR" | "VARCHAR" | "TINYTEXT" | "TEXT" | "MEDIUMTEXT" | "LONGTEXT"
    )
}

fn is_blob_type(name: &str) -> bool {
    matches!(
        name,
        "BINARY" | "VARBINARY" | "TINYBLOB" | "BLOB" | "MEDIUMBLOB" | "LONGBLOB"
    )
}

fn is_ascii_digits(text: &str) -> bool {
    !text.is_empty() && text.bytes().all(|byte| byte.is_ascii_digit())
}

/// `NAME(digits)` with the name in `names`; returns `(name, digits)`.
fn sized<'t>(upper: &'t str, names: &[&str]) -> Option<(&'t str, &'t str)> {
    let open = upper.find('(')?;
    let name = &upper[..open];
    if !names.contains(&name) {
        return None;
    }
    let inner = upper[open + 1..].strip_suffix(')')?;
    if !is_ascii_digits(inner) {
        return None;
    }
    Some((name, inner))
}

fn parse_small(digits: &str) -> Option<u32> {
    // Large numbers are out of every allowed range; treat them as invalid.
    digits.parse::<u32>().ok()
}

fn map_known(upper: &str) -> Option<MappedSqlType> {
    if upper == "BOOLEAN" {
        return standard(upper, Some(DeclaredType::boolean()));
    }
    if let Some(bits) = integer_bits(upper) {
        return standard(upper, DeclaredType::signed_integer(bits).ok());
    }
    if let Some(base) = upper.strip_suffix(" UNSIGNED")
        && let Some(bits) = integer_bits(base)
    {
        return standard(upper, DeclaredType::unsigned_integer(bits).ok());
    }
    if let Some(name) = float_display(upper) {
        return if name == "FLOAT" {
            standard("FLOAT", Some(DeclaredType::float32()))
        } else {
            standard("DOUBLE", Some(DeclaredType::float64()))
        };
    }
    if let Some(args) = upper
        .strip_prefix("DECIMAL(")
        .and_then(|rest| rest.strip_suffix(')'))
    {
        let (precision_text, scale_text) = match args.split_once(',') {
            Some((p, s)) => (p, Some(s)),
            None => (args, None),
        };
        if is_ascii_digits(precision_text) && scale_text.is_none_or(is_ascii_digits) {
            let precision = parse_small(precision_text);
            let scale = match scale_text {
                Some(text) => parse_small(text),
                None => Some(0),
            };
            let (Some(precision), Some(scale)) = (precision, scale) else {
                return None;
            };
            if !((1..=65).contains(&precision) && scale <= 30 && scale <= precision) {
                return None;
            }
            let declared = DeclaredType::decimal(precision as u8, scale as u8).ok();
            return standard(format!("DECIMAL({precision},{scale})"), declared);
        }
    }
    if let Some((_, digits)) = sized(upper, &["BIT"]) {
        let width = parse_small(digits)?;
        if !(1..=64).contains(&width) {
            return None;
        }
        return standard(format!("BIT({width})"), DeclaredType::bit(width as u8).ok());
    }
    if upper == "DATE" {
        return standard(upper, Some(DeclaredType::date()));
    }
    if let Some(temporal) = map_temporal(upper) {
        return temporal;
    }
    if is_text_type(upper) || sized(upper, &["CHAR", "VARCHAR"]).is_some() {
        return standard(upper, Some(DeclaredType::string()));
    }
    if is_blob_type(upper) || sized(upper, &["BINARY", "VARBINARY"]).is_some() {
        return standard(upper, Some(DeclaredType::binary()));
    }
    if upper == "JSON" {
        return Some(MappedSqlType {
            sql_type: "JSON".to_string(),
            logical_type: SqlLogicalType::Json,
            declared_type: Some(DeclaredType::string()),
            labels: None,
            error: None,
        });
    }
    None
}

/// `^(FLOAT|DOUBLE)(?:\(\d+(?:\s*,\s*\d+)?\))?$`
fn float_display(upper: &str) -> Option<&'static str> {
    let (name, rest) = if let Some(rest) = upper.strip_prefix("FLOAT") {
        ("FLOAT", rest)
    } else {
        let rest = upper.strip_prefix("DOUBLE")?;
        ("DOUBLE", rest)
    };
    if rest.is_empty() {
        return Some(name);
    }
    let inner = rest.strip_prefix('(')?.strip_suffix(')')?;
    match inner.split_once(',') {
        None => is_ascii_digits(inner).then_some(name),
        Some((left, right)) => {
            let left = left.trim_end_matches(is_python_space);
            let right = right.trim_start_matches(is_python_space);
            (is_ascii_digits(left) && is_ascii_digits(right)).then_some(name)
        }
    }
}

fn map_temporal(upper: &str) -> Option<Option<MappedSqlType>> {
    for kind in ["TIME", "DATETIME", "TIMESTAMP"] {
        if upper == kind {
            return Some(temporal_mapped(kind, None));
        }
    }
    for kind in ["TIME", "DATETIME", "TIMESTAMP"] {
        let Some(rest) = upper.strip_prefix(kind).and_then(|r| r.strip_prefix('(')) else {
            continue;
        };
        let Some(inner) = rest.strip_suffix(')') else {
            continue;
        };
        if !is_ascii_digits(inner) || (inner.len() > 1 && inner.starts_with('0')) {
            return Some(None);
        }
        let fsp = parse_small(inner)?;
        if fsp > 6 {
            return Some(None);
        }
        return Some(temporal_mapped(kind, Some(fsp)));
    }
    None
}

fn temporal_mapped(kind: &str, fsp: Option<u32>) -> Option<MappedSqlType> {
    let sql_type = match fsp {
        None => kind.to_string(),
        Some(fsp) => format!("{kind}({fsp})"),
    };
    let declared = match kind {
        "TIME" => DeclaredType::time_duration(),
        "TIMESTAMP" => DeclaredType::timestamp(),
        _ => DeclaredType::datetime(),
    };
    standard(sql_type, Some(declared))
}

fn is_malformed_known_family(upper: &str) -> bool {
    if upper.starts_with("DECIMAL") || upper.starts_with("BIT(") {
        return true;
    }
    for kind in ["TIME", "DATETIME", "TIMESTAMP"] {
        if let Some(rest) = upper.strip_prefix(kind) {
            match rest.chars().next() {
                None => return true,
                Some('(') => return true,
                Some(ch) if is_python_space(ch) => return true,
                Some(_) => {}
            }
        }
    }
    leading_enum_set(upper).is_some()
}

/// `\w` for Python `str` patterns (approximation: Unicode alphanumerics and `_`).
fn is_word_char(ch: char) -> bool {
    ch.is_alphanumeric() || ch == '_'
}

/// `^(ENUM|SET)\b` with IGNORECASE; returns the upper-cased kind and the rest.
fn leading_enum_set(text: &str) -> Option<(&'static str, &str)> {
    for kind in ["ENUM", "SET"] {
        if text.len() >= kind.len() && text.is_char_boundary(kind.len()) {
            let (head, rest) = text.split_at(kind.len());
            if head.eq_ignore_ascii_case(kind) && !rest.chars().next().is_some_and(is_word_char) {
                return Some((kind, rest));
            }
        }
    }
    None
}

enum EnumSet {
    Other,
    Malformed,
    Valid {
        kind: &'static str,
        labels: Vec<String>,
        normalized: String,
    },
}

fn classify_enum_set(sql_type: &str, max_enum_set_bytes: usize) -> EnumSet {
    let stripped = collapse_ws_outside_quotes(&strip_charset_collate(sql_type));
    let rest = stripped.trim_start_matches(is_python_space);
    let Some((kind, body)) = leading_enum_set(rest) else {
        return EnumSet::Other;
    };
    match parse_enum_set_body(kind, body, max_enum_set_bytes) {
        Some((labels, normalized)) => EnumSet::Valid {
            kind,
            labels,
            normalized,
        },
        None => EnumSet::Malformed,
    }
}

fn skip_space(chars: &[char], mut index: usize) -> usize {
    while index < chars.len() && is_python_space(chars[index]) {
        index += 1;
    }
    index
}

fn parse_sql_string(chars: &[char], mut index: usize) -> Option<(String, usize)> {
    if index >= chars.len() || chars[index] != '\'' {
        return None;
    }
    index += 1;
    let mut out = String::new();
    while index < chars.len() {
        if chars[index] == '\'' {
            if index + 1 < chars.len() && chars[index + 1] == '\'' {
                out.push('\'');
                index += 2;
                continue;
            }
            return Some((out, index + 1));
        }
        out.push(chars[index]);
        index += 1;
    }
    None
}

fn parse_enum_set_body(
    kind: &'static str,
    body: &str,
    max_enum_set_bytes: usize,
) -> Option<(Vec<String>, String)> {
    let chars: Vec<char> = body.chars().collect();
    let mut index = skip_space(&chars, 0);
    if index >= chars.len() || chars[index] != '(' {
        return None;
    }
    index = skip_space(&chars, index + 1);
    if index < chars.len() && chars[index] == ')' {
        return None;
    }
    let mut labels = Vec::new();
    loop {
        let (label, next) = parse_sql_string(&chars, index)?;
        labels.push(label);
        index = skip_space(&chars, next);
        if index >= chars.len() {
            return None;
        }
        if chars[index] == ',' {
            index = skip_space(&chars, index + 1);
            if index < chars.len() && chars[index] == ')' {
                return None;
            }
            continue;
        }
        if chars[index] == ')' {
            index += 1;
            break;
        }
        return None;
    }
    if chars[index..].iter().any(|ch| !is_python_space(*ch)) {
        return None;
    }
    validated_enum_set(kind, labels, max_enum_set_bytes)
}

fn validated_enum_set(
    kind: &'static str,
    labels: Vec<String>,
    max_enum_set_bytes: usize,
) -> Option<(Vec<String>, String)> {
    if kind == "ENUM" {
        if !(1..=MAX_ENUM_MEMBERS).contains(&labels.len()) {
            return None;
        }
        for label in &labels {
            // Empty ENUM labels are allowed, as in the reference.
            if label.chars().count() > MAX_LABEL_SCALARS {
                return None;
            }
        }
    } else {
        if !(1..=MAX_SET_MEMBERS).contains(&labels.len()) {
            return None;
        }
        for label in &labels {
            let length = label.chars().count();
            if !(1..=MAX_LABEL_SCALARS).contains(&length) || label.contains(',') {
                return None;
            }
        }
    }
    let mut seen = std::collections::HashSet::new();
    for label in &labels {
        if !seen.insert(label.as_bytes()) {
            return None;
        }
    }
    let quoted: Vec<String> = labels
        .iter()
        .map(|label| format!("'{}'", label.replace('\'', "''")))
        .collect();
    let normalized = format!("{kind}({})", quoted.join(","));
    if normalized.len() > max_enum_set_bytes {
        return None;
    }
    Some((labels, normalized))
}

/// Split into `(quoted, segment)` pieces on single quotes (`''` doubles).
fn single_quoted_segments(text: &str) -> Vec<(bool, &str)> {
    let bytes = text.as_bytes();
    let mut segments = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'\'' {
            let start = index;
            index += 1;
            let mut closed = false;
            while index < bytes.len() {
                if bytes[index] == b'\'' {
                    if index + 1 < bytes.len() && bytes[index + 1] == b'\'' {
                        index += 2;
                        continue;
                    }
                    index += 1;
                    closed = true;
                    break;
                }
                index += 1;
            }
            if !closed {
                index = bytes.len();
            }
            segments.push((true, &text[start..index]));
            continue;
        }
        let start = index;
        while index < bytes.len() && bytes[index] != b'\'' {
            index += 1;
        }
        segments.push((false, &text[start..index]));
    }
    segments
}

fn strip_charset_collate(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for (quoted, segment) in single_quoted_segments(text) {
        if quoted {
            out.push_str(segment);
        } else {
            let without_charset = remove_modifier(segment, &["CHARACTER", "SET"]);
            out.push_str(&remove_modifier(&without_charset, &["COLLATE"]));
        }
    }
    out
}

fn collapse_ws_outside_quotes(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for (quoted, segment) in single_quoted_segments(text) {
        if quoted {
            out.push_str(segment);
        } else {
            out.push_str(&python_collapse_ws(segment));
        }
    }
    out
}

/// Remove every match of `\s+W1\s+W2...\s+\S+` (IGNORECASE).
fn remove_modifier(segment: &str, words: &[&str]) -> String {
    let chars: Vec<(usize, char)> = segment.char_indices().collect();
    let mut out = String::with_capacity(segment.len());
    let mut index = 0;
    while index < chars.len() {
        if is_python_space(chars[index].1)
            && let Some(end) = match_modifier(&chars, index, words)
        {
            index = end;
            continue;
        }
        out.push(chars[index].1);
        index += 1;
    }
    out
}

fn match_modifier(chars: &[(usize, char)], start: usize, words: &[&str]) -> Option<usize> {
    let mut index = start;
    for word in words {
        let ws_start = index;
        while index < chars.len() && is_python_space(chars[index].1) {
            index += 1;
        }
        if index == ws_start {
            return None;
        }
        for expected in word.chars() {
            if index >= chars.len() || !chars[index].1.eq_ignore_ascii_case(&expected) {
                return None;
            }
            index += 1;
        }
    }
    let ws_start = index;
    while index < chars.len() && is_python_space(chars[index].1) {
        index += 1;
    }
    if index == ws_start {
        return None;
    }
    let value_start = index;
    while index < chars.len() && !is_python_space(chars[index].1) {
        index += 1;
    }
    if index == value_start {
        return None;
    }
    Some(index)
}

/// `re.sub(r"\bZEROFILL\b", " ", text, flags=IGNORECASE)`.
fn replace_zerofill(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let word: Vec<char> = "ZEROFILL".chars().collect();
    let mut out = String::with_capacity(text.len());
    let mut index = 0;
    while index < chars.len() {
        let fits = index + word.len() <= chars.len()
            && chars[index..index + word.len()]
                .iter()
                .zip(&word)
                .all(|(a, b)| a.eq_ignore_ascii_case(b));
        let before_ok = index == 0 || !is_word_char(chars[index - 1]);
        let after_ok =
            index + word.len() >= chars.len() || !is_word_char(chars[index + word.len()]);
        if fits && before_ok && after_ok {
            out.push(' ');
            index += word.len();
            continue;
        }
        out.push(chars[index]);
        index += 1;
    }
    out
}

/// `^(TINYINT|SMALLINT|MEDIUMINT|INT|BIGINT)\(\d+\)(\s+UNSIGNED)?$`
fn strip_integer_display(upper: &str) -> String {
    let Some(open) = upper.find('(') else {
        return upper.to_string();
    };
    let name = &upper[..open];
    if integer_bits(name).is_none() {
        return upper.to_string();
    }
    let rest = &upper[open + 1..];
    let Some(close) = rest.find(')') else {
        return upper.to_string();
    };
    if !is_ascii_digits(&rest[..close]) {
        return upper.to_string();
    }
    let suffix = &rest[close + 1..];
    if suffix.is_empty() {
        return name.to_string();
    }
    let trimmed = suffix.trim_start_matches(is_python_space);
    if trimmed.len() < suffix.len() && trimmed == "UNSIGNED" {
        return format!("{name}{suffix}");
    }
    upper.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mapped(raw: &str) -> (String, SqlLogicalType, Option<DeclaredType>, Option<Code>) {
        let m = map_sql_type(raw, 64 * 1024);
        (m.sql_type, m.logical_type, m.declared_type, m.error)
    }

    /// `(spelling, normalized, logical type, declared type, error code)`.
    type TypeCase = (
        &'static str,
        &'static str,
        SqlLogicalType,
        Option<DeclaredType>,
        Option<Code>,
    );

    #[test]
    fn known_type_table_matches_reference_cases() -> Result<(), String> {
        let s8 = DeclaredType::signed_integer(8).map_err(|e| e.to_string())?;
        let s24 = DeclaredType::signed_integer(24).map_err(|e| e.to_string())?;
        let s32 = DeclaredType::signed_integer(32).map_err(|e| e.to_string())?;
        let s64 = DeclaredType::signed_integer(64).map_err(|e| e.to_string())?;
        let u32t = DeclaredType::unsigned_integer(32).map_err(|e| e.to_string())?;
        let d10_2 = DeclaredType::decimal(10, 2).map_err(|e| e.to_string())?;
        let bit8 = DeclaredType::bit(8).map_err(|e| e.to_string())?;
        let std = SqlLogicalType::Standard;
        let cases: Vec<TypeCase> = vec![
            (
                "BOOLEAN",
                "BOOLEAN",
                std,
                Some(DeclaredType::boolean()),
                None,
            ),
            ("BOOL", "BOOLEAN", std, Some(DeclaredType::boolean()), None),
            ("TINYINT(1)", "TINYINT", std, Some(s8), None),
            ("INT(11)", "INT", std, Some(s32.clone()), None),
            ("INTEGER", "INT", std, Some(s32), None),
            (
                "INT UNSIGNED",
                "INT UNSIGNED",
                std,
                Some(u32t.clone()),
                None,
            ),
            ("int(10) unsigned", "INT UNSIGNED", std, Some(u32t), None),
            ("MEDIUMINT", "MEDIUMINT", std, Some(s24), None),
            ("BIGINT ZEROFILL", "BIGINT", std, Some(s64), None),
            ("DECIMAL(10,2)", "DECIMAL(10,2)", std, Some(d10_2), None),
            ("FLOAT", "FLOAT", std, Some(DeclaredType::float32()), None),
            (
                "double(16,4)",
                "DOUBLE",
                std,
                Some(DeclaredType::float64()),
                None,
            ),
            ("DOUBLE", "DOUBLE", std, Some(DeclaredType::float64()), None),
            ("BIT(8)", "BIT(8)", std, Some(bit8), None),
            ("DATE", "DATE", std, Some(DeclaredType::date()), None),
            (
                "TIME",
                "TIME",
                std,
                Some(DeclaredType::time_duration()),
                None,
            ),
            (
                "DATETIME(6)",
                "DATETIME(6)",
                std,
                Some(DeclaredType::datetime()),
                None,
            ),
            (
                "TIMESTAMP",
                "TIMESTAMP",
                std,
                Some(DeclaredType::timestamp()),
                None,
            ),
            (
                "VARCHAR(16)",
                "VARCHAR(16)",
                std,
                Some(DeclaredType::string()),
                None,
            ),
            (
                "TEXT CHARACTER SET utf8mb4",
                "TEXT",
                std,
                Some(DeclaredType::string()),
                None,
            ),
            (
                "varchar(32) COLLATE utf8mb4_bin",
                "VARCHAR(32)",
                std,
                Some(DeclaredType::string()),
                None,
            ),
            ("BLOB", "BLOB", std, Some(DeclaredType::binary()), None),
            (
                "JSON",
                "JSON",
                SqlLogicalType::Json,
                Some(DeclaredType::string()),
                None,
            ),
            (
                "ENUM('a','b')",
                "ENUM('a','b')",
                SqlLogicalType::Enum,
                Some(DeclaredType::string()),
                None,
            ),
            (
                "enum( 'a' , 'it''s' )",
                "ENUM('a','it''s')",
                SqlLogicalType::Enum,
                Some(DeclaredType::string()),
                None,
            ),
            (
                "SET('x','y')",
                "SET('x','y')",
                SqlLogicalType::Set,
                None,
                None,
            ),
            (
                "YEAR",
                "YEAR",
                SqlLogicalType::Unknown,
                None,
                Some(Code::UnknownSqlType),
            ),
            (
                "ENUM()",
                "ENUM()",
                SqlLogicalType::Unknown,
                None,
                Some(Code::SqlTypeMalformed),
            ),
            (
                "TIME(7)",
                "TIME(7)",
                SqlLogicalType::Unknown,
                None,
                Some(Code::SqlTypeMalformed),
            ),
            (
                "DECIMAL(70,0)",
                "DECIMAL(70,0)",
                SqlLogicalType::Unknown,
                None,
                Some(Code::SqlTypeMalformed),
            ),
            (
                "ENUM('a','a')",
                "ENUM('A','A')",
                SqlLogicalType::Unknown,
                None,
                Some(Code::SqlTypeMalformed),
            ),
            (
                "INTEGER(11)",
                "INTEGER(11)",
                SqlLogicalType::Unknown,
                None,
                Some(Code::UnknownSqlType),
            ),
        ];
        for (raw, sql_type, logical, declared, error) in cases {
            let got = mapped(raw);
            if got != (sql_type.to_string(), logical, declared.clone(), error) {
                return Err(format!("{raw}: got {got:?}"));
            }
        }
        Ok(())
    }
}
