//! Parse canonical form: a byte-deterministic encoding of a parse result,
//! used only by the differential and the measurements (Phase 6 V6).
//!
//! Layout (all integers big-endian):
//!
//! ```text
//! magic   b"GDMSPCF1"
//! header  u32 length + JSON {"format","status","table_count","version"}
//! per table, in source order:
//!   u32 length + JSON {"canonical_name","columns":[...],"display_name",
//!                      "primary_key","reader_ready","row_count"}
//!   when reader_ready, per column in ordinal order:
//!     b'C', u32 ordinal, then per row: u8 type mark, u32 length, payload
//! ```
//!
//! JSON objects have sorted keys and no whitespace; strings escape `"`,
//! `\`, and control characters (`\b \f \n \r \t`, otherwise `\u00xx`),
//! matching Python's `json.dumps(..., sort_keys=True, separators=(",", ":"),
//! ensure_ascii=False)`.
//!
//! Type marks: null 0x00, boolean 0x01, signed-integer 0x10,
//! unsigned-integer 0x11, decimal 0x12, float32 0x13, float64 0x14,
//! string 0x20 (also ENUM and JSON), binary 0x21, bit 0x22, date 0x30,
//! datetime 0x31, timestamp 0x32, time-duration 0x33, set 0x40.
//! Payloads are the Shared Kernel scalar payloads (integers as 8-byte
//! two's complement / unsigned, floats as IEEE bits, text as UTF-8, binary
//! raw); a SET payload is its members in declaration order joined by `,`.

use arrow_array::{
    Array, BinaryArray, BooleanArray, Float32Array, Float64Array, Int64Array, StringArray,
    UInt64Array,
};
use gateway_shared_kernel::DeclaredType;

use super::errors::{Fault, ParserDiagnosticCode as Code};
use super::model::{ColumnDescriptor, TableDescriptor, ValueKind};
use super::{ParsedTable, SqlParseOutput};

pub const PARSE_CANONICAL_FORMAT: &str = "gateway.table-access.parse-canonical";
pub const PARSE_CANONICAL_VERSION: u32 = 1;
const MAGIC: &[u8; 8] = b"GDMSPCF1";

/// Encodes `output` in the parse canonical form.
pub fn encode_parse_canonical(output: &SqlParseOutput) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    out.extend_from_slice(MAGIC);
    let header = format!(
        "{{\"format\":{},\"status\":{},\"table_count\":{},\"version\":{}}}",
        json_string(PARSE_CANONICAL_FORMAT),
        json_string(output.status.as_str()),
        output.tables.len(),
        PARSE_CANONICAL_VERSION,
    );
    put_block(&mut out, header.as_bytes())?;
    for table in &output.tables {
        put_block(&mut out, table_json(table).as_bytes())?;
        if table.descriptor.reader_ready {
            encode_columns(&mut out, table).map_err(|fault| fault.message.into_owned())?;
        }
    }
    Ok(out)
}

fn put_u32(out: &mut Vec<u8>, value: usize) -> Result<(), String> {
    let value = u32::try_from(value).map_err(|_| "canonical length exceeds u32".to_string())?;
    out.extend_from_slice(&value.to_be_bytes());
    Ok(())
}

fn put_block(out: &mut Vec<u8>, bytes: &[u8]) -> Result<(), String> {
    put_u32(out, bytes.len())?;
    out.extend_from_slice(bytes);
    Ok(())
}

