"""HTTP header models for synchronous create and upload mutations."""

from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, field_validator

from gateway_repository_contracts.types import Sha256String

REPOSITORY_IMPORT_MEDIA_TYPE = "application/vnd.gateway.repository-import.v1+tar+zstd"

DEFAULT_MAX_UPLOAD_BYTES = 256 * 1024 * 1024

IdempotencyKeyString: TypeAlias = Annotated[
    str,
    Field(min_length=1, max_length=255),
]


class _HeaderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UploadRequestHeaders(_HeaderModel):
    """Required headers for raw-body artifact upload."""

    content_type: str
    content_length: NonNegativeInt
    idempotency_key: IdempotencyKeyString
    artifact_sha256: Sha256String

    @field_validator("content_type")
    @classmethod
    def _content_type_must_match_repository_import_media_type(cls, value: str) -> str:
        if value != REPOSITORY_IMPORT_MEDIA_TYPE:
            raise ValueError("content_type must be the repository import media type")
        return value

    @field_validator("content_length")
    @classmethod
    def _content_length_must_be_within_default_upload_limit(cls, value: int) -> int:
        if value > DEFAULT_MAX_UPLOAD_BYTES:
            raise ValueError("content_length exceeds the default upload limit")
        return value


def validate_upload_content_length(
    content_length: int,
    *,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> int:
    """Validate declared upload size against a deployment-configured upper bound."""
    if content_length < 0:
        raise ValueError("content_length must be non-negative")
    if content_length > max_upload_bytes:
        raise ValueError("content_length exceeds configured upload limit")
    return content_length
