"""Subprocess crash worker for Versioned import recovery tests."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from uuid import UUID

from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.faults import ImportWorkerFaultPoint
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.worker import ImportWorkerPool
from support.crash_recovery_worker import CRASH_EXIT_CODE
from support.import_worker_harness import published_repository_path


_FAULT_POINTS = {
    "after_running_claim": ImportWorkerFaultPoint.AFTER_RUNNING_CLAIM,
    "after_package_extracted": ImportWorkerFaultPoint.AFTER_PACKAGE_EXTRACTED,
    "after_private_ref_created": ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED,
    "after_replay_before_marker": ImportWorkerFaultPoint.AFTER_REPLAY_BEFORE_MARKER,
}


def _crash() -> None:
    os._exit(CRASH_EXIT_CODE)


class _CrashImportWorkerFaultInjector:
    def __init__(self, point: ImportWorkerFaultPoint) -> None:
        self._point = point

    def maybe_raise(self, point: ImportWorkerFaultPoint) -> None:
        if point == self._point:
            _crash()


def _settings_from_args(args: argparse.Namespace) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        data_root=Path(args.data_root),
        bearer_token="test-bearer-token",
        dolt_binary=Path(args.dolt_binary),
        dolt_version=args.dolt_version,
    )


def _run_import_worker(args: argparse.Namespace) -> None:
    settings = _settings_from_args(args)
    fault_point = _FAULT_POINTS[args.fault_point]
    layout = DurableLayout.create_for_probe(settings.data_root)
    runner = DoltRunner(settings, layout.root)
    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )

    def provider_factory(repository_id: UUID) -> CandidateAImportProvider:
        repository_path = published_repository_path(layout, repository_id)
        return CandidateAImportProvider(settings, layout, repository_path, runner)

    pool = ImportWorkerPool(
        settings=settings,
        layout=layout,
        store=store,
        provider_factory=provider_factory,
        locks=RepositoryLockRegistry(),
        fault_injector=_CrashImportWorkerFaultInjector(fault_point),
    )
    pool.start()
    try:
        pool.notify()
        time.sleep(120.0)
    finally:
        try:
            pool.stop(timeout=1.0)
        except Exception:
            pass
        control_store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--dolt-binary", default="/usr/local/bin/dolt")
    parser.add_argument("--dolt-version", default="2.1.11")
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--fault-point", choices=tuple(_FAULT_POINTS), required=True)
    args = parser.parse_args(argv)
    _run_import_worker(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
