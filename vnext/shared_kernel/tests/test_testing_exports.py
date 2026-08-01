"""Production package must not re-export test-only tooling."""

from __future__ import annotations

import gateway_shared_kernel as root


def test_production_all_excludes_testing() -> None:
    assert "testing" not in root.__all__
    assert not hasattr(root, "validate_scalar_frame")
    assert not hasattr(root, "dispatch_case")
