"""Byte-oriented SQL dump scanner. Does not execute SQL."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from gateway_shared_kernel import CanonicalEncodingError, canonicalize_identifier

from gateway_backend.capabilities.table_access._parser_runtime import ParserHalt, ParserRuntime
from gateway_backend.capabilities.table_access.contracts import ParserDiagnosticCode

_WS = frozenset({0x09, 0x0A, 0x0D, 0x20})
_IDENT_START = frozenset(range(ord("A"), ord("Z") + 1)) | frozenset(
    range(ord("a"), ord("z") + 1)
) | {ord("_")}
_IDENT_CONTINUE = _IDENT_START | frozenset(range(ord("0"), ord("9") + 1)) | {ord("$")}
_DIGITS = frozenset(range(ord("0"), ord("9") + 1))
_HEX = _DIGITS | frozenset(range(ord("A"), ord("F") + 1)) | frozenset(
    range(ord("a"), ord("f") + 1)
)
_VERSIONED_HEAD = b"/*!"
_BLOCK_HEAD = b"/*"
_BLOCK_TAIL = b"*/"
_ALLOWLIST_INNER_HEADS = (
    b"set",
    b"create",
    b"insert",
    b"drop",
    b"lock",
    b"unlock",
    b"alter",
)


@dataclass(frozen=True, slots=True)
class SqlStatementSpan:
    start: int
    end: int


class ByteCursor:
    def __init__(self, data: bytes, start: int, end: int) -> None:
        if type(data) is not bytes:
            raise ValueError("data must be bytes")
        if type(start) is not int or type(end) is not int or start < 0 or end < start:
            raise ValueError("cursor range is invalid")
        if end > len(data):
            raise ValueError("cursor end exceeds data")
        self.data = data
        self.start = start
        self.end = end
        self.pos = start

    def at_end(self) -> bool:
        return self.pos >= self.end

    def peek(self) -> int | None:
        if self.pos >= self.end:
            return None
        return self.data[self.pos]

    def skip_ws_and_comments(self, runtime: ParserRuntime) -> None:
        while self.pos < self.end:
            runtime.checkpoint(self.pos)
            byte = self.data[self.pos]
            if byte in _WS:
                self.pos += 1
                continue
            if byte == ord("-") and _starts_dash_comment(self.data, self.pos, self.end):
                self._skip_line_comment()
                continue
            if byte == ord("#"):
                self._skip_line_comment()
                continue
            if _starts_with(self.data, self.pos, self.end, _VERSIONED_HEAD):
                self._reject_inline_versioned(runtime)
            if _starts_with(self.data, self.pos, self.end, _BLOCK_HEAD):
                self._skip_block_comment(runtime)
                continue
            return

    def try_keyword(self, keyword: str, runtime: ParserRuntime) -> bool:
        self.skip_ws_and_comments(runtime)
        encoded = keyword.encode("ascii")
        length = len(encoded)
        if self.pos + length > self.end:
            return False
        fragment = self.data[self.pos : self.pos + length]
        if fragment.lower() != encoded:
            return False
        after = self.pos + length
        if after < self.end and self.data[after] in _IDENT_CONTINUE:
            return False
        self.pos = after
        return True

    def parse_identifier(self, runtime: ParserRuntime) -> tuple[str, str]:
        self.skip_ws_and_comments(runtime)
        start = self.pos
        if self.peek() == ord("`"):
            display = self._parse_backtick_identifier(runtime)
        elif self.peek() == ord('"'):
            runtime.fail_document(
                ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
                "ANSI_QUOTES double-quoted identifiers are not in the source dump allowlist",
                self.pos,
            )
        else:
            display = self._parse_unquoted_identifier(runtime)
        if len(display) > runtime.budgets.max_identifier_code_points:
            runtime.fail_document(
                ParserDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
                "max_identifier_code_points exceeded",
                start,
            )
        try:
            canonical = canonicalize_identifier(display)
        except CanonicalEncodingError as exc:
            runtime.fail_document(
                ParserDiagnosticCode.CANONICAL_IDENTIFIER_COLLISION
                if exc.code.value == "CANONICAL_IDENTIFIER_COLLISION"
                else ParserDiagnosticCode.MALFORMED_SQL,
                str(exc),
                start,
            )
        if canonical == "":
            runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_SQL,
                "identifier must not be empty",
                start,
            )
        return display, canonical

    def parse_table_name(self, runtime: ParserRuntime) -> tuple[str, str]:
        display, canonical = self.parse_identifier(runtime)
        self.skip_ws_and_comments(runtime)
        if self.peek() == ord("."):
            self.pos += 1
            display, canonical = self.parse_identifier(runtime)
        return display, canonical

    def expect(self, punct: int, runtime: ParserRuntime, message: str) -> None:
        self.skip_ws_and_comments(runtime)
        if self.peek() != punct:
            runtime.fail_document(ParserDiagnosticCode.MALFORMED_SQL, message, self.pos)
        self.pos += 1

    def take_balanced_paren(self, runtime: ParserRuntime) -> tuple[int, int]:
        self.skip_ws_and_comments(runtime)
        start = self.pos
        if self.peek() != ord("("):
            runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_SQL,
                "expected '('",
                self.pos,
            )
        depth = 0
        quote: int | None = None
        escape = False
        while self.pos < self.end:
            runtime.checkpoint(self.pos)
            byte = self.data[self.pos]
            if quote is not None:
                if escape:
                    escape = False
                    self.pos += 1
                    continue
                if byte == ord("\\") and quote == ord("'"):
                    escape = True
                    self.pos += 1
                    continue
                if byte == quote:
                    nxt = self.pos + 1
                    if quote == ord("'") and nxt < self.end and self.data[nxt] == quote:
                        self.pos += 2
                        continue
                    if quote == ord("`") and nxt < self.end and self.data[nxt] == quote:
                        self.pos += 2
                        continue
                    quote = None
                self.pos += 1
                continue
            if byte == ord("'") or byte == ord("`"):
                quote = byte
                self.pos += 1
                continue
            if byte == ord('"'):
                runtime.fail_document(
                    ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
                    "ANSI_QUOTES double-quoted identifiers are not in the source dump allowlist",
                    self.pos,
                )
            if _starts_with(self.data, self.pos, self.end, _VERSIONED_HEAD):
                self._reject_inline_versioned(runtime)
            if _starts_with(self.data, self.pos, self.end, _BLOCK_HEAD):
                self._skip_block_comment(runtime)
                continue
            if byte == ord("-") and _starts_dash_comment(self.data, self.pos, self.end):
                self._skip_line_comment()
                continue
            if byte == ord("#"):
                self._skip_line_comment()
                continue
            if byte == ord("("):
                depth += 1
            elif byte == ord(")"):
                depth -= 1
                self.pos += 1
                if depth == 0:
                    return start, self.pos
                continue
            self.pos += 1
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "unclosed parenthesis",
            start,
        )
        raise AssertionError("unreachable")

    def _parse_unquoted_identifier(self, runtime: ParserRuntime) -> str:
        if self.peek() not in _IDENT_START:
            runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_SQL,
                "expected identifier",
                self.pos,
            )
        start = self.pos
        self.pos += 1
        while self.pos < self.end and self.data[self.pos] in _IDENT_CONTINUE:
            self.pos += 1
        return self.data[start : self.pos].decode("ascii")

    def _parse_backtick_identifier(self, runtime: ParserRuntime) -> str:
        start = self.pos
        self.pos += 1
        chunks: list[bytes] = []
        piece_start = self.pos
        while self.pos < self.end:
            if self.data[self.pos] != ord("`"):
                self.pos += 1
                continue
            chunks.append(self.data[piece_start : self.pos])
            nxt = self.pos + 1
            if nxt < self.end and self.data[nxt] == ord("`"):
                chunks.append(b"`")
                self.pos += 2
                piece_start = self.pos
                continue
            self.pos += 1
            raw = b"".join(chunks)
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ParserHalt(
                    ParserDiagnosticCode.MALFORMED_SQL,
                    "identifier is not strict UTF-8",
                    start,
                ) from exc
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "unclosed quoted identifier",
            start,
        )
        raise AssertionError("unreachable")

    def _skip_line_comment(self) -> None:
        while self.pos < self.end and self.data[self.pos] not in {0x0A, 0x0D}:
            self.pos += 1

    def _skip_block_comment(self, runtime: ParserRuntime) -> None:
        start = self.pos
        self.pos += 2
        while self.pos + 1 < self.end:
            if self.data[self.pos] == ord("*") and self.data[self.pos + 1] == ord("/"):
                self.pos += 2
                return
            self.pos += 1
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "unclosed block comment",
            start,
        )

    def _reject_inline_versioned(self, runtime: ParserRuntime) -> None:
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            "versioned comment is not an allowlisted statement",
            self.pos,
        )


def iter_statements(data: bytes, runtime: ParserRuntime) -> Iterator[SqlStatementSpan]:
    if type(data) is not bytes:
        raise ValueError("data must be bytes")
    cursor = ByteCursor(data, 0, len(data))
    while True:
        runtime.checkpoint(cursor.pos)
        _skip_leading_trivia(cursor, runtime)
        if cursor.at_end():
            return
        if _starts_with(data, cursor.pos, cursor.end, _VERSIONED_HEAD):
            span = _expand_versioned_statement(cursor, runtime)
        else:
            span = _scan_plain_statement(cursor, runtime)
        if span.end - span.start > runtime.budgets.max_statement_bytes:
            runtime.resource_exceeded("max_statement_bytes", span.start)
        yield span


def _skip_leading_trivia(cursor: ByteCursor, runtime: ParserRuntime) -> None:
    data = cursor.data
    while cursor.pos < cursor.end:
        runtime.checkpoint(cursor.pos)
        byte = data[cursor.pos]
        if byte in _WS:
            cursor.pos += 1
            continue
        if byte == ord("-") and _starts_dash_comment(data, cursor.pos, cursor.end):
            cursor._skip_line_comment()
            continue
        if byte == ord("#"):
            cursor._skip_line_comment()
            continue
        if _starts_with(data, cursor.pos, cursor.end, _VERSIONED_HEAD):
            return
        if _starts_with(data, cursor.pos, cursor.end, _BLOCK_HEAD):
            cursor._skip_block_comment(runtime)
            continue
        if byte == ord(";"):
            cursor.pos += 1
            continue
        return


def _expand_versioned_statement(cursor: ByteCursor, runtime: ParserRuntime) -> SqlStatementSpan:
    start = cursor.pos
    if cursor.pos + 3 >= cursor.end:
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "unclosed versioned comment",
            start,
        )
    cursor.pos += 3
    while cursor.pos < cursor.end and cursor.data[cursor.pos] in _DIGITS:
        cursor.pos += 1
    inner_start = cursor.pos
    close = _find_block_close(cursor.data, cursor.pos, cursor.end)
    if close is None:
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "unclosed versioned comment",
            start,
        )
    inner_end = close
    inner = cursor.data[inner_start:inner_end]
    stripped = inner.lstrip()
    if not _inner_is_allowlisted(stripped):
        runtime.fail_document(
            ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
            "versioned comment is not an allowlisted statement",
            start,
        )
    cursor.pos = close + 2
    _skip_ws_only(cursor)
    if cursor.peek() == ord(";"):
        cursor.pos += 1
    return SqlStatementSpan(inner_start, inner_end)


def _scan_plain_statement(cursor: ByteCursor, runtime: ParserRuntime) -> SqlStatementSpan:
    start = cursor.pos
    quote: int | None = None
    escape = False
    while cursor.pos < cursor.end:
        runtime.checkpoint(cursor.pos)
        byte = cursor.data[cursor.pos]
        if quote is not None:
            if escape:
                escape = False
                cursor.pos += 1
                continue
            if byte == ord("\\") and quote == ord("'"):
                escape = True
                cursor.pos += 1
                continue
            if byte == quote:
                nxt = cursor.pos + 1
                if quote in {ord("'"), ord("`")} and nxt < cursor.end and cursor.data[nxt] == quote:
                    cursor.pos += 2
                    continue
                quote = None
            cursor.pos += 1
            continue
        if byte == ord("'") or byte == ord("`"):
            quote = byte
            cursor.pos += 1
            continue
        if byte == ord('"'):
            runtime.fail_document(
                ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
                "ANSI_QUOTES double-quoted identifiers are not in the source dump allowlist",
                cursor.pos,
            )
        if _starts_with(cursor.data, cursor.pos, cursor.end, _VERSIONED_HEAD):
            cursor._reject_inline_versioned(runtime)
        if _starts_with(cursor.data, cursor.pos, cursor.end, _BLOCK_HEAD):
            cursor._skip_block_comment(runtime)
            continue
        if byte == ord("-") and _starts_dash_comment(cursor.data, cursor.pos, cursor.end):
            cursor._skip_line_comment()
            continue
        if byte == ord("#"):
            cursor._skip_line_comment()
            continue
        if byte == ord(";"):
            end = cursor.pos
            cursor.pos += 1
            return SqlStatementSpan(start, end)
        cursor.pos += 1
    if quote is not None:
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_SQL,
            "unclosed quoted literal",
            start,
        )
    return SqlStatementSpan(start, cursor.pos)


def _inner_is_allowlisted(inner: bytes) -> bool:
    lowered = inner.lstrip().lower()
    for head in _ALLOWLIST_INNER_HEADS:
        if lowered.startswith(head) and (
            len(lowered) == len(head) or lowered[len(head)] not in _IDENT_CONTINUE
        ):
            return True
    return False


def _find_block_close(data: bytes, start: int, end: int) -> int | None:
    index = start
    while index + 1 < end:
        if data[index] == ord("*") and data[index + 1] == ord("/"):
            return index
        index += 1
    return None


def _starts_with(data: bytes, pos: int, end: int, token: bytes) -> bool:
    return pos + len(token) <= end and data[pos : pos + len(token)] == token


def _starts_dash_comment(data: bytes, pos: int, end: int) -> bool:
    if pos + 2 > end or data[pos] != ord("-") or data[pos + 1] != ord("-"):
        return False
    if pos + 2 == end:
        return True
    return data[pos + 2] in _WS


def _skip_ws_only(cursor: ByteCursor) -> None:
    while cursor.pos < cursor.end and cursor.data[cursor.pos] in _WS:
        cursor.pos += 1


def is_digit(byte: int) -> bool:
    return byte in _DIGITS


def is_hex(byte: int) -> bool:
    return byte in _HEX
