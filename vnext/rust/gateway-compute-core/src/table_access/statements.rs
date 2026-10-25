//! Allowlisted dump statements (`_sql_statements`), minus value conversion.
//!
//! CREATE TABLE is parsed for the column descriptors and the primary key;
//! INSERT up to `VALUES` (the tuples are parsed later, in parallel); session
//! boilerplate (SET, LOCK/UNLOCK TABLES, DROP TABLE IF EXISTS, ALTER TABLE
//! ... DISABLE/ENABLE KEYS) is checked against the reference allowlist.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use super::ParserBudgets;
use super::cursor::{Cursor, python_strip};
use super::errors::{Fault, PResult, ParserDiagnostic, ParserDiagnosticCode as Code};
use super::literal::{LexError, parse_literal};
use super::model::{ColumnDescriptor, SqlLogicalType};
use super::types::map_sql_type;

const CONSTRAINT_HEADS: [&[u8]; 9] = [
    b"primary",
    b"key",
    b"index",
    b"unique",
    b"foreign",
    b"check",
    b"constraint",
    b"fulltext",
    b"spatial",
];

const ALLOWED_SET_NAMES: [&str; 9] = [
    "names",
    "time_zone",
    "unique_checks",
    "foreign_key_checks",
    "sql_mode",
    "sql_notes",
    "collation_connection",
    "collation_database",
    "collation_server",
];

const TABLE_OPTIONS: [&[u8]; 27] = [
    b"engine",
    b"charset",
    b"collate",
    b"auto_increment",
    b"comment",
    b"row_format",
    b"stats_persistent",
    b"checksum",
    b"delay_key_write",
    b"key_block_size",
    b"max_rows",
    b"min_rows",
    b"avg_row_length",
    b"pack_keys",
    b"default",
    b"character",
    b"data",
    b"index",
    b"tablespace",
    b"compression",
    b"encryption",
    b"union",
    b"insert_method",
    b"connection",
    b"password",
    b"stats_auto_recalc",
    b"stats_sample_pages",
];

const STATEMENT_KEYWORDS: [&str; 21] = [
    "create",
    "insert",
    "replace",
    "drop",
    "set",
    "lock",
    "unlock",
    "alter",
    "use",
    "delimiter",
    "update",
    "delete",
    "truncate",
    "rename",
    "call",
    "start",
    "begin",
    "commit",
    "rollback",
    "savepoint",
    "trigger",
];

#[derive(Debug)]
pub(crate) struct TableBuild {
    pub display_name: String,
    pub canonical_name: String,
    pub columns: Vec<ColumnDescriptor>,
    pub pk: Vec<String>,
    pub create_offset: usize,
    /// Offset of the first event that invalidated the table.
    pub failed_at: Option<usize>,
    pub unknown: bool,
    pub diagnostics: Vec<ParserDiagnostic>,
}

impl TableBuild {
    fn fail(&mut self, fault: Fault, column: Option<String>) {
        if self.failed_at.is_none_or(|at| fault.offset < at) {
            self.failed_at = Some(fault.offset);
        }
        self.diagnostics
            .push(fault.into_diagnostic(Some(self.display_name.clone()), column));
    }
}

/// An INSERT whose tuples are parsed in phase B.
#[derive(Debug, Clone)]
pub(crate) struct InsertJob {
    pub table: usize,
    pub ordinals: Arc<[usize]>,
    /// First byte after the `VALUES` keyword.
    pub values_start: usize,
    pub end: usize,
    pub splits: Vec<usize>,
}

pub(crate) struct Catalog {
    pub tables: Vec<TableBuild>,
    pub index: HashMap<String, usize>,
    /// A document failure the reference records but does not stop on (see
    /// `skip_table_options`): every table then stays not ready.
    pub soft_failure: Option<Fault>,
}

