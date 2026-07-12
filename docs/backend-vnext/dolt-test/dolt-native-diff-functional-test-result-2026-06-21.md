# Dolt Native Diff Functional Test Result

## Environment
```yaml
os: Linux-6.6.114.1-microsoft-standard-WSL2-x86_64-with-glibc2.41
dolt_path: /usr/local/bin/dolt
dolt_version: dolt version 2.1.8
python_version: 3.13.2
mysql_client_available: true
run_root: /tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt
cleanup: kept for diagnostics
```

## Preflight
```yaml
has_dolt_diff: true
has_dolt_diff_json: true
has_dolt_diff_summary: true
has_dolt_diff_stat: true
has_dolt_sql_diff_function: true
summary_json_available: false
stat_json_available: true
supported_diff_commands:
  - dolt diff -r json HEAD~1 HEAD t
  - dolt diff --summary HEAD~1 HEAD t
  - dolt diff --stat -r json HEAD~1 HEAD t
  - dolt sql -r json -q "select * from dolt_diff('HEAD~1','HEAD','t')"
unsupported_diff_commands:
  - dolt diff --summary -r json HEAD~1 HEAD t (summary output remains tabular even with -r json)
before_commit: 6dro3j2og2udcdmh81c9rfr0p8dclr43
current_commit: 34l88moro8u59m0ujk9cei5fsa7sb8qo
```

## Summary
```yaml
total_cases: 18
passed: 11
failed: 0
unsupported: 2
fallback_required: 4
provider_neutral_core_cache_ok: 11
provider_local_only: 4
needs_design: 1
```

## Recommendation
```yaml
native_provider_viable_for:
  - standard PK tables
  - composite PK tables
  - table add/delete
  - ignored-column normalization
  - schema length and metadata normalization
  - scalar encoding with NULL, quotes, commas, UTF-8 and tinyint values
native_provider_not_viable_for:
  - tables without a stable identity unless a compare key is provided
  - duplicate effective keys after compare-key projection
  - primary key changes that cause Dolt to skip data diff
  - case-only rename operations because Dolt treats names case-insensitively
required_fallbacks:
  - SNAPSHOT_TABLE_COMPARE for no-identity tables and duplicate effective keys
  - fallback or degraded diagnostics when primary key sets change
  - mixed pairs containing any degraded table should stay provider-local only
required_contract_changes:
  - decide whether true table rename should be preserved as rename or flattened to delete+add
  - document that case-only table and column renames are unsupported in Dolt native diff because names are case-insensitive
  - define how metadata-only schema facts are exposed in diagnostics versus compare schema
benchmark_next_steps:
  - treat the passed cases as the first provider-neutral benchmark slice
  - route fallback cases through snapshot-based comparison and keep them out of core cache
  - add a contract test for rename semantics before benchmarking rename-heavy repositories
```

## Case Results
### T10_added_deleted
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `pr6e6usiaormaaerkreh08tlg6ivu3hv`
- current_commit: `fdqf30f1en3b8n80l3nllc9danpctvmi`
- notes:
  - table-level add and delete are both visible in summary and JSON output
