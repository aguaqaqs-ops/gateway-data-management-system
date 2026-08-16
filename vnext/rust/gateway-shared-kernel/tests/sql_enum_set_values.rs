#![forbid(unsafe_code)]

//! Shared Kernel consumer of Repository ENUM/SET content-byte goldens.
//!
//! SQL grammar stays in Repository Service. This test only re-encodes already
//! canonical labels/members with production string/null/sequence primitives.

mod support;

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use gateway_shared_kernel::{
    CollectionSemantics, DeclaredType, NullScalar, StringScalar, TypedScalar, encode_collection,
    encode_typed_scalar,
};
use support::codec::encode_base64url;

const EXPECTED_VALUE_CASE_COUNT: usize = 9;

#[test]
fn rust_sql_enum_set_values_match_shared_kernel() -> Result<(), String> {
    let path = values_path();
    let text = fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?;
    let mut cases = Vec::new();
    for (line_number, line) in text.lines().enumerate() {
        let case: serde_json::Value = serde_json::from_str(line)
            .map_err(|error| format!("{}:{}: {error}", path.display(), line_number + 1))?;
        cases.push(case);
    }
    let case_ids: Vec<&str> = cases
        .iter()
        .map(|case| {
            case.get("case_id")
                .and_then(serde_json::Value::as_str)
                .ok_or_else(|| "case_id must be a string".to_string())
        })
        .collect::<Result<_, _>>()?;
    if case_ids.len() != EXPECTED_VALUE_CASE_COUNT {
        return Err(format!(
            "ENUM/SET values corpus contains {}, expected {EXPECTED_VALUE_CASE_COUNT}",
            case_ids.len()
        ));
    }
    if case_ids.iter().collect::<BTreeSet<_>>().len() != case_ids.len() {
        return Err("duplicate case_id detected".to_string());
    }
    for case in &cases {
        dispatch_value_case(case)
            .map_err(|error| format!("ENUM/SET value case failed: {error}"))?;
    }
    Ok(())
}

fn dispatch_value_case(case: &serde_json::Value) -> Result<(), String> {
    let case_id = case
        .get("case_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("<unknown>");
    let operation = required_str(case, "operation")?;
    let input = required_object(case, "input")?;
    let expected = required_object(case, "expected")?;
    let actual = encode_content_bytes(operation, input)?;
    for (key, expected_value) in expected {
        let actual_value = actual
            .get(key)
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| format!("case {case_id:?} missing actual field {key}"))?;
        let expected_text = expected_value
            .as_str()
            .ok_or_else(|| format!("case {case_id:?} expected.{key} must be a string"))?;
        if actual_value != expected_text {
            return Err(format!(
                "case {case_id:?} field {key} mismatch:\n  actual={actual_value}\n  expected={expected_text}"
            ));
        }
    }
    Ok(())
}

fn encode_content_bytes(
    operation: &str,
    input: &serde_json::Map<String, serde_json::Value>,
) -> Result<serde_json::Map<String, serde_json::Value>, String> {
    let value = required_object_from_map(input, "value")?;
    let kind = required_str_from_map(value, "kind")?;
    match operation {
        "encode-enum-value" => {
            let encoded = encode_scalar(kind, value)?;
            let mut actual = serde_json::Map::new();
            actual.insert(
                "payload_base64url".to_string(),
                serde_json::Value::String(encode_base64url(&encoded.payload)),
            );
            actual.insert(
                "scalar_frame_base64url".to_string(),
                serde_json::Value::String(encode_base64url(&encoded.scalar_frame)),
            );
            Ok(actual)
        }
        "encode-set-value" => match kind {
            "null" => {
                let encoded = encode_scalar(kind, value)?;
                let mut actual = serde_json::Map::new();
                actual.insert(
                    "scalar_frame_base64url".to_string(),
                    serde_json::Value::String(encode_base64url(&encoded.scalar_frame)),
                );
                Ok(actual)
            }
            "set-members" => {
                let members = value
                    .get("members")
                    .and_then(serde_json::Value::as_array)
                    .ok_or_else(|| "set-members requires members array".to_string())?;
                let mut frames = Vec::with_capacity(members.len());
                for member in members {
                    let text = member
                        .as_str()
                        .ok_or_else(|| "SET member must be a string".to_string())?;
                    let encoded = encode_typed_scalar(
                        &DeclaredType::string(),
                        &TypedScalar::String(StringScalar {
                            text: text.to_string(),
                        }),
                    )
                    .map_err(|error| error.to_string())?;
                    frames.push(encoded.scalar_frame);
                }
                let item_refs: Vec<&[u8]> = frames.iter().map(Vec::as_slice).collect();
                let encoded =
                    encode_collection(CollectionSemantics::Sequence, Some(&item_refs), None)
                        .map_err(|error| error.to_string())?;
                let mut actual = serde_json::Map::new();
                actual.insert(
                    "sequence_frame_base64url".to_string(),
                    serde_json::Value::String(encode_base64url(&encoded.collection_frame)),
                );
                Ok(actual)
            }
            other => Err(format!("unsupported SET value kind {other:?}")),
        },
        other => Err(format!("unsupported operation {other:?}")),
    }
}

fn encode_scalar(
    kind: &str,
    value: &serde_json::Map<String, serde_json::Value>,
) -> Result<gateway_shared_kernel::EncodedScalar, String> {
    match kind {
        "null" => encode_typed_scalar(&DeclaredType::null(), &TypedScalar::Null(NullScalar))
            .map_err(|error| error.to_string()),
        "string" => {
            let text = required_str_from_map(value, "text")?;
            encode_typed_scalar(
                &DeclaredType::string(),
                &TypedScalar::String(StringScalar {
                    text: text.to_string(),
                }),
            )
            .map_err(|error| error.to_string())
        }
        other => Err(format!("unsupported scalar kind {other:?}")),
    }
}

fn required_str<'a>(value: &'a serde_json::Value, key: &str) -> Result<&'a str, String> {
    value
        .get(key)
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| format!("{key} must be a string"))
}

fn required_object<'a>(
    value: &'a serde_json::Value,
    key: &str,
) -> Result<&'a serde_json::Map<String, serde_json::Value>, String> {
    value
        .get(key)
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| format!("{key} must be an object"))
}

fn required_object_from_map<'a>(
    value: &'a serde_json::Map<String, serde_json::Value>,
    key: &str,
) -> Result<&'a serde_json::Map<String, serde_json::Value>, String> {
    value
        .get(key)
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| format!("{key} must be an object"))
}

fn required_str_from_map<'a>(
    value: &'a serde_json::Map<String, serde_json::Value>,
    key: &str,
) -> Result<&'a str, String> {
    value
        .get(key)
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| format!("{key} must be a string"))
}

fn values_path() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/vectors/repository/sql-enum-set/v1/values.jsonl")
}
