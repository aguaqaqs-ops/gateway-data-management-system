use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use arrow_array::{Array, Int64Array, RecordBatch, RecordBatchOptions, StringArray, UInt64Array};
use arrow_schema::{Field, Schema};
use gateway_shared_kernel::DeclaredType;

use super::*;
use crate::canonical_ipc::{CanonicalIpcBudgets, CanonicalIpcControl, CanonicalIpcOptions, encode_v1};
use crate::table_access::{ParsedTable, SqlParseOptions, build_parser_pool, parse_sql_dump};

fn options() -> BusinessKernelOptions<'static> {
    BusinessKernelOptions { budgets: BusinessKernelBudgets { max_columns: 2048, max_batches: 64, max_rows: 10000, max_metadata_bytes: 1024 * 1024, max_input_bytes: 16 * 1024 * 1024, max_live_bytes: 128 * 1024 * 1024, max_output_bytes: 32 * 1024 * 1024, max_diagnostic_bytes: 256 * 1024 }, control: BusinessKernelControl::default() }
}

fn batches(table: &ParsedTable) -> Result<Vec<RecordBatch>, String> {
    let arrays = table.columns.clone().ok_or("table is not READY")?;
    let schema = Arc::new(Schema::new(table.descriptor.columns.iter().zip(&arrays).map(|(column, array)| Field::new(&column.canonical_name, array.data_type().clone(), column.nullable)).collect::<Vec<_>>()));
    Ok(vec![RecordBatch::try_new_with_options(schema, arrays, &RecordBatchOptions::new().with_row_count(Some(table.row_count))).map_err(|error| error.to_string())?])
}

fn plan(table: &ParsedTable, policy: ProjectionRowPolicy) -> CanonicalProjectionPlan {
    CanonicalProjectionPlan { materialization_stage: MaterializationStage::Final, canonical_table: table.descriptor.canonical_name.clone(), expected_source_row_count: table.row_count, columns: table.descriptor.columns.iter().enumerate().map(|(index, descriptor)| CanonicalProjectionColumn { source_index: Some(index), descriptor: descriptor.clone() }).collect(), canonical_key_columns: table.descriptor.primary_key.clone(), structural_columns: Vec::new(), row_policy: policy, canonicalized_input: false, schema_diagnostics: Vec::new(), omitted_schema_diagnostic_count: 0 }
}

fn hex(bytes: &[u8]) -> String { bytes.iter().map(|byte| format!("{byte:02x}")).collect() }

#[test]
fn sql_materialization_matches_existing_snapshot_goldens() -> Result<(), String> {
    let pool = build_parser_pool(2).map_err(|error| error.to_string())?;
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/golden/snapshot-materialization");
    for case in ["sql/valid/s2-minimal-create-insert", "sql/valid/s2-duplicate-rows", "sql/valid/s2-keyless", "sql/valid/s2-null-and-types", "sql/partial/s2-unknown-type-mixed"] {
        let sql = std::fs::read(root.join(case).join("input.sql")).map_err(|error| error.to_string())?;
        let expected: serde_json::Value = serde_json::from_slice(&std::fs::read(root.join(case).join("expected.json")).map_err(|error| error.to_string())?).map_err(|error| error.to_string())?;
        let parsed = parse_sql_dump(&sql, &SqlParseOptions::default(), &pool);
        for table in &parsed.tables {
            if !table.descriptor.reader_ready { continue; }
            let expected = expected["tables"].as_array().ok_or("missing expected tables")?.iter().find(|expected| expected["table_name"] == table.descriptor.canonical_name).ok_or("missing table oracle")?;
            let batches = batches(table)?;
            let plan = SqlMaterializationPlan { stage: MaterializationStage::Final, effective_compare_key_columns: expected["compare_key_columns"].as_array().ok_or("missing expected keys")?.iter().map(|value| value.as_str().map(str::to_owned).ok_or("bad key")).collect::<Result<_, _>>()? };
            let result = materialize_sql_table(KernelTableInput { descriptor: &table.descriptor, batches: &batches }, &plan, &pool, options()).map_err(|error| error.to_string())?;
            let output = result.output.ok_or("SQL unexpectedly blocked")?;
            assert_eq!(format!("sha256:{}", hex(&output.raw_content_digest.ok_or("digest missing")?)), expected["raw_content_digest"].as_str().ok_or("missing digest oracle")?, "{case}");
            assert_eq!(output.table.row_count, table.row_count);
            assert_eq!(output.duplicate_effective_key, case.ends_with("s2-duplicate-rows"));
            let provisional = materialize_sql_table(KernelTableInput { descriptor: &table.descriptor, batches: &batches }, &SqlMaterializationPlan { stage: MaterializationStage::Provisional, ..plan }, &pool, options()).map_err(|error| error.to_string())?.output.ok_or("provisional blocked")?;
            assert!(provisional.raw_content_digest.is_none());
        }
    }
    Ok(())
}

