#!/usr/bin/env bash
set -euo pipefail
repo="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
head_start="$(git -C "$repo" rev-parse HEAD)"
lock="$repo/directory/frontend/package-lock.json"
lock_start="$(sha256sum "$lock" | cut -d' ' -f1)"
tmp=""
finish() {
  result=$?
  trap - EXIT
  end="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
  lock_end="$(sha256sum "$lock" 2>/dev/null | cut -d' ' -f1 || true)"
  if [[ "$end" != "$head_start" || "$end" != "${GDDS_DIRECTORY_TEST_HEAD:-}" || "$lock_end" != "$lock_start" || -n "$(git -C "$repo" status --porcelain --untracked-files=all)" ]]; then (( result != 0 )) || result=1; fi
  if [[ -n "$tmp" ]] && ! rm -rf -- "$tmp"; then (( result != 0 )) || result=1; fi
  printf 'end_utc=%s\nend_head=%s\nlock_sha256_end=%s\nrunner_exit=%s\n' "$(date -u +%FT%TZ)" "$end" "$lock_end" "$result"
  exit "$result"
}
trap finish EXIT
printf 'hostname=%s\nstart_utc=%s\nstart_head=%s\nlock_sha256_start=%s\nargv=' "$(hostname)" "$(date -u +%FT%TZ)" "$head_start" "$lock_start"
printf '%q ' "$0" "$@"; printf '\n'
[[ "$(hostname)" == gw-dms-07 && "${GDDS_DIRECTORY_TEST_HEAD:-}" =~ ^[0-9a-f]{40}$ && "$head_start" == "$GDDS_DIRECTORY_TEST_HEAD" ]]
[[ -z "$(git -C "$repo" status --porcelain --untracked-files=all)" ]]
[[ "${TMPDIR:-}" == /home/dev/gdds-test-tmp && "${GATEWAY_FE_TEST_WORKERS:-}" == 2 ]]
[[ $# -eq 2 && "$1" == --screenshots && "$2" == /* ]]
shots="$(realpath -m "$2")"
[[ "$shots" != "$repo" && "$shots" != "$repo/"* && ! -e "$shots" ]]
cache="$(realpath "${GDDS_DIRECTORY_NPM_CACHE:?}")"
archive="$(realpath "${GDDS_DIRECTORY_NPM_ARCHIVE:?}")"
manifest="$(realpath "${GDDS_DIRECTORY_NPM_MANIFEST:?}")"
[[ "$cache" != "$repo/"* && "$archive" != "$repo/"* && "$manifest" != "$repo/"* ]]
python3 -I "$repo/directory/scripts/frontend-inputs.py" verify "$manifest" "$cache" "$archive" "$lock"
tmp="$(mktemp -d "$TMPDIR/gdds-directory-frontend.XXXXXXXX")"
image='mcr.microsoft.com/playwright:v1.64.1-noble'
docker image save -o "$tmp/image.tar" "$image"
identity="$(python3 -I "$repo/directory/scripts/docker-save-image-identity.py" "$tmp/image.tar")"
python3 -I "$repo/directory/scripts/frontend-inputs.py" image "$identity"
printf 'toolchain_image=%s\ntoolchain_identity=%s\n' "$image" "$identity"
rm "$tmp/image.tar"
git -C "$repo" archive HEAD directory/frontend > "$tmp/source.tar"
mkdir "$shots"
docker run --rm --init --ipc=host --network none \
  -v "$tmp/source.tar:/source.tar:ro" -v "$cache:/cache:ro" -v "$shots:/evidence" \
  -e GATEWAY_FE_TEST_WORKERS=2 -e GDDS_DIRECTORY_SCREENSHOT_DIR=/evidence \
  "$image" bash -euo pipefail -c '
    mkdir -p /tmp/app /tmp/npm-cache
    tar -xf /source.tar --strip-components=2 -C /tmp/app
    cp -a /cache/. /tmp/npm-cache/
    cd /tmp/app
    npm ci --offline --cache /tmp/npm-cache --no-audit --no-fund
    npm run typecheck
    npm run lint
    npm run test:unit
    npm run build
    npm run test:e2e -- --workers=2
    npm run test:screenshots -- --workers=2
  '
python3 -I "$repo/directory/scripts/frontend-inputs.py" screenshots "$shots"