- native_commands_used:
  - `dolt diff -r json pr6e6usiaormaaerkreh08tlg6ivu3hv fdqf30f1en3b8n80l3nllc9danpctvmi`
  - `dolt diff --summary pr6e6usiaormaaerkreh08tlg6ivu3hv fdqf30f1en3b8n80l3nllc9danpctvmi`
  - `dolt diff --stat -r json pr6e6usiaormaaerkreh08tlg6ivu3hv fdqf30f1en3b8n80l3nllc9danpctvmi`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T10_added_deleted/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T10_added_deleted/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T10_added_deleted/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T10_added_deleted/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T10_added_deleted/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "tables": [
    {
      "expected_raw_counts": {
        "added": 1,
        "deleted": 0,
        "modified": 0
      },
      "summary_name": "add_tbl",
      "summary_type": "added",
      "table": "add_tbl"
    },
    {
      "expected_raw_counts": {
        "added": 0,
        "deleted": 1,
        "modified": 0
      },
      "summary_name": "drop_tbl",
      "summary_type": "dropped",
      "table": "drop_tbl"
    }
  ]
}
```
- actual_canonical_result:
```json
{
  "summary": [
    {
      "data_change": true,
      "diff_type": "dropped",
      "schema_change": true,
      "table_name": "drop_tbl"
    },
    {
      "data_change": true,
      "diff_type": "added",
      "schema_change": true,
      "table_name": "add_tbl"
    }
  ],
  "tables": {
    "add_tbl": {
      "counts": {
        "added": 1,
        "deleted": 0,
        "modified": 0
      },
      "rows": [
        {
          "before": {},
          "current": {
            "id": 2,
            "v": "new"
          },
          "kind": "added"
        }
      ],
      "schema_diff": [
        "CREATE TABLE `add_tbl` (\n  `id` int NOT NULL,\n  `v` varchar(10),\n  PRIMARY KEY (`id`)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;"
      ]
    },
    "drop_tbl": {
      "counts": {
        "added": 0,
        "deleted": 1,
        "modified": 0
      },
      "rows": [
        {
          "before": {
            "id": 1,
            "v": "gone"
          },
          "current": {},
          "kind": "deleted"
        }
      ],
      "schema_diff": [
        "DROP TABLE `drop_tbl`;"
      ]
    }
  }
}
```
### T20_row_add_delete_modify
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `1psjq928397pptgi854cg0jgo935n37h`
- current_commit: `iifbl7unn6isrk9dfbr3q5mk6iqnc863`
- notes:
  - primary-key row add/delete/modify is fully canonicalizable
  - stat mismatch: expected {'rows_added': 1, 'rows_deleted': 1, 'rows_modified': 1, 'rows_unmodified': 0, 'cells_added': 2, 'cells_deleted': 2, 'cells_modified': 1}, got {'name': 'device_cfg', 'stats': {'rows_added': 1, 'rows_deleted': 1, 'rows_modified': 1, 'rows_unmodified': 1, 'cells_added': 3, 'cells_deleted': 3, 'cells_modified': 1}}
- native_commands_used:
  - `dolt diff -r json 1psjq928397pptgi854cg0jgo935n37h iifbl7unn6isrk9dfbr3q5mk6iqnc863 device_cfg`
  - `dolt diff --summary 1psjq928397pptgi854cg0jgo935n37h iifbl7unn6isrk9dfbr3q5mk6iqnc863 device_cfg`
  - `dolt diff --stat -r json 1psjq928397pptgi854cg0jgo935n37h iifbl7unn6isrk9dfbr3q5mk6iqnc863 device_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T20_row_add_delete_modify/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T20_row_add_delete_modify/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T20_row_add_delete_modify/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T20_row_add_delete_modify/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T20_row_add_delete_modify/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "changed_columns": {
    "[2]": [
      "name"
    ]
  },
  "counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "table": "device_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {
    "[2]": [
      "name"
    ]
  },
  "counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "duplicate_keys": [],
  "raw_counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "reason": null,
  "schema_diff": [],
  "supported": true
}
```
### T30_composite_pk
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `b5d44kq164u9hipqpi2ppggi6g4m0cm7`
- current_commit: `dmt0r142plpsspfr5drlj674ap7qmltb`
- notes:
  - composite primary key canonicalization uses the tuple (device_id, point_no)
  - stat mismatch: expected {'rows_added': 1, 'rows_deleted': 1, 'rows_modified': 1, 'rows_unmodified': 1, 'cells_added': 2, 'cells_deleted': 2, 'cells_modified': 1}, got {'name': 'relay_cfg', 'stats': {'rows_added': 1, 'rows_deleted': 1, 'rows_modified': 1, 'rows_unmodified': 1, 'cells_added': 3, 'cells_deleted': 3, 'cells_modified': 1}}
- native_commands_used:
  - `dolt diff -r json b5d44kq164u9hipqpi2ppggi6g4m0cm7 dmt0r142plpsspfr5drlj674ap7qmltb relay_cfg`
  - `dolt diff --summary b5d44kq164u9hipqpi2ppggi6g4m0cm7 dmt0r142plpsspfr5drlj674ap7qmltb relay_cfg`
  - `dolt diff --stat -r json b5d44kq164u9hipqpi2ppggi6g4m0cm7 dmt0r142plpsspfr5drlj674ap7qmltb relay_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T30_composite_pk/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T30_composite_pk/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T30_composite_pk/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T30_composite_pk/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T30_composite_pk/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "changed_columns": {
    "[1, 2]": [
      "value"
    ]
  },
  "counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "table": "relay_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {
    "[1, 2]": [
      "value"
    ]
  },
  "counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "duplicate_keys": [],
  "raw_counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "reason": null,
  "schema_diff": [],
  "supported": true
}
```
### T40_no_compare_key
- status: FALLBACK_REQUIRED
- canonical_equivalence: UNSUPPORTED
- cache_reuse_decision: PROVIDER_LOCAL_ONLY
- before_commit: `7kadfg9sppjfigqnasjvdff4jhj0sbsn`
- current_commit: `ggfun129b4rd8id2g888cof5tokh8012`
- notes:
  - native diff can show rows, but without a compare key there is no stable row identity for core cache
  - stat mismatch: expected {'rows_added': 2, 'rows_deleted': 2, 'rows_modified': 0, 'rows_unmodified': 0, 'cells_added': 4, 'cells_deleted': 4, 'cells_modified': 0}, got {'name': 'no_pk_cfg', 'stats': {'rows_added': 2, 'rows_deleted': 2, 'rows_modified': 0, 'rows_unmodified': 18446744073709551614, 'cells_added': 4, 'cells_deleted': 4, 'cells_modified': 0}}
- native_commands_used:
  - `dolt diff -r json 7kadfg9sppjfigqnasjvdff4jhj0sbsn ggfun129b4rd8id2g888cof5tokh8012 no_pk_cfg`
  - `dolt diff --summary 7kadfg9sppjfigqnasjvdff4jhj0sbsn ggfun129b4rd8id2g888cof5tokh8012 no_pk_cfg`
  - `dolt diff --stat -r json 7kadfg9sppjfigqnasjvdff4jhj0sbsn ggfun129b4rd8id2g888cof5tokh8012 no_pk_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_no_compare_key/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_no_compare_key/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_no_compare_key/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_no_compare_key/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_no_compare_key/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "counts": {
    "added": 2,
    "deleted": 2,
    "modified": 0
  },
  "status": "fallback_required_no_stable_identity",
  "table": "no_pk_cfg"
}
```
- actual_canonical_result:
```json
{
  "counts": {
    "added": 2,
    "deleted": 2,
    "modified": 0
  },
  "raw_counts": {
    "added": 2,
    "deleted": 2,
    "modified": 0
  },
  "reason": "no_stable_identity",
  "schema_diff": [],
  "supported": false
}
```
### T40_compare_key_name
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `1ql7g4bknuqnu9bu4s86qvtnf66nc2s1`
- current_commit: `5apsba8taflmsqqb74vcpscnc39buc2b`
- notes:
  - compare key name can canonicalize keyless raw add/delete pairs into a modified row
- native_commands_used:
  - `dolt diff -r json 1ql7g4bknuqnu9bu4s86qvtnf66nc2s1 5apsba8taflmsqqb74vcpscnc39buc2b no_pk_cfg`
  - `dolt diff --summary 1ql7g4bknuqnu9bu4s86qvtnf66nc2s1 5apsba8taflmsqqb74vcpscnc39buc2b no_pk_cfg`
  - `dolt diff --stat -r json 1ql7g4bknuqnu9bu4s86qvtnf66nc2s1 5apsba8taflmsqqb74vcpscnc39buc2b no_pk_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_compare_key_name/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_compare_key_name/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_compare_key_name/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_compare_key_name/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T40_compare_key_name/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "changed_columns": {
    "[\"a\"]": [
      "value"
    ]
  },
  "counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "table": "no_pk_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {
    "[\"a\"]": [
      "value"
    ]
  },
  "counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "raw_counts": {
    "added": 2,
    "deleted": 2,
    "modified": 0
  },
  "reason": null,
  "schema_diff": [],
  "supported": true
}
```
### T50_pk_change
- status: FALLBACK_REQUIRED
- canonical_equivalence: UNSUPPORTED
- cache_reuse_decision: PROVIDER_LOCAL_ONLY
- before_commit: `07aqfkdn43tqn9loip9b9r15l9rodjvj`
- current_commit: `oa1ai456tsshbhg4gtmashf46nr370b3`
- notes:
  - Dolt skips data diff when primary key sets differ between revisions
- native_commands_used:
  - `dolt diff -r json 07aqfkdn43tqn9loip9b9r15l9rodjvj oa1ai456tsshbhg4gtmashf46nr370b3 pk_change_cfg`
  - `dolt diff --summary 07aqfkdn43tqn9loip9b9r15l9rodjvj oa1ai456tsshbhg4gtmashf46nr370b3 pk_change_cfg`
  - `dolt diff --stat -r json 07aqfkdn43tqn9loip9b9r15l9rodjvj oa1ai456tsshbhg4gtmashf46nr370b3 pk_change_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T50_pk_change/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T50_pk_change/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T50_pk_change/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T50_pk_change/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T50_pk_change/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "schema_diff": [
    "ALTER TABLE `pk_change_cfg` DROP PRIMARY KEY;",
    "ALTER TABLE `pk_change_cfg` ADD PRIMARY KEY (code);"
  ],
  "status": "degraded_effective_key_changed",
  "table": "pk_change_cfg"
}
```
- actual_canonical_result:
```json
{
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "reason": "primary_key_change_skips_data_diff",
  "schema_diff": [
    "ALTER TABLE `pk_change_cfg` DROP PRIMARY KEY;",
    "ALTER TABLE `pk_change_cfg` ADD PRIMARY KEY (code);"
  ],
  "stderr_contains_warning": true,
  "supported": false
}
```
### T60_ignored_columns
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `m18em3jdpa14cqht45an87rt7iuvdmek`
- current_commit: `6le17pb68rqkuptrdeogqjgmom9rntt4`
- notes:
  - only the ignored column changed, so canonical comparison is unchanged
- native_commands_used:
  - `dolt diff -r json m18em3jdpa14cqht45an87rt7iuvdmek 6le17pb68rqkuptrdeogqjgmom9rntt4 ignore_col_cfg`
  - `dolt diff --summary m18em3jdpa14cqht45an87rt7iuvdmek 6le17pb68rqkuptrdeogqjgmom9rntt4 ignore_col_cfg`
  - `dolt diff --stat -r json m18em3jdpa14cqht45an87rt7iuvdmek 6le17pb68rqkuptrdeogqjgmom9rntt4 ignore_col_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T60_ignored_columns/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T60_ignored_columns/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T60_ignored_columns/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T60_ignored_columns/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T60_ignored_columns/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "projection": "updated_at ignored => business equivalent",
  "table": "ignore_col_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {},
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "duplicate_keys": [],
  "raw_counts": {
    "added": 0,
    "deleted": 0,
    "modified": 1
  },
  "reason": null,
  "schema_diff": [],
  "supported": true
}
```
### T70_type_length_only
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `vppbfjnqs5c7dpqt3klvq32aa6eujccg`
- current_commit: `sqone6kuduh0slaikgad2kb2qtksk0np`
- notes:
  - varchar length change surfaces in raw schema diff but is ignored by vNext compare schema policy
  - stat mismatch: expected {'rows_added': 0, 'rows_deleted': 0, 'rows_modified': 0, 'rows_unmodified': 1, 'cells_added': 0, 'cells_deleted': 0, 'cells_modified': 0}, got {'name': 'schema_len_cfg', 'stats': {}}
- native_commands_used:
  - `dolt diff -r json vppbfjnqs5c7dpqt3klvq32aa6eujccg sqone6kuduh0slaikgad2kb2qtksk0np schema_len_cfg`
  - `dolt diff --summary vppbfjnqs5c7dpqt3klvq32aa6eujccg sqone6kuduh0slaikgad2kb2qtksk0np schema_len_cfg`
  - `dolt diff --stat -r json vppbfjnqs5c7dpqt3klvq32aa6eujccg sqone6kuduh0slaikgad2kb2qtksk0np schema_len_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_type_length_only/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_type_length_only/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_type_length_only/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_type_length_only/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_type_length_only/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "schema_change": "length_only_ignored",
  "table": "schema_len_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {},
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "duplicate_keys": [],
  "raw_counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "reason": null,
  "schema_diff": [
    "ALTER TABLE `schema_len_cfg` MODIFY COLUMN `name` varchar(128);"
  ],
  "supported": true
}
```
### T70_meta_only_comment_engine_charset
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `2cr84hiov67b6u8rpdfkvsu6uqu2kpl2`
- current_commit: `j5e5tcmgi710sjk1pcdiv4ap1ep472mq`
- notes:
  - comment and engine-only changes were normalized away; charset/collation change is visible in raw schema diff
- native_commands_used:
  - `dolt diff -r json 2cr84hiov67b6u8rpdfkvsu6uqu2kpl2 j5e5tcmgi710sjk1pcdiv4ap1ep472mq schema_meta_cfg`
  - `dolt diff --summary 2cr84hiov67b6u8rpdfkvsu6uqu2kpl2 j5e5tcmgi710sjk1pcdiv4ap1ep472mq schema_meta_cfg`
  - `dolt diff --stat -r json 2cr84hiov67b6u8rpdfkvsu6uqu2kpl2 j5e5tcmgi710sjk1pcdiv4ap1ep472mq schema_meta_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_meta_only_comment_engine_charset/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_meta_only_comment_engine_charset/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_meta_only_comment_engine_charset/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_meta_only_comment_engine_charset/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_meta_only_comment_engine_charset/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "schema_change": "comment_engine_charset_normalized",
  "table": "schema_meta_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {},
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "duplicate_keys": [],
  "raw_counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "reason": null,
  "schema_diff": [
    "ALTER TABLE `schema_meta_cfg` COLLATE='latin1_swedish_ci';"
  ],
  "supported": true
}
```
### T70_case_only_column_name
- status: UNSUPPORTED
- canonical_equivalence: UNSUPPORTED
- cache_reuse_decision: NEEDS_DESIGN
- before_commit: `qfcb7bhfkcsej4mlp4e8jf3dh7asr4h0`
- current_commit: `None`
- failure_reason: error on line 1 for query ALTER TABLE `schema_case_col_cfg` RENAME COLUMN `name` TO `NAME`: Column "NAME" already exists
- notes:
  - error on line 1 for query ALTER TABLE `schema_case_col_cfg` RENAME COLUMN `name` TO `NAME`: Column "NAME" already exists
- native_commands_used:
  - `dolt sql < before.sql`
  - `dolt sql < current.sql`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_case_only_column_name/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_case_only_column_name/artifacts/current.sql.out`
