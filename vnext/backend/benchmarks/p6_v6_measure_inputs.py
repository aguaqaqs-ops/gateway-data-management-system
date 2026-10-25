"""Measurement-only inputs and throughput runs for the Phase 6 V6 parser prototype.

Standard library only, so it runs with ``python3 -I`` on a measurement node
without a backend environment. Outputs contain sizes, digests, timings, thread
counts and memory -- never dump contents (DC22).

Subcommands::

    extract-sql --archive rd.tar.gz --out dump.sql
    make-2x --first v1.sql --second v2.sql --out x2.sql [--suffix __x2]
    measure --rust-bin table_access_parse --sql x2.sql --workdir DIR
        [--threads 1,2,4,8,16,32] [--chunk-bytes 1048576] [--repeat 4]
        [--determinism-chunks 1048576,65536,4096] [--summary-out s.json]

``make-2x`` concatenates two dumps and renames every table of the second one
(CREATE/INSERT/DROP/LOCK/ALTER heads), giving the synthetic 2x t4 input of
DC35. ``measure`` runs the Rust example once per thread count in its own
process (so peak RSS is per configuration), takes the median of all repeats
after the first, then runs one determinism pass over every thread count and
the given chunk sizes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import statistics
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any

_RENAME_HEADS = re.compile(
    rb"(?m)^(CREATE TABLE (?:IF NOT EXISTS )?|INSERT INTO |DROP TABLE IF EXISTS |LOCK TABLES |/\*!\d+ ALTER TABLE )`([^`]+)`"
)


def make_2x(first: Path, second: Path, out: Path, suffix: str) -> dict[str, Any]:
    """Concatenate two dumps, renaming the second dump's tables (measurement only)."""
    second_data = second.read_bytes()
    renamed, count = _RENAME_HEADS.subn(lambda m: m.group(1) + b"`" + m.group(2) + suffix.encode() + b"`", second_data)
    first_data = first.read_bytes()
    joined = first_data + (b"" if first_data.endswith(b"\n") else b"\n") + renamed
    out.write_bytes(joined)
    os.chmod(out, 0o600)
    return {
        "first_bytes": len(first_data),
        "second_bytes": len(second_data),
        "out_bytes": len(joined),
        "renamed_statements": count,
        "out_sha256": hashlib.sha256(joined).hexdigest(),
    }


def extract_sql(package: Path, out: Path) -> dict[str, Any]:
    with tarfile.open(package, "r:gz") as archive:
        member = next(item for item in archive.getmembers() if item.name.lstrip("/") == "sql/dbcfg.sql")
        handle = archive.extractfile(member)
        if handle is None:
            raise ValueError("sql/dbcfg.sql is not a regular file")
        data = handle.read()
    out.write_bytes(data)
    os.chmod(out, 0o600)
    return {"package": package.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _run_rust(rust_bin: Path, args: list[str], summary: Path) -> dict[str, Any]:
    subprocess.run([str(rust_bin), *args, "--summary-out", str(summary)], check=True)
    os.chmod(summary, 0o600)
    loaded: dict[str, Any] = json.loads(summary.read_text(encoding="utf-8"))
    return loaded


def _cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def measure(
    rust_bin: Path,
    sql: Path,
    workdir: Path,
    threads: list[int],
    chunk_bytes: int,
    repeat: int,
    determinism_chunks: list[int],
) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    os.chmod(workdir, 0o700)
    input_bytes = sql.stat().st_size
    rows: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    for count in threads:
        summary = _run_rust(
            rust_bin,
            [
                "--input",
                str(sql),
                "--threads",
                str(count),
                "--chunk-bytes",
                str(chunk_bytes),
                "--repeat",
                str(repeat),
                "--canonical",
                "none",
            ],
            workdir / f"threads-{count}.json",
        )
        config = summary["configs"][0]
        seconds = [float(value) for value in config["parse_seconds"]]
        measured = seconds[1:] if len(seconds) > 1 else seconds
        median = statistics.median(measured)
        phases = config["phase_seconds"][1:] if len(seconds) > 1 else config["phase_seconds"]
        phase_median = {
            name: statistics.median(float(item[name]) for item in phases)
            for name in ("validate", "scan", "values", "merge")
        }
        rows.append(
            {
                "threads": count,
                "parse_seconds": seconds,
                "median_seconds": median,
                "median_phase_seconds": phase_median,
                "mb_per_second": input_bytes / 1e6 / median,
                "mib_per_second": input_bytes / (1 << 20) / median,
                "peak_rss_kib": summary["peak_rss_kib"],
            }
        )
        result = summary["result"]
    base = rows[0]["median_seconds"]
    for row in rows:
        row["speedup"] = base / row["median_seconds"]
        row["efficiency"] = row["speedup"] / (row["threads"] / rows[0]["threads"])
    determinism = _run_rust(
        rust_bin,
        [
            "--input",
            str(sql),
            "--threads",
            ",".join(str(count) for count in threads),
            "--chunk-bytes",
            ",".join(str(size) for size in determinism_chunks),
            "--canonical",
            "sha",
        ],
        workdir / "determinism.json",
    )
    digests = sorted({config["canonical_sha256"] for config in determinism["configs"]})
    return {
        "hostname": socket.gethostname(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "input": sql.name,
        "input_bytes": input_bytes,
        "input_sha256": determinism["input_sha256"],
        "rust_bin_sha256": hashlib.sha256(rust_bin.read_bytes()).hexdigest(),
        "chunk_bytes": chunk_bytes,
        "repeat": repeat,
        "median_of": "repeats after the first",
        "result": None
        if result is None
        else {key: result[key] for key in ("status", "table_count", "ready_tables", "total_rows", "document_failure")},
        "scaling": rows,
        "determinism": {
            "threads": threads,
            "chunk_bytes": determinism_chunks,
            "configs": len(determinism["configs"]),
            "deterministic": determinism["deterministic"],
            "canonical_sha256": digests,
            "canonical_bytes": determinism["configs"][0].get("canonical_bytes"),
            "peak_rss_kib_with_canonical": determinism["peak_rss_kib"],
        },
        "finished_unix": time.time(),
    }


def _ints(text: str) -> list[int]:
    return [int(item) for item in text.split(",") if item.strip()]


def _emit(value: object, path: str | None) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
    print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("extract-sql")
    p.add_argument("--archive", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("make-2x")
    p.add_argument("--first", required=True)
    p.add_argument("--second", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--suffix", default="__x2")
    p = sub.add_parser("measure")
    p.add_argument("--rust-bin", required=True)
    p.add_argument("--sql", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--threads", default="1,2,4,8,16,32")
    p.add_argument("--chunk-bytes", type=int, default=1 << 20)
    p.add_argument("--repeat", type=int, default=4)
    p.add_argument("--determinism-chunks", default="1048576,65536,4096")
    p.add_argument("--summary-out")
    args = parser.parse_args(argv)

    if args.command == "extract-sql":
        _emit(extract_sql(Path(args.archive), Path(args.out)), None)
        return 0
    if args.command == "make-2x":
        _emit(make_2x(Path(args.first), Path(args.second), Path(args.out), args.suffix), None)
        return 0
    if args.command == "measure":
        summary = measure(
            Path(args.rust_bin),
            Path(args.sql),
            Path(args.workdir),
            _ints(args.threads),
            args.chunk_bytes,
            args.repeat,
            _ints(args.determinism_chunks),
        )
        _emit(summary, args.summary_out)
        return 0 if summary["determinism"]["deterministic"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
