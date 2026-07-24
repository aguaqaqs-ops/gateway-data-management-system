"""Strict YAML acceptance and rejection tests."""

from __future__ import annotations

import pytest

from gateway_conformance.strict_yaml import StrictYAMLValidationError, loads_strict_yaml


def test_yaml_comment_and_key_order_are_semantically_equivalent() -> None:
    a = loads_strict_yaml(
        "manifest_schema_version: 1\n"
        "track: data\n"
        "# comment\n"
        "subject:\n"
        "  kind: capability\n"
        "  name: test-capability\n"
    )
    b = loads_strict_yaml(
        "subject:\n"
        "  name: test-capability\n"
        "  kind: capability\n"
        "track: data\n"
        "manifest_schema_version: 1\n"
    )
    assert a == b


@pytest.mark.parametrize(
    ("document", "fragment"),
    [
        ("&anchor {}\n*anchor", "aliases"),
        ("key: &a {}\nmerge: <<: *a", "merge"),
        ("---\n{}\n---\n{}", "multi-document"),
        ("%YAML 1.2\n{}", "directives"),
        ("!!str value", "explicit tags"),
    ],
)
def test_strict_yaml_rejects_forbidden_constructs(document: str, fragment: str) -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml(document)


def test_strict_yaml_rejects_non_mapping_root() -> None:
    with pytest.raises(StrictYAMLValidationError, match="mapping"):
        loads_strict_yaml("[a, b]\n")


def test_strict_yaml_rejects_duplicate_keys() -> None:
    with pytest.raises(StrictYAMLValidationError, match="duplicate"):
        loads_strict_yaml("key: 1\nkey: 2\n")


def test_strict_yaml_rejects_nan_and_infinity() -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml("value: .nan\n")
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml("value: .inf\n")


def test_strict_yaml_rejects_implicit_timestamp() -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml("when: 2026-01-01\n")


def test_strict_yaml_rejects_invalid_utf8_bytes() -> None:
    from gateway_conformance.strict_yaml import loads_strict_yaml_bytes

    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml_bytes(b"\xff\xfe")


def test_strict_yaml_accepts_ijson_numbers() -> None:
    doc = loads_strict_yaml("count: 42\nratio: 1.5\nenabled: true\nempty:\n")
    assert doc["count"] == 42
    assert doc["ratio"] == 1.5
    assert doc["enabled"] is True
    assert doc["empty"] is None


