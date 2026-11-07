//! Operation-owned resource and lifetime boundary for comparison kernels.

use std::cmp::Ordering as CompareOrder;
use std::collections::HashSet;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::Instant;

use arrow_array::RecordBatch;
use arrow_schema::{DataType, SchemaRef};
use gateway_shared_kernel::DeclaredType;
use serde_json::Value;

use super::ordered::{OrderedCompareError, declared_type};

/// The caller owns one context for its operation. `remaining_bytes` excludes
/// memory already pinned and charged by the Arrow input owner.
pub struct KernelContext {
    remaining_bytes: AtomicUsize,
    cancelled: Arc<AtomicBool>,
    deadline: Option<Instant>,
}

/// An explicit schema distinguishes a zero-batch empty table from a missing
/// side. RecordBatch clones retain Arrow buffer Arcs after a reader closes.
pub struct CanonicalBatchSide<'a> {
    pub schema: SchemaRef,
    pub batches: &'a [RecordBatch],
}

impl<'a> CanonicalBatchSide<'a> {
    pub fn new(schema: SchemaRef, batches: &'a [RecordBatch]) -> Self {
        Self { schema, batches }
    }
}

impl KernelContext {
    pub fn new(
        remaining_bytes: usize,
        cancelled: Arc<AtomicBool>,
        deadline: Option<Instant>,
    ) -> Self {
        Self {
            remaining_bytes: AtomicUsize::new(remaining_bytes),
            cancelled,
            deadline,
        }
    }

    pub fn check(&self) -> Result<(), OrderedCompareError> {
        if self.cancelled.load(Ordering::Relaxed) {
            return Err(OrderedCompareError::new("COMPARISON_CANCELLED"));
        }
        if self
            .deadline
            .is_some_and(|deadline| Instant::now() >= deadline)
        {
            return Err(OrderedCompareError::new("COMPARISON_DEADLINE_EXCEEDED"));
        }
        Ok(())
    }

    /// Reserve before allocating. The returned lease keeps that charge until
    /// the last result owner drops it; failed work releases it automatically.
    pub fn reserve(self: &Arc<Self>, bytes: usize) -> Result<KernelLease, OrderedCompareError> {
        self.check()?;
        self.remaining_bytes
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |left| {
                left.checked_sub(bytes)
            })
            .map_err(|_| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        Ok(KernelLease {
            context: Arc::clone(self),
            charged_bytes: bytes,
        })
    }

    pub fn remaining_bytes(&self) -> usize {
        self.remaining_bytes.load(Ordering::Acquire)
    }
}

pub struct KernelLease {
    context: Arc<KernelContext>,
    charged_bytes: usize,
}

