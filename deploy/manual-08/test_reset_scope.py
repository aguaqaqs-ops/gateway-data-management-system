"""Scope guards for destructive manual-environment reset."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import reset_a


class ResetScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.a = self.root / 'a'
        for path in (self.a / 'group/roots', self.a / 'entry', self.a / 'private'):
            path.mkdir(parents=True)
        self.original_root, self.original_a = reset_a.ROOT, reset_a.A
        reset_a.ROOT, reset_a.A = self.root, self.a
        roots = {}
        for index, slot in enumerate(reset_a.SLOTS, 1):
            path = self.a / 'group/roots' / slot
            path.mkdir()
            identity = f'{index:032x}'
            roots[slot] = {'source': str(path), 'storage_id': identity}
            (path / '.gateway-storage.json').write_text(json.dumps({
                'schema_version': 1, 'environment_id': 'gw08-a', 'group_id': 'group-a',
                'slot': slot, 'storage_id': identity}))
        (self.a / 'group/storage-layout.json').write_text(json.dumps({
            'environment_id': 'gw08-a', 'group_id': 'group-a', 'roots': roots}))

    def tearDown(self):
        reset_a.ROOT, reset_a.A = self.original_root, self.original_a
        self.temp.cleanup()

    def test_rejects_redirected_or_unmarked_roots(self):
        reset_a.validate_roots()
        root = self.a / 'group/roots/be-durable'
        (root / '.gateway-storage.json').unlink()
        (root / 'unknown').write_text('x')
        with self.assertRaises((ValueError, OSError)):
            reset_a.validate_roots()
        (root / 'unknown').unlink()
        root.rmdir()
        root.symlink_to(self.a / 'group/roots/be-canonical', target_is_directory=True)
        with self.assertRaises(ValueError):
            reset_a.validate_roots()

    def test_refuses_foreign_container_mounting_reset_scope(self):
        containers = [{'Config': {'Labels': {'com.docker.compose.project': 'gdds08-b'}},
                       'Mounts': [{'Type': 'bind', 'Source': str(self.a / 'group/roots/be-durable')}]}]
        def fake_call(*args):
            return 'container-id' if args[:3] == ('docker', 'ps', '-aq') else json.dumps(containers)
        with patch.object(reset_a, 'call', side_effect=fake_call):
            with self.assertRaises(ValueError):
                reset_a.inspect_scope(allow_owned=True)

    def test_refuses_target_project_mounting_outside_a(self):
        containers = [{'Config': {'Labels': {'com.docker.compose.project': 'gdds08-a'}},
                       'Mounts': [{'Type': 'bind', 'Source': str(self.root / 'b')}]}]
        def fake_call(*args):
            return 'container-id' if args[:3] == ('docker', 'ps', '-aq') else json.dumps(containers)
        with patch.object(reset_a, 'call', side_effect=fake_call):
            with self.assertRaises(ValueError):
                reset_a.inspect_scope(allow_owned=True)

    def test_compose_config_cannot_bind_b_or_publish_another_port(self):
        group = {'name': 'gdds08-a', 'services': {
            'backend': {'volumes': [{'type': 'bind', 'source': str(self.a / 'group/roots/be-durable')}],
                        'ports': [{'target': 8000, 'published': '18000', 'host_ip': '127.0.0.1'}]},
            'worker': {}, 'repository-service': {}},
            'networks': {'default': {'name': 'gdds08-a_default'}}}
        entry = {'name': 'gdds08-a-entry', 'services': {'entry': {'network_mode': 'host',
                  'volumes': [{'type': 'bind', 'source': str(self.a / 'entry')}]}}}
        def fake_call(*args, **kwargs):
            return json.dumps(group if args[0] == 'group' else entry)
        with patch.object(reset_a, 'call', side_effect=fake_call):
            reset_a.validate_compose(('group',), ('entry',), {})
            group['services']['backend']['volumes'][0]['source'] = str(self.root / 'b')
            with self.assertRaises(ValueError):
                reset_a.validate_compose(('group',), ('entry',), {})
            group['services']['backend']['volumes'][0]['source'] = str(self.a / 'group/roots/be-durable')
            group['services']['backend']['ports'][0]['published'] = '18001'
            with self.assertRaises(ValueError):
                reset_a.validate_compose(('group',), ('entry',), {})


if __name__ == '__main__':
    unittest.main()
