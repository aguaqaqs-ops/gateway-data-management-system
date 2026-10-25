use std::collections::HashMap;
use std::error::Error;

use arrow_array::{Int64Array, RecordBatch, StringArray};
use arrow_schema::{ArrowError, DataType, Field, Schema};
use proptest::prelude::*;

use super::*;

fn field(name: &str, scalar_type: &str, data_type: DataType, nullable: bool) -> Field {
    let metadata = HashMap::from([("gdms.scalar_type".to_string(), scalar_type.to_string())]);
    Field::new(name, data_type, nullable).with_metadata(metadata)
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
    let mut fields = vec![
        field("gid", "INT UNSIGNED", DataType::Int64, true),
        field("no", "INT", DataType::Int64, false),
        field("name", "VARCHAR(64)", DataType::Utf8, true),
    ];
    let mut arrays: Vec<arrow_array::ArrayRef> = vec![
        std::sync::Arc::new(Int64Array::from(gids.to_vec())),
        std::sync::Arc::new(Int64Array::from(positions.to_vec())),
        std::sync::Arc::new(StringArray::from(names.to_vec())),
    ];
    if let Some(values) = extra {
        fields.push(field("extra", "VARCHAR(64)", DataType::Utf8, true));
        arrays.push(std::sync::Arc::new(StringArray::from(values.to_vec())));
    }
    RecordBatch::try_new(std::sync::Arc::new(Schema::new(fields)), arrays)
}

fn options() -> OrderedCompareOptions {
    let mut options = OrderedCompareOptions::new("b1_n1_measure");
    options.policy_version = "iec104-gid-no-v1".to_string();
    options.value_columns = vec!["name".to_string()];
    options
}

