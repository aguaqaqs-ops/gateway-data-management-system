//! Canonical in-memory Arrow mapping and IPC file codec, version 1.
//!
//! The caller supplies already projected columns and already ordered rows.
//! This module binds columns by canonical field name, writes them in UTF-8
//! byte order, and never performs business row selection or row sorting.

use std::collections::{HashMap, HashSet};
use std::io::{self, Cursor, Write};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

use arrow_array::builder::{
    BinaryBuilder, BooleanBuilder, FixedSizeBinaryBuilder, Float32Builder, Float64Builder,
    Int64Builder, LargeBinaryBuilder, LargeStringBuilder, StringBuilder, UInt64Builder,
};
use arrow_array::{
    Array, ArrayRef, BinaryArray, BooleanArray, FixedSizeBinaryArray, Float32Array, Float64Array,
    Int64Array, LargeBinaryArray, LargeStringArray, RecordBatch, RecordBatchOptions, StringArray,
    UInt64Array,
};
use arrow_ipc::reader::FileReaderBuilder;
use arrow_ipc::writer::{FileWriter, IpcWriteOptions};
use arrow_ipc::{MessageHeader, MetadataVersion, root_as_footer, root_as_message};
use arrow_schema::{DataType, Field, Schema, SchemaRef};
use gateway_shared_kernel::{DeclaredType, canonicalize_jcs};
use rayon::ThreadPool;
use rayon::prelude::*;
use serde_json::json;

use crate::table_access::{ColumnDescriptor, SqlLogicalType};

/// Canonical mapping profile version written to schema metadata.
pub const CANONICAL_MAPPING_VERSION: &str = "1";
/// Maximum number of rows in a record batch in mapping version 1.
pub const CANONICAL_IPC_BATCH_ROWS: usize = 65_536;

const SCHEMA_VERSION_KEY: &str = "gdds.canonical_mapping_version";
const FIELD_TYPE_KEY: &str = "gdds.canonical_type";
const ARROW_MAGIC: &[u8; 6] = b"ARROW1";
const IPC_EOS_MARKER: &[u8; 8] = &[0xff, 0xff, 0xff, 0xff, 0, 0, 0, 0];
const IPC_ALIGNMENT: usize = 64;
const MAX_POLL_INTERVAL: usize = 1024;

/// Failure class for the canonical IPC codec.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CanonicalIpcErrorKind {
    /// Descriptor, schema, metadata, or binding mismatch.
    Schema,
    /// A value does not fit its declared canonical mapping.
    Value,
    /// A local input, output, or allocation budget was exceeded.
    Resource,
    /// The caller's cancellation probe was set.
    Cancelled,
    /// The caller's finite monotonic deadline elapsed.
    Deadline,
    /// Arrow IPC bytes are malformed or outside the v1 profile.
    Ipc,
}

/// Structured failure from mapping, writing, or reading canonical IPC.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonicalIpcError {
    kind: CanonicalIpcErrorKind,
    message: String,
}

impl CanonicalIpcError {
    fn new(kind: CanonicalIpcErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }

    /// Returns the stable failure category.
    pub const fn kind(&self) -> CanonicalIpcErrorKind {
        self.kind
    }

    /// Returns a diagnostic message suitable for a local capability error.
    pub fn message(&self) -> &str {
        &self.message
    }
}

impl std::fmt::Display for CanonicalIpcError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{:?}: {}", self.kind, self.message)
    }
}

impl std::error::Error for CanonicalIpcError {}

/// Explicit local bounds for one in-memory encode or decode call.
///
/// `max_input_bytes` bounds borrowed input: encode sums every input Arrow array
/// occurrence (so shared backing buffers may count more than once), while decode
/// bounds the borrowed IPC file slice. `max_output_bytes` limits actual encoded
/// file bytes. `max_codec_peak_bytes` bounds codec-owned live memory using
/// checked conservative estimates. These local bounds do not claim a process RSS
/// or worker memory guarantee.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CanonicalIpcBudgets {
    /// Maximum total rows accepted in one table.
    pub max_rows: usize,
    /// Maximum number of fields.
    pub max_columns: usize,
    /// Maximum referenced bytes in the small canonical column descriptors.
    pub max_descriptor_bytes: usize,
    /// Maximum number of caller-provided record batches.
    pub max_input_batches: usize,
    /// Conservative upper bound for input Arrow array memory sizes.
    pub max_input_bytes: usize,
    /// Maximum final encoded IPC file length.
    pub max_output_bytes: usize,
    /// Maximum estimated live memory allocated by this codec.
    pub max_codec_peak_bytes: usize,
}

/// Per-call cancellation and finite-deadline controls.
#[derive(Debug, Clone, Copy, Default)]
pub struct CanonicalIpcControl<'a> {
    /// A caller-owned cooperative stop probe.
    pub cancel: Option<&'a AtomicBool>,
    /// A caller-owned monotonic deadline. `None` means no fixed deadline.
    pub deadline: Option<Instant>,
}

/// Local limits and controls for one canonical IPC operation.
#[derive(Debug, Clone, Copy)]
pub struct CanonicalIpcOptions<'a> {
    /// Explicit local resource bounds.
    pub budgets: CanonicalIpcBudgets,
    /// Cooperative operation control supplied by the caller.
    pub control: CanonicalIpcControl<'a>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ValueMapping {
    Signed { bits: u8 },
    Unsigned { bits: u8 },
    Boolean,
    Float32,
    Float64,
    Utf8,
    Binary,
    Bit { bit_width: u8, width: usize },
}

#[derive(Debug, Clone)]
struct ColumnPlan<'a> {
    descriptor: &'a ColumnDescriptor,
    mapping: ValueMapping,
    metadata: String,
    total_payload_bytes: usize,
    large_offsets: bool,
}

#[derive(Debug, Clone)]
struct BatchLayout {
    /// For every canonical field, the corresponding field index in the input batch.
    input_indices: Vec<usize>,
    row_count: usize,
}

#[derive(Debug, Clone, Copy)]
struct RowSpan {
    batch_index: usize,
    start: usize,
    len: usize,
}

fn schema_error(message: impl Into<String>) -> CanonicalIpcError {
    CanonicalIpcError::new(CanonicalIpcErrorKind::Schema, message)
}

fn value_error(message: impl Into<String>) -> CanonicalIpcError {
    CanonicalIpcError::new(CanonicalIpcErrorKind::Value, message)
}

fn resource_error(message: impl Into<String>) -> CanonicalIpcError {
    CanonicalIpcError::new(CanonicalIpcErrorKind::Resource, message)
}

fn ipc_error(message: impl Into<String>) -> CanonicalIpcError {
    CanonicalIpcError::new(CanonicalIpcErrorKind::Ipc, message)
}

fn check_control(control: CanonicalIpcControl<'_>) -> Result<(), CanonicalIpcError> {
    if control
        .cancel
        .is_some_and(|cancel| cancel.load(Ordering::Relaxed))
    {
        return Err(CanonicalIpcError::new(
            CanonicalIpcErrorKind::Cancelled,
            "canonical IPC operation was cancelled",
        ));
    }
    if control
        .deadline
        .is_some_and(|deadline| Instant::now() >= deadline)
    {
        return Err(CanonicalIpcError::new(
            CanonicalIpcErrorKind::Deadline,
            "canonical IPC operation deadline elapsed",
        ));
    }
    Ok(())
}

fn checked_add(left: usize, right: usize, description: &str) -> Result<usize, CanonicalIpcError> {
    left.checked_add(right)
        .ok_or_else(|| resource_error(format!("{description} size overflow")))
}

fn checked_mul(left: usize, right: usize, description: &str) -> Result<usize, CanonicalIpcError> {
    left.checked_mul(right)
        .ok_or_else(|| resource_error(format!("{description} size overflow")))
}

fn descriptor_metadata(
    column: &ColumnDescriptor,
    control: CanonicalIpcControl<'_>,
) -> Result<(ValueMapping, String), CanonicalIpcError> {
    check_control(control)?;
    if column.canonical_name.is_empty() {
        return Err(schema_error("canonical column name is empty"));
    }
    if column.sql_type.is_empty() {
        return Err(schema_error("canonical SQL type spelling is empty"));
    }

    let declared_metadata = column.declared_type_metadata();
    let labels_json = match column.logical_type {
        SqlLogicalType::Standard | SqlLogicalType::Json => {
            if column.labels.is_some() {
                return Err(schema_error("labels are only valid for ENUM and SET"));
            }
            json!(null)
        }
        SqlLogicalType::Enum | SqlLogicalType::Set => {
            let labels = column
                .labels
                .as_ref()
                .ok_or_else(|| schema_error("ENUM/SET labels are missing"))?;
            let unique = labels.iter().collect::<HashSet<_>>();
            if unique.len() != labels.len() {
                return Err(schema_error("ENUM/SET labels contain duplicates"));
            }
            if labels.is_empty() {
                return Err(schema_error("ENUM/SET labels must not be empty"));
            }
            match column.logical_type {
                SqlLogicalType::Enum if labels.len() > 65_535 => {
                    return Err(schema_error("ENUM label count exceeds the v1 limit"));
                }
                SqlLogicalType::Set if labels.len() > 64 => {
                    return Err(schema_error("SET label count exceeds the v1 limit"));
                }
                _ => {}
            }
            for label in labels {
                check_control(control)?;
                let scalar_count = label.chars().take(256).count();
                if scalar_count > 255 {
                    return Err(schema_error("ENUM/SET label exceeds the v1 length limit"));
                }
                if column.logical_type == SqlLogicalType::Set
                    && (label.is_empty() || label.contains(','))
                {
                    return Err(schema_error("SET labels cannot be empty or contain commas"));
                }
            }
            json!(labels)
        }
        SqlLogicalType::Unknown => {
            return Err(schema_error("unknown SQL logical type cannot be mapped"));
        }
    };

    let mapping = match column.logical_type {
        SqlLogicalType::Enum => {
            if !matches!(column.declared_type, Some(DeclaredType::String)) {
                return Err(schema_error("ENUM requires the declared string type"));
            }
            ValueMapping::Utf8
        }
        SqlLogicalType::Set => {
            if column.declared_type.is_some() {
                return Err(schema_error("SET must not have a declared scalar type"));
            }
            ValueMapping::Utf8
        }
        SqlLogicalType::Json => {
            if !matches!(column.declared_type, Some(DeclaredType::String)) {
                return Err(schema_error("JSON requires the declared string type"));
            }
            ValueMapping::Utf8
        }
        SqlLogicalType::Standard => {
            let declared = column
                .declared_type
                .as_ref()
                .ok_or_else(|| schema_error("standard type has no declared scalar type"))?;
            declared
                .validate()
                .map_err(|error| schema_error(error.to_string()))?;
            match declared {
                DeclaredType::SignedInteger { bits } => ValueMapping::Signed { bits: *bits },
                DeclaredType::UnsignedInteger { bits } => ValueMapping::Unsigned { bits: *bits },
                DeclaredType::Boolean => ValueMapping::Boolean,
                DeclaredType::Float32 => ValueMapping::Float32,
                DeclaredType::Float64 => ValueMapping::Float64,
                DeclaredType::Decimal { .. }
                | DeclaredType::String
                | DeclaredType::Date
                | DeclaredType::DateTime
                | DeclaredType::Timestamp
                | DeclaredType::TimeDuration => ValueMapping::Utf8,
                DeclaredType::Binary => ValueMapping::Binary,
                DeclaredType::Bit { bit_width } => ValueMapping::Bit {
                    bit_width: *bit_width,
                    width: usize::from(*bit_width).div_ceil(8),
                },
                DeclaredType::Null | DeclaredType::SourceLiteralAnomaly => {
                    return Err(schema_error("unsupported declared scalar type"));
                }
            }
        }
        SqlLogicalType::Unknown => {
            return Err(schema_error("unknown SQL logical type cannot be mapped"));
        }
    };

    let declared_json = match declared_metadata {
        Some(declared) => json!({
            "kind": declared.kind,
            "bits": declared.bits,
            "precision": declared.precision,
            "scale": declared.scale,
            "bit_width": declared.bit_width,
        }),
        None => json!(null),
    };
    let payload = serde_json::to_vec(&json!({
        "logical_type": column.logical_type.as_str(),
        "sql_type": column.sql_type.as_str(),
        "declared_type": declared_json,
        "labels": labels_json,
    }))
    .map_err(|error| {
        schema_error(format!(
            "canonical type metadata serialization failed: {error}"
        ))
    })?;
    let canonical = canonicalize_jcs(&payload).map_err(|error| {
        schema_error(format!(
            "canonical type metadata is invalid: {}",
            error.message()
        ))
    })?;
    let metadata = String::from_utf8(canonical)
        .map_err(|_| schema_error("canonical type metadata is not UTF-8"))?;
    Ok((mapping, metadata))
}

