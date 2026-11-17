"""Strict document decoding and Arrow boundary tests for L2."""

from __future__ import annotations

import copy
from typing import Any

import pyarrow as pa
import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.comparison.contracts import ComparisonStorageFacts
from gateway_backend.capabilities.comparison.documents import (
    storage_facts_from_documents,
    storage_facts_to_documents,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    DegradedReason,
    DiagnosticSeverity,
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    MaterializationStage,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.snapshot_materialization.documents import (
    snapshot_descriptor_from_document,
    snapshot_descriptor_to_document,
)
from gateway_backend.capabilities.snapshot_materialization.native import (
    _convert_catalog_from_arrow_result,
)
from gateway_backend.capabilities.table_access.contracts import NeverCancel
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    StorageRuleView,
)

pytestmark = pytest.mark.unit

_DIGEST_A = raw_blob_digest(b"a")
_DIGEST_B = raw_blob_digest(b"b")
_DIGEST_C = raw_blob_digest(b"c")


def _sample_descriptor() -> SnapshotTableDescriptor:
    return SnapshotTableDescriptor(
        table_name="device_st",
        display_table_name="device_st",
        columns=(
            SnapshotColumnDescriptor(
                name="gid",
                display_name="gid",
                nullable=False,
                scalar_type="BIGINT",
            ),
            SnapshotColumnDescriptor(
                name="label",
                display_name="label",
                nullable=True,
                scalar_type=None,
            ),
        ),
        primary_key_columns=("gid",),
        compare_key_columns=("gid",),
        row_count=3,
        materialization_stage=MaterializationStage.FINAL,
        compare_schema_digest=_DIGEST_A,
        table_ruleset_version=2,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        raw_content_digest=_DIGEST_B,
        degraded_reason=DegradedReason.KEYLESS,
        diagnostics=(
            MaterializationDiagnostic(
                code=MaterializationDiagnosticCode.DUPLICATE_EFFECTIVE_KEY,
                severity=DiagnosticSeverity.WARNING,
                message="duplicate effective key",
                table="device_st",
                column="gid",
            ),
        ),
    )


def _sample_storage_facts() -> tuple[ComparisonStorageFacts, ...]:
    return (
        ComparisonStorageFacts(
            storage_rule_view=StorageRuleView(
                canonical_table="device_st",
                canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
                ordered_policy=OrderedPolicy.NONE,
                dropped_columns=(DroppedColumn(name="ignored_col", reason="legacy_ignored"),),
                structural_columns=("no",),
                retained_columns=("gid", "no"),
                canonical_key_columns=("gid",),
                storage_rule_digest=_DIGEST_C,
            ),
            source_schema_digest=_DIGEST_A,
            canonical_schema_digest=_DIGEST_B,
            raw_content_digest=_DIGEST_C,
            storage_projection_version="4",
        ),
    )


def _mutated_descriptor(mutator: Any) -> dict[str, object]:
    doc = copy.deepcopy(snapshot_descriptor_to_document(_sample_descriptor()))
    mutator(doc)
    return doc


def _mutated_facts(mutator: Any) -> list[dict[str, object]]:
    docs = copy.deepcopy(storage_facts_to_documents(_sample_storage_facts()))
    mutator(docs)
    return docs


MALFORMED_DESCRIPTOR_DOCUMENTS: tuple[tuple[str, object], ...] = (
    ("non_dict_list", []),
    ("non_dict_bytes", b"{}"),
    ("extra_top_key", _mutated_descriptor(lambda d: d.__setitem__("extra", 1))),
    ("missing_top_key", _mutated_descriptor(lambda d: d.pop("row_count"))),
    ("bool_as_row_count", _mutated_descriptor(lambda d: d.__setitem__("row_count", True))),
    (
        "bool_as_ruleset_version",
        _mutated_descriptor(lambda d: d.__setitem__("table_ruleset_version", True)),
    ),
    (
        "bool_as_scalar_version",
        _mutated_descriptor(lambda d: d.__setitem__("scalar_encoding_version", True)),
    ),
    (
        "int_as_nullable",
        _mutated_descriptor(lambda d: d["columns"][0].__setitem__("nullable", 1)),
    ),
    (
        "tuple_as_columns",
        _mutated_descriptor(lambda d: d.__setitem__("columns", tuple(d["columns"]))),
    ),
    (
        "tuple_as_primary_key_columns",
        _mutated_descriptor(lambda d: d.__setitem__("primary_key_columns", ("gid",))),
    ),
    (
        "tuple_as_diagnostics",
        _mutated_descriptor(lambda d: d.__setitem__("diagnostics", tuple(d["diagnostics"]))),
    ),
    (
        "non_str_in_compare_key",
        _mutated_descriptor(lambda d: d.__setitem__("compare_key_columns", [1])),
    ),
    (
        "extra_column_key",
        _mutated_descriptor(lambda d: d["columns"][0].__setitem__("extra", "x")),
    ),
    (
        "extra_diagnostic_key",
        _mutated_descriptor(lambda d: d["diagnostics"][0].__setitem__("extra", "x")),
    ),
    ("empty_table_name", _mutated_descriptor(lambda d: d.__setitem__("table_name", ""))),
    (
        "empty_scalar_type",
        _mutated_descriptor(lambda d: d["columns"][0].__setitem__("scalar_type", "")),
    ),
    (
        "invalid_stage",
        _mutated_descriptor(lambda d: d.__setitem__("materialization_stage", "BOGUS")),
    ),
    (
        "invalid_degraded_reason",
        _mutated_descriptor(lambda d: d.__setitem__("degraded_reason", "BOGUS")),
    ),
    (
        "invalid_digest",
        _mutated_descriptor(lambda d: d.__setitem__("compare_schema_digest", "not-a-digest")),
    ),
)


