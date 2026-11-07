//! Replacement-period, test-only comparison probe. E removes this module.
//! It accepts retained canonical Arrow batches and small policy metadata, and returns
//! row locator views with encoded frames for differential assertions. It is
//! never selected by the production comparison route.

use std::sync::Arc;

use arrow_array::RecordBatch;
use arrow_schema::SchemaRef;
use serde_json::{Value, json};

use super::{
    BlankProvenance, CanonicalBatchSide, KernelContext, OrderedBatchPair,
    OrderedCompareError, OrderedCompareOptions, RowLocation, StandardMode, StandardOptions,
    canonical_cell_frame_at, compare_ordered_batches, compare_standard_table,
    summarize_unchanged_ordered_batches,
};

fn bad(_message: impl std::fmt::Display) -> OrderedCompareError {
    OrderedCompareError::new("PROBE_POLICY_INVALID")
}

fn required_string<'a>(value: &'a Value, name: &str) -> Result<&'a str, OrderedCompareError> {
    value.get(name).and_then(Value::as_str)
        .ok_or_else(|| bad(format!("missing {name}")))
}

fn strings(value: &Value, name: &str) -> Result<Vec<String>, OrderedCompareError> {
    let array = value.get(name).and_then(Value::as_array)
        .ok_or_else(|| bad(format!("missing {name}")))?;
    array.iter().map(|item| item.as_str()
        .map(str::to_owned).ok_or_else(|| bad(format!("invalid {name}")))).collect()
}

fn optional_strings(value: &Value, name: &str) -> Result<Vec<String>, OrderedCompareError> {
    if value.get(name).is_none() { Ok(Vec::new()) } else { strings(value, name) }
}

fn flag(value: &Value, name: &str, default: bool) -> Result<bool, OrderedCompareError> {
    match value.get(name) {
        None => Ok(default),
        Some(item) => item.as_bool().ok_or_else(|| bad(format!("invalid {name}"))),
    }
}

fn provenance(value: &Value, name: &str) -> Result<BlankProvenance, OrderedCompareError> {
    match value.get(name).and_then(Value::as_str).unwrap_or("source") {
        "source" => Ok(BlankProvenance::SourceMissingStableKey),
        "canonical" => Ok(BlankProvenance::CanonicalPseudoGid),
        _ => Err(bad(format!("invalid {name}"))),
    }
}

fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut text = String::with_capacity(bytes.len().saturating_mul(2));
    for byte in bytes {
        text.push(char::from(DIGITS[usize::from(byte >> 4)]));
        text.push(char::from(DIGITS[usize::from(byte & 15)]));
    }
    text
}

fn frames(
    batches: &[RecordBatch], location: Option<RowLocation>, columns: &[String],
) -> Result<Value, OrderedCompareError> {
    let Some(location) = location else { return Ok(json!([])); };
    columns.iter().map(|name| {
        let frame = canonical_cell_frame_at(batches, location, name)?;
        Ok(json!({"column": name, "frame_hex": hex(&frame)}))
    }).collect::<Result<Vec<_>, OrderedCompareError>>().map(|values| json!(values))
}

fn location(value: Option<RowLocation>) -> Value {
    value.map_or(Value::Null, |place| json!({"batch":place.batch,"row":place.row}))
}

