"""Stage/install a one-commit independent shallow repository; never bundle ancestry.

Run stage on CT201 only after exact source/draft review. Transfer source-repo.tar,
receipt.json and objects.txt through the approved LAN. Install verifies their
pinned SHA and does not fetch, test, compile, build or run product code.
"""
import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

SENSITIVE = ('21623404c7bf7f512b4b57b34ed0712f2d1f46a9',
             'b04388d041ed4b35849f05c05e5326a8e56caeb9')
AUDIT_ROOT = None
AUDIT_SEQUENCE = 0


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def write(path, value):
    with path.open('x') as f:
        json.dump(value,f,sort_keys=True,indent=2)
        f.write('\n')


def git(repo, *args, ok=True):
    global AUDIT_SEQUENCE
    require(AUDIT_ROOT is not None, 'external Git command evidence initialized')
    AUDIT_SEQUENCE += 1
    prefix = AUDIT_ROOT/f'{AUDIT_SEQUENCE:05d}'
    try:
        result = subprocess.run(['git','-C',str(repo),*args],capture_output=True,timeout=180,check=False)
    except (subprocess.TimeoutExpired,OSError) as exc:
        prefix.with_suffix('.stdout.log').write_bytes(getattr(exc,'stdout',None) or b'')
        prefix.with_suffix('.stderr.log').write_bytes(getattr(exc,'stderr',None) or b'')
        write(prefix.with_suffix('.json'),{'numeric_exit':None,'exception_type':type(exc).__name__})
        raise
    prefix.with_suffix('.stdout.log').write_bytes(result.stdout)
    prefix.with_suffix('.stderr.log').write_bytes(result.stderr)
    write(prefix.with_suffix('.json'),{'git_arguments':list(args),'numeric_exit':result.returncode})
    if ok:
        require(result.returncode == 0, f'git {args[:2]} exit{result.returncode}; originals {prefix}')
    return result


def inspect(repo, head):
    require((repo/'.git').is_dir() and not (repo/'.git').is_symlink(), 'independent real .git directory')
    require(not (repo/'.git/objects/info/alternates').exists(), 'no alternate object store')
    require(git(repo,'rev-parse','--git-common-dir').stdout.strip() == b'.git', 'no external common Git directory')
    require(git(repo,'rev-parse','--is-shallow-repository').stdout.strip() == b'true', 'shallow repository')
    require((repo/'.git/shallow').read_text().splitlines() == [head], 'exact one-H shallow boundary')
    require(git(repo,'rev-parse','HEAD').stdout.decode().strip() == head, 'exact H')
    require(git(repo,'rev-list','--count','--all').stdout.strip() == b'1', 'exactly one reachable commit')
    require(not git(repo,'tag','--list').stdout and not git(repo,'remote').stdout, 'no tags or fetch remotes')
    origin_head = repo/'.git/refs/remotes/origin/HEAD'
    require(not origin_head.exists() and not origin_head.is_symlink(), 'no leftover loose remote HEAD symbolic reference')
    refs = git(repo,'for-each-ref','--format=%(objectname) %(refname)').stdout.decode().splitlines()
    require(refs == [head+' refs/heads/main'], 'only fixed local main ref')
    require(not git(repo,'status','--porcelain').stdout, 'clean committed checkout')
    require(git(repo,'symbolic-ref','-q','HEAD',ok=False).returncode == 1, 'detached HEAD')
    objects = git(repo,'cat-file','--batch-all-objects','--batch-check=%(objectname) %(objecttype) %(objectsize)').stdout
    rows = objects.decode().splitlines()
    actual = {row.split()[0] for row in rows}
    reachable = {row.split()[0] for row in git(repo,'rev-list','--objects','--all').stdout.decode().splitlines()}
    require(len(actual) == len(rows) and actual == reachable, 'physical object inventory exactly equals shallow reachable closure')
    require({row.split()[0] for row in rows if row.split()[1] == 'commit'} == {head}, 'physical commit inventory only H')
    for oid in SENSITIVE:
        require(oid not in actual, 'sensitive prior oracle blob absent from complete object inventory')
        result = git(repo,'cat-file','-e',oid,ok=False)
        require(result.returncode != 0, 'sensitive blob query fails; complete physical inventory already excludes it; no lazy fetch')
    git(repo,'fsck','--full')
    return ('\n'.join(sorted(rows))+'\n').encode()


