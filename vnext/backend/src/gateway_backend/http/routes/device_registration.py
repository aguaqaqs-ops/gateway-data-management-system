"""Internal device registration; bearer authority and the original admission gate."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from gateway_backend.application.provisioning.registration import DeviceRegistration
from gateway_backend.application.provisioning.contracts import (
    RegistrationConflict,
    RegistrationDependencyUnavailable,
)
from gateway_backend.http.auth import require_internal_bearer
from gateway_backend.http.dependencies import acquire_new_work
from gateway_backend.http.errors import ApiError
from gateway_backend.http.routes.maintenance import _gate
from gateway_backend.http.schemas.device_registration import (
    DeviceRegistrationResponse,
    RegisterDeviceRequest,
    ScopeIdentity,
)

router = APIRouter(tags=["device-registration"], dependencies=[Depends(require_internal_bearer)])


def _application(request: Request) -> DeviceRegistration:
    application = getattr(request.app.state, "device_registration", None)
    if not isinstance(application, DeviceRegistration):
        raise ApiError(
            code="SERVICE_NOT_READY", message="device registration unavailable", status_code=503
        )
    return application


@router.post(
    "/internal/v1/devices/register",
    response_model=DeviceRegistrationResponse,
    include_in_schema=False,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        409: {"description": "DEVICE_REGISTRATION_CONFLICT"},
        413: {"description": "REQUEST_TOO_LARGE"},
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "SERVICE_NOT_READY or DEPENDENCY_UNAVAILABLE"},
    },
)
async def register_device(
    request: Request, body: RegisterDeviceRequest
) -> DeviceRegistrationResponse:
    with acquire_new_work(_gate(request), closed_code="SERVICE_NOT_READY", closed_status=503):
        try:
            result = await _application(request).register(
                environment=body.environment_id,
                group=body.group_id,
                device=body.gateway_device_external_key,
                project=body.business_project_id,
            )
        except RegistrationConflict:
            raise ApiError(
                code="DEVICE_REGISTRATION_CONFLICT",
                message="device registration conflicts with fixed scope",
                status_code=409,
            ) from None
        except RegistrationDependencyUnavailable:
            raise ApiError(
                code="DEPENDENCY_UNAVAILABLE",
                message="repository service unavailable or unresolved",
                status_code=503,
            ) from None
    return DeviceRegistrationResponse.model_validate(asdict(result))


@router.get(
    "/internal/v1/devices/registration",
    response_model=DeviceRegistrationResponse,
    include_in_schema=False,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        409: {"description": "DEVICE_REGISTRATION_CONFLICT"},
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def query_registration(
    request: Request, device: Annotated[ScopeIdentity, Query()]
) -> DeviceRegistrationResponse:
    if (
        list(request.query_params.keys()) != ["device"]
        or len(request.query_params.getlist("device")) != 1
    ):
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED", message="request validation failed", status_code=422
        )
    try:
        result = _application(request).query(device)
    except RegistrationConflict:
        raise ApiError(
            code="DEVICE_REGISTRATION_CONFLICT",
            message="device registration conflicts with fixed scope",
            status_code=409,
        ) from None
    if result is None:
        raise ApiError(code="RESOURCE_NOT_FOUND", message="resource not found", status_code=404)
    return DeviceRegistrationResponse.model_validate(asdict(result))
