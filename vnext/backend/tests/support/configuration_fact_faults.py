"""Shared corrupt-body vectors for public authorization-before-decode owners."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
from typing import Literal

import pytest

from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_submission import SQLiteSubmissionRepository
from gateway_backend.infrastructure.control_db.sqlite_workspace import SQLiteWorkspaceRepository

CONFIGURATION_BODY_FAULTS = ("missing_facts", "source_binding")


def corrupt_configuration_body(db_path: Path, *, kind: Literal["preview", "attempt", "submission"],
                               target_id: str, fault: str) -> str:
    table, key = {"preview": ("preview_result_records", "preview_result_id"),
                  "attempt": ("submit_attempt_records", "submit_attempt_id"),
                  "submission": ("submission_records", "submission_id")}[kind]
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        if kind == "preview":
            row = unit_of_work.connection.execute("SELECT binding FROM preview_result_records WHERE preview_result_id = ?", (target_id,)).fetchone()
            assert row is not None
            binding = json.loads(row[0])
            if fault == "missing_facts":
                binding["canonical"]["configuration_facts"] = {}
                message = "configuration facts envelope fields"
            else:
                assert fault == "source_binding"
                binding["canonical"]["canonical_table_set_closure_ref"]["raw_sha256"] = "sha256:" + "8" * 64
                message = "canonical table set closure digest"
            unit_of_work.connection.execute("UPDATE preview_result_records SET binding = ? WHERE preview_result_id = ?",
                (canonicalize_json_value(binding), target_id))
        else:
            if fault == "missing_facts":
                column, value, message = "configuration_facts", b"{}", "configuration facts envelope fields"
            else:
                assert fault == "source_binding"
                column, value, message = "source_artifact_refs", b'["a1:durable:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"]', "configuration source artifacts"
            unit_of_work.connection.execute(f"UPDATE {table} SET {column} = ? WHERE {key} = ?", (value, target_id))
    return message


@contextmanager
def forbid_configuration_object_reads(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("permission must be checked before business-object reads")
    with monkeypatch.context() as patch:
        for name in ("get_submission_access_binding", "get_submission", "get_submit_attempt"):
            patch.setattr(SQLiteSubmissionRepository, name, forbidden)
        for name in ("get_workspace", "get_preview_result"):
            patch.setattr(SQLiteWorkspaceRepository, name, forbidden)
        yield
