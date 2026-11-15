use std::collections::HashMap;
use std::error::Error;
use std::ops::Deref;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use arrow_array::{Int64Array, RecordBatch, StringArray, UInt64Array};
use arrow_schema::{ArrowError, DataType, Field, Schema};

use super::*;

fn field(
    name: &str,
    scalar_type: &str,
    data_type: DataType,
    nullable: bool,
) -> Result<Field, ArrowError> {
    let (sql_type, kind, bits) = match scalar_type {
        "INT UNSIGNED" => ("INT UNSIGNED", "unsigned-integer", Some(32u8)),
        "BIGINT" => ("BIGINT", "signed-integer", Some(64u8)),
        "INT" => ("INT", "signed-integer", Some(32u8)),
        "VARCHAR(64)" => ("VARCHAR(64)", "string", None),
        _ => {
            return Err(ArrowError::SchemaError(
                "unexpected test scalar type".to_string(),
            ));
        }
    };
    let canonical_type = serde_json::json!({
        "declared_type": {"kind": kind, "bits": bits, "precision": null, "scale": null, "bit_width": null},
        "labels": null,
        "logical_type": "standard",
        "sql_type": sql_type,
    });
    Ok(
        Field::new(name, data_type, nullable).with_metadata(HashMap::from([(
            "gdds.canonical_type".to_string(),
            canonical_type.to_string(),
        )])),
    )
}

fn batch(
    gids: &[Option<i64>],
    positions: &[i64],
    names: &[Option<&str>],
) -> Result<RecordBatch, ArrowError> {
    batch_with_extra(gids, positions, names, None)
}

fn batch_with_extra(
    gids: &[Option<i64>],
    positions: &[i64],
    names: &[Option<&str>],
    extra: Option<&[Option<&str>]>,
) -> Result<RecordBatch, ArrowError> {
    let signed_gid = gids.iter().flatten().any(|gid| *gid < 0);
    let mut fields = vec![
        field(
            "gid",
            if signed_gid { "BIGINT" } else { "INT UNSIGNED" },
            if signed_gid {
                DataType::Int64
            } else {
                DataType::UInt64
            },
            true,
        )?,
        field("no", "INT", DataType::Int64, false)?,
        field("name", "VARCHAR(64)", DataType::Utf8, true)?,
    ];
    let gid_array: arrow_array::ArrayRef = if signed_gid {
        Arc::new(Int64Array::from(gids.to_vec()))
    } else {
        let unsigned = gids
            .iter()
            .map(|gid| gid.map(u64::try_from).transpose())
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| ArrowError::SchemaError(error.to_string()))?;
        Arc::new(UInt64Array::from(unsigned))
    };
    let mut arrays: Vec<arrow_array::ArrayRef> = vec![
        gid_array,
        std::sync::Arc::new(Int64Array::from(positions.to_vec())),
        std::sync::Arc::new(StringArray::from(names.to_vec())),
    ];
    if let Some(values) = extra {
        fields.push(field("extra", "VARCHAR(64)", DataType::Utf8, true)?);
        arrays.push(std::sync::Arc::new(StringArray::from(values.to_vec())));
    }
    let schema = Schema::new(fields).with_metadata(HashMap::from([(
        "gdds.canonical_mapping_version".to_string(),
        "1".to_string(),
    )]));
    RecordBatch::try_new(Arc::new(schema), arrays)
}

fn options() -> OrderedCompareOptions {
    let mut options = OrderedCompareOptions::new("b1_n1_measure");
    options.policy_version = "iec104-gid-no-v1".to_string();
    options.value_columns = vec!["name".to_string()];
    options
}

#[test]
fn invalid_gid_diagnostic_keeps_source_and_canonical_provenance_distinct()
-> Result<(), Box<dyn Error>> {
    let invalid = batch(&[Some(-1)], &[1], &[Some("x")])?;
    let mut source = options();
    source.before_blank_provenance = BlankProvenance::SourceMissingStableKey;
    source.current_blank_provenance = BlankProvenance::SourceMissingStableKey;
    let source_result = compare(&invalid, &invalid, &source)?;
    assert_eq!(source_result.diagnostics, ["SOURCE_GID_INVALID"]);

    let mut canonical = options();
    canonical.before_blank_provenance = BlankProvenance::CanonicalPseudoGid;
    canonical.current_blank_provenance = BlankProvenance::CanonicalPseudoGid;
    let canonical_result = compare(&invalid, &invalid, &canonical)?;
    assert_eq!(canonical_result.diagnostics, ["CANONICAL_GID_INVALID"]);
    Ok(())
}

