"""One-shot group maintenance preserves the distinction between workers and writers."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def maintenance() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location("group_maintenance", SCRIPTS / "manage-worker-group.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def _group() -> dict[str, dict[str, Any]]:
    return {service: {"Id": service, "Config": {"Labels": {"com.docker.compose.service": service}},
        "State": {"Status": "running", "Running": True, "Pid": 1, "ExitCode": 0,
                  "Health": {"Status": "healthy"}},
        "HostConfig": {"PortBindings": {"8000/tcp": [{"HostPort": "8000"}]}}}
        for service in ("backend", "repository-service", "worker", "worker-2")}


def test_group_validation_uses_actual_configuration_binds_and_exact_project_services(maintenance: ModuleType) -> None:
    fixture = SCRIPTS.parent / "fixtures/runtime-config/v1"
    storage, resources = fixture / "storage-layout.json", fixture / "resource-profile.json"
    config = maintenance.DeploymentConfig.load(storage, resources)
    group = _group()
    del group["worker-2"]
    for service, container in group.items():
        container["Config"]["Labels"].update({"com.docker.compose.project": "ours",
            "com.docker.compose.container-number": "1", "com.docker.compose.oneoff": "False"})
        container["Mounts"] = [{"Destination": target, "Source": str(source), "Type": "bind", "RW": False}
            for target, source in (("/run/gateway/storage-layout.json", storage),
                                   ("/run/gateway/resource-profile.json", resources))]
        if service == "worker":
            profile = config.resources.worker
            container["Config"]["Env"] = ["GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX=1"]
            container["Image"] = "sha256:fixed-worker"
            container["HostConfig"].update(Memory=profile.memory_envelope_bytes,
                MemorySwap=profile.memory_envelope_bytes + profile.swap_limit_bytes,
                NanoCpus=round(profile.cpu_limit * 1_000_000_000), RestartPolicy={"Name": "no"})
    assert set(maintenance.validate_group(config, "ours", list(group.values()))) == set(group)
    group["backend"]["Mounts"][0]["RW"] = True
    with pytest.raises(ValueError, match="read-only bind"):
        maintenance.validate_group(config, "ours", list(group.values()))


@pytest.mark.parametrize("payload", [b"private\ncredential", b"\xffprivate", b""])
def test_invalid_credential_diagnostics_do_not_include_file_contents(
    maintenance: ModuleType, tmp_path: Path, payload: bytes,
) -> None:
    path = tmp_path / "token"
    path.write_bytes(payload)
    with pytest.raises(ValueError) as raised:
        maintenance.read_token(path)
    assert str(raised.value) in {"invalid credential file", "unreadable credential file"}


@pytest.mark.parametrize("command", ["drain", "stop-group"])
def test_group_shutdown_closes_admission_before_workers_and_stops_callers_before_rs(
    maintenance: ModuleType, monkeypatch: pytest.MonkeyPatch, command: str,
) -> None:
    from types import SimpleNamespace
    config = SimpleNamespace(resources=SimpleNamespace(worker=SimpleNamespace(count=2)))
    events: list[object] = []
    group = _group()
    monkeypatch.setattr(maintenance, "inspect_project", lambda project: [])
    monkeypatch.setattr(maintenance, "validate_group", lambda *args: group)
    monkeypatch.setattr(maintenance, "close_admission", lambda *args: events.append("closed-and-drained"))
    monkeypatch.setattr(maintenance, "stop_services", lambda items: events.append([item["Id"] for item in items]))
    monkeypatch.setattr(maintenance, "assert_business_settled", lambda config: events.append("settled"))
    result = maintenance.manage(command, config, "ours", "http://127.0.0.1:8000", "private")
    assert events[:2] == ["closed-and-drained", ["worker", "worker-2"]]
    if command == "drain":
        assert len(events) == 2
        assert "not quiescent" in result
    else:
        assert events[2:] == ["settled", ["backend"], ["repository-service"]]


def test_unsettled_business_keeps_backend_and_rs_for_original_request_recovery(
    maintenance: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    events: list[object] = []
    group = _group()
    monkeypatch.setattr(maintenance, "inspect_project", lambda project: [])
    monkeypatch.setattr(maintenance, "validate_group", lambda *args: group)
    monkeypatch.setattr(maintenance, "close_admission", lambda *args: events.append("closed"))
    monkeypatch.setattr(maintenance, "stop_services", lambda items: events.append([item["Id"] for item in items]))
    def unsettled(config: object) -> None:
        raise ValueError("unsettled external effects")
    monkeypatch.setattr(maintenance, "assert_business_settled", unsettled)
    config = SimpleNamespace(resources=SimpleNamespace(worker=SimpleNamespace(count=2)))
    with pytest.raises(ValueError, match="unsettled"):
        maintenance.manage("stop-group", config, "ours", "http://127.0.0.1:8000", "private")
    assert events == ["closed", ["worker", "worker-2"]]


def test_term_timeout_preserves_running_instances_without_kill_or_restart(
    maintenance: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    group = _group()
    calls: list[tuple[str, ...]] = []
    workers = [group["worker"], group["worker-2"]]
    def docker(*args: str) -> str:
        calls.append(args)
        return json.dumps(workers) if args[0] == "inspect" else ""
    ticks = iter((0, 181))
    monkeypatch.setattr(maintenance, "_docker", docker)
    monkeypatch.setattr(maintenance, "_cgroup", lambda item: tmp_path)
    monkeypatch.setattr(maintenance.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ValueError, match="still active, no KILL sent: worker,worker-2"):
        maintenance.stop_services(workers)
    assert calls == [("kill", "--signal", "TERM", "worker", "worker-2"), ("inspect", "worker", "worker-2")]


def test_stopped_container_requires_empty_cgroup_and_successful_exit(
    maintenance: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    worker = _group()["worker"]
    worker["State"].update(Status="exited", Running=False, Pid=0)
    (tmp_path / "cgroup.events").write_text("populated 1\nfrozen 0\n")
    assert not maintenance._empty(tmp_path)
    (tmp_path / "cgroup.events").write_text("populated 0\nfrozen 0\n")
    monkeypatch.setattr(maintenance, "_cgroup", lambda item: tmp_path)
    monkeypatch.setattr(maintenance, "_docker", lambda *args: json.dumps([worker]))
    maintenance.stop_services([worker])
    worker["State"]["ExitCode"] = 1
    with pytest.raises(ValueError, match="abnormal exit"):
        maintenance.stop_services([worker])


def test_recovery_starts_only_original_stopped_containers_after_closed_gate_and_rs_ready(
    maintenance: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from types import SimpleNamespace
    config = SimpleNamespace(resources=SimpleNamespace(worker=SimpleNamespace(count=2)))
    group = _group()
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(maintenance, "inspect_project", lambda project: [])
    monkeypatch.setattr(maintenance, "validate_group", lambda *args: group)
    monkeypatch.setattr(maintenance, "drain_request", lambda *args: {"accepting_new_work": False, "in_flight": 0})
    monkeypatch.setattr(maintenance, "_cgroup", lambda item: tmp_path / "absent")
    monkeypatch.setattr(maintenance, "_docker", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="fully stopped"):
        maintenance.manage("start-recovery", config, "ours", "http://127.0.0.1:8000", "private")
    assert not calls
    for service in ("worker", "worker-2"):
        group[service]["State"].update(Status="exited", Running=False, Pid=0)
    assert "not quiescent" in maintenance.manage("start-recovery", config, "ours", "http://127.0.0.1:8000", "private")
    assert calls == [("start", "worker", "worker-2")]


def test_admission_wait_observes_existing_requests_without_reopening(
    maintenance: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = iter(({"accepting_new_work": False, "in_flight": 1},
                      {"accepting_new_work": False, "in_flight": 0}))
    methods: list[bool] = []
    def request(url: str, token: str, *, close: bool = False) -> dict[str, Any]:
        methods.append(close)
        return next(snapshots)
    monkeypatch.setattr(maintenance, "drain_request", request)
    monkeypatch.setattr(maintenance.time, "sleep", lambda seconds: None)
    maintenance.close_admission("http://127.0.0.1:8000", "private")
    assert methods == [True, False]


@pytest.mark.parametrize(("service", "was_running", "exit_code", "oom", "error", "accepted"), [
    ("repository-service", True, 143, False, "", True),
    ("repository-service", True, 0, False, "", True),
    ("repository-service", False, 143, False, "", False),
    ("repository-service", True, 1, False, "", False),
    ("repository-service", True, 137, False, "", False),
    ("repository-service", True, 143, True, "", False),
    ("repository-service", True, 143, False, "daemon error", False),
    ("backend", True, 143, False, "", False),
    ("worker", True, 143, False, "", False),
])
def test_controlled_rs_term_exit_requires_signalled_role_and_complete_exit(
    maintenance: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    service: str, was_running: bool, exit_code: int, oom: bool, error: str, accepted: bool,
) -> None:
    from copy import deepcopy
    original = _group()[service]
    if not was_running:
        original["State"].update(Status="exited", Running=False, Pid=0, ExitCode=exit_code)
    stopped = deepcopy(original)
    stopped["State"].update(Status="exited", Running=False, Pid=0,
                            ExitCode=exit_code, OOMKilled=oom, Error=error)
    calls: list[tuple[str, ...]] = []
    def docker(*args: str) -> str:
        calls.append(args)
        return json.dumps([stopped]) if args[0] == "inspect" else ""
    monkeypatch.setattr(maintenance, "_cgroup", lambda item: tmp_path / "absent")
    monkeypatch.setattr(maintenance, "_docker", docker)
    if accepted:
        maintenance.stop_services([original])
    else:
        with pytest.raises(ValueError, match="abnormal exit"):
            maintenance.stop_services([original])
    assert (("kill", "--signal", "TERM", service) in calls) is was_running
    assert all(call[0] in {"kill", "inspect"} for call in calls)


def test_rs_term_exit_keeps_waiting_for_child_cgroup_and_never_escalates(
    maintenance: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from copy import deepcopy
    original = _group()["repository-service"]
    stopped = deepcopy(original)
    stopped["State"].update(Status="exited", Running=False, Pid=0, ExitCode=143)
    (tmp_path / "cgroup.events").write_text("populated 1\nfrozen 0\n")
    calls: list[tuple[str, ...]] = []
    def docker(*args: str) -> str:
        calls.append(args)
        return json.dumps([stopped]) if args[0] == "inspect" else ""
    ticks = iter((0, 181))
    monkeypatch.setattr(maintenance, "time", type("Clock", (), {"monotonic": staticmethod(lambda: next(ticks))}))
    monkeypatch.setattr(maintenance, "_cgroup", lambda item: tmp_path)
    monkeypatch.setattr(maintenance, "_docker", docker)
    with pytest.raises(ValueError, match="still active, no KILL sent: repository-service"):
        maintenance.stop_services([original])
    assert calls == [("kill", "--signal", "TERM", "repository-service"), ("inspect", "repository-service")]
