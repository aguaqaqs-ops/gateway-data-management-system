"""Unicode scalar validation for strict JSON wire paths."""

from __future__ import annotations

from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode


def validate_unicode_string(text: str) -> None:
    for codepoint in map(ord, text):
        if 0xD800 <= codepoint <= 0xDFFF:
            raise RepositoryContractError(
                RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
                "string contains lone UTF-16 surrogate",
            )
        if is_unicode_noncharacter(codepoint):
            raise RepositoryContractError(
                RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
                "string contains Unicode noncharacter",
            )


def is_unicode_noncharacter(codepoint: int) -> bool:
    if 0xFDD0 <= codepoint <= 0xFDEF:
        return True
    return (codepoint & 0xFFFE) == 0xFFFE and 0xFFFE <= codepoint <= 0x10FFFF
