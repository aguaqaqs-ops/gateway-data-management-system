"""Gateway vNext Repository Service client SDK package."""

from gateway_repository_client.client import RepositoryClient
from gateway_repository_client.errors import RepositoryClientError
from gateway_repository_client.retry import (
    DEFAULT_BASE_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    RETRYABLE_STATUS_CODES,
    retry_idempotent_request,
)
from gateway_repository_client.upload import (
    NonRewindableBody,
    NonRewindableUploadSourceError,
    RewindableBody,
    UploadBodySource,
    coerce_upload_body_source,
)

__all__ = [
    "DEFAULT_BASE_DELAY_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "NonRewindableBody",
    "NonRewindableUploadSourceError",
    "RETRYABLE_STATUS_CODES",
    "RepositoryClient",
    "RepositoryClientError",
    "RewindableBody",
    "UploadBodySource",
    "coerce_upload_body_source",
    "retry_idempotent_request",
]
