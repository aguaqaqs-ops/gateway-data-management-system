//! INSERT value tuple parsing for one chunk of one statement.
//!
//! A chunk is a run of complete tuples between two top-level commas found by
//! the scanner. Chunks are independent, so they run in parallel; the outcome
//! records the first table-level and document-level problem with its offset
//! so the merge can reproduce the reference's sequential behaviour.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

use super::columns::ColumnBuilder;
use super::convert::{ConvError, convert_value};
use super::cursor::Cursor;
use super::errors::{Fault, ParserDiagnosticCode as Code};
use super::literal::{LexError, Lit, parse_literal};
use super::model::ColumnPlan;
use super::statements::expect_end;

/// How often (in tuples) a chunk checks cancellation and the deadline.
const CANCEL_CHECK_TUPLES: usize = 4096;

#[derive(Debug, Clone, Copy)]
pub(crate) struct ChunkSpec {
    pub job: usize,
    pub table: usize,
    pub start: usize,
    pub end: usize,
    /// Whether to convert values (false when the table already failed
    /// before this chunk).
    pub convert: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum DocErrorKind {
    /// Syntax and resource errors that stop the reference regardless of
    /// table state.
    Syntax,
    /// `max_field_bytes`, only raised by the reference while converting
    /// values of a table that has not failed yet.
    Conversion,
}

#[derive(Debug)]
pub(crate) struct ChunkOutcome {
    pub table: usize,
    pub columns: Vec<ColumnBuilder>,
    pub rows: usize,
    pub first_row_offset: Option<usize>,
    pub table_error: Option<Fault>,
    pub doc_error: Option<(Fault, DocErrorKind)>,
}

pub(crate) struct ChunkContext<'a> {
    pub data: &'a [u8],
    pub plans: &'a [Arc<[ColumnPlan]>],
    pub ordinals: &'a [Arc<[usize]>],
    pub max_field_bytes: usize,
    pub max_insert_tuple_bytes: usize,
    pub cancel: Option<&'a AtomicBool>,
    pub deadline: Option<Instant>,
}

impl ChunkContext<'_> {
    pub fn interrupted(&self, offset: usize) -> Option<Fault> {
        if self.cancel.is_some_and(|flag| flag.load(Ordering::Relaxed)) {
            return Some(Fault::new(
                Code::ParserCancelled,
                offset,
                "parser cancelled",
            ));
        }
        if self
            .deadline
            .is_some_and(|deadline| Instant::now() >= deadline)
        {
            return Some(Fault::new(
                Code::ParserTimeout,
                offset,
                "parser deadline exceeded",
            ));
        }
        None
    }
}

pub(crate) fn parse_chunk(context: &ChunkContext<'_>, spec: ChunkSpec) -> ChunkOutcome {
    let plans = &context.plans[spec.table];
    let ordinals = &context.ordinals[spec.job];
    let mut outcome = ChunkOutcome {
        table: spec.table,
        columns: plans
            .iter()
            .map(|plan| ColumnBuilder::new(plan.kind.layout()))
            .collect(),
        rows: 0,
        first_row_offset: None,
        table_error: None,
        doc_error: None,
    };
    if let Some(fault) = context.interrupted(spec.start) {
        outcome.doc_error = Some((fault, DocErrorKind::Syntax));
        return outcome;
    }
    if let Err((fault, kind)) = parse_tuples(context, spec, plans, ordinals, &mut outcome) {
        outcome.doc_error = Some((fault, kind));
    }
    outcome
}

fn syntax(fault: Fault) -> (Fault, DocErrorKind) {
    (fault, DocErrorKind::Syntax)
}

