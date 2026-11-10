#!/usr/bin/env bash
# FE4a evidence wrapper (kickoff §3.8): runs a frontend evidence entry with a
# fixed pre-flight check and a fixed provenance record. The wrapper writes the
# log before the entry runs; when any check fails it exits non-zero without
# running the entry, and the log it already wrote gets a .sha256 sidecar
# (FE3c once ran the log dir into `$2` and the entry never ran).
#
# usage:
#   frontend/scripts/run-evidence-wrapper.sh --session <name> --worktree <abs-path>
#     --entry <entry-basename> --log-dir <abs-existing-dir>
#     [--shots-dir <abs-path-outside-worktree>] [-- <entry-arg>...]
#
# --entry is one of run-tests.sh, validate-upload-package.sh,
# run-real-backend-e2e.sh (resolved under <worktree>/frontend/scripts).
# The log file is <log-dir>/<session>-<entry>-<UTC>.log; its SHA256 goes to a
# .sha256 sidecar. Occupancy: run-tests.sh and validate-upload-package.sh are
# wrapped here with an atomic mkdir marker; run-real-backend-e2e.sh takes its
# own marker, so the wrapper only verifies the marker dir is absent first.
# A pre-existing marker is never taken over, reused, or removed, even when it
# is empty or names this session: the wrapper reports it and exits.
set -Eeuo pipefail

SESSION=""
WORKTREE=""
ENTRY=""
LOG_DIR=""
SHOTS_DIR=""
ENTRY_ARGS=()
SEPARATOR_SEEN=0

