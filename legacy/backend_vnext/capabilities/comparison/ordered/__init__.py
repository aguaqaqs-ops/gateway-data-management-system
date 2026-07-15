"""Ordered comparison scaffold for backend_vnext.

The ordered provider is routed separately from the standard snapshot compare
path, but the first slice still keeps the algorithm intentionally thin.
"""

from .models import (
    OrderedEntityKeyKind,
    OrderedPreparedRowsCache,
    OrderedRecord,
    OrderedRecordKind,
    OrderedReplayGuarantee,
    OrderedReplayValidation,
    OrderedSemanticKind,
    OrderedSummary,
    OrderedTableCompareInput,
    OrderedTableCompareResult,
    OrderedTableProcessingMode,
)
from .policy import OrderedTablePolicy, build_ordered_table_policy
from .provider import compare_ordered_table

__all__ = [
    "OrderedEntityKeyKind",
    "OrderedPreparedRowsCache",
    "OrderedRecord",
    "OrderedRecordKind",
    "OrderedReplayGuarantee",
    "OrderedReplayValidation",
    "OrderedSemanticKind",
    "OrderedSummary",
    "OrderedTableCompareInput",
    "OrderedTableCompareResult",
    "OrderedTablePolicy",
    "OrderedTableProcessingMode",
    "build_ordered_table_policy",
    "compare_ordered_table",
]
