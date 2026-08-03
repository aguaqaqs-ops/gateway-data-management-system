#!/bin/sh
set -eu

# The normal entry point creates a provenance-bound systemd service instance.
# The same script is installed at /usr/local/libexec for the service instance,
# which keeps the checked-in launcher and the service implementation identical.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
RUN_ROOT=${GATEWAY_P2R1_RUN_ROOT:-/run/gateway-p2r1}
UNIT_PREFIX=gateway-p2r1-runner
IMAGE=${GATEWAY_P2R1_IMAGE:-gateway-p2r1-repository:dev}
CACHE_CONDITION=${GATEWAY_P2R1_CACHE_CONDITION:-retained-dependency-cache}

fail() {
  echo "p2-r1 launcher: $*" >&2
  exit 2
}

valid_cache() {
  case "$1" in
    retained-dependency-cache|cold-dependencies) return 0 ;;
    *) return 1 ;;
  esac
}

valid_project_name() {
  printf '%s\n' "$1" | grep -Eq '^[a-z0-9][a-z0-9_-]*$'
}

json_write() {
  target=$1
  shift
  python3 - "$target" "$@" <<'PY'
import json
import os
import sys
from pathlib import Path

target = Path(sys.argv[1])
kind = sys.argv[2]
values = sys.argv[3:]
target.parent.mkdir(parents=True, exist_ok=True)
temporary = target.with_name(f".{target.name}.tmp")
if kind == "argv":
    value = values
else:
    value = json.loads(values[0])
with temporary.open("w", encoding="utf-8") as handle:
    json.dump(value, handle, sort_keys=True, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, target)
PY
}

write_manifest() {
  target=$1
  image_id=$2
  revision=$3
  tree_digest=$4
  lock_sha=$5
  dolt_version=$6
  uv_version=$7
  connector_version=$8
  pyarrow_version=$9
  cache_condition=${10}
  project_name=${11}
  python3 - "$target" "$image_id" "$revision" "$tree_digest" "$lock_sha" "$dolt_version" "$uv_version" "$connector_version" "$pyarrow_version" "$cache_condition" "$project_name" <<'PY'
import json
import os
import sys
from pathlib import Path

target = Path(sys.argv[1])
manifest = {
    "image_digest": sys.argv[2],
    "build_revision": sys.argv[3],
    "source_tree_sha256": sys.argv[4],
    "lock_sha256": sys.argv[5],
    "dolt_version": sys.argv[6],
    "uv_version": sys.argv[7],
    "mysql_connector_version": sys.argv[8],
    "pyarrow_version": sys.argv[9],
    "cache_condition": sys.argv[10],
    "project_name": sys.argv[11],
    "manifest_version": "p2-r1-provenance-v2",
}

temporary = target.with_name(f".{target.name}.tmp")
with temporary.open("w", encoding="utf-8") as handle:
    json.dump(manifest, handle, sort_keys=True, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, target)
PY
  chmod 0444 "$target"
}

