#!/usr/bin/env bash
# Dedicated 06 preparation only; exact produced SHA arguments require review first.
set -euo pipefail
[[ $# -eq 5 ]] || exit 2
candidate=$1
source=$(realpath -e -- "$2")
archive_sha=$3
identity_sha=$4
input_sha=$5
[[ $candidate =~ ^[0-9a-f]{40}$ && $archive_sha =~ ^[0-9a-f]{64}$ && $identity_sha =~ ^[0-9a-f]{64}$ && $input_sha =~ ^[0-9a-f]{64}$ ]] || exit 2
[[ $(hostname) = gw-dms-06 ]] || exit 2
[[ $(git -C "$source" rev-parse HEAD) = "$candidate" && -z $(git -C "$source" status --porcelain) ]] || exit 2
plan=docs/backend-vnext/refactoring/formal/plans
[[ $(realpath -e -- "$0") = "$source/$plan/p7-s1a-b-prefill-rs-dependency.sh" ]] || exit 2
incoming=/home/dev/gdds-test-tmp/p7-s1a-b-rs-deps-b47d6de3-incoming
out=/home/dev/gdds-test-tmp/p7-s1a-b-rs-deps-b47d6de3
[[ -d $incoming && ! -L $incoming && ! -e $out && ! -L $out ]] || exit 2
mkdir -- "$out"
mkdir -- "$out/archives"
cd -- "$source"
busy=/home/dev/gdds-node-busy.d
marker="$busy/p7-s1a-b-rs-deps-b47d6de3.owner"
tag=gateway-p2r1-repository:lock-b47d6de3cbce
container="p7-s1a-b-rs-prefill-${candidate:0:12}"
run() {
    local label=$1 result
    shift
    printf '\nSTEP=%s\nCOMMAND:' "$label"; printf ' %q' "$@"; printf '\n'
    if "$@"; then result=0; else result=$?; fi
    printf 'ORIGINAL_EXIT=%s\n' "$result"
    return "$result"
}
capture() {
    local label=$1 output=$2 result
    shift 2
    printf '\nSTEP=%s\nCOMMAND:' "$label"; printf ' %q' "$@"; printf '\n'
    if "$@" > "$output" 2>&1; then result=0; else result=$?; fi
    cat -- "$output"
    printf 'ORIGINAL_EXIT=%s\n' "$result"
    return "$result"
}
prefill() (
    set -euo pipefail
    acquired=0
    ownership=''
    finish() {
        local original=$? final result
        final=$original
        trap - EXIT
        set +e
        run 'end hostname' hostname
        run 'end UTC' date -u +%Y-%m-%dT%H:%M:%SZ
        capture 'end HEAD' "$out/end-head.out" git rev-parse HEAD
        capture 'end clean' "$out/end-status.out" git status --porcelain
        if [[ $(cat "$out/end-head.out") != "$candidate" || -s $out/end-status.out ]]; then final=1; fi
        if [[ $acquired -eq 1 ]]; then
            if docker container inspect "$container" > "$out/container-residual.json" 2>/dev/null; then
                if [[ $(docker container inspect "$container" --format '{{index .Config.Labels "gateway.p7-s1a-b.owner"}}') = "$candidate" ]]; then
                    run 'remove own prefill container' docker container rm -f "$container"
                    result=$?; if [[ $result -ne 0 ]]; then final=$result; fi
                else
                    echo 'CONTAINER_OWNER_MISMATCH; retained'; final=1
                fi
            fi
            if [[ -f $marker && $(cat "$marker") = "$ownership" ]]; then
                run 'remove own prefill marker' rm -- "$marker"
                result=$?
                if [[ $result -eq 0 ]]; then run 'release own busy directory' rmdir -- "$busy"; result=$?; fi
                if [[ $result -ne 0 ]]; then final=$result; fi
            else
                echo 'BUSY_OWNER_MISMATCH; retained'; final=1
            fi
        fi
        echo "PREFILL_ORIGINAL_EXIT=$original"
        echo "PREFILL_FINAL_EXIT=$final"
        echo 'Retain all source, incoming files, archives, own image and logs; no automatic retry.'
        exit "$final"
    }
    trap finish EXIT
    run 'start hostname' hostname
    run 'start UTC' date -u +%Y-%m-%dT%H:%M:%SZ
    run 'acquire own prefill marker' mkdir -- "$busy"
    acquired=1
    ownership="candidate=$candidate purpose=p7-s1a-b-rs-deps-b47d6de3 source=$source started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '%s\n' "$ownership" > "$marker"
    printf 'OWNERSHIP=%s\n' "$ownership"
    [[ -z ${DOCKER_HOST:-} && -z ${DOCKER_CONTEXT:-} ]] || exit 2
    for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do [[ -z ${!name:-} ]] || exit 2; done
    run 'local endpoint and idle resource checks' python3 -I - "$tag" "$container" <<'PY'
import json, pathlib, socket, subprocess, sys
context = subprocess.check_output(['docker', 'context', 'show'], text=True).strip()
metadata = json.loads(subprocess.check_output(['docker', 'context', 'inspect', context]))[0]
assert metadata['Endpoints']['docker']['Host'].startswith('unix://')
assert not subprocess.check_output(['docker', 'image', 'ls', '--quiet', '--no-trunc', sys.argv[1]], text=True).strip(), 'new tag already exists'
assert not subprocess.check_output(['docker', 'container', 'ls', '--all', '--quiet', '--filter', 'name=^/' + sys.argv[2] + '$'], text=True).strip(), 'container collision'
assert not subprocess.check_output(['docker', 'ps', '--quiet', '--filter', 'label=com.docker.compose.project'], text=True).strip(), 'active Compose conflict'
for proc in pathlib.Path('/proc').iterdir():
    if not proc.name.isdigit(): continue
    try: comm = (proc/'comm').read_text().strip()
    except (FileNotFoundError, ProcessLookupError): continue
    assert comm != 'dolt', 'Dolt conflict'
with socket.socket() as sock:
    sock.bind(('0.0.0.0', 8000))
print('LOCAL_IDLE_AND_NEW_RESOURCES=OK')
PY
    run 'fixed incoming artifacts and source image claims' python3 -I - "$incoming" "$candidate" "$archive_sha" "$identity_sha" "$input_sha" "$plan/p7-s1a-b-rs-base-source.json" <<'PY'
import hashlib, json, sys, tarfile
from pathlib import Path
incoming, candidate = Path(sys.argv[1]), sys.argv[2]
for filename, expected in zip(('dependency-base.tar','image-identity.json','dependency-input.json'), sys.argv[3:6], strict=True):
    path = incoming/filename
    assert path.is_file() and not path.is_symlink()
    with path.open('rb') as stream: actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert actual == expected, filename
    print(filename, actual)
entries = json.loads((incoming/'image-identity.json').read_bytes())
assert len(entries) == 1
entry = entries[0]
assert entry['ref'] == 'gateway-p2r1-repository:lock-b47d6de3cbce'
assert entry['source_commit'] == candidate and entry['archive_sha256'] == sys.argv[3]
assert entry['dependency_input_sha256'] == sys.argv[5]
inputs = json.loads((incoming/'dependency-input.json').read_bytes())
assert inputs['source_commit'] == candidate
assert inputs['files']['vnext/repository_service/uv.lock'] == 'b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f'
assert inputs['files']['vnext/repository_service/pyproject.toml'] == hashlib.sha256(Path('vnext/repository_service/pyproject.toml').read_bytes()).hexdigest()
assert inputs['files']['docs/backend-vnext/refactoring/formal/plans/p7-s1a-b-rs-dependency.Dockerfile'] == hashlib.sha256(Path('docs/backend-vnext/refactoring/formal/plans/p7-s1a-b-rs-dependency.Dockerfile').read_bytes()).hexdigest()
with tarfile.open(incoming/'dependency-base.tar') as archive:
    manifest = json.load(archive.extractfile('manifest.json'))
    assert len(manifest) == 1 and manifest[0]['RepoTags'] == [entry['ref']]
    raw = archive.extractfile(manifest[0]['Config']).read()
config = json.loads(raw)
assert 'sha256:'+hashlib.sha256(raw).hexdigest() == entry['config_digest']
assert config['rootfs']['diff_ids'] == entry['diff_ids']
assert config['config']['Labels'] == entry['labels']
old = json.loads(Path(sys.argv[6]).read_bytes())['base_image_identity']['diff_ids']
assert entry['diff_ids'][:len(old)] == old
labels = entry['labels']
assert labels['org.opencontainers.image.revision'] == candidate
assert labels['gateway.p2r1.source-tree-sha256'] == inputs['repository_build_identity']['source_tree_sha256']
assert labels['gateway.p2r1.build-input-revision'] == inputs['repository_build_identity']['build_input_revision']
assert labels['gateway.p2r1.dependency-input-sha256'] == sys.argv[5]
assert labels['gateway.p2r1.uv-lock-sha256'] == 'b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f'
print('FIXED_SOURCE_ARCHIVE_IDENTITY=MATCH')
PY
    for filename in dependency-base.tar image-identity.json dependency-input.json; do run "retain exact incoming $filename" cp -- "$incoming/$filename" "$out/archives/$filename"; done
    run 'load only fixed new dependency archive' docker image load --input "$out/archives/dependency-base.tar"
    run 're-save current new dependency image' docker image save --output "$out/current-dependency-base.tar" "$tag"
    run 'normalize fixed source identity' python3 -I - "$out/archives/image-identity.json" "$out/expected.json" <<'PY'
import json, sys
from pathlib import Path
entry = json.loads(Path(sys.argv[1]).read_bytes())[0]
Path(sys.argv[2]).write_text(json.dumps({'base_image_identity': {key: entry[key] for key in ('config_digest','diff_ids')}}, sort_keys=True)+'\n')
PY
    run 'current config raw bytes and complete DiffID match' python3 -I "$plan/p7-s1a-b-verify-saved-image.py" "$out/expected.json" base "$out/current-dependency-base.tar"
    run 'current complete labels match' python3 -I - "$out/archives/image-identity.json" "$tag" <<'PY'
import json, subprocess, sys
from pathlib import Path
source = json.loads(Path(sys.argv[1]).read_bytes())[0]
current = json.loads(subprocess.check_output(['docker', 'image', 'inspect', sys.argv[2]]))[0]
assert current['Config']['Labels'] == source['labels']
print('CURRENT_LABELS=MATCH')
PY
    capture '06 complete locked image environment' "$out/environment.json" docker run --rm --name "$container" --label "gateway.p7-s1a-b.owner=$candidate" --network none --read-only --entrypoint /app/.venv/bin/python -v "$source/vnext/repository_service/uv.lock:/input.lock:ro" -v "$source/$plan/p7-s1a-b-rs-environment.py:/inspect-environment.py:ro" "$tag" -IB /inspect-environment.py /input.lock
    run '06 pip check and exact dependency tools' docker run --rm --name "$container" --label "gateway.p7-s1a-b.owner=$candidate" --network none --read-only --entrypoint /bin/sh "$tag" -ec 'uv --no-config pip check --python /app/.venv/bin/python; test "$(uv --version)" = "uv 0.11.28"; test "$(dolt version)" = "dolt version 2.1.11"; uv --version; dolt version'
    export UV_OFFLINE=1 CARGO_NET_OFFLINE=true TMPDIR=/home/dev/gdds-test-tmp
    export PATH=/home/dev/.cargo/bin:$PATH
    run 'separate host uv-cache offline readiness for new RS lock' ./vnext/scripts/uv-consume.sh -C vnext/repository_service sync
    run 'prefill artifacts SHA256' sha256sum "$out/archives/dependency-base.tar" "$out/archives/image-identity.json" "$out/archives/dependency-input.json" "$out/current-dependency-base.tar" "$out/environment.json"
    echo 'RS_DEPENDENCY_PREFILL=COMPLETE; no product pytest/lint result; body requires separate EXEC_GO'
)
set +e
prefill 2>&1 | tee "$out/prefill.log"
status=("${PIPESTATUS[@]}")
set -e
printf 'PREFILL_EXIT=%s\nLOGGER_EXIT=%s\n' "${status[0]}" "${status[1]}" > "$out/exit-codes.txt"
sha256sum "$out/prefill.log" > "$out/prefill.log.sha256"
cat "$out/exit-codes.txt" "$out/prefill.log.sha256"
if [[ ${status[0]} -ne 0 ]]; then exit "${status[0]}"; fi
exit "${status[1]}"
