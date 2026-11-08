"""Small fixed C/D outputs captured from the pre-E Python source."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, cast


_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures/golden/comparison/s3-e/old-python-expected.json"
)
_SOURCE = "a9da0c59277e3179f34d646eabcd9c185917ae05"
_ALGORITHM_SOURCE = "4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec"


@cache
def _cases() -> dict[str, dict[str, Any]]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert payload["source_commit"] == _SOURCE
    assert payload["old_algorithm_source"] == _ALGORITHM_SOURCE
    cases = cast(dict[str, dict[str, Any]], payload["cases"])
    assert len(cases) == 20
    return cases


def frozen_case(nodeid: str) -> dict[str, Any]:
    """Get a frozen old-source expectation for one exact expanded pytest case."""
    return _cases()[nodeid]