fn compare<'a>(
    before: &'a RecordBatch,
    current: &'a RecordBatch,
    options: &'a OrderedCompareOptions,
) -> Result<TestedComparison, OrderedCompareError> {
    let before_batches = [before.clone()];
    let current_batches = [current.clone()];
    let context = Arc::new(KernelContext::new(
        64 * 1024 * 1024,
        Arc::new(AtomicBool::new(false)),
        None,
    ));
    let result = compare_ordered_batches(
        OrderedBatchPair {
            before: Some(&before_batches),
            current: Some(&current_batches),
            before_schema: Some(before.schema()),
            current_schema: Some(current.schema()),
            options,
        },
        &context,
    )?;
    Ok(TestedComparison {
        standard_count: result.standard_records.len(),
        ordered_count: result.ordered_records.len(),
        ordered_records: result.ordered_records,
        blank_records: result.blank_records,
        facts: result.facts_metadata,
    })
}

struct TestedComparison {
    facts: OrderedCompareResult,
    standard_count: usize,
    ordered_count: usize,
    ordered_records: Vec<OrderedRecordRef>,
    blank_records: Vec<BlankRecordRef>,
}

impl Deref for TestedComparison {
    type Target = OrderedCompareResult;

    fn deref(&self) -> &Self::Target {
        &self.facts
    }
}

#[test]
fn replacement_slots_ignore_blank_rows_before_a_patch() -> Result<(), Box<dyn Error>> {
    let before = batch(
        &[
            Some(10),
            Some(11),
            Some(12),
            Some(13),
            Some(14),
            Some(15),
            Some(16),
        ],
        &[10, 11, 12, 13, 14, 15, 16],
        &[
            Some("a"),
            Some("b"),
            Some("c"),
            Some("d"),
            Some("e"),
            Some("f"),
            Some("g"),
        ],
    )?;
    for blanks in 1..=3 {
        let mut gids = vec![Some(10), Some(11)];
        let mut names = vec![Some("a"), Some("b")];
        gids.extend(std::iter::repeat_n(None, blanks));
        names.extend(std::iter::repeat_n(Some("blank"), blanks));
        gids.extend([Some(12), Some(113), Some(114), Some(115), Some(16)]);
        names.extend([Some("c"), Some("x"), Some("y"), Some("z"), Some("g")]);
        let positions: Vec<i64> = (10..10 + i64::try_from(gids.len())?).collect();
        let current = batch(&gids, &positions, &names)?;
        let result = compare(&before, &current, &options())?;
        let mut deleted: Vec<_> = result
            .ordered_records
            .iter()
            .filter(|record| record.kind == "ORDERED_ROW_DELETED")
            .collect();
        let mut added: Vec<_> = result
            .ordered_records
            .iter()
            .filter(|record| record.kind == "ORDERED_ROW_ADDED")
            .collect();
        deleted.sort_by_key(|record| record.before_position);
        added.sort_by_key(|record| record.current_position);
        assert_eq!(added.len(), 3);
        assert_eq!(deleted.len(), 3);
        for (old, new) in deleted.iter().zip(added) {
            let old_position = old
                .before_position
                .ok_or_else(|| std::io::Error::other("deleted record has no before position"))?;
            assert_eq!(
                new.replacement_before.as_ref(),
                Some(&(old.row_identity.clone(), old_position))
            );
        }
    }
    Ok(())
}

