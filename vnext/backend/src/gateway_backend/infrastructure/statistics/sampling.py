"""Read only bounded proc/cgroup v2 counters; no preflight or host privileges."""

from __future__ import annotations

import os
from pathlib import Path
from time import time_ns
from uuid import uuid4

from gateway_backend.statistics.models import ResourceRecord, StatisticsIdentity
from gateway_repository_contracts.statistics import Role

_READ_LIMIT = 64 * 1024


def _read(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            value = stream.read(_READ_LIMIT + 1)
        if len(value) > _READ_LIMIT:
            return None
        return value.decode("ascii")
    except OSError, UnicodeError:
        return None


def _number(path: Path) -> int | None:
    value = _read(path)
    if value is None:
        return None
    try:
        return max(0, int(value.strip()))
    except ValueError:
        return None


class ProcessSampler:
    def __init__(
        self,
        identity: StatisticsIdentity,
        role: Role,
        process_instance_id: str,
        *,
        proc_root: Path = Path("/proc"),
        cgroup_root: Path = Path("/sys/fs/cgroup"),
    ) -> None:
        self.identity, self.role, self.process_instance_id = identity, role, process_instance_id
        self.proc_root, self.cgroup_root = proc_root, cgroup_root

    def sample(self) -> ResourceRecord:
        cpu = rss = read = write = memory = None
        stat = _read(self.proc_root / "self/stat")
        if stat is not None:
            try:
                fields = stat.rsplit(")", 1)[1].split()
                cpu = (int(fields[11]) + int(fields[12])) * 1000000 // os.sysconf("SC_CLK_TCK")
                rss = int(fields[21]) * os.sysconf("SC_PAGE_SIZE")
            except IndexError, ValueError, OSError:
                pass
        io = _read(self.proc_root / "self/io")
        if io is not None:
            try:
                values = dict(line.split(":", 1) for line in io.splitlines())
                read, write = int(values["read_bytes"]), int(values["write_bytes"])
            except KeyError, ValueError:
                pass
        # /proc identifies the current cgroup; never scan host groups or follow caller paths.
        cgroup = _read(self.proc_root / "self/cgroup")
        if cgroup is not None:
            for line in cgroup.splitlines():
                if line.startswith("0::/"):
                    relative = Path(line[4:])
                    if ".." not in relative.parts:
                        memory = _number(self.cgroup_root / relative / "memory.current")
                    break
        complete = all(value is not None for value in (cpu, rss, read, write, memory))
        return ResourceRecord(
            **self.identity.model_dump(),
            role=self.role,
            process_instance_id=self.process_instance_id,
            source_event_id=str(uuid4()),
            sampled_at_us=time_ns() // 1000,
            cpu_time_us=cpu,
            rss_bytes=rss,
            cgroup_bytes=memory,
            read_bytes=read,
            write_bytes=write,
            quality="available" if complete else "partial",
            reason=None if complete else "counter_unavailable",
        )


def counter_delta(
    first: ResourceRecord, last: ResourceRecord, name: str
) -> tuple[int | None, bool]:
    before, after = getattr(first, name), getattr(last, name)
    if (
        first.process_instance_id != last.process_instance_id
        or first.sampled_at_us > last.sampled_at_us
    ):
        return None, True
    if first.sampled_at_us == last.sampled_at_us:
        return None, False
    if before is None or after is None:
        return None, False
    if after < before:
        return None, True
    return int(after - before), False
