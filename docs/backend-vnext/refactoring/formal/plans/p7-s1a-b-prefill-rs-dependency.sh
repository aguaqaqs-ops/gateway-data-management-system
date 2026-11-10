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
    cidfiles=()
    container_attempted=0
    own_container() {
        local output=$1 label=$2 cidfile
        shift 2
        cidfile="$out/container-${#cidfiles[@]}.cid"
        [[ ! -e $cidfile && ! -L $cidfile ]] || return 2
        cidfiles+=("$cidfile")
        container_attempted=1
        if [[ $output = - ]]; then
            run "$label" docker run --rm --name "$container" --cidfile "$cidfile" --label "gateway.p7-s1a-b.owner=$candidate" --label "gateway.p7-s1a-b.invocation=$out" --network none --read-only "$@"
        else
            capture "$label" "$output" docker run --rm --name "$container" --cidfile "$cidfile" --label "gateway.p7-s1a-b.owner=$candidate" --label "gateway.p7-s1a-b.invocation=$out" --network none --read-only "$@"
        fi
    }
    acquired=0
    ownership=''
    finish() {
        local original=$? final result resources_clear residual owned created cidfile
        local -a residual_ids=()
        final=$original
        trap - EXIT INT TERM
        set +e
        aggregate() { if [[ $1 -ne 0 && $final -eq 0 ]]; then final=$1; fi; }
        run 'end hostname' hostname
        result=$?; aggregate "$result"
        run 'end UTC' date -u +%Y-%m-%dT%H:%M:%SZ
        result=$?; aggregate "$result"
        capture 'end HEAD' "$out/end-head.out" git rev-parse HEAD
        result=$?; aggregate "$result"
        capture 'end clean' "$out/end-status.out" git status --porcelain
        result=$?; aggregate "$result"
        if [[ $(cat "$out/end-head.out") != "$candidate" || -s $out/end-status.out ]]; then aggregate 1; fi
        resources_clear=1
        # Early collision checks never authorize cleanup of an existing container.
        if [[ $container_attempted -eq 1 ]]; then
            capture 'end container list (absence requires successful empty query)' "$out/end-container-ids.out" docker container ls --all --quiet --no-trunc --filter "name=^/$container$"
            result=$?; aggregate "$result"
            if [[ $result -ne 0 ]]; then
                resources_clear=0
            elif [[ -s $out/end-container-ids.out ]]; then
                mapfile -t residual_ids < "$out/end-container-ids.out"
                if [[ ${#residual_ids[@]} -ne 1 || ! ${residual_ids[0]} =~ ^[0-9a-f]{64}$ ]]; then
                    echo 'CONTAINER_QUERY_UNKNOWN; retain resources'; resources_clear=0; aggregate 1
                else
                    residual=${residual_ids[0]}
                    owned=0
                    for cidfile in "${cidfiles[@]}"; do
                        if [[ -f $cidfile && ! -L $cidfile ]]; then
                            created=''
                            created=$(cat -- "$cidfile")
                            result=$?; aggregate "$result"
                            if [[ $result -eq 0 && $created = "$residual" ]]; then owned=1; fi
                        fi
                    done
                    if [[ $owned -ne 1 ]]; then
                        echo 'NO_CURRENT_INVOCATION_CID_PROOF; retained'; resources_clear=0; aggregate 1
                    else
                        capture 'inspect own recorded CID' "$out/container-residual.json" docker container inspect "$residual"
                        result=$?; aggregate "$result"
                        if [[ $result -ne 0 ]]; then
                            resources_clear=0
                        else
                            run 'verify exact recorded CID and unique invocation owner' python3 -I - "$out/container-residual.json" "$residual" "$candidate" "$out" "$container" <<'PYOWNER'
import json, sys
from pathlib import Path
entries = json.loads(Path(sys.argv[1]).read_bytes())
assert len(entries) == 1
entry = entries[0]
assert entry['Id'] == sys.argv[2] and entry['Name'] == '/' + sys.argv[5]
assert entry['Config']['Labels']['gateway.p7-s1a-b.owner'] == sys.argv[3]
assert entry['Config']['Labels']['gateway.p7-s1a-b.invocation'] == sys.argv[4]
print('CURRENT_INVOCATION_CID_OWNER=PROVEN')
PYOWNER
                            result=$?; aggregate "$result"
                            if [[ $result -ne 0 ]]; then
                                resources_clear=0
                            else
                                run 'remove only this invocation recorded container CID' docker container rm -f "$residual"
                                result=$?; aggregate "$result"
                                if [[ $result -ne 0 ]]; then
                                    resources_clear=0
                                else
                                    capture 'confirm own container absent after removal' "$out/end-container-confirm.out" docker container ls --all --quiet --no-trunc --filter "name=^/$container$"
                                    result=$?; aggregate "$result"
                                    if [[ $result -ne 0 || -s $out/end-container-confirm.out ]]; then resources_clear=0; aggregate 1; fi
                                fi
                            fi
                        fi
                    fi
                fi
            fi
        fi
        if [[ $resources_clear -ne 1 ]]; then echo 'PREPARATION_CONTAINERS=UNKNOWN_OR_REMAINING'; aggregate 1; fi
        if [[ $acquired -eq 1 ]]; then
            if [[ $resources_clear -ne 1 ]]; then
                echo 'PREFILL_BUSY=RETAINED; unresolved container state'; aggregate 1
            elif [[ -f $marker && $(cat "$marker") = "$ownership" ]]; then
                run 'remove own prefill marker' rm -- "$marker"
                result=$?; aggregate "$result"
                if [[ $result -eq 0 ]]; then
                    run 'release own busy directory' rmdir -- "$busy"
                    result=$?; aggregate "$result"
                    if [[ $result -eq 0 ]]; then echo 'PREFILL_BUSY=RELEASED'; else echo 'PREFILL_BUSY=RETAINED'; fi
                else
                    echo 'PREFILL_BUSY=RETAINED'
                fi
            else
                echo 'BUSY_OWNER_MISMATCH; retained'; aggregate 1
            fi
        fi
        echo "PREFILL_ORIGINAL_EXIT=$original"
        echo "PREFILL_FINAL_EXIT=$final"
        echo 'Retain all source, incoming files, archives, own image and logs; no automatic retry.'
        exit "$final"
    }
    trap finish EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
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
    own_container "$out/environment.json" '06 complete locked image environment'  --entrypoint /app/.venv/bin/python -v "$source/vnext/repository_service/uv.lock:/input.lock:ro" -v "$source/$plan/p7-s1a-b-rs-environment.py:/inspect-environment.py:ro" "$tag" -IB /inspect-environment.py /input.lock
    own_container - '06 pip check and exact dependency tools' --interactive \
        --tmpfs /tmp:rw,nosuid,nodev,noexec,size=16m \
        --tmpfs /home/gateway/.dolt:rw,nosuid,nodev,noexec,size=1m \
        --env UV_CACHE_DIR=/tmp/uv-cache --env UV_OFFLINE=1 \
        --entrypoint /bin/sh "$tag" -s <<'P7TOOLS'
set -eu
/app/.venv/bin/python -IB - <<'P7DOLTCONFIG'
import json
import os
from pathlib import Path
home = Path(os.environ["HOME"])
assert home == Path("/home/gateway"), "unexpected dependency image HOME"
config = home / ".dolt"
config.mkdir(parents=True, exist_ok=True)
(config / "config_global.json").write_text(json.dumps({
    "versioncheck.disabled": "true", "metrics.disabled": "true",
}), encoding="utf-8")
P7DOLTCONFIG
uv --no-config pip check --python /app/.venv/bin/python
uv --version > /tmp/uv-version.txt
dolt version > /tmp/dolt-version.txt
/app/.venv/bin/python -IB - <<'P7TOOLVERSIONS'
from pathlib import Path
uv = Path("/tmp/uv-version.txt").read_text().strip()
dolt = Path("/tmp/dolt-version.txt").read_text().strip()
print("UV_VERSION=" + uv)
print("DOLT_VERSION=" + dolt)
uv_fields, dolt_fields = uv.split(), dolt.split()
assert len(uv_fields) >= 2 and uv_fields[:2] == ["uv", "0.11.28"]
assert len(dolt_fields) >= 3 and dolt_fields[:3] == ["dolt", "version", "2.1.11"]
P7TOOLVERSIONS
P7TOOLS
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
