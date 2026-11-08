//! The single MySQL repository replay encoder for structured ChangeSets and
//! canonical storage table locators. No database or backend objects live here.

use crate::comparison::KernelContext;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;

pub const STATEMENT_BYTES: usize = 4 * 1024 * 1024;
pub const STATEMENT_ROWS: usize = 256;
pub const REPLAY_BYTES: usize = 200 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SqlError(pub &'static str);
impl std::fmt::Display for SqlError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.0)
    }
}
impl std::error::Error for SqlError {}
fn invalid() -> SqlError {
    SqlError("TARGET_CAPABILITY_UNSUPPORTED")
}
fn limit() -> SqlError {
    SqlError("RESOURCE_EXCEEDED")
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct NamedCell {
    pub column: String,
    pub value: Value,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SqlMutation {
    pub canonical_table: String,
    pub operation: String,
    pub canonical_storage_key: Vec<NamedCell>,
    pub after_image: Option<Vec<NamedCell>>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SqlColumn {
    pub name: String,
    pub sql_type: String,
    pub nullable: bool,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SqlTable {
    pub name: String,
    pub columns: Vec<SqlColumn>,
    pub primary_key: Vec<String>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SqlSchema {
    pub removed_tables: Vec<String>,
    pub tables: Vec<SqlTable>,
}

pub fn quote_identifier(name: &str) -> Result<String, SqlError> {
    if name.is_empty() || name.chars().any(|c| matches!(c, '\0' | '/' | '\\')) {
        return Err(invalid());
    }
    Ok(format!("`{}`", name.replace('`', "``")))
}
fn identifier_sql_len(name: &str) -> Result<usize, SqlError> {
    if name.is_empty() || name.chars().any(|c| matches!(c, '\0' | '/' | '\\')) {
        return Err(invalid());
    }
    name.len()
        .checked_add(name.bytes().filter(|c| *c == b'`').count())
        .and_then(|size| size.checked_add(2))
        .ok_or_else(limit)
}
fn checked_total(parts: impl IntoIterator<Item = usize>) -> Result<usize, SqlError> {
    parts.into_iter().try_fold(0usize, |sum, size| sum.checked_add(size).ok_or_else(limit))
}
fn schema_table_sql_len(table: &SqlTable) -> Result<usize, SqlError> {
    let name_len = identifier_sql_len(&table.name)?;
    let definition_count = table.columns.len()
        .checked_add(usize::from(!table.primary_key.is_empty())).ok_or_else(limit)?;
    let mut definitions = Vec::with_capacity(definition_count);
    for column in &table.columns {
        if column.sql_type.is_empty() || column.sql_type.contains('\0') { return Err(invalid()); }
        definitions.push(checked_total([
            identifier_sql_len(&column.name)?, 1, column.sql_type.len(), 1,
            if column.nullable { "NULL".len() } else { "NOT NULL".len() },
        ])?);
    }
    if !table.primary_key.is_empty() {
        let keys = table.primary_key.iter().map(|name| identifier_sql_len(name))
            .collect::<Result<Vec<_>, _>>()?;
        definitions.push(checked_total([
            "PRIMARY KEY (".len(), checked_total(keys)?,
            (table.primary_key.len() - 1).checked_mul(2).ok_or_else(limit)?, 1,
        ])?);
    }
    checked_total([
        "DROP TABLE IF EXISTS ".len(), name_len, ";\n".len(),
        "CREATE TABLE ".len(), name_len, " (".len(), checked_total(definitions)?,
        definition_count.saturating_sub(1).checked_mul(2).ok_or_else(limit)?,
        ");\n".len(),
    ])
}
fn quote_text(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    out.push('\'');
    for c in value.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\'' => out.push_str("\\'"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\0' => out.push_str("\\0"),
            '\t' => out.push_str("\\t"),
            _ => out.push(c),
        }
    }
    out.push('\'');
    out
}
fn decode_url64(text: &str) -> Result<Vec<u8>, SqlError> {
    let mut out = Vec::with_capacity(text.len() * 3 / 4 + 2);
    let mut bits: u32 = 0;
    let mut count = 0u8;
    for c in text.bytes() {
        let digit = match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'-' => 62,
            b'_' => 63,
            _ => return Err(invalid()),
        };
        bits = (bits << 6) | u32::from(digit);
        count += 6;
        if count >= 8 {
            count -= 8;
            out.push((bits >> count) as u8);
            bits &= (1 << count) - 1;
        }
    }
    if count == 6 || (count > 0 && bits != 0) {
        return Err(invalid());
    }
    Ok(out)
}
fn decimal(value: &Value, kind: &str) -> Result<&str, SqlError> {
    let text = value.as_str().ok_or_else(invalid)?;
    let body = text.strip_prefix('-').unwrap_or(text);
    let valid = if kind == "decimal" {
        let (integer, fraction) = body.split_once('.').unwrap_or((body, ""));
        !integer.is_empty()
            && integer.bytes().all(|c| c.is_ascii_digit())
            && (fraction.is_empty() || fraction.bytes().all(|c| c.is_ascii_digit()))
            && body.bytes().filter(|c| *c == b'.').count() <= 1
    } else {
        !body.is_empty() && body.bytes().all(|c| c.is_ascii_digit())
    };
    if !valid || (kind == "unsigned-integer" && text.starts_with('-')) {
        return Err(invalid());
    }
    Ok(text)
}
/// Python .15g uses 15 significant decimal places and switches notation at
/// exponent -4/15 after rounding. f64 is used for f32 expansion as in Python.
fn float_text(value: f64) -> Result<String, SqlError> {
    if !value.is_finite() {
        return Err(invalid());
    }
    if value == 0.0 {
        return Ok("0".into());
    }
    let scientific = format!("{value:.14e}");
    let (mantissa, exponent) = scientific.split_once('e').ok_or_else(invalid)?;
    let exponent: i32 = exponent.parse().map_err(|_| invalid())?;
    let digits: String = mantissa.chars().filter(|c| c.is_ascii_digit()).collect();
    let negative = mantissa.starts_with('-');
    let sign = if negative { "-" } else { "" };
    if (-4..15).contains(&exponent) {
        let point = exponent + 1;
        let mut fixed = if point <= 0 {
            format!("0.{}{}", "0".repeat((-point) as usize), digits)
        } else if point as usize >= digits.len() {
            format!("{}{}", digits, "0".repeat(point as usize - digits.len()))
        } else {
            format!(
                "{}.{}",
                &digits[..point as usize],
                &digits[point as usize..]
            )
        };
        if fixed.contains('.') {
            fixed = fixed.trim_end_matches('0').trim_end_matches('.').to_owned();
        }
        Ok(format!("{sign}{fixed}"))
    } else {
        let fraction = digits[1..].trim_end_matches('0');
        let body = if fraction.is_empty() {
            digits[..1].to_owned()
        } else {
            format!("{}.{}", &digits[..1], fraction)
        };
        Ok(format!(
            "{sign}{body}e{}{:02}",
            if exponent < 0 { "-" } else { "+" },
            exponent.abs()
        ))
    }
}
pub fn literal(value: &Value) -> Result<String, SqlError> {
    let kind = value
        .get("kind")
        .and_then(Value::as_str)
        .ok_or_else(invalid)?;
    match kind {
        "null" => Ok("NULL".into()),
        "boolean" => Ok(if value
            .get("value")
            .and_then(Value::as_bool)
            .ok_or_else(invalid)?
        {
            "TRUE"
        } else {
            "FALSE"
        }
        .into()),
        "signed-integer" | "unsigned-integer" | "decimal" => {
            Ok(decimal(value.get("decimal").ok_or_else(invalid)?, kind)?.to_owned())
        }
        "float32" | "float64" => {
            let bits = value
                .get("bits_hex")
                .and_then(Value::as_str)
                .ok_or_else(invalid)?;
            if !bits
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            {
                return Err(invalid());
            }
            let n = if kind == "float32" && bits.len() == 8 {
                f32::from_bits(u32::from_str_radix(bits, 16).map_err(|_| invalid())?) as f64
            } else if kind == "float64" && bits.len() == 16 {
                f64::from_bits(u64::from_str_radix(bits, 16).map_err(|_| invalid())?)
            } else {
                return Err(invalid());
            };
            float_text(n)
        }
        "string" | "date" | "datetime" | "timestamp" | "time-duration" => Ok(quote_text(
            value
                .get("text")
                .and_then(Value::as_str)
                .ok_or_else(invalid)?,
        )),
        "binary" | "bit" => {
            let raw = decode_url64(
                value
                    .get("bytes_base64url")
                    .and_then(Value::as_str)
                    .ok_or_else(invalid)?,
            )?;
            if kind == "binary" {
                let mut out = String::from("X'");
                for byte in raw {
                    out.push_str(&format!("{byte:02X}"));
                }
                out.push('\'');
                Ok(out)
            } else {
                let mut out = String::from("b'");
                for byte in raw {
                    out.push_str(&format!("{byte:08b}"));
                }
                out.push('\'');
                Ok(out)
            }
        }
        _ => Err(invalid()),
    }
}

pub fn render_schema(
    schema: &SqlSchema,
    max_bytes: usize,
    context: &KernelContext,
) -> Result<Vec<u8>, SqlError> {
    let mut out = Vec::new();
    for name in &schema.removed_tables {
        context.check().map_err(|error| SqlError(error.code()))?;
        let next_len = checked_total(["DROP TABLE IF EXISTS ".len(), identifier_sql_len(name)?, ";\n".len()])?;
        if out.len().checked_add(next_len).ok_or_else(limit)? > max_bytes { return Err(limit()); }
        append(
            &mut out,
            format!("DROP TABLE IF EXISTS {};\n", quote_identifier(name)?).as_bytes(),
            max_bytes,
        )?;
    }
    for table in &schema.tables {
        context.check().map_err(|error| SqlError(error.code()))?;
        if out.len().checked_add(schema_table_sql_len(table)?).ok_or_else(limit)? > max_bytes {
            return Err(limit());
        }
        let name = quote_identifier(&table.name)?;
        let mut definitions = Vec::with_capacity(table.columns.len() + 1);
        for col in &table.columns {
            if col.sql_type.is_empty() || col.sql_type.contains('\0') {
                return Err(invalid());
            }
            definitions.push(format!(
                "{} {} {}",
                quote_identifier(&col.name)?,
                col.sql_type,
                if col.nullable { "NULL" } else { "NOT NULL" }
            ));
        }
        if !table.primary_key.is_empty() {
            let keys = table
                .primary_key
                .iter()
                .map(|c| quote_identifier(c))
                .collect::<Result<Vec<_>, _>>()?;
            definitions.push(format!("PRIMARY KEY ({})", keys.join(", ")));
        }
        append(
            &mut out,
            format!(
                "DROP TABLE IF EXISTS {name};\nCREATE TABLE {name} ({});\n",
                definitions.join(", ")
            )
            .as_bytes(),
            max_bytes,
        )?;
    }
    Ok(out)
}
fn append(out: &mut Vec<u8>, bytes: &[u8], cap: usize) -> Result<(), SqlError> {
    if out.len().checked_add(bytes.len()).ok_or_else(limit)? > cap {
        return Err(limit());
    }
    out.extend_from_slice(bytes);
    Ok(())
}

fn key_shape(m: &SqlMutation) -> Vec<&str> {
    m.canonical_storage_key
        .iter()
        .map(|c| c.column.as_str())
        .collect()
}
fn after_shape(m: &SqlMutation) -> Option<Vec<&str>> {
    m.after_image
        .as_ref()
        .map(|a| a.iter().map(|c| c.column.as_str()).collect())
}

struct PreparedRow {
    where_item: String,
    key_predicate: String,
    literals: Vec<String>,
    insert_values: String,
}

/// One running statement. `window_seen` counts original 256-row windows and
/// intentionally survives a byte flush.
pub struct SqlBatcher {
    operation: String,
    table: String,
    key_names: Vec<String>,
    after_names: Vec<String>,
    set_indices: Vec<usize>,
    fixed_len: usize,
    variable_len: usize,
    remaining_cap: usize,
    rows: Vec<PreparedRow>,
    window_seen: usize,
}
impl SqlBatcher {
    pub fn operation(&self) -> &str {
        &self.operation
    }
    pub fn pending_bytes(&self) -> usize {
        self.table.capacity()
            + self.operation.capacity()
            + self.key_names.capacity() * std::mem::size_of::<String>()
            + self.key_names.iter().map(String::capacity).sum::<usize>()
            + self.after_names.capacity() * std::mem::size_of::<String>()
            + self.after_names.iter().map(String::capacity).sum::<usize>()
            + self.set_indices.capacity() * std::mem::size_of::<usize>()
            + (if self.rows.is_empty() {
                0
            } else {
                (self.fixed_len + self.variable_len) * 2
            })
            + self.rows.capacity() * std::mem::size_of::<PreparedRow>()
            + self
                .rows
                .iter()
                .map(|row| {
                    row.where_item.capacity()
                        + row.key_predicate.capacity()
                        + row.insert_values.capacity()
                        + row.literals.capacity() * std::mem::size_of::<String>()
                        + row.literals.iter().map(String::capacity).sum::<usize>()
                })
                .sum::<usize>()
    }
    pub fn new(first: &SqlMutation) -> Result<Self, SqlError> {
        Self::with_cap(first, REPLAY_BYTES)
    }
    pub fn with_cap(first: &SqlMutation, cap: usize) -> Result<Self, SqlError> {
        let table = first.canonical_table.clone();
        let operation = first.operation.clone();
        let key_names = first
            .canonical_storage_key
            .iter()
            .map(|c| c.column.clone())
            .collect::<Vec<_>>();
        let after_names = first
            .after_image
            .as_ref()
            .map_or_else(Vec::new, |a| a.iter().map(|c| c.column.clone()).collect());
        let key_set: HashSet<&str> = key_names.iter().map(String::as_str).collect();
        let set_indices = after_names
            .iter()
            .enumerate()
            .filter_map(|(i, name)| (!key_set.contains(name.as_str())).then_some(i))
            .collect::<Vec<_>>();
        let quoted_table = quote_identifier(&table)?;
        let quoted_keys = key_names
            .iter()
            .map(|name| quote_identifier(name))
            .collect::<Result<Vec<_>, _>>()?;
        let where_prefix = if quoted_keys.len() == 1 {
            quoted_keys[0].clone()
        } else {
            format!("({})", quoted_keys.join(","))
        };
        let fixed_len = match operation.as_str() {
            "DELETE" if !key_names.is_empty() => {
                format!("DELETE FROM {quoted_table} WHERE {where_prefix} IN ();\n").len()
            }
            "UPDATE" if !key_names.is_empty() && !set_indices.is_empty() => {
                let mut fixed = format!("UPDATE {quoted_table} SET ").len()
                    + format!(" WHERE {where_prefix} IN ();\n").len();
                for (position, &index) in set_indices.iter().enumerate() {
                    let q = quote_identifier(&after_names[index])?;
                    fixed +=
                        format!("{q}=CASE  ELSE {q} END").len() + if position > 0 { 2 } else { 0 };
                }
                fixed
            }
            "INSERT" if !after_names.is_empty() => {
                let names = after_names
                    .iter()
                    .map(|name| quote_identifier(name))
                    .collect::<Result<Vec<_>, _>>()?;
                format!(
                    "INSERT INTO {quoted_table} ({}) VALUES ;\n",
                    names.join(", ")
                )
                .len()
            }
            _ => return Err(invalid()),
        };
        Ok(Self {
            operation,
            table,
            key_names,
            after_names,
            set_indices,
            fixed_len,
            variable_len: 0,
            remaining_cap: cap,
            rows: Vec::new(),
            window_seen: 0,
        })
    }
    fn prepare(&self, mutation: &SqlMutation) -> Result<PreparedRow, SqlError> {
        if mutation.canonical_table != self.table
            || mutation.operation != self.operation
            || (self.operation != "INSERT"
                && key_shape(mutation)
                    != self
                        .key_names
                        .iter()
                        .map(String::as_str)
                        .collect::<Vec<_>>())
            || after_shape(mutation)
                != (if self.operation == "DELETE" {
                    None
                } else {
                    Some(self.after_names.iter().map(String::as_str).collect())
                })
        {
            return Err(invalid());
        }
        let key_literals = if self.operation == "INSERT" {
            Vec::new()
        } else {
            mutation
                .canonical_storage_key
                .iter()
                .map(|cell| literal(&cell.value))
                .collect::<Result<Vec<_>, SqlError>>()?
        };
        let key_predicate = if self.operation == "INSERT" {
            String::new()
        } else {
            mutation
                .canonical_storage_key
                .iter()
                .zip(&key_literals)
                .map(|(cell, value)| Ok(format!("{}={value}", quote_identifier(&cell.column)?)))
                .collect::<Result<Vec<_>, SqlError>>()?
                .join(" AND ")
        };
        let where_item = if self.operation == "INSERT" {
            String::new()
        } else if self.key_names.len() == 1 {
            key_literals[0].clone()
        } else if self.key_names.is_empty() {
            String::new()
        } else {
            format!("({})", key_literals.join(", "))
        };
        let literals = mutation
            .after_image
            .as_ref()
            .map_or(Ok(Vec::new()), |cells| {
                cells
                    .iter()
                    .map(|cell| literal(&cell.value))
                    .collect::<Result<Vec<_>, _>>()
            })?;
        let insert_values = if self.operation == "INSERT" {
            format!("({})", literals.join(", "))
        } else {
            String::new()
        };
        Ok(PreparedRow {
            where_item,
            key_predicate,
            literals,
            insert_values,
        })
    }
    fn added_len(&self, row: &PreparedRow) -> Result<usize, SqlError> {
        let separator = if self.rows.is_empty() { 0 } else { 1 };
        let extra = match self.operation.as_str() {
            "DELETE" => row.where_item.len() + separator,
            "UPDATE" => {
                let branches = self
                    .set_indices
                    .iter()
                    .try_fold(0usize, |sum, &index| {
                        sum.checked_add(5 + row.key_predicate.len() + 6 + row.literals[index].len())
                    })
                    .ok_or_else(limit)?;
                row.where_item.len() + branches + separator * (self.set_indices.len() + 1)
            }
            "INSERT" => row.insert_values.len() + separator * 2,
            _ => return Err(invalid()),
        };
        Ok(extra)
    }
    fn emit(&mut self) -> Result<Option<Vec<u8>>, SqlError> {
        if self.rows.is_empty() {
            return Ok(None);
        }
        let complete_len = self
            .fixed_len
            .checked_add(self.variable_len)
            .ok_or_else(limit)?;
        if complete_len > self.remaining_cap {
            return Err(limit());
        }
        self.remaining_cap -= complete_len;
        let rows = std::mem::take(&mut self.rows);
        let table = quote_identifier(&self.table)?;
        let statement = match self.operation.as_str() {
            "DELETE" | "UPDATE" => {
                let names = self
                    .key_names
                    .iter()
                    .map(|name| quote_identifier(name))
                    .collect::<Result<Vec<_>, _>>()?;
                let left = if names.len() == 1 {
                    names[0].clone()
                } else {
                    format!("({})", names.join(","))
                };
                let items = rows
                    .iter()
                    .map(|row| row.where_item.as_str())
                    .collect::<Vec<_>>()
                    .join(",");
                let where_sql = format!("{left} IN ({items})");
                if self.operation == "DELETE" {
                    format!("DELETE FROM {table} WHERE {where_sql};\n")
                } else {
                    let mut assignments = Vec::with_capacity(self.set_indices.len());
                    for &index in &self.set_indices {
                        let q = quote_identifier(&self.after_names[index])?;
                        let branches = rows
                            .iter()
                            .map(|row| {
                                format!("WHEN {} THEN {}", row.key_predicate, row.literals[index])
                            })
                            .collect::<Vec<_>>()
                            .join(" ");
                        assignments.push(format!("{q}=CASE {branches} ELSE {q} END"));
                    }
                    format!(
                        "UPDATE {table} SET {} WHERE {where_sql};\n",
                        assignments.join(", ")
                    )
                }
            }
            "INSERT" => {
                let names = self
                    .after_names
                    .iter()
                    .map(|name| quote_identifier(name))
                    .collect::<Result<Vec<_>, _>>()?;
                let values = rows
                    .iter()
                    .map(|row| row.insert_values.as_str())
                    .collect::<Vec<_>>()
                    .join(", ");
                format!(
                    "INSERT INTO {table} ({}) VALUES {values};\n",
                    names.join(", ")
                )
            }
            _ => return Err(invalid()),
        };
        if statement.len() != self.fixed_len + self.variable_len {
            return Err(invalid());
        }
        self.variable_len = 0;
        Ok(Some(statement.into_bytes()))
    }
    /// Returns one completed statement, if a byte/window boundary was hit.
    /// The caller feeds the same operation and shape until `finish`.
    pub fn push(&mut self, mutation: &SqlMutation) -> Result<Vec<Vec<u8>>, SqlError> {
        let mut emitted = Vec::new();
        if self.operation != "INSERT" && self.window_seen == STATEMENT_ROWS {
            if let Some(value) = self.emit()? {
                emitted.push(value);
            }
            self.window_seen = 0;
        }
        let row = self.prepare(mutation)?;
        let mut added = self.added_len(&row)?;
        if !self.rows.is_empty()
            && self
                .fixed_len
                .checked_add(self.variable_len)
                .and_then(|len| len.checked_add(added))
                .ok_or_else(limit)?
                > STATEMENT_BYTES
        {
            if let Some(value) = self.emit()? {
                emitted.push(value);
            }
            added = self.added_len(&row)?;
        }
        self.variable_len = self.variable_len.checked_add(added).ok_or_else(limit)?;
        if self
            .fixed_len
            .checked_add(self.variable_len)
            .ok_or_else(limit)?
            > REPLAY_BYTES
        {
            return Err(limit());
        }
        self.rows.push(row);
        self.window_seen += 1;
        if (self.operation == "INSERT" && self.rows.len() == STATEMENT_ROWS)
            || (self.operation != "INSERT" && self.window_seen == STATEMENT_ROWS)
        {
            if let Some(value) = self.emit()? {
                emitted.push(value);
            }
            if self.operation != "INSERT" {
                self.window_seen = 0;
            }
        }
        Ok(emitted)
    }
    pub fn finish(&mut self) -> Result<Option<Vec<u8>>, SqlError> {
        self.emit()
    }
}

pub fn render_mutations(
    mutations: &[SqlMutation],
    cap: usize,
    context: &KernelContext,
) -> Result<Vec<u8>, SqlError> {
    let mut out = Vec::new();
    let mut cleared = HashSet::new();
    let mut i = 0;
    while i < mutations.len() {
        context.check().map_err(|error| SqlError(error.code()))?;
        let first = &mutations[i];
        if first.operation == "DELETE" && first.canonical_storage_key.is_empty() {
            let table = &first.canonical_table;
            while i < mutations.len()
                && mutations[i].operation == "DELETE"
                && mutations[i].canonical_table == *table
                && mutations[i].canonical_storage_key.is_empty()
            {
                i += 1;
            }
            if cleared.insert(table.as_str()) {
                append(
                    &mut out,
                    format!("DELETE FROM {};\n", quote_identifier(table)?).as_bytes(),
                    cap,
                )?;
            }
            continue;
        }
        let start = i;
        i += 1;
        while i < mutations.len()
            && mutations[i].canonical_table == first.canonical_table
            && mutations[i].operation == first.operation
            && (first.operation == "INSERT" && after_shape(&mutations[i]) == after_shape(first)
                || first.operation == "DELETE" && key_shape(&mutations[i]) == key_shape(first)
                || first.operation == "UPDATE"
                    && key_shape(&mutations[i]) == key_shape(first)
                    && after_shape(&mutations[i]) == after_shape(first))
        {
            i += 1;
        }
        let mut batcher = SqlBatcher::with_cap(first, cap.saturating_sub(out.len()))?;
        for mutation in &mutations[start..i] {
            for statement in batcher.push(mutation)? {
                append(&mut out, &statement, cap)?;
            }
        }
        if let Some(statement) = batcher.finish()? {
            append(&mut out, &statement, cap)?;
        }
    }
    Ok(out)
}

pub fn render_json_mutations(
    input: &[u8],
    cap: usize,
    context: &KernelContext,
) -> Result<Vec<u8>, SqlError> {
    let values: Vec<SqlMutation> = serde_json::from_slice(input).map_err(|_| invalid())?;
    render_mutations(&values, cap, context)
}
pub fn render_json_schema(
    input: &[u8],
    cap: usize,
    context: &KernelContext,
) -> Result<Vec<u8>, SqlError> {
    let value: SqlSchema = serde_json::from_slice(input).map_err(|_| invalid())?;
    render_schema(&value, cap, context)
}
