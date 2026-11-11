#!/bin/sh
# Repository Service entrypoint: prepare server-owned layout then drop to gateway.
set -eu

LAYOUT_FILE="${GATEWAY_STORAGE_LAYOUT_FILE:?GATEWAY_STORAGE_LAYOUT_FILE is required}"
GATEWAY_USER="${GATEWAY_REPOSITORY_GATEWAY_USER:-gateway}"

python -c 'from pathlib import Path; import os; from gateway_repository_service.deployment_config import DeploymentConfig; from gateway_repository_service.runtime_preflight import RuntimePreflight; RuntimePreflight(DeploymentConfig.load(Path(os.environ["GATEWAY_STORAGE_LAYOUT_FILE"]), Path(os.environ["GATEWAY_RESOURCE_PROFILE_FILE"])), "repository_service", startup_capacity=False)'

python -m gateway_repository_service.artifact_layout \
  --storage-layout-file "${LAYOUT_FILE}" \
  --gateway-user "${GATEWAY_USER}"

# Drop privileges in this process and exec the command directly. A supervising
# runuser/su wrapper escalates TERM to KILL after two seconds, which would bypass
# the service's own bounded shutdown and the maintenance command's no-KILL rule.
exec python -c '
import os, pwd, sys
account = pwd.getpwnam(sys.argv[1])
os.initgroups(account.pw_name, account.pw_gid)
os.setgid(account.pw_gid)
os.setuid(account.pw_uid)
os.environ.update(HOME=account.pw_dir, SHELL=account.pw_shell,
                  USER=account.pw_name, LOGNAME=account.pw_name)
os.execvp(sys.argv[2], sys.argv[2:])
' "${GATEWAY_USER}" "$@"
