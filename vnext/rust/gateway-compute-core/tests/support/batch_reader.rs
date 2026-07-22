use std::sync::Arc;

use arrow_array::RecordBatch;
use arrow_array::RecordBatchReader;
use arrow_schema::{ArrowError, Schema};

pub struct VecBatchReader {
    schema: Arc<Schema>,
    batches: Vec<RecordBatch>,
    index: usize,
}

impl VecBatchReader {
    pub fn new(batches: Vec<RecordBatch>) -> Self {
        let schema = batches
            .first()
            .map(|batch| batch.schema())
            .unwrap_or_else(|| Arc::new(Schema::empty()));
        Self {
            schema,
            batches,
            index: 0,
        }
    }

    pub fn with_schema(schema: Arc<Schema>, batches: Vec<RecordBatch>) -> Self {
        Self {
            schema,
            batches,
            index: 0,
        }
    }

    pub fn into_boxed(self) -> Box<dyn RecordBatchReader + Send> {
        Box::new(self)
    }
}

/// Reader that exposes `schema()` but yields zero batches.
pub struct SchemaOnlyReader {
    schema: Arc<Schema>,
}

impl SchemaOnlyReader {
    pub fn new(schema: Arc<Schema>) -> Self {
        Self { schema }
    }

    pub fn into_boxed(self) -> Box<dyn RecordBatchReader + Send> {
        Box::new(self)
    }
}

impl RecordBatchReader for VecBatchReader {
    fn schema(&self) -> Arc<Schema> {
        self.schema.clone()
    }
}

impl Iterator for VecBatchReader {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.index >= self.batches.len() {
            return None;
        }
        let batch = self.batches[self.index].clone();
        self.index += 1;
        Some(Ok(batch))
    }
}

impl RecordBatchReader for SchemaOnlyReader {
    fn schema(&self) -> Arc<Schema> {
        self.schema.clone()
    }
}

impl Iterator for SchemaOnlyReader {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        None
    }
}
