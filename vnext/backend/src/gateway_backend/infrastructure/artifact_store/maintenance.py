"""One bounded, cooperative maintenance pass. Cursors contain no caller paths."""
from __future__ import annotations

import base64
import ctypes
import fcntl
import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from gateway_backend.artifacts.bounded_store import CleanupClassification
from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.artifacts.serialize import artifact_ref_from_json
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
from gateway_backend.infrastructure.artifact_store.layout import _directory_identity
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore

_HEX2 = re.compile(r'[0-9a-f]{2}')
_HEX64 = re.compile(r'[0-9a-f]{64}')
_TEMP = re.compile(r'(?:object|scratch)-[A-Za-z0-9_-]{6,64}')
_FILE = re.compile(r'file-[0-9a-f]{32}')
_LOCATIONS = tuple(ArtifactLocation)
_MAX_VISITS = 1024


class _Dirent(ctypes.Structure):
    _fields_ = [('inode', ctypes.c_ulong), ('offset', ctypes.c_long), ('length', ctypes.c_ushort),
               ('kind', ctypes.c_ubyte), ('name', ctypes.c_char * 256)]


_libc = ctypes.CDLL(None, use_errno=True)
_libc.fdopendir.argtypes = [ctypes.c_int]
_libc.fdopendir.restype = ctypes.c_void_p
_libc.readdir.argtypes = [ctypes.c_void_p]
_libc.readdir.restype = ctypes.POINTER(_Dirent)
_libc.seekdir.argtypes = [ctypes.c_void_p, ctypes.c_long]
_libc.telldir.argtypes = [ctypes.c_void_p]
_libc.telldir.restype = ctypes.c_long
_libc.closedir.argtypes = [ctypes.c_void_p]


