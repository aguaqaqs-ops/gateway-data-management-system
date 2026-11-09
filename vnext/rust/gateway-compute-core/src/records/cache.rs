//! Neutral facts views. No I/O or artifact locators enter the core.

use std::sync::Arc;

use arrow_array::builder::{LargeBinaryBuilder, UInt32Builder};
use arrow_array::{Array, LargeBinaryArray, RecordBatch, UInt32Array};
use arrow_schema::{DataType, Field, Schema, SchemaRef};
use gateway_shared_kernel::{canonicalize_identifier, canonicalize_jcs};
use serde_json::Value;
use sha2::{Digest, Sha256};

use super::builders::charge_arrow_batches;
use super::facts::{Part, TableFactsSource, fact_row_upper, fact_row_value, facts_count};
use crate::comparison::{KernelContext, OrderedKernelResult, StandardComputation};

/// Parsed small metadata stays in the core, where JSON validation is owned.
pub struct CacheMetadata(Value);

impl CacheMetadata {
    pub fn parse(raw: &str) -> Result<Self, String> {
        let value: Value = serde_json::from_str(raw).map_err(|error| error.to_string())?;
        if !value.is_object() {
            return Err("neutral metadata must be an object".to_string());
        }
        Ok(Self(value))
    }

    pub fn validate(&self, kind: &str, counts: [usize; 3]) -> Result<(), String> {
        validate_cache_metadata(kind, &self.0, counts)
    }
}

pub fn validate_neutral_risk_column(name: &str) -> Result<(), String> {
    if canonicalize_identifier(name).map_err(|error| error.to_string())? != name {
        return Err("neutral risk changed column is invalid".to_string());
    }
    Ok(())
}

pub struct NeutralFacts {
    pub standard: Vec<RecordBatch>,
    pub ordered: Vec<RecordBatch>,
    pub blank: Vec<RecordBatch>,
}

pub fn facts_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("ordinal", DataType::UInt32, false),
        Field::new("row_jcs", DataType::LargeBinary, false),
    ]))
}

fn part(family: &str) -> Result<Part, String> {
    match family {
        "STANDARD" => Ok(Part::Root),
        "ORDERED" => Ok(Part::OrderedExtension),
        "BLANK" => Ok(Part::BlankExtension),
        _ => Err("unknown facts family".to_string()),
    }
}

impl NeutralFacts {
    pub fn family(&self, family: &str) -> Result<&[RecordBatch], String> {
        match family {
            "STANDARD" => Ok(&self.standard),
            "ORDERED" => Ok(&self.ordered),
            "BLANK" => Ok(&self.blank),
            _ => Err("unknown facts family".to_string()),
        }
    }

    pub fn validate(
        &self,
        max_records: usize,
        max_row_bytes: usize,
        context: &Arc<KernelContext>,
    ) -> Result<(), String> {
        for family in ["STANDARD", "ORDERED", "BLANK"] {
            let mut ordinal = 0usize;
            for batch in self.family(family)? {
                context.check().map_err(|error| error.to_string())?;
                if batch.schema().as_ref() != facts_schema().as_ref() || batch.num_rows() > 1024 {
                    return Err("invalid neutral facts Arrow schema/batch".to_string());
                }
                let ordinals = batch
                    .column(0)
                    .as_any()
                    .downcast_ref::<UInt32Array>()
                    .ok_or("invalid facts ordinal type")?;
                let rows = batch
                    .column(1)
                    .as_any()
                    .downcast_ref::<LargeBinaryArray>()
                    .ok_or("invalid facts row type")?;
                for row in 0..batch.num_rows() {
                    if row % 256 == 0 {
                        context.check().map_err(|error| error.to_string())?;
                    }
                    if ordinal >= max_records
                        || ordinals.is_null(row)
                        || rows.is_null(row)
                        || usize::try_from(ordinals.value(row))
                            .map_err(|error| error.to_string())?
                            != ordinal
                    {
                        return Err("invalid facts count/ordinal/null".to_string());
                    }
                    let raw = rows.value(row);
                    if raw.len() > max_row_bytes {
                        return Err("facts JCS row budget exceeded".to_string());
                    }
                    let _scratch = context
                        .reserve(super::json_metadata_upper(
                            std::str::from_utf8(raw).map_err(|error| error.to_string())?,
                        )?)
                        .map_err(|error| error.to_string())?;
                    validate_facts_row(family, raw)?;
                    ordinal += 1;
                }
            }
        }
        Ok(())
    }

