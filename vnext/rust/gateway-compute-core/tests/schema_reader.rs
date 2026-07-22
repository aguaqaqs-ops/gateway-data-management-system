#![forbid(unsafe_code)]

mod support;

use std::sync::Arc;

use arrow_schema::{DataType, Field, Schema};
use gateway_compute_core::ComputeFailureCode;

use support::batch_reader::SchemaOnlyReader;
use support::builders::{boolean_batch, empty_schema_batch, int32_batch};
use support::runner::{run_err_reader, run_ok_reader};

#[test]
fn zero_batch_reader_with_schema_succeeds() -> Result<(), String> {
    let schema = Arc::new(Schema::new(vec![Field::new("v", DataType::Boolean, false)]));
    let output = run_ok_reader(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]"#,
        SchemaOnlyReader::new(schema).into_boxed(),
    )?;
    assert_eq!(output.output_batches[0].num_rows(), 0);
    assert!(String::from_utf8_lossy(&output.result_jcs).contains("\"row_count\":\"0\""));
    Ok(())
}

#[test]
fn zero_batch_reader_empty_table_schema() -> Result<(), String> {
    let output = run_ok_reader(
        "[]",
        SchemaOnlyReader::new(Arc::new(Schema::empty())).into_boxed(),
    )?;
    assert_eq!(output.output_batches[0].num_rows(), 0);
    Ok(())
}

#[test]
fn batch_schema_mismatch_with_reader_schema() -> Result<(), String> {
    let reader_schema = Arc::new(Schema::new(vec![Field::new("v", DataType::Boolean, false)]));
    let batch = int32_batch("v", false, vec![Some(1)]).map_err(|e| e.to_string())?;
    let reader =
        support::batch_reader::VecBatchReader::with_schema(reader_schema, vec![batch]).into_boxed();
    let failure = run_err_reader(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]"#,
        reader,
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::ArrowSchemaMismatch,
    );
    Ok(())
}

#[test]
fn multi_batch_requires_consistent_schema() -> Result<(), String> {
    let batch_a = boolean_batch("v", false, vec![Some(true)]).map_err(|e| e.to_string())?;
    let batch_b = int32_batch("v", false, vec![Some(1)]).map_err(|e| e.to_string())?;
    let reader = support::batch_reader::VecBatchReader::new(vec![batch_a, batch_b]).into_boxed();
    let failure = run_err_reader(
        r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]"#,
        reader,
    )?;
    support::assert_envelope::assert_failure_code(
        &failure,
        ComputeFailureCode::ArrowSchemaMismatch,
    );
    Ok(())
}

#[test]
fn multi_batch_partition_preserves_digest() -> Result<(), String> {
    let fields = r#"[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]"#;
    let single = support::runner::run_ok(
        fields,
        vec![boolean_batch("v", false, vec![Some(true), Some(false)]).map_err(|e| e.to_string())?],
    )?;
    let split = support::runner::run_ok(
        fields,
        vec![
            boolean_batch("v", false, vec![Some(true)]).map_err(|e| e.to_string())?,
            boolean_batch("v", false, vec![Some(false)]).map_err(|e| e.to_string())?,
        ],
    )?;
    if single.result_jcs != split.result_jcs {
        return Err("multi-batch partition changed digest".to_string());
    }
    Ok(())
}

#[test]
fn empty_schema_batch_matches_zero_batch_reader() -> Result<(), String> {
    let from_batch = support::runner::run_ok(
        "[]",
        vec![empty_schema_batch(&[]).map_err(|e| e.to_string())?],
    )?;
    let from_reader = run_ok_reader(
        "[]",
        SchemaOnlyReader::new(Arc::new(Schema::empty())).into_boxed(),
    )?;
    if from_batch.result_jcs != from_reader.result_jcs {
        return Err("empty batch vs zero-batch reader digest mismatch".to_string());
    }
    Ok(())
}