fn descriptor_size(
    columns: &[ColumnDescriptor],
    budgets: CanonicalIpcBudgets,
) -> Result<usize, CanonicalIpcError> {
    if columns.len() > budgets.max_columns {
        return Err(resource_error("canonical IPC column limit exceeded"));
    }
    let mut descriptor_bytes = 0_usize;
    for column in columns {
        descriptor_bytes = checked_add(
            descriptor_bytes,
            column.canonical_name.len(),
            "canonical descriptor",
        )?;
        descriptor_bytes = checked_add(
            descriptor_bytes,
            column.sql_type.len(),
            "canonical descriptor",
        )?;
        descriptor_bytes = checked_add(descriptor_bytes, 128, "canonical descriptor")?;
        if let Some(labels) = &column.labels {
            descriptor_bytes = checked_add(
                descriptor_bytes,
                checked_mul(
                    labels.len(),
                    std::mem::size_of::<String>(),
                    "canonical labels",
                )?,
                "canonical descriptor",
            )?;
            for label in labels {
                descriptor_bytes =
                    checked_add(descriptor_bytes, label.len(), "canonical descriptor")?;
            }
        }
    }
    if descriptor_bytes > budgets.max_descriptor_bytes {
        return Err(resource_error("canonical descriptor byte limit exceeded"));
    }
    Ok(descriptor_bytes)
}

fn canonical_plans<'a>(
    columns: &'a [ColumnDescriptor],
    descriptor_bytes: usize,
    budgets: CanonicalIpcBudgets,
    control: CanonicalIpcControl<'_>,
) -> Result<Vec<ColumnPlan<'a>>, CanonicalIpcError> {
    let escaped_bytes = checked_mul(descriptor_bytes, 6, "canonical metadata escaping")?;
    let metadata_peak = checked_add(
        checked_mul(escaped_bytes, 4, "canonical descriptor metadata")?,
        checked_mul(columns.len(), 4096, "canonical descriptor metadata")?,
        "canonical descriptor metadata",
    )?;
    reserve_peak(budgets, 0, metadata_peak)?;
    let mut plans = columns
        .iter()
        .map(|descriptor| {
            check_control(control)?;
            let (mapping, metadata) = descriptor_metadata(descriptor, control)?;
            Ok(ColumnPlan {
                descriptor,
                mapping,
                metadata,
                total_payload_bytes: 0,
                large_offsets: false,
            })
        })
        .collect::<Result<Vec<_>, CanonicalIpcError>>()?;
    plans.sort_by(|left, right| {
        left.descriptor
            .canonical_name
            .as_bytes()
            .cmp(right.descriptor.canonical_name.as_bytes())
    });
    for pair in plans.windows(2) {
        if pair[0].descriptor.canonical_name == pair[1].descriptor.canonical_name {
            return Err(schema_error("canonical column names are duplicated"));
        }
    }
    Ok(plans)
}

fn output_type(plan: &ColumnPlan<'_>) -> DataType {
    match plan.mapping {
        ValueMapping::Signed { .. } => DataType::Int64,
        ValueMapping::Unsigned { .. } => DataType::UInt64,
        ValueMapping::Boolean => DataType::Boolean,
        ValueMapping::Float32 => DataType::Float32,
        ValueMapping::Float64 => DataType::Float64,
        ValueMapping::Utf8 => {
            if plan.large_offsets {
                DataType::LargeUtf8
            } else {
                DataType::Utf8
            }
        }
        ValueMapping::Binary => {
            if plan.large_offsets {
                DataType::LargeBinary
            } else {
                DataType::Binary
            }
        }
        ValueMapping::Bit { width, .. } => DataType::FixedSizeBinary(width as i32),
    }
}

fn arrow_schema(plans: &[ColumnPlan<'_>]) -> Result<SchemaRef, CanonicalIpcError> {
    let mut fields = Vec::with_capacity(plans.len());
    for plan in plans {
        let mut metadata = HashMap::new();
        metadata.insert(FIELD_TYPE_KEY.to_owned(), plan.metadata.clone());
        fields.push(
            Field::new(
                plan.descriptor.canonical_name.as_str(),
                output_type(plan),
                plan.descriptor.nullable,
            )
            .with_metadata(metadata),
        );
    }
    let mut metadata = HashMap::new();
    metadata.insert(
        SCHEMA_VERSION_KEY.to_owned(),
        CANONICAL_MAPPING_VERSION.to_owned(),
    );
    Ok(Arc::new(Schema::new_with_metadata(fields, metadata)))
}

fn accepts_input_type(mapping: ValueMapping, actual: &DataType) -> bool {
    match mapping {
        ValueMapping::Signed { .. } => actual == &DataType::Int64,
        ValueMapping::Unsigned { .. } => actual == &DataType::UInt64,
        ValueMapping::Boolean => actual == &DataType::Boolean,
        ValueMapping::Float32 => actual == &DataType::Float32,
        ValueMapping::Float64 => actual == &DataType::Float64,
        ValueMapping::Utf8 => matches!(actual, DataType::Utf8 | DataType::LargeUtf8),
        ValueMapping::Binary => matches!(actual, DataType::Binary | DataType::LargeBinary),
        ValueMapping::Bit { width, .. } => {
            matches!(actual, DataType::Binary | DataType::LargeBinary)
                || actual == &DataType::FixedSizeBinary(width as i32)
        }
    }
}

fn input_array<'a>(batch: &'a RecordBatch, index: usize) -> &'a ArrayRef {
    batch.column(index)
}

