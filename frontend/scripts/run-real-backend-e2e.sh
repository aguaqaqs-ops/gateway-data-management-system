#!/usr/bin/env bash
# FE3a real-backend e2e runner (frontend kickoff §4).
#
# Standalone script, NOT part of run-tests.sh (kickoff §4.1, owner Q4).
# Spins up the Compose backend stack on this node, seeds one scope,
# verifies the running /openapi.json against the committed snapshot,
# then runs the Playwright real-backend suite inside the toolchain
# container (production build, per-identity browser contexts).
#
# Usage:
#   frontend/scripts/run-real-backend-e2e.sh --suite smoke \
#     --log-dir <absolute-dir> [--evidence-dir <absolute-dir>]
#
# Environment (same npm cache variables as run-tests.sh, kickoff §2.2):
#   GATEWAY_FRONTEND_NPM_CACHE / _ARCHIVE / _SOURCE_COMMIT
set -Eeuo pipefail

FRONTEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
REPO_DIR="$(git -C "$FRONTEND_DIR" rev-parse --show-toplevel)"
NPM_CACHE_DIR="${GATEWAY_FRONTEND_NPM_CACHE:-/home/dev/gdds-fe-cache/frontend/npm-cache}"
NPM_CACHE_ARCHIVE="${GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE:-/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz}"
NPM_CACHE_SOURCE_COMMIT="${GATEWAY_FRONTEND_NPM_CACHE_SOURCE_COMMIT:-unknown}"
TOOLCHAIN_IMAGE="mcr.microsoft.com/playwright:v1.64.1-noble"

SUITE=""
LOG_DIR=""
EVIDENCE_DIR=""
LOG_FILE=""
RUN_STAGE="argument-validation"

usage() {
  cat <<'USAGE'
usage: frontend/scripts/run-real-backend-e2e.sh --suite smoke|journeys|t1 [--input-root <dir>] --log-dir <absolute-dir> [--evidence-dir <absolute-dir>]
USAGE
}