def _entry(path: Path, cookie: int) -> tuple[str | None, int]:
    """Read exactly one directory entry using a Linux filesystem continuation cookie."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory = _libc.fdopendir(fd)
    if not directory:
        os.close(fd)
        raise OSError(ctypes.get_errno(), 'fdopendir failed')
    try:
        _libc.seekdir(directory, cookie)
        ctypes.set_errno(0)
        entry = _libc.readdir(directory)
        if not entry:
            if error := ctypes.get_errno():
                raise OSError(error, 'readdir failed')
            return None, cookie
        return os.fsdecode(entry.contents.name), _libc.telldir(directory)
    finally:
        _libc.closedir(directory)


@dataclass
class _Lane:
    stack: list[tuple[str, int]] = field(default_factory=lambda: [('', 0)])
    done: bool = False


@dataclass(frozen=True)
class MaintenanceItem:
    location: str
    relative_path: str
    disposition: str
    reason: str | None = None


@dataclass(frozen=True)
class MaintenanceResult:
    candidates: int
    visits: int
    items: tuple[MaintenanceItem, ...]
    cursor: str | None


class _Budget:
    def __init__(self) -> None:
        self.visits = 0

    def take(self, amount: int = 1) -> bool:
        if self.visits + amount > _MAX_VISITS:
            return False
        self.visits += amount
        return True


def _valid_relative(relative: str, lane: int) -> bool:
    if relative == '':
        return True
    parts = relative.split('/')
    if lane >= 4:
        return False  # temporary lanes never recurse beyond one owner directory
    if parts[0] != 'objects' or len(parts) > 3:
        return False
    return all(_HEX2.fullmatch(part) for part in parts[1:])


class ArtifactMaintenance:
    def __init__(self, local: LocalArtifactStore, bounded: BoundedArtifactStore, *, scratch_root: Path,
                 owner_active: Callable[[str], bool], grace: timedelta = timedelta(hours=24)) -> None:
        self.local = local
        self.bounded = bounded
        self.scratch_root = scratch_root
        self.scratch_identity = _directory_identity(scratch_root)
        self.owner_active = owner_active
        self.grace = grace
        self.identity = hashlib.sha256(json.dumps([
            [(loc.value, str(local.layout.root(loc)), local.layout._identities[loc]) for loc in _LOCATIONS],
            str(scratch_root), self.scratch_identity], sort_keys=True).encode()).hexdigest()

    def _decode(self, cursor: str | None) -> tuple[list[_Lane], int]:
        if cursor is None:
            return [_Lane() for _ in range(9)], 0
        try:
            if type(cursor) is not str or len(cursor) > 8192:
                raise ValueError()
            doc = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
            if set(doc) != {'v', 'identity', 'next', 'lanes'} or doc['v'] != 1 or doc['identity'] != self.identity:
                raise ValueError()
            if type(doc['next']) is not int or not 0 <= doc['next'] < 9 or len(doc['lanes']) != 9:
                raise ValueError()
            lanes: list[_Lane] = []
            for index, item in enumerate(doc['lanes']):
                if set(item) != {'stack', 'done'} or type(item['done']) is not bool or len(item['stack']) > 4:
                    raise ValueError()
                stack: list[tuple[str, int]] = []
                for relative, cookie in item['stack']:
                    if type(relative) is not str or not _valid_relative(relative, index):
                        raise ValueError()
                    if type(cookie) is not int or not 0 <= cookie < 2**63:
                        raise ValueError()
                    if len(Path(relative).parts) != len(stack):
                        raise ValueError()
                    if stack and not relative.startswith(stack[-1][0] + ('/' if stack[-1][0] else '')):
                        raise ValueError()
                    stack.append((relative, cookie))
                if item['done'] != (not stack):
                    raise ValueError()
                lanes.append(_Lane(stack, item['done']))
            return lanes, doc['next']
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError('invalid or foreign cleanup cursor') from None

    def _encode(self, lanes: list[_Lane], next_lane: int) -> str | None:
        if all(lane.done for lane in lanes):
            return None
        doc = {'v': 1, 'identity': self.identity, 'next': next_lane, 'lanes': [asdict(lane) for lane in lanes]}
        return base64.urlsafe_b64encode(json.dumps(doc, separators=(',', ':')).encode()).decode()

    def run(self, *, max_candidates: int = 32, cursor: str | None = None,
            now: datetime | None = None) -> MaintenanceResult:
        if type(max_candidates) is not int or not 1 <= max_candidates <= 32:
            raise ValueError('max_candidates must be between 1 and 32')
        when = now or datetime.now(UTC)
        lanes, next_lane = self._decode(cursor)
        budget = _Budget()
        items: list[MaintenanceItem] = []
        disabled: set[int] = set()
        while len(items) < max_candidates and budget.visits < _MAX_VISITS:
            available = [index for index, lane in enumerate(lanes) if not lane.done and index not in disabled]
            if not available:
                break
            index = next((index for offset in range(9) if (index := (next_lane + offset) % 9) in available))
            next_lane = (index + 1) % 9
            location = _LOCATIONS[index % 4] if index < 8 else None
            label = ('staging:' + location.value if index >= 4 else location.value) if location else 'scratch'
            root = self.local.layout.root(location) if location else self.scratch_root
            base = root / '.staging' if 4 <= index < 8 else root
            try:
                if location:
                    with self.local.layout.cleanup_session(location) as acquired:
                        if not acquired:
                            disabled.add(index)
                            continue
                        item = self._advance(index, lanes[index], root, base, budget, when)
                else:
                    if _directory_identity(root) != self.scratch_identity:
                        raise ValueError('scratch root identity changed')
                    item = self._advance(index, lanes[index], root, base, budget, when)
                if item is not None:
                    relative, disposition, reason, ref = item
                    if ref is not None:
                        # The adapter owns EX -> short DB -> recheck/delete. Do
                        # not enter its SH borrowing UoW while holding scan EX.
                        disposition = self.bounded.delete_eligible(ref,
                            expected_classification=CleanupClassification.ELIGIBLE_AFTER, now=when).value
                    items.append(MaintenanceItem(label, relative, disposition, reason))
            except FileNotFoundError:
                if root.is_dir() and 4 <= index < 8 and not base.exists():
                    lanes[index].stack.clear()
                    lanes[index].done = True
                else:
                    disabled.add(index)
                    items.append(MaintenanceItem(label, '', 'manual_review', 'configured root or scan directory unavailable'))
            except (OSError, ValueError, ManifestVerificationError) as exc:
                disabled.add(index)
                items.append(MaintenanceItem(label, '', 'manual_review', str(exc)))
        return MaintenanceResult(len(items), budget.visits, tuple(items), self._encode(lanes, next_lane))

    def _advance(self, index: int, lane: _Lane, root: Path, base: Path, budget: _Budget,
                 now: datetime) -> tuple[str, str, str | None, ArtifactRef | None] | None:
        relative, cookie = lane.stack[-1]
        directory = base / relative
        self.local._check_path(root, directory)
        if not budget.take():
            return None
        name, cookie = _entry(directory, cookie)
        lane.stack[-1] = (relative, cookie)
        if name is None:
            lane.stack.pop()
            lane.done = not lane.stack
            return None
        if name in {'.', '..'}:
            return None
        if relative == '' and name == '.gateway-storage.json' and (index < 4 or index == 8):
            # Deployment owns marker identity validation; reserve only its name.
            self.local._check_path(root, base / name)
            if not stat.S_ISREG((base / name).lstat().st_mode):
                return name, 'manual_review', 'marker must be an ordinary file', None
            return None
        child_relative = str(Path(relative) / name)
        child = base / child_relative
        self.local._check_path(root, child)
        info = child.lstat()
        if index < 4:
            if relative == '' and name == '.staging':
                return None
            if ((relative == '' and name == 'objects') or
                    (1 <= len(Path(relative).parts) <= 2 and _HEX2.fullmatch(name))):
                if not stat.S_ISDIR(info.st_mode):
                    return child_relative, 'manual_review', 'expected ordinary shard directory', None
                lane.stack.append((child_relative, 0))
                return None
            if len(Path(relative).parts) != 3 or not _HEX64.fullmatch(name):
                return child_relative, 'manual_review', 'unknown artifact root shape', None
            if not budget.take(16):
                # Resume this entry next time; all prior visits remain charged.
                lane.stack[-1] = (relative, lane.stack[-1][1])
                return child_relative, 'manual_review', 'inspection budget exhausted', None
            ref = self._object_ref(child, root)
            return child_relative, 'candidate', None, ref
        if not _TEMP.fullmatch(name) or not stat.S_ISDIR(info.st_mode):
            return child_relative, 'manual_review', 'unknown temporary owner shape', None
        if not budget.take(4):
            return child_relative, 'manual_review', 'inspection budget exhausted', None
        disposition, reason = self._temporary(child, root, index == 8, budget, now)
        return child_relative, disposition, reason, None

    def _object_ref(self, path: Path, root: Path) -> ArtifactRef:
        names: list[str] = []
        with os.scandir(path) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > 2:
                    raise ValueError('unknown object members')
                self.local._check_path(root, path / entry.name)
                if not entry.is_file(follow_symlinks=False):
                    raise ValueError('object members must be ordinary files')
        if set(names) - {'payload', 'ref.jcs'} or 'ref.jcs' not in names:
            raise ValueError('incomplete or unknown object shape')
        with (path / 'ref.jcs').open('rb') as handle:
            raw_ref = handle.read(4097)
        if len(raw_ref) > 4096:
            raise ValueError('object ref exceeds byte bound')
        ref = artifact_ref_from_json(raw_ref)
        if self.local.object_directory(ref.artifact_id) != path:
            raise ValueError('object ref belongs to a different directory/root')
        return ref

    def _temporary(self, path: Path, root: Path, scratch: bool, budget: _Budget,
                   now: datetime) -> tuple[str, str | None]:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 'retryable_failure', 'temporary owner is active'
            names: list[str] = []
            with os.scandir(path) as entries:
                for entry in entries:
                    # Each entry inspection and later unlink consume budget.
                    if not budget.take(2) or len(names) >= 64:
                        return 'manual_review', 'temporary directory exceeds bounded inspection'
                    names.append(entry.name)
                    allowed = entry.name == 'owner.json' or (_FILE.fullmatch(entry.name) if scratch
                        else entry.name in {'payload', 'ref.jcs'})
                    self.local._check_path(root, path / entry.name)
                    if not allowed or not entry.is_file(follow_symlinks=False):
                        return 'manual_review', 'unknown temporary member'
            if 'owner.json' not in names:
                return 'manual_review', 'temporary owner metadata unavailable'
            with (path / 'owner.json').open('rb') as handle:
                owner = json.loads(handle.read(4097))
            if (type(owner) is not dict or set(owner) != {'version', 'owner'} or owner['version'] != 1
                    or type(owner['owner']) is not str or not owner['owner'] or len(owner['owner']) > 512):
                return 'manual_review', 'invalid temporary owner metadata'
            owner_id = owner['owner']
            if not owner_id.startswith(('operation:', 'upload:', 'request:')):
                return 'manual_review', 'unknown temporary owner kind'
            if self.owner_active(owner_id):
                return 'retryable_failure', 'business owner remains active'
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if now < modified + self.grace:
                return 'retained', 'orphan grace has not expired'
            for name in names:
                (path / name).unlink()
            path.rmdir()
            return 'deleted', None
        finally:
            os.close(descriptor)
