"""Shared catalog failure metadata for the native filtering adapter."""

from gateway_backend.capabilities.composite_signal.contracts import CompositeDiagnosticCode


class CatalogError(Exception):
    def __init__(self, code: CompositeDiagnosticCode, message: str, *, table: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.table = table

