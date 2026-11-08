//! Complete facts-table and facts-core JCS replay over B's locator order.

use std::sync::Arc;

use gateway_shared_kernel::{DigestRef, canonicalize_jcs};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use crate::comparison::{
    KernelContext, OrderedKernelResult, RowLocation, StandardComputation, StandardRecordRef,
    canonical_cell_frame_at,
};

pub struct TableFactsSource<'a> {
    /// The small `_table_digest_payload` shape with each records array empty.
    /// It contains the full stable table metadata, never row payloads.
    pub metadata: &'a Value,
    pub standard: Option<&'a StandardComputation>,
    pub ordered: Option<&'a OrderedKernelResult>,
}

pub struct TableFactsInput<'a> {
    pub metadata_json: &'a str,
    pub standard: Option<&'a StandardComputation>,
    pub ordered: Option<&'a OrderedKernelResult>,
}

pub fn digest_table_fact_json(
    input: TableFactsInput<'_>,
    max_jcs_row_bytes: usize,
    context: &Arc<KernelContext>,
) -> Result<DigestRef, String> {
    let metadata = parse_small_json(input.metadata_json)?;
    digest_table_fact(&TableFactsSource {
        metadata: &metadata, standard: input.standard, ordered: input.ordered,
    }, max_jcs_row_bytes, context)
}

