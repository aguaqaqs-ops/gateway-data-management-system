"""Independent S3 risk replay expectations from the frozen Python control flow.

These cases deliberately feed small contract facts, without invoking either comparison
kernel. The expected counts come from Risk Contract S3 and _engine.emit's existing
limit-before-filter, normal-return, and exception branches.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison.artifacts import (
    RecordsPublicationError,
    RecordsPublicationContext,
    RecordsPublicationPolicy,
    _validate_parquet_bytes,
    _schema_for,
    write_arrow_parquet,
)
from gateway_backend.capabilities.comparison.contracts import (
    RECORDS_PARQUET_FORMAT,
    STANDARD_RECORDS_SCHEMA_VERSION,
    ComparisonFacts,
    ComparisonMode,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTableStatus,
    PairResultStatus,
    RecordsArtifactFamily,
    RecordsArtifactManifest,
    RecordsDetailPolicy,
)
from gateway_backend.capabilities.comparison.row_encoding import _row_occurrence_digest
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
    RiskEvaluationStatus,
    RiskExecutionPolicy,
    RiskOptions,
    RiskRulesetSnapshot,
    V1_RISK_RULE_SPECS,
    evaluate_risk,
)


def _added_rows(
    name: str,
    count: int,
    *,
    diagnostics: tuple[str, ...] = (),
) -> ComparisonTableFact:
    return ComparisonTableFact(
        table_name=name,
        status=ComparisonTableStatus.MODIFIED,
        row_added_count=count,
        records=tuple(
            ComparisonRecord(
                table_name=name,
                record_kind=ComparisonRecordKind.ROW_ADDED,
                row_identity=DigestRef(f"sha256:{index + 1:064x}"),
            )
            for index in range(count)
        ),
        diagnostics=diagnostics,
    )


def _input(tables: tuple[ComparisonTableFact, ...], *, options: RiskOptions | None = None) -> RiskEvaluationInput:
    facts = ComparisonFacts(
        comparison_digest=raw_blob_digest(b"s3-risk-comparison"),
        facts_core_digest=raw_blob_digest(b"s3-risk-facts"),
        comparison_contract_version="backend-vnext/comparison/v3",
        projection_contract_version="backend-vnext/comparison-projection/v1",
        scalar_encoding_version=1,
        before_snapshot_digest=raw_blob_digest(b"s3-risk-before"),
        current_snapshot_digest=raw_blob_digest(b"s3-risk-current"),
        comparison_mode=ComparisonMode.DETAILED,
        direction="BEFORE_TO_CURRENT",
        summary=ComparisonSummary(
            status=PairResultStatus.CHANGED,
            table_count=len(tables),
            unchanged_table_count=0,
            changed_table_count=len(tables),
            added_table_count=0,
            deleted_table_count=0,
            schema_changed_table_count=sum(
                table.status in {
                    ComparisonTableStatus.SCHEMA_CHANGED,
                    ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
                }
                for table in tables
            ),
            degraded_table_count=0,
            row_added_count=sum(table.row_added_count for table in tables),
            row_deleted_count=0,
            row_modified_count=0,
            suppressed_added_count=0,
            suppressed_deleted_count=0,
            diagnostics_count=sum(len(table.diagnostics) for table in tables),
        ),
        tables=tables,
    )
    return RiskEvaluationInput(
        comparison_facts=facts,
        risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
        risk_options=options or RiskOptions(),
    )


def test_keyless_third_copy_uses_frozen_occurrence_two_identity() -> None:
    # The row digest is the frozen mixed-fields vector in Shared Kernel v1;
    # the expected occurrence digest is the Contract domain preimage with ULEB128(2).
    row = DigestRef("sha256:401578531a0add4dd48daa932190b0f1fff21f90cd2378a112c32199b1a80f39")
    assert _row_occurrence_digest(row, 2) == DigestRef(
        "sha256:a30dfdfae0f29e7d4a7da411578d351fac59a100052dc8fd2135f6940f4ba2bb"
    )


def test_records_writer_uses_1024_rows_then_one_row_group() -> None:
    fixture = (
        Path(__file__).resolve().parents[2]
        / "fixtures/vectors/comparison/records/standard-v1.parquet.b64"
    )
    source = pq.read_table(pa.BufferReader(base64.b64decode(fixture.read_text(encoding="ascii"))))
    one_row = source.to_pylist()[0]
    rows = tuple(
        dict(one_row, row_identity=index.to_bytes(32, "big"))
        for index in range(1025)
    )
    schema = _schema_for(
        RecordsArtifactFamily.STANDARD, None,
        RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
    )
    raw = write_arrow_parquet(
        (
            pa.RecordBatch.from_pylist(list(rows[:1024]), schema=schema),
            pa.RecordBatch.from_pylist(list(rows[1024:]), schema=schema),
        ),
        schema, RecordsPublicationPolicy(), RecordsPublicationContext(),
    )
    file = pq.ParquetFile(pa.BufferReader(raw))

    assert file.metadata is not None
    assert file.metadata.num_row_groups == 2
    assert tuple(file.metadata.row_group(index).num_rows for index in range(2)) == (1024, 1)


def test_table_budget_exception_does_not_consume_pair_count() -> None:
    # A's third Emit raises the table exception. Its one degraded annotation is
    # published, but the outer exception path does not add it to total_annotations.
    # B consumes two of three pair slots; C consumes the final slot and ends.
    source = _input((_added_rows("a", 3), _added_rows("b", 2), _added_rows("c", 1)))
    result = evaluate_risk(
        source,
        artifact_store=InMemoryArtifactStore(),
        execution_policy=RiskExecutionPolicy(max_annotations_per_table=2, max_annotations_per_pair=3),
    )

    assert result.status is RiskEvaluationStatus.DEGRADED
    assert result.risk_report is not None
    assert tuple((table.table_name, table.annotation_count) for table in result.risk_report.tables) == (
        ("a", 1),
        ("b", 2),
        ("c", 1),
    )
    assert result.risk_report.tables[0].diagnostics == ("RISK_TABLE_BUDGET_EXCEEDED",)
    assert result.risk_closure is not None


def test_diagnostics_preflight_degraded_does_consume_pair_count() -> None:
    # A normally returns its degraded outcome from the diagnostics preflight.
    # Its count is therefore one: B fills the pair cap and C's next Emit triggers
    # pair degradation, discarding all partial annotations and their closure.
    source = _input(
        (
            _added_rows("a", 3, diagnostics=("first", "second")),
            _added_rows("b", 2),
            _added_rows("c", 1),
        )
    )
    result = evaluate_risk(
        source,
        artifact_store=InMemoryArtifactStore(),
        execution_policy=RiskExecutionPolicy(
            max_annotations_per_table=2,
            max_annotations_per_pair=3,
            max_diagnostics_per_table=1,
        ),
    )

    assert result.status is RiskEvaluationStatus.DEGRADED
    assert result.risk_report is not None
    assert tuple((table.table_name, table.annotation_count) for table in result.risk_report.tables) == (
        ("a", 0),
        ("b", 0),
        ("c", 0),
    )
    assert all(
        table.diagnostics == ("RISK_ANNOTATION_LIMIT_EXCEEDED",)
        for table in result.risk_report.tables
    )
    assert result.annotation_artifacts == ()
    assert result.risk_closure is None


def test_filtered_emit_after_pair_cap_still_triggers_pair_degradation() -> None:
    # ROW_ADDED is MEDIUM_LOW in the frozen ruleset. The second table's Emit is
    # filtered by include_low_risk=False, but the pair cap is checked first.
    first = ComparisonTableFact(
        table_name="a",
        status=ComparisonTableStatus.SCHEMA_CHANGED,
    )
    second = _added_rows("b", 1)
    result = evaluate_risk(
        _input((first, second), options=RiskOptions(include_low_risk=False)),
        artifact_store=InMemoryArtifactStore(),
        execution_policy=RiskExecutionPolicy(max_annotations_per_pair=1),
    )

    assert result.status is RiskEvaluationStatus.DEGRADED
    assert result.risk_report is not None
    assert tuple(table.annotation_count for table in result.risk_report.tables) == (0, 0)
    assert result.annotation_artifacts == ()
    assert result.risk_closure is None


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("schema", "schema mismatch"),
        ("count", "count mismatch"),
        ("content", "content digest mismatch"),
    ),
)
def test_records_fixed_vector_rejects_independent_semantic_corruption(
    corruption: str,
    message: str,
) -> None:
    # This fixture and its digest predate S3. C must move this same vector through
    # the real PyO3 Arrow validator when the old Python reader is removed.
    fixture = (
        Path(__file__).resolve().parents[2]
        / "fixtures/vectors/comparison/records/standard-v1.parquet.b64"
    )
    raw = base64.b64decode(fixture.read_text(encoding="ascii"))
    manifest = RecordsArtifactManifest(
        table_name="t",
        family=RecordsArtifactFamily.STANDARD,
        record_format=RECORDS_PARQUET_FORMAT,
        schema_version=STANDARD_RECORDS_SCHEMA_VERSION,
        row_diff_detail_policy=RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
        record_count=1,
        content_digest=DigestRef(
            "sha256:22bfb26abb0aaeb3d279cdae0614d2733bebbd8cdf8021cfa6751c690db561d4"
        ),
    )
    table = pq.read_table(pa.BufferReader(raw))
    if corruption == "schema":
        table = table.replace_schema_metadata({})
    elif corruption == "count":
        table = table.slice(0, 0)
    else:
        table = table.set_column(
            1,
            table.schema.field(1),
            pa.array(["ROW_ADDED"], type=pa.string()),
        )
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="zstd", use_dictionary=False)

    with pytest.raises(RecordsPublicationError, match=message):
        _validate_parquet_bytes(sink.getvalue().to_pybytes(), manifest, RecordsPublicationPolicy())