@pytest.mark.parametrize(
    "document",
    [
        "value: 0o77\n",
        "value: 0xFF\n",
        "nested:\n  count: 0o10\n",
        "inline: {count: 0o10}\n",
        "items: [0xFF, 1]\n",
    ],
)
def test_strict_yaml_rejects_octal_and_hex_literals(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml(document)


def test_strict_yaml_rejects_underscore_digit_literals() -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml("value: 1_000\n")


def test_strict_yaml_accepts_hex_substring_inside_quoted_string() -> None:
    doc = loads_strict_yaml('description: "contains 0xFF substring"\n')
    assert doc["description"] == "contains 0xFF substring"


def test_strict_yaml_accepts_sha256_digest_line() -> None:
    digest = "sha256:" + "a" * 64
    doc = loads_strict_yaml(f"fixture_content_digest: {digest}\n")
    assert doc["fixture_content_digest"] == digest


@pytest.mark.parametrize(
    "document",
    [
        "value: 0b10\n",
        "value: 0123\n",
        "value: +12\n",
        "value: .5\n",
    ],
)
def test_strict_yaml_rejects_non_json_numeric_forms(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml(document)


def test_strict_yaml_accepts_quoted_date_string() -> None:
    doc = loads_strict_yaml('when: "2026-01-01"\n')
    assert doc["when"] == "2026-01-01"


def test_strict_yaml_accepts_comment_with_anchor_text() -> None:
    doc = loads_strict_yaml("# &anchor comment\nvalue: 1\n")
    assert doc["value"] == 1


@pytest.mark.parametrize(
    "document",
    [
        "value:\n  - +12\n",
        "value: [.5]\n",
        "value: {k: +12}\n",
        "+12: ok\n",
    ],
)
def test_strict_yaml_rejects_plus_and_dot_in_seq_flow_key(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml(document)


def test_strict_yaml_accepts_quoted_plus_in_string() -> None:
    doc = loads_strict_yaml('value: "literal: +12"\n')
    assert doc["value"] == "literal: +12"


def test_strict_yaml_accepts_plus_in_comment() -> None:
    doc = loads_strict_yaml("# value: +12\nok: 1\n")
    assert doc["ok"] == 1


@pytest.mark.parametrize(
    "document",
    [
        "value: .label\n",
        "value: +label\n",
        "value:\n  - .label\n",
        "value: [+label]\n",
        "value: -label\n",
        "value: 1label\n",
        "value: 1e\n",
        "value:\n  - -label\n",
        "value: [1label]\n",
        "value: {1e: ok}\n",
        "-label: ok\n",
        "1label: ok\n",
    ],
)
def test_strict_yaml_accepts_non_json_numeric_looking_strings(document: str) -> None:
    doc = loads_strict_yaml(document)
    assert doc is not None


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("value: true\n", True),
        ("value: false\n", False),
        ("value: null\n", None),
        ("value: True\n", "True"),
        ("value: FALSE\n", "FALSE"),
        ("value: Null\n", "Null"),
        ("value: NULL\n", "NULL"),
        ("value: ~\n", "~"),
    ],
)
def test_strict_yaml_json_schema_bool_null_resolution(document: str, expected: object) -> None:
    doc = loads_strict_yaml(document)
    assert doc["value"] == expected


@pytest.mark.parametrize(
    "document",
    [
        "value: -\n",
        "k: -\n",
    ],
)
def test_strict_yaml_normalizes_scanner_errors(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError, match="YAML parse failed"):
        loads_strict_yaml(document)


def test_strict_yaml_accepts_plain_minus_zero_and_block_sequence() -> None:
    assert loads_strict_yaml("value: -0\n")["value"] == 0
    assert loads_strict_yaml("value: -label\n")["value"] == "-label"
    assert loads_strict_yaml("items:\n  - a\n")["items"] == ["a"]


@pytest.mark.parametrize(
    "document",
    [
        "value: -.5\n",
        "value: +.5\n",
        "value: -.0\n",
        "value: 1.\n",
        "value: -1.\n",
        "value: [.5]\n",
        "value: {k: -.5}\n",
        "1.: ok\n",
        "-.5: ok\n",
    ],
)
def test_strict_yaml_rejects_core_pseudo_floats(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml(document)


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("value: -0\n", 0),
        ("value: 1.5\n", 1.5),
        ("value: 1.0e+2\n", 100),
        ('value: "-.5"\n', "-.5"),
        ('value: "1."\n', "1."),
        ('value: "1.e2"\n', "1.e2"),
    ],
)
def test_strict_yaml_accepts_json_numbers_and_quoted_pseudo_floats(
    document: str, expected: object
) -> None:
    assert loads_strict_yaml(document)["value"] == expected


