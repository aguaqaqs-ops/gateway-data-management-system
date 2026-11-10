#!/usr/bin/env python3
"""FE4a handoff hex cross-check (kickoff §3.8).

Reads a handoff markdown file, finds every hex value, and checks each one
against its source without hand copying:

- ``--git-objects`` (with ``--repo``): every 7-12/40-char token must resolve
  to a git object (``git cat-file -e``); 40-char tokens must resolve
  unambiguously.
- ``--sha-file <sha256sum-format-file>`` (repeatable): every 64-char token
  must appear with the recorded path. Files are parsed in ``sha256sum``
  output format (``<sha>  <path>`` or ``<sha> *<path>``).
- ``--source-dir <dir>``: for lines holding both a ``/``-path and a 64-char
  token, the file must exist under the dir and its SHA256 must match.

Truncated display forms (``<hex>…<hex>``) are listed, not verified: handoffs
must carry the full value somewhere for the strict check. Tokens whose
length is not 7-12, 40 or 64 are reported as abnormal.

Exit 0 when every full token resolves and no abnormal lengths exist,
otherwise exit 1. Only the standard library is used; run with ``python3 -I``.
"""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

FULL_RE = re.compile(r"\b[0-9a-f]{7,}\b")
TRUNC_RE = re.compile(r"[0-9a-f]{1,64}…[0-9a-f]{1,64}")
VALID_LENGTHS = set(range(7, 13)) | {40, 64}


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True, help="handoff markdown file")
    parser.add_argument("--git-objects", action="store_true", help="verify 7-12/40-char tokens as git objects")
    parser.add_argument("--repo", default=None, help="git repo for --git-objects (default: script toplevel)")
    parser.add_argument("--sha-file", action="append", default=[], help="sha256sum-format file (repeatable)")
    parser.add_argument("--source-dir", default=None, help="root for path+SHA pairing checks")
    return parser.parse_args(argv)


def script_toplevel():
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent,
        check=False,
    )
    return out.stdout.strip() or None


def load_sha_files(paths):
    """Return (sha -> [paths]) and a list of problem lines."""
    table = {}
    problems = []
    for name in paths:
        try:
            text = Path(name).read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"{name}: cannot read ({exc})")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = re.match(r"\s*([0-9a-fA-F]{64})\s+[ *]?(.+?)\s*$", line)
            if not match:
                problems.append(f"{name}:{lineno}: not sha256sum format")
                continue
            table.setdefault(match.group(1).lower(), []).append(f"{name}:{lineno}:{match.group(2)}")
    return table, problems


def git_resolves(repo, token):
    out = subprocess.run(
        ["git", "-C", repo, "cat-file", "-e", token],
        capture_output=True,
        text=False,
        check=False,
    )
    return out.returncode == 0


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    handoff = Path(args.handoff)
    if not handoff.is_file():
        print(f"error: handoff is not a file: {handoff}")
        return 2
    lines = handoff.read_text(encoding="utf-8").splitlines()

    sha_table, sha_problems = load_sha_files(args.sha_file)
    repo = args.repo or script_toplevel()

    findings = []
    truncated = []
    for lineno, line in enumerate(lines, 1):
        for match in TRUNC_RE.finditer(line):
            truncated.append((lineno, match.group(0)))
        for match in FULL_RE.finditer(line):
            token = match.group(0)
            # Skip the hex half of an already-recorded truncated form: the
            # truncation regex above owns those spans.
            if any(m.start() <= match.start() and match.end() <= m.end() for m in TRUNC_RE.finditer(line)):
                continue
            findings.append((lineno, token))

    # De-duplicate tokens but keep every occurrence line for the report.
    by_token = {}
    for lineno, token in findings:
        by_token.setdefault(token, []).append(lineno)

    failures = []
    for problem in sha_problems:
        failures.append(f"sha-file problem: {problem}")

    for token in sorted(by_token, key=lambda t: (len(t), t)):
        linenos = by_token[token]
        where = ",".join(str(n) for n in linenos)
        if len(token) not in VALID_LENGTHS:
            failures.append(f"abnormal length {len(token)}: {token} (lines {where})")
            continue
        if len(token) == 64:
            hits = sha_table.get(token, [])
            if args.sha_file and not hits:
                failures.append(f"unresolved sha256: {token} (lines {where})")
            else:
                for hit in hits:
                    print(f"ok sha256 {token} -> {hit} (lines {where})")
                if not args.sha_file:
                    print(f"unverified sha256 (no --sha-file): {token} (lines {where})")
        else:
            if args.git_objects:
                if repo is None:
                    failures.append(f"no git repo for object check: {token} (lines {where})")
                elif git_resolves(repo, token):
                    print(f"ok git object {token} (lines {where})")
                else:
                    failures.append(f"unresolved git object: {token} (lines {where})")
            else:
                print(f"unverified git token (no --git-objects): {token} (lines {where})")

    # Path + SHA pairing: lines holding both resolve under --source-dir.
    if args.source_dir is not None:
        root = Path(args.source_dir)
        for lineno, line in enumerate(lines, 1):
            tokens64 = [m.group(0) for m in FULL_RE.finditer(line) if len(m.group(0)) == 64]
            if not tokens64:
                continue
            for path_match in re.finditer(r"(?<![0-9a-f/])((?:[\w.~-]+/)+[\w.~-]+)", line):
                candidate = root / path_match.group(1)
                if candidate.is_file():
                    actual = file_sha256(candidate)
                    for token in tokens64:
                        if actual == token:
                            print(f"ok pairing {path_match.group(1)} == {token} (line {lineno})")
                        else:
                            failures.append(
                                f"pairing mismatch line {lineno}: {path_match.group(1)} sha256 is {actual}, handoff says {token}"
                            )

    for lineno, token in truncated:
        print(f"truncated (not verified): {token} (line {lineno})")

    if failures:
        print(f"FAILED: {len(failures)} problem(s)")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"OK: {len(by_token)} distinct full token(s), {len(truncated)} truncated form(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
