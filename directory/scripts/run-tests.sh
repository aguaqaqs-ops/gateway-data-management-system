#!/usr/bin/env bash
# Directory component gate. Capture stdout/stderr to a file outside the worktree.
set -euo pipefail

if [[ "${1:-}" == --frontend ]]; then
  printf 'entry_argv='
  printf '%q ' "$0" "$@"
  printf '\n'
  shift
  exec "$(dirname "$0")/run-frontend-tests.sh" "$@"
fi

repo="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
service="$repo/directory/service"
lock="$service/uv.lock"
start_head="$(git -C "$repo" rev-parse HEAD)"
expected="${GDDS_DIRECTORY_TEST_HEAD:-}"
started=0
lock_before=""
run_dir=""

finish() {
  local result=$?
  trap - EXIT
  if (( started )); then
    local end_head end_lock
    end_head="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
    end_lock="$(sha256sum "$lock" 2>/dev/null | cut -d' ' -f1 || true)"
    if [[ "$end_head" != "$expected" || "$end_head" != "$start_head" ]]; then
      echo 'ERROR: HEAD changed during run' >&2
      (( result != 0 )) || result=1
    fi
    if [[ -z "$end_lock" || "$end_lock" != "$lock_before" ]]; then
      echo 'ERROR: service lock changed during run' >&2
      (( result != 0 )) || result=1
    fi
    if [[ -n "$(git -C "$repo" status --porcelain --untracked-files=all)" ]]; then
      echo 'ERROR: worktree changed during run' >&2
      (( result != 0 )) || result=1
    fi
  fi
  if [[ -n "$run_dir" ]] && ! rm -rf -- "$run_dir"; then
    echo 'ERROR: could not clean the temporary environment' >&2
    (( result != 0 )) || result=1
  fi
  if (( started )); then
    printf 'end_utc=%s\nend_head=%s\nlock_sha256_end=%s\nrunner_exit=%s\n' "$(date -u +%FT%TZ)" "$end_head" "$end_lock" "$result"
  fi
  exit "$result"
}
trap finish EXIT

if [[ -f "$lock" ]]; then lock_before="$(sha256sum "$lock" | cut -d' ' -f1)"; fi
started=1
printf 'hostname=%s\nstart_utc=%s\nstart_head=%s\nlock_sha256_start=%s\nargv=' "$(hostname)" "$(date -u +%FT%TZ)" "$start_head" "$lock_before"
printf '%q ' "$0" "$@"
printf '\n'
if [[ "${1:-}" != --service ]]; then
  echo 'usage: run-tests.sh --service [pytest arguments...]' >&2
  exit 2
fi
shift
if [[ "$(hostname)" != gw-dms-06 ]]; then
  echo 'service checks must run on gw-dms-06' >&2
  exit 2
fi
if [[ ! "$expected" =~ ^[0-9a-f]{40}$ || "$expected" != "$start_head" ]]; then
  echo 'GDDS_DIRECTORY_TEST_HEAD must be the full expected HEAD' >&2
  exit 2
fi
if [[ -n "$(git -C "$repo" status --porcelain --untracked-files=all)" ]]; then
  echo 'clean committed worktree required' >&2
  exit 2
fi
if [[ "${UV_OFFLINE:-}" != 1 ]]; then
  echo 'UV_OFFLINE=1 is required' >&2
  exit 2
fi
if [[ -z "${TMPDIR:-}" || "$TMPDIR" != /* || ! -d "$TMPDIR" ]]; then
  echo 'TMPDIR must name an existing absolute directory outside the worktree' >&2
  exit 2
fi
tmp="$(realpath "$TMPDIR")"
if [[ "$tmp" != /home/dev/gdds-test-tmp ]]; then
  echo 'TMPDIR must resolve to /home/dev/gdds-test-tmp' >&2
  exit 2
fi
if [[ ! -f "$lock" ]]; then echo 'missing service uv.lock' >&2; exit 2; fi
# A per-run environment keeps all generated state outside the checkout.
run_dir="$(mktemp -d "$tmp/gdds-directory-service.XXXXXXXX")"
# Remove ambient uv/index/virtualenv settings. UV_CACHE_DIR may select a
# prefilled local cache; never print its value or any proxy credentials.
cache="${UV_CACHE_DIR:-/home/dev/.cache/uv}"
cache_resolved="$(realpath -m "$cache")"
cache="$cache_resolved"
if [[ "$cache_resolved" == "$repo" || "$cache_resolved" == "$repo/"* ]]; then
  echo 'UV cache must be outside the worktree' >&2
  exit 2
fi
manifest="${GDDS_DIRECTORY_CACHE_MANIFEST:-}"
if [[ "$manifest" != /* || ! -f "$manifest" ]]; then
  echo 'GDDS_DIRECTORY_CACHE_MANIFEST must be an absolute manifest path' >&2
  exit 2
fi
uv_bin="$(command -v uv)"
python3 -I "$repo/directory/scripts/service_inputs.py" verify "$manifest" "$cache" "$lock" "$uv_bin" "$repo"
python_bin="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["python_path"])' "$manifest")"
common=(env -i "PATH=$PATH" "HOME=/home/dev" "TMPDIR=$tmp" "UV_OFFLINE=1" "UV_NO_CONFIG=1" "UV_PYTHON_DOWNLOADS=never" "UV_CACHE_DIR=$cache" "UV_PROJECT_ENVIRONMENT=$run_dir/venv" "PYTHONDONTWRITEBYTECODE=1" "RUFF_CACHE_DIR=$run_dir/ruff" "MYPY_CACHE_DIR=$run_dir/mypy")
cd "$service"
"${common[@]}" "$uv_bin" sync --locked --offline --no-config --python "$python_bin"
mkdir -m 700 "$run_dir/private"
(cd "$run_dir" && env -i "PATH=$repo/directory/bin:$run_dir/venv/bin:$PATH" "HOME=/home/dev" \
  "PYTHONDONTWRITEBYTECODE=1" "GDDS_DIRECTORY_DB=$run_dir/private/directory.sqlite" gdds-directory status)
"${common[@]}" "$uv_bin" run --locked --offline --no-config --no-sync ruff check .
"${common[@]}" "$uv_bin" run --locked --offline --no-config --no-sync mypy
"${common[@]}" "$uv_bin" run --locked --offline --no-config --no-sync python -m pytest -o "cache_dir=$run_dir/pytest" "$@"
