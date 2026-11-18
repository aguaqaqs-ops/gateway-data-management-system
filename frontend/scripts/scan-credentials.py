#!/usr/bin/env python3
"""Read-only credential scan for frontend evidence logs and directories.

Counts credential shapes without printing any matched value:
  * ``Bearer `` followed by token characters (the ``Bearer ${`` source
    template is counted separately, because it is not a credential),
  * ``dir-token`` markers,
  * ``gdds-handoff=`` markers,
  * entry-generated tokens: ``fe3a-``/``fe3b-`` plus one or more lowercase
    segments and a final 32-hex suffix (covers smoke roles, journey
    scene-role pairs and the two service-level tokens).

ZIP members (Playwright traces are ZIPs) are scanned member by member. The
script first proves it can detect every shape in a temporary self-check, then
scans the given directories. A non-zero credential count exits non-zero.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import socket
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ENTRY_TOKEN = re.compile(r"fe3[ab]-[a-z0-9-]+?-[0-9a-f]{32}(?![0-9a-f])")
BEARER_TOKEN = re.compile(r"Bearer (?!\$\{)[A-Za-z0-9._~+/=-]+")
SOURCE_TEMPLATE = "Bearer ${"
DIR_TOKEN = "dir-token"
HANDOFF_TOKEN = "gdds-handoff="


class Counts:
    def __init__(self) -> None:
        self.bearer = 0
        self.dir_token = 0
        self.handoff = 0
        self.entry = 0
        self.template = 0
        self.files = 0
        self.hits: set[str] = set()

    def add(self, text: str, origin: str) -> None:
        bearer = len(BEARER_TOKEN.findall(text))
        dir_token = text.count(DIR_TOKEN)
        handoff = text.count(HANDOFF_TOKEN)
        entry = len(ENTRY_TOKEN.findall(text))
        template = text.count(SOURCE_TEMPLATE)
        self.bearer += bearer
        self.dir_token += dir_token
        self.handoff += handoff
        self.entry += entry
        self.template += template
        if bearer or dir_token or handoff or entry or template:
            self.hits.add(origin)

    def credential_total(self) -> int:
        return self.bearer + self.dir_token + self.handoff + self.entry


def scan_bytes(counts: Counts, data: bytes, origin: str) -> None:
    counts.add(data.decode("utf-8", errors="replace"), origin)


def scan_file(counts: Counts, path: Path) -> None:
    counts.files += 1
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    try:
                        scan_bytes(counts, archive.read(member), f"{path}!/{member.filename}")
                    except (RuntimeError, OSError, zipfile.BadZipFile) as error:
                        print(f"warning: cannot read {path}!/{member.filename}: {error}", file=sys.stderr)
            return
        scan_bytes(counts, path.read_bytes(), str(path))
    except OSError as error:
        print(f"warning: cannot read {path}: {error}", file=sys.stderr)


def scan_directory(counts: Counts, root: Path) -> None:
    for current, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        for name in sorted(files):
            scan_file(counts, Path(current) / name)


def self_check() -> bool:
    # One entry-token shape per input kind: smoke roles, journey scene-role
    # pairs, and the Repository Service bearer. Every shape is planted twice
    # (plaintext file and zip member) and every planting must be detected on
    # its own: aggregate totals alone cannot prove that each shape is hit, a
    # pattern that misses one shape would still pass a totals-only check.
    shapes = [
        ("fe3a-smoke", f"fe3a-submitter-{secrets.token_hex(16)}"),
        ("fe3b-journeys", f"fe3b-r2-preview-submitter-{secrets.token_hex(16)}"),
        ("fe3b-rs", f"fe3b-rs-{secrets.token_hex(16)}"),
    ]
    ok = True
    with tempfile.TemporaryDirectory(prefix="scan-credentials-selfcheck-") as temporary:
        root = Path(temporary)
        for name, shape in shapes:
            (root / f"plain-{name}.txt").write_text(
                f"Authorization: Bearer {shape}\ndir-token value\n"
                f"gdds-handoff={shape}\nBearer ${{token}}\n",
                encoding="utf-8",
            )
        with zipfile.ZipFile(root / "traces.zip", "w") as archive:
            for name, shape in shapes:
                archive.writestr(
                    f"trace-{name}.txt",
                    f"Authorization: Bearer {shape}\ndir-token value\ngdds-handoff={shape}\n",
                )
        for name, _shape in shapes:
            plain_counts = Counts()
            scan_file(plain_counts, root / f"plain-{name}.txt")
            sample_ok = (
                plain_counts.entry >= 1
                and plain_counts.bearer >= 1
                and plain_counts.dir_token >= 1
                and plain_counts.handoff >= 1
                and plain_counts.template >= 1
            )
            ok = ok and sample_ok
            print(
                f"self-check-sample shape={name} medium=plain"
                f" entry={plain_counts.entry} bearer={plain_counts.bearer}"
                f" dir-token={plain_counts.dir_token} gdds-handoff={plain_counts.handoff}"
                f" template={plain_counts.template}"
                f" result={'ok' if sample_ok else 'failed'}"
            )
        with zipfile.ZipFile(root / "traces.zip") as archive:
            for name, _shape in shapes:
                member_counts = Counts()
                member = f"trace-{name}.txt"
                scan_bytes(member_counts, archive.read(member), f"traces.zip!/{member}")
                sample_ok = (
                    member_counts.entry >= 1
                    and member_counts.bearer >= 1
                    and member_counts.dir_token >= 1
                    and member_counts.handoff >= 1
                )
                ok = ok and sample_ok
                print(
                    f"self-check-sample shape={name} medium=zip"
                    f" entry={member_counts.entry} bearer={member_counts.bearer}"
                    f" dir-token={member_counts.dir_token}"
                    f" gdds-handoff={member_counts.handoff}"
                    f" result={'ok' if sample_ok else 'failed'}"
                )
    print("self-check=" + ("ok" if ok else "failed"))
    return ok


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="scan directories for frontend credential shapes")
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"hostname={socket.gethostname()} started_at={started}")
    print("directories=" + " ".join(str(directory) for directory in args.directories))

    if not self_check():
        print("self-check failed: credential detector did not observe every sample shape", file=sys.stderr)
        return 2

    counts = Counts()
    missing = False
    for directory in args.directories:
        if not directory.is_dir():
            print(f"error: not a directory: {directory}", file=sys.stderr)
            missing = True
            continue
        scan_directory(counts, directory)
    finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(
        f"scanned_files={counts.files} bearer={counts.bearer} dir-token={counts.dir_token}"
        + f" gdds-handoff={counts.handoff} entry_tokens={counts.entry}"
        + f" source_template={counts.template}"
    )
    for hit in sorted(counts.hits):
        print(f"hit={hit}")
    print(f"finished_at={finished} total_credentials={counts.credential_total()}")
    if missing:
        return 2
    return 1 if counts.credential_total() > 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
