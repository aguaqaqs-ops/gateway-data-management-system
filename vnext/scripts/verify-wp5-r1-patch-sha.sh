#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

BASE="${BASE:-f1a6135ebf532d83d8179f22bad6637ed24b6d02}"
EXCLUDE="${EXCLUDE:-docs/backend-vnext/refactoring/temporary/phase-1/wp5-r1-scenario-schema-closure-evidence.md}"

sha=$(
  {
    # Existing baseline paths use one canonical tracked diff. Disable rename
    # detection so a rename is represented deterministically as delete + add.
    git diff --no-ext-diff --binary --no-renames --diff-filter=MDTUXB \
      "${BASE}" -- . ":!${EXCLUDE}"

    # Files absent from BASE always use the same /dev/null representation,
    # whether they are currently untracked, staged, or already committed.
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
