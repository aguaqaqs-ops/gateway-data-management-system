#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

BASE="${BASE:-b747590ac6ffdfe0e00b320363ce429e663e358e}"
DEFAULT_EXCLUDE="docs/backend-vnext/refactoring/temporary/phase-1/wp5-r5-phase1-exit-evidence.md"
EXCLUDE="${EXCLUDE:-${DEFAULT_EXCLUDE}}"

if [[ "${EXCLUDE}" != "${DEFAULT_EXCLUDE}" ]]; then
  echo "EXCLUDE override is not permitted for WP5 R5 patch SHA" >&2
  exit 1
fi
if [[ "${EXCLUDE}" == *".."* ]] || [[ "${EXCLUDE}" == /* ]]; then
  echo "EXCLUDE must be a repository-relative path" >&2
  exit 1
fi

path_is_excluded() {
  local path="$1"
  case "${path}" in
    "${EXCLUDE}") return 0 ;;
    .vscode/*) return 0 ;;
    .cursor/*) return 0 ;;
  esac
  return 1
}

sha=$(
  {
    git diff --no-ext-diff --binary --no-renames --diff-filter=MDTUXB \
      "${BASE}" -- . \
      ":!${EXCLUDE}" ":!.vscode/*" ":!.cursor/*"

    {
      git diff --name-only -z --no-renames --diff-filter=A \
        "${BASE}" -- . \
        ":!${EXCLUDE}" ":!.vscode/*" ":!.cursor/*"
      git ls-files -o -z --exclude-standard
    } | LC_ALL=C sort -zu \
      | while IFS= read -r -d '' path; do
          if path_is_excluded "${path}"; then
            continue
          fi
          git diff --no-ext-diff --binary --no-index /dev/null "${path}" || true
        done
  } | sha256sum | awk '{print $1}'
)

printf '%s  -\n' "${sha}"

if [[ -n "${EXPECTED_SHA:-}" && "${sha}" != "${EXPECTED_SHA}" ]]; then
  echo "patch SHA mismatch: expected ${EXPECTED_SHA}, got ${sha}" >&2
  exit 1
fi
