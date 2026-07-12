from __future__ import annotations

from collections.abc import Callable

from ..capabilities.snapshot_materialization import (
    RepositoryRefMaterializationInput,
    SnapshotMaterializationResult,
    materialize_repository_ref,
)
from ..repository_server import (
    RepositoryRef,
    RepositoryRefTimeoutPolicy,
    RepositoryTableAccessProvider,
)
from ..submissions import SubmissionRecord
from .models import ArchiveBatchRecord, ArchiveCandidateRecord


def open_ref_closeout(
    *,
    batch: ArchiveBatchRecord,
    selected_modified: ArchiveCandidateRecord,
    repository_table_access_provider: RepositoryTableAccessProvider | None,
    require_submission: Callable[[str | None], SubmissionRecord],
    requested_tables: tuple[str, ...],
    timeout_policy: RepositoryRefTimeoutPolicy | None,
) -> SnapshotMaterializationResult:
    if repository_table_access_provider is None:
        raise RuntimeError("repository_table_access_provider is required for archive open ref closeout")
    selected_modified_submission = require_submission(selected_modified.source_submission_id)
    repository_ref = selected_modified_submission.repository_target_ref
    if repository_ref is None:
        raise ValueError("selected modified submission is missing repository_target_ref")
    return materialize_repository_ref(
        RepositoryRefMaterializationInput(
            repository_ref=RepositoryRef(
                repository_id=batch.repository_id,
                repository_ref=repository_ref,
            ),
            repository_table_access_provider=repository_table_access_provider,
            requested_tables=requested_tables,
            timeout_policy=timeout_policy,
        )
    )
