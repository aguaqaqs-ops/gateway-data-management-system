from __future__ import annotations

from collections.abc import Sequence
from collections.abc import Mapping
from dataclasses import dataclass

from ...artifacts.manifest import ArtifactRef
from ...contracts.versions import SCALAR_ENCODING_VERSION
from ...core.digests import DigestRef
from ...core.row_digests import stable_rows_digest
from ...core.scalar_encoding import (
    normalize_snapshot_row,
    normalize_snapshot_rows,
)
from ...core.identifiers import canonical_identifier


@dataclass(frozen=True, slots=True)
class ProjectionLogicalDigestParts:
    row_identity_digest: DigestRef
    projected_row_value_digest: DigestRef
    projection_logical_digest: DigestRef


def normalize_projection_row(
    row: Sequence[object],
    columns: Sequence[object],
) -> tuple[object, ...]:
    return normalize_snapshot_row(row, columns)


def normalize_projection_rows(
    rows: Sequence[Sequence[object]],
    columns: Sequence[object],
) -> tuple[tuple[object, ...], ...]:
    return normalize_snapshot_rows(rows, columns)


def build_projection_schema_digest(
    *,
    table_name: str,
    selected_columns: Sequence[str],
    ignored_columns: Sequence[str],
    effective_compare_key: Sequence[str],
    table_ruleset_version: str,
    projection_contract_version: str,
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION,
) -> DigestRef:
    normalized_table_name = canonical_identifier(table_name)
    if not normalized_table_name:
        raise ValueError("table_name must resolve to a non-empty identifier")
    for field_name, value in (
        ("table_ruleset_version", table_ruleset_version),
        ("projection_contract_version", projection_contract_version),
        ("scalar_encoding_version", scalar_encoding_version),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")
    return DigestRef.from_payload(
        {
            "table_name": normalized_table_name,
            "selected_columns": _normalize_identifier_set(
                selected_columns,
                field_name="selected_columns",
            ),
            "ignored_columns": _normalize_identifier_set(
                ignored_columns,
                field_name="ignored_columns",
            ),
            "effective_compare_key": _normalize_identifier_set(
                effective_compare_key,
                field_name="effective_compare_key",
            ),
            "table_ruleset_version": table_ruleset_version,
            "projection_contract_version": projection_contract_version,
            "scalar_encoding_version": scalar_encoding_version,
        }
    )


def build_projection_logical_digest(
    rows: Sequence[Sequence[object]],
    columns: Sequence[object],
    *,
    projection_schema_digest: DigestRef | str,
    row_identity_columns: Sequence[str] = (),
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION,
) -> DigestRef:
    return build_projection_logical_digest_parts(
        rows=rows,
        columns=columns,
        projection_schema_digest=projection_schema_digest,
        row_identity_columns=row_identity_columns,
        scalar_encoding_version=scalar_encoding_version,
    ).projection_logical_digest


def build_projection_logical_digest_from_parts(
    *,
    row_identity_digest: DigestRef | str,
    projected_row_value_digest: DigestRef | str,
    projection_schema_digest: DigestRef | str,
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION,
) -> DigestRef:
    normalized_projection_schema_digest = DigestRef.parse(str(projection_schema_digest))
    normalized_row_identity_digest = DigestRef.parse(str(row_identity_digest))
    normalized_projected_row_value_digest = DigestRef.parse(str(projected_row_value_digest))
    if not isinstance(scalar_encoding_version, str) or not scalar_encoding_version.strip():
        raise ValueError("scalar_encoding_version must be a non-empty string")
    return DigestRef.from_payload(
        {
            "projection_schema_digest": normalized_projection_schema_digest.to_payload(),
            "row_identity_digest": normalized_row_identity_digest.to_payload(),
            "projected_row_value_digest": normalized_projected_row_value_digest.to_payload(),
            "scalar_encoding_version": scalar_encoding_version,
        }
    )


def build_projection_logical_digest_parts(
    rows: Sequence[Sequence[object]],
    columns: Sequence[object],
    *,
    projection_schema_digest: DigestRef | str,
    row_identity_columns: Sequence[str] = (),
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION,
) -> ProjectionLogicalDigestParts:
    normalized_projection_schema_digest = DigestRef.parse(str(projection_schema_digest))
    if not isinstance(scalar_encoding_version, str) or not scalar_encoding_version.strip():
        raise ValueError("scalar_encoding_version must be a non-empty string")
    normalized_rows = normalize_projection_rows(rows, columns)
    canonical_column_names = tuple(_column_name(column) for column in columns)
    if len(set(canonical_column_names)) != len(canonical_column_names):
        raise ValueError("columns must resolve to unique canonical names")

    if row_identity_columns:
        normalized_row_identity_columns = _normalize_identifier_set(
            row_identity_columns,
            field_name="row_identity_columns",
        )
    else:
        normalized_row_identity_columns = canonical_column_names

    column_indexes = {column_name: index for index, column_name in enumerate(canonical_column_names)}
    try:
        row_identity_indexes = tuple(column_indexes[column_name] for column_name in normalized_row_identity_columns)
    except KeyError as exc:
        raise ValueError("row_identity_columns must be present in columns") from exc

    row_identity_rows = tuple(
        tuple(row[index] for index in row_identity_indexes)
        for row in normalized_rows
    )
    row_identity_column_names = tuple(canonical_column_names[index] for index in row_identity_indexes)
    row_identity_digest = stable_rows_digest(row_identity_rows, row_identity_column_names)
    projected_row_value_digest = stable_rows_digest(normalized_rows, canonical_column_names)

    projection_logical_digest = build_projection_logical_digest_from_parts(
        row_identity_digest=row_identity_digest,
        projected_row_value_digest=projected_row_value_digest,
        projection_schema_digest=normalized_projection_schema_digest,
        scalar_encoding_version=scalar_encoding_version,
    )
    return ProjectionLogicalDigestParts(
        row_identity_digest=row_identity_digest,
        projected_row_value_digest=projected_row_value_digest,
        projection_logical_digest=projection_logical_digest,
    )


def build_comparison_table_fact_digest(
    table_fact: object,
    *,
    comparison_contract_version: str,
    projection_contract_version: str,
    table_ruleset_version: str,
    scalar_encoding_version: str,
) -> DigestRef:
    from .models import ComparisonTableFact

    if not isinstance(table_fact, ComparisonTableFact):
        raise TypeError("table_fact must be a ComparisonTableFact")
    if not isinstance(comparison_contract_version, str) or not comparison_contract_version.strip():
        raise ValueError("comparison_contract_version must be a non-empty string")
    if not isinstance(projection_contract_version, str) or not projection_contract_version.strip():
        raise ValueError("projection_contract_version must be a non-empty string")
    if not isinstance(table_ruleset_version, str) or not table_ruleset_version.strip():
        raise ValueError("table_ruleset_version must be a non-empty string")
    if not isinstance(scalar_encoding_version, str) or not scalar_encoding_version.strip():
        raise ValueError("scalar_encoding_version must be a non-empty string")
    return DigestRef.from_payload(
        {
            "comparison_contract_version": comparison_contract_version,
            "projection_contract_version": projection_contract_version,
            "table_ruleset_version": table_ruleset_version,
            "scalar_encoding_version": scalar_encoding_version,
            "table_name": canonical_identifier(table_fact.table_name),
            "status": table_fact.status.value,
            "projection_schema_digest": _optional_digest_payload(
                table_fact.projection_schema_digest,
            ),
            "before_projection_logical_digest": _optional_digest_payload(
                table_fact.before_projection_logical_digest,
            ),
            "current_projection_logical_digest": _optional_digest_payload(
                table_fact.current_projection_logical_digest,
            ),
            "row_counts": _row_counts_payload(table_fact.row_counts),
            "row_change_stats": _mapping_payload(table_fact.row_change_stats),
            "schema_changes": _mapping_payload(table_fact.schema_changes),
            "records_manifest_digest": _records_manifest_digest_payload(
                table_fact.records_ref,
            ),
            "ordered_extension": _ordered_extension_payload(table_fact.ordered_extension),
        }
    )


def build_comparison_digest(
    *,
    before_snapshot_digest: DigestRef | str,
    current_snapshot_digest: DigestRef | str,
    comparison_contract_version: str,
    projection_contract_version: str,
    table_ruleset_version: str,
    scalar_encoding_version: str,
    requested_tables: Sequence[str] = (),
    comparison_options: object | None = None,
    table_ruleset_digest: DigestRef | str | None = None,
    table_aliases: Sequence[object] = (),
    table_fact_digests: Mapping[str, DigestRef | str] | Sequence[tuple[str, DigestRef | str]] = (),
    summary_digest: DigestRef | str | None = None,
) -> DigestRef:
    if not isinstance(comparison_contract_version, str) or not comparison_contract_version.strip():
        raise ValueError("comparison_contract_version must be a non-empty string")
    if not isinstance(projection_contract_version, str) or not projection_contract_version.strip():
        raise ValueError("projection_contract_version must be a non-empty string")
    if not isinstance(table_ruleset_version, str) or not table_ruleset_version.strip():
        raise ValueError("table_ruleset_version must be a non-empty string")
    if not isinstance(scalar_encoding_version, str) or not scalar_encoding_version.strip():
        raise ValueError("scalar_encoding_version must be a non-empty string")
    normalized_fact_digests = tuple(
        (
            canonical_identifier(table_name),
            _optional_digest_payload(digest_value),
        )
        for table_name, digest_value in _iter_table_fact_digests(table_fact_digests)
    )
    return DigestRef.from_payload(
        {
            "before_snapshot_digest": DigestRef.parse(str(before_snapshot_digest)).to_payload(),
            "current_snapshot_digest": DigestRef.parse(str(current_snapshot_digest)).to_payload(),
            "comparison_contract_version": comparison_contract_version,
            "projection_contract_version": projection_contract_version,
            "table_ruleset_version": table_ruleset_version,
            "scalar_encoding_version": scalar_encoding_version,
            "table_ruleset_digest": _optional_digest_payload(table_ruleset_digest),
            "table_aliases": _table_aliases_payload(table_aliases),
            "requested_tables": tuple(
                canonical_identifier(table_name)
                for table_name in requested_tables
                if canonical_identifier(table_name)
            ),
            "comparison_options": comparison_options,
            "table_fact_digests": normalized_fact_digests,
            "summary_digest": _optional_digest_payload(summary_digest),
        }
    )


def build_comparison_records_closure_digest(closure: object) -> DigestRef:
    if not hasattr(closure, "payload_for_digest"):
        raise TypeError("closure must provide payload_for_digest()")
    payload = closure.payload_for_digest()
    if not isinstance(payload, Mapping):
        raise TypeError("closure payload_for_digest() must return a mapping")
    return DigestRef.from_payload(payload)


def _column_name(column: object) -> str:
    value = getattr(column, "name", column)
    if not isinstance(value, str):
        value = str(value)
    normalized = canonical_identifier(value)
    if not normalized:
        raise ValueError("column names must resolve to non-empty identifiers")
    return normalized


def _normalize_identifier_set(
    values: Sequence[str],
    *,
    field_name: str,
) -> tuple[str, ...]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        normalized_value = canonical_identifier(value)
        if not normalized_value:
            raise ValueError(f"{field_name} must not contain empty identifiers")
        if normalized_value in seen:
            raise ValueError(f"duplicate canonical identifier in {field_name}: {normalized_value}")
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return tuple(sorted(normalized_values))


def _mapping_payload(payload: object | None) -> dict[str, object] | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise TypeError("mapping payload must be a mapping or None")
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


def _table_aliases_payload(aliases: Sequence[object]) -> tuple[object, ...]:
    payloads: list[dict[str, object] | None] = []
    for alias in aliases:
        payload_for_digest = getattr(alias, "payload_for_digest", None)
        if callable(payload_for_digest):
            payload = payload_for_digest()
        elif isinstance(alias, Mapping):
            payload = alias
        else:
            raise TypeError("table_aliases must contain alias payloads")
        payloads.append(_mapping_payload(payload))
    return tuple(sorted(payloads, key=lambda item: repr(item)))


def _optional_digest_payload(value: DigestRef | str | object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value.to_payload()
    if hasattr(value, "to_payload"):
        payload = value.to_payload()
        if isinstance(payload, str):
            return payload
    if isinstance(value, str):
        return DigestRef.parse(value).to_payload()
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return DigestRef.parse(getattr(value, "value")).to_payload()
    if hasattr(value, "manifest_digest"):
        manifest_digest = getattr(value, "manifest_digest")
        return _optional_digest_payload(manifest_digest)
    if hasattr(value, "records_manifest_digest"):
        records_manifest_digest = getattr(value, "records_manifest_digest")
        return _optional_digest_payload(records_manifest_digest)
    if hasattr(value, "ref"):
        return _optional_digest_payload(getattr(value, "ref"))
    raise TypeError(f"unsupported digest payload value: {type(value)!r}")


def _records_manifest_digest_payload(value: object | None) -> str | None:
    if value is None:
        return None
    return _optional_digest_payload(value)


def _ordered_extension_payload(value: object | None) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not hasattr(value, "payload_for_digest"):
        raise TypeError("ordered_extension must provide payload_for_digest()")
    payload = value.payload_for_digest()
    if not isinstance(payload, Mapping):
        raise TypeError("ordered_extension payload_for_digest() must return a mapping")
    return _mapping_payload(payload)


def _row_counts_payload(value: tuple[int | None, int | None] | None) -> tuple[int | None, int | None] | None:
    if value is None:
        return None
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError("row_counts must be a pair or None")
    return value


def _iter_table_fact_digests(
    table_fact_digests: Mapping[str, DigestRef | str] | Sequence[tuple[str, DigestRef | str]],
) -> tuple[tuple[str, DigestRef | str], ...]:
    if isinstance(table_fact_digests, Mapping):
        items = table_fact_digests.items()
    else:
        items = table_fact_digests
    normalized: list[tuple[str, DigestRef | str]] = []
    for table_name, digest_value in items:
        if not isinstance(table_name, str) or not table_name.strip():
            raise ValueError("table_fact_digests keys must be non-empty strings")
        normalized.append((table_name, digest_value))
    normalized.sort(key=lambda item: canonical_identifier(item[0]))
    return tuple(normalized)


__all__ = [
    "build_comparison_digest",
    "build_comparison_records_closure_digest",
    "build_comparison_table_fact_digest",
    "build_projection_logical_digest",
    "build_projection_logical_digest_from_parts",
    "build_projection_logical_digest_parts",
    "build_projection_schema_digest",
    "normalize_projection_row",
    "normalize_projection_rows",
]
