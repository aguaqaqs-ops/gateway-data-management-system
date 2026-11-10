"""Rebuildable BE/worker configuration comparison; never business authority."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from uuid import uuid4

from gateway_backend.deployment_config import DeploymentConfig, _document
from gateway_backend.runtime_preflight import DeploymentIdentityChanged, check_configured_root
from gateway_backend.infrastructure.artifact_store.layout import descriptor_mount_id

CONFIGURATION_RECORD = ".gateway-runtime-configuration.json"


def configuration_document(config: DeploymentConfig) -> dict[str, object]:
    return {"schema_version": 1, "environment_id": config.storage.environment_id,
        "group_id": config.storage.group_id, "storage_digest": config.storage.digest,
        "resource_digest": config.resources.digest}


def _read(directory: int) -> dict[str, object]:
    descriptor = os.open(CONFIGURATION_RECORD, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or descriptor_mount_id(descriptor) != descriptor_mount_id(directory):
            raise ValueError("configuration record must be an ordinary file on metadata")
        raw = os.read(descriptor, 4097)
        if len(raw) > 4096:
            raise ValueError("configuration record exceeds its bound")
        document = _document(raw)
        if type(document.get("schema_version")) is not int:
            raise ValueError("configuration record has invalid schema")
        return document
    finally:
        os.close(descriptor)


def compare_configuration(config: DeploymentConfig) -> None:
    try:
        metadata = Path(config.storage.roots["be-metadata"].path)
        check_configured_root(config.storage, "be-metadata")
        directory = os.open(metadata, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if _read(directory) != configuration_document(config):
                raise ValueError("configuration record mismatch")
        finally:
            os.close(directory)
    except (OSError, ValueError, StopIteration):
        raise DeploymentIdentityChanged("backend/worker configuration record unavailable or inconsistent") from None


def publish_configuration(config: DeploymentConfig) -> None:
    """Publish only at explicit backend startup after role/euid preflight.

    Stopped-service restart may replace stale/malformed ordinary derived bytes.
    Symlinks, non-files and submounts never grant replacement authority.
    """
    check_configured_root(config.storage, "be-metadata")
    directory = os.open(config.storage.roots["be-metadata"].path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".gateway-configuration-" + uuid4().hex
    created = False
    try:
        try:
            descriptor = os.open(CONFIGURATION_RECORD, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            pass
        else:
            try:
                if (not stat.S_ISREG(os.fstat(descriptor).st_mode)
                        or descriptor_mount_id(descriptor) != descriptor_mount_id(directory)):
                    raise ValueError("configuration record is redirected or not ordinary")
            finally:
                os.close(descriptor)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=directory)
        created = True
        try:
            payload = json.dumps(configuration_document(config), sort_keys=True).encode()
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, CONFIGURATION_RECORD, src_dir_fd=directory, dst_dir_fd=directory)
        created = False
        os.fsync(directory)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(directory)
