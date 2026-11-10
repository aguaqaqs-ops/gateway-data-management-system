#!/usr/bin/env python3
"""FE4a handoff hex cross-check (kickoff §3.8).

Reads a handoff markdown file, finds every hex value, and checks each one
against its source without hand copying:

- ``--git-objects`` (with ``--repo``): every 7-12/40-char token must resolve
  to a git object (``git cat-file -e``). 40-char tokens must resolve
  unambiguously. When the same line names the value as a tree or a commit, the
  object type must match.
- ``--sha-file <sha256sum-format-file>`` (repeatable): every 64-char token
  must appear with the recorded path. Files are parsed in ``sha256sum``
  output format (``<sha>  <path>`` or ``<sha> *<path>``).
- ``--evidence-file <raw-log-or-manifest>`` (repeatable): a captured log,
  manifest, or inspect dump used directly as the source instead of a
  hand-written label list. Every 64-char value in the file counts as observed;
  ``name + SHA`` pairs (table rows, ``sha256sum`` output, and prose) are kept
  for positional pairing.
- ``--source-dir <dir>``: the root for on-site recomputation. Path+SHA pairs
  from a handoff line are paired by position (not cross-product), then checked
  against same-named files in the SHA/evidence sources or under this root.

A 64-char value with no SHA source, or a 7-12/40-char value without
``--git-objects`` (and without ``--allow``), is reported as 未核对 and exits
non-zero. Truncated display forms (``<hex>…<hex>``) are listed, not verified:
handoffs must carry the full value somewhere for the strict check. Tokens whose
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

HEX64_RE = re.compile(r"\b[0-9a-f]{64}\b")
TRUNC_RE = re.compile(r"[0-9a-f]{1,64}…[0-9a-f]{1,64}")
SHORT_RE = re.compile(r"\b[0-9a-f]{7,12}\b|\b[0-9a-f]{40}\b")
VALID_LENGTHS = set(range(7, 13)) | {40, 64}
FILE_EXT = (
    "png|jpg|jpeg|webp|gif|svg|log|json|jsonl|txt|md|sha256|toml|lock|ya?ml|"
    "bundle|tar|gz|tgz|zip|xml|csv|html|css|m?js|cjs|ts|tsx|pdf"
)
NAME_RE = re.compile(
    rf"(?<![\w.~-])((?:[\w.~-]+/)+[\w.~-]+|[\w.~-]+\.(?:{FILE_EXT}))(?![\w.~-])"
)
SHA_LINE_RE = re.compile(r"\s*([0-9a-fA-F]{64})\s+[ *]?(.+?)\s*$")


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


def basename(path):
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


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

    When a line holds the same number of path-like names and 64-char values,
    they pair by order (table rows and ``name SHA`` runs). Otherwise each value
    takes the nearest unused name, preferring a name before it on a tie.
    """
    hexes = [(m.start(), m.group(0)) for m in HEX64_RE.finditer(line)]
    if not hexes:
        return []
    names = [(m.start(1), m.group(1)) for m in NAME_RE.finditer(line)]
    if not names:
        return [(None, sha) for _, sha in hexes]
    pairs = []
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
        elif candidates:
            _index, _name_pos, name = min(candidates, key=lambda item: abs(item[1] - pos))
        else:
            pairs.append((None, sha))
            continue
        used.add(_index)
        pairs.append((name, sha))
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
            for path, sha in pair_line(line):
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
    labels = []
    for match in re.finditer(r"树|提交|(?<![A-Za-z])(?:tree|commit)(?![A-Za-z])", line):
        labels.append((abs(match.start() - start), 0 if match.start() < start else 1, match.group(0)))
    if not labels:
        return None
    labels.sort()
    word = labels[0][2]
    return "tree" if word in ("树", "tree") else "commit"


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    handoff = Path(args.handoff)
    if not handoff.is_file():
        print(f"error: handoff is not a file: {handoff}")
        return 2
    lines = handoff.read_text(encoding="utf-8").splitlines()

    root = Path(args.source_dir) if args.source_dir else None
    if root is not None and not root.is_dir():
        print(f"error: source dir is not a directory: {root}")
        return 2

    sha_table, sha_problems, sha_observed = load_sha_files(args.sha_file)
    ev_table, ev_problems, ev_observed = load_evidence_files(args.evidence_file)
    files_by_name, files_by_hash = index_source_dir(root)
    repo = args.repo or script_toplevel()

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
        for start, end, text in trunc_spans:
            truncated.append((lineno, text))
        for match in HEX64_RE.finditer(line):
            findings.append((lineno, line, match.start(), match.group(0), False))
        for match in SHORT_RE.finditer(line):
            if any(start <= match.start() and match.end() <= end for start, end, _ in trunc_spans):
                continue
            findings.append((lineno, line, match.start(), match.group(0), True))

    failures.extend(f"sha-file problem: {problem}" for problem in sha_problems)
    failures.extend(f"evidence-file problem: {problem}" for problem in ev_problems)

    token_lines = {}
    for lineno, _line, _start, token, _is_short in findings:
        token_lines.setdefault(token, []).append(lineno)

    # Positional name+SHA pairs from the handoff itself.
    handoff_pairs = []
    for lineno, line in enumerate(lines, 1):
        for name, sha in pair_line(line):
            if name is not None:
                handoff_pairs.append((lineno, name, sha))

    for token in sorted(token_lines, key=lambda t: (len(t), t)):
        where = ",".join(str(n) for n in token_lines[token])
        if len(token) not in VALID_LENGTHS:
            failures.append(f"abnormal length {len(token)}: {token} (lines {where})")
            continue
        if len(token) == 64:
            source_found = token in observed or token in files_by_hash
            if not source_found:
                failures.append(
                    f"unverified sha256 (no --sha-file/--evidence-file/source-dir source): {token} (lines {where})"
                )
                continue
            print(f"ok sha256 {token} (lines {where})")
            continue

        if token in args.allow:
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
        for lineno, line, start, line_token, is_short in findings:
            if line_token != token or not is_short:
                continue
            expected_type = expected_object_type(line, start)
            if expected_type is not None:
                type_checked = True
                if actual_type != expected_type:
                    failures.append(
                        f"object type mismatch {token}: handoff says {expected_type}, git says {actual_type} (line {lineno})"
                    )
        suffix = f" type={actual_type}" if type_checked else ""
        print(f"ok git object {token}{suffix} (lines {where})")

    # Pair each handoff path-like name with its positional SHA. The name is
    # resolved by on-site recomputation first, then by the same-named recorded
    # source; every source must agree with the handoff value.
    for lineno, name, sha in handoff_pairs:
        actual_files = []
        if "/" in name:
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

    if failures:
        print(f"FAILED: {len(failures)} problem(s)")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"OK: {len(token_lines)} distinct full token(s), {len(truncated)} truncated form(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
