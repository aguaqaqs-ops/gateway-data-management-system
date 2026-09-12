"""Secret-file repository read settings and HTTP/Arrow table-access adapter."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gateway_backend.domain.workspace.models import BaselineHead
from gateway_backend.infrastructure.repository_read.http_arrow import (
    HttpArrowRepositoryTableAccessProvider,
    build_http_repository_provider_factory,
)


def load_repository_bearer_token(token_file: Path) -> str:
    """Read a bearer token from a server-owned file without embedding it in errors."""

    if not isinstance(token_file, Path) or not token_file.is_absolute():
        raise ValueError("repository bearer token file must be absolute")
    try:
        if not token_file.is_file():
            raise ValueError("repository bearer token file is unreadable")
        token = token_file.read_text(encoding="utf-8").strip()
    except OSError:
        raise ValueError("repository bearer token file is unreadable") from None
    if token == "":
        raise ValueError("repository bearer token file is empty")
    return token


class FailClosedBaselineHeadRead:
    """BaselineHead port that fails closed until a provisioned mapping exists."""

    def get_current_head(self, repository_id: str) -> BaselineHead:
        del repository_id
        raise KeyError("provisioned baseline head is missing")


class UnwiredRepositoryTableAccessProvider:
    """Fail-closed table-access provider retained only as a test seam."""

    def open_ref(self, repository_ref: object, timeout_policy: object = None) -> object:
        del repository_ref, timeout_policy
        raise RuntimeError("repository table-access adapter is not wired")


def build_unwired_repository_provider_factory(
    token: str,
) -> Callable[[str, str], UnwiredRepositoryTableAccessProvider]:
    """Bind the loaded token in memory and never return it to logs or events."""

    if type(token) is not str or token == "":
        raise ValueError("repository bearer token is missing")
    bound_token = token

    def factory(repository_id: str, commit_id: str) -> UnwiredRepositoryTableAccessProvider:
        del repository_id, commit_id
        if bound_token == "":
            raise ValueError("repository bearer token is missing")
        return UnwiredRepositoryTableAccessProvider()

    return factory


__all__ = [
    "FailClosedBaselineHeadRead",
    "HttpArrowRepositoryTableAccessProvider",
    "UnwiredRepositoryTableAccessProvider",
    "build_http_repository_provider_factory",
    "build_unwired_repository_provider_factory",
    "load_repository_bearer_token",
]