- expected_canonical_result:
```json
{
  "status": "unsupported_case_insensitive_column_rename",
  "table": "schema_case_col_cfg"
}
```
- actual_canonical_result:
```json
{}
```
### T70_add_column
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `v2teg20kc8ejipmtvcdll76tisrk5kbo`
- current_commit: `1asrjhgm8o8gb6nd8f2f2oo6v3r664fc`
- notes:
  - schema add surfaces in raw diff, but row projection over common columns stays equal
- native_commands_used:
  - `dolt diff -r json v2teg20kc8ejipmtvcdll76tisrk5kbo 1asrjhgm8o8gb6nd8f2f2oo6v3r664fc schema_add_cfg`
  - `dolt diff --summary v2teg20kc8ejipmtvcdll76tisrk5kbo 1asrjhgm8o8gb6nd8f2f2oo6v3r664fc schema_add_cfg`
  - `dolt diff --stat -r json v2teg20kc8ejipmtvcdll76tisrk5kbo 1asrjhgm8o8gb6nd8f2f2oo6v3r664fc schema_add_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_add_column/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_add_column/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_add_column/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_add_column/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_add_column/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "schema_change": "add_column_ignored_in_row_projection",
  "table": "schema_add_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {},
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "duplicate_keys": [],
  "raw_counts": {
    "added": 0,
    "deleted": 0,
    "modified": 1
  },
  "reason": null,
  "schema_diff": [
    "ALTER TABLE `schema_add_cfg` ADD `note` varchar(64);"
  ],
  "supported": true
}
```
### T70_drop_column
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `81akftc0gmt6bnjl7imgos3b0l3el2hl`
- current_commit: `qdbk02h9ng2kfaddknmdmni61d7m3h08`
- notes:
  - schema drop surfaces in raw diff, but row projection over common columns stays equal
