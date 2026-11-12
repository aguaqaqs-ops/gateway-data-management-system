"""Connection-scoped registration reads and one atomic scope/INITIAL/Head insert."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from gateway_backend.application.provisioning.contracts import Registration, RegistrationConflict
from gateway_backend.device_identity import validate_scope_identity
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_mapping import _apply_seed_record

def load_registration(connection: sqlite3.Connection, *, environment: str, group: str,
                      device: str, project: str | None = None) -> Registration | None:
    """Read all device rows, including disabled rows; never infer INITIAL from Head."""
    validate_scope_identity(device)
    rows = connection.execute("SELECT * FROM provisioned_scope_mappings WHERE gateway_device_external_key = ?", (device,)).fetchall()
    if not rows:
        # An orphan INITIAL is contradictory evidence, not an unregistered device.
        if connection.execute("SELECT 1 FROM baseline_node_records WHERE gateway_device_external_key = ?", (device,)).fetchone():
            raise RegistrationConflict("fixed scope conflicts")
        return None
    if len(rows) != 1:
        raise RegistrationConflict("fixed scope conflicts")
    row = rows[0]
    if row["enabled"] != 1 or (project is not None and row["business_project_id"] != project):
        raise RegistrationConflict("fixed scope conflicts")
    initial = connection.execute("SELECT * FROM baseline_node_records WHERE repository_id = ? AND kind = 'INITIAL'", (row["repository_id"],)).fetchone()
    head = connection.execute("SELECT n.repository_id FROM baseline_head_records h JOIN baseline_node_records n ON n.node_id = h.node_id WHERE h.repository_id = ?", (row["repository_id"],)).fetchone()
    if (initial is None or head is None or head["repository_id"] != row["repository_id"]
            or initial["gateway_device_external_key"] != device or initial["business_project_id"] != row["business_project_id"]):
        raise RegistrationConflict("fixed scope conflicts")
    return Registration(environment, group, device, row["business_project_id"], row["repository_id"], initial["node_id"], initial["commit_id"])



class SQLiteRegistrationStore:
    def __init__(self, database: Path, environment: str, group: str) -> None:
        self.database = database
        self.environment = environment
        self.group = group

    def lookup(self, device: str, project: str | None = None) -> Registration | None:
        with ControlDbUnitOfWork(self.database, read_only=True) as uow:
            return load_registration(uow.connection, environment=self.environment, group=self.group,
                device=device, project=project)

    def insert_or_exact(self, registration: Registration) -> Registration:
        expected = registration
        try:
            with ControlDbUnitOfWork(self.database) as uow:
                existing = load_registration(uow.connection, environment=self.environment, group=self.group,
                    device=expected.gateway_device_external_key, project=expected.business_project_id)
                if existing is not None:
                    if existing != expected:
                        raise RegistrationConflict("repository response differs from fixed registration")
                    return existing
                _apply_seed_record(uow.connection, {
                    "gateway_device_external_key": expected.gateway_device_external_key,
                    "business_project_id": expected.business_project_id,
                    "repository_id": expected.repository_id, "business_baseline_node_id": expected.initial_node_id,
                    "business_baseline_commit_id": expected.initial_commit_id, "baseline_head_version": 0, "enabled": True,
                }, seed_now=datetime.now(UTC))
        except (sqlite3.IntegrityError, ValueError) as exc:
            raise RegistrationConflict("fixed scope conflicts") from exc
        return expected
