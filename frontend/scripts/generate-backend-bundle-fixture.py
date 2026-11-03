#!/usr/bin/env python3
"""Generate deterministic FE2 bundles through backend production code."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from gateway_backend.application.pair_pipeline import run_history_pair_pipeline, run_preview_pair_pipeline
from gateway_backend.application.preview_jobs import (
    _PAIR_BASELINE_TO_INITIAL,
    _PAIR_INITIAL_TO_MODIFIED,
    _unchanged_baseline_identity_table_set,
    surface_artifact_closure,
)
from gateway_backend.artifacts import InMemoryArtifactStore, artifact_ref_from_dict, put_with_built_ref
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION,
    BundleAssemblyInput,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleRefScope,
    assemble_bundle,
)
from gateway_backend.capabilities.comparison import BoundSnapshotInput
from gateway_backend.capabilities.composite_signal import present_composite_logic_source
from gateway_backend.capabilities.snapshot_materialization import (
    BusinessSnapshotMaterializationRequest,
    MaterializationPolicy,
    MaterializationStage,
    SqlSnapshotMaterializationRequest,
    materialize_business_snapshot,
)
from gateway_backend.capabilities.surface_assembly import (
    compute_surface_digest,
    validate_surface,
    validate_surface_artifacts,
)
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceProjectionRef
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    PARSER_INPUT_CONTRACT_VERSION,
    ParserInvocationContext,
    SqlParseRequest,
    SqlSourceInput,
    XmlParseRequest,
    XmlSourceInput,
)
from gateway_backend.capabilities.table_access import parse_xml
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_rules import (
    TABLE_RULESET_VERSION,
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
)
from gateway_backend.operations.worker import ExecutionControl
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value


BASELINE_SQL = """\
CREATE TABLE device (
  gid INT NOT NULL,
  dev_addr INT NOT NULL,
  description VARCHAR(128),
  PRIMARY KEY (dev_addr)
);
INSERT INTO device VALUES (1, 1, '线路保护装置 A'), (2, 2, '测控装置'), (4, 4, '故障录波装置'), (65532, 65532, '复合信号虚装置');
CREATE TABLE device_st (gid INT NOT NULL PRIMARY KEY, name VARCHAR(128) NOT NULL, dev_addr INT NOT NULL);
INSERT INTO device_st VALUES (8, 'Device 65532:复合测点', 65532);
CREATE TABLE keyless_demo (value VARCHAR(64) NULL);
INSERT INTO keyless_demo VALUES ('保留'), ('删除'), ('删除');
CREATE TABLE retired_table (id INT NOT NULL PRIMARY KEY, label VARCHAR(32));
INSERT INTO retired_table VALUES (1, '旧表');
CREATE TABLE schema_demo (id INT NOT NULL PRIMARY KEY, label VARCHAR(16));
INSERT INTO schema_demo VALUES (1, '原值');
CREATE TABLE b1_n1_iec104_syx_list (gid INT NULL, no INT NOT NULL, value VARCHAR(32) NULL);
INSERT INTO b1_n1_iec104_syx_list VALUES (1, 1, '遥信 A'), (NULL, 2, NULL), (2, 3, '遥信 B'), (NULL, 4, NULL);
CREATE TABLE b1_n1_iec104_yc_list (no INT NOT NULL, value VARCHAR(32) NULL);
INSERT INTO b1_n1_iec104_yc_list VALUES (1, '无稳定 gid');
CREATE TABLE version_manager (project_id VARCHAR(32) NOT NULL PRIMARY KEY, build VARCHAR(32), no INT);
INSERT INTO version_manager VALUES ('project-a', 'build-1', 1);
"""

INITIAL_SQL = """\
CREATE TABLE device (
  gid INT NOT NULL,
  dev_addr INT NOT NULL,
  description VARCHAR(128),
  PRIMARY KEY (dev_addr)
);
INSERT INTO device VALUES (1, 1, '线路保护装置 A'), (2, 2, '测控装置（升级）'), (3, 3, '直流屏'), (65532, 65532, '复合信号虚装置');
CREATE TABLE device_st (gid INT NOT NULL PRIMARY KEY, name VARCHAR(128) NOT NULL, dev_addr INT NOT NULL);
INSERT INTO device_st VALUES (8, 'Device 65532:复合测点', 65532);
CREATE TABLE keyless_demo (value VARCHAR(64) NULL);
INSERT INTO keyless_demo VALUES ('保留'), ('删除'), ('新增');
CREATE TABLE retired_table (id INT NOT NULL PRIMARY KEY, label VARCHAR(32));
INSERT INTO retired_table VALUES (1, '旧表');
CREATE TABLE schema_demo (id INT NOT NULL PRIMARY KEY, label VARCHAR(32), enabled TINYINT NULL);
INSERT INTO schema_demo VALUES (1, '初始值', 0);
CREATE TABLE b1_n1_iec104_syx_list (gid INT NULL, no INT NOT NULL, value VARCHAR(32) NULL);
INSERT INTO b1_n1_iec104_syx_list VALUES (2, 1, '遥信 B'), (1, 2, '遥信 A'), (NULL, 3, NULL);
CREATE TABLE b1_n1_iec104_yc_list (no INT NOT NULL, value VARCHAR(32) NULL);
INSERT INTO b1_n1_iec104_yc_list VALUES (1, '无稳定 gid');
CREATE TABLE version_manager (project_id VARCHAR(32) NOT NULL PRIMARY KEY, build VARCHAR(32), no INT);
INSERT INTO version_manager VALUES ('project-a', 'build-1', 1);
"""

MODIFIED_SQL = """\
CREATE TABLE device (
  gid INT NOT NULL,
  dev_addr INT NOT NULL,
  description VARCHAR(128),
  PRIMARY KEY (dev_addr)
);
INSERT INTO device VALUES (1, 1, '线路保护装置 A'), (2, 2, '测控装置（再次升级）'), (3, 3, '直流屏'), (65532, 65532, '复合信号虚装置');
CREATE TABLE device_st (gid INT NOT NULL PRIMARY KEY, name VARCHAR(128) NOT NULL, dev_addr INT NOT NULL);
INSERT INTO device_st VALUES (8, 'Device 65532:复合测点', 65532);
CREATE TABLE keyless_demo (value VARCHAR(64) NULL);
INSERT INTO keyless_demo VALUES ('保留'), ('新增'), ('新增');
CREATE TABLE schema_demo (id INT NOT NULL PRIMARY KEY, label VARCHAR(32), enabled TINYINT NULL, source VARCHAR(12) NULL);
INSERT INTO schema_demo VALUES (1, '最终值', 1, 'upload');
CREATE TABLE added_table (id INT NOT NULL PRIMARY KEY, label VARCHAR(32));
INSERT INTO added_table VALUES (9, '新表');
CREATE TABLE b1_n1_iec104_syx_list (gid INT NULL, no INT NOT NULL, value VARCHAR(32) NULL);
INSERT INTO b1_n1_iec104_syx_list VALUES (2, 1, '遥信 B'), (1, 2, '遥信 A'), (NULL, 3, NULL);
CREATE TABLE b1_n1_iec104_yc_list (no INT NOT NULL, value VARCHAR(32) NULL);
INSERT INTO b1_n1_iec104_yc_list VALUES (1, '无稳定 gid');
CREATE TABLE version_manager (project_id VARCHAR(32) NOT NULL PRIMARY KEY, build VARCHAR(32), no INT);
INSERT INTO version_manager VALUES ('project-a', 'build-1', 1);
"""

REPLACEMENT_BEFORE_SQL = """\
CREATE TABLE device (gid INT NOT NULL, dev_addr INT NOT NULL PRIMARY KEY, description VARCHAR(64));
INSERT INTO device VALUES (1, 1, '替换前装置'), (65532, 65532, '复合信号虚装置');
CREATE TABLE device_st (gid INT NOT NULL PRIMARY KEY, name VARCHAR(128) NOT NULL, dev_addr INT NOT NULL);
INSERT INTO device_st VALUES (8, 'Device 65532:复合测点', 65532);
CREATE TABLE version_manager (project_id VARCHAR(32) NOT NULL PRIMARY KEY, build VARCHAR(32), no INT);
INSERT INTO version_manager VALUES ('project-a', 'build-a', 1);
"""

REPLACEMENT_CURRENT_SQL = """\
CREATE TABLE device (gid INT NOT NULL, dev_addr INT NOT NULL PRIMARY KEY, description VARCHAR(64));
INSERT INTO device VALUES (2, 2, '替换后装置'), (65532, 65532, '复合信号虚装置');
CREATE TABLE device_st (gid INT NOT NULL PRIMARY KEY, name VARCHAR(128) NOT NULL, dev_addr INT NOT NULL);
INSERT INTO device_st VALUES (8, 'Device 65532:复合测点', 65532);
CREATE TABLE version_manager (project_id VARCHAR(32) NOT NULL PRIMARY KEY, build VARCHAR(32), no INT);
INSERT INTO version_manager VALUES ('project-b', 'build-b', 1);
"""
HISTORY_OPERATION_ID = "fe2a-history-fixture"
HISTORY_REF_IDS = ("fe2a-history-ref-0", "fe2a-history-ref-1", "fe2a-history-ref-2")


def _composite_logic(primary_value: str) -> str:
    return f"""<Logic_Set>
  <Express Name="Device 65532:复合测点" Operator_Type="|">
    <Express Name="嵌套命名表达式" Operator_Type="+">
      <Express Operator_Type="+">
        <Point Name="Device 1:线路电流"/>
        <Digital value="{primary_value}"/>
        <Express Operator_Type="+">
          <Digital value="2"/>
          <Point Name="Device 2:测量电压"/>
        </Express>
      </Express>
      <Express Operator_Type="*">
        <Digital value="3"/>
        <Express Operator_Type="*">
          <Point Name="Device 2:测量电压"/>
          <Digital value="4"/>
        </Express>
      </Express>
    </Express>
    <Express Operator_Type="|">
      <Point Name="Device 999:未映射测点"/>
      <Digital value="5"/>
    </Express>
    <Express Operator_Type=""><Digital value="6"/></Express>
    <Express Operator_Type="-"><Point Name="Device 1:线路电流"/></Express>
  </Express>