write_storage_layout() {
  target=$1
  container_id=$2
  project_name=$3
  destination=$4
  mounts=$(docker inspect --format '{{json .Mounts}}' "$container_id") \
    || fail "cannot inspect target container mounts"
  volume_name=$(python3 - "$mounts" "$destination" "$project_name" <<'PY'
import json
import sys

mounts = json.loads(sys.argv[1])
destination = sys.argv[2]
matches = [mount for mount in mounts if mount.get("Destination") == destination]
if len(matches) != 1:
    raise SystemExit("target data root must have exactly one mount")
mount = matches[0]
if mount.get("Type") != "volume" or mount.get("RW") is not True:
    raise SystemExit("target data root is not a writable named volume")
name = mount.get("Name")
if not isinstance(name, str) or not name:
    raise SystemExit("target volume name is missing")
print(name)
PY
) || fail "target volume mount validation failed"
  volume_json=$(docker volume inspect --format '{{json .}}' "$volume_name") \
    || fail "cannot inspect target probe volume"
  filesystem_type=$(docker exec "$container_id" stat -f -c '%T' "$destination") \
    || fail "cannot inspect target volume filesystem"
  root_identity_raw=$(docker exec "$container_id" stat -c '%d:%i' "$destination") \
    || fail "cannot inspect target volume root identity"
  root_identity=$(printf '%s' "$root_identity_raw" | sha256sum | awk '{print "sha256:" $1}')
  python3 - "$target" "$destination" "$volume_name" "$project_name" \
    "$filesystem_type" "$root_identity" "$volume_json" <<'PY'
import json
import os
import sys
from pathlib import Path

target = Path(sys.argv[1])
destination = sys.argv[2]
volume_name = sys.argv[3]
project = sys.argv[4]
filesystem_type = sys.argv[5]
root_identity = sys.argv[6]
volume = json.loads(sys.argv[7])
labels = volume.get("Labels") or {}
if labels.get("com.docker.compose.project") != project:
    raise SystemExit("target volume is not owned by this Compose project")
if volume.get("Name") != volume_name:
    raise SystemExit("docker volume identity changed during inspection")
manifest = {
    "storage_layout_version": "p2-r1-storage-layout-v1",
    "data_root": destination,
    "destination": destination,
    "mount_type": "volume",
    "read_write": True,
    "volume_name": volume_name,
    "volume_project": project,
    "storage_root_identity": root_identity,
    "filesystem_type": filesystem_type,
}
temporary = target.with_name(f".{target.name}.tmp")
with temporary.open("w", encoding="utf-8") as handle:
    json.dump(manifest, handle, sort_keys=True, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, target)
PY
  chmod 0444 "$target"
}

write_layout() {
  target=$1
  delegated_root=$2
  supervisor=$3
  samples=$4
  parent_control_group=$5
  slice_control_group=$6
  service_control_group=$7
  delegated_control_group=$8
  supervisor_control_group=$9
  python3 - "$target" "$delegated_root" "$supervisor" "$samples" \
    "$parent_control_group" "$slice_control_group" "$service_control_group" \
    "$delegated_control_group" "$supervisor_control_group" <<'PY'
import json
import os
import sys
from pathlib import Path

target = Path(sys.argv[1])
value = {
    "layout_version": "p2-r1-cgroup-layout-v1",
    "delegated_root": sys.argv[2],
    "supervisor": sys.argv[3],
    "samples": sys.argv[4],
    "parent_control_group": sys.argv[5],
    "slice_control_group": sys.argv[6],
    "service_control_group": sys.argv[7],
    "delegated_control_group": sys.argv[8],
    "supervisor_control_group": sys.argv[9],
}
temporary = target.with_name(f".{target.name}.tmp")
with temporary.open("w", encoding="utf-8") as handle:
    json.dump(value, handle, sort_keys=True, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, target)
PY
  chmod 0444 "$target"
}

image_metadata() {
  IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$IMAGE")
  IMAGE_REVISION=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE")
  IMAGE_TREE=$(docker image inspect --format '{{index .Config.Labels "gateway.p2r1.source-tree-sha256"}}' "$IMAGE")
  IMAGE_LOCK=$(docker image inspect --format '{{index .Config.Labels "gateway.p2r1.uv-lock-sha256"}}' "$IMAGE")
  IMAGE_DOLT=$(docker image inspect --format '{{index .Config.Labels "gateway.p2r1.dolt-version"}}' "$IMAGE")
  IMAGE_UV=$(docker image inspect --format '{{index .Config.Labels "gateway.p2r1.uv-version"}}' "$IMAGE")
  IMAGE_CONNECTOR=$(docker image inspect --format '{{index .Config.Labels "gateway.p2r1.mysql-connector-version"}}' "$IMAGE")
  IMAGE_PYARROW=$(docker image inspect --format '{{index .Config.Labels "gateway.p2r1.pyarrow-version"}}' "$IMAGE")
  printf '%s\n' "$IMAGE_ID" | grep -Eq '^sha256:[0-9a-f]{64}$' || fail "image ID is not a sha256 digest"
  printf '%s\n' "$IMAGE_REVISION" | grep -Eq '^[0-9a-f]{40,64}$' || fail "image revision label is invalid"
  printf '%s\n' "$IMAGE_TREE" | grep -Eq '^sha256:[0-9a-f]{64}$' || fail "source tree label is invalid"
  printf '%s\n' "$IMAGE_LOCK" | grep -Eq '^[0-9a-f]{64}$' || fail "lock label is invalid"
  test "$IMAGE_DOLT" = "2.1.11" || fail "image Dolt version is not 2.1.11"
  test "$IMAGE_UV" = "0.11.28" || fail "image uv version is not 0.11.28"
  test "$IMAGE_CONNECTOR" = "9.7.0" || fail "image connector version is not 9.7.0"
  test "$IMAGE_PYARROW" = "25.0.0" || fail "image PyArrow version is not 25.0.0"
}