@pytest.mark.parametrize(
    "document",
    [
        "value: 1.e2\n",
        "value: 1.e+2\n",
        "value: [1.e2]\n",
        "value: {k: 1.e+2}\n",
    ],
)
def test_strict_yaml_rejects_pseudo_scientific_floats(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml(document)


@pytest.mark.parametrize(
    "document",
    [
        "value: +1label\n",
        "value: .5label\n",
        "value: +.5label\n",
        "value: [+1label]\n",
        "value: {.5label: ok}\n",
        "+1label: ok\n",
    ],
)
def test_strict_yaml_accepts_label_suffix_not_core_number(document: str) -> None:
    assert loads_strict_yaml(document) is not None


@pytest.mark.parametrize(
    "document",
    [
        "value: 1_0.5\n",
        "value: 1.0_0\n",
        "value: 1_0e2\n",
        "value: .Inf\n",
        "value: .INF\n",
        "value: .NaN\n",
        "value: .Nan\n",
        "value: .NAN\n",
        "value: +.Inf\n",
        "value: Inf\n",
        "value: NaN\n",
        "value: 1:2\n",
        "value: 1:2:3\n",
        "value: 190:20:30\n",
        "value: [1_0.5]\n",
        "value: {k: .Inf}\n",
        "1:2: ok\n",
    ],
)
def test_strict_yaml_rejects_core_number_extensions(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml(document)


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ('value: "1_0.5"\n', "1_0.5"),
        ('value: "2026-01-01"\n', "2026-01-01"),
        ('value: "2026-01-01 1:02:03"\n', "2026-01-01 1:02:03"),
        ("value: not-a-date\n", "not-a-date"),
    ],
)
def test_strict_yaml_accepts_quoted_core_and_non_dates(document: str, expected: object) -> None:
    assert loads_strict_yaml(document)["value"] == expected


@pytest.mark.parametrize(
    "document",
    [
        "when: 2026-01-01\n",
        "when: 2026-01-01 1:02:03\n",
        "when: 2026-01-01T12:00:00Z\n",
        "when: 2001-12-15 2:59:43\n",
        "when: 2001-12-15 2:59:43.10\n",
        "when: 2001-12-14 21:59:43.10 -5\n",
        "when: 2001-12-14 21:59:43.10 -5:00\n",
        "when: 2001-1-1T00:00:00Z\n",
        "when: 2001-01-1 2:59:43\n",
        "when: 2001-1-01t2:59:43\n",
        "when: 2026-01-01\t1:02:03\n",
    ],
)
def test_strict_yaml_rejects_yaml11_timestamps(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError, match="timestamp"):
        loads_strict_yaml(document)


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("when: 2001-1-1\n", "2001-1-1"),
        ("when: 2001-01-1\n", "2001-01-1"),
        ("when: 2001-1-01\n", "2001-1-01"),
        ("when: 2001-01-01Z\n", "2001-01-01Z"),
        ("when: 2001-01-01 2:59\n", "2001-01-01 2:59"),
        ("when: 2001-01-01 0:0:00\n", "2001-01-01 0:0:00"),
    ],
)
def test_strict_yaml_accepts_non_timestamp_date_like_strings(
    document: str, expected: object
) -> None:
    assert loads_strict_yaml(document)["when"] == expected


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("value: 1e+02\n", 100),
        ("value: 1e02\n", 100),
        ("value: 1e-02\n", 0.01),
        ("value: 1.0E+02\n", 100),
        ("value: 1e+2\n", 100),
        ("value: 1.0e+2\n", 100),
    ],
)
def test_strict_yaml_accepts_json_exponent_with_leading_zeros(
    document: str, expected: object
) -> None:
    assert loads_strict_yaml(document)["value"] == expected


@pytest.mark.parametrize(
    "document",
    [
        "value: _1\n",
        "value: _\n",
        "value: __\n",
        "value: 0_\n",
        "value: 1_\n",
        "value: ._5\n",
        "value: [_1]\n",
        "1_: ok\n",
    ],
)
def test_strict_yaml_accepts_underscore_edge_strings(document: str) -> None:
    assert loads_strict_yaml(document) is not None


@pytest.mark.parametrize(
    "document",
    [
        "value: 1_000\n",
        "value: 1_0.5\n",
        "value: 1.0_0\n",
        "value: 1_0e2\n",
    ],
)
def test_strict_yaml_rejects_internal_underscore_numbers(document: str) -> None:
    with pytest.raises(StrictYAMLValidationError):
        loads_strict_yaml(document)
