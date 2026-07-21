"""Test-only tooling for Shared Kernel vector candidates.

Not part of the production public API. Do not re-export from package root.
"""

from __future__ import annotations

from gateway_shared_kernel.testing.closure import validate_vector_set
from gateway_shared_kernel.testing.dispatch import dispatch_case
from gateway_shared_kernel.testing.generate import generate_candidate
from gateway_shared_kernel.testing.validate_frame import validate_scalar_frame

__all__ = [
    "dispatch_case",
    "generate_candidate",
    "validate_scalar_frame",
    "validate_vector_set",
]