fn map_input_fields(
    batch: &RecordBatch,
    plans: &[ColumnPlan<'_>],
) -> Result<Vec<usize>, CanonicalIpcError> {
    if batch.num_columns() != plans.len() {
        return Err(schema_error(
            "input batch field count does not match descriptor",
        ));
    }
    let mut input_indices = vec![usize::MAX; plans.len()];
    for (input_index, field) in batch.schema().fields().iter().enumerate() {
        let plan_index = plans
            .binary_search_by(|plan| {
                plan.descriptor
                    .canonical_name
                    .as_bytes()
                    .cmp(field.name().as_bytes())
            })
            .map_err(|_| schema_error("input batch contains an unbound field name"))?;
        if input_indices[plan_index] != usize::MAX {
            return Err(schema_error(
                "input batch contains duplicate canonical fields",
            ));
        }
        let plan = &plans[plan_index];
        if field.is_nullable() != plan.descriptor.nullable {
            return Err(schema_error(format!(
                "input nullability does not match field {}",
                field.name()
            )));
        }
        if !accepts_input_type(plan.mapping, field.data_type()) {
            return Err(schema_error(format!(
                "input Arrow type does not match field {} mapping",
                field.name()
            )));
        }
        input_indices[plan_index] = input_index;
    }
    if input_indices.iter().any(|index| *index == usize::MAX) {
        return Err(schema_error("input batch is missing a bound field"));
    }
    Ok(input_indices)
}

fn signed_fits(value: i64, bits: u8) -> bool {
    if bits == 64 {
        return true;
    }
    let limit = 1_i64 << (bits - 1);
    value >= -limit && value < limit
}

fn unsigned_fits(value: u64, bits: u8) -> bool {
    bits == 64 || value < (1_u64 << bits)
}

fn bit_payload_valid(bytes: &[u8], bit_width: u8) -> bool {
    let expected_bytes = usize::from(bit_width).div_ceil(8);
    if bytes.len() != expected_bytes {
        return false;
    }
    let mut magnitude = 0_u128;
    for byte in bytes {
        magnitude = (magnitude << 8) | u128::from(*byte);
    }
    magnitude >> bit_width == 0
}

fn enum_value_declared(value: &str, column: &ColumnDescriptor) -> bool {
    column
        .labels
        .as_ref()
        .is_some_and(|labels| labels.iter().any(|label| label == value))
}

fn set_value_canonical(value: &str, column: &ColumnDescriptor) -> bool {
    if value.is_empty() {
        return true;
    }
    let Some(labels) = column.labels.as_ref() else {
        return false;
    };
    let mut previous_index = None;
    for member in value.split(',') {
        if member.is_empty() {
            return false;
        }
        let Some(index) = labels.iter().position(|label| label == member) else {
            return false;
        };
        if previous_index.is_some_and(|previous| previous >= index) {
            return false;
        }
        previous_index = Some(index);
    }
    true
}

fn add_payload_bytes(
    plan: &mut ColumnPlan<'_>,
    value_bytes: usize,
) -> Result<(), CanonicalIpcError> {
    plan.total_payload_bytes = checked_add(
        plan.total_payload_bytes,
        value_bytes,
        "canonical column payload",
    )?;
    Ok(())
}

fn inspect_input_array(
    plan: &ColumnPlan<'_>,
    array: &ArrayRef,
    control: CanonicalIpcControl<'_>,
) -> Result<usize, CanonicalIpcError> {
    let mut payload_bytes = 0_usize;
    if array.null_count() > 0 && !plan.descriptor.nullable {
        return Err(value_error(format!(
            "non-nullable field {} contains NULL",
            plan.descriptor.canonical_name
        )));
    }
    match plan.mapping {
        ValueMapping::Signed { bits } => {
            let values = array
                .as_any()
                .downcast_ref::<Int64Array>()
                .ok_or_else(|| schema_error("signed Arrow array has an unexpected type"))?;
            for index in 0..values.len() {
                if index % MAX_POLL_INTERVAL == 0 {
                    check_control(control)?;
                }
                if values.is_valid(index) && !signed_fits(values.value(index), bits) {
                    return Err(value_error(format!(
                        "value exceeds declared integer width for {}",
                        plan.descriptor.canonical_name
                    )));
                }
            }
        }
        ValueMapping::Unsigned { bits } => {
            let values = array
                .as_any()
                .downcast_ref::<UInt64Array>()
                .ok_or_else(|| schema_error("unsigned Arrow array has an unexpected type"))?;
            for index in 0..values.len() {
                if index % MAX_POLL_INTERVAL == 0 {
                    check_control(control)?;
                }
                if values.is_valid(index) && !unsigned_fits(values.value(index), bits) {
                    return Err(value_error(format!(
                        "value exceeds declared integer width for {}",
                        plan.descriptor.canonical_name
                    )));
                }
            }
        }
        ValueMapping::Float32 => {
            let values = array
                .as_any()
                .downcast_ref::<Float32Array>()
                .ok_or_else(|| schema_error("Float32 Arrow array has an unexpected type"))?;
            for index in 0..values.len() {
                if index % MAX_POLL_INTERVAL == 0 {
                    check_control(control)?;
                }
                if values.is_valid(index) && !values.value(index).is_finite() {
                    return Err(value_error(format!(
                        "non-finite FLOAT value for {}",
                        plan.descriptor.canonical_name
                    )));
                }
            }
        }
        ValueMapping::Float64 => {
            let values = array
                .as_any()
                .downcast_ref::<Float64Array>()
                .ok_or_else(|| schema_error("Float64 Arrow array has an unexpected type"))?;
            for index in 0..values.len() {
                if index % MAX_POLL_INTERVAL == 0 {
                    check_control(control)?;
                }
                if values.is_valid(index) && !values.value(index).is_finite() {
                    return Err(value_error(format!(
                        "non-finite DOUBLE value for {}",
                        plan.descriptor.canonical_name
                    )));
                }
            }
        }
        ValueMapping::Utf8 => {
            if let Some(values) = array.as_any().downcast_ref::<StringArray>() {
                for index in 0..values.len() {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(index) {
                        if plan.descriptor.logical_type == SqlLogicalType::Enum
                            && !enum_value_declared(values.value(index), plan.descriptor)
                        {
                            return Err(value_error(format!(
                                "ENUM value is not declared for {}",
                                plan.descriptor.canonical_name
                            )));
                        }
                        if plan.descriptor.logical_type == SqlLogicalType::Set
                            && !set_value_canonical(values.value(index), plan.descriptor)
                        {
                            return Err(value_error(format!(
                                "SET value is not in declaration order for {}",
                                plan.descriptor.canonical_name
                            )));
                        }
                        payload_bytes = checked_add(
                            payload_bytes,
                            values.value(index).len(),
                            "canonical column payload",
                        )?;
                    }
                }
            } else if let Some(values) = array.as_any().downcast_ref::<LargeStringArray>() {
                for index in 0..values.len() {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(index) {
                        if plan.descriptor.logical_type == SqlLogicalType::Enum
                            && !enum_value_declared(values.value(index), plan.descriptor)
                        {
                            return Err(value_error(format!(
                                "ENUM value is not declared for {}",
                                plan.descriptor.canonical_name
                            )));
                        }
                        if plan.descriptor.logical_type == SqlLogicalType::Set
                            && !set_value_canonical(values.value(index), plan.descriptor)
                        {
                            return Err(value_error(format!(
                                "SET value is not in declaration order for {}",
                                plan.descriptor.canonical_name
                            )));
                        }
                        payload_bytes = checked_add(
                            payload_bytes,
                            values.value(index).len(),
                            "canonical column payload",
                        )?;
                    }
                }
            } else {
                return Err(schema_error("UTF-8 Arrow array has an unexpected type"));
            }
        }
        ValueMapping::Binary => {
            if let Some(values) = array.as_any().downcast_ref::<BinaryArray>() {
                for index in 0..values.len() {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(index) {
                        payload_bytes = checked_add(
                            payload_bytes,
                            values.value(index).len(),
                            "canonical column payload",
                        )?;
                    }
                }
            } else if let Some(values) = array.as_any().downcast_ref::<LargeBinaryArray>() {
                for index in 0..values.len() {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(index) {
                        payload_bytes = checked_add(
                            payload_bytes,
                            values.value(index).len(),
                            "canonical column payload",
                        )?;
                    }
                }
            } else {
                return Err(schema_error("binary Arrow array has an unexpected type"));
            }
        }
        ValueMapping::Bit { bit_width, width } => {
            if let Some(values) = array.as_any().downcast_ref::<BinaryArray>() {
                for index in 0..values.len() {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(index) && !bit_payload_valid(values.value(index), bit_width)
                    {
                        return Err(value_error(format!(
                            "BIT payload does not match declared width for {}",
                            plan.descriptor.canonical_name
                        )));
                    }
                }
            } else if let Some(values) = array.as_any().downcast_ref::<LargeBinaryArray>() {
                for index in 0..values.len() {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(index) && !bit_payload_valid(values.value(index), bit_width)
                    {
                        return Err(value_error(format!(
                            "BIT payload does not match declared width for {}",
                            plan.descriptor.canonical_name
                        )));
                    }
                }
            } else if let Some(values) = array.as_any().downcast_ref::<FixedSizeBinaryArray>() {
                if usize::try_from(values.value_length()).ok() != Some(width) {
                    return Err(value_error(format!(
                        "BIT payload width does not match {}",
                        plan.descriptor.canonical_name
                    )));
                }
                for index in 0..values.len() {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(index) && !bit_payload_valid(values.value(index), bit_width)
                    {
                        return Err(value_error(format!(
                            "BIT payload does not match declared width for {}",
                            plan.descriptor.canonical_name
                        )));
                    }
                }
            } else {
                return Err(schema_error("BIT Arrow array has an unexpected type"));
            }
        }
        ValueMapping::Boolean => {
            if array.as_any().downcast_ref::<BooleanArray>().is_none() {
                return Err(schema_error("Boolean Arrow array has an unexpected type"));
            }
        }
    }
    Ok(payload_bytes)
}

fn inspect_input(
    plans: &mut [ColumnPlan<'_>],
    batches: &[RecordBatch],
    options: CanonicalIpcOptions<'_>,
    live_bytes: usize,
) -> Result<(Vec<BatchLayout>, usize, usize, usize), CanonicalIpcError> {
    if batches.len() > options.budgets.max_input_batches {
        return Err(resource_error("canonical IPC input batch limit exceeded"));
    }
    let layout_indexes = checked_mul(
        checked_mul(batches.len(), plans.len(), "canonical input layout")?,
        std::mem::size_of::<usize>(),
        "canonical input layout",
    )?;
    let layout_headers = checked_mul(
        batches.len(),
        std::mem::size_of::<BatchLayout>(),
        "canonical input layout",
    )?;
    reserve_peak(
        options.budgets,
        live_bytes,
        checked_add(layout_indexes, layout_headers, "canonical input layout")?,
    )?;
    let mut layouts = Vec::with_capacity(batches.len());
    let mut total_rows = 0_usize;
    let mut input_bytes = 0_usize;
    for batch in batches {
        check_control(options.control)?;
        let indices = map_input_fields(batch, plans)?;
        total_rows = checked_add(total_rows, batch.num_rows(), "canonical IPC row count")?;
        if total_rows > options.budgets.max_rows {
            return Err(resource_error("canonical IPC row limit exceeded"));
        }
        for (plan_index, input_index) in indices.iter().copied().enumerate() {
            let array = input_array(batch, input_index);
            input_bytes = checked_add(
                input_bytes,
                array.get_array_memory_size(),
                "canonical IPC input array",
            )?;
            if input_bytes > options.budgets.max_input_bytes {
                return Err(resource_error("canonical IPC input byte limit exceeded"));
            }
            let payload_bytes = inspect_input_array(&plans[plan_index], array, options.control)?;
            add_payload_bytes(&mut plans[plan_index], payload_bytes)?;
        }
        layouts.push(BatchLayout {
            input_indices: indices,
            row_count: batch.num_rows(),
        });
    }
    for plan in plans {
        plan.large_offsets = plan.total_payload_bytes > i32::MAX as usize;
    }
    let layout_bytes = checked_add(layout_indexes, layout_headers, "canonical input layout")?;
    Ok((layouts, total_rows, input_bytes, layout_bytes))
}

fn string_or_binary_payload(
    plan: &ColumnPlan<'_>,
    array: &ArrayRef,
    start: usize,
    end: usize,
    control: CanonicalIpcControl<'_>,
) -> Result<usize, CanonicalIpcError> {
    let mut payload_bytes = 0_usize;
    match plan.mapping {
        ValueMapping::Utf8 => {
            if let Some(values) = array.as_any().downcast_ref::<StringArray>() {
                for row in start..end {
                    if row % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(row) {
                        payload_bytes = checked_add(
                            payload_bytes,
                            values.value(row).len(),
                            "canonical batch payload",
                        )?;
                    }
                }
            } else if let Some(values) = array.as_any().downcast_ref::<LargeStringArray>() {
                for row in start..end {
                    if row % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(row) {
                        payload_bytes = checked_add(
                            payload_bytes,
                            values.value(row).len(),
                            "canonical batch payload",
                        )?;
                    }
                }
            }
        }
        ValueMapping::Binary => {
            if let Some(values) = array.as_any().downcast_ref::<BinaryArray>() {
                for row in start..end {
                    if row % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(row) {
                        payload_bytes = checked_add(
                            payload_bytes,
                            values.value(row).len(),
                            "canonical batch payload",
                        )?;
                    }
                }
            } else if let Some(values) = array.as_any().downcast_ref::<LargeBinaryArray>() {
                for row in start..end {
                    if row % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_valid(row) {
                        payload_bytes = checked_add(
                            payload_bytes,
                            values.value(row).len(),
                            "canonical batch payload",
                        )?;
                    }
                }
            }
        }
        _ => {}
    }
    Ok(payload_bytes)
}

fn array_buffer_estimate(
    mapping: ValueMapping,
    large_offsets: bool,
    rows: usize,
    payload_bytes: usize,
) -> Result<usize, CanonicalIpcError> {
    let validity = rows.div_ceil(8);
    let value_bytes = match mapping {
        ValueMapping::Signed { .. } | ValueMapping::Unsigned { .. } | ValueMapping::Float64 => {
            checked_mul(rows, 8, "canonical array")?
        }
        ValueMapping::Float32 => checked_mul(rows, 4, "canonical array")?,
        ValueMapping::Boolean => rows.div_ceil(8),
        ValueMapping::Utf8 | ValueMapping::Binary => {
            let offset_width = if large_offsets { 8 } else { 4 };
            let offsets = checked_mul(
                checked_add(rows, 1, "canonical offsets")?,
                offset_width,
                "canonical offsets",
            )?;
            checked_add(offsets, payload_bytes, "canonical byte array")?
        }
        ValueMapping::Bit { width, .. } => checked_mul(rows, width, "canonical BIT array")?,
    };
    checked_add(value_bytes, validity, "canonical array")
}

fn buffer_count(mapping: ValueMapping) -> usize {
    match mapping {
        ValueMapping::Utf8 | ValueMapping::Binary => 3,
        ValueMapping::Signed { .. }
        | ValueMapping::Unsigned { .. }
        | ValueMapping::Boolean
        | ValueMapping::Float32
        | ValueMapping::Float64
        | ValueMapping::Bit { .. } => 2,
    }
}

fn schema_metadata_estimate(plans: &[ColumnPlan<'_>]) -> Result<usize, CanonicalIpcError> {
    let mut estimate = 4096_usize;
    for plan in plans {
        estimate = checked_add(
            estimate,
            plan.descriptor.canonical_name.len(),
            "IPC schema metadata",
        )?;
        estimate = checked_add(estimate, plan.metadata.len(), "IPC schema metadata")?;
        estimate = checked_add(estimate, 512, "IPC schema metadata")?;
    }
    checked_add(
        estimate,
        SCHEMA_VERSION_KEY.len() + CANONICAL_MAPPING_VERSION.len(),
        "IPC schema metadata",
    )
}

fn reserve_peak(
    budgets: CanonicalIpcBudgets,
    live_bytes: usize,
    requested_bytes: usize,
) -> Result<(), CanonicalIpcError> {
    let peak = checked_add(live_bytes, requested_bytes, "canonical IPC codec peak")?;
    if peak > budgets.max_codec_peak_bytes {
        return Err(resource_error("canonical IPC codec peak limit exceeded"));
    }
    Ok(())
}

#[derive(Debug)]
struct BudgetedVecWriter {
    bytes: Vec<u8>,
    max_output_bytes: usize,
    budget_failure: bool,
}

impl BudgetedVecWriter {
    fn new(max_output_bytes: usize) -> Self {
        Self {
            bytes: Vec::new(),
            max_output_bytes,
            budget_failure: false,
        }
    }

    fn into_bytes(self) -> Vec<u8> {
        self.bytes
    }
}

impl Write for BudgetedVecWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let new_len = self.bytes.len().checked_add(bytes.len()).ok_or_else(|| {
            self.budget_failure = true;
            io::Error::other("canonical IPC output length overflow")
        })?;
        if new_len > self.max_output_bytes {
            self.budget_failure = true;
            return Err(io::Error::other("canonical IPC output limit exceeded"));
        }
        if self.bytes.try_reserve_exact(bytes.len()).is_err() {
            self.budget_failure = true;
            return Err(io::Error::other("canonical IPC output allocation failed"));
        }
        self.bytes.extend_from_slice(bytes);
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn writer_error(error: arrow_schema::ArrowError, writer: &BudgetedVecWriter) -> CanonicalIpcError {
    if writer.budget_failure {
        resource_error(error.to_string())
    } else {
        ipc_error(error.to_string())
    }
}

struct RowSpanCursor {
    batch_index: usize,
    row_index: usize,
}

impl RowSpanCursor {
    fn next(&mut self, layouts: &[BatchLayout], rows: usize) -> Vec<RowSpan> {
        let mut spans = Vec::new();
        let mut remaining = rows;
        while remaining > 0 && self.batch_index < layouts.len() {
            let batch = &layouts[self.batch_index];
            if self.row_index >= batch.row_count {
                self.batch_index += 1;
                self.row_index = 0;
                continue;
            }
            let available = batch.row_count - self.row_index;
            let take = available.min(remaining);
            spans.push(RowSpan {
                batch_index: self.batch_index,
                start: self.row_index,
                len: take,
            });
            self.row_index += take;
            remaining -= take;
        }
        spans
    }
}

enum CanonicalBuilder {
    Signed(Int64Builder),
    Unsigned(UInt64Builder),
    Boolean(BooleanBuilder),
    Float32(Float32Builder),
    Float64(Float64Builder),
    Utf8Small(StringBuilder),
    Utf8Large(LargeStringBuilder),
    BinarySmall(BinaryBuilder),
    BinaryLarge(LargeBinaryBuilder),
    Bit(FixedSizeBinaryBuilder),
}

impl CanonicalBuilder {
    fn new(
        plan: &ColumnPlan<'_>,
        rows: usize,
        payload_bytes: usize,
    ) -> Result<Self, CanonicalIpcError> {
        Ok(match plan.mapping {
            ValueMapping::Signed { .. } => Self::Signed(Int64Builder::with_capacity(rows)),
            ValueMapping::Unsigned { .. } => Self::Unsigned(UInt64Builder::with_capacity(rows)),
            ValueMapping::Boolean => Self::Boolean(BooleanBuilder::with_capacity(rows)),
            ValueMapping::Float32 => Self::Float32(Float32Builder::with_capacity(rows)),
            ValueMapping::Float64 => Self::Float64(Float64Builder::with_capacity(rows)),
            ValueMapping::Utf8 if plan.large_offsets => {
                Self::Utf8Large(LargeStringBuilder::with_capacity(rows, payload_bytes))
            }
            ValueMapping::Utf8 => {
                Self::Utf8Small(StringBuilder::with_capacity(rows, payload_bytes))
            }
            ValueMapping::Binary if plan.large_offsets => {
                Self::BinaryLarge(LargeBinaryBuilder::with_capacity(rows, payload_bytes))
            }
            ValueMapping::Binary => {
                Self::BinarySmall(BinaryBuilder::with_capacity(rows, payload_bytes))
            }
            ValueMapping::Bit { width, .. } => Self::Bit(FixedSizeBinaryBuilder::with_capacity(
                rows,
                i32::try_from(width)
                    .map_err(|_| schema_error("BIT width is outside Arrow range"))?,
            )),
        })
    }

    fn append_span(
        &mut self,
        plan: &ColumnPlan<'_>,
        array: &ArrayRef,
        start: usize,
        len: usize,
        control: CanonicalIpcControl<'_>,
    ) -> Result<(), CanonicalIpcError> {
        let end = checked_add(start, len, "canonical input span")?;
        match self {
            Self::Signed(builder) => {
                let values = array
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .ok_or_else(|| schema_error("signed Arrow array changed type"))?;
                for index in start..end {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_null(index) {
                        builder.append_null();
                    } else {
                        builder.append_value(values.value(index));
                    }
                }
            }
            Self::Unsigned(builder) => {
                let values = array
                    .as_any()
                    .downcast_ref::<UInt64Array>()
                    .ok_or_else(|| schema_error("unsigned Arrow array changed type"))?;
                for index in start..end {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_null(index) {
                        builder.append_null();
                    } else {
                        builder.append_value(values.value(index));
                    }
                }
            }
            Self::Boolean(builder) => {
                let values = array
                    .as_any()
                    .downcast_ref::<BooleanArray>()
                    .ok_or_else(|| schema_error("Boolean Arrow array changed type"))?;
                for index in start..end {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_null(index) {
                        builder.append_null();
                    } else {
                        builder.append_value(values.value(index));
                    }
                }
            }
            Self::Float32(builder) => {
                let values = array
                    .as_any()
                    .downcast_ref::<Float32Array>()
                    .ok_or_else(|| schema_error("Float32 Arrow array changed type"))?;
                for index in start..end {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_null(index) {
                        builder.append_null();
                    } else {
                        let value = values.value(index);
                        if !value.is_finite() {
                            return Err(value_error(format!(
                                "non-finite FLOAT value for {}",
                                plan.descriptor.canonical_name
                            )));
                        }
                        builder.append_value(if value == 0.0 { 0.0 } else { value });
                    }
                }
            }
            Self::Float64(builder) => {
                let values = array
                    .as_any()
                    .downcast_ref::<Float64Array>()
                    .ok_or_else(|| schema_error("Float64 Arrow array changed type"))?;
                for index in start..end {
                    if index % MAX_POLL_INTERVAL == 0 {
                        check_control(control)?;
                    }
                    if values.is_null(index) {
                        builder.append_null();
                    } else {
                        let value = values.value(index);
                        if !value.is_finite() {
                            return Err(value_error(format!(
                                "non-finite DOUBLE value for {}",
                                plan.descriptor.canonical_name
                            )));
                        }
                        builder.append_value(if value == 0.0 { 0.0 } else { value });
                    }
                }
            }
            Self::Utf8Small(builder) => {
                append_utf8_small(builder, array, start, end, control)?;
            }
            Self::Utf8Large(builder) => {
                append_utf8_large(builder, array, start, end, control)?;
            }
            Self::BinarySmall(builder) => {
                append_binary_small(builder, array, start, end, control)?;
            }
            Self::BinaryLarge(builder) => {
                append_binary_large(builder, array, start, end, control)?;
            }
            Self::Bit(builder) => {
                append_bit(builder, array, start, end, control, plan)?;
            }
        }
        Ok(())
    }

    fn finish(self) -> ArrayRef {
        match self {
            Self::Signed(mut builder) => Arc::new(builder.finish()),
            Self::Unsigned(mut builder) => Arc::new(builder.finish()),
            Self::Boolean(mut builder) => Arc::new(builder.finish()),
            Self::Float32(mut builder) => Arc::new(builder.finish()),
            Self::Float64(mut builder) => Arc::new(builder.finish()),
            Self::Utf8Small(mut builder) => Arc::new(builder.finish()),
            Self::Utf8Large(mut builder) => Arc::new(builder.finish()),
            Self::BinarySmall(mut builder) => Arc::new(builder.finish()),
            Self::BinaryLarge(mut builder) => Arc::new(builder.finish()),
            Self::Bit(mut builder) => Arc::new(builder.finish()),
        }
    }
}

fn append_utf8_small(
    builder: &mut StringBuilder,
    array: &ArrayRef,
    start: usize,
    end: usize,
    control: CanonicalIpcControl<'_>,
) -> Result<(), CanonicalIpcError> {
    if let Some(values) = array.as_any().downcast_ref::<StringArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder.append_value(values.value(index));
            }
        }
    } else if let Some(values) = array.as_any().downcast_ref::<LargeStringArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder.append_value(values.value(index));
            }
        }
    } else {
        return Err(schema_error("UTF-8 Arrow array changed type"));
    }
    Ok(())
}

