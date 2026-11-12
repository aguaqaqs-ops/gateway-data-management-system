"""Authenticated RS identity is strict and independent from readiness."""
import pytest

from gateway_repository_contracts import DeploymentIdentityResponse

pytestmark = pytest.mark.unit


def test_deployment_identity_roundtrip() -> None:
    response = DeploymentIdentityResponse(environment_id="test-env", group_id="group-a", storage_digest="sha256:" + "a" * 64)
    assert DeploymentIdentityResponse.model_validate_json(response.model_dump_json()) == response


@pytest.mark.parametrize(("key", "value"), [("environment_id", "../other"), ("group_id", True),
    ("storage_digest", "a" * 64), ("storage_digest", "sha256:" + "A" * 64), ("extra", "bad")])
def test_deployment_identity_rejects_invalid_fields(key: str, value: object) -> None:
    document = dict(environment_id="test-env", group_id="group-a", storage_digest="sha256:" + "a" * 64)
    document[key] = value  # type: ignore[assignment]
    with pytest.raises(ValueError):
        DeploymentIdentityResponse.model_validate(document)