- native_commands_used:
  - `dolt diff -r json 81akftc0gmt6bnjl7imgos3b0l3el2hl qdbk02h9ng2kfaddknmdmni61d7m3h08 schema_drop_cfg`
  - `dolt diff --summary 81akftc0gmt6bnjl7imgos3b0l3el2hl qdbk02h9ng2kfaddknmdmni61d7m3h08 schema_drop_cfg`
  - `dolt diff --stat -r json 81akftc0gmt6bnjl7imgos3b0l3el2hl qdbk02h9ng2kfaddknmdmni61d7m3h08 schema_drop_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_drop_column/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_drop_column/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_drop_column/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_drop_column/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T70_drop_column/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "schema_change": "drop_column_ignored_in_row_projection",
  "table": "schema_drop_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {},
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "duplicate_keys": [],
  "raw_counts": {
    "added": 0,
    "deleted": 0,
    "modified": 1
  },
  "reason": null,
  "schema_diff": [
    "ALTER TABLE `schema_drop_cfg` DROP `note`;"
  ],
  "supported": true
}
```
### T80_scalar_encoding
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `6tmc3n7k5dkreq4at16n8d8mdl3v5d0d`
- current_commit: `3ctq3eeoa4d2kbe3ciaqv60a1phb8me8`
- notes:
  - NULL, empty string, comma, quote, UTF-8 Chinese and tinyint values are all preserved in JSON diff output