fn json_string(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            c if u32::from(c) < 0x20 => out.push_str(&format!("\\u{:04x}", u32::from(c))),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn json_string_list(items: &[String]) -> String {
    let parts: Vec<String> = items.iter().map(|item| json_string(item)).collect();
    format!("[{}]", parts.join(","))
}

fn declared_json(declared: &Option<DeclaredType>) -> String {
    let Some(declared) = declared else {
        return "null".to_string();
    };
    let kind = json_string(declared.kind_str());
    match declared {
        DeclaredType::SignedInteger { bits } | DeclaredType::UnsignedInteger { bits } => {
            format!("{{\"bits\":{bits},\"kind\":{kind}}}")
        }
        DeclaredType::Decimal { precision, scale } => {
            format!("{{\"kind\":{kind},\"precision\":{precision},\"scale\":{scale}}}")
        }
        DeclaredType::Bit { bit_width } => format!("{{\"bit_width\":{bit_width},\"kind\":{kind}}}"),
        _ => format!("{{\"kind\":{kind}}}"),
    }
}

fn column_json(column: &ColumnDescriptor) -> String {
    let labels = match &column.labels {
        None => "null".to_string(),
        Some(labels) => json_string_list(labels),
    };
    format!(
        "{{\"canonical_name\":{},\"declared_type\":{},\"display_name\":{},\"labels\":{},\"logical_type\":{},\"nullable\":{},\"ordinal\":{},\"sql_type\":{}}}",
        json_string(&column.canonical_name),
        declared_json(&column.declared_type),
        json_string(&column.display_name),
        labels,
        json_string(column.logical_type.as_str()),
        column.nullable,
        column.ordinal,
        json_string(&column.sql_type),
    )
}

fn table_json(table: &ParsedTable) -> String {
    let descriptor: &TableDescriptor = &table.descriptor;
    let columns: Vec<String> = descriptor.columns.iter().map(column_json).collect();
    let row_count = if descriptor.reader_ready {
        table.row_count.to_string()
    } else {
        "null".to_string()
    };
    format!(
        "{{\"canonical_name\":{},\"columns\":[{}],\"display_name\":{},\"primary_key\":{},\"reader_ready\":{},\"row_count\":{}}}",
        json_string(&descriptor.canonical_name),
        columns.join(","),
        json_string(&descriptor.display_name),
        json_string_list(&descriptor.primary_key),
        descriptor.reader_ready,
        row_count,
    )
}

fn internal(message: &'static str) -> Fault {
    Fault::new(Code::ParserInternalError, 0, message)
}

fn put_value(out: &mut Vec<u8>, mark: u8, payload: &[u8]) -> Result<(), Fault> {
    out.push(mark);
    let length =
        u32::try_from(payload.len()).map_err(|_| internal("canonical value exceeds u32"))?;
    out.extend_from_slice(&length.to_be_bytes());
    out.extend_from_slice(payload);
    Ok(())
}

fn encode_columns(out: &mut Vec<u8>, table: &ParsedTable) -> Result<(), Fault> {
    let Some(arrays) = &table.columns else {
        return Err(internal("ready table without columns"));
    };
    for (column, array) in table.descriptor.columns.iter().zip(arrays) {
        out.push(b'C');
        let ordinal = u32::try_from(column.ordinal).map_err(|_| internal("ordinal exceeds u32"))?;
        out.extend_from_slice(&ordinal.to_be_bytes());
        let kind = ValueKind::of(column);
        let mark = kind.mark();
        let any = array.as_any();
        for row in 0..array.len() {
            if array.is_null(row) {
                put_value(out, 0x00, &[])?;
                continue;
            }
            if let Some(values) = any.downcast_ref::<Int64Array>() {
                put_value(out, mark, &values.value(row).to_be_bytes())?;
            } else if let Some(values) = any.downcast_ref::<UInt64Array>() {
                put_value(out, mark, &values.value(row).to_be_bytes())?;
            } else if let Some(values) = any.downcast_ref::<BooleanArray>() {
                put_value(out, mark, &[u8::from(values.value(row))])?;
            } else if let Some(values) = any.downcast_ref::<Float32Array>() {
                put_value(out, mark, &values.value(row).to_bits().to_be_bytes())?;
            } else if let Some(values) = any.downcast_ref::<Float64Array>() {
                put_value(out, mark, &values.value(row).to_bits().to_be_bytes())?;
            } else if let Some(values) = any.downcast_ref::<StringArray>() {
                put_value(out, mark, values.value(row).as_bytes())?;
            } else if let Some(values) = any.downcast_ref::<BinaryArray>() {
                put_value(out, mark, values.value(row))?;
            } else {
                return Err(internal("unsupported arrow array in canonical encoding"));
            }
        }
    }
    Ok(())
}