fn compare<'a>(
    before: &'a RecordBatch,
    current: &'a RecordBatch,
    options: &'a OrderedCompareOptions,
) -> Result<OrderedCompareResult, OrderedCompareError> {
    compare_ordered_table(OrderedTablePair {
        before: Some(before),
        current: Some(current),
        options,
    })
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
    assert_eq!(result.records.len(), 3);
    assert_eq!(result.ordered_extension.records.len(), 3);
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
    assert_eq!(result.blank_extension.records.len(), 1);
    assert_eq!(result.blank_extension.records[0].interval.row_count, 1);
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
    assert!(result.records.is_empty());
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

#[test]
fn row_and_column_budgets_produce_bounded_degraded_facts() -> Result<(), Box<dyn Error>> {
    let before = batch(&[Some(1), Some(2)], &[1, 2], &[Some("a"), Some("b")])?;
    let current = batch(&[Some(1)], &[1], &[Some("a")])?;
    let mut policy = options();
    policy.max_rows = 1;
    let result = compare(&before, &current, &policy)?;

    assert_eq!(result.status, "DEGRADED");
    assert_eq!(result.diagnostics, vec!["RESOURCE_LIMIT_EXCEEDED"]);
    assert!(result.canonical_bytes()?.len() < 4096);
    Ok(())
}

#[test]
fn table_parallelism_is_byte_deterministic_for_one_and_many_threads() -> Result<(), Box<dyn Error>>
{
    let mut owned = Vec::new();
    for number in (1..=9).rev() {
        let before = batch(
            &[Some(number), Some(number + 100)],
            &[1, 2],
            &[Some("a"), Some("b")],
        )?;
        let current = batch(
            &[Some(number + 100), Some(number), Some(number + 200)],
            &[1, 2, 3],
            &[Some("b"), Some("a"), Some("c")],
        )?;
        let mut policy = options();
        policy.table_name = format!("b1_n1_table_{number:02}");
        owned.push((before, current, policy));
    }
    let pairs: Vec<OrderedTablePair<'_>> = owned
        .iter()
        .map(|(before, current, policy)| OrderedTablePair {
            before: Some(before),
            current: Some(current),
            options: policy,
        })
        .collect();
    let one = build_ordered_pool(1)?;
    let many = build_ordered_pool(8)?;
    let serial = compare_ordered_tables_parallel(&pairs, &one)?;
    let parallel = compare_ordered_tables_parallel(&pairs, &many)?;

    assert_eq!(serial.len(), parallel.len());
    for (left, right) in serial.iter().zip(&parallel) {
        assert_eq!(left.table_name, right.table_name);
        assert_eq!(left.canonical_bytes()?, right.canonical_bytes()?);
    }
    assert!(
        serial
            .windows(2)
            .all(|window| window[0].table_name < window[1].table_name)
    );
    assert!(build_ordered_pool(0).is_err());
    assert!(build_ordered_pool(MAX_ORDERED_THREADS + 1).is_err());
    Ok(())
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(96))]

    #[test]
    fn arbitrary_unique_sequences_stay_bounded_and_thread_independent(
        before_order in prop::collection::vec(0u8..80, 0..48),
        current_order in prop::collection::vec(0u8..80, 0..48),
        before_blanks in prop::collection::vec(any::<bool>(), 0..48),
        current_blanks in prop::collection::vec(any::<bool>(), 0..48),
        before_values in prop::collection::vec(0u8..10, 0..48),
        current_values in prop::collection::vec(0u8..10, 0..48),
    ) {
        let before = unique_rows(&before_order, &before_blanks, &before_values);
        let current = unique_rows(&current_order, &current_blanks, &current_values);
        let before_batch = batch(&before.0, &before.1, &before.2).map_err(|error| TestCaseError::fail(error.to_string()))?;
        let current_batch = batch(&current.0, &current.1, &current.2).map_err(|error| TestCaseError::fail(error.to_string()))?;
        let policy = options();
        let one = build_ordered_pool(1).map_err(|error| TestCaseError::fail(error.to_string()))?;
        let many = build_ordered_pool(4).map_err(|error| TestCaseError::fail(error.to_string()))?;
        let single = compare(&before_batch, &current_batch, &policy)
            .map_err(|error| TestCaseError::fail(error.to_string()))?;
        let pair = [OrderedTablePair {
            before: Some(&before_batch),
            current: Some(&current_batch),
            options: &policy,
        }];
        let single_pool_result = compare_ordered_tables_parallel(&pair, &one)
            .map_err(|error| TestCaseError::fail(error.to_string()))?;
        let parallel_pool_result = compare_ordered_tables_parallel(&pair, &many)
            .map_err(|error| TestCaseError::fail(error.to_string()))?;
        prop_assert!(single.canonical_bytes().map_err(|error| TestCaseError::fail(error.to_string()))?.len() < 1_000_000);
        prop_assert_eq!(
            single_pool_result[0].canonical_bytes().map_err(|error| TestCaseError::fail(error.to_string()))?,
            parallel_pool_result[0].canonical_bytes().map_err(|error| TestCaseError::fail(error.to_string()))?
        );
    }
}

fn unique_rows(
    requested_ids: &[u8],
    requested_blanks: &[bool],
    requested_values: &[u8],
) -> (Vec<Option<i64>>, Vec<i64>, Vec<Option<&'static str>>) {
    let mut seen = std::collections::BTreeSet::new();
    let ids: Vec<u8> = requested_ids
        .iter()
        .copied()
        .filter(|value| seen.insert(*value))
        .collect();
    let count = ids.len();
    let mut gids = Vec::with_capacity(count);
    let mut positions = Vec::with_capacity(count);
    let mut names = Vec::with_capacity(count);
    for (index, id) in ids.into_iter().enumerate() {
        let is_blank = requested_blanks.get(index).copied().unwrap_or(false);
        gids.push(if is_blank {
            None
        } else {
            Some(i64::from(id) + 1)
        });
        positions.push(i64::try_from(index + 1).unwrap_or(i64::MAX));
        let value = requested_values.get(index).copied().unwrap_or(0);
        let text = match value % 10 {
            0 => "v0",
            1 => "v1",
            2 => "v2",
            3 => "v3",
            4 => "v4",
            5 => "v5",
            6 => "v6",
            7 => "v7",
            8 => "v8",
            _ => "v9",
        };
        names.push(Some(text));
    }
    (gids, positions, names)
}
