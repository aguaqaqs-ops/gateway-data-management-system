#!/usr/bin/env bash
# A-only documentation verification. Run on ct107-gw-dms-06 after SCRIPT_GO.
set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo 'usage: bash p7-s1a-a-verify.sh A_SHA CLEAN_WORKTREE NEW_LOG_DIR SESSION' >&2
    exit 2
fi
candidate=$1
worktree=$2
logdir=$3
session=$4
[[ $candidate =~ ^[0-9a-f]{40}$ && $session =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]] || exit 2
[[ $worktree = /* && $logdir = /* && -d $worktree && ! -e $logdir ]] || exit 2
# Resolve before creating anything; log output must be outside the worktree.
worktree=$(realpath -e -- "$worktree")
log_parent=$(realpath -e -- "$(dirname -- "$logdir")")
logdir="$log_parent/$(basename -- "$logdir")"
[[ $logdir != "$worktree" && $logdir != "$worktree/"* ]] || exit 2
[[ $(hostname) = gw-dms-06 ]] || { echo 'wrong test node' >&2; exit 2; }
mkdir -- "$logdir"
log="$logdir/verification.log"
busy=/home/dev/gdds-node-busy.d
marker="$busy/p7-s1a-a-$session.owner"
S=5ddd73b962e2432f961a46f6743395a53a388435
I=bc184e5007
B=b0fc25e881cb4ce39b1cc847bad92b4ccb06b809
plan=docs/backend-vnext/refactoring/formal/plans
script_path="$plan/p7-s1a-a-verify.sh"
draft_path="$plan/p7-s1a-a-verification.md"

run() {
    local label="$1"
    shift
    local result
    printf '\nCHECK: %s\nCOMMAND:' "$label"
    printf ' %q' "$@"
    printf '\n'
    if "$@"; then result=0; else result=$?; fi
    printf 'ORIGINAL_EXIT=%s\n' "$result"
    return "$result"
}

capture() {
    local label="$1"
    local output="$2"
    shift 2
    local result
    printf '\nCHECK: %s\nCOMMAND:' "$label"
    printf ' %q' "$@"
    printf '\n'
    if "$@" > "$output" 2>&1; then result=0; else result=$?; fi
    cat -- "$output"
    printf 'ORIGINAL_EXIT=%s\n' "$result"
    return "$result"
}

assert_text() {
    local label="$1"
    local actual="$2"
    local expected="$3"
    if [[ $actual = "$expected" ]]; then
        printf 'ASSERT %s: PASS (exit 0)\n' "$label"
    else
        printf 'ASSERT %s: FAIL (exit 1)\nexpected=%q\nactual=%q\n' "$label" "$expected" "$actual"
        return 1
    fi
}

check_original() {
    # Split dependent assignments: local expands all RHS before assigning filename.
    local filename="$1"
    local expected="$2"
    local output
    local raw
    local result
    output="$logdir/original-${filename%.md}.sha.out"
    raw="$logdir/original-$filename"
    printf '\nCHECK: original %s\nCOMMAND: git show %q\n' "$filename" "$I:$plan/$filename"
    if git show "$I:$plan/$filename" > "$raw"; then result=0; else result=$?; fi
    printf 'ORIGINAL_EXIT=%s\n' "$result"
    [[ $result -eq 0 ]] || return "$result"
    capture "original SHA256 $filename" "$output" sha256sum "$raw"
    local actual
    read -r actual _ < "$output"
    assert_text "original SHA256 $filename" "$actual" "$expected"
}

verify() (
    set -euo pipefail
    # A subshell keeps this EXIT trap and resource ownership local to one run.
    acquired=0
    finish() {
        local original=$?
        local final_result=$original
        local result
        trap - EXIT
        set +e
        printf '\n## Final state (also recorded after failure)\n'
        run 'end hostname' hostname
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        run 'end UTC' date -u +%Y-%m-%dT%H:%M:%SZ
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        capture 'end HEAD' "$logdir/end-head.out" git rev-parse HEAD
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        assert_text 'end HEAD equals candidate' "$(cat "$logdir/end-head.out")" "$candidate"
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        capture 'end clean' "$logdir/end-status.out" git status --porcelain
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        assert_text 'end tracked/untracked clean' "$(cat "$logdir/end-status.out")" ''
        result=$?; if [[ $result -ne 0 && $final_result -eq 0 ]]; then final_result=$result; fi
        if [[ $acquired -eq 1 ]]; then
            if [[ -f $marker ]] && [[ $(cat "$marker") = "$ownership" ]]; then
                run 'remove own marker file' rm -- "$marker"
                result=$?
                if [[ $result -eq 0 ]]; then
                    run 'release own busy directory' rmdir -- "$busy"
                    result=$?
                fi
                if [[ $result -ne 0 ]]; then
                    echo 'RESOURCE_RELEASE=FAILED; preserve state for owner; do not remove other entries'
                    if [[ $final_result -eq 0 ]]; then final_result=$result; fi
                else
                    echo 'RESOURCE_RELEASE=RELEASED'
                fi
            else
                echo 'RESOURCE_RELEASE=FAILED; ownership mismatch; marker retained'
                if [[ $final_result -eq 0 ]]; then final_result=1; fi
            fi
        else
            echo 'RESOURCE_RELEASE=NOT_ACQUIRED; no existing marker touched'
        fi
        printf 'RUN_ORIGINAL_EXIT=%s\nRUN_FINAL_EXIT=%s\n' "$original" "$final_result"
        exit "$final_result"
    }
    cd -- "$worktree"
    trap finish EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    printf 'P7-S1a A fixed static verification\ncandidate=%s\nworktree=%s\nlog=%s\nsession=%s\n' "$candidate" "$worktree" "$log" "$session"
    run 'start hostname' hostname
    run 'start UTC' date -u +%Y-%m-%dT%H:%M:%SZ
    ownership="session=$session purpose=p7-s1a-a-static candidate=$candidate worktree=$worktree started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    # Do not nest an outer reservation. Existing busy directory is a conflict.
    run 'acquire node marker' mkdir -- "$busy"
    acquired=1
    printf '%s\n' "$ownership" > "$marker"
    printf 'OWNERSHIP=%s\n' "$ownership"
    capture 'start HEAD' "$logdir/start-head.out" git rev-parse HEAD
    assert_text 'HEAD equals A_SHA' "$(cat "$logdir/start-head.out")" "$candidate"
    capture 'start clean' "$logdir/start-status.out" git status --porcelain
    assert_text 'tracked/untracked clean' "$(cat "$logdir/start-status.out")" ''
    run 'S ancestor' git merge-base --is-ancestor "$S" HEAD
    run 'I ancestor' git merge-base --is-ancestor "$I" HEAD
    # Bind the invoked source and the draft to this exact clean candidate.
    assert_text 'invoked script is candidate script' "$(realpath -e -- "$0")" "$worktree/$script_path"
    run 'script SHA256' sha256sum "$script_path"
    run 'draft SHA256' sha256sum "$draft_path"
    run 'diff check' git diff --check "$S" HEAD
    capture 'S..HEAD changed paths' "$logdir/s-head-paths.out" git diff --name-only "$S" HEAD
    run 'fixed path whitelist and links' python3 -I - "$S" <<'PY'
from pathlib import Path
import re
import subprocess
import sys

base = sys.argv[1]
plan = 'docs/backend-vnext/refactoring/formal/plans/'
contracts = 'docs/backend-vnext/refactoring/formal/contracts/'
short_contracts = 'docs/backend-vnext/contracts/'
allowed = {plan + name for name in (
    'p7-s0-owner-decisions.md', 'p7-design.md', 'p7-execution-plan.md',
    'p7-s1a-storage-resource-design.md', 'p7-s1a-execution-plan.md',
    'p7-processing-groups-and-test-extraction-design.md', 'p7-s1a-implementation-prompt.md',
    'p7-s1a-a-entry-and-contract.md', 'p7-s1a-a-verification.md', 'p7-s1a-a-verify.sh',
)}
allowed |= {contracts + name for name in (
    'canonical-storage-and-repository-boundary.md', 'operation-lifecycle-and-integrity.md',
    'business-lifecycle-and-state.md', 'storage-mutation-and-change-set.md', 'repository-service.md',
)}
allowed |= {short_contracts + name for name in (
    'snapshot-table-access.md', 'comparison-bundle.md', 'comparison.md', 'risk.md',
)}
allowed.add('docs/backend-vnext/artifacts.md')
changed = subprocess.check_output(['git', 'diff', '--name-only', base, 'HEAD'], text=True).splitlines()
assert set(changed) <= allowed, f'outside whitelist: {set(changed) - allowed}'
print('PATH_WHITELIST=PASS')
# Check only newly added Markdown link lines. Old links outside this scope are not a new gate.
# This deliberately does not invent a Chinese heading slug validator; anchors remain review-owned.
patch = subprocess.check_output(['git', 'diff', '--unified=0', base, 'HEAD', '--', '*.md'], text=True)
current = None
tracked = set(subprocess.check_output(['git', 'ls-files'], text=True).splitlines())
root = Path.cwd().resolve()
count = 0
for line in patch.splitlines():
    if line.startswith('+++ b/'):
        current = Path(line[6:])
    elif line.startswith('+') and not line.startswith('+++') and current is not None:
        for target in re.findall(r'\]\(([^)]+)\)', line[1:]):
            if target.startswith(('https://', 'http://', 'mailto:', '#')):
                continue
            target = target.split('#', 1)[0]
            if not target:
                continue
            resolved = (current.parent / target).resolve()
            relative = resolved.relative_to(root).as_posix()
            assert relative in tracked and resolved.is_file(), f'{current}: missing tracked link {target}'
            count += 1
print(f'NEW_LOCAL_LINK_FILES=PASS count={count}; anchors=independent-review')
for name in sorted(allowed):
    if name.startswith((contracts, short_contracts)):
        assert '待实现' in Path(name).read_text(), f'missing pending target marker: {name}'
print('PENDING_CONTRACT_TARGETS=PASS; semantic/version review remains independent')
PY
    capture 'HEAD:vnext' "$logdir/head-vnext.out" git rev-parse HEAD:vnext
    assert_text 'unchanged vnext tree' "$(cat "$logdir/head-vnext.out")" 49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3
    run 'no product/frontend/governance diff' git diff --exit-code "$S" HEAD -- vnext frontend AGENTS.md docs/backend-vnext/testing-conventions.md
    capture 'B..S paths' "$logdir/b-s-paths.out" git diff --name-only "$B" "$S"
    assert_text 'B..S paths' "$(cat "$logdir/b-s-paths.out")" $'docs/frontend-vnext/reviews/fe3c-evidence-stop-1.md\ndocs/frontend-vnext/reviews/fe3c-fix2-check.md'
    capture 'p6-exit target' "$logdir/p6-exit.out" git rev-parse 'p6-exit^{commit}'
    assert_text 'p6-exit target' "$(cat "$logdir/p6-exit.out")" "$B"
    check_original p7-s0-owner-decisions.md c120c608cbcc0cea234132b5ad0257ccb4a2f16470b15c92571fc100c56a009a
    check_original p7-design.md 6664ed579ea6fe1be8bbc98f400f1bd600b72386ce28d2ebbaf315a749074acc
    check_original p7-execution-plan.md 12ce37ad871a1e25abccd361758074c46944b28d769640d85ed2291219a6be26
    check_original p7-s1a-storage-resource-design.md 1ebfd1d8209b79da6eb35746baf65a64f224dde65b3b55d2207e47252c18e5f2
    check_original p7-s1a-execution-plan.md 7681166cf9cb89188fc3787e24d51bfd867b7bdb9e772a017fd8fe1613c2fcd3
    check_original p7-processing-groups-and-test-extraction-design.md 554668c7475f264e59ba33c39f5f8c937635a20d6a49a60f8f7e9af69e4334bf
    check_original p7-s1a-implementation-prompt.md 47548deac73848fe9973cbc987e0e11ae4b0aabd9c7dc7e3a983d3d630389bec
    echo 'STATIC_CHECKS=PASS; no product behavior tested'
)

# tee is waited for before hashing the final log. Preserve verifier and logger exits separately.
set +e
verify 2>&1 | tee "$log"
pipeline_status=("${PIPESTATUS[@]}")
set -e
verifier_exit=${pipeline_status[0]}
logger_exit=${pipeline_status[1]}
printf 'VERIFIER_EXIT=%s\nLOGGER_EXIT=%s\n' "$verifier_exit" "$logger_exit" > "$logdir/exit-codes.txt"
sha256sum "$log" > "$logdir/verification.log.sha256"
cat -- "$logdir/exit-codes.txt" "$logdir/verification.log.sha256"
if [[ $verifier_exit -ne 0 ]]; then exit "$verifier_exit"; fi
exit "$logger_exit"
