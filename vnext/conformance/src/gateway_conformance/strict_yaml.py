"""Strict YAML 1.2 JSON tag-resolution subset loader."""

from __future__ import annotations

import math
import re
from io import StringIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError
from ruamel.yaml.loader import SafeLoader
from ruamel.yaml.resolver import VersionedResolver
from ruamel.yaml.tokens import AliasToken, AnchorToken, DirectiveToken, ScalarToken, TagToken

from gateway_conformance.errors import ConformanceValidationError

_IJSON_MIN = -(2**53) + 1
_IJSON_MAX = (2**53) - 1
_JSON_NUMBER = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
_JSON_INT = re.compile(r"^-?(?:0|[1-9][0-9]*)$")
_JSON_FLOAT = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+(?:[eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)$")
# Underscores only between digit groups (not leading/trailing/_ alone).
_DEC = r"[0-9]+(?:_[0-9]+)*"
_BIN = r"[01]+(?:_[01]+)*"
_OCT = r"[0-7]+(?:_[0-7]+)*"
_HEX = r"[0-9A-Fa-f]+(?:_[0-9A-Fa-f]+)*"
# YAML 1.2 Core (plus common extensions: _, 0b, sexagesimal) — reject when not JSON.
_CORE_NUMBER = re.compile(
    r"^(?:"
    rf"[-+]?(?:0b{_BIN}|0o{_OCT}|0x{_HEX})"  # base prefixes
    rf"|[-+]?0[0-9]+(?:\.{_DEC})?(?:[eE][-+]?{_DEC})?"  # leading-zero decimal 0123
    rf"|[-+]?(?:0|[1-9][0-9]*(?:_[0-9]+)*)(?::[0-5]?[0-9])+(?:\.{_DEC})?"  # sexagesimal
    rf"|[-+]?(?:{_DEC}(?:\.(?:{_DEC})?)?|\.{_DEC})(?:[eE][-+]?{_DEC})?"  # Core float / +int / _
    r"|[-+]?\.(?:[Ii][Nn][Ff]|[Nn][Aa][Nn])"  # .inf / .nan any case
    r"|[-+]?(?:[Ii][Nn][Ff]|[Nn][Aa][Nn])"  # Inf / NaN without dot
    r")$"
)
# YAML 1.1 !!timestamp lexical form (yaml.org/type/timestamp.html).
# Bare date: YYYY-MM-DD only. Single-digit Y/M/D fields require a time part.
_IMPLICIT_TIMESTAMP = re.compile(
    r"^(?:"
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"|"
    r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}"
    r"(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]*)?"
    r"(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?"
    r")$"
)

_JSON_IMPLICIT_RESOLVERS: tuple[tuple[str, re.Pattern[str], list[str | None]], ...] = (
    ("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf")),
    ("tag:yaml.org,2002:null", re.compile(r"^(?:null)$"), list("n")),
    ("tag:yaml.org,2002:null", re.compile(r"^$"), [""]),
    ("tag:yaml.org,2002:int", _JSON_INT, list("-+0123456789")),
    ("tag:yaml.org,2002:float", _JSON_FLOAT, list("-+0123456789.")),
)


class _JsonSchemaResolver(VersionedResolver):
    """YAML 1.2 JSON Schema implicit resolvers only (no Core bool/null/octal)."""

    @property
    def versioned_resolver(self) -> Any:
        version = self.processing_version
        if isinstance(version, str):
            version = tuple(map(int, version.split(".")))
        if version not in self._version_implicit_resolver:
            for tag, regexp, first in _JSON_IMPLICIT_RESOLVERS:
                self.add_version_implicit_resolver(version, tag, regexp, first)
        return self._version_implicit_resolver[version]


class StrictYAMLValidationError(ConformanceValidationError):
    """YAML document violates the strict JSON-compatible subset."""


def loads_strict_yaml_bytes(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictYAMLValidationError("YAML document is not valid UTF-8") from exc
    return loads_strict_yaml(text)


def loads_strict_yaml(text: str) -> dict[str, Any]:
    if "\x00" in text:
        raise StrictYAMLValidationError("YAML document contains NUL byte")
    if text.lstrip().startswith("%"):
        raise StrictYAMLValidationError("YAML directives are not allowed")
    _scan_forbidden_tokens(text)

    yaml = YAML(typ="safe")
    yaml.Resolver = _JsonSchemaResolver
    yaml.allow_duplicate_keys = False
    try:
        loaded = yaml.load(StringIO(text))
    except YAMLError as exc:
        message = str(exc)
        if "duplicate" in message.lower():
            raise StrictYAMLValidationError("duplicate mapping key") from exc
        raise StrictYAMLValidationError(f"YAML parse failed: {exc}") from exc

    if loaded is None:
        raise StrictYAMLValidationError("YAML document is empty")
    document = _to_plain_json_tree(loaded)
    if not isinstance(document, dict):
        raise StrictYAMLValidationError("scenario manifest root must be a mapping")
    return document


def _scan_forbidden_tokens(text: str) -> None:
    try:
        loader = SafeLoader(StringIO(text))
        while loader.check_token():
            token = loader.get_token()
            if isinstance(token, (TagToken, AnchorToken, AliasToken, DirectiveToken)):
                raise StrictYAMLValidationError("YAML forbidden construct is not allowed")
            if not isinstance(token, ScalarToken):
                continue
            if token.style in ("'", '"'):
                continue
            raw = text[token.start_mark.index : token.end_mark.index]
            if _IMPLICIT_TIMESTAMP.fullmatch(raw):
                raise StrictYAMLValidationError("implicit timestamps are not allowed")
            _assert_unquoted_numeric_scalar(raw)
    except YAMLError as exc:
        raise StrictYAMLValidationError(f"YAML parse failed: {exc}") from exc


def _assert_unquoted_numeric_scalar(raw: str) -> None:
    """Accept JSON numbers; reject Core numeric forms; leave other strings alone."""
    if _JSON_NUMBER.fullmatch(raw):
        return
    if _CORE_NUMBER.fullmatch(raw):
        raise StrictYAMLValidationError("YAML core numeric extension is not allowed")


def _to_plain_json_tree(value: Any) -> Any:
    if isinstance(value, CommentedMap):
        mapping: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise StrictYAMLValidationError("mapping keys must be strings")
            mapping[key] = _to_plain_json_tree(item)
        return mapping
    if isinstance(value, CommentedSeq):
        return [_to_plain_json_tree(item) for item in value]
    if isinstance(value, dict):
        mapping = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise StrictYAMLValidationError("mapping keys must be strings")
            mapping[key] = _to_plain_json_tree(item)
        return mapping
    if isinstance(value, list):
        return [_to_plain_json_tree(item) for item in value]
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value < _IJSON_MIN or value > _IJSON_MAX:
            raise StrictYAMLValidationError("integer outside I-JSON safe range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrictYAMLValidationError("non-finite floats are not allowed")
        if value < _IJSON_MIN or value > _IJSON_MAX:
            raise StrictYAMLValidationError("float outside I-JSON safe range")
        if value == int(value) and abs(value) <= _IJSON_MAX:
            return int(value)
        return value
    if isinstance(value, str):
        return value
    raise StrictYAMLValidationError(f"unsupported YAML value type: {type(value).__name__}")
