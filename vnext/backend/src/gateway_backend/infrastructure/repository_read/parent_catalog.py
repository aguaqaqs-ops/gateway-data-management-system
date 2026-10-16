"""Exact-commit Repository parent catalog adapter for Submit preparation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import httpx
from gateway_repository_client import RepositoryClient
from gateway_repository_client.errors import RepositoryClientError, RepositoryProtocolError

from gateway_backend.application.submission.errors import SubmitImportPublicationError


@dataclass(frozen=True, slots=True)
class HttpRepositoryParentCatalogPort:
    base_url: str
    bearer_token: str
    timeout_seconds: float = 30.0
    transport: httpx.AsyncBaseTransport | None = None

    def get_table_names(self, *, repository_id: str, commit_id: str) -> tuple[str, ...]:
        try:
            response = asyncio.run(
                RepositoryClient(
                    base_url=self.base_url,
                    bearer_token=self.bearer_token,
                    timeout_seconds=self.timeout_seconds,
                    transport=self.transport,
                ).get_versioned_catalog(
                    repository_id=UUID(repository_id),
                    commit_id=commit_id,
                )
            )
        except (ValueError, RepositoryClientError, RepositoryProtocolError, httpx.HTTPError) as exc:
            raise SubmitImportPublicationError(
                "frozen Repository parent catalog is unavailable"
            ) from exc

        if response.catalog.commit_id != commit_id:
            raise SubmitImportPublicationError(
                "Repository parent catalog commit does not match the frozen expected parent"
            )
        table_names = tuple(table.name for table in response.catalog.tables)
        if len(table_names) != len(set(table_names)):
            raise SubmitImportPublicationError("Repository parent catalog contains duplicate tables")
        return tuple(sorted(table_names, key=lambda name: name.encode("utf-8")))


__all__ = ["HttpRepositoryParentCatalogPort"]
