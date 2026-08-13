"""Central test classification and external-dependency gating."""

from __future__ import annotations

import pytest

from support.lifecycle_harness import dolt_available

# Fixtures that initialize a real Dolt repository. Requesting one of these
# makes a test an integration test regardless of how it is decorated, which
# keeps the gate correct for tests that forget the explicit marker.
_DOLT_FIXTURES = frozenset({"import_layout", "import_provider"})

_DOLT_MISSING = pytest.mark.skip(reason="dolt executable is unavailable")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    dolt_present = dolt_available()
    for item in items:
        if item.get_closest_marker("serial") is not None:
            # Keep the timing sensitive tests on a single xdist worker so they
            # never race each other; the two-pass runner script isolates them
            # from the rest of the suite entirely.
            item.add_marker(pytest.mark.xdist_group("serial"))

        requests_dolt_fixture = isinstance(item, pytest.Function) and bool(
            _DOLT_FIXTURES.intersection(item.fixturenames)
        )
        needs_dolt = (
            item.get_closest_marker("integration") is not None or requests_dolt_fixture
        )
        if not needs_dolt:
            item.add_marker(pytest.mark.unit)
            continue
        item.add_marker(pytest.mark.integration)
        if not dolt_present:
            item.add_marker(_DOLT_MISSING)
