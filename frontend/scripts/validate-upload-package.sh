#!/usr/bin/env bash
# Backend validation of the frontend Source Package output (kickoff §7.1, Q17).
set -euo pipefail

ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
OUT="${GATEWAY_UPLOAD_VALIDATION_DIR:-/home/dev/gdds-test-tmp/fe2c-upload-package-$(date -u +%Y%m%dT%H%M%SZ)}"
FE_IMAGE="${GATEWAY_FE_PACKAGE_IMAGE:-mcr.microsoft.com/playwright:v1.64.1-noble}"
BACKEND_IMAGE="${GATEWAY_BACKEND_DEPS_IMAGE:-gateway-backend-deps:lock-d054366c02fa}"

mkdir -p "$OUT"
chmod 0777 "$OUT"
echo "hostname=$(hostname)"
echo "start=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "head=$(git -C "$ROOT" rev-parse HEAD)"
echo "frontend_tree=$(git -C "$ROOT" rev-parse HEAD:frontend)"
echo "vnext_tree=$(git -C "$ROOT" rev-parse HEAD:vnext)"
for image in "$FE_IMAGE" "$BACKEND_IMAGE"; do
  echo "image=$image config_digest=$(docker image inspect --format '{{.Id}}' "$image")"
  echo "image=$image diffids=$(docker image inspect --format '{{range .RootFS.Layers}}{{.}} {{end}}' "$image")"
done
echo "output=$OUT"

set -o pipefail
docker run --rm --network none \
  -v "$ROOT/frontend:/src:ro" -v "$OUT:/out" -w /src \
  "$FE_IMAGE" node scripts/build-upload-validation-fixtures.mjs /out

docker run --rm --network none \
  -v "$ROOT:/src:ro" -v "$OUT:/out:ro" -w /src \
  -e PYTHONPATH=/src/vnext/backend/src \
  "$BACKEND_IMAGE" /build/backend/.venv/bin/python frontend/scripts/validate_upload_package.py /out

sha256sum "$OUT"/*.tar.gz
echo "end=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