#[test]
fn replacement_slots_require_equal_counts_and_unmoved_anchors() -> Result<(), Box<dyn Error>> {
    let before = batch(
        &[Some(1), Some(2), Some(3), Some(4), Some(5)],
        &[1, 2, 3, 4, 5],
        &[Some("a"), Some("b"), Some("c"), Some("d"), Some("e")],
    )?;
    let unequal = batch(
        &[
            Some(1),
            None,
            Some(2),
            Some(13),
            Some(14),
            Some(15),
            Some(5),
        ],
        &[1, 2, 3, 4, 5, 6, 7],
        &[
            Some("a"),
            None,
            Some("b"),
            Some("x"),
            Some("y"),
            Some("z"),
            Some("e"),
        ],
    )?;
    let result = compare(&before, &unequal, &options())?;
    assert!(
        result
            .ordered_records
            .iter()
            .filter(|record| record.kind == "ORDERED_ROW_ADDED")
            .all(|record| record.replacement_before.is_none())
    );

    let before_move = batch(
        &[Some(1), Some(2), Some(3), Some(4), Some(5), Some(6)],
        &[1, 2, 3, 4, 5, 6],
        &[
            Some("a"),
            Some("b"),
            Some("c"),
            Some("d"),
            Some("e"),
            Some("f"),
        ],
    )?;
    let moved = batch(
        &[Some(1), Some(4), Some(2), Some(13), Some(14), Some(6)],
        &[1, 2, 3, 4, 5, 6],
        &[
            Some("a"),
            Some("d"),
            Some("b"),
            Some("x"),
            Some("y"),
            Some("f"),
        ],
    )?;
    let result = compare(&before_move, &moved, &options())?;
    assert_eq!(result.ordered_extension.summary.row_moved_count, 1);
    assert!(
        result
            .ordered_records
            .iter()
            .filter(|record| record.kind == "ORDERED_ROW_ADDED")
            .all(|record| record.replacement_before.is_none())
    );
    Ok(())
}

#[test]
fn combines_insert_delete_modify_and_absolute_position_shift() -> Result<(), Box<dyn Error>> {
    let before = batch(
        &[Some(1), Some(2), Some(3)],
        &[1, 2, 3],
        &[Some("a"), Some("b"), Some("c")],
    )?;
    let current = batch(
        &[Some(2), Some(3), Some(4)],
        &[1, 2, 3],
        &[Some("b"), Some("changed"), Some("d")],
    )?;
    let policy = options();
    let result = compare(&before, &current, &policy)?;

    assert_eq!(result.status, "MODIFIED");
    assert_eq!(result.row_added_count, 1);
    assert_eq!(result.row_deleted_count, 1);
    assert_eq!(result.row_modified_count, 1);
    assert_eq!(result.ordered_extension.summary.row_moved_count, 0);
    assert_eq!(result.ordered_extension.summary.position_changed_count, 2);
    assert_eq!(
        result.ordered_extension.table_processing_mode.as_deref(),
        Some("ORDERED_SHIFT_REPAIRED")
    );
    assert_eq!(result.standard_count, 3);
    assert_eq!(result.ordered_count, 3);
    Ok(())
}

#[test]
fn reverse_reorder_uses_earliest_backbone_tie() -> Result<(), Box<dyn Error>> {
    let before = batch(
        &[Some(1), Some(2), Some(3), Some(4)],
        &[1, 2, 3, 4],
        &[Some("a"), Some("b"), Some("c"), Some("d")],
    )?;
    let current = batch(
        &[Some(4), Some(3), Some(2), Some(1)],
        &[1, 2, 3, 4],
        &[Some("d"), Some("c"), Some("b"), Some("a")],
    )?;
    let policy = options();
    let result = compare(&before, &current, &policy)?;

    assert_eq!(result.ordered_extension.summary.row_moved_count, 3);
    assert_eq!(result.ordered_extension.summary.position_changed_count, 1);
    assert_eq!(
        result.ordered_extension.table_processing_mode.as_deref(),
        Some("ORDERED_REORDER_COMPLEX")
    );
    Ok(())
}

#[test]
fn blank_rows_are_counted_by_backbone_interval_and_ignore_payload() -> Result<(), Box<dyn Error>> {
    let before = batch(
        &[Some(1), None, Some(2)],
        &[1, 2, 3],
        &[Some("a"), Some("old blank"), Some("b")],
    )?;
    let current = batch(
        &[Some(1), Some(0), None, Some(2)],
        &[1, 2, 3, 4],
        &[Some("a"), Some("new blank"), Some("different"), Some("b")],
    )?;
    let policy = options();
    let result = compare(&before, &current, &policy)?;

    assert_eq!(result.blank_extension.summary.interval_inserted_count, 1);
    assert_eq!(result.blank_extension.summary.interval_deleted_count, 0);
    assert_eq!(result.blank_extension.summary.blank_changed_count, 1);
    assert_eq!(result.blank_records.len(), 1);
    assert_eq!(result.blank_records[0].interval.row_count, 1);
    assert_eq!(result.ordered_extension.summary.position_changed_count, 1);
    Ok(())
}

