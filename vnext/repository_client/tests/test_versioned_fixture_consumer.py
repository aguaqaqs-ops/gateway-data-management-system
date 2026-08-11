"""Unit tests for Versioned fixture consumer support."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.ipc as pa_ipc  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy, VerificationPolicy, VersionedImportResult
from support.versioned_fixture_consumer import (
    ExpectedTableRows,
    assert_import_result_identity,
    assert_rows_match,
    canonical_row_set,
    decode_arrow_stream,
    load_expected_facts,
    load_fixture_bundle,
    package_digest,
    parse_expected_facts,
    row_primary_key_tuple,
)

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "versioned_v1"
SUPPORT_ROOT = Path(__file__).resolve().parent / "support"

_ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")


def _minimal_expected_payload(*, row_count: object = 0) -> dict[str, object]:
    return {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                    "row_count": row_count,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": ["id"],
                "records": [],
            }
        },
    }


def test_parse_expected_facts_rejects_extra_top_level_key() -> None:
    with pytest.raises(ValueError, match="unexpected keys"):
        parse_expected_facts({"catalog": {"tables": {}}, "rows": {}, "commit_id": "x"})


def test_parse_expected_facts_rejects_invalid_row_count() -> None:
    payload = _minimal_expected_payload(row_count=-1)
    with pytest.raises(ValueError, match="row_count"):
        parse_expected_facts(payload)


@pytest.mark.parametrize("row_count", [True, 1.0, "1"])
def test_parse_expected_facts_rejects_non_integer_row_count(row_count: object) -> None:
    payload = _minimal_expected_payload(row_count=row_count)
    with pytest.raises(ValueError, match="row_count"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_catalog_rows_table_mismatch() -> None:
    payload = {
        "catalog": {
            "tables": {
                "a": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                    "row_count": 0,
                }
            }
        },
        "rows": {
            "b": {
                "primary_key": ["id"],
                "records": [],
            }
        },
    }
    with pytest.raises(ValueError, match="same table set"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_empty_primary_key() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": [],
                    "row_count": 0,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": [],
                "records": [],
            }
        },
    }
    with pytest.raises(ValueError, match="primary_key must not be empty"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_duplicate_column_names() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [
                        {"name": "id", "sql_type": "INT", "nullable": False},
                        {"name": "id", "sql_type": "BIGINT", "nullable": False},
                    ],
                    "primary_key": ["id"],
                    "row_count": 0,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": ["id"],
                "records": [],
            }
        },
    }
    with pytest.raises(ValueError, match="duplicate names"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_duplicate_primary_key_columns() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id", "id"],
                    "row_count": 0,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": ["id", "id"],
                "records": [],
            }
        },
    }
    with pytest.raises(ValueError, match="duplicate column names"):
        parse_expected_facts(payload)


def test_parse_expected_facts_rejects_duplicate_record_primary_keys() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                    "row_count": 2,
                }
            }
        },
        "rows": {
            "items": {
                "primary_key": ["id"],
                "records": [
                    {"id": 1},
                    {"id": 1},
                ],
            }
        },
    }
    with pytest.raises(ValueError, match="duplicate primary keys"):
        parse_expected_facts(payload)


def test_load_expected_facts_is_deterministic(tmp_path: Path) -> None:
    payload = _minimal_expected_payload()
    path = tmp_path / "expected.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    first = load_expected_facts(path)
    second = load_expected_facts(path)
    assert first == second


def test_fixture_material_exists_and_package_digest_is_stable() -> None:
    for label in ("c1", "c2"):
        bundle = load_fixture_bundle(FIXTURE_ROOT, label)
        assert bundle.package_bytes
        first = package_digest(bundle.package_bytes)
        second = package_digest(bundle.package_bytes)
        assert first == second
        assert first[0] > 0
        assert len(first[1]) == 64


def test_canonical_row_set_is_order_independent() -> None:
    records_a = (
        {"id": 2, "label": "b"},
        {"id": 1, "label": "a"},
    )
    records_b = (
        {"id": 1, "label": "a"},
        {"id": 2, "label": "b"},
    )
    primary_key = ("id",)
    assert canonical_row_set(records_a, primary_key=primary_key) == canonical_row_set(
        records_b,
        primary_key=primary_key,
    )
    assert row_primary_key_tuple(records_a[0], primary_key) == (2,)


def test_assert_rows_match_rejects_duplicate_primary_keys() -> None:
    expected = ExpectedTableRows(
        primary_key=("id",),
        records=(
            {"id": 1, "label": "alpha"},
            {"id": 2, "label": "beta"},
        ),
    )
    actual = [
        {"id": 1, "label": "alpha"},
        {"id": 1, "label": "alpha"},
    ]
    with pytest.raises(AssertionError, match="duplicate primary keys"):
        assert_rows_match(actual, expected, table_name="items")


def test_c1_c2_expected_catalog_differ() -> None:
    c1 = load_fixture_bundle(FIXTURE_ROOT, "c1")
    c2 = load_fixture_bundle(FIXTURE_ROOT, "c2")
    assert set(c1.expected.catalog) == {"fixture_items"}
    assert set(c2.expected.catalog) == {"fixture_items", "fixture_meta"}
    assert c1.expected.catalog["fixture_items"].row_count == 1
    assert c2.expected.catalog["fixture_items"].row_count == 2


def test_assert_import_result_identity_rejects_drift() -> None:
    result = VersionedImportResult(
        commit_id="commit-c1",
        target_ref="main",
        artifact_id=_ARTIFACT_ID,
        canonicalization_manifest_digest="digest",
        expected_commit_id="commit-c0",
        completed_verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    with pytest.raises(AssertionError, match="expected_commit_id"):
        assert_import_result_identity(
            result,
            expected_commit_id="commit-wrong",
            artifact_id=_ARTIFACT_ID,
        )


@pytest.mark.parametrize(
    ("policy_field", "policy_value"),
    [
        ("completed_verification_policy", VerificationPolicy.FULL_SCAN),
        ("unknown_type_policy", UnknownTypePolicy.STRINGIFY),
    ],
)
def test_assert_import_result_identity_rejects_policy_drift(
    policy_field: str,
    policy_value: VerificationPolicy | UnknownTypePolicy,
) -> None:
    result = VersionedImportResult(
        commit_id="commit-c1",
        target_ref="main",
        artifact_id=_ARTIFACT_ID,
        canonicalization_manifest_digest="digest",
        expected_commit_id="commit-c0",
        completed_verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    drifted = result.model_copy(update={policy_field: policy_value})
    with pytest.raises(AssertionError, match=policy_field):
        assert_import_result_identity(
            drifted,
            expected_commit_id="commit-c0",
            artifact_id=_ARTIFACT_ID,
        )


def test_decode_arrow_stream_rejects_truncated_body() -> None:
    table = pa.table({"id": [1]})
    sink = pa.BufferOutputStream()
    with pa_ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    truncated = sink.getvalue().to_pybytes()[:16]
    with pytest.raises((pa.ArrowInvalid, OSError, EOFError, ValueError)):
        decode_arrow_stream(truncated)


def test_support_modules_do_not_import_service() -> None:
    banned = "gateway_repository_service"
    offenders: list[str] = []
    for path in sorted(SUPPORT_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == banned:
                        offenders.append(f"{path.name}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.split(".")[0] == banned:
                    offenders.append(f"{path.name}:{node.module}")
    assert offenders == []
