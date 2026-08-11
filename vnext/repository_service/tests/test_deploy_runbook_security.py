"""Static scans for deployment runbooks that must not embed credentials."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK_PATHS = sorted(
    [
        *REPO_ROOT.glob("vnext/deploy/**/*.md"),
        REPO_ROOT / "vnext" / "repository_service" / "README.md",
    ]
)


@pytest.mark.parametrize(
    ("pattern", "description"),
    [
        (r"sudo\s+-S\b", "non-interactive sudo password flag"),
        (r"echo\s+.*\|\s*sudo\b", "password piped into sudo"),
        (r"<\s*password\s*>", "password placeholder in command examples"),
    ],
)
def test_runbooks_do_not_embed_sudo_credentials(pattern: str, description: str) -> None:
    offenders: list[str] = []
    compiled = re.compile(pattern, re.I)
    for path in RUNBOOK_PATHS:
        text = path.read_text(encoding="utf-8")
        if compiled.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"found forbidden {description} in: {offenders}"