impl KernelLease {
    /// Check and charge before a result index or variable-width field grows.
    pub fn grow(&mut self, bytes: usize) -> Result<(), OrderedCompareError> {
        self.context.check()?;
        let total = self
            .charged_bytes
            .checked_add(bytes)
            .ok_or_else(|| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        self.context
            .remaining_bytes
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |left| {
                left.checked_sub(bytes)
            })
            .map_err(|_| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        self.charged_bytes = total;
        Ok(())
    }

    /// Release scratch after the result has been built. `retained_bytes`
    /// includes the result's own vectors and strings, but not the already
    /// charged Arrow backing retained through cloned RecordBatch owners.
    pub fn shrink_to(&mut self, retained_bytes: usize) -> Result<(), OrderedCompareError> {
        if retained_bytes > self.charged_bytes {
            return Err(OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"));
        }
        self.context
            .remaining_bytes
            .fetch_add(self.charged_bytes - retained_bytes, Ordering::Release);
        self.charged_bytes = retained_bytes;
        Ok(())
    }
}

impl Drop for KernelLease {
    fn drop(&mut self) {
        self.context
            .remaining_bytes
            .fetch_add(self.charged_bytes, Ordering::Release);
    }
}

/// Stable fallible index sort. Batch checks also cover large merge stages;
/// record payloads stay in their owner and only indexes are rearranged.
pub(super) fn sort_indices_checked<T>(
    items: &[T],
    context: &KernelContext,
    compare: impl Fn(&T, &T) -> CompareOrder,
) -> Result<Vec<usize>, OrderedCompareError> {
    context.check()?;
    let count = items.len();
    let mut order: Vec<usize> = (0..count).collect();
    let mut scratch = Vec::with_capacity(count);
    let mut width = 1usize;
    while width < count {
        scratch.clear();
        let mut start = 0usize;
        while start < count {
            context.check()?;
            let mid = start.saturating_add(width).min(count);
            let end = mid.saturating_add(width).min(count);
            let (mut left, mut right) = (start, mid);
            while left < mid && right < end {
                if scratch.len() % 1024 == 0 {
                    context.check()?;
                }
                if compare(&items[order[left]], &items[order[right]]) != CompareOrder::Greater {
                    scratch.push(order[left]);
                    left += 1;
                } else {
                    scratch.push(order[right]);
                    right += 1;
                }
            }
            scratch.extend_from_slice(&order[left..mid]);
            scratch.extend_from_slice(&order[right..end]);
            start = end;
        }
        std::mem::swap(&mut order, &mut scratch);
        width = width.saturating_mul(2);
    }
    context.check()?;
    Ok(order)
}

/// A new comparison call accepts only the S2b canonical Arrow profile. The
/// old ordered prototype keeps its fixture-specific metadata until E removes
/// that test surface; it is not accepted by this entry.
pub(super) fn validate_canonical_batches(
    side: &CanonicalBatchSide<'_>,
) -> Result<(), OrderedCompareError> {
    let schema = &side.schema;
    if schema
        .metadata()
        .get("gdds.canonical_mapping_version")
        .map(String::as_str)
        != Some("1")
    {
        return Err(OrderedCompareError::new("CANONICAL_SCHEMA_REQUIRED"));
    }
    for field in schema.fields() {
        let metadata = field
            .metadata()
            .get("gdds.canonical_type")
            .ok_or_else(|| OrderedCompareError::new("CANONICAL_TYPE_REQUIRED"))?;
        let value: Value = serde_json::from_str(metadata)
            .map_err(|_| OrderedCompareError::new("CANONICAL_TYPE_INVALID"))?;
        let logical = value
            .get("logical_type")
            .and_then(Value::as_str)
            .ok_or_else(|| OrderedCompareError::new("CANONICAL_TYPE_INVALID"))?;
        let spelling = value
            .get("sql_type")
            .and_then(Value::as_str)
            .ok_or_else(|| OrderedCompareError::new("CANONICAL_TYPE_INVALID"))?;
        let normalized = spelling.trim().to_ascii_lowercase();
        let expected_logical = if normalized.starts_with("set(") {
            "set"
        } else if normalized.starts_with("enum(") {
            "enum"
        } else if normalized == "json" {
            "json"
        } else {
            "standard"
        };
        if logical != expected_logical {
            return Err(OrderedCompareError::new("CANONICAL_TYPE_INVALID"));
        }
        let physical = field.data_type();
        if logical == "standard" {
            let declared = declared_type(spelling, physical)
                .map_err(|_| OrderedCompareError::new("CANONICAL_TYPE_INVALID"))?;
            let expected_kind = match &declared {
                DeclaredType::Boolean => "boolean",
                DeclaredType::SignedInteger { .. } => "signed-integer",
                DeclaredType::UnsignedInteger { .. } => "unsigned-integer",
                DeclaredType::Decimal { .. } => "decimal",
                DeclaredType::Float32 => "float32",
                DeclaredType::Float64 => "float64",
                DeclaredType::String => "string",
                DeclaredType::Binary => "binary",
                DeclaredType::Bit { .. } => "bit",
                DeclaredType::Date => "date",
                DeclaredType::DateTime => "datetime",
                DeclaredType::Timestamp => "timestamp",
                DeclaredType::TimeDuration => "time-duration",
                DeclaredType::Null | DeclaredType::SourceLiteralAnomaly => {
                    return Err(OrderedCompareError::new("CANONICAL_TYPE_INVALID"));
                }
            };
            let metadata = value
                .get("declared_type")
                .ok_or_else(|| OrderedCompareError::new("CANONICAL_TYPE_INVALID"))?;
            if metadata.get("kind").and_then(Value::as_str) != Some(expected_kind) {
                return Err(OrderedCompareError::new("CANONICAL_TYPE_INVALID"));
            }
            let expected_parameters = match &declared {
                DeclaredType::SignedInteger { bits } | DeclaredType::UnsignedInteger { bits } => {
                    ("bits", u64::from(*bits))
                }
                DeclaredType::Decimal { precision, .. } => ("precision", u64::from(*precision)),
                DeclaredType::Bit { bit_width } => ("bit_width", u64::from(*bit_width)),
                _ => ("", 0),
            };
            if !expected_parameters.0.is_empty()
                && metadata.get(expected_parameters.0).and_then(Value::as_u64)
                    != Some(expected_parameters.1)
            {
                return Err(OrderedCompareError::new("CANONICAL_TYPE_INVALID"));
            }
            if let DeclaredType::Decimal { scale, .. } = &declared
                && metadata.get("scale").and_then(Value::as_u64) != Some(u64::from(*scale))
            {
                return Err(OrderedCompareError::new("CANONICAL_TYPE_INVALID"));
            }
        }
        let text = matches!(physical, DataType::Utf8 | DataType::LargeUtf8);
        let labels_valid = |set: bool| {
            let Some(labels) = value.get("labels").and_then(Value::as_array) else {
                return false;
            };
            if labels.is_empty() || (set && labels.len() > 64) {
                return false;
            }
            let mut seen = HashSet::new();
            labels.iter().all(|item| {
                item.as_str().is_some_and(|label| {
                    (!set || (!label.is_empty() && !label.contains(','))) && seen.insert(label)
                })
            })
        };
        let valid = match logical {
            "set" => {
                value.get("declared_type").is_some_and(Value::is_null) && labels_valid(true) && text
            }
            "enum" => {
                value
                    .get("declared_type")
                    .and_then(|part| part.get("kind"))
                    .and_then(Value::as_str)
                    == Some("string")
                    && labels_valid(false)
                    && text
            }
            "json" => {
                value
                    .get("declared_type")
                    .and_then(|part| part.get("kind"))
                    .and_then(Value::as_str)
                    == Some("string")
                    && value.get("labels").is_some_and(Value::is_null)
                    && text
            }
            "standard" => {
                value.get("labels").is_some_and(Value::is_null)
                    && match value
                        .get("declared_type")
                        .and_then(|part| part.get("kind"))
                        .and_then(Value::as_str)
                    {
                        Some("boolean") => matches!(physical, DataType::Boolean),
                        Some("signed-integer") => matches!(physical, DataType::Int64),
                        Some("unsigned-integer") => matches!(physical, DataType::UInt64),
                        Some("float32") => matches!(physical, DataType::Float32),
                        Some("float64") => matches!(physical, DataType::Float64),
                        Some("binary") => {
                            matches!(physical, DataType::Binary | DataType::LargeBinary)
                        }
                        Some("bit") => value
                            .get("declared_type")
                            .and_then(|part| part.get("bit_width"))
                            .and_then(Value::as_u64)
                            .and_then(|bits| i32::try_from(bits.div_ceil(8)).ok())
                            .is_some_and(|width| physical == &DataType::FixedSizeBinary(width)),
                        Some(
                            "decimal" | "string" | "date" | "datetime" | "timestamp"
                            | "time-duration",
                        ) => text,
                        _ => false,
                    }
            }
            _ => false,
        };
        if !valid {
            return Err(OrderedCompareError::new("CANONICAL_TYPE_INVALID"));
        }
    }
    for batch in side.batches {
        if batch.schema().as_ref() != schema.as_ref() {
            return Err(OrderedCompareError::new("CANONICAL_SCHEMA_MISMATCH"));
        }
    }
    Ok(())
}
