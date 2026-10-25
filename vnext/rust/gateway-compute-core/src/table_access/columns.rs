//! Column builders for parsed values and their Arrow conversion.
//!
//! Prototype Arrow mapping (not the final DC46 item 6 mapping): signed and
//! unsigned integers as Int64 / UInt64, BOOLEAN as Boolean, FLOAT / DOUBLE as
//! Float32 / Float64 (negative zero already normalized), BINARY and BIT as
//! Binary, and every other type as Utf8 holding the canonical scalar text
//! (DECIMAL, temporal types, ENUM, JSON, and SET members joined with `,`).

use std::sync::Arc;

use arrow_array::{
    ArrayRef, BinaryArray, BooleanArray, Float32Array, Float64Array, Int64Array, StringArray,
    UInt64Array,
};
use arrow_buffer::{BooleanBuffer, Buffer, NullBuffer, OffsetBuffer, ScalarBuffer};

use super::errors::{Fault, ParserDiagnosticCode as Code};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Layout {
    I64,
    U64,
    Bool,
    F32,
    F64,
    Utf8,
    Binary,
}

#[derive(Debug)]
enum Values {
    I64(Vec<i64>),
    U64(Vec<u64>),
    Bool(Vec<bool>),
    F32(Vec<f32>),
    F64(Vec<f64>),
    Bytes { ends: Vec<usize>, data: Vec<u8> },
}

#[derive(Debug)]
pub(crate) struct ColumnBuilder {
    layout: Layout,
    values: Values,
    /// `None` until the first null; then one flag per row (`true` = valid).
    validity: Option<Vec<bool>>,
    len: usize,
}

impl ColumnBuilder {
    pub fn new(layout: Layout) -> Self {
        let values = match layout {
            Layout::I64 => Values::I64(Vec::new()),
            Layout::U64 => Values::U64(Vec::new()),
            Layout::Bool => Values::Bool(Vec::new()),
            Layout::F32 => Values::F32(Vec::new()),
            Layout::F64 => Values::F64(Vec::new()),
            Layout::Utf8 | Layout::Binary => Values::Bytes {
                ends: Vec::new(),
                data: Vec::new(),
            },
        };
        Self {
            layout,
            values,
            validity: None,
            len: 0,
        }
    }

    pub fn len(&self) -> usize {
        self.len
    }

    fn valid(&mut self) {
        if let Some(validity) = self.validity.as_mut() {
            validity.push(true);
        }
        self.len += 1;
    }

    pub fn push_null(&mut self) {
        match &mut self.values {
            Values::I64(v) => v.push(0),
            Values::U64(v) => v.push(0),
            Values::Bool(v) => v.push(false),
            Values::F32(v) => v.push(0.0),
            Values::F64(v) => v.push(0.0),
            Values::Bytes { ends, data } => ends.push(data.len()),
        }
        let len = self.len;
        self.validity
            .get_or_insert_with(|| vec![true; len])
            .push(false);
        self.len += 1;
    }

    pub fn push_i64(&mut self, value: i64) -> Result<(), Fault> {
        match &mut self.values {
            Values::I64(v) => v.push(value),
            _ => return Err(layout_mismatch()),
        }
        self.valid();
        Ok(())
    }

    pub fn push_u64(&mut self, value: u64) -> Result<(), Fault> {
        match &mut self.values {
            Values::U64(v) => v.push(value),
            _ => return Err(layout_mismatch()),
        }
        self.valid();
        Ok(())
    }

    pub fn push_bool(&mut self, value: bool) -> Result<(), Fault> {
        match &mut self.values {
            Values::Bool(v) => v.push(value),
            _ => return Err(layout_mismatch()),
        }
        self.valid();
        Ok(())
    }

    pub fn push_f32(&mut self, value: f32) -> Result<(), Fault> {
        match &mut self.values {
            Values::F32(v) => v.push(value),
            _ => return Err(layout_mismatch()),
        }
        self.valid();
        Ok(())
    }

