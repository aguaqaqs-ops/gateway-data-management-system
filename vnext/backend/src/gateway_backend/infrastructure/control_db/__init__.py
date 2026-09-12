"""Concrete local SQLite control DB boundary for the backend runtime."""

from gateway_backend.infrastructure.control_db.database import (
    ControlDbIntegrityError,
    ControlDbUnitOfWork,
    assert_control_db_integrity,
    connect_control_db,
    initialize_and_verify_control_db,
    initialize_control_db,
)
from gateway_backend.infrastructure.control_db.migrations import (
    OPERATIONS_SCHEMA_COMPONENT,
    OPERATIONS_SCHEMA_VERSION,
    WORKSPACE_SCHEMA_COMPONENT,
    WORKSPACE_SCHEMA_VERSION,
    bootstrap_control_schema,
    bootstrap_workspace_schema,
)

__all__ = [
    "ControlDbIntegrityError",
    "ControlDbUnitOfWork",
    "OPERATIONS_SCHEMA_COMPONENT",
    "OPERATIONS_SCHEMA_VERSION",
    "WORKSPACE_SCHEMA_COMPONENT",
    "WORKSPACE_SCHEMA_VERSION",
    "assert_control_db_integrity",
    "bootstrap_control_schema",
    "bootstrap_workspace_schema",
    "connect_control_db",
    "initialize_and_verify_control_db",
    "initialize_control_db",
]