usage() {
  cat <<'USAGE'
usage: run-evidence-wrapper.sh --session <name> --worktree <abs-path> --entry <run-tests.sh|validate-upload-package.sh|run-real-backend-e2e.sh> --log-dir <abs-existing-dir> [--shots-dir <abs-path-outside-worktree>] [-- <entry-arg>...]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session) [[ -z "$SESSION" && $# -ge 2 ]] || { usage >&2; exit 2; }; SESSION="$2"; shift 2 ;;
    --worktree) [[ -z "$WORKTREE" && $# -ge 2 ]] || { usage >&2; exit 2; }; WORKTREE="$2"; shift 2 ;;
    --entry) [[ -z "$ENTRY" && $# -ge 2 ]] || { usage >&2; exit 2; }; ENTRY="$2"; shift 2 ;;
    --log-dir) [[ -z "$LOG_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; LOG_DIR="$2"; shift 2 ;;
    --shots-dir) [[ -z "$SHOTS_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; SHOTS_DIR="$2"; shift 2 ;;
    --) SEPARATOR_SEEN=1; shift; while [[ $# -gt 0 ]]; do ENTRY_ARGS+=("$1"); shift; done ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

fail() { printf 'wrapper_error=%s\n' "$1" >&2; exit "${2:-2}"; }

# Pre-flight checks: parameter count/shape, absolute paths, existing log dir,
# log dir outside the worktree, shots dir outside the worktree. Any failure
# exits before the entry runs.
[[ -n "$SESSION" ]] || fail "missing --session"
[[ -n "$WORKTREE" ]] || fail "missing --worktree"
[[ -n "$ENTRY" ]] || fail "missing --entry"
[[ -n "$LOG_DIR" ]] || fail "missing --log-dir"
[[ "$SESSION" =~ ^[a-z0-9][a-z0-9-]{1,62}$ ]] || fail "bad --session (want ^[a-z0-9][a-z0-9-]{1,62}$)"
case "$ENTRY" in
  run-tests.sh|validate-upload-package.sh|run-real-backend-e2e.sh) ;;
  *) fail "unknown --entry $ENTRY" ;;
esac
[[ "$WORKTREE" == /* ]] || fail "worktree must be absolute (got $WORKTREE)"
[[ "$LOG_DIR" == /* ]] || fail "log-dir must be absolute (got $LOG_DIR)"
[[ -d "$WORKTREE" ]] || fail "worktree is not a directory: $WORKTREE"
[[ -d "$LOG_DIR" ]] || fail "log dir does not exist: $LOG_DIR (wrapper runs nothing)"
WORKTREE_REAL="$(realpath -m -- "$WORKTREE")"
LOG_REAL="$(realpath -m -- "$LOG_DIR")"
[[ "$LOG_REAL" != "$WORKTREE_REAL" && "$LOG_REAL" != "$WORKTREE_REAL"/* ]] || fail "log dir must be outside the worktree (got $LOG_DIR)"
SHOTS_REAL=""
if [[ -n "$SHOTS_DIR" ]]; then
  [[ "$SHOTS_DIR" == /* ]] || fail "shots dir must be absolute (got $SHOTS_DIR)"
  SHOTS_REAL="$(realpath -m -- "$SHOTS_DIR")"
  [[ "$SHOTS_REAL" != "$WORKTREE_REAL" && "$SHOTS_REAL" != "$WORKTREE_REAL"/* ]] || fail "shots dir must be outside the worktree (got $SHOTS_DIR)"
fi

# With --shots-dir the wrapper supplies the entry's --screenshots argument.
# An explicit entry argument is accepted only when it names the same dir.
shoot_arg_index() {
  local i=0
  while [[ $i -lt ${#ENTRY_ARGS[@]} ]]; do
    if [[ "${ENTRY_ARGS[$i]}" == "--screenshots" ]]; then
      printf '%s' "$i"
      return 0
    fi
    i=$((i + 1))
  done
  return 1
}
if shoot_idx="$(shoot_arg_index)"; then
  [[ $((shoot_idx + 1)) -lt ${#ENTRY_ARGS[@]} ]] || fail "--screenshots needs a value"
  [[ -n "$SHOTS_DIR" ]] || fail "entry has --screenshots but wrapper has no --shots-dir to validate it"
  GIVEN_SHOTS_REAL="$(realpath -m -- "${ENTRY_ARGS[$((shoot_idx + 1))]}")"
  [[ "$GIVEN_SHOTS_REAL" == "$SHOTS_REAL" ]] || fail "entry --screenshots (${ENTRY_ARGS[$((shoot_idx + 1))]}) does not match --shots-dir ($SHOTS_DIR)"
else
  case "$ENTRY" in
    run-tests.sh)
      if [[ -n "$SHOTS_DIR" ]]; then
        ENTRY_ARGS+=("--screenshots" "$SHOTS_DIR")
        SEPARATOR_SEEN=1
      fi
      ;;
  esac
fi

ENTRY_PATH="$WORKTREE/frontend/scripts/$ENTRY"
[[ -x "$ENTRY_PATH" ]] || fail "entry is not executable: $ENTRY_PATH"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$LOG_DIR/${SESSION}-${ENTRY%.sh}-${STAMP}.log"
[[ -e "$LOG_FILE" ]] && fail "log file already exists: $LOG_FILE"
: > "$LOG_FILE" || fail "cannot write log file: $LOG_FILE"

write_log_sha256() {
  sha256sum "$LOG_FILE" | awk '{ print $1 }' > "${LOG_FILE}.sha256"
}

early_exit() {
  local status="$1"
  write_log_sha256
  printf 'log=%s\nlog_sha256=%s\n' "$LOG_FILE" "$(cat "${LOG_FILE}.sha256")"
  exit "$status"
}

BUSY_DIR="/home/dev/gdds-node-busy.d"
HOSTNAME_START="$(hostname -f 2>/dev/null || hostname)"
HEAD_START="$(git -C "$WORKTREE" rev-parse HEAD)"
FRONTEND_TREE_START="$(git -C "$WORKTREE" rev-parse HEAD:frontend)"
VNEXT_TREE_START="$(git -C "$WORKTREE" rev-parse HEAD:vnext)"
STATUS_START="$(git -C "$WORKTREE" status --porcelain --untracked-files=all)"
{
  printf 'wrapper=run-evidence-wrapper.sh\n'
  printf 'session=%s\n' "$SESSION"
  printf 'hostname=%s\n' "$HOSTNAME_START"
  printf 'started_at=%s\n' "$STAMP"
  printf 'head_start=%s\n' "$HEAD_START"
  printf 'frontend_tree_start=%s\n' "$FRONTEND_TREE_START"
  printf 'vnext_tree_start=%s\n' "$VNEXT_TREE_START"
  printf 'status_start=%s\n' "${STATUS_START:-clean}"
  printf 'entry=%s\n' "$ENTRY_PATH"
  printf 'entry_args=%s\n' "${ENTRY_ARGS[*]}"
  printf 'shots_dir=%s\n' "$SHOTS_DIR"
  printf 'gateway_env_begin\n'
} >> "$LOG_FILE"

# GATEWAY_* effective values. Credential-bearing names are recorded as a
# SHA256 fingerprint of the value; everything else is recorded verbatim.
gateway_env_dump() {
  local name value
  while IFS='=' read -r name value; do
    case "$name" in
      GATEWAY_*) ;;
      *) continue ;;
    esac
    if [[ "$name" =~ (TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|COOKIE|KEY|URL) ]]; then
      printf '%s=[redacted sha256=%s]\n' "$name" "$(printf '%s' "$value" | sha256sum | cut -d' ' -f1)"
    else
      printf '%s=%s\n' "$name" "$value"
    fi
  done < <(env | sort)
}
gateway_env_dump >> "$LOG_FILE"
printf 'gateway_env_end\n' >> "$LOG_FILE"

if [[ -n "$STATUS_START" ]]; then
  printf 'wrapper_error=worktree is not clean at start; not running the entry\n' | tee -a "$LOG_FILE" >&2
  early_exit 2
fi

HAVE_MARKER=0
marker_release() {
  if [[ "$HAVE_MARKER" == "1" ]]; then
    rm -f "$BUSY_DIR/$SESSION" 2>/dev/null || true
    rmdir "$BUSY_DIR" 2>/dev/null || true
    HAVE_MARKER=0
  fi
}
trap marker_release EXIT

if [[ "$ENTRY" == "run-real-backend-e2e.sh" ]]; then
  # The entry takes its own occupancy marker; the wrapper must not take one
  # (double mkdir would exit 3). Any pre-existing marker stops the run.
  if [[ -e "$BUSY_DIR" ]]; then
    printf 'wrapper_error=node is busy: %s exists; not running the entry\n' "$BUSY_DIR" | tee -a "$LOG_FILE" >&2
    early_exit 3
  fi
  printf 'occupancy=entry-owned (%s absent at start)\n' "$BUSY_DIR" >> "$LOG_FILE"
else
  if ! mkdir "$BUSY_DIR" 2>/dev/null; then
    printf 'wrapper_error=node is busy: %s exists; not running the entry\n' "$BUSY_DIR" | tee -a "$LOG_FILE" >&2
    ls -la "$BUSY_DIR" >> "$LOG_FILE" 2>/dev/null || true
    early_exit 3
  fi
  HAVE_MARKER=1
  printf 'session=%s\npurpose=%s\nstarted_at=%s\nhostname=%s\nworktree=%s\nhead=%s\n' \
    "$SESSION" "$ENTRY" "$STAMP" "$HOSTNAME_START" "$WORKTREE" "$HEAD_START" > "$BUSY_DIR/$SESSION"
  printf 'occupancy_marker=%s\n' "$(tr '\n' ';' < "$BUSY_DIR/$SESSION")" >> "$LOG_FILE"
fi

printf 'entry_output_begin=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" >> "$LOG_FILE"
set +e
if [[ "$SEPARATOR_SEEN" == "1" ]]; then
  ( cd "$WORKTREE" && "$ENTRY_PATH" "${ENTRY_ARGS[@]}" ) >> "$LOG_FILE" 2>&1
else
  ( cd "$WORKTREE" && "$ENTRY_PATH" ) >> "$LOG_FILE" 2>&1
fi
ENTRY_EXIT=$?
set -e
printf 'entry_output_end=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" >> "$LOG_FILE"

# Record the marker before releasing our own copy.
busy_end_value() {
  if [[ -f "$BUSY_DIR/$SESSION" ]]; then
    tr '\n' ';' < "$BUSY_DIR/$SESSION"
  elif [[ -d "$BUSY_DIR" ]]; then
    printf 'dir-present-no-%s-file:' "$SESSION"
    ls -A "$BUSY_DIR" 2>/dev/null | tr '\n' ';' || true
  else
    printf 'absent'
  fi
}
BUSY_END="$(busy_end_value)"

# The EXIT trap stays armed (marker_release is idempotent) so a later failure
# still releases a wrapper-owned marker.
marker_release

HEAD_END="$(git -C "$WORKTREE" rev-parse HEAD)"
STATUS_END="$(git -C "$WORKTREE" status --porcelain --untracked-files=all)"
{
  printf 'entry_exit=%s\n' "$ENTRY_EXIT"
  printf 'hostname_end=%s\n' "$(hostname -f 2>/dev/null || hostname)"
  printf 'ended_at=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)"
  printf 'head_end=%s\n' "$HEAD_END"
  printf 'status_end=%s\n' "${STATUS_END:-clean}"
  printf 'busy_end=%s\n' "$BUSY_END"
} >> "$LOG_FILE"

# Result fields are read only from the entry-output section, never from the
# wrapper's own header/footer lines. When a field is absent the wrapper records
# why instead of writing a placeholder.
entry_output() {
  awk '/^entry_output_begin=/ { found = 1; next } /^entry_output_end=/ { found = 0 } found { print }' "$LOG_FILE"
}
report_field() {
  local key="$1" reason="$2" line=""
  line="$(entry_output | grep -a -m 1 -E "^${key}=" || true)"
  if [[ -n "$line" ]]; then
    printf 'wrapper_field %s\n' "$line" >> "$LOG_FILE"
  else
    printf 'wrapper_field_missing %s reason=%s\n' "$key" "$reason" >> "$LOG_FILE"
  fi
}
case "$ENTRY" in
  run-tests.sh)
    report_field "hostname_end" "entry did not log hostname_end"
    report_field "exit_code" "entry did not log exit_code"
    ;;
  validate-upload-package.sh)
    report_field "exit_code" "entry did not log exit_code"
    ;;
  run-real-backend-e2e.sh)
    report_field "suite" "entry did not log suite"
    report_field "suite_exit" "entry did not log suite_exit"
    ;;
esac

write_log_sha256
printf 'log=%s\nlog_sha256=%s\nentry_exit=%s\n' "$LOG_FILE" "$(cat "${LOG_FILE}.sha256")" "$ENTRY_EXIT"
exit "$ENTRY_EXIT"
