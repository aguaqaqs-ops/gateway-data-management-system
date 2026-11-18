#!/usr/bin/env python3
"""Redact entry-generated tokens retained in real-backend e2e logs/evidence.

Only the standard library; run with ``python3 -I``. Collects the candidate
token values (entry argv) plus every token-shaped value found directly under
the run root, replaces them with ``<redacted-entry-token>`` under ``LOG_DIR``
and ``EVIDENCE_DIR`` (ZIP members rewritten member by member, preserving
``ZipInfo``), then counts surviving entry-token and ``Bearer`` shapes.

Prints only counts and paths, never token values::

    token_redacted_files=<n> token_hits_after_redaction=<n> bearer_hits_after_redaction=<n>
    token_redaction_file_error=<path>: <error>   # one line per failed rewrite

Exits 0 only when every rewrite succeeded and no shape survives; exits 1 when
a file could not be rewritten (``token_redaction_file_error``) or any shape
survives. The caller keeps the suite result intact and fails the run on a
non-zero exit.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import zipfile

TOKEN_RE = re.compile(r"fe3[ab]-[a-z0-9-]+?-[0-9a-f]{32}(?![0-9a-f])")
BEARER_RE = re.compile(r"Bearer (?!\$\{)[A-Za-z0-9._~+/=-]+")
PLACEHOLDER = b"<redacted-entry-token>"


def main(argv: list[str]) -> int:
    # NOTE: `argv` already excludes the program name (the `__main__` block
    # passes `sys.argv[1:]`), so directories are `argv[0:3]`.
    if len(argv) < 3:
        print(
            "usage: redact-entry-tokens.py LOG_DIR [EVIDENCE_DIR] RUN_ROOT [TOKEN ...]",
            file=sys.stderr,
        )
        return 2
    log_dir, evidence_dir, run_root = argv[0:3]
    tokens = {value for value in argv[3:] if TOKEN_RE.fullmatch(value)}
    try:
        run_names = os.listdir(run_root)
    except OSError as error:
        print(f"token_redaction_file_error={run_root}: {error}")
        return 1
    for name in run_names:
        path = os.path.join(run_root, name)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError as error:
            print(f"token_redaction_file_error={path}: {error}")
            return 1
        tokens.update(TOKEN_RE.findall(text))
    token_bytes = sorted(value.encode() for value in tokens)

    def redact_bytes(data: bytes) -> tuple[bytes, bool]:
        changed = False
        for token in token_bytes:
            if token in data:
                data = data.replace(token, PLACEHOLDER)
                changed = True
        return data, changed

    def redact_zip(path: str) -> bool:
        changed = False
        with zipfile.ZipFile(path) as archive:
            members = [(info, archive.read(info.filename)) for info in archive.infolist()]
        rebuilt = []
        for info, data in members:
            data, member_changed = redact_bytes(data)
            changed = changed or member_changed
            rebuilt.append((info, data))
        if not changed:
            return False
        handle, temporary = tempfile.mkstemp(
            prefix=".redacted-", suffix=".zip", dir=os.path.dirname(path)
        )
        os.close(handle)
        try:
            with zipfile.ZipFile(temporary, "w") as archive:
                for info, data in rebuilt:
                    archive.writestr(info, data)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return True

    def redacted_files(root: str):
        for current, _directories, files in os.walk(root):
            for name in files:
                yield os.path.join(current, name)

    failed = False
    changed_files = 0
    for root in [log_dir, evidence_dir]:
        if not root:
            continue
        for path in redacted_files(root):
            try:
                if zipfile.is_zipfile(path):
                    changed_files += 1 if redact_zip(path) else 0
                    continue
                with open(path, "rb") as handle:
                    data = handle.read()
                redacted, changed = redact_bytes(data)
                if changed:
                    with open(path, "wb") as handle:
                        handle.write(redacted)
                    changed_files += 1
            except (OSError, zipfile.BadZipFile) as error:
                print(f"token_redaction_file_error={path}: {error}")
                failed = True

    token_count = 0
    bearer_count = 0
    for root in [log_dir, evidence_dir]:
        if not root:
            continue
        for path in redacted_files(root):
            try:
                if zipfile.is_zipfile(path):
                    with zipfile.ZipFile(path) as archive:
                        payloads = [
                            archive.read(info.filename)
                            for info in archive.infolist()
                            if not info.is_dir()
                        ]
                else:
                    with open(path, "rb") as handle:
                        payloads = [handle.read()]
            except (OSError, zipfile.BadZipFile):
                continue
            for payload in payloads:
                text = payload.decode("utf-8", errors="replace")
                token_count += len(TOKEN_RE.findall(text))
                bearer_count += len(BEARER_RE.findall(text))
    print(
        f"token_redacted_files={changed_files} "
        f"token_hits_after_redaction={token_count} "
        f"bearer_hits_after_redaction={bearer_count}"
    )
    if failed:
        print("credential redaction failed: a retained file could not be rewritten")
    if token_count or bearer_count:
        print("credential scan failed: entry tokens or Bearer credentials survived in retained output")
    return 1 if failed or token_count or bearer_count else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
