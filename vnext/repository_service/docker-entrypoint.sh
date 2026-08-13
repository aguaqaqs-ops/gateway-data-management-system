#!/bin/sh
# Repository Service entrypoint: prepare server-owned layout then drop to gateway.
set -eu

DATA_ROOT="${GATEWAY_REPOSITORY_DATA_ROOT:-/var/lib/gateway/repository}"
GATEWAY_USER="${GATEWAY_REPOSITORY_GATEWAY_USER:-gateway}"
ARTIFACTS="${DATA_ROOT}/artifacts"

python -m gateway_repository_service.artifact_layout \
  --data-root "${DATA_ROOT}" \
  --artifacts "${ARTIFACTS}" \
  --gateway-user "${GATEWAY_USER}"

if command -v runuser >/dev/null 2>&1; then
  exec runuser -u "${GATEWAY_USER}" -- "$@"
fi
exec su -s /bin/sh -c 'exec "$@"' "${GATEWAY_USER}" -- "$@"