fn parse_tuples(
    context: &ChunkContext<'_>,
    spec: ChunkSpec,
    plans: &[ColumnPlan],
    ordinals: &[usize],
    outcome: &mut ChunkOutcome,
) -> Result<(), (Fault, DocErrorKind)> {
    let mut cursor = Cursor::new(context.data, spec.start, spec.end);
    let mut values: Vec<Lit<'_>> = Vec::with_capacity(ordinals.len());
    let mut convert = spec.convert;
    let mut tuples = 0usize;
    loop {
        cursor.skip_ws_and_comments().map_err(syntax)?;
        let tuple_start = cursor.pos;
        tuples += 1;
        if tuples.is_multiple_of(CANCEL_CHECK_TUPLES)
            && let Some(fault) = context.interrupted(tuple_start)
        {
            return Err(syntax(fault));
        }
        values.clear();
        let (tuple_end, tuple_ok) = match parse_tuple_values(&mut cursor, &mut values) {
            Ok(()) => (cursor.pos, true),
            Err(LexError::Halt(fault)) => return Err(syntax(fault)),
            Err(LexError::Literal(fault)) if fault.code == Code::MalformedSql => {
                return Err(syntax(fault));
            }
            Err(LexError::Literal(fault)) => {
                // Table-level literal error (DEFAULT): the reference has
                // already bracket-matched the tuple; skip to its end.
                let mut skip = Cursor::new(context.data, tuple_start, spec.end);
                let (_, end) = skip.take_balanced_paren().map_err(syntax)?;
                cursor.pos = end;
                record_table_error(outcome, fault);
                convert = false;
                (end, false)
            }
        };
        if tuple_end - tuple_start > context.max_insert_tuple_bytes {
            return Err(syntax(Fault::resource(
                "max_insert_tuple_bytes",
                tuple_start,
            )));
        }
        if tuple_ok {
            if values.len() != ordinals.len() {
                record_table_error(
                    outcome,
                    Fault::new(
                        Code::RowShapeMismatch,
                        tuple_start,
                        "INSERT tuple width does not match columns",
                    ),
                );
                convert = false;
            } else if convert {
                match convert_row(context, plans, ordinals, &values, outcome, tuple_start) {
                    Ok(()) => {
                        outcome.rows += 1;
                        outcome.first_row_offset.get_or_insert(tuple_start);
                    }
                    Err(ConvError::Table(fault)) => {
                        record_table_error(outcome, fault);
                        convert = false;
                    }
                    Err(ConvError::Document(fault)) => {
                        return Err((fault, DocErrorKind::Conversion));
                    }
                }
            }
        }
        cursor.skip_ws_and_comments().map_err(syntax)?;
        if cursor.try_keyword(b"on").map_err(syntax)? {
            return Err(syntax(Fault::unsupported(
                cursor.pos,
                "ON DUPLICATE KEY UPDATE is not in the source dump allowlist",
            )));
        }
        if cursor.peek() == Some(b',') {
            cursor.pos += 1;
            continue;
        }
        break;
    }
    expect_end(&mut cursor).map_err(syntax)
}

fn record_table_error(outcome: &mut ChunkOutcome, fault: Fault) {
    if outcome.table_error.is_none() {
        outcome.table_error = Some(fault);
    }
}

/// `(` literal (`,` literal)* `)` with the reference's empty-tuple and
/// trailing-comma rules. Leaves the cursor after `)`.
fn parse_tuple_values<'a>(
    cursor: &mut Cursor<'a>,
    values: &mut Vec<Lit<'a>>,
) -> Result<(), LexError> {
    if cursor.peek() != Some(b'(') {
        return Err(LexError::Halt(Fault::malformed(cursor.pos, "expected '('")));
    }
    cursor.pos += 1;
    loop {
        cursor.skip_ws_and_comments().map_err(LexError::Halt)?;
        match cursor.peek() {
            Some(b')') => {
                if !values.is_empty() {
                    return Err(LexError::Halt(Fault::malformed(
                        cursor.pos,
                        "trailing comma in VALUES",
                    )));
                }
                cursor.pos += 1;
                return Ok(());
            }
            None => {
                return Err(LexError::Halt(Fault::malformed(
                    cursor.pos,
                    "unclosed parenthesis",
                )));
            }
            Some(_) => {}
        }
        values.push(parse_literal(cursor)?);
        cursor.skip_ws_and_comments().map_err(LexError::Halt)?;
        match cursor.peek() {
            Some(b',') => cursor.pos += 1,
            Some(b')') => {
                cursor.pos += 1;
                return Ok(());
            }
            _ => {
                return Err(LexError::Halt(Fault::malformed(
                    cursor.pos,
                    "malformed VALUES tuple",
                )));
            }
        }
    }
}

fn convert_row(
    context: &ChunkContext<'_>,
    plans: &[ColumnPlan],
    ordinals: &[usize],
    values: &[Lit<'_>],
    outcome: &mut ChunkOutcome,
    tuple_start: usize,
) -> Result<(), ConvError> {
    for (value, ordinal) in values.iter().zip(ordinals) {
        let (Some(plan), Some(column)) = (plans.get(*ordinal), outcome.columns.get_mut(*ordinal))
        else {
            return Err(ConvError::Table(Fault::new(
                Code::RowShapeMismatch,
                tuple_start,
                "INSERT tuple is missing a column",
            )));
        };
        convert_value(value, plan, column, context.max_field_bytes, tuple_start)?;
    }
    Ok(())
}
