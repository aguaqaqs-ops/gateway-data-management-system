//! Public descriptors and the per-column value plan.

use std::collections::HashSet;

use gateway_shared_kernel::DeclaredType;

use super::columns::Layout;
pub use super::types::SqlLogicalType;

/// Column descriptor (`SourceColumnDescriptor`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ColumnDescriptor {
    pub display_name: String,
    pub canonical_name: String,
    pub ordinal: usize,
    pub sql_type: String,
    pub logical_type: SqlLogicalType,
    pub declared_type: Option<DeclaredType>,
    pub nullable: bool,
    pub labels: Option<Vec<String>>,
}

/// Table descriptor (`SourceTableDescriptor`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TableDescriptor {
    pub display_name: String,
    pub canonical_name: String,
    pub columns: Vec<ColumnDescriptor>,
    pub primary_key: Vec<String>,
    pub reader_ready: bool,
}

/// How values of one column are converted and stored.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ValueKind {
    SignedInt {
        bits: u8,
    },
    UnsignedInt {
        bits: u8,
    },
    Boolean,
    Decimal,
    Float32,
    Float64,
    Str,
    Enum,
    Json,
    Binary,
    Bit {
        width: u8,
    },
    Date,
    DateTime,
    Timestamp,
    Time,
    Set,
    /// UNKNOWN columns: any non-NULL value is illegal.
    Unready,
}

impl ValueKind {
    pub fn of(column: &ColumnDescriptor) -> Self {
        match column.logical_type {
            SqlLogicalType::Set => Self::Set,
            SqlLogicalType::Unknown => Self::Unready,
            SqlLogicalType::Enum => Self::Enum,
            SqlLogicalType::Json => Self::Json,
            SqlLogicalType::Standard => match &column.declared_type {
                None => Self::Unready,
                Some(declared) => match declared {
                    DeclaredType::Boolean => Self::Boolean,
                    DeclaredType::SignedInteger { bits } => Self::SignedInt { bits: *bits },
                    DeclaredType::UnsignedInteger { bits } => Self::UnsignedInt { bits: *bits },
                    DeclaredType::Decimal { .. } => Self::Decimal,
                    DeclaredType::Float32 => Self::Float32,
                    DeclaredType::Float64 => Self::Float64,
                    DeclaredType::String => Self::Str,
                    DeclaredType::Binary => Self::Binary,
                    DeclaredType::Bit { bit_width } => Self::Bit { width: *bit_width },
                    DeclaredType::Date => Self::Date,
                    DeclaredType::DateTime => Self::DateTime,
                    DeclaredType::Timestamp => Self::Timestamp,
                    DeclaredType::TimeDuration => Self::Time,
                    DeclaredType::Null | DeclaredType::SourceLiteralAnomaly => Self::Unready,
                },
            },
        }
    }

    pub fn layout(&self) -> Layout {
        match self {
            Self::SignedInt { .. } => Layout::I64,
            Self::UnsignedInt { .. } => Layout::U64,
            Self::Boolean => Layout::Bool,
            Self::Float32 => Layout::F32,
            Self::Float64 => Layout::F64,
            Self::Binary | Self::Bit { .. } => Layout::Binary,
            _ => Layout::Utf8,
        }
    }

    /// Type mark of non-null values in the parse canonical form.
    pub fn mark(&self) -> u8 {
        match self {
            Self::Boolean => 0x01,
            Self::SignedInt { .. } => 0x10,
            Self::UnsignedInt { .. } => 0x11,
            Self::Decimal => 0x12,
            Self::Float32 => 0x13,
            Self::Float64 => 0x14,
            Self::Str | Self::Enum | Self::Json => 0x20,
            Self::Binary => 0x21,
            Self::Bit { .. } => 0x22,
            Self::Date => 0x30,
            Self::DateTime => 0x31,
            Self::Timestamp => 0x32,
            Self::Time => 0x33,
            Self::Set => 0x40,
            Self::Unready => 0xff,
        }
    }
}

/// Conversion plan for one column, shared by all chunks of a table.
#[derive(Debug, Clone)]
pub(crate) struct ColumnPlan {
    pub kind: ValueKind,
    pub nullable: bool,
    pub declared: Option<DeclaredType>,
    /// ENUM or SET labels in declaration order.
    pub labels: Vec<String>,
    pub label_set: HashSet<String>,
}

impl ColumnPlan {
    pub fn new(column: &ColumnDescriptor) -> Self {
        let labels = column.labels.clone().unwrap_or_default();
        let label_set = labels.iter().cloned().collect();
        Self {
            kind: ValueKind::of(column),
            nullable: column.nullable,
            declared: column.declared_type.clone(),
            labels,
            label_set,
        }
    }
}
