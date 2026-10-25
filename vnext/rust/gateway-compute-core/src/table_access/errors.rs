//! Stable diagnostic codes and the internal failure value.
//!
//! Codes mirror `ParserDiagnosticCode` of the Python Table Access contract.
//! Messages are informative only; the differential compares codes and
//! positions, never message text (DC46 item 4).

use std::borrow::Cow;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum ParserDiagnosticCode {
    SqlTypeMalformed,
    SqlValueIllegal,
    UnknownSqlType,
    ResourceLimitExceeded,
    ParserCancelled,
    ParserTimeout,
    UnsupportedStatement,
    DuplicateTable,
    DuplicateColumn,
    DuplicatePrimaryKey,
    CanonicalIdentifierCollision,
    RowShapeMismatch,
    IncompleteInsert,
    MalformedSql,
    /// The input is not strict UTF-8. The Python request type rejects such
    /// input before parsing; the kernel reports it as a document failure.
    InvalidSourceEncoding,
    /// An internal invariant failed (including a caught panic). Never expected.
    ParserInternalError,
}

impl ParserDiagnosticCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::SqlTypeMalformed => "SQL_TYPE_MALFORMED",
            Self::SqlValueIllegal => "SQL_VALUE_ILLEGAL",
            Self::UnknownSqlType => "UNKNOWN_SQL_TYPE",
            Self::ResourceLimitExceeded => "RESOURCE_LIMIT_EXCEEDED",
            Self::ParserCancelled => "PARSER_CANCELLED",
            Self::ParserTimeout => "PARSER_TIMEOUT",
            Self::UnsupportedStatement => "UNSUPPORTED_STATEMENT",
            Self::DuplicateTable => "DUPLICATE_TABLE",
            Self::DuplicateColumn => "DUPLICATE_COLUMN",
            Self::DuplicatePrimaryKey => "DUPLICATE_PRIMARY_KEY",
            Self::CanonicalIdentifierCollision => "CANONICAL_IDENTIFIER_COLLISION",
            Self::RowShapeMismatch => "ROW_SHAPE_MISMATCH",
            Self::IncompleteInsert => "INCOMPLETE_INSERT",
            Self::MalformedSql => "MALFORMED_SQL",
            Self::InvalidSourceEncoding => "INVALID_SOURCE_ENCODING",
            Self::ParserInternalError => "PARSER_INTERNAL_ERROR",
        }
    }
}

/// One diagnostic in the parse output.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParserDiagnostic {
    pub code: ParserDiagnosticCode,
    pub byte_offset: usize,
    pub table: Option<String>,
    pub column: Option<String>,
    pub message: String,
}

/// Internal failure: a code, a byte offset and a short message.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Fault {
    pub code: ParserDiagnosticCode,
    pub offset: usize,
    pub message: Cow<'static, str>,
}

impl Fault {
    pub fn new(
        code: ParserDiagnosticCode,
        offset: usize,
        message: impl Into<Cow<'static, str>>,
    ) -> Self {
        Self {
            code,
            offset,
            message: message.into(),
        }
    }

    pub fn malformed(offset: usize, message: &'static str) -> Self {
        Self::new(ParserDiagnosticCode::MalformedSql, offset, message)
    }

    pub fn unsupported(offset: usize, message: impl Into<Cow<'static, str>>) -> Self {
        Self::new(ParserDiagnosticCode::UnsupportedStatement, offset, message)
    }

    pub fn resource(budget: &'static str, offset: usize) -> Self {
        Self::new(
            ParserDiagnosticCode::ResourceLimitExceeded,
            offset,
            format!("{budget} exceeded"),
        )
    }

    pub fn illegal(offset: usize, message: impl Into<Cow<'static, str>>) -> Self {
        Self::new(ParserDiagnosticCode::SqlValueIllegal, offset, message)
    }

    pub fn into_diagnostic(
        self,
        table: Option<String>,
        column: Option<String>,
    ) -> ParserDiagnostic {
        ParserDiagnostic {
            code: self.code,
            byte_offset: self.offset,
            table,
            column,
            message: self.message.into_owned(),
        }
    }
}

/// Result of a document-level step: `Err` stops the whole document.
pub(crate) type PResult<T> = Result<T, Fault>;

pub(crate) const ANSI_QUOTES_MESSAGE: &str =
    "ANSI_QUOTES double-quoted identifiers are not in the source dump allowlist";
pub(crate) const VERSIONED_MESSAGE: &str = "versioned comment is not an allowlisted statement";
