#!/bin/sh
# Repository Service entrypoint: start artifact-broker then drop to gateway (ADR 0011).
set -eu

DATA_ROOT="${GATEWAY_REPOSITORY_DATA_ROOT:-/var/lib/gateway/repository}"
RUN_DIR="${GATEWAY_REPOSITORY_ARTIFACT_BROKER_RUN_DIR:-${DATA_ROOT}/run}"
BROKER_SOCK="${GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET:-${RUN_DIR}/artifact-broker.sock}"
BROKER_PIDFILE="${RUN_DIR}/artifact-broker.pid"
BROKER_USER="${GATEWAY_REPOSITORY_ARTIFACT_BROKER_USER:-artifact-broker}"
GATEWAY_USER="${GATEWAY_REPOSITORY_GATEWAY_USER:-gateway}"
ARTIFACTS="${DATA_ROOT}/artifacts"

mkdir -p "${RUN_DIR}" "${ARTIFACTS}"
chown "${BROKER_USER}:${GATEWAY_USER}" "${RUN_DIR}"
chmod 0750 "${RUN_DIR}"
# Directory tree only: broker owns dentries; do not recursively chown file contents.
chown "${BROKER_USER}:${GATEWAY_USER}" "${ARTIFACTS}"
chmod 0750 "${ARTIFACTS}"
if [ -d "${ARTIFACTS}" ]; then
  find "${ARTIFACTS}" -type d -exec chown "${BROKER_USER}:${GATEWAY_USER}" {} \;
  find "${ARTIFACTS}" -type d -name ready -exec chmod 0750 {} \;
  find "${ARTIFACTS}" -type d -name staging -exec chmod 0770 {} \;
  find "${ARTIFACTS}" -type d ! -name ready ! -name staging -exec chmod 0750 {} \;
  # Keep existing files readable/writable by gateway group without taking content ownership away.
  find "${ARTIFACTS}" -type f -exec chmod g+rw {} \;
fi

GATEWAY_UID="$(id -u "${GATEWAY_USER}")"
GATEWAY_GID="$(id -g "${GATEWAY_USER}")"
rm -f "${BROKER_SOCK}" "${BROKER_PIDFILE}"
if command -v runuser >/dev/null 2>&1; then
  runuser -u "${BROKER_USER}" -- \
    python -m gateway_repository_service.artifact_broker_server \
      --socket "${BROKER_SOCK}" \
      --peer-uid "${GATEWAY_UID}" \
      --peer-gid "${GATEWAY_GID}" \
      --artifacts-root "${ARTIFACTS}" &
else
  su -s /bin/sh -c \
    "python -m gateway_repository_service.artifact_broker_server --socket '${BROKER_SOCK}' --peer-uid '${GATEWAY_UID}' --peer-gid '${GATEWAY_GID}' --artifacts-root '${ARTIFACTS}'" \
    "${BROKER_USER}" &
fi
echo $! > "${BROKER_PIDFILE}"

i=0
while [ ! -S "${BROKER_SOCK}" ] && [ "$i" -lt 50 ]; do
  i=$((i + 1))
  sleep 0.1
done
if [ ! -S "${BROKER_SOCK}" ]; then
  echo "artifact-broker socket missing after startup" >&2
  exit 1
fi
chown "${BROKER_USER}:${GATEWAY_USER}" "${BROKER_SOCK}"
chmod 0660 "${BROKER_SOCK}"

export GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET="${BROKER_SOCK}"
export GATEWAY_REPOSITORY_ARTIFACT_BROKER_MODE=socket
export GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE="${BROKER_PIDFILE}"

if command -v runuser >/dev/null 2>&1; then
  runuser -u "${GATEWAY_USER}" -- python -c \
    "from pathlib import Path; from gateway_repository_service.artifact_broker import SocketArtifactDirBroker; SocketArtifactDirBroker(Path('${BROKER_SOCK}')).ping()"
else
  su -s /bin/sh -c \
    "python -c \"from pathlib import Path; from gateway_repository_service.artifact_broker import SocketArtifactDirBroker; SocketArtifactDirBroker(Path('${BROKER_SOCK}')).ping()\"" \
    "${GATEWAY_USER}"
fi

if command -v runuser >/dev/null 2>&1; then
  exec runuser -u "${GATEWAY_USER}" -- "$@"
fi
exec su -s /bin/sh -c 'exec "$@"' "${GATEWAY_USER}" -- "$@"
