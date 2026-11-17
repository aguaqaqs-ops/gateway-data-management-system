"""Internal process-local creation drain; reads and recovery remain available."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from gateway_backend.http.auth import require_internal_bearer
from gateway_backend.http.dependencies import ClosableAdmissionGate
from gateway_backend.http.errors import ApiError

router = APIRouter(tags=["maintenance"], dependencies=[Depends(require_internal_bearer)])


class DrainSnapshot(BaseModel):
    accepting_new_work: bool
    in_flight: Annotated[int, Field(ge=0)]


def _gate(request: Request) -> ClosableAdmissionGate:
    gate = getattr(request.app.state, "admission_gate", None)
    if not isinstance(gate, ClosableAdmissionGate):
        raise ApiError(
            code="SERVICE_NOT_READY", message="maintenance gate unavailable", status_code=503
        )
    return gate


@router.get(
    "/internal/v1/maintenance/drain",
    response_model=DrainSnapshot,
    include_in_schema=False,
)
def drain_status(request: Request) -> dict[str, bool | int]:
    return _gate(request).snapshot()


@router.post(
    "/internal/v1/maintenance/drain",
    response_model=DrainSnapshot,
    include_in_schema=False,
)
def drain(request: Request) -> dict[str, bool | int]:
    gate = _gate(request)
    gate.close()
    request.app.state.ready = False
    return gate.snapshot()
