#!/bin/sh
# Repository Service entrypoint: prepare server-owned layout then drop to gateway.
set -eu

LAYOUT_FILE="${GATEWAY_STORAGE_LAYOUT_FILE:?GATEWAY_STORAGE_LAYOUT_FILE is required}"
GATEWAY_USER="${GATEWAY_REPOSITORY_GATEWAY_USER:-gateway}"

python -c 'from pathlib import Path; import os; from gateway_repository_service.deployment_config import DeploymentConfig; from gateway_repository_service.runtime_preflight import RuntimePreflight; RuntimePreflight(DeploymentConfig.load(Path(os.environ["GATEWAY_STORAGE_LAYOUT_FILE"]), Path(os.environ["GATEWAY_RESOURCE_PROFILE_FILE"])), "repository_service")'

python -m gateway_repository_service.artifact_layout \
  --storage-layout-file "${LAYOUT_FILE}" \
  --gateway-user "${GATEWAY_USER}"

if command -v runuser >/dev/null 2>&1; then
  exec runuser -u "${GATEWAY_USER}" -- "$@"
fi
exec su -s /bin/sh -c 'exec "$@"' "${GATEWAY_USER}" -- "$@"
