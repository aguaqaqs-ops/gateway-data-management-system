"""Unit tests for the W2 SQL scaler and S6 result-record schema."""

from __future__ import annotations

import pytest

from gateway_backend.synthetic_w2 import (
    SCHEMA_VERSION,
    SyntheticW2Error,
    build_scaled_replay_sql,
    classify_pk_strategy,
    parse_create_table,
    replica_integer,
    replica_varchar,
    scale_insert_rows,
    validate_replay_size,
    validate_s6_result_record,
)

pytestmark = pytest.mark.unit

_MINI_DUMP = """\
CREATE TABLE `items` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
INSERT INTO `items` VALUES (1,'alpha'),(2,'beta');
CREATE TABLE `tags` (
  `code` varchar(8) NOT NULL,
  PRIMARY KEY (`code`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
INSERT INTO `tags` VALUES ('ab');
"""


def _valid_record() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_sha": "abc",
        "synthetic": False,
        "dataset_id": "p2-r6-business-medium",
        "package_bytes": 1,
        "package_sha256": "sha256:" + "a" * 64,
        "canonicalization_manifest_digest": "sha256:" + "b" * 64,
        "settings": {
            "max_upload_bytes": 1,
            "max_decompressed_tar_stream_bytes": 1,
            "max_total_expanded_entry_bytes": 1,
            "max_replay_sql_bytes": 1,
            "record_batch_bytes": 1,
            "min_free_disk_bytes": 1,
            "import_headroom_bytes": 1,
            "max_concurrent_uploads": 8,
            "max_import_workers": 4,
            "max_concurrent_row_streams": 8,
        },
        "timings": {"upload_seconds": 0.1},
        "layers": {
            "raw_upload_bytes": 1,
            "package_bytes": 1,
            "decoded_manifest_bytes": 1,
            "decoded_replay_sql_bytes": 1,
            "record_batch_bytes_limit": 1,
            "peak_durable_root_bytes": 1,
            "peak_rss_kib": 1,
        },
        "result": "pass",
        "cleanup": {"work_root_removed": True},
    }


def test_integer_and_varchar_pk_transforms_are_deterministic() -> None:
    assert replica_integer(7, 0) == 7
    assert replica_integer(7, 2) == 7 + 2 * 1_000_000
    assert replica_varchar("ab", 0) == "ab"
    assert replica_varchar("ab", 3) == "r03_ab"
    assert classify_pk_strategy("int(11) unsigned") == "integer"
    assert classify_pk_strategy("varchar(8)") == "varchar"
    assert classify_pk_strategy("datetime") == "none"


def test_same_seed_same_sql_emits_identical_bytes() -> None:
    rows = ",".join(f"({index},'v{index}')" for index in range(1, 40))
    source = (
        "CREATE TABLE `items` (\n"
        "  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,\n"
        "  `name` varchar(32) DEFAULT NULL,\n"
        "  PRIMARY KEY (`id`)\n"
        ") ENGINE=MyISAM DEFAULT CHARSET=utf8;\n"
        f"INSERT INTO `items` VALUES {rows};\n"
        "CREATE TABLE `tags` (\n"
        "  `code` varchar(8) NOT NULL,\n"
        "  PRIMARY KEY (`code`)\n"
        ") ENGINE=MyISAM DEFAULT CHARSET=utf8;\n"
        "INSERT INTO `tags` VALUES ('ab');\n"
    )
    first, report = build_scaled_replay_sql(
        source,
        target_bytes=len(source) + 80,
        min_bytes=len(source) + 40,
        max_bytes=len(source) + 4000,
        seed="p2-r6-ext-w1-medium",
        enforce_production_band=False,
    )
    second, _ = build_scaled_replay_sql(
        source,
        target_bytes=len(source) + 80,
        min_bytes=len(source) + 40,
        max_bytes=len(source) + 4000,
        seed="p2-r6-ext-w1-medium",
        enforce_production_band=False,
    )
    assert first == second
    replicas = report["replicas_emitted"]
    scaled_tables = report["scaled_tables"]
    assert isinstance(replicas, int) and replicas >= 1
    assert isinstance(scaled_tables, list) and "items" in scaled_tables
    decoded = first.decode("utf-8")
    assert "(1000001,'v1')" in decoded
    assert decoded.count("CREATE TABLE `items`") == 1


def test_parse_create_and_scale_insert_keep_schema() -> None:
    plan = parse_create_table(
        "CREATE TABLE `items` (\n"
        "  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,\n"
        "  `name` varchar(32) DEFAULT NULL,\n"
        "  PRIMARY KEY (`id`)\n"
        ") ENGINE=MyISAM DEFAULT CHARSET=utf8"
    )
    assert plan.strategy == "integer"
    assert plan.primary_key == ("id",)
    scaled = scale_insert_rows("INSERT INTO `items` VALUES (1,'a'),(2,'b');\n", plan, 1)
    assert scaled is not None
    table, rows = scaled
    assert table == "items"
    assert rows == ["(1000001,'a')", "(1000002,'b')"]


def test_production_replay_band_rejects_small_and_over_cap() -> None:
    with pytest.raises(SyntheticW2Error, match="below the 180 MiB band"):
        validate_replay_size(100)
    with pytest.raises(SyntheticW2Error, match="hard cap"):
        validate_replay_size(200 * 1024 * 1024)


def test_result_record_rejects_forbidden_keys_and_accepts_complete_payload() -> None:
    validate_s6_result_record(_valid_record())
    forbidden = _valid_record()
    forbidden["raw_sql_bytes"] = 1
    with pytest.raises(SyntheticW2Error, match="forbidden keys"):
        validate_s6_result_record(forbidden)
    missing = _valid_record()
    del missing["layers"]
    with pytest.raises(SyntheticW2Error, match="missing keys"):
        validate_s6_result_record(missing)
