#!/usr/bin/env bash
set -euo pipefail
exec python3 -B -I "$(dirname "$0")/real_journey.py" "$@"
