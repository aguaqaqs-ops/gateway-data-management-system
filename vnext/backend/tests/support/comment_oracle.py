"""Independent CREATE/COMMENT subset oracle; never imports the native parser."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"--[^\n]*(?:\n|$)|\#[^\n]*(?:\n|$)|/\*.*?\*/|'(?:\\.|''|[^'\\])*'|`(?:``|[^`])*`|[A-Za-z_][A-Za-z_0-9]*|\S", re.S)
_ESCAPE = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "Z": "\x1a", "b": "\b"}


def _string(token: str) -> str | None:
    if not token.startswith("'"):
        raise ValueError("COMMENT requires a string")
    body = token[1:-1]
    decoded = re.sub(r"\\(.)|('')", lambda match: _ESCAPE.get(match[1], match[1]) if match[1] is not None else "'", body, flags=re.S)
    if "\0" in decoded:
        raise ValueError("NUL comment")
    return decoded if decoded.strip() else None


def comment_oracle(sql: str) -> dict[str, object]:
    tokens = [m[0] for m in _TOKEN.finditer(sql) if not m[0].startswith(("--", "#", "/*"))]
    tables = []
    index = 0
    while index < len(tokens):
        if tokens[index].casefold() != "create":
            index += 1
            continue
        assert tokens[index + 1].casefold() == "table"
        name = tokens[index + 2].strip("`").casefold()
        index += 4
        columns = []
        while tokens[index] != ")":
            column = tokens[index].strip("`").casefold()
            index += 1
            depth = 0
            comment = None
            while not (depth == 0 and tokens[index] in (",", ")")):
                token = tokens[index]
                if depth == 0 and token.casefold() == "comment":
                    comment = _string(tokens[index + 1])
                    index += 1
                elif token == "(":
                    depth += 1
                elif token == ")":
                    depth -= 1
                index += 1
            columns.append({"name": column, "comment": comment})
            if tokens[index] == ",":
                index += 1
        index += 1
        comment = None
        while index < len(tokens) and tokens[index] != ";":
            if tokens[index].casefold() == "comment":
                index += 1
                if tokens[index] == "=":
                    index += 1
                comment = _string(tokens[index])
            index += 1
        tables.append({"table_name": name, "comment": comment, "columns": columns})
    return {"tables": sorted(tables, key=lambda t: str(t["table_name"]).encode())}
