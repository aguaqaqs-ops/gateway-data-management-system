"""Preview budget and ambiguity barriers for the five-step driver."""
from __future__ import annotations

import json

import httpx
import pytest

from benchmarks.preview_bundle_five_step import RecordingClient
from benchmarks.real_dump_journey import JourneyFailure


def test_attempt_is_recorded_before_an_ambiguous_transport_failure(tmp_path):
    def fail(request: httpx.Request) -> httpx.Response:
        assert json.loads((tmp_path / "attempt-1.json").read_text())["state"] == "acceptance_unknown"
        raise httpx.ReadTimeout("response lost", request=request)

    with RecordingClient(base_url="http://test", ledger=tmp_path, transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(httpx.ReadTimeout):
            client.post("/v1/workspaces/ws/preview-operations")
    assert json.loads((tmp_path / "attempt-1.json").read_text())["state"] == "acceptance_unknown"


def test_accepted_operation_is_recorded_and_limit_stops_before_http(tmp_path):
    requests = []

    def accept(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"operation_id": "op-1"})

    with RecordingClient(base_url="http://test", ledger=tmp_path, transport=httpx.MockTransport(accept)) as client:
        client.count = 5
        client.post("/v1/workspaces/ws/preview-operations")
        with pytest.raises(JourneyFailure):
            client.post("/v1/workspaces/ws/preview-operations")
    record = json.loads((tmp_path / "attempt-6.json").read_text())
    assert record["state"] == "accepted"
    assert record["operation_id"] == "op-1"
    assert len(requests) == 1
