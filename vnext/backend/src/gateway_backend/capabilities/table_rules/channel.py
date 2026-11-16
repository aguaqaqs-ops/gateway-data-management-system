"""Shared channel-table naming and reference classification rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gateway_backend.capabilities.table_rules.contracts import canonicalize_rule_identifier

_CHANNEL_TABLE = re.compile(r"^b([0-9]+)_([nc])([0-9]+)_(.+)$")
_MAX_CHANNEL_NUMBER = 9007199254740991


@dataclass(frozen=True, slots=True)
class ChannelTableName:
    board: int
    kind: str
    channel_no: int
    suffix: str


def _number(value: str) -> int | None:
    digits = value.lstrip("0") or "0"
    if len(digits) > 16:
        return None
    number = int(digits)
    return number if number <= _MAX_CHANNEL_NUMBER else None


def parse_channel_table_name(table_name: str) -> ChannelTableName | None:
    match = _CHANNEL_TABLE.fullmatch(canonicalize_rule_identifier(table_name))
    if match is None:
        return None
    board = _number(match[1])
    channel_no = _number(match[3])
    if board is None or channel_no is None:
        return None
    return ChannelTableName(board, match[2], channel_no, match[4])


def is_ordered_reference_table(table_name: str, table_comment: str | None) -> bool:
    return (parse_channel_table_name(table_name) is not None
            and table_comment is not None and "引用表" in table_comment)