    pub(super) fn write_family(
        &self,
        sink: &mut Sha256,
        part: Part,
        context: &KernelContext,
    ) -> Result<(), String> {
        let batches = match part {
            Part::Root => &self.standard,
            Part::OrderedExtension => &self.ordered,
            Part::BlankExtension => &self.blank,
            Part::Other => return Err("invalid facts part".to_string()),
        };
        sink.update(b"[");
        let mut first = true;
        for batch in batches {
            context.check().map_err(|error| error.to_string())?;
            let rows = batch
                .column(1)
                .as_any()
                .downcast_ref::<LargeBinaryArray>()
                .ok_or("invalid facts row type")?;
            for row in 0..rows.len() {
                if row % 256 == 0 {
                    context.check().map_err(|error| error.to_string())?;
                }
                if !first {
                    sink.update(b",");
                }
                first = false;
                sink.update(rows.value(row));
            }
        }
        sink.update(b"]");
        Ok(())
    }
}

/// Export the existing facts orders without exposing JSON values to the FFI.
pub fn export_neutral_facts(
    standard: Option<&StandardComputation>,
    ordered: Option<&OrderedKernelResult>,
    neutral: Option<&NeutralFacts>,
    max_row_bytes: usize,
    context: &Arc<KernelContext>,
    owner: Arc<dyn std::any::Any + Send + Sync>,
) -> Result<NeutralFacts, String> {
    let metadata = serde_json::json!({"table_name": "neutral"});
    let source = TableFactsSource {
        metadata: &metadata,
        standard,
        ordered,
        neutral,
    };
    Ok(NeutralFacts {
        standard: export_facts_family(&source, "STANDARD", max_row_bytes, context, owner.clone())?,
        ordered: export_facts_family(&source, "ORDERED", max_row_bytes, context, owner.clone())?,
        blank: export_facts_family(&source, "BLANK", max_row_bytes, context, owner)?,
    })
}

fn export_facts_family(
    source: &TableFactsSource<'_>,
    family: &str,
    max_row_bytes: usize,
    context: &Arc<KernelContext>,
    owner: Arc<dyn std::any::Any + Send + Sync>,
) -> Result<Vec<RecordBatch>, String> {
    if let Some(neutral) = source.neutral {
        return Ok(neutral.family(family)?.to_vec());
    }
    let part = part(family)?;
    let count = facts_count(source, part)?;
    let table = source
        .metadata
        .get("table_name")
        .and_then(Value::as_str)
        .ok_or("facts table_name missing")?;
    let mut lease = context
        .reserve(512 * 1024)
        .map_err(|error| error.to_string())?;
    let mut batches = Vec::new();
    for start in (0..count).step_by(1024) {
        context.check().map_err(|error| error.to_string())?;
        lease.grow(32 * 1024).map_err(|error| error.to_string())?;
        let mut ordinals = UInt32Builder::with_capacity(1024);
        let mut rows = LargeBinaryBuilder::new();
        for position in start..count.min(start + 1024) {
            let upper = fact_row_upper(source, part, position, table)?
                .checked_mul(8)
                .and_then(|size| size.checked_add(4096))
                .ok_or("facts export size overflow")?;
            if upper / 2 > max_row_bytes {
                return Err("facts JCS row budget exceeded".to_string());
            }
            lease.grow(upper).map_err(|error| error.to_string())?;
            let value = fact_row_value(source, part, position)?;
            let raw =
                canonicalize_jcs(&serde_json::to_vec(&value).map_err(|error| error.to_string())?)
                    .map_err(|error| error.to_string())?;
            if raw.len() > max_row_bytes {
                return Err("facts JCS row budget exceeded".to_string());
            }
            ordinals.append_value(u32::try_from(position).map_err(|error| error.to_string())?);
            rows.append_value(raw);
        }
        batches.push(
            RecordBatch::try_new(
                facts_schema(),
                vec![Arc::new(ordinals.finish()), Arc::new(rows.finish())],
            )
            .map_err(|error| error.to_string())?,
        );
    }
    charge_arrow_batches(batches, lease, owner)
}

