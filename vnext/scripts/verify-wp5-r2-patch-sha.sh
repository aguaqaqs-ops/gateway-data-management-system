#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

BASE="${BASE:-4df45e417c897f3523b9ef559cfa03427d364d58}"
EXCLUDE="${EXCLUDE:-docs/backend-vnext/refactoring/temporary/phase-1/wp5-r2-runner-lifecycle-evidence.md}"

sha=$(
  {
    git diff --no-ext-diff --binary --no-renames --diff-filter=MDTUXB \
      "${BASE}" -- . ":!${EXCLUDE}"

    {
      git diff --name-only -z --no-renames --diff-filter=A \
        "${BASE}" -- . ":!${EXCLUDE}"
      git ls-files -o -z --exclude-standard
    } | LC_ALL=C sort -zu \
      | while IFS= read -r -d '' path; do
          case "${path}" in
            ${EXCLUDE}) continue ;;
            .vscode/*) continue ;;
            .cursor/*) continue ;;
          esac
          git diff --no-ext-diff --binary --no-index /dev/null "${path}" || true
        done
  } | sha256sum | awk '{print $1}'
)

printf '%s  -\n' "${sha}"

if [[ -n "${EXPECTED_SHA:-}" && "${sha}" != "${EXPECTED_SHA}" ]]; then
  echo "patch SHA mismatch: expected ${EXPECTED_SHA}, got ${sha}" >&2
  exit 1
fi
