"""Bounded process-local scalar hooks; no I/O, serialization or business imports."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import monotonic
from typing import Callable, Literal, ParamSpec, TypeVar

Stage = Literal['parse', 'materialize', 'compare', 'risk', 'export', 'bundle', 'rs_import', 'finalize']
Layer = Literal['canonical', 'comparison', 'risk_candidate', 'snapshot_export']
P = ParamSpec('P')
R = TypeVar('R')


@dataclass
class Metrics:
    durations: dict[str, int] = field(default_factory=dict)
    lookups: dict[str, int] = field(default_factory=dict)
    hits: dict[str, int] = field(default_factory=dict)
    shape: dict[str, int] = field(default_factory=dict)
    tables: list[tuple[str, str, str, int | None, int | None, int | None]] = field(default_factory=list)
    table_bytes: int = 0
    tables_total: int = 0
    truncated: bool = False
    input_identity: str | None = None
    # At most one current input: additional different inputs are explicitly unknown.
    ambiguous_input: bool = False
    ordered_seen: set[str] = field(default_factory=set)
    ordered_incomplete: bool = False
    repository_id: str | None = None
    submit_attempt_id: str | None = None


_current: ContextVar[Metrics | None] = ContextVar('execution_metrics', default=None)


def current_metrics() -> Metrics | None:
    return _current.get()


def set_metrics(metrics: Metrics | None) -> None:
    _current.set(metrics)


def duration(stage: Stage, seconds: float) -> None:
    try:
        metrics = _current.get()
        if metrics is not None:
            metrics.durations[stage] = metrics.durations.get(stage, 0) + max(0, int(seconds * 1000))
    except Exception:
        pass


def timed(stage: Stage) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def call(*args: P.args, **kwargs: P.kwargs) -> R:
            if _current.get() is None:
                return function(*args, **kwargs)
            started = monotonic()
            try:
                return function(*args, **kwargs)
            finally:
                duration(stage, monotonic() - started)
        return call
    return decorate


def cache_lookup(layer: Layer, count: int = 1) -> None:
    try:
        metrics = _current.get()
        if metrics is not None:
            metrics.lookups[layer] = metrics.lookups.get(layer, 0) + count
            metrics.hits.setdefault(layer, 0)
    except Exception:
        pass


def cache_hit(layer: Layer) -> None:
    try:
        metrics = _current.get()
        if metrics is not None:
            metrics.hits[layer] = metrics.hits.get(layer, 0) + 1
    except Exception:
        pass


def input_shape(identity: str, *, table_count: int, total_rows: int, max_table_rows: int,
                sql_bytes: int | None = None) -> None:
    try:
        metrics = _current.get()
        if metrics is None or metrics.ambiguous_input:
            return
        if metrics.input_identity is not None and metrics.input_identity != identity:
            metrics.ambiguous_input = True
            for key in ('table_count', 'total_rows', 'max_table_rows', 'sql_bytes', 'ordered_table_rows'):
                metrics.shape.pop(key, None)
            return
        metrics.input_identity = identity
        metrics.shape.update(table_count=table_count, total_rows=total_rows, max_table_rows=max_table_rows)
        if sql_bytes is not None:
            metrics.shape['sql_bytes'] = sql_bytes
    except Exception:
        pass


def pair_table(pair: str, name: str, mode: str, before: int | None, after: int | None,
               changed: int | None) -> None:
    try:
        metrics = _current.get()
        if metrics is None:
            return
        metrics.tables_total += 1
        charge = 192 + len(name.encode('utf-8')) + len(pair.encode('utf-8')) + len(mode.encode('utf-8'))
        if (len(metrics.tables) < 100 and len(name) <= 256 and len(name.encode('utf-8')) <= 256
                and len(pair) <= 255 and len(mode) <= 255 and metrics.table_bytes + charge <= 10 * 1024):
            metrics.table_bytes += charge
            metrics.tables.append((pair, name, mode, before, after, changed))
        else:
            metrics.truncated = True
    except Exception:
        pass


def pair_totals(*, changed_tables: int, changed_rows: int) -> None:
    try:
        metrics = _current.get()
        if metrics is not None:
            for key, value in (('changed_tables', changed_tables), ('changed_rows', changed_rows)):
                metrics.shape[key] = metrics.shape.get(key, 0) + value
    except Exception:
        pass


def bind_scope(repository_id: str, submit_attempt_id: str | None = None) -> None:
    try:
        metrics = _current.get()
        if metrics is not None:
            metrics.repository_id = repository_id
            metrics.submit_attempt_id = submit_attempt_id
    except Exception:
        pass


def ordered_input_table(identity: str, name: str | None = None, rows: int = 0) -> None:
    try:
        metrics = _current.get()
        if metrics is None or metrics.ambiguous_input or metrics.input_identity != identity or metrics.ordered_incomplete:
            return
        metrics.shape.setdefault('ordered_table_rows', 0)
        if name is None or name in metrics.ordered_seen:
            return
        if len(metrics.ordered_seen) >= 100:
            metrics.ordered_incomplete = True
            metrics.shape.pop('ordered_table_rows', None)
            return
        metrics.ordered_seen.add(name)
        metrics.shape['ordered_table_rows'] += rows
    except Exception:
        pass
