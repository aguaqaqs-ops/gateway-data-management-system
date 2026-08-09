"""Durable evidence helpers for real Dolt import crash-recovery tests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.faults import ImportWorkerFaultPoint
from gateway_repository_service.versioned_import.models import derive_private_ref_name
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.ports import (
    MarkerInspectionUnique,
    MarkerInspectionZero,
)

MarkerKind = Literal["absent", "zero", "unique"]
PrivateRefHead = Literal["expected", "candidate"]
RECORDS_TABLE = "records"
REPLAY_AUDIT_TABLE = "import_replay_audit"


@dataclass(frozen=True, slots=True)
class CrashStateExpectation:
    operation_status: OperationStatus
    replay_count: int
    main_ref: Literal["expected", "candidate"]
    private_ref_exists: bool
    private_ref_head: PrivateRefHead | None
    marker_kind: MarkerKind
    marker_refs_contain: tuple[str, ...] | None
    records_on_private: int | None
    records_on_main: int | None
    artifact_present: bool


def _refs_for_private_ref(private_ref: str) -> tuple[str, ...]:
    return (private_ref,)


def _refs_for_main_and_private(private_ref: str) -> tuple[str, ...]:
    return ("main", private_ref)


def _refs_for_main_only() -> tuple[str, ...]:
    return ("main",)


_CRASH_STATE: dict[ImportWorkerFaultPoint, CrashStateExpectation] = {
    ImportWorkerFaultPoint.AFTER_RUNNING_CLAIM: CrashStateExpectation(
        operation_status=OperationStatus.RUNNING,
        replay_count=0,
        main_ref="expected",
        private_ref_exists=False,
        private_ref_head=None,
        marker_kind="zero",
        marker_refs_contain=None,
        records_on_private=None,
        records_on_main=0,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_PACKAGE_EXTRACTED: CrashStateExpectation(
        operation_status=OperationStatus.RUNNING,
        replay_count=0,
        main_ref="expected",
        private_ref_exists=False,
        private_ref_head=None,
        marker_kind="zero",
        marker_refs_contain=None,
        records_on_private=None,
        records_on_main=0,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED: CrashStateExpectation(
        operation_status=OperationStatus.RUNNING,
        replay_count=0,
        main_ref="expected",
        private_ref_exists=True,
        private_ref_head="expected",
        marker_kind="zero",
        marker_refs_contain=None,
        records_on_private=0,
        records_on_main=0,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_REPLAY_BEFORE_MARKER: CrashStateExpectation(
        operation_status=OperationStatus.RUNNING,
        replay_count=0,
        main_ref="expected",
        private_ref_exists=True,
        private_ref_head="expected",
        marker_kind="zero",
        marker_refs_contain=None,
        records_on_private=1,
        records_on_main=0,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION: CrashStateExpectation(
        operation_status=OperationStatus.RUNNING,
        replay_count=0,
        main_ref="expected",
        private_ref_exists=True,
        private_ref_head="candidate",
        marker_kind="unique",
        marker_refs_contain=None,
        records_on_private=1,
        records_on_main=0,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_VERIFICATION_BEFORE_SECOND_MAIN_CHECK: CrashStateExpectation(
        operation_status=OperationStatus.RUNNING,
        replay_count=0,
        main_ref="expected",
        private_ref_exists=True,
        private_ref_head="candidate",
        marker_kind="unique",
        marker_refs_contain=None,
        records_on_private=1,
        records_on_main=0,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_SECOND_MAIN_CHECK_BEFORE_PUBLISH: CrashStateExpectation(
        operation_status=OperationStatus.RUNNING,
        replay_count=0,
        main_ref="expected",
        private_ref_exists=True,
        private_ref_head="candidate",
        marker_kind="unique",
        marker_refs_contain=None,
        records_on_private=1,
        records_on_main=0,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED: CrashStateExpectation(
        operation_status=OperationStatus.RUNNING,
        replay_count=0,
        main_ref="candidate",
        private_ref_exists=True,
        private_ref_head="candidate",
        marker_kind="unique",
        marker_refs_contain=None,
        records_on_private=1,
        records_on_main=1,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_PRIVATE_REF_CLEANUP: CrashStateExpectation(
        operation_status=OperationStatus.SUCCEEDED,
        replay_count=0,
        main_ref="candidate",
        private_ref_exists=True,
        private_ref_head="candidate",
        marker_kind="unique",
        marker_refs_contain=None,
        records_on_private=1,
        records_on_main=1,
        artifact_present=True,
    ),
    ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP: CrashStateExpectation(
        operation_status=OperationStatus.SUCCEEDED,
        replay_count=0,
        main_ref="candidate",
        private_ref_exists=False,
        private_ref_head=None,
        marker_kind="unique",
        marker_refs_contain=None,
        records_on_private=None,
        records_on_main=1,
        artifact_present=True,
    ),
}


def _marker_refs_for_fault(
    fault_point: ImportWorkerFaultPoint,
    private_ref: str,
) -> tuple[str, ...] | None:
    if fault_point in {
        ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION,
        ImportWorkerFaultPoint.AFTER_VERIFICATION_BEFORE_SECOND_MAIN_CHECK,
        ImportWorkerFaultPoint.AFTER_SECOND_MAIN_CHECK_BEFORE_PUBLISH,
    }:
        return _refs_for_private_ref(private_ref)
    if fault_point in {
        ImportWorkerFaultPoint.AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED,
        ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_PRIVATE_REF_CLEANUP,
    }:
        return _refs_for_main_and_private(private_ref)
    if fault_point == ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP:
        return _refs_for_main_only()
    return None


def _query_row_count(
    provider: CandidateAImportProvider,
    table: str,
    *,
    revision: str | None = None,
) -> int:
    rows = provider._cli.query_json(  # noqa: SLF001
        f"{table}_count",
        f"SELECT COUNT(*) AS row_count FROM {table};\n",
        revision=revision,
    )
    if not rows:
        raise AssertionError(f"expected row count for {table}, got empty query result")
    row = rows[0]
    raw = row.get("row_count", row.get("COUNT(*)", None))
    if raw is None:
        raise AssertionError(f"expected row count column for {table}, got {row!r}")
    return int(raw)


def table_exists(
    provider: CandidateAImportProvider,
    table: str,
    *,
    revision: str | None = None,
) -> bool:
    rows = provider._cli.query_json(  # noqa: SLF001
        f"{table}_exists",
        "SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = DATABASE() AND table_name = '{table}';\n",
        revision=revision,
    )
    return bool(rows)


def table_row_count(
    provider: CandidateAImportProvider,
    table: str,
    *,
    revision: str | None = None,
) -> int:
    if not table_exists(provider, table, revision=revision):
        return 0
    return _query_row_count(provider, table, revision=revision)


def records_row_count(
    provider: CandidateAImportProvider,
    *,
    revision: str = "main",
) -> int:
    return table_row_count(provider, RECORDS_TABLE, revision=revision)


def replay_audit_row_count(
    provider: CandidateAImportProvider,
    *,
    revision: str | None = None,
) -> int:
    return table_row_count(provider, REPLAY_AUDIT_TABLE, revision=revision)


def assert_replay_audit_table_absent(
    provider: CandidateAImportProvider,
    *,
    revision: str = "main",
) -> None:
    assert not table_exists(provider, REPLAY_AUDIT_TABLE, revision=revision), (
        f"{REPLAY_AUDIT_TABLE} must not exist on {revision}"
    )


def assert_main_ref(provider: CandidateAImportProvider, expected_commit: str) -> None:
    actual = provider.read_ref("main")
    assert actual == expected_commit, f"main ref mismatch: expected {expected_commit}, got {actual}"


def assert_private_ref(
    provider: CandidateAImportProvider,
    operation_id: UUID,
    *,
    exists: bool,
    head: str | None = None,
) -> None:
    private_ref = derive_private_ref_name(operation_id)
    actual_exists = provider.private_ref_exists(private_ref)
    assert actual_exists is exists, (
        f"private ref {private_ref} existence mismatch: expected {exists}, got {actual_exists}"
    )
    if exists and head is not None:
        actual_head = provider.read_ref(private_ref)
        assert actual_head == head, f"private ref head mismatch: expected {head}, got {actual_head}"


def assert_marker_inspection(
    provider: CandidateAImportProvider,
    marker: str,
    *,
    kind: MarkerKind,
    parent: str | None = None,
    refs_contain: str | tuple[str, ...] | None = None,
) -> str | None:
    if kind == "absent":
        return None
    inspection = provider.inspect_marker(marker)
    if kind == "zero":
        assert isinstance(inspection, MarkerInspectionZero), (
            f"expected zero marker evidence, got {inspection!r}"
        )
        return None
    assert isinstance(inspection, MarkerInspectionUnique), (
        f"expected unique marker evidence, got {inspection!r}"
    )
    if parent is not None:
        assert inspection.parent == parent, (
            f"marker parent mismatch: expected {parent}, got {inspection.parent}"
        )
    if refs_contain is not None:
        required = (refs_contain,) if isinstance(refs_contain, str) else refs_contain
        for ref in required:
            assert ref in inspection.refs, (
                f"marker refs {inspection.refs!r} missing required ref {ref!r}"
            )
    return inspection.candidate


def assert_artifact_bytes(
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
    *,
    size_bytes: int,
    raw_sha256: str,
    present: bool,
) -> None:
    path = artifact_ready_path(layout, repository_id, artifact_id)
    if not present:
        assert not path.exists(), f"artifact {artifact_id} should be absent at {path}"
        return
    assert path.is_file(), f"artifact {artifact_id} missing at {path}"
    payload = path.read_bytes()
    assert len(payload) == size_bytes, (
        f"artifact size mismatch: expected {size_bytes}, got {len(payload)}"
    )
    digest = hashlib.sha256(payload).hexdigest()
    assert digest == raw_sha256, f"artifact hash mismatch: expected {raw_sha256}, got {digest}"


def _resolve_candidate_commit(
    provider: CandidateAImportProvider,
    operation_marker: str,
    expected_commit: str,
    *,
    refs_contain: str | tuple[str, ...] | None = None,
) -> str:
    candidate = assert_marker_inspection(
        provider,
        operation_marker,
        kind="unique",
        parent=expected_commit,
        refs_contain=refs_contain,
    )
    assert candidate is not None
    return candidate


def assert_crash_state_evidence(
    *,
    fault_point: ImportWorkerFaultPoint,
    provider: CandidateAImportProvider,
    store: ImportOperationStore,
    layout: DurableLayout,
    repository_id: UUID,
    operation_id: UUID,
    expected_commit: str,
) -> None:
    expectation = _CRASH_STATE[fault_point]
    operation = store.get_operation(repository_id, operation_id)
    assert operation is not None
    context = store.load_execution_context(operation_id)
    assert context is not None
    assert operation.status == expectation.operation_status
    assert store.get_automatic_replay_count(operation_id) == expectation.replay_count

    private_ref = derive_private_ref_name(operation_id)
    marker_refs = _marker_refs_for_fault(fault_point, private_ref)

    candidate: str | None = None
    if expectation.marker_kind == "unique":
        assert operation.operation_marker
        candidate = _resolve_candidate_commit(
            provider,
            operation.operation_marker,
            expected_commit,
            refs_contain=marker_refs,
        )
    elif expectation.marker_kind == "zero":
        assert operation.operation_marker
        assert_marker_inspection(provider, operation.operation_marker, kind="zero")

    if expectation.main_ref == "expected":
        assert_main_ref(provider, expected_commit)
    else:
        assert candidate is not None
        assert_main_ref(provider, candidate)

    if expectation.private_ref_exists:
        head: str | None = None
        if expectation.private_ref_head == "expected":
            head = expected_commit
        elif expectation.private_ref_head == "candidate":
            assert candidate is not None
            head = candidate
        assert_private_ref(provider, operation_id, exists=True, head=head)
    else:
        assert_private_ref(provider, operation_id, exists=False)

    if expectation.records_on_main is not None:
        assert records_row_count(provider, revision="main") == expectation.records_on_main
    if expectation.records_on_private is not None:
        assert (
            records_row_count(provider, revision=private_ref) == expectation.records_on_private
        )

    assert_artifact_bytes(
        layout,
        repository_id,
        operation.artifact_id,
        size_bytes=context.artifact_size_bytes,
        raw_sha256=context.artifact_raw_sha256,
        present=expectation.artifact_present,
    )


def assert_final_state_evidence(
    *,
    fault_point: ImportWorkerFaultPoint,
    provider: CandidateAImportProvider,
    store: ImportOperationStore,
    layout: DurableLayout,
    repository_id: UUID,
    operation_id: UUID,
    expected_commit: str,
    terminal: OperationStatus,
) -> None:
    operation = store.get_operation(repository_id, operation_id)
    assert operation is not None
    context = store.load_execution_context(operation_id)

    if fault_point in {
        ImportWorkerFaultPoint.AFTER_RUNNING_CLAIM,
        ImportWorkerFaultPoint.AFTER_PACKAGE_EXTRACTED,
    }:
        if terminal == OperationStatus.SUCCEEDED:
            assert operation.result is not None
            assert_main_ref(provider, operation.result.commit_id)
            assert_private_ref(provider, operation_id, exists=False)
            assert records_row_count(provider, revision="main") == 1
        else:
            assert operation.operation_marker
            assert_marker_inspection(provider, operation.operation_marker, kind="zero")
            assert_main_ref(provider, expected_commit)
            assert_private_ref(provider, operation_id, exists=False)
            assert records_row_count(provider, revision="main") == 0
        return

    if fault_point == ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED:
        if terminal == OperationStatus.FAILED:
            assert_main_ref(provider, expected_commit)
            assert_private_ref(provider, operation_id, exists=True)
            assert (
                records_row_count(provider, revision=derive_private_ref_name(operation_id)) == 0
            )
        return

    if terminal == OperationStatus.SUCCEEDED:
        assert operation.result is not None
        assert_main_ref(provider, operation.result.commit_id)
        assert_private_ref(provider, operation_id, exists=False)
        assert records_row_count(provider, revision="main") == 1
        if fault_point == ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION:
            assert operation.operation_marker
            assert isinstance(
                provider.inspect_marker(operation.operation_marker),
                MarkerInspectionUnique,
            )
        if fault_point == ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP:
            assert context is not None
            assert_artifact_bytes(
                layout,
                repository_id,
                operation.artifact_id,
                size_bytes=context.artifact_size_bytes,
                raw_sha256=context.artifact_raw_sha256,
                present=False,
            )
        return


def assert_fault_point_evidence(
    *,
    fault_point: ImportWorkerFaultPoint,
    provider: CandidateAImportProvider,
    store: ImportOperationStore,
    repository_id: UUID,
    operation_id: UUID,
    expected_commit: str,
    terminal: OperationStatus,
    layout: DurableLayout | None = None,
) -> None:
    resolved_layout = layout if layout is not None else provider._layout  # noqa: SLF001
    assert_final_state_evidence(
        fault_point=fault_point,
        provider=provider,
        store=store,
        layout=resolved_layout,
        repository_id=repository_id,
        operation_id=operation_id,
        expected_commit=expected_commit,
        terminal=terminal,
    )
