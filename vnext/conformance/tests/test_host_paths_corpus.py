"""Table-driven host_paths corpus: detect / golden / sanitize symmetry."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.golden.security import assert_golden_payload_safe
from gateway_conformance.host_paths import contains_host_path
from gateway_conformance.sanitize import sanitize_message


@dataclass(frozen=True)
class CorpusCase:
    value: str
    expect_detect: bool
    absent_in_sanitize: tuple[str, ...] = ()


_POSITIVE: tuple[CorpusCase, ...] = (
    # MIN-024 spaced paths
    CorpusCase("/home/alice/My Secrets/id_rsa", True, ("Secrets", "id_rsa", "alice")),
    CorpusCase(
        r"C:\Users\alice\My Documents\secret.yaml",
        True,
        ("Documents", "Users", "alice"),
    ),
    # MIN-027 unicode / NBSP gaps
    CorpusCase("/home/alice/\u3000Documents/id_rsa", True, ("Documents", "id_rsa")),
    CorpusCase("/var/log/\xa0MyApp/secret.key", True, ("MyApp", "secret.key")),
    # MIN-025 / MIN-029 unicode separators & fullwidth punct
    CorpusCase("／etc／passwd", True, ("passwd",)),
    CorpusCase("⧸etc⧸passwd", True, ("passwd",)),
    CorpusCase(r"C：\Users\Alice\.ssh\id_rsa", True, ("Users", "Alice", "id_rsa")),
    CorpusCase("～alice/.ssh/id_rsa", True, ("alice", "id_rsa")),
    CorpusCase(r"C:﹨Users﹨secret", True, ("Users", "secret")),
    # MIN-026 / MIN-028 home forms
    CorpusCase("~alice/.ssh/id_rsa", True, ("alice", "id_rsa")),
    CorpusCase("%7Ealice%2F.ssh", True, ("alice",)),
    CorpusCase("$HOME/.ssh/id_rsa", True, ("HOME", "id_rsa")),
    CorpusCase(r"%USERPROFILE%\AppData\secret", True, ("USERPROFILE", "AppData", "secret")),
    CorpusCase("%USERPROFILE%/secrets", True, ("USERPROFILE", "secrets")),
    CorpusCase("${HOME}/.config/secret", True, ("HOME", "secret")),
    # Historical encoding regression
    CorpusCase("file:%2F%2F%2Fetc%2Fpasswd", True, ("passwd", "file:%2f")),
    CorpusCase("file:%252F%252F%252Fetc%252Fpasswd", True, ("passwd",)),
    CorpusCase("%2Fetc%2Fpasswd", True, ("passwd",)),
    CorpusCase(r"C:%5CUsers%5Csecret", True, ("Users", "secret")),
    CorpusCase("file:///tmp/secret", True, ("/tmp", "secret")),
    # MIN-032 percent-encoded fullwidth fold after unquote
    CorpusCase("%EF%BC%8Fetc%EF%BC%8Fpasswd", True, ("passwd",)),
    CorpusCase(r"C%EF%BC%9A%5CUsers%5Csecret", True, ("Users", "secret")),
    CorpusCase("%EF%BD%9Ealice%2F.ssh%2Fid_rsa", True, ("alice", "id_rsa")),
    CorpusCase("%E2%A7%B8etc%E2%A7%B8passwd", True, ("passwd",)),
    CorpusCase(
        "file:%EF%BC%8F%EF%BC%8F%EF%BC%8Ftmp%EF%BC%8Fx",
        True,
        ("tmp",),
    ),
    # MIN-036 additional slash/tilde folds
    CorpusCase("╱etc╱passwd", True, ("passwd",)),
    CorpusCase(r"C:╲Users╲secret", True, ("Users", "secret")),
    CorpusCase(r"C:∖Users∖secret", True, ("Users", "secret")),
    CorpusCase("∼alice/.ssh/id_rsa", True, ("alice", "id_rsa")),
    CorpusCase("⁓alice/x", True, ("alice",)),
    CorpusCase("%E2%95%B1etc%E2%95%B1passwd", True, ("passwd",)),  # ╱
    CorpusCase("%E2%88%BCalice%2Fx", True, ("alice",)),  # ∼
)

_NEGATIVE: tuple[CorpusCase, ...] = (
    CorpusCase("expected/result.golden.json", False),
    CorpusCase("sha256:" + "0" * 64, False),
    CorpusCase("review-ticket:42", False),
    CorpusCase("ok relative/path", False),
)


@pytest.mark.parametrize("case", _POSITIVE, ids=[c.value[:48] for c in _POSITIVE])
def test_host_paths_corpus_positive(case: CorpusCase) -> None:
    assert contains_host_path(case.value) is True
    with pytest.raises(ConformanceValidationError, match="absolute paths|host path"):
        assert_golden_payload_safe(case.value)
    sanitized = sanitize_message(f"failed at {case.value}")
    assert "<path>" in sanitized
    lowered = sanitized.lower()
    for fragment in case.absent_in_sanitize:
        assert fragment.lower() not in lowered, (fragment, sanitized)


@pytest.mark.parametrize("case", _NEGATIVE, ids=[c.value[:48] for c in _NEGATIVE])
def test_host_paths_corpus_negative(case: CorpusCase) -> None:
    assert contains_host_path(case.value) is False
    assert_golden_payload_safe(case.value)
    assert sanitize_message(case.value) == case.value
