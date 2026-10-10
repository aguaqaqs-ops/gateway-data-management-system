"""Read-only census over GATEWAY_REAL_DUMP_ROOT datasets (DC22, G2 update).

Not imported by production code. Host-side only.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.composite_signal.contracts import present_composite_logic_source
from gateway_backend.capabilities.snapshot_materialization.compose import materialize_business_snapshot
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BusinessSnapshotMaterializationRequest,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    MaterializationStage,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SqlSnapshotMaterializationRequest,
    SnapshotTableSet,
)
from gateway_backend.capabilities.snapshot_materialization.materialize import materialize_sql_snapshot
from gateway_backend.capabilities.source_package_staging.contracts import (
    OPTIONAL_XML_PATH,
    NeverCancel as StagingNeverCancel,
    PackageKind,
    REQUIRED_SQL_PATH,
    SourcePackageInput,
    StagingInvocationContext,
    StagingTransport,
)
from gateway_backend.capabilities.source_package_staging.staging import stage_source_package
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
    SqlLogicalType,
    SqlParseRequest,
    SqlSourceInput,
    XmlEventKind,
    XmlParseRequest,
    XmlSourceInput,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_access.xml import parse_xml
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.resolver import resolve_table_rule
from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy, TableStaticRole
from gateway_backend.capabilities.storage_projection.view import StorageViewError, derive_storage_rule_view
from gateway_backend.capabilities.table_rules.contracts import canonicalize_rule_identifier
from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableDescriptor
from gateway_backend.capabilities.table_access.contracts import SourceRow

_ZERO_DIGEST = DigestRef("sha256:" + "00" * 32)

_TIER_MAP = {
    "small_cut": ("t1", "a"),
    "small": ("t2", "b"),
    "medium": ("t3", "c"),
    "large": ("t4", "d"),
}
_VERSION_SUFFIX = re.compile(r"^(?P<tier>[^-]+)-(?P<idx>[12])$")
_CONTEXT = StagingInvocationContext(StagingNeverCancel())
_LOGICS_XML_REL = Path("comps") / "logic" / "logics.xml"


def _dump_root() -> Path:
    raw = os.environ.get("GATEWAY_REAL_DUMP_ROOT", "").strip()
    if not raw:
        raise SystemExit("GATEWAY_REAL_DUMP_ROOT must be set")
    root = Path(raw)
    if not root.is_dir():
        raise SystemExit(f"GATEWAY_REAL_DUMP_ROOT is not a directory: {root}")
    return root


def pack_tar_gz(members: dict[str, bytes], *, mtime: int = 0) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mtime = mtime
            archive.addfile(info, io.BytesIO(payload))
    return gzip.compress(tar_buffer.getvalue())


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _storage_column_type_key(sql_type: str) -> str:
    """Keep UNSIGNED distinct while dropping type widths and enum values."""

    words = re.sub(r"\([^)]*\)", "", sql_type.strip().upper()).split()
    if not words:
        return "UNKNOWN"
    base = words[0]
    if "UNSIGNED" in words[1:]:
        return f"{base} UNSIGNED"
    return base


def _discover_engine_dirs(root: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for tier_name in _TIER_MAP:
        tier_dir = root / tier_name
        if not tier_dir.is_dir():
            continue
        for child in sorted(tier_dir.iterdir()):
            if not child.is_dir():
                continue
            match = _VERSION_SUFFIX.match(child.name)
            if match is None or match.group("tier") != tier_name:
                continue
            sql_path = child / "sql" / "dbcfg.sql"
            if not sql_path.is_file():
                continue
            found.append((tier_name, child))
    return found


def _dataset_id(tier_name: str, idx: str) -> str:
    tier_code, project_alias = _TIER_MAP[tier_name]
    version = "v1" if idx == "1" else "v2"
    return f"rd-{tier_code}-{project_alias}-{version}"


@dataclass(frozen=True)
class DatasetCensus:
    dataset_id: str
    tier: str
    project_alias: str
    version: str
    pair_of: str | None
    package_sha256: str
    package_bytes: int
    staging_status: str
    materialization_status: str
    source_ddl_table_count: int
    table_count: int | None
    row_count_total: int | None
    storage_column_type_counts: dict[str, int]
    unknown_sql_types: list[str]
    json_columns: list[str]
    nullable_key_columns: list[str]
    tables_without_keys: list[str]
    version_manager_saved_time_type: str | None
    logics_xml_status: str
    logics_xml_event_count: int | None
    logics_xml_max_depth: int | None
    composite_stage_status: str
    materialization_diagnostics: list[str]
    materialization_diagnostic_details: list[dict[str, str]]
    role_table_counts: dict[str, int]
    has_logics_xml: bool
    key_scan_source: str
    duplicate_key_scan_status: str
    duplicate_key_extra_rows: int
    duplicate_key_exact_extra_rows: int
    duplicate_key_conflicting_extra_rows: int
    duplicate_key_by_table: dict[str, int]
    duplicate_key_details_by_table: dict[str, dict[str, Any]]
    duplicate_key_scanned_table_count: int
    duplicate_key_rule_skipped_table_count: int
    duplicate_key_scan_unresolved_tables: list[str]
    duplicate_key_reader_unavailable_tables: list[str]
    effective_key_scan_status: str
    effective_key_tables: list[str]
    effective_keyless_tables: list[str]
    effective_key_unresolved_tables: list[str]


def _load_pairing_map(root: Path) -> dict[str, str]:
    path = root / "dataset_pairing.json"
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    pairings = document.get("pairings", document)
    if not isinstance(pairings, dict):
        raise SystemExit("dataset_pairing.json must be a JSON object or contain a pairings object")
    return {str(key): str(value) for key, value in pairings.items()}


def _production_sql_parse_report(sql_bytes: bytes) -> dict[str, Any]:
    context = ParserInvocationContext(NeverCancel())
    parse_result = parse_sql(
        SqlParseRequest(
            source=SqlSourceInput(
                document_content_digest=_ZERO_DIGEST,
                sql_source_digest=raw_blob_digest(sql_bytes),
                parser_input_contract_version=1,
                encoding="utf-8",
                source_size_bytes=len(sql_bytes),
            ),
            sql_utf8=sql_bytes,
            context=context,
        )
    )
    report: dict[str, Any] = {"status": parse_result.status.value}
    if parse_result.diagnostics:
        first = parse_result.diagnostics[0]
        report["code"] = first.code.value
        report["message"] = first.message
    return report


def _analyze_parse(sql_bytes: bytes) -> dict[str, Any]:
    context = ParserInvocationContext(NeverCancel())
    parse_result = parse_sql(
        SqlParseRequest(
            source=SqlSourceInput(
                document_content_digest=_ZERO_DIGEST,
                sql_source_digest=raw_blob_digest(sql_bytes),
                parser_input_contract_version=1,
                encoding="utf-8",
                source_size_bytes=len(sql_bytes),
            ),
            sql_utf8=sql_bytes,
            context=context,
        )
    )
    ruleset = migrated_table_ruleset_snapshot()
    storage_types: Counter[str] = Counter()
    unknown: set[str] = set()
    json_cols: list[str] = []
    nullable_keys: list[str] = []
    no_key: list[str] = []
    vm_type: str | None = None
    role_counts: Counter[str] = Counter()

    for parsed in parse_result.tables:
        descriptor = parsed.descriptor
        resolved = resolve_table_rule(
            ruleset,
            descriptor.canonical_name,
            primary_key_columns=descriptor.primary_key_canonical_names,
        )
        role_counts[resolved.decision.static_role.value] += 1
        if resolved.decision.static_role.value == "SKIP":
            continue
        for column in descriptor.columns:
            base = _storage_column_type_key(column.sql_type)
            storage_types[base] += 1
            if column.logical_type is SqlLogicalType.UNKNOWN:
                unknown.add(column.sql_type)
            if column.logical_type is SqlLogicalType.JSON:
                json_cols.append(f"{descriptor.canonical_name}.{column.canonical_name}")
        if descriptor.canonical_name == "version_manager":
            for column in descriptor.columns:
                if column.canonical_name == "saved_time":
                    vm_type = column.sql_type
        if not descriptor.primary_key_canonical_names:
            no_key.append(descriptor.canonical_name)
        else:
            key_names = set(descriptor.primary_key_canonical_names)
            for column in descriptor.columns:
                if column.canonical_name in key_names and column.nullable:
                    nullable_keys.append(f"{descriptor.canonical_name}.{column.canonical_name}")

    return {
        "ddl_table_count": len(parse_result.tables),
        "storage_types": dict(storage_types),
        "unknown": sorted(unknown),
        "json_cols": sorted(json_cols),
        "nullable_keys": sorted(nullable_keys),
        "no_key": sorted(no_key),
        "vm_type": vm_type,
        "role_counts": dict(role_counts),
        "parse_result": parse_result,
        "context": context,
    }


def _sql_snapshot_request(
    analysis: dict[str, Any],
    *,
    sql_bytes: bytes,
    ruleset: Any,
    artifact_store: InMemoryArtifactStore,
    diagnostic_mode: bool,
) -> SqlSnapshotMaterializationRequest:
    return SqlSnapshotMaterializationRequest(
        parse_result=analysis["parse_result"],
        sql_source_digest=raw_blob_digest(sql_bytes),
        ruleset=ruleset,
        table_ruleset_version=ruleset.table_ruleset_version,
        materialization_stage=MaterializationStage.FINAL,
        policy=(
            MaterializationPolicy.READERS_REQUIRED
            if diagnostic_mode
            else MaterializationPolicy.DESCRIPTOR_ONLY
        ),
        context=analysis["context"],
        requested_tables=None,
        artifact_store=artifact_store,
    )


def _column_index_by_name(descriptor: SnapshotTableDescriptor) -> dict[str, int]:
    return {
        canonicalize_rule_identifier(column.name): index
        for index, column in enumerate(descriptor.columns)
    }


def _row_key_fingerprint(row: SourceRow, key_indexes: tuple[int, ...]) -> tuple[str, ...]:
    return tuple(repr(row[index]) for index in key_indexes)


def _row_fingerprint(row: SourceRow) -> bytes:
    return hashlib.sha256(repr(row).encode("utf-8")).digest()


def _xml_max_depth(events: tuple[Any, ...]) -> int:
    depth = 0
    maximum = 0
    for event in events:
        if event.kind is XmlEventKind.START_ELEMENT:
            depth += 1
            maximum = max(maximum, depth)
        elif event.kind is XmlEventKind.END_ELEMENT:
            depth -= 1
    return maximum


def _composite_stage_status(
    business: SnapshotMaterializationResult,
    xml_parse: Any,
) -> str:
    if business.status is SnapshotMaterializationStatus.COMPLETE:
        return "COMPLETE"
    if xml_parse is not None and xml_parse.status.value == "FAILED":
        return "FAILED"
    if any(
        item.code is MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED
        for item in business.diagnostics
    ):
        return "FAILED"
    return "NOT_REACHED"


@dataclass(frozen=True)
class KeyScanStats:
    duplicate_by_table: dict[str, int]
    duplicate_extra_rows: int
    exact_duplicate_extra_rows: int
    conflicting_extra_rows: int
    duplicate_details_by_table: dict[str, dict[str, Any]]
    unresolved_tables: list[str]
    effective_key_tables: list[str]
    effective_keyless_tables: list[str]
    scanned_table_count: int
    rule_skipped_table_count: int
    reader_unavailable_tables: list[str]
    duplicate_scan_status: str
    effective_key_scan_status: str


def _duplicate_and_effective_key_stats(
    *,
    table_set: SnapshotTableSet | None,
    ruleset: Any,
    diagnostic_mode: bool,
    materialization_complete: bool,
) -> KeyScanStats:
    if not diagnostic_mode:
        return KeyScanStats({}, 0, 0, 0, {}, [], [], [], 0, 0, [], "not_run", "not_run")
    if table_set is None:
        return KeyScanStats(
            {}, 0, 0, 0, {}, [], [], [], 0, 0, [],
            "materialization_unavailable", "materialization_unavailable"
        )
    if not materialization_complete:
        return KeyScanStats(
            {}, 0, 0, 0, {}, [], [], [], 0, 0, [],
            "materialization_incomplete", "materialization_incomplete"
        )
    duplicate_by_table: dict[str, int] = {}
    extra_rows = 0
    exact_duplicate_extra_rows = 0
    conflicting_extra_rows = 0
    duplicate_details_by_table: dict[str, dict[str, Any]] = {}
    unresolved: list[str] = []
    effective_key_tables: list[str] = []
    effective_keyless_tables: list[str] = []
    rule_skipped_table_count = 0
    reader_unavailable: list[str] = []
    scanned_table_count = 0
    for table in table_set.tables:
        descriptor = table.descriptor
        try:
            resolved = resolve_table_rule(
                ruleset,
                descriptor.table_name,
                primary_key_columns=descriptor.primary_key_columns,
            )
        except ValueError:
            unresolved.append(descriptor.table_name)
            continue
        if resolved.record.static_role is TableStaticRole.SKIP:
            rule_skipped_table_count += 1
            continue
        try:
            view = derive_storage_rule_view(resolved.record, descriptor)
        except StorageViewError:
            unresolved.append(descriptor.table_name)
            continue
        if view is None:
            effective_keyless_tables.append(descriptor.table_name)
            continue
        if not view.canonical_key_columns:
            effective_keyless_tables.append(descriptor.table_name)
            continue
        by_name = _column_index_by_name(descriptor)
        try:
            key_indexes = tuple(by_name[name] for name in view.canonical_key_columns)
        except KeyError:
            unresolved.append(descriptor.table_name)
            continue
        effective_key_tables.append(descriptor.table_name)
        if table.reader is None:
            reader_unavailable.append(descriptor.table_name)
            continue
        seen: dict[tuple[str, ...], Counter[bytes]] = {}
        for row in table.reader.iter_rows():
            key = _row_key_fingerprint(row, key_indexes)
            seen.setdefault(key, Counter())[_row_fingerprint(row)] += 1
        scanned_table_count += 1
        duplicate_rows = 0
        table_exact_extra_rows = 0
        table_conflicting_extra_rows = 0
        for variants in seen.values():
            row_count = sum(variants.values())
            if row_count <= 1:
                continue
            duplicate_rows += row_count - 1
            table_exact_extra_rows += sum(count - 1 for count in variants.values())
            table_conflicting_extra_rows += len(variants) - 1
        if duplicate_rows:
            duplicate_by_table[descriptor.table_name] = duplicate_rows
            extra_rows += duplicate_rows
            exact_duplicate_extra_rows += table_exact_extra_rows
            conflicting_extra_rows += table_conflicting_extra_rows
            key_source = (
                "EXPLICIT_RULE"
                if view.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT
                else "DDL_PRIMARY_KEY"
            )
            duplicate_details_by_table[descriptor.table_name] = {
                "key_columns": list(view.canonical_key_columns),
                "key_source": key_source,
                "exact_duplicate_extra_rows": table_exact_extra_rows,
                "conflicting_extra_rows": table_conflicting_extra_rows,
            }
    key_scan_status = "complete" if not unresolved else "partial"
    duplicate_scan_status = (
        "complete" if not unresolved and not reader_unavailable else "partial"
    )
    return KeyScanStats(
        duplicate_by_table,
        extra_rows,
        exact_duplicate_extra_rows,
        conflicting_extra_rows,
        duplicate_details_by_table,
        sorted(set(unresolved)),
        sorted(effective_key_tables),
        sorted(effective_keyless_tables),
        scanned_table_count,
        rule_skipped_table_count,
        sorted(reader_unavailable),
        duplicate_scan_status,
        key_scan_status,
    )


def _sql_scan_source_after_composite_failure(
    business: SnapshotMaterializationResult,
    sql_request: SqlSnapshotMaterializationRequest,
    *,
    diagnostic_mode: bool,
) -> tuple[SnapshotTableSet | None, bool, str]:
    """Keep SQL census available when only the derived composite stage fails."""

    if not diagnostic_mode or business.status is not SnapshotMaterializationStatus.FAILED:
        return (
            business.table_set,
            business.status is SnapshotMaterializationStatus.COMPLETE,
            "business_snapshot",
        )
    if not any(
        item.code is MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED
        for item in business.diagnostics
    ):
        return None, False, "business_snapshot_unavailable"

    sql_result = materialize_sql_snapshot(sql_request)
    if (
        sql_result.status is SnapshotMaterializationStatus.COMPLETE
        and sql_result.table_set is not None
    ):
        return sql_result.table_set, True, "sql_snapshot_after_composite_failure"
    return None, False, "sql_snapshot_after_composite_failure_unavailable"


def census_one(
    *,
    tier_name: str,
    engine_dir: Path,
    pair_of: str | None,
    diagnostic_mode: bool,
) -> DatasetCensus:
    idx_match = _VERSION_SUFFIX.match(engine_dir.name)
    assert idx_match is not None
    idx = idx_match.group("idx")
    tier_code, project_alias = _TIER_MAP[tier_name]
    version = "v1" if idx == "1" else "v2"
    dataset_id = _dataset_id(tier_name, idx)

    sql_bytes = (engine_dir / "sql" / "dbcfg.sql").read_bytes()
    xml_path = engine_dir / _LOGICS_XML_REL
    has_logics_xml = xml_path.is_file()
    xml_bytes = xml_path.read_bytes() if has_logics_xml else None
    members: dict[str, bytes] = {REQUIRED_SQL_PATH: sql_bytes}
    if xml_bytes is not None:
        members[OPTIONAL_XML_PATH] = xml_bytes
    package_bytes = pack_tar_gz(members)
    package_sha256 = _sha256_bytes(package_bytes)

    store = InMemoryArtifactStore()
    staging = stage_source_package(
        SourcePackageInput(
            package_kind=PackageKind.TAR_GZ,
            transport=StagingTransport.IDENTITY,
            context=_CONTEXT,
            payload=package_bytes,
        ),
        store,
    )

    analysis = _analyze_parse(sql_bytes)
    ruleset = migrated_table_ruleset_snapshot()

    logics_status = "absent"
    logics_events: int | None = None
    xml_parse = None
    logic_source = present_composite_logic_source(xml_bytes or b"<Logic_Set></Logic_Set>")
    if xml_bytes is not None:
        xml_parse = parse_xml(
            XmlParseRequest(
                source=XmlSourceInput(
                    document_content_digest=_ZERO_DIGEST,
                    xml_source_digest=raw_blob_digest(xml_bytes),
                    parser_input_contract_version=1,
                    encoding="utf-8",
                    source_size_bytes=len(xml_bytes),
                ),
                xml_utf8=xml_bytes,
                context=ParserInvocationContext(NeverCancel()),
            )
        )
        logics_status = xml_parse.status.value.lower()
        if xml_parse.status.value == "COMPLETE":
            logics_events = len(xml_parse.events)

    sql_request_obj = _sql_snapshot_request(
        analysis,
        sql_bytes=sql_bytes,
        ruleset=ruleset,
        artifact_store=store,
        diagnostic_mode=diagnostic_mode,
    )
    business = materialize_business_snapshot(
        BusinessSnapshotMaterializationRequest(
            sql=sql_request_obj,
            logic=logic_source,
            xml=xml_parse,
        )
    )

    table_count: int | None = None
    row_total: int | None = None
    if business.summary is not None:
        table_count = business.summary.table_count
        row_total = business.summary.row_count_total

    scan_sql_request = sql_request_obj
    if (
        diagnostic_mode
        and business.status is SnapshotMaterializationStatus.FAILED
        and any(
            item.code is MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED
            for item in business.diagnostics
        )
    ):
        fallback_analysis = _analyze_parse(sql_bytes)
        scan_sql_request = _sql_snapshot_request(
            fallback_analysis,
            sql_bytes=sql_bytes,
            ruleset=ruleset,
            artifact_store=InMemoryArtifactStore(),
            diagnostic_mode=True,
        )
    scan_table_set, scan_complete, key_scan_source = _sql_scan_source_after_composite_failure(
        business,
        scan_sql_request,
        diagnostic_mode=diagnostic_mode,
    )
    key_scan = _duplicate_and_effective_key_stats(
        table_set=scan_table_set,
        ruleset=ruleset,
        diagnostic_mode=diagnostic_mode,
        materialization_complete=scan_complete,
    )

    return DatasetCensus(
        dataset_id=dataset_id,
        tier=tier_code,
        project_alias=project_alias,
        version=version,
        pair_of=pair_of,
        package_sha256=package_sha256,
        package_bytes=len(package_bytes),
        staging_status=staging.status.value,
        materialization_status=business.status.value,
        source_ddl_table_count=analysis["ddl_table_count"],
        table_count=table_count,
        row_count_total=row_total,
        storage_column_type_counts=analysis["storage_types"],
        unknown_sql_types=analysis["unknown"],
        json_columns=analysis["json_cols"],
        nullable_key_columns=analysis["nullable_keys"],
        tables_without_keys=analysis["no_key"],
        version_manager_saved_time_type=analysis["vm_type"],
        logics_xml_status=logics_status,
        logics_xml_event_count=logics_events,
        logics_xml_max_depth=(
            _xml_max_depth(xml_parse.events)
            if xml_parse is not None and xml_parse.status.value == "COMPLETE"
            else None
        ),
        composite_stage_status=_composite_stage_status(business, xml_parse),
        materialization_diagnostics=[item.code.value for item in business.diagnostics],
        materialization_diagnostic_details=[
            {
                key: value
                for key, value in {
                    "code": item.code.value,
                    "message": item.message,
                    "table": item.table or "",
                }.items()
                if value
            }
            for item in business.diagnostics
        ],
        role_table_counts=analysis["role_counts"],
        has_logics_xml=has_logics_xml,
        key_scan_source=key_scan_source,
        duplicate_key_scan_status=key_scan.duplicate_scan_status,
        duplicate_key_extra_rows=key_scan.duplicate_extra_rows,
        duplicate_key_exact_extra_rows=key_scan.exact_duplicate_extra_rows,
        duplicate_key_conflicting_extra_rows=key_scan.conflicting_extra_rows,
        duplicate_key_by_table=key_scan.duplicate_by_table,
        duplicate_key_details_by_table=key_scan.duplicate_details_by_table,
        duplicate_key_scanned_table_count=key_scan.scanned_table_count,
        duplicate_key_rule_skipped_table_count=key_scan.rule_skipped_table_count,
        duplicate_key_scan_unresolved_tables=key_scan.unresolved_tables,
        duplicate_key_reader_unavailable_tables=key_scan.reader_unavailable_tables,
        effective_key_scan_status=key_scan.effective_key_scan_status,
        effective_key_tables=key_scan.effective_key_tables,
        effective_keyless_tables=key_scan.effective_keyless_tables,
        effective_key_unresolved_tables=key_scan.unresolved_tables,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Real dump structural census (host-side only).")
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Use READERS_REQUIRED materialization to compute read-only key statistics.",
    )
    args = parser.parse_args()
    diagnostic_mode = bool(args.diagnostic)

    root = _dump_root()
    census_dir = root / "census"
    census_dir.mkdir(parents=True, exist_ok=True)

    engines = _discover_engine_dirs(root)
    pairing_map = _load_pairing_map(root)
    production_reports: list[dict[str, Any]] = []
    censuses: list[DatasetCensus] = []
    for tier_name, engine_dir in engines:
        idx_match = _VERSION_SUFFIX.match(engine_dir.name)
        assert idx_match is not None
        idx = idx_match.group("idx")
        dataset_id = _dataset_id(tier_name, idx)
        pair_of = pairing_map.get(dataset_id)
        if pair_of is None and idx == "2":
            pair_of = _dataset_id(tier_name, "1")
        sql_bytes = (engine_dir / "sql" / "dbcfg.sql").read_bytes()
        production_reports.append(
            {
                "dataset_id": dataset_id,
                "sql_parse": _production_sql_parse_report(sql_bytes),
            }
        )
        item = census_one(
            tier_name=tier_name,
            engine_dir=engine_dir,
            pair_of=pair_of,
            diagnostic_mode=diagnostic_mode,
        )
        censuses.append(item)

    summary = {
        "diagnostic_mode": diagnostic_mode,
        "parser_production_path": production_reports,
        "datasets": [asdict(item) for item in censuses],
        "dc12_json_columns_present": any(item.json_columns for item in censuses),
        "dc15_unknown_sql_types": sorted({t for item in censuses for t in item.unknown_sql_types}),
        "duplicate_key_extra_rows_total": sum(item.duplicate_key_extra_rows for item in censuses),
        "duplicate_key_exact_extra_rows_total": sum(
            item.duplicate_key_exact_extra_rows for item in censuses
        ),
        "duplicate_key_conflicting_extra_rows_total": sum(
            item.duplicate_key_conflicting_extra_rows for item in censuses
        ),
        "datasets_with_duplicate_keys": sorted(
            item.dataset_id for item in censuses if item.duplicate_key_by_table
        ),
    }
    summary_path = census_dir / (
        "summary-diagnostic.json" if diagnostic_mode else "summary-production.json"
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"dataset_count": len(censuses), "summary_file": summary_path.name}, indent=2))


if __name__ == "__main__":
    main()
