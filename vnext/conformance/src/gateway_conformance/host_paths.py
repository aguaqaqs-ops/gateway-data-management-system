"""Shared host-path detection and redaction for golden/sanitize."""

from __future__ import annotations

import re
from urllib.parse import unquote

_BOUNDARY = r"(?:^|[^A-Za-z0-9_.-])"
_PATH_GAP = r"\s+"
_PATH_BODY = rf"[^\s'\"(),;]+(?:{_PATH_GAP}[^\s'\"(),;]+)*"
ABSOLUTE_PATH = re.compile(_BOUNDARY + r"(/" + _PATH_BODY + r")")
WINDOWS_DRIVE_PATH = re.compile(_BOUNDARY + r"[A-Za-z]:(?:\\|/)" + _PATH_BODY)
UNC_PATH = re.compile(_BOUNDARY + r"\\\\" + _PATH_BODY)
FILE_URI = re.compile(
    r"file:(?:/{2,3}|(?:%(?:2[fF])){2,3})" + _PATH_BODY,
    re.IGNORECASE,
)
HOME_PATH = re.compile(_BOUNDARY + r"~(?:[A-Za-z0-9_.-]+)?(?:/|\\)" + _PATH_BODY)
ENV_HOME = re.compile(
    _BOUNDARY
    + r"(?:\$\{HOME\}|\$HOME|%USERPROFILE%|%HOMEDRIVE%%HOMEPATH%|%HOMEPATH%)"
    + r"(?:(?:/|\\)"
    + _PATH_BODY
    + r")?",
    re.IGNORECASE,
)
_SLASH_FOLD = str.maketrans(
    {
        "\uff0f": "/",  # ／
        "\u2215": "/",  # ∕
        "\u2044": "/",  # ⁄
        "\u29f8": "/",  # ⧸
        "\u2571": "/",  # ╱
        "\uff3c": "\\",  # ＼
        "\ufe68": "\\",  # ﹨
        "\u2572": "\\",  # ╲
        "\u2216": "\\",  # ∖
    }
)
_PUNCT_FOLD = str.maketrans(
    {
        "\uff1a": ":",  # ：
        "\uff5e": "~",  # ～
        "\u223c": "~",  # ∼
        "\u2053": "~",  # ⁓
    }
)
_UNQUOTE_ROUNDS = 4


def _normalize_folds(value: str) -> str:
    return value.translate(_SLASH_FOLD).translate(_PUNCT_FOLD)


def _unquote_variants(value: str) -> list[str]:
    variants: list[str] = []
    seen: set[str] = set()
    current = value
    for _ in range(_UNQUOTE_ROUNDS + 1):
        if current not in seen:
            seen.add(current)
            variants.append(current)
        nxt = unquote(current)
        if nxt == current:
            break
        current = nxt
    return variants


def _stabilize_forms(value: str) -> list[str]:
    """Collect unquote/fold closures so percent-encoded fullwidth chars are folded."""
    forms: list[str] = []
    seen: set[str] = set()
    queue = [value]
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        forms.append(cur)
        for nxt in (_normalize_folds(cur), unquote(cur)):
            if nxt not in seen and len(seen) < 64:
                queue.append(nxt)
    return forms


def _stabilize_text(value: str) -> str:
    current = value
    for _ in range(_UNQUOTE_ROUNDS * 2):
        nxt = _normalize_folds(unquote(current))
        if nxt == current:
            return current
        current = nxt
    return current


def _detection_forms(value: str) -> list[str]:
    return _stabilize_forms(value)


def _detect_raw(value: str) -> bool:
    if "/etc/passwd" in value:
        return True
    return (
        ABSOLUTE_PATH.search(value) is not None
        or WINDOWS_DRIVE_PATH.search(value) is not None
        or UNC_PATH.search(value) is not None
        or FILE_URI.search(value) is not None
        or HOME_PATH.search(value) is not None
        or ENV_HOME.search(value) is not None
    )


def contains_host_path(value: str) -> bool:
    """Return True if value embeds a host absolute path, Windows/UNC path, or file URI."""
    return any(_detect_raw(candidate) for candidate in _detection_forms(value))


def _regex_redact(text: str) -> str:
    # FILE_URI before ABSOLUTE_PATH so file:///... is not split into "file <path>".
    text = FILE_URI.sub("<path>", text)
    text = WINDOWS_DRIVE_PATH.sub("<path>", text)
    text = UNC_PATH.sub("<path>", text)
    text = HOME_PATH.sub("<path>", text)
    text = ENV_HOME.sub("<path>", text)
    text = ABSOLUTE_PATH.sub(" <path> ", text)
    return text


def redact_host_paths(text: str) -> str:
    """Replace host path fragments with placeholders for error messages."""
    redacted = _regex_redact(_stabilize_text(text))
    if not contains_host_path(redacted):
        return redacted

    def _token(match: re.Match[str]) -> str:
        token = match.group(0)
        return "<path>" if contains_host_path(token) else token

    return re.sub(r"\S+", _token, redacted)
