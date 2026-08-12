#!/bin/sh
# Repository Service entrypoint: start artifact-broker then drop to gateway (ADR 0011).
set -eu

DATA_ROOT="${GATEWAY_REPOSITORY_DATA_ROOT:-/var/lib/gateway/repository}"
BROKER_SOCK="${GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET:-${DATA_ROOT}/artifact-broker.sock}"
BROKER_USER="${GATEWAY_REPOSITORY_ARTIFACT_BROKER_USER:-artifact-broker}"
GATEWAY_USER="${GATEWAY_REPOSITORY_GATEWAY_USER:-gateway}"

mkdir -p "${DATA_ROOT}/artifacts"
# Prefer broker ownership of artifact trees; group gateway retains traverse/read.
chown -R "${BROKER_USER}:${GATEWAY_USER}" "${DATA_ROOT}/artifacts" 2>/dev/null || true
find "${DATA_ROOT}/artifacts" -type d -exec chmod 0750 {} \; 2>/dev/null || true

GATEWAY_UID="$(id -u "${GATEWAY_USER}")"
rm -f "${BROKER_SOCK}"
if command -v runuser >/dev/null 2>&1; then
  runuser -u "${BROKER_USER}" -- \
    python -m gateway_repository_service.artifact_broker_server \
      --socket "${BROKER_SOCK}" --peer-uid "${GATEWAY_UID}" &
else
  su -s /bin/sh -c \
    "python -m gateway_repository_service.artifact_broker_server --socket '${BROKER_SOCK}' --peer-uid '${GATEWAY_UID}'" \
    "${BROKER_USER}" &
fi

i=0
while [ ! -S "${BROKER_SOCK}" ] && [ "$i" -lt 50 ]; do
  i=$((i + 1))
  sleep 0.1
done

export GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET="${BROKER_SOCK}"
chown "${BROKER_USER}:${GATEWAY_USER}" "${BROKER_SOCK}" 2>/dev/null || true
chmod 0660 "${BROKER_SOCK}" 2>/dev/null || true

if command -v runuser >/dev/null 2>&1; then
  exec runuser -u "${GATEWAY_USER}" -- "$@"
fi
exec su -s /bin/sh -c 'exec "$@"' "${GATEWAY_USER}" -- "$@"
