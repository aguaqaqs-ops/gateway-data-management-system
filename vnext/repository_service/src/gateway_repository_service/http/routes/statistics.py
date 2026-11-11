"""Authenticated read of existing ring entries; never performs collection."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request

from gateway_repository_contracts.statistics import StatisticsFeedQuery, StatisticsFeedResponse
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.statistics import ObservationRing


def register_statistics_routes(app: FastAPI) -> None:
    @app.get('/v1/statistics/observations', response_model=StatisticsFeedResponse,
             responses={401: {'description': 'Authentication failed'}})
    def get_observations(request: Request,
                         _authorized: Annotated[None, Depends(require_bearer_token)],
                         instance_id: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
                         after_sequence: Annotated[int, Query(ge=0, le=2**63-1)] = 0,
                         limit: Annotated[int, Query(ge=1, le=100)] = 100) -> StatisticsFeedResponse:
        ring = getattr(request.app.state, 'statistics_ring', None)
        if not isinstance(ring, ObservationRing):
            # Disabled collection still exposes an empty instance, never starts a scanner.
            ring = request.app.state.empty_statistics_ring
        return ring.read(StatisticsFeedQuery(instance_id=instance_id, after_sequence=after_sequence, limit=limit))
