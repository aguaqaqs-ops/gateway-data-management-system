"""Test-only helpers for Shared Kernel owner tests.

Not part of the production public API. Do not re-export from package root.
"""

from __future__ import annotations

from gateway_shared_kernel.testing.dispatch import dispatch_case
from gateway_shared_kernel.testing.validate_frame import validate_scalar_frame

__all__ = [
    "dispatch_case",
    "validate_scalar_frame",
]
