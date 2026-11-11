"""Disposable bounded observations. Business hooks only enqueue scalar state."""
from __future__ import annotations

import os
import queue
import stat
import threading
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, time_ns
from uuid import UUID, uuid4
from typing import Literal
from gateway_repository_contracts.statistics import Reason

from gateway_repository_contracts.statistics import (
    FilesystemCapacityObservation, ResourceObservation, ResourceValues,
    Observation, RepositoryStorageObservation, StatisticsFeedQuery, StatisticsFeedRecord,
    StatisticsFeedResponse, StorageValues, WriteObservation, WriteValues,
)
from gateway_repository_service.artifact_root import ArtifactRootError, assert_no_symlink_ancestors, open_dir_nofollow, same_mount
from gateway_repository_service.layout import DurableLayout, repository_key


def utc_us() -> int:
    return time_ns() // 1000


class ObservationRing:
    def __init__(self, environment_id: str, group_id: str, *, max_items: int = 4096,
                 max_bytes: int = 16 * 1024 * 1024) -> None:
        if max_items < 1 or max_bytes < 1:
            raise ValueError('ring budgets must be positive')
        self.environment_id, self.group_id = environment_id, group_id
        self.instance_id = str(uuid4())
        self.max_items, self.max_bytes = max_items, max_bytes
        self._records: deque[tuple[StatisticsFeedRecord, int]] = deque()
        self._bytes = self._sequence = self._dropped = 0
        self._lock = threading.Lock()

    def append(self, observation: Observation, *, observation_id: UUID | None = None) -> None:
        with self._lock:
            self._sequence += 1
            record = StatisticsFeedRecord(observation_id=observation_id or uuid4(),
                sequence=self._sequence, instance_id=self.instance_id,
                environment_id=self.environment_id, group_id=self.group_id,
                generated_at_us=utc_us(), observation=observation)
            size = len(record.model_dump_json().encode())
            if size > self.max_bytes:
                self._dropped += 1
                return
            while self._records and (len(self._records) >= self.max_items or self._bytes + size > self.max_bytes):
                _, removed = self._records.popleft()
                self._bytes -= removed
                self._dropped += 1
            self._records.append((record, size))
            self._bytes += size

    def read(self, query: StatisticsFeedQuery) -> StatisticsFeedResponse:
        with self._lock:
            oldest = self._records[0][0].sequence if self._records else self._sequence + 1
            reset = query.instance_id is not None and query.instance_id != self.instance_id
            after = 0 if reset else query.after_sequence
            records: list[StatisticsFeedRecord] = []
            size = 2048
            for record, count in self._records:
                if record.sequence <= after:
                    continue
                if len(records) >= query.limit or size + count > 1024 * 1024:
                    break
                records.append(record)
                size += count
            return StatisticsFeedResponse(instance_id=self.instance_id,
                oldest_sequence=oldest, next_sequence=self._sequence + 1, dropped_count=self._dropped,
                reset=reset, truncated=after < oldest - 1 or (not reset and after > self._sequence),
                records=tuple(records),
                coverage_start_us=self._records[0][0].generated_at_us if self._records else None,
                coverage_end_us=self._records[-1][0].generated_at_us if self._records else None)


@dataclass(frozen=True)
class ScanResult:
    start_us: int
    end_us: int
    start_mono: float
    end_mono: float
    objects: int | None
    logical: int | None
    allocated: int | None
    complete: bool
    reason: Reason | None = None


def scan_repository(path: Path, *, max_entries: int = 10000, max_seconds: float = 2,
                    slice_entries: int = 256, slice_seconds: float = .05,
                    clock: Callable[[], float] = monotonic) -> Iterator[ScanResult | None]:
    """Yield between bounded slices; fd-relative traversal never follows links/mounts.

    Incomplete results deliberately have no byte totals. No repair or Dolt call.
    """
    start, start_us = clock(), utc_us()
    objects = logical = allocated = entries = 0
    stack: list[tuple[int, os.ScandirIterator[str]]] = []
    complete = False
    reason: Reason | None = 'collection_failed'
    try:
        assert_no_symlink_ancestors(path)
        root = open_dir_nofollow(path)
        stack.append((root, os.scandir(root)))
        tick, count = clock(), 0
        while stack:
            if clock() - start >= max_seconds or entries >= max_entries:
                reason = 'budget_exceeded'
                break
            parent, iterator = stack[-1]
            entry = next(iterator, None)
            if entry is None:
                iterator.close()
                os.close(parent)
                stack.pop()
                continue
            entries += 1
            count += 1
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise OSError('symlink inside repository')
            if stat.S_ISDIR(info.st_mode):
                child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                if not same_mount(parent, child):
                    os.close(child)
                    raise OSError('child mount inside repository')
                stack.append((child, os.scandir(child)))
            elif stat.S_ISREG(info.st_mode):
                # A concurrent replacement can make this stat approximate, never a content read.
                objects += 1
                logical += info.st_size
                allocated += info.st_blocks * 512
            else:
                raise OSError('nonregular repository member')
            if count >= slice_entries or clock() - tick >= slice_seconds:
                yield None
                tick, count = clock(), 0
        else:
            complete, reason = True, None
    except (OSError, ArtifactRootError):
        pass
    finally:
        for descriptor, iterator in stack:
            iterator.close()
            os.close(descriptor)
    yield ScanResult(start_us, utc_us(), start, clock(), objects if complete else None,
                     logical if complete else None, allocated if complete else None, complete, reason)


