"""Zero-swap registration rejects already-drifted container limits."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pin_cgroups


class PinCgroupsTest(unittest.TestCase):
    def test_refuses_preexisting_drift_before_setting_property(self):
        ident = 'a' * 64
        containers = [{'Id': ident, 'Config': {'Labels': {'com.docker.compose.service': role}},
                       'State': {'Running': True, 'Pid': index + 100},
                       'HostConfig': {'Memory': 1024, 'MemorySwap': 1024}}
                      for index, role in enumerate(('backend', 'worker', 'repository-service'))]
        def output(args, **kwargs):
            if args[:2] == ['docker', 'info']:
                return 'systemd\n'
            if args[:2] == ['docker', 'ps']:
                return 'first\nsecond\nthird\n'
            return json.dumps(containers)
        def content(path, *args, **kwargs):
            if str(path).endswith('/cgroup'):
                return f'0::/system.slice/docker-{ident}.scope\n'
            return '1024\n' if path.name == 'memory.max' else 'max\n'
        with patch.object(sys, 'argv', ['pin_cgroups.py', 'a']), \
             patch.object(pin_cgroups.subprocess, 'check_output', side_effect=output), \
             patch.object(Path, 'read_text', content), \
             patch.object(pin_cgroups.subprocess, 'run') as command:
            with self.assertRaises(ValueError):
                pin_cgroups.main()
            command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
