//! Neutral facts views. No I/O or artifact locators enter the core.

use std::sync::Arc;

use arrow_array::builder::{LargeBinaryBuilder, UInt32Builder};
use arrow_array::{Array, LargeBinaryArray, RecordBatch, UInt32Array};
use arrow_schema::{DataType, Field, Schema, SchemaRef};
use gateway_shared_kernel::canonicalize_jcs;
use serde_json::Value;
use sha2::{Digest, Sha256};

use super::builders::charge_arrow_batches;
use super::facts::{Part, TableFactsSource, fact_row_upper, fact_row_value, facts_count};
use crate::comparison::KernelContext;

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

    pub fn validate(&self, max_records: usize, max_row_bytes: usize,
                    context: &Arc<KernelContext>) -> Result<(), String> {
        for family in ["STANDARD", "ORDERED", "BLANK"] {
            let mut ordinal = 0usize;
            for batch in self.family(family)? {
                context.check().map_err(|error| error.to_string())?;
                if batch.schema().as_ref() != facts_schema().as_ref() || batch.num_rows() > 1024 {
                    return Err("invalid neutral facts Arrow schema/batch".to_string());
                }
                let ordinals = batch.column(0).as_any().downcast_ref::<UInt32Array>()
                    .ok_or("invalid facts ordinal type")?;
                let rows = batch.column(1).as_any().downcast_ref::<LargeBinaryArray>()
                    .ok_or("invalid facts row type")?;
                for row in 0..batch.num_rows() {
                    if row % 256 == 0 { context.check().map_err(|error| error.to_string())?; }
                    if ordinal >= max_records || ordinals.is_null(row) || rows.is_null(row)
                        || usize::try_from(ordinals.value(row)).map_err(|error| error.to_string())? != ordinal {
                        return Err("invalid facts count/ordinal/null".to_string());
                    }
                    let raw = rows.value(row);
                    if raw.len() > max_row_bytes { return Err("facts JCS row budget exceeded".to_string()); }
                    let _scratch = context.reserve(super::json_metadata_upper(
                        std::str::from_utf8(raw).map_err(|error| error.to_string())?)?)
                        .map_err(|error| error.to_string())?;
                    validate_facts_row(family, raw)?;
                    ordinal += 1;
                }
            }
        }
        Ok(())
    }

    pub(super) fn write_family(&self, sink: &mut Sha256, part: Part,
                              context: &KernelContext) -> Result<(), String> {
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
            let rows = batch.column(1).as_any().downcast_ref::<LargeBinaryArray>()
                .ok_or("invalid facts row type")?;
            for row in 0..rows.len() {
                if row % 256 == 0 { context.check().map_err(|error| error.to_string())?; }
                if !first { sink.update(b","); }
                first = false;
                sink.update(rows.value(row));
            }
        }
        sink.update(b"]");
        Ok(())
    }
}

pub fn export_facts_family(source: &TableFactsSource<'_>, family: &str,
    max_row_bytes: usize, context: &Arc<KernelContext>,
    owner: Arc<dyn std::any::Any + Send + Sync>,
) -> Result<Vec<RecordBatch>, String> {
    if let Some(neutral) = source.neutral {
        return Ok(neutral.family(family)?.to_vec());
    }
    let part = part(family)?;
    let count = facts_count(source, part)?;
    let table = source.metadata.get("table_name").and_then(Value::as_str)
        .ok_or("facts table_name missing")?;
    let mut lease = context.reserve(512 * 1024).map_err(|error| error.to_string())?;
    let mut batches = Vec::new();
    for start in (0..count).step_by(1024) {
        context.check().map_err(|error| error.to_string())?;
        lease.grow(32 * 1024).map_err(|error| error.to_string())?;
        let mut ordinals = UInt32Builder::with_capacity(1024);
        let mut rows = LargeBinaryBuilder::new();
        for position in start..count.min(start + 1024) {
            let upper = fact_row_upper(source, part, position, table)?
                .checked_mul(8).and_then(|size| size.checked_add(4096))
                .ok_or("facts export size overflow")?;
            if upper / 2 > max_row_bytes { return Err("facts JCS row budget exceeded".to_string()); }
            lease.grow(upper).map_err(|error| error.to_string())?;
            let value = fact_row_value(source, part, position)?;
            let raw = canonicalize_jcs(&serde_json::to_vec(&value).map_err(|error| error.to_string())?)
                .map_err(|error| error.to_string())?;
            if raw.len() > max_row_bytes { return Err("facts JCS row budget exceeded".to_string()); }
            ordinals.append_value(u32::try_from(position).map_err(|error| error.to_string())?);
            rows.append_value(raw);
        }
        batches.push(RecordBatch::try_new(facts_schema(), vec![Arc::new(ordinals.finish()), Arc::new(rows.finish())])
            .map_err(|error| error.to_string())?);
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
    value.as_str().ok_or("facts string field has wrong type".to_string())
}

fn strings(value: &Value) -> Result<(), String> {
    for item in value.as_array().ok_or("facts list field has wrong type")? { text(item)?; }
    Ok(())
}

fn identity(value: &Value, nullable: bool) -> Result<(), String> {
    if nullable && value.is_null() { return Ok(()); }
    let digest = text(value)?.strip_prefix("sha256:").ok_or("facts digest missing prefix")?;
    if digest.len() != 64 || !digest.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) {
        return Err("invalid facts digest".to_string());
    }
    Ok(())
}