MALFORMED_STORAGE_FACTS_DOCUMENTS: tuple[tuple[str, object], ...] = (
    ("non_list_dict", {}),
    ("non_list_tuple", tuple(storage_facts_to_documents(_sample_storage_facts()))),
    ("extra_item_key", _mutated_facts(lambda ds: ds[0].__setitem__("extra", 1))),
    ("missing_item_key", _mutated_facts(lambda ds: ds[0].pop("ordered_policy"))),
    (
        "extra_dropped_key",
        _mutated_facts(lambda ds: ds[0]["dropped_columns"][0].__setitem__("extra", 1)),
    ),
    (
        "tuple_as_dropped_columns",
        _mutated_facts(
            lambda ds: ds[0].__setitem__("dropped_columns", tuple(ds[0]["dropped_columns"]))
        ),
    ),
    (
        "tuple_as_structural_columns",
        _mutated_facts(lambda ds: ds[0].__setitem__("structural_columns", ("no",))),
    ),
    (
        "bool_as_projection_version",
        _mutated_facts(lambda ds: ds[0].__setitem__("storage_projection_version", True)),
    ),
    (
        "empty_projection_version",
        _mutated_facts(lambda ds: ds[0].__setitem__("storage_projection_version", "")),
    ),
    (
        "invalid_key_policy",
        _mutated_facts(lambda ds: ds[0].__setitem__("canonical_key_policy", "BOGUS")),
    ),
    (
        "invalid_source_digest",
        _mutated_facts(lambda ds: ds[0].__setitem__("source_schema_digest", "bad")),
    ),
)


def test_snapshot_descriptor_document_round_trip_preserves_canonical_bytes() -> None:
    descriptor = _sample_descriptor()
    document = snapshot_descriptor_to_document(descriptor)
    restored = snapshot_descriptor_from_document(document)
    assert restored == descriptor
    assert canonicalize_json_value(
        snapshot_descriptor_to_document(restored)
    ) == canonicalize_json_value(document)
    assert isinstance(restored.compare_schema_digest, DigestRef)


def test_storage_facts_document_round_trip_preserves_canonical_bytes() -> None:
    facts = _sample_storage_facts()
    documents = storage_facts_to_documents(facts)
    restored = storage_facts_from_documents(documents)
    assert restored == facts
    assert canonicalize_json_value(storage_facts_to_documents(restored)) == canonicalize_json_value(
        documents
    )


@pytest.mark.parametrize(("label", "payload"), MALFORMED_DESCRIPTOR_DOCUMENTS)
def test_snapshot_descriptor_from_document_rejects_malformed_shapes(
    label: str, payload: object
) -> None:
    del label
    with pytest.raises(ValueError):
        snapshot_descriptor_from_document(payload)


@pytest.mark.parametrize(("label", "payload"), MALFORMED_STORAGE_FACTS_DOCUMENTS)
def test_storage_facts_from_documents_rejects_malformed_shapes(label: str, payload: object) -> None:
    del label
    with pytest.raises(ValueError):
        storage_facts_from_documents(payload)


def test_arrow_catalog_adapter_rejects_bool_gid_before_contract_construction() -> None:
    batch = pa.record_batch(
        [pa.array([True]), pa.array([65532]), pa.array(["复合信号虚装置"])],
        names=["gid", "dev_addr", "description"],
    )
    reader = pa.RecordBatchReader.from_batches(batch.schema, [batch])
    result = {
        "output": {
            "source_device_row_count": 1,
            "tables": [
                {
                    "canonical_name": "device",
                    "arrow_stream": reader,
                    "columns": [
                        {"canonical_name": "gid", "logical_type": "int", "declared_type": None},
                        {
                            "canonical_name": "dev_addr",
                            "logical_type": "int",
                            "declared_type": None,
                        },
                        {
                            "canonical_name": "description",
                            "logical_type": "str",
                            "declared_type": None,
                        },
                    ],
                }
            ],
        }
    }
    with pytest.raises(ValueError, match="gid must be int"):
        _convert_catalog_from_arrow_result(
            result,
            budgets={
                "max_live_bytes": 10_000_000,
                "max_output_bytes": 10_000_000,
                "max_metadata_bytes": 1_000_000,
            },
            cancel_probe=NeverCancel(),
            deadline_monotonic=None,
            reserve=lambda _size: None,
        )