@dataclass(eq=False)
class WriteWindow:
    repository_id: UUID
    operation_id: UUID
    observation_id: UUID
    before_commit: str | None
    mutation_cutoff: float | None = None
    end_cutoff: float | None = None
    before: ScanResult | None = None
    after: ScanResult | None = None
    interference: bool = False
    outcome: Literal['succeeded', 'failed', 'unknown'] = 'unknown'
    after_commit: str | None = None


class RepositoryStatistics:
    """One finite pending queue; scan_one/scan jobs run only on its background thread.

    E owns construction/start/stop and periodic storage/capacity/resource scheduling.
    """
    def __init__(self, layout: DurableLayout, ring: ObservationRing, *,
                 scanner: Callable[[Path], Iterator[ScanResult | None]] = scan_repository,
                 clock: Callable[[], float] = monotonic, max_pending: int = 512,
                 outcome: Callable[[UUID, UUID], tuple[Literal['succeeded', 'failed', 'unknown'], str | None]] | None = None) -> None:
        self.layout, self.ring, self.scanner, self.clock = layout, ring, scanner, clock
        self.outcome = outcome
        self._pending: queue.Queue[tuple[WriteWindow, bool]] = queue.Queue(maxsize=max_pending)
        self._active: dict[UUID, WriteWindow] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.dropped = 0

    def begin(self, repository_id: UUID, operation_id: UUID, before_commit: str | None) -> WriteWindow | None:
        # No blocking lock acquisition, encoding, scanning or database operation.
        if not self._lock.acquire(blocking=False):
            self.dropped += 1
            return None
        try:
            if len(self._active) >= self._pending.maxsize:
                self.dropped += 1
                return None
            previous = self._active.get(repository_id)
            if previous is not None:
                previous.interference = True
            window = WriteWindow(repository_id, operation_id, uuid4(), before_commit)
            self._active[repository_id] = window
            try:
                self._pending.put_nowait((window, False))
            except queue.Full:
                self.dropped += 1
            return window
        finally:
            self._lock.release()

    def mutation(self, window: WriteWindow | None) -> None:
        if window is not None:
            window.mutation_cutoff = self.clock()

    def end(self, window: WriteWindow | None) -> None:
        if window is None:
            return
        window.end_cutoff = self.clock()
        try:
            self._pending.put_nowait((window, True))
        except queue.Full:
            self.dropped += 1
            # No completed observation is promised when the finite queue is full.

    def _publish(self, window: WriteWindow) -> None:
        before, after = window.before, window.after
        valid_before = (before is not None and before.complete and window.mutation_cutoff is not None
                        and before.end_mono <= window.mutation_cutoff)
        valid_after = (after is not None and after.complete and window.end_cutoff is not None
                       and after.start_mono >= window.end_cutoff and not window.interference)
        b, a = before if valid_before else None, after if valid_after else None
        def delta(name: str) -> int | None:
            left, right = getattr(b, name, None), getattr(a, name, None)
            return right - left if left is not None and right is not None else None
        reason = ('interference' if window.interference else
                  'budget_exceeded' if any(s is not None and s.reason == 'budget_exceeded' for s in (before, after))
                  else 'not_collected')
        self.ring.append(WriteObservation(repository_id=window.repository_id, payload=WriteValues(
            rs_operation_id=window.operation_id, process_instance_id=self.ring.instance_id,
            before_commit=window.before_commit, after_commit=window.after_commit,
            before_start_us=b.start_us if b else None, before_end_us=b.end_us if b else None,
            after_start_us=a.start_us if a else None, after_end_us=a.end_us if a else None,
            before_logical_bytes=b.logical if b else None, after_logical_bytes=a.logical if a else None,
            before_allocated_bytes=b.allocated if b else None, after_allocated_bytes=a.allocated if a else None,
            logical_net_change_bytes=delta('logical'), allocated_net_change_bytes=delta('allocated'),
            observed_outcome=window.outcome, quality='available' if b and a else 'partial',
            reason=None if b and a else reason)), observation_id=window.observation_id)

    def collect_one(self) -> bool:
        """Background-only bounded job; injected scanner/clock support cutoff tests."""
        try:
            window, after = self._pending.get_nowait()
        except queue.Empty:
            return False
        try:
            if after:
                if self.outcome is not None:
                    window.outcome, window.after_commit = self.outcome(window.repository_id, window.operation_id)
                self._publish(window)  # pending after, followed by a new sequence on completion
            if not after and window.mutation_cutoff is not None:
                return True
            result = None
            for result in self.scanner(self.layout.published_repository(repository_key(window.repository_id))):
                if self._stop.is_set():
                    return True
                if result is None:
                    # The real scanner yields after 256 entries/50ms, relinquish CPU.
                    self._stop.wait(.001)
            if after:
                window.after = result
                self._publish(window)
                with self._lock:
                    if self._active.get(window.repository_id) is window:
                        del self._active[window.repository_id]
            else:
                window.before = result
            return True
        finally:
            self._pending.task_done()

    def collect_repository(self, repository_id: UUID) -> None:
        result = None
        for result in self.scanner(self.layout.published_repository(repository_key(repository_id))):
            if self._stop.is_set():
                return
            if result is None:
                self._stop.wait(.001)
        if result is not None:
            self.ring.append(RepositoryStorageObservation(repository_id=repository_id, payload=StorageValues(
                category='repository', object_count=result.objects, logical_bytes=result.logical,
                allocated_bytes=result.allocated, window_start_us=result.start_us, window_end_us=result.end_us,
                quality='available' if result.complete else 'partial', reason=result.reason)))

    def start(self) -> None:
        if self._thread is None:
            try:
                self._thread = threading.Thread(target=self._run, name='repository-statistics', daemon=True)
                self._thread.start()
            except Exception:
                self._thread = None
                self.dropped += 1

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.collect_one():
                    self._stop.wait(.05)
            except Exception:
                self.dropped += 1

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)


