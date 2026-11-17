"""Actual runtime fixture update and gateway numeric identity filesystem access."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from uuid import uuid4
from typing import Any

import pytest

from benchmarks import comparison_correctness_acceptance as acceptance
from benchmarks import comparison_correctness_history_supplement as supplement
from benchmarks import real_dump_journey as journey
from benchmarks.comparison_correctness_cache_probe import TARGETS
from tests.support import compose_gate_harness as harness

pytestmark = pytest.mark.unit
OVERRIDE_FAULTS = ("owner", "path", "symlink", "untracked", "uid")


@contextmanager
def _runtime_fixture(
    base: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[dict[str, str], Path]]:
    # Use the actual production fixture creator, but no Docker build/service.
    monkeypatch.setenv("TMPDIR", str(base))
    env = journey._compose_environment(
        base / ("secrets-" + uuid4().hex), "e-cs-repair-" + uuid4().hex
    )
    harness.prepare_runtime_config(env)
    root, _owner = harness._runtime_fixtures[env["COMPOSE_PROJECT_NAME"]]
    try:
        yield env, root
    finally:
        # Only this test's newly created fixture; its parent TemporaryDirectory
        # owns all the generated files, including negative-vector symlinks.
        harness._runtime_fixtures.pop(env["COMPOSE_PROJECT_NAME"], None)


def _probe_files(root: Path) -> tuple[Path, Path]:
    targets, probe = root / "history-targets.json", root / "history-cache-probe.py"
    targets.write_bytes(TARGETS.dump_json([]))
    probe.write_text("# independent test mount\n")
    return targets, probe


def test_actual_prepare_updates_owned_override_and_keeps_evidence_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _runtime_fixture(tmp_path, monkeypatch) as (env, root):
        path = Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"])
        original = path.stat()
        before = json.loads(path.read_bytes())
        targets, probe = _probe_files(root)
        supplement.update_fixture_override(
            env, targets, probe, tmp_path / "old-root", tmp_path / "old-run"
        )
        result = json.loads(path.read_bytes())
        assert path.stat().st_ino == original.st_ino
        assert result["services"]["repository-service"] == before["services"]["repository-service"]
        assert result["services"]["worker"]["command"] == [
            "python",
            "/run/gateway/history-cache-probe.py",
            "worker",
            "/run/gateway/history-targets.json",
        ]
        for service in ("backend", "worker"):
            mounts = result["services"][service]["volumes"][-2:]
            assert [item["source"] for item in mounts] == [str(targets), str(probe)]
            assert all(
                item["read_only"] and not item["bind"]["create_host_path"] for item in mounts
            )
        evidence = tmp_path / "evidence.json"
        acceptance._write(evidence, {"original": True})
        with pytest.raises(FileExistsError):
            acceptance._write(evidence, {"replaced": True})
        assert json.loads(evidence.read_bytes()) == {"original": True}


@pytest.mark.parametrize("fault", OVERRIDE_FAULTS)
def test_override_rejects_wrong_ownership_and_redirected_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with _runtime_fixture(tmp_path, monkeypatch) as (env, root):
        path = Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"])
        targets, probe = _probe_files(root)
        original = path.read_bytes()
        other = tmp_path / "foreign.json"
        other.write_bytes(original)
        if fault == "owner":
            owner_path = root / ".gateway-runtime-fixture-owner.json"
            value = json.loads(owner_path.read_bytes())
            value["owner"] = "another-session"
            owner_path.write_text(json.dumps(value))
        elif fault == "path":
            env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"] = str(other)
        elif fault == "symlink":
            path.unlink()
            path.symlink_to(other)
        elif fault == "uid":
            assert os.geteuid() == 0, "dedicated node must permit the real service identity vector"
            os.chown(path, 100, 101)
        else:
            harness._runtime_fixtures.pop(env["COMPOSE_PROJECT_NAME"])
        with pytest.raises((journey.JourneyFailure, OSError)):
            supplement.update_fixture_override(
                env, targets, probe, tmp_path / "old-root", tmp_path / "old-run"
            )
        assert path.read_bytes() == original and other.read_bytes() == original


def _gateway_data(root: Path) -> tuple[Path, Path, Path]:
    repository = root / "roots/rs-repository"
    metadata = root / "roots/rs-metadata"
    noms = repository / "data/repositories/source/.dolt/noms"
    noms.mkdir(parents=True)
    manifest, lock = noms / "manifest", noms / "LOCK"
    manifest.write_bytes(b"source Dolt manifest\n")
    lock.write_bytes(b"")
    database = metadata / "repository-service.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE ownership_probe(value TEXT NOT NULL)")
        conn.execute("INSERT INTO ownership_probe VALUES ('source')")
    for slot in (repository, metadata):
        for path in (slot, *slot.rglob("*")):
            if path.name == ".gateway-storage.json":
                continue
            os.chown(path, 100, 101)
            path.chmod(0o750 if path.is_dir() else 0o600)
    database.chmod(0o644)
    return manifest, lock, database


def test_production_fixture_clone_is_usable_by_gateway_uid_gid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert os.geteuid() == 0, (
        "the gateway uid100/gid101 vector requires the dedicated root executor"
    )
    # The host test TMPDIR is root-only (0700). Container bind mounts do not
    # expose that ancestor, and SQLite resolves relative names to absolute
    # paths. Use only our own directory on the same filesystem under its
    # traversable parent; do not chmod the shared TMPDIR or any source path.
    with tempfile.TemporaryDirectory(
        prefix="gdds-e-cs2-", dir=Path(os.environ["TMPDIR"]).parent
    ) as directory:
        base = Path(directory)
        base.chmod(0o755)
        with (
            _runtime_fixture(base, monkeypatch) as (_source_env, source),
            _runtime_fixture(base, monkeypatch) as (_clone_env, clone),
        ):
            manifest, lock, database = _gateway_data(source)
            before = supplement.tree_manifest(source / "roots")
            supplement.clone_roots(source / "roots", clone / "roots")
            assert supplement.tree_manifest(clone / "roots") == before
            script = (
                "import os,sqlite3,fcntl,sys; from pathlib import Path; "
                "assert (os.geteuid(),os.getegid())==(100,101); "
                "manifest,lock,database=map(Path,sys.argv[1:]); "
                "assert manifest.read_bytes()==b'source Dolt manifest\\n'; "
                "fd=os.open(lock,os.O_RDWR); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); "
                "os.write(fd,b'clone lock'); os.close(fd); "
                "conn=sqlite3.connect(database); "
                "conn.execute(\"INSERT INTO ownership_probe VALUES ('clone')\"); conn.commit(); "
                "assert conn.execute('SELECT count(*) FROM ownership_probe').fetchone()[0]==2; conn.close()"
            )
            # A container bind exposes the fixture inode, not the host's
            # root-only TMPDIR ancestors. Enter our fixture before dropping
            # identity and resolve only paths inside that view.
            args = [
                str((clone / path.relative_to(source)).relative_to(base))
                for path in (manifest, lock, database)
            ]
            completed = subprocess.run(
                ["/usr/bin/python3", "-I", "-c", script, *args],
                cwd=base,
                user=100,
                group=101,
                extra_groups=[],
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
            assert supplement.tree_manifest(source / "roots") == before
            assert (clone / manifest.relative_to(source)).stat().st_uid == 100
            assert (clone / lock.relative_to(source)).stat().st_mode & 0o777 == 0o600
            assert (clone / manifest.relative_to(source)).parent.stat().st_mode & 0o777 == 0o750


def test_clone_ownership_failure_does_not_weaken_permissions_or_change_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, clone = tmp_path / "source", tmp_path / "clone"
    (source / "rs-repository").mkdir(parents=True)
    clone.mkdir()
    payload = source / "rs-repository/private"
    payload.write_bytes(b"owner-only")
    payload.chmod(0o600)
    before = supplement.tree_manifest(source)

    def denied(*args: Any, **kwargs: Any) -> None:
        raise PermissionError("ownership preservation is not permitted")

    monkeypatch.setattr(os, "chown", denied)
    with pytest.raises(PermissionError, match="ownership preservation"):
        supplement.clone_roots(source, clone)
    assert supplement.tree_manifest(source) == before
    assert (clone / "rs-repository/private").stat().st_mode & 0o777 == 0o600
