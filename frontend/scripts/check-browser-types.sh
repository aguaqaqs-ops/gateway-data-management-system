#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="$(cd -- "$(dirname -- "$0")/.." && pwd)"
PROBE="$(mktemp "$FRONTEND_DIR/.browser-type-probe.XXXXXX.ts")"
OUTPUT="$(mktemp)"
trap 'rm -f "$PROBE" "$OUTPUT"' EXIT
cat >"$PROBE" <<'TS'
const browserBuffer: Buffer = Buffer.from([]);
void browserBuffer;
TS

if "$FRONTEND_DIR/node_modules/.bin/tsc" --noEmit --strict --target ES2022 --lib ES2022,DOM \
  --module ESNext --moduleResolution Bundler --types vite/client "$PROBE" >"$OUTPUT" 2>&1; then
  echo "browser TypeScript unexpectedly includes Node Buffer types" >&2
  exit 1
fi
if ! grep -q "Cannot find name 'Buffer'" "$OUTPUT"; then
  cat "$OUTPUT" >&2
  echo "browser type probe failed for a reason other than Node Buffer being unavailable" >&2
  exit 1
fi
echo "browser type isolation probe passed: Buffer is unavailable to app code"
