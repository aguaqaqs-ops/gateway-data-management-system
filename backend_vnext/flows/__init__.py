from __future__ import annotations

from .comparison_risk import (
    ComparisonRiskFlowInput,
    ComparisonRiskFlowResult,
    ComparisonRecordsClosureAccess,
    compare_and_evaluate_risk,
    complete_comparison_core_cache,
)
from .business_projection import (
    assemble_business_projection_for_surface,
    build_business_projection_input_for_surface,
)
from .history_compare import (
    build_history_compare_pair_input,
    HistoryCompareFlowInput,
    HistoryCompareFlowResult,
    HistoryComparePairInput,
    HistoryComparePairResult,
    run_history_compare,
)
from .submit_finalize import (
    RepositoryImportRunnerProtocol,
    SubmitFinalizeFlowInput,
    SubmitFinalizeFlowResult,
    SubmitFinalizeWorker,
    SubmitFinalizeWorkerProtocol,
    run_submit_finalize,
)
from .submission_review import (
    SubmissionReviewAction,
    SubmissionReviewFlowInput,
    SubmissionReviewFlowResult,
    SubmissionReviewWorker,
    run_submission_review,
)
from .submit_acceptance import (
    SubmitAcceptanceFlowInput,
    SubmitAcceptanceFlowResult,
    run_submit_acceptance,
)
from .upload_preview import (
    UploadPreviewFlowInput,
    UploadPreviewFlowResult,
    complete_upload_preview_cache,
    run_upload_preview,
)

__all__ = [
    "ComparisonRiskFlowInput",
    "ComparisonRiskFlowResult",
    "ComparisonRecordsClosureAccess",
    "ArchivePromoteFlowInput",
    "ArchivePromoteFlowResult",
    "ArchivePromoteWorker",
    "HistoryCompareFlowInput",
    "HistoryCompareFlowResult",
    "HistoryComparePairInput",
    "HistoryComparePairResult",
    "build_history_compare_pair_input",
    "assemble_business_projection_for_surface",
    "build_business_projection_input_for_surface",
    "RepositoryImportRunnerProtocol",
    "SubmitFinalizeFlowInput",
    "SubmitFinalizeFlowResult",
    "SubmitFinalizeWorker",
    "SubmitFinalizeWorkerProtocol",
    "SubmitAcceptanceFlowInput",
    "SubmitAcceptanceFlowResult",
    "SubmissionReviewAction",
    "SubmissionReviewFlowInput",
    "SubmissionReviewFlowResult",
    "SubmissionReviewWorker",
    "UploadPreviewFlowInput",
    "UploadPreviewFlowResult",
    "compare_and_evaluate_risk",
    "complete_comparison_core_cache",
    "complete_upload_preview_cache",
    "run_submit_acceptance",
    "run_history_compare",
    "run_archive_promote",
    "run_submit_finalize",
    "run_submission_review",
    "run_upload_preview",
]

_ARCHIVE_EXPORTS = {
    "ArchivePromoteFlowInput",
    "ArchivePromoteFlowResult",
    "ArchivePromoteWorker",
    "run_archive_promote",
}


def __getattr__(name: str):
    if name in _ARCHIVE_EXPORTS:
        from . import archive as archive_flow

        value = getattr(archive_flow, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
