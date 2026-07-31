"""Schema asset snapshot and packaging tests."""

from __future__ import annotations

import hashlib
import json
import zipfile
from importlib import resources
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from gateway_repository_contracts.wire import schema_files_in_source_tree, schema_resource_names

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCHEMA_DIR = PACKAGE_ROOT / "src" / "gateway_repository_contracts" / "schemas"

SCHEMA_GOLDEN_SHA256: dict[str, str] = {
    "identities-v1.schema.json": (
        "7751ae3be5ef901a402ae6cadf5556c75703dec304a17c036588b85c1368ef5c"
    ),
    "problem-v1.schema.json": ("34c9e1a420539efc586e546c9ea5f730fd1b8e93815d51a2d938b75a1777cd6c"),
    "stream-metadata-v1.schema.json": (
        "34de986ff7c2c635ea33d602ff1fb092f41bca182627d3f1bfcaf4714fd34550"
    ),
    "stream-envelope-v1.schema.json": (
        "972aba17d34301592d2ff7e07b69c6f225fa96946b16c7793899706c5d7a2e38"
    ),
    "stream-framing-v1.schema.json": (
        "f3777807f6c570d6c12efae485699ee2ad80339cea1bd3cf3525033d6f9b854b"
    ),
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("name", schema_resource_names())
def test_schema_raw_bytes_are_stable(name: str) -> None:
    raw = (SOURCE_SCHEMA_DIR / name).read_bytes()
    digest = _sha256_bytes(raw)
    assert digest == SCHEMA_GOLDEN_SHA256[name]
    Draft202012Validator.check_schema(json.loads(raw.decode("utf-8")))


def test_source_tree_schema_paths_match_inventory() -> None:
    inventory = schema_files_in_source_tree(PACKAGE_ROOT)
    assert set(inventory) == set(schema_resource_names())
    for path in inventory.values():
        assert path.is_file()


def test_installed_resources_match_source_tree() -> None:
    for name in schema_resource_names():
        source = (SOURCE_SCHEMA_DIR / name).read_bytes()
        installed = (
            resources.files("gateway_repository_contracts").joinpath("schemas", name).read_bytes()
        )
        assert source == installed


def test_built_wheel_contains_only_schema_assets(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    import subprocess

    subprocess.run(
        ["uv", "build", "--offline", "--out-dir", str(dist_dir)],
        cwd=PACKAGE_ROOT,
        check=True,
    )
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        schema_entries = [name for name in names if "/schemas/" in name and name.endswith(".json")]
        assert {Path(name).name for name in schema_entries} == set(schema_resource_names())
        forbidden = [name for name in names if "/tests/" in name or "__pycache__" in name]
        assert forbidden == []