#[test]
fn set_cell_uses_fixed_sequence_frame_and_distinguishes_null_and_empty() -> Result<(), String> {
    let pool = build_parser_pool(1).map_err(|error| error.to_string())?;
    let parsed = parse_sql_dump(b"CREATE TABLE t (s SET('b','a') NULL); INSERT INTO t VALUES ('a,b'), (''), (NULL);", &SqlParseOptions::default(), &pool);
    let table = parsed.tables.first().ok_or("table missing")?;
    let column = &table.descriptor.columns[0];
    // Existing ENUM/SET vectors: each string scalar is framed as sequence item.
    assert_eq!(cells::frame(column, cells::Cell::Text("a,b")).map_err(|error| error.to_string())?, [2, 3, 0x20, 1, b'b', 3, 0x20, 1, b'a']);
    assert_eq!(cells::frame(column, cells::Cell::Text("")).map_err(|error| error.to_string())?, [0]);
    assert_eq!(cells::frame(column, cells::Cell::Null).map_err(|error| error.to_string())?, [0, 0]);
    Ok(())
}

#[test]
fn keyed_projection_orders_cell_frames_and_is_chunk_and_ddl_invariant() -> Result<(), String> {
    let mut encoded = Vec::new();
    for (threads, sql) in [(1, "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, value VARCHAR(8)); INSERT INTO t VALUES (10,'a'),(-1,'c'),(2,'b');"), (3, "CREATE TABLE t (value VARCHAR(8), id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES ('b',2),('a',10),('c',-1);")] {
        let pool = build_parser_pool(threads).map_err(|error| error.to_string())?;
        let parsed = parse_sql_dump(sql.as_bytes(), &SqlParseOptions { chunk_bytes: 1, ..SqlParseOptions::default() }, &pool);
        let table = parsed.tables.first().ok_or("table missing")?;
        let input_batches = batches(table)?;
        let result = project_canonical_table(KernelTableInput { descriptor: &table.descriptor, batches: &input_batches }, &plan(table, ProjectionRowPolicy::Keyed), &pool, options()).map_err(|error| error.to_string())?.output.ok_or("projection blocked")?;
        let id = result.table.descriptor.columns.iter().position(|column| column.canonical_name == "id").ok_or("missing id")?;
        let values = result.table.batches[0].column(id).as_any().downcast_ref::<Int64Array>().ok_or("bad id Arrow")?;
        assert_eq!(values.values().as_ref(), &[2, 10, -1]);
        let ipc = encode_v1(&result.table.descriptor.columns, &result.table.batches, &pool, CanonicalIpcOptions { budgets: CanonicalIpcBudgets { max_rows: 10000, max_columns: 2048, max_descriptor_bytes: 1024 * 1024, max_input_batches: 64, max_input_bytes: 16 * 1024 * 1024, max_output_bytes: 32 * 1024 * 1024, max_codec_peak_bytes: 128 * 1024 * 1024 }, control: CanonicalIpcControl::default() }).map_err(|error| error.to_string())?;
        encoded.push((result.raw_content_digest, ipc));
    }
    assert_eq!(encoded[0], encoded[1]);
    Ok(())
}

#[test]
fn keyless_preserves_duplicate_zero_column_rows_and_source_count_binding() -> Result<(), String> {
    let pool = build_parser_pool(1).map_err(|error| error.to_string())?;
    let parsed = parse_sql_dump(b"CREATE TABLE t (v INT); INSERT INTO t VALUES (1),(1),(2);", &SqlParseOptions::default(), &pool);
    let table = parsed.tables.first().ok_or("table missing")?;
    let input_batches = batches(table)?;
    let mut plan = plan(table, ProjectionRowPolicy::Keyless);
    plan.columns.clear();
    let input = KernelTableInput { descriptor: &table.descriptor, batches: &input_batches };
    let result = project_canonical_table(input, &plan, &pool, options()).map_err(|error| error.to_string())?.output.ok_or("zero column projection blocked")?;
    assert_eq!(result.table.batches[0].num_columns(), 0);
    assert_eq!(result.table.batches[0].num_rows(), 3);
    plan.expected_source_row_count = 0;
    let failed = project_canonical_table(input, &plan, &pool, options()).map_err(|error| error.to_string())?;
    assert!(failed.output.is_none());
    assert_eq!(failed.diagnostics[0].code, "ROW_INTEGRITY");
    Ok(())
}

