"""Canonical storage identity across a live Repository Service round trip."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from gateway_shared_kernel import (
    DateTimeScalar,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
    raw_blob_digest,
)

from gateway_backend.capabilities.snapshot_materialization import materialize_repository_ref
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    SnapshotTable,
    SnapshotTableSet,
)
from gateway_backend.capabilities.storage_projection import (
    NeverCancel,
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionStatus,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    build_repository_import_package,
    project_canonical_table_set,
    project_storage,
    render_repository_import_schema_replay_sql,
)
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel as ParserNeverCancel,
    ParserInvocationContext,
    SqlSetValue,
)
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.infrastructure.repository_read.http_arrow import (
    build_http_repository_provider_factory,
)
from gateway_backend.capabilities.table_access.contracts import SourceCell, SourceRow
from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE
from tests.support.submit_job_harness import repository_service_session
from tests.support.storage_projection import (
    as_row,
    dummy_digest,
    int_cell,
    int_column,
    null_cell,
    set_cell,
    set_column,
    table_input,
    typed_column,
    uint_cell,
    varchar_cell,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

_SOURCE_SNAPSHOT_DIGEST = dummy_digest()
_RULESET = migrated_table_ruleset_snapshot()
_CANONICAL_COLUMNS = (
    int_column("id"),
    typed_column("tiny_unsigned", "TINYINT UNSIGNED"),
    typed_column("small_unsigned", "SMALLINT UNSIGNED"),
    typed_column("unsigned_value", "INT UNSIGNED"),
    typed_column("wide_value", "BIGINT"),
    typed_column("reading", "FLOAT"),
    typed_column("double_reading", "DOUBLE"),
    typed_column("sampled_at", "DATETIME"),
    typed_column("label", "CHAR(8)"),
    typed_column("optional_text", "VARCHAR(64)", nullable=True),
    typed_column("state", "ENUM('idle','active')"),
    set_column("permissions", "SET('read','write','admin')"),
)
_CANONICAL_ROWS = (
    as_row(
        int_cell(1),
        uint_cell(2),
        uint_cell(300),
        uint_cell(4294967295),
        SignedIntegerScalar(decimal="-9223372036854775808"),
        Float32Scalar(bits_hex="3dcccccd"),
        Float64Scalar(bits_hex="8000000000000000"),
        DateTimeScalar(text="2026-10-11T12:34:56"),
        varchar_cell("tail  "),
        null_cell(),
        varchar_cell("active"),
        set_cell("admin", "read"),
    ),
    as_row(
        int_cell(2),
        uint_cell(255),
        uint_cell(65535),
        uint_cell(0),
        SignedIntegerScalar(decimal="9223372036854775807"),
        Float32Scalar(bits_hex="bf9d70a4"),
        Float64Scalar(bits_hex="3fb999999999999a"),
        DateTimeScalar(text="2026-10-11T12:35:00"),
        varchar_cell("head"),
        varchar_cell("value"),
        varchar_cell("idle"),
        set_cell("write"),
    ),
    as_row(
        int_cell(3),
        uint_cell(7),
        uint_cell(7),
        uint_cell(2147483648),
        SignedIntegerScalar(decimal="-1"),
        Float32Scalar(bits_hex="33d6bf95"),
        Float64Scalar(bits_hex="bff3ae147ae147ae"),
        DateTimeScalar(text="2026-10-11T12:35:04"),
        varchar_cell("third"),
        null_cell(),
        varchar_cell("active"),
        set_cell("read"),
    ),
    as_row(
        int_cell(4),
        uint_cell(8),
        uint_cell(8),
        uint_cell(1000),
        SignedIntegerScalar(decimal="1"),
        Float32Scalar(bits_hex="00000001"),
        Float64Scalar(bits_hex="3fb999999999999a"),
        DateTimeScalar(text="2026-10-11T12:35:08"),
        varchar_cell("fourth"),
        varchar_cell("value"),
        varchar_cell("idle"),
        set_cell("write"),
    ),
    as_row(
        int_cell(5),
        uint_cell(0),
        uint_cell(0),
        uint_cell(42),
        SignedIntegerScalar(decimal="0"),
        Float32Scalar(bits_hex="80000000"),
        Float64Scalar(bits_hex="0000000000000000"),
        DateTimeScalar(text="2026-10-11T12:35:12"),
        varchar_cell("fifth"),
        null_cell(),
        varchar_cell("active"),
        set_cell("admin"),
    ),
)
_ORDERED_ROWS = (
    as_row(null_cell(), int_cell(2), varchar_cell("blank")),
    as_row(int_cell(9), int_cell(1), varchar_cell("real")),
)


def test_canonical_snapshot_identity(
    tmp_path: Path,
    requires_dolt: None,
) -> None:
    data_reader, data_binding = table_input(
        "identity_dc15",
        columns=_CANONICAL_COLUMNS,
        primary_key_columns=("id",),
        rows=_CANONICAL_ROWS,
        snapshot_digest=_SOURCE_SNAPSHOT_DIGEST,
    )
    ordered_reader, ordered_binding = table_input(
        "b1_n1_iec104_syx_list",
        columns=(
            int_column("gid", nullable=True),
            int_column("no", nullable=True),
            typed_column("value", "VARCHAR(64)"),
        ),
        primary_key_columns=("gid",),
        rows=_ORDERED_ROWS,
        snapshot_digest=_SOURCE_SNAPSHOT_DIGEST,
    )
    raw_table_set = SnapshotTableSet(
        snapshot_id="raw-canonical-identity",
        snapshot_digest=_SOURCE_SNAPSHOT_DIGEST,
        table_ruleset_version=TABLE_RULESET_VERSION,
        tables=(
            SnapshotTable(descriptor=data_binding.descriptor, reader=data_reader),
            SnapshotTable(descriptor=ordered_binding.descriptor, reader=ordered_reader),
        ),
    )
    canonical = project_canonical_table_set(raw_table_set, _RULESET)
    assert canonical.manifest is not None
    assert len(canonical.tables) == 2
    projection_inputs = (
        ProjectionTableInput(
            canonical_table="identity_dc15",
            reader=data_reader.reopen(),
            source_binding=data_binding,
        ),
        ProjectionTableInput(
            canonical_table="b1_n1_iec104_syx_list",
            reader=ordered_reader.reopen(),
            source_binding=ordered_binding,
        ),
    )
    projection = project_storage(
        ProjectionRequest(
            ruleset=_RULESET,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            tables=projection_inputs,
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
    )
    assert projection.status is ProjectionStatus.COMPLETE
    assert projection.import_input is not None
    canonical_rows = {
        table.descriptor.table_name: tuple(table.reader.iter_rows())
        for table in canonical.tables
        if table.reader is not None
    }
    replay_sql = render_repository_import_schema_replay_sql(projection.import_input)
    replay_sql += _render_canonical_inserts(canonical.tables, canonical_rows)
    package = build_repository_import_package(
        import_input=projection.import_input,
        replay_sql=replay_sql,
    )
    package_bytes = package.payload
    package_sha = raw_blob_digest(package_bytes).value

    with repository_service_session(tmp_path) as service:
        seeded = service.repository_id_factory(idempotency_key="create-canonical-identity")
        write_client = service.write_client()
        repository_artifact = write_client.upload_artifact(
            repository_id=seeded.repository_id,
            idempotency_key="upload-canonical-identity",
            media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
            raw_sha256=package_sha,
            body=package_bytes,
        )
        operation_id = write_client.submit_versioned_import(
            repository_id=seeded.repository_id,
            idempotency_key="import-canonical-identity",
            artifact_ref=repository_artifact,
            expected_commit_id=seeded.initial_commit_id,
        )
        operation = write_client.wait_operation(
            repository_id=seeded.repository_id,
            operation_id=operation_id,
            deadline_seconds=120.0,
        )
        assert operation.status.value == "SUCCEEDED", operation.error
        assert operation.result is not None

        provider = build_http_repository_provider_factory(
            base_url=service.base_url,
            bearer_token=service.bearer_token,
            timeout_seconds=30.0,
        )(seeded.repository_id, operation.result.commit_id)
        materialized = materialize_repository_ref(
            RepositoryRefMaterializationRequest(
                repository_ref=RepositoryRef(
                    repository_id=seeded.repository_id,
                    ref=operation.result.commit_id,
                ),
                provider=provider,
                ruleset=_RULESET,
                table_ruleset_version=TABLE_RULESET_VERSION,
                materialization_stage=MaterializationStage.FINAL,
                policy=MaterializationPolicy.READERS_REQUIRED,
                context=ParserInvocationContext(ParserNeverCancel()),
                requested_tables=("identity_dc15", "b1_n1_iec104_syx_list"),
            )
        )

    assert materialized.table_set is not None
    expected_by_name = {table.descriptor.table_name: table for table in canonical.tables}
    observed_by_name = {
        table.descriptor.table_name: table for table in materialized.table_set.tables
    }
    assert set(observed_by_name) == set(expected_by_name)
    for name, expected in expected_by_name.items():
        observed = observed_by_name[name]
        assert observed.descriptor.columns == expected.descriptor.columns
        assert observed.descriptor.primary_key_columns == expected.descriptor.primary_key_columns
        assert observed.descriptor.row_count == expected.descriptor.row_count
        assert observed.descriptor.business_schema_digest == expected.descriptor.business_schema_digest
        assert observed.descriptor.raw_content_digest == expected.descriptor.raw_content_digest
        assert expected.reader is not None
        assert observed.reader is not None
        assert tuple(observed.reader.iter_rows()) == canonical_rows[name]
        observed.reader.close()
    for table in canonical.tables:
        if table.reader is not None:
            table.reader.close()


def _render_canonical_inserts(
    tables: tuple[SnapshotTable, ...],
    rows_by_table: dict[str, tuple[SourceRow, ...]],
) -> bytes:
    statements: list[str] = []
    for table in tables:
        columns = table.descriptor.columns
        names = ", ".join(_quote_identifier(column.name) for column in columns)
        for row in rows_by_table[table.descriptor.table_name]:
            values = ", ".join(_sql_literal(cell) for cell in row)
            statements.append(
                f"INSERT INTO {_quote_identifier(table.descriptor.table_name)} ({names}) "
                f"VALUES ({values});\n"
            )
    return "".join(statements).encode("utf-8")


def _sql_literal(cell: SourceCell) -> str:
    if isinstance(cell, NullScalar):
        return "NULL"
    if isinstance(cell, (SignedIntegerScalar, UnsignedIntegerScalar)):
        return cell.decimal
    if isinstance(cell, Float32Scalar):
        number = struct.unpack(">f", bytes.fromhex(cell.bits_hex))[0]
        return format(number, ".9g")
    if isinstance(cell, Float64Scalar):
        number = struct.unpack(">d", bytes.fromhex(cell.bits_hex))[0]
        return format(number, ".17g")
    if isinstance(cell, DateTimeScalar):
        return _quote_string(cell.text.replace("T", " "))
    if isinstance(cell, StringScalar):
        return _quote_string(cell.text)
    if isinstance(cell, SqlSetValue):
        return _quote_string(",".join(cell.members))
    raise AssertionError(f"unsupported test cell: {type(cell).__name__}")


def _quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def _quote_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