#[test]
fn schema_addition_uses_only_shared_columns_for_value_comparison() -> Result<(), Box<dyn Error>> {
    let before = batch(&[Some(1)], &[1], &[Some("a")])?;
    let current = batch_with_extra(&[Some(1)], &[1], &[Some("a")], Some(&[Some("new")]))?;
    let mut policy = options();
    policy.value_columns.clear();
    policy.schema_changed = true;
    policy.schema_changes = SchemaChanges {
        before_only_columns: Vec::new(),
        current_only_columns: vec!["extra".to_string()],
        selected_columns: vec!["gid".to_string(), "name".to_string(), "no".to_string()],
        ..SchemaChanges::default()
    };
    let result = compare(&before, &current, &policy)?;

    assert_eq!(result.status, "SCHEMA_ONLY_CHANGED");
    assert_eq!(result.row_modified_count, 0);
    assert_eq!(result.ordered_extension.summary.row_modified_count, 0);
    assert_eq!(result.standard_count, 0);
    Ok(())
}

#[test]
fn schema_only_shared_content_evidence_requires_column_projection() -> Result<(), Box<dyn Error>> {
    let before = batch(&[Some(1)], &[1], &[Some("a")])?;
    let current = batch(&[Some(1)], &[1], &[Some("b")])?;
    for column_projection in [false, true] {
        let mut policy = options();
        policy.schema_changed = true;
        policy.raw_content_changed = true;
        policy.columns_added = column_projection;
        policy.compare_excluded_columns = vec!["name".to_string()];
        let result = compare(&before, &current, &policy)?;
        assert_eq!(result.status, "SCHEMA_ONLY_CHANGED");
        assert_eq!(result.row_modified_count, 0);
        assert_eq!(result.content_changed, column_projection);
    }
    Ok(())
}

#[test]
fn duplicate_identity_and_position_degrade_with_contract_diagnostics() -> Result<(), Box<dyn Error>>
{
    let duplicate_identity = batch(&[Some(1), Some(1)], &[1, 2], &[Some("a"), Some("b")])?;
    let valid = batch(&[Some(1)], &[1], &[Some("a")])?;
    let policy = options();
    let identity_result = compare(&duplicate_identity, &valid, &policy)?;
    assert_eq!(identity_result.status, "DEGRADED");
    assert_eq!(identity_result.diagnostics, vec!["ROW_IDENTITY_DUPLICATE"]);
    assert_eq!(
        identity_result.ordered_extension.replay_guarantee,
        "UNSUPPORTED"
    );

    let duplicate_position = batch(&[Some(1), Some(2)], &[1, 1], &[Some("a"), Some("b")])?;
    let position_result = compare(&duplicate_position, &valid, &policy)?;
    assert_eq!(position_result.status, "DEGRADED");
    assert_eq!(position_result.diagnostics, vec!["ORDER_KEY_DUPLICATE"]);
    Ok(())
}

#[test]
fn pseudo_gid_requires_canonical_provenance_and_is_not_a_stable_identity()
-> Result<(), Box<dyn Error>> {
    let source_pseudo = batch(&[Some(4_000_000_000)], &[1], &[Some("blank")])?;
    let ordinary = batch(&[Some(1)], &[1], &[Some("row")])?;
    let policy = options();
    let rejected = compare(&source_pseudo, &ordinary, &policy)?;
    assert_eq!(rejected.diagnostics, vec!["SOURCE_RESERVED_PSEUDO_GID"]);

    let mut canonical_policy = options();
    canonical_policy.before_blank_provenance = BlankProvenance::CanonicalPseudoGid;
    canonical_policy.current_blank_provenance = BlankProvenance::CanonicalPseudoGid;
    let canonical_current = batch(&[Some(4_000_000_001)], &[1], &[Some("other blank")])?;
    let canonical = compare(&source_pseudo, &canonical_current, &canonical_policy)?;
    assert_eq!(canonical.row_added_count, 0);
    assert_eq!(canonical.row_deleted_count, 0);
    assert_eq!(canonical.blank_extension.summary.blank_changed_count, 0);
    Ok(())
}

#[test]
fn missing_blank_provenance_degrades_before_reading_rows() -> Result<(), Box<dyn Error>> {
    let before = batch(&[Some(1)], &[1], &[Some("a")])?;
    let current = batch(&[Some(1)], &[1], &[Some("a")])?;
    let mut policy = options();
    policy.before_blank_provenance = BlankProvenance::Missing;
    let result = compare(&before, &current, &policy)?;

    assert_eq!(result.status, "DEGRADED");
    assert_eq!(result.diagnostics, vec!["BLANK_PROVENANCE_MISSING"]);
    assert_eq!(result.ordered_extension.status, "ORDERED_DEGRADED");
    Ok(())
}
