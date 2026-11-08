# Phase 6 S3 E handoff (candidate)

## Scope and fixed sources

E retires the superseded Python row comparator, tuple records writer, and Rust ordered Vec prototype. The production route is canonical Arrow → Rust batch comparison → Arrow records publication. Small Python metadata, Submit/replacement, and real records readers remain. The C/D fixture has 20 exact expanded cases captured on 06 from old Python source `a9da0c59277e3179f34d646eabcd9c185917ae05` (original algorithm traced to `4d5`), not from the new Rust output. Its accepted r3 JSONL SHA is `7c629fdbe64bc4ffb016135accd86cc74edacd93cd7b32347d4ed2364e0027f9`. The one supplemental old Risk digest for keyless UPDATE_ONLY is `sha256:0b383a46b75deede4a692ec08b7a7e9911ebd62bb7775284a59f8d458c4f5122`.

The following table records each removed Python test function's retained business assertion owner. `E live` means `vnext/backend/tests/test_comparison_s3_e_live_semantics.py`; `D` means `test_comparison_s3_d_production.py`; `C` means `test_comparison_s3_c_arrow.py`. An internal raw-reader/mock probe is retired only where its current boundary is identified below. All E live assertions are candidate assertions until dedicated-node focused execution.

### Old `test_comparison_standard.py`

| Removed test function | Current assertion owner |
| --- | --- |
| `test_keyed_comparison_emits_added_deleted_modified_and_field_change` | D `test_production_standard_preserves_fixed_facts_and_facts_order_risk_view`; C `test_native_standard_arrow_and_complete_facts_match_pre_c_source`; E records `test_records_sort_is_independent_of_source_row_order` |
| `test_null_values_remain_typed_and_are_not_stringified` | E artifacts `test_unchanged_pair_publishes_an_empty_closure`; E records `test_records_preserve_binary_float_decimal_time_and_null` |
| `test_modified_null_value_is_retained_as_typed_null_in_field_change` | E artifacts `test_publish_and_reopen_standard_records_preserves_typed_null` |
| `test_added_columns_compare_common_columns_without_schema_status_or_record` | E live `test_standard_added_column_preserves_shared_row_association` |
| `test_added_column_does_not_hide_changes_in_shared_columns` | Rust `standard.rs::columns_added_does_not_treat_nonshared_exclusion_as_hidden_content`; E live `test_standard_added_column_preserves_shared_row_association` |
| `test_added_column_keeps_shared_excluded_value_changes_summary_only` | E live `test_standard_added_column_preserves_shared_row_association` and `test_keyless_added_column_uses_shared_row_multiset` |
| `test_added_column_preserves_excluded_values_row_association` (keyed/keyless) | E live `test_standard_added_column_preserves_shared_row_association` and `test_keyless_added_column_uses_shared_row_multiset` |
| `test_added_column_and_physical_row_reorder_remain_unchanged` (keyed/keyless) | Same two E live parametrized tests, physical-reorder cases |
| `test_enum_and_set_member_additions_are_columns_added` | E live `test_enum_set_label_spelling_changes_schema_and_risk` (add-in-middle cases) |
| `test_enum_and_set_schema_evolution_preserves_exact_label_spelling` (six cases) | Same six E live cases; old independent S1b golden remains the precise schema/Risk reference |
| `test_removed_column_is_classified_separately_from_incompatible_schema` | E live `test_removed_column_is_distinct_from_incompatible_schema` |
| `test_compare_excluded_only_change_is_visible_without_row_records` | E live `test_excluded_value_change_is_visible_without_row_record` |
| `test_incompatible_non_key_type_does_not_create_field_change` | E live `test_incompatible_non_key_type_has_no_value_change_record` |
| `test_changed_effective_key_degrades_without_positional_fallback` | E live `test_changed_effective_key_degrades_without_positional_match` |
| `test_keyless_table_degrades_without_a_safe_effective_key` | D `test_source_key_transition_uses_the_keyless_policy` (DEGRADE case); D `test_keyless_degrade_policy_still_checks_reader_before_schema_record` |
| `test_raw_primary_key_fallback_compares_keyless_rows_as_a_multiset` | Rust `standard.rs::keyless_multiset_keeps_third_occurrence_and_reverse_delete`; D `test_keyless_columns_added_update_only_keeps_suppressed_counts_and_status` |
| `test_keyless_table_addition_is_table_level_without_row_records` | D `test_metadata_only_added_deleted_tables_replay_full_core_without_native_reads` (added case) |
| `test_whole_table_deletion_is_table_level_without_row_records` | Same D test (deleted case) |
| `test_single_side_facts_use_only_metadata_budget_without_reading_rows` (standard/ordered, added/deleted) | Same four D cases with `native_calls == input_reads == 0` and fixed old-source core |
| `test_raw_primary_key_appearance_or_disappearance_is_a_source_schema_change` | E live `test_raw_primary_key_appearance_is_a_source_schema_change`; D `test_source_key_transition_uses_the_keyless_policy` (disappearance); planning `test_source_ddl_primary_key_change_does_not_masquerade_as_rule_change` |
| `test_update_only_suppresses_records_but_keeps_counts` | D `test_keyless_columns_added_update_only_keeps_suppressed_counts_and_status`; E records `test_update_only_publishes_only_update_records` |
| `test_missing_tables_are_not_materialized_as_empty_tables` | D `test_metadata_only_added_deleted_tables_replay_full_core_without_native_reads`; Rust `standard.rs::present_zero_batch_table_is_distinct_from_missing_side` |
| `test_duplicate_effective_key_is_table_degraded_not_fake_update` | D `test_duplicate_key_keeps_the_frozen_table_diagnostic`; Rust `standard.rs::duplicate_effective_key_is_a_table_error_for_planner_degradation` |
| `test_pair_and_table_early_exit_do_not_iterate_or_reopen_readers` | E live `test_equal_canonical_storage_short_circuits_table_read_across_snapshots`; D `test_metadata_only_added_deleted_tables_replay_full_core_without_native_reads` covers no native read on metadata path. The removed counting-reader mock is not retained. |
| `test_table_early_exit_works_when_pair_snapshot_digests_differ` | Same E live cross-snapshot test |
| `test_invalid_row_shape_is_degraded_and_never_treated_as_empty` | E live `test_malformed_canonical_row_shape_degrades_instead_of_appearing_empty` passes a profiled Arrow batch with a selected column absent and asserts production `ROW_SHAPE_MISMATCH`, DEGRADED, and zero row counts. |
| `test_facts_digest_is_deterministic_and_directional` | E live `test_comparison_digest_is_repeatable_and_directional`; C/D fixed old-source core/comparison digest cases |
| `test_comparison_propagates_operation_stop_and_resource_rejection` | D `test_reader_cancel_inside_arrow_stream_stops_before_table_degradation`; C `test_native_operation_rejects_cancel_or_expired_deadline_and_releases`, `test_native_budget_failure_releases_input_and_phase_charges` |

