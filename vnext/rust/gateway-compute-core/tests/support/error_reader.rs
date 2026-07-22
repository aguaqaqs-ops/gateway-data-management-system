use std::sync::Arc;

use arrow_array::RecordBatch;
use arrow_array::RecordBatchReader;
use arrow_schema::{ArrowError, Schema};

pub struct ErrorBatchReader {
    schema: Arc<Schema>,
}

impl ErrorBatchReader {
    pub fn new(schema: Arc<Schema>) -> Self {
        Self { schema }
    }

    pub fn into_boxed(self) -> Box<dyn RecordBatchReader + Send> {
        Box::new(self)
    }
}

impl RecordBatchReader for ErrorBatchReader {
    fn schema(&self) -> Arc<Schema> {
        self.schema.clone()
    }
}

impl Iterator for ErrorBatchReader {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        Some(Err(ArrowError::ComputeError(
            "simulated stream import failure".to_string(),
        )))
    }
}
