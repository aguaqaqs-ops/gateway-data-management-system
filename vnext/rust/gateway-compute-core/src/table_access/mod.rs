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
mod generation_time;
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
pub use generation_time::{CONFIGURATION_GENERATED_TIME_RULE, ConfigurationGeneratedTime};
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
    /// Parser-owned peak reservation; borrowed SQL bytes belong to the caller.
    pub max_live_bytes: usize,
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
            max_live_bytes: usize::MAX,
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
    pub configuration_generated_time: Option<ConfigurationGeneratedTime>,
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
        configuration_generated_time: None,
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
    memory_upper_bytes: usize,
}

fn run_phase_a(sql: &[u8], options: &SqlParseOptions<'_>, pool_threads: usize) -> PhaseA {
    let budgets = &options.budgets;
    let mut catalog = Catalog::new();
    let mut jobs = Vec::new();
    let mut phase_a_bytes = 4096_usize;
    let mut values_bytes = 0_usize;
    let mut max_chunk_scratch = 0_usize;
    let mut total_chunks = 0_usize;
    let mut scanner = Scanner::new(sql, options.chunk_bytes, budgets.max_statement_bytes);
    let halt = loop {
        if let Some(fault) = interrupted(options, scanner.position()) {
            break Some(fault);
        }
        // Scanner allocates at most one split offset per chunk. This is
        // checked before its first Vec growth, including a final partial chunk.
        let scan_upper = (sql.len() - scanner.position())
            .checked_div(options.chunk_bytes.max(1))
            .and_then(|n| n.checked_add(1))
            .and_then(|n| n.checked_mul(2 * std::mem::size_of::<usize>()));
        if scan_upper
            .and_then(|n| n.checked_add(phase_a_bytes))
            .is_none_or(|n| n > budgets.max_live_bytes)
        {
            break Some(Fault::resource("max_live_bytes", 0));
        }
        let span = match scanner.next_statement() {
            Ok(Some(span)) => span,
            Ok(None) => break None,
            Err(fault) => break Some(fault),
        };
        let mut cursor = Cursor::new(sql, span.start, span.end);
        let result = statements::classify_statement(&mut cursor).and_then(|kind| {
            // CREATE declarations are cloned into plans, hash sets and Python
            // Unicode/metadata. INSERT jobs can omit a wide table's column list.
            // Reserve actual catalog width as well as split/header storage.
            let columns = catalog
                .tables
                .iter()
                .map(|t| t.columns.len())
                .max()
                .unwrap_or(0);
            let statement_bytes = span.end - span.start;
            let extra = match kind {
                StatementKind::Create => statement_bytes
                    .checked_mul(128)
                    .and_then(|n| n.checked_add(4096)),
                StatementKind::Insert => statement_bytes
                    .checked_mul(2)
                    .and_then(|n| columns.checked_mul(16).and_then(|c| n.checked_add(c)))
                    .and_then(|n| {
                        span.splits
                            .len()
                            .checked_mul(16 + 2 * std::mem::size_of::<ConfigurationGeneratedTime>())
                            .and_then(|c| n.checked_add(c))
                    })
                    .and_then(|n| n.checked_add(4 * std::mem::size_of::<InsertJob>() + 4096)),
                _ => Some(0),
            };
            phase_a_bytes = extra
                .and_then(|n| phase_a_bytes.checked_add(n))
                .filter(|n| *n <= budgets.max_live_bytes)
                .ok_or_else(|| Fault::resource("max_live_bytes", 0))?;
            match kind {
                StatementKind::Empty => Ok(()),
                StatementKind::Create => {
                    statements::parse_create_table(&mut cursor, &mut catalog, budgets)
                }
                StatementKind::Insert => {
                    statements::parse_insert_header(
                        &mut cursor,
                        &mut catalog,
                        budgets,
                        &span.splits,
                    )
                    .and_then(|job| {
                        let table = &catalog.tables[job.table];
                        let rows = span.outer_groups.max(1);
                        // Four simultaneous capacity-sized value/validity slots
                        // include append reallocation and ends -> Arrow offsets.
                        let slots = table
                            .columns
                            .len()
                            .checked_mul(36)
                            .and_then(|n| n.checked_add(32));
                        // Existing malformed tuples retain Faults, cloned event
                        // vectors and diagnostics until the final truncation.
                        // Current value/literal error templates are bounded by
                        // 256 bytes; no template includes raw literal contents.
                        let diagnostics = std::mem::size_of::<Fault>()
                            .checked_add(std::mem::size_of::<ParserDiagnostic>())
                            .and_then(|n| n.checked_add(256 + table.display_name.len()))
                            .and_then(|n| n.checked_mul(4));
                        let headers = (span.splits.len() + 1)
                            .checked_mul(table.columns.len())
                            .and_then(|n| {
                                n.checked_mul(4 * std::mem::size_of::<columns::ColumnBuilder>())
                            });
                        let owned = slots
                            .and_then(|n| diagnostics.and_then(|d| n.checked_add(d)))
                            .and_then(|n| n.checked_mul(rows))
                            .and_then(|n| {
                                statement_bytes
                                    .checked_mul(8)
                                    .and_then(|b| n.checked_add(b))
                            })
                            .and_then(|n| headers.and_then(|h| n.checked_add(h)));
                        values_bytes = owned
                            .and_then(|n| values_bytes.checked_add(n))
                            .ok_or_else(|| Fault::resource("max_live_bytes", 0))?;
                        // Literal Vec capacity uses actual scanned tuple width,
                        // including malformed tuples wider than the schema.
                        // Payload scratch covers unescape/hex, normalization and
                        // JSON string work. SET holds at most 64 seen/ordered refs.
                        let scratch = span
                            .max_group_fields
                            .max(job.ordinals.len())
                            .checked_mul(2 * std::mem::size_of::<literal::Lit<'_>>())
                            .and_then(|n| {
                                span.max_group_bytes
                                    .checked_mul(8)
                                    .and_then(|b| n.checked_add(b))
                            })
                            .and_then(|n| {
                                n.checked_add(
                                    64 * 2 * std::mem::size_of::<&str>() + 100 * 64 + 4096,
                                )
                            })
                            .ok_or_else(|| Fault::resource("max_live_bytes", 0))?;
                        max_chunk_scratch = max_chunk_scratch.max(scratch);
                        total_chunks = total_chunks
                            .checked_add(span.splits.len() + 1)
                            .ok_or_else(|| Fault::resource("max_live_bytes", 0))?;
                        let active = total_chunks.min(pool_threads);
                        let peak = max_chunk_scratch
                            .checked_mul(active)
                            .and_then(|n| n.checked_add(values_bytes))
                            .and_then(|n| n.checked_add(phase_a_bytes));
                        if peak.is_none_or(|n| n > budgets.max_live_bytes) {
                            return Err(Fault::resource("max_live_bytes", 0));
                        }
                        jobs.push(job);
                        Ok(())
                    })
                }
                other => statements::parse_boilerplate(other, &mut cursor, budgets),
            }
        });
        if let Err(fault) = result {
            break Some(fault);
        }
    };
    PhaseA {
        catalog,
        memory_upper_bytes: phase_a_bytes
            .saturating_add(values_bytes)
            .saturating_add(max_chunk_scratch.saturating_mul(total_chunks.min(pool_threads))),
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
        memory_upper_bytes,
    } = run_phase_a(sql, options, pool.current_num_threads());
    if halt
        .as_ref()
        .is_some_and(|fault| fault.offset == 0 && fault.message == "max_live_bytes exceeded")
        || memory_upper_bytes > budgets.max_live_bytes
    {
        return failed_document(Vec::new(), Fault::resource("max_live_bytes", 0), budgets);
    }

    let plans: Vec<Arc<[ColumnPlan]>> = catalog
        .tables
        .iter()
        .map(|table| table.columns.iter().map(ColumnPlan::new).collect())
        .collect();
    let ordinals: Vec<Arc<[usize]>> = jobs.iter().map(|job| Arc::clone(&job.ordinals)).collect();
    let specs = chunk_specs(&jobs, &catalog.tables);
    let time_table = catalog
        .tables
        .iter()
        .position(|table| table.canonical_name == "version_manager");
    let time_column = time_table.and_then(|index| {
        catalog.tables[index]
            .columns
            .iter()
            .position(|column| column.canonical_name == "saved_time")
            .map(|column| (index, column))
    });
    let context = ChunkContext {
        time_column,
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
    let configuration_generated_time = if document_failed
        || time_table.is_some_and(|index| {
            catalog.tables[index].failed_at.is_some() || catalog.tables[index].unknown
        }) {
        None
    } else {
        let mut facts = ConfigurationGeneratedTime::default();
        for outcome in &outcomes {
            facts.merge(&outcome.configuration_generated_time);
        }
        Some(facts.finish(if time_table.is_none() {
            "TABLE_ABSENT"
        } else if time_column.is_none() {
            "COLUMN_ABSENT"
        } else {
            "PRESENT"
        }))
    };
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
        configuration_generated_time,
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
