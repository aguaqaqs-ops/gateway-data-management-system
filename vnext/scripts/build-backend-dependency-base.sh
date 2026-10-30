#!/usr/bin/env bash
set -euo pipefail

# Build and retain the backend's locked Python and Rust dependency inputs.
# The image tag is derived from the full input digest; an existing tag with a
# different label is rejected instead of silently reused or overwritten.
# The tag digest includes the base image config digest and all RootFS DiffIDs.
# The local inspect ID is recorded as metadata only and is excluded from the tag.
# When comparing saved images across nodes, compare config digest plus every
# DiffID; inspect IDs are store-specific and must not be used for that check.
#
# Usage:
#   build-backend-dependency-base.sh [--print-input | --save <path>]
#   The derived tag uses the source image's config digest and all RootFS DiffIDs.
#   Its local inspect ID is metadata only and does not affect the tag.
#   Compare cross-node images by config digest plus every DiffID, never inspect ID.
#
# Environment:
#   GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE       optional; must equal the derived tag
#   GATEWAY_DOCKER_BUILD_NETWORK               dependency-base build network (default: host)

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${SCRIPT_ROOT}/backend/Dockerfile.dependency-base"
VNEXT_ROOT="${SCRIPT_ROOT}"
MODE=build
SAVE_PATH=""

