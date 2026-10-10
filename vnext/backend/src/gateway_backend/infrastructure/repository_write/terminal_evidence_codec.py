"""Wire-backed decode adapter for persisted submit terminal repository evidence."""

from __future__ import annotations

from gateway_backend.application.submission.contracts import RepositoryImportOperation
from gateway_backend.infrastructure.repository_write.wire_codec import (
    import_operation_from_evidence_payload,
)


class WireRepositoryTerminalEvidenceDecodePort:
    def decode_from_evidence_payload(
        self,
        operation_payload: dict[str, object],
    ) -> RepositoryImportOperation:
        return import_operation_from_evidence_payload(operation_payload)


__all__ = ["WireRepositoryTerminalEvidenceDecodePort"]
