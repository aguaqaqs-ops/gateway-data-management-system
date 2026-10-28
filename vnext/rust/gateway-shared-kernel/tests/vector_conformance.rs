#![forbid(unsafe_code)]

//! Shared Kernel owner test: load the ordinary canonical corpus and dispatch all cases.

mod support;

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use support::dispatch::dispatch_case;

const CASE_FILES: &[&str] = &["digest.jsonl", "invalid.jsonl", "jcs.jsonl", "scalar.jsonl"];
const EXPECTED_CASE_COUNT: usize = 129;

#[test]
fn rust_canonical_cases_match_shared_kernel() -> Result<(), String> {
    let root = corpus_root();
    let mut cases = Vec::new();
    for file_name in CASE_FILES {
        let path = root.join(file_name);
        let text =
            fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?;
        for (line_number, line) in text.lines().enumerate() {
            let case: serde_json::Value = serde_json::from_str(line)
                .map_err(|error| format!("{}:{}: {error}", path.display(), line_number + 1))?;
            cases.push(case);
        }
    }
    let case_ids: Vec<&str> = cases
        .iter()
        .map(|case| {
            case.get("case_id")
                .and_then(serde_json::Value::as_str)
                .ok_or_else(|| "case_id must be a string".to_string())
        })
        .collect::<Result<_, _>>()?;
    if case_ids.len() != EXPECTED_CASE_COUNT {
        return Err(format!(
            "canonical corpus contains {}, expected {EXPECTED_CASE_COUNT}",
            case_ids.len()
        ));
    }
    if case_ids.iter().collect::<BTreeSet<_>>().len() != case_ids.len() {
        return Err("duplicate case_id detected".to_string());
    }
    for case in &cases {
        dispatch_case(case).map_err(|error| format!("canonical case failed: {error}"))?;
    }
    Ok(())
}

fn corpus_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/vectors/shared-kernel/canonical-encoding/v1")
}
