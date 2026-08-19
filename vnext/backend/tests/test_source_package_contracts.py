"""SourcePackage public contract tests. Does not parse SQL or XML."""

from __future__ import annotations

from dataclasses import fields

import pytest
from gateway_backend.capabilities.source_package_staging.contracts import (
    RESOURCE_BUDGETS,
    SOURCE_PACKAGE_CONTRACT_VERSION,
    NeverCancel,
    PackageKind,
    SourcePackageInput,
    StagingInvocationContext,
    StagingStatus,
    StagingTransport,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import CacheTrustLevel

_MIB = 1024 * 1024
_KIB = 1024
_CONTEXT = StagingInvocationContext(NeverCancel())

EXPECTED_RESOURCE_BUDGETS = (
    ("max_source_package_compressed_bytes", 256 * _MIB),
    ("max_source_package_expanded_bytes", 1024 * _MIB),
    ("max_source_package_entries", 8192),
    ("max_normalized_path_bytes", 1024),
    ("max_path_segments", 32),
    ("max_sql_document_bytes", 512 * _MIB),
    ("max_xml_document_bytes", 64 * _MIB),
    ("max_diagnostics", 1024),
    ("max_diagnostic_message_bytes", 4 * _KIB),
)

FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "host_path",
        "snapshot_id",
        "snapshot_digest",
        "cache_key",
    }
)


def test_versions_and_budgets_match_s0() -> None:
    assert SOURCE_PACKAGE_CONTRACT_VERSION == 1
    for name, expected in EXPECTED_RESOURCE_BUDGETS:
        assert getattr(RESOURCE_BUDGETS, name) == expected, name


def test_tar_zst_is_not_a_package_kind() -> None:
    assert "TAR_ZST" not in PackageKind.__members__
    assert "PARTIAL" not in StagingStatus.__members__


def test_source_package_input_has_no_forbidden_fields() -> None:
    names = {item.name for item in fields(SourcePackageInput)}
    assert names.isdisjoint(FORBIDDEN_FIELD_NAMES)


def test_trust_levels_remain_orthogonal_to_staging() -> None:
    assert CacheTrustLevel.CONTENT_VERIFIED.value == "CONTENT_VERIFIED"
    assert StagingStatus.FAILED.value == "FAILED"


def test_directory_rejects_payload_bytes() -> None:
    with pytest.raises(ValueError, match="DIRECTORY forbids payload bytes"):
        SourcePackageInput(
            package_kind=PackageKind.DIRECTORY,
            transport=StagingTransport.IDENTITY,
            context=_CONTEXT,
            payload=b"x",
            directory_entries=(("sql/dbcfg.sql", b"x"),),
        )


def test_tar_gz_requires_payload_bytes() -> None:
    with pytest.raises(ValueError, match="payload must be bytes"):
        SourcePackageInput(
            package_kind=PackageKind.TAR_GZ,
            transport=StagingTransport.IDENTITY,
            context=_CONTEXT,
            payload=None,
        )
