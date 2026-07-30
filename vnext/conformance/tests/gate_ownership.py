"""Gate authority to pytest ownership registry."""

from __future__ import annotations

CONTAINER_OWNED_MODULES = (
    "tests/test_phase_exit_container_gate.py",
    "tests/test_phase_exit_identity_bundle.py",
)
CONTAINER_OWNED_BACKEND_MODULE = "tests/test_container_native_smoke.py"
CORRECTNESS_MARKER_EXPR = "not phase_exit_container"
CONTAINER_MARKER_EXPR = "phase_exit_container"
EXPECTED_CONTAINER_OWNED_COUNT = 66
