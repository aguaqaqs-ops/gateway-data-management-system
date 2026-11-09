#!/usr/bin/env bash
# S6 node lifecycle inherited from I r3; only unique Luna executes on a dedicated CT.
set -euo pipefail
subject=${1:?clean committed worktree required}
evidence=${2:?new absolute external evidence directory required}
session=${3:?unique session name required}
expected=${4:?fixed independently reviewed candidate HEAD required}
case ${GATEWAY_S6_TEST_NODE_ALIAS:?record the actual SSH alias} in
  ct108-gw-dms-04|ct108-gw-dms-05|ct108-gw-dms|ct107-gw-dms-06|ct109-gw-dms-07) ;;
  *) exit 2 ;;
esac
subject=$(realpath "$subject")
evidence=$(realpath -m "$evidence")
cd "$subject"
test "$(git rev-parse HEAD)" = "$expected"
test -z "$(git status --porcelain)"
test -L legacy
test "$(readlink legacy)" = /home/dev/gateway-data-management-system/legacy
test ! -e "$evidence"
case "$evidence/" in "$subject/"*) exit 2 ;; esac
busy=/home/dev/gdds-node-busy.d
active_pid=
active_label=
idle_scene() {
  local phase=$1 containers listeners
  printf 'SCENE_START phase=%s utc=%s\n' "$phase" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  containers=$(timeout --kill-after=2s 20s docker ps -q) || return 1
  listeners=$(timeout --kill-after=2s 10s ss -H -ltn 'sport = :8000') || return 1
  if test -n "$containers" || test -n "$listeners"; then
    printf 'SCENE_CONFLICT phase=%s running_container_ids=%s port8000=%s\n' \
      "$phase" "$containers" "$listeners"
    return 1
  fi
  timeout --kill-after=2s 15s python3 - "$phase" <<'PY'
import os
import sys
from pathlib import Path

names = {"dolt", "cargo", "rustc", "rustfmt", "clippy-driver", "pytest", "ruff", "mypy",
         "maturin", "uv", "uvx", "npm", "node", "docker", "docker-compose"}
tokens = {"pytest", "mypy", "gateway_backend", "gateway_repository_service"}
scripts = {"run-tests.sh", "uv-consume.sh", "run-real-backend-e2e.sh"}
conflicts = []
for directory in Path("/proc").iterdir():
    if not directory.name.isdecimal() or int(directory.name) == os.getpid():
        continue
    try:
        comm = (directory / "comm").read_text().strip()
        arguments = (directory / "cmdline").read_bytes().split(b"\0")
    except (FileNotFoundError, ProcessLookupError):
        continue
    except OSError:
        print(f"SCENE_UNKNOWN pid={directory.name}")
        raise SystemExit(2)
    words = [argument.decode("utf-8", errors="replace") for argument in arguments if argument]
    if comm in names or any(word in tokens or Path(word).name in scripts for word in words):
        conflicts.append((directory.name, comm))
for pid, comm in conflicts:
    print(f"SCENE_ACTIVE phase={sys.argv[1]} pid={pid} comm={comm}")
if conflicts:
    raise SystemExit(1)
print(f"SCENE_IDLE phase={sys.argv[1]}")
PY
}
active_group_alive() {
  kill -0 -- "-$active_pid" 2>/dev/null || kill -0 "$active_pid" 2>/dev/null
}
stop_active_group() {
  test -n "$active_pid" || return 0
  printf 'COMMAND_CLEANUP label=%s pgid=%s\n' "$active_label" "$active_pid"
  if active_group_alive; then
    kill -TERM -- "-$active_pid" 2>/dev/null
    kill -TERM "$active_pid" 2>/dev/null
    deadline=$((SECONDS + 30))
    while active_group_alive && test "$SECONDS" -lt "$deadline"; do
      sleep 1
    done
    if active_group_alive; then
      printf 'COMMAND_CLEANUP_ESCALATE pgid=%s signal=KILL\n' "$active_pid"
      kill -KILL -- "-$active_pid" 2>/dev/null
      kill -KILL "$active_pid" 2>/dev/null
      deadline=$((SECONDS + 5))
      while active_group_alive && test "$SECONDS" -lt "$deadline"; do
        sleep 1
      done
    fi
  fi
  if active_group_alive; then
    printf 'COMMAND_CLEANUP_UNKNOWN label=%s pid=%s\n' "$active_label" "$active_pid"
    return 1
  fi
  wait "$active_pid"
  child_result=$?
  printf 'COMMAND_CLEANUP_WAIT label=%s pid=%s exit=%s\n' "$active_label" "$active_pid" "$child_result"
  if kill -0 -- "-$active_pid" 2>/dev/null || kill -0 "$active_pid" 2>/dev/null; then
    return 1
  fi
  active_pid=
  return 0
}
finish() {
  local result=$? cleanup_ok=1 release_result
  trap - EXIT
  trap '' INT TERM
  set +e
  printf 'CHECKS_EXIT=%s\n' "$result"
  stop_active_group || cleanup_ok=0
  idle_scene postflight || cleanup_ok=0
  git status --short
  if test "$(git rev-parse HEAD)" != "$expected" || test -n "$(git status --porcelain)"; then
    result=1
  fi
  if test "$(cat "$busy/session" 2>/dev/null)" != "$session"; then
    cleanup_ok=0
    printf 'node_marker=OWNERSHIP_MISMATCH\n'
  elif test "$cleanup_ok" -eq 1; then
    rm "$busy/session" "$busy/purpose" "$busy/started_utc"
    release_result=$?
    if test "$release_result" -eq 0; then
      rmdir "$busy"
      release_result=$?
    fi
    if test "$release_result" -ne 0; then
      cleanup_ok=0
      if test -d "$busy"; then
        printf '%s\n' "$session" > "$busy/session"
        printf 'cleanup-failed utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$busy/cleanup-failed"
      fi
    fi
    printf 'node_marker_release_exit=%s\n' "$release_result"
  else
    printf 'cleanup-failed utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$busy/cleanup-failed"
    printf 'node_marker=RETAINED_CLEANUP_UNKNOWN\n'
  fi
  if test "$cleanup_ok" -ne 1; then result=1; fi
  printf 'END hostname=%s utc=%s head=%s exit=%s\n' "$(hostname)" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(git rev-parse HEAD)" "$result"
  exit "$result"
}
mkdir "$busy"
trap finish EXIT
trap 'printf "SIGNAL=INT\n"; exit 130' INT
trap 'printf "SIGNAL=TERM\n"; exit 143' TERM
printf '%s\n' "$session" > "$busy/session"
printf '%s\n' 'S6 real t4 minimal chain; fixed reviewed source, normal local image build' > "$busy/purpose"
date -u +%Y-%m-%dT%H:%M:%SZ > "$busy/started_utc"
printf 'START hostname=%s alias=%s utc=%s head=%s\n' "$(hostname)" \
  "$GATEWAY_S6_TEST_NODE_ALIAS" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$expected"
