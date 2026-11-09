"""Fixed S6 t4 evidence driver; run on an occupied dedicated CT via Python stdin.

Uses the existing t4-w1-w2 journey without replacing its business steps. Evidence
hooks add independent Repository checks, complete tar preservation and calibrated
log windows. --prepare-only never starts Docker or executes the journey.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.ipc as pa_ipc
from gateway_repository_contracts import encode_commit_id_path_segment

sys.path.insert(0, str(Path.cwd()))
from benchmarks import real_dump_journey as j
from benchmarks import s4_repository_identity as identity
from benchmarks import s4_submit_measurement_driver as resource
from benchmarks.bundle_tar import download_bundle_tar

DATASET = "rd-t4-d-v1"
B_SOURCE = "788ed36e7742a067bf01c16ad2e6aaed2fed91fb"
DATASETS_SHA = "78c7cbba05acbbe92cc9a22351f8caf800824c4520e0d9685c6e776d6042da4f"
CENSUS_SHA = "733b506e43164a62f30d3a1d665449471e8edf25b515701150f6e73a824a6988"
EXPECTED_SHA = "0e67afac5eb529282b2aa59ed833ccf40cbb3ab82b2da64861e1b904079e7915"
MAPPED_SHA = "258a99660244281532a1c14e50ad9dd40a214289925248bc84b3c25bba39a19f"
PACKAGE = (5597503, "95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675")
SET_TYPE = "SET('1','3','5','7')"
M = 25769803776
ENVELOPE = 34359738368
SERVICES = ("worker", "backend", "repository-service")
COMMAND_ROOT = None
COMMAND_SEQUENCE = 0


def require(value, message):
    if not value:
        raise RuntimeError(message)


def utc():
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    with path.open("x") as target:
        json.dump(value, target, sort_keys=True, indent=2)
        target.write("\n")


def command(argv, **kwargs):
    global COMMAND_SEQUENCE
    require(COMMAND_ROOT is not None, 'external command evidence configured before subprocess')
    COMMAND_SEQUENCE += 1
    prefix = COMMAND_ROOT/f'{COMMAND_SEQUENCE:05d}'
    text_mode = kwargs.pop('text',False)
    timeout = kwargs.pop('timeout',180)
    started = utc()
    try:
        result = subprocess.run(argv,check=False,capture_output=True,timeout=timeout,**kwargs)
    except (subprocess.TimeoutExpired,OSError) as exc:
        prefix.with_suffix('.stdout.log').write_bytes(getattr(exc,'stdout',None) or b'')
        prefix.with_suffix('.stderr.log').write_bytes(getattr(exc,'stderr',None) or b'')
        write(prefix.with_suffix('.json'),{'command_prefix':argv[:2],'start_utc':started,'end_utc':utc(),
              'numeric_exit':None,'exception_type':type(exc).__name__,'timeout_seconds':timeout})
        raise
    prefix.with_suffix('.stdout.log').write_bytes(result.stdout)
    prefix.with_suffix('.stderr.log').write_bytes(result.stderr)
    write(prefix.with_suffix('.json'),{'command_prefix':argv[:2],'start_utc':started,'end_utc':utc(),
          'numeric_exit':result.returncode,'stdout_sha256':sha(prefix.with_suffix('.stdout.log')),
          'stderr_sha256':sha(prefix.with_suffix('.stderr.log'))})
    require(result.returncode == 0, f"command {argv[:2]} exit {result.returncode}; originals {prefix}")
    if text_mode:
        return subprocess.CompletedProcess(result.args,result.returncode,result.stdout.decode('utf-8'),result.stderr.decode('utf-8'))
    return result


def resource_command(argv, *, cwd, env, timeout=60):
    return command(argv,cwd=cwd,env=env,timeout=timeout,text=True).stdout


def digest_typed(rows):
    digest = hashlib.sha256()
    for row in sorted(identity._json_bytes(value) for value in rows):
        digest.update(len(row).to_bytes(8, "big"))
        digest.update(row)
    return "sha256:" + digest.hexdigest()


# Read-only verifier retained from S4 fixed source 5b02e2f53e7e; SET mapping is fixed old B.
def read_repository(
    *, base_url: str, repository_id: str, commit_id: str, dataset_id: str,
    expected: dict[str, Any], mapped: dict[str, Any], evidence: Path, version: str,
) -> dict[str, Any]:
    item = expected["datasets"][dataset_id]
    selected = list(item["selected_tables"])
    actual = identity.read_identity(base_url=base_url, repository_id=repository_id,
                                    commit_id=commit_id, selected_tables=selected)
    (evidence / f"{version}-repository-actual.json").write_text(
        json.dumps(actual, sort_keys=True, indent=2) + "\n")
    summary: dict[str, Any] = {"dataset_id": dataset_id, "commit_id": commit_id,
                               "actual_identity": actual, "matches_independent_expectation": False}
    if (actual["catalog_table_count"] != item["catalog_table_count"] or
            actual["catalog_schema_sha256"] != item["catalog_schema_sha256"] or
            actual["schema_version"] != item["schema_version"]):
        raise RuntimeError(f"{dataset_id}: exact Repository Catalog differs from frozen B")
    for name, prior in item["selected_tables"].items():
        if name != "app_cfg" and actual["selected_tables"][name] != prior:
            raise RuntimeError(f"{dataset_id}: {name} exact Repository rows differ from frozen B")
    old = mapped["datasets"][dataset_id]
    if (old["row_count"] != 24 or old["raw_row_digest"] != item["selected_tables"]["app_cfg"]["row_digest"] or
            old["run_board_sql_type"] != SET_TYPE or
            len(old["raw_rows_typed"]) != 24 or len(old["wire_rows_typed"]) != 24 or
            digest_typed(old["raw_rows_typed"]) != old["raw_row_digest"] or
            digest_typed(old["wire_rows_typed"]) != old["wire_row_digest"]):
        raise RuntimeError("independent B app_cfg row conversion evidence differs")
    encoded = encode_commit_id_path_segment(commit_id)
    with httpx.Client(base_url=base_url,
                      headers={"Authorization": f"Bearer {j.BEARER_TOKEN}"}, timeout=300.0) as client:
        response = client.get(
            f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/rows",
            params={"table_name": "app_cfg"})
        response.raise_for_status()
        table = pa_ipc.open_stream(response.content).read_all()
    field = table.schema.field("run_board")
    if (not pa.types.is_list(field.type) or not pa.types.is_string(field.type.value_type) or
            field.type.value_field.nullable or field.metadata is None or
            field.metadata.get(b"gateway.logical_type") != b"set" or
            field.metadata.get(b"gateway.sql_type") != SET_TYPE.encode()):
        raise RuntimeError("Repository app_cfg SET Arrow wire type differs from Contract")
    rows = [identity._typed(row) for row in table.to_pylist()]
    (evidence / f"{version}-appcfg-actual.json").write_text(
        json.dumps({"row_count": len(rows), "rows_typed": rows}, sort_keys=True, indent=2) + "\n")
    wire_digest = digest_typed(rows)
    if (table.num_rows != 24 or actual["selected_tables"]["app_cfg"]["row_count"] != 24 or
            wire_digest != actual["selected_tables"]["app_cfg"]["row_digest"] or
            wire_digest != old["wire_row_digest"] or
            Counter(identity._json_bytes(row) for row in rows) !=
            Counter(identity._json_bytes(row) for row in old["wire_rows_typed"])):
        raise RuntimeError(f"{dataset_id}: app_cfg 24-row wire multiset differs from mapped frozen B")
    summary["app_cfg_wire_row_digest"] = wire_digest
    summary["app_cfg_raw_b_digest"] = old["raw_row_digest"]
    summary["app_cfg_row_multiset_equal"] = True
    summary["matches_independent_expectation"] = True
    return summary


# Only metadata and owning checkpoint/manifest validators; no Repository calls,
# cache lookup/touch, row reader, bootstrap, migration or persistent writes.
CANONICAL = r'''
import json, sqlite3, sys
from dataclasses import asdict
from pathlib import Path
from gateway_backend.artifacts import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application import preview_jobs as p
from gateway_backend.application.canonical_metadata.binding import _storage_rule_view
from gateway_backend.capabilities.storage_projection import open_canonicalization_manifest
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.control_db.schema import verify_control_db_file
repo, op, commit = json.loads(sys.argv[1])
path = Path('/var/lib/gateway/control/control.sqlite3')
verify_control_db_file(path)
c = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, isolation_level=None)
c.execute('PRAGMA query_only=ON')
c.execute('BEGIN')
try:
    step = c.execute('SELECT checkpoint_ref,status,operation_id,step_name FROM step_records WHERE step_id=?',
        (p._successor_step_id(op,p.PREVIEW_STEP_MATERIALIZE),)).fetchone()
    assert step and tuple(step[1:]) == ('SUCCEEDED',op,p.PREVIEW_STEP_MATERIALIZE)
    assert c.execute('SELECT status FROM operation_records WHERE operation_id=?',(op,)).fetchone() == ('SUCCEEDED',)
    row = c.execute('SELECT canonicalization_manifest_ref,canonicalization_manifest_digest FROM submission_records WHERE repository_id=? AND repository_commit_id=?',(repo,commit)).fetchall()
    assert len(row) == 1
    store = LocalArtifactStore(Path('/var/lib/gateway/artifacts'))
    with store.read_session():
        ref = artifact_ref_from_dict(json.loads(step[0]))
        envelope = load_checkpoint_envelope(store,ref)
        assert (envelope.operation_id,envelope.step_name,envelope.job_kind) == (op,p.PREVIEW_STEP_MATERIALIZE,p.PREVIEW_JOB_KIND)
        inputs = p._materialized_preview_inputs_from_checkpoint(envelope.job_state,store,repository_id=repo)
        assert not inputs.canonical.baseline_is_initial
        before_ref = store.get_ref(row[0][0])
        before_manifest = open_canonicalization_manifest(store,before_ref)
        after_manifest = open_canonicalization_manifest(store,inputs.canonical.canonicalization_manifest_ref)
        assert before_manifest.manifest_digest.value == row[0][1]
        before = inputs.sides[p._SIDE_BASELINE]
        current = inputs.sides[p._SIDE_MODIFIED]
        assert inputs.sides[p._SIDE_INITIAL] == before
        assert inputs.canonical.baseline_canonical_state_digest == inputs.canonical.modified_canonical_state_digest
        def identities(manifest, bound):
            descriptors = {t.table_name:t for t in bound.summary.tables}
            facts = {t.storage_rule_view.canonical_table:t for t in bound.storage_facts}
            assert set(descriptors) == set(facts) == {t.name for t in manifest.tables}
            result = {}
            for t in manifest.tables:
                d, f = descriptors[t.name], facts[t.name]
                assert t.content_digest and t.source_schema_digest and t.canonical_schema_digest
                view = _storage_rule_view(t)
                assert d.row_count == t.canonical_row_count and d.raw_content_digest == t.content_digest
                assert f.raw_content_digest == t.content_digest and f.source_schema_digest == t.source_schema_digest
                assert f.canonical_schema_digest == t.canonical_schema_digest and f.storage_rule_view == view
                assert f.storage_projection_version == manifest.storage_projection_version
                result[t.name] = {'row_count':d.row_count,'raw_content_digest':d.raw_content_digest.value,
                    'business_schema_digest':d.business_schema_digest.value,
                    'source_schema_digest':t.source_schema_digest.value,'canonical_schema_digest':t.canonical_schema_digest.value,
                    'storage_rule_view':asdict(view),'storage_projection_version':manifest.storage_projection_version}
            return result
        b, a = identities(before_manifest,before), identities(after_manifest,current)
        u = sorted(n for n in b.keys() & a.keys() if b[n] == a[n])
        x = sorted(n for n in b.keys() & a.keys() if b[n] != a[n])
        added, deleted = sorted(a.keys()-b.keys()), sorted(b.keys()-a.keys())
        assert not x and not deleted and not added and len(u) == 312
        print(json.dumps({'repository_id':repo,'operation_id':op,'exact_commit':commit,
            'checkpoint_ref':artifact_ref_to_dict(ref),'baseline_manifest_ref':artifact_ref_to_dict(before_ref),
            'current_manifest_ref':artifact_ref_to_dict(inputs.canonical.canonicalization_manifest_ref),
            'U':u,'X':x,'A':added,'D':deleted,'logical_baseline_row_demand':0,
            'before_identities':b,'current_identities':a,
            'policy':'full schema/count/content/storage view/projection identity, metadata only; independent of HTTP count'},sort_keys=True))
finally:
    c.execute('ROLLBACK')
    c.close()
'''


def inputs(args):
    root, worktree, assets = args.input_root.resolve(), args.worktree.resolve(), args.assets.resolve()
    require(not assets.is_relative_to(worktree), 'real old B row payloads must remain outside Git/worktree')
    head = command(['git','-C',str(worktree),'rev-parse','HEAD'],text=True).stdout.strip()
    require(re.fullmatch(r'[0-9a-f]{40}', args.candidate_head) and head == args.candidate_head, 'fixed clean candidate HEAD')
    require(not command(['git','-C',str(worktree),'status','--porcelain'],text=True).stdout, 'clean committed worktree')
    require(Path.cwd().resolve() == worktree/'vnext/backend', 'backend controlled stdin working directory')
    require(sha(root/'datasets.json') == DATASETS_SHA, 'standard datasets identity')
    require(sha(worktree/'docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s1-census.json') == CENSUS_SHA, 'standard census identity')
    require(sha(assets/'old-b-t4-expected.json') == EXPECTED_SHA and sha(assets/'old-b-mapped-t4.json') == MAPPED_SHA, 'independent old B bytes')
    expected = json.loads((assets/'old-b-t4-expected.json').read_bytes())
    mapped = json.loads((assets/'old-b-mapped-t4.json').read_bytes())
    package = root/'packages'/f'{DATASET}.tar.gz'
    require((package.stat().st_size, sha(package)) == PACKAGE, 'standard t4 v1 frozen package')
    require(expected['source_commit'] == mapped['source_commit'] == B_SOURCE and expected['profile'] == 't4', 'old B source')
    require(mapped['b_expected_sha256'] == EXPECTED_SHA and mapped['source_metadata_sha256'] == DATASETS_SHA
            and mapped['set_sql_type'] == SET_TYPE and mapped['declared_labels'] == ['1','3','5','7'], 'fixed SET mapping provenance')
    old = mapped['datasets'][DATASET]
    require(old['package_sha256'] == PACKAGE[1] and len(old['raw_rows_typed']) == len(old['wire_rows_typed']) == 24, 'old B row/source identity')
    require(digest_typed(old['raw_rows_typed']) == old['raw_row_digest'] == expected['datasets'][DATASET]['selected_tables']['app_cfg']['row_digest']
            and digest_typed(old['wire_rows_typed']) == old['wire_row_digest'], 'complete old B typed-row digests')
    # Reconstruct the legal mapping independently from the saved raw B rows.
    rebuilt = []
    for row in old['raw_rows_typed']:
        require(row[0] == 'map', 'typed old B map')
        pairs = []
        for key, value in row[1]:
            if key == 'run_board':
                require(value[0] == 'str', 'this fixed B input has no NULL SET')
                members = value[1].split(',') if value[1] else []
                require(all(m in mapped['declared_labels'] for m in members), 'declared SET labels')
                value = ['list', [['str', m] for m in members]]
            pairs.append([key,value])
        rebuilt.append(['map',pairs])
    require(Counter(identity._json_bytes(r) for r in rebuilt) == Counter(identity._json_bytes(r) for r in old['wire_rows_typed']), 'independently rebuilt full SET mapping')
    return expected, mapped


def main():
    global COMMAND_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree',type=Path,required=True)
    parser.add_argument('--candidate-head',required=True)
    parser.add_argument('--input-root',type=Path,required=True)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--compose-name',required=True)
    parser.add_argument('--prepare-only',action='store_true')
    args = parser.parse_args()
    output,worktree = args.evidence.resolve(),args.worktree.resolve()
    require(not output.is_relative_to(worktree) and not output.exists(), 'new external evidence directory')
    output.mkdir(parents=True,mode=0o700)
    COMMAND_ROOT = output/'commands'
    COMMAND_ROOT.mkdir(mode=0o700)
    resource.command = resource_command
    try:
        expected,mapped = inputs(args)
    except BaseException as exc:
        write(output/'preparation.json',{'status':'PREPARATION_FAIL','head':args.candidate_head,
              'failure_type':type(exc).__name__,'message':str(exc),'product_started':False})
        raise
    if args.prepare_only:
        facts = {'status':'PREPARATION_PASS','head':args.candidate_head,'datasets_sha256':DATASETS_SHA,
                 'census_sha256':CENSUS_SHA,'expected_sha256':EXPECTED_SHA,'mapped_sha256':MAPPED_SHA}
        write(output/'preparation.json',facts)
        print(json.dumps(facts))
        return 0
    require(re.fullmatch(r's6-t4-[a-z0-9-]+',args.compose_name), 'owned fresh S6 project namespace')
    require(os.environ.get('UV_OFFLINE') == '1' and os.environ.get('CARGO_NET_OFFLINE') == 'true'
            and os.environ.get('GATEWAY_DOCKER_BUILD_NETWORK') == 'none'
            and os.environ.get('GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES') == '1'
            and os.environ.get('GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES') == '1'
            and not os.environ.get('GATEWAY_COMPOSE_GATE_PREBUILT'), 'offline normal local Compose build')
    require(os.environ.get('GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_THREADS') == '1'
            and os.environ.get('GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_MEMORY_BUDGET_BYTES') == str(M)
            and os.environ.get('GATEWAY_BACKEND_OPERATION_WORKER_MEMORY_ENVELOPE_BYTES') == str(ENVELOPE)
            and os.environ.get('GATEWAY_BACKEND_OPERATION_WORKER_MEMORY_RESERVE_BYTES') == '8589934592', 'explicit N1/32/8/M24')
    require(not resource._owned_containers(args.compose_name,worktree,dict(os.environ))
            and not resource._owned_ids('volume',args.compose_name,worktree,dict(os.environ))
            and not resource._owned_ids('network',args.compose_name,worktree,dict(os.environ)), 'fresh project has no existing resources')
    result = {'start_head':args.candidate_head,'hostname':socket.gethostname(),'start_utc':utc(),
              'scope':'t4-w1-w2','N':1,'M':M,'worker_envelope':ENVELOPE,'reserve':8589934592,
              'expected_sha256':EXPECTED_SHA,'mapped_sha256':MAPPED_SHA,'status':'FAIL','windows':[]}
    context = {}
    original_env, original_preview = j._compose_environment, j._preview
    original_read, original_tier = j._pseudo_counts_from_http, j._run_tier
    serial = 0

    def compose_env(*a,**kw):
        env = original_env(*a,**kw)
        context['env'] = env
        return env

    def snapshot(label):
        env = context['env']
        ids = resource._owned_containers(args.compose_name,worktree,env)
        state = resource._resource_snapshot(ids,args.compose_name,worktree,env)
        worker = state['services']['worker']
        require(worker['host_memory_limit'] == ENVELOPE and worker['memory_max'] == str(ENVELOPE), 'actual worker32GiB cgroup')
        for service,current in state['services'].items():
            require(not current['oom_killed'] and current['restart_count'] == 0
                    and all(current['memory_events'][k] == 0 for k in ('oom','oom_kill','oom_group_kill')), 'no OOM/restart')
            if 'services' in context:
                prior = context['services'][service]
                require((prior['id'],prior['started_at'],prior['image_id']) == (current['id'],current['started_at'],current['image_id']), 'same service/container since ready')
        context.setdefault('services',state['services'])
        write(output/f'{label}-resources.json',state)
        logs = {}
        for service in ('worker','repository-service'):
            cid = state['services'][service]['id']
            raw = command(['docker','logs','--timestamps',cid])
            for stream,data in (('stdout',raw.stdout),('stderr',raw.stderr)):
                logs[(service,stream)] = data
                (output/f'{label}-{service}.{stream}.log').write_bytes(data)
        return {'utc':utc(),'logs':logs,'resources':state}

    def window(label,before,after,repo,commit):
        text = {}
        for service in ('worker','repository-service'):
            parts = []
            for stream in ('stdout','stderr'):
                first,last = before['logs'][(service,stream)],after['logs'][(service,stream)]
                require(last.startswith(first), 'complete exact-container log prefix; no rotation/truncation')
                delta = last[len(first):]
                require(not delta or delta.endswith(b'\n'), 'complete access-log line boundary')
                (output/f'{label}-{service}.{stream}.delta.log').write_bytes(delta)
                parts.append(delta.decode('utf-8',errors='strict'))
            text[service] = '\n'.join(parts)
        prefix = r'"GET /v1/repositories/'+re.escape(repo)+r'/versioned/commits/'+re.escape(commit)
        rs = text['repository-service']
        rows = re.findall(prefix+r'/rows\?[^\s"]* HTTP/[^\s"]+" (\d{3})',rs)
        catalogs = re.findall(prefix+r'/catalog HTTP/[^\s"]+" (\d{3})',rs)
        # The entire exclusive window must contain no other repository/commit
        # data reads, even if the expected target happens to have zero matches.
        all_rows = re.findall(r'"GET /v1/repositories/[^\s"]+/versioned/commits/[^\s"]+/rows\?[^\s"]* HTTP/',rs)
        all_catalogs = re.findall(r'"GET /v1/repositories/[^\s"]+/versioned/commits/[^\s"]+/catalog HTTP/',rs)
        require(len(rows) == len(all_rows) and len(catalogs) == len(all_catalogs), 'all actual data HTTP scoped to exact repository/commit')
        require(all(s == '200' for s in rows+catalogs), 'actual RS data HTTP successful')
        return {'label':label,'since_before_call_utc':before['utc'],'until_after_complete_tar_utc':after['utc'],
                'window_method':'full timestamped same-container log prefix byte delta; snapshots retained',
                'repository_id':repo,'exact_commit':commit,'rows_HTTP_requests':len(rows),'catalog_HTTP_requests':len(catalogs),
                'worker_text':text['worker']}

    def checked_read(**kw):
        actual = original_read(**kw)
        before = snapshot('calibration-before')
        result['repository_oracle'] = read_repository(base_url=kw['base_url'],repository_id=kw['repository_id'],
            commit_id=kw['commit_id'],dataset_id=DATASET,expected=expected,mapped=mapped,evidence=output,version='v1')
        after = snapshot('calibration-after')
        cal = window('calibration',before,after,kw['repository_id'],kw['commit_id'])
        cal.pop('worker_text')
        require(cal['rows_HTTP_requests'] >= 6 and cal['catalog_HTTP_requests'] >= 1, 'positive same-log exact-commit rows/catalog calibration')
        context['calibration'] = cal
        context['commit'] = kw['commit_id']
        write(output/'calibration.json',cal)
        return actual

    def checked_preview(*a,**kw):
        nonlocal serial
        label = 'w1' if serial == 0 else 'w2'
        require(serial < 2, 'only W1 and W2 Preview permitted')
        serial += 1
        before = snapshot(label+'-before')
        preview,manifest = original_preview(*a,**kw)
        after = snapshot(label+'-after')
        operation = preview['result']['operation_id']
        pairs = manifest['pairs']
        require(len(pairs) == 1, 'one MODIFIED_ONLY pair')
        # First empty-baseline preview must not read any Repository rows; its
        # exact initial commit is the context passed by _run_tier.
        commit = context.get('commit',context['initial_commit'])
        value = window(label,before,after,context['repo'],commit)
        worker = value.pop('worker_text')
        records = [json.loads(line.split('s3_pair_metrics ',1)[1]) for line in worker.splitlines() if 's3_pair_metrics ' in line]
        require(len(records) == 1 and records[0]['pair_id'] == pairs[0]['pair_id'], 'unique pair metric in isolated Preview window')
        observed = re.findall(r'operation_worker_event code=\S+ operation_id=(\S+)',worker)
        require(set(observed)-{'-'} == {operation}, 'actual worker event operation attribution')
        metric = records[0]
        for key in ('comparison_kernel_calls','ordered_single_side_calls','cache_restore_calls','cache_records_validation_calls','digest_rebinds','charged_high_water_bytes'):
            require(type(metric.get(key)) is int and metric[key] >= 0, 'required real pair counter '+key)
        require(metric['charged_high_water_bytes'] <= M, 'actual pair reservation HWM <= M24')
        value.update(operation_id=operation,pair_id=pairs[0]['pair_id'],pair_metrics=metric)
        if label == 'w2':
            require('calibration' in context and context['calibration']['rows_HTTP_requests'] > 0, 'positive calibration precedes W2')
            require(metric['comparison_kernel_calls'] == 0 and value['rows_HTTP_requests'] == 0, 'W2 kernel and actual RS rows zero')
            backend = after['resources']['services']['backend']['id']
            raw = command(['docker','exec',backend,'python','-c',CANONICAL,json.dumps([context['repo'],operation,context['commit']])],text=True)
            (output/'w2-canonical.stdout.log').write_text(raw.stdout)
            (output/'w2-canonical.stderr.log').write_text(raw.stderr)
            logical = json.loads(raw.stdout)
            require(logical['logical_baseline_row_demand'] == 0 and not logical['X'] and not logical['D'], 'W2 complete canonical U/X/A/D demand')
            write(output/'w2-canonical-identities.json',logical)
        write(output/(label+'-window.json'),value)
        result['windows'].append(value)
        return preview,manifest

    def saved_bundle(client,url,**kw):
        index = len(list(output.glob('preview-*.tar')))
        require(index < 2, 'only two existing complete Preview GETs')
        manifest,transfer = download_bundle_tar(client,url,destination=output/f'preview-{index}.tar',**kw)
        transfer['theoretical_1Mbps_lower_bound_seconds'] = 8*transfer['actual_bytes']/1000000
        write(output/f'preview-{index}-manifest.json',manifest)
        write(output/f'preview-{index}-transfer.json',transfer)
        return manifest,transfer

    def tier(**kw):
        context.update(repo=kw['repository_id'],initial_commit=kw['initial_commit_id'])
        snapshot('ready')
        return original_tier(**kw)

    j._compose_environment,j._preview = compose_env,checked_preview
    j._pseudo_counts_from_http,j._run_tier,j.download_bundle_tar = checked_read,tier,saved_bundle
    code = 1
    try:
        os.environ['GATEWAY_REAL_DUMP_ROOT'] = str(args.input_root.resolve())
        os.environ['GATEWAY_REAL_DUMP_LOG_DIR'] = str(output/'compose-logs')
        result['journey'] = j._run_kernel_journey(argparse.Namespace(
            kernel_threads=1,kernel_memory_budget_bytes=M,tier='t4',scope='t4-w1-w2',
            cross_project=False,from_step=None,keep_stack=True,project_name=args.compose_name,
            dc32_output=None,debug_submit_probe_t1=False,v2_input_completeness='MODIFIED_ONLY',
            s3_census=None,submit_measurements=None,s4_skip_repeat_v1=False))
        require(serial == 2 and len(result['windows']) == 2 and 'repository_oracle' in result, 'all mandatory scope consumers ran')
        snapshot('final-running')
        result['status'] = 'PASS'
        code = 0
    except BaseException as exc:
        result['failure'] = {'type':type(exc).__name__,'message':str(exc)}
    finally:
        errors = []
        if context.get('env'):
            env = context['env']
            try:
                ids = resource._owned_containers(args.compose_name,worktree,env)
            except BaseException as exc:
                errors.append('stop inventory: '+type(exc).__name__+': '+str(exc))
                ids = [service['id'] for service in context.get('services',{}).values()]
            for cid in ids:
                name = next((key for key,value in context.get('services',{}).items() if value['id'] == cid),cid)
                try:
                    info = resource._inspect(cid,worktree,env)
                    name = info['Config']['Labels']['com.docker.compose.service']
                    require(info['Config']['Labels']['com.docker.compose.project'] == args.compose_name and name in SERVICES,
                            'stop only known owned project services')
                    resource._stop_normally(cid,worktree,env)
                    stopped = resource._inspect(cid,worktree,env)
                    result.setdefault('stopped_services',{})[name] = {'container_id':cid,'exit_code':stopped['State']['ExitCode'],
                        'running':stopped['State']['Running'],'oom_killed':stopped['State']['OOMKilled'],
                        'restart_count':stopped['RestartCount'],'image_id':stopped['Image']}
                    accepted_exits = {0,143} if name == 'repository-service' else {0}
                    require(not stopped['State']['Running'] and stopped['State']['ExitCode'] in accepted_exits
                            and not stopped['State']['OOMKilled'] and stopped['RestartCount'] == 0,
                            'normal owned service termination without OOM/restart')
                except BaseException as exc:
                    errors.append(str(name)+' stop: '+type(exc).__name__+': '+str(exc))
                finally:
                    try:
                        raw = command(['docker','logs','--timestamps',cid])
                        (output/f'final-{cid}.stdout.log').write_bytes(raw.stdout)
                        (output/f'final-{cid}.stderr.log').write_bytes(raw.stderr)
                    except BaseException as exc:
                        errors.append(str(name)+' final logs: '+type(exc).__name__+': '+str(exc))
            if context.get('services') and set(result.get('stopped_services',{})) != set(SERVICES):
                errors.append('all started owned services require actual stopped-service receipts')
        end_head = command(['git','-C',str(worktree),'rev-parse','HEAD'],text=True).stdout.strip()
        end_dirty = command(['git','-C',str(worktree),'status','--porcelain'],text=True).stdout
        if end_head != args.candidate_head or end_dirty:
            errors.append('end candidate HEAD/clean guard failed')
        if errors:
            code = 1
            result['status'] = 'FAIL'
        result.update(end_head=end_head,end_worktree_clean=not bool(end_dirty),
                      end_utc=utc(),exit_code=code,stop_errors=errors,volumes_preserved=True,
                      cleanup_policy='own services normally stopped; inputs, secrets, original evidence and owned volumes retained for review')
        write(output/'result.json',result)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