clean_source_metadata() {
  test -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" \
    || fail "formal launcher requires a clean tracked and untracked worktree"
  SOURCE_REVISION=$(git -C "$REPO_ROOT" rev-parse HEAD)
  SOURCE_TREE_SHA="sha256:$(git -C "$REPO_ROOT" archive HEAD | sha256sum | awk '{print $1}')"
  LOCK_SHA=$(sha256sum "$REPO_ROOT/vnext/repository_service/uv.lock" | awk '{print $1}')
  test "$SOURCE_TREE_SHA" = "$IMAGE_TREE" || fail "image source tree digest does not match source"
  test "$SOURCE_REVISION" = "$IMAGE_REVISION" || fail "image revision does not match source"
  test "$LOCK_SHA" = "$IMAGE_LOCK" || fail "image lock label does not match source"
}

read_output_argument() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for index, value in enumerate(args):
    if value == "--output" and index + 1 < len(args):
        output = args[index + 1]
        break
    if value.startswith("--output="):
        output = value.split("=", 1)[1]
        break
else:
    raise SystemExit("formal launcher requires --output")
path = Path(output)
if not path.is_absolute():
    raise SystemExit("formal launcher requires an absolute --output path")
print(path)
PY
}

artifact_path() {
  python3 - "$1" "$2" <<'PY'
import sys
from pathlib import Path

print(Path(sys.argv[1]).with_suffix(sys.argv[2]))
PY
}

publish_export_file() {
  python3 - "$1" "$2" <<'PY'
import ctypes
import errno
import hashlib
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
if target.exists():
    raise FileExistsError(target)
if source.stat().st_dev != target.parent.stat().st_dev:
    raise OSError("artifact staging and target are on different filesystems")
source_size = source.stat().st_size
def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()
source_digest = digest(source)
with source.open("rb") as handle:
    os.fsync(handle.fileno())
def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
fsync_dir(source.parent)
libc = ctypes.CDLL(None, use_errno=True)
renameat2 = libc.renameat2
renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
renameat2.restype = ctypes.c_int
if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(target)
    raise OSError(error, os.strerror(error))
fsync_dir(source.parent)
fsync_dir(target.parent)
if target.stat().st_size != source_size:
    raise OSError("published artifact size changed")
if digest(target) != source_digest:
    raise OSError("published artifact digest changed")
PY
}

validate_raw_jsonl() {
  python3 - "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
target_status = int(sys.argv[2])
records = []
with path.open("r", encoding="utf-8", newline="") as handle:
    for line in handle:
        if not line.endswith("\n") or not line.strip():
            raise SystemExit("raw JSONL has an incomplete or empty line")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise SystemExit("raw JSONL record is not an object")
        records.append(value)
if not records:
    raise SystemExit("raw JSONL is empty")
last = records[-1]
is_terminal = (
    last.get("record_type") == "run_status"
    and last.get("status") == "incomplete"
    and last.get("p2_r1_exit") == "no-go"
)
if target_status != 0 and not is_terminal:
    raise SystemExit("failed target raw JSONL lacks terminal incomplete/no-go status")
if target_status == 0 and any(value.get("record_type") == "run_status" for value in records):
    raise SystemExit("successful target raw JSONL contains terminal failure status")
PY
}

prepare_artifact_destination() {
  HOST_OUTPUT=$(read_output_argument "$run_dir/argv.json") || fail "cannot resolve --output"
  OUTPUT_PARENT=$(dirname "$HOST_OUTPUT")
  mkdir -p "$OUTPUT_PARENT"
  for artifact in "$HOST_OUTPUT" "$(artifact_path "$HOST_OUTPUT" .summary.json)" "$(artifact_path "$HOST_OUTPUT" .md)"; do
    test ! -e "$artifact" || fail "formal artifact already exists: $artifact"
  done
  ARTIFACT_STAGE=$(mktemp -d "$OUTPUT_PARENT/.p2-r1-export-$run_id.XXXXXX")
  ARTIFACT_EXPORT_ATTEMPTED=0
  ARTIFACT_EXPORT_FAILED=0
}