#[test]
fn ordered_projection_allocates_pseudo_by_no_and_stores_by_numeric_gid() -> Result<(), String> {
    let pool = build_parser_pool(1).map_err(|error| error.to_string())?;
    let parsed = parse_sql_dump(b"CREATE TABLE t (gid BIGINT NULL, no INT NOT NULL, value VARCHAR(8)); INSERT INTO t VALUES (0,3,'c'),(NULL,1,'a'),(7,2,'b');", &SqlParseOptions::default(), &pool);
    let table = parsed.tables.first().ok_or("table missing")?;
    let input_batches = batches(table)?;
    let mut plan = plan(table, ProjectionRowPolicy::OrderedGidNo);
    plan.canonical_key_columns = vec!["gid".into()];
    plan.structural_columns = vec!["no".into()];
    plan.columns[0].descriptor.sql_type = "INT UNSIGNED".into();
    plan.columns[0].descriptor.declared_type = Some(DeclaredType::UnsignedInteger { bits: 32 });
    plan.columns[0].descriptor.nullable = false;
    let result = project_canonical_table(KernelTableInput { descriptor: &table.descriptor, batches: &input_batches }, &plan, &pool, options()).map_err(|error| error.to_string())?.output.ok_or("ordered projection blocked")?;
    let gids = result.table.batches[0].column(0).as_any().downcast_ref::<UInt64Array>().ok_or("bad gid Arrow")?;
    assert_eq!(gids.values().as_ref(), &[7, 4_000_000_000, 4_000_000_001]);
    let nos = result.table.batches[0].column(1).as_any().downcast_ref::<Int64Array>().ok_or("bad no Arrow")?;
    assert_eq!(nos.values().as_ref(), &[2, 1, 3]);
    assert_eq!((result.gid_real_count, result.gid_pseudo_count), (Some(1), Some(2)));
    Ok(())
}

#[test]
fn catalog_retains_source_count_when_no_special_device_matches() -> Result<(), String> {
    let pool = build_parser_pool(1).map_err(|error| error.to_string())?;
    let parsed = parse_sql_dump("CREATE TABLE device (gid INT, dev_addr INT, description TEXT); INSERT INTO device VALUES (1,1,''),(2,65532,'ordinary');".as_bytes(), &SqlParseOptions::default(), &pool);
    let table = parsed.tables.first().ok_or("table missing")?;
    let input_batches = batches(table)?;
    let result = filter_catalog(CatalogFilterInput { device_table: Some(KernelTableInput { descriptor: &table.descriptor, batches: &input_batches }), point_tables: &[] }, &pool, options()).map_err(|error| error.to_string())?.output.ok_or("catalog blocked")?;
    assert_eq!(result.source_device_row_count, 2);
    assert_eq!(result.matching_devices.ok_or("device table missing")?.row_count, 0);
    Ok(())
}

#[test]
fn business_kernel_control_and_budget_failures_have_no_publishable_output() -> Result<(), String> {
    let pool = build_parser_pool(1).map_err(|error| error.to_string())?;
    let parsed = parse_sql_dump(b"CREATE TABLE t (id INT); INSERT INTO t VALUES (1);", &SqlParseOptions::default(), &pool);
    let table = parsed.tables.first().ok_or("table missing")?;
    let input_batches = batches(table)?;
    let input = KernelTableInput { descriptor: &table.descriptor, batches: &input_batches };
    let cancel = AtomicBool::new(true);
    let mut cancelled = options();
    cancelled.control.cancel = Some(&cancel);
    let error = project_canonical_table(input, &plan(table, ProjectionRowPolicy::Keyless), &pool, cancelled).err().ok_or("cancel should fail")?;
    assert_eq!(error.kind(), BusinessKernelErrorKind::Cancelled);
    let mut limited = options(); limited.budgets.max_output_bytes = 1;
    let error = project_canonical_table(input, &plan(table, ProjectionRowPolicy::Keyless), &pool, limited).err().ok_or("output budget should fail")?;
    assert_eq!(error.kind(), BusinessKernelErrorKind::Resource);
    Ok(())
}
