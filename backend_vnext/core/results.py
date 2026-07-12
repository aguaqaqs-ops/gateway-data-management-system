from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeAlias

from .diagnostics import DiagnosticRecord, ErrorRecord
from .digests import DigestRef


@dataclass(frozen=True, slots=True)
class ResultRecord:
    status: str
    value: object | None = None
    error: ErrorRecord | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or not self.status:
            raise ValueError("result status must be a non-empty string")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "value": self.value,
            "error": None if self.error is None else self.error.to_payload(),
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ResultRecord":
        error_payload = payload.get("error")
        diagnostics_payload = payload.get("diagnostics", [])
        if error_payload is not None and not isinstance(error_payload, Mapping):
            raise TypeError("result error payload must be a mapping or null")
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, list):
            raise TypeError("result diagnostics payload must be a list")
        return cls(
            status=_required_str(payload, "status"),
            value=payload.get("value"),
            error=(
                None
                if error_payload is None
                else ErrorRecord.from_payload(error_payload)
            ),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(item)
                for item in diagnostics_payload
            ),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkRunResult:
    dataset_id: str
    dataset_kind: str
    profile: str
    provider: str
    status: str
    validation_result: str
    server_mode: str | None = None
    machine_profile_id: str | None = None
    source_sql_digest: DigestRef | None = None
    source_sql_bytes: int | None = None
    table_count: int | None = None
    row_count_total: int | None = None
    largest_table_row_count: int | None = None
    staging_artifact_bytes: int | None = None
    parse_duration_ms: int | None = None
    staging_duration_ms: int | None = None
    server_start_ms: int | None = None
    import_duration_ms: int | None = None
    commit_duration_ms: int | None = None
    validation_duration_ms: int | None = None
    cleanup_duration_ms: int | None = None
    total_duration_ms: int | None = None
    rows_per_second: float | None = None
    memory_peak: int | None = None
    dolt_version: str | None = None
    provider_contract_version: str | None = None
    import_artifact_manifest_digest: DigestRef | None = None
    source_snapshot_digest: DigestRef | None = None
    readback_snapshot_digest: DigestRef | None = None
    commit_hash: str | None = None
    failure_phase: str | None = None
    failure_reason: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in (
            "dataset_id",
            "dataset_kind",
            "profile",
            "provider",
            "status",
            "validation_result",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        for field_name in (
            "server_mode",
            "machine_profile_id",
            "dolt_version",
            "provider_contract_version",
            "commit_hash",
            "failure_phase",
            "failure_reason",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        for field_name in (
            "source_sql_bytes",
            "table_count",
            "row_count_total",
            "largest_table_row_count",
            "staging_artifact_bytes",
            "parse_duration_ms",
            "staging_duration_ms",
            "server_start_ms",
            "import_duration_ms",
            "commit_duration_ms",
            "validation_duration_ms",
            "cleanup_duration_ms",
            "total_duration_ms",
            "memory_peak",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.rows_per_second is not None and (
            isinstance(self.rows_per_second, bool) or self.rows_per_second < 0
        ):
            raise ValueError("rows_per_second must be non-negative or None")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_kind": self.dataset_kind,
            "profile": self.profile,
            "provider": self.provider,
            "status": self.status,
            "validation_result": self.validation_result,
            "server_mode": self.server_mode,
            "machine_profile_id": self.machine_profile_id,
            "source_sql_digest": _digest_payload(self.source_sql_digest),
            "source_sql_bytes": self.source_sql_bytes,
            "table_count": self.table_count,
            "row_count_total": self.row_count_total,
            "largest_table_row_count": self.largest_table_row_count,
            "staging_artifact_bytes": self.staging_artifact_bytes,
            "parse_duration_ms": self.parse_duration_ms,
            "staging_duration_ms": self.staging_duration_ms,
            "server_start_ms": self.server_start_ms,
            "import_duration_ms": self.import_duration_ms,
            "commit_duration_ms": self.commit_duration_ms,
            "validation_duration_ms": self.validation_duration_ms,
            "cleanup_duration_ms": self.cleanup_duration_ms,
            "total_duration_ms": self.total_duration_ms,
            "rows_per_second": self.rows_per_second,
            "memory_peak": self.memory_peak,
            "dolt_version": self.dolt_version,
            "provider_contract_version": self.provider_contract_version,
            "import_artifact_manifest_digest": _digest_payload(
                self.import_artifact_manifest_digest
            ),
            "source_snapshot_digest": _digest_payload(self.source_snapshot_digest),
            "readback_snapshot_digest": _digest_payload(
                self.readback_snapshot_digest
            ),
            "commit_hash": self.commit_hash,
            "failure_phase": self.failure_phase,
            "failure_reason": self.failure_reason,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "BenchmarkRunResult":
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, list):
            raise TypeError("benchmark diagnostics payload must be a list")
        return cls(
            dataset_id=_required_str(payload, "dataset_id"),
            dataset_kind=_required_str(payload, "dataset_kind"),
            profile=_required_str(payload, "profile"),
            provider=_required_str(payload, "provider"),
            status=_required_str(payload, "status"),
            validation_result=_required_str(payload, "validation_result"),
            server_mode=_optional_str(payload.get("server_mode"), field_name="server_mode"),
            machine_profile_id=_optional_str(
                payload.get("machine_profile_id"),
                field_name="machine_profile_id",
            ),
            source_sql_digest=_optional_digest(payload.get("source_sql_digest")),
            source_sql_bytes=_optional_int(payload.get("source_sql_bytes")),
            table_count=_optional_int(payload.get("table_count")),
            row_count_total=_optional_int(payload.get("row_count_total")),
            largest_table_row_count=_optional_int(
                payload.get("largest_table_row_count")
            ),
            staging_artifact_bytes=_optional_int(
                payload.get("staging_artifact_bytes")
            ),
            parse_duration_ms=_optional_int(payload.get("parse_duration_ms")),
            staging_duration_ms=_optional_int(payload.get("staging_duration_ms")),
            server_start_ms=_optional_int(payload.get("server_start_ms")),
            import_duration_ms=_optional_int(payload.get("import_duration_ms")),
            commit_duration_ms=_optional_int(payload.get("commit_duration_ms")),
            validation_duration_ms=_optional_int(
                payload.get("validation_duration_ms")
            ),
            cleanup_duration_ms=_optional_int(payload.get("cleanup_duration_ms")),
            total_duration_ms=_optional_int(payload.get("total_duration_ms")),
            rows_per_second=_optional_float(payload.get("rows_per_second")),
            memory_peak=_optional_int(payload.get("memory_peak")),
            dolt_version=_optional_str(payload.get("dolt_version"), field_name="dolt_version"),
            provider_contract_version=_optional_str(
                payload.get("provider_contract_version"),
                field_name="provider_contract_version",
            ),
            import_artifact_manifest_digest=_optional_digest(
                payload.get("import_artifact_manifest_digest")
            ),
            source_snapshot_digest=_optional_digest(
                payload.get("source_snapshot_digest")
            ),
            readback_snapshot_digest=_optional_digest(
                payload.get("readback_snapshot_digest")
            ),
            commit_hash=_optional_str(payload.get("commit_hash"), field_name="commit_hash"),
            failure_phase=_optional_str(payload.get("failure_phase"), field_name="failure_phase"),
            failure_reason=_optional_str(
                payload.get("failure_reason"),
                field_name="failure_reason",
            ),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(item)
                for item in diagnostics_payload
            ),
        )


def _digest_payload(value: DigestRef | None) -> str | None:
    if value is None:
        return None
    return value.to_payload()


def _optional_digest(value: object) -> DigestRef | None:
    if value is None:
        return None
    return DigestRef.parse(str(value))


def _required_str(payload: Mapping[str, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("expected an integer or null")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("expected a number or null")
    return float(value)


def _optional_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string or None")
    return value


Result: TypeAlias = ResultRecord
