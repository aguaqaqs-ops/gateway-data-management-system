"""Stdlib Nginx entry rendering and bounded, observable atomic hot publication."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Callable
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError

from processing_group_config import DeviceDirectory, ProcessingGroupsConfig

DEFAULT_ENTRY_IMAGE = "nginx:1.28.0"
CONTAINER_DIRECTORY = "/etc/gateway-entry"


class Incomplete(RuntimeError):
    """A durable step may have completed; inspect and retry the same identity."""


class Busy(RuntimeError):
    """A prior worker generation is still serving a request."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: object, code: int, msg: str,
                         headers: object, newurl: str) -> None:
        return None


def request_json(url: str, *, token: str | None = None, key: str | None = None,
                 body: dict[str, object] | None = None, timeout: float = 5) -> dict[str, object]:
    headers = {"Accept": "application/json", "Connection": "close"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if key is not None:
        headers["X-Gateway-Device-Key"] = key
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(Request(url, data=data, headers=headers), timeout=timeout) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise Incomplete("management response exceeds limit")
            value = json.loads(raw)
    except HTTPError as exc:
        # Never echo a URL, credential, response payload or server private path.
        raise Incomplete("management request rejected (HTTP " + str(exc.code) + ")") from None
    except (OSError, ValueError):
        raise Incomplete("management request unavailable or invalid") from None
    if type(value) is not dict:
        raise Incomplete("invalid management response")
    return value


def atomic_write(path: Path, raw: bytes, *, mode: int = 0o644) -> None:
    """Publish in the existing controlled parent; containers mount that parent."""
    descriptor, temporary = tempfile.mkstemp(prefix=".gateway-publish-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def render_entry(groups: ProcessingGroupsConfig, directory: DeviceDirectory) -> tuple[str, bytes]:
    groups.require_directory(directory)
    entry = groups.entry
    listen = "[" + entry.listen_address + "]" if ":" in entry.listen_address else entry.listen_address
    enabled = sorted((row.route_key, row.group_id) for row in directory.devices if row.enabled)
    backends = "\n".join(f"    upstream gateway_{group.group_id} {{ server 127.0.0.1:{group.backend_port}; }}" for group in groups.groups)
    routes = "\n".join(f"        {key} http://gateway_{group};" for key, group in enabled)
    names = "\n".join(f"        {key} {group};" for key, group in enabled)
    # Empty default and case-sensitive regex precede maps; arbitrary caller bytes
    # never become an upstream URL. SHA-256 keys avoid map's case-folded strings.
    text = f'''worker_processes 1;
pid /tmp/gateway-entry.pid;
error_log /dev/stderr warn;
events {{ worker_connections 1024; }}
http {{
    access_log off;
    map_hash_bucket_size 128;
    map_hash_max_size 32768;
    client_body_temp_path /tmp/client_body;
    proxy_temp_path /tmp/proxy;
    fastcgi_temp_path /tmp/fastcgi;
    uwsgi_temp_path /tmp/uwsgi;
    scgi_temp_path /tmp/scgi;
    map $http_x_gateway_device_key $gateway_key {{
        default "";
        "~^[0-9a-f]{{64}}$" $http_x_gateway_device_key;
    }}
    map $gateway_key $gateway_upstream {{
        default "";
{routes}
    }}
    map $arg_key $gateway_probe_group {{
        default "";
{names}
    }}
{backends}
    server {{
        listen {listen}:{entry.listen_port};
        server_name _;
        default_type application/json;
        error_page 400 411 414 422 494 = @gateway_invalid;
        error_page 404 = @gateway_not_found;
        error_page 408 502 503 504 = @gateway_unavailable;
        error_page 500 = @gateway_internal;
        location @gateway_invalid {{ return 422 '{{"code":"REQUEST_VALIDATION_FAILED","message":"request validation failed","details":null}}'; }}
        location @gateway_not_found {{ return 404 '{{"code":"RESOURCE_NOT_FOUND","message":"resource not found","details":null}}'; }}
        location @gateway_unavailable {{ return 503 '{{"code":"DEPENDENCY_UNAVAILABLE","message":"service unavailable","details":null}}'; }}
        location @gateway_internal {{ return 500 '{{"code":"INTERNAL_ERROR","message":"internal server error","details":null}}'; }}
        client_max_body_size 0;
        client_body_timeout 600s;
        send_timeout 600s;
        location = /healthz {{ return 200 '{{"status":"ok"}}'; }}
        location /v1/ {{
            if ($gateway_key = "") {{ return 422; }}
            if ($gateway_upstream = "") {{ return 404; }}
            proxy_http_version 1.1;
            proxy_request_buffering off;
            proxy_buffering off;
            proxy_cache off;
            proxy_next_upstream off;
            proxy_intercept_errors off;
            proxy_redirect off;
            proxy_connect_timeout 5s;
            proxy_read_timeout 600s;
            proxy_send_timeout 600s;
            proxy_set_header Connection "";
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Gateway-Group "";
            proxy_set_header X-Gateway-Environment "";
            proxy_set_header X-Gateway-Internal-Identity "";
            proxy_pass $gateway_upstream$request_uri;
        }}
        location / {{ return 404; }}
    }}
    server {{
        listen 127.0.0.1:{entry.management_port};
        server_name _;
        default_type application/json;
        location = /status {{ return 200 '{{"config_digest":"DIGEST_PLACEHOLDER","group_id":"$gateway_probe_group"}}'; }}
        location / {{ return 404; }}
    }}
}}
'''
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest, text.replace("DIGEST_PLACEHOLDER", digest).encode("utf-8")


def verify_config_identity(raw: bytes, digest: str) -> None:
    """Bind the loaded static probe digest to these exact generated bytes."""
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise Incomplete("entry digest is invalid")
    needle = ('"config_digest":"' + digest + '"').encode()
    if raw.count(needle) != 1:
        raise Incomplete("entry version identity is missing or ambiguous")
    preimage = raw.replace(needle, b'"config_digest":"DIGEST_PLACEHOLDER"')
    if hashlib.sha256(preimage).hexdigest() != digest:
        raise Incomplete("entry version content differs from loaded identity")


def require_append_only_routes(previous: bytes, current: bytes) -> None:
    """Hot add cannot alter a route or upstream already loaded by Nginx."""
    def selections(raw: bytes) -> tuple[dict[bytes, bytes], dict[bytes, bytes]]:
        routes = dict(re.findall(rb"^        ([0-9a-f]{64}) http://gateway_([a-z0-9][a-z0-9_-]{0,63});$", raw, re.MULTILINE))
        upstreams = dict(re.findall(rb"^    upstream gateway_([a-z0-9][a-z0-9_-]{0,63}) \{ server 127\.0\.0\.1:([0-9]+); \}$", raw, re.MULTILINE))
        return routes, upstreams
    listeners_before = re.findall(rb"^        listen ([^;\n]+);$", previous, re.MULTILINE)
    listeners_after = re.findall(rb"^        listen ([^;\n]+);$", current, re.MULTILINE)
    if not listeners_before or listeners_before != listeners_after:
        raise Incomplete("hot publication would alter entry listeners")
    before, after = selections(previous), selections(current)
    if any(after[index].get(key) != value for index in (0, 1) for key, value in before[index].items()):
        raise Incomplete("hot publication would alter an existing route or upstream")


class EntryRuntime:
    """Only targets the independent entry project and its single fixed service."""
    def __init__(self, groups: ProcessingGroupsConfig, directory: Path, project: str) -> None:
        import re
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project) is None:
            raise ValueError("invalid entry compose project")
        if project in {group.project for group in groups.groups}:
            raise ValueError("entry project must be independent")
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError("entry directory must exist and be absolute")
        self.groups, self.directory, self.project = groups, directory, project
        self.compose_file = Path(__file__).resolve().parents[1] / "deploy/compose.entry.yaml"

    def _environment(self) -> dict[str, str]:
        return {**os.environ, "GATEWAY_ENTRY_DIRECTORY": str(self.directory),
            "GATEWAY_ENTRY_IMAGE": self.groups.entry.image,
            "GATEWAY_ENTRY_MEMORY": str(self.groups.entry.memory_limit_bytes),
            "GATEWAY_ENTRY_CPUS": str(self.groups.entry.cpu_limit)}

    def command(self, arguments: list[str], *, timeout: float = 15) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(arguments, env=self._environment(), capture_output=True, text=True,
                timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise Incomplete("entry command unavailable or timed out") from None

    def compose(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.command(["docker", "compose", "-p", self.project, "-f", str(self.compose_file), *arguments])

    def container_id(self) -> str:
        result = self.compose("ps", "-q", "entry")
        container = result.stdout.strip()
        if result.returncode or not container or "\n" in container:
            raise Incomplete("entry is not running")
        inspected = self.command(["docker", "container", "inspect", container])
        selected = self.command(["docker", "image", "inspect", "--format", "{{.Id}}", self.groups.entry.image])
        if inspected.returncode or selected.returncode:
            raise Incomplete("entry image or container identity unavailable")
        try:
            actual = json.loads(inspected.stdout)[0]
            labels = actual["Config"]["Labels"]
            mounts = [mount for mount in actual["Mounts"] if mount["Destination"] == CONTAINER_DIRECTORY]
            if (labels.get("com.docker.compose.project"), labels.get("com.docker.compose.service")) != (self.project, "entry"):
                raise ValueError("entry project differs")
            if actual["Image"] != selected.stdout.strip() or actual["Config"]["Image"] != self.groups.entry.image:
                raise ValueError("entry image differs from validator")
            if actual["HostConfig"]["NetworkMode"] != "host" or actual["HostConfig"]["Memory"] != self.groups.entry.memory_limit_bytes:
                raise ValueError("entry network or memory differs")
            if actual["HostConfig"]["NanoCpus"] != round(self.groups.entry.cpu_limit * 1_000_000_000):
                raise ValueError("entry CPU differs")
            if len(mounts) != 1 or mounts[0]["Type"] != "bind" or mounts[0]["RW"] or Path(mounts[0]["Source"]).resolve() != self.directory.resolve():
                raise ValueError("entry parent mount differs")
        except (ValueError, KeyError, IndexError, TypeError):
            raise Incomplete("entry deployment differs from selected manifest") from None
        return container

    def retiring_workers(self) -> bool:
        result = self.command(["docker", "top", self.container_id(), "-eo", "pid,args"])
        if result.returncode:
            raise Incomplete("entry process generation unavailable")
        return "nginx: worker process is shutting down" in result.stdout

    def probe(self, key: str = "", *, timeout: float = 5) -> dict[str, object]:
        return request_json(f"http://127.0.0.1:{self.groups.entry.management_port}/status?key={key}", timeout=timeout)

    def validate(self, filename: str) -> None:
        # Same selected image, host network and parent mount; no pulls or mutable build.
        result = self.command(["docker", "run", "--rm", "--pull=never", "--network=host",
            "--read-only", "--user", "101:101", "--cap-drop=ALL", "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp", "-v", str(self.directory) + ":" + CONTAINER_DIRECTORY + ":ro",
            "--entrypoint", "nginx", self.groups.entry.image,
            "-t", "-c", CONTAINER_DIRECTORY + "/" + filename])
        if result.returncode:
            atomic_write(self.directory / "last-error.txt", result.stderr.encode("utf-8", errors="replace"))
            raise Incomplete("candidate entry configuration rejected")

    def loaded_config(self, current: dict[str, object]) -> bytes:
        loaded_digest = current.get("config_digest")
        if type(loaded_digest) is not str or len(loaded_digest) != 64 or any(char not in "0123456789abcdef" for char in loaded_digest):
            raise Incomplete("loaded entry digest unavailable")
        version = self.directory / "versions" / (loaded_digest + ".conf")
        raw = version.read_bytes() if version.exists() else (self.directory / "nginx.conf").read_bytes()
        verify_config_identity(raw, loaded_digest)
        return raw

    def require_append_only(self, candidate: bytes) -> None:
        require_append_only_routes(self.loaded_config(self.probe()), candidate)

    def publish(self, digest: str, raw: bytes, *, key: str, group: str,
                timeout: float = 30, poll: Callable[[float], None] = time.sleep) -> None:
        verify_config_identity(raw, digest)
        try:
            current = self.probe(key)
        except Incomplete:
            raise Incomplete("entry load state unavailable; start a validated entry before hot add") from None
        if current == {"config_digest": digest, "group_id": group}:
            # Repair disk after a previous interrupted confirmation/rollback only
            # after proving these exact bytes are the currently loaded generation.
            atomic_write(self.directory / "nginx.conf", raw)
            return
        if self.retiring_workers():
            raise Busy("previous entry generation is still serving requests")
        versions = self.directory / "versions"
        versions.mkdir(exist_ok=True)
        filename = "versions/" + digest + ".conf"
        atomic_write(self.directory / filename, raw)
        self.validate(filename)
        active = self.directory / "nginx.conf"
        old = self.loaded_config(current)
        require_append_only_routes(old, raw)
        atomic_write(self.directory / "previous.conf", old)
        atomic_write(active, raw)
        result = self.compose("exec", "-T", "entry", "nginx", "-s", "reload", "-c", CONTAINER_DIRECTORY + "/nginx.conf")
        if result.returncode:
            atomic_write(self.directory / "last-error.txt", result.stderr.encode("utf-8", errors="replace"))
            # The signal tool failed: restore startup's last valid bytes, leave
            # any already-loaded workers untouched and report incomplete.
            atomic_write(active, old)
            raise Incomplete("entry reload signal failed")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.probe(key, timeout=min(5, max(0.001, deadline - time.monotonic()))) == {"config_digest": digest, "group_id": group}:
                    return
            except Incomplete:
                pass
            poll(0.1)
        # HUP may still complete: do not replace an unconfirmed live generation
        # or kill old workers. Retry derives state from disk plus actual probe.
        raise Incomplete("entry reload not confirmed")