    pub fn push_f64(&mut self, value: f64) -> Result<(), Fault> {
        match &mut self.values {
            Values::F64(v) => v.push(value),
            _ => return Err(layout_mismatch()),
        }
        self.valid();
        Ok(())
    }

    pub fn push_bytes(&mut self, value: &[u8]) -> Result<(), Fault> {
        match &mut self.values {
            Values::Bytes { ends, data } => {
                data.extend_from_slice(value);
                ends.push(data.len());
            }
            _ => return Err(layout_mismatch()),
        }
        self.valid();
        Ok(())
    }

    /// Appends `other` (same layout) after the rows already present.
    pub fn append(&mut self, other: ColumnBuilder) -> Result<(), Fault> {
        if self.layout != other.layout {
            return Err(layout_mismatch());
        }
        match (&mut self.validity, other.validity) {
            (None, None) => {}
            (Some(mine), None) => mine.resize(mine.len() + other.len, true),
            (mine @ None, Some(theirs)) => {
                let mut combined = vec![true; self.len];
                combined.extend(theirs);
                *mine = Some(combined);
            }
            (Some(mine), Some(theirs)) => mine.extend(theirs),
        }
        match (&mut self.values, other.values) {
            (Values::I64(a), Values::I64(b)) => a.extend(b),
            (Values::U64(a), Values::U64(b)) => a.extend(b),
            (Values::Bool(a), Values::Bool(b)) => a.extend(b),
            (Values::F32(a), Values::F32(b)) => a.extend(b),
            (Values::F64(a), Values::F64(b)) => a.extend(b),
            (
                Values::Bytes { ends, data },
                Values::Bytes {
                    ends: other_ends,
                    data: other_data,
                },
            ) => {
                let base = data.len();
                ends.extend(other_ends.into_iter().map(|end| end + base));
                data.extend(other_data);
            }
            _ => return Err(layout_mismatch()),
        }
        self.len += other.len;
        Ok(())
    }

    pub fn finish(self) -> Result<ArrayRef, Fault> {
        let nulls = self
            .validity
            .map(|flags| NullBuffer::new(BooleanBuffer::from_iter(flags)));
        let array: ArrayRef = match self.values {
            Values::I64(v) => {
                Arc::new(Int64Array::try_new(ScalarBuffer::from(v), nulls).map_err(arrow_error)?)
            }
            Values::U64(v) => {
                Arc::new(UInt64Array::try_new(ScalarBuffer::from(v), nulls).map_err(arrow_error)?)
            }
            Values::Bool(v) => {
                let values = BooleanBuffer::from_iter(v);
                if nulls.as_ref().is_some_and(|n| n.len() != values.len()) {
                    return Err(layout_mismatch());
                }
                Arc::new(BooleanArray::new(values, nulls))
            }
            Values::F32(v) => {
                Arc::new(Float32Array::try_new(ScalarBuffer::from(v), nulls).map_err(arrow_error)?)
            }
            Values::F64(v) => {
                Arc::new(Float64Array::try_new(ScalarBuffer::from(v), nulls).map_err(arrow_error)?)
            }
            Values::Bytes { ends, data } => {
                let mut offsets: Vec<i32> = Vec::with_capacity(ends.len() + 1);
                offsets.push(0);
                for end in ends {
                    offsets.push(
                        i32::try_from(end)
                            .map_err(|_| Fault::resource("arrow utf8/binary column offsets", 0))?,
                    );
                }
                let offsets = OffsetBuffer::new(ScalarBuffer::from(offsets));
                let values = Buffer::from_vec(data);
                if self.layout == Layout::Binary {
                    Arc::new(BinaryArray::try_new(offsets, values, nulls).map_err(arrow_error)?)
                } else {
                    Arc::new(StringArray::try_new(offsets, values, nulls).map_err(arrow_error)?)
                }
            }
        };
        Ok(array)
    }
}

fn layout_mismatch() -> Fault {
    Fault::new(Code::ParserInternalError, 0, "column layout mismatch")
}

fn arrow_error(error: arrow_schema::ArrowError) -> Fault {
    Fault::new(
        Code::ParserInternalError,
        0,
        format!("arrow array construction failed: {error}"),
    )
}
