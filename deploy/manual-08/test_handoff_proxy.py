"""Address-aware handoff checks, without real credentials or business data."""
import base64
import json
import unittest
from urllib.parse import urlsplit

import handoff_proxy


def handoff(return_url: str) -> bytes:
    payload = {'token': 'test-token', 'return_url': return_url, 'business_project_id': 'test'}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    return json.dumps({'gateway_url': 'https://192.168.233.209:10443/#gdds-handoff=' + encoded}).encode()


class HandoffProxyTest(unittest.TestCase):
    def test_preserves_scope_and_returns_to_the_accessed_address(self):
        for host, env, gateway, public in (
            ('192.168.233.209:28443', '/a', 'https://192.168.233.209:28443/', 'https://192.168.233.209:28443/?q=x'),
            ('10.78.0.3:28443', '/a', 'https://10.78.0.3:28443/', 'https://10.78.0.3:28443/?q=x'),
            ('10.79.0.3:9443', '/b', 'https://10.79.0.3:10443/', 'https://10.79.0.3:9443/?q=x'),
            ('192.168.233.209:9443', '/b', 'https://192.168.233.209:10443/', 'https://192.168.233.209:9443/?q=x'),
            ('[2001:db8::1]:9443', '/b', 'https://[2001:db8::1]:10443/', 'https://[2001:db8::1]:9443/?q=x'),
        ):
            with self.subTest(host=host):
                result = json.loads(handoff_proxy.rewrite(handoff('https://old.example/?q=x'), host, env))
                target = result['gateway_url']
                self.assertTrue(target.startswith(gateway + '#gdds-handoff='))
                value = urlsplit(target).fragment.split('=', 1)[1]
                decoded = json.loads(base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)))
                self.assertEqual(decoded['return_url'], public)
                self.assertEqual(decoded['token'], 'test-token')
                self.assertEqual(decoded['business_project_id'], 'test')

    def test_rejects_unsafe_authorities_and_unmapped_ports(self):
        for host in ('evil.example@10.78.0.3:9443', '10.78.0.3:9443/path',
                     '10.78.0.3:9443,evil', '10.78.0.3', '10.78.0.3:9444'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                handoff_proxy.external_urls(host, '/b')


if __name__ == '__main__':
    unittest.main()