def main():
    global AUDIT_ROOT
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('stage','install'))
    p.add_argument('--head',required=True)
    p.add_argument('--source',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--archive',type=Path)
    p.add_argument('--archive-sha256')
    p.add_argument('--objects',type=Path)
    p.add_argument('--objects-sha256')
    a = p.parse_args()
    require(len(a.head) == 40 and all(c in '0123456789abcdef' for c in a.head), 'literal full H')
    for key in ('GIT_DIR','GIT_WORK_TREE','GIT_COMMON_DIR','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES','GIT_INDEX_FILE'):
        os.environ.pop(key,None)
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    os.umask(0o022)
    output = a.output.resolve()
    require(not output.exists(), 'new task-owned staging/install root')
    output.mkdir(parents=True,mode=0o700)
    AUDIT_ROOT = output/'commands'
    AUDIT_ROOT.mkdir(mode=0o700)
    repo = output/'subject'
    if a.mode == 'stage':
        require(a.source is not None, 'source required')
        source = a.source.resolve()
        require(not output.is_relative_to(source), 'staging outside source worktree')
        require(git(source,'rev-parse','refs/heads/main').stdout.decode().strip() == a.head
                and git(source,'rev-parse','HEAD').stdout.decode().strip() == a.head
                and not git(source,'status','--porcelain').stdout, 'source fixed main H and clean')
        result = subprocess.run(['git','clone','--no-local','--depth=1','--single-branch','--no-tags',
            '--branch','main',source.as_uri(),str(repo)],capture_output=True,check=False,timeout=180)
        (output/'clone.stdout.log').write_bytes(result.stdout)
        (output/'clone.stderr.log').write_bytes(result.stderr)
        write(output/'clone-exit.json',{'numeric_exit':result.returncode})
        require(result.returncode == 0, 'depth1 file-protocol clone completed')
        remote_head = git(repo,'symbolic-ref','--quiet','refs/remotes/origin/HEAD').stdout.decode().strip()
        require(remote_head == 'refs/remotes/origin/main', 'clone remote HEAD points only to fixed origin/main')
        git(repo,'symbolic-ref','--delete','refs/remotes/origin/HEAD')
        git(repo,'remote','remove','origin')
        git(repo,'checkout','--detach',a.head)
        with (repo/'.git/info/exclude').open('a') as f:
            f.write('\n/legacy\n')
        inventory = inspect(repo,a.head)
        (output/'objects.txt').write_bytes(inventory)
        require(git(source,'rev-parse','HEAD').stdout.decode().strip() == a.head
                and not git(source,'status','--porcelain').stdout, 'source stayed at clean H')
        archive = output/'source-repo.tar'
        with tarfile.open(archive,'w') as tar:
            tar.add(repo,arcname='subject',recursive=True)
        write(output/'receipt.json',{'head':a.head,'shallow_boundary':[a.head],
            'source_archive_sha256':sha(archive),'objects_sha256':sha(output/'objects.txt'),
            'sensitive_blobs_absent':list(SENSITIVE),'ancestry_transferred':False,
            'source':str(source),'utc':datetime.now(UTC).isoformat(),'clone_exit':0})
        print(json.dumps({'status':'SHALLOW_STAGE_PASS','head':a.head,'archive_sha256':sha(archive),'objects_sha256':sha(output/'objects.txt')}))
    else:
        require(a.archive is not None and a.objects is not None and a.archive_sha256 and a.objects_sha256, 'pinned archive/object inventory required')
        require(sha(a.archive) == a.archive_sha256 and sha(a.objects) == a.objects_sha256, 'LAN transfer archive and complete inventory bytes')
        with tarfile.open(a.archive,'r:') as tar:
            members = tar.getmembers()
            require(members and all(m.name == 'subject' or m.name.startswith('subject/') for m in members), 'archive under sole subject root')
            require(all(not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
                        and (m.isfile() or m.isdir()) for m in members), 'only ordinary repository files/directories; no traversal or links')
            # Archive is the just-SHA-verified, task-produced standalone clone.
            tar.extractall(output,members=members,filter='data')
        inventory = inspect(repo,a.head)
        require(inventory == a.objects.read_bytes(), 'installed complete object inventory equals staged closure')
        require(not (repo/'legacy').exists(), 'no bundled legacy data')
        require(Path('/home/dev/gateway-data-management-system/legacy').is_dir(), 'node-local legacy reference exists')
        (repo/'legacy').symlink_to('/home/dev/gateway-data-management-system/legacy')
        require(not git(repo,'status','--porcelain').stdout, 'exact clean committed node H with node-local legacy link')
        write(output/'install-receipt.json',{'status':'SHALLOW_INSTALL_PASS','head':a.head,
            'archive_sha256':a.archive_sha256,'objects_sha256':a.objects_sha256,
            'sensitive_blobs_absent':list(SENSITIVE),'utc':datetime.now(UTC).isoformat(),
            'legacy_target':'/home/dev/gateway-data-management-system/legacy','clean':True})
        print(json.dumps({'status':'SHALLOW_INSTALL_PASS','head':a.head,'clean':True}))


if __name__ == '__main__':
    main()
