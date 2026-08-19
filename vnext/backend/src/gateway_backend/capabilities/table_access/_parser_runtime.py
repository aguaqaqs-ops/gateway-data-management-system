"""Cancel, timeout, budget and diagnostic helpers for table_access parsers."""

from __future__ import annotations

import time
from typing import NoReturn

from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS,
    DiagnosticSeverity,
    DiagnosticSource,
    ParserDiagnostic,
    ParserDiagnosticCode,
    ParserInvocationContext,
    ResourceBudgets,
    diagnostic_sort_key,
)

_TRUNCATED_MESSAGE = "parser diagnostics truncated"


class ParserHalt(Exception):
    """Document-level stop: cancel, timeout, or fail-closed statement."""

    def __init__(self, code: ParserDiagnosticCode, message: str, byte_offset: int) -> None:
        if type(code) is not ParserDiagnosticCode:
            raise ValueError("code must be ParserDiagnosticCode")
        if type(message) is not str or message == "":
            raise ValueError("message must be a non-empty string")
        if type(byte_offset) is not int or byte_offset < 0:
            raise ValueError("byte_offset must be a non-negative int")
        super().__init__(message)
        self.code = code
        self.message = message
        self.byte_offset = byte_offset


class ParserRuntime:
    def __init__(
        self,
        context: ParserInvocationContext,
        budgets: ResourceBudgets = RESOURCE_BUDGETS,
        source: DiagnosticSource = DiagnosticSource.SQL,
    ) -> None:
        if type(context) is not ParserInvocationContext:
            raise ValueError("context must be ParserInvocationContext")
        if type(budgets) is not ResourceBudgets:
            raise ValueError("budgets must be ResourceBudgets")
        self.context = context
        self.budgets = budgets
        self.source = source
        self.document_failed = False
        self._diagnostics: list[ParserDiagnostic] = []

    def checkpoint(self, byte_offset: int) -> None:
        if type(byte_offset) is not int or byte_offset < 0:
            raise ValueError("byte_offset must be a non-negative int")
        if self.context.cancel_requested.is_set():
            raise ParserHalt(
                ParserDiagnosticCode.PARSER_CANCELLED,
                "parser cancelled",
                byte_offset,
            )
        deadline = self.context.deadline_monotonic
        if deadline is not None and time.monotonic() >= deadline:
            raise ParserHalt(
                ParserDiagnosticCode.PARSER_TIMEOUT,
                "parser deadline exceeded",
                byte_offset,
            )

    def add_diagnostic(
        self,
        code: ParserDiagnosticCode,
        message: str,
        byte_offset: int,
        *,
        table: str | None = None,
        column: str | None = None,
        severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
    ) -> None:
        if code not in {
            ParserDiagnosticCode.PARSER_CANCELLED,
            ParserDiagnosticCode.PARSER_TIMEOUT,
        }:
            self.checkpoint(byte_offset)
        text = _clip_message(message, self.budgets.max_diagnostic_message_bytes)
        self._diagnostics.append(
            ParserDiagnostic(
                code=code,
                severity=severity,
                source=self.source,
                byte_offset=byte_offset,
                message=text,
                table=table,
                column=column,
            )
        )

    def fail_document(
        self, code: ParserDiagnosticCode, message: str, byte_offset: int
    ) -> NoReturn:
        self.add_diagnostic(code, message, byte_offset)
        self.document_failed = True
        raise ParserHalt(code, message, byte_offset)

    def resource_exceeded(self, budget: str, byte_offset: int) -> NoReturn:
        self.fail_document(
            ParserDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            f"{budget} exceeded",
            byte_offset,
        )

    def record_halt(self, halt: ParserHalt) -> None:
        self.document_failed = True
        for diagnostic in self._diagnostics:
            if diagnostic.code is halt.code and diagnostic.byte_offset == halt.byte_offset:
                return
        self.add_diagnostic(halt.code, halt.message, halt.byte_offset)

    def finish_diagnostics(self) -> tuple[ParserDiagnostic, ...]:
        ordered = sorted(self._diagnostics, key=diagnostic_sort_key)
        kept: list[ParserDiagnostic] = []
        total = 0
        truncated = False
        for diagnostic in ordered:
            if diagnostic.code is ParserDiagnosticCode.PARSER_DIAGNOSTICS_TRUNCATED:
                continue
            size = len(diagnostic.message.encode("utf-8"))
            if (
                len(kept) >= self.budgets.max_diagnostics
                or total + size > self.budgets.max_diagnostics_total_bytes
            ):
                truncated = True
                break
            kept.append(diagnostic)
            total += size
        if truncated:
            offset = kept[-1].byte_offset if kept else 0
            marker = ParserDiagnostic(
                code=ParserDiagnosticCode.PARSER_DIAGNOSTICS_TRUNCATED,
                severity=DiagnosticSeverity.WARNING,
                source=self.source,
                byte_offset=offset,
                message=_clip_message(_TRUNCATED_MESSAGE, self.budgets.max_diagnostic_message_bytes),
            )
            marker_size = len(marker.message.encode("utf-8"))
            while kept and (
                len(kept) + 1 > self.budgets.max_diagnostics
                or total + marker_size > self.budgets.max_diagnostics_total_bytes
            ):
                removed = kept.pop()
                total -= len(removed.message.encode("utf-8"))
            if (
                len(kept) + 1 <= self.budgets.max_diagnostics
                and total + marker_size <= self.budgets.max_diagnostics_total_bytes
            ):
                kept.append(marker)
        return tuple(kept)


def _clip_message(message: str, max_bytes: int) -> str:
    if type(message) is not str or message == "":
        raise ValueError("message must be a non-empty string")
    encoded = message.encode("utf-8")
    if len(encoded) <= max_bytes:
        return message
    clipped = encoded[:max_bytes]
    while True:
        try:
            text = clipped.decode("utf-8")
        except UnicodeDecodeError:
            clipped = clipped[:-1]
            continue
        if text:
            return text
        raise ValueError("message exceeds max_diagnostic_message_bytes")