export_artifacts() {
  test "$ARTIFACT_EXPORT_ATTEMPTED" -eq 0 || return 0
  ARTIFACT_EXPORT_ATTEMPTED=1
  raw_target="$HOST_OUTPUT"
  summary_target=$(artifact_path "$HOST_OUTPUT" .summary.json)
  report_target=$(artifact_path "$HOST_OUTPUT" .md)
  raw_stage="$ARTIFACT_STAGE/raw.jsonl"
  summary_stage="$ARTIFACT_STAGE/summary.json"
  report_stage="$ARTIFACT_STAGE/report.md"
  export_error=0
  if ! docker inspect --format '{{.State.Running}}' "$container_id" 2>/dev/null | grep -qx false; then
    export_error=1
  elif ! docker cp "$container_id:$raw_target" "$raw_stage"; then
    export_error=1
  elif ! validate_raw_jsonl "$raw_stage" "$target_status"; then
    export_error=1
  elif ! publish_export_file "$raw_stage" "$raw_target"; then
    export_error=1
  fi
  for pair in "$summary_target:$summary_stage" "$report_target:$report_stage"; do
    target=${pair%%:*}
    stage=${pair#*:}
    if docker cp "$container_id:$target" "$stage"; then
      publish_export_file "$stage" "$target" || export_error=1
    elif test "$target_status" -eq 0; then
      export_error=1
    fi
  done
  if test "$target_status" -eq 0 && test "$export_error" -ne 0; then
    echo "p2-r1 launcher: successful target did not export all artifacts" >&2
  fi
  if test "$export_error" -ne 0; then
    ARTIFACT_EXPORT_FAILED=1
    echo "p2-r1 launcher: artifact staging retained at $ARTIFACT_STAGE" >&2
    return 1
  fi
  ARTIFACT_EXPORT_COMPLETE=1
  rmdir "$ARTIFACT_STAGE" 2>/dev/null || true
  ARTIFACT_STAGE=""
  return 0
}

stop_target_and_wait() {
  test -n "$container_id" || return 0
  running=$(docker inspect --format '{{.State.Running}}' "$container_id" 2>/dev/null || echo false)
  if test "$running" = true; then
    docker stop -t 5 "$container_id" >/dev/null 2>&1 || true
    i=0
    while test "$i" -lt 100; do
      running=$(docker inspect --format '{{.State.Running}}' "$container_id" 2>/dev/null || echo false)
      test "$running" = false && break
      i=$((i + 1))
      sleep 0.05
    done
    if test "$running" = true; then
      docker kill "$container_id" >/dev/null 2>&1 || true
      i=0
      while test "$i" -lt 100; do
        running=$(docker inspect --format '{{.State.Running}}' "$container_id" 2>/dev/null || echo false)
        test "$running" = false && break
        i=$((i + 1))
        sleep 0.05
      done
    fi
    test "$running" = false || return 1
    docker wait "$container_id" >/dev/null 2>&1 || true
    test "$target_status" -eq 0 && target_status=125
  fi
  return 0
}

service_run() {
  run_id=$1
  run_dir="$RUN_ROOT/$run_id"
  test -f "$run_dir/environment" || fail "service run environment is missing"
  # shellcheck disable=SC1091
  . "$run_dir/environment"
  REPO_ROOT=${GATEWAY_P2R1_REPO_ROOT:-$REPO_ROOT}
  COMPOSE_FILE=${GATEWAY_P2R1_COMPOSE_FILE:-$REPO_ROOT/vnext/deploy/compose.yaml}
  PROJECT_NAME=${GATEWAY_P2R1_PROJECT_NAME:-gateway-p2r1-$run_id}
  valid_project_name "$PROJECT_NAME" || fail "Compose project name is invalid"
  UNIT="$UNIT_PREFIX@$run_id.service"
  container_id=""
  container_cgroup=""
  supervisor_cgroup=""
  samples_cgroup=""
  cleanup_failed=0
  compose_started=0
  target_status=125
  ARTIFACT_STAGE=""
  ARTIFACT_EXPORT_ATTEMPTED=1
  ARTIFACT_EXPORT_COMPLETE=0
  ARTIFACT_EXPORT_FAILED=0
  probe_volume_ids=""
  project_runtime_is_clean() {
    test -z "$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME")" \
      && test -z "$(docker network ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME")"
  }
  project_is_clean() {
    project_runtime_is_clean \
      && test -z "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME")"
  }
  force_runtime_cleanup() {
    docker ps -aq --filter "label=com.docker.compose.project=$PROJECT_NAME" | while read -r object; do
      test -n "$object" && docker rm -f "$object" || true
    done
    docker network ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME" | while read -r object; do
      test -n "$object" && docker network rm "$object" || true
    done
  }
  force_project_cleanup() {
    force_runtime_cleanup
    docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME" | while read -r object; do
      test -n "$object" && docker volume rm "$object" || true
    done
  }
  project_probe_volumes_retained() {
    test -n "$probe_volume_ids" || return 1
    for volume_id in $probe_volume_ids; do
      docker volume inspect "$volume_id" >/dev/null 2>&1 || return 1
    done
  }
  cleanup_target() {
    cleanup_status=0
    if test "$compose_started" -eq 1; then
      if test -z "$container_id"; then
        container_id=$(docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --profile p2-r1 ps -aq | head -n 1)
      fi
      if ! stop_target_and_wait; then
        echo "p2-r1 launcher: target container did not stop cleanly" >&2
        cleanup_status=1
      fi
      if test -n "$container_id" && test "$ARTIFACT_EXPORT_ATTEMPTED" -eq 0; then
        export_artifacts || cleanup_status=1
      fi
      if test "$target_status" -eq 0 && test "$ARTIFACT_EXPORT_COMPLETE" -eq 1 \
        && test "$ARTIFACT_EXPORT_FAILED" -eq 0; then
        if ! docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --profile p2-r1 down -v; then
          cleanup_status=1
        fi
        if project_is_clean; then
          if test "$cleanup_status" -eq 0; then
            container_id=""
            compose_started=0
          fi
        else
          force_project_cleanup
          project_is_clean || cleanup_status=1
          if project_is_clean && test "$cleanup_status" -eq 0; then
            container_id=""
            compose_started=0
          fi
        fi
      else
        echo "p2-r1 launcher: retaining probe volume because target or artifact publication failed" >&2
        echo "p2-r1 launcher: recovery quarantine project=$PROJECT_NAME volume_ids=${probe_volume_ids:-none} staging=${ARTIFACT_STAGE:-none}" >&2
        if ! docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --profile p2-r1 down; then
          cleanup_status=1
        fi
        if project_runtime_is_clean; then
          if test "$cleanup_status" -eq 0; then
            container_id=""
            compose_started=0
          fi
        else
          force_runtime_cleanup
          project_runtime_is_clean || cleanup_status=1
          if test "$cleanup_status" -eq 0; then
            container_id=""
            compose_started=0
          fi
        fi
        project_probe_volumes_retained || cleanup_status=1
        if ! project_probe_volumes_retained; then
          echo "p2-r1 launcher: source probe volume is missing after failed publication" >&2
        fi
      fi
    fi
    for cgroup_path in "$samples_cgroup" "$supervisor_cgroup"; do
      test -n "$cgroup_path" || continue
      i=0
      while test "$i" -lt 100 && test -d "$cgroup_path"; do
        rmdir "$cgroup_path" 2>/dev/null || true
        test -d "$cgroup_path" || break
        i=$((i + 1))
        sleep 0.05
      done
      test ! -d "$cgroup_path" || cleanup_status=1
    done
    for cgroup_path in "$container_cgroup" "$supervisor_cgroup" "$samples_cgroup"; do
      test -n "$cgroup_path" || continue
      i=0
      while test "$i" -lt 100 && test -e "$cgroup_path"; do
        i=$((i + 1))
        sleep 0.05
      done
      if test -e "$cgroup_path"; then
        cleanup_status=1
        echo "p2-r1 launcher: cgroup cleanup left $cgroup_path" >&2
      fi
    done
    if test "$cleanup_status" -ne 0; then
      cleanup_failed=1
      return 1
    fi
    return 0
  }
  on_exit() {
    exit_code=$?
    trap - EXIT HUP INT TERM
    cleanup_target || true
    if test "$exit_code" -eq 0 && { test "$cleanup_failed" -ne 0 || test "$ARTIFACT_EXPORT_FAILED" -ne 0; }; then
      exit_code=2
    fi
    exit "$exit_code"
  }
  trap on_exit EXIT HUP INT TERM
  image_metadata
  clean_source_metadata
  test "$(docker info --format '{{.CgroupDriver}}')" = systemd \
    || fail "Docker must use the systemd cgroup driver"
  PARENT_SLICE=$(systemctl show "$UNIT" -p Slice --value)
  test -n "$PARENT_SLICE" && printf '%s\n' "$PARENT_SLICE" | grep -Eq '\.slice$' \
    || fail "runner service has no systemd slice parent"
  SLICE_CONTROL_GROUP=$(systemctl show "$PARENT_SLICE" -p ControlGroup --value)
  test -n "$SLICE_CONTROL_GROUP" && test "$SLICE_CONTROL_GROUP" != "-" \
    || fail "systemd did not expose the per-run slice ControlGroup"
  printf '%s\n' "$PARENT_SLICE" | grep -Eq '^gateway-p2r1-[a-z0-9][a-z0-9_]*\.slice$' \
    || fail "runner service did not resolve to a unique per-run slice"
  TOP_SLICE=$(systemctl show "$PARENT_SLICE" -p Slice --value)
  test "$TOP_SLICE" = "gateway-p2r1.slice" \
    || fail "per-run slice is outside the dedicated P2-R1 slice"
  TOP_SLICE_CONTROL_GROUP=$(systemctl show "$TOP_SLICE" -p ControlGroup --value)
  test -n "$TOP_SLICE_CONTROL_GROUP" && test "$TOP_SLICE_CONTROL_GROUP" != "-" \
    || fail "systemd did not expose the dedicated P2-R1 slice ControlGroup"
  SERVICE_CONTROL_GROUP=$(systemctl show "$UNIT" -p ControlGroup --value)
  test -n "$SERVICE_CONTROL_GROUP" && test "$SERVICE_CONTROL_GROUP" != "-" \
    || fail "systemd did not expose the runner service ControlGroup"
  test "$SERVICE_CONTROL_GROUP" != "$SLICE_CONTROL_GROUP" \
    || fail "runner service ControlGroup is the parent slice itself"
  case "$SERVICE_CONTROL_GROUP" in
    "$SLICE_CONTROL_GROUP"/*) : ;;
    *) fail "runner service is not a child of its per-run slice" ;;
  esac
  test "${SERVICE_CONTROL_GROUP%/*}" = "$SLICE_CONTROL_GROUP" \
    || fail "runner service is not a direct per-run slice sibling"
  CGROUP_MOUNT_ROOT="/sys/fs/cgroup$SLICE_CONTROL_GROUP"
  test -d "$CGROUP_MOUNT_ROOT" || fail "resolved cgroup mount root is unavailable"
  for file in cgroup.procs cgroup.threads cgroup.subtree_control; do
    test -e "$CGROUP_MOUNT_ROOT/$file" || fail "cgroup mount root lacks $file"
  done

  export GATEWAY_P2R1_CGROUP_PARENT="$PARENT_SLICE"
  export GATEWAY_P2R1_CGROUP_CONTROL_GROUP="$SLICE_CONTROL_GROUP"
  export GATEWAY_P2R1_PARENT_SLICE="$PARENT_SLICE"
  export GATEWAY_P2R1_PARENT_SLICE_CONTROL_GROUP="$TOP_SLICE_CONTROL_GROUP"
  export GATEWAY_P2R1_SERVICE_CONTROL_GROUP="$SERVICE_CONTROL_GROUP"
  export GATEWAY_P2R1_CGROUP_ROOT="$CGROUP_MOUNT_ROOT"
  export GATEWAY_P2R1_RUN_DIR="$run_dir"
  export GATEWAY_P2R1_PROVENANCE_MANIFEST="$run_dir/provenance.json"
  export GATEWAY_P2R1_IMAGE_DIGEST="$IMAGE_ID"
  export GATEWAY_P2R1_BUILD_REVISION="$IMAGE_REVISION"
  export GATEWAY_P2R1_CACHE_CONDITION="$CACHE_CONDITION"
  export GATEWAY_P2R1_LOCK_SHA256="$IMAGE_LOCK"
  export GATEWAY_P2R1_SOURCE_TREE_SHA256="$IMAGE_TREE"
  export GATEWAY_P2R1_PROVENANCE_VERIFIED=1
  prepare_artifact_destination

  compose_started=1
  if ! docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --profile p2-r1 up -d --no-build repository-probe; then
    cleanup_target || true
    fail "target container failed to start"
  fi
  container_id=$(docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --profile p2-r1 ps -q repository-probe)
  test -n "$container_id" || fail "target container ID was not reported"
  probe_volume_ids=$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT_NAME")
  test -n "$probe_volume_ids" || fail "target probe volume was not created"
  container_pid=""
  i=0
  while test "$i" -lt 200; do
    container_pid=$(docker inspect --format '{{.State.Pid}}' "$container_id")
    test "$container_pid" != "0" && test -n "$container_pid" && test -f "/proc/$container_pid/cgroup" && break
    i=$((i + 1))
    sleep 0.05
  done
  test -n "$container_pid" && test -f "/proc/$container_pid/cgroup" \
    || fail "target container PID was not available"
  container_membership=$(awk -F: '$1 == "0" {print $3}' "/proc/$container_pid/cgroup")
  test "$container_membership" = "$SLICE_CONTROL_GROUP" \
    || case "$container_membership" in
         "$SLICE_CONTROL_GROUP"/*) : ;;
         *) fail "target container is outside the per-run slice" ;;
       esac
  case "$container_membership" in
    "$SERVICE_CONTROL_GROUP"/*) fail "target container is inside runner service subtree" ;;
  esac
  test "${container_membership%/*}" = "$SLICE_CONTROL_GROUP" \
    || fail "target container is not a direct per-run slice sibling"
  container_relative=${container_membership#"$SLICE_CONTROL_GROUP"/}
  test -n "$container_relative" && test "$container_relative" != "$container_membership" \
    || fail "target container cgroup is not a child of the delegated parent"
  printf '%s\n' "$container_relative" | grep -Eq '^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$' \
    || fail "target container cgroup relative path is invalid"
  container_cgroup="/sys/fs/cgroup$container_membership"
  supervisor_cgroup="$container_cgroup/supervisor"
  samples_cgroup="$container_cgroup/samples"
  test -d "$container_cgroup" || fail "target container cgroup path is unavailable"
  test ! -e "$supervisor_cgroup" && test ! -e "$samples_cgroup" \
    || fail "target container cgroup topology already exists"
  mkdir "$supervisor_cgroup" "$samples_cgroup" \
    || fail "cannot create target supervisor and samples cgroups"
  gateway_uid=$(awk '/^Uid:/ {print $2; exit}' "/proc/$container_pid/status")
  printf '%s\n' "$gateway_uid" | grep -Eq '^[0-9]+$' || fail "target UID is invalid"
  direct_pid=""
  while read -r direct_pid; do
    test -n "$direct_pid" || continue
    printf '%s\n' "$direct_pid" | grep -Eq '^[0-9]+$' \
      || fail "target cgroup contains an invalid PID"
    printf '%s\n' "$direct_pid" > "$supervisor_cgroup/cgroup.procs" \
      || fail "cannot migrate target PID into supervisor cgroup"
  done < "$container_cgroup/cgroup.procs"
  test ! -s "$container_cgroup/cgroup.procs" \
    || fail "target container cgroup still contains direct processes"
  test ! -s "$samples_cgroup/cgroup.procs" \
    || fail "new samples cgroup unexpectedly contains processes"
  printf '+memory +pids' > "$container_cgroup/cgroup.subtree_control" \
    || fail "cannot enable controllers on empty target container cgroup"
  printf '+memory +pids' > "$samples_cgroup/cgroup.subtree_control" \
    || fail "cannot enable controllers on empty samples cgroup"
  chown "$gateway_uid":"$gateway_uid" "$container_cgroup/cgroup.procs" \
    || fail "cannot delegate the common-ancestor cgroup.procs"
  chown "$gateway_uid":"$gateway_uid" "$samples_cgroup" \
    || fail "cannot delegate samples child creation"

  delegated_root_visible="/sys/fs/cgroup/gateway-p2r1/$container_relative"
  supervisor_visible="$delegated_root_visible/supervisor"
  samples_visible="$delegated_root_visible/samples"
  write_layout "$run_dir/cgroup-layout.json" "$delegated_root_visible" \
    "$supervisor_visible" "$samples_visible" "$SLICE_CONTROL_GROUP" \
    "$TOP_SLICE_CONTROL_GROUP" "$SERVICE_CONTROL_GROUP" "$container_membership" \
    "$container_membership/supervisor"
  write_storage_layout "$run_dir/storage-layout.json" "$container_id" \
    "$PROJECT_NAME" "/var/lib/gateway/repository"
  export GATEWAY_P2R1_CONTAINER_RELATIVE="$container_relative"
  export GATEWAY_P2R1_CGROUP_LAYOUT="$run_dir/cgroup-layout.json"
  : > "$run_dir/release"
  status=$(docker wait "$container_id")
  printf '%s\n' "$status" | grep -Eq '^[0-9]+$' || status=125
  target_status="$status"
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --profile p2-r1 logs --no-color repository-probe || true
  cleanup_target || true
  test "$cleanup_failed" -eq 0 || return 2
  test "$ARTIFACT_EXPORT_FAILED" -eq 0 || return 2
  if test "$status" -ne 0; then
    return "$status"
  fi
  return 0
}

if test "${1:-}" = "--service-run"; then
  test "$#" -eq 2 || fail "--service-run requires a run ID"
  service_run "$2"
  exit $?
fi

test "$(id -u)" -eq 0 || fail "formal target launcher must run as root"
REPO_ROOT=${GATEWAY_P2R1_REPO_ROOT:-$REPO_ROOT}
test -f "$REPO_ROOT/vnext/deploy/compose.yaml" || fail "repository root is invalid"
image_metadata
clean_source_metadata
valid_cache "$CACHE_CONDITION" || fail "unsupported cache condition"

RUN_ID="$(date +%Y%m%d%H%M%S)_$$"
PROJECT_NAME="gateway-p2r1-$RUN_ID"
valid_project_name "$PROJECT_NAME" || fail "generated Compose project name is invalid"
RUN_DIR="$RUN_ROOT/$RUN_ID"
umask 077
mkdir -p "$RUN_DIR"
chmod 0755 "$RUN_DIR"
trap 'rm -rf "$RUN_DIR"' EXIT HUP INT TERM
write_manifest "$RUN_DIR/provenance.json" "$IMAGE_ID" "$SOURCE_REVISION" \
  "$SOURCE_TREE_SHA" "$LOCK_SHA" "$IMAGE_DOLT" "$IMAGE_UV" "$IMAGE_CONNECTOR" "$IMAGE_PYARROW" "$CACHE_CONDITION" "$PROJECT_NAME"
json_write "$RUN_DIR/argv.json" argv "$@"
chmod 0444 "$RUN_DIR/argv.json"
cat > "$RUN_DIR/environment" <<EOF
GATEWAY_P2R1_REPO_ROOT=$REPO_ROOT
GATEWAY_P2R1_IMAGE=$IMAGE
GATEWAY_P2R1_CACHE_CONDITION=$CACHE_CONDITION
GATEWAY_P2R1_COMPOSE_FILE=${GATEWAY_P2R1_COMPOSE_FILE:-$REPO_ROOT/vnext/deploy/compose.yaml}
GATEWAY_P2R1_IMAGE_DIGEST=$IMAGE_ID
GATEWAY_P2R1_BUILD_REVISION=$SOURCE_REVISION
GATEWAY_P2R1_LOCK_SHA256=$LOCK_SHA
GATEWAY_P2R1_SOURCE_TREE_SHA256=$IMAGE_TREE
GATEWAY_P2R1_PROJECT_NAME=$PROJECT_NAME
EOF
chmod 0600 "$RUN_DIR/environment"

systemctl start --wait "$UNIT_PREFIX@$RUN_ID.service"
