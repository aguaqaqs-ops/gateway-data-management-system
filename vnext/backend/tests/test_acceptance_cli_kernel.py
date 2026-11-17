"""Fresh-process CLI composition consumes real published records without pytest startup."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys

import pytest

from gateway_backend.artifacts import InMemoryArtifactStore, artifact_ref_to_dict
from tests.support.comparison_s3_e_live import native_product, publish_product

pytestmark = pytest.mark.unit

# The child imports no pytest/conftest and starts with an actually uninitialized
# native pool. Only external node/daemon checks and the costly journey dispatch
# are replaced; main owns initialization, evidence and occupation lifecycle.
CHILD = r"""
import base64,json,os,sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from benchmarks import comparison_correctness_acceptance as entry
from benchmarks import comparison_correctness_history_supplement as supplement
from benchmarks import comparison_correctness_number1_supplement as number1
from gateway_backend.artifacts import InMemoryArtifactStore,artifact_ref_from_dict
from gateway_backend.capabilities.comparison.artifacts import open_records_closure

scope,source,directory=sys.argv[1:]
root=Path(directory)
data=json.loads(Path(source).read_text())
store=InMemoryArtifactStore()
for item in data['artifacts']:
    store.put(base64.b64decode(item['raw']),artifact_ref_from_dict(item['ref']))
ref=artifact_ref_from_dict(data['closure'])
try:
    open_records_closure(store,ref)
except RuntimeError as exc:
    assert str(exc)=='kernel pool has not been initialized',str(exc)
else:
    raise AssertionError('child inherited or implicitly initialized the native pool')
calls=[]
initialize=entry.initialize_compute_kernel
def initialize_once(threads):
    calls.append(threads)
    initialize(threads)
def consume(*args,**kwargs):
    assert calls==[1],calls
    closure=open_records_closure(store,ref)
    assert len(closure.records)==1 and closure.records[0].record_count==1
    # The public composition helper must retain the fixed N, not merely make
    # this one validator succeed using an arbitrary implicit configuration.
    try:
        initialize(2)
    except ValueError as exc:
        assert 'initialized with 1 threads' in str(exc),str(exc)
    else:
        raise AssertionError('CLI failed to establish fixed N1')
real_path=Path
def local_path(value):
    return root/'busy' if str(value)=='/home/dev/gdds-node-busy.d' else real_path(value)
def git(*args):
    if args==('rev-parse','HEAD'):
        return 'a'*40
    if args==('rev-parse','--show-toplevel'):
        return str(root/'worktree')
    assert args==('status','--porcelain'),args
    return ''
arguments=['--scope',scope,'--input-root',str(root/'input'),'--output',str(root/'output'),
           '--expected-head','a'*40,'--session','fresh-cli-kernel']
if scope in ('t4-history','number1-replay','number1-terminal'):
    arguments+=['--source-run',str(root/'source-run'),'--source-root',str(root/'source-root'),
                '--source-head','b'*40]
if scope=='number1-terminal':
    arguments+=['--replay-run',str(root/'replay')]
with ExitStack() as patches:
    patches.enter_context(patch.dict(os.environ,{
        'UV_OFFLINE':'1','CARGO_NET_OFFLINE':'true','GATEWAY_DOCKER_BUILD_NETWORK':'none',
        'GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES':'1',
        'GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES':'1'}))
    for owner,name,value in ((entry,'initialize_compute_kernel',initialize_once),
            (entry,'_git',git),(entry,'_assert_execution_isolation',lambda:{}),
            (entry,'_idle',lambda:None),(entry,'Path',local_path),(entry,'_run',consume),
            (supplement,'run_supplement',consume),(number1,'run_replay',consume),
            (number1,'run_terminal',consume)):
        patches.enter_context(patch.object(owner,name,value))
    assert entry.main(arguments)==0
assert calls==[1] and not (root/'busy').exists()
assert json.loads((root/'output/finish.json').read_text())['exit_code']==0
print(json.dumps({'scope':scope,'initialized':calls,'records':1,'fresh_process':True}))
"""


@pytest.mark.parametrize(
    "scope", ("t4", "t4-history", "number1", "number1-replay", "number1-terminal")
)
def test_fresh_cli_initializes_fixed_kernel_before_consuming_records(
    tmp_path: Path, scope: str
) -> None:
    store = InMemoryArtifactStore()
    schema = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8));"
    product = native_product(
        schema + " INSERT INTO t VALUES(1,'before');",
        schema + " INSERT INTO t VALUES(1,'current');",
    )
    try:
        published = publish_product(product, store)
        assert published.facts is not None and published.facts.records_ref is not None
        assert published.records_closure is not None
        (record,) = published.records_closure.records
        closure = published.facts.records_ref
        refs = (closure, record.records_ref, record.records_manifest_ref)
        source = tmp_path / "published.json"
        source.write_text(
            json.dumps(
                {
                    "closure": artifact_ref_to_dict(closure),
                    "artifacts": [
                        {
                            "ref": artifact_ref_to_dict(ref),
                            "raw": base64.b64encode(store.locate(ref)).decode(),
                        }
                        for ref in refs
                    ],
                }
            )
        )
    finally:
        product.close()
    (tmp_path / "input").mkdir()
    completed = subprocess.run(
        [sys.executable, "-c", CHILD, scope, str(source), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "scope": scope,
        "initialized": [1],
        "records": 1,
        "fresh_process": True,
    }
