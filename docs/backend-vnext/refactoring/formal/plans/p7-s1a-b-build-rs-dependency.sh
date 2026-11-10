#!/usr/bin/env bash
# Fixed dependency preparation on CT201; no product tests and no automatic retry.
set -euo pipefail
[[ $# -eq 3 ]] || exit 2
candidate=$1
source=$(realpath -e -- "$2")
out=$3
[[ $candidate =~ ^[0-9a-f]{40}$ && $out = /home/dev/gdds-test-tmp/* && ! -e $out && ! -L $out ]] || exit 2
[[ $(hostname) = heavy-dev-01 ]] || { echo 'CT201 dependency preparation only'; exit 2; }
[[ $(git -C "$source" rev-parse HEAD) = "$candidate" && -z $(git -C "$source" status --porcelain) ]] || exit 2
plan=docs/backend-vnext/refactoring/formal/plans
[[ $(realpath -e -- "$0") = "$source/$plan/p7-s1a-b-build-rs-dependency.sh" ]] || exit 2
mkdir -- "$out"
cd -- "$source"
old=gateway-p2r1-repository:lock-6dc9659f0aee
new=gateway-p2r1-repository:lock-b47d6de3cbce
container="p7-s1a-b-rs-deps-${candidate:0:12}"
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
prepare() (
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
        if [[ $resources_clear -eq 1 ]]; then echo 'PREPARATION_RESOURCE_STATE=CLEAR'; else echo 'PREPARATION_RESOURCE_STATE=RETAINED_OR_UNKNOWN'; fi
        echo "PREPARATION_ORIGINAL_EXIT=$original"
        echo "PREPARATION_FINAL_EXIT=$final"
        echo 'Retain all source, context, image tags and logs; no automatic retry/cleanup.'
        exit "$final"
    }
    trap finish EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    run 'start hostname' hostname
    run 'start UTC' date -u +%Y-%m-%dT%H:%M:%SZ
    run 'start HEAD and preparation inputs' git rev-parse HEAD
    run 'clean diff check' git diff --check 00ca325c2ed6d705abfa39e9528ef148e6029cfc HEAD
    run 'preparation script inputs SHA256' sha256sum "$plan/p7-s1a-b-build-rs-dependency.sh" "$plan/p7-s1a-b-rs-dependency.Dockerfile" "$plan/p7-s1a-b-rs-base-source.json" "$plan/p7-s1a-b-rs-environment.py"
    [[ -z ${DOCKER_HOST:-} && -z ${DOCKER_CONTEXT:-} ]] || exit 2
    run 'local Docker endpoint and new resource collision guards' python3 -I - "$new" "$container" <<'PY'
import json, subprocess, sys
context = subprocess.check_output(['docker', 'context', 'show'], text=True).strip()
metadata = json.loads(subprocess.check_output(['docker', 'context', 'inspect', context]))[0]
assert metadata['Endpoints']['docker']['Host'].startswith('unix://')
for arguments in (['image', 'ls', '--quiet', '--no-trunc', sys.argv[1]], ['container', 'ls', '--all', '--quiet', '--filter', 'name=^/' + sys.argv[2] + '$']):
    assert not subprocess.check_output(['docker', *arguments], text=True).strip(), 'new resource already exists; stop'
print('LOCAL_DOCKER_AND_NEW_RESOURCES=OK')
PY
    run 'make own retained context' mkdir "$out/context"
    capture 'original 6dc lock' "$out/context/old.lock" git show 2bacea83601290f1b3db75205f4d27d951ea1481:vnext/repository_service/uv.lock
    run 'copy candidate lock' cp vnext/repository_service/uv.lock "$out/context/uv.lock"
    run 'strict old/new lock-only-rfc proof' python3 -I - "$out/context/old.lock" "$out/context/uv.lock" <<'PY'
import hashlib, json, sys, tomllib
from pathlib import Path
old_raw, new_raw = (Path(path).read_bytes() for path in sys.argv[1:])
assert hashlib.sha256(old_raw).hexdigest() == '6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11'
assert hashlib.sha256(new_raw).hexdigest() == 'b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f'
old, new = (tomllib.loads(raw.decode()) for raw in (old_raw, new_raw))
rfc = [p for p in new['package'] if p['name'] == 'rfc8785']
assert len(rfc) == 1 and rfc[0]['version'] == '0.1.4'
assert rfc[0]['source'] == {'registry': 'https://pypi.org/simple'}
assert rfc[0]['wheels'][0]['hash'] == 'sha256:520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48'
new['package'].remove(rfc[0])
root = next(p for p in new['package'] if p['name'] == 'gateway-repository-service')
root['dependencies'].remove({'name': 'rfc8785'})
root['metadata']['requires-dist'].remove({'name': 'rfc8785', 'specifier': '==0.1.4'})
assert new == old, 'old dependency/source/metadata drift'
print(json.dumps({'lock_delta': 'only rfc8785==0.1.4', 'old_dependencies': 'unchanged'}, sort_keys=True))
PY
    run 'save original CT201 6dc base' docker image save --output "$out/source-6dc.tar" "$old"
    run 'original base config bytes and all DiffID identity' python3 -I "$plan/p7-s1a-b-verify-saved-image.py" "$plan/p7-s1a-b-rs-base-source.json" base "$out/source-6dc.tar"
    own_container "$out/old-environment.json" 'original lock environment metadata'  --entrypoint /app/.venv/bin/python -v "$out/context/old.lock:/input.lock:ro" -v "$source/$plan/p7-s1a-b-rs-environment.py:/inspect-environment.py:ro" "$old" -IB /inspect-environment.py /input.lock
    run 'download exact pinned wheel on CT201' curl --fail --location --proto '=https' --tlsv1.2 --output "$out/context/rfc8785-0.1.4-py3-none-any.whl" https://files.pythonhosted.org/packages/4d/78/119878110660b2ad709888c8a1614fce7e2fab39080ab960656dc8605bf6/rfc8785-0.1.4-py3-none-any.whl
    run 'wheel SHA256' python3 -I - "$out/context/rfc8785-0.1.4-py3-none-any.whl" <<'PY'
import hashlib, sys
from pathlib import Path
actual = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
print(actual)
assert actual == '520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48'
PY
    capture 'official current repository build identity' "$out/build-identity.json" python3 -I vnext/repository_service/tests/support/build_context_digest.py identity
    run 'write full dependency input identity' python3 -I - "$candidate" "$out" "$plan" <<'PY'
import hashlib, json, sys
from pathlib import Path
candidate, out, plan = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
identity = json.loads((out/'build-identity.json').read_bytes())
assert identity['candidate_sha'] == candidate
paths = ['vnext/repository_service/pyproject.toml', 'vnext/repository_service/uv.lock', str(plan/'p7-s1a-b-rs-dependency.Dockerfile'), str(plan/'p7-s1a-b-rs-base-source.json')]
inputs = {'source_commit': candidate, 'repository_build_identity': identity, 'files': {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}, 'wheel_sha256': '520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48'}
raw = (json.dumps(inputs, sort_keys=True, separators=(',', ':'))+'\n').encode()
(out/'dependency-input.json').write_bytes(raw)
(out/'dependency-input.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
print(raw.decode(), 'DEPENDENCY_INPUT_SHA256='+hashlib.sha256(raw).hexdigest())
PY
    readarray -t identity_fields < <(python3 -I - "$out/build-identity.json" <<'PY'
import json, sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_bytes())
print(value['build_input_revision']); print(value['source_tree_sha256'])
PY
)
    input_sha=$(cat "$out/dependency-input.sha256")
    run 'copy exact dependency build recipe' cp "$plan/p7-s1a-b-rs-dependency.Dockerfile" "$out/context/Dockerfile"
    run 'build new RS dependency-base offline' docker build --network none --pull=false --file "$out/context/Dockerfile" --tag "$new" --build-arg "SOURCE_COMMIT=$candidate" --build-arg "BUILD_INPUT_REVISION=${identity_fields[0]}" --build-arg "SOURCE_TREE_SHA256=${identity_fields[1]}" --build-arg "DEPENDENCY_INPUT_SHA256=$input_sha" "$out/context"
    own_container "$out/new-environment.json" 'new lock environment metadata'  --entrypoint /app/.venv/bin/python -v "$out/context/uv.lock:/input.lock:ro" -v "$source/$plan/p7-s1a-b-rs-environment.py:/inspect-environment.py:ro" "$new" -IB /inspect-environment.py /input.lock
    run 'old/new full environment unchanged except RFC library' python3 -I - "$out/old-environment.json" "$out/new-environment.json" <<'PY'
import json, sys
from pathlib import Path
old, new = (json.loads(Path(path).read_bytes()) for path in sys.argv[1:])
assert new['versions'].pop('rfc8785') == '0.1.4'
assert new == old, 'old environment or editable metadata drift'
print('FULL_LOCK_ENVIRONMENT_MATCH')
PY
    own_container - 'dependency pip check and exact tools'  --entrypoint /bin/sh "$new" -ec 'uv --no-config pip check --python /app/.venv/bin/python; test "$(uv --version)" = "uv 0.11.28"; test "$(dolt version)" = "dolt version 2.1.11"; uv --version; dolt version'
    run 'save new dependency image' docker image save --output "$out/dependency-base.tar" "$new"
    run 'write raw config digest/full DiffID identity and validate true labels' python3 -I - "$out" "$new" "$candidate" <<'PY'
import hashlib, json, sys, tarfile
from pathlib import Path
out, tag, candidate = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
with tarfile.open(out/'dependency-base.tar') as archive:
    manifest = json.load(archive.extractfile('manifest.json'))
    assert len(manifest) == 1 and tag in manifest[0]['RepoTags']
    raw = archive.extractfile(manifest[0]['Config']).read()
config = json.loads(raw)
original = json.loads(Path('docs/backend-vnext/refactoring/formal/plans/p7-s1a-b-rs-base-source.json').read_bytes())['base_image_identity']
assert config['rootfs']['diff_ids'][:len(original['diff_ids'])] == original['diff_ids'], 'source base changed during preparation'
labels = config['config']['Labels']
identity = json.loads((out/'build-identity.json').read_bytes())
expected = {'org.opencontainers.image.revision': candidate, 'gateway.p2r1.build-input-revision': identity['build_input_revision'], 'gateway.p2r1.source-tree-sha256': identity['source_tree_sha256'], 'gateway.p2r1.dependency-input-sha256': (out/'dependency-input.sha256').read_text().strip(), 'gateway.p2r1.uv-lock-sha256': 'b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f', 'gateway.p2r1.dolt-version': '2.1.11', 'gateway.p2r1.uv-version': '0.11.28', 'gateway.p2r1.mysql-connector-version': '9.7.0', 'gateway.p2r1.pyarrow-version': '25.0.0'}
for key, value in expected.items(): assert labels[key] == value, key
entry = {'ref': tag, 'source_commit': candidate, 'config_digest': 'sha256:'+hashlib.sha256(raw).hexdigest(), 'diff_ids': config['rootfs']['diff_ids'], 'labels': labels, 'archive_sha256': hashlib.file_digest((out/'dependency-base.tar').open('rb'), 'sha256').hexdigest(), 'dependency_input_sha256': expected['gateway.p2r1.dependency-input-sha256']}
(out/'image-identity.json').write_text(json.dumps([entry], sort_keys=True, indent=2)+'\n')
(out/'config.json').write_bytes(raw)
print(json.dumps(entry, sort_keys=True))
PY
    run 'all preparation artifacts SHA256' sha256sum "$out/source-6dc.tar" "$out/context/uv.lock" "$out/context/rfc8785-0.1.4-py3-none-any.whl" "$out/dependency-base.tar" "$out/config.json" "$out/image-identity.json" "$out/dependency-input.json" "$out/old-environment.json" "$out/new-environment.json"
    echo 'DEPENDENCY_PREPARATION=COMPLETE; no product test result; 06 prefill and actual product validation still required'
)
set +e
prepare 2>&1 | tee "$out/build.log"
status=("${PIPESTATUS[@]}")
set -e
printf 'PREPARATION_EXIT=%s\nLOGGER_EXIT=%s\n' "${status[0]}" "${status[1]}" > "$out/exit-codes.txt"
sha256sum "$out/build.log" > "$out/build.log.sha256"
cat "$out/exit-codes.txt" "$out/build.log.sha256"
if [[ ${status[0]} -ne 0 ]]; then exit "${status[0]}"; fi
exit "${status[1]}"