pub fn digest_facts_core_json(
    algorithm_version: &str,
    summary_json: &str,
    inputs: &[TableFactsInput<'_>],
    max_jcs_row_bytes: usize,
    context: &Arc<KernelContext>,
) -> Result<DigestRef, String> {
    let summary = parse_small_json(summary_json)?;
    let metadata = inputs.iter().map(|input| parse_small_json(input.metadata_json))
        .collect::<Result<Vec<_>, _>>()?;
    let sources = inputs.iter().zip(&metadata).map(|(input, value)| TableFactsSource {
        metadata: value, standard: input.standard, ordered: input.ordered,
    }).collect::<Vec<_>>();
    digest_facts_core(algorithm_version, &summary, &sources, max_jcs_row_bytes, context)
}

fn parse_small_json(raw: &str) -> Result<Value, String> {
    if raw.len() > 1024 * 1024 { return Err("facts metadata exceeds limit".to_string()); }
    serde_json::from_str(raw).map_err(|error| error.to_string())
}

#[derive(Clone, Copy)]
enum Part {
    Root,
    OrderedExtension,
    BlankExtension,
    Other,
}

pub fn digest_table_fact(
    source: &TableFactsSource<'_>,
    max_jcs_row_bytes: usize,
    context: &Arc<KernelContext>,
) -> Result<DigestRef, String> {
    let _scratch = context.reserve(max_jcs_row_bytes).map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    write_table(&mut hasher, source, max_jcs_row_bytes, context)?;
    digest_ref(hasher)
}

/// `summary` precedes `tables` in JCS. Each complete table payload is replayed
/// into the same sink; table digests are not concatenated as a substitute.
pub fn digest_facts_core(
    algorithm_version: &str,
    summary: &Value,
    tables: &[TableFactsSource<'_>],
    max_jcs_row_bytes: usize,
    context: &Arc<KernelContext>,
) -> Result<DigestRef, String> {
    let _scratch = context.reserve(max_jcs_row_bytes).map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    hasher.update(b"{\"algorithm_version\":");
    write_small(&mut hasher, &json!(algorithm_version), max_jcs_row_bytes)?;
    hasher.update(b",\"kind\":\"comparison-facts-core\",\"summary\":");
    write_small(&mut hasher, summary, max_jcs_row_bytes)?;
    hasher.update(b",\"tables\":[");
    for (index, table) in tables.iter().enumerate() {
        context.check().map_err(|error| error.to_string())?;
        if index != 0 { hasher.update(b","); }
        write_table(&mut hasher, table, max_jcs_row_bytes, context)?;
    }
    hasher.update(b"]}");
    digest_ref(hasher)
}

fn write_table(
    hasher: &mut Sha256,
    source: &TableFactsSource<'_>,
    max_bytes: usize,
    context: &KernelContext,
) -> Result<(), String> {
    write_value(hasher, source.metadata, source, Part::Root, max_bytes, context)
}

fn write_value(
    hasher: &mut Sha256,
    value: &Value,
    source: &TableFactsSource<'_>,
    part: Part,
    max_bytes: usize,
    context: &KernelContext,
) -> Result<(), String> {
    match value {
        Value::Object(object) => {
            hasher.update(b"{");
            let mut keys: Vec<&str> = object.keys().map(String::as_str).collect();
            keys.sort_by(|left, right| left.encode_utf16().cmp(right.encode_utf16()));
            for (index, key) in keys.into_iter().enumerate() {
                if index != 0 { hasher.update(b","); }
                write_small(hasher, &json!(key), max_bytes)?;
                hasher.update(b":");
                let child = object.get(key).ok_or("facts table object changed")?;
                if key == "records" && matches!(part, Part::Root | Part::OrderedExtension | Part::BlankExtension) {
                    if child.as_array().is_none_or(|items| !items.is_empty()) {
                        return Err("facts metadata must contain empty records arrays".to_string());
                    }
                    write_records(hasher, source, part, max_bytes, context)?;
                } else {
                    let child_part = match (part, key) {
                        (Part::Root, "ordered_extension") => Part::OrderedExtension,
                        (Part::Root, "blank_extension") => Part::BlankExtension,
                        _ => Part::Other,
                    };
                    write_value(hasher, child, source, child_part, max_bytes, context)?;
                }
            }
            hasher.update(b"}");
        }
        Value::Array(items) => {
            hasher.update(b"[");
            for (index, item) in items.iter().enumerate() {
                if index != 0 { hasher.update(b","); }
                write_value(hasher, item, source, Part::Other, max_bytes, context)?;
            }
            hasher.update(b"]");
        }
        _ => write_small(hasher, value, max_bytes)?,
    }
    Ok(())
}

fn write_records(
    hasher: &mut Sha256,
    source: &TableFactsSource<'_>,
    part: Part,
    max_bytes: usize,
    context: &KernelContext,
) -> Result<(), String> {
    let count = match part {
        Part::Root => source.standard.map_or_else(
            || source.ordered.map_or(0, |result| result.standard_facts_order.len()),
            |result| result.facts_order.len(),
        ),
        Part::OrderedExtension => source.ordered.map_or(0, |result| result.ordered_facts_order.len()),
        Part::BlankExtension => source.ordered.map_or(0, |result| result.blank_facts_order.len()),
        Part::Other => return Err("invalid facts records part".to_string()),
    };
    hasher.update(b"[");
    for position in 0..count {
        context.check().map_err(|error| error.to_string())?;
        if position != 0 { hasher.update(b","); }
        let value = match part {
            Part::Root => {
                if let Some(result) = source.standard {
                    let index = result.facts_order[position];
                    standard_fact(&result.records[index], &result.before_batches, &result.current_batches)?
                } else {
                    let result = source.ordered.ok_or("facts standard source missing")?;
                    let index = result.standard_facts_order[position];
                    standard_fact(&result.standard_records[index], &result.before_batches, &result.current_batches)?
                }
            }
            Part::OrderedExtension => {
                let result = source.ordered.ok_or("facts ordered source missing")?;
                let record = &result.ordered_records[result.ordered_facts_order[position]];
                json!({
                    "record_kind": record.kind,
                    "semantic_kind": record.semantic_kind,
                    "entity_key_kind": record.entity_key_kind,
                    "row_identity": record.row_identity,
                    "before_position": record.before_position,
                    "current_position": record.current_position,
                    "changed_columns": record.changed_columns,
                    "before_values": frame_values(&result.before_batches, record.before, &record.value_columns)?,
                    "current_values": frame_values(&result.current_batches, record.current, &record.value_columns)?,
                })
            }
            Part::BlankExtension => {
                let result = source.ordered.ok_or("facts blank source missing")?;
                let record = &result.blank_records[result.blank_facts_order[position]];
                json!({
                    "record_kind": record.kind,
                    "semantic_kind": record.semantic_kind,
                    "entity_key_kind": record.entity_key_kind,
                    "interval": {
                        "before_start": record.interval.before_start,
                        "before_end": record.interval.before_end,
                        "current_start": record.interval.current_start,
                        "current_end": record.interval.current_end,
                        "row_count": record.interval.row_count,
                        "interval_digest": record.interval.interval_digest,
                    },
                    "before_occupancy": record.before_occupancy,
                    "current_occupancy": record.current_occupancy,
                })
            }
            Part::Other => return Err("invalid facts records part".to_string()),
        };
        write_small(hasher, &value, max_bytes)?;
    }
    hasher.update(b"]");
    Ok(())
}

fn standard_fact(
    record: &StandardRecordRef,
    before: &[arrow_array::RecordBatch],
    current: &[arrow_array::RecordBatch],
) -> Result<Value, String> {
    let field_changes = record.changed_columns.iter().map(|column| {
        Ok(json!({
            "column": column,
            "before": frame_at(before, record.before, column)?,
            "current": frame_at(current, record.current, column)?,
        }))
    }).collect::<Result<Vec<_>, String>>()?;
    Ok(json!({
        "kind": record.kind.contract_name(),
        "row_identity": record.row_identity,
        "changed_columns": record.changed_columns,
        "before_values": frame_values(before, record.before, &record.value_columns)?,
        "current_values": frame_values(current, record.current, &record.value_columns)?,
        "field_changes": field_changes,
    }))
}

fn frame_values(
    batches: &[arrow_array::RecordBatch],
    location: Option<RowLocation>,
    columns: &[String],
) -> Result<Vec<Value>, String> {
    let Some(location) = location else { return Ok(Vec::new()) };
    columns.iter().map(|column| {
        Ok(json!([column, frame_at(batches, Some(location), column)?]))
    }).collect()
}

fn frame_at(
    batches: &[arrow_array::RecordBatch],
    location: Option<RowLocation>,
    column: &str,
) -> Result<String, String> {
    let Some(location) = location else { return Err("facts frame location missing".to_string()) };
    let frame = canonical_cell_frame_at(batches, location, column).map_err(|error| error.to_string())?;
    Ok(hex_bytes(&frame))
}

fn write_small(hasher: &mut Sha256, value: &Value, max_bytes: usize) -> Result<(), String> {
    let encoded = serde_json::to_vec(value).map_err(|error| error.to_string())?;
    if encoded.len() > max_bytes { return Err("facts JCS row budget exceeded".to_string()); }
    let canonical = canonicalize_jcs(&encoded).map_err(|error| error.to_string())?;
    if canonical.len() > max_bytes { return Err("facts JCS row budget exceeded".to_string()); }
    hasher.update(canonical);
    Ok(())
}

fn digest_ref(hasher: Sha256) -> Result<DigestRef, String> {
    DigestRef::from_raw_digest(&hasher.finalize()).map_err(|error| error.to_string())
}

fn hex_bytes(bytes: &[u8]) -> String {
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        use std::fmt::Write;
        let _ = write!(&mut result, "{byte:02x}");
    }
    result
}
