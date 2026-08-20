"""Public surface of the Comparison capability."""

from gateway_backend.capabilities.comparison.contracts import (
    COMPARISON_BATCH_PORT_VERSION,
    ComparisonBatchProvider,
    ComparisonBatchRequest,
    ComparisonBatchResult,
)
from gateway_backend.capabilities.comparison.provider import (
    PythonReferenceBatchProvider,
    RustArrowBatchProvider,
)

__all__ = [
    "COMPARISON_BATCH_PORT_VERSION",
    "ComparisonBatchProvider",
    "ComparisonBatchRequest",
    "ComparisonBatchResult",
    "PythonReferenceBatchProvider",
    "RustArrowBatchProvider",
]
