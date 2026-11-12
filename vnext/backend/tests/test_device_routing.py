"""The receiving backend is the authority even when entry routing is wrong."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from typing import cast
from fastapi import FastAPI

import pytest
from starlette.requests import Request

from gateway_backend.device_identity import device_route_key
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeResolutionError
from gateway_backend.http.auth import require_identity
from gateway_backend.http.errors import ApiError
from gateway_backend.http.routes.statistics import _internal_group_identity
from tests.support.http_workspace_harness import create_workspace_http_environment

pytestmark = pytest.mark.unit
INVALID_HEADERS = [[], [(b'x-gateway-device-key', b'a' * 63)],
    [(b'x-gateway-device-key', b'A' * 64)], [(b'x-gateway-device-key', b'a' * 65)],
    [(b'x-gateway-device-key', b'\xe8\xae\xbe\xe5\xa4\x87')],
    [(b'x-gateway-device-key', b'a' * 64), (b'x-gateway-device-key', b'a' * 64)],
    [(b'x-gateway-device-key', b'a' * 64 + b', ' + b'a' * 64)]]


@pytest.mark.parametrize('headers', INVALID_HEADERS)
def test_route_header_is_single_strict_ascii_hex(tmp_path: Path, headers: list[tuple[bytes, bytes]]) -> None:
    env = create_workspace_http_environment(tmp_path)
    request = Request({'type': 'http', 'app': env.client.app, 'headers': headers})
    with pytest.raises(ApiError) as error:
        require_identity(request, env.identity, '')
    assert error.value.status_code == 422


def test_bearer_precedes_route_validation_and_unknown_key_is_not_a_default_group(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path)
    assert env.client.get('/v1/device-context').status_code == 401
    assert env.client.get('/v1/device-context', headers={'Authorization': env.auth_headers()['Authorization']}).status_code == 422
    assert env.client.get('/v1/device-context', headers={**env.auth_headers(), 'X-Gateway-Device-Key': device_route_key('other')}).status_code == 404


def test_context_needs_local_scope_and_remains_readable_while_admission_is_closed(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path)
    cast(FastAPI, env.client.app).state.deployment_identity = ('environment', 'group-a')
    response = env.client.get('/v1/device-context', headers=env.auth_headers())
    assert response.status_code == 200
    assert response.json() == {'environment_id': 'environment', 'group_id': 'group-a',
        'gateway_device_external_key': env.identity.gateway_device_external_key,
        'business_project_id': env.identity.business_project_id, 'repository_id': env.scope_resolution.resolve(env.identity).repository_id}
    with patch.object(env.scope_resolution, 'resolve', side_effect=ScopeResolutionError('wrong local group')):
        for path in ('/v1/device-context', '/v1/operations/unknown'):
            rejected = env.client.get(path, headers=env.auth_headers())
            assert rejected.status_code == 404
            assert rejected.json()['code'] == 'RESOURCE_NOT_FOUND'
    gate = cast(FastAPI, env.client.app).state.admission_gate
    with patch.object(gate, 'allows_new_work', return_value=False):
        assert env.client.get('/v1/device-context', headers=env.auth_headers()).status_code == 200


def test_internal_statistics_uses_current_session_permission_without_mapping(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path)
    identity = replace(env.identity, permissions=frozenset({'statistics_read_group'}))
    deps = cast(FastAPI, env.client.app).state.workspace_http
    with patch.object(deps.session_port, 'resolve', return_value=identity), \
            patch.object(env.scope_resolution, 'resolve', side_effect=AssertionError('internal read must not resolve device')):
        request = Request({'type': 'http', 'app': env.client.app, 'headers': [], 'client': ('127.0.0.1', 1)})
        assert _internal_group_identity(request) == identity
        request = Request({'type': 'http', 'app': env.client.app, 'headers': [], 'client': ('10.0.0.1', 1)})
        with pytest.raises(ApiError) as hidden:
            _internal_group_identity(request)
        assert hidden.value.status_code == 404
    with patch.object(deps.session_port, 'resolve', return_value=env.identity):
        request = Request({'type': 'http', 'app': env.client.app, 'headers': [], 'client': ('127.0.0.1', 1)})
        with pytest.raises(PermissionDenied):
            _internal_group_identity(request)


def test_internal_statistics_trusts_only_actual_gateway_not_host_or_forwarded_headers(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path)
    identity = replace(env.identity, permissions=frozenset({'statistics_read_group'}))
    deps = cast(FastAPI, env.client.app).state.workspace_http
    with patch.object(deps.session_port, 'resolve', return_value=identity), \
            patch('gateway_backend.http.routes.statistics._default_gateway_peer', return_value='172.23.0.1'):
        for peer, allowed in [('172.23.0.1', True), ('172.23.0.2', False), ('10.0.0.1', False)]:
            request = Request({'type': 'http', 'app': env.client.app, 'client': (peer, 1),
                'headers': [(b'host', b'127.0.0.1'), (b'x-forwarded-for', b'127.0.0.1')]})
            if allowed:
                assert _internal_group_identity(request) == identity
            else:
                with pytest.raises(ApiError) as error:
                    _internal_group_identity(request)
                assert error.value.status_code == 404
