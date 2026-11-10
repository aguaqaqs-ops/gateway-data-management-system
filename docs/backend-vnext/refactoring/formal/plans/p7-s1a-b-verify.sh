#!/usr/bin/env bash
# B focused/format verification. Run on ct107-gw-dms-06 after SCRIPT_GO.
set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo 'usage: bash p7-s1a-b-verify.sh B_SHA CLEAN_WORKTREE NEW_LOG_DIR SESSION' >&2
    exit 2
fi
candidate=$1
worktree=$2
logdir=$3
session=$4
[[ $candidate =~ ^[0-9a-f]{40}$ && $session =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]] || exit 2
[[ $worktree = /* && $logdir = /* && -d $worktree && ! -e $logdir ]] || exit 2
# Resolve before creating anything; log output must be outside the worktree.
worktree=$(realpath -e -- "$worktree")
log_parent=$(realpath -e -- "$(dirname -- "$logdir")")
logdir="$log_parent/$(basename -- "$logdir")"
[[ $logdir != "$worktree" && $logdir != "$worktree/"* ]] || exit 2
[[ $(hostname) = gw-dms-06 ]] || { echo 'wrong test node' >&2; exit 2; }
mkdir -- "$logdir"
log="$logdir/verification.log"
busy=/home/dev/gdds-node-busy.d
marker="$busy/p7-s1a-b-$session.owner"
S=00ca325c2ed6d705abfa39e9528ef148e6029cfc
plan=docs/backend-vnext/refactoring/formal/plans
script_path="$plan/p7-s1a-b-verify.sh"
draft_path="$plan/p7-s1a-b-verification.md"

run() {
    local label="$1"
    shift
    local result
    printf '\nCHECK: %s\nCOMMAND:' "$label"
    printf ' %q' "$@"
    printf '\n'
    if "$@"; then result=0; else result=$?; fi
    printf 'ORIGINAL_EXIT=%s\n' "$result"
    return "$result"
}

capture() {
    local label="$1"
    local output="$2"
    shift 2
    local result
    printf '\nCHECK: %s\nCOMMAND:' "$label"
    printf ' %q' "$@"
    printf '\n'
    if "$@" > "$output" 2>&1; then result=0; else result=$?; fi
    cat -- "$output"
    printf 'ORIGINAL_EXIT=%s\n' "$result"
    return "$result"
}

assert_text() {
    local label="$1"
    local actual="$2"
    local expected="$3"
    if [[ $actual = "$expected" ]]; then
        printf 'ASSERT %s: PASS (exit 0)\n' "$label"
    else
        printf 'ASSERT %s: FAIL (exit 1)\nexpected=%q\nactual=%q\n' "$label" "$expected" "$actual"
        return 1
    fi
}

verify() (
    set -euo pipefail
    # A subshell keeps this EXIT trap and resource ownership local to one run.
    acquired=0
    compose_started=0
    finish() {
        local original=$?
        local final_result=$original
        local result
        trap - EXIT
        set +e
        printf '\n## Final state (also recorded after failure)\n'
        run 'end hostname' hostname
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        run 'end UTC' date -u +%Y-%m-%dT%H:%M:%SZ
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        capture 'end HEAD' "$logdir/end-head.out" git rev-parse HEAD
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        assert_text 'end HEAD equals candidate' "$(cat "$logdir/end-head.out")" "$candidate"
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        capture 'end clean' "$logdir/end-status.out" git status --porcelain
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        assert_text 'end tracked/untracked clean' "$(cat "$logdir/end-status.out")" ''
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        local may_release=1
        if [[ $compose_started -eq 1 ]]; then
            capture 'own Compose residual containers' "$logdir/compose-residual-containers.out" docker ps -aq --filter "label=com.docker.compose.project=$GATEWAY_COMPOSE_GATE_PROJECT_NAME"
            result=$?
            if [[ $result -ne 0 || -s $logdir/compose-residual-containers.out ]]; then
                may_release=0
                if [[ $final_result -eq 0 ]]; then final_result=1; fi
                echo 'RESOURCE_RELEASE=RETAINED; own Compose cleanup incomplete; do not touch other projects'
            fi
        fi
        if [[ $acquired -eq 1 && $may_release -eq 1 ]]; then
            if [[ -f $marker ]] && [[ $(cat "$marker") = "$ownership" ]]; then
                run 'remove own marker file' rm -- "$marker"
                result=$?
                if [[ $result -eq 0 ]]; then
                    run 'release own busy directory' rmdir -- "$busy"
                    result=$?
                fi
                if [[ $result -ne 0 ]]; then
                    echo 'RESOURCE_RELEASE=FAILED; preserve state for owner; do not remove other entries'
                    if [[ $final_result -eq 0 ]]; then final_result=$result; fi
                else
                    echo 'RESOURCE_RELEASE=RELEASED'
                fi
            else
                echo 'RESOURCE_RELEASE=FAILED; ownership mismatch; marker retained'
                if [[ $final_result -eq 0 ]]; then final_result=1; fi
            fi
        elif [[ $acquired -eq 0 ]]; then
            echo 'RESOURCE_RELEASE=NOT_ACQUIRED; no existing marker touched'
        fi
        printf 'RUN_ORIGINAL_EXIT=%s\nRUN_FINAL_EXIT=%s\n' "$original" "$final_result"
        exit "$final_result"
    }
    cd -- "$worktree"
    trap finish EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    printf 'P7-S1a B fixed focused verification\ncandidate=%s\nworktree=%s\nlog=%s\nsession=%s\n' "$candidate" "$worktree" "$log" "$session"
    run 'start hostname' hostname
    run 'start UTC' date -u +%Y-%m-%dT%H:%M:%SZ
    ownership="session=$session purpose=p7-s1a-b-static candidate=$candidate worktree=$worktree started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    # Do not nest an outer reservation. Existing busy directory is a conflict.
    run 'acquire node marker' mkdir -- "$busy"
    acquired=1
    printf '%s\n' "$ownership" > "$marker"
    printf 'OWNERSHIP=%s\n' "$ownership"
    capture 'start HEAD' "$logdir/start-head.out" git rev-parse HEAD
    assert_text 'HEAD equals B_SHA' "$(cat "$logdir/start-head.out")" "$candidate"
    capture 'start clean' "$logdir/start-status.out" git status --porcelain
    assert_text 'tracked/untracked clean' "$(cat "$logdir/start-status.out")" ''
    run 'B baseline ancestor' git merge-base --is-ancestor "$S" HEAD
    assert_text 'invoked script is candidate script' "$(realpath -e -- "$0")" "$worktree/$script_path"
    run 'script/draft SHA256' sha256sum "$script_path" "$draft_path"
    run 'diff check' git diff --check "$S" HEAD
    run 'unchanged locks and Rust sources' git diff --exit-code "$S" HEAD -- vnext/rust \
        vnext/backend/uv.lock vnext/repository_service/uv.lock vnext/repository_client/uv.lock \
        vnext/repository_contracts/uv.lock vnext/shared_kernel/uv.lock
    [[ -L legacy && -d legacy ]] || { echo 'missing reference legacy link'; exit 2; }
    [[ ! -v RUSTUP_TOOLCHAIN && ! -v RUSTUP_HOME && ! -v CARGO_HOME ]] || { echo 'unexpected Rust environment override'; exit 2; }
    export PATH=/home/dev/.cargo/bin:$PATH
    export TMPDIR=/home/dev/gdds-test-tmp
    export UV_OFFLINE=1 CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=4
    export CARGO_TARGET_DIR="$logdir/cargo-target"
    export GATEWAY_RUST_BUILD_INPUT
    GATEWAY_RUST_BUILD_INPUT=$(git rev-parse HEAD:vnext/rust)
    [[ -d $TMPDIR ]] || exit 2
    run 'uv version' uv --version
    [[ -z ${GATEWAY_COMPOSE_GATE_PREBUILT:-} ]] || { echo 'prebuilt bypass forbidden'; exit 2; }
    export GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1
    export GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-d054366c02fa
    export GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=gateway-p2r1-repository:lock-6dc9659f0aee
    export GATEWAY_DOCKER_BUILD_NETWORK=none
    for proxy_name in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do
        [[ -z ${!proxy_name:-} ]] || { echo 'forward proxy forbidden on 06'; exit 2; }
    done
    [[ -z ${DOCKER_HOST:-} && -z ${DOCKER_CONTEXT:-} ]] || { echo 'ambient Docker endpoint override forbidden'; exit 2; }
    run 'local Docker endpoint' python3 -I - <<'PYLOCAL'
import json
import subprocess
context = subprocess.check_output(["docker", "context", "show"], text=True).strip()
metadata = json.loads(subprocess.check_output(["docker", "context", "inspect", context]))[0]
assert metadata["Endpoints"]["docker"]["Host"].startswith("unix://"), "local Unix Docker daemon required"
print("DOCKER_ENDPOINT=local-unix")
PYLOCAL
    run 'local Docker daemon identity' docker info --format '{{.ID}} {{.Name}} {{.ServerVersion}}'
    capture 'candidate backend dependency inputs' "$logdir/backend-deps-input.json" ./vnext/scripts/build-backend-dependency-base.sh --print-input
    run 'candidate dependency-base input and RS lock identity' python3 -I - "$logdir/backend-deps-input.json" "$GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE" "$GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE" <<'PYCODE'
import hashlib
import json
from pathlib import Path
import subprocess
import sys
inputs = json.loads(Path(sys.argv[1]).read_bytes())
backend_tag, repository_tag = sys.argv[2:4]
assert inputs["image"] == backend_tag, "backend dependency input tag mismatch"
backend = json.loads(subprocess.check_output(["docker", "image", "inspect", backend_tag]))[0]
assert backend["Config"]["Labels"]["gateway.backend.dependency-input-sha256"] == inputs["input_sha256"], "backend dependency input label mismatch"
repository = json.loads(subprocess.check_output(["docker", "image", "inspect", repository_tag]))[0]
lock_sha = hashlib.sha256(Path("vnext/repository_service/uv.lock").read_bytes()).hexdigest()
assert repository["Config"]["Labels"]["gateway.p2r1.uv-lock-sha256"] == lock_sha, "RS dependency lock label mismatch"
assert repository_tag == "gateway-p2r1-repository:lock-" + lock_sha[:12], "RS dependency lock tag mismatch"
print("CANDIDATE_DEPENDENCY_INPUTS=MATCH; no build/pull/fallback performed")
PYCODE
    run 'candidate dependency inputs SHA256' sha256sum "$logdir/backend-deps-input.json"
    (cd vnext/rust && run 'rustc version' rustc --version && run 'cargo version' cargo --version &&
        run 'rustfmt version' rustfmt --version && run 'clippy version' clippy-driver --version)
    for package in shared_kernel repository_contracts repository_client backend repository_service; do
        if [[ $package = backend ]]; then
            run "offline sync $package" ./vnext/scripts/uv-consume.sh -C "vnext/$package" sync --reinstall-package gateway-compute-python
        else
            run "offline sync $package" ./vnext/scripts/uv-consume.sh -C "vnext/$package" sync
        fi
    done
    run 'installed extension identity' ./vnext/scripts/check-rust-extension-build-input.sh
    for package in shared_kernel repository_contracts repository_client backend repository_service; do
        run "ruff $package" ./vnext/scripts/uv-consume.sh -C "vnext/$package" run --no-sync ruff check .
        run "mypy $package" ./vnext/scripts/uv-consume.sh -C "vnext/$package" run --no-sync mypy
    done
    backend_files=(
        tests/test_archive_audit.py
        tests/test_archive_queries.py
        tests/test_archive_business_validation.py
        tests/test_archive_transactions.py
        tests/test_artifact_boundary.py
        tests/test_artifact_ref_conformance.py
        tests/test_artifact_staging_conformance.py
        tests/test_bundle_assembly.py
        tests/test_bundle_contracts.py
        tests/test_bundle_download.py
        tests/test_bundle_download_http.py
        tests/test_canonical_table_cache.py
        tests/test_canonical_table_store.py
        tests/test_commit_canonical_metadata.py
        tests/test_comparison_artifacts.py
        tests/test_comparison_cache.py
        tests/test_comparison_records.py
        tests/test_comparison_s3_d_production.py
        tests/test_computation_cache.py
        tests/test_configuration_facts.py
        tests/test_deployment_config.py
        tests/test_history_compare_jobs.py
        tests/test_history_projection.py
        tests/test_job_payload_decoding.py
        tests/test_mutation_planning.py
        tests/test_operation_checkpoint_contracts.py
        tests/test_operation_contracts.py
        tests/test_operation_job_recovery.py
        tests/test_operation_job_synthetic.py
        tests/test_operation_lease_session.py
        tests/test_operation_state.py
        tests/test_preview_application.py
        tests/test_preview_job_assemble.py
        tests/test_preview_job_materialize.py
        tests/test_preview_job_payload.py
        tests/test_preview_read_http.py
        tests/test_production_wiring.py
        tests/test_review_persistence.py
        tests/test_review_transactions.py
        tests/test_risk_candidate_cache.py
        tests/test_real_dump_canonical_metadata.py
        tests/test_real_dump_journey.py
        tests/test_risk_contracts.py
        tests/test_risk_evaluation.py
        tests/test_snapshot_artifact_faults.py
        tests/test_snapshot_artifact_roundtrip.py
        tests/test_snapshot_export_cache.py
        tests/test_source_package_staging.py
        tests/test_sqlite_submit_repository.py
        tests/test_sqlite_workspace_repository.py
        tests/test_storage_mutation_native.py
        tests/test_storage_projection_publication.py
        tests/test_submit_application.py
        tests/test_submit_artifact_protection.py
        tests/test_submit_domain.py
        tests/test_submit_finalize.py
        tests/test_submit_http.py
        tests/test_submit_idempotency.py
        tests/test_submit_import_builder.py
        tests/test_submit_job_payload.py
        tests/test_submit_job_prepare.py
        tests/test_submit_prepare_removed_tables.py
        tests/test_submit_read_http.py
        tests/test_submit_transactions.py
        tests/test_submit_worker.py
        tests/test_submit_worker_process.py
        tests/test_surface_assembly.py
        tests/test_surface_contracts.py
        tests/test_upload_application.py
        tests/test_upload_http.py
        tests/test_upload_streaming.py
        tests/test_workspace_artifact_store.py
        tests/test_workspace_domain.py
    )
    for file in "${backend_files[@]}"; do [[ -f vnext/backend/$file ]] || { echo "unknown focused test: $file"; exit 2; }; done
    run 'backend focused unit parallel' ./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest \
        "${backend_files[@]}" -m 'unit and not serial' -n 4
    run 'backend focused unit serial' ./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest \
        "${backend_files[@]}" -m 'unit and serial' -n 0
    run 'RS shared configuration vectors' ./vnext/scripts/uv-consume.sh -C vnext/repository_service run --no-sync pytest \
        tests/test_deployment_config.py -m unit -n 0
    export GATEWAY_COMPOSE_GATE_PROJECT_NAME="p7-s1a-b-$session"
    export GATEWAY_COMPOSE_GATE_SESSION="$session"
    export GATEWAY_COMPOSE_GATE_PROVENANCE_PATH="$logdir/compose-provenance.json"
    compose_started=1
    run 'history Compose ID decoder zero-write and restart' ./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest \
        tests/test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart -n 0
    run 'preserved Compose provenance SHA256' sha256sum "$logdir/compose-provenance.json"
    echo 'B_FOCUSED_CHECKS=PASS; representative existing Compose journey only; no multi-root mount/cgroup/real-input assertion'
)

# tee is waited for before hashing the final log. Preserve verifier and logger exits separately.
set +e
verify 2>&1 | tee "$log"
pipeline_status=("${PIPESTATUS[@]}")
set -e
verifier_exit=${pipeline_status[0]}
logger_exit=${pipeline_status[1]}
printf 'VERIFIER_EXIT=%s\nLOGGER_EXIT=%s\n' "$verifier_exit" "$logger_exit" > "$logdir/exit-codes.txt"
sha256sum "$log" > "$logdir/verification.log.sha256"
cat -- "$logdir/exit-codes.txt" "$logdir/verification.log.sha256"
if [[ $verifier_exit -ne 0 ]]; then exit "$verifier_exit"; fi
exit "$logger_exit"