case "${1:-}" in
  "") ;;
  --print-input)
    [[ $# -eq 1 ]] || { echo "usage: $0 [--print-input | --save <path>]" >&2; exit 2; }
    MODE=print
    ;;
  --save)
    [[ $# -eq 2 && -n "${2}" ]] || { echo "usage: $0 [--print-input | --save <path>]" >&2; exit 2; }
    SAVE_PATH="${2}"
    ;;
  *)
    echo "usage: $0 [--print-input | --save <path>]" >&2
    exit 2
    ;;
esac

command -v docker >/dev/null 2>&1 || { echo "error: docker is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "error: python3 is required" >&2; exit 1; }

PYTHON_VERSION="$(tr -d '[:space:]' < "${VNEXT_ROOT}/backend/.python-version")"
UV_VERSION="$(sed -n 's/^ARG UV_VERSION=//p' "${DOCKERFILE}" | head -n 1)"
RUSTUP_TOOLCHAIN="$(python3 - "${VNEXT_ROOT}/rust/rust-toolchain.toml" <<'PY'
import sys
import tomllib
from pathlib import Path

selector = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(selector["toolchain"]["channel"])
PY
)"
BASE_IMAGE="rust:${RUSTUP_TOOLCHAIN}-bookworm"

if [[ -z "${UV_VERSION}" || -z "${PYTHON_VERSION}" || -z "${RUSTUP_TOOLCHAIN}" ]]; then
  echo "error: unable to read locked backend dependency-base versions" >&2
  exit 1
fi

TMP_INPUTS="$(mktemp)"
TMP_BASE_IMAGE_ARCHIVE=""
cleanup() {
  rm -f -- "${TMP_INPUTS}"
  if [[ -n "${TMP_BASE_IMAGE_ARCHIVE}" ]]; then
    rm -f -- "${TMP_BASE_IMAGE_ARCHIVE}"
  fi
}
trap cleanup EXIT

load_base_image_id() {
  local image_id
  if ! image_id="$(docker image inspect --format '{{.Id}}' "${BASE_IMAGE}" 2>/dev/null)" \
      || [[ -z "${image_id}" ]]; then
    if [[ "${MODE}" == "print" ]]; then
      echo "error: base image ${BASE_IMAGE} is not present locally" >&2
      return 1
    fi
    docker pull "${BASE_IMAGE}"
    image_id="$(docker image inspect --format '{{.Id}}' "${BASE_IMAGE}")"
  fi
  printf '%s' "${image_id}"
}

load_base_image_identity() {
  TMP_BASE_IMAGE_ARCHIVE="$(mktemp)"
  docker image save --output "${TMP_BASE_IMAGE_ARCHIVE}" "${BASE_IMAGE}" >/dev/null
  python3 - "${TMP_BASE_IMAGE_ARCHIVE}" <<'PY'
import hashlib
import json
import sys
import tarfile

with tarfile.open(sys.argv[1], mode="r:*") as archive:
    manifest = json.load(archive.extractfile("manifest.json"))
    if len(manifest) != 1:
        raise SystemExit("error: expected one base image in docker save archive")
    config_blob = archive.extractfile(manifest[0]["Config"]).read()
    config = json.loads(config_blob)
    diff_ids = config.get("rootfs", {}).get("diff_ids")
    if not isinstance(diff_ids, list) or not diff_ids or not all(isinstance(item, str) for item in diff_ids):
        raise SystemExit("error: base image config has no complete RootFS DiffID list")

print(
    json.dumps(
        {
            "config_digest": "sha256:" + hashlib.sha256(config_blob).hexdigest(),
            "diff_ids": diff_ids,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY
  rm -f -- "${TMP_BASE_IMAGE_ARCHIVE}"
  TMP_BASE_IMAGE_ARCHIVE=""
}

write_inputs() {
  python3 - "${VNEXT_ROOT}" "${BASE_IMAGE}" "${1}" "${2}" "${PYTHON_VERSION}" "${UV_VERSION}" "${RUSTUP_TOOLCHAIN}" <<'PY'
import hashlib
import json
import sys
import tomllib
from pathlib import Path

root = Path(sys.argv[1])
base_image, base_image_id, base_image_identity_json, python_version, uv_version, toolchain = sys.argv[2:]
relative_files = (
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/.python-version",
    "rust/Cargo.lock",
    "rust/rust-toolchain.toml",
)
selector = tomllib.loads((root / "rust/rust-toolchain.toml").read_text(encoding="utf-8"))["toolchain"]
if selector["channel"] != toolchain:
    raise SystemExit("error: Rust toolchain selector changed while inputs were being read")
tag_inputs = {
    "schema": "gateway.backend.dependency-base-tag-inputs",
    "schema_version": 1,
    "files": {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in relative_files
    },
    "python_version": python_version,
    "uv_version": uv_version,
    "rust_toolchain": {
        "channel": selector["channel"],
        "profile": selector.get("profile", "default"),
        "components": sorted(selector.get("components", [])),
    },
    "base_image": base_image,
    "base_image_identity": json.loads(base_image_identity_json),
}
inputs = {
    "schema": "gateway.backend.dependency-base-inputs",
    "schema_version": 1,
    "tag_inputs": tag_inputs,
    "base_image_id": base_image_id,
}
print(json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
PY
}

input_digest() {
  python3 - "${1}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
canonical = json.dumps(
    payload["tag_inputs"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
).encode()
print(hashlib.sha256(canonical).hexdigest())
PY
}

BASE_IMAGE_ID="$(load_base_image_id)"
BASE_IMAGE_IDENTITY_JSON="$(load_base_image_identity)"
INPUTS_JSON="$(write_inputs "${BASE_IMAGE_ID}" "${BASE_IMAGE_IDENTITY_JSON}")"
printf '%s' "${INPUTS_JSON}" >"${TMP_INPUTS}"
INPUT_SHA256="$(input_digest "${TMP_INPUTS}")"
IMAGE_TAG="gateway-backend-deps:lock-${INPUT_SHA256:0:12}"
if [[ -n "${GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE:-}" \
    && "${GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE}" != "${IMAGE_TAG}" ]]; then
  echo "error: GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE does not match the current dependency input tag" >&2
  exit 1
fi

if [[ "${MODE}" == "print" ]]; then
  python3 - "${TMP_INPUTS}" "${INPUT_SHA256}" "${IMAGE_TAG}" <<'PY'
import json
import sys
from pathlib import Path

print(
    json.dumps(
        {
            "image": sys.argv[3],
            "input_sha256": sys.argv[2],
            "inputs": json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
)
PY
  exit 0
fi

if docker image inspect "${IMAGE_TAG}" >/dev/null 2>&1; then
  EXISTING_LABEL="$(docker image inspect --format '{{index .Config.Labels "gateway.backend.dependency-input-sha256"}}' "${IMAGE_TAG}")"
  if [[ "${EXISTING_LABEL}" != "${INPUT_SHA256}" ]]; then
    echo "error: refusing to reuse ${IMAGE_TAG}: dependency input label does not match ${INPUT_SHA256}" >&2
    exit 1
  fi
  echo "==> reusing ${IMAGE_TAG}"
else
  INPUTS_BASE64="$(base64 <"${TMP_INPUTS}" | tr -d '\n')"
  BUILD_NETWORK="${GATEWAY_DOCKER_BUILD_NETWORK:-host}"
  timeout 1800 docker build \
    --pull=false \
    --network="${BUILD_NETWORK}" \
    --file "${DOCKERFILE}" \
    --tag "${IMAGE_TAG}" \
    --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
    --build-arg "BASE_IMAGE_ID=${BASE_IMAGE_ID}" \
    --build-arg "DEPENDENCY_INPUT_SHA256=${INPUT_SHA256}" \
    --build-arg "DEPENDENCY_INPUTS_BASE64=${INPUTS_BASE64}" \
    --build-arg "BACKEND_PYPROJECT_SHA256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag_inputs"]["files"]["backend/pyproject.toml"])' "${TMP_INPUTS}")" \
    --build-arg "BACKEND_UV_LOCK_SHA256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag_inputs"]["files"]["backend/uv.lock"])' "${TMP_INPUTS}")" \
    --build-arg "BACKEND_PYTHON_VERSION_SHA256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag_inputs"]["files"]["backend/.python-version"])' "${TMP_INPUTS}")" \
    --build-arg "RUST_CARGO_LOCK_SHA256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag_inputs"]["files"]["rust/Cargo.lock"])' "${TMP_INPUTS}")" \
    --build-arg "RUST_TOOLCHAIN_SHA256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag_inputs"]["files"]["rust/rust-toolchain.toml"])' "${TMP_INPUTS}")" \
    --build-arg "PYTHON_VERSION=${PYTHON_VERSION}" \
    --build-arg "UV_VERSION=${UV_VERSION}" \
    --build-arg "RUSTUP_TOOLCHAIN=${RUSTUP_TOOLCHAIN}" \
    "${VNEXT_ROOT}"
fi

AFTER_BASE_IMAGE_ID="$(load_base_image_id)"
AFTER_BASE_IMAGE_IDENTITY_JSON="$(load_base_image_identity)"
if [[ "${AFTER_BASE_IMAGE_IDENTITY_JSON}" != "${BASE_IMAGE_IDENTITY_JSON}" ]]; then
  echo "error: backend dependency-base source image content changed during the build" >&2
  exit 1
fi
AFTER_INPUTS="$(write_inputs "${AFTER_BASE_IMAGE_ID}" "${AFTER_BASE_IMAGE_IDENTITY_JSON}")"
printf '%s' "${AFTER_INPUTS}" >"${TMP_INPUTS}"
AFTER_SHA256="$(input_digest "${TMP_INPUTS}")"
if [[ "${AFTER_SHA256}" != "${INPUT_SHA256}" ]]; then
  echo "error: backend dependency inputs changed during the build" >&2
  exit 1
fi

ACTUAL_LABEL="$(docker image inspect --format '{{index .Config.Labels "gateway.backend.dependency-input-sha256"}}' "${IMAGE_TAG}")"
if [[ "${ACTUAL_LABEL}" != "${INPUT_SHA256}" ]]; then
  echo "error: built dependency-base label does not match input digest ${INPUT_SHA256}" >&2
  exit 1
fi
IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE_TAG}")"
printf 'image=%s\ninput_sha256=%s\nimage_id=%s\n' "${IMAGE_TAG}" "${INPUT_SHA256}" "${IMAGE_ID}"

if [[ -n "${SAVE_PATH}" ]]; then
  docker save --output "${SAVE_PATH}" "${IMAGE_TAG}"
  SAVE_SHA256="$(sha256sum "${SAVE_PATH}" | awk '{print $1}')"
  printf 'save_file=%s\nsave_sha256=%s\n' "${SAVE_PATH}" "${SAVE_SHA256}"
fi
