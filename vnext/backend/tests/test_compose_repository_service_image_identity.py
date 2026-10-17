"""Repository-service image binding for backend Compose gates."""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.support import compose_gate_harness

EXPECTED_BUILD_INPUT_REVISION = "a" * 40
EXPECTED_SOURCE_TREE_SHA256 = f"sha256:{'b' * 64}"
EXPECTED_IDENTITY = (EXPECTED_BUILD_INPUT_REVISION, EXPECTED_SOURCE_TREE_SHA256)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("image_exists", "initial_labels", "expected_builds"),
    [
        pytest.param(
            True,
            {
                "gateway.p2r1.build-input-revision": EXPECTED_BUILD_INPUT_REVISION,
                "gateway.p2r1.source-tree-sha256": EXPECTED_SOURCE_TREE_SHA256,
            },
            0,
            id="matching-labels-reuse-image",
        ),
        pytest.param(
            True,
            {
                "gateway.p2r1.build-input-revision": EXPECTED_BUILD_INPUT_REVISION,
                "gateway.p2r1.source-tree-sha256": f"sha256:{'c' * 64}",
            },
            1,
            id="stale-source-tree-rebuilds-image",
        ),
        pytest.param(
            False,
            {},
            1,
            id="missing-image-builds-image",
        ),
    ],
)
def test_repository_service_image_is_bound_to_current_build_identity(
    monkeypatch: pytest.MonkeyPatch,
    image_exists: bool,
    initial_labels: dict[str, str],
    expected_builds: int,
) -> None:
    labels = dict(initial_labels)
    present = image_exists
    build_calls: list[list[str]] = []
    image_ref = "gateway-repository-service:local"
    monkeypatch.setattr(compose_gate_harness, "repository_service_image", lambda: image_ref)
    monkeypatch.setattr(
        compose_gate_harness,
        "_repository_service_image_identity",
        lambda: EXPECTED_IDENTITY,
    )

    def fake_run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
        cwd: object = None,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal labels, present
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout > 0
        if args == ["docker", "image", "inspect", image_ref]:
            if not present:
                return subprocess.CompletedProcess(args, 1, "", "missing")
            output = json.dumps(
                [{"Id": "sha256:" + "d" * 64, "Config": {"Labels": labels}}]
            )
            return subprocess.CompletedProcess(args, 0, output, "")
        if args == [str(compose_gate_harness.BUILD_REPOSITORY_SCRIPT)]:
            assert cwd == compose_gate_harness.VNEXT_ROOT
            build_calls.append(args)
            labels = {
                "gateway.p2r1.build-input-revision": EXPECTED_BUILD_INPUT_REVISION,
                "gateway.p2r1.source-tree-sha256": EXPECTED_SOURCE_TREE_SHA256,
            }
            present = True
            return subprocess.CompletedProcess(args, 0, "built", "")
        pytest.fail(f"unexpected subprocess call: {args}")

    monkeypatch.setattr("tests.support.compose_gate_harness.subprocess.run", fake_run)

    compose_gate_harness.ensure_repository_service_image()

    assert len(build_calls) == expected_builds
