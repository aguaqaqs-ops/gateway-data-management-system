"""HTTP pre-drain coordination for admission-first shutdown."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from gateway_backend.http.dependencies import ClosableAdmissionGate


def resolve_fastapi_app(app: Any) -> FastAPI | None:
    """Unwrap Uvicorn middleware to reach the FastAPI instance with process state."""

    current = app
    seen: set[int] = set()
    while id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, FastAPI):
            return current
        inner = getattr(current, "app", None)
        if inner is None or inner is current:
            break
        current = inner
    return None


def begin_http_pre_drain(app: Any) -> None:
    """Mark the process not ready and close creation admission before connection drain."""

    fastapi_app = resolve_fastapi_app(app)
    if fastapi_app is None:
        return
    fastapi_app.state.ready = False
    gate = getattr(fastapi_app.state, "admission_gate", None)
    if isinstance(gate, ClosableAdmissionGate):
        gate.close()
