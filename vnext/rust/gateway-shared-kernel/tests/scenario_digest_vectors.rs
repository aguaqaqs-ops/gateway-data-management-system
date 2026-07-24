#![forbid(unsafe_code)]

//! Independent oracle: scenario-digest collection frames from normative vectors.

use gateway_shared_kernel::{DigestKind, semantic_digest};
use serde::Deserialize;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Deserialize)]
struct DigestRow {
    #[allow(dead_code)]
    case_id: String,
    #[serde(default)]
    input_digest: Option<String>,
    #[serde(default)]
    fixture_content_digest: Option<String>,
    collection_frame_base64url: String,
}

fn vector_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/vectors/conformance/scenario-digest/v1")
}

fn b64url_decode(value: &str) -> Result<Vec<u8>, String> {
    use base64::Engine;
    let pad = (4 - value.len() % 4) % 4;
    let padded = format!("{}{}", value, "=".repeat(pad));
    base64::engine::general_purpose::URL_SAFE
        .decode(padded)
        .map_err(|error| error.to_string())
}

fn load_jsonl(path: PathBuf) -> Result<Vec<DigestRow>, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    text.lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).map_err(|error| error.to_string()))
        .collect()
}

#[test]
fn scenario_digest_preimage_vectors_match_rust_oracle() -> Result<(), String> {
    let root = vector_root();
    let input_rows = load_jsonl(root.join("input-digest.jsonl"))?;
    let fixture_rows = load_jsonl(root.join("fixture-digest.jsonl"))?;
    for row in input_rows {
        let frame = b64url_decode(&row.collection_frame_base64url)?;
        let digest = semantic_digest(DigestKind::ScenarioInput, &frame)
            .map_err(|error| error.to_string())?;
        let expected = row
            .input_digest
            .ok_or_else(|| "missing input_digest".to_string())?;
        if digest.digest_ref().as_str() != expected {
            return Err(format!(
                "input digest mismatch: {} != {}",
                digest.digest_ref().as_str(),
                expected
            ));
        }
    }
    for row in fixture_rows {
        let frame = b64url_decode(&row.collection_frame_base64url)?;
        let digest = semantic_digest(DigestKind::ScenarioFixture, &frame)
            .map_err(|error| error.to_string())?;
        let expected = row
            .fixture_content_digest
            .ok_or_else(|| "missing fixture_content_digest".to_string())?;
        if digest.digest_ref().as_str() != expected {
            return Err(format!(
                "fixture digest mismatch: {} != {}",
                digest.digest_ref().as_str(),
                expected
            ));
        }
    }
    Ok(())
}
