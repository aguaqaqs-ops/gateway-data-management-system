#!/usr/bin/env python3
"""FE4a handoff hex cross-check (kickoff §3.8).

Reads a handoff markdown file, finds every contiguous lowercase hex run of
seven or more characters, and verifies it from its source without hand
copying:

- 7-12 and 40-char tokens are git objects (``--git-objects`` with ``--repo``);
  40-char tokens must resolve unambiguously. When the token is immediately
  preceded by a 树/tree/提交/commit label, the object type must match.
- 64-char tokens are SHA256 values (``--sha-file``/``--evidence-file``/
  ``--source-dir``).
- Any other length (13-39, 41-63, 65+) is reported as ``abnormal length`` and
  makes the run fail.
- Truncated forms (``<hex>…<hex>``) are printed and not verified.

Path+SHA256 pairing is recognised only in two shapes: a Markdown table row
(path and value in cells) and the prose form ``path`` SHA256 ``value``. Script
files such as ``.sh`` and ``.py`` count as paths; ordinary words like ``J1/J2``
do not.

Exit codes: 0 when every full token resolves and no abnormal length exists,
1 on any unverified/mismatched value or abnormal length, 2 on usage errors.
Only the standard library is used; run with ``python3 -I``.
"""

import argparse
import hashlib
import os
import re
import shlex
import socket
import subprocess
import sys
from pathlib import Path

TOKEN_RE = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,}(?![0-9A-Za-z])")
TRUNC_RE = re.compile(r"[0-9a-f]{1,64}…[0-9a-f]{1,64}")
HEX64_RE = re.compile(r"(?<![0-9a-zA-Z])[0-9a-f]{64}(?![0-9a-zA-Z])")
FILE_EXT = (
    "png|jpg|jpeg|webp|gif|svg|log|json|jsonl|txt|md|sha256|toml|lock|ya?ml|"
    "bundle|tar|gz|tgz|zip|xml|csv|html|css|m?js|cjs|ts|tsx|pdf|sh|bash|py|rb|pl|ps1"
)
FILE_NAME_RE = re.compile(rf"[\w.~-]+\.(?:{FILE_EXT})$")
SHA_LINE_RE = re.compile(r"\s*([0-9a-fA-F]{64})\s+[ *]?(.+?)\s*$")
SHA_PAIR_RE = re.compile(r"`([^`\n]+)`\s*SHA256\s*`?([0-9a-f]{64})`?")


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True, help="handoff markdown file")
    parser.add_argument("--git-objects", action="store_true", help="verify 7-12/40-char tokens as git objects")
    parser.add_argument("--repo", default=None, help="git repo for --git-objects (default: script toplevel)")
    parser.add_argument("--sha-file", action="append", default=[], help="sha256sum-format file (repeatable)")
    parser.add_argument(
        "--evidence-file",
        action="append",
        default=[],
        help="captured log/manifest/inspect text used directly as a source (repeatable)",
    )
    parser.add_argument("--source-dir", default=None, help="root for path+SHA pairing checks")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="7-12/40-char token that is intentionally not a git object (for example an image-tag suffix); reported as allowed",
    )
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


