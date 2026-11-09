"""Read-only BE-c facts from exactly four saved S5 complete tars; dedicated CT only."""
import argparse
import hashlib
import json
from pathlib import Path
from benchmarks.bundle_tar import verify_bundle_tar
from gateway_backend.bootstrap.compute_kernel import initialize_compute_kernel

p = argparse.ArgumentParser()
p.add_argument('--bundle-index',type=Path,required=True)
p.add_argument('--tar-root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a = p.parse_args()
initialize_compute_kernel(1)
result = []
for row in json.loads(a.bundle_index.read_bytes())['bundles']:
    path = a.tar_root / row['path']
    with path.open('rb') as source:
        digest = hashlib.file_digest(source,'sha256').hexdigest()
        assert digest == row['tar_sha256'] and path.stat().st_size == row['actual_bytes']
        source.seek(0)
        manifest,metrics = verify_bundle_tar(source,total_bytes=row['actual_bytes'])
    prior = json.loads((a.tar_root/row['transfer_path']).read_bytes())
    assert metrics['bundle_digest'] == prior['bundle_digest'] and len(manifest['pairs']) == row['pair_count']
    assert all(metrics[k] == prior[k] for k in metrics)
    result.append({**row,'bundle_identity':metrics['bundle_digest'],'current_read_only_complete_integrity':'PASS',
                   'integrity':metrics,'theoretical_1Mbps_lower_bound_seconds':8*row['actual_bytes']/1000000,
                   'timing_policy':'theoretical bound only; no protocol/browser overhead, no network measurement'})
with a.output.open('x') as f:
    json.dump({'source':'preserved S5 original bytes, no stack/HTTP/new operation','bundles':result},f,sort_keys=True,indent=2)
    f.write('\n')