impl Catalog {
    pub fn new() -> Self {
        Self {
            tables: Vec::new(),
            index: HashMap::new(),
            soft_failure: None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum StatementKind {
    Empty,
    Create,
    Insert,
    Other(&'static str),
    Unknown,
}

pub(crate) fn classify_statement(cursor: &mut Cursor<'_>) -> PResult<StatementKind> {
    let saved = cursor.pos;
    cursor.skip_ws_and_comments()?;
    if cursor.at_end() {
        return Ok(StatementKind::Empty);
    }
    for keyword in STATEMENT_KEYWORDS {
        cursor.pos = saved;
        if cursor.try_keyword(keyword.as_bytes())? {
            cursor.pos = saved;
            return Ok(match keyword {
                "create" => StatementKind::Create,
                "insert" => StatementKind::Insert,
                other => StatementKind::Other(other),
            });
        }
    }
    cursor.pos = saved;
    Ok(StatementKind::Unknown)
}

pub(crate) fn parse_create_table(
    cursor: &mut Cursor<'_>,
    catalog: &mut Catalog,
    budgets: &ParserBudgets,
) -> PResult<()> {
    let offset = cursor.pos;
    let max_ident = budgets.max_identifier_code_points;
    if !cursor.try_keyword(b"create")? {
        return Err(Fault::malformed(offset, "expected CREATE TABLE"));
    }
    if !cursor.try_keyword(b"table")? {
        return Err(Fault::unsupported(
            offset,
            "CREATE statement is not in the source dump allowlist",
        ));
    }
    let saved = cursor.pos;
    if !(cursor.try_keyword(b"if")?
        && cursor.try_keyword(b"not")?
        && cursor.try_keyword(b"exists")?)
    {
        cursor.pos = saved;
    }
    let (display, canonical) = cursor.parse_table_name(max_ident)?;
    if let Some(&existing) = catalog.index.get(&canonical) {
        let table = &mut catalog.tables[existing];
        let code = if table.display_name == display {
            Code::DuplicateTable
        } else {
            Code::CanonicalIdentifierCollision
        };
        table.fail(
            Fault::new(code, offset, format!("duplicate table {display}")),
            None,
        );
        skip_create_remainder(cursor, catalog, max_ident)?;
        return Ok(());
    }
    if catalog.tables.len() >= budgets.max_tables_per_source {
        return Err(Fault::resource("max_tables_per_source", offset));
    }
    let mut table = TableBuild {
        display_name: display,
        canonical_name: canonical.clone(),
        columns: Vec::new(),
        pk: Vec::new(),
        create_offset: offset,
        failed_at: None,
        unknown: false,
        diagnostics: Vec::new(),
    };
    let (body_start, body_end) = cursor.take_balanced_paren()?;
    parse_table_items(
        cursor.data,
        body_start + 1,
        body_end - 1,
        &mut table,
        budgets,
    )?;
    skip_table_options(cursor, catalog, max_ident)?;
    cursor.skip_ws_and_comments()?;
    if !cursor.at_end() {
        return Err(Fault::malformed(
            cursor.pos,
            "unexpected tokens after CREATE TABLE",
        ));
    }
    catalog.index.insert(canonical, catalog.tables.len());
    catalog.tables.push(table);
    Ok(())
}

/// Parses `INSERT INTO t [(cols)] VALUES` and returns the job for its tuples.
pub(crate) fn parse_insert_header(
    cursor: &mut Cursor<'_>,
    catalog: &mut Catalog,
    budgets: &ParserBudgets,
    splits: &[usize],
) -> PResult<InsertJob> {
    let offset = cursor.pos;
    let max_ident = budgets.max_identifier_code_points;
    if !cursor.try_keyword(b"insert")? {
        return Err(Fault::malformed(offset, "expected INSERT"));
    }
    if cursor.try_keyword(b"ignore")? {
        return Err(Fault::unsupported(
            offset,
            "INSERT IGNORE is not in the source dump allowlist",
        ));
    }
    if !cursor.try_keyword(b"into")? {
        return Err(Fault::malformed(offset, "expected INSERT INTO"));
    }
    let (_display, canonical) = cursor.parse_table_name(max_ident)?;
    let Some(&table_index) = catalog.index.get(&canonical) else {
        return Err(Fault::malformed(offset, "INSERT targets an unknown table"));
    };
    cursor.skip_ws_and_comments()?;
    if cursor.try_keyword(b"set")? {
        return Err(Fault::unsupported(
            offset,
            "INSERT ... SET is not in the source dump allowlist",
        ));
    }
    if cursor.try_keyword(b"select")? {
        return Err(Fault::unsupported(
            offset,
            "INSERT ... SELECT is not in the source dump allowlist",
        ));
    }
    let table = &mut catalog.tables[table_index];
    let ordinals: Vec<usize> = if cursor.peek() == Some(b'(') {
        parse_insert_columns(cursor, table, max_ident)?
    } else {
        (0..table.columns.len()).collect()
    };
    if !cursor.try_keyword(b"values")? {
        let code = if cursor.try_keyword(b"select")? {
            Code::IncompleteInsert
        } else {
            Code::MalformedSql
        };
        return Err(Fault::new(
            code,
            cursor.pos,
            "INSERT must use VALUES with complete columns",
        ));
    }
    let values_start = cursor.pos;
    Ok(InsertJob {
        table: table_index,
        ordinals: ordinals.into(),
        values_start,
        end: cursor.end,
        splits: splits
            .iter()
            .copied()
            .filter(|split| *split > values_start)
            .collect(),
    })
}

fn parse_insert_columns(
    cursor: &mut Cursor<'_>,
    table: &mut TableBuild,
    max_ident: usize,
) -> PResult<Vec<usize>> {
    let (start, end) = cursor.take_balanced_paren()?;
    let mut inner = Cursor::new(cursor.data, start + 1, end - 1);
    let mut ordinals = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    let index_by_name: HashMap<&str, usize> = table
        .columns
        .iter()
        .map(|column| (column.canonical_name.as_str(), column.ordinal))
        .collect();
    let mut pending: Vec<(Fault, Option<String>)> = Vec::new();
    loop {
        inner.skip_ws_and_comments()?;
        if inner.at_end() {
            break;
        }
        let (display, canonical) = inner.parse_identifier(max_ident)?;
        if seen.contains(&canonical) {
            pending.push((
                Fault::new(
                    Code::DuplicateColumn,
                    inner.pos,
                    format!("duplicate column {display}"),
                ),
                Some(display.clone()),
            ));
        }
        match index_by_name.get(canonical.as_str()) {
            Some(ordinal) => ordinals.push(*ordinal),
            None => {
                pending.push((
                    Fault::new(
                        Code::RowShapeMismatch,
                        inner.pos,
                        format!("INSERT column {display} is not in the table"),
                    ),
                    Some(display.clone()),
                ));
                ordinals.push(0);
            }
        }
        seen.insert(canonical);
        inner.skip_ws_and_comments()?;
        if inner.peek() == Some(b',') {
            inner.pos += 1;
            continue;
        }
        if inner.at_end() {
            break;
        }
        return Err(Fault::malformed(inner.pos, "malformed INSERT column list"));
    }
    let expected: HashSet<String> = table
        .columns
        .iter()
        .map(|c| c.canonical_name.clone())
        .collect();
    if seen != expected {
        pending.push((
            Fault::new(
                Code::IncompleteInsert,
                start,
                "INSERT column list must include every column",
            ),
            None,
        ));
    }
    for (fault, column) in pending {
        table.fail(fault, column);
    }
    Ok(ordinals)
}

pub(crate) fn parse_boilerplate(
    kind: StatementKind,
    cursor: &mut Cursor<'_>,
    budgets: &ParserBudgets,
) -> PResult<()> {
    let offset = cursor.pos;
    let max_ident = budgets.max_identifier_code_points;
    let name = match kind {
        StatementKind::Other(name) => name,
        _ => "unknown",
    };
    match name {
        "replace" => Err(Fault::unsupported(
            offset,
            "REPLACE is not in the source dump allowlist",
        )),
        "drop" => parse_drop_table(cursor, max_ident),
        "set" => parse_set(cursor, max_ident),
        "lock" => parse_lock(cursor, max_ident),
        "unlock" => {
            if !cursor.try_keyword(b"unlock")? || !cursor.try_keyword(b"tables")? {
                return Err(Fault::malformed(offset, "expected UNLOCK TABLES"));
            }
            expect_end(cursor)
        }
        "alter" => parse_alter_keys(cursor, max_ident),
        other => Err(Fault::unsupported(
            offset,
            format!(
                "{} is not in the source dump allowlist",
                other.to_ascii_uppercase()
            ),
        )),
    }
}

fn parse_table_items(
    data: &[u8],
    start: usize,
    end: usize,
    table: &mut TableBuild,
    budgets: &ParserBudgets,
) -> PResult<()> {
    for (item_start, item_end) in split_top_level(data, start, end) {
        let mut item = Cursor::new(data, item_start, item_end);
        item.skip_ws_and_comments()?;
        if item.at_end() {
            return Err(Fault::malformed(item_start, "empty table item"));
        }
        if is_constraint_item(&mut item)? {
            parse_constraint(&mut item, table, budgets.max_identifier_code_points)?;
        } else {
            parse_column(&mut item, table, budgets)?;
        }
        item.skip_ws_and_comments()?;
        if !item.at_end() {
            return Err(Fault::malformed(
                item.pos,
                "unexpected tokens in table item",
            ));
        }
    }
    Ok(())
}

fn parse_column(
    cursor: &mut Cursor<'_>,
    table: &mut TableBuild,
    budgets: &ParserBudgets,
) -> PResult<()> {
    let offset = cursor.pos;
    let (display, canonical) = cursor.parse_identifier(budgets.max_identifier_code_points)?;
    if let Some(existing) = table.columns.iter().find(|c| c.canonical_name == canonical) {
        let code = if existing.display_name == display {
            Code::DuplicateColumn
        } else {
            Code::CanonicalIdentifierCollision
        };
        table.fail(
            Fault::new(code, offset, format!("duplicate column {display}")),
            Some(display),
        );
        skip_column_remainder(cursor)?;
        return Ok(());
    }
    if table.columns.len() >= budgets.max_columns_per_table {
        return Err(Fault::resource("max_columns_per_table", offset));
    }
    let type_sql = parse_column_type(cursor, budgets.max_identifier_code_points)?;
    let mapped = map_sql_type(&type_sql, budgets.max_enum_set_sql_type_bytes);
    let mut nullable = true;
    let mut inline_pk = false;
    while !cursor.at_end() {
        cursor.skip_ws_and_comments()?;
        if cursor.at_end() {
            break;
        }
        let attr_offset = cursor.pos;
        if cursor.try_keyword(b"generated")? {
            return Err(Fault::unsupported(
                attr_offset,
                "GENERATED columns are not in the source dump allowlist",
            ));
        }
        if cursor.try_keyword(b"virtual")? || cursor.try_keyword(b"stored")? {
            return Err(Fault::unsupported(
                attr_offset,
                "GENERATED columns are not in the source dump allowlist",
            ));
        }
        if cursor.try_keyword(b"not")? {
            if !cursor.try_keyword(b"null")? {
                return Err(Fault::malformed(attr_offset, "expected NOT NULL"));
            }
            nullable = false;
            continue;
        }
        if cursor.try_keyword(b"null")? {
            nullable = true;
            continue;
        }
        if cursor.try_keyword(b"default")? {
            skip_default(cursor, budgets.max_identifier_code_points)?;
            continue;
        }
        if cursor.try_keyword(b"on")? {
            if !cursor.try_keyword(b"update")? {
                return Err(Fault::malformed(attr_offset, "expected ON UPDATE"));
            }
            skip_default(cursor, budgets.max_identifier_code_points)?;
            continue;
        }
        if cursor.try_keyword(b"auto_increment")? {
            continue;
        }
        if cursor.try_keyword(b"comment")? {
            skip_default(cursor, budgets.max_identifier_code_points)?;
            continue;
        }
        if cursor.try_keyword(b"primary")? {
            if !cursor.try_keyword(b"key")? {
                return Err(Fault::malformed(attr_offset, "expected PRIMARY KEY"));
            }
            inline_pk = true;
            nullable = false;
            continue;
        }
        if cursor.try_keyword(b"unique")? {
            cursor.try_keyword(b"key")?;
            continue;
        }
        if cursor.try_keyword(b"references")? {
            skip_column_remainder(cursor)?;
            break;
        }
        if cursor.try_keyword(b"constraint")? {
            return Err(Fault::malformed(
                attr_offset,
                "unexpected CONSTRAINT on column",
            ));
        }
        break;
    }
    let column = ColumnDescriptor {
        display_name: display.clone(),
        canonical_name: canonical.clone(),
        ordinal: table.columns.len(),
        sql_type: mapped.sql_type.clone(),
        logical_type: mapped.logical_type,
        declared_type: mapped.declared_type.clone(),
        nullable,
        labels: mapped.labels.clone(),
    };
    table.columns.push(column);
    if let Some(code) = mapped.error {
        table.fail(
            Fault::new(code, offset, format!("column type {}", mapped.sql_type)),
            Some(display),
        );
        if mapped.logical_type == SqlLogicalType::Unknown {
            table.unknown = true;
        }
    }
    if inline_pk {
        add_pk(table, vec![canonical], offset);
    }
    Ok(())
}

fn parse_column_type(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<String> {
    cursor.skip_ws_and_comments()?;
    let start = cursor.pos;
    if cursor.at_end() {
        return Err(Fault::malformed(start, "expected column type"));
    }
    // Type name (an identifier), optionally `DOUBLE PRECISION` / `CHAR VARYING`.
    cursor.parse_identifier(max_ident)?;
    cursor.skip_ws_and_comments()?;
    let saved = cursor.pos;
    if !cursor.try_keyword(b"precision")? {
        cursor.pos = saved;
        cursor.try_keyword(b"varying")?;
    }
    cursor.skip_ws_and_comments()?;
    if cursor.peek() == Some(b'(') {
        cursor.take_balanced_paren()?;
    }
    loop {
        cursor.skip_ws_and_comments()?;
        let saved = cursor.pos;
        if cursor.try_keyword(b"unsigned")? || cursor.try_keyword(b"zerofill")? {
            continue;
        }
        if cursor.try_keyword(b"character")? {
            if !cursor.try_keyword(b"set")? {
                cursor.pos = saved;
                break;
            }
            skip_name_or_string(cursor, max_ident)?;
            continue;
        }
        if cursor.try_keyword(b"collate")? {
            skip_name_or_string(cursor, max_ident)?;
            continue;
        }
        cursor.pos = saved;
        break;
    }
    let raw = &cursor.data[start..cursor.pos];
    let text = std::str::from_utf8(raw)
        .map_err(|_| Fault::malformed(start, "column type is not UTF-8"))?;
    Ok(python_strip(text).to_string())
}

fn is_constraint_item(cursor: &mut Cursor<'_>) -> PResult<bool> {
    let saved = cursor.pos;
    for head in CONSTRAINT_HEADS {
        cursor.pos = saved;
        if cursor.try_keyword(head)? {
            cursor.pos = saved;
            return Ok(true);
        }
    }
    cursor.pos = saved;
    Ok(false)
}

fn parse_constraint(
    cursor: &mut Cursor<'_>,
    table: &mut TableBuild,
    max_ident: usize,
) -> PResult<()> {
    let offset = cursor.pos;
    if cursor.try_keyword(b"constraint")? {
        let saved = cursor.pos;
        let named_kind = cursor.try_keyword(b"primary")?
            || cursor.try_keyword(b"unique")?
            || cursor.try_keyword(b"foreign")?
            || cursor.try_keyword(b"check")?;
        if named_kind {
            cursor.pos = saved;
        } else {
            cursor.parse_identifier(max_ident)?;
        }
    }
    if cursor.try_keyword(b"primary")? {
        if !cursor.try_keyword(b"key")? {
            return Err(Fault::malformed(offset, "expected PRIMARY KEY"));
        }
        let names = parse_index_columns(cursor, max_ident)?;
        add_pk(table, names, offset);
        return Ok(());
    }
    let skipped = cursor.try_keyword(b"unique")?
        || cursor.try_keyword(b"key")?
        || cursor.try_keyword(b"index")?
        || cursor.try_keyword(b"fulltext")?
        || cursor.try_keyword(b"spatial")?
        || cursor.try_keyword(b"foreign")?
        || cursor.try_keyword(b"check")?;
    if skipped {
        skip_column_remainder(cursor)?;
        return Ok(());
    }
    Err(Fault::malformed(offset, "unsupported table constraint"))
}

fn parse_index_columns(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<Vec<String>> {
    let (start, end) = cursor.take_balanced_paren()?;
    let mut inner = Cursor::new(cursor.data, start + 1, end - 1);
    let mut names = Vec::new();
    loop {
        inner.skip_ws_and_comments()?;
        if inner.at_end() {
            break;
        }
        let (_display, canonical) = inner.parse_identifier(max_ident)?;
        names.push(canonical);
        inner.skip_ws_and_comments()?;
        if inner.peek() == Some(b'(') {
            inner.take_balanced_paren()?;
        }
        inner.skip_ws_and_comments()?;
        if inner.peek() == Some(b',') {
            inner.pos += 1;
            continue;
        }
        if inner.at_end() {
            break;
        }
        return Err(Fault::malformed(inner.pos, "malformed key column list"));
    }
    if names.is_empty() {
        return Err(Fault::malformed(start, "primary key requires columns"));
    }
    Ok(names)
}

fn add_pk(table: &mut TableBuild, names: Vec<String>, offset: usize) {
    if !table.pk.is_empty() {
        table.fail(
            Fault::new(Code::DuplicatePrimaryKey, offset, "duplicate primary key"),
            None,
        );
        return;
    }
    let mut seen: HashSet<&str> = HashSet::new();
    let columns: HashSet<&str> = table
        .columns
        .iter()
        .map(|c| c.canonical_name.as_str())
        .collect();
    let mut failure: Option<(Fault, String)> = None;
    for name in &names {
        if !seen.insert(name.as_str()) {
            failure = Some((
                Fault::new(
                    Code::DuplicatePrimaryKey,
                    offset,
                    "duplicate primary key column",
                ),
                name.clone(),
            ));
            break;
        }
        if !columns.contains(name.as_str()) {
            failure = Some((
                Fault::malformed(offset, "primary key must reference a column"),
                name.clone(),
            ));
            break;
        }
    }
    match failure {
        Some((fault, column)) => table.fail(fault, Some(column)),
        None => table.pk = names,
    }
}

fn parse_drop_table(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<()> {
    let offset = cursor.pos;
    if !cursor.try_keyword(b"drop")? || !cursor.try_keyword(b"table")? {
        return Err(Fault::malformed(offset, "expected DROP TABLE"));
    }
    if !cursor.try_keyword(b"if")? || !cursor.try_keyword(b"exists")? {
        return Err(Fault::unsupported(
            offset,
            "DROP TABLE without IF EXISTS is not in the source dump allowlist",
        ));
    }
    cursor.parse_table_name(max_ident)?;
    loop {
        cursor.skip_ws_and_comments()?;
        if cursor.peek() == Some(b',') {
            cursor.pos += 1;
            cursor.parse_table_name(max_ident)?;
            continue;
        }
        break;
    }
    expect_end(cursor)
}

fn parse_set(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<()> {
    let offset = cursor.pos;
    if !cursor.try_keyword(b"set")? {
        return Err(Fault::malformed(offset, "expected SET"));
    }
    cursor.skip_ws_and_comments()?;
    if cursor.try_keyword(b"names")? {
        skip_set_rhs(cursor, max_ident)?;
        while cursor.peek() == Some(b',') {
            cursor.pos += 1;
            parse_one_set_assignment(cursor, max_ident)?;
        }
        return expect_end(cursor);
    }
    parse_one_set_assignment(cursor, max_ident)?;
    loop {
        cursor.skip_ws_and_comments()?;
        if cursor.peek() == Some(b',') {
            cursor.pos += 1;
            parse_one_set_assignment(cursor, max_ident)?;
            continue;
        }
        break;
    }
    expect_end(cursor)
}

fn parse_one_set_assignment(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<()> {
    let offset = cursor.pos;
    let name = parse_set_lhs(cursor, max_ident)?;
    if !allowed_set_name(&name) {
        return Err(Fault::unsupported(
            offset,
            format!("SET {name} is not in the source dump allowlist"),
        ));
    }
    cursor.skip_ws_and_comments()?;
    if cursor.peek() != Some(b'=') {
        return Err(Fault::malformed(cursor.pos, "expected '=' in SET"));
    }
    cursor.pos += 1;
    skip_set_rhs(cursor, max_ident)
}

fn parse_set_lhs(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<String> {
    cursor.skip_ws_and_comments()?;
    let start = cursor.pos;
    if cursor.peek() == Some(b'@') {
        cursor.pos += 1;
        if cursor.peek() == Some(b'@') {
            cursor.pos += 1;
        }
    }
    let (_display, canonical) = cursor.parse_identifier(max_ident)?;
    // `decode("ascii", "ignore")` of the raw spelling.
    let prefix: String = cursor.data[start..cursor.pos]
        .iter()
        .filter(|b| b.is_ascii())
        .map(|b| char::from(*b))
        .collect();
    if prefix.starts_with('@') {
        return Ok(prefix);
    }
    Ok(canonical)
}

fn allowed_set_name(name: &str) -> bool {
    let lowered_full = name.to_lowercase();
    if lowered_full == "@saved_cs_client" {
        return true;
    }
    let lowered = lowered_full.trim_start_matches('@');
    lowered.starts_with("old_")
        || lowered.starts_with("character_set_")
        || lowered.starts_with("collation_")
        || ALLOWED_SET_NAMES.contains(&lowered)
}

fn skip_set_rhs(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<()> {
    cursor.skip_ws_and_comments()?;
    let saved = cursor.pos;
    match parse_literal(cursor) {
        Ok(_) => return Ok(()),
        Err(LexError::Halt(fault)) => return Err(fault),
        Err(LexError::Literal(_)) => cursor.pos = saved,
    }
    if cursor.peek() == Some(b'@') {
        cursor.pos += 1;
        if cursor.peek() == Some(b'@') {
            cursor.pos += 1;
        }
        cursor.parse_identifier(max_ident)?;
        return Ok(());
    }
    if cursor.peek().is_some() {
        cursor.parse_identifier(max_ident)?;
        cursor.skip_ws_and_comments()?;
        if cursor.peek() == Some(b'(') {
            cursor.take_balanced_paren()?;
        }
        return Ok(());
    }
    Err(Fault::malformed(cursor.pos, "expected SET value"))
}

fn parse_lock(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<()> {
    let offset = cursor.pos;
    if !cursor.try_keyword(b"lock")? || !cursor.try_keyword(b"tables")? {
        return Err(Fault::malformed(offset, "expected LOCK TABLES"));
    }
    loop {
        cursor.parse_table_name(max_ident)?;
        cursor.skip_ws_and_comments()?;
        if cursor.try_keyword(b"as")? {
            cursor.parse_identifier(max_ident)?;
        }
        if !cursor.try_keyword(b"read")? {
            cursor.try_keyword(b"write")?;
        }
        cursor.try_keyword(b"local")?;
        cursor.skip_ws_and_comments()?;
        if cursor.peek() == Some(b',') {
            cursor.pos += 1;
            continue;
        }
        break;
    }
    expect_end(cursor)
}

fn parse_alter_keys(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<()> {
    let offset = cursor.pos;
    if !cursor.try_keyword(b"alter")? || !cursor.try_keyword(b"table")? {
        return Err(Fault::malformed(offset, "expected ALTER TABLE"));
    }
    cursor.parse_table_name(max_ident)?;
    if (cursor.try_keyword(b"disable")? || cursor.try_keyword(b"enable")?)
        && cursor.try_keyword(b"keys")?
    {
        return expect_end(cursor);
    }
    Err(Fault::unsupported(
        offset,
        "ALTER TABLE statement is not in the source dump allowlist",
    ))
}

fn skip_table_options(
    cursor: &mut Cursor<'_>,
    catalog: &mut Catalog,
    max_ident: usize,
) -> PResult<()> {
    while !cursor.at_end() {
        cursor.skip_ws_and_comments()?;
        if cursor.at_end() || cursor.peek() == Some(b';') {
            return Ok(());
        }
        let saved = cursor.pos;
        let mut matched = false;
        for option in TABLE_OPTIONS {
            cursor.pos = saved;
            if cursor.try_keyword(option)? {
                matched = true;
                break;
            }
        }
        if !matched {
            cursor.pos = saved;
            return Ok(());
        }
        cursor.skip_ws_and_comments()?;
        if cursor.peek() == Some(b'=') {
            cursor.pos += 1;
            skip_set_rhs(cursor, max_ident)?;
        } else if cursor.try_keyword(b"character")? {
            cursor.try_keyword(b"set")?;
            cursor.skip_ws_and_comments()?;
            if cursor.peek() == Some(b'=') {
                cursor.pos += 1;
            }
            skip_name_or_string(cursor, max_ident)?;
        } else if cursor.try_keyword(b"set")? || cursor.try_keyword(b"charset")? {
            cursor.skip_ws_and_comments()?;
            if cursor.peek() == Some(b'=') {
                cursor.pos += 1;
            }
            skip_name_or_string(cursor, max_ident)?;
        } else {
            let saved_rhs = cursor.pos;
            if let Err(fault) = skip_name_or_string(cursor, max_ident) {
                // The reference catches ParserHalt here after fail_document
                // already marked the document failed.
                if catalog.soft_failure.is_none() {
                    catalog.soft_failure = Some(fault);
                }
                cursor.pos = saved_rhs;
            }
        }
    }
    Ok(())
}

fn skip_name_or_string(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<()> {
    cursor.skip_ws_and_comments()?;
    let saved = cursor.pos;
    match parse_literal(cursor) {
        Ok(_) => return Ok(()),
        Err(LexError::Halt(fault)) => return Err(fault),
        Err(LexError::Literal(_)) => cursor.pos = saved,
    }
    cursor.parse_identifier(max_ident)?;
    Ok(())
}

fn skip_default(cursor: &mut Cursor<'_>, max_ident: usize) -> PResult<()> {
    cursor.skip_ws_and_comments()?;
    let saved = cursor.pos;
    match parse_literal(cursor) {
        Ok(_) => return Ok(()),
        Err(LexError::Halt(fault)) => return Err(fault),
        Err(LexError::Literal(_)) => cursor.pos = saved,
    }
    if cursor.peek() == Some(b'(') {
        cursor.take_balanced_paren()?;
        return Ok(());
    }
    cursor.parse_identifier(max_ident)?;
    cursor.skip_ws_and_comments()?;
    if cursor.peek() == Some(b'(') {
        cursor.take_balanced_paren()?;
    }
    Ok(())
}

fn skip_column_remainder(cursor: &mut Cursor<'_>) -> PResult<()> {
    while !cursor.at_end() {
        if cursor.peek() == Some(b'(') {
            cursor.take_balanced_paren()?;
            continue;
        }
        cursor.pos += 1;
    }
    Ok(())
}

fn skip_create_remainder(
    cursor: &mut Cursor<'_>,
    catalog: &mut Catalog,
    max_ident: usize,
) -> PResult<()> {
    cursor.skip_ws_and_comments()?;
    if cursor.peek() == Some(b'(') {
        cursor.take_balanced_paren()?;
    }
    skip_table_options(cursor, catalog, max_ident)
}

pub(crate) fn expect_end(cursor: &mut Cursor<'_>) -> PResult<()> {
    cursor.skip_ws_and_comments()?;
    if !cursor.at_end() {
        return Err(Fault::malformed(
            cursor.pos,
            "unexpected tokens after statement",
        ));
    }
    Ok(())
}

/// Top-level comma split of a CREATE TABLE body (quotes aware, comments not).
fn split_top_level(data: &[u8], start: usize, end: usize) -> Vec<(usize, usize)> {
    let mut items = Vec::new();
    let mut item_start = start;
    let mut depth: i64 = 0;
    let mut quote: Option<u8> = None;
    let mut escape = false;
    let mut pos = start;
    while pos < end {
        let byte = data[pos];
        if let Some(q) = quote {
            if escape {
                escape = false;
                pos += 1;
                continue;
            }
            if byte == b'\\' && q == b'\'' {
                escape = true;
                pos += 1;
                continue;
            }
            if byte == q {
                if pos + 1 < end && data[pos + 1] == q {
                    pos += 2;
                    continue;
                }
                quote = None;
            }
            pos += 1;
            continue;
        }
        match byte {
            b'\'' | b'`' => {
                quote = Some(byte);
                pos += 1;
                continue;
            }
            b'(' => depth += 1,
            b')' => depth -= 1,
            b',' if depth == 0 => {
                items.push((item_start, pos));
                pos += 1;
                item_start = pos;
                continue;
            }
            _ => {}
        }
        pos += 1;
    }
    items.push((item_start, end));
    items
}