### Old `test_comparison_ordered.py`

| Removed test function | Current assertion owner |
| --- | --- |
| `test_ordered_content_and_move_are_separate_records` | D `test_production_ordered_move_and_blank_match_frozen_facts_and_three_parquets`; C `test_ordered_and_blank_arrow_and_complete_fact_replay_match_frozen_python` |
| `test_comparison_reopens_an_intermediate_snapshot_used_by_multiple_pairs` | History `test_history_compare_jobs.py` and Compose checkpoint/materialization binding assertions; D `test_full_pair_session_reuses_only_an_identical_declared_task` |
| `test_ordered_move_only_has_no_content_update` | Rust `ordered/tests.rs::reverse_reorder_uses_earliest_backbone_tie`; D ordered fixed case |
| `test_ordered_absolute_renumber_is_position_change_not_move` | E live `test_absolute_order_renumber_is_a_position_shift_without_records` |
| `test_ordered_does_not_use_positional_fallback` | E live `test_ordered_identity_change_emits_add_delete_without_positional_fallback` |
| `test_ordered_compare_excluded_change_is_visible_without_row_change` | E live `test_ordered_excluded_value_change_is_visible_without_row_record` |
| `test_ordered_added_column_compares_shared_excluded_values` | D `test_ordered_added_column_uses_shared_row_association` (excluded swap case) |
| `test_ordered_added_column_and_physical_row_reorder_remain_unchanged` | Same D test (physical reorder case) |
| `test_ordered_integrity_faults_degrade_without_records` (duplicate gid/no, missing no) | Rust `ordered/tests.rs::duplicate_identity_and_position_degrade_with_contract_diagnostics`; E live `test_missing_order_key_degrades_ordered_replay` |
| `test_sql_reserved_pseudo_gid_is_rejected_at_materialization_boundary` | `test_business_kernel_native.py::test_reserved_source_gid_strings_follow_the_python_int_owner` asserts `materialize_sql` rejects the reserved gid; `test_storage_projection_integrity.py::test_ordered_gid_no_faults` covers the downstream projection boundary. |
| `test_ordered_missing_provenance_degrades_before_row_interpretation` | Rust `ordered/tests.rs::missing_blank_provenance_degrades_before_reading_rows`; D `test_ordered_reader_failure_preserves_standard_ordered_and_blank_degradation` |
| `test_ordered_facts_and_extension_digests_are_deterministic` | C/D fixed old-source ordered core/table/extension/Parquet; E live directional digest |
| `test_unchanged_ordered_early_exit_matches_full_facts_without_running_diff` | Rust `standard.rs::unchanged_ordered_reads_current_side_only`; D `test_full_pair_session_reuses_only_an_identical_declared_task`. Retired Python diff monkeypatch is an implementation probe. |
| `test_canonical_pseudo_gid_requires_explicit_provenance` | Rust `ordered/tests.rs::pseudo_gid_requires_canonical_provenance_and_is_not_a_stable_identity`; `test_storage_projection_integrity.py::test_canonical_ordered_snapshot_reprojection_preserves_pseudo_identity` |
| `test_backbone_reports_moves_blank_intervals_and_summarised_shifts` (G8b table) | Rust `ordered/tests.rs` batch cases for insert/delete/modify/shift, earliest tie, blank interval; D frozen ordered case; E live pure shift, blank interval shift, and `test_ordered_public_processing_modes_have_live_batch_records` for LOCAL_PATCH/TAIL_SEGMENT |
| `test_backbone_is_the_earliest_longest_increasing_run_in_before_order` | Rust `ordered/tests.rs::reverse_reorder_uses_earliest_backbone_tie`, `standard.rs::ordered_locator_path_reuses_earliest_lis_tie` |
| `test_backbone_of_a_long_table_skips_only_the_moved_row` | Rust `standard.rs::ordered_locator_path_reuses_earliest_lis_tie`; Rust `ordered/tests.rs` batch move/shift cases. The retired Python LIS stress probe has no live Python algorithm. |

