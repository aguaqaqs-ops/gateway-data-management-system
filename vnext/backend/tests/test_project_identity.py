"""The project identity rule compares complete canonical version-manager entries."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.project_identity import (
    ProjectIdentityInput,
    ProjectIdentityStatus,
    assess_project_identity,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotTableDescriptor,
    SnapshotTableReader,
)
from gateway_backend.capabilities.table_access.contracts import SourceRow
from tests.support.snapshot_materialization import materialize_sql

pytestmark = pytest.mark.unit

IDENTITY_ASSESSMENT_CASES = (
    pytest.param(
        (("version", "build", "no"), (("v1", "b1", "old"),)),
        (("no", "build", "version"), (("new", "b1", "v1"),)),
        ProjectIdentityStatus.SAME_PROJECT,
        id="column-order-does-not-change-complete-entry",
    ),
    pytest.param(
        (("version", "no"), (("v1", "before"),)),
        (("version", "no"), (("v2", "after"),)),
        ProjectIdentityStatus.DIFFERENT_PROJECT,
        id="disjoint-complete-entries",
    ),
    pytest.param(
        (("version", "no"), (("v1", "before"),)),
        (("version", "no"), (("v1", "after"),)),
        ProjectIdentityStatus.SAME_PROJECT,
        id="no-column-is-excluded",
    ),
    pytest.param(
        None,
        (("version",), (("v1",),)),
        ProjectIdentityStatus.UNVERIFIABLE,
        id="missing-version-manager-table",
    ),
    pytest.param(
        (("version",), ()),
        (("version",), (("v1",),)),
        ProjectIdentityStatus.UNVERIFIABLE,
        id="empty-version-manager-table",
    ),
    pytest.param(
        (("no",), (("before",),)),
        (("no",), (("after",),)),
        ProjectIdentityStatus.UNVERIFIABLE,
        id="no-identity-column-remains",
    ),
    pytest.param(
        (("version", "build"), (("v1", "b1"),)),
        (("version", "release"), (("v1", "b1"),)),
        ProjectIdentityStatus.UNVERIFIABLE,
        id="identity-column-set-mismatch",
    ),
    pytest.param(
        (("version",), ((None,),)),
        (("version",), (("",),)),
        ProjectIdentityStatus.DIFFERENT_PROJECT,
        id="null-and-empty-string-remain-distinct",
    ),
    pytest.param(
        (("version",), ((" A ",),)),
        (("version",), (("a",),)),
        ProjectIdentityStatus.DIFFERENT_PROJECT,
        id="identity-values-are-not-trimmed-or-case-folded",
    ),
)


def _sql_for_table(
    shape: tuple[tuple[str, ...], tuple[tuple[object | None, ...], ...]] | None,
) -> str:
    if shape is None:
        return "CREATE TABLE unrelated (value VARCHAR(32)); INSERT INTO unrelated VALUES ('x');"
    columns, rows = shape
    definitions = ", ".join(f"`{column}` VARCHAR(32)" for column in columns)
    statements = [f"CREATE TABLE version_manager ({definitions});"]
    for row in rows:
        values = ", ".join(
            "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"
            for value in row
        )
        statements.append(f"INSERT INTO version_manager VALUES ({values});")
    return " ".join(statements)


def _identity_input(
    shape: tuple[tuple[str, ...], tuple[tuple[object | None, ...], ...]] | None,
) -> ProjectIdentityInput:
    result = materialize_sql(
        _sql_for_table(shape),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.snapshot is not None
    assert result.table_set is not None
    return ProjectIdentityInput(result.snapshot.snapshot_digest, result.table_set)


@pytest.mark.parametrize(
    ("before_shape", "current_shape", "expected_status"),
    IDENTITY_ASSESSMENT_CASES,
)
def test_identity_assessment_compares_complete_version_manager_entries(
    before_shape: tuple[tuple[str, ...], tuple[tuple[object | None, ...], ...]] | None,
    current_shape: tuple[tuple[str, ...], tuple[tuple[object | None, ...], ...]] | None,
    expected_status: ProjectIdentityStatus,
) -> None:
    assessment = assess_project_identity(
        _identity_input(before_shape),
        _identity_input(current_shape),
    )

    assert assessment.status is expected_status
    assert assessment.schema_version == "project-identity-assessment/v1"
    assert assessment.rule_version == "version-manager-overlap/v1"
    if expected_status is ProjectIdentityStatus.UNVERIFIABLE:
        assert assessment.diagnostics
    else:
        assert assessment.before_entry_set_digest is not None
        assert assessment.current_entry_set_digest is not None
        assert assessment.comparable_columns
        document = assessment.to_document()
        document.pop("assessment_digest")
        assert assessment.assessment_digest == raw_blob_digest(canonicalize_json_value(document))


def test_identity_assessment_does_not_publish_source_entries() -> None:
    assessment = assess_project_identity(
        _identity_input((("version",), (("private-version",),))),
        _identity_input((("version",), (("private-version",),))),
    )

    assert "private-version" not in str(assessment.to_document())


def test_identity_assessment_turns_table_reader_failure_into_unverifiable() -> None:
    before = _identity_input((("version",), (("v1",),)))
    assert before.table_set is not None
    table = before.table_set.tables[0]

    class BrokenReader:
        def descriptor(self) -> SnapshotTableDescriptor:
            return table.descriptor

        def iter_rows(self) -> Iterator[SourceRow]:
            raise OSError("fixture read failure")

        def close(self) -> None:
            return None

        def reopen(self) -> SnapshotTableReader:
            return self

    broken_table = replace(table, reader=BrokenReader())
    broken_set = replace(before.table_set, tables=(broken_table,))
    broken = replace(before, table_set=broken_set)
    assessment = assess_project_identity(broken, _identity_input((("version",), (("v1",),))))

    assert assessment.status is ProjectIdentityStatus.UNVERIFIABLE
    assert assessment.diagnostics == ("VERSION_MANAGER_READ_FAILED",)
