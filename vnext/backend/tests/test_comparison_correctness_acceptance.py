"""Acceptance consumer boundaries with owning producer bytes and tiny native rows."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import socket
from typing import Any

import pytest
from pydantic import ValidationError

from benchmarks import comparison_correctness_acceptance as acceptance
from benchmarks.real_dump_journey import JourneyFailure
from gateway_backend.capabilities.comparison import ComparisonPlan, ComparisonRequest, plan_comparison
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceCompare
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from tests.support.comparison_s3_e_live import canonical_bound

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


def test_acceptance_checks_owning_surface_canonical_configuration_key_order() -> None:
    compare = SurfaceCompare(None, ("no", "page_no"), (), ("no", "page_no"))
    document = compare.to_document()
    acceptance._configuration_keys(document["compare_key_columns"])  # type: ignore[arg-type]
    with pytest.raises(JourneyFailure, match="comparison key"):
        acceptance._configuration_keys(["no"])


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
           "  `dev_addr` INT,\n  `map_addr` INT,\n  `description` VARCHAR(255)\n) ENGINE=MyISAM;\n")
    source_sql = []
    for side, value in (("data1", "公用测控装置2"), ("data2", "公用测控装置2--1")):
        sql = ddl + f"INSERT INTO `device` VALUES (15542,17,17,'{value}');\n"
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