### Old `test_comparison_blank.py`

| Removed test function | Current assertion owner |
| --- | --- |
| `test_blank_payload_change_has_no_ordinary_or_blank_record` | Rust `ordered/tests.rs::blank_rows_are_counted_by_backbone_interval_and_ignore_payload`; C/D ordered fixed case |
| `test_blank_occupancy_change_is_an_interval_delete_without_move` | Rust same batch case; D `test_production_ordered_move_and_blank_match_frozen_facts_and_three_parquets` |
| `test_blank_occupancy_change_is_an_interval_insert_without_move` | Rust same batch case; E live `test_blank_interval_shift_emits_delete_and_insert_without_move_pairing` |
| `test_blank_no_renumber_keeps_occupancy_digest_and_records_stable` | E live `test_blank_position_renumber_keeps_occupancy_without_records` |
| `test_blank_interval_shift_is_delete_and_insert_without_move_pairing` | E live `test_blank_interval_shift_emits_delete_and_insert_without_move_pairing` |

### Other former Python and Rust owners

| Removed or rewritten file | Current owner / retained boundary |
| --- | --- |
| `test_comparison_records.py` | Same file now uses real native/Arrow publication for deterministic sort, binary/float/decimal/DATE/DATETIME/TIMESTAMP/null, UPDATE_ONLY and replacement records-ref rejection. Rust records validator owns duplicate logical-record rejection; C `test_actual_records_reader_rejects_noncanonical_parquet_shape` and `test_real_open_read_restore_use_native_arrow_validator` own malformed/restore. |
| `test_comparison_artifacts.py` | Same file now uses real native/Arrow publication for STANDARD/ORDERED/BLANK families, empty closure, ref rewrite, store failure, corrupt payload/manifest, duplicate closure, all three detail policies, record/artifact/spool/JSON limits, reopen limits, cancellation/stop. The no-handle metadata branch still checks the per-table sum before publication, although current metadata degradation generates only one record; the real multi-family budget test belongs to the native-handle path. |
| `test_comparison_rule_roles.py`, `test_comparison_planning.py`, `test_comparison_replacement.py` | Same suites now use canonical Arrow/native and preserve non-record role suppression, source-vs-rule schema facts, effective keys, replacement Preview/History bundle. |
| `tests/support/history_compare_oracle.py`, `tests/support/compose_gate_harness.py`, `benchmarks/real_dump_census.py` | Live canonical Arrow/native comparison and real handle count; History digest equality is checkpoint/materialization→assemble or remote→local binding, with status/kinds/count/commit/side/ref assertions retained. Compose embedded oracle does not parse unused gid/identity. |
| Rust ordered Vec entrypoints/tests/example, B differential/probe/benchmark | Deleted with the superseded entrypoint. Eight distinct ordered business cases moved to `ordered/tests.rs` batch tests, missing-no to E live; B added-column full shared association has one permanent owner in D `test_ordered_added_column_uses_shared_row_association`. Resource and parallel behavior remain in Rust standard batch tests. |

## Validation state

The latest Rust tree `9d4f` at commit `2c9eaf72adaedf99d55da4b85f254baad560cae7` passed 06 `cargo fmt --all --check`, workspace/all-target Clippy `-D warnings`, and workspace test (197 passed), with independent evidence review. Python source deletion, live assertion transfers, metrics, and the final six-package/container/real-data gates remain pending dedicated-node execution and review. E performance logs observe actual preview uploaded projection and bundle assembly entrances with operation ID and stage; pair-local `upstream_projection_seconds` and `bundle_assembly_seconds` remain `None`. Risk's ruleset validation, fact extraction, rule evaluation, publication, and residual are disjoint top-level elapsed partitions; necessary Arrow conversion is inside fact extraction, while digest JCS, report JCS, and artifact publication are inside publication. Rule evaluation may include record iteration and scalar decoding, so it is not a pure rule-engine cost. These 06 timings are diagnostic, not formal CT108 performance evidence.