fn exact_keys(value: &Value, expected: &[&str]) -> Result<(), String> {
    let object = value.as_object().ok_or("facts row must be an object")?;
    if object.len() != expected.len() || expected.iter().any(|key| !object.contains_key(*key)) {
        return Err("facts row fields mismatch".to_string());
    }
    Ok(())
}

fn text(value: &Value) -> Result<&str, String> {
    value
        .as_str()
        .ok_or("facts string field has wrong type".to_string())
}

fn strings(value: &Value) -> Result<(), String> {
    for item in value.as_array().ok_or("facts list field has wrong type")? {
        text(item)?;
    }
    Ok(())
}

fn identity(value: &Value, nullable: bool) -> Result<(), String> {
    if nullable && value.is_null() {
        return Ok(());
    }
    let digest = text(value)?
        .strip_prefix("sha256:")
        .ok_or("facts digest missing prefix")?;
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err("invalid facts digest".to_string());
    }
    Ok(())
}

fn position(value: &Value, nullable: bool) -> Result<(), String> {
    if nullable && value.is_null() {
        return Ok(());
    }
    if value.as_u64().is_none_or(|value| value == 0) {
        return Err("invalid facts position".to_string());
    }
    Ok(())
}

fn frames(value: &Value) -> Result<(), String> {
    for entry in value.as_array().ok_or("facts values must be a list")? {
        let entry = entry
            .as_array()
            .ok_or("facts value must be a name/frame pair")?;
        if entry.len() != 2 {
            return Err("facts value pair arity".to_string());
        }
        text(&entry[0])?;
        frame(&entry[1])?;
    }
    Ok(())
}

