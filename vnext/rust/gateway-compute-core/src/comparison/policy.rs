//! Small, versioned policy metadata for the production Arrow comparison entry.

use serde_json::Value;
use std::sync::Arc;

use super::{BlankProvenance, KernelContext, OrderedCompareOptions, StandardMode, StandardOptions};
use crate::records::json_metadata_upper;

pub enum ParsedComparisonPolicy {
    Standard(StandardOptions),
    Ordered(OrderedCompareOptions),
}

pub fn parse_comparison_policy(
    kind: &str,
    raw: &str,
    context: &Arc<KernelContext>,
) -> Result<ParsedComparisonPolicy, String> {
    let _metadata_charge = context
        .reserve(json_metadata_upper(raw)?)
        .map_err(|error| error.to_string())?;
    let value: Value = serde_json::from_str(raw).map_err(|error| error.to_string())?;
    match kind {
        "standard" => {
            let mode = match required_string(&value, "mode")? {
                "keyed" => StandardMode::Keyed,
                "keyless" => StandardMode::Keyless,
                _ => return Err("comparison mode is invalid".to_string()),
            };
            Ok(ParsedComparisonPolicy::Standard(StandardOptions {
                selected_columns: strings(&value, "selected_columns")?,
                effective_key_before: optional_strings(&value, "effective_key_before")?,
                effective_key_current: optional_strings(&value, "effective_key_current")?,
                compare_excluded_columns: optional_strings(&value, "compare_excluded_columns")?,
                incompatible_columns: optional_strings(&value, "incompatible_columns")?,
                mode,
                emit_add_delete: flag(&value, "emit_add_delete", true)?,
                columns_added: flag(&value, "columns_added", false)?,
            }))
        }
        "ordered" => {
            let mut options = OrderedCompareOptions::new(required_string(&value, "table_name")?);
            options.policy_version = required_string(&value, "policy_version")?.to_string();
            options.policy_digest = value
                .get("policy_digest")
                .and_then(Value::as_str)
                .map(str::to_string);
            options.value_columns = optional_strings(&value, "value_columns")?;
            options.digest_value_columns = optional_strings(&value, "digest_value_columns")?;
            options.compare_excluded_columns =
                optional_strings(&value, "compare_excluded_columns")?;
            options.include_add_delete_records = flag(&value, "emit_add_delete", true)?;
            options.schema_changed = flag(&value, "schema_changed", false)?;
            options.raw_content_changed = flag(&value, "raw_content_changed", false)?;
            options.columns_added = flag(&value, "columns_added", false)?;
            if let Some(changes) = value.get("schema_changes") {
                options.schema_changes =
                    serde_json::from_value(changes.clone()).map_err(|error| error.to_string())?;
            }
            options.before_blank_provenance = provenance(&value, "before_blank_provenance")?;
            options.current_blank_provenance = provenance(&value, "current_blank_provenance")?;
            if let Some(max_rows) = value.get("max_rows") {
                options.max_rows = max_rows
                    .as_u64()
                    .and_then(|number| usize::try_from(number).ok())
                    .ok_or_else(|| "ordered max_rows is invalid".to_string())?;
            }
            Ok(ParsedComparisonPolicy::Ordered(options))
        }
        _ => Err("comparison kind is invalid".to_string()),
    }
}

fn required_string<'a>(value: &'a Value, name: &str) -> Result<&'a str, String> {
    value
        .get(name)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("comparison policy {name} is missing"))
}

fn strings(value: &Value, name: &str) -> Result<Vec<String>, String> {
    value
        .get(name)
        .and_then(Value::as_array)
        .ok_or_else(|| format!("comparison policy {name} is missing"))?
        .iter()
        .map(|item| {
            item.as_str()
                .map(str::to_string)
                .ok_or_else(|| format!("comparison policy {name} is invalid"))
        })
        .collect()
}

fn optional_strings(value: &Value, name: &str) -> Result<Vec<String>, String> {
    if value.get(name).is_none() {
        Ok(Vec::new())
    } else {
        strings(value, name)
    }
}

fn flag(value: &Value, name: &str, default: bool) -> Result<bool, String> {
    match value.get(name) {
        None => Ok(default),
        Some(item) => item
            .as_bool()
            .ok_or_else(|| format!("comparison policy {name} is invalid")),
    }
}

fn provenance(value: &Value, name: &str) -> Result<BlankProvenance, String> {
    match value.get(name).and_then(Value::as_str).unwrap_or("source") {
        "source" => Ok(BlankProvenance::SourceMissingStableKey),
        "canonical" => Ok(BlankProvenance::CanonicalPseudoGid),
        _ => Err(format!("comparison policy {name} is invalid")),
    }
}
