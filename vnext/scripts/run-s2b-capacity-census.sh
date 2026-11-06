#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export UV_OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1

exec "${REPOSITORY_ROOT}/vnext/scripts/uv-consume.sh" \
  -C "${REPOSITORY_ROOT}/vnext/backend" \
  run --no-sync python \
  "${REPOSITORY_ROOT}/vnext/backend/benchmarks/s2b_capacity_census.py" \
  "$@"
