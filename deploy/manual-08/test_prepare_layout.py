"""Exercise initial layout rendering against the real host preflight."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / 'vnext/scripts'))
import prepare_layout  # noqa: E402


class PrepareLayoutTest(unittest.TestCase):
    def test_one_group_uses_owned_roots_and_standard_renderer(self):
        with tempfile.TemporaryDirectory() as directory:
            original = (prepare_layout.ROOT, prepare_layout.SOURCE, prepare_layout.PYTHON,
                        prepare_layout.HOST_BUDGET)
            try:
                prepare_layout.ROOT = Path(directory)
                prepare_layout.SOURCE = REPOSITORY
                prepare_layout.PYTHON = Path(sys.executable)
                prepare_layout.HOST_BUDGET = {'memory_bytes': 48 * 1024**3, 'cpu_count': 8,
                                              'shared_memory_reserve_bytes': 8 * 1024**3,
                                              'shared_cpu_reserve': 2}
                prepare_layout.prepare('a', 'a' * 40, prepare_layout.host.mounts())
                a = Path(directory) / 'a'
                groups = json.loads((a / 'public/groups.json').read_text())
                layout = json.loads((a / 'group/storage-layout.json').read_text())
                self.assertEqual(groups['environment_id'], 'gw08-a')
                self.assertEqual(groups['groups'][0]['project'], 'gdds08-a')
                self.assertEqual(len(layout['roots']), 10)
                self.assertTrue(all(Path(v['source']).is_relative_to(a / 'group/roots') for v in layout['roots'].values()))
                self.assertNotEqual((a / 'group/internal.token').read_bytes(), (a / 'group/repository.token').read_bytes())
                self.assertTrue((a / 'group/compose-runtime.json').is_file())
            finally:
                (prepare_layout.ROOT, prepare_layout.SOURCE, prepare_layout.PYTHON,
                 prepare_layout.HOST_BUDGET) = original


if __name__ == '__main__':
    unittest.main()
