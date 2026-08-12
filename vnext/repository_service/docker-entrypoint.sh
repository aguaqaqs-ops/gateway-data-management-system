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

_is_hex32() {
  [ "${#1}" -eq 32 ] || return 1
  case "$1" in
    *[!0-9a-f]*) return 1 ;;
  esac
  return 0
}

_same_dev_as_parent() {
  _path="$1"
  _parent=$(dirname "${_path}")
  _dev=$(stat -c %d "${_path}" 2>/dev/null || echo "")
  _pdev=$(stat -c %d "${_parent}" 2>/dev/null || echo "")
  [ -n "${_dev}" ] && [ "${_dev}" = "${_pdev}" ]
}

mkdir -p "${RUN_DIR}" "${ARTIFACTS}"
chown "${BROKER_USER}:${GATEWAY_USER}" "${RUN_DIR}"
chmod 0750 "${RUN_DIR}"
# Own only the known layout: artifacts/, hex32 repo dirs, ready/, staging/.
# Do not recurse, follow symlinks, enter mount points, or touch unknown names.
chown "${BROKER_USER}:${GATEWAY_USER}" "${ARTIFACTS}"
chmod 0750 "${ARTIFACTS}"
if [ -d "${ARTIFACTS}" ] && [ ! -L "${ARTIFACTS}" ]; then
  for repo in "${ARTIFACTS}"/*; do
    [ -e "${repo}" ] || continue
    [ -L "${repo}" ] && continue
    [ -d "${repo}" ] || continue
    _same_dev_as_parent "${repo}" || continue
    base=$(basename "${repo}")
    _is_hex32 "${base}" || continue
    chown "${BROKER_USER}:${GATEWAY_USER}" "${repo}"
    chmod 0750 "${repo}"
    if [ -d "${repo}/ready" ] && [ ! -L "${repo}/ready" ] && _same_dev_as_parent "${repo}/ready"; then
      chown "${BROKER_USER}:${GATEWAY_USER}" "${repo}/ready"
      chmod 0750 "${repo}/ready"
    fi
    if [ -d "${repo}/staging" ] && [ ! -L "${repo}/staging" ] && _same_dev_as_parent "${repo}/staging"; then
      chown "${BROKER_USER}:${GATEWAY_USER}" "${repo}/staging"
      chmod 0770 "${repo}/staging"
    fi
  done
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