- native_commands_used:
  - `dolt diff -r json 6tmc3n7k5dkreq4at16n8d8mdl3v5d0d 3ctq3eeoa4d2kbe3ciaqv60a1phb8me8 scalar_cfg`
  - `dolt diff --summary 6tmc3n7k5dkreq4at16n8d8mdl3v5d0d 3ctq3eeoa4d2kbe3ciaqv60a1phb8me8 scalar_cfg`
  - `dolt diff --stat -r json 6tmc3n7k5dkreq4at16n8d8mdl3v5d0d 3ctq3eeoa4d2kbe3ciaqv60a1phb8me8 scalar_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T80_scalar_encoding/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T80_scalar_encoding/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T80_scalar_encoding/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T80_scalar_encoding/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T80_scalar_encoding/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "changed_columns": {
    "[1]": [
      "str_val",
      "tiny_val"
    ],
    "[2]": [
      "str_val",
      "num_val",
      "tiny_val",
      "note"
    ],
    "[3]": [
      "str_val",
      "note"
    ]
  },
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 3
  },
  "table": "scalar_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {
    "[1]": [
      "str_val",
      "tiny_val"
    ],
    "[2]": [
      "str_val",
      "num_val",
      "tiny_val",
      "note"
    ],
    "[3]": [
      "str_val",
      "note"
    ]
  },
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 3
  },
  "duplicate_keys": [],
  "raw_counts": {
    "added": 0,
    "deleted": 0,
    "modified": 3
  },
  "reason": null,
  "schema_diff": [],
  "supported": true
}
```
### T90_duplicate_effective_key_after_projection
- status: FALLBACK_REQUIRED
- canonical_equivalence: UNSUPPORTED
- cache_reuse_decision: PROVIDER_LOCAL_ONLY
- before_commit: `lrnm0rdh1dqb8g7vsq7nq8v5gfcma4vg`
- current_commit: `co3tg7o89gt8flp9d2b06pc23dc2huih`
- notes:
  - compare key name becomes duplicated after projection, so the table must degrade
  - canonical diff not supported: duplicate_identity