idle_scene preflight
mkdir -p "$evidence"
export PATH=/home/dev/.cargo/bin:$PATH
unset RUSTUP_TOOLCHAIN RUSTUP_HOME CARGO_HOME
export UV_OFFLINE=1 CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=4
export TMPDIR=/home/dev/gdds-test-tmp
unset GATEWAY_TEST_BASETEMP
export CARGO_TARGET_DIR="$evidence/cargo-target"
mkdir -p "$TMPDIR"
printf 'cache_source=preloaded_per_node_uv_and_cargo; network=offline\n'
run_check() {
  local label=$1 result
  shift
  printf 'STEP_START %s utc=%s\n' "$label" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  active_label=$label
  setsid "$@" > "$evidence/$label.log" 2>&1 &
  active_pid=$!
  printf 'COMMAND_START label=%s pid=%s pgid=%s\n' "$label" "$active_pid" "$active_pid"
  set +e
  wait "$active_pid"
  result=$?
  set -e
  if kill -0 -- "-$active_pid" 2>/dev/null; then
    printf 'COMMAND_DESCENDANTS_REMAIN pgid=%s\n' "$active_pid"
    return 1
  fi
  active_pid=
  cat "$evidence/$label.log"
  printf 'STEP_END %s exit=%s utc=%s\n' "$label" "$result" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  sha256sum "$evidence/$label.log"
  return "$result"
}
assets="$subject/docs/backend-vnext/refactoring/formal/plans/p6-s6-assets"
input_root=${GATEWAY_REAL_DUMP_ROOT:?own copied standard input root required}
oracle_root=${GATEWAY_S6_ORACLE_ROOT:?external SHA-pinned old B JSON copies required}
export GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1
export GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-578e079b762e
export GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES=1
export GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE=gateway-p2r1-repository:lock-6dc9659f0aee
export GATEWAY_REPOSITORY_BASE_IMAGE=gateway-p2r1-repository:lock-6dc9659f0aee
export GATEWAY_REPOSITORY_SERVICE_IMAGE="gateway-repository-service:s6-t4-${expected:0:12}"
export GATEWAY_DOCKER_BUILD_NETWORK=none
export GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_THREADS=1
export GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_MEMORY_BUDGET_BYTES=25769803776
export GATEWAY_BACKEND_OPERATION_WORKER_MEMORY_ENVELOPE_BYTES=34359738368
export GATEWAY_BACKEND_OPERATION_WORKER_MEMORY_RESERVE_BYTES=8589934592
unset GATEWAY_COMPOSE_GATE_PREBUILT HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
run_check disk-before df -B1 "$subject" "$evidence" /var/lib/docker
run_check memory-before cat /proc/meminfo
run_check backend-dependency docker image inspect "$GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE" --format '{{json .RootFS.Layers}}'
run_check repository-dependency docker image inspect "$GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE" --format '{{json .RootFS.Layers}}'
build_input=$(git rev-parse HEAD:vnext/rust)
run_check sync-backend env GATEWAY_RUST_BUILD_INPUT="$build_input" \
  ./vnext/scripts/uv-consume.sh -C vnext/backend sync --reinstall-package gateway-compute-python
run_check native-build-input ./vnext/scripts/check-rust-extension-build-input.sh
run_check repository-image ./vnext/scripts/build-repository-service-image.sh
run_check prepare ./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync python - \
  --worktree "$subject" --candidate-head "$expected" --input-root "$input_root" \
  --assets "$oracle_root" --evidence "$evidence/journey" --compose-name "s6-t4-${expected:0:12}" \
  --prepare-only < "$assets/t4-evidence.py"
run_check t4 ./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync python - \
  --worktree "$subject" --candidate-head "$expected" --input-root "$input_root" \
  --assets "$oracle_root" --evidence "$evidence/journey" --compose-name "s6-t4-${expected:0:12}" \
  < "$assets/t4-evidence.py"
run_check disk-after df -B1 "$subject" "$evidence" /var/lib/docker
