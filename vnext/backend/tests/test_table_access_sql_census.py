"""Coverage map from the G2 dump census to native SQL tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gateway_shared_kernel import SignedIntegerScalar
from gateway_backend.capabilities.table_access.contracts import ParseStatus
from tests.support.table_access_sql import parse_text


_CENSUS_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "backend-vnext"
    / "refactoring"
    / "formal"
    / "plans"
    / "p5-arch-closure-s1-census.json"
)

# The type spellings come from datasets[*].storage_column_type_counts and
# datasets[*].version_manager_saved_time_type in the G2-updated census JSON.
# Each owner is a parameter in the existing native type test.
G2_CENSUS_FORMAT_COVERAGE = (
    ("SQL type DATETIME", "test_sql_parser_type_descriptors_match_the_type_mapper[DATETIME]"),
    ("SQL type ENUM", "test_sql_parser_type_descriptors_match_the_type_mapper[ENUM('a','b')]"),
    ("SQL type FLOAT", "test_sql_parser_type_descriptors_match_the_type_mapper[FLOAT]"),
    ("SQL type INT", "test_sql_parser_type_descriptors_match_the_type_mapper[INT]"),
    (
        "SQL type INT UNSIGNED",
        "test_sql_parser_type_descriptors_match_the_type_mapper[INT UNSIGNED]",
    ),
    ("SQL type SET", "test_sql_parser_type_descriptors_match_the_type_mapper[SET('x','y')]"),
    (
        "SQL type SMALLINT UNSIGNED",
        "test_sql_parser_type_descriptors_match_the_type_mapper[SMALLINT UNSIGNED]",
    ),
    ("SQL type TEXT", "test_sql_parser_type_descriptors_match_the_type_mapper[TEXT]"),
    ("SQL type TINYINT", "test_sql_parser_type_descriptors_match_the_type_mapper[TINYINT]"),
    (
        "SQL type TINYINT UNSIGNED",
        "test_sql_parser_type_descriptors_match_the_type_mapper[TINYINT UNSIGNED]",
    ),
    ("SQL type VARCHAR", "test_sql_parser_type_descriptors_match_the_type_mapper[VARCHAR(16)]"),
    (
        "SQL type VARCHAR(128)",
        "test_sql_parser_type_descriptors_match_the_type_mapper[VARCHAR(128)]",
    ),
    (
        "G2 accepted conditional SET @saved_cs_client",
        "test_mysqldump_session_setup_statements_are_accepted",
    ),
    (
        "G2 rd-t3-c-v1 retained an unsupported bare SET statement",
        "test_unsupported_statements_fail_document",
    ),
    (
        "mysqldump SET/DROP/CREATE/LOCK/ALTER KEYS/INSERT/UNLOCK boilerplate",
        "test_sql_golden_parser_matches_expected[sql/valid/s2-dump-boilerplate]",
    ),
)

# V6 report §7 lists statement-boundary forms absent from the aggregate G2 JSON.
# This format had no direct Layer ① case, so keep one small synthetic row here.
SYNTHETIC_FORMAT_CASES = (
    (
        "line/block comments, conditional comment, and CRLF between statements",
        "/* dump header */\r\n"
        "CREATE TABLE `commented` (`id` INT NOT NULL PRIMARY KEY);\r\n"
        "-- mysqldump boundary\r\n"
        "/*!40101 SET NAMES utf8mb4 */;\r\n"
        "# before rows\n"
        "INSERT INTO `commented` (`id`) VALUES (7);\r\n",
    ),
)


def test_g2_census_format_categories_have_native_owners() -> None:
    census = json.loads(_CENSUS_PATH.read_text(encoding="utf-8"))
    observed_types = {
        sql_type
        for dataset in census["datasets"]
        for sql_type in dataset["storage_column_type_counts"]
    }
    observed_types.update(
        dataset["version_manager_saved_time_type"]
        for dataset in census["datasets"]
        if dataset["version_manager_saved_time_type"] is not None
    )
    mapped_types = {
        category.removeprefix("SQL type ")
        for category, _test_owner in G2_CENSUS_FORMAT_COVERAGE
        if category.startswith("SQL type ")
    }
    categories = [category for category, _test_owner in G2_CENSUS_FORMAT_COVERAGE]

    assert census["contains_row_data"] is False
    assert observed_types == mapped_types
    assert len(categories) == len(set(categories))
    assert all(owner for _category, owner in G2_CENSUS_FORMAT_COVERAGE)
    assert not any(dataset["json_columns"] for dataset in census["datasets"])
    assert census["dc15_unknown_sql_types"] == []


@pytest.mark.parametrize(
    ("category", "sql"),
    SYNTHETIC_FORMAT_CASES,
    ids=[case[0] for case in SYNTHETIC_FORMAT_CASES],
)
def test_synthetic_census_format_sample_keeps_known_row(category: str, sql: str) -> None:
    assert category
    result = parse_text(sql)
    assert result.status is ParseStatus.COMPLETE
    assert result.diagnostics == ()
    assert result.tables[0].descriptor.canonical_name == "commented"
    assert result.tables[0].reader is not None
    assert tuple(result.tables[0].reader.iter_rows()) == ((SignedIntegerScalar("7"),),)
