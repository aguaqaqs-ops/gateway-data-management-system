"""Shared helpers for Versioned import admin CLI subprocess tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from gateway_repository_contracts import RepositoryArtifactRef, SimpleError, UnknownTypePolicy, VerificationPolicy
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import IdempotencyKeyHash, configure_connection
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.models import (
    MANUAL_RECOVERY_REQUIRED_CODE,
    ImportRequestBinding,
    derive_operation_marker,
    derive_private_ref_name,
    versioned_import_fingerprint_v1,
)
from gateway_repository_service.versioned_import.package import validate_and_extract_import_package
from gateway_repository_service.versioned_import.ports import PublishMainPublished
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.store import ImportOperationStore
from support.import_worker_harness import MEDIA_TYPE, published_repository_path
from support.lifecycle_harness import lifecycle_settings
from test_import_package import build_package_bytes, write_artifact

FORBIDDEN_AUDIT_KEYS = frozenset(
    {
        "token",
        "idempotency_key",
        "replay_sql",
        "stderr",
        "host_path",
        "credential",
        "raw_sha256",
        "private_ref_name",
        "operation_marker",
    }
)

DEFAULT_REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
DEFAULT_ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
DEFAULT_OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")


def run_admin_cli(
    settings_data_root: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "gateway_repository_service.versioned_import.admin",
        *args,
        "--data-root",
        str(settings_data_root),
    ]
    merged_env = os.environ.copy()
    merged_env.setdefault("GATEWAY_REPOSITORY_PROFILE", "test")
    merged_env.setdefault("GATEWAY_REPOSITORY_ARTIFACT_BROKER_MODE", "inprocess")
    if env is not None:
        merged_env.update(env)
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=merged_env,
        timeout=120,
    )


def parse_stdout_json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    line = result.stdout.strip()
    assert line, f"expected stdout JSON, got empty output: stderr={result.stderr!r}"
    parsed = json.loads(line)
    assert isinstance(parsed, dict)
    return parsed


def control_db_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_audit_rows(control_db_path: Path, operation_id: UUID) -> int:
    connection = sqlite3.connect(control_db_path)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM repository_import_recovery_audit WHERE operation_id = ?",
            (str(operation_id),),
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def load_audit_row(control_db_path: Path, operation_id: UUID) -> dict[str, object]:
    connection = sqlite3.connect(control_db_path)
    configure_connection(connection)
    try:
        row = connection.execute(
            """
            SELECT action, prior_status, prior_code, final_status, final_code, evidence_summary_json, applied_at
            FROM repository_import_recovery_audit
            WHERE operation_id = ?
            """,
            (str(operation_id),),
        ).fetchone()
        assert row is not None
        evidence_summary = json.loads(str(row["evidence_summary_json"]))
        return {
            "action": row["action"],
            "prior_status": row["prior_status"],
            "prior_code": row["prior_code"],
            "final_status": row["final_status"],
            "final_code": row["final_code"],
            "applied_at": row["applied_at"],
            "evidence_summary": evidence_summary,
        }
    finally:
        connection.close()


def assert_audit_row(
    control_db_path: Path,
    operation_id: UUID,
    *,
    action: str,
    prior_status: str,
    prior_code: str,
    final_status: str,
    final_code: str | None,
) -> dict[str, object]:
    audit = load_audit_row(control_db_path, operation_id)
    assert audit["action"] == action
    assert audit["prior_status"] == prior_status
    assert audit["prior_code"] == prior_code
    assert audit["final_status"] == final_status
    assert audit["final_code"] == final_code
    evidence = audit["evidence_summary"]
    assert isinstance(evidence, dict)
    for forbidden in FORBIDDEN_AUDIT_KEYS:
        assert forbidden not in evidence
    return audit


@dataclass
class AdminCliControlDbEnvironment:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    control_store: ControlStore
    store: ImportOperationStore
    repository_id: UUID = DEFAULT_REPOSITORY_ID

    @classmethod
    def create(
        cls,
        tmp_path: Path,
        *,
        repository_id: UUID = DEFAULT_REPOSITORY_ID,
    ) -> AdminCliControlDbEnvironment:
        settings = lifecycle_settings(tmp_path)
        layout = DurableLayout.create_service(settings.data_root)
        control_store = ControlStore.open(
            settings.control_db_path,
            expected_version=CONTROL_DB_USER_VERSION,
            busy_timeout_ms=1000,
        )
        store = ImportOperationStore(
            control_store.connection,
            transaction_lock=control_store.transaction_lock,
        )
        return cls(
            settings=settings,
            layout=layout,
            control_store=control_store,
            store=store,
            repository_id=repository_id,
        )

    def close(self) -> None:
        if self.control_store.is_open():
            self.control_store.close()

    def run(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run_admin_cli(self.settings.data_root, *args, env=env)

    def seed_artifact_lifecycle(
        self,
        artifact_id: UUID,
        *,
        size_bytes: int,
        raw_sha256: str,
    ) -> None:
        now = "2026-08-06T00:00:00+00:00"
        with self.store._lock:
            self.store.mutation_store._connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id,
                    repository_scope,
                    media_type,
                    size_bytes,
                    raw_sha256,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(artifact_id),
                    self.repository_id.hex,
                    MEDIA_TYPE,
                    size_bytes,
                    raw_sha256,
                    now,
                    now,
                ),
            )
            self.store.mutation_store._connection.commit()

    def enqueue_operation(
        self,
        *,
        operation_id: UUID,
        artifact_id: UUID,
        expected_commit_id: str = "expected-commit-1",
        key: str = "import-key",
    ) -> ImportRequestBinding:
        size_bytes, raw_sha256 = (128, "a" * 64)
        self.seed_artifact_lifecycle(artifact_id, size_bytes=size_bytes, raw_sha256=raw_sha256)
        binding = ImportRequestBinding(
            repository_id=self.repository_id,
            artifact_ref=RepositoryArtifactRef(
                artifact_id=artifact_id,
                media_type=MEDIA_TYPE,
                size_bytes=size_bytes,
                raw_sha256=raw_sha256,
            ),
            target_ref="main",
            expected_commit_id=expected_commit_id,
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )
        key_hash = IdempotencyKeyHash.from_raw_key(key)
        fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
        self.store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=fingerprint,
            operation_id=operation_id,
        )
        return binding

    def downgrade_control_db_to_v6(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP TABLE IF EXISTS repository_import_recovery_audit")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_claim_idx")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_artifact_idx")
            connection.execute("DROP TABLE IF EXISTS repository_import_operations")
            connection.execute("PRAGMA user_version = 6")
            connection.commit()
        finally:
            connection.close()

    def drop_import_operations_table(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_claim_idx")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_artifact_idx")
            connection.execute("DROP TABLE IF EXISTS repository_import_operations")
            connection.commit()
        finally:
            connection.close()
        self.control_store = ControlStore.open(
            self.settings.control_db_path,
            expected_version=CONTROL_DB_USER_VERSION,
            busy_timeout_ms=1000,
        )
        self.store = ImportOperationStore(
            self.control_store.connection,
            transaction_lock=self.control_store.transaction_lock,
        )

    def set_journal_mode(self, mode: str) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute(f"PRAGMA journal_mode = {mode.upper()}")
            connection.commit()
        finally:
            connection.close()

    def write_non_sqlite_control_db(self) -> None:
        self.control_store.close()
        self.settings.control_db_path.write_bytes(b"not-a-database")

    def corrupt_operations_schema(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP TABLE repository_import_operations")
            connection.execute(
                "CREATE TABLE repository_import_operations (wrong_id TEXT PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()

    def corrupt_operations_column_types(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_claim_idx")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_artifact_idx")
            connection.execute("DROP TABLE repository_import_operations")
            connection.execute(
                """
                CREATE TABLE repository_import_operations (
                    operation_id INTEGER PRIMARY KEY,
                    repository_scope TEXT NOT NULL,
                    key_hash BLOB NOT NULL,
                    request_fingerprint BLOB NOT NULL,
                    artifact_id TEXT NOT NULL,
                    artifact_media_type TEXT NOT NULL,
                    artifact_size_bytes INTEGER NOT NULL,
                    artifact_raw_sha256 TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    expected_commit_id TEXT NOT NULL,
                    requested_verification_policy TEXT NOT NULL,
                    unknown_type_policy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    private_ref_name TEXT NOT NULL,
                    operation_marker TEXT NOT NULL,
                    canonicalization_manifest_digest TEXT NULL,
                    automatic_replay_count INTEGER NOT NULL DEFAULT 0,
                    enqueue_sequence INTEGER NOT NULL,
                    result_json TEXT NULL,
                    error_json TEXT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def insert_malformed_operation_row(self, operation_id: UUID) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute(
                """
                INSERT INTO repository_import_operations (
                    operation_id,
                    repository_scope,
                    key_hash,
                    request_fingerprint,
                    artifact_id,
                    artifact_media_type,
                    artifact_size_bytes,
                    artifact_raw_sha256,
                    target_ref,
                    expected_commit_id,
                    requested_verification_policy,
                    unknown_type_policy,
                    status,
                    private_ref_name,
                    operation_marker,
                    canonicalization_manifest_digest,
                    automatic_replay_count,
                    enqueue_sequence,
                    result_json,
                    error_json,
                    created_at,
                    started_at,
                    updated_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(operation_id),
                    "not-a-valid-repository-scope",
                    b"\x00" * 32,
                    b"fingerprint",
                    str(DEFAULT_ARTIFACT_ID),
                    MEDIA_TYPE,
                    1,
                    "a" * 64,
                    "main",
                    "commit-1",
                    "STRUCTURAL",
                    "REJECT",
                    "FAILED",
                    "private-ref",
                    "marker",
                    None,
                    0,
                    1,
                    None,
                    '{"code":"MANUAL_RECOVERY_REQUIRED","message":"manual"}',
                    "2026-08-06T00:00:00+00:00",
                    None,
                    "2026-08-06T00:00:00+00:00",
                    None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def strip_operations_table_constraints(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_claim_idx")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_artifact_idx")
            connection.execute("DROP TABLE repository_import_operations")
            connection.execute(
                """
                CREATE TABLE repository_import_operations (
                    operation_id TEXT PRIMARY KEY,
                    repository_scope TEXT NOT NULL,
                    key_hash BLOB NOT NULL,
                    request_fingerprint BLOB NOT NULL,
                    artifact_id TEXT NOT NULL,
                    artifact_media_type TEXT NOT NULL,
                    artifact_size_bytes INTEGER NOT NULL,
                    artifact_raw_sha256 TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    expected_commit_id TEXT NOT NULL,
                    requested_verification_policy TEXT NOT NULL,
                    unknown_type_policy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    private_ref_name TEXT NOT NULL,
                    operation_marker TEXT NOT NULL,
                    canonicalization_manifest_digest TEXT NULL,
                    automatic_replay_count INTEGER NOT NULL DEFAULT 0,
                    enqueue_sequence INTEGER NOT NULL,
                    result_json TEXT NULL,
                    error_json TEXT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX repository_import_operations_claim_idx
                ON repository_import_operations (repository_scope, status, enqueue_sequence)
                """
            )
            connection.execute(
                """
                CREATE INDEX repository_import_operations_artifact_idx
                ON repository_import_operations (artifact_id)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def corrupt_operations_check_literal_case(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_claim_idx")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_artifact_idx")
            connection.execute("DROP TABLE repository_import_operations")
            connection.execute(
                """
                CREATE TABLE repository_import_operations (
                    operation_id TEXT PRIMARY KEY,
                    repository_scope TEXT NOT NULL,
                    key_hash BLOB NOT NULL CHECK (length(key_hash) = 32),
                    request_fingerprint BLOB NOT NULL,
                    artifact_id TEXT NOT NULL,
                    artifact_media_type TEXT NOT NULL,
                    artifact_size_bytes INTEGER NOT NULL CHECK (artifact_size_bytes >= 0),
                    artifact_raw_sha256 TEXT NOT NULL CHECK (length(artifact_raw_sha256) = 64),
                    target_ref TEXT NOT NULL CHECK (target_ref = 'MAIN'),
                    expected_commit_id TEXT NOT NULL,
                    requested_verification_policy TEXT NOT NULL,
                    unknown_type_policy TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('ADMISSION_PENDING', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')
                    ),
                    private_ref_name TEXT NOT NULL,
                    operation_marker TEXT NOT NULL,
                    canonicalization_manifest_digest TEXT NULL,
                    automatic_replay_count INTEGER NOT NULL DEFAULT 0 CHECK (automatic_replay_count IN (0, 1)),
                    enqueue_sequence INTEGER NOT NULL,
                    result_json TEXT NULL,
                    error_json TEXT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT NULL,
                    UNIQUE (repository_scope, key_hash)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX repository_import_operations_claim_idx
                ON repository_import_operations (repository_scope, status, enqueue_sequence)
                """
            )
            connection.execute(
                """
                CREATE INDEX repository_import_operations_artifact_idx
                ON repository_import_operations (artifact_id)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def corrupt_trigger_succeeded_literal_case(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP TRIGGER IF EXISTS prevent_succeeded_when_terminal")
            connection.execute(
                """
                CREATE TRIGGER prevent_succeeded_when_terminal
                BEFORE UPDATE ON synchronous_mutation_effects
                FOR EACH ROW
                WHEN NEW.status = 'succeeded'
                BEGIN
                    SELECT RAISE(ABORT, 'terminal-not-published effects cannot succeed')
                    WHERE EXISTS (
                        SELECT 1
                        FROM mutation_idempotency
                        WHERE id = NEW.idempotency_id
                          AND terminal_not_published = 1
                    );
                END
                """
            )
            connection.commit()
        finally:
            connection.close()

    def replace_trigger_with_noop(self, trigger_name: str) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
            connection.execute(
                f"""
                CREATE TRIGGER {trigger_name}
                AFTER INSERT ON synchronous_mutation_effects
                BEGIN
                    SELECT 1;
                END
                """
            )
            connection.commit()
        finally:
            connection.close()

    def write_malformed_layout_marker(self) -> None:
        self.layout.layout_marker.write_text("{not-json", encoding="utf-8")

    def remove_control_db(self) -> None:
        self.control_store.close()
        if self.settings.control_db_path.exists():
            self.settings.control_db_path.unlink()


@dataclass
class AdminCliEnvironment:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    control_store: ControlStore
    store: ImportOperationStore
    provider: CandidateAImportProvider
    repository_id: UUID

    @classmethod
    def create(
        cls,
        tmp_path: Path,
        *,
        repository_id: UUID = DEFAULT_REPOSITORY_ID,
    ) -> AdminCliEnvironment:
        settings = lifecycle_settings(tmp_path)
        layout = DurableLayout.create_service(settings.data_root)
        repository = published_repository_path(layout, repository_id)
        repository.mkdir(parents=True, exist_ok=True)
        runner = DoltRunner(settings, layout.root)
        cli = OfflineCliProvider(settings, layout, repository, runner)
        cli.initialize_repository()
        provider = CandidateAImportProvider(settings, layout, repository, runner)
        control_store = ControlStore.open(
            settings.control_db_path,
            expected_version=CONTROL_DB_USER_VERSION,
            busy_timeout_ms=1000,
        )
        store = ImportOperationStore(
            control_store.connection,
            transaction_lock=control_store.transaction_lock,
        )
        return cls(
            settings=settings,
            layout=layout,
            control_store=control_store,
            store=store,
            provider=provider,
            repository_id=repository_id,
        )

    def close(self) -> None:
        if self.control_store.is_open():
            self.control_store.close()

    def run(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run_admin_cli(self.settings.data_root, *args, env=env)

    def seed_artifact_lifecycle(
        self,
        artifact_id: UUID,
        *,
        size_bytes: int,
        raw_sha256: str,
    ) -> None:
        now = "2026-08-06T00:00:00+00:00"
        with self.store._lock:
            self.store.mutation_store._connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id,
                    repository_scope,
                    media_type,
                    size_bytes,
                    raw_sha256,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(artifact_id),
                    self.repository_id.hex,
                    MEDIA_TYPE,
                    size_bytes,
                    raw_sha256,
                    now,
                    now,
                ),
            )
            self.store.mutation_store._connection.commit()

    def write_ready_artifact(
        self,
        artifact_id: UUID,
        *,
        manifest_digest: str = "manifest-digest-1",
        replay_sql: bytes | None = None,
        payload: bytes | None = None,
    ) -> tuple[int, str]:
        replay = replay_sql or (
            b"CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\n"
            b"INSERT INTO records (id) VALUES (1);\n"
        )
        manifest = {
            "package_version": 1,
            "canonicalization_manifest_digest": manifest_digest,
            "tables": [
                {
                    "name": "records",
                    "schema": {
                        "columns": [{"name": "id", "sql_type": "BIGINT", "nullable": False}],
                        "primary_key": ["id"],
                    },
                    "row_count": 1,
                }
            ],
        }
        package = payload or build_package_bytes(manifest=manifest, replay_sql=replay)
        ready_path = artifact_ready_path(self.layout, self.repository_id, artifact_id)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        return write_artifact(ready_path, package)

    def enqueue_operation(
        self,
        *,
        operation_id: UUID,
        artifact_id: UUID,
        expected_commit_id: str | None = None,
        key: str = "import-key",
        write_artifact_file: bool = True,
    ) -> ImportRequestBinding:
        if expected_commit_id is None:
            expected_commit_id = self.provider.read_ref("main")
        if write_artifact_file:
            size_bytes, raw_sha256 = self.write_ready_artifact(artifact_id)
        else:
            size_bytes, raw_sha256 = (128, "a" * 64)
        self.seed_artifact_lifecycle(artifact_id, size_bytes=size_bytes, raw_sha256=raw_sha256)
        binding = ImportRequestBinding(
            repository_id=self.repository_id,
            artifact_ref=RepositoryArtifactRef(
                artifact_id=artifact_id,
                media_type=MEDIA_TYPE,
                size_bytes=size_bytes,
                raw_sha256=raw_sha256,
            ),
            target_ref="main",
            expected_commit_id=expected_commit_id,
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )
        key_hash = IdempotencyKeyHash.from_raw_key(key)
        fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
        self.store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=fingerprint,
            operation_id=operation_id,
        )
        return binding

    def mark_manual(
        self,
        operation_id: UUID,
        *,
        message: str = "manual recovery required",
    ) -> None:
        claimed = self.store.claim_if_queued(operation_id)
        assert claimed is not None
        self.store.mark_failed(
            operation_id,
            error=SimpleError(
                code=MANUAL_RECOVERY_REQUIRED_CODE,
                message=message,
                details={"reason": "test"},
                request_id=None,
            ),
        )

    def publish_unique_marker_evidence(self, operation_id: UUID) -> str:
        context = self.store.load_execution_context(operation_id)
        assert context is not None
        expected = context.expected_commit_id
        private_ref = derive_private_ref_name(operation_id)
        marker = derive_operation_marker(operation_id)
        staging_dir = self.layout.staging_artifacts / f"setup-{operation_id.hex}"
        staging_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifact_path = artifact_ready_path(
                self.layout,
                self.repository_id,
                context.artifact_id,
            )
            package = validate_and_extract_import_package(
                artifact_path=artifact_path,
                expected_size_bytes=context.artifact_size_bytes,
                expected_raw_sha256=context.artifact_raw_sha256,
                staging_dir=staging_dir,
                settings=self.settings,
            )
            try:
                self.provider.delete_private_ref(private_ref)
            except Exception:
                pass
            self.provider.create_private_ref(private_ref, expected)
            self.provider.checkout_private_ref(private_ref)
            self.provider.replay_sql(private_ref, package.replay_sql_path)
            candidate = self.provider.commit_operation_marker(private_ref, marker)
            publish = self.provider.publish_main(expected, candidate)
            assert isinstance(publish, PublishMainPublished)
            assert self.provider.read_ref("main") == candidate
            return candidate
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)

    def setup_manual_with_published_evidence(
        self,
        *,
        operation_id: UUID = DEFAULT_OPERATION_ID,
        artifact_id: UUID = DEFAULT_ARTIFACT_ID,
    ) -> str:
        self.enqueue_operation(operation_id=operation_id, artifact_id=artifact_id)
        candidate = self.publish_unique_marker_evidence(operation_id)
        self.mark_manual(operation_id)
        return candidate

    def setup_manual_without_publish(
        self,
        *,
        operation_id: UUID = DEFAULT_OPERATION_ID,
        artifact_id: UUID = DEFAULT_ARTIFACT_ID,
    ) -> None:
        self.enqueue_operation(operation_id=operation_id, artifact_id=artifact_id)
        self.mark_manual(operation_id)

    def setup_manual_with_private_candidate_unverified(
        self,
        *,
        operation_id: UUID = DEFAULT_OPERATION_ID,
        artifact_id: UUID = DEFAULT_ARTIFACT_ID,
    ) -> str:
        self.enqueue_operation(operation_id=operation_id, artifact_id=artifact_id)
        context = self.store.load_execution_context(operation_id)
        assert context is not None
        expected = context.expected_commit_id
        private_ref = derive_private_ref_name(operation_id)
        marker = derive_operation_marker(operation_id)
        staging_dir = self.layout.staging_artifacts / f"setup-{operation_id.hex}"
        staging_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifact_path = artifact_ready_path(
                self.layout,
                self.repository_id,
                context.artifact_id,
            )
            package = validate_and_extract_import_package(
                artifact_path=artifact_path,
                expected_size_bytes=context.artifact_size_bytes,
                expected_raw_sha256=context.artifact_raw_sha256,
                staging_dir=staging_dir,
                settings=self.settings,
            )
            try:
                self.provider.delete_private_ref(private_ref)
            except Exception:
                pass
            self.provider.create_private_ref(private_ref, expected)
            self.provider.checkout_private_ref(private_ref)
            self.provider.replay_sql(private_ref, package.replay_sql_path)
            candidate = self.provider.commit_operation_marker(private_ref, marker)
            assert self.provider.read_ref("main") == expected
            self.mark_manual(operation_id)
            return candidate
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)

    def setup_published_then_main_advanced(
        self,
        *,
        operation_id: UUID = DEFAULT_OPERATION_ID,
        artifact_id: UUID = DEFAULT_ARTIFACT_ID,
    ) -> str:
        candidate = self.setup_manual_with_published_evidence(
            operation_id=operation_id,
            artifact_id=artifact_id,
        )
        other_operation = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11")
        other_ref = derive_private_ref_name(other_operation)
        other_marker = derive_operation_marker(other_operation)
        self.provider.create_private_ref(other_ref, candidate)
        self.provider.checkout_private_ref(other_ref)
        new_head = self.provider.commit_operation_marker(other_ref, other_marker)
        self.provider.publish_main(candidate, new_head)
        assert self.provider.read_ref("main") == new_head
        assert new_head != candidate
        return new_head

    def downgrade_control_db_to_v6(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP TABLE IF EXISTS repository_import_recovery_audit")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_claim_idx")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_artifact_idx")
            connection.execute("DROP TABLE IF EXISTS repository_import_operations")
            connection.execute("PRAGMA user_version = 6")
            connection.commit()
        finally:
            connection.close()

    def drop_import_operations_table(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_claim_idx")
            connection.execute("DROP INDEX IF EXISTS repository_import_operations_artifact_idx")
            connection.execute("DROP TABLE IF EXISTS repository_import_operations")
            connection.commit()
        finally:
            connection.close()
        self.control_store = ControlStore.open(
            self.settings.control_db_path,
            expected_version=CONTROL_DB_USER_VERSION,
            busy_timeout_ms=1000,
        )
        self.store = ImportOperationStore(
            self.control_store.connection,
            transaction_lock=self.control_store.transaction_lock,
        )

    def set_journal_mode(self, mode: str) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute(f"PRAGMA journal_mode = {mode.upper()}")
            connection.commit()
        finally:
            connection.close()

    def write_non_sqlite_control_db(self) -> None:
        self.control_store.close()
        self.settings.control_db_path.write_bytes(b"not-a-database")

    def corrupt_operations_schema(self) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute("DROP TABLE repository_import_operations")
            connection.execute(
                "CREATE TABLE repository_import_operations (wrong_id TEXT PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()

    def bump_control_db_version(self, version: int) -> None:
        self.control_store.close()
        connection = sqlite3.connect(self.settings.control_db_path)
        try:
            connection.execute(f"PRAGMA user_version = {int(version)}")
            connection.commit()
        finally:
            connection.close()
        self.control_store = ControlStore.open(
            self.settings.control_db_path,
            expected_version=CONTROL_DB_USER_VERSION,
            busy_timeout_ms=1000,
        )
        self.store = ImportOperationStore(
            self.control_store.connection,
            transaction_lock=self.control_store.transaction_lock,
        )
