//! Operation-owned resource and lifetime boundary for comparison kernels.

use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Instant;

use arrow_array::RecordBatch;
use arrow_schema::DataType;
use serde_json::Value;

use super::ordered::OrderedCompareError;

/// The caller owns one context for its operation. `remaining_bytes` excludes
/// memory already pinned and charged by the Arrow input owner.
pub struct KernelContext {
    remaining_bytes: AtomicUsize,
    cancelled: Arc<AtomicBool>,
    deadline: Option<Instant>,
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
        if self.deadline.is_some_and(|deadline| Instant::now() >= deadline) {
            return Err(OrderedCompareError::new("COMPARISON_DEADLINE_EXCEEDED"));
        }
        Ok(())
    }

    /// Reserve before allocating. The returned lease keeps that charge until
    /// the last result owner drops it; failed work releases it automatically.
    pub fn reserve(self: &Arc<Self>, bytes: usize) -> Result<KernelLease, OrderedCompareError> {
        self.check()?;
        self.remaining_bytes
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |left| left.checked_sub(bytes))
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
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |left| left.checked_sub(bytes))
            .map_err(|_| OrderedCompareError::new("RESOURCE_LIMIT_EXCEEDED"))?;
        self.charged_bytes = total;
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

/// A new comparison call accepts only the S2b canonical Arrow profile. The
/// old ordered prototype keeps its fixture-specific metadata until E removes
/// that test surface; it is not accepted by this entry.
pub(super) fn validate_canonical_batches(
    batches: &[RecordBatch],
) -> Result<(), OrderedCompareError> {
    for batch in batches {
        let schema = batch.schema();
        if schema.metadata().get("gdds.canonical_mapping_version").map(String::as_str) != Some("1") {
            return Err(OrderedCompareError::new("CANONICAL_SCHEMA_REQUIRED"));
        }
        for field in schema.fields() {
            let metadata = field.metadata().get("gdds.canonical_type")
                .ok_or_else(|| OrderedCompareError::new("CANONICAL_TYPE_REQUIRED"))?;
            let value: Value = serde_json::from_str(metadata)
                .map_err(|_| OrderedCompareError::new("CANONICAL_TYPE_INVALID"))?;
            let logical = value.get("logical_type").and_then(Value::as_str)
                .ok_or_else(|| OrderedCompareError::new("CANONICAL_TYPE_INVALID"))?;
            let spelling = value.get("sql_type").and_then(Value::as_str)
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
            let text = matches!(physical, DataType::Utf8 | DataType::LargeUtf8);
            let valid = match logical {
                "set" => {
                    value.get("declared_type").is_some_and(Value::is_null)
                        && value.get("labels").and_then(Value::as_array).is_some()
                        && text
                }
                "enum" | "json" => text,
                "standard" => {
                    match value.get("declared_type").and_then(|part| part.get("kind")).and_then(Value::as_str) {
                        Some("boolean") => matches!(physical, DataType::Boolean),
                        Some("signed-integer") => matches!(physical, DataType::Int64),
                        Some("unsigned-integer") => matches!(physical, DataType::UInt64),
                        Some("float32") => matches!(physical, DataType::Float32),
                        Some("float64") => matches!(physical, DataType::Float64),
                        Some("binary") | Some("bit") => matches!(physical, DataType::Binary | DataType::LargeBinary | DataType::FixedSizeBinary(_)),
                        Some("decimal" | "string" | "date" | "datetime" | "timestamp" | "time-duration") => text,
                        _ => false,
                    }
                }
                _ => false,
            };
            if !valid {
                return Err(OrderedCompareError::new("CANONICAL_TYPE_INVALID"));
            }
        }
    }
    Ok(())
}