- native_commands_used:
  - `dolt diff -r json lrnm0rdh1dqb8g7vsq7nq8v5gfcma4vg co3tg7o89gt8flp9d2b06pc23dc2huih dup_key_cfg`
  - `dolt diff --summary lrnm0rdh1dqb8g7vsq7nq8v5gfcma4vg co3tg7o89gt8flp9d2b06pc23dc2huih dup_key_cfg`
  - `dolt diff --stat -r json lrnm0rdh1dqb8g7vsq7nq8v5gfcma4vg co3tg7o89gt8flp9d2b06pc23dc2huih dup_key_cfg`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T90_duplicate_effective_key_after_projection/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T90_duplicate_effective_key_after_projection/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T90_duplicate_effective_key_after_projection/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T90_duplicate_effective_key_after_projection/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T90_duplicate_effective_key_after_projection/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "status": "duplicate_effective_key_after_projection",
  "table": "dup_key_cfg"
}
```
- actual_canonical_result:
```json
{
  "changed_columns": {},
  "counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "duplicate_keys": [
    [
      "alpha"
    ]
  ],
  "raw_counts": {
    "added": 0,
    "deleted": 0,
    "modified": 1
  },
  "reason": "duplicate_identity",
  "schema_diff": [],
  "supported": false
}
```
### T100_case_only_table_rename
- status: UNSUPPORTED
- canonical_equivalence: UNSUPPORTED
- cache_reuse_decision: NEEDS_DESIGN
- before_commit: `48ikr73rval5hcti93bl0if1iu7led2r`
- current_commit: `None`
- failure_reason: error on line 1 for query RENAME TABLE `case_rename_tbl` TO `CASE_RENAME_TBL`: table with name CASE_RENAME_TBL already exists
- notes:
  - error on line 1 for query RENAME TABLE `case_rename_tbl` TO `CASE_RENAME_TBL`: table with name CASE_RENAME_TBL already exists
- native_commands_used:
  - `dolt sql < before.sql`
  - `dolt sql < current.sql`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T100_case_only_table_rename/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T100_case_only_table_rename/artifacts/current.sql.out`
- expected_canonical_result:
```json
{
  "status": "case_only_table_rename_rejected",
  "table": "case_rename_tbl"
}
```
- actual_canonical_result:
```json
{}
```
### T100_true_table_rename
- status: NEEDS_DESIGN
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: NEEDS_DESIGN
- before_commit: `vcf9fdpi3sa03gej3abq2sajqno0m2d4`
- current_commit: `0lqgn05fihtd4k5t3gm01609pqg0db8q`
- notes:
  - native diff exposes an explicit rename, but the vNext business rule still needs a contract decision