fn standard_probe(
    before_schema: SchemaRef, before: &[RecordBatch],
    current_schema: SchemaRef, current: &[RecordBatch],
    policy: &Value, context: &Arc<KernelContext>,
) -> Result<Value, OrderedCompareError> {
    let mode = match required_string(policy, "mode")? {
        "keyed" => StandardMode::Keyed,
        "keyless" => StandardMode::Keyless,
        other => return Err(bad(format!("invalid mode {other}"))),
    };
    let options = StandardOptions {
        selected_columns: strings(policy, "selected_columns")?,
        effective_key_before: optional_strings(policy, "effective_key_before")?,
        effective_key_current: optional_strings(policy, "effective_key_current")?,
        compare_excluded_columns: optional_strings(policy, "compare_excluded_columns")?,
        incompatible_columns: optional_strings(policy, "incompatible_columns")?,
        mode,
        emit_add_delete: flag(policy, "emit_add_delete", true)?,
        columns_added: flag(policy, "columns_added", false)?,
    };
    let result = compare_standard_table(
        CanonicalBatchSide::new(before_schema, before),
        CanonicalBatchSide::new(current_schema, current),
        &options, context,
    )?;
    let records = result.records.iter().map(|record| {
        Ok(json!({
            "kind": record.kind.contract_name(),
            "row_identity": record.row_identity,
            "changed_columns": record.changed_columns,
            "diagnostics": record.diagnostics,
            "before": location(record.before),
            "current": location(record.current),
            "before_frames": frames(&result.before_batches, record.before, &record.value_columns)?,
            "current_frames": frames(&result.current_batches, record.current, &record.value_columns)?,
        }))
    }).collect::<Result<Vec<_>, OrderedCompareError>>()?;
    Ok(json!({
        "row_added_count":result.row_added_count,
        "row_deleted_count":result.row_deleted_count,
        "row_modified_count":result.row_modified_count,
        "suppressed_added_count":result.suppressed_added_count,
        "suppressed_deleted_count":result.suppressed_deleted_count,
        "ignored_shared_content_changed":result.ignored_shared_content_changed,
        "records":records,
        "facts_order":result.facts_order,
        "artifact_order":result.artifact_order,
    }))
}

