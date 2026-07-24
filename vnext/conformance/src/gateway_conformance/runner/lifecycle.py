"""Fixed runner lifecycle (formal §7.2)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.protocol.digest import compute_run_evidence_content_digest
from gateway_conformance.protocol.validate import validate_run_evidence_bundle
from gateway_conformance.runner.compare import (
    compare_checkpoint,
    compare_observations,
    recompute_actual_digest,
    validate_observation_set,
)
from gateway_conformance.runner.diagnostics import sanitize_diagnostic
from gateway_conformance.runner.evidence import package_run_evidence, validate_environment_versions
from gateway_conformance.runner.observation_snapshot import snapshot_observations
from gateway_conformance.runner.plan import RunParams, build_harness_plan
from gateway_conformance.runner.registry import SubjectHarnessRegistry, subject_key_from_manifest
from gateway_conformance.runner.receipts import (
    receipt_diagnostics_for_state,
    validate_cleanup_receipt,
    validate_phase_receipt,
    validate_support_decision,
)
from gateway_conformance.runner.result import (
    apply_recovery_checkpoint_gate,
    build_not_run_expectations,
    build_runner_result,
)
from gateway_conformance.runner.runtime import (
    FaultSideChannel,
    HarnessRuntimeContext,
    LogicalClock,
    ProfileHandle,
    RunCapabilityTokens,
    RunIdentity,
    build_harness_context,
    build_resolver,
    unregister_run_tokens,
)
from gateway_conformance.runner.types import (
    ActualObservation,
    CleanupStatus,
    ComparisonRow,
    Diagnostic,
    PhaseReceipt,
    RunState,
)
from gateway_conformance.sanitize import sanitize_message
from gateway_conformance.scenario.validate import load_validated_scenario


@dataclass(frozen=True, slots=True)
class RunOutcome:
    result: dict[str, Any]
    evidence: dict[str, Any]


def _requested_expectation_ids(plan: dict[str, Any]) -> list[str]:
    return [str(item["expectation_id"]) for item in plan["observation_requests"]]


def _mark_harness_error(state: RunState, exc: Exception) -> None:
    state.harness_error = True
    state.runner_diagnostics.append(
        Diagnostic(code="harness-error", message=sanitize_message(str(exc))[:500])
    )


def _checkpoint_wire(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "checkpoint": checkpoint["checkpoint"],
        "outcome": checkpoint["outcome"],
        "content_digest": checkpoint.get("content_digest"),
    }


def _filter_trusted_observations(observations: list[ActualObservation]) -> list[ActualObservation]:
    trusted: list[ActualObservation] = []
    for item in observations:
        try:
            if recompute_actual_digest(item) == item.actual_content_digest:
                trusted.append(item)
        except ConformanceValidationError:
            continue
    return trusted


def _verify_fault_channel(
    fault: FaultSideChannel,
    plan: dict[str, Any],
    *,
    require_consumed: bool,
) -> None:
    if "fault" not in plan:
        return
    if require_consumed:
        if fault.arm_count != 1 or fault.consume_count != 1 or not fault.consumed:
            raise ConformanceValidationError(
                "fault must be armed once and consumed exactly once by harness"
            )
    elif fault.arm_count > 0 and not fault.consumed:
        raise ConformanceValidationError("fault armed but not consumed by harness")


def _rows_from_trusted_checkpoints(
    state: RunState,
    manifest: dict[str, Any],
) -> list[ComparisonRow] | None:
    if not any(str(item.get("outcome")) == "MISMATCH" for item in state.checkpoint_results):
        return None
    gated_source = build_not_run_expectations(manifest)
    try:
        return apply_recovery_checkpoint_gate(
            gated_source,
            state.checkpoint_results,
            expectation_digests=state.checkpoint_gate_expectation_digests,
            mismatch_expectation_ids=state.checkpoint_gate_mismatch_ids,
        )
    except ConformanceValidationError:
        return None


def _apply_gate_if_needed(
    track: str,
    state: RunState,
    rows: list[ComparisonRow],
) -> list[ComparisonRow]:
    if track != "recovery":
        return rows
    if not state.checkpoint_gate_mismatch_ids:
        return rows
    return apply_recovery_checkpoint_gate(
        rows,
        state.checkpoint_results,
        expectation_digests=state.checkpoint_gate_expectation_digests,
        mismatch_expectation_ids=state.checkpoint_gate_mismatch_ids,
    )


_SAFE_ENV_VERSIONS: list[dict[str, str]] = [
    {"component": "gateway-conformance", "version": "unknown"},
]


def _minimal_evidence_fallback(
    *,
    plan: dict[str, Any],
    cleanup: CleanupStatus,
    runner_diagnostics: list[Diagnostic],
    cleanup_diagnostics: list[Diagnostic],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "run_evidence_schema_version": 1,
        "execution_key": dict(plan["execution_key"]),
        "run_id": str(plan["run_id"]),
        "environment_versions": list(_SAFE_ENV_VERSIONS),
        "fault_receipt": None,
        "observations": [],
        "checkpoint_results": [],
        "cleanup": {
            "status": cleanup,
            "diagnostics": [item.to_wire() for item in cleanup_diagnostics],
        },
        "diagnostics": [item.to_wire() for item in runner_diagnostics],
        "content_digest": "sha256:" + "0" * 64,
    }
    evidence["content_digest"] = compute_run_evidence_content_digest(evidence)
    validate_run_evidence_bundle(evidence)
    return evidence


def _safe_fallback_runner_diagnostics(state: RunState) -> list[Diagnostic]:
    safe: list[Diagnostic] = []
    for item in state.runner_diagnostics:
        if item.code in ("harness-error", "evidence-packaging-failed"):
            safe.append(item)
    if not safe:
        safe.append(
            Diagnostic(code="harness-error", message="evidence packaging failed"),
        )
    return safe


def _finalize_run_outcome(
    *,
    state: RunState,
    plan_authority: dict[str, Any],
    manifest: dict[str, Any],
    track: str,
    rows: list[ComparisonRow],
    environment_versions: list[dict[str, str]],
) -> RunOutcome:
    safe_env: list[dict[str, str]] = []
    if state.validated_environment_versions is not None:
        safe_env = list(state.validated_environment_versions)
    else:
        try:
            safe_env = validate_environment_versions(environment_versions)
        except ConformanceValidationError as exc:
            _mark_harness_error(state, exc)

    rows_for_result = list(rows)
    try:
        rows_for_result = _apply_gate_if_needed(track, state, rows)
    except ConformanceValidationError as exc:
        _mark_harness_error(state, exc)
        rows_for_result = rows
    trusted_observations = _filter_trusted_observations(state.collected_observations)
    observations_for_evidence = (
        trusted_observations if state.harness_error else list(state.collected_observations)
    )
    if state.harness_error and not trusted_observations:
        observations_for_evidence = []

    runner_diag = list(state.runner_diagnostics)
    cleanup_diag = list(state.cleanup_diagnostics)

    try:
        result = build_runner_result(
            plan=plan_authority,
            rows=rows_for_result,
            unsupported=state.unsupported,
            harness_error=state.harness_error,
            cleanup=state.cleanup_status,
            diagnostics=runner_diag,
            cleanup_diagnostics=cleanup_diag,
        )
        evidence = package_run_evidence(
            plan=plan_authority,
            environment_versions=safe_env,
            observations=observations_for_evidence,
            checkpoint_results=state.checkpoint_results,
            fault_receipt=state.fault_receipt,
            cleanup=state.cleanup_status,
            diagnostics=runner_diag,
            cleanup_diagnostics=cleanup_diag,
        )
        return RunOutcome(result=result, evidence=evidence)
    except Exception as exc:
        _mark_harness_error(state, exc)
        if not runner_diag or runner_diag[-1].code != "evidence-packaging-failed":
            state.runner_diagnostics.append(
                Diagnostic(
                    code="evidence-packaging-failed",
                    message=sanitize_message(str(exc))[:500],
                )
            )
        runner_diag = _safe_fallback_runner_diagnostics(state)
        safe_rows = rows_for_result
        if state.harness_error:
            checkpoint_rows = _rows_from_trusted_checkpoints(state, manifest)
            if checkpoint_rows is not None:
                safe_rows = checkpoint_rows
        trusted_obs = _filter_trusted_observations(state.collected_observations)
        try:
            result = build_runner_result(
                plan=plan_authority,
                rows=safe_rows,
                unsupported=False,
                harness_error=True,
                cleanup=state.cleanup_status,
                diagnostics=runner_diag,
                cleanup_diagnostics=cleanup_diag,
            )
            evidence = package_run_evidence(
                plan=plan_authority,
                environment_versions=_SAFE_ENV_VERSIONS,
                observations=trusted_obs if trusted_obs else [],
                checkpoint_results=list(state.checkpoint_results),
                fault_receipt=state.fault_receipt,
                cleanup=state.cleanup_status,
                diagnostics=runner_diag,
                cleanup_diagnostics=cleanup_diag,
            )
            return RunOutcome(result=result, evidence=evidence)
        except Exception:
            fallback_rows = build_not_run_expectations(manifest)
            result = build_runner_result(
                plan=plan_authority,
                rows=fallback_rows,
                unsupported=False,
                harness_error=True,
                cleanup=state.cleanup_status,
                diagnostics=runner_diag,
                cleanup_diagnostics=cleanup_diag,
            )
            evidence = _minimal_evidence_fallback(
                plan=plan_authority,
                cleanup=state.cleanup_status,
                runner_diagnostics=runner_diag,
                cleanup_diagnostics=cleanup_diag,
            )
            return RunOutcome(result=result, evidence=evidence)


def _record_phase_receipt(state: RunState, receipt: PhaseReceipt, *, prefix: str) -> None:
    state.runner_diagnostics.extend(receipt_diagnostics_for_state(receipt, prefix=prefix))


def execute_scenario_run(
    root: Path,
    *,
    profile: str,
    provider_id: str | None,
    run_id: str,
    deterministic_seed: str,
    clock: LogicalClock,
    environment_versions: list[dict[str, str]],
    registry: SubjectHarnessRegistry,
) -> RunOutcome:
    state = RunState()
    manifest, closure = load_validated_scenario(root)
    params = RunParams(
        profile=profile,
        provider_id=provider_id,
        run_id=run_id,
        deterministic_seed=deterministic_seed,
        logical_time_start=clock.now_iso(),
    )
    plan = build_harness_plan(manifest, closure, params)
    plan_authority = copy.deepcopy(plan)
    plan_harness = copy.deepcopy(plan)
    track = str(manifest["track"])
    request_ids = _requested_expectation_ids(plan_authority)
    manifest_expected = list(manifest["expected"])

    harness = None
    context: HarnessRuntimeContext | None = None
    capability_tokens: RunCapabilityTokens | None = None
    fault_channel: FaultSideChannel | None = None
    profile_handle: ProfileHandle | None = None
    rows = build_not_run_expectations(manifest)

    try:
        try:
            state.validated_environment_versions = validate_environment_versions(
                environment_versions
            )
        except ConformanceValidationError as exc:
            _mark_harness_error(state, exc)
            return _finalize_run_outcome(
                state=state,
                plan_authority=plan_authority,
                manifest=manifest,
                track=track,
                rows=rows,
                environment_versions=environment_versions,
            )

        key = subject_key_from_manifest(manifest)
        harness = registry.resolve(key)
        from gateway_conformance.owner.canonical_row_hash import FORMAL_SCENARIO_ID
        from gateway_conformance.runner.fake.harness import FakeSubjectHarness

        if str(manifest.get("scenario_id")) == FORMAL_SCENARIO_ID and isinstance(
            harness, FakeSubjectHarness
        ):
            raise ConformanceValidationError(
                "fake harness cannot execute formal canonical-row-hash scenario"
            )
        decision = harness.preflight(plan_harness)
        validate_support_decision(decision)
        state.runner_diagnostics.extend(
            receipt_diagnostics_for_state(decision, prefix="preflight"),
        )
        if decision.support == "UNSUPPORTED":
            state.unsupported = True
            state.unsupported_reason = decision.reason_code
            state.runner_diagnostics.append(
                sanitize_diagnostic(
                    Diagnostic(
                        code="unsupported-reason",
                        message=str(decision.reason_code or "unsupported"),
                    )
                )
            )
            rows = build_not_run_expectations(manifest)
            return _finalize_run_outcome(
                state=state,
                plan_authority=plan_authority,
                manifest=manifest,
                track=track,
                rows=rows,
                environment_versions=environment_versions,
            )

        profile_handle = ProfileHandle(profile=profile, provider_id=provider_id)
        profile_handle.provision()
        state.provision_count = profile_handle.provision_count
        state.subject_started = True
        if "fault" in plan_authority:
            fault_channel = FaultSideChannel()

        context, capability_tokens = build_harness_context(
            identity=RunIdentity(run_id=run_id, deterministic_seed=deterministic_seed),
            clock=clock,
            profile=profile_handle.view(),
            resolver=build_resolver(closure),
            fault=fault_channel,
        )

        seed_receipt = harness.seed(context, plan_harness)
        validate_phase_receipt(seed_receipt, "seed")
        _record_phase_receipt(state, seed_receipt, prefix="seed")
        if seed_receipt.outcome == "FAILED":
            raise ConformanceValidationError(seed_receipt.stable_code or "seed-failed")

        if fault_channel is not None:
            fault_channel.arm()
            state.fault_receipt = fault_channel.receipt()

        invoke_receipt = harness.invoke(context, plan_harness)
        validate_phase_receipt(invoke_receipt, "invoke")
        _record_phase_receipt(state, invoke_receipt, prefix="invoke")
        if invoke_receipt.outcome == "FAILED":
            raise ConformanceValidationError(invoke_receipt.stable_code or "invoke-failed")

        if "fault" in plan_authority and fault_channel is not None:
            _verify_fault_channel(fault_channel, plan_authority, require_consumed=True)
            state.fault_receipt = fault_channel.receipt()

        observation_points: list[str]
        if track == "recovery":
            observation_points = ["after-failure", "after-recovery"]
        else:
            observation_points = ["final"]

        phase_observations: dict[str, list[ActualObservation]] = {}
        for point in observation_points:
            if point == "after-recovery" and "recovery_trigger" in plan_authority:
                recovery_receipt = harness.drive_recovery(context, plan_harness)
                validate_phase_receipt(recovery_receipt, "drive_recovery")
                _record_phase_receipt(state, recovery_receipt, prefix="drive-recovery")
                if recovery_receipt.outcome == "FAILED":
                    raise ConformanceValidationError(
                        recovery_receipt.stable_code or "recovery-failed"
                    )
            context.stable_read_barrier()
            obs_set = harness.stabilize_and_observe(context, plan_harness, observation_point=point)
            validate_phase_receipt(obs_set.receipt, "stabilize_and_observe")
            _record_phase_receipt(state, obs_set.receipt, prefix="observe")
            if obs_set.receipt.outcome == "FAILED":
                raise ConformanceValidationError(obs_set.receipt.stable_code or "observe-failed")
            validate_observation_set(
                list(obs_set.observations),
                observation_point=point,
                requested_ids=request_ids,
            )
            snapped = snapshot_observations(list(obs_set.observations))
            phase_observations[point] = snapped
            state.collected_observations.extend(snapped)
            if track == "recovery":
                checkpoint = point.replace("-", "_")
                raw_checkpoint = compare_checkpoint(
                    closure,
                    snapped,
                    checkpoint=checkpoint,
                    manifest_entries=manifest_expected,
                )
                state.checkpoint_results.append(_checkpoint_wire(raw_checkpoint))
                if str(raw_checkpoint.get("outcome")) == "MISMATCH":
                    outcomes = dict(raw_checkpoint.get("expectation_outcomes", {}))
                    digests = dict(raw_checkpoint.get("expectation_digests", {}))
                    for eid, outcome in outcomes.items():
                        if outcome != "MISMATCH":
                            continue
                        eid_key = str(eid)
                        state.checkpoint_gate_mismatch_ids.add(eid_key)
                        if (
                            eid_key not in state.checkpoint_gate_expectation_digests
                            and eid_key in digests
                        ):
                            state.checkpoint_gate_expectation_digests[eid_key] = str(
                                digests[eid_key]
                            )

        final_point = observation_points[-1]
        final_observations = phase_observations.get(final_point, [])
        if state.harness_error:
            rows = build_not_run_expectations(manifest)
        else:
            rows = compare_observations(
                closure,
                final_observations,
                manifest_entries=manifest_expected,
            )

    except ConformanceValidationError as exc:
        _mark_harness_error(state, exc)
        if state.checkpoint_results:
            checkpoint_rows = _rows_from_trusted_checkpoints(state, manifest)
            if checkpoint_rows is not None:
                rows = checkpoint_rows
            else:
                final_point = "after-recovery" if track == "recovery" else "final"
                final_obs = [
                    item
                    for item in state.collected_observations
                    if item.observation_point == final_point
                ]
                if final_obs:
                    try:
                        rows = compare_observations(
                            closure,
                            final_obs,
                            manifest_entries=manifest_expected,
                        )
                    except ConformanceValidationError:
                        rows = build_not_run_expectations(manifest)
                else:
                    rows = build_not_run_expectations(manifest)
        elif state.collected_observations and not state.unsupported:
            try:
                final_point = "after-recovery" if track == "recovery" else "final"
                final_obs = [
                    item
                    for item in state.collected_observations
                    if item.observation_point == final_point
                ]
                if final_obs:
                    rows = compare_observations(
                        closure,
                        final_obs,
                        manifest_entries=manifest_expected,
                    )
                else:
                    rows = build_not_run_expectations(manifest)
            except ConformanceValidationError:
                rows = build_not_run_expectations(manifest)
        else:
            rows = build_not_run_expectations(manifest)
    except Exception as exc:
        _mark_harness_error(state, ConformanceValidationError(str(exc)))
        checkpoint_rows = _rows_from_trusted_checkpoints(state, manifest)
        rows = (
            checkpoint_rows if checkpoint_rows is not None else build_not_run_expectations(manifest)
        )
    finally:
        cleanup_status: CleanupStatus = "CLEAN"
        cleanup_diag: list[Diagnostic] = []
        if harness is not None and context is not None and state.subject_started:
            try:
                cleanup = harness.cleanup_subject(context)
                validate_cleanup_receipt(cleanup)
                cleanup_status = cleanup.status
                cleanup_diag = [sanitize_diagnostic(item) for item in cleanup.diagnostics]
            except Exception as exc:
                cleanup_status = "FAILED"
                cleanup_diag = [
                    Diagnostic(
                        code="cleanup-failed",
                        message=sanitize_message(str(exc))[:200],
                    )
                ]
            if fault_channel is not None:
                try:
                    if "fault" in plan_authority:
                        _verify_fault_channel(
                            fault_channel,
                            plan_authority,
                            require_consumed=not state.harness_error,
                        )
                except ConformanceValidationError as exc:
                    _mark_harness_error(state, exc)
                fault_channel.disarm()
                if "fault" in plan_authority:
                    state.fault_receipt = fault_channel.receipt()
            if profile_handle is not None:
                try:
                    if state.subject_started and profile_handle.provision_count != 1:
                        raise ConformanceValidationError("profile provision count must be 1")
                    profile_handle.teardown()
                    if state.subject_started and profile_handle.teardown_count != 1:
                        raise ConformanceValidationError("profile teardown count must be 1")
                except Exception as exc:
                    _mark_harness_error(state, exc)
                    if cleanup_status == "CLEAN":
                        cleanup_status = "FAILED"
                    cleanup_diag.append(
                        sanitize_diagnostic(
                            Diagnostic(
                                code="profile-teardown-failed",
                                message=sanitize_message(str(exc))[:500],
                            )
                        )
                    )
        state.cleanup_status = cleanup_status
        state.cleanup_diagnostics = cleanup_diag
        if capability_tokens is not None:
            unregister_run_tokens(
                clock_token=capability_tokens.clock_token,
                fault_token=capability_tokens.fault_token,
            )

    return _finalize_run_outcome(
        state=state,
        plan_authority=plan_authority,
        manifest=manifest,
        track=track,
        rows=rows,
        environment_versions=environment_versions,
    )
