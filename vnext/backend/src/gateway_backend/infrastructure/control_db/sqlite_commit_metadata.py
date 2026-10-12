"""SQLite-backed commit canonical metadata resolver."""

from __future__ import annotations

import logging
import sqlite3

from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadata,
    CommitCanonicalMetadataCode,
    CommitCanonicalMetadataError,
    CommitCanonicalMetadataMetricsPort,
    CommitCanonicalMetadataPort,
    CommitCanonicalScope,
    CanonicalizationManifestReadPort,
    ManifestArtifactUnavailable,
)
from gateway_backend.domain.baseline.models import BaselineNodeKind

_LOGGER = logging.getLogger(__name__)


class SQLiteCommitCanonicalMetadataPort(CommitCanonicalMetadataPort):
    """Resolve only Submission and INITIAL metadata belonging to one frozen scope."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        manifest_reader: CanonicalizationManifestReadPort,
        metrics: CommitCanonicalMetadataMetricsPort | None = None,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteCommitCanonicalMetadataPort requires an active transaction")
        self._connection = connection
        self._manifest_reader = manifest_reader
        self._metrics = metrics

    def resolve(
        self,
        *,
        repository_id: str,
        commit_id: str,
        scope: CommitCanonicalScope,
    ) -> CommitCanonicalMetadata:
        if type(repository_id) is not str or not repository_id:
            raise ValueError("repository_id must be a non-empty string")
        if type(commit_id) is not str or not commit_id:
            raise ValueError("commit_id must be a non-empty string")
        if type(scope) is not CommitCanonicalScope:
            raise ValueError("scope must be CommitCanonicalScope")

        submission_rows = self._connection.execute(
            """
            SELECT s.canonicalization_manifest_ref, s.canonicalization_manifest_digest
            FROM submission_records AS s
            JOIN workspace_records AS w ON w.workspace_id = s.workspace_id
            WHERE s.repository_id = ?
              AND s.repository_commit_id = ?
              AND w.repository_id = s.repository_id
              AND w.gateway_device_external_key = ?
              AND w.business_project_id = ?
            LIMIT 2
            """,
            (
                repository_id,
                commit_id,
                scope.gateway_device_external_key,
                scope.business_project_id,
            ),
        ).fetchall()
        initial_rows = self._connection.execute(
            """
            SELECT node_id
            FROM baseline_node_records
            WHERE repository_id = ?
              AND commit_id = ?
              AND kind = ?
              AND gateway_device_external_key = ?
              AND business_project_id = ?
            LIMIT 2
            """,
            (
                repository_id,
                commit_id,
                BaselineNodeKind.INITIAL.value,
                scope.gateway_device_external_key,
                scope.business_project_id,
            ),
        ).fetchall()

        if len(submission_rows) > 1 or len(initial_rows) > 1 or (submission_rows and initial_rows):
            raise _missing_metadata()
        if initial_rows:
            return CommitCanonicalMetadata(
                repository_id=repository_id,
                commit_id=commit_id,
                scope=scope,
                initial=True,
            )
        if not submission_rows:
            raise _missing_metadata()

        manifest_ref_id, expected_digest = submission_rows[0]
        return self._load_submission_metadata(
            repository_id=repository_id,
            commit_id=commit_id,
            scope=scope,
            manifest_ref_id=manifest_ref_id,
            expected_digest=expected_digest,
        )

    def _load_submission_metadata(
        self,
        *,
        repository_id: str,
        commit_id: str,
        scope: CommitCanonicalScope,
        manifest_ref_id: object,
        expected_digest: object,
    ) -> CommitCanonicalMetadata:
        if type(manifest_ref_id) is not str or not manifest_ref_id:
            raise _missing_metadata()
        if type(expected_digest) is not str or not expected_digest:
            raise _missing_metadata()
        try:
            manifest = self._manifest_reader.read_manifest(manifest_ref_id)
        except (ManifestArtifactUnavailable, OSError, ValueError):
            raise _missing_metadata() from None

        observed_digest = manifest.manifest_digest
        if observed_digest is None or observed_digest.value != expected_digest:
            self._record_digest_mismatch(
                repository_id=repository_id,
                commit_id=commit_id,
                manifest_ref_id=manifest_ref_id,
                expected_digest=expected_digest,
                observed_digest=None if observed_digest is None else observed_digest.value,
            )
            raise CommitCanonicalMetadataError(
                CommitCanonicalMetadataCode.DIGEST_MISMATCH,
                "canonicalization manifest digest does not match Submission metadata",
            )
        return CommitCanonicalMetadata(
            repository_id=repository_id,
            commit_id=commit_id,
            scope=scope,
            initial=False,
            manifest=manifest,
        )

    def _record_digest_mismatch(
        self,
        *,
        repository_id: str,
        commit_id: str,
        manifest_ref_id: str,
        expected_digest: str,
        observed_digest: str | None,
    ) -> None:
        _LOGGER.error(
            "Commit canonical metadata digest mismatch",
            extra={
                "event": "commit_canonical_metadata_digest_mismatch",
                "diagnostic_code": CommitCanonicalMetadataCode.DIGEST_MISMATCH.value,
                "metric_name": "commit_canonical_metadata_digest_mismatch_total",
                "metric_increment": 1,
                "repository_id": repository_id,
                "commit_id": commit_id,
                "manifest_artifact_id": manifest_ref_id,
                "expected_digest": expected_digest,
                "observed_digest": observed_digest,
            },
        )
        if self._metrics is not None:
            try:
                self._metrics.increment_digest_mismatch()
            except Exception:
                _LOGGER.exception("Commit canonical metadata metric emission failed")


def _missing_metadata() -> CommitCanonicalMetadataError:
    return CommitCanonicalMetadataError(
        CommitCanonicalMetadataCode.MISSING,
        "canonical metadata is not registered for this Repository commit and scope",
    )


__all__ = ["SQLiteCommitCanonicalMetadataPort"]
