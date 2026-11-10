"""Linux directory publication with real no-replace semantics, without a fallback."""
from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path

_LIBC = ctypes.CDLL(None, use_errno=True)
_RENAME = getattr(_LIBC, 'renameat2', None)
if _RENAME is not None:
    _RENAME.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    _RENAME.restype = ctypes.c_int


def rename_noreplace(source: Path, target: Path) -> None:
    if _RENAME is None:
        raise OSError(errno.ENOSYS, 'renameat2(RENAME_NOREPLACE) is required')
    if _RENAME(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, 'artifact directory publication failed')


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def check_publication_support(root: Path) -> None:
    """Check the configured filesystem, including refusal to replace a directory."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='.publication-check-', dir=root) as probe:
        directory = Path(probe)
        source, target = directory / 'source', directory / 'target'
        source.mkdir()
        target.mkdir()
        try:
            rename_noreplace(source, target)
        except FileExistsError:
            pass
        else:
            raise ValueError('filesystem must support no-replace directory publication')
        target.rmdir()
        rename_noreplace(source, target)
        fsync_directory(directory)
        target.rmdir()
    fsync_directory(root)
