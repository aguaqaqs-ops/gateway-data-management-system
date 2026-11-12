#!/usr/bin/env python3
"""Deterministic identity checks for directory frontend evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import zlib
from datetime import datetime
spec = importlib.util.spec_from_file_location('service_inputs', Path(__file__).with_name('service_inputs.py'))
if spec is None or spec.loader is None:
    raise RuntimeError('cannot load input verifier')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
file_hash, tree_hash = module.file_hash, module.tree_hash

CONFIG = 'sha256:a0d7b2b49ffa0e99787a00b7ec2af46eca58020082713f002ca9f0f1cfd1a017'
DIFFS = ['sha256:bec87777bc2fb2edcdf9af11df1531469e7df911309c1413082b18fcb8610278', 'sha256:1590c449306a9032a32c49afeac5e4c7cae86197c4a7dd95c095c3ae220a7f07', 'sha256:c8a795d9cdbc02d20daf1ecac5377667d61d63392fbe5bdbba94cc79a4cf3fe9', 'sha256:89e210c351d8ddaa3c7a6132e19a5aaf27ec837371dd94f0698dfa4c1e5aef3d', 'sha256:ea03ac3d8e487159afdc9d45b9a8d3f4035418655881b896cc34fa2e464c27fc', 'sha256:16f77d0178dafdf603cd05f8464e39df636665b2b028e18e0b95bfbee5ecacd5', 'sha256:d8597d6a5431eca9c1082ade19c2b7cdef69fbaaae43f0b67fbbd25f3a35c2bb']


def main() -> None:
    command, *args = sys.argv[1:]
    if command == 'image' and len(args) == 1:
        value = json.loads(args[0])
        if value['config_digest'] != CONFIG or value['diff_ids'] != DIFFS:
            raise ValueError('toolchain identity mismatch')
    elif command == 'verify' and len(args) == 4:
        manifest, cache, archive, lock = map(Path, args)
        doc = json.loads(manifest.read_text())
        fields = {'source_hostname', 'source_commit', 'prefilled_utc', 'lock_sha256', 'archive_sha256', 'cache_tree_sha256'}
        if set(doc) != fields or not all(isinstance(v, str) and v for v in doc.values()):
            raise ValueError('invalid cache manifest')
        if not re.fullmatch(r'[A-Za-z0-9._-]+', doc['source_hostname']) or not re.fullmatch(r'[0-9a-f]{40}', doc['source_commit']):
            raise ValueError('invalid source')
        datetime.strptime(doc['prefilled_utc'], '%Y-%m-%dT%H:%M:%SZ')
        if file_hash(lock) != doc['lock_sha256'] or file_hash(archive) != doc['archive_sha256'] or tree_hash(cache) != doc['cache_tree_sha256']:
            raise ValueError('cache input mismatch')
        print('cache_manifest_sha256=' + file_hash(manifest))
        print(json.dumps(doc, sort_keys=True))
    elif command == 'screenshots' and len(args) == 1:
        root = Path(args[0])
        names = [f'{state}-{width}.png' for state in ('browse', 'search', 'unprovisioned', 'handoff-error', 'empty') for width in (1280, 1920)]
        if set(p.name for p in root.iterdir()) != set(names):
            raise ValueError('screenshot set mismatch')
        records = []
        for name in names:
            path = root / name
            if path.is_symlink() or not path.is_file():
                raise ValueError('invalid screenshot')
            data = path.read_bytes()
            if data[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError('invalid PNG signature')
            offset, kinds, compressed = 8, [], bytearray()
            while offset < len(data):
                if offset + 12 > len(data):
                    raise ValueError('truncated PNG chunk')
                size = struct.unpack('>I', data[offset:offset + 4])[0]
                end = offset + 12 + size
                if end > len(data):
                    raise ValueError('truncated PNG payload')
                kind, payload = data[offset + 4:offset + 8], data[offset + 8:offset + 8 + size]
                crc = struct.unpack('>I', data[offset + 8 + size:end])[0]
                if zlib.crc32(kind + payload) != crc:
                    raise ValueError('invalid PNG CRC')
                kinds.append(kind)
                if len(kinds) == 1:
                    if kind != b'IHDR' or size != 13 or struct.unpack('>I', payload[:4])[0] != int(name.rsplit('-', 1)[1][:-4]) or struct.unpack('>I', payload[4:8])[0] == 0:
                        raise ValueError('invalid PNG dimensions')
                    width, height, depth, colour, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
                    if depth != 8 or colour not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
                        raise ValueError('unsupported PNG encoding')
                if kind == b'IDAT':
                    compressed.extend(payload)
                if kind == b'IEND':
                    if size != 0 or end != len(data):
                        raise ValueError('invalid PNG ending')
                    break
                offset = end
            if not kinds or kinds[-1] != b'IEND' or not compressed:
                raise ValueError('incomplete PNG')
            decoder = zlib.decompressobj()
            pixels = decoder.decompress(compressed) + decoder.flush()
            stride = 1 + width * (3 if colour == 2 else 4)
            if not decoder.eof or decoder.unused_data or len(pixels) != height * stride or any(pixels[row * stride] > 4 for row in range(height)):
                raise ValueError('invalid PNG scanlines')
            records.append(f'{file_hash(path)}  {name}\n')
        contents = ''.join(records).encode()
        (root / 'SHA256SUMS').write_bytes(contents)
        print('screenshot_manifest_sha256=' + hashlib.sha256(contents).hexdigest())
        print(contents.decode(), end='')
    else:
        raise ValueError('invalid arguments')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
        print(f'frontend input verification failed: {type(exc).__name__}', file=sys.stderr)
        sys.exit(1)
