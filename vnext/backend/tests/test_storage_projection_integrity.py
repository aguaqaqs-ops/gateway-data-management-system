"""Ordered, keyless and digest integrity for storage projection. No package publication."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from gateway_shared_kernel import (
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    DigestRef,
    NullScalar,
    StringScalar,
    encode_collection,
    encode_typed_scalar,
)

from gateway_backend.capabilities.storage_projection import (
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    ProjectionDiagnosticCode,
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionResult,
    ProjectionStatus,
    ProjectionTableInput,
    project_storage,
)
from gateway_backend.capabilities.storage_projection._digest import (
    CanonicalColumnCodec,
    compute_keyless_content_digest,
    encode_canonical_cell,
    manifest_document,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ArtifactSourceBinding,
    SnapshotColumnDescriptor,
)
from gateway_backend.capabilities.storage_projection._ordered import GID_PSEUDO_MIN
from gateway_backend.capabilities.table_access.contracts import SourceRow
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    SelectorPrecedenceClass,
    TableArtifactScope,
    TableRuleRecord,
    TableRuleSelector,
    TableRuleSelectorKind,
    TableRulesetSnapshot,
    TableStaticRole,
    TableStorageDisposition,
    legacy_ignored_column_reason,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from tests.support.storage_projection import (
    FakeSnapshotTableReader,
    as_row,
    digest_ref,
    dummy_digest,
    enum_column,
    int_cell,
    int_column,
    null_cell,
    set_cell,
    set_column,
    table_input,
    typed_column,
    varchar_cell,
    varchar_column,
)
from tests.support.table_rules import keyless_record, snapshot_from_records

pytestmark = pytest.mark.unit

TableInput = tuple[FakeSnapshotTableReader, ArtifactSourceBinding]
_ENUM_SQL = "ENUM('','active','paused')"
_SET_SQL = "SET('read','write','admin')"
_NULL_FRAME = encode_typed_scalar(DeclaredType(kind=DeclaredTypeKind.NULL), NullScalar()).scalar_frame
_STRING_TYPE = DeclaredType(kind=DeclaredTypeKind.STRING)


def _request(
    *inputs: TableInput,
    ruleset: TableRulesetSnapshot | None = None,
    context: ProjectionInvocationContext | None = None,
) -> ProjectionRequest:
    tables = tuple(
        ProjectionTableInput(
            canonical_table=binding.descriptor.table_name,
            reader=reader,
            source_binding=binding,
        )
        for reader, binding in inputs
    )
    return ProjectionRequest(
        ruleset=ruleset or migrated_table_ruleset_snapshot(),
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        tables=tables,
        context=context or ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )


def _codes(result: ProjectionResult) -> tuple[ProjectionDiagnosticCode, ...]:
    return tuple(item.code for item in result.diagnostics)


def _ordered_input(
    rows: tuple[SourceRow, ...],
    *,
    table_name: str = "b1_n1_iec104_syx_list",
) -> TableInput:
    return table_input(
        table_name,
        columns=(int_column("gid", nullable=True), int_column("no"), varchar_column("value")),
        primary_key_columns=("gid",),
        rows=rows,
    )


def _keyless_input(
    rows: tuple[SourceRow, ...],
    *,
    extra_columns: tuple[SnapshotColumnDescriptor, ...] = (),
) -> TableInput:
    columns = (varchar_column("note"),) + extra_columns
    return table_input(
        "notes",
        columns=columns,
        primary_key_columns=(),
        rows=rows,
    )


def test_keyless_preserves_duplicates_and_is_order_independent() -> None:
    first_rows = (
        as_row(varchar_cell("b")),
        as_row(varchar_cell("a")),
        as_row(varchar_cell("b")),
    )
    second_rows = (
        as_row(varchar_cell("a")),
        as_row(varchar_cell("b")),
        as_row(varchar_cell("b")),
    )
    ruleset = snapshot_from_records(keyless_record())
    first = project_storage(_request(_keyless_input(first_rows), ruleset=ruleset))
    second = project_storage(_request(_keyless_input(second_rows), ruleset=ruleset))
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.tables[0].row_count == 3
    assert first.tables[0].storage_view.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT_KEYLESS
    assert first.tables[0].storage_view.canonical_key_columns == ()
    assert first.import_input is not None
    assert first.import_input.tables[0].primary_key == ()
    assert first.manifest is not None
    assert second.manifest is not None
    assert first.tables[0].content_digest == second.tables[0].content_digest
    assert first.manifest.manifest_digest == second.manifest.manifest_digest


def test_keyless_does_not_invent_a_surrogate_key() -> None:
    ruleset = snapshot_from_records(keyless_record())
    result = project_storage(
        _request(_keyless_input((as_row(varchar_cell("x")), as_row(varchar_cell("x")))), ruleset=ruleset)
    )
    assert result.status is ProjectionStatus.COMPLETE
    assert result.tables[0].row_count == 2
    assert result.tables[0].storage_view.canonical_key_columns == ()


_SCALAR_TYPE_VOCABULARY_CASES: tuple[tuple[str, Callable[[], TableInput], ProjectionStatus, str | None], ...] = (
    (
        "ordered_vocab",
        lambda: _ordered_input(
            (
                as_row(int_cell(1), int_cell(1), varchar_cell("a")),
                as_row(int_cell(2), int_cell(2), varchar_cell("b")),
            )
        ),
        ProjectionStatus.COMPLETE,
        None,
    ),
    (
        "ordered_sized_varchar",
        lambda: table_input(
            "b1_n1_iec104_syx_list",
            columns=(
                int_column("gid", nullable=True),
                int_column("no"),
                typed_column("value", "VARCHAR(8)", nullable=True),
            ),
            primary_key_columns=("gid",),
            rows=(
                as_row(int_cell(1), int_cell(1), varchar_cell("a")),
                as_row(int_cell(2), int_cell(2), varchar_cell("b")),
            ),
        ),
        ProjectionStatus.COMPLETE,
        None,
    ),
    (
        "plain_sized_varchar",
        lambda: table_input(
            "t3",
            columns=(
                int_column("id"),
                typed_column("label", "VARCHAR(8)"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), varchar_cell("x")),),
        ),
        ProjectionStatus.COMPLETE,
        None,
    ),
    (
        "plain_bigint",
        lambda: table_input(
            "t4",
            columns=(
                int_column("id"),
                typed_column("big", "BIGINT"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), int_cell(99)),),
        ),
        ProjectionStatus.COMPLETE,
        None,
    ),
    (
        "bigint_above_int32_max",
        lambda: table_input(
            "t4",
            columns=(
                int_column("id"),
                typed_column("big", "BIGINT"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), int_cell(2_147_483_648)),),
        ),
        ProjectionStatus.COMPLETE,
        None,
    ),
    (
        "bigint_large_positive",
        lambda: table_input(
            "t4",
            columns=(
                int_column("id"),
                typed_column("big", "BIGINT"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), int_cell(5_000_000_000)),),
        ),
        ProjectionStatus.COMPLETE,
        None,
    ),
    (
        "bigint_below_int32_min",
        lambda: table_input(
            "t4",
            columns=(
                int_column("id"),
                typed_column("big", "BIGINT"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), int_cell(-2_147_483_649)),),
        ),
        ProjectionStatus.COMPLETE,
        None,
    ),
    (
        "unsupported_decimal",
        lambda: table_input(
            "t5",
            columns=(
                int_column("id"),
                typed_column("amount", "DECIMAL(10,2)"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), varchar_cell("1.00")),),
        ),
        ProjectionStatus.FAILED,
        "t5",
    ),
    (
        "unsupported_decimal_single_precision",
        lambda: table_input(
            "t5",
            columns=(
                int_column("id"),
                typed_column("amount", "DECIMAL(10)"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), varchar_cell("1.00")),),
        ),
        ProjectionStatus.FAILED,
        "t5",
    ),
    (
        "bigint_unsigned",
        lambda: table_input(
            "t6",
            columns=(
                int_column("id"),
                typed_column("big", "BIGINT UNSIGNED"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), int_cell(1)),),
        ),
        ProjectionStatus.FAILED,
        "t6",
    ),
)


@pytest.mark.parametrize(
    ("label", "table_input_factory", "expected_status", "expected_table_name"),
    _SCALAR_TYPE_VOCABULARY_CASES,
    ids=tuple(case[0] for case in _SCALAR_TYPE_VOCABULARY_CASES),
)
def test_storage_projection_scalar_type_vocabulary_cases(
    label: str,
    table_input_factory: Callable[[], TableInput],
    expected_status: ProjectionStatus,
    expected_table_name: str | None,
) -> None:
    del label
    result = project_storage(_request(table_input_factory()))
    assert result.status is expected_status
    if expected_status is ProjectionStatus.FAILED:
        assert result.diagnostics
        diagnostic = result.diagnostics[0]
        assert diagnostic.code is ProjectionDiagnosticCode.UNSUPPORTED_TABLE
        assert diagnostic.message == "column scalar_type is not supported"
        assert diagnostic.table_name == expected_table_name


def test_ordered_real_gid_and_blank_pseudo_allocation() -> None:
    result = project_storage(
        _request(
            _ordered_input(
                (
                    as_row(null_cell(), int_cell(2), varchar_cell("second")),
                    as_row(int_cell(1), int_cell(1), varchar_cell("first")),
                )
            )
        )
    )
    assert result.status is ProjectionStatus.COMPLETE
    table = result.tables[0]
    assert table.storage_view.canonical_key_columns == ("gid",)
    assert table.storage_view.structural_columns == ("no",)
    assert table.ordering_digest is not None
    assert result.manifest is not None
    facts = result.manifest.tables[0]
    assert facts.gid_real_count == 1
    assert facts.gid_pseudo_count == 1
    assert facts.canonical_schema_digest is not None
    import_table = result.import_input.tables[0] if result.import_input is not None else None
    assert import_table is not None
    assert import_table.primary_key == ("gid",)
    assert import_table.columns[0].sql_type == "INT UNSIGNED"
    assert import_table.columns[0].nullable is False
    zero = project_storage(
        _request(
            _ordered_input(
                (
                    as_row(int_cell(0), int_cell(2), varchar_cell("second")),
                    as_row(int_cell(1), int_cell(1), varchar_cell("first")),
                )
            )
        )
    )
    empty = project_storage(
        _request(
            _ordered_input(
                (
                    as_row(varchar_cell(""), int_cell(2), varchar_cell("second")),
                    as_row(int_cell(1), int_cell(1), varchar_cell("first")),
                )
            )
        )
    )
    assert zero.status is ProjectionStatus.COMPLETE
    assert empty.status is ProjectionStatus.COMPLETE
    assert table.content_digest == zero.tables[0].content_digest == empty.tables[0].content_digest
    assert table.ordering_digest == zero.tables[0].ordering_digest == empty.tables[0].ordering_digest
    assert GID_PSEUDO_MIN == 4_000_000_000


def test_ordered_insert_order_does_not_change_digests() -> None:
    rows = (
        as_row(int_cell(1), int_cell(1), varchar_cell("a")),
        as_row(int_cell(2), int_cell(2), varchar_cell("b")),
    )
    reordered = (rows[1], rows[0])
    first = project_storage(_request(_ordered_input(rows)))
    second = project_storage(_request(_ordered_input(reordered)))
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.tables[0].content_digest == second.tables[0].content_digest
    assert first.tables[0].ordering_digest == second.tables[0].ordering_digest


def test_ordered_position_shift_changes_only_ordering_digest() -> None:
    original = (
        as_row(int_cell(1), int_cell(1), varchar_cell("a")),
        as_row(int_cell(2), int_cell(2), varchar_cell("b")),
    )
    shifted = (
        as_row(int_cell(1), int_cell(2), varchar_cell("a")),
        as_row(int_cell(2), int_cell(1), varchar_cell("b")),
    )
    changed = (
        as_row(int_cell(1), int_cell(1), varchar_cell("changed")),
        as_row(int_cell(2), int_cell(2), varchar_cell("b")),
    )
    first = project_storage(_request(_ordered_input(original)))
    position = project_storage(_request(_ordered_input(shifted)))
    content = project_storage(_request(_ordered_input(changed)))
    assert first.status is ProjectionStatus.COMPLETE
    assert position.status is ProjectionStatus.COMPLETE
    assert content.status is ProjectionStatus.COMPLETE
    assert first.tables[0].content_digest == position.tables[0].content_digest
    assert first.tables[0].ordering_digest != position.tables[0].ordering_digest
    assert first.tables[0].content_digest != content.tables[0].content_digest


GID_NO_FAULTS: tuple[tuple[str, ProjectionDiagnosticCode, tuple[SourceRow, ...]], ...] = (
    (
        "reserved_gid",
        ProjectionDiagnosticCode.ROW_INTEGRITY,
        (
            as_row(int_cell(4_000_000_000), int_cell(1), varchar_cell("a")),
        ),
    ),
    (
        "duplicate_gid",
        ProjectionDiagnosticCode.KEY_DUPLICATE,
        (
            as_row(int_cell(1), int_cell(1), varchar_cell("a")),
            as_row(int_cell(1), int_cell(2), varchar_cell("b")),
        ),
    ),
    (
        "duplicate_no",
        ProjectionDiagnosticCode.ROW_INTEGRITY,
        (
            as_row(int_cell(1), int_cell(1), varchar_cell("a")),
            as_row(int_cell(2), int_cell(1), varchar_cell("b")),
        ),
    ),
    (
        "missing_no",
        ProjectionDiagnosticCode.ROW_INTEGRITY,
        (
            as_row(int_cell(1), null_cell(), varchar_cell("a")),
        ),
    ),
    (
        "non_continuous_no",
        ProjectionDiagnosticCode.ROW_INTEGRITY,
        (
            as_row(int_cell(1), int_cell(1), varchar_cell("a")),
            as_row(int_cell(2), int_cell(3), varchar_cell("b")),
        ),
    ),
    (
        "negative_gid",
        ProjectionDiagnosticCode.ROW_INTEGRITY,
        (
            as_row(int_cell(-1), int_cell(1), varchar_cell("a")),
        ),
    ),
)


@pytest.mark.parametrize(
    ("label", "code", "rows"),
    GID_NO_FAULTS,
    ids=[item[0] for item in GID_NO_FAULTS],
)
def test_ordered_gid_no_faults(
    label: str, code: ProjectionDiagnosticCode, rows: tuple[SourceRow, ...]
) -> None:
    result = project_storage(_request(_ordered_input(rows)))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert code in _codes(result)


def test_enum_and_set_cell_vectors_match_shared_kernel() -> None:
    enum_codec = CanonicalColumnCodec(
        sql_type=_ENUM_SQL,
        nullable=True,
        family="enum",
        declared_type=_STRING_TYPE,
        labels=("", "active", "paused"),
    )
    set_codec = CanonicalColumnCodec(
        sql_type=_SET_SQL,
        nullable=False,
        family="set",
        labels=("read", "write", "admin"),
    )
    empty_string = encode_typed_scalar(_STRING_TYPE, StringScalar(text="")).scalar_frame
    active = encode_typed_scalar(_STRING_TYPE, StringScalar(text="active")).scalar_frame
    read = encode_typed_scalar(_STRING_TYPE, StringScalar(text="read")).scalar_frame
    write = encode_typed_scalar(_STRING_TYPE, StringScalar(text="write")).scalar_frame
    assert encode_canonical_cell(null_cell(), enum_codec) == _NULL_FRAME
    assert encode_canonical_cell(varchar_cell(""), enum_codec) == empty_string
    assert encode_canonical_cell(null_cell(), enum_codec) != encode_canonical_cell(
        varchar_cell(""), enum_codec
    )
    assert encode_canonical_cell(varchar_cell("active"), enum_codec) == active
    assert encode_canonical_cell(null_cell(), set_codec) == _NULL_FRAME
    empty_set = encode_collection(CollectionSemantics.SEQUENCE, items=()).collection_frame
    assert encode_canonical_cell(set_cell(), set_codec) == empty_set
    assert encode_canonical_cell(null_cell(), set_codec) != encode_canonical_cell(set_cell(), set_codec)
    members = encode_collection(CollectionSemantics.SEQUENCE, items=(read, write)).collection_frame
    assert encode_canonical_cell(set_cell("write", "read"), set_codec) == members
    assert encode_canonical_cell(set_cell("read", "write"), set_codec) == members


def test_enum_set_projection_and_schema_declaration_order() -> None:
    first = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=(
                    int_column("id"),
                    enum_column("kind", "ENUM('a','b')", nullable=True),
                    set_column("flags", "SET('x','y')"),
                ),
                primary_key_columns=("id",),
                rows=(as_row(int_cell(1), varchar_cell("a"), set_cell("y", "x")),),
            )
        )
    )
    swapped = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=(
                    int_column("id"),
                    enum_column("kind", "ENUM('b','a')", nullable=True),
                    set_column("flags", "SET('x','y')"),
                ),
                primary_key_columns=("id",),
                rows=(as_row(int_cell(1), varchar_cell("a"), set_cell("y", "x")),),
            )
        )
    )
    nullable = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=(
                    int_column("id"),
                    enum_column("kind", "ENUM('a','b')", nullable=False),
                    set_column("flags", "SET('x','y')"),
                ),
                primary_key_columns=("id",),
                rows=(as_row(int_cell(1), varchar_cell("a"), set_cell("y", "x")),),
            )
        )
    )
    assert first.status is ProjectionStatus.COMPLETE
    assert swapped.status is ProjectionStatus.COMPLETE
    assert nullable.status is ProjectionStatus.COMPLETE
    assert first.tables[0].schema_digest != swapped.tables[0].schema_digest
    assert first.tables[0].schema_digest != nullable.tables[0].schema_digest
    assert first.import_input is not None
    assert first.import_input.tables[0].columns[1].sql_type == "ENUM('a','b')"


def test_drop_restore_changes_schema_identity() -> None:
    selector = TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value="notes")
    dropped = snapshot_from_records(
        TableRuleRecord(
            selector=selector,
            precedence_class=SelectorPrecedenceClass.STANDARD_EXACT,
            static_role=TableStaticRole.STANDARD_DIFF,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.EXPLICIT_KEYLESS,
            ordered_policy=OrderedPolicy.NONE,
            ignored_columns=("aux",),
            artifact_scope=TableArtifactScope.ALL_CHANGES,
            dropped_columns=(DroppedColumn(name="aux", reason=legacy_ignored_column_reason(selector)),),
        )
    )
    retained = snapshot_from_records(keyless_record())
    columns = (varchar_column("note"), varchar_column("aux"))
    rows = (as_row(varchar_cell("n"), varchar_cell("old")),)
    dropped_result = project_storage(_request(_keyless_input(rows, extra_columns=(varchar_column("aux"),)), ruleset=dropped))
    retained_result = project_storage(_request(_keyless_input(rows, extra_columns=(varchar_column("aux"),)), ruleset=retained))
    changed_dropped = project_storage(
        _request(
            _keyless_input((as_row(varchar_cell("n"), varchar_cell("new")),), extra_columns=(varchar_column("aux"),)),
            ruleset=dropped,
        )
    )
    assert dropped_result.status is ProjectionStatus.COMPLETE
    assert retained_result.status is ProjectionStatus.COMPLETE
    assert changed_dropped.status is ProjectionStatus.COMPLETE
    assert dropped_result.tables[0].schema_digest != retained_result.tables[0].schema_digest
    assert dropped_result.tables[0].storage_view.storage_rule_digest != (
        retained_result.tables[0].storage_view.storage_rule_digest
    )
    assert dropped_result.tables[0].content_digest == changed_dropped.tables[0].content_digest
    assert columns[0].name == "note"


def test_manifest_digest_is_independent_of_table_input_order() -> None:
    ordered = _ordered_input((as_row(int_cell(1), int_cell(1), varchar_cell("a")),))
    keyed = table_input(
        "unknown_widget",
        columns=(int_column("id"),),
        primary_key_columns=("id",),
        rows=(as_row(int_cell(1)),),
    )
    ordered_reader, ordered_binding = ordered
    keyed_reader, keyed_binding = keyed
    first = project_storage(_request(ordered, keyed))
    second = project_storage(
        _request(
            (keyed_reader.reopen(), keyed_binding),
            (ordered_reader.reopen(), ordered_binding),
        )
    )
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.manifest is not None
    assert second.manifest is not None
    assert first.manifest.manifest_digest == second.manifest.manifest_digest
    names = tuple(table.canonical_table for table in first.tables)
    assert names == tuple(sorted(names, key=lambda item: item.encode("utf-8")))
    shuffled = {
        "tables": first.manifest.tables,
        "contract_version": first.manifest.contract_version,
        "source_artifact_digest": first.manifest.source_artifact_digest,
        "storage_projection_version": first.manifest.storage_projection_version,
        "ruleset_id": first.manifest.ruleset_id,
        "ruleset_version": first.manifest.ruleset_version,
        "ruleset_digest": first.manifest.ruleset_digest,
        "tables_document": manifest_document(first.manifest)["tables"],
    }
    assert shuffled["tables_document"] == manifest_document(first.manifest)["tables"]


def test_raw_provenance_digest_is_not_r4_content() -> None:
    rows = (as_row(int_cell(1), int_cell(1), varchar_cell("a")),)
    first = project_storage(
        _request(
            table_input(
                "b1_n1_iec104_syx_list",
                columns=(int_column("gid", nullable=True), int_column("no"), varchar_column("value")),
                primary_key_columns=("gid",),
                rows=rows,
                raw_content_digest=digest_ref("aa"),
            )
        )
    )
    second = project_storage(
        _request(
            table_input(
                "b1_n1_iec104_syx_list",
                columns=(int_column("gid", nullable=True), int_column("no"), varchar_column("value")),
                primary_key_columns=("gid",),
                rows=rows,
                raw_content_digest=digest_ref("bb"),
            )
        )
    )
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.tables[0].content_digest == second.tables[0].content_digest
    assert first.tables[0].schema_digest == second.tables[0].schema_digest
    assert dummy_digest() != digest_ref("aa")


def test_digest_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    original = compute_keyless_content_digest

    def flaky(frames: object) -> DigestRef:
        calls["n"] += 1
        digest = original(frames)  # type: ignore[arg-type]
        if calls["n"] == 2:
            return DigestRef.from_raw_digest(b"\x00" * 32)
        return digest

    monkeypatch.setattr(
        "gateway_backend.capabilities.storage_projection.project.compute_keyless_content_digest",
        flaky,
    )
    result = project_storage(
        _request(
            _keyless_input((as_row(varchar_cell("a")),)),
            ruleset=snapshot_from_records(keyless_record()),
        )
    )
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert ProjectionDiagnosticCode.DIGEST_MISMATCH in _codes(result)


def test_output_write_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> bytes:
        raise OSError("hash sink failed")

    monkeypatch.setattr(
        "gateway_backend.capabilities.storage_projection._digest.encode_canonical_cell",
        boom,
    )
    result = project_storage(
        _request(
            _keyless_input((as_row(varchar_cell("a")),)),
            ruleset=snapshot_from_records(keyless_record()),
        )
    )
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert ProjectionDiagnosticCode.BINDING_INVALID in _codes(result)


MALFORMED_SCALAR: tuple[tuple[str, Callable[[], TableInput]], ...] = (
    (
        "undeclared_enum",
        lambda: table_input(
            "unknown_widget",
            columns=(int_column("id"), enum_column("kind", "ENUM('a','b')")),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), varchar_cell("z")),),
        ),
    ),
    (
        "undeclared_set",
        lambda: table_input(
            "unknown_widget",
            columns=(int_column("id"), set_column("flags", "SET('x','y')")),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), set_cell("z")),),
        ),
    ),
)


@pytest.mark.parametrize(("label", "factory"), MALFORMED_SCALAR, ids=[item[0] for item in MALFORMED_SCALAR])
def test_malformed_enum_set_values_fail_closed(
    label: str, factory: Callable[[], TableInput]
) -> None:
    result = project_storage(_request(factory()))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert ProjectionDiagnosticCode.UNSUPPORTED_TABLE in _codes(result)