def git_head(repo):
    if repo is None:
        return None
    out = subprocess.run(
        ["git", "-C", repo, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or None


def basename(path):
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def strip_markup(text):
    return text.strip().strip("`").replace("**", "").strip()


def looks_like_path(text):
    """True for a Markdown cell or prose name that is a file path.

    Plain words (``J1/J2``) and phrases with whitespace are not paths.  A
    relative path must carry a file extension somewhere in its last segment.
    """
    value = strip_markup(text)
    if not value or " " in value or "\t" in value or "…" in value:
        return False
    if value.startswith(("/", "./", "../")):
        return True
    if "/" in value:
        last = value.rsplit("/", 1)[-1]
        return bool(FILE_NAME_RE.fullmatch(last)) or "." in last
    return bool(FILE_NAME_RE.fullmatch(value))


def same_path(recorded: str, name: str) -> bool:
    """Match a recorded path against a handoff path, tolerating a missing
    leading slash and comparing by basename when the handoff names the file
    without its directory."""
    recorded_norm = recorded.replace("\\", "/")
    name_norm = name.replace("\\", "/")
    if recorded_norm == name_norm or recorded_norm.lstrip("/") == name_norm.lstrip("/"):
        return True
    if "/" not in name_norm and basename(recorded_norm) == name_norm:
        return True
    return False


def pair_line(line):
    """Return positionally paired (name, sha) entries for 64-char values.

    Only Markdown table rows and the prose form ``name`` SHA256 ``value`` are
    paired.  In a table row, path cells and 64-char values pair in order; if
    the row is not balanced each value takes the nearest path cell (before it
    on a tie).
    """
    hexes = [(m.start(), m.group(0)) for m in HEX64_RE.finditer(line)]
    if not hexes:
        return []
    pairs = []
    if line.lstrip().startswith("|"):
        cells = []
        offset = 0
        for part in line.split("|"):
            cells.append((offset, strip_markup(part)))
            offset += len(part) + 1
        names = [(pos, text) for pos, text in cells if looks_like_path(text)]
        if len(names) == len(hexes):
            for (_, name), (_, sha) in zip(names, hexes):
                pairs.append((name, sha))
            return pairs
        used = set()
        for pos, sha in hexes:
            candidates = [
                (index, name_pos, name)
                for index, (name_pos, name) in enumerate(names)
                if index not in used
            ]
            before = [item for item in candidates if item[1] < pos]
            if before:
                _index, _name_pos, name = max(before, key=lambda item: item[1])
            else:
                after = [item for item in candidates if item[1] > pos]
                if not after:
                    pairs.append((None, sha))
                    continue
                _index, _name_pos, name = min(after, key=lambda item: item[1])
            used.add(_index)
            pairs.append((name, sha))
        return pairs
    for match in SHA_PAIR_RE.finditer(line):
        pairs.append((strip_markup(match.group(1)), match.group(2).lower()))
    return pairs


def load_sha_files(paths):
    """Return (sha -> [(source, path)]), a list of problem lines, observed set."""
    table = {}
    problems = []
    observed = set()
    for name in paths:
        try:
            text = Path(name).read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"{name}: cannot read ({exc})")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = SHA_LINE_RE.match(line)
            if match:
                sha = match.group(1).lower()
                table.setdefault(sha, []).append((f"{name}:{lineno}", match.group(2)))
                observed.add(sha)
                continue
            for path, sha in pair_line(line):
                observed.add(sha)
                if path is not None:
                    table.setdefault(sha, []).append((f"{name}:{lineno}", path))
    return table, problems, observed


def load_evidence_files(paths):
    """Return (sha -> [(source, path)]), problems, all observed 64-char values."""
    table = {}
    problems = []
    observed = set()
    for name in paths:
        try:
            text = Path(name).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"{name}: cannot read ({exc})")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in HEX64_RE.finditer(line):
                observed.add(match.group(0))
            match = SHA_LINE_RE.match(line)
            if match:
                table.setdefault(match.group(1).lower(), []).append((f"{name}:{lineno}", match.group(2)))
                continue
            for path, sha in pair_line(line):
                observed.add(sha)
                if path is not None:
                    table.setdefault(sha, []).append((f"{name}:{lineno}", path))
    return table, problems, observed


