"""Stopped-service private admin CLI for Versioned import manual recovery."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from uuid import UUID

from gateway_repository_contracts import OperationStatus

from gateway_repository_service.control_db import (
    CONTROL_DB_USER_VERSION,
    ControlDbError,
    ControlDbNewerVersionError,
    ControlStore,
)
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.models import (
    ManualCorrectionDecision,
    RecoveryAuditAction,
    is_manual_recovery_error,
    utc_now_iso,
)
from gateway_repository_service.versioned_import.recovery import (
    build_evidence_summary,
    build_succeeded_result,
    cleanup_after_not_published_correction,
    cleanup_after_succeeded_correction,
    collect_recovery_evidence,
    evidence_supports_not_published_decision,
    evidence_supports_succeeded_decision,
    resolve_not_published_error,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore

_LOGGER = logging.getLogger(__name__)


def _print_json_summary(summary: dict[str, object]) -> None:
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))


def _parse_operation_id(raw: str) -> UUID | None:
    try:
        return UUID(raw)
    except ValueError:
        return None


def _parse_decision(raw: str) -> ManualCorrectionDecision | None:
    try:
        return ManualCorrectionDecision(raw)
    except ValueError:
        return None


def _open_import_store(
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
) -> tuple[ControlStore, ImportOperationStore, DoltRunner]:
    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
    )
    import_store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    OfflineCliCapabilityGate.verify(settings, layout)
    dolt_runner = DoltRunner(settings, layout.root)
    return control_store, import_store, dolt_runner


def _run_inspect(
    *,
    settings: RepositoryServiceSettings,
    operation_id: UUID,
) -> int:
    layout = DurableLayout.create_service(settings.data_root)
    root_lock = DurableRootLock(layout.service_lock)
    control_store: ControlStore | None = None
    try:
        try:
            root_lock.acquire()
        except RootLockBusy:
            print("durable root lock is held by a running service", file=sys.stderr)
            return 3

        try:
            control_store, import_store, dolt_runner = _open_import_store(settings, layout)
        except ControlDbNewerVersionError as exc:
            print(str(exc), file=sys.stderr)
            return 4
        except ControlDbError as exc:
            print(str(exc), file=sys.stderr)
            return 4

        context = import_store.load_execution_context(operation_id)
        if context is None:
            print("operation does not exist", file=sys.stderr)
            return 5
        operation = import_store.get_operation(context.repository_id, operation_id)
        if (
            operation is None
            or operation.status != OperationStatus.FAILED
            or not is_manual_recovery_error(operation.error)
        ):
            print("operation is not awaiting manual recovery", file=sys.stderr)
            return 5

        provider_factory = ServiceRuntime._build_provider_factory(
            settings=settings,
            layout=layout,
            dolt_runner=dolt_runner,
        )
        provider = provider_factory(context.repository_id)
        evidence = collect_recovery_evidence(
            settings=settings,
            layout=layout,
            store=import_store,
            provider=provider,
            context=context,
        )
        if evidence is None:
            print("recovery evidence is unavailable", file=sys.stderr)
            return 6

        summary = build_evidence_summary(evidence, operation=operation)
        _print_json_summary(summary)
        return 0
    finally:
        if control_store is not None:
            control_store.close()
        root_lock.release()


def _run_apply(
    *,
    settings: RepositoryServiceSettings,
    operation_id: UUID,
    decision: ManualCorrectionDecision,
) -> int:
    layout = DurableLayout.create_service(settings.data_root)
    root_lock = DurableRootLock(layout.service_lock)
    control_store: ControlStore | None = None
    try:
        try:
            root_lock.acquire()
        except RootLockBusy:
            print("durable root lock is held by a running service", file=sys.stderr)
            return 3

        try:
            control_store, import_store, dolt_runner = _open_import_store(settings, layout)
        except ControlDbNewerVersionError as exc:
            print(str(exc), file=sys.stderr)
            return 4
        except ControlDbError as exc:
            print(str(exc), file=sys.stderr)
            return 4

        context = import_store.load_execution_context(operation_id)
        if context is None:
            print("operation does not exist", file=sys.stderr)
            return 5
        operation = import_store.get_operation(context.repository_id, operation_id)
        if (
            operation is None
            or operation.status != OperationStatus.FAILED
            or not is_manual_recovery_error(operation.error)
        ):
            print("operation is not awaiting manual recovery", file=sys.stderr)
            return 5

        provider_factory = ServiceRuntime._build_provider_factory(
            settings=settings,
            layout=layout,
            dolt_runner=dolt_runner,
        )
        provider = provider_factory(context.repository_id)
        evidence = collect_recovery_evidence(
            settings=settings,
            layout=layout,
            store=import_store,
            provider=provider,
            context=context,
        )
        if evidence is None:
            print("recovery evidence is unavailable", file=sys.stderr)
            return 6

        prior_status = operation.status.value
        prior_code = operation.error.code if operation.error is not None else None
        applied_at = utc_now_iso()

        if decision == ManualCorrectionDecision.SUCCEEDED:
            if not evidence_supports_succeeded_decision(evidence):
                print("evidence does not support SUCCEEDED correction", file=sys.stderr)
                return 6
            final_result = build_succeeded_result(evidence, context)
            if final_result is None:
                print("unable to rebuild VersionedImportResult from evidence", file=sys.stderr)
                return 6
            evidence_summary = build_evidence_summary(
                evidence,
                operation=operation,
                decision=decision,
                action=RecoveryAuditAction.INSPECT_APPLY_SUCCESS,
                prior_status=prior_status,
                prior_code=prior_code,
                final_status=OperationStatus.SUCCEEDED.value,
                applied_at=applied_at,
            )
            corrected = import_store.apply_manual_correction(
                operation_id,
                decision=decision,
                evidence_summary=evidence_summary,
                final_result=final_result,
            )
            cleanup_after_succeeded_correction(
                store=import_store,
                layout=layout,
                context=context,
                provider=provider,
                candidate=final_result.commit_id,
            )
            final_status = corrected.status.value
            final_code = None
            action = RecoveryAuditAction.INSPECT_APPLY_SUCCESS
        else:
            if not evidence_supports_not_published_decision(evidence):
                print("evidence does not support NOT_PUBLISHED correction", file=sys.stderr)
                return 6
            final_error = resolve_not_published_error(evidence)
            if final_error is None:
                print("unable to resolve NOT_PUBLISHED terminal error from evidence", file=sys.stderr)
                return 6
            evidence_summary = build_evidence_summary(
                evidence,
                operation=operation,
                decision=decision,
                action=RecoveryAuditAction.INSPECT_APPLY_NOT_PUBLISHED,
                prior_status=prior_status,
                prior_code=prior_code,
                final_status=OperationStatus.FAILED.value,
                final_code=final_error.code,
                applied_at=applied_at,
            )
            corrected = import_store.apply_manual_correction(
                operation_id,
                decision=decision,
                evidence_summary=evidence_summary,
                final_error=final_error,
            )
            cleanup_after_not_published_correction(
                layout=layout,
                context=context,
                provider=provider,
            )
            final_status = corrected.status.value
            final_code = final_error.code
            action = RecoveryAuditAction.INSPECT_APPLY_NOT_PUBLISHED

        summary = build_evidence_summary(
            evidence,
            operation=corrected,
            decision=decision,
            action=action,
            prior_status=prior_status,
            prior_code=prior_code,
            final_status=final_status,
            final_code=final_code,
            applied_at=applied_at,
        )
        _LOGGER.info("admin apply audit identity %s", json.dumps(summary, sort_keys=True))
        _print_json_summary(summary)
        return 0
    finally:
        if control_store is not None:
            control_store.close()
        root_lock.release()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Private Versioned import recovery admin CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--operation-id", required=True)
    inspect_parser.add_argument("--data-root", type=Path)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--operation-id", required=True)
    apply_parser.add_argument("--decision", required=True, choices=[item.value for item in ManualCorrectionDecision])
    apply_parser.add_argument("--data-root", type=Path)

    args = parser.parse_args(argv)

    operation_id = _parse_operation_id(args.operation_id)
    if operation_id is None:
        print("invalid operation id", file=sys.stderr)
        raise SystemExit(2)

    settings = RepositoryServiceSettings()
    if args.data_root is not None:
        settings = settings.model_copy(update={"data_root": args.data_root})

    if args.command == "inspect":
        raise SystemExit(_run_inspect(settings=settings, operation_id=operation_id))

    decision = _parse_decision(args.decision)
    if decision is None:
        print("invalid decision", file=sys.stderr)
        raise SystemExit(2)

    raise SystemExit(_run_apply(settings=settings, operation_id=operation_id, decision=decision))


if __name__ == "__main__":
    main()
