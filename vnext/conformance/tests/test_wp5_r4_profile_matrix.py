"""WP5 R4 required profile matrix for formal canonical-row-hash scenario."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.harness.canonical_row_hashes.coverage_inventory import (
    CANONICAL_SEMANTIC_KINDS,
    assert_mapping_matrix_executed,
)
from gateway_conformance.harness.canonical_row_hashes.mapping_matrix import (
    run_mapping_provider_matrix,
)
from gateway_conformance.harness.canonical_row_hashes.harness import (
    CanonicalRowHashesSubjectHarness,
)
from gateway_conformance.harness.canonical_row_hashes.integration import reset_integration_probes
from gateway_conformance.harness.canonical_row_hashes.native_compute import (
    reset_native_invoke_probe,
)
from gateway_conformance.harness.canonical_row_hashes.register import (
    register_production_canonical_row_hashes_harness,
)
from gateway_conformance.matrix import (
    ExecutionCell,
    assert_cell_legality,
    assert_exact_cell_closure,
    execute_formal_canonical_row_hash_matrix,
    expand_required_cells,
    matrix_semantic_fingerprint,
)
from gateway_conformance.matrix.executor import discover_formal_scenario_root
from gateway_conformance.owner.arrow_row_hash_oracle import multiset_digest_differs_from_deduped
from gateway_conformance.paths import FORBIDDEN_PROTOCOL_FIELDS, VNEXT_ROOT
from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.plan import RunParams, build_harness_plan
from gateway_conformance.runner.registry import (
    FORMAL_PRODUCTION_SUBJECT_KEY,
    SubjectHarnessRegistry,
)
from gateway_conformance.runner.runtime import LogicalClock
from gateway_conformance.scenario.validate import load_validated_scenario
from tests.runner_support import default_env_versions
from tests.test_runner_golden_isolation import _walk_forbidden

REPO_ROOT = VNEXT_ROOT.parent
FORMAL_SCENARIO_ROOT = (
    VNEXT_ROOT / "fixtures" / "scenarios" / "data" / "canonical-row-hashes" / "mixed-scalars"
)
PATCH_SHA_SCRIPT = REPO_ROOT / "vnext" / "scripts" / "verify-wp5-r4-patch-sha.sh"
EVIDENCE_PATH = (
    REPO_ROOT / "docs/backend-vnext/refactoring/temporary/phase-1/wp5-r4-profile-matrix-evidence.md"
)

EXPECTED_CELLS = (
    ExecutionCell(profile="integration", provider_id=None),
    ExecutionCell(profile="provider-matrix", provider_id="python-reference"),
    ExecutionCell(profile="provider-matrix", provider_id="rust-native"),
    ExecutionCell(profile="reference", provider_id=None),
)


def _registry_with_production() -> SubjectHarnessRegistry:
    registry = SubjectHarnessRegistry()
    register_production_canonical_row_hashes_harness(registry)
    return registry


def _run_matrix() -> Any:
    reset_native_invoke_probe()
    reset_integration_probes()
    return execute_formal_canonical_row_hash_matrix(
        environment_versions=default_env_versions(),
        registry=_registry_with_production(),
        clock=LogicalClock("2026-01-01T00:00:00Z"),
    )


def test_formal_matrix_four_cells_all_passed() -> None:
    suite = _run_matrix()
    assert suite.passed
    assert len(suite.cells) == 4
    for item in suite.cells:
        assert item.outcome.result["status"] == "PASSED"
        assert item.outcome.result["comparison_outcome"] == "MATCH"
        assert item.outcome.result["cleanup"]["status"] == "CLEAN"


def test_formal_matrix_cell_closure_matches_authority() -> None:
    manifest, _ = load_validated_scenario(FORMAL_SCENARIO_ROOT)
    cells = expand_required_cells(manifest)
    assert cells == EXPECTED_CELLS


def test_matrix_missing_required_cell_fails_closure() -> None:
    manifest, _ = load_validated_scenario(FORMAL_SCENARIO_ROOT)
    expected = expand_required_cells(manifest)
    partial = expected[:3]
    with pytest.raises(ConformanceValidationError, match="matrix cell"):
        assert_exact_cell_closure(expected, partial)


def test_matrix_duplicate_cell_fails() -> None:
    manifest, _ = load_validated_scenario(FORMAL_SCENARIO_ROOT)
    expected = expand_required_cells(manifest)
    duplicated = expected + (expected[0],)
    with pytest.raises(ConformanceValidationError, match="duplicate"):
        assert_exact_cell_closure(expected, duplicated)


def test_unknown_provider_id_rejected() -> None:
    with pytest.raises(ConformanceValidationError, match="unknown provider"):
        assert_cell_legality(
            ExecutionCell(profile="provider-matrix", provider_id="repository"),
        )


def test_provider_matrix_null_provider_rejected() -> None:
    with pytest.raises(ConformanceValidationError, match="non-null"):
        assert_cell_legality(ExecutionCell(profile="provider-matrix", provider_id=None))


def test_reference_with_provider_id_rejected() -> None:
    with pytest.raises(ConformanceValidationError, match="null provider"):
        assert_cell_legality(ExecutionCell(profile="reference", provider_id="python-reference"))


def test_integration_with_provider_id_rejected() -> None:
    with pytest.raises(ConformanceValidationError, match="null provider"):
        assert_cell_legality(ExecutionCell(profile="integration", provider_id="rust-native"))


def test_unsupported_cell_blocks_suite() -> None:
    registry = SubjectHarnessRegistry()

    class UnsupportedHarness(CanonicalRowHashesSubjectHarness):
        def preflight(self, plan: dict[str, object]) -> Any:
            from gateway_conformance.runner.types import SupportDecision

            return SupportDecision(support="UNSUPPORTED", reason_code="probe-unsupported")

    registry.register(
        FORMAL_PRODUCTION_SUBJECT_KEY,
        lambda: UnsupportedHarness(),
        harness_provenance="production",
    )
    suite = execute_formal_canonical_row_hash_matrix(
        environment_versions=default_env_versions(),
        registry=registry,
        clock=LogicalClock("2026-01-01T00:00:00Z"),
    )
    assert not suite.passed
    assert any(item.outcome.result["status"] == "UNSUPPORTED" for item in suite.cells)


def test_harness_error_cell_blocks_suite(tmp_path: Path) -> None:
    registry = SubjectHarnessRegistry()

    class ErrorHarness(CanonicalRowHashesSubjectHarness):
        def seed(self, context: Any, plan: dict[str, object]) -> Any:
            raise ConformanceValidationError("probe-harness-error")

    registry.register(
        FORMAL_PRODUCTION_SUBJECT_KEY,
        lambda: ErrorHarness(),
        harness_provenance="production",
    )
    suite = execute_formal_canonical_row_hash_matrix(
        environment_versions=default_env_versions(),
        registry=registry,
        clock=LogicalClock("2026-01-01T00:00:00Z"),
    )
    assert not suite.passed


def test_assertion_failed_cell_blocks_suite() -> None:
    registry = SubjectHarnessRegistry()

    class BadHarness(CanonicalRowHashesSubjectHarness):
        def stabilize_and_observe(
            self, context: Any, plan: dict[str, object], *, observation_point: str
        ) -> Any:
            from gateway_conformance.harness.canonical_row_hashes.result_payload import (
                build_row_hashes_observation,
            )

            value = {
                "result_schema_version": 1,
                "contract_binding": {
                    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
                    "semantic_version": "1.0.0",
                },
                "canonical_encoding_version": 1,
                "arrow_mapping_schema_version": 1,
                "table_schema_digest": "sha256:" + "f" * 64,
                "row_count": "0",
                "raw_content_digest": "sha256:" + "a" * 64,
                "diagnostics": [],
            }
            obs = build_row_hashes_observation(
                plan, observation_point=observation_point, value=value
            )
            from gateway_conformance.runner.types import ObservationSet, PhaseReceipt

            return ObservationSet(
                observations=(obs,),
                receipt=PhaseReceipt(phase="stabilize_and_observe", outcome="COMPLETED"),
            )

    registry.register(
        FORMAL_PRODUCTION_SUBJECT_KEY,
        lambda: BadHarness(),
        harness_provenance="production",
    )
    suite = execute_formal_canonical_row_hash_matrix(
        environment_versions=default_env_versions(),
        registry=registry,
        clock=LogicalClock("2026-01-01T00:00:00Z"),
    )
    assert not suite.passed
    assert any(item.outcome.result["status"] == "ASSERTION_FAILED" for item in suite.cells)


def test_cleanup_leak_blocks_suite() -> None:
    registry = SubjectHarnessRegistry()
    registry.register(
        FORMAL_PRODUCTION_SUBJECT_KEY,
        lambda: CanonicalRowHashesSubjectHarness(cleanup_mode="LEAKED"),
        harness_provenance="production",
    )
    suite = execute_formal_canonical_row_hash_matrix(
        environment_versions=default_env_versions(),
        registry=registry,
        clock=LogicalClock("2026-01-01T00:00:00Z"),
    )
    assert not suite.passed


def test_reference_does_not_invoke_native_facade() -> None:
    from gateway_conformance.harness.canonical_row_hashes import native_compute as native_mod

    reset_native_invoke_probe()
    registry = _registry_with_production()
    root = discover_formal_scenario_root()
    execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="r4-ref",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert native_mod.NATIVE_FACADE_INVOKE_COUNT == 0


def test_reference_cannot_read_oracle_anchor() -> None:
    from gateway_conformance.runner.runtime import VerifiedAssetResolver

    _manifest, closure = load_validated_scenario(FORMAL_SCENARIO_ROOT)
    resolver = VerifiedAssetResolver(closure.assets)
    with pytest.raises(ConformanceValidationError, match="unknown verified asset"):
        resolver.read_bytes("row-hash-oracle-anchor")


def test_integration_invokes_facade_persist_and_reopen() -> None:
    from gateway_conformance.harness.canonical_row_hashes import integration as integration_mod

    reset_integration_probes()
    registry = _registry_with_production()
    root = discover_formal_scenario_root()
    outcome = execute_scenario_run(
        root,
        profile="integration",
        provider_id=None,
        run_id="r4-int",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"
    assert integration_mod.INTEGRATION_FACADE_INVOKE_COUNT >= 1
    assert integration_mod.INTEGRATION_PERSIST_COUNT == 1
    assert integration_mod.INTEGRATION_REOPEN_COUNT == 1


def test_corrupt_artifact_fails_integration(tmp_path: Path) -> None:
    from gateway_conformance.harness.canonical_row_hashes import integration as integration_mod

    registry = SubjectHarnessRegistry()

    class CorruptHarness(CanonicalRowHashesSubjectHarness):
        def seed(self, context: Any, plan: dict[str, object]) -> Any:
            from gateway_conformance.runner.types import PhaseReceipt

            self._integration_root = integration_mod.IntegrationArtifactSession().provision()
            return PhaseReceipt(phase="seed", outcome="COMPLETED")

        def stabilize_and_observe(
            self, context: Any, plan: dict[str, object], *, observation_point: str
        ) -> Any:
            from gateway_backend.artifacts import RetentionClass, build_logical_ref
            from gateway_backend.canonical_row_hash_ipc import (
                content_manifest_from_compute_result,
                persist_canonical_row_hash_stream,
                reopen_and_verify_canonical_row_hash_artifact,
            )
            from gateway_backend.compute import canonical_row_hashes_v1
            from gateway_backend.infrastructure.artifact_store import LocalArtifactStore
            from gateway_conformance.harness.canonical_row_hashes.result_payload import (
                declared_fields_from_plan,
                request_jcs_from_plan,
            )
            import io
            import pyarrow as pa

            ipc = context.resolver.read_bytes("table-stream")
            reader = pa.ipc.open_stream(io.BytesIO(ipc))
            output, result_jcs = canonical_row_hashes_v1(request_jcs_from_plan(plan), reader)
            content = content_manifest_from_compute_result(result_jcs)
            store = LocalArtifactStore(self._integration_root)
            ref = persist_canonical_row_hash_stream(
                store,
                logical_ref=build_logical_ref("canonical-row-hash", "corrupt"),
                reader=output,
                content_manifest=content,
                declared_table_schema_fields=declared_fields_from_plan(plan),
                retention_class=RetentionClass.OPERATION,
            )
            object_path = store._object_path(ref.logical_ref)  # noqa: SLF001
            object_path.write_bytes(b"truncated")
            fresh = LocalArtifactStore(self._integration_root)
            reopen_and_verify_canonical_row_hash_artifact(
                fresh,
                ref,
                expected_content=content,
                declared_table_schema_fields=declared_fields_from_plan(plan),
            )
            raise AssertionError("corrupt artifact must not pass reopen")

    registry.register(
        FORMAL_PRODUCTION_SUBJECT_KEY,
        lambda: CorruptHarness(),
        harness_provenance="production",
    )
    outcome = execute_scenario_run(
        FORMAL_SCENARIO_ROOT,
        profile="integration",
        provider_id=None,
        run_id="r4-corrupt",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"


def test_python_reference_and_rust_native_results_match() -> None:
    registry = _registry_with_production()
    root = discover_formal_scenario_root()
    ref_outcome = execute_scenario_run(
        root,
        profile="provider-matrix",
        provider_id="python-reference",
        run_id="r4-py",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    rust_outcome = execute_scenario_run(
        root,
        profile="provider-matrix",
        provider_id="rust-native",
        run_id="r4-rust",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    ref_digest = ref_outcome.result["expectations"][0]["actual_content_digest"]
    rust_digest = rust_outcome.result["expectations"][0]["actual_content_digest"]
    assert ref_digest == rust_digest


def test_duplicate_row_hashes_change_multiset_digest() -> None:
    from gateway_conformance.owner.arrow_row_hash_oracle import compute_row_hashes_from_ipc

    manifest, closure = load_validated_scenario(FORMAL_SCENARIO_ROOT)
    ipc = closure.assets["table-stream"].raw
    fields = cast(
        list[dict[str, Any]],
        manifest["stimulus"]["payload"]["value"]["declared_table_schema"]["fields"],
    )
    hashes = compute_row_hashes_from_ipc(ipc, fields)
    assert len(hashes) == 3
    assert len(set(hashes)) == 2
    assert multiset_digest_differs_from_deduped(hashes)


def test_dedupe_provider_observation_fails_matrix() -> None:
    from gateway_conformance.harness.canonical_row_hashes.result_payload import (
        build_row_hashes_observation,
        declared_fields_from_plan,
    )
    from gateway_conformance.owner.arrow_row_hash_oracle import compute_table_content_identity
    from gateway_conformance.runner.types import ObservationSet, PhaseReceipt

    registry = SubjectHarnessRegistry()

    class DedupeHarness(CanonicalRowHashesSubjectHarness):
        def stabilize_and_observe(
            self, context: Any, plan: dict[str, object], *, observation_point: str
        ) -> ObservationSet:
            ipc = context.resolver.read_bytes("table-stream")
            fields = declared_fields_from_plan(plan)
            row_count, raw_content_digest, sorted_hashes = compute_table_content_identity(
                ipc, fields
            )
            unique_sorted = sorted(set(sorted_hashes))
            buffer = bytearray()
            for row_hash in unique_sorted:
                buffer.extend(row_hash)
            from gateway_shared_kernel import (
                unordered_row_hashes_content_digest_from_sorted_row_buffer,
            )

            deduped_digest = unordered_row_hashes_content_digest_from_sorted_row_buffer(
                bytes(buffer),
                len(unique_sorted),
            ).digest_ref.value
            requests = plan["observation_requests"]
            request = next(
                item
                for item in cast(list[dict[str, Any]], requests)
                if str(item.get("expectation_id")) == "row-hashes"
            )
            binding = dict(request["contract_binding"])
            value = {
                "result_schema_version": 1,
                "contract_binding": {
                    "contract_id": binding["contract_id"],
                    "semantic_version": binding["semantic_version"],
                },
                "canonical_encoding_version": 1,
                "arrow_mapping_schema_version": 1,
                "table_schema_digest": "sha256:" + "0" * 64,
                "row_count": row_count,
                "raw_content_digest": deduped_digest,
                "diagnostics": [],
            }
            obs = build_row_hashes_observation(
                plan, observation_point=observation_point, value=value
            )
            return ObservationSet(
                observations=(obs,),
                receipt=PhaseReceipt(phase="stabilize_and_observe", outcome="COMPLETED"),
            )

    registry.register(
        FORMAL_PRODUCTION_SUBJECT_KEY,
        lambda: DedupeHarness(),
        harness_provenance="production",
    )
    outcome = execute_scenario_run(
        FORMAL_SCENARIO_ROOT,
        profile="provider-matrix",
        provider_id="python-reference",
        run_id="r4-dedupe",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "ASSERTION_FAILED"


def test_field_order_permutation_preserves_semantic_digest() -> None:
    from gateway_conformance.owner.arrow_row_hash_oracle import compute_table_content_identity

    manifest, closure = load_validated_scenario(FORMAL_SCENARIO_ROOT)
    ipc = closure.assets["table-stream"].raw
    fields = cast(
        list[dict[str, Any]],
        manifest["stimulus"]["payload"]["value"]["declared_table_schema"]["fields"],
    )
    _, digest_a, _ = compute_table_content_identity(ipc, fields)
    permuted = list(reversed(fields))
    _, digest_b, _ = compute_table_content_identity(ipc, permuted)
    assert digest_a == digest_b


def test_integration_stale_sidecar_rejects_harness() -> None:
    from gateway_conformance.harness.canonical_row_hashes import integration as integration_mod

    registry = SubjectHarnessRegistry()

    class StaleSidecarHarness(CanonicalRowHashesSubjectHarness):
        def seed(self, context: Any, plan: dict[str, object]) -> Any:
            from gateway_conformance.runner.types import PhaseReceipt

            self._integration_root = integration_mod.IntegrationArtifactSession().provision()
            return PhaseReceipt(phase="seed", outcome="COMPLETED")

        def stabilize_and_observe(
            self, context: Any, plan: dict[str, object], *, observation_point: str
        ) -> Any:
            from gateway_backend.artifacts import RetentionClass, build_logical_ref
            from gateway_backend.canonical_row_hash_ipc import (
                content_manifest_from_compute_result,
                persist_canonical_row_hash_stream,
                reopen_and_verify_canonical_row_hash_artifact,
            )
            from gateway_backend.compute import canonical_row_hashes_v1
            from gateway_backend.infrastructure.artifact_store import LocalArtifactStore
            from gateway_conformance.harness.canonical_row_hashes.result_payload import (
                declared_fields_from_plan,
                request_jcs_from_plan,
            )
            import io
            import pyarrow as pa

            ipc = context.resolver.read_bytes("table-stream")
            reader = pa.ipc.open_stream(io.BytesIO(ipc))
            output, result_jcs = canonical_row_hashes_v1(request_jcs_from_plan(plan), reader)
            content = content_manifest_from_compute_result(result_jcs)
            artifact_root = self._integration_root
            if artifact_root is None:
                raise ConformanceValidationError("integration artifact root not provisioned")
            store = LocalArtifactStore(artifact_root)
            ref = persist_canonical_row_hash_stream(
                store,
                logical_ref=build_logical_ref("canonical-row-hash", "stale-sidecar"),
                reader=output,
                content_manifest=content,
                declared_table_schema_fields=declared_fields_from_plan(plan),
                retention_class=RetentionClass.OPERATION,
            )
            sidecar = next(artifact_root.rglob("*.manifest.jcs"))
            sidecar.write_text('{"tampered":true}\n', encoding="utf-8")
            fresh = LocalArtifactStore(artifact_root)
            reopen_and_verify_canonical_row_hash_artifact(
                fresh,
                ref,
                expected_content=content,
                declared_table_schema_fields=declared_fields_from_plan(plan),
            )
            raise AssertionError("stale sidecar must not pass reopen")

    registry.register(
        FORMAL_PRODUCTION_SUBJECT_KEY,
        lambda: StaleSidecarHarness(),
        harness_provenance="production",
    )
    outcome = execute_scenario_run(
        FORMAL_SCENARIO_ROOT,
        profile="integration",
        provider_id=None,
        run_id="r4-stale",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"


def test_matrix_run_result_and_evidence_exclude_host_paths() -> None:
    import json

    suite = _run_matrix()
    forbidden = ("/root/", "/tmp/", "file:", "\\\\", "C:\\")
    for item in suite.cells:
        blob = json.dumps(item.outcome.result, sort_keys=True)
        if item.outcome.evidence is not None:
            blob += json.dumps(item.outcome.evidence, sort_keys=True)
        for marker in forbidden:
            assert marker not in blob, marker


def test_production_register_duplicate_raises() -> None:
    registry = SubjectHarnessRegistry()
    register_production_canonical_row_hashes_harness(registry)
    with pytest.raises(ConformanceValidationError, match="duplicate harness registration"):
        register_production_canonical_row_hashes_harness(registry)


def test_matrix_plan_excludes_golden_and_paths() -> None:
    manifest, closure = load_validated_scenario(FORMAL_SCENARIO_ROOT)
    for profile, provider in (("reference", None), ("integration", None)):
        plan = build_harness_plan(
            manifest,
            closure,
            RunParams(
                profile=profile,
                provider_id=provider,
                run_id="r4-plan",
                deterministic_seed="seed",
                logical_time_start="2026-01-01T00:00:00Z",
            ),
        )
        _walk_forbidden(plan, label="plan")
        assert FORBIDDEN_PROTOCOL_FIELDS.isdisjoint(plan.keys())


def test_fake_harness_cannot_pass_formal_cell() -> None:
    registry = SubjectHarnessRegistry()
    with registry._lock:  # noqa: SLF001
        registry._factories[FORMAL_PRODUCTION_SUBJECT_KEY] = lambda: FakeSubjectHarness()
    outcome = execute_scenario_run(
        FORMAL_SCENARIO_ROOT,
        profile="reference",
        provider_id=None,
        run_id="r4-fake",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"


def test_runner_still_unique_compare_authority() -> None:
    suite = _run_matrix()
    for item in suite.cells:
        result = item.outcome.result
        assert result["runner_result_schema_version"] == 1
        assert result["comparison_outcome"] in {"MATCH", "MISMATCH"}
        for row in result["expectations"]:
            assert "outcome" in row


def test_repeated_matrix_semantic_fingerprint_stable() -> None:
    suite_a = _run_matrix()
    suite_b = _run_matrix()
    assert matrix_semantic_fingerprint(suite_a.cells) == matrix_semantic_fingerprint(suite_b.cells)


def test_coverage_inventory_guard() -> None:
    executed = run_mapping_provider_matrix()
    assert_mapping_matrix_executed(executed)
    assert len(CANONICAL_SEMANTIC_KINDS) == 15


def test_wp5_r4_patch_sha_script_exists() -> None:
    assert PATCH_SHA_SCRIPT.is_file()


def _evidence_patch_sha() -> str:
    if not EVIDENCE_PATH.is_file():
        return ""
    for line in EVIDENCE_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("EXPECTED_SHA="):
            return line.split("=", 1)[1].strip()
    return ""


R4_ACCEPTED_COMMIT = "b747590ac6ffdfe0e00b320363ce429e663e358e"


def _worktree_matches_commit(commit: str) -> bool:
    if (
        subprocess.run(
            ["git", "diff", "--quiet", commit, "--", "."],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        != 0
    ):
        return False
    untracked = subprocess.run(
        ["git", "ls-files", "-o", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return untracked == ""


def test_wp5_r4_patch_sha_matches_worktree() -> None:
    if not _worktree_matches_commit(R4_ACCEPTED_COMMIT):
        pytest.skip("R4 patch SHA guard applies only on the exact accepted R4 tree")
    proc = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    sha = proc.stdout.split()[0]
    assert len(sha) == 64
    expected = _evidence_patch_sha()
    assert expected
    assert sha == expected


def test_wp5_r4_patch_sha_rejects_exclude_override() -> None:
    proc = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        env={**os.environ, "EXCLUDE": "other.md"},
        capture_output=True,
    )
    assert proc.returncode != 0
