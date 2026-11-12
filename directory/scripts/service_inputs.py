#!/usr/bin/env python3
"""Check the service gate's externally supplied, content-addressed inputs.

Use `service_inputs.py tree CACHE_DIR` to calculate the cache tree SHA256
for the provenance manifest after prefill. The gate's verify form checks it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def tree_hash(root: Path) -> str:
    if not root.is_dir() or root.is_symlink():
        raise ValueError('cache must be a directory, not a symlink')
    digest = hashlib.sha256()
    def visit(path: Path, relative: str) -> None:
        stat = path.lstat()
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('cache symlink escapes cache root')
            kind, payload = 'link', os.readlink(path)
        elif path.is_dir():
            kind, payload = 'dir', ''
        elif path.is_file():
            kind, payload = 'file', file_hash(path)
        else:
            raise ValueError('cache contains unsupported file type')
        digest.update(json.dumps([relative, kind, stat.st_mode & 0o7777, payload], ensure_ascii=True, separators=(',', ':')).encode() + b'\n')
        if kind == 'dir':
            for child in sorted(path.iterdir(), key=lambda item: os.fsencode(item.name)):
                visit(child, f'{relative}/{child.name}' if relative else child.name)
    visit(root, '')
    return digest.hexdigest()


def verify(manifest_path: Path, cache: Path, lock: Path, uv: Path, repo: Path) -> None:
    doc = json.loads(manifest_path.read_text(encoding='utf-8'))
    fields = {'source_hostname', 'source_commit', 'prefilled_utc', 'lock_sha256',
              'cache_archive', 'cache_archive_sha256', 'cache_tree_sha256',
              'uv_path', 'uv_sha256', 'uv_version', 'python_path', 'python_sha256', 'python_version'}
    if not isinstance(doc, dict) or set(doc) != fields or not all(isinstance(v, str) and v for v in doc.values()):
        raise ValueError('invalid manifest fields')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', doc['source_hostname']):
        raise ValueError('invalid source hostname')
    if not re.fullmatch(r'[0-9a-f]{40}', doc['source_commit']):
        raise ValueError('invalid source commit')
    if not re.fullmatch(r'uv [0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.]+)?(?: \([A-Za-z0-9._-]+\))?', doc['uv_version']):
        raise ValueError('invalid uv version')
    if not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', doc['prefilled_utc']):
        raise ValueError('invalid prefill UTC')
    datetime.strptime(doc['prefilled_utc'], '%Y-%m-%dT%H:%M:%SZ')
    for key in ('lock_sha256', 'cache_archive_sha256', 'cache_tree_sha256', 'uv_sha256', 'python_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', doc[key]):
            raise ValueError('invalid digest')
    archive = Path(doc['cache_archive'])
    python = Path(doc['python_path'])
    uv_manifest = Path(doc['uv_path'])
    for path in (manifest_path, archive, python, uv_manifest):
        if not path.is_absolute() or path.resolve().is_relative_to(repo.resolve()):
            raise ValueError('input must be absolute and outside the worktree')
    if uv.resolve() != uv_manifest.resolve():
        raise ValueError('uv path mismatch')
    if file_hash(lock) != doc['lock_sha256'] or file_hash(archive) != doc['cache_archive_sha256']:
        raise ValueError('lock or cache archive digest mismatch')
    if tree_hash(cache) != doc['cache_tree_sha256']:
        raise ValueError('cache tree digest mismatch')
    if file_hash(uv) != doc['uv_sha256'] or file_hash(python) != doc['python_sha256']:
        raise ValueError('toolchain digest mismatch')
    uv_version = subprocess.check_output([str(uv), '--version'], text=True).strip()
    py_version = subprocess.check_output([str(python), '--version'], text=True).strip()
    if uv_version != doc['uv_version'] or py_version != doc['python_version'] or py_version != 'Python 3.14.6':
        raise ValueError('toolchain version mismatch')
    print(f"cache_source_hostname={doc['source_hostname']}\ncache_source_commit={doc['source_commit']}\ncache_prefilled_utc={doc['prefilled_utc']}")
    for key in ('lock_sha256', 'cache_archive_sha256', 'cache_tree_sha256', 'uv_sha256', 'python_sha256', 'uv_version', 'python_version'):
        print(f'{key}={doc[key]}')
    print(f'manifest_sha256={file_hash(manifest_path)}')


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == 'tree':
            print(tree_hash(Path(sys.argv[2])))
        elif len(sys.argv) == 7 and sys.argv[1] == 'verify':
            verify(*(Path(arg) for arg in sys.argv[2:]))
        else:
            raise ValueError('usage: service_inputs.py tree CACHE | verify MANIFEST CACHE LOCK UV REPO')
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        # Never print file contents or subprocess output on failure.
        print(f'service input verification failed: {type(exc).__name__}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