def git_object(repo, token):
    out = subprocess.run(
        ["git", "-C", repo, "cat-file", "-t", token],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_source_dir(root):
    """Return (files_by_name, files_by_hash) for regular files under root."""
    by_name = {}
    by_hash = {}
    if root is None:
        return by_name, by_hash
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            digest = file_sha256(path)
        except OSError:
            continue
        by_name.setdefault(path.name, []).append((path, digest))
        by_hash.setdefault(digest, []).append(path)
    return by_name, by_hash


def expected_object_type(line, start):
    """Return the type named by a label immediately before the value."""
    match = re.search(r"(树|提交|tree|commit)[\s`'\"：:（(]*$", line[:start])
    if not match:
        return None
    word = match.group(1)
    return "tree" if word in ("树", "tree") else "commit"


def main(argv=None):
    raw_args = sys.argv[1:] if argv is None else list(argv)
    args = parse_args(raw_args)
    handoff = Path(args.handoff)
    if not handoff.is_file():
        print(f"error: handoff is not a file: {handoff}")
        return 2
    lines = handoff.read_text(encoding="utf-8").splitlines()

    root = Path(args.source_dir) if args.source_dir else None
    if root is not None and not root.is_dir():
        print(f"error: source dir is not a directory: {root}")
        return 2

    repo = args.repo or script_toplevel()
    head = git_head(repo)

    print(f"argv: {shlex.join([sys.argv[0], *raw_args])}")
    print(f"hostname: {socket.gethostname()}")
    print(f"cwd: {os.getcwd()}")
    print(f"repo: {repo or 'none'}")
    print(f"HEAD: {head or 'unknown'}")

    sha_table, sha_problems, sha_observed = load_sha_files(args.sha_file)
    ev_table, ev_problems, ev_observed = load_evidence_files(args.evidence_file)
    files_by_name, files_by_hash = index_source_dir(root)

    observed = sha_observed | ev_observed
    combined_table = {}
    for source in (sha_table, ev_table):
        for sha, entries in source.items():
            combined_table.setdefault(sha, []).extend(entries)

    failures = []
    truncated = []
    findings = []
    for lineno, line in enumerate(lines, 1):
        trunc_spans = [(m.start(), m.end(), m.group(0)) for m in TRUNC_RE.finditer(line)]
        for _start, _end, text in trunc_spans:
            truncated.append((lineno, text))
        for match in TOKEN_RE.finditer(line):
            if any(start <= match.start() and match.end() <= end for start, end, _text in trunc_spans):
                continue
            findings.append((lineno, line, match.start(), match.group(0), len(match.group(0))))

    failures.extend(f"sha-file problem: {problem}" for problem in sha_problems)
    failures.extend(f"evidence-file problem: {problem}" for problem in ev_problems)

    token_lines = {}
    for lineno, _line, _start, token, _length in findings:
        token_lines.setdefault(token, []).append(lineno)

    # Positional name+SHA pairs from the handoff itself.
    handoff_pairs = []
    for lineno, line in enumerate(lines, 1):
        for name, sha in pair_line(line):
            if name is not None:
                handoff_pairs.append((lineno, name, sha))

    counts = {"git": 0, "sha256": 0, "allowed": 0, "abnormal": 0}
    short_findings = [
        (lineno, line, start, token)
        for lineno, line, start, token, length in findings
        if length == 40 or 7 <= length <= 12
    ]

    for token in sorted(token_lines, key=lambda t: (len(t), t)):
        where = ",".join(str(n) for n in token_lines[token])
        length = len(token)
        if length == 64:
            source_found = token in observed or token in files_by_hash
            if not source_found:
                failures.append(
                    f"unverified sha256 (no --sha-file/--evidence-file/source-dir source): {token} (lines {where})"
                )
                continue
            counts["sha256"] += 1
            print(f"ok sha256 {token} (lines {where})")
            continue
        if length == 40 or 7 <= length <= 12:
            if token in args.allow:
                counts["allowed"] += 1
                print(f"allowed non-git token {token} (lines {where})")
                continue
            if not args.git_objects:
                failures.append(f"unverified git token (no --git-objects): {token} (lines {where})")
                continue
            if repo is None:
                failures.append(f"no git repo for object check: {token} (lines {where})")
                continue
            actual_type = git_object(repo, token)
            if actual_type is None:
                failures.append(f"unresolved git object: {token} (lines {where})")
                continue
            type_checked = False
            for lineno, line, start, line_token in short_findings:
                if line_token != token:
                    continue
                expected_type = expected_object_type(line, start)
                if expected_type is not None:
                    type_checked = True
                    if actual_type != expected_type:
                        failures.append(
                            f"object type mismatch {token}: handoff says {expected_type}, git says {actual_type} (line {lineno})"
                        )
            counts["git"] += 1
            suffix = f" type={actual_type}" if type_checked else ""
            print(f"ok git object {token}{suffix} (lines {where})")
            continue
        counts["abnormal"] += 1
        failures.append(f"abnormal length {length}: {token} (lines {where})")

    # Pair each handoff path-like name with its positional SHA. The name is
    # resolved by on-site recomputation first, then by the same-named recorded
    # source; every source must agree with the handoff value.
    for lineno, name, sha in handoff_pairs:
        actual_files = []
        if name.startswith("/"):
            candidate = Path(name)
            if candidate.is_file():
                actual_files.append(candidate)
        elif "/" in name:
            if root is not None:
                candidate = root / name
                if candidate.is_file() and not candidate.is_symlink():
                    actual_files.append(candidate)
        else:
            actual_files.extend(path for path, _digest in files_by_name.get(name, []))
        recorded = []
        for source_sha, entries in combined_table.items():
            for origin, path in entries:
                if same_path(path, name):
                    recorded.append((source_sha, origin, path))
        matching_recorded = [(source_sha, origin, path) for source_sha, origin, path in recorded if source_sha == sha]
        if actual_files:
            actual_hashes = {file_sha256(path) for path in actual_files}
            if sha not in actual_hashes:
                shown = ", ".join(sorted(actual_hashes))
                failures.append(
                    f"pairing mismatch line {lineno}: {name} on-site sha256 is {shown}, handoff says {sha}"
                )
                continue
            print(f"ok pairing {name} == {sha} (line {lineno}, on-site)")
        if recorded and not matching_recorded:
            origins = ", ".join(f"{origin} {source_sha}" for source_sha, origin, _path in recorded)
            failures.append(f"pairing mismatch line {lineno}: {name} recorded as {origins}, handoff says {sha}")
            continue
        if not actual_files and not matching_recorded:
            failures.append(
                f"pairing has no source line {lineno}: {name} + {sha} (no on-site file and no --sha-file/--evidence-file entry)"
            )
            continue
        if matching_recorded and not actual_files:
            origin = matching_recorded[0][1]
            print(f"ok pairing {name} == {sha} (line {lineno}, {origin})")

    for lineno, token in truncated:
        print(f"truncated (not verified): {token} (line {lineno})")

    print(
        f"summary: {len(token_lines)} distinct full token(s); "
        f"git={counts['git']} sha256={counts['sha256']} allowed={counts['allowed']} "
        f"abnormal={counts['abnormal']}; {len(truncated)} truncated form(s)"
    )
    if failures:
        print(f"FAILED: {len(failures)} problem(s)")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"OK: {len(token_lines)} distinct full token(s), {len(truncated)} truncated form(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