fn append_utf8_large(
    builder: &mut LargeStringBuilder,
    array: &ArrayRef,
    start: usize,
    end: usize,
    control: CanonicalIpcControl<'_>,
) -> Result<(), CanonicalIpcError> {
    if let Some(values) = array.as_any().downcast_ref::<StringArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder.append_value(values.value(index));
            }
        }
    } else if let Some(values) = array.as_any().downcast_ref::<LargeStringArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder.append_value(values.value(index));
            }
        }
    } else {
        return Err(schema_error("UTF-8 Arrow array changed type"));
    }
    Ok(())
}

fn append_binary_small(
    builder: &mut BinaryBuilder,
    array: &ArrayRef,
    start: usize,
    end: usize,
    control: CanonicalIpcControl<'_>,
) -> Result<(), CanonicalIpcError> {
    if let Some(values) = array.as_any().downcast_ref::<BinaryArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder.append_value(values.value(index));
            }
        }
    } else if let Some(values) = array.as_any().downcast_ref::<LargeBinaryArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder.append_value(values.value(index));
            }
        }
    } else {
        return Err(schema_error("binary Arrow array changed type"));
    }
    Ok(())
}

fn append_binary_large(
    builder: &mut LargeBinaryBuilder,
    array: &ArrayRef,
    start: usize,
    end: usize,
    control: CanonicalIpcControl<'_>,
) -> Result<(), CanonicalIpcError> {
    if let Some(values) = array.as_any().downcast_ref::<BinaryArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder.append_value(values.value(index));
            }
        }
    } else if let Some(values) = array.as_any().downcast_ref::<LargeBinaryArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder.append_value(values.value(index));
            }
        }
    } else {
        return Err(schema_error("binary Arrow array changed type"));
    }
    Ok(())
}

fn append_bit(
    builder: &mut FixedSizeBinaryBuilder,
    array: &ArrayRef,
    start: usize,
    end: usize,
    control: CanonicalIpcControl<'_>,
    plan: &ColumnPlan<'_>,
) -> Result<(), CanonicalIpcError> {
    if let Some(values) = array.as_any().downcast_ref::<BinaryArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder
                    .append_value(values.value(index))
                    .map_err(|error| value_error(error.to_string()))?;
            }
        }
    } else if let Some(values) = array.as_any().downcast_ref::<LargeBinaryArray>() {
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder
                    .append_value(values.value(index))
                    .map_err(|error| value_error(error.to_string()))?;
            }
        }
    } else if let Some(values) = array.as_any().downcast_ref::<FixedSizeBinaryArray>() {
        let expected_width = match plan.mapping {
            ValueMapping::Bit { width, .. } => i32::try_from(width)
                .map_err(|_| schema_error("BIT width is outside Arrow range"))?,
            _ => return Err(schema_error("non-BIT descriptor reached BIT writer")),
        };
        if values.value_length() != expected_width {
            return Err(value_error(
                "BIT fixed-width input has an inconsistent width",
            ));
        }
        for index in start..end {
            if index % MAX_POLL_INTERVAL == 0 {
                check_control(control)?;
            }
            if values.is_null(index) {
                builder.append_null();
            } else {
                builder
                    .append_value(values.value(index))
                    .map_err(|error| value_error(error.to_string()))?;
            }
        }
    } else {
        return Err(schema_error("BIT Arrow array changed type"));
    }
    Ok(())
}

fn spans_for_column_payload(
    plan: &ColumnPlan<'_>,
    plan_index: usize,
    spans: &[RowSpan],
    batches: &[RecordBatch],
    layouts: &[BatchLayout],
    control: CanonicalIpcControl<'_>,
) -> Result<usize, CanonicalIpcError> {
    let mut payload = 0_usize;
    for span in spans {
        let input_index = layouts[span.batch_index].input_indices[plan_index];
        let array = input_array(&batches[span.batch_index], input_index);
        payload = checked_add(
            payload,
            string_or_binary_payload(plan, array, span.start, span.start + span.len, control)?,
            "canonical batch payload",
        )?;
    }
    Ok(payload)
}

