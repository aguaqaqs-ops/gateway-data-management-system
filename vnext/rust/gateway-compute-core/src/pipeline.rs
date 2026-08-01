use std::sync::Arc;

use arrow_array::{
    Array, FixedSizeBinaryArray, RecordBatch, RecordBatchReader, builder::FixedSizeBinaryBuilder,
};
use arrow_schema::{DataType, Field, Schema};
use gateway_shared_kernel::unordered_row_hashes_content_digest;

use crate::arrow_extract::{build_column_bindings, encode_row_at};
use crate::arrow_mapping::{cross_check_stream_schema, schemas_equal};
use crate::errors::{ComputeFailure, ComputeFailureCode};
use crate::request::ParsedRequest;
use crate::result::{CanonicalRowHashOutput, serialize_success_result};

pub fn canonical_row_hashes_v2(
    request: &ParsedRequest,
    mut input: Box<dyn RecordBatchReader + Send>,
) -> Result<CanonicalRowHashOutput, ComputeFailure> {
    request.validate_digest_binding()?;

    let reader_schema = input.schema();
    cross_check_stream_schema(request.fields(), reader_schema.as_ref())?;

    let mut row_hashes: Vec<[u8; 32]> = Vec::new();
    let mut bindings: Option<Vec<crate::arrow_extract::ColumnBinding>> = None;

    loop {
        let batch = match input.next() {
            Some(Ok(batch)) => batch,
            Some(Err(error)) => return Err(ComputeFailure::from(error)),
            None => break,
        };

        if !schemas_equal(reader_schema.as_ref(), batch.schema().as_ref()) {
            return Err(ComputeFailure::new(ComputeFailureCode::ArrowSchemaMismatch));
        }

        if bindings.is_none() {
            bindings = Some(build_column_bindings(&batch, request.fields())?);
        }

        let bindings = bindings
            .as_ref()
            .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
        for row_index in 0..batch.num_rows() {
            let encoded = encode_row_at(&batch, bindings, row_index)?;
            row_hashes.push(*encoded.raw_hash());
        }
    }

    row_hashes.sort();
    let raw_content_digest = unordered_row_hashes_content_digest(&row_hashes)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;

    let row_count = u64::try_from(row_hashes.len())
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
    let output_batches = vec![build_output_batch(&row_hashes)?];
    let result_jcs = serialize_success_result(
        request.table_schema_digest(),
        row_count,
        &raw_content_digest,
    )?;

    Ok(CanonicalRowHashOutput {
        output_batches,
        result_jcs,
    })
}

fn build_output_batch(row_hashes: &[[u8; 32]]) -> Result<RecordBatch, ComputeFailure> {
    let mut builder = FixedSizeBinaryBuilder::with_capacity(row_hashes.len(), 32);
    for hash in row_hashes {
        builder
            .append_value(hash)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
    }
    let array = builder.finish();
    let schema = Arc::new(Schema::new(vec![Field::new(
        "row_hash",
        DataType::FixedSizeBinary(32),
        false,
    )]));
    RecordBatch::try_new(schema, vec![Arc::new(array)])
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
}

#[allow(dead_code)]
pub fn output_row_hash_bytes(batch: &RecordBatch) -> Result<Vec<[u8; 32]>, ComputeFailure> {
    let array = batch
        .column(0)
        .as_any()
        .downcast_ref::<FixedSizeBinaryArray>()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
    let mut out = Vec::with_capacity(array.len());
    for row in 0..array.len() {
        let value = array.value(row);
        let mut hash = [0u8; 32];
        if value.len() == 32 {
            hash.copy_from_slice(value);
            out.push(hash);
        } else {
            return Err(ComputeFailure::new(
                ComputeFailureCode::RowHashComputeFailed,
            ));
        }
    }
    Ok(out)
}