fn position(value: &Value, nullable: bool) -> Result<(), String> {
    if nullable && value.is_null() { return Ok(()); }
    if value.as_u64().is_none_or(|value| value == 0) { return Err("invalid facts position".to_string()); }
    Ok(())
}

fn frames(value: &Value) -> Result<(), String> {
    for entry in value.as_array().ok_or("facts values must be a list")? {
        let entry = entry.as_array().ok_or("facts value must be a name/frame pair")?;
        if entry.len() != 2 { return Err("facts value pair arity".to_string()); }
        text(&entry[0])?;
        frame(&entry[1])?;
    }
    Ok(())
}

fn frame(value: &Value) -> Result<(), String> {
    let hex = text(value)?;
    if hex.len() % 2 != 0 || hex.len() < 4 || !hex.is_ascii() { return Err("invalid facts frame hex".to_string()); }
    let bytes = hex.as_bytes().chunks_exact(2).map(|chunk| {
        let raw = std::str::from_utf8(chunk).map_err(|error| error.to_string())?;
        if raw.bytes().any(|byte| byte.is_ascii_uppercase()) { return Err("noncanonical frame hex".to_string()); }
        u8::from_str_radix(raw, 16).map_err(|error| error.to_string())
    }).collect::<Result<Vec<_>, _>>()?;
    let tag = bytes[0];
    if !matches!(tag, 0x00 | 0x01 | 0x10..=0x14 | 0x20 | 0x21 | 0x30..=0x33 | 0x7f) {
        return Err("unknown facts scalar tag".to_string());
    }
    let mut length = 0usize;
    let mut offset = 1usize;
    loop {
        let byte = *bytes.get(offset).ok_or("truncated facts frame length")?;
        let shift = (offset - 1) * 7;
        if shift >= 63 { return Err("facts frame length overflow".to_string()); }
        length |= usize::from(byte & 0x7f).checked_shl(u32::try_from(shift).map_err(|error| error.to_string())?)
            .ok_or("facts frame length overflow")?;
        offset += 1;
        if byte & 0x80 == 0 {
            if offset > 2 && byte == 0 { return Err("nonminimal facts frame length".to_string()); }
            break;
        }
    }
    let payload = bytes.get(offset..).ok_or("truncated facts frame")?;
    if payload.len() != length { return Err("facts frame length mismatch".to_string()); }
    match tag {
        0x00 if length != 0 => return Err("invalid null frame".to_string()),
        0x01 if length != 1 || payload[0] > 1 => return Err("invalid boolean frame".to_string()),
        0x10 | 0x11 | 0x14 if length != 8 => return Err("invalid numeric frame width".to_string()),
        0x13 if length != 4 => return Err("invalid float frame width".to_string()),
        0x12 | 0x20 | 0x30..=0x33 | 0x7f => { std::str::from_utf8(payload).map_err(|error| error.to_string())?; },
        _ => {},
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
            exact_keys(&value, &["kind", "row_identity", "changed_columns", "before_values", "current_values", "field_changes"])?;
            let kind = text(&value["kind"])?;
            if !matches!(kind, "ROW_ADDED" | "ROW_DELETED" | "ROW_MODIFIED" | "SCHEMA_CHANGE" | "TABLE_DEGRADED") {
                return Err("unknown standard facts kind".to_string());
            }
            identity(&value["row_identity"], matches!(kind, "SCHEMA_CHANGE" | "TABLE_DEGRADED"))?;
            strings(&value["changed_columns"])?;
            frames(&value["before_values"])?;
            frames(&value["current_values"])?;
            for change in value["field_changes"].as_array().ok_or("facts field_changes must be a list")? {
                exact_keys(change, &["column", "before", "current"])?;
                text(&change["column"])?; frame(&change["before"])?; frame(&change["current"])?;
            }
        },
        "ORDERED" => {
            exact_keys(&value, &["record_kind", "semantic_kind", "entity_key_kind", "row_identity", "before_position", "current_position", "changed_columns", "before_values", "current_values"])?;
            if !matches!(text(&value["record_kind"])?, "ORDERED_ROW_ADDED" | "ORDERED_ROW_DELETED" | "ORDERED_ROW_MODIFIED" | "ORDERED_ROW_MOVED" | "ORDERED_TABLE_DEGRADED")
                || !matches!(text(&value["semantic_kind"])?, "DATA_INSERT" | "DATA_DELETE" | "MOVE" | "CONTENT_UPDATE")
                || text(&value["entity_key_kind"])? != "REAL_STABLE" { return Err("invalid ordered facts kind".to_string()); }
            identity(&value["row_identity"], false)?;
            position(&value["before_position"], true)?; position(&value["current_position"], true)?;
            strings(&value["changed_columns"])?; frames(&value["before_values"])?; frames(&value["current_values"])?;
        },
        "BLANK" => {
            exact_keys(&value, &["record_kind", "semantic_kind", "entity_key_kind", "interval", "before_occupancy", "current_occupancy"])?;
            if !matches!(text(&value["record_kind"])?, "BLANK_DELETE_INTERVAL" | "BLANK_INSERT_INTERVAL")
                || value["record_kind"] != value["semantic_kind"]
                || text(&value["entity_key_kind"])? != "PSEUDO_BLANK" { return Err("invalid blank facts kind".to_string()); }
            let interval = &value["interval"];
            exact_keys(interval, &["before_start", "before_end", "current_start", "current_end", "row_count", "interval_digest"])?;
            for key in ["before_start", "before_end", "current_start", "current_end"] { position(&interval[key], true)?; }
            if interval["row_count"].as_u64().is_none() || value["before_occupancy"].as_u64().is_none()
                || value["current_occupancy"].as_u64().is_none() { return Err("invalid blank facts count".to_string()); }
            identity(&interval["interval_digest"], true)?;
        },
        _ => return Err("unknown facts family".to_string()),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicBool;
    use crate::{TableFactsInput, digest_table_fact_json};

    const STANDARD: &[u8] = br#"{"before_values":[["id","10080000000000000001"]],"changed_columns":[],"current_values":[],"field_changes":[],"kind":"ROW_DELETED","row_identity":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}"#;
    const ORDERED: &[u8] = br#"{"before_position":1,"before_values":[],"changed_columns":[],"current_position":2,"current_values":[],"entity_key_kind":"REAL_STABLE","record_kind":"ORDERED_ROW_MOVED","row_identity":"sha256:0000000000000000000000000000000000000000000000000000000000000000","semantic_kind":"MOVE"}"#;
    const BLANK: &[u8] = br#"{"before_occupancy":1,"current_occupancy":0,"entity_key_kind":"PSEUDO_BLANK","interval":{"before_end":1,"before_start":1,"current_end":null,"current_start":null,"interval_digest":null,"row_count":1},"record_kind":"BLANK_DELETE_INTERVAL","semantic_kind":"BLANK_DELETE_INTERVAL"}"#;

    #[test]
    fn independent_facts_rows_validate_all_three_families() {
        for (family, raw) in [("STANDARD", STANDARD), ("ORDERED", ORDERED), ("BLANK", BLANK)] {
            validate_facts_row(family, raw).expect("handwritten contract row");
        }
    }

    #[test]
    fn facts_validator_rejects_missing_blank_information_and_bad_frames() {
        for (family, raw) in [
            ("BLANK", String::from_utf8_lossy(BLANK).replace("\"entity_key_kind\":\"PSEUDO_BLANK\",", "")),
            ("STANDARD", String::from_utf8_lossy(STANDARD).replace("10080000000000000001", "1007")),
            ("STANDARD", String::from_utf8_lossy(STANDARD).replace("\"kind\":\"ROW_DELETED\"", "\"kind\":\"ROGUE\"")),
        ] {
            assert!(validate_facts_row(family, raw.as_bytes()).is_err());
        }
    }

    #[test]
    fn neutral_facts_replay_hashes_the_handwritten_complete_stream() {
        let context = Arc::new(KernelContext::new(1024 * 1024, Arc::new(AtomicBool::new(false)), None));
        let batch = RecordBatch::try_new(facts_schema(), vec![
            Arc::new(UInt32Array::from(vec![0])),
            Arc::new(LargeBinaryArray::from_vec(vec![STANDARD])),
        ]).expect("fixed facts batch");
        let facts = NeutralFacts { standard: vec![batch], ordered: vec![], blank: vec![] };
        facts.validate(2, 65536, &context).expect("valid fixed facts");
        let digest = digest_table_fact_json(TableFactsInput {
            metadata_json: r#"{"records":[],"table_name":"t"}"#,
            standard: None, ordered: None, neutral: Some(&facts),
        }, 65536, &context).expect("neutral replay");
        let expected = [b"{\"records\":[".as_slice(), STANDARD, b"],\"table_name\":\"t\"}".as_slice()].concat();
        let expected = gateway_shared_kernel::DigestRef::from_raw_digest(&Sha256::digest(expected)).expect("digest");
        assert_eq!(digest, expected);
    }
}
