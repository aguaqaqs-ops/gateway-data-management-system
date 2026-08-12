"""Subprocess tests for the private Versioned import recovery admin CLI."""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import pytest

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.mutation_store import IdempotencyKeyHash
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import versioned_import_fingerprint_v1
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.models import (
    MANUAL_RECOVERY_REQUIRED_CODE,
    ImportRequestBinding,
    ManualCorrectionDecision,
    RecoveryAuditAction,
    derive_operation_marker,
    derive_private_ref_name,
)
from gateway_repository_service.versioned_import.package import validate_and_extract_import_package
from gateway_repository_service.versioned_import.worker import ImportWorkerPool
from support.import_admin_cli_harness import (
    DEFAULT_ARTIFACT_ID,
    DEFAULT_OPERATION_ID,
    DEFAULT_REPOSITORY_ID,
    AdminCliControlDbEnvironment,
    AdminCliEnvironment,
    assert_audit_row,
    control_db_digest,
    count_audit_rows,
    load_audit_row,
    parse_stdout_json,
    run_admin_cli,
)
from support.import_worker_harness import MEDIA_TYPE, published_repository_path
from support.lifecycle_harness import lifecycle_settings


def test_invalid_operation_id_exit_2(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    result = run_admin_cli(settings.data_root, "inspect", "--operation-id", "not-a-uuid")
    assert result.returncode == 2


def test_invalid_decision_exit_2(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    result = run_admin_cli(
        settings.data_root,
        "apply",
        "--operation-id",
        str(DEFAULT_OPERATION_ID),
        "--decision",
        "FORCE",
    )
    assert result.returncode == 2


@pytest.mark.serial
def test_root_lock_busy_exit_3(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    lock = DurableRootLock(env.layout.service_lock)
    try:
        lock.acquire()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 3
    finally:
        lock.release()
        env.close()


@pytest.mark.serial
def test_root_lock_busy_with_missing_db_exit_3(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    lock = DurableRootLock(env.layout.service_lock)
    try:
        env.remove_control_db()
        lock.acquire()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 3
        assert "Traceback" not in result.stderr
    finally:
        lock.release()
        env.close()


def test_control_db_newer_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.control_store.close()
        connection = sqlite3.connect(env.settings.control_db_path)
        try:
            connection.execute("PRAGMA user_version = 10")
            connection.commit()
        finally:
            connection.close()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
    finally:
        env.close()


def test_operation_not_found_exit_5(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 5
    finally:
        env.close()


@pytest.mark.parametrize("status_name", ["queued", "running", "succeeded", "ordinary_failed"])
def test_non_manual_operation_exit_5(tmp_path: Path, status_name: str) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    operation_id = uuid4()
    expected_commit_id = "expected-commit-1"
    try:
        if status_name == "queued":
            env.enqueue_operation(
                operation_id=operation_id,
                artifact_id=DEFAULT_ARTIFACT_ID,
                expected_commit_id=expected_commit_id,
            )
        elif status_name == "running":
            env.enqueue_operation(
                operation_id=operation_id,
                artifact_id=DEFAULT_ARTIFACT_ID,
                expected_commit_id=expected_commit_id,
            )
            env.store.claim_if_queued(operation_id)
        elif status_name == "succeeded":
            env.enqueue_operation(
                operation_id=operation_id,
                artifact_id=DEFAULT_ARTIFACT_ID,
                expected_commit_id=expected_commit_id,
            )
            env.store.claim_if_queued(operation_id)
            env.store.mark_succeeded(
                operation_id,
                result=VersionedImportResult(
                    commit_id=expected_commit_id,
                    target_ref="main",
                    artifact_id=DEFAULT_ARTIFACT_ID,
                    canonicalization_manifest_digest="manifest-digest-1",
                    expected_commit_id=expected_commit_id,
                    completed_verification_policy=VerificationPolicy.STRUCTURAL,
                    unknown_type_policy=UnknownTypePolicy.REJECT,
                ),
            )
        else:
            env.enqueue_operation(
                operation_id=operation_id,
                artifact_id=DEFAULT_ARTIFACT_ID,
                expected_commit_id=expected_commit_id,
            )
            env.store.claim_if_queued(operation_id)
            env.store.mark_failed(
                operation_id,
                error=SimpleError(code="IMPORT_REJECTED", message="rejected", request_id=None),
            )

        result = env.run("inspect", "--operation-id", str(operation_id))
        assert result.returncode == 5
    finally:
        env.close()


@pytest.mark.integration
def test_inspect_zero_mutation(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_manual_without_publish()
        db_before = control_db_digest(env.settings.control_db_path)
        audit_before = count_audit_rows(env.settings.control_db_path, DEFAULT_OPERATION_ID)
        artifact_path = artifact_ready_path(env.layout, env.repository_id, DEFAULT_ARTIFACT_ID)
        artifact_before = artifact_path.read_bytes()

        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 0
        summary = parse_stdout_json(result)
        assert summary["marker_inspection"] == "zero"
        assert summary["stable_code"] == MANUAL_RECOVERY_REQUIRED_CODE

        assert control_db_digest(env.settings.control_db_path) == db_before
        assert count_audit_rows(env.settings.control_db_path, DEFAULT_OPERATION_ID) == audit_before
        assert artifact_path.read_bytes() == artifact_before
    finally:
        env.close()


@pytest.mark.integration
def test_apply_not_published_writes_audit(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_manual_without_publish()
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert result.returncode == 0
        summary = parse_stdout_json(result)
        assert summary["decision"] == ManualCorrectionDecision.NOT_PUBLISHED.value
        assert summary["action"] == RecoveryAuditAction.INSPECT_APPLY_NOT_PUBLISHED.value
        assert summary["final_status"] == OperationStatus.FAILED.value
        assert summary["final_code"] == "IMPORT_REJECTED"

        operation = env.store.get_operation(env.repository_id, DEFAULT_OPERATION_ID)
        assert operation is not None
        assert operation.error is not None
        assert operation.error.code == "IMPORT_REJECTED"
        assert operation.error.details == {"reason": "operator_confirmed_not_published"}

        assert_audit_row(
            env.settings.control_db_path,
            DEFAULT_OPERATION_ID,
            action=RecoveryAuditAction.INSPECT_APPLY_NOT_PUBLISHED.value,
            prior_status=OperationStatus.FAILED.value,
            prior_code=MANUAL_RECOVERY_REQUIRED_CODE,
            final_status=OperationStatus.FAILED.value,
            final_code="IMPORT_REJECTED",
        )
        audit = load_audit_row(env.settings.control_db_path, DEFAULT_OPERATION_ID)
        assert audit["evidence_summary"] == summary
        assert summary["stable_code"] == "IMPORT_REJECTED"
    finally:
        env.close()


@pytest.mark.integration
def test_audit_persistence_reopen_control_db(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_manual_without_publish()
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert result.returncode == 0
        env.control_store.close()

        audit = load_audit_row(env.settings.control_db_path, DEFAULT_OPERATION_ID)
        evidence = audit["evidence_summary"]
        assert isinstance(evidence, dict)
        assert evidence["decision"] == ManualCorrectionDecision.NOT_PUBLISHED.value
        assert "token" not in json.dumps(evidence)
        assert "replay_sql" not in json.dumps(evidence)
    finally:
        env.close()


@pytest.mark.integration
def test_apply_succeeded_real_dolt_evidence(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        candidate = env.setup_manual_with_published_evidence()
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.SUCCEEDED.value,
        )
        assert result.returncode == 0
        summary = parse_stdout_json(result)
        assert summary["decision"] == ManualCorrectionDecision.SUCCEEDED.value
        assert summary["action"] == RecoveryAuditAction.INSPECT_APPLY_SUCCESS.value
        assert summary["final_status"] == OperationStatus.SUCCEEDED.value
        assert summary["candidate_commit_id"] == candidate
        assert summary["main_commit_id"] == candidate

        operation = env.store.get_operation(env.repository_id, DEFAULT_OPERATION_ID)
        assert operation is not None
        assert operation.status == OperationStatus.SUCCEEDED
        assert operation.result is not None
        assert operation.result.commit_id == candidate

        assert_audit_row(
            env.settings.control_db_path,
            DEFAULT_OPERATION_ID,
            action=RecoveryAuditAction.INSPECT_APPLY_SUCCESS.value,
            prior_status=OperationStatus.FAILED.value,
            prior_code=MANUAL_RECOVERY_REQUIRED_CODE,
            final_status=OperationStatus.SUCCEEDED.value,
            final_code=None,
        )
        audit = load_audit_row(env.settings.control_db_path, DEFAULT_OPERATION_ID)
        assert audit["evidence_summary"] == summary
    finally:
        env.close()


@pytest.mark.integration
def test_stale_evidence_apply_succeeded_exit_6(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        candidate = env.setup_manual_with_published_evidence()
        other_operation = uuid4()
        other_ref = derive_private_ref_name(other_operation)
        other_marker = derive_operation_marker(other_operation)
        env.provider.create_private_ref(other_ref, candidate)
        env.provider.checkout_private_ref(other_ref)
        new_head = env.provider.commit_operation_marker(other_ref, other_marker)
        env.provider.publish_main(candidate, new_head)
        assert env.provider.read_ref("main") == new_head
        assert new_head != candidate

        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.SUCCEEDED.value,
        )
        assert result.returncode == 6
        assert count_audit_rows(env.settings.control_db_path, DEFAULT_OPERATION_ID) == 0
    finally:
        env.close()


@pytest.mark.integration
def test_ambiguous_marker_exit_6(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_manual_without_publish()
        context = env.store.load_execution_context(DEFAULT_OPERATION_ID)
        assert context is not None
        marker = context.operation_marker
        expected = context.expected_commit_id
        private_ref = derive_private_ref_name(DEFAULT_OPERATION_ID)

        staging_dir = env.layout.staging_artifacts / "ambiguous-setup"
        staging_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifact_path = artifact_ready_path(env.layout, env.repository_id, context.artifact_id)
            package = validate_and_extract_import_package(
                artifact_path=artifact_path,
                expected_size_bytes=context.artifact_size_bytes,
                expected_raw_sha256=context.artifact_raw_sha256,
                staging_dir=staging_dir,
                settings=env.settings,
            )
            repository = published_repository_path(env.layout, env.repository_id)
            runner = DoltRunner(env.settings, env.layout.root)
            timeout = env.settings.import_timeout_seconds
            env.provider.create_private_ref(private_ref, expected)
            env.provider.checkout_private_ref(private_ref)
            env.provider.replay_sql(private_ref, package.replay_sql_path)
            env.provider.commit_operation_marker(private_ref, marker)
            runner.run(
                "create_ambiguity_branch",
                ["checkout", "-b", "gateway-import-ambiguityprobe"],
                cwd=repository,
                timeout=timeout,
            )
            runner.run(
                "ambiguity_schema",
                ["sql", "-q", "CREATE TABLE ambiguity_probe (id BIGINT PRIMARY KEY);"],
                cwd=repository,
                timeout=timeout,
            )
            runner.run(
                "ambiguity_commit",
                ["commit", "-Am", marker],
                cwd=repository,
                timeout=timeout,
            )
            inspection = env.provider.inspect_marker(marker)
            from gateway_repository_service.versioned_import.ports import MarkerInspectionAmbiguous

            assert isinstance(inspection, MarkerInspectionAmbiguous)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)

        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert result.returncode == 6
    finally:
        env.close()


@pytest.mark.integration
def test_missing_artifact_exit_6(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.enqueue_operation(
            operation_id=DEFAULT_OPERATION_ID,
            artifact_id=DEFAULT_ARTIFACT_ID,
            write_artifact_file=False,
        )
        env.mark_manual(DEFAULT_OPERATION_ID)
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.SUCCEEDED.value,
        )
        assert result.returncode == 6
    finally:
        env.close()


@pytest.mark.integration
def test_invalid_artifact_exit_6(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.enqueue_operation(operation_id=DEFAULT_OPERATION_ID, artifact_id=DEFAULT_ARTIFACT_ID)
        env.mark_manual(DEFAULT_OPERATION_ID)
        ready_path = artifact_ready_path(env.layout, env.repository_id, DEFAULT_ARTIFACT_ID)
        ready_path.write_bytes(b"not-a-valid-package")
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.SUCCEEDED.value,
        )
        assert result.returncode == 6
    finally:
        env.close()


@pytest.mark.integration
def test_duplicate_apply_exit_5_without_second_audit(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_manual_without_publish()
        first = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert first.returncode == 0
        assert count_audit_rows(env.settings.control_db_path, DEFAULT_OPERATION_ID) == 1

        second = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert second.returncode == 5
        assert count_audit_rows(env.settings.control_db_path, DEFAULT_OPERATION_ID) == 1
    finally:
        env.close()


@pytest.mark.integration
@pytest.mark.serial
def test_manual_barrier_cleared_after_apply_allows_dispatch(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_manual_without_publish()
        second_artifact = uuid4()
        second_operation = uuid4()
        size_bytes, raw_sha256 = env.write_ready_artifact(second_artifact)
        env.seed_artifact_lifecycle(second_artifact, size_bytes=size_bytes, raw_sha256=raw_sha256)
        binding = ImportRequestBinding(
            repository_id=env.repository_id,
            artifact_ref=RepositoryArtifactRef(
                artifact_id=second_artifact,
                media_type=MEDIA_TYPE,
                size_bytes=size_bytes,
                raw_sha256=raw_sha256,
            ),
            target_ref="main",
            expected_commit_id=env.provider.read_ref("main"),
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )
        key_hash = IdempotencyKeyHash.from_raw_key("queued-behind-barrier")
        fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
        env.store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=fingerprint,
            operation_id=second_operation,
        )
        assert env.store.has_unresolved_manual_barrier(env.repository_id) is True

        apply_result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert apply_result.returncode == 0
        assert env.store.has_unresolved_manual_barrier(env.repository_id) is False

        pool = ImportWorkerPool(
            settings=env.settings,
            layout=env.layout,
            store=env.store,
            provider_factory=lambda _repository_id: env.provider,
            locks=RepositoryLockRegistry(),
        )
        pool.start()
        try:
            pool.notify()
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                updated = env.store.get_operation(env.repository_id, second_operation)
                if updated is not None and updated.status in {
                    OperationStatus.SUCCEEDED,
                    OperationStatus.FAILED,
                }:
                    break
                time.sleep(0.05)
            updated = env.store.get_operation(env.repository_id, second_operation)
            assert updated is not None
            assert updated.status == OperationStatus.SUCCEEDED, updated
        finally:
            pool.stop()
    finally:
        env.close()


def test_control_db_v6_exit_4_no_migration(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.downgrade_control_db_to_v6()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
        connection = sqlite3.connect(env.settings.control_db_path)
        try:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            connection.close()
        assert version == 6
        assert "repository_import_recovery_audit" not in tables
    finally:
        env.close()


def test_control_db_missing_operations_table_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.drop_import_operations_table()
        env.control_store.close()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_control_db_missing_file_exit_4(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    result = run_admin_cli(settings.data_root, "inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
    assert result.returncode == 4
    assert "Traceback" not in result.stderr


def test_operation_not_found_dolt_unavailable_exit_5(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.control_store.close()
        missing_dolt = tmp_path / "missing-dolt"
        result = env.run(
            "inspect",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            env={"GATEWAY_REPOSITORY_DOLT_BINARY": str(missing_dolt)},
        )
        assert result.returncode == 5
        assert "Traceback" not in result.stderr
    finally:
        env.close()


@pytest.mark.integration
def test_published_then_advanced_not_published_exit_6(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_published_then_main_advanced()
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert result.returncode == 6
        assert count_audit_rows(env.settings.control_db_path, DEFAULT_OPERATION_ID) == 0
    finally:
        env.close()


@pytest.mark.integration
def test_missing_artifact_not_published_exit_6(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.enqueue_operation(
            operation_id=DEFAULT_OPERATION_ID,
            artifact_id=DEFAULT_ARTIFACT_ID,
            write_artifact_file=False,
        )
        env.mark_manual(DEFAULT_OPERATION_ID)
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert result.returncode == 6
        assert count_audit_rows(env.settings.control_db_path, DEFAULT_OPERATION_ID) == 0
    finally:
        env.close()


def test_collect_recovery_evidence_returns_none_on_provider_private_ref_probe_failure(
    tmp_path: Path,
) -> None:
    from gateway_repository_service.versioned_import.errors import ImportProviderError
    from gateway_repository_service.versioned_import.recovery import collect_recovery_evidence
    from support.import_worker_harness import FakeImportProvider, WorkerTestEnvironment

    repository_id = DEFAULT_REPOSITORY_ID
    artifact_id = DEFAULT_ARTIFACT_ID
    operation_id = DEFAULT_OPERATION_ID

    env = WorkerTestEnvironment(tmp_path)
    try:
        operation_id = env.enqueue(repository_id, artifact_id=artifact_id, operation_id=operation_id)
        context = env.store.load_execution_context(operation_id)
        assert context is not None
        provider = FakeImportProvider()

        def failing_private_ref_exists(private_ref: str) -> bool:
            raise ImportProviderError("branch list failed")

        provider.private_ref_exists = failing_private_ref_exists  # type: ignore[method-assign]

        evidence = collect_recovery_evidence(
            settings=env.settings,
            layout=env.layout,
            store=env.store,
            provider=provider,
            context=context,
        )
        assert evidence is None
    finally:
        env.close()


@pytest.mark.integration
def test_unverified_private_candidate_not_published_import_rejected(tmp_path: Path) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_manual_with_private_candidate_unverified()
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert result.returncode == 0
        summary = parse_stdout_json(result)
        assert summary["final_code"] == "IMPORT_REJECTED"
        assert summary.get("stable_code") == "IMPORT_REJECTED"
        operation = env.store.get_operation(env.repository_id, DEFAULT_OPERATION_ID)
        assert operation is not None
        assert operation.error is not None
        assert operation.error.code == "IMPORT_REJECTED"
    finally:
        env.close()


@pytest.mark.integration
def test_unverified_private_candidate_missing_artifact_not_published_exit_6(
    tmp_path: Path,
) -> None:
    env = AdminCliEnvironment.create(tmp_path)
    try:
        env.setup_manual_with_private_candidate_unverified()
        ready_path = artifact_ready_path(env.layout, env.repository_id, DEFAULT_ARTIFACT_ID)
        ready_path.unlink()
        result = env.run(
            "apply",
            "--operation-id",
            str(DEFAULT_OPERATION_ID),
            "--decision",
            ManualCorrectionDecision.NOT_PUBLISHED.value,
        )
        assert result.returncode == 6
        assert count_audit_rows(env.settings.control_db_path, DEFAULT_OPERATION_ID) == 0
    finally:
        env.close()


def test_control_db_corrupt_operations_schema_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.corrupt_operations_schema()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_control_db_non_sqlite_file_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.write_non_sqlite_control_db()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_inspect_delete_journal_mode_exit_4_no_mutation(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.set_journal_mode("DELETE")
        env.control_store.close()
        db_before = control_db_digest(env.settings.control_db_path)
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
        assert control_db_digest(env.settings.control_db_path) == db_before
    finally:
        env.close()


def test_control_db_noop_trigger_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.replace_trigger_with_noop("prevent_succeeded_when_terminal")
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_control_db_corrupt_operations_column_types_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.corrupt_operations_column_types()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_control_db_missing_table_constraints_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.strip_operations_table_constraints()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_control_db_case_sensitive_check_literal_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.corrupt_operations_check_literal_case()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_control_db_case_sensitive_trigger_literal_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.corrupt_trigger_succeeded_literal_case()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_admin_cli_ddl_signature_preserves_string_literals() -> None:
    from gateway_repository_service.control_db import _admin_cli_ddl_signature

    main_check = "CHECK (target_ref = 'main')"
    main_upper_check = "CHECK (target_ref = 'MAIN')"
    assert _admin_cli_ddl_signature(main_check) != _admin_cli_ddl_signature(main_upper_check)


def test_control_db_malformed_operation_row_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.insert_malformed_operation_row(DEFAULT_OPERATION_ID)
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
        assert "control database contains invalid operation data" in result.stderr
    finally:
        env.close()


def test_malformed_layout_json_exit_4(tmp_path: Path) -> None:
    env = AdminCliControlDbEnvironment.create(tmp_path)
    try:
        env.write_malformed_layout_marker()
        result = env.run("inspect", "--operation-id", str(DEFAULT_OPERATION_ID))
        assert result.returncode == 4
        assert "Traceback" not in result.stderr
    finally:
        env.close()


def test_inspect_missing_data_root_exit_4_no_side_effects(tmp_path: Path) -> None:
    missing_root = tmp_path / "does-not-exist"
    assert not missing_root.exists()
    result = run_admin_cli(
        missing_root,
        "inspect",
        "--operation-id",
        str(DEFAULT_OPERATION_ID),
    )
    assert result.returncode == 4
    assert "Traceback" not in result.stderr
    assert not missing_root.exists()
