"""Acceptance consumer boundaries with owning producer bytes and tiny native rows."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import socket
import sys
from typing import Any

import pytest
from pydantic import ValidationError

from benchmarks import comparison_correctness_acceptance as acceptance
from benchmarks.real_dump_journey import JourneyFailure
from gateway_backend.application.comparison_audit import ComparisonStructureAudit
from gateway_backend.application.pair_pipeline import run_history_pair_pipeline
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison import ComparisonPlan, ComparisonRequest, plan_comparison
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.operations.worker import ExecutionControl
from tests.support.comparison_s3_e_live import canonical_bound
from tests.test_comparison_replacement import _artifact_bound

pytestmark = pytest.mark.unit
GOLDEN = Path(__file__).resolve().parents[2] / "fixtures/golden/presentation/be-b/v2/surface"
SURFACE_VECTORS = tuple(sorted(GOLDEN.glob("*.json")))
ISOLATION_FAULTS = (
    ("repository", "http://existing-deployment:8000", "unix:///var/run/docker.sock", "node", "Repository"),
    ("host", "ssh://other-node", "unix:///var/run/docker.sock", "node", "overrides"),
    ("context", "remote", "unix:///var/run/docker.sock", "node", "overrides"),
    ("endpoint", "", "ssh://other-node", "node", "local"),
    ("daemon", "", "unix:///var/run/docker.sock", "other-node", "hostname"),
)
MARKER_FAULTS = ("wrong-name", "nonempty", "extra")
RECORD_FAULTS = ("identity", "before", "current")
CONFIGURATION_KEY_FAULTS = ("none", "before-missing", "current-missing", "before-order", "current-order", "changed")


@pytest.mark.parametrize("path", SURFACE_VECTORS, ids=lambda path: path.stem)
def test_acceptance_decodes_every_frozen_production_surface(path: Path) -> None:
    vectors = json.loads(path.read_bytes())
    for vector in vectors:
        document = vector["document"]
        surface = acceptance._Surface.model_validate_json(json.dumps(document))
        assert surface.view.table_count == surface.summary["table_count"]
        for target in (document, document["view"]):
            target["unexpected"] = True
            with pytest.raises(ValidationError, match="extra_forbidden"):
                acceptance._Surface.model_validate_json(json.dumps(document))
            del target["unexpected"]


def _local_docker(monkeypatch: pytest.MonkeyPatch, *, endpoint: str, daemon: str) -> None:
    for key in ("GATEWAY_BACKEND_REPOSITORY_BASE_URL", "DOCKER_HOST", "DOCKER_CONTEXT",
                "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "node")

    def command(*args: str) -> subprocess.CompletedProcess[str]:
        if args == ("docker", "context", "show"):
            stdout = "default\n"
        elif args == ("docker", "context", "inspect", "default", "--format", "{{.Endpoints.docker.Host}}"):
            stdout = endpoint + "\n"
        elif args == ("docker", "info", "--format", "{{.Name}}"):
            stdout = daemon + "\n"
        else:
            raise AssertionError("unexpected command")
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(acceptance, "_command", command)


@pytest.mark.parametrize("fault,value,endpoint,daemon,message", ISOLATION_FAULTS)
def test_acceptance_rejects_external_repository_and_docker_connections(
    monkeypatch: pytest.MonkeyPatch, fault: str, value: str,
    endpoint: str, daemon: str, message: str,
) -> None:
    _local_docker(monkeypatch, endpoint=endpoint, daemon=daemon)
    if fault in {"repository", "host", "context"}:
        variable = {"repository": "GATEWAY_BACKEND_REPOSITORY_BASE_URL",
                    "host": "DOCKER_HOST", "context": "DOCKER_CONTEXT"}[fault]
        monkeypatch.setenv(variable, value)
    with pytest.raises(JourneyFailure, match=message):
        acceptance._assert_execution_isolation()


def test_acceptance_records_local_docker_and_internal_repository_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _local_docker(monkeypatch, endpoint="unix:///var/run/docker.sock", daemon="node")
    assert acceptance._assert_execution_isolation() == {
        "repository_url": "http://repository-service:8000", "docker_context": "default",
        "docker_endpoint": "unix:///var/run/docker.sock", "docker_hostname": "node"}


def _failed_compose(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["docker", "compose"], 7, "original stdout\n", "original stderr\n")


def test_acceptance_preserves_failed_probe_output_and_numeric_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(acceptance, "run_compose", _failed_compose)
    with pytest.raises(JourneyFailure, match="probe failed"):
        acceptance._probe({}, "preview", "submission", tmp_path, "probe-before")
    assert (tmp_path / "probe-before-stdout.log").read_text() == "original stdout\n"
    assert (tmp_path / "probe-before-stderr.log").read_text() == "original stderr\n"
    assert json.loads((tmp_path / "probe-before-command.json").read_bytes())["exit_code"] == 7


@pytest.mark.parametrize("missing_ready_protection", (False, True))
def test_acceptance_probe_reads_local_ready_audit_and_requires_complete_protection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    missing_ready_protection: bool,
) -> None:
    from gateway_backend.application.checkpoints import ReadyClosureDocument
    from gateway_backend.bootstrap.storage_layout import local_store_from_config
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    import tests.support.preview_job_harness as preview_harness
    from tests.support.runtime_settings import make_backend_settings
    from tests.test_preview_job_assemble import _run_through_publish

    unchanged = "CREATE TABLE probe_structure(id INT PRIMARY KEY,value INT); INSERT INTO probe_structure VALUES(1,10);"
    extended = "CREATE TABLE probe_structure(id INT PRIMARY KEY,value INT,extra INT); INSERT INTO probe_structure VALUES(1,10,99);"
    # Keep the repository provider's existing baseline rows; this new table is
    # materialized from the uploaded initial/modified SQL by the real pipeline.
    monkeypatch.setattr(preview_harness, "INITIAL_SQL", preview_harness.INITIAL_SQL + unchanged)
    monkeypatch.setattr(preview_harness, "MODIFIED_SQL", preview_harness.MODIFIED_SQL + extended)
    harness = preview_harness.build_preview_harness(tmp_path / "preview")
    _run_through_publish(harness, "op-local-probe")
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        workspace = uow.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert workspace is not None and workspace.current_preview_result_id is not None
        preview = uow.workspace.get_preview_result(workspace.current_preview_result_id)
    assert preview is not None
    audit_pairs = {pair.pair_id for pair in preview.comparison_pairs if pair.structure_audit_artifact_id is not None}
    assert audit_pairs, "the probe must exercise its backend-only audit lookup"

    settings = make_backend_settings(tmp_path / "deployment")
    store = local_store_from_config(settings.deployment_config)
    for ref, raw in harness.artifact_store._artifacts.values():
        store.put(raw, ref)
    ready_ref = store.get_ref(preview.ready_closure_artifact_id)
    ready = ReadyClosureDocument.from_canonical_bytes(store.locate(ready_ref))
    refs = (ready_ref, *ready.artifact_refs())
    with ControlDbUnitOfWork(harness.db_path) as uow:
        uow.set_artifact_protection(refs[1:] if missing_ready_protection else refs,
            owner_kind="submission-review", owner_id="sub-local-probe", intent="submission-review")

    # Execute the exact container probe with real filesystem adapters. Only its
    # deployment settings and fixed container DB path point to this test's data.
    monkeypatch.setattr("gateway_backend.settings.BackendSettings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["probe", preview.preview_result_id, "sub-local-probe"])
    uri = "file:/var/lib/gateway/be-metadata/control.sqlite3?mode=ro"
    assert acceptance._REVIEW_PROBE.count(uri) == 1
    source = acceptance._REVIEW_PROBE.replace(repr(uri), repr(f"file:{harness.db_path}?mode=ro"))
    capsys.readouterr()
    if missing_ready_protection:
        with pytest.raises(RuntimeError, match="submission protection is incomplete"):
            exec(source, {})
    else:
        exec(source, {})
        observed = acceptance._Probe.model_validate_json(capsys.readouterr().out)
        assert observed.ready_artifact_ids == sorted(ref.artifact_id for ref in refs)
        assert observed.protected_artifact_ids == observed.ready_artifact_ids
        assert set(observed.audits) == audit_pairs
        assert all(audit.tables[0].table_name == "probe_structure" for audit in observed.audits.values())


@pytest.mark.parametrize("primary_failure", (False, True))
def test_acceptance_log_failure_cleans_own_stack_and_cannot_replace_original_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, primary_failure: bool,
) -> None:
    monkeypatch.setattr(acceptance, "run_compose", _failed_compose)
    cleaned: list[bool] = []
    monkeypatch.setattr(acceptance, "cleanup_compose_project_artifacts", lambda _env: cleaned.append(True))
    (tmp_path / "secrets").mkdir()
    state = acceptance._RunState(cleanup_complete=False)
    primary = ValueError("original business failure") if primary_failure else None
    if primary is None:
        with pytest.raises(JourneyFailure, match="log collection failed"):
            acceptance._finish_stack({}, tmp_path, state, primary)
    else:
        acceptance._finish_stack({}, tmp_path, state, primary)
        assert "original business failure" in (tmp_path / "business-exception.log").read_text()
        assert primary.__notes__
    assert cleaned == [True] and state.cleanup_complete
    assert not (tmp_path / "secrets").exists()
    assert json.loads((tmp_path / "compose-command.json").read_bytes())["exit_code"] == 7
    assert (tmp_path / "compose-stderr.log").read_text() == "original stderr\n"


@pytest.mark.parametrize("nonempty", (False, True))
@pytest.mark.parametrize("fault", CONFIGURATION_KEY_FAULTS)
def test_acceptance_checks_effective_audit_keys_with_keyless_canonical_storage(nonempty: bool, fault: str) -> None:
    store = InMemoryArtifactStore()
    before = "CREATE TABLE cnt_manage_cfg(page_no INT UNSIGNED,no INT UNSIGNED,value INT);"
    current = "CREATE TABLE cnt_manage_cfg(page_no INT UNSIGNED,no INT UNSIGNED,value INT,config_type TEXT,tips TEXT);"
    if nonempty:
        before += " INSERT INTO cnt_manage_cfg VALUES(1,2,10);"
        current += " INSERT INTO cnt_manage_cfg VALUES(1,2,10,'type','tip');"
    before_bound = _artifact_bound(before, store)
    current_bound = _artifact_bound(current, store)
    assert before_bound.presentation is not None and current_bound.presentation is not None
    result = run_history_pair_pipeline(pair_id="configuration-key-audit",
        before=before_bound, current=current_bound,
        before_presentation=before_bound.presentation, current_presentation=current_bound.presentation,
        rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()), store=store,
        control=ExecutionControl(), on_cancel=lambda: None, repository_id="replacement-fixture")
    assert result.structure_audit_ref is not None
    assert result.surface_result.surface is not None
    surface, = result.surface_result.surface.tables
    assert surface.compare.compare_key_columns == ()
    audit = ComparisonStructureAudit.model_validate_json(store.locate(result.structure_audit_ref))
    fact, = audit.tables
    assert fact.equality_evidence == ("NATIVE_SHARED_VALUES" if nonempty else "BOUND_EMPTY_DESCRIPTORS")
    changes = fact.raw_fact.schema_changes
    assert changes.effective_compare_key_before == changes.effective_compare_key_current == ("page_no", "no")
    acceptance._configuration_keys(fact)
    if fault != "none":
        if fault == "changed":
            update: dict[str, Any] = {"effective_compare_key_changed": True}
        else:
            side, failure = fault.split("-")
            update = {"effective_compare_key_" + side: ("no",) if failure == "missing" else ("no", "page_no")}
        altered = fact.model_copy(update={"raw_fact": fact.raw_fact.model_copy(update={
            "schema_changes": changes.model_copy(update=update)})})
        with pytest.raises(JourneyFailure, match="comparison key"):
            acceptance._configuration_keys(altered)


@pytest.mark.parametrize("fault", MARKER_FAULTS)
def test_acceptance_requires_the_exact_original_project_marker(tmp_path: Path, fault: str) -> None:
    marker = tmp_path / acceptance.NUMBER1_MARKER
    marker.write_bytes(b"")
    assert acceptance._number1_marker(tmp_path) == marker
    if fault == "wrong-name":
        marker.rename(tmp_path / "replacement.pmc")
    elif fault == "nonempty":
        marker.write_bytes(b"changed")
    else:
        (tmp_path / "additional.pmc").write_bytes(b"")
    with pytest.raises(JourneyFailure, match="marker name/content"):
        acceptance._number1_marker(tmp_path)


def _source_and_native_rows(root: Path) -> tuple[acceptance._DeviceChange, list[dict[str, Any]]]:
    ddl = ("CREATE TABLE `device` (\n  `gid` INT UNSIGNED NOT NULL PRIMARY KEY,\n"
           "  `dev_addr` INT,\n  `map_addr` INT,\n  `description` VARCHAR(255),\n"
           "  `model` VARCHAR(32)\n) ENGINE=MyISAM;\n")
    source_sql = []
    for side, value in (("data1", "公用测控装置2"), ("data2", "公用测控装置2--1")):
        sql = ddl + f"INSERT INTO `device` VALUES (15542,17,17,'{value}','model');\n"
        directory = root / side / "sql"
        directory.mkdir(parents=True)
        (directory / "dbcfg.sql").write_text(sql, encoding="utf-8")
        source_sql.append(sql)
    oracle = acceptance._source_device_change(root)
    plan = plan_comparison(ComparisonRequest(pair_id="source-record-check",
        before=canonical_bound(source_sql[0]), current=canonical_bound(source_sql[1]),
        rule_set=comparison_rule_set(migrated_table_ruleset_snapshot())))
    assert isinstance(plan, ComparisonPlan)
    rows: list[dict[str, Any]] = []
    product = compare_plan_native(plan)
    try:
        for handle in product.handles.values():
            with closing(handle.record_batches("STANDARD")) as reader:
                rows.extend(row for batch in reader for row in batch.to_pylist())
    finally:
        product.close()
    return oracle, rows


@pytest.mark.parametrize("fault", RECORD_FAULTS)
def test_acceptance_matches_source_literal_to_native_record_identity_and_values(tmp_path: Path, fault: str) -> None:
    oracle, rows = _source_and_native_rows(tmp_path)
    assert acceptance._check_device_record(rows, oracle)
    altered = deepcopy(rows)
    if fault == "identity":
        altered[0]["row_identity"] = bytes(32)
    else:
        field = "before_values" if fault == "before" else "current_values"
        value = next(item["value"] for item in altered[0][field] if item["column_name"] == "description")
        value["text"] = "incorrect"
    with pytest.raises(JourneyFailure, match="mismatch"):
        acceptance._check_device_record(altered, oracle)
