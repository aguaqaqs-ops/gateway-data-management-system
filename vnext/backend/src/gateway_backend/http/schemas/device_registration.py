"""Processing-group wire models; routes own authentication and bounded body reading."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from gateway_backend.device_identity import (
    validate_deployment_identity,
    validate_device_route_key,
    validate_scope_identity,
)
from gateway_backend.http.schemas.constraints import BoundedOpaqueId, CommitIdString

ScopeIdentity = Annotated[str, BeforeValidator(validate_scope_identity), Field(min_length=1, max_length=255)]
DeploymentIdentity = Annotated[str, BeforeValidator(validate_deployment_identity),
    Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
DeviceRouteKey = Annotated[str, BeforeValidator(validate_device_route_key), Field(pattern=r"^[0-9a-f]{64}$")]


class RegisterDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    environment_id: DeploymentIdentity
    group_id: DeploymentIdentity
    gateway_device_external_key: ScopeIdentity
    business_project_id: ScopeIdentity


class DeviceRegistrationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    device: ScopeIdentity


class DeviceContextResponse(RegisterDeviceRequest):
    repository_id: BoundedOpaqueId


class DeviceRegistrationResponse(DeviceContextResponse):
    initial_node_id: BoundedOpaqueId
    initial_commit_id: CommitIdString
