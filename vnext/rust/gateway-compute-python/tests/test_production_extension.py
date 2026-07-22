"""Production extension must not expose fault-injection controls."""

from __future__ import annotations

import gateway_compute.gateway_compute as native


def test_production_extension_has_no_test_hooks() -> None:
    for name in dir(native):
        assert not name.startswith("_test_"), f"unexpected test hook: {name}"
        assert not name.startswith("_TEST_"), f"unexpected test hook: {name}"
