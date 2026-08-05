"""Subprocess crash worker for synchronous mutation recovery tests."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from uuid import UUID

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE, UploadRequestHeaders
from gateway_repository_service.create_repository.adapters import FilesystemPublicationAdapter
from gateway_repository_service.create_repository.command import CreateRepositoryCommand
from gateway_repository_service.create_repository.ports import NoOpCreateRepositoryFaultInjector
from gateway_repository_service.publication import (
    FaultPoint,
    atomic_publish,
    atomic_publish_file,
    prepare_directory_publish,
    prepare_file_publish,
)
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.adapters import ArtifactFilesystemPublicationAdapter
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand
from gateway_repository_service.upload_artifact.ports import NoOpUploadArtifactFaultInjector

CRASH_EXIT_CODE = 75


def _upload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _crash() -> None:
    os._exit(CRASH_EXIT_CODE)


class CrashFilesystemPublicationAdapter(FilesystemPublicationAdapter):
    def __init__(self, point: str | None) -> None:
        self._point = point

    def publish(
        self,
        staging: Path,
        target: Path,
        *,
        fault: FaultPoint = FaultPoint.NONE,
    ) -> None:
        del fault
        if self._point == "before_rename":
            if target.exists():
                raise FileExistsError(target)
            if staging.stat().st_dev != target.parent.stat().st_dev:
                raise OSError("staging and target parent are on different filesystems")
            prepare_directory_publish(staging)
            _crash()
        atomic_publish(staging, target, fault=FaultPoint.NONE)
        if self._point == "after_rename":
            _crash()


class CrashArtifactPublicationAdapter(ArtifactFilesystemPublicationAdapter):
    def __init__(self, point: str | None) -> None:
        self._point = point

    def publish_file(
        self,
        staging: Path,
        target: Path,
        *,
        fault: FaultPoint = FaultPoint.NONE,
    ) -> None:
        del fault
        if self._point == "before_rename":
            if target.exists():
                raise FileExistsError(target)
            prepare_file_publish(staging)
            _crash()
        atomic_publish_file(staging, target, fault=FaultPoint.NONE)
        if self._point == "after_rename":
            _crash()


class CrashCreateFaultInjector(NoOpCreateRepositoryFaultInjector):
    def __init__(self, point: str) -> None:
        self._point = point

    def after_pending(self) -> None:
        if self._point == "after_pending":
            _crash()

    def after_staging(self) -> None:
        if self._point == "after_staging":
            _crash()

    def after_dolt_init(self) -> None:
        if self._point == "after_dolt_init":
            _crash()

    def after_succeeded_before_response(self) -> None:
        if self._point == "after_succeeded":
            _crash()

    def publication_fault(self) -> FaultPoint:
        return FaultPoint.NONE


class CrashUploadFaultInjector(NoOpUploadArtifactFaultInjector):
    def __init__(self, point: str) -> None:
        self._point = point

    def after_pending(self) -> None:
        if self._point == "after_pending":
            _crash()

    def after_partial_body(self) -> None:
        if self._point == "after_partial_body":
            _crash()

    def after_complete_close(self) -> None:
        if self._point == "after_complete_close":
            _crash()

    def after_succeeded_before_response(self) -> None:
        if self._point == "after_succeeded":
            _crash()

    def publication_fault(self) -> FaultPoint:
        return FaultPoint.NONE


class _UploadBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._sent = False

    def __aiter__(self) -> "_UploadBody":
        return self

    async def __anext__(self) -> bytes:
        if self._sent:
            raise StopAsyncIteration
        self._sent = True
        return self._payload


def _settings_from_args(args: argparse.Namespace) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        data_root=Path(args.data_root),
        bearer_token="test-bearer-token",
        dolt_binary=Path(args.dolt_binary),
        dolt_version=args.dolt_version,
    )


def _publication_point(point: str | None) -> str | None:
    if point in {"before_rename", "after_rename"}:
        return point
    return None


def _run_create(settings: RepositoryServiceSettings, *, idempotency_key: str, point: str | None) -> None:
    runtime = ServiceRuntime.start(settings)
    command = CreateRepositoryCommand(
        settings=runtime.settings,
        layout=runtime.layout,
        mutation_store=runtime.mutation_store,
        publication_port=CrashFilesystemPublicationAdapter(_publication_point(point)),
        fault_injector=CrashCreateFaultInjector(point) if point is not None else None,
    )
    command.execute(idempotency_key)
    runtime.shutdown()


async def _run_upload(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    idempotency_key: str,
    payload: bytes,
    point: str | None,
) -> None:
    runtime = ServiceRuntime.start(settings)
    headers = UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(payload),
        idempotency_key=idempotency_key,
        artifact_sha256=_upload_sha256(payload),
    )
    command = UploadArtifactCommand(
        settings=runtime.settings,
        layout=runtime.layout,
        mutation_store=runtime.mutation_store,
        publication_port=CrashArtifactPublicationAdapter(_publication_point(point)),
        fault_injector=CrashUploadFaultInjector(point) if point is not None else None,
    )
    body = cast(AsyncIterator[bytes], _UploadBody(payload))
    await command.execute(repository_id, headers, body)
    runtime.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--dolt-binary", default="/usr/local/bin/dolt")
    parser.add_argument("--dolt-version", default="2.1.11")
    parser.add_argument("--mode", choices=("setup_create", "crash_create", "crash_upload"), required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--fault-point", default=None)
    parser.add_argument("--repository-id", default=None)
    parser.add_argument("--payload-hex", default=None)
    args = parser.parse_args(argv)
    settings = _settings_from_args(args)

    if args.mode == "setup_create":
        _run_create(settings, idempotency_key=args.idempotency_key, point=None)
        return 0

    if args.mode == "crash_create":
        if args.fault_point is None:
            raise SystemExit("crash_create requires --fault-point")
        _run_create(settings, idempotency_key=args.idempotency_key, point=args.fault_point)
        return 0

    if args.repository_id is None or args.payload_hex is None:
        raise SystemExit("crash_upload requires --repository-id and --payload-hex")
    if args.fault_point is None:
        raise SystemExit("crash_upload requires --fault-point")
    repository_id = UUID(args.repository_id)
    payload = bytes.fromhex(args.payload_hex)
    asyncio.run(
        _run_upload(
            settings,
            repository_id=repository_id,
            idempotency_key=args.idempotency_key,
            payload=payload,
            point=args.fault_point,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
