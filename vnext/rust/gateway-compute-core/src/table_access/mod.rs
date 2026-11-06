//! Table Access kernel: SQL dump scanning and INSERT value parsing.
//!
//! Semantics follow the Python reference
//! `gateway_backend.capabilities.table_access.sql.parse_sql`:
//!
//! 1. Phase A (sequential): find statement boundaries (quotes, escapes,
//!    comments, versioned comments), parse CREATE TABLE descriptors and
//!    INSERT headers, check session boilerplate against the allowlist.
//! 2. Phase B (parallel, Rayon): parse INSERT value tuples chunk by chunk and
//!    convert them straight into column builders.
//! 3. Merge (parallel per table): concatenate chunks in source order and
//!    build Arrow arrays. Output does not depend on the thread count or the
//!    chunk size.
//!
//! The core never touches the file system; callers pass the dump bytes and a
//! caller-owned, fixed-size Rayon pool. Diagnostics are bounded and merged in
//! source order so chunk size and worker count do not change observable output.

mod canonical;
mod columns;
mod convert;
mod cursor;
mod errors;
mod json_check;
mod literal;
mod model;
mod scan;
mod statements;
mod types;
mod values;

use std::panic::AssertUnwindSafe;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use arrow_array::ArrayRef;
use rayon::prelude::*;

pub use canonical::{PARSE_CANONICAL_FORMAT, PARSE_CANONICAL_VERSION, encode_parse_canonical};
pub use errors::{ParserDiagnostic, ParserDiagnosticCode};
pub use model::{ColumnDescriptor, DeclaredTypeMetadata, SqlLogicalType, TableDescriptor};

use cursor::Cursor;
use errors::Fault;
use model::ColumnPlan;
use scan::Scanner;
use statements::{Catalog, InsertJob, StatementKind, TableBuild};
use values::{ChunkContext, ChunkOutcome, ChunkSpec, DocErrorKind, TableErrorKind};

/// Upper bound for the parser thread pool (DC47: fixed, bounded fan-out).
pub const MAX_PARSER_THREADS: usize = 256;
/// Default target size of one INSERT parse task.
pub const DEFAULT_CHUNK_BYTES: usize = 1 << 20;

/// Verify metadata at an Arrow business boundary using the parser's existing
/// type vocabulary. Spelling normalization remains with the caller's owner.
pub(crate) fn valid_column_type(column: &ColumnDescriptor) -> bool {
    let mapped = types::map_sql_type(&column.sql_type, column.sql_type.len());
    mapped.logical_type == column.logical_type
        && mapped.declared_type == column.declared_type
        && mapped.labels == column.labels
        && column
            .declared_type
            .as_ref()
            .is_none_or(|declared| declared.validate().is_ok())
}

pub(crate) fn same_column_sql_type(left: &ColumnDescriptor, right: &ColumnDescriptor) -> bool {
    types::map_sql_type(&left.sql_type, left.sql_type.len()).sql_type
        == types::map_sql_type(&right.sql_type, right.sql_type.len()).sql_type
}

/// Resource budgets (`RESOURCE_BUDGETS` of the Python contract).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParserBudgets {
    pub max_sql_source_bytes: usize,
    pub max_statement_bytes: usize,
    pub max_tables_per_source: usize,
    pub max_columns_per_table: usize,
    pub max_identifier_code_points: usize,
    pub max_rows_per_table: usize,
    pub max_rows_per_source: usize,
    pub max_field_bytes: usize,
    pub max_insert_tuple_bytes: usize,
    pub max_enum_set_sql_type_bytes: usize,
    pub max_diagnostics: usize,
    pub max_diagnostic_message_bytes: usize,
    pub max_diagnostics_total_bytes: usize,
}

impl Default for ParserBudgets {
    fn default() -> Self {
        const MIB: usize = 1024 * 1024;
        Self {
            max_sql_source_bytes: 512 * MIB,
            max_statement_bytes: 16 * MIB,
            max_tables_per_source: 2048,
            max_columns_per_table: 512,
            max_identifier_code_points: 64,
            max_rows_per_table: 2_000_000,
            max_rows_per_source: 10_000_000,
            max_field_bytes: 4 * MIB,
            max_insert_tuple_bytes: 16 * MIB,
            max_enum_set_sql_type_bytes: 64 * 1024,
            max_diagnostics: 1024,
            max_diagnostic_message_bytes: 4 * 1024,
            max_diagnostics_total_bytes: 256 * 1024,
        }
    }
}

