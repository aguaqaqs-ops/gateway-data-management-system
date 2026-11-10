import hashlib
import json
import sys
import tarfile
from pathlib import Path

source = json.loads(Path(sys.argv[1]).read_text())
mode = sys.argv[2]
assert mode in {'base', 'dependency'}
expected = source['base_image_identity'] if mode == 'base' else {
    'config_digest': source['config_digest'], 'diff_ids': source['diff_ids']
}
with tarfile.open(sys.argv[3], mode='r:*') as archive:
    item = archive.extractfile('manifest.json')
    assert item is not None
    manifest = json.load(item)
    assert len(manifest) == 1
    item = archive.extractfile(manifest[0]['Config'])
    assert item is not None
    raw = item.read()
    config = json.loads(raw)
actual = {'config_digest': 'sha256:' + hashlib.sha256(raw).hexdigest(),
          'diff_ids': config['rootfs']['diff_ids']}
print(json.dumps({'mode': mode, 'actual': actual, 'expected': expected}, sort_keys=True))
assert actual == expected, 'config digest or complete DiffID list differs'
if mode == 'dependency':
    assert config['config']['Labels']['gateway.backend.dependency-input-sha256'] == source['input_sha256']
print('IDENTITY_MATCH', mode)