INPUT_ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite) [[ -z "$SUITE" && $# -ge 2 ]] || { usage >&2; exit 2; }; SUITE="$2"; shift 2 ;;
    --input-root) [[ -z "$INPUT_ROOT" && $# -ge 2 ]] || { usage >&2; exit 2; }; INPUT_ROOT="$2"; shift 2 ;;
    --log-dir) [[ -z "$LOG_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; LOG_DIR="$2"; shift 2 ;;
    --evidence-dir) [[ -z "$EVIDENCE_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; EVIDENCE_DIR="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "$SUITE" && -n "$LOG_DIR" ]] || { usage >&2; exit 2; }
[[ "$SUITE" == "smoke" || "$SUITE" == "journeys" || "$SUITE" == "t1" ]] || { usage >&2; exit 2; }
[[ "$LOG_DIR" == /* ]] || { echo "log dir must be absolute" >&2; exit 2; }
[[ -z "$EVIDENCE_DIR" || "$EVIDENCE_DIR" == /* ]] || { echo "evidence dir must be absolute" >&2; exit 2; }
LOG_DIR="$(realpath -m -- "$LOG_DIR")"
[[ -n "$EVIDENCE_DIR" ]] && EVIDENCE_DIR="$(realpath -m -- "$EVIDENCE_DIR")"

path_in_repo() { [[ "$1" == "$REPO_DIR" || "$1" == "$REPO_DIR/"* ]]; }
if path_in_repo "$LOG_DIR" || { [[ -n "$EVIDENCE_DIR" ]] && path_in_repo "$EVIDENCE_DIR"; }; then
  echo "logs and evidence must be outside the worktree" >&2
  exit 2
fi

# --- occupancy: whole-node mkdir + compose gate flock (kickoff §4.2) ---
BUSY_DIR="/home/dev/gdds-node-busy.d"
GATE_LOCK="/tmp/gateway-compose-gate.lock"
SESSION_NAME="fe3a-impl"
HAVE_BUSY=0
HAVE_FLOCK=0

log() { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }

mkdir -p -- "$LOG_DIR"
[[ -n "$EVIDENCE_DIR" ]] && mkdir -p -- "$EVIDENCE_DIR"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_START="$(git -C "$REPO_DIR" rev-parse HEAD)"
LOG_FILE="$LOG_DIR/real-backend-e2e-${SUITE}-$(git -C "$REPO_DIR" rev-parse --short HEAD)-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
[[ ! -e "$LOG_FILE" ]] || { echo "refusing to overwrite log: $LOG_FILE" >&2; exit 2; }
: > "$LOG_FILE"

cleanup() {
  local exit_code=$?
  trap - EXIT
  # 1. stop toolchain container first (kickoff §4.5/§4.8)
  if [[ -n "${TOOLCHAIN_CONTAINER:-}" ]]; then
    docker stop --time 10 "$TOOLCHAIN_CONTAINER" >/dev/null 2>&1 || true
    docker rm --force "$TOOLCHAIN_CONTAINER" >/dev/null 2>&1 || true
  fi
  # 2-4. compose logs, down, residual check
  if [[ -n "${PROJECT_NAME:-}" ]]; then
    docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" logs --no-color --timestamps >"$LOG_DIR/compose-$PROJECT_NAME.log" 2>&1 || true
    docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" down -v --remove-orphans --rmi local >/dev/null 2>&1 || true
  fi
  # 5. release flock, then busy marker (kickoff §4.2 order)
  if [[ "$HAVE_FLOCK" == "1" ]]; then
    exec 9>&- || true
    HAVE_FLOCK=0
  fi
  if [[ "$HAVE_BUSY" == "1" ]]; then
    rm -f -- "$BUSY_DIR/$SESSION_NAME" 2>/dev/null || true
    HAVE_BUSY=0
  fi
  {
    printf 'ended_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'hostname_end=%s\n' "$(hostname -f 2>/dev/null || hostname)"
    printf 'head_end=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true)"
    printf 'exit_code=%s\n' "$exit_code"
  } >> "$LOG_FILE" 2>/dev/null || true
  sha256sum "$LOG_FILE" > "$LOG_FILE.sha256" 2>/dev/null || true
  printf 'log_file=%s\n' "$LOG_FILE"
  cat "$LOG_FILE.sha256" 2>/dev/null || true
  exit "$exit_code"
}
trap cleanup EXIT

RUN_STAGE="occupancy"
HOSTNAME_START="$(hostname -f 2>/dev/null || hostname)"
{
  printf 'hostname=%s\n' "$HOSTNAME_START"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'head_start=%s\n' "$HEAD_START"
  printf 'frontend_tree_start=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD:frontend)"
  printf 'vnext_tree_start=%s\n' "$(git -C "$REPO_DIR" rev-parse HEAD:vnext)"
  printf 'suite=%s\n' "$SUITE"
} | tee "$LOG_FILE"

if ! mkdir "$BUSY_DIR" 2>/dev/null; then
  if [[ -f "$BUSY_DIR/$SESSION_NAME" ]]; then
    log "error=node is busy (own marker present)"
  else
    log "error=node is busy: $BUSY_DIR exists"
    ls -la "$BUSY_DIR" 2>/dev/null | tee -a "$LOG_FILE" || true
  fi
  exit 3
fi
printf 'session=%s\npurpose=fe3a-real-backend-e2e-%s\nstarted_at=%s\nhostname=%s\nworktree=%s\nhead=%s\n' \
  "$SESSION_NAME" "$SUITE" "$STARTED_AT" "$HOSTNAME_START" "$REPO_DIR" "$HEAD_START" > "$BUSY_DIR/$SESSION_NAME"
HAVE_BUSY=1
log "occupancy_acquired=$BUSY_DIR/$SESSION_NAME"

exec 9>"$GATE_LOCK"
if ! flock -n 9; then
  log "error=compose gate lock is held"
  exit 3
fi
HAVE_FLOCK=1
log "flock_acquired=$GATE_LOCK"

# Residual checks (kickoff §4.2): port 8000, dolt, own project leftovers.
RUN_STAGE="residual-check"
if [[ -n "$(docker ps --filter publish=8000 --format '{{.Names}}' 2>/dev/null)" ]]; then
  log "error=port 8000 is already published"
  docker ps --filter publish=8000 --format '{{.Names}}' | tee -a "$LOG_FILE"
  exit 3
fi
if pgrep -f dolt >/dev/null 2>&1; then
  log "error=dolt processes are running"
  exit 3
fi

# Toolchain + npm cache preconditions (same as run-tests.sh).
RUN_STAGE="preconditions"
if [[ ! -d "$NPM_CACHE_DIR" ]] || [[ -z "$(find "$NPM_CACHE_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  log "error=npm cache is missing or empty: $NPM_CACHE_DIR"
  exit 2
fi
if ! docker image inspect "$TOOLCHAIN_IMAGE" >/dev/null 2>&1; then
  log "error=toolchain image is not loaded locally: $TOOLCHAIN_IMAGE"
  exit 2
fi
if [[ -n "$(git -C "$REPO_DIR" status --porcelain=v1 --untracked-files=all)" ]]; then
  log "error=source worktree is not clean"
  exit 2
fi

# Dependency input tag (kickoff §4.3): never build the dep image here.
RUN_STAGE="dependency-input"
DEPENDENCY_TAG="$(vnext/scripts/build-backend-dependency-base.sh --print-input 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["image"])')"
log "dependency_base_image=$DEPENDENCY_TAG"
if ! docker image inspect "$DEPENDENCY_TAG" >/dev/null 2>&1; then
  log "error=dependency-base image missing locally: $DEPENDENCY_TAG (cache miss, stop)"
  exit 2
fi
DEP_LABEL="$(docker image inspect "$DEPENDENCY_TAG" --format '{{index .Config.Labels "gateway.backend.dependency-input-sha256}}')"
log "dependency_input_label=$DEP_LABEL"

# RS dependency tag + label check (kickoff §4.3).
RUN_STAGE="rs-dependency"
RS_UV_SHA="$(sha256sum "$REPO_DIR/vnext/repository_service/uv.lock" | awk '{print $1}')"
RS_DEP_TAG="gateway-p2r1-repository:lock-${RS_UV_SHA:0:12}"
log "rs_dependency_base_image=$RS_DEP_TAG"
if ! docker image inspect "$RS_DEP_TAG" >/dev/null 2>&1; then
  log "error=RS dependency image missing: $RS_DEP_TAG (cache miss, stop)"
  exit 2
fi
RS_LABEL="$(docker image inspect "$RS_DEP_TAG" --format '{{index .Config.Labels "gateway.p2r1.uv-lock-sha256}}')"
if [[ "$RS_LABEL" != "$RS_UV_SHA" ]]; then
  log "error=RS dependency label mismatch: $RS_LABEL != $RS_UV_SHA"
  exit 2
fi
log "rs_dependency_label=$RS_LABEL"

RUN_STAGE="rs-build"
RS_TAG="gateway-repository-service:fe-${HEAD_START:0:12}"
log "rs_image_tag=$RS_TAG"
if ! GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE="$RS_DEP_TAG" GATEWAY_DOCKER_BUILD_NETWORK=none \
  "$REPO_DIR/vnext/scripts/build-repository-service-image.sh" 2>&1 | tee -a "$LOG_FILE"; then
  log "error=RS image build failed (cache miss or network needed, stop)"
  exit 2
fi
# The build script tags gateway-repository-service:local; retag to the run tag.
docker tag gateway-repository-service:local "$RS_TAG" 2>&1 | tee -a "$LOG_FILE"
log "rs_image_built=$RS_TAG"

# Project + secrets (outside the worktree, container-readable).
RUN_STAGE="compose-up"
STAMP="$(date -u +%Y%m%dt%H%M%Sz | tr 'A-Z' 'a-z')"
PROJECT_NAME="gdds-fe3a-${HEAD_START:0:12}-${STAMP}"
export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/gateway-fe3a-e2e.XXXXXX")"
chmod 0755 "$RUN_ROOT"
log "compose_project=$PROJECT_NAME"
log "run_root=$RUN_ROOT"

# Random per-run tokens (never logged, never in build products).
SUBMITTER_TOKEN="fe3a-submitter-$(openssl rand -hex 16)"
NOPREVIEW_TOKEN="fe3a-nopreview-$(openssl rand -hex 16)"
REVIEWER_TOKEN="fe3a-reviewer-$(openssl rand -hex 16)"
ARCHIVER_TOKEN="fe3a-archiver-$(openssl rand -hex 16)"
NOPERM_TOKEN="fe3a-noperm-$(openssl rand -hex 16)"
RS_BEARER="fe3a-rs-$(openssl rand -hex 16)"
INTERNAL_BEARER="fe3a-internal-$(openssl rand -hex 16)"
SESSION_ACTOR="fe3a-submitter"
DEVICE_KEY="fe3a-device"
BUSINESS_PROJECT="fe3a-project"
BASELINE_NODE="fe3a-node"

SCOPE_NAME="smoke"
cat > "$RUN_ROOT/session.json" <<EOF
{"sessions": [
  {"token": "$SUBMITTER_TOKEN", "actor_id": "$SESSION_ACTOR", "gateway_device_external_key": "$DEVICE_KEY", "business_project_id": "$BUSINESS_PROJECT", "permissions": ["workspace_read", "upload_submit_workspace", "preview_workspace"]},
  {"token": "$NOPREVIEW_TOKEN", "actor_id": "fe3a-no-preview", "gateway_device_external_key": "$DEVICE_KEY", "business_project_id": "$BUSINESS_PROJECT", "permissions": ["workspace_read", "upload_submit_workspace"]},
  {"token": "$REVIEWER_TOKEN", "actor_id": "fe3a-reviewer", "gateway_device_external_key": "$DEVICE_KEY", "business_project_id": "$BUSINESS_PROJECT", "permissions": ["workspace_read", "read_project_history", "review_submission"]},
  {"token": "$ARCHIVER_TOKEN", "actor_id": "fe3a-archiver", "gateway_device_external_key": "$DEVICE_KEY", "business_project_id": "$BUSINESS_PROJECT", "permissions": ["workspace_read", "read_project_history", "archive_submission"]},
  {"token": "$NOPERM_TOKEN", "actor_id": "fe3a-noperm", "gateway_device_external_key": "$DEVICE_KEY", "business_project_id": "$BUSINESS_PROJECT", "permissions": []}
EOF
printf '%s\n' "$RS_BEARER" > "$RUN_ROOT/repository-bearer-token"
printf '%s\n' "$INTERNAL_BEARER" > "$RUN_ROOT/internal-bearer-token"
chmod 0600 "$RUN_ROOT/session.json" "$RUN_ROOT/repository-bearer-token" "$RUN_ROOT/internal-bearer-token"
export GATEWAY_P2R2_BEARER_TOKEN_FILE="$RUN_ROOT/repository-bearer-token"
export GATEWAY_BACKEND_SESSION_FILE="$RUN_ROOT/session.json"
export GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE="$RUN_ROOT/provisioned-mapping.json"
export GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE="$RUN_ROOT/internal-bearer-token"
export GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE="$RUN_ROOT/repository-bearer-token"
export GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1
export GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE="$DEPENDENCY_TAG"
export GATEWAY_DOCKER_BUILD_NETWORK=none
export GATEWAY_REPOSITORY_SERVICE_IMAGE="$RS_TAG"
log "identity_scopes=smoke(submitter/reviewer/archiver/noperm)"

# 1. build backend+worker images (offline, preloaded deps).
if ! docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" build backend worker 2>&1 | tee -a "$LOG_FILE"; then
  log "error=backend/worker build failed"
  exit 2
fi
# 2. up repository-service, wait ready, seed one scope with a unique key.
if ! docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" up -d --no-build repository-service 2>&1 | tee -a "$LOG_FILE"; then
  log "error=repository-service up failed"
  exit 2
fi
SEED_KEY="fe3a-seed-${HEAD_START:0:12}-smoke"
SEED_JSON="$(docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" exec -T repository-service python -c "
import json, urllib.request
req = urllib.request.Request('http://127.0.0.1:8000/v1/repositories', method='POST', headers={'Authorization': 'Bearer $RS_BEARER', 'Idempotency-Key': '$SEED_KEY'})
print(urllib.request.urlopen(req, timeout=30.0).read().decode())" 2>&1 | tee -a "$LOG_FILE" | tail -1)"
REPO_ID="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['repository_id'])" "$SEED_JSON")"
INIT_COMMIT="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['initial_commit_id'])" "$SEED_JSON")"
log "seeded_repository_id=$REPO_ID"
log "seed_initial_commit_id=$INIT_COMMIT"
cat > "$RUN_ROOT/provisioned-mapping.json" <<EOF
{"mappings": [{"gateway_device_external_key": "$DEVICE_KEY", "business_project_id": "$BUSINESS_PROJECT", "repository_id": "$REPO_ID", "business_baseline_node_id": "$BASELINE_NODE", "business_baseline_commit_id": "$INIT_COMMIT", "baseline_head_version": 0, "enabled": true}]}
EOF
chmod 0644 "$RUN_ROOT/provisioned-mapping.json"
# 3. up backend+worker, wait /readyz.
if ! docker compose -f "$REPO_DIR/vnext/deploy/compose.yaml" -p "$PROJECT_NAME" up -d --no-build backend worker 2>&1 | tee -a "$LOG_FILE"; then
  log "error=backend/worker up failed"
  exit 2
fi
READYZ_OK=0
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/readyz >/dev/null 2>&1; then READYZ_OK=1; break; fi
  sleep 2
done
if [[ "$READYZ_OK" != "1" ]]; then
  log "error=backend /readyz never became ready"
  exit 2
fi
log "backend_readyz=ok"

# 4. Runtime OpenAPI comparison (Python-normalized, kickoff §5.2).
RUN_STAGE="openapi-compare"
python3 - "$REPO_DIR/frontend/openapi.json" > "$RUN_ROOT/openapi-compare.txt" <<'PYEOF' 2>&1 | tee -a "$LOG_FILE"
import json, sys, urllib.request
snapshot_path = sys.argv[1]
with open(snapshot_path, encoding="utf-8") as f:
    snapshot = json.load(f)
with urllib.request.urlopen("http://127.0.0.1:8000/openapi.json", timeout=30.0) as r:
    runtime = json.loads(r.read().decode("utf-8"))
def norm(obj):
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
if norm(snapshot) != norm(runtime):
    print("openapi_compare=mismatch")
    sys.exit(3)
print("openapi_compare=match")
PYEOF
if [[ "${PIPESTATUS[0]}" != "0" ]]; then
  log "error=runtime /openapi.json differs from committed snapshot (stop, no browser tests)"
  exit 2
fi

# 5. Toolchain container on the compose network, production build.
RUN_STAGE="browser"
TOOLCHAIN_CONTAINER="${PROJECT_NAME}-toolchain"
docker run -d --rm --init --name "$TOOLCHAIN_CONTAINER" --label "com.docker.compose.project=$PROJECT_NAME" \
  --network "${PROJECT_NAME}_default" \
  --volume "$REPO_DIR/frontend:/frontend-source.tar:ro" \
  --volume "$NPM_CACHE_DIR:/npm-cache:ro" \
  ${SMOKE_INPUT:+--volume "$SMOKE_INPUT:/input:ro"} \
  --env "GATEWAY_FE_SUITE=$SUITE" \
  "$TOOLCHAIN_IMAGE" sleep infinity >/dev/null 2>&1
log "toolchain_container=$TOOLCHAIN_CONTAINER"
log "compose_network=${PROJECT_NAME}_default"

docker exec "$TOOLCHAIN_CONTAINER" bash -euo pipefail -c "
  mkdir -p /tmp/frontend /tmp/npm-cache
  tar -xf /frontend-source.tar --strip-components=1 -C /tmp/frontend 2>/dev/null || cp -a /frontend-source.tar/. /tmp/frontend/
  cp -a /npm-cache/. /tmp/npm-cache/
  cd /tmp/frontend
  npm ci --offline --cache /tmp/npm-cache --no-audit --no-fund
  npm run build
" 2>&1 | tee -a "$LOG_FILE"

# Smoke input directory from the shared upload files (kickoff §4.6):
# one placeholder .pmc + sql/dbcfg.sql + logics.xml, written outside the
# worktree and mounted read-only into the toolchain container at /input.
SMOKE_INPUT="$RUN_ROOT/smoke-input"
if [[ "$SUITE" == "smoke" ]]; then
  mkdir -p -- "$SMOKE_INPUT/sql" "$SMOKE_INPUT/comps/logic"
  printf 'fe3a-smoke-v1\n' > "$SMOKE_INPUT/smoke.pmc"
  cp -- "$REPO_DIR/frontend/src/test/fixtures/source/upload-inputs/sql-modified.sql" "$SMOKE_INPUT/sql/dbcfg.sql"
  cp -- "$REPO_DIR/frontend/src/test/fixtures/source/upload-inputs/logics-3.xml" "$SMOKE_INPUT/comps/logic/logics.xml"
  chmod -R a+rX -- "$SMOKE_INPUT"
  log "smoke_input=$SMOKE_INPUT"
fi

# Identities JSON for per-context injection (owner Q5). Tokens are random
# per run; the file stays outside the worktree and is mounted read-only.
cat > "$RUN_ROOT/identities.json" <<EOF
[{"name": "submitter", "token": "$SUBMITTER_TOKEN", "actorId": "$SESSION_ACTOR", "businessProjectId": "$BUSINESS_PROJECT", "gatewayDeviceExternalKey": "$DEVICE_KEY"},
 {"name": "reviewer", "token": "$REVIEWER_TOKEN", "actorId": "fe3a-reviewer", "businessProjectId": "$BUSINESS_PROJECT", "gatewayDeviceExternalKey": "$DEVICE_KEY"},
 {"name": "archiver", "token": "$ARCHIVER_TOKEN", "actorId": "fe3a-archiver", "businessProjectId": "$BUSINESS_PROJECT", "gatewayDeviceExternalKey": "$DEVICE_KEY"},
 {"name": "noperm", "token": "$NOPERM_TOKEN", "actorId": "fe3a-noperm", "businessProjectId": "$BUSINESS_PROJECT", "gatewayDeviceExternalKey": "$DEVICE_KEY"},
 {"name": "no-preview", "token": "$NOPREVIEW_TOKEN", "actorId": "fe3a-no-preview", "businessProjectId": "$BUSINESS_PROJECT", "gatewayDeviceExternalKey": "$DEVICE_KEY"}]
EOF
chmod 0600 "$RUN_ROOT/identities.json"
IDENTITIES_JSON="$(cat "$RUN_ROOT/identities.json")"
log "identities_written=5 scopes(submitter/no-preview/reviewer/archiver/noperm)"

# Identities: one browser context each via addInitScript (kickoff §4.5).
RUN_STAGE="suite"
log "suite_start=$SUITE"
set +e
docker cp "$RUN_ROOT/identities.json" "$TOOLCHAIN_CONTAINER:/tmp/identities.json"
docker exec --env "GATEWAY_FE_SUITE=$SUITE" --env "GATEWAY_FE_SMOKE_INPUT_ROOT=/input" "$TOOLCHAIN_CONTAINER" bash -euo pipefail -c '
  cd /tmp/frontend
  export GATEWAY_FE_IDENTITIES="$(cat /tmp/identities.json)"
  GATEWAY_M1_INPUT_ROOT= GATEWAY_M1_MODE= npx playwright test --config playwright.real.config.ts
' 2>&1 | tee -a "$LOG_FILE"
SUITE_EXIT="${PIPESTATUS[0]}"
set -e
log "suite_exit=$SUITE_EXIT"
exit "$SUITE_EXIT"