fn build_output_batch(
    plans: &[ColumnPlan<'_>],
    schema: &SchemaRef,
    spans: &[RowSpan],
    rows: usize,
    batches: &[RecordBatch],
    layouts: &[BatchLayout],
    pool: &ThreadPool,
    options: CanonicalIpcOptions<'_>,
    live_bytes: usize,
    output_bytes: usize,
) -> Result<RecordBatch, CanonicalIpcError> {
    let span_bytes = checked_mul(
        spans.len(),
        std::mem::size_of::<RowSpan>(),
        "canonical batch row spans",
    )?;
    let payload_bytes = checked_mul(
        plans.len(),
        std::mem::size_of::<usize>(),
        "canonical batch payload counts",
    )?;
    reserve_peak(
        options.budgets,
        checked_add(live_bytes, output_bytes, "canonical IPC live output")?,
        checked_add(span_bytes, payload_bytes, "canonical IPC batch scratch")?,
    )?;
    let mut payloads = Vec::with_capacity(plans.len());
    for (plan_index, plan) in plans.iter().enumerate() {
        payloads.push(spans_for_column_payload(
            plan,
            plan_index,
            spans,
            batches,
            layouts,
            options.control,
        )?);
    }

    let mut array_estimate = 0_usize;
    let mut writer_padding = 0_usize;
    for (plan, payload_bytes) in plans.iter().zip(&payloads) {
        array_estimate = checked_add(
            array_estimate,
            array_buffer_estimate(plan.mapping, plan.large_offsets, rows, *payload_bytes)?,
            "canonical batch arrays",
        )?;
        writer_padding = checked_add(
            writer_padding,
            checked_mul(
                buffer_count(plan.mapping),
                IPC_ALIGNMENT,
                "IPC buffer alignment",
            )?,
            "IPC buffer alignment",
        )?;
    }
    let message_overhead = checked_add(
        4096,
        checked_mul(plans.len(), 256, "IPC batch metadata")?,
        "IPC batch metadata",
    )?;
    let writer_temporary = checked_add(
        checked_add(array_estimate, writer_padding, "IPC batch body")?,
        message_overhead,
        "IPC batch message",
    )?;
    let batch_array_peak = checked_add(
        array_estimate,
        checked_add(span_bytes, payload_bytes, "IPC batch scratch")?,
        "canonical batch arrays",
    )?;
    let output_growth = writer_temporary;
    // Arrow's EncodedData buffers grow as it appends buffers, and the output
    // sink can reallocate while the old output allocation is still live.
    // Bound both capacities conservatively before constructing the batch.
    let encoded_capacity = checked_mul(writer_temporary, 2, "IPC encoded data capacity")?;
    let old_output_capacity = checked_mul(output_bytes, 2, "IPC output capacity")?;
    let new_output_capacity = checked_mul(
        checked_add(output_bytes, output_growth, "IPC output growth")?,
        2,
        "IPC output growth capacity",
    )?;
    let peak_request = checked_add(
        checked_add(
            batch_array_peak,
            encoded_capacity,
            "canonical IPC batch peak",
        )?,
        checked_add(
            old_output_capacity,
            new_output_capacity,
            "canonical IPC output peak",
        )?,
        "canonical IPC batch peak",
    )?;
    reserve_peak(
        options.budgets,
        checked_add(live_bytes, output_bytes, "canonical IPC live output")?,
        peak_request,
    )?;

    let columns = pool.install(|| {
        plans
            .par_iter()
            .enumerate()
            .map(|(plan_index, plan)| {
                let mut builder = CanonicalBuilder::new(plan, rows, payloads[plan_index])?;
                for span in spans {
                    check_control(options.control)?;
                    let input_index = layouts[span.batch_index].input_indices[plan_index];
                    builder.append_span(
                        plan,
                        input_array(&batches[span.batch_index], input_index),
                        span.start,
                        span.len,
                        options.control,
                    )?;
                }
                Ok::<ArrayRef, CanonicalIpcError>(builder.finish())
            })
            .collect::<Vec<_>>()
    });
    let columns = columns.into_iter().collect::<Result<Vec<_>, _>>()?;
    let batch_options = RecordBatchOptions::new().with_row_count(Some(rows));
    RecordBatch::try_new_with_options(Arc::clone(schema), columns, &batch_options).map_err(
        |error| {
            ipc_error(format!(
                "canonical RecordBatch construction failed: {error}"
            ))
        },
    )
}

/// Encode already projected, row-ordered Arrow batches as canonical IPC file bytes.
///
/// The descriptor list is the external row layout. Input RecordBatch fields are
/// matched by `canonical_name`; both descriptor `sql_type` and values must have
/// already been normalized by the owning projection capability.
pub fn encode_v1(
    columns: &[ColumnDescriptor],
    batches: &[RecordBatch],
    pool: &ThreadPool,
    options: CanonicalIpcOptions<'_>,
) -> Result<Vec<u8>, CanonicalIpcError> {
    check_control(options.control)?;
    let descriptor_bytes = descriptor_size(columns, options.budgets)?;
    let mut plans = canonical_plans(columns, descriptor_bytes, options.budgets, options.control)?;
    let plan_metadata_bytes = plans.iter().try_fold(0_usize, |total, plan| {
        checked_add(total, plan.metadata.len(), "canonical IPC plan metadata")
    })?;
    let plans_live = checked_add(
        checked_add(
            descriptor_bytes,
            checked_mul(
                plans.len(),
                std::mem::size_of::<ColumnPlan<'_>>(),
                "canonical IPC plans",
            )?,
            "canonical IPC plans",
        )?,
        plan_metadata_bytes,
        "canonical IPC plans",
    )?;
    let schema_estimate = schema_metadata_estimate(&plans)?;
    reserve_peak(options.budgets, plans_live, schema_estimate)?;
    let (layouts, total_rows, _input_bytes, layout_bytes) = inspect_input(
        &mut plans,
        batches,
        options,
        checked_add(plans_live, schema_estimate, "canonical IPC schema")?,
    )?;
    let resident_base = checked_add(
        checked_add(
            plans_live,
            checked_mul(schema_estimate, 2, "canonical IPC schemas")?,
            "canonical IPC base",
        )?,
        layout_bytes,
        "canonical IPC base",
    )?;
    reserve_peak(
        options.budgets,
        checked_add(plans_live, layout_bytes, "canonical IPC schema base")?,
        checked_mul(schema_estimate, 2, "canonical IPC schema peak")?,
    )?;
    let schema = arrow_schema(&plans)?;

    let write_options = IpcWriteOptions::try_new(IPC_ALIGNMENT, false, MetadataVersion::V5)
        .map_err(|error| ipc_error(error.to_string()))?;
    reserve_peak(
        options.budgets,
        checked_add(
            plans_live,
            checked_add(schema_estimate, layout_bytes, "canonical IPC base")?,
            "canonical IPC base",
        )?,
        checked_mul(schema_estimate, 3, "canonical IPC schema writer")?,
    )?;
    let sink = BudgetedVecWriter::new(options.budgets.max_output_bytes);
    let mut writer = FileWriter::try_new_with_options(sink, schema.as_ref(), write_options)
        .map_err(writer_creation_error)?;
    check_control(options.control)?;

    let mut cursor = RowSpanCursor {
        batch_index: 0,
        row_index: 0,
    };
    let mut rows_written = 0_usize;
    while rows_written < total_rows {
        check_control(options.control)?;
        let rows = (total_rows - rows_written).min(CANONICAL_IPC_BATCH_ROWS);
        let span_bytes_upper = checked_mul(
            layouts.len(),
            std::mem::size_of::<RowSpan>(),
            "canonical batch row spans",
        )?;
        let out_len = writer.get_ref().bytes.len();
        reserve_peak(
            options.budgets,
            checked_add(resident_base, out_len, "canonical IPC live output")?,
            span_bytes_upper,
        )?;
        let spans = cursor.next(&layouts, rows);
        let span_rows = spans.iter().try_fold(0_usize, |count, span| {
            checked_add(count, span.len, "canonical IPC output batch")
        })?;
        if span_rows != rows {
            return Err(ipc_error("input batch traversal lost canonical rows"));
        }
        let batch = build_output_batch(
            &plans,
            &schema,
            &spans,
            rows,
            batches,
            &layouts,
            pool,
            options,
            resident_base,
            out_len,
        )?;
        writer
            .write(&batch)
            .map_err(|error| writer_error(error, writer.get_ref()))?;
        check_control(options.control)?;
        rows_written = checked_add(rows_written, rows, "canonical IPC written rows")?;
    }
    check_control(options.control)?;
    let output_len = writer.get_ref().bytes.len();
    let output_batches = total_rows.div_ceil(CANONICAL_IPC_BATCH_ROWS);
    let footer_estimate = checked_add(
        checked_mul(schema_estimate, 2, "canonical IPC footer")?,
        checked_add(
            8192,
            checked_mul(output_batches, 64, "canonical IPC footer blocks")?,
            "canonical IPC footer",
        )?,
        "canonical IPC footer",
    )?;
    reserve_peak(
        options.budgets,
        checked_add(resident_base, output_len, "canonical IPC footer")?,
        checked_mul(footer_estimate, 2, "canonical IPC footer peak")?,
    )?;
    writer
        .finish()
        .map_err(|error| writer_error(error, writer.get_ref()))?;
    check_control(options.control)?;
    let sink = writer
        .into_inner()
        .map_err(|error| ipc_error(error.to_string()))?;
    if sink.bytes.len() > options.budgets.max_output_bytes {
        return Err(resource_error("canonical IPC output byte limit exceeded"));
    }
    Ok(sink.into_bytes())
}

fn writer_creation_error(error: arrow_schema::ArrowError) -> CanonicalIpcError {
    match &error {
        arrow_schema::ArrowError::IoError(_, _) => resource_error(error.to_string()),
        _ => ipc_error(error.to_string()),
    }
}

trait RawMetadataEntry {
    fn raw_key(&self) -> Option<&str>;
    fn raw_value(&self) -> Option<&str>;
}

impl<'a> RawMetadataEntry for arrow_ipc::KeyValue<'a> {
    fn raw_key(&self) -> Option<&str> {
        arrow_ipc::KeyValue::key(self)
    }

    fn raw_value(&self) -> Option<&str> {
        arrow_ipc::KeyValue::value(self)
    }
}

fn require_raw_metadata<I>(
    entries: Option<I>,
    expected_key: &str,
    expected_value: &str,
    scope: &str,
) -> Result<(), CanonicalIpcError>
where
    I: IntoIterator,
    I::Item: RawMetadataEntry,
{
    let mut entries = entries.into_iter().flatten();
    let entry = entries
        .next()
        .ok_or_else(|| schema_error(format!("{scope} mapping metadata is missing")))?;
    if entries.next().is_some() {
        return Err(schema_error(format!(
            "{scope} contains duplicate or unexpected mapping metadata"
        )));
    }
    if entry.raw_key() != Some(expected_key) || entry.raw_value() != Some(expected_value) {
        return Err(schema_error(format!(
            "{scope} mapping metadata does not match the bound descriptor"
        )));
    }
    Ok(())
}

fn raw_field_has_v1_type(field: arrow_ipc::Field<'_>, plan: &ColumnPlan<'_>) -> bool {
    match plan.mapping {
        ValueMapping::Signed { .. } => {
            field.type_type() == arrow_ipc::Type::Int
                && field
                    .type_as_int()
                    .is_some_and(|integer| integer.bitWidth() == 64 && integer.is_signed())
        }
        ValueMapping::Unsigned { .. } => {
            field.type_type() == arrow_ipc::Type::Int
                && field
                    .type_as_int()
                    .is_some_and(|integer| integer.bitWidth() == 64 && !integer.is_signed())
        }
        ValueMapping::Boolean => field.type_type() == arrow_ipc::Type::Bool,
        ValueMapping::Float32 => {
            field.type_type() == arrow_ipc::Type::FloatingPoint
                && field
                    .type_as_floating_point()
                    .is_some_and(|value| value.precision() == arrow_ipc::Precision::SINGLE)
        }
        ValueMapping::Float64 => {
            field.type_type() == arrow_ipc::Type::FloatingPoint
                && field
                    .type_as_floating_point()
                    .is_some_and(|value| value.precision() == arrow_ipc::Precision::DOUBLE)
        }
        ValueMapping::Utf8 => matches!(
            field.type_type(),
            arrow_ipc::Type::Utf8 | arrow_ipc::Type::LargeUtf8
        ),
        ValueMapping::Binary => matches!(
            field.type_type(),
            arrow_ipc::Type::Binary | arrow_ipc::Type::LargeBinary
        ),
        ValueMapping::Bit { width, .. } => {
            field.type_type() == arrow_ipc::Type::FixedSizeBinary
                && field
                    .type_as_fixed_size_binary()
                    .is_some_and(|value| value.byteWidth() > 0 && value.byteWidth() == width as i32)
        }
    }
}

fn validate_raw_schema(
    schema: arrow_ipc::Schema<'_>,
    plans: &[ColumnPlan<'_>],
) -> Result<(), CanonicalIpcError> {
    if schema.endianness() != arrow_ipc::Endianness::Little {
        return Err(schema_error(
            "canonical IPC schema endianness is not little-endian",
        ));
    }
    require_raw_metadata(
        schema.custom_metadata(),
        SCHEMA_VERSION_KEY,
        CANONICAL_MAPPING_VERSION,
        "schema",
    )?;
    let fields = schema
        .fields()
        .ok_or_else(|| ipc_error("canonical IPC schema field vector is missing"))?;
    if fields.len() != plans.len() {
        return Err(schema_error(
            "canonical IPC field count does not match descriptors",
        ));
    }
    for (field, plan) in fields.iter().zip(plans) {
        if field.name() != Some(plan.descriptor.canonical_name.as_str())
            || field.nullable() != plan.descriptor.nullable
        {
            return Err(schema_error(
                "canonical IPC field order or nullability does not match descriptors",
            ));
        }
        if field.dictionary().is_some()
            || field.children().is_some_and(|children| children.len() != 0)
        {
            return Err(schema_error(
                "canonical IPC nested or dictionary fields are unsupported",
            ));
        }
        if !raw_field_has_v1_type(field, plan) {
            return Err(schema_error(format!(
                "canonical IPC raw field type does not match descriptor {}",
                plan.descriptor.canonical_name
            )));
        }
        require_raw_metadata(
            field.custom_metadata(),
            FIELD_TYPE_KEY,
            &plan.metadata,
            "field",
        )?;
    }
    Ok(())
}

fn raw_schemas_match(
    left: &arrow_ipc::Schema<'_>,
    right: &arrow_ipc::Schema<'_>,
) -> Result<(), CanonicalIpcError> {
    let left_fields = left
        .fields()
        .ok_or_else(|| ipc_error("canonical IPC header field vector is missing"))?;
    let right_fields = right
        .fields()
        .ok_or_else(|| ipc_error("canonical IPC footer field vector is missing"))?;
    if left_fields.len() != right_fields.len() {
        return Err(schema_error(
            "canonical IPC header and footer field counts differ",
        ));
    }
    for (left_field, right_field) in left_fields.iter().zip(right_fields.iter()) {
        if left_field.type_type() != right_field.type_type() {
            return Err(schema_error(
                "canonical IPC header and footer physical types differ",
            ));
        }
    }
    Ok(())
}

#[derive(Debug, Clone, Copy)]
struct DecodePreflight {
    footer_len: usize,
    block_count: usize,
    total_rows: usize,
    block_bytes: usize,
}

fn raw_framed_message_payload<'a>(
    bytes: &'a [u8],
    offset: usize,
    metadata_len: usize,
) -> Result<&'a [u8], CanonicalIpcError> {
    let end = checked_add(offset, metadata_len, "IPC block metadata")?;
    let metadata = bytes
        .get(offset..end)
        .ok_or_else(|| ipc_error("IPC block metadata exceeds the file"))?;
    if !metadata.starts_with(&[0xff; 4]) {
        return Err(ipc_error("canonical IPC requires continuation framing"));
    }
    let encoded = metadata
        .get(4..8)
        .ok_or_else(|| ipc_error("IPC continuation prefix is truncated"))?;
    let prefix_len = 8;
    let encoded_len = i32::from_le_bytes([encoded[0], encoded[1], encoded[2], encoded[3]]);
    let encoded_len = usize::try_from(encoded_len)
        .map_err(|_| ipc_error("IPC metadata prefix has a negative length"))?;
    if encoded_len == 0 {
        return Err(ipc_error("IPC record-batch metadata is empty"));
    }
    let payload_end = checked_add(prefix_len, encoded_len, "IPC metadata length")?;
    if payload_end > metadata.len() {
        return Err(ipc_error("IPC metadata length exceeds its footer block"));
    }
    if metadata[payload_end..].iter().any(|byte| *byte != 0) {
        return Err(ipc_error("IPC metadata padding is not zero"));
    }
    Ok(&metadata[prefix_len..payload_end])
}

fn align_to(value: usize, alignment: usize) -> Result<usize, CanonicalIpcError> {
    let remainder = value % alignment;
    if remainder == 0 {
        Ok(value)
    } else {
        checked_add(value, alignment - remainder, "canonical IPC alignment")
    }
}

fn preflight_schema_header<'a>(
    bytes: &'a [u8],
    plans: &[ColumnPlan<'_>],
    options: CanonicalIpcOptions<'_>,
) -> Result<(usize, arrow_ipc::Schema<'a>), CanonicalIpcError> {
    let header_metadata_start = IPC_ALIGNMENT;
    if bytes.len() < header_metadata_start + 8
        || bytes[6..header_metadata_start]
            .iter()
            .any(|byte| *byte != 0)
    {
        return Err(ipc_error("canonical IPC schema header padding is invalid"));
    }
    if bytes[header_metadata_start..header_metadata_start + 4] != [0xff; 4] {
        return Err(ipc_error(
            "canonical IPC schema message is not continuation-framed",
        ));
    }
    let metadata_len_bytes = &bytes[header_metadata_start + 4..header_metadata_start + 8];
    let metadata_len = usize::try_from(i32::from_le_bytes([
        metadata_len_bytes[0],
        metadata_len_bytes[1],
        metadata_len_bytes[2],
        metadata_len_bytes[3],
    ]))
    .map_err(|_| ipc_error("canonical IPC schema metadata has a negative length"))?;
    if metadata_len == 0 {
        return Err(ipc_error("canonical IPC schema metadata is empty"));
    }
    let padded_header_len = align_to(
        checked_add(8, metadata_len, "canonical IPC schema metadata")?,
        IPC_ALIGNMENT,
    )?;
    let message_bytes =
        raw_framed_message_payload(bytes, header_metadata_start, padded_header_len)?;
    let message = root_as_message(message_bytes)
        .map_err(|error| ipc_error(format!("invalid canonical IPC schema message: {error:?}")))?;
    if message.version() != MetadataVersion::V5
        || message.header_type() != MessageHeader::Schema
        || message.bodyLength() != 0
        || message
            .custom_metadata()
            .is_some_and(|metadata| metadata.len() != 0)
    {
        return Err(ipc_error(
            "canonical IPC schema message does not match v1 framing",
        ));
    }
    let schema = message
        .header_as_schema()
        .ok_or_else(|| ipc_error("canonical IPC schema header is missing"))?;
    validate_raw_schema(schema, plans)?;
    check_control(options.control)?;
    let header_end = checked_add(
        header_metadata_start,
        padded_header_len,
        "canonical IPC schema header",
    )?;
    Ok((header_end, schema))
}

