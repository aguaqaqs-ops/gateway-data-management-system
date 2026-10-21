"""Helpers for serialized direct access to the shared control database in tests."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from gateway_repository_service.control_db import ControlStore


@contextmanager
def locked_control_connection(control_store: ControlStore) -> Iterator[sqlite3.Connection]:
    with control_store.transaction_lock:
        yield control_store.connection


@contextmanager
def control_db_transaction(control_store: ControlStore) -> Iterator[sqlite3.Connection]:
    with control_store.transaction_lock:
        connection = control_store.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
