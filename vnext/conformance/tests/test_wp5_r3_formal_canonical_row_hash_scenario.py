"""WP5 R3 formal canonical-row-hash scenario tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.owner.arrow_row_hash_oracle import compute_table_content_identity
from gateway_conformance.owner.canonical_row_hash import (
    FORMAL_REQUIRED_PROFILES,
    ORACLE_ANCHOR_LOGICAL_NAME,
)
from gateway_conformance.owner.validate import compute_golden_content_digest
from gateway_conformance.paths import VNEXT_ROOT
from gateway_conformance.scenario.closure import load_scenario_closure
from gateway_conformance.scenario.digest import (
    compute_fixture_content_digest,
    compute_input_digest,
)
from gateway_conformance.scenario.discovery import (
    discover_formal_scenarios,
    load_formal_scenario,
    validate_formal_scenario_oracle,
)
from gateway_conformance.scenario.validate import validate_scenario
from gateway_conformance.strict_yaml import loads_strict_yaml

FORMAL_SCENARIO_ROOT = (
    VNEXT_ROOT / "fixtures" / "scenarios" / "data" / "canonical-row-hashes" / "mixed-scalars"
)
REPO_ROOT = VNEXT_ROOT.parent
CONFORMANCE_ROOT = VNEXT_ROOT / "conformance"
WRITE_SCENARIO_SCRIPT = REPO_ROOT / "vnext" / "scripts" / "write-wp5-r3-formal-scenario.py"
SCENARIO_REL_DIR = Path("data") / "canonical-row-hashes" / "mixed-scalars"
PATCH_SHA_SCRIPT = REPO_ROOT / "vnext" / "scripts" / "verify-wp5-r3-patch-sha.sh"
R3_BASE = "97720ea1ce857e320090623372e746b1f12f38fc"
EVIDENCE_PATH = (
    REPO_ROOT
    / "docs/backend-vnext/refactoring/temporary/phase-1/wp5-r3-canonical-row-hash-scenario-evidence.md"
)


def _evidence_patch_sha() -> str:
    text = EVIDENCE_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "EXPECTED_SHA=" in line:
            value = line.split("EXPECTED_SHA=", 1)[1].strip().rstrip("\\").strip()
            if value:
                return value
    raise AssertionError("Evidence missing EXPECTED_SHA line")


def _run_patch_sha(env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.stdout.split()[0]


def _copy_formal_scenario(tmp_path: Path) -> Path:
    dest = tmp_path / "data" / "canonical-row-hashes" / "mixed-scalars"
    shutil.copytree(FORMAL_SCENARIO_ROOT, dest)
    return dest


def test_formal_scenario_passes_closure_validation() -> None:
    validate_formal_scenario_oracle()


def test_formal_scenario_digests_recompute() -> None:
    manifest, closure = load_formal_scenario()
    recomputed_input = compute_input_digest(manifest, closure.assets)
    recomputed_fixture = compute_fixture_content_digest(closure)
    assert manifest["input_digest"] == recomputed_input
    assert manifest["fixture_content_digest"] == recomputed_fixture


def test_formal_golden_content_digest_recomputes() -> None:
    _manifest, closure = load_formal_scenario()
    envelope = closure.golden_envelopes["row-hashes"]
    assert compute_golden_content_digest(envelope) == str(envelope["content_digest"])


def test_formal_golden_content_digest_matches_normative_vector() -> None:
    _manifest, closure = load_formal_scenario()
    envelope = closure.golden_envelopes["row-hashes"]
    computed = compute_golden_content_digest(envelope)
    assert computed == str(envelope["content_digest"])
    vector_root = (
        VNEXT_ROOT / "fixtures" / "vectors" / "shared-kernel" / "canonical-encoding" / "v1"
    )
    digest_lines = (vector_root / "digest.jsonl").read_text(encoding="utf-8").splitlines()
    case = next(
        json.loads(line)
        for line in digest_lines
        if line.strip()
        and json.loads(line)["case_id"]
        == "digest.semantic.canonical-table-result.mixed-scalars-golden"
    )
    assert case["expected"]["digest_ref"] == computed


def test_formal_scenario_oracle_anchor_in_closure() -> None:
    _manifest, closure = load_formal_scenario()
    assert "input/row-hash-oracle-anchor.json" in closure.declared_paths
    assert ORACLE_ANCHOR_LOGICAL_NAME in closure.owner_closure_assets
    assert ORACLE_ANCHOR_LOGICAL_NAME not in closure.assets


def test_formal_scenario_binds_independent_oracle() -> None:
    manifest, closure = load_formal_scenario()
    fields = manifest["stimulus"]["payload"]["value"]["declared_table_schema"]["fields"]
    ipc_bytes = closure.assets["table-stream"].raw
    row_count, raw_digest, sorted_hashes = compute_table_content_identity(ipc_bytes, fields)
    golden = closure.golden_envelopes["row-hashes"]["payload"]["value"]
    assert golden["row_count"] == row_count
    assert golden["raw_content_digest"] == raw_digest
    anchor = json.loads(
        closure.owner_closure_assets[ORACLE_ANCHOR_LOGICAL_NAME].raw.decode("utf-8")
    )
    assert anchor["row_count"] == row_count
    assert anchor["raw_content_digest"] == raw_digest
    assert [bytes.fromhex(item) for item in anchor["sorted_row_hashes_hex"]] == sorted_hashes


def test_formal_oracle_matches_closure_anchor() -> None:
    manifest, closure = load_formal_scenario()
    fields = manifest["stimulus"]["payload"]["value"]["declared_table_schema"]["fields"]
    ipc_bytes = closure.assets["table-stream"].raw
    row_count, raw_digest, sorted_hashes = compute_table_content_identity(ipc_bytes, fields)
    anchor = json.loads(
        closure.owner_closure_assets[ORACLE_ANCHOR_LOGICAL_NAME].raw.decode("utf-8")
    )
    assert anchor["scenario_id"] == manifest["scenario_id"]
    assert anchor["row_count"] == row_count
    assert anchor["raw_content_digest"] == raw_digest
    assert [bytes.fromhex(item) for item in anchor["sorted_row_hashes_hex"]] == sorted_hashes


def test_formal_golden_host_metadata_absent() -> None:
    _manifest, closure = load_formal_scenario()
    golden = closure.golden_envelopes["row-hashes"]["payload"]["value"]
    allowed = {
        "arrow_mapping_schema_version",
        "canonical_encoding_version",
        "contract_binding",
        "diagnostics",
        "raw_content_digest",
        "result_schema_version",
        "row_count",
        "table_schema_digest",
    }
    assert set(golden.keys()) == allowed
    assert golden["diagnostics"] == []


def test_discovery_rejects_second_unauthorized_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import gateway_conformance.scenario.discovery as discovery_mod

    fake_root = tmp_path / "fixtures" / "scenarios"
    authorized = fake_root / "data" / "canonical-row-hashes" / "mixed-scalars"
    authorized.mkdir(parents=True)
    (authorized / "scenario.yaml").write_text("manifest_schema_version: 1\n", encoding="utf-8")
    rogue = fake_root / "data" / "evil" / "extra"
    rogue.mkdir(parents=True)
    (rogue / "scenario.yaml").write_text("manifest_schema_version: 1\n", encoding="utf-8")

    monkeypatch.setattr(discovery_mod, "FORMAL_SCENARIO_ROOT", fake_root)
    with pytest.raises(ConformanceValidationError, match="unauthorized formal scenario"):
        discovery_mod.discover_formal_scenarios()


def test_formal_scenario_stale_input_digest_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    manifest, _closure = load_formal_scenario()
    stale = manifest["input_digest"]
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    (root / "scenario.yaml").write_text(
        text.replace(stale, "sha256:" + "f" * 64, 1),
        encoding="utf-8",
    )
    with pytest.raises(ConformanceValidationError, match="input_digest"):
        validate_scenario(root)


def test_formal_scenario_stale_fixture_digest_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    manifest, _closure = load_formal_scenario()
    stale = manifest["fixture_content_digest"]
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    (root / "scenario.yaml").write_text(
        text.replace(stale, "sha256:" + "e" * 64, 1),
        encoding="utf-8",
    )
    with pytest.raises(ConformanceValidationError, match="fixture_content_digest"):
        validate_scenario(root)


def test_formal_scenario_stale_raw_sha256_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    (root / "scenario.yaml").write_text(
        text.replace(
            "raw_sha256: sha256:1b4586a017ccde6ed136feab26e3e835f5198dcb5dbfa8644c34c8d5664d600f",
            "raw_sha256: sha256:" + "a" * 64,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConformanceValidationError, match="raw_sha256"):
        validate_scenario(root)


def test_formal_scenario_stale_size_bytes_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    (root / "scenario.yaml").write_text(
        text.replace("size_bytes: 728", "size_bytes: 729"), encoding="utf-8"
    )
    with pytest.raises(ConformanceValidationError, match="size_bytes"):
        validate_scenario(root)


def test_formal_scenario_owner_content_digest_mismatch_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    (root / "scenario.yaml").write_text(
        text.replace(
            "content_digest: sha256:9ca39767f4f7e685da2d91699681b988e69fcc6ee9ce4d90e1634b487f81f420",
            "content_digest: sha256:" + "b" * 64,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConformanceValidationError, match="content_digest"):
        validate_scenario(root)


def test_formal_scenario_golden_binding_mismatch_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    (root / "scenario.yaml").write_text(
        text.replace(
            "    contract_binding:\n      owner: canonical-row-hash-capability\n"
            "      contract_id: gateway-vnext.canonical-row-hash-compute-boundary\n"
            "      semantic_version: 1.0.0\n    content_digest:",
            "    contract_binding:\n      owner: canonical-row-hash-capability\n"
            "      contract_id: gateway-vnext.canonical-row-hash-compute-boundary\n"
            "      semantic_version: 9.9.9\n    content_digest:",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConformanceValidationError, match="contract_binding"):
        validate_scenario(root)


def test_formal_scenario_stale_oracle_anchor_semantic_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    anchor_path = root / "input" / "row-hash-oracle-anchor.json"
    payload = json.loads(anchor_path.read_text(encoding="utf-8"))
    payload["row_count"] = "99"
    raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    anchor_path.write_bytes(raw)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    text = re.sub(
        r"logical_name: row-hash-oracle-anchor\n    path: input/row-hash-oracle-anchor.json\n"
        r"    media_type: application/json\n    size_bytes: \d+\n    raw_sha256: sha256:[0-9a-f]{64}",
        "logical_name: row-hash-oracle-anchor\n    path: input/row-hash-oracle-anchor.json\n"
        f"    media_type: application/json\n    size_bytes: {len(raw)}\n"
        f"    raw_sha256: sha256:{hashlib.sha256(raw).hexdigest()}",
        text,
        count=1,
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConformanceValidationError, match="oracle anchor row_count mismatch"):
        validate_scenario(root)


def test_formal_scenario_undeclared_asset_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    (root / "input" / "extra.bin").write_bytes(b"x")
    with pytest.raises(ConformanceValidationError, match="undeclared"):
        validate_scenario(root)


def _mutate_golden_result_field(root: Path, field: str, value: str) -> None:
    golden_path = root / "expected" / "row-hashes.golden.json"
    envelope = json.loads(golden_path.read_text(encoding="utf-8"))
    payload_value = envelope["payload"]["value"]
    payload_value[field] = value
    envelope["content_digest"] = compute_golden_content_digest(envelope)
    golden_path.write_text(json.dumps(envelope, separators=(",", ":")) + "\n", encoding="utf-8")
    raw = golden_path.read_bytes()
    text = (root / "scenario.yaml").read_text(encoding="utf-8")

    digest = hashlib.sha256(raw).hexdigest()
    text = text.replace(
        "raw_sha256: sha256:a99ee842cdf7d9d34dd662c4ec552470044579bf649a0483458727116e6b61f5",
        f"raw_sha256: sha256:{digest}",
    )
    text = text.replace("size_bytes: 995", f"size_bytes: {len(raw)}")
    text = text.replace(
        "content_digest: sha256:9ca39767f4f7e685da2d91699681b988e69fcc6ee9ce4d90e1634b487f81f420",
        f"content_digest: {envelope['content_digest']}",
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    closure = load_scenario_closure(root)
    fixture_digest = compute_fixture_content_digest(closure)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    text = re.sub(
        r"fixture_content_digest: sha256:[0-9a-f]{64}",
        f"fixture_content_digest: {fixture_digest}",
        text,
        count=1,
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")


def test_formal_scenario_stale_row_count_in_golden_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    _mutate_golden_result_field(root, "row_count", "9")
    with pytest.raises(ConformanceValidationError, match="row_count"):
        validate_scenario(root)


def test_formal_scenario_stale_raw_content_digest_in_golden_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    _mutate_golden_result_field(
        root,
        "raw_content_digest",
        "sha256:" + "c" * 64,
    )
    with pytest.raises(ConformanceValidationError, match="raw_content_digest"):
        validate_scenario(root)


@pytest.mark.parametrize(
    "profiles",
    [
        ["integration", "reference"],
        ["integration", "provider-matrix", "reference", "process-crash"],
        ["reference", "integration", "provider-matrix"],
    ],
)
def test_formal_scenario_required_profiles_rejected(tmp_path: Path, profiles: list[str]) -> None:
    root = _copy_formal_scenario(tmp_path)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []
    skip = False
    for line in lines:
        if line.startswith("required_profiles:"):
            out.append("required_profiles:")
            for profile in profiles:
                out.append(f"  - {profile}")
            skip = True
            continue
        if skip:
            if line.startswith("  - "):
                continue
            skip = False
        out.append(line)
    (root / "scenario.yaml").write_text("\n".join(out) + "\n", encoding="utf-8")
    assert profiles != FORMAL_REQUIRED_PROFILES
    with pytest.raises(ConformanceValidationError, match="required_profiles"):
        validate_scenario(root)


def test_formal_scenario_path_escape_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    (root / "scenario.yaml").write_text(
        text.replace("path: input/table.arrow-stream", "path: input/../outside.arrow-stream"),
        encoding="utf-8",
    )
    with pytest.raises(ConformanceValidationError, match="parent segments"):
        validate_scenario(root)


def test_formal_scenario_input_symlink_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    outside = tmp_path / "outside.arrow-stream"
    shutil.copyfile(root / "input" / "table.arrow-stream", outside)
    (root / "input" / "table.arrow-stream").unlink()
    (root / "input" / "table.arrow-stream").symlink_to(outside)
    with pytest.raises(ConformanceValidationError, match="opened safely"):
        validate_scenario(root)


def test_formal_scenario_expected_symlink_rejected(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    outside = tmp_path / "row-hashes.golden.json"
    shutil.copyfile(root / "expected" / "row-hashes.golden.json", outside)
    (root / "expected" / "row-hashes.golden.json").unlink()
    (root / "expected" / "row-hashes.golden.json").symlink_to(outside)
    with pytest.raises(ConformanceValidationError, match="opened safely"):
        validate_scenario(root)


def test_formal_scenario_yaml_presentation_does_not_change_semantic_identity(
    tmp_path: Path,
) -> None:
    root = _copy_formal_scenario(tmp_path)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    decorated = "# presentation-only comment\n\n" + text
    (root / "scenario.yaml").write_text(decorated, encoding="utf-8")
    before = loads_strict_yaml(decorated)
    after_manifest = validate_scenario(root)
    assert after_manifest["scenario_id"] == before["scenario_id"]
    assert after_manifest["input_digest"] == before["input_digest"]
    assert after_manifest["fixture_content_digest"] == before["fixture_content_digest"]


def test_formal_scenario_plan_excludes_golden_material() -> None:
    from gateway_conformance.runner.plan import RunParams, build_harness_plan
    from gateway_conformance.paths import FORBIDDEN_PROTOCOL_FIELDS
    from tests.test_runner_golden_isolation import _walk_forbidden

    manifest, closure = load_formal_scenario()
    plan = build_harness_plan(
        manifest,
        closure,
        RunParams(
            profile="reference",
            provider_id=None,
            run_id="r3-plan",
            deterministic_seed="seed",
            logical_time_start="2026-01-01T00:00:00Z",
        ),
    )
    _walk_forbidden(plan, label="plan")
    assert FORBIDDEN_PROTOCOL_FIELDS.isdisjoint(plan.keys())


def test_formal_scenario_not_run_without_real_harness() -> None:
    from gateway_conformance.runner.lifecycle import execute_scenario_run
    from gateway_conformance.runner.registry import SubjectHarnessRegistry
    from gateway_conformance.runner.runtime import LogicalClock
    from tests.runner_support import default_env_versions

    registry = SubjectHarnessRegistry()
    outcome = execute_scenario_run(
        FORMAL_SCENARIO_ROOT,
        profile="reference",
        provider_id=None,
        run_id="r3-unsupported",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
    assert outcome.result["expectations"][0]["outcome"] == "NOT_RUN"


def test_formal_scenario_rejects_non_canonical_row_count_in_golden(tmp_path: Path) -> None:
    root = _copy_formal_scenario(tmp_path)
    golden_path = root / "expected" / "row-hashes.golden.json"
    envelope = json.loads(golden_path.read_text(encoding="utf-8"))
    envelope["payload"]["value"]["row_count"] = "03"
    golden_path.write_text(json.dumps(envelope, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


R3_ACCEPT_BASELINE = "f50015c3439b598b2d5b43afd82b10ceadd070fd"
R3_FROZEN_PATH_PREFIXES = (
    "vnext/fixtures/scenarios/data/canonical-row-hashes/mixed-scalars/",
    "vnext/scripts/write-wp5-r3-formal-scenario.py",
    "vnext/scripts/render-wp5-r3-golden-candidate.py",
)


def test_wp5_r3_patch_sha_script_matches_worktree() -> None:
    assert PATCH_SHA_SCRIPT.is_file()
    sha = _run_patch_sha()
    assert len(sha) == 64
    changed = subprocess.run(
        ["git", "diff", "--name-only", R3_ACCEPT_BASELINE],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for path in changed:
        if not path:
            continue
        for prefix in R3_FROZEN_PATH_PREFIXES:
            if path.startswith(prefix) or path == prefix.rstrip("/"):
                raise AssertionError(f"R3-frozen path changed since accept baseline: {path}")
    bad = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        env={**os.environ, "EXPECTED_SHA": "0" * 64},
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0


def test_formal_scenario_fake_harness_cannot_pass(tmp_path: Path) -> None:
    from gateway_conformance.runner.fake.harness import FakeSubjectHarness
    from gateway_conformance.runner.lifecycle import execute_scenario_run
    from gateway_conformance.runner.registry import (
        FORMAL_PRODUCTION_SUBJECT_KEY,
        SubjectHarnessRegistry,
    )
    from gateway_conformance.runner.runtime import LogicalClock
    from tests.runner_support import default_env_versions

    root = _copy_formal_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    with registry._lock:
        registry._factories[FORMAL_PRODUCTION_SUBJECT_KEY] = lambda: FakeSubjectHarness()
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="r3-fake",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
    assert outcome.result["expectations"][0]["outcome"] == "NOT_RUN"


def test_formal_resolver_cannot_read_oracle_anchor() -> None:
    from gateway_conformance.runner.runtime import VerifiedAssetResolver

    _manifest, closure = load_formal_scenario()
    resolver = VerifiedAssetResolver(closure.assets)
    with pytest.raises(ConformanceValidationError, match="unknown verified asset"):
        resolver.read_bytes(ORACLE_ANCHOR_LOGICAL_NAME)


def test_formal_anchor_only_harness_cannot_pass(tmp_path: Path) -> None:
    from gateway_conformance.runner.lifecycle import execute_scenario_run
    from gateway_conformance.runner.registry import (
        FORMAL_PRODUCTION_SUBJECT_KEY,
        SubjectHarnessRegistry,
    )
    from gateway_conformance.runner.runtime import HarnessRuntimeContext, LogicalClock
    from gateway_conformance.runner.types import (
        ActualObservation,
        CleanupReceipt,
        InvocationReceipt,
        ObservationSet,
        PhaseReceipt,
        RecoveryReceipt,
        SupportDecision,
    )
    from gateway_conformance.owner.validate import compute_owner_content_digest
    from tests.runner_support import default_env_versions

    class AnchorOnlyHarness:
        def preflight(self, plan: dict[str, object]) -> SupportDecision:
            return SupportDecision(support="SUPPORTED")

        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            return PhaseReceipt(phase="seed", outcome="COMPLETED")

        def invoke(
            self, context: HarnessRuntimeContext, plan: dict[str, object]
        ) -> InvocationReceipt:
            return InvocationReceipt.completed()

        def stabilize_and_observe(
            self, context: HarnessRuntimeContext, plan: dict[str, object], *, observation_point: str
        ) -> ObservationSet:
            anchor_raw = context.resolver.read_bytes(ORACLE_ANCHOR_LOGICAL_NAME)
            anchor = json.loads(anchor_raw.decode("utf-8"))
            requests = cast(
                list[dict[str, Any]],
                plan["observation_requests"],
            )
            request = next(item for item in requests if str(item["expectation_id"]) == "row-hashes")
            binding = dict(request["contract_binding"])
            descriptor = dict(request["payload_descriptor"])
            value = {
                "result_schema_version": 1,
                "contract_binding": {
                    "contract_id": binding["contract_id"],
                    "semantic_version": binding["semantic_version"],
                },
                "canonical_encoding_version": 1,
                "arrow_mapping_schema_version": 1,
                "table_schema_digest": "sha256:0d6c0579ef52cbdd310be9c95879d3d9dfc2d867271fd387fa9e66a0d34cc28e",
                "row_count": anchor["row_count"],
                "raw_content_digest": anchor["raw_content_digest"],
                "diagnostics": [],
            }
            digest = compute_owner_content_digest(
                value,
                owner=str(binding["owner"]),
                contract_id=str(binding["contract_id"]),
                semantic_version=str(binding["semantic_version"]),
                schema_id=str(descriptor["schema_id"]),
                schema_version=int(descriptor["schema_version"]),
            )
            obs = ActualObservation(
                expectation_id="row-hashes",
                observation_point=observation_point,
                contract_binding=binding,
                payload_descriptor=descriptor,
                canonical_encoding_version=1,
                actual_content_digest=digest,
                payload={"storage": "inline", "value": value},
            )
            return ObservationSet(
                observations=(obs,),
                receipt=PhaseReceipt(phase="stabilize_and_observe", outcome="COMPLETED"),
            )

        def drive_recovery(
            self, context: HarnessRuntimeContext, plan: dict[str, object]
        ) -> RecoveryReceipt:
            return RecoveryReceipt.completed()

        def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt:
            return CleanupReceipt(status="CLEAN")

    root = _copy_formal_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    registry.register(FORMAL_PRODUCTION_SUBJECT_KEY, AnchorOnlyHarness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="r3-anchor-only",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] != "PASSED"


def test_formal_production_subject_rejects_fake_registration() -> None:
    from gateway_conformance.runner.fake.harness import FakeSubjectHarness
    from gateway_conformance.runner.registry import (
        FORMAL_PRODUCTION_SUBJECT_KEY,
        SubjectHarnessRegistry,
    )

    registry = SubjectHarnessRegistry()
    with pytest.raises(ConformanceValidationError, match="fake harness cannot register"):
        registry.register(
            FORMAL_PRODUCTION_SUBJECT_KEY,
            FakeSubjectHarness,
            harness_provenance="production",
        )
    with pytest.raises(ConformanceValidationError, match="test-only harness cannot register"):
        registry.register(
            FORMAL_PRODUCTION_SUBJECT_KEY,
            FakeSubjectHarness,
            harness_provenance="test-only",
        )


def test_wp5_r3_patch_sha_rejects_exclude_override() -> None:
    proc = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        env={**os.environ, "EXCLUDE": "docs/evil.md"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0


def test_wp5_r3_patch_sha_stable_after_git_add(tmp_path: Path) -> None:
    if not (REPO_ROOT / ".git").is_dir():
        pytest.fail("git repository required for patch SHA index isolation test")
    index_before = subprocess.run(
        ["git", "write-tree"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status_before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    before = _run_patch_sha()
    temp_index = tmp_path / "isolated-index"
    temp_index.write_bytes(b"")
    env = {**os.environ, "GIT_INDEX_FILE": str(temp_index)}
    subprocess.run(["git", "read-tree", "HEAD"], cwd=REPO_ROOT, env=env, check=True)
    subprocess.run(
        ["git", "add", "vnext/conformance/src/gateway_conformance/owner/arrow_mapping.py"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )
    after = _run_patch_sha(env)
    assert after == before
    index_after = subprocess.run(
        ["git", "write-tree"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status_after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert index_after == index_before
    assert status_after == status_before


def test_wp5_r3_patch_sha_stable_under_locale() -> None:
    proc = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    proc_c = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
    )
    assert proc.stdout == proc_c.stdout
    assert len(proc.stdout.split()[0]) == 64


def test_wp5_r3_writer_offline_command_reproduces_committed_identity(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.fail(
            "uv is required for WP5 R3 writer offline reproduction (gate installs writer extra)"
        )

    out_base = tmp_path / "out"
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--offline",
            "--no-sync",
            "--extra",
            "writer",
            "python",
            str(WRITE_SCENARIO_SCRIPT),
            "--output-dir",
            str(out_base),
        ],
        cwd=CONFORMANCE_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"writer script failed (exit {proc.returncode}):\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )

    scenario_root = out_base / SCENARIO_REL_DIR
    assert scenario_root.is_dir()

    formal_manifest = loads_strict_yaml(
        (FORMAL_SCENARIO_ROOT / "scenario.yaml").read_text(encoding="utf-8")
    )
    written_manifest = loads_strict_yaml(
        (scenario_root / "scenario.yaml").read_text(encoding="utf-8")
    )
    assert written_manifest["input_digest"] == formal_manifest["input_digest"]
    assert written_manifest["fixture_content_digest"] == formal_manifest["fixture_content_digest"]

    anchor_written = (scenario_root / "input" / "row-hash-oracle-anchor.json").read_bytes()
    anchor_committed = (FORMAL_SCENARIO_ROOT / "input" / "row-hash-oracle-anchor.json").read_bytes()
    assert anchor_written == anchor_committed


def test_discover_formal_scenarios_returns_single_path() -> None:
    roots = discover_formal_scenarios()
    assert len(roots) == 1
    assert roots[0] == FORMAL_SCENARIO_ROOT
