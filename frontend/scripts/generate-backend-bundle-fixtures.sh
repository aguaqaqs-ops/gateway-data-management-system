#!/usr/bin/env bash
# Regenerates the committed mock-bundle fixture source from the backend-owned
# presentation fixture generator. The wrapper only drives the backend entry
# (`vnext/scripts/generate-presentation-fixtures.py`): it never builds fixtures
# itself, never edits generator output, and replaces the committed tree
# wholesale after two byte-identical runs.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
FRONTEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
REPO_DIR="$(cd -- "$(git -C "$FRONTEND_DIR" rev-parse --show-toplevel)" && pwd -P)"
FIXTURE_SOURCE="$FRONTEND_DIR/src/test/fixtures/source/backend"
INPUT_ROOT="$REPO_DIR/vnext/fixtures/presentation-inputs"
GEN="$REPO_DIR/vnext/scripts/generate-presentation-fixtures.py"
BACKEND_PYTHON="$REPO_DIR/vnext/backend/.venv/bin/python"

WORK_DIR=""
LOG_DIR=""
CHECK_ONLY=0
usage() {
  cat <<'USAGE'
usage: frontend/scripts/generate-backend-bundle-fixtures.sh \
  --work-dir <empty-absolute-directory-outside-the-repository> \
  --log-dir <absolute-directory> [--check-only]

--check-only regenerates and compares twice without replacing the committed
fixture source.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --work-dir) [[ -z "$WORK_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; WORK_DIR="$2"; shift 2 ;;
    --log-dir) [[ -z "$LOG_DIR" && $# -ge 2 ]] || { usage >&2; exit 2; }; LOG_DIR="$2"; shift 2 ;;
    --check-only) CHECK_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "$WORK_DIR" && -n "$LOG_DIR" ]] || { usage >&2; exit 2; }
for value in "$WORK_DIR" "$LOG_DIR"; do
  [[ "$value" = /* ]] || { echo "error: 目录必须是绝对路径：$value" >&2; exit 2; }
done
[[ -d "$WORK_DIR" ]] || { echo "error: work dir 不存在：$WORK_DIR" >&2; exit 2; }
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/fixture-generation-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "hostname: $(hostname)"
echo "started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Inputs and provenance ---------------------------------------------------------
dirty="$(git -C "$REPO_DIR" status --porcelain)"
[[ -z "$dirty" ]] || { echo "error: worktree 有未提交改动，无法生成 fixture" >&2; exit 3; }
HEAD_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"
V3_TREE="$(git -C "$REPO_DIR" rev-parse HEAD:vnext)"
echo "commit: $HEAD_SHA"
echo "vnext_tree: $V3_TREE"
echo "input_manifest_sha256: $(sha256sum "$INPUT_ROOT/manifest.json" | awk '{print $1}')"
echo "generator: $GEN"
[[ -x "$BACKEND_PYTHON" ]] || {
  echo "error: 缺少 vnext/backend 的 uv 环境（$BACKEND_PYTHON）。先用 uv-consume.sh 同步并按需重建 Rust 扩展。" >&2
  exit 3
}

if [[ -n "$(ls -A "$WORK_DIR" 2>/dev/null)" ]]; then
  echo "error: work dir 必须为空：$WORK_DIR" >&2
  exit 2
fi
A_DIR="$WORK_DIR/a"
B_DIR="$WORK_DIR/b"
mkdir -p "$A_DIR" "$B_DIR"

run_generator() {
  local output_root="$1" phase="$2"
  echo "generator_${phase}_started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$BACKEND_PYTHON" "$GEN" --input-root "$INPUT_ROOT" --output-root "$output_root"
  echo "generator_${phase}_finished_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

run_generator "$A_DIR" one
run_generator "$B_DIR" two

# Two independent runs must be byte-identical: any difference stops the wrapper
# instead of silently committing what the node happened to produce.
echo "byte_identical: $(diff -qr "$A_DIR" "$B_DIR" >/dev/null && echo true || echo false)"
diff -qr "$A_DIR" "$B_DIR" && status=0 || status=$?
[[ "$status" -eq 0 ]] || { echo "error: 两次生成的输出不一致" >&2; exit 4; }

# Required outputs come from the backend-owned input manifest.
python3 - "$INPUT_ROOT/manifest.json" "$A_DIR" <<'PY'
import json, pathlib, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
root = pathlib.Path(sys.argv[2])
missing = [p for p in manifest["required_output_directories"] if not (root / p).is_dir()]
missing += [p for p in manifest["required_root_outputs"] if not (root / p).is_file()]
if missing:
    print("error: 缺少后端要求的输出：" + ", ".join(sorted(missing)), file=sys.stderr)
    raise SystemExit(5)
retired = [p for p in manifest.get("retired_output_directories", []) if (root / p).exists()]
if retired:
    print("error: 已退役目录仍被生成：" + ", ".join(retired), file=sys.stderr)
    raise SystemExit(5)
index = json.load(open(root / "index.json", encoding="utf-8"))
print("scenario_count:", len(index.get("scenarios", {})))
print("index_generator_commit:", index.get("generator_commit"))
print("index_vnext_tree:", index.get("vnext_tree"))
print("index_sha256:", __import__("hashlib").sha256((root / "index.json").read_bytes()).hexdigest())
PY

INDEX_TREE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["vnext_tree"])' "$A_DIR/index.json")"
[[ "$INDEX_TREE" == "$V3_TREE" ]] || { echo "error: index vnext_tree 与当前提交不一致：$INDEX_TREE != $V3_TREE" >&2; exit 6; }
echo "index_vnext_tree_matches: true"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "check_only: true (committed fixture source unchanged)"
else
  rm -rf "$FIXTURE_SOURCE"
  cp -a "$A_DIR/backend" "$FIXTURE_SOURCE"
  echo "replaced: $FIXTURE_SOURCE"
fi

echo "finished_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "log_file: $LOG_FILE"
