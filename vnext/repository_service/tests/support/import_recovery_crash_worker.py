"""Subprocess worker that crashes during startup recovery reconciliation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from uuid import UUID

from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.faults import ImportRecoveryFaultPoint
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.recovery import ImportStartupReconciler
from gateway_repository_service.versioned_import.store import ImportOperationStore
from support.crash_recovery_worker import CRASH_EXIT_CODE
from support.import_worker_harness import published_repository_path


def _crash() -> None:
    os._exit(CRASH_EXIT_CODE)


class _CrashRecoveryFaultInjector:
    def __init__(self, point: ImportRecoveryFaultPoint) -> None:
        self._point = point

    def maybe_raise(self, point: ImportRecoveryFaultPoint) -> None:
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


def _run_recovery_reconcile(args: argparse.Namespace) -> None:
    settings = _settings_from_args(args)
    fault_point = ImportRecoveryFaultPoint(args.fault_point)
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

    def provider_factory(repo_id: UUID) -> CandidateAImportProvider:
        path = published_repository_path(layout, repo_id)
        return CandidateAImportProvider(settings, layout, path, runner)

    reconciler = ImportStartupReconciler(
        settings=settings,
        layout=layout,
        store=store,
        provider_factory=provider_factory,
        fault_injector=_CrashRecoveryFaultInjector(fault_point),
    )
    try:
        reconciler.reconcile()
    finally:
        control_store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--dolt-binary", default="/usr/local/bin/dolt")
    parser.add_argument("--dolt-version", default="2.1.11")
    parser.add_argument("--repository-id", required=True)
    parser.add_argument(
        "--fault-point",
        choices=(ImportRecoveryFaultPoint.AFTER_AUTOMATIC_REPLAY_COUNT_INCREMENT.value,),
        required=True,
    )
    args = parser.parse_args(argv)
    _run_recovery_reconcile(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