def best_effort(callback: Callable[[], object]) -> object | None:
    try:
        return callback()
    except Exception:
        return None


def filesystem_capacity(ring: ObservationRing, roots: dict[str, tuple[Path, str]]) -> None:
    seen: set[str] = set()
    for path, identity in roots.values():
        if identity in seen:
            continue
        seen.add(identity)
        try:
            value = os.statvfs(path)
            payload = StorageValues(category='filesystem', filesystem_id=identity,
                total_bytes=value.f_blocks * value.f_frsize, available_bytes=value.f_bavail * value.f_frsize,
                available_inodes=value.f_favail, window_end_us=utc_us())
        except OSError:
            payload = StorageValues(category='filesystem', filesystem_id=identity,
                window_end_us=utc_us(), quality='partial', reason='collection_failed')
        ring.append(FilesystemCapacityObservation(payload=payload))


def sample_resources(ring: ObservationRing) -> None:
    """Bounded process counters; shared service scope, never attributed to a device."""
    cpu = rss = read = write = None
    try:
        with Path('/proc/self/stat').open('rb') as handle:
            raw = handle.read(65537)
        if len(raw) <= 65536:
            values = raw.decode('ascii').rsplit(')', 1)[1].split()
            cpu = (int(values[11]) + int(values[12])) * 1000000 // os.sysconf('SC_CLK_TCK')
            rss = int(values[21]) * os.sysconf('SC_PAGE_SIZE')
        with Path('/proc/self/io').open('rb') as handle:
            raw = handle.read(65537)
        if len(raw) <= 65536:
            counters = dict(line.split(':', 1) for line in raw.decode('ascii').splitlines())
            read, write = int(counters['read_bytes']), int(counters['write_bytes'])
    except (OSError, ValueError, IndexError, KeyError):
        pass
    ring.append(ResourceObservation(payload=ResourceValues(role='repository_service',
        process_instance_id=ring.instance_id, sampled_at_us=utc_us(), cpu_time_us=cpu,
        rss_bytes=rss, read_bytes=read, write_bytes=write, quality='partial', reason='counter_unavailable')))