- native_commands_used:
  - `dolt diff -r json vcf9fdpi3sa03gej3abq2sajqno0m2d4 0lqgn05fihtd4k5t3gm01609pqg0db8q`
  - `dolt diff --summary vcf9fdpi3sa03gej3abq2sajqno0m2d4 0lqgn05fihtd4k5t3gm01609pqg0db8q`
  - `dolt diff --stat -r json vcf9fdpi3sa03gej3abq2sajqno0m2d4 0lqgn05fihtd4k5t3gm01609pqg0db8q`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T100_true_table_rename/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T100_true_table_rename/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T100_true_table_rename/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T100_true_table_rename/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T100_true_table_rename/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "rename": "rename_me -> renamed_me",
  "table": "rename_me"
}
```
- actual_canonical_result:
```json
{
  "raw_counts": {
    "added": 0,
    "deleted": 0,
    "modified": 0
  },
  "schema_diff": [
    "RENAME TABLE `rename_me` TO `renamed_me`;"
  ],
  "summary": {
    "data_change": false,
    "diff_type": "renamed",
    "schema_change": true,
    "table_name": "rename_me -> renamed_me"
  }
}
```
### T110_ordering_and_digest
- status: PASSED
- canonical_equivalence: NORMALIZED_EQUIVALENT
- cache_reuse_decision: PROVIDER_NEUTRAL_CORE_CACHE_OK
- before_commit: `1t80uvmle333nvkbn1tclb4ijlenlqjo`
- current_commit: `77dnilkrnb12jlukgqhsrs6csiuqr3o7`
- notes:
  - the diff output is deterministic across repeated runs in this environment, so no order-only divergence was observed
- native_commands_used:
  - `dolt diff -r json 1t80uvmle333nvkbn1tclb4ijlenlqjo 77dnilkrnb12jlukgqhsrs6csiuqr3o7 order_probe`
  - `dolt diff --summary 1t80uvmle333nvkbn1tclb4ijlenlqjo 77dnilkrnb12jlukgqhsrs6csiuqr3o7 order_probe`
  - `dolt diff --stat -r json 1t80uvmle333nvkbn1tclb4ijlenlqjo 77dnilkrnb12jlukgqhsrs6csiuqr3o7 order_probe`
  - `dolt diff -r json 1t80uvmle333nvkbn1tclb4ijlenlqjo 77dnilkrnb12jlukgqhsrs6csiuqr3o7 order_probe (second run)`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T110_ordering_and_digest/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T110_ordering_and_digest/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T110_ordering_and_digest/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T110_ordering_and_digest/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T110_ordering_and_digest/artifacts/stat.json.out`
  - diff_second_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T110_ordering_and_digest/artifacts/diff-second.json.out`
- expected_canonical_result:
```json
{
  "changed_columns": {
    "[10]": [
      "label"
    ]
  },
  "counts": {
    "added": 1,
    "deleted": 1,
    "modified": 1
  },
  "digest_stable_across_two_runs": true,
  "table": "order_probe"
}
```
- actual_canonical_result:
```json
{
  "digest_equal": true,
  "first_run": {
    "canonical": {
      "added_keys": [
        [
          25
        ]
      ],
      "changed_columns": {
        "[10]": [
          "label"
        ]
      },
      "counts": {
        "added": 1,
        "deleted": 1,
        "modified": 1
      },
      "deleted_keys": [
        [
          20
        ]
      ],
      "duplicate_keys": [],
      "modified_keys": [
        [
          10
        ]
      ],
      "reason": null,
      "supported": true
    },
    "digest": "68cceff38ac025d98b4bed2306199c9949f3a97aa4b5ced34a5c0dd2bd48a747",
    "raw_counts": {
      "added": 1,
      "deleted": 1,
      "modified": 1
    },
    "schema_diff": []
  },
  "second_run": {
    "canonical": {
      "added_keys": [
        [
          25
        ]
      ],
      "changed_columns": {
        "[10]": [
          "label"
        ]
      },
      "counts": {
        "added": 1,
        "deleted": 1,
        "modified": 1
      },
      "deleted_keys": [
        [
          20
        ]
      ],
      "duplicate_keys": [],
      "modified_keys": [
        [
          10
        ]
      ],
      "reason": null,
      "supported": true
    },
    "digest": "68cceff38ac025d98b4bed2306199c9949f3a97aa4b5ced34a5c0dd2bd48a747",
    "raw_counts": {
      "added": 1,
      "deleted": 1,
      "modified": 1
    },
    "schema_diff": []
  }
}
```
### T120_small_multi_table_pair
- status: FALLBACK_REQUIRED
- canonical_equivalence: UNSUPPORTED
- cache_reuse_decision: PROVIDER_LOCAL_ONLY
- before_commit: `1pgl0435jjvg6664erdhfper66tefnat`
- current_commit: `36qtupjj2utfc9qgq98rfcgklq91l4ui`
- notes:
  - mixed pair shows that one degraded table does not block canonical facts for the other tables, but the pair as a whole still needs fallback
- native_commands_used:
  - `dolt diff -r json 1pgl0435jjvg6664erdhfper66tefnat 36qtupjj2utfc9qgq98rfcgklq91l4ui`
  - `dolt diff --summary 1pgl0435jjvg6664erdhfper66tefnat 36qtupjj2utfc9qgq98rfcgklq91l4ui`
  - `dolt diff --stat -r json 1pgl0435jjvg6664erdhfper66tefnat 36qtupjj2utfc9qgq98rfcgklq91l4ui`
- native_output_artifacts:
  - before_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T120_small_multi_table_pair/artifacts/before.sql.out`
  - current_sql_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T120_small_multi_table_pair/artifacts/current.sql.out`
  - diff_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T120_small_multi_table_pair/artifacts/diff.json.out`
  - summary_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T120_small_multi_table_pair/artifacts/summary.out`
  - stat_json_out: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/cases/T120_small_multi_table_pair/artifacts/stat.json.out`
