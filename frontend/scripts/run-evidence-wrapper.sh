#!/usr/bin/env bash
# FE4a evidence wrapper (kickoff §3.8): runs a frontend evidence entry with a
# fixed pre-flight check and a fixed provenance record. The wrapper writes the
# log before the entry runs nothing: when any check fails it exits non-zero
# without running the entry (FE3c once ran the log dir into `$2` and the entry
# never ran).
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
# shots dir outside the worktree. Any failure exits before the entry runs.
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
if [[ -n "$SHOTS_DIR" ]]; then
  [[ "$SHOTS_DIR" == /* ]] || fail "shots dir must be absolute (got $SHOTS_DIR)"
  [[ "$SHOTS_DIR" != "$WORKTREE" && "$SHOTS_DIR" != "$WORKTREE"/* ]] || fail "shots dir must be outside the worktree (got $SHOTS_DIR)"
fi
ENTRY_PATH="$WORKTREE/frontend/scripts/$ENTRY"
[[ -x "$ENTRY_PATH" ]] || fail "entry is not executable: $ENTRY_PATH"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$LOG_DIR/${SESSION}-${ENTRY%.sh}-${STAMP}.log"
[[ -e "$LOG_FILE" ]] && fail "log file already exists: $LOG_FILE"
: > "$LOG_FILE" || fail "cannot write log file: $LOG_FILE"

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
} >> "$LOG_FILE"

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
  # (double mkdir would exit 3). A pre-existing marker stops the run.
  if [[ -e "$BUSY_DIR" ]]; then
    printf 'wrapper_error=node is busy: %s exists; not running the entry\n' "$BUSY_DIR" | tee -a "$LOG_FILE" >&2
    exit 3
  fi
  printf 'occupancy=entry-owned (%s absent at start)\n' "$BUSY_DIR" >> "$LOG_FILE"
else
  if ! mkdir "$BUSY_DIR" 2>/dev/null; then
    if [[ -f "$BUSY_DIR/$SESSION" ]] || [[ -z "$(ls -A "$BUSY_DIR" 2>/dev/null)" ]]; then
      # Own-session residual or an empty dir: take over and note it; anything
      # else belongs to someone else and stops the run.
      printf 'occupancy_takeover=same-session-or-empty dir reused\n' >> "$LOG_FILE"
      ls -la "$BUSY_DIR" >> "$LOG_FILE" 2>/dev/null || true
    else
      printf 'wrapper_error=node is busy: %s exists; not running the entry\n' "$BUSY_DIR" | tee -a "$LOG_FILE" >&2
      ls -la "$BUSY_DIR" >> "$LOG_FILE" 2>/dev/null || true
      exit 3
    fi
  fi
  HAVE_MARKER=1
  printf 'session=%s\npurpose=%s\nstarted_at=%s\nhostname=%s\nworktree=%s\nhead=%s\n' \
    "$SESSION" "$ENTRY" "$STAMP" "$HOSTNAME_START" "$WORKTREE" "$HEAD_START" > "$BUSY_DIR/$SESSION"
  printf 'occupancy_marker=%s\n' "$(tr '\n' ';' < "$BUSY_DIR/$SESSION")" >> "$LOG_FILE"
fi

set +e
if [[ "$SEPARATOR_SEEN" == "1" ]]; then
  ( cd "$WORKTREE" && "$ENTRY_PATH" "${ENTRY_ARGS[@]}" ) >> "$LOG_FILE" 2>&1
else
  ( cd "$WORKTREE" && "$ENTRY_PATH" ) >> "$LOG_FILE" 2>&1
fi
ENTRY_EXIT=$?
set -e
# The EXIT trap stays armed (marker_release is idempotent) so a later failure
# still releases a wrapper-owned marker.
marker_release

HEAD_END="$(git -C "$WORKTREE" rev-parse HEAD)"
STATUS_END="$(git -C "$WORKTREE" status --porcelain --untracked-files=all)"
BUSY_END="$(ls -la "$BUSY_DIR" 2>/dev/null || echo "busy dir absent")"
{
  printf 'entry_exit=%s\n' "$ENTRY_EXIT"
  printf 'hostname_end=%s\n' "$(hostname -f 2>/dev/null || hostname)"
  printf 'ended_at=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)"
  printf 'head_end=%s\n' "$HEAD_END"
  printf 'status_end=%s\n' "${STATUS_END:-clean}"
  printf 'busy_end=%s\n' "$BUSY_END"
} >> "$LOG_FILE"

# Result fields are read back from the entry log by whole lines. When a field
# is absent the wrapper records why instead of writing a placeholder.
report_field() {
  local key="$1" reason="$2" line=""
  line="$(grep -a -m 1 -E "^${key}=" "$LOG_FILE" || true)"
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

sha256sum "$LOG_FILE" | awk '{ print $1 }' > "${LOG_FILE}.sha256"
printf 'log=%s\nlog_sha256=%s\nentry_exit=%s\n' "$LOG_FILE" "$(cat "${LOG_FILE}.sha256")" "$ENTRY_EXIT"
exit "$ENTRY_EXIT"