fn frame(value: &Value) -> Result<(), String> {
    let hex = text(value)?;
    if hex.len() % 2 != 0 || hex.len() < 2 || !hex.is_ascii() {
        return Err("invalid facts frame hex".to_string());
    }
    let bytes = hex
        .as_bytes()
        .chunks_exact(2)
        .map(|chunk| {
            let raw = std::str::from_utf8(chunk).map_err(|error| error.to_string())?;
            if raw.bytes().any(|byte| byte.is_ascii_uppercase()) {
                return Err("noncanonical frame hex".to_string());
            }
            u8::from_str_radix(raw, 16).map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if scalar_frame(&bytes).is_ok() {
        return Ok(());
    }
    set_sequence_frame(&bytes)
}

fn decode_length(bytes: &[u8], mut offset: usize) -> Result<(usize, usize), String> {
    let start = offset;
    let mut value = 0usize;
    loop {
        let byte = *bytes.get(offset).ok_or("truncated facts frame length")?;
        let shift = (offset - start) * 7;
        if shift >= 63 {
            return Err("facts frame length overflow".to_string());
        }
        value |= usize::from(byte & 0x7f)
            .checked_shl(u32::try_from(shift).map_err(|error| error.to_string())?)
            .ok_or("facts frame length overflow")?;
        offset += 1;
        if byte & 0x80 == 0 {
            if offset > start + 1 && byte == 0 {
                return Err("nonminimal facts frame length".to_string());
            }
            return Ok((value, offset));
        }
    }
}

fn set_sequence_frame(bytes: &[u8]) -> Result<(), String> {
    let (count, mut offset) = decode_length(bytes, 0)?;
    if count > 64 {
        return Err("facts SET member limit exceeded".to_string());
    }
    let mut seen = std::collections::HashSet::new();
    for _ in 0..count {
        let (size, start) = decode_length(bytes, offset)?;
        let end = start.checked_add(size).ok_or("facts SET length overflow")?;
        let item = bytes.get(start..end).ok_or("truncated facts SET member")?;
        if item.first() != Some(&0x20) {
            return Err("facts SET member must be a string scalar".to_string());
        }
        scalar_frame(item)?;
        let (_, payload) = decode_length(item, 1)?;
        if payload == item.len() || !seen.insert(&item[payload..]) {
            return Err("facts SET members must be nonempty and distinct".to_string());
        }
        offset = end;
    }
    if offset != bytes.len() {
        return Err("trailing facts SET bytes".to_string());
    }
    Ok(())
}

fn scalar_frame(bytes: &[u8]) -> Result<(), String> {
    let tag = bytes[0];
    if !matches!(tag, 0x00 | 0x01 | 0x10..=0x14 | 0x20 | 0x21 | 0x30..=0x33 | 0x7f) {
        return Err("unknown facts scalar tag".to_string());
    }
    let (length, offset) = decode_length(bytes, 1)?;
    let payload = bytes.get(offset..).ok_or("truncated facts frame")?;
    if payload.len() != length {
        return Err("facts frame length mismatch".to_string());
    }
    match tag {
        0x00 if length != 0 => return Err("invalid null frame".to_string()),
        0x01 if length != 1 || payload[0] > 1 => return Err("invalid boolean frame".to_string()),
        0x10 | 0x11 | 0x14 if length != 8 => return Err("invalid numeric frame width".to_string()),
        0x13 if length != 4 => return Err("invalid float frame width".to_string()),
        0x12 | 0x20 | 0x30..=0x33 | 0x7f => {
            std::str::from_utf8(payload).map_err(|error| error.to_string())?;
        }
        _ => {}
    }
    Ok(())
}

/// Complete neutral facts shape, canonical JSON and typed-frame validation.
pub fn validate_facts_row(family: &str, raw: &[u8]) -> Result<(), String> {
    if canonicalize_jcs(raw).map_err(|error| error.to_string())? != raw {
        return Err("facts row is not canonical JCS".to_string());
    }
    let value: Value = serde_json::from_slice(raw).map_err(|error| error.to_string())?;
    match family {
        "STANDARD" => {
            exact_keys(
                &value,
                &[
                    "kind",
                    "row_identity",
                    "changed_columns",
                    "before_values",
                    "current_values",
                    "field_changes",
                ],
            )?;
            let kind = text(&value["kind"])?;
            if !matches!(
                kind,
                "ROW_ADDED" | "ROW_DELETED" | "ROW_MODIFIED" | "SCHEMA_CHANGE" | "TABLE_DEGRADED"
            ) {
                return Err("unknown standard facts kind".to_string());
            }
            identity(
                &value["row_identity"],
                matches!(kind, "SCHEMA_CHANGE" | "TABLE_DEGRADED"),
            )?;
            strings(&value["changed_columns"])?;
            frames(&value["before_values"])?;
            frames(&value["current_values"])?;
            for change in value["field_changes"]
                .as_array()
                .ok_or("facts field_changes must be a list")?
            {
                exact_keys(change, &["column", "before", "current"])?;
                text(&change["column"])?;
                frame(&change["before"])?;
                frame(&change["current"])?;
            }
        }
        "ORDERED" => {
            exact_keys(
                &value,
                &[
                    "record_kind",
                    "semantic_kind",
                    "entity_key_kind",
                    "row_identity",
                    "before_position",
                    "current_position",
                    "changed_columns",
                    "before_values",
                    "current_values",
                ],
            )?;
            if !matches!(
                text(&value["record_kind"])?,
                "ORDERED_ROW_ADDED"
                    | "ORDERED_ROW_DELETED"
                    | "ORDERED_ROW_MODIFIED"
                    | "ORDERED_ROW_MOVED"
                    | "ORDERED_TABLE_DEGRADED"
            ) || !matches!(
                text(&value["semantic_kind"])?,
                "DATA_INSERT" | "DATA_DELETE" | "MOVE" | "CONTENT_UPDATE"
            ) || text(&value["entity_key_kind"])? != "REAL_STABLE"
            {
                return Err("invalid ordered facts kind".to_string());
            }
            identity(&value["row_identity"], false)?;
            position(&value["before_position"], true)?;
            position(&value["current_position"], true)?;
            strings(&value["changed_columns"])?;
            frames(&value["before_values"])?;
            frames(&value["current_values"])?;
        }
        "BLANK" => {
            exact_keys(
                &value,
                &[
                    "record_kind",
                    "semantic_kind",
                    "entity_key_kind",
                    "interval",
                    "before_occupancy",
                    "current_occupancy",
                ],
            )?;
            if !matches!(
                text(&value["record_kind"])?,
                "BLANK_DELETE_INTERVAL" | "BLANK_INSERT_INTERVAL"
            ) || value["record_kind"] != value["semantic_kind"]
                || text(&value["entity_key_kind"])? != "PSEUDO_BLANK"
            {
                return Err("invalid blank facts kind".to_string());
            }
            let interval = &value["interval"];
            exact_keys(
                interval,
                &[
                    "before_start",
                    "before_end",
                    "current_start",
                    "current_end",
                    "row_count",
                    "interval_digest",
                ],
            )?;
            for key in ["before_start", "before_end", "current_start", "current_end"] {
                position(&interval[key], true)?;
            }
            if interval["row_count"].as_u64().is_none()
                || value["before_occupancy"].as_u64().is_none()
                || value["current_occupancy"].as_u64().is_none()
            {
                return Err("invalid blank facts count".to_string());
            }
            identity(&interval["interval_digest"], true)?;
        }
        _ => return Err("unknown facts family".to_string()),
    }
    Ok(())
}

/// Validate the existing producer's small metadata and required family counts.
/// This proves format completeness, not an additional cross-view authenticity protocol.
fn validate_cache_metadata(kind: &str, value: &Value, counts: [usize; 3]) -> Result<(), String> {
    let standard_keys = [
        "row_added_count",
        "row_deleted_count",
        "row_modified_count",
        "suppressed_added_count",
        "suppressed_deleted_count",
        "ignored_shared_content_changed",
        "record_count",
    ];
    let ordered_keys = [
        "format",
        "version",
        "table_name",
        "status",
        "row_count_before",
        "row_count_current",
        "row_added_count",
        "row_deleted_count",
        "row_modified_count",
        "suppressed_added_count",
        "suppressed_deleted_count",
        "content_changed",
        "schema_changes",
        "diagnostics",
        "records",
        "ordered_extension",
        "blank_extension",
    ];
    match kind {
        "standard" => {
            exact_keys(value, &standard_keys)?;
            if value["ignored_shared_content_changed"].as_bool().is_none()
                || count(&value["record_count"])? != counts[0]
                || counts[1] != 0
                || counts[2] != 0
            {
                return Err("invalid standard cache metadata".to_string());
            }
        }
        "ordered" => {
            exact_keys(value, &ordered_keys)?;
            if text(&value["format"])? != crate::comparison::ordered::ORDERED_COMPARE_FORMAT
                || value["version"].as_u64()
                    != Some(u64::from(
                        crate::comparison::ordered::ORDERED_COMPARE_VERSION,
                    ))
                || text(&value["table_name"])?.is_empty()
                || !matches!(
                    text(&value["status"])?,
                    "UNCHANGED"
                        | "BUSINESS_EQUIVALENT"
                        | "MODIFIED"
                        | "SCHEMA_CHANGED"
                        | "SCHEMA_ONLY_CHANGED"
                        | "DEGRADED"
                )
                || value["content_changed"].as_bool().is_none()
            {
                return Err("invalid ordered cache metadata".to_string());
            }
            for name in ["row_count_before", "row_count_current"] {
                if !value[name].is_null() {
                    count(&value[name])?;
                }
            }
            strings(&value["diagnostics"])?;
            empty_records(&value["records"])?;
            let schema = &value["schema_changes"];
            exact_keys(
                schema,
                &[
                    "before_only_columns",
                    "current_only_columns",
                    "selected_columns",
                    "effective_compare_key_before",
                    "effective_compare_key_current",
                    "effective_compare_key_changed",
                    "incompatible_columns",
                    "change_source",
                ],
            )?;
            for name in [
                "before_only_columns",
                "current_only_columns",
                "selected_columns",
                "effective_compare_key_before",
                "effective_compare_key_current",
                "incompatible_columns",
            ] {
                strings(&schema[name])?;
            }
            if schema["effective_compare_key_changed"].as_bool().is_none()
                || !(schema["change_source"].is_null()
                    || matches!(
                        schema["change_source"].as_str(),
                        Some("SOURCE_SCHEMA" | "STORAGE_PROJECTION_POLICY" | "BOTH")
                    ))
            {
                return Err("invalid cache schema changes".to_string());
            }
            let ordered = &value["ordered_extension"];
            exact_keys(
                ordered,
                &[
                    "contract_version",
                    "status",
                    "summary",
                    "before_ordered_digest",
                    "current_ordered_digest",
                    "replay_guarantee",
                    "table_processing_mode",
                    "policy_digest",
                    "diagnostics",
                    "records",
                ],
            )?;
            extension(
                ordered,
                crate::comparison::ordered::ORDERED_DIFF_CONTRACT_VERSION,
            )?;
            for name in [
                "before_ordered_digest",
                "current_ordered_digest",
                "policy_digest",
            ] {
                identity(&ordered[name], true)?;
            }
            if !ordered["table_processing_mode"].is_null()
                && !matches!(
                    ordered["table_processing_mode"].as_str(),
                    Some(
                        "ORDERED_TAIL_SEGMENT"
                            | "ORDERED_LOCAL_PATCH"
                            | "ORDERED_SHIFT_REPAIRED"
                            | "ORDERED_REORDER_COMPLEX"
                            | "DEGRADED"
                    )
                )
            {
                return Err("invalid ordered cache processing mode".to_string());
            }
            let summary = &ordered["summary"];
            exact_keys(
                summary,
                &[
                    "row_added_count",
                    "row_deleted_count",
                    "row_modified_count",
                    "row_moved_count",
                    "position_changed_count",
                    "degraded_count",
                ],
            )?;
            for name in ["row_added_count", "row_deleted_count", "row_modified_count"] {
                if count(&summary[name])? != count(&value[name])? {
                    return Err("cache summary count mismatch".to_string());
                }
            }
            count(&summary["position_changed_count"])?;
            count(&summary["degraded_count"])?;
            let emitted = count(&value["row_added_count"])?
                .checked_sub(count(&value["suppressed_added_count"])?)
                .ok_or("cache suppressed count mismatch")?
                .checked_add(
                    count(&value["row_deleted_count"])?
                        .checked_sub(count(&value["suppressed_deleted_count"])?)
                        .ok_or("cache suppressed count mismatch")?,
                )
                .and_then(|n| n.checked_add(count(&summary["row_modified_count"]).ok()?))
                .and_then(|n| n.checked_add(count(&summary["row_moved_count"]).ok()?))
                .ok_or("cache count overflow")?;
            if emitted != counts[1] {
                return Err("ordered cache records count mismatch".to_string());
            }
            let blank = &value["blank_extension"];
            exact_keys(
                blank,
                &[
                    "contract_version",
                    "status",
                    "summary",
                    "before_occupancy_digest",
                    "current_occupancy_digest",
                    "replay_guarantee",
                    "diagnostics",
                    "records",
                ],
            )?;
            extension(
                blank,
                crate::comparison::ordered::BLANK_COMPARISON_CONTRACT_VERSION,
            )?;
            for name in ["before_occupancy_digest", "current_occupancy_digest"] {
                identity(&blank[name], true)?;
            }
            let summary = &blank["summary"];
            exact_keys(
                summary,
                &[
                    "interval_inserted_count",
                    "interval_deleted_count",
                    "blank_changed_count",
                    "degraded_count",
                ],
            )?;
            count(&summary["blank_changed_count"])?;
            count(&summary["degraded_count"])?;
            if count(&summary["interval_inserted_count"])?
                .checked_add(count(&summary["interval_deleted_count"])?)
                != Some(counts[2])
            {
                return Err("blank cache records count mismatch".to_string());
            }
        }
        _ => return Err("invalid native cache kind".to_string()),
    }
    for name in [
        "row_added_count",
        "row_deleted_count",
        "row_modified_count",
        "suppressed_added_count",
        "suppressed_deleted_count",
    ] {
        count(&value[name])?;
    }
    if count(&value["suppressed_added_count"])? > count(&value["row_added_count"])?
        || count(&value["suppressed_deleted_count"])? > count(&value["row_deleted_count"])?
    {
        return Err("cache suppressed count mismatch".to_string());
    }
    Ok(())
}

fn count(value: &Value) -> Result<usize, String> {
    usize::try_from(
        value
            .as_u64()
            .ok_or("cache count must be unsigned integer")?,
    )
    .map_err(|error| error.to_string())
}

fn empty_records(value: &Value) -> Result<(), String> {
    if value.as_array().is_none_or(|values| !values.is_empty()) {
        return Err("neutral metadata records must be empty".to_string());
    }
    Ok(())
}

fn extension(value: &Value, contract: &str) -> Result<(), String> {
    if text(&value["contract_version"])? != contract
        || !matches!(
            text(&value["status"])?,
            "ORDERED_UNCHANGED"
                | "ORDERED_CHANGED"
                | "ORDERED_BUSINESS_EQUIVALENT"
                | "ORDERED_DEGRADED"
        )
        || !matches!(
            text(&value["replay_guarantee"])?,
            "EXACT" | "PARTIAL" | "UNSUPPORTED"
        )
    {
        return Err("invalid cache extension metadata".to_string());
    }
    strings(&value["diagnostics"])?;
    empty_records(&value["records"])
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{TableFactsInput, digest_table_fact_json};
    use std::sync::atomic::AtomicBool;

    const STANDARD: &[u8] = br#"{"before_values":[["id","10080000000000000001"]],"changed_columns":[],"current_values":[],"field_changes":[],"kind":"ROW_DELETED","row_identity":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}"#;
    const ORDERED: &[u8] = br#"{"before_position":1,"before_values":[],"changed_columns":[],"current_position":2,"current_values":[],"entity_key_kind":"REAL_STABLE","record_kind":"ORDERED_ROW_MOVED","row_identity":"sha256:0000000000000000000000000000000000000000000000000000000000000000","semantic_kind":"MOVE"}"#;
    const BLANK: &[u8] = br#"{"before_occupancy":1,"current_occupancy":0,"entity_key_kind":"PSEUDO_BLANK","interval":{"before_end":1,"before_start":1,"current_end":null,"current_start":null,"interval_digest":null,"row_count":1},"record_kind":"BLANK_DELETE_INTERVAL","semantic_kind":"BLANK_DELETE_INTERVAL"}"#;

    #[test]
    fn scalar_and_set_sequence_frames_keep_their_distinct_frozen_grammar() -> Result<(), String> {
        for encoded in ["0000", "00", "020320016103200162"] {
            frame(&Value::String(encoded.to_string()))?;
        }
        for encoded in ["0001", "0203200161", "01032001ff", "020320016103200161"] {
            assert!(frame(&Value::String(encoded.to_string())).is_err());
        }
        Ok(())
    }

    #[test]
    fn independent_facts_rows_validate_all_three_families() -> Result<(), String> {
        for (family, raw) in [
            ("STANDARD", STANDARD),
            ("ORDERED", ORDERED),
            ("BLANK", BLANK),
        ] {
            validate_facts_row(family, raw)?;
        }
        Ok(())
    }

    #[test]
    fn facts_validator_rejects_missing_blank_information_and_bad_frames() {
        for (family, raw) in [
            (
                "BLANK",
                String::from_utf8_lossy(BLANK).replace("\"entity_key_kind\":\"PSEUDO_BLANK\",", ""),
            ),
            (
                "STANDARD",
                String::from_utf8_lossy(STANDARD).replace("10080000000000000001", "1007"),
            ),
            (
                "STANDARD",
                String::from_utf8_lossy(STANDARD)
                    .replace("\"kind\":\"ROW_DELETED\"", "\"kind\":\"ROGUE\""),
            ),
        ] {
            assert!(validate_facts_row(family, raw.as_bytes()).is_err());
        }
    }

    #[test]
    fn neutral_facts_replay_hashes_the_handwritten_complete_stream() -> Result<(), String> {
        let context = Arc::new(KernelContext::new(
            1024 * 1024,
            Arc::new(AtomicBool::new(false)),
            None,
        ));
        let batch = RecordBatch::try_new(
            facts_schema(),
            vec![
                Arc::new(UInt32Array::from(vec![0])),
                Arc::new(LargeBinaryArray::from_vec(vec![STANDARD])),
            ],
        )
        .map_err(|error| error.to_string())?;
        let facts = NeutralFacts {
            standard: vec![batch],
            ordered: vec![],
            blank: vec![],
        };
        facts.validate(2, 65536, &context)?;
        let digest = digest_table_fact_json(
            TableFactsInput {
                metadata_json: r#"{"records":[],"table_name":"t"}"#,
                standard: None,
                ordered: None,
                neutral: Some(&facts),
            },
            65536,
            &context,
        )?;
        let expected = [
            b"{\"records\":[".as_slice(),
            STANDARD,
            b"],\"table_name\":\"t\"}".as_slice(),
        ]
        .concat();
        let expected = gateway_shared_kernel::DigestRef::from_raw_digest(&Sha256::digest(expected))
            .map_err(|error| error.to_string())?;
        assert_eq!(digest, expected);
        Ok(())
    }
}