- expected_canonical_result:
```json
{
  "tables": {
    "add_tbl": {
      "counts": {
        "added": 1,
        "deleted": 0,
        "modified": 0
      }
    },
    "degraded_tbl": {
      "status": "fallback_required_no_stable_identity"
    },
    "drop_tbl": {
      "counts": {
        "added": 0,
        "deleted": 1,
        "modified": 0
      }
    },
    "ignore_tbl": {
      "counts": {
        "added": 0,
        "deleted": 0,
        "modified": 0
      },
      "status": "business_equivalent_under_projection"
    },
    "mod_tbl": {
      "counts": {
        "added": 0,
        "deleted": 0,
        "modified": 1
      }
    }
  }
}
```
- actual_canonical_result:
```json
{
  "summary": [
    {
      "data_change": true,
      "diff_type": "dropped",
      "schema_change": true,
      "table_name": "drop_tbl"
    },
    {
      "data_change": true,
      "diff_type": "added",
      "schema_change": true,
      "table_name": "add_tbl"
    },
    {
      "data_change": true,
      "diff_type": "modified",
      "schema_change": false,
      "table_name": "degraded_tbl"
    },
    {
      "data_change": true,
      "diff_type": "modified",
      "schema_change": false,
      "table_name": "ignore_tbl"
    },
    {
      "data_change": true,
      "diff_type": "modified",
      "schema_change": false,
      "table_name": "mod_tbl"
    }
  ],
  "tables": {
    "add_tbl": {
      "cache_reuse_decision": "PROVIDER_NEUTRAL_CORE_CACHE_OK",
      "canonical": {
        "added_keys": [
          [
            1
          ]
        ],
        "changed_columns": {},
        "counts": {
          "added": 1,
          "deleted": 0,
          "modified": 0
        },
        "deleted_keys": [],
        "duplicate_keys": [],
        "modified_keys": [],
        "reason": null,
        "supported": true
      },
      "canonical_equivalence": "NORMALIZED_EQUIVALENT",
      "raw_counts": {
        "added": 1,
        "deleted": 0,
        "modified": 0
      },
      "schema_diff": [
        "CREATE TABLE `add_tbl` (\n  `id` int NOT NULL,\n  `v` varchar(10),\n  PRIMARY KEY (`id`)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;"
      ],
      "status": "PASSED",
      "summary": {
        "data_change": true,
        "diff_type": "added",
        "schema_change": true,
        "table_name": "add_tbl"
      }
    },
    "degraded_tbl": {
      "cache_reuse_decision": "PROVIDER_LOCAL_ONLY",
      "canonical": {
        "changed_columns": {},
        "counts": {
          "added": 1,
          "deleted": 1,
          "modified": 0
        },
        "duplicate_keys": [],
        "reason": "no_stable_identity",
        "supported": false
      },
      "canonical_equivalence": "UNSUPPORTED",
      "raw_counts": {
        "added": 1,
        "deleted": 1,
        "modified": 0
      },
      "schema_diff": [],
      "status": "FALLBACK_REQUIRED",
      "summary": {
        "data_change": true,
        "diff_type": "modified",
        "schema_change": false,
        "table_name": "degraded_tbl"
      }
    },
    "drop_tbl": {
      "cache_reuse_decision": "PROVIDER_NEUTRAL_CORE_CACHE_OK",
      "canonical": {
        "added_keys": [],
        "changed_columns": {},
        "counts": {
          "added": 0,
          "deleted": 1,
          "modified": 0
        },
        "deleted_keys": [
          [
            1
          ]
        ],
        "duplicate_keys": [],
        "modified_keys": [],
        "reason": null,
        "supported": true
      },
      "canonical_equivalence": "NORMALIZED_EQUIVALENT",
      "raw_counts": {
        "added": 0,
        "deleted": 1,
        "modified": 0
      },
      "schema_diff": [
        "DROP TABLE `drop_tbl`;"
      ],
      "status": "PASSED",
      "summary": {
        "data_change": true,
        "diff_type": "dropped",
        "schema_change": true,
        "table_name": "drop_tbl"
      }
    },
    "ignore_tbl": {
      "cache_reuse_decision": "PROVIDER_NEUTRAL_CORE_CACHE_OK",
      "canonical": {
        "added_keys": [],
        "changed_columns": {},
        "counts": {
          "added": 0,
          "deleted": 0,
          "modified": 0
        },
        "deleted_keys": [],
        "duplicate_keys": [],
        "modified_keys": [],
        "reason": null,
        "supported": true
      },
      "canonical_equivalence": "NORMALIZED_EQUIVALENT",
      "raw_counts": {
        "added": 0,
        "deleted": 0,
        "modified": 1
      },
      "schema_diff": [],
      "status": "PASSED",
      "summary": {
        "data_change": true,
        "diff_type": "modified",
        "schema_change": false,
        "table_name": "ignore_tbl"
      }
    },
    "mod_tbl": {
      "cache_reuse_decision": "PROVIDER_NEUTRAL_CORE_CACHE_OK",
      "canonical": {
        "added_keys": [],
        "changed_columns": {
          "[1]": [
            "name"
          ]
        },
        "counts": {
          "added": 0,
          "deleted": 0,
          "modified": 1
        },
        "deleted_keys": [],
        "duplicate_keys": [],
        "modified_keys": [
          [
            1
          ]
        ],
        "reason": null,
        "supported": true
      },
      "canonical_equivalence": "NORMALIZED_EQUIVALENT",
      "raw_counts": {
        "added": 0,
        "deleted": 0,
        "modified": 1
      },
      "schema_diff": [],
      "status": "PASSED",
      "summary": {
        "data_change": true,
        "diff_type": "modified",
        "schema_change": false,
        "table_name": "mod_tbl"
      }
    }
  }
}
```

## Artifacts
- run_root: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt`
- summary_json: `/tmp/dolt-native-diff-functional-test-linux-x86_64-880916-c875j4qt/summary.json`
- cleanup: kept for diagnostics
