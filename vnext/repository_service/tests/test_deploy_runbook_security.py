"""Static scans for deployment runbooks that must not embed credentials."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK_PATHS = sorted(
    [
        *REPO_ROOT.glob("vnext/deploy/**/*.md"),
        *REPO_ROOT.glob("vnext/deploy/**/*"),
        REPO_ROOT / "vnext" / "repository_service" / "README.md",
    ]
)
RUNBOOK_TEXT_PATHS = sorted(
    {
        path
        for path in RUNBOOK_PATHS
        if path.is_file() and path.suffix in {".md", ".example", ".sh"}
    }
)
DEPLOY_ROOT = REPO_ROOT / "vnext" / "deploy"


@pytest.mark.parametrize(
    ("pattern", "description"),
    [
        (r"sudo\s+-S\b", "non-interactive sudo password flag"),
        (r"sudo\s+-n\b", "non-interactive sudo without password prompt"),
        (r"echo\s+.*\|\s*sudo\b", "password piped into sudo"),
        (r"<\s*password\s*>", "password placeholder in command examples"),
        (r"\bNOPASSWD\b", "passwordless sudo grant"),
        (r"sudoers-compose-e2e", "pytest NOPASSWD sudoers example"),
    ],
)
def test_runbooks_do_not_embed_sudo_credentials(pattern: str, description: str) -> None:
    offenders: list[str] = []
    compiled = re.compile(pattern, re.I)
    for path in RUNBOOK_TEXT_PATHS:
        text = path.read_text(encoding="utf-8")
        if compiled.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"found forbidden {description} in: {offenders}"


def test_sudoers_compose_e2e_example_removed() -> None:
    assert not (DEPLOY_ROOT / "p2r1-cache" / "sudoers-compose-e2e.example").exists()


def test_deploy_tree_has_no_nopasswd_sudoers_examples() -> None:
    offenders: list[str] = []
    for path in DEPLOY_ROOT.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "NOPASSWD" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"found NOPASSWD in deploy files: {offenders}"
