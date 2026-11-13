"""Adapt the fixed directory handoff to the address used by this browser."""
import base64
import http.client
import ipaddress
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

DESTINATIONS = {'/a': 18100, '/b': 18101}
GATEWAY_PORTS = {9443: 10443}


def external_urls(host: str, environment: str) -> tuple[str, str]:
    if not host.isascii() or any(c.isspace() or c in '\\,@/#?' for c in host):
        raise ValueError('invalid host')
    parsed = urlsplit('https://' + host)
    name, port = parsed.hostname, parsed.port
    if (not name or not port or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('invalid host')
    try:
        ipaddress.ip_address(name)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9.-]+', name):
            raise ValueError('invalid host') from None
    authority = f'[{name}]' if ':' in name else name
    origin = f'https://{authority}:{port}'
    if environment == '/a':
        return origin + '/', origin + '/'
    if environment == '/b' and port in GATEWAY_PORTS:
        return origin + '/', f'https://{authority}:{GATEWAY_PORTS[port]}/'
    raise ValueError('unsupported directory port')


def rewrite(data: bytes, host: str, environment: str) -> bytes:
    public_url, gateway_url = external_urls(host, environment)
    result = json.loads(data)
    fragment = urlsplit(result['gateway_url']).fragment
    prefix = 'gdds-handoff='
    if not fragment.startswith(prefix):
        raise ValueError('invalid handoff')
    encoded = fragment[len(prefix):]
    payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    previous = urlsplit(payload['return_url'])
    if previous.fragment:
        raise ValueError('invalid return URL')
    payload['return_url'] = public_url + ('?' + previous.query if previous.query else '')
    encoded = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()).decode().rstrip('=')
    return json.dumps({'gateway_url': gateway_url + '#' + prefix + encoded}, separators=(',', ':')).encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        try:
            if self.path not in DESTINATIONS or len(self.headers.get_all('Host', [])) != 1:
                raise ValueError('invalid request')
            host = self.headers['Host']
            external_urls(host, self.path)
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or self.headers.get('Transfer-Encoding') is not None:
                raise ValueError('invalid length')
            length = int(lengths[0])
            if not 0 <= length <= 8192:
                raise ValueError('invalid length')
            self.connection.settimeout(10)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError('incomplete request')
            upstream = http.client.HTTPConnection('127.0.0.1', DESTINATIONS[self.path], timeout=15)
            try:
                upstream.request('POST', '/api/handoffs', body=body, headers={'Content-Type': 'application/json'})
                response = upstream.getresponse()
                status, data = response.status, response.read(1048577)
            finally:
                upstream.close()
            if len(data) > 1048576:
                raise ValueError('response too large')
            if status == 200:
                data = rewrite(data, host, self.path)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, http.client.HTTPException):
            status, data = 400, b'{"code":"HANDOFF_UNAVAILABLE"}'
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self) -> None:
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(('127.0.0.1', 18102), Handler)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(10)
        return request, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


if __name__ == '__main__':
    Server().serve_forever()
