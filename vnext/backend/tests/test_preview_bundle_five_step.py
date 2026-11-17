"""Preview budget and ambiguity barriers for the five-step driver."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from benchmarks.preview_bundle_five_step import RecordingClient
from benchmarks.real_dump_journey import JourneyFailure


def test_attempt_is_recorded_before_an_ambiguous_transport_failure(tmp_path: Path) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        assert (
            json.loads((tmp_path / "attempt-1.json").read_text())["state"] == "acceptance_unknown"
        )
        raise httpx.ReadTimeout("response lost", request=request)

    with RecordingClient(
        base_url="http://test", ledger=tmp_path, transport=httpx.MockTransport(fail)
    ) as client:
        with pytest.raises(httpx.ReadTimeout):
            client.post("/v1/workspaces/ws/preview-operations")
    assert json.loads((tmp_path / "attempt-1.json").read_text())["state"] == "acceptance_unknown"


def test_accepted_operation_is_recorded_and_limit_stops_before_http(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def accept(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"operation_id": "op-1"})

    with RecordingClient(
        base_url="http://test", ledger=tmp_path, transport=httpx.MockTransport(accept)
    ) as client:
        client.count = 5
        client.post("/v1/workspaces/ws/preview-operations")
        with pytest.raises(JourneyFailure):
            client.post("/v1/workspaces/ws/preview-operations")
    record = json.loads((tmp_path / "attempt-6.json").read_text())
    assert record["state"] == "accepted"
    assert record["operation_id"] == "op-1"
    assert len(requests) == 1


def test_preview_saves_same_operation_result_and_invalid_bundle_before_failure(
    tmp_path: Path,
) -> None:
    from benchmarks.preview_bundle_five_step import _preview

    ledger = tmp_path / "ledger"
    ledger.mkdir()
    stage = tmp_path / "M1"
    stage.mkdir()

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/preview-operations"):
            return httpx.Response(202, json={"operation_id": "op-1"})
        if path == "/v1/operations/op-1":
            return httpx.Response(200, json={"status": "SUCCEEDED"})
        if path == "/v1/workspaces":
            return httpx.Response(
                200, json={"workspace_id": "ws", "current_preview_result_id": "r1"}
            )
        if path.endswith("/bundle"):
            return httpx.Response(
                200, content=b"bad", headers={"content-type": "application/x-tar"}
            )
        if path.endswith("/preview-results/r1"):
            return httpx.Response(200, json={"operation_id": "op-1", "preview_result_id": "r1"})
        raise AssertionError(path)

    with RecordingClient(
        base_url="http://test", ledger=ledger, transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(JourneyFailure, match="length"):
            _preview(
                client,
                workspace={"workspace_id": "ws"},
                upload={"optimistic_version": 1, "upload_revision_id": "u", "generation": 1},
                output=stage,
                baseline_node_id="b",
                baseline_head_version=0,
                idempotency_key="key",
                stage="test",
                operation_timeout_seconds=5,
            )
    assert (stage / "preview.tar").read_bytes() == b"bad"
    assert json.loads((stage / "result-response.json").read_text())["operation_id"] == "op-1"
    assert json.loads((stage / "visibility.json").read_text())["operation_id"] == "op-1"
    assert json.loads((ledger / "attempt-1.json").read_text())["operation_id"] == "op-1"


def test_preview_rejects_valid_bundle_with_different_result_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from benchmarks import preview_bundle_five_step as target

    ledger = tmp_path / "ledger"
    ledger.mkdir()
    stage = tmp_path / "F"
    stage.mkdir()
    monkeypatch.setattr(
        target, "verify_bundle_tar", lambda *_args, **_kwargs: ({"bundle_digest": "bundle-A"}, {})
    )

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/preview-operations"):
            return httpx.Response(202, json={"operation_id": "op-1"})
        if path == "/v1/operations/op-1":
            return httpx.Response(200, json={"status": "SUCCEEDED"})
        if path == "/v1/workspaces":
            return httpx.Response(
                200, json={"workspace_id": "ws", "current_preview_result_id": "r1"}
            )
        if path.endswith("/bundle"):
            return httpx.Response(
                200,
                content=bytes(2048),
                headers={"content-type": "application/x-tar", "etag": '"bundle-A"'},
            )
        if path.endswith("/preview-results/r1"):
            return httpx.Response(
                200,
                json={
                    "operation_id": "op-1",
                    "preview_result_id": "r1",
                    "bundle_digest": "bundle-B",
                },
            )
        raise AssertionError(path)

    with RecordingClient(
        base_url="http://test", ledger=ledger, transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(JourneyFailure, match="same operation result digest"):
            target._preview(
                client,
                workspace={"workspace_id": "ws"},
                upload={"optimistic_version": 1, "upload_revision_id": "u", "generation": 1},
                output=stage,
                baseline_node_id="b",
                baseline_head_version=0,
                idempotency_key="key",
                stage="test",
                operation_timeout_seconds=5,
            )
    assert json.loads((stage / "manifest.json").read_text())["bundle_digest"] == "bundle-A"
    assert json.loads((stage / "result-response.json").read_text())["bundle_digest"] == "bundle-B"
    assert (stage / "preview.tar").stat().st_size == 2048


def test_source_oracle_requires_exact_changed_name_and_identity() -> None:
    from benchmarks.preview_bundle_five_step import _assert_name_record
    from gateway_shared_kernel import (
        DeclaredType,
        DeclaredTypeKind,
        RowField,
        UnsignedIntegerScalar,
        encode_row,
    )

    identity = encode_row(
        [
            RowField(
                "gid",
                DeclaredType(DeclaredTypeKind.UNSIGNED_INTEGER, bits=32),
                UnsignedIntegerScalar("628"),
            )
        ]
    ).digest_ref.raw_digest
    row = {
        "table_name": "device_st",
        "row_identity": identity,
        "record_kind": "ROW_MODIFIED",
        "changed_columns": ["name"],
        "before_values": [{"column_name": "name", "value": {"kind": "string", "text": "检修"}}],
        "current_values": [
            {"column_name": "name", "value": {"kind": "string", "text": "检修1111"}}
        ],
    }
    _assert_name_record([row], "检修", "检修1111")
    with pytest.raises(JourneyFailure):
        _assert_name_record([row], "检修", "different")
