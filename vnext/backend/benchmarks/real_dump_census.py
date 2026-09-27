"""Read-only census over GATEWAY_REAL_DUMP_ROOT datasets (DC22, S1 kickoff).

Not imported by production code. Host-side only.
"""

from __future__ import annotations

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

_ZERO_DIGEST = DigestRef("sha256:" + "00" * 32)

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.composite_signal.contracts import present_composite_logic_source
from gateway_backend.capabilities.snapshot_materialization.compose import materialize_business_snapshot
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BusinessSnapshotMaterializationRequest,
    MaterializationPolicy,
    MaterializationStage,
    SqlSnapshotMaterializationRequest,
)
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
    XmlParseRequest,
    XmlSourceInput,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_access.xml import parse_xml
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.resolver import resolve_table_rule

_TIER_MAP = {
    "small_cut": ("t1", "a"),
    "small": ("t2", "b"),
    "medium": ("t3", "c"),
    "large": ("t4", "d"),
}
_VERSION_SUFFIX = re.compile(r"^(?P<tier>[^-]+)-(?P<idx>[12])$")
_CONTEXT = StagingInvocationContext(StagingNeverCancel())


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
    source_dir: str
    package_sha256: str
    package_bytes: int
    staging_status: str
    materialization_status: str
    table_count: int
    row_count_total: int
    storage_column_type_counts: dict[str, int]
    unknown_sql_types: list[str]
    json_columns: list[str]
    nullable_key_columns: list[str]
    tables_without_keys: list[str]
    version_manager_saved_time_type: str | None
    logics_xml_status: str
    logics_xml_event_count: int | None
    materialization_diagnostics: list[str]


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

    for parsed in parse_result.tables:
        descriptor = parsed.descriptor
        resolved = resolve_table_rule(
            ruleset,
            descriptor.canonical_name,
            primary_key_columns=descriptor.primary_key_canonical_names,
        )
        if resolved.decision.static_role.value == "SKIP":
            continue
        for column in descriptor.columns:
            spelling = column.sql_type.strip().upper()
            base = spelling.split("(")[0].split()[0]
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
        "storage_types": dict(storage_types),
        "unknown": sorted(unknown),
        "json_cols": sorted(json_cols),
        "nullable_keys": sorted(nullable_keys),
        "no_key": sorted(no_key),
        "vm_type": vm_type,
        "parse_result": parse_result,
        "context": context,
    }


def census_one(*, tier_name: str, engine_dir: Path, pair_of: str | None) -> DatasetCensus:
    idx_match = _VERSION_SUFFIX.match(engine_dir.name)
    assert idx_match is not None
    idx = idx_match.group("idx")
    tier_code, project_alias = _TIER_MAP[tier_name]
    version = "v1" if idx == "1" else "v2"
    dataset_id = _dataset_id(tier_name, idx)

    sql_bytes = (engine_dir / "sql" / "dbcfg.sql").read_bytes()
    xml_path = engine_dir / "comps" / "logic" / "logics.xml"
    xml_bytes = xml_path.read_bytes() if xml_path.is_file() else None
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
    parse_result = analysis["parse_result"]
    context = analysis["context"]
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

    sql_request_obj = SqlSnapshotMaterializationRequest(
        parse_result=parse_result,
        sql_source_digest=raw_blob_digest(sql_bytes),
        ruleset=ruleset,
        table_ruleset_version=ruleset.table_ruleset_version,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.DESCRIPTOR_ONLY,
        context=context,
        requested_tables=None,
        artifact_store=store,
    )
    business = materialize_business_snapshot(
        BusinessSnapshotMaterializationRequest(
            sql=sql_request_obj,
            logic=logic_source,
            xml=xml_parse,
        )
    )

    table_count = 0
    row_total = 0
    if business.summary is not None:
        table_count = business.summary.table_count
        row_total = business.summary.row_count_total

    return DatasetCensus(
        dataset_id=dataset_id,
        tier=tier_code,
        project_alias=project_alias,
        version=version,
        pair_of=pair_of,
        source_dir=str(engine_dir),
        package_sha256=package_sha256,
        package_bytes=len(package_bytes),
        staging_status=staging.status.value,
        materialization_status=business.status.value,
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
        materialization_diagnostics=[item.code.value for item in business.diagnostics[:32]],
    )


def build_datasets_json(censuses: list[DatasetCensus]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in censuses:
        records.append(
            {
                "dataset_id": item.dataset_id,
                "tier": item.tier,
                "project_alias": item.project_alias,
                "version": item.version,
                "pair_of": item.pair_of,
                "has_logics_xml": True,
                "files": [
                    {
                        "path": "package.tar.gz",
                        "bytes": item.package_bytes,
                        "sha256": item.package_sha256,
                    }
                ],
                "note": f"source={item.source_dir}",
            }
        )
    return records


def main() -> None:
    root = _dump_root()
    packages_dir = root / "packages"
    census_dir = root / "census"
    packages_dir.mkdir(parents=True, exist_ok=True)
    census_dir.mkdir(parents=True, exist_ok=True)

    engines = _discover_engine_dirs(root)
    censuses: list[DatasetCensus] = []
    for tier_name, engine_dir in engines:
        idx_match = _VERSION_SUFFIX.match(engine_dir.name)
        assert idx_match is not None
        idx = idx_match.group("idx")
        pair_of: str | None = None
        if idx == "2":
            pair_of = _dataset_id(tier_name, "1")
        item = census_one(tier_name=tier_name, engine_dir=engine_dir, pair_of=pair_of)
        censuses.append(item)
        (packages_dir / f"{item.dataset_id}.tar.gz").write_bytes(pack_tar_gz({
            REQUIRED_SQL_PATH: (engine_dir / "sql" / "dbcfg.sql").read_bytes(),
            **(
                {OPTIONAL_XML_PATH: (engine_dir / "comps" / "logic" / "logics.xml").read_bytes()}
                if (engine_dir / "comps" / "logic" / "logics.xml").is_file()
                else {}
            ),
        }))

    summary = {
        "datasets": [asdict(item) for item in censuses],
        "dc12_json_columns_present": any(item.json_columns for item in censuses),
        "dc15_unknown_sql_types": sorted({t for item in censuses for t in item.unknown_sql_types}),
    }
    (census_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    datasets_doc = {"datasets": build_datasets_json(censuses)}
    (root / "datasets.json").write_text(
        json.dumps(datasets_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"dataset_count": len(censuses), "census_dir": str(census_dir)}, indent=2))


if __name__ == "__main__":
    main()