</Logic_Set>"""


LOGIC_BASELINE = _composite_logic("1")
LOGIC_INITIAL = _composite_logic("2")
LOGIC_MODIFIED = _composite_logic("3")


@dataclass(frozen=True)
class PairFixture:
    pair_id: str
    before_index: int
    current_index: int
    before: BoundSnapshotInput
    current: BoundSnapshotInput
    result: Any
    history: bool = False
    replacement: bool = False


def _materialize(sql: str, store: InMemoryArtifactStore, logic_xml: str) -> BoundSnapshotInput:
    raw = sql.encode("utf-8")
    digest = raw_blob_digest(raw)
    context = ParserInvocationContext(NeverCancel())
    parsed = parse_sql(
        SqlParseRequest(
            source=SqlSourceInput(
                document_content_digest=digest,
                sql_source_digest=digest,
                parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION,
                encoding="utf-8",
                source_size_bytes=len(raw),
            ),
            sql_utf8=raw,
            context=context,
        )
    )
    ruleset = migrated_table_ruleset_snapshot()
    sql_request = SqlSnapshotMaterializationRequest(
        parse_result=parsed,
        sql_source_digest=digest,
        ruleset=ruleset,
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=context,
        artifact_store=store,
    )
    xml_raw = logic_xml.encode("utf-8")
    xml_digest = raw_blob_digest(xml_raw)
    xml_request = XmlParseRequest(
        source=XmlSourceInput(
            document_content_digest=xml_digest,
            xml_source_digest=xml_digest,
            parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION,
            encoding="utf-8",
            source_size_bytes=len(xml_raw),
        ),
        xml_utf8=xml_raw,
        context=context,
    )
    logic = present_composite_logic_source(xml_raw)
    result = materialize_business_snapshot(
        BusinessSnapshotMaterializationRequest(
            sql=sql_request,
            logic=logic,
            xml=parse_xml(xml_request),
        )
    )
    if result.status.value != "COMPLETE" or result.snapshot is None or result.summary is None or result.table_set is None:
        raise RuntimeError("backend snapshot materialization failed: " + repr([item.message for item in result.diagnostics]))
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _pair(
    pair_id: str,
    view_id: str,
    before_index: int,
    current_index: int,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    store: InMemoryArtifactStore,
    *,
    history: bool = False,
    assess_identity: bool = True,
    identity_before_table_set=None,
    replacement: bool = False,
):
    ruleset = migrated_table_ruleset_snapshot()
    if history:
        result = run_history_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            store=store,
            control=ExecutionControl(),
            on_cancel=lambda: None,
            rule_set=comparison_rule_set(ruleset),
        )
    else:
        result = run_preview_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            store=store,
            control=ExecutionControl(),
            on_cancel=lambda: None,
            view_id=view_id,
            rule_set=comparison_rule_set(ruleset),
            assess_identity=assess_identity,
            identity_before_table_set=identity_before_table_set,
        )
    return PairFixture(pair_id, before_index, current_index, before, current, result, history, replacement)


def _attach_frontend_projections(
    fixture: PairFixture,
    store: InMemoryArtifactStore,
    navigation: dict[str, Any] | None,
    navigation_diagnostics: dict[str, Any] | None,
):
    source_surface = fixture.result.surface_result.surface
    if source_surface is None:
        raise RuntimeError("backend surface assembly returned no surface")
    projections = list(source_surface.projections)
    if navigation is not None:
        groups = navigation.get("groups")
        if not isinstance(groups, list):
            raise ValueError("business navigation input must contain a groups array")
        navigation_bytes = canonicalize_json_value(navigation)
        navigation_ref = put_with_built_ref(
            store,
            navigation_bytes,
            artifact_id="fixture-navigation-" + hashlib.sha256(navigation_bytes).hexdigest()[:32],
            media_type="application/json",
        )
        diagnostics_ref = None
        if navigation_diagnostics is not None:
            if not isinstance(navigation_diagnostics.get("diagnostics"), list) or not navigation_diagnostics["diagnostics"]:
                raise ValueError("navigation diagnostics document must contain at least one diagnostic")
            diagnostics_bytes = canonicalize_json_value(navigation_diagnostics)
            diagnostics_ref = put_with_built_ref(
                store,
                diagnostics_bytes,
                artifact_id="fixture-navigation-diagnostics-" + hashlib.sha256(diagnostics_bytes).hexdigest()[:32],
                media_type="application/json",
            )
        projection = SurfaceProjectionRef(
            projection_id="business-navigation",
            projection_kind="BUSINESS_NAVIGATION",
            projection_ref=navigation_ref,
            projection_digest=navigation_ref.raw_sha256,
            projection_summary=(("group_count", str(len(groups))),),
            diagnostics_ref=diagnostics_ref,
        )
        projections.append(projection)
    surface = replace(
        source_surface,
        projections=tuple(sorted(projections, key=lambda item: item.projection_id)),
        surface_digest=DigestRef("sha256:" + "00" * 32),
    )
    surface = replace(surface, surface_digest=compute_surface_digest(surface))
    validate_surface(surface)
    validate_surface_artifacts(surface, store)
    surface_result = replace(fixture.result.surface_result, surface=surface)
    closure = surface_artifact_closure(
        surface,
        fixture.pair_id,
        fixture.result.records_closure,
        before=fixture.before,
        current=fixture.current,
        include_all_tables=fixture.history,
    )
    return BundlePairInput(
        fixture.pair_id,
        fixture.before_index,
        fixture.current_index,
        surface_result,
        closure,
    )


def _write_member(root: Path, logical_path: str, data: bytes) -> Path:
    path = PurePosixPath(logical_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("backend emitted an invalid logical path: " + logical_path)
    destination = root.joinpath(*path.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return destination


def _risk_levels(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "risk_level" and isinstance(item, str):
                found.add(item)
            found.update(_risk_levels(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_risk_levels(item))
    return found


def _pair_projection_documents(
    fixture: PairFixture,
    navigation: dict[str, Any] | None,
    navigation_diagnostics: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if navigation is None:
        return None, None
    projected_navigation = json.loads(json.dumps(navigation))
    projected_diagnostics = json.loads(json.dumps(navigation_diagnostics)) if navigation_diagnostics is not None else None
    surface = fixture.result.surface_result.surface
    if surface is None:
        raise RuntimeError("backend surface assembly returned no surface")
    available_table_ids = {value for table in surface.tables for value in (table.table_id, table.table_name)}
    for group in projected_navigation.get("groups", []):
        items = []
        for item in group.get("items", []):
            item["tabs"] = [tab for tab in item.get("tabs", []) if tab.get("table_id") in available_table_ids]
            if item["tabs"]:
                items.append(item)
        group["items"] = items
    projected_navigation["groups"] = [group for group in projected_navigation.get("groups", []) if group["items"]]
    if fixture.pair_id == "initial_to_modified" or (fixture.history and fixture.current_index == 2):
        for group in projected_navigation.get("groups", []):
            for item in group.get("items", []):
                for tab in item.get("tabs", []):
                    if tab.get("table_id") == "device" and tab.get("row_filter") is not None:
                        tab["facts"] = {
                            "change_kind": "UNCHANGED",
                            "before_row_count": 1,
                            "current_row_count": 1,
                        }
    if fixture.replacement:
        for group in projected_navigation.get("groups", []):
            group["items"] = [item for item in group["items"] if item.get("item_key") == "device:table"]
            for item in group["items"]:
                for tab in item.get("tabs", []):
                    tab["row_filter"] = None
                    tab.pop("facts", None)
        projected_navigation["groups"] = [group for group in projected_navigation.get("groups", []) if group["items"]]
        projected_diagnostics = None
    return projected_navigation, projected_diagnostics


def _write_bundle(
    output_root: Path,
    name: str,
    store: InMemoryArtifactStore,
    inputs: list[tuple[str, str, BoundSnapshotInput]],
    fixtures: list[PairFixture],
    navigation: dict[str, Any] | None,
    navigation_diagnostics: dict[str, Any] | None,
) -> None:
    pair_inputs = tuple(
        _attach_frontend_projections(
            item,
            store,
            *_pair_projection_documents(item, navigation, navigation_diagnostics),
        )
        for item in fixtures
    )
    input_values = tuple(
        BundleInput(index, role, display, snapshot_digest=bound.snapshot.snapshot_digest)
        for index, (role, display, bound) in enumerate(inputs)
    )
    result = assemble_bundle(
        BundleAssemblyInput(
            bundle_contract_version=BUNDLE_CONTRACT_VERSION,
            bundle_profile=BundleProfile.MULTI_PAIR if len(pair_inputs) > 1 else BundleProfile.SINGLE_PAIR,
            inputs=input_values,
            pairs=pair_inputs,
            ref_scope=BundleRefScope.BUNDLE_RELATIVE,
        ),
        source_store=store,
    )
    if result.bundle is None or result.manifest_ref is None or result.artifact_closure_ref is None:
        raise RuntimeError("backend bundle assembly failed: " + repr(result.diagnostics))
    manifest_bytes = store.locate(result.manifest_ref)
    closure_bytes = store.locate(result.artifact_closure_ref)
    manifest = json.loads(manifest_bytes)
    closure = json.loads(closure_bytes)
    fixture_root = output_root / name
    fixture_root.mkdir(parents=True)
    (fixture_root / "manifest.json").write_bytes(manifest_bytes)
    (fixture_root / "artifact-closure.json").write_bytes(closure_bytes)
    semantic_entries = manifest["closure"]["entries"]
    physical_entries = manifest["closure_entries"]
    if len(semantic_entries) != len(physical_entries):
        raise RuntimeError("backend manifest semantic and physical closure counts differ")
    written: list[tuple[str, bytes]] = [("manifest.json", manifest_bytes), ("artifact-closure.json", closure_bytes)]
    if closure.get("bundle_digest") != manifest.get("bundle_digest"):
        raise RuntimeError("backend manifest and artifact closure bundle digests differ")
    for semantic, physical in zip(semantic_entries, physical_entries, strict=True):
        logical_path = semantic["logical_path"]
        if physical["logical_path"] != logical_path:
            raise RuntimeError("backend manifest closure order differs")
        ref = artifact_ref_from_dict(physical["artifact_ref"])
        data = store.locate(ref)
        _write_member(fixture_root, logical_path, data)
        written.append((logical_path, data))
    levels: set[str] = set()
    for logical_path, data in written:
        if logical_path.endswith(".json") and not logical_path.endswith("/business-navigation.json") and not logical_path.endswith("/business-navigation-diagnostics.json"):
            try:
                levels.update(_risk_levels(json.loads(data.decode("utf-8"))))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
    print("fixture=" + name)
    print("bundle_digest=" + manifest["bundle_digest"])
    print("closure_manifest_digest=" + manifest["closure_manifest_digest"])
    print("bundle_manifest_digest=" + closure["bundle_manifest_digest"])
    print("closure_product_count=" + str(len(semantic_entries)))
    print("risk_levels=" + (",".join(sorted(levels)) if levels else "none"))
    for logical_path, data in written:
        print("artifact_sha256=" + logical_path + " sha256:" + hashlib.sha256(data).hexdigest())


def _workbench_telemetry_sql(*, modified: bool) -> str:
    deleted = {9, 22, 37, 54, 68, 83}
    inserted_after = {7, 21, 36, 53, 67, 82}
    changed = {5, 19, 35, 51, 70, 90}
    rows: list[tuple[int, int, str, int]] = []
    if not modified:
        for gid in range(1, 91):
            rows.append((gid, gid, f"测点-{gid:03d}", gid * 137))
    else:
        position = 0
        for gid in range(1, 91):
            if gid not in deleted:
                position += 1
                value = gid * 137 + (425 if gid in changed else 0)
                rows.append((gid, position, f"测点-{gid:03d}", value))
            if gid in inserted_after:
                position += 1
                new_gid = 100 + gid
                rows.append((new_gid, position, f"新增测点-{gid:03d}", new_gid * 113))
    values = ",\n".join(
        f"({gid}, {position}, '{name}', {value})"
        for gid, position, name, value in rows
    )
    return "CREATE TABLE b1_n1_iec104_yc_list (gid INT NOT NULL, no INT NOT NULL, point_name VARCHAR(64) NOT NULL, value BIGINT NOT NULL);\nINSERT INTO b1_n1_iec104_yc_list VALUES\n" + values + ";\n"


def _generate_workbench_fixture(output_root: Path, navigation_path: Path) -> None:
    navigation = json.loads(navigation_path.read_bytes())
    store = InMemoryArtifactStore()
    before = _materialize(_workbench_telemetry_sql(modified=False), store, "<Logic_Set />")
    current = _materialize(_workbench_telemetry_sql(modified=True), store, "<Logic_Set />")
    fixture = _pair(
        _PAIR_INITIAL_TO_MODIFIED,
        _PAIR_INITIAL_TO_MODIFIED,
        0,
        1,
        before,
        current,
        store,
        assess_identity=False,
    )
    _write_bundle(
        output_root,
        "preview-workbench-normal",
        store,
        [("baseline", "当前基线", before), ("modified", "上传组态", current)],
        [fixture],
        navigation,
        None,
    )


def generate(output_root: Path, navigation_path: Path, diagnostics_path: Path, workbench_navigation_path: Path | None = None) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("output directory must be empty: " + str(output_root))
    output_root.mkdir(parents=True, exist_ok=True)
    navigation = json.loads(navigation_path.read_bytes())
    diagnostics = json.loads(diagnostics_path.read_bytes())

    full_store = InMemoryArtifactStore()
    baseline = _materialize(BASELINE_SQL, full_store, LOGIC_BASELINE)
    initial = _materialize(INITIAL_SQL, full_store, LOGIC_INITIAL)
    modified = _materialize(MODIFIED_SQL, full_store, LOGIC_MODIFIED)
    full_fixtures = [
        _pair(
            _PAIR_BASELINE_TO_INITIAL,
            _PAIR_INITIAL_TO_MODIFIED,
            0,
            1,
            baseline,
            initial,
            full_store,
            assess_identity=True,
            identity_before_table_set=_unchanged_baseline_identity_table_set(baseline, initial),
        ),
        _pair(
            _PAIR_INITIAL_TO_MODIFIED,
            _PAIR_INITIAL_TO_MODIFIED,
            1,
            2,
            initial,
            modified,
            full_store,
            assess_identity=True,
        ),
    ]
    _write_bundle(
        output_root,
        "preview-full",
        full_store,
        [("baseline", "Baseline", baseline), ("initial", "Initial", initial), ("modified", "Modified", modified)],
        full_fixtures,
        navigation,
        diagnostics,
    )

    modified_store = InMemoryArtifactStore()
    modified_before = _materialize(BASELINE_SQL, modified_store, LOGIC_BASELINE)
    modified_current = _materialize(MODIFIED_SQL, modified_store, LOGIC_MODIFIED)
    _write_bundle(
        output_root,
        "preview-modified-only",
        modified_store,
        [("baseline", "Baseline", modified_before), ("modified", "Modified", modified_current)],
        [
            _pair(
                _PAIR_INITIAL_TO_MODIFIED,
                _PAIR_INITIAL_TO_MODIFIED,
                0,
                1,
                modified_before,
                modified_current,
                modified_store,
                assess_identity=True,
                identity_before_table_set=_unchanged_baseline_identity_table_set(modified_before, modified_current),
            )
        ],
        navigation,
        diagnostics,
    )

    replacement_store = InMemoryArtifactStore()
    replacement_before = _materialize(REPLACEMENT_BEFORE_SQL, replacement_store, LOGIC_BASELINE)
    replacement_current = _materialize(REPLACEMENT_CURRENT_SQL, replacement_store, LOGIC_MODIFIED)
    _write_bundle(
        output_root,
        "preview-replacement",
        replacement_store,
        [("baseline", "Baseline", replacement_before), ("modified", "Modified", replacement_current)],
        [
            _pair(
                _PAIR_INITIAL_TO_MODIFIED,
                _PAIR_INITIAL_TO_MODIFIED,
                0,
                1,
                replacement_before,
                replacement_current,
                replacement_store,
                assess_identity=True,
                identity_before_table_set=_unchanged_baseline_identity_table_set(replacement_before, replacement_current),
                replacement=True,
            )
        ],
        navigation,
        diagnostics,
    )

    history_store = InMemoryArtifactStore()
    history_nodes = [
        _materialize(BASELINE_SQL, history_store, LOGIC_BASELINE),
        _materialize(INITIAL_SQL, history_store, LOGIC_INITIAL),
        _materialize(MODIFIED_SQL, history_store, LOGIC_MODIFIED),
    ]
    history_fixtures = [
        _pair(f"{HISTORY_OPERATION_ID}-p0", "", 0, 1, history_nodes[0], history_nodes[1], history_store, history=True),
        _pair(f"{HISTORY_OPERATION_ID}-p1", "", 1, 2, history_nodes[1], history_nodes[2], history_store, history=True),
    ]
    _write_bundle(
        output_root,
        "history-three-nodes",
        history_store,
        [(ref_id, f"node-{index}", node) for index, (ref_id, node) in enumerate(zip(HISTORY_REF_IDS, history_nodes, strict=True))],
        history_fixtures,
        navigation,
        diagnostics,
    )

    fallback_store = InMemoryArtifactStore()
    fallback_before = _materialize(BASELINE_SQL, fallback_store, LOGIC_BASELINE)
    fallback_current = _materialize(MODIFIED_SQL, fallback_store, LOGIC_MODIFIED)
    _write_bundle(
        output_root,
        "preview-no-navigation",
        fallback_store,
        [("baseline", "Baseline", fallback_before), ("modified", "Modified", fallback_current)],
        [
            _pair(
                _PAIR_INITIAL_TO_MODIFIED,
                _PAIR_INITIAL_TO_MODIFIED,
                0,
                1,
                fallback_before,
                fallback_current,
                fallback_store,
                assess_identity=True,
                identity_before_table_set=_unchanged_baseline_identity_table_set(fallback_before, fallback_current),
            )
        ],
        None,
        None,
    )

    if workbench_navigation_path is not None:
        _generate_workbench_fixture(output_root, workbench_navigation_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--navigation", type=Path, required=True)
    parser.add_argument("--navigation-diagnostics", type=Path, required=True)
    parser.add_argument("--workbench-navigation", type=Path)
    arguments = parser.parse_args()
    generate(arguments.output_root, arguments.navigation, arguments.navigation_diagnostics, arguments.workbench_navigation)


if __name__ == "__main__":
    main()