fn ordered_probe(
    before_schema: SchemaRef, before: &[RecordBatch],
    current_schema: SchemaRef, current: &[RecordBatch],
    policy: &Value, context: &Arc<KernelContext>,
) -> Result<Value, OrderedCompareError> {
    let mut options = OrderedCompareOptions::new(required_string(policy, "table_name")?);
    options.policy_version = required_string(policy, "policy_version")?.to_owned();
    options.policy_digest = policy.get("policy_digest").and_then(Value::as_str).map(str::to_owned);
    options.value_columns = optional_strings(policy, "value_columns")?;
    options.digest_value_columns = optional_strings(policy, "digest_value_columns")?;
    options.compare_excluded_columns = optional_strings(policy, "compare_excluded_columns")?;
    options.include_add_delete_records = flag(policy, "emit_add_delete", true)?;
    options.schema_changed = flag(policy, "schema_changed", false)?;
    options.raw_content_changed = flag(policy, "raw_content_changed", false)?;
    options.columns_added = flag(policy, "columns_added", false)?;
    if let Some(changes) = policy.get("schema_changes") {
        options.schema_changes = serde_json::from_value(changes.clone()).map_err(bad)?;
    }
    options.before_blank_provenance = provenance(policy, "before_blank_provenance")?;
    options.current_blank_provenance = provenance(policy, "current_blank_provenance")?;
    if let Some(max_rows) = policy.get("max_rows") {
        options.max_rows = max_rows.as_u64().and_then(|number| usize::try_from(number).ok())
            .ok_or_else(|| bad("invalid max_rows"))?;
    }
    if flag(policy, "unchanged", false)? {
        let summary = summarize_unchanged_ordered_batches(
            CanonicalBatchSide::new(current_schema, current), &options, context,
        )?;
        return Ok(json!({
            "unchanged":true,
            "row_count":summary.row_count,
            "before_ordered_digest":summary.before_ordered_digest,
            "current_ordered_digest":summary.current_ordered_digest,
            "before_occupancy_digest":summary.before_occupancy_digest,
            "current_occupancy_digest":summary.current_occupancy_digest,
            "records":[],
        }));
    }
    let result = compare_ordered_batches(OrderedBatchPair {
        before: Some(before), current: Some(current),
        before_schema: Some(before_schema), current_schema: Some(current_schema),
        options: &options,
    }, context)?;
    let standard = result.standard_records.iter().map(|record| {
        Ok(json!({
            "kind":record.kind.contract_name(),
            "row_identity":record.row_identity,
            "changed_columns":record.changed_columns,
            "diagnostics":record.diagnostics,
            "before":location(record.before),"current":location(record.current),
            "before_frames":frames(&result.before_batches, record.before, &record.value_columns)?,
            "current_frames":frames(&result.current_batches, record.current, &record.value_columns)?,
        }))
    }).collect::<Result<Vec<_>, OrderedCompareError>>()?;
    let ordered = result.ordered_records.iter().map(|record| {
        Ok(json!({
            "kind":record.kind,"semantic_kind":record.semantic_kind,
            "entity_key_kind":record.entity_key_kind,"row_identity":record.row_identity,
            "before_position":record.before_position,"current_position":record.current_position,
            "changed_columns":record.changed_columns,
            "before":location(record.before),"current":location(record.current),
            "before_frames":frames(&result.before_batches, record.before, &record.value_columns)?,
            "current_frames":frames(&result.current_batches, record.current, &record.value_columns)?,
        }))
    }).collect::<Result<Vec<_>, OrderedCompareError>>()?;
    let blank = result.blank_records.iter().map(|record| json!({
        "kind":record.kind,"semantic_kind":record.semantic_kind,
        "entity_key_kind":record.entity_key_kind,
        "interval":record.interval,
        "before_occupancy":record.before_occupancy,
        "current_occupancy":record.current_occupancy,
    })).collect::<Vec<_>>();
    Ok(json!({
        "status":result.facts_metadata.status,
        "row_count_before":result.facts_metadata.row_count_before,
        "row_count_current":result.facts_metadata.row_count_current,
        "row_added_count":result.facts_metadata.row_added_count,
        "row_deleted_count":result.facts_metadata.row_deleted_count,
        "row_modified_count":result.facts_metadata.row_modified_count,
        "suppressed_added_count":result.facts_metadata.suppressed_added_count,
        "suppressed_deleted_count":result.facts_metadata.suppressed_deleted_count,
        "content_changed":result.facts_metadata.content_changed,
        "ordered_summary":result.facts_metadata.ordered_extension.summary,
        "blank_summary":result.facts_metadata.blank_extension.summary,
        "before_ordered_digest":result.facts_metadata.ordered_extension.before_ordered_digest,
        "current_ordered_digest":result.facts_metadata.ordered_extension.current_ordered_digest,
        "before_occupancy_digest":result.facts_metadata.blank_extension.before_occupancy_digest,
        "current_occupancy_digest":result.facts_metadata.blank_extension.current_occupancy_digest,
        "standard_records":standard,
        "ordered_records":ordered,
        "blank_records":blank,
        "standard_facts_order":result.standard_facts_order,
        "standard_artifact_order":result.standard_artifact_order,
        "ordered_facts_order":result.ordered_facts_order,
        "ordered_artifact_order":result.ordered_artifact_order,
        "blank_facts_order":result.blank_facts_order,
        "blank_artifact_order":result.blank_artifact_order,
    }))
}

pub fn comparison_probe_json(
    kind: &str,
    before_schema: SchemaRef,
    before: &[RecordBatch],
    current_schema: SchemaRef,
    current: &[RecordBatch],
    policy_json: &str,
    context: &Arc<KernelContext>,
) -> Result<String, OrderedCompareError> {
    let policy: Value = serde_json::from_str(policy_json).map_err(bad)?;
    let output = match kind {
        "standard" => standard_probe(
            before_schema, before, current_schema, current, &policy, context,
        )?,
        "ordered" => ordered_probe(
            before_schema, before, current_schema, current, &policy, context,
        )?,
        _ => return Err(bad("unknown comparison probe kind")),
    };
    serde_json::to_string(&output).map_err(bad)
}