#[derive(Debug, Clone)]
pub struct SqlParseOptions<'a> {
    /// Target bytes per INSERT parse task. Does not change the output.
    pub chunk_bytes: usize,
    pub budgets: ParserBudgets,
    pub cancel: Option<&'a AtomicBool>,
    pub deadline: Option<Instant>,
}

impl Default for SqlParseOptions<'_> {
    fn default() -> Self {
        Self {
            chunk_bytes: DEFAULT_CHUNK_BYTES,
            budgets: ParserBudgets::default(),
            cancel: None,
            deadline: None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ParseStatus {
    Complete,
    Partial,
    Failed,
}

impl ParseStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Complete => "COMPLETE",
            Self::Partial => "PARTIAL",
            Self::Failed => "FAILED",
        }
    }
}

#[derive(Debug, Clone)]
pub struct ParsedTable {
    pub descriptor: TableDescriptor,
    pub row_count: usize,
    /// One array per column in ordinal order; `None` when not reader-ready.
    pub columns: Option<Vec<ArrayRef>>,
}

#[derive(Debug, Clone)]
pub struct SqlParseOutput {
    pub status: ParseStatus,
    /// Empty when the document failed.
    pub tables: Vec<ParsedTable>,
    pub diagnostics: Vec<ParserDiagnostic>,
    /// Wall time per phase, for measurement only; not part of the result.
    /// Zero for phases that did not run.
    pub timings: ParsePhaseTimings,
}

/// Wall time of each parser phase (measurement only).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ParsePhaseTimings {
    /// UTF-8 validation of the whole source (sequential).
    pub validate: Duration,
    /// Phase A: statement scan, DDL and INSERT headers, chunk plan (sequential).
    pub scan: Duration,
    /// Phase B: value tuples into column builders (parallel).
    pub values: Duration,
    /// Error merge and Arrow array assembly (parallel per table).
    pub merge: Duration,
}