fn preflight_record_block(
    bytes: &[u8],
    block: &arrow_ipc::Block,
    block_index: usize,
    block_count: usize,
    footer_start: usize,
    previous_end: usize,
    plans: &[ColumnPlan<'_>],
    options: CanonicalIpcOptions<'_>,
) -> Result<(usize, usize, usize), CanonicalIpcError> {
    check_control(options.control)?;
    let offset = usize::try_from(block.offset())
        .map_err(|_| ipc_error("IPC record-batch block has a negative offset"))?;
    let metadata_len = usize::try_from(block.metaDataLength())
        .map_err(|_| ipc_error("IPC record-batch metadata has a negative length"))?;
    let body_len = usize::try_from(block.bodyLength())
        .map_err(|_| ipc_error("IPC record-batch body has a negative length"))?;
    if metadata_len == 0
        || offset % IPC_ALIGNMENT != 0
        || metadata_len % IPC_ALIGNMENT != 0
        || body_len % IPC_ALIGNMENT != 0
        || offset != previous_end
    {
        return Err(ipc_error(
            "IPC record-batch block is outside the v1 layout profile",
        ));
    }
    let metadata_end = checked_add(offset, metadata_len, "IPC record-batch block")?;
    let block_end = checked_add(metadata_end, body_len, "IPC record-batch block")?;
    if block_end > footer_start || offset >= footer_start {
        return Err(ipc_error("IPC record-batch block overlaps the footer"));
    }

    let message_bytes = raw_framed_message_payload(bytes, offset, metadata_len)?;
    let message = root_as_message(message_bytes)
        .map_err(|error| ipc_error(format!("invalid IPC record-batch message: {error:?}")))?;
    if message.version() != MetadataVersion::V5
        || message.header_type() != MessageHeader::RecordBatch
        || message.bodyLength() != block.bodyLength()
    {
        return Err(ipc_error(
            "IPC record-batch message does not match its footer block",
        ));
    }
    if message
        .custom_metadata()
        .is_some_and(|metadata| metadata.len() != 0)
    {
        return Err(ipc_error(
            "IPC record-batch message has unsupported custom metadata",
        ));
    }
    let record_batch = message
        .header_as_record_batch()
        .ok_or_else(|| ipc_error("IPC record-batch header is missing"))?;
    if record_batch.compression().is_some()
        || record_batch
            .variadicBufferCounts()
            .is_some_and(|counts| counts.len() != 0)
    {
        return Err(ipc_error(
            "IPC record-batch compression or variadic buffers are unsupported",
        ));
    }
    let rows = usize::try_from(record_batch.length())
        .map_err(|_| ipc_error("IPC record-batch has a negative row count"))?;
    if rows == 0 || rows > CANONICAL_IPC_BATCH_ROWS || rows > options.budgets.max_rows {
        return Err(resource_error("IPC record-batch row limit exceeded"));
    }
    let expected_rows = if block_index + 1 < block_count {
        CANONICAL_IPC_BATCH_ROWS
    } else {
        rows
    };
    if rows != expected_rows {
        return Err(ipc_error(
            "IPC record-batch chunking does not match the v1 profile",
        ));
    }

    let nodes = record_batch.nodes();
    let node_count = nodes.as_ref().map_or(0, |values| values.len());
    if node_count != plans.len() {
        return Err(ipc_error(
            "IPC record-batch field-node count does not match schema",
        ));
    }
    if let Some(nodes) = nodes {
        for node in nodes {
            let node_rows = usize::try_from(node.length())
                .map_err(|_| ipc_error("IPC field node has a negative row count"))?;
            let null_count = usize::try_from(node.null_count())
                .map_err(|_| ipc_error("IPC field node has a negative null count"))?;
            if node_rows != rows || null_count > rows {
                return Err(ipc_error("IPC field-node counts do not match the batch"));
            }
        }
    }
    let expected_buffers = plans.iter().try_fold(0_usize, |total, plan| {
        checked_add(
            total,
            buffer_count(plan.mapping),
            "IPC record-batch buffers",
        )
    })?;
    let buffers = record_batch.buffers();
    let buffer_count_actual = buffers.as_ref().map_or(0, |values| values.len());
    if buffer_count_actual != expected_buffers {
        return Err(ipc_error(
            "IPC record-batch buffer count does not match schema",
        ));
    }
    if let Some(buffers) = buffers {
        let mut previous_buffer_end = 0_usize;
        for buffer in buffers {
            let buffer_offset = usize::try_from(buffer.offset())
                .map_err(|_| ipc_error("IPC data buffer has a negative offset"))?;
            let buffer_len = usize::try_from(buffer.length())
                .map_err(|_| ipc_error("IPC data buffer has a negative length"))?;
            let buffer_end = checked_add(buffer_offset, buffer_len, "IPC data buffer")?;
            if buffer_offset % IPC_ALIGNMENT != 0
                || buffer_offset < previous_buffer_end
                || buffer_end > body_len
            {
                return Err(ipc_error("IPC data buffer exceeds the v1 block layout"));
            }
            previous_buffer_end = buffer_end;
        }
    }
    let block_bytes = checked_add(metadata_len, body_len, "IPC record-batch block")?;
    Ok((block_end, rows, block_bytes))
}

fn preflight_arrow_file(
    bytes: &[u8],
    plans: &[ColumnPlan<'_>],
    options: CanonicalIpcOptions<'_>,
) -> Result<DecodePreflight, CanonicalIpcError> {
    check_control(options.control)?;
    if bytes.len() > options.budgets.max_input_bytes {
        return Err(resource_error("canonical IPC input byte limit exceeded"));
    }
    if bytes.len() < 18 || &bytes[..6] != ARROW_MAGIC {
        return Err(ipc_error("canonical IPC file header is missing"));
    }
    let (header_end, header_schema) = preflight_schema_header(bytes, plans, options)?;
    let trailer_start = bytes
        .len()
        .checked_sub(10)
        .ok_or_else(|| ipc_error("canonical IPC file trailer is truncated"))?;
    if &bytes[trailer_start + 4..] != ARROW_MAGIC {
        return Err(ipc_error("canonical IPC file footer marker is missing"));
    }
    let footer_len_i32 = i32::from_le_bytes([
        bytes[trailer_start],
        bytes[trailer_start + 1],
        bytes[trailer_start + 2],
        bytes[trailer_start + 3],
    ]);
    let footer_len = usize::try_from(footer_len_i32)
        .map_err(|_| ipc_error("canonical IPC footer has a negative length"))?;
    let footer_start = trailer_start
        .checked_sub(footer_len)
        .ok_or_else(|| ipc_error("canonical IPC footer length exceeds the file"))?;
    if footer_start < 8 {
        return Err(ipc_error("canonical IPC footer overlaps the file header"));
    }
    if header_end > footer_start {
        return Err(ipc_error("canonical IPC schema header overlaps the footer"));
    }
    let footer_bytes = &bytes[footer_start..trailer_start];
    let footer = root_as_footer(footer_bytes)
        .map_err(|error| ipc_error(format!("invalid IPC footer: {error:?}")))?;
    if footer.version() != MetadataVersion::V5 {
        return Err(ipc_error("canonical IPC footer metadata version is not V5"));
    }
    if footer
        .dictionaries()
        .is_some_and(|dictionaries| dictionaries.len() != 0)
        || footer
            .custom_metadata()
            .is_some_and(|metadata| metadata.len() != 0)
    {
        return Err(ipc_error(
            "canonical IPC footer contains unsupported metadata",
        ));
    }
    let schema = footer
        .schema()
        .ok_or_else(|| ipc_error("canonical IPC footer schema is missing"))?;
    validate_raw_schema(schema, plans)?;
    raw_schemas_match(&header_schema, &schema)?;
    let blocks = footer
        .recordBatches()
        .ok_or_else(|| ipc_error("canonical IPC record-batch index is missing"))?;
    let block_count = blocks.len();
    if block_count > options.budgets.max_input_batches {
        return Err(resource_error("canonical IPC record-batch limit exceeded"));
    }
    let mut previous_end = header_end;
    let mut total_rows = 0_usize;
    let mut block_bytes = 0_usize;
    for (block_index, block) in blocks.iter().enumerate() {
        let (block_end, rows, current_block_bytes) = preflight_record_block(
            bytes,
            block,
            block_index,
            block_count,
            footer_start,
            previous_end,
            plans,
            options,
        )?;
        previous_end = block_end;
        total_rows = checked_add(total_rows, rows, "canonical IPC row count")?;
        if total_rows > options.budgets.max_rows {
            return Err(resource_error("canonical IPC row limit exceeded"));
        }
        block_bytes = checked_add(
            block_bytes,
            current_block_bytes,
            "canonical IPC block bytes",
        )?;
    }
    let eos_end = checked_add(previous_end, 8, "canonical IPC EOS marker")?;
    if eos_end != footer_start
        || bytes.get(previous_end..eos_end) != Some(IPC_EOS_MARKER.as_slice())
    {
        return Err(ipc_error(
            "canonical IPC EOS marker does not match block layout",
        ));
    }
    check_control(options.control)?;
    Ok(DecodePreflight {
        footer_len,
        block_count,
        total_rows,
        block_bytes,
    })
}

fn decoded_field_large_offsets(
    plan: &ColumnPlan<'_>,
    actual_type: &DataType,
) -> Result<bool, CanonicalIpcError> {
    match plan.mapping {
        ValueMapping::Signed { .. } if actual_type == &DataType::Int64 => Ok(false),
        ValueMapping::Unsigned { .. } if actual_type == &DataType::UInt64 => Ok(false),
        ValueMapping::Boolean if actual_type == &DataType::Boolean => Ok(false),
        ValueMapping::Float32 if actual_type == &DataType::Float32 => Ok(false),
        ValueMapping::Float64 if actual_type == &DataType::Float64 => Ok(false),
        ValueMapping::Utf8 if actual_type == &DataType::Utf8 => Ok(false),
        ValueMapping::Utf8 if actual_type == &DataType::LargeUtf8 => Ok(true),
        ValueMapping::Binary if actual_type == &DataType::Binary => Ok(false),
        ValueMapping::Binary if actual_type == &DataType::LargeBinary => Ok(true),
        ValueMapping::Bit { width, .. }
            if actual_type == &DataType::FixedSizeBinary(width as i32) =>
        {
            Ok(false)
        }
        _ => Err(schema_error(format!(
            "canonical IPC physical type does not match field {}",
            plan.descriptor.canonical_name
        ))),
    }
}

fn validate_reader_schema(
    schema: &Schema,
    plans: &[ColumnPlan<'_>],
) -> Result<Vec<bool>, CanonicalIpcError> {
    if schema.metadata().len() != 1
        || schema
            .metadata()
            .get(SCHEMA_VERSION_KEY)
            .map(String::as_str)
            != Some(CANONICAL_MAPPING_VERSION)
    {
        return Err(schema_error(
            "canonical IPC schema mapping version is missing or unexpected",
        ));
    }
    if schema.fields().len() != plans.len() {
        return Err(schema_error(
            "canonical IPC schema field count does not match descriptors",
        ));
    }
    let mut large_offsets = Vec::new();
    large_offsets
        .try_reserve_exact(plans.len())
        .map_err(|_| resource_error("canonical IPC schema validation allocation failed"))?;
    for (index, plan) in plans.iter().enumerate() {
        let field = schema.field(index);
        if field.name().as_str() != plan.descriptor.canonical_name.as_str()
            || field.is_nullable() != plan.descriptor.nullable
        {
            return Err(schema_error(
                "canonical IPC field layout does not match descriptors",
            ));
        }
        if field.metadata().len() != 1
            || field.metadata().get(FIELD_TYPE_KEY).map(String::as_str)
                != Some(plan.metadata.as_str())
        {
            return Err(schema_error(
                "canonical IPC field metadata does not match descriptor",
            ));
        }
        large_offsets.push(decoded_field_large_offsets(plan, field.data_type())?);
    }
    Ok(large_offsets)
}

/// Decode a v1 canonical Arrow IPC file after validating its raw mapping metadata,
/// footer ranges, block layout, and bound physical schema.
///
/// The returned batches use the input descriptor order. Their values are checked
/// for mapping-level constraints such as integer width, finite floats, SET order,
/// and BIT width/high bits. Business-specific Decimal, temporal, and JSON grammar
/// remains the responsibility of the projection owner that created this file.
pub fn decode_v1(
    bytes: &[u8],
    columns: &[ColumnDescriptor],
    pool: &ThreadPool,
    options: CanonicalIpcOptions<'_>,
) -> Result<Vec<RecordBatch>, CanonicalIpcError> {
    check_control(options.control)?;
    let descriptor_bytes = descriptor_size(columns, options.budgets)?;
    let mut plans = canonical_plans(columns, descriptor_bytes, options.budgets, options.control)?;
    let plan_metadata_bytes = plans.iter().try_fold(0_usize, |total, plan| {
        checked_add(total, plan.metadata.len(), "canonical IPC plan metadata")
    })?;
    let plans_live = checked_add(
        checked_add(
            descriptor_bytes,
            checked_mul(
                plans.len(),
                std::mem::size_of::<ColumnPlan<'_>>(),
                "canonical IPC plans",
            )?,
            "canonical IPC plans",
        )?,
        plan_metadata_bytes,
        "canonical IPC plans",
    )?;
    let schema_estimate = schema_metadata_estimate(&plans)?;
    let preflight = preflight_arrow_file(bytes, &plans, options)?;
    let record_batch_index_bytes = checked_mul(
        preflight.block_count,
        std::mem::size_of::<arrow_ipc::Block>(),
        "canonical IPC record-batch index",
    )?;
    let output_batch_bytes = checked_mul(
        preflight.block_count,
        std::mem::size_of::<RecordBatch>(),
        "canonical IPC output batches",
    )?;
    let output_array_refs = checked_mul(
        checked_mul(
            preflight.block_count,
            plans.len(),
            "canonical IPC output arrays",
        )?,
        std::mem::size_of::<ArrayRef>(),
        "canonical IPC output arrays",
    )?;
    let output_array_headers = checked_mul(
        checked_mul(
            preflight.block_count,
            plans.len(),
            "canonical IPC output arrays",
        )?,
        1024,
        "canonical IPC output array headers",
    )?;
    let output_order_bytes = checked_mul(
        columns.len(),
        std::mem::size_of::<usize>(),
        "canonical IPC external field order",
    )?;
    let decode_peak = [
        checked_mul(preflight.footer_len, 2, "canonical IPC footer peak")?,
        checked_mul(preflight.block_bytes, 2, "canonical IPC block peak")?,
        record_batch_index_bytes,
        output_batch_bytes,
        output_array_refs,
        output_array_headers,
        output_order_bytes,
        checked_mul(schema_estimate, 3, "canonical IPC schema peak")?,
    ]
    .into_iter()
    .try_fold(0_usize, |total, bytes| {
        checked_add(total, bytes, "canonical IPC decode peak")
    })?;
    reserve_peak(options.budgets, plans_live, decode_peak)?;

    let footer_table_limit = checked_add(
        checked_mul(plans.len(), 8, "canonical IPC footer table limit")?,
        64,
        "canonical IPC footer table limit",
    )?;
    let mut reader = FileReaderBuilder::new()
        .with_max_footer_fb_tables(footer_table_limit)
        .with_max_footer_fb_depth(16)
        .build(Cursor::new(bytes))
        .map_err(|error| ipc_error(format!("canonical Arrow file reader failed: {error}")))?;
    check_control(options.control)?;
    if reader.num_batches() != preflight.block_count || !reader.custom_metadata().is_empty() {
        return Err(ipc_error(
            "canonical Arrow reader footer differs from preflight",
        ));
    }
    let reader_schema = reader.schema();
    let large_offsets = validate_reader_schema(reader_schema.as_ref(), &plans)?;

    let mut output_indices = Vec::new();
    output_indices
        .try_reserve_exact(columns.len())
        .map_err(|_| resource_error("canonical IPC field-order allocation failed"))?;
    for column in columns {
        let index = plans
            .binary_search_by(|plan| {
                plan.descriptor
                    .canonical_name
                    .as_bytes()
                    .cmp(column.canonical_name.as_bytes())
            })
            .map_err(|_| schema_error("canonical IPC descriptor disappeared during binding"))?;
        output_indices.push(index);
    }
    let mut output_fields = Vec::new();
    output_fields
        .try_reserve_exact(output_indices.len())
        .map_err(|_| resource_error("canonical IPC output schema allocation failed"))?;
    for index in &output_indices {
        output_fields.push(reader_schema.fields()[*index].clone());
    }
    let output_schema = Arc::new(Schema::new_with_metadata(
        output_fields,
        reader_schema.metadata().clone(),
    ));
    let mut output = Vec::new();
    output
        .try_reserve_exact(preflight.block_count)
        .map_err(|_| resource_error("canonical IPC output batch allocation failed"))?;

    let mut rows_read = 0_usize;
    let mut batch_index = 0_usize;
    while let Some(batch_result) = {
        check_control(options.control)?;
        reader.next()
    } {
        let batch = batch_result
            .map_err(|error| ipc_error(format!("canonical Arrow record batch failed: {error}")))?;
        check_control(options.control)?;
        if batch_index >= preflight.block_count || batch.num_columns() != plans.len() {
            return Err(ipc_error(
                "canonical Arrow reader returned an unexpected batch",
            ));
        }
        let expected_rows = if batch_index + 1 < preflight.block_count {
            CANONICAL_IPC_BATCH_ROWS
        } else {
            batch.num_rows()
        };
        if batch.num_rows() == 0 || batch.num_rows() != expected_rows {
            return Err(ipc_error(
                "canonical Arrow reader returned invalid v1 chunking",
            ));
        }
        rows_read = checked_add(rows_read, batch.num_rows(), "canonical IPC decoded rows")?;
        if rows_read > options.budgets.max_rows {
            return Err(resource_error("canonical IPC row limit exceeded"));
        }

        let payload_results = pool.install(|| {
            plans
                .par_iter()
                .enumerate()
                .map(|(index, plan)| {
                    check_control(options.control)?;
                    inspect_input_array(plan, batch.column(index), options.control)
                })
                .collect::<Vec<_>>()
        });
        for (plan, payload_result) in plans.iter_mut().zip(payload_results) {
            add_payload_bytes(plan, payload_result?)?;
        }

        let mut output_arrays = Vec::new();
        output_arrays
            .try_reserve_exact(output_indices.len())
            .map_err(|_| resource_error("canonical IPC batch layout allocation failed"))?;
        for index in &output_indices {
            output_arrays.push(batch.column(*index).clone());
        }
        let batch_options = RecordBatchOptions::new().with_row_count(Some(batch.num_rows()));
        output.push(
            RecordBatch::try_new_with_options(
                Arc::clone(&output_schema),
                output_arrays,
                &batch_options,
            )
            .map_err(|error| ipc_error(format!("canonical IPC output layout failed: {error}")))?,
        );
        batch_index = checked_add(batch_index, 1, "canonical IPC batch count")?;
    }
    check_control(options.control)?;
    if batch_index != preflight.block_count || rows_read != preflight.total_rows {
        return Err(ipc_error(
            "canonical Arrow reader returned incomplete record batches",
        ));
    }
    for (plan, is_large) in plans.iter().zip(large_offsets) {
        let should_be_large = plan.total_payload_bytes > i32::MAX as usize;
        if is_large != should_be_large {
            return Err(schema_error(format!(
                "canonical IPC offset width does not match field {} payload size",
                plan.descriptor.canonical_name
            )));
        }
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use std::error::Error;
    use std::io;
    use std::panic::AssertUnwindSafe;
    use std::sync::atomic::AtomicBool;
    use std::sync::{Arc, Barrier};
    use std::thread;
    use std::time::{Duration, Instant};

    use arrow_array::{
        ArrayRef, BinaryArray, BooleanArray, FixedSizeBinaryArray, Int64Array, RecordBatchOptions,
        StringArray,
    };
    use arrow_schema::{Field, Schema};
    use rayon::{ThreadPool, ThreadPoolBuilder};

    use super::*;

    fn column(
        name: &str,
        ordinal: usize,
        sql_type: &str,
        logical_type: SqlLogicalType,
        declared_type: Option<DeclaredType>,
        nullable: bool,
        labels: Option<Vec<&str>>,
    ) -> ColumnDescriptor {
        ColumnDescriptor {
            display_name: name.to_owned(),
            canonical_name: name.to_owned(),
            ordinal,
            sql_type: sql_type.to_owned(),
            logical_type,
            declared_type,
            nullable,
            labels: labels.map(|items| items.into_iter().map(str::to_owned).collect()),
        }
    }

    fn options() -> CanonicalIpcOptions<'static> {
        CanonicalIpcOptions {
            budgets: CanonicalIpcBudgets {
                max_rows: 25_000_000,
                max_columns: 64,
                max_descriptor_bytes: 1 << 20,
                max_input_batches: 64,
                max_input_bytes: 1 << 30,
                max_output_bytes: 1 << 30,
                max_codec_peak_bytes: 2 << 30,
            },
            control: CanonicalIpcControl::default(),
        }
    }

    fn pool() -> Result<ThreadPool, Box<dyn Error>> {
        ThreadPoolBuilder::new()
            .num_threads(2)
            .build()
            .map_err(Into::into)
    }

    fn mapping_fixture() -> Result<(Vec<ColumnDescriptor>, RecordBatch), Box<dyn Error>> {
        let columns = vec![
            column(
                "z",
                0,
                "BIT(9)",
                SqlLogicalType::Standard,
                Some(DeclaredType::Bit { bit_width: 9 }),
                true,
                None,
            ),
            column(
                "b",
                1,
                "BOOLEAN",
                SqlLogicalType::Standard,
                Some(DeclaredType::Boolean),
                true,
                None,
            ),
            column(
                "s",
                2,
                "VARCHAR(16)",
                SqlLogicalType::Standard,
                Some(DeclaredType::String),
                true,
                None,
            ),
            column(
                "i",
                3,
                "BIGINT",
                SqlLogicalType::Standard,
                Some(DeclaredType::SignedInteger { bits: 64 }),
                true,
                None,
            ),
        ];
        let bit_one = [0x00_u8, 0x01_u8];
        let bit_256 = [0x01_u8, 0x00_u8];
        let schema = Arc::new(Schema::new(vec![
            Field::new("i", DataType::Int64, true),
            Field::new("s", DataType::Utf8, true),
            Field::new("b", DataType::Boolean, true),
            Field::new("z", DataType::Binary, true),
        ]));
        let arrays: Vec<ArrayRef> = vec![
            Arc::new(Int64Array::from(vec![Some(7), None, Some(-1)])),
            Arc::new(StringArray::from(vec![Some("é"), None, Some("")])),
            Arc::new(BooleanArray::from(vec![Some(true), None, Some(false)])),
            Arc::new(BinaryArray::from(vec![
                Some(bit_one.as_slice()),
                None,
                Some(bit_256.as_slice()),
            ])),
        ];
        let batch = RecordBatch::try_new(schema, arrays)?;
        Ok((columns, batch))
    }

    fn footer_start(bytes: &[u8]) -> Result<usize, Box<dyn Error>> {
        let trailer_start = bytes
            .len()
            .checked_sub(10)
            .ok_or_else(|| io::Error::other("IPC test footer is missing"))?;
        let footer_len = usize::try_from(i32::from_le_bytes([
            bytes[trailer_start],
            bytes[trailer_start + 1],
            bytes[trailer_start + 2],
            bytes[trailer_start + 3],
        ]))?;
        trailer_start
            .checked_sub(footer_len)
            .ok_or_else(|| io::Error::other("IPC test footer range is invalid").into())
    }

    fn first_record_batch_buffers(bytes: &[u8]) -> Result<Vec<Vec<u8>>, Box<dyn Error>> {
        let footer_offset = footer_start(bytes)?;
        let trailer_start = bytes
            .len()
            .checked_sub(10)
            .ok_or_else(|| io::Error::other("IPC test trailer is missing"))?;
        let footer = root_as_footer(&bytes[footer_offset..trailer_start])
            .map_err(|error| io::Error::other(format!("invalid test footer: {error:?}")))?;
        let blocks = footer
            .recordBatches()
            .ok_or_else(|| io::Error::other("test file has no record-batch index"))?;
        let block = blocks
            .get(0);
        let offset = usize::try_from(block.offset())?;
        let metadata_len = usize::try_from(block.metaDataLength())?;
        let body_len = usize::try_from(block.bodyLength())?;
        let metadata_end = offset
            .checked_add(metadata_len)
            .ok_or_else(|| io::Error::other("test block metadata overflow"))?;
        let metadata = bytes
            .get(offset..metadata_end)
            .ok_or_else(|| io::Error::other("test block metadata is out of range"))?;
        let message_len = usize::try_from(i32::from_le_bytes([
            metadata[4], metadata[5], metadata[6], metadata[7],
        ]))?;
        let message_end = 8_usize
            .checked_add(message_len)
            .ok_or_else(|| io::Error::other("test message length overflow"))?;
        let message = root_as_message(&metadata[8..message_end])
            .map_err(|error| io::Error::other(format!("invalid test message: {error:?}")))?;
        let record_batch = message
            .header_as_record_batch()
            .ok_or_else(|| io::Error::other("test record-batch message is missing"))?;
        let buffers = record_batch
            .buffers()
            .ok_or_else(|| io::Error::other("test record-batch buffers are missing"))?;
        let mut result = Vec::new();
        for buffer in buffers {
            let start = metadata_end
                .checked_add(usize::try_from(buffer.offset())?)
                .ok_or_else(|| io::Error::other("test buffer offset overflow"))?;
            let end = start
                .checked_add(usize::try_from(buffer.length())?)
                .ok_or_else(|| io::Error::other("test buffer end overflow"))?;
            if end > metadata_end + body_len {
                return Err(io::Error::other("test buffer exceeds body").into());
            }
            let value = bytes
                .get(start..end)
                .ok_or_else(|| io::Error::other("test buffer is out of range"))?;
            result.push(value.to_vec());
        }
        Ok(result)
    }

    fn record_batch_rows(bytes: &[u8]) -> Result<Vec<usize>, Box<dyn Error>> {
        let footer_offset = footer_start(bytes)?;
        let trailer_start = bytes
            .len()
            .checked_sub(10)
            .ok_or_else(|| io::Error::other("IPC test trailer is missing"))?;
        let footer = root_as_footer(&bytes[footer_offset..trailer_start])
            .map_err(|error| io::Error::other(format!("invalid test footer: {error:?}")))?;
        let blocks = footer
            .recordBatches()
            .ok_or_else(|| io::Error::other("test file has no record-batch index"))?;
        let mut rows = Vec::new();
        for block in blocks {
            let offset = usize::try_from(block.offset())?;
            let metadata_len = usize::try_from(block.metaDataLength())?;
            let end = offset
                .checked_add(metadata_len)
                .ok_or_else(|| io::Error::other("test block metadata overflow"))?;
            let metadata = bytes
                .get(offset..end)
                .ok_or_else(|| io::Error::other("test block metadata is out of range"))?;
            let message_len = usize::try_from(i32::from_le_bytes([
                metadata[4], metadata[5], metadata[6], metadata[7],
            ]))?;
            let message_end = 8_usize
                .checked_add(message_len)
                .ok_or_else(|| io::Error::other("test message length overflow"))?;
            let message = root_as_message(&metadata[8..message_end])
                .map_err(|error| io::Error::other(format!("invalid test message: {error:?}")))?;
            let record_batch = message
                .header_as_record_batch()
                .ok_or_else(|| io::Error::other("test record-batch message is missing"))?;
            rows.push(usize::try_from(record_batch.length())?);
        }
        Ok(rows)
    }

    #[test]
    fn canonical_mapping_preserves_independent_arrow_buffer_vectors_and_outer_layout(
    ) -> Result<(), Box<dyn Error>> {
        let (columns, batch) = mapping_fixture()?;
        let pool = pool()?;
        let encoded = encode_v1(&columns, std::slice::from_ref(&batch), &pool, options())?;
        let buffers = first_record_batch_buffers(&encoded)?;
        let signed_slots = [7_i64.to_le_bytes(), 0_i64.to_le_bytes(), (-1_i64).to_le_bytes()]
            .concat();
        let utf8_offsets = [0_i32.to_le_bytes(), 2_i32.to_le_bytes(), 2_i32.to_le_bytes(), 2_i32.to_le_bytes()]
            .concat();
        assert_eq!(buffers[0], [0x05]);
        assert_eq!(buffers[1], [0x01]);
        assert_eq!(buffers[2], [0x05]);
        assert_eq!(buffers[3], signed_slots);
        assert_eq!(buffers[4], [0x05]);
        assert_eq!(buffers[5], utf8_offsets);
        assert_eq!(buffers[6], [0xc3, 0xa9]);
        assert_eq!(buffers[7], [0x05]);
        assert_eq!(buffers[8], [0x00, 0x01, 0x00, 0x00, 0x01, 0x00]);

        let decoded = decode_v1(&encoded, &columns, &pool, options())?;
        assert_eq!(decoded.len(), 1);
        assert_eq!(decoded[0].num_rows(), 3);
        assert_eq!(decoded[0].schema().field(0).name(), "z");
        assert_eq!(decoded[0].schema().field(1).name(), "b");
        assert_eq!(decoded[0].schema().field(2).name(), "s");
        assert_eq!(decoded[0].schema().field(3).name(), "i");
        let bit_values = decoded[0]
            .column(0)
            .as_any()
            .downcast_ref::<FixedSizeBinaryArray>()
            .ok_or_else(|| io::Error::other("decoded BIT column has an unexpected type"))?;
        assert_eq!(bit_values.value(0), [0x00, 0x01]);
        assert!(bit_values.is_null(1));
        assert_eq!(bit_values.value(2), [0x01, 0x00]);
        let string_values = decoded[0]
            .column(2)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| io::Error::other("decoded text column has an unexpected type"))?;
        assert_eq!(string_values.value(0), "é");
        assert!(string_values.is_null(1));
        assert_eq!(string_values.value(2), "");

        let split_batches = vec![batch.slice(0, 1), batch.slice(1, 1), batch.slice(2, 1)];
        let split_encoded = encode_v1(&columns, &split_batches, &pool, options())?;
        assert_eq!(encoded, split_encoded);
        Ok(())
    }

    #[test]
    fn canonical_ipc_sets_unused_validity_and_boolean_value_tail_bits(
    ) -> Result<(), Box<dyn Error>> {
        let column = column(
            "b",
            0,
            "BOOLEAN",
            SqlLogicalType::Standard,
            Some(DeclaredType::Boolean),
            false,
            None,
        );
        let columns = vec![column];
        let schema = Arc::new(Schema::new(vec![Field::new("b", DataType::Boolean, false)]));
        let batch = RecordBatch::try_new(
            schema,
            vec![Arc::new(BooleanArray::from(vec![true, false, true])) as ArrayRef],
        )?;
        let pool = pool()?;
        let encoded = encode_v1(&columns, std::slice::from_ref(&batch), &pool, options())?;
        let buffers = first_record_batch_buffers(&encoded)?;
        assert_eq!(buffers[0], [0xff]);
        assert_eq!(buffers[1], [0x05]);
        Ok(())
    }

    #[test]
    fn canonical_ipc_uses_fixed_65536_row_chunks_independent_of_input_batches(
    ) -> Result<(), Box<dyn Error>> {
        let column = column(
            "b",
            0,
            "BOOLEAN",
            SqlLogicalType::Standard,
            Some(DeclaredType::Boolean),
            false,
            None,
        );
        let columns = vec![column];
        let rows = CANONICAL_IPC_BATCH_ROWS + 1;
        let schema = Arc::new(Schema::new(vec![Field::new("b", DataType::Boolean, false)]));
        let array = Arc::new(BooleanArray::from(vec![false; rows])) as ArrayRef;
        let batch = RecordBatch::try_new(Arc::clone(&schema), vec![array])?;
        let split_batches = vec![batch.slice(0, 17_000), batch.slice(17_000, rows - 17_000)];
        let pool = pool()?;
        let whole_encoded = encode_v1(&columns, std::slice::from_ref(&batch), &pool, options())?;
        let split_encoded = encode_v1(&columns, &split_batches, &pool, options())?;
        assert_eq!(whole_encoded, split_encoded);
        assert_eq!(record_batch_rows(&whole_encoded)?, [CANONICAL_IPC_BATCH_ROWS, 1]);
        let decoded = decode_v1(&whole_encoded, &columns, &pool, options())?;
        assert_eq!(decoded.iter().map(RecordBatch::num_rows).collect::<Vec<_>>(), [
            CANONICAL_IPC_BATCH_ROWS,
            1,
        ]);
        Ok(())
    }

    #[test]
    fn canonical_ipc_preserves_nonzero_row_count_for_zero_columns(
    ) -> Result<(), Box<dyn Error>> {
        let schema = Arc::new(Schema::empty());
        let batch_options = RecordBatchOptions::new().with_row_count(Some(3));
        let batch = RecordBatch::try_new_with_options(schema, Vec::new(), &batch_options)?;
        let pool = pool()?;
        let mut call_options = options();
        call_options.budgets.max_columns = 0;
        let encoded = encode_v1(&[], std::slice::from_ref(&batch), &pool, call_options)?;
        let decoded = decode_v1(&encoded, &[], &pool, call_options)?;
        assert_eq!(decoded.len(), 1);
        assert_eq!(decoded[0].num_columns(), 0);
        assert_eq!(decoded[0].num_rows(), 3);
        Ok(())
    }

    #[test]
    fn decoder_rejects_invalid_raw_integer_width_without_panicking(
    ) -> Result<(), Box<dyn Error>> {
        let descriptor = column(
            "i",
            0,
            "BIGINT",
            SqlLogicalType::Standard,
            Some(DeclaredType::SignedInteger { bits: 64 }),
            false,
            None,
        );
        let columns = vec![descriptor];
        let schema = Arc::new(Schema::new(vec![Field::new("i", DataType::Int64, false)]));
        let batch = RecordBatch::try_new(
            schema,
            vec![Arc::new(Int64Array::from(vec![7_i64])) as ArrayRef],
        )?;
        let pool = pool()?;
        let mut bytes = encode_v1(&columns, std::slice::from_ref(&batch), &pool, options())?;
        let footer_offset = footer_start(&bytes)?;
        let trailer_start = bytes
            .len()
            .checked_sub(10)
            .ok_or_else(|| io::Error::other("IPC test trailer is missing"))?;
        let footer = root_as_footer(&bytes[footer_offset..trailer_start])
            .map_err(|error| io::Error::other(format!("invalid test footer: {error:?}")))?;
        let schema = footer
            .schema()
            .ok_or_else(|| io::Error::other("test footer schema is missing"))?;
        let fields = schema
            .fields()
            .ok_or_else(|| io::Error::other("test footer fields are missing"))?;
        let field = fields.get(0);
        let integer = field
            .type_as_int()
            .ok_or_else(|| io::Error::other("test integer type metadata is missing"))?;
        let table = integer._tab;
        let slot_offset = table.vtable().get(arrow_ipc::Int::VT_BITWIDTH);
        if slot_offset == 0 {
            return Err(io::Error::other("test integer width slot is missing").into());
        }
        let width_start = footer_offset
            .checked_add(table.loc())
            .and_then(|offset| offset.checked_add(usize::from(slot_offset)))
            .ok_or_else(|| io::Error::other("test integer width offset overflow"))?;
        let width_end = width_start
            .checked_add(std::mem::size_of::<i32>())
            .ok_or_else(|| io::Error::other("test integer width end overflow"))?;
        let width_bytes = bytes
            .get_mut(width_start..width_end)
            .ok_or_else(|| io::Error::other("test integer width is out of range"))?;
        width_bytes.copy_from_slice(&96_i32.to_le_bytes());

        let caught = std::panic::catch_unwind(AssertUnwindSafe(|| {
            decode_v1(&bytes, &columns, &pool, options())
        }));
        let result = caught.map_err(|_| io::Error::other("decoder panicked on a raw type fault"))?;
        let error = result
            .err()
            .ok_or_else(|| io::Error::other("decoder accepted an unsupported 96-bit integer"))?;
        assert_eq!(error.kind(), CanonicalIpcErrorKind::Schema);
        Ok(())
    }

    #[test]
    fn decoder_enforces_borrowed_input_byte_budget() -> Result<(), Box<dyn Error>> {
        let (columns, batch) = mapping_fixture()?;
        let pool = pool()?;
        let encoded = encode_v1(&columns, std::slice::from_ref(&batch), &pool, options())?;
        let mut call_options = options();
        call_options.budgets.max_input_bytes = encoded.len() - 1;
        let error = decode_v1(&encoded, &columns, &pool, call_options)
            .err()
            .ok_or_else(|| io::Error::other("decoder accepted an over-budget input file"))?;
        assert_eq!(error.kind(), CanonicalIpcErrorKind::Resource);
        Ok(())
    }

    #[test]
    fn canonical_encoder_checks_live_deadlines_during_large_array_work(
    ) -> Result<(), Box<dyn Error>> {
        let rows = 8_000_000_usize;
        let column = column(
            "i",
            0,
            "BIGINT",
            SqlLogicalType::Standard,
            Some(DeclaredType::SignedInteger { bits: 64 }),
            false,
            None,
        );
        let columns = vec![column];
        let schema = Arc::new(Schema::new(vec![Field::new("i", DataType::Int64, false)]));
        let batch = RecordBatch::try_new(
            schema,
            vec![Arc::new(Int64Array::from(vec![0_i64; rows])) as ArrayRef],
        )?;
        let pool = pool()?;
        let start = Instant::now();
        let deadline = start + Duration::from_millis(100);
        assert!(Instant::now() < deadline);
        let mut call_options = options();
        call_options.budgets.max_rows = rows;
        call_options.budgets.max_input_bytes = 128 << 20;
        call_options.budgets.max_output_bytes = 256 << 20;
        call_options.budgets.max_codec_peak_bytes = 1 << 30;
        call_options.control.deadline = Some(deadline);
        let error = encode_v1(&columns, std::slice::from_ref(&batch), &pool, call_options)
            .err()
            .ok_or_else(|| io::Error::other("encoder ignored a live finite deadline"))?;
        assert_eq!(error.kind(), CanonicalIpcErrorKind::Deadline);
        Ok(())
    }

    #[test]
    fn canonical_encoder_checks_cancellation_while_scanning_arrays(
    ) -> Result<(), Box<dyn Error>> {
        let rows = 8_000_000_usize;
        let column = column(
            "i",
            0,
            "BIGINT",
            SqlLogicalType::Standard,
            Some(DeclaredType::SignedInteger { bits: 64 }),
            false,
            None,
        );
        let columns = vec![column];
        let schema = Arc::new(Schema::new(vec![Field::new("i", DataType::Int64, false)]));
        let batch = RecordBatch::try_new(
            schema,
            vec![Arc::new(Int64Array::from(vec![0_i64; rows])) as ArrayRef],
        )?;
        let pool = pool()?;
        let cancel = Arc::new(AtomicBool::new(false));
        let worker_cancel = Arc::clone(&cancel);
        let start_gate = Arc::new(Barrier::new(2));
        let worker_gate = Arc::clone(&start_gate);
        let canceller = thread::spawn(move || {
            worker_gate.wait();
            thread::sleep(Duration::from_millis(25));
            worker_cancel.store(true, Ordering::Relaxed);
        });
        let mut call_options = options();
        call_options.budgets.max_rows = rows;
        call_options.budgets.max_input_bytes = 128 << 20;
        call_options.budgets.max_output_bytes = 256 << 20;
        call_options.budgets.max_codec_peak_bytes = 1 << 30;
        call_options.control.cancel = Some(&cancel);
        start_gate.wait();
        let result = encode_v1(&columns, std::slice::from_ref(&batch), &pool, call_options);
        canceller
            .join()
            .map_err(|_| io::Error::other("cancellation helper thread panicked"))?;
        let error = result
            .err()
            .ok_or_else(|| io::Error::other("encoder ignored cancellation"))?;
        assert_eq!(error.kind(), CanonicalIpcErrorKind::Cancelled);
        Ok(())
    }
}
