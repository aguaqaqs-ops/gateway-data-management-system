"""Fixed C/D vectors: original semantic preimages with v4 evidence identities."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any, cast


_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures/golden/comparison/s3-e/comparison-v4-expected.json"
)
_SOURCE = "f0b4ee93cd036f5941f0227839e807445274f500"
_ALGORITHM_SOURCE = "4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec"


@cache
def _cases() -> dict[str, dict[str, Any]]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert payload["source_commit"] == _SOURCE
    assert payload["old_algorithm_source"] == _ALGORITHM_SOURCE
    assert payload["historical_source_commit"] == "a9da0c59277e3179f34d646eabcd9c185917ae05"
    assert payload["contract_version"] == "backend-vnext/comparison/v4"
    assert payload["algorithm_version"] == "standard-reference/v3"
    cases = cast(dict[str, dict[str, Any]], payload["cases"])
    assert len(cases) == 20
    return cases


def frozen_case(nodeid: str) -> dict[str, Any]:
    """Get the fixed v4 expectation for one exact expanded pytest case."""
    return deepcopy(_cases()[nodeid])
