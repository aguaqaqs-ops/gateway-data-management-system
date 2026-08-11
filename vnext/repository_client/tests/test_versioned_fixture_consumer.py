"""Unit tests for Versioned fixture consumer support."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from support.versioned_fixture_consumer import (
    canonical_row_set,
    load_expected_facts,
    load_fixture_bundle,
    package_digest,
    parse_expected_facts,
    row_primary_key_tuple,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "versioned_v1"
SUPPORT_ROOT = Path(__file__).resolve().parent / "support"


def test_parse_expected_facts_rejects_extra_top_level_key() -> None:
    with pytest.raises(ValueError, match="unexpected keys"):
        parse_expected_facts({"catalog": {"tables": {}}, "rows": {}, "commit_id": "x"})


def test_parse_expected_facts_rejects_invalid_row_count() -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                    "row_count": -1,
                }
            }
        },
        "rows": {},
    }
    with pytest.raises(ValueError, match="row_count"):
        parse_expected_facts(payload)


def test_load_expected_facts_is_deterministic(tmp_path: Path) -> None:
    payload = {
        "catalog": {
            "tables": {
                "items": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
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


def test_c1_c2_expected_catalog_differ() -> None:
    c1 = load_fixture_bundle(FIXTURE_ROOT, "c1")
    c2 = load_fixture_bundle(FIXTURE_ROOT, "c2")
    assert set(c1.expected.catalog) == {"fixture_items"}
    assert set(c2.expected.catalog) == {"fixture_items", "fixture_meta"}
    assert c1.expected.catalog["fixture_items"].row_count == 1
    assert c2.expected.catalog["fixture_items"].row_count == 2


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