impl SqlParseOutput {
    /// The document-level failure, when the whole document failed.
    pub fn document_failure(&self) -> Option<&ParserDiagnostic> {
        if self.status == ParseStatus::Failed && self.tables.is_empty() {
            self.diagnostics.last()
        } else {
            None
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParserPoolError(String);

impl std::fmt::Display for ParserPoolError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for ParserPoolError {}

/// Builds a fixed-size pool for the parser (1..=MAX_PARSER_THREADS threads).
pub fn build_parser_pool(threads: usize) -> Result<rayon::ThreadPool, ParserPoolError> {
    if !(1..=MAX_PARSER_THREADS).contains(&threads) {
        return Err(ParserPoolError(format!(
            "parser threads must be in 1..={MAX_PARSER_THREADS}, got {threads}"
        )));
    }
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .thread_name(|index| format!("gdms-table-access-{index}"))
        .build()
        .map_err(|error| ParserPoolError(error.to_string()))
}

/// Parses a SQL dump. Never panics: unexpected panics become a
/// `PARSER_INTERNAL_ERROR` document failure.
pub fn parse_sql_dump(
    sql: &[u8],
    options: &SqlParseOptions<'_>,
    pool: &rayon::ThreadPool,
) -> SqlParseOutput {
    match catch_parser_panic(|| parse_document(sql, options, pool)) {
        Ok(output) => output,
        Err(fault) => failed_document(Vec::new(), fault, &options.budgets),
    }
}

fn catch_parser_panic<T>(operation: impl FnOnce() -> T) -> Result<T, Fault> {
    std::panic::catch_unwind(AssertUnwindSafe(operation)).map_err(|_| {
        Fault::new(
            ParserDiagnosticCode::ParserInternalError,
            0,
            "parser panicked",
        )
    })
}

fn failed_document(
    mut diagnostics: Vec<ParserDiagnostic>,
    fault: Fault,
    budgets: &ParserBudgets,
) -> SqlParseOutput {
    diagnostics.retain(|item| item.byte_offset <= fault.offset);
    diagnostics.push(fault.into_diagnostic(None, None));
    let diagnostics = finish_diagnostics(diagnostics, budgets);
    SqlParseOutput {
        status: ParseStatus::Failed,
        tables: Vec::new(),
        diagnostics,
        timings: ParsePhaseTimings::default(),
    }
}

fn sort_diagnostics(diagnostics: &mut [ParserDiagnostic]) {
    diagnostics.sort_by(|a, b| {
        a.byte_offset
            .cmp(&b.byte_offset)
            .then_with(|| a.code.as_str().cmp(b.code.as_str()))
    });
}

fn finish_diagnostics(
    mut diagnostics: Vec<ParserDiagnostic>,
    budgets: &ParserBudgets,
) -> Vec<ParserDiagnostic> {
    sort_diagnostics(&mut diagnostics);
    let mut kept = Vec::new();
    let mut total_bytes = 0usize;
    let mut truncated = false;
    for mut diagnostic in diagnostics {
        if diagnostic.code == ParserDiagnosticCode::ParserDiagnosticsTruncated {
            continue;
        }
        diagnostic.message =
            clip_message(&diagnostic.message, budgets.max_diagnostic_message_bytes);
        let size = diagnostic.message.len();
        if kept.len() >= budgets.max_diagnostics
            || total_bytes.saturating_add(size) > budgets.max_diagnostics_total_bytes
        {
            truncated = true;
            break;
        }
        total_bytes += size;
        kept.push(diagnostic);
    }
    if truncated {
        let marker = ParserDiagnostic {
            code: ParserDiagnosticCode::ParserDiagnosticsTruncated,
            byte_offset: kept.last().map_or(0, |item| item.byte_offset),
            table: None,
            column: None,
            message: clip_message(
                "parser diagnostics truncated",
                budgets.max_diagnostic_message_bytes,
            ),
        };
        let marker_size = marker.message.len();
        while !kept.is_empty()
            && (kept.len() + 1 > budgets.max_diagnostics
                || total_bytes.saturating_add(marker_size) > budgets.max_diagnostics_total_bytes)
        {
            if let Some(removed) = kept.pop() {
                total_bytes -= removed.message.len();
            }
        }
        if kept.len() < budgets.max_diagnostics
            && total_bytes.saturating_add(marker_size) <= budgets.max_diagnostics_total_bytes
        {
            kept.push(marker);
        }
    }
    kept
}

fn clip_message(message: &str, max_bytes: usize) -> String {
    if message.len() <= max_bytes {
        return message.to_owned();
    }
    let end = message
        .char_indices()
        .take_while(|(offset, character)| *offset + character.len_utf8() <= max_bytes)
        .map(|(offset, character)| offset + character.len_utf8())
        .last()
        .unwrap_or(0);
    message[..end].to_owned()
}

fn interrupted(options: &SqlParseOptions<'_>, offset: usize) -> Option<Fault> {
    if options
        .cancel
        .is_some_and(|flag| flag.load(Ordering::Relaxed))
    {
        return Some(Fault::new(
            ParserDiagnosticCode::ParserCancelled,
            offset,
            "parser cancelled",
        ));
    }
    if options
        .deadline
        .is_some_and(|deadline| Instant::now() >= deadline)
    {
        return Some(Fault::new(
            ParserDiagnosticCode::ParserTimeout,
            offset,
            "parser deadline exceeded",
        ));
    }
    None
}

struct PhaseA {
    catalog: Catalog,
    jobs: Vec<InsertJob>,
    halt: Option<Fault>,
}

fn run_phase_a(sql: &[u8], options: &SqlParseOptions<'_>) -> PhaseA {
    let budgets = &options.budgets;
    let mut catalog = Catalog::new();
    let mut jobs = Vec::new();
    let mut scanner = Scanner::new(sql, options.chunk_bytes, budgets.max_statement_bytes);
    let halt = loop {
        if let Some(fault) = interrupted(options, scanner.position()) {
            break Some(fault);
        }
        let span = match scanner.next_statement() {
            Ok(Some(span)) => span,
            Ok(None) => break None,
            Err(fault) => break Some(fault),
        };
        let mut cursor = Cursor::new(sql, span.start, span.end);
        let result = statements::classify_statement(&mut cursor).and_then(|kind| match kind {
            StatementKind::Empty => Ok(()),
            StatementKind::Create => {
                statements::parse_create_table(&mut cursor, &mut catalog, budgets)
            }
            StatementKind::Insert => {
                statements::parse_insert_header(&mut cursor, &mut catalog, budgets, &span.splits)
                    .map(|job| jobs.push(job))
            }
            other => statements::parse_boilerplate(other, &mut cursor, budgets),
        });
        if let Err(fault) = result {
            break Some(fault);
        }
    };
    PhaseA {
        catalog,
        jobs,
        halt,
    }
}

fn chunk_specs(jobs: &[InsertJob], tables: &[TableBuild]) -> Vec<ChunkSpec> {
    let mut specs = Vec::new();
    for (index, job) in jobs.iter().enumerate() {
        let failed_at = tables.get(job.table).and_then(|table| table.failed_at);
        let mut start = job.values_start;
        let mut push = |start: usize, end: usize| {
            specs.push(ChunkSpec {
                job: index,
                table: job.table,
                start,
                end,
                convert: failed_at.is_none_or(|at| at > start),
            });
        };
        for &split in &job.splits {
            push(start, split);
            start = split + 1;
        }
        push(start, job.end);
    }
    specs
}

fn parse_document(
    sql: &[u8],
    options: &SqlParseOptions<'_>,
    pool: &rayon::ThreadPool,
) -> SqlParseOutput {
    let budgets = &options.budgets;
    let started = Instant::now();
    if sql.len() > budgets.max_sql_source_bytes {
        return failed_document(
            Vec::new(),
            Fault::resource("max_sql_source_bytes", 0),
            budgets,
        );
    }
    if let Err(error) = std::str::from_utf8(sql) {
        return failed_document(
            Vec::new(),
            Fault::new(
                ParserDiagnosticCode::InvalidSourceEncoding,
                error.valid_up_to(),
                "SQL source is not strict UTF-8",
            ),
            budgets,
        );
    }

    let validated = Instant::now();
    let PhaseA {
        mut catalog,
        jobs,
        halt,
    } = run_phase_a(sql, options);

    let plans: Vec<Arc<[ColumnPlan]>> = catalog
        .tables
        .iter()
        .map(|table| table.columns.iter().map(ColumnPlan::new).collect())
        .collect();
    let ordinals: Vec<Arc<[usize]>> = jobs.iter().map(|job| Arc::clone(&job.ordinals)).collect();
    let specs = chunk_specs(&jobs, &catalog.tables);
    let context = ChunkContext {
        data: sql,
        plans: &plans,
        ordinals: &ordinals,
        max_field_bytes: budgets.max_field_bytes,
        max_insert_tuple_bytes: budgets.max_insert_tuple_bytes,
        cancel: options.cancel,
        deadline: options.deadline,
    };
    let scanned = Instant::now();
    let outcomes: Vec<ChunkOutcome> = pool.install(|| {
        specs
            .par_iter()
            .map(|spec| values::parse_chunk(&context, *spec))
            .collect()
    });
    let parsed = Instant::now();

    // Merge table events in source order. Structural tuple errors are
    // reported after a table has failed; value conversion stops at the first
    // earlier table failure, matching the sequential reference parser.
    let mut table_errors: Vec<Vec<(Fault, TableErrorKind)>> =
        (0..catalog.tables.len()).map(|_| Vec::new()).collect();
    for outcome in &outcomes {
        if let Some(events) = table_errors.get_mut(outcome.table) {
            events.extend(outcome.table_errors.iter().cloned());
        }
    }
    for (table_index, events) in table_errors.iter_mut().enumerate() {
        events.sort_by_key(|(fault, _)| fault.offset);
        let Some(table) = catalog.tables.get_mut(table_index) else {
            continue;
        };
        let phase_a_failed_at = table.failed_at;
        let mut failed_before = false;
        for (fault, kind) in events {
            if phase_a_failed_at.is_some_and(|offset| offset <= fault.offset) {
                failed_before = true;
            }
            if *kind == TableErrorKind::Conversion && failed_before {
                continue;
            }
            let name = table.display_name.clone();
            table
                .diagnostics
                .push(fault.clone().into_diagnostic(Some(name), None));
            table.failed_at = Some(
                table
                    .failed_at
                    .map_or(fault.offset, |at| at.min(fault.offset)),
            );
            failed_before = true;
        }
    }
    let mut document_fault = halt;
    let mut consider = |fault: &Fault| {
        if document_fault
            .as_ref()
            .is_none_or(|current| fault.offset < current.offset)
        {
            document_fault = Some(fault.clone());
        }
    };
    for outcome in &outcomes {
        if let Some((fault, kind)) = &outcome.doc_error {
            let counts = match kind {
                DocErrorKind::Syntax => true,
                DocErrorKind::Conversion => catalog
                    .tables
                    .get(outcome.table)
                    .and_then(|table| table.failed_at)
                    .is_none_or(|at| fault.offset < at),
            };
            if counts {
                consider(fault);
            }
        }
    }
    if let Some(fault) = rows_budget_fault(&outcomes, &catalog.tables, budgets) {
        consider(&fault);
    }

    let mut diagnostics: Vec<ParserDiagnostic> = Vec::new();
    for table in &mut catalog.tables {
        if table.columns.is_empty() {
            let fault = Fault::malformed(table.create_offset, "CREATE TABLE requires columns");
            table.failed_at.get_or_insert(table.create_offset);
            table
                .diagnostics
                .push(fault.into_diagnostic(Some(table.display_name.clone()), None));
        }
        diagnostics.append(&mut table.diagnostics);
    }
    if let Some(fault) = document_fault {
        return failed_document(diagnostics, fault, budgets);
    }
    if let Some(fault) = catalog.soft_failure.clone() {
        diagnostics.push(fault.into_diagnostic(None, None));
    }
    let diagnostics = finish_diagnostics(diagnostics, budgets);

    let document_failed = catalog.soft_failure.is_some();
    let mut grouped: Vec<Vec<ChunkOutcome>> =
        (0..catalog.tables.len()).map(|_| Vec::new()).collect();
    for outcome in outcomes {
        if let Some(group) = grouped.get_mut(outcome.table) {
            group.push(outcome);
        }
    }
    let work: Vec<(TableBuild, Vec<ChunkOutcome>, Arc<[ColumnPlan]>)> = catalog
        .tables
        .into_iter()
        .zip(grouped)
        .zip(plans)
        .map(|((table, chunks), plan)| (table, chunks, plan))
        .collect();
    let built: Vec<Result<ParsedTable, Fault>> = pool.install(|| {
        work.into_par_iter()
            .map(|(table, chunks, plan)| finish_table(table, chunks, &plan, document_failed))
            .collect()
    });
    let mut tables = Vec::with_capacity(built.len());
    for item in built {
        match item {
            Ok(table) => tables.push(table),
            Err(fault) => return failed_document(diagnostics, fault, budgets),
        }
    }
    let ready = tables
        .iter()
        .filter(|table| table.descriptor.reader_ready)
        .count();
    let status = if ready == tables.len() {
        ParseStatus::Complete
    } else if ready == 0 {
        ParseStatus::Failed
    } else {
        ParseStatus::Partial
    };
    SqlParseOutput {
        status,
        tables,
        diagnostics,
        timings: ParsePhaseTimings {
            validate: validated - started,
            scan: scanned - validated,
            values: parsed - scanned,
            merge: parsed.elapsed(),
        },
    }
}

/// Row budgets are checked at each successful tuple in source order.
fn rows_budget_fault(
    outcomes: &[ChunkOutcome],
    tables: &[TableBuild],
    budgets: &ParserBudgets,
) -> Option<Fault> {
    let mut row_offsets: Vec<(usize, usize)> = outcomes
        .iter()
        .flat_map(|outcome| {
            let failed_at = tables.get(outcome.table).and_then(|table| table.failed_at);
            outcome
                .row_offsets
                .iter()
                .copied()
                .filter_map(move |offset| {
                    failed_at
                        .is_none_or(|failed_at| offset < failed_at)
                        .then_some((offset, outcome.table))
                })
        })
        .collect();
    row_offsets.sort_by_key(|(offset, _)| *offset);
    let mut per_table = vec![0usize; tables.len()];
    let mut total = 0usize;
    for (offset, table) in row_offsets {
        if let Some(count) = per_table.get_mut(table) {
            *count = count.saturating_add(1);
            if *count > budgets.max_rows_per_table {
                return Some(Fault::resource("max_rows_per_table", offset));
            }
        }
        total = total.saturating_add(1);
        if total > budgets.max_rows_per_source {
            return Some(Fault::resource("max_rows_per_source", offset));
        }
    }
    None
}

fn finish_table(
    table: TableBuild,
    chunks: Vec<ChunkOutcome>,
    plan: &[ColumnPlan],
    document_failed: bool,
) -> Result<ParsedTable, Fault> {
    let ready = table.failed_at.is_none()
        && !table.unknown
        && !document_failed
        && !table.columns.is_empty();
    let descriptor = TableDescriptor {
        display_name: table.display_name,
        canonical_name: table.canonical_name,
        columns: table.columns,
        primary_key: table.pk,
        reader_ready: ready,
    };
    if !ready {
        return Ok(ParsedTable {
            descriptor,
            row_count: 0,
            columns: None,
        });
    }
    let mut chunks = chunks.into_iter();
    let mut builders = match chunks.next() {
        Some(first) => first.columns,
        None => plan
            .iter()
            .map(|p| columns::ColumnBuilder::new(p.kind.layout()))
            .collect(),
    };
    for chunk in chunks {
        for (builder, part) in builders.iter_mut().zip(chunk.columns) {
            builder.append(part)?;
        }
    }
    let row_count = builders.first().map_or(0, columns::ColumnBuilder::len);
    let arrays = builders
        .into_iter()
        .map(columns::ColumnBuilder::finish)
        .collect::<Result<Vec<_>, _>>()?;
    Ok(ParsedTable {
        descriptor,
        row_count,
        columns: Some(arrays),
    })
}

#[cfg(test)]
mod tests;
