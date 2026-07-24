"""Shared helpers for runner contract tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.registry import SubjectHarnessRegistry, SubjectKey
from tests.support import (
    build_valid_command_scenario,
    build_valid_data_scenario,
    build_valid_recovery_scenario,
    build_valid_structured_input_scenario,
)


def default_env_versions() -> list[dict[str, str]]:
    return [{"component": "gateway-conformance", "version": "0.1.0-test"}]


def test_capability_key(*, track: str = "data") -> SubjectKey:
    return SubjectKey(track=track, subject_kind="capability", subject_name="test-capability")


def scenario_root(
    tmp_path: Path,
    *,
    track: str = "data",
    scenario_suffix: str = "minimal",
) -> Path:
    return tmp_path / track / "test-capability" / scenario_suffix


def build_data_scenario(tmp_path: Path) -> Path:
    root = scenario_root(tmp_path)
    build_valid_data_scenario(root)
    return root


def build_command_scenario(tmp_path: Path) -> Path:
    root = scenario_root(tmp_path, track="command", scenario_suffix="submit")
    build_valid_command_scenario(root)
    return root


def build_recovery_scenario(tmp_path: Path) -> Path:
    root = scenario_root(tmp_path, track="recovery", scenario_suffix="timeout-success")
    build_valid_recovery_scenario(root)
    return root


def build_structured_input_scenario(tmp_path: Path) -> Path:
    root = scenario_root(tmp_path, scenario_suffix="structured-input")
    build_valid_structured_input_scenario(root)
    return root


def register_fake_harness(
    registry: SubjectHarnessRegistry,
    *,
    track: str = "data",
    factory: Callable[[], FakeSubjectHarness] | None = None,
) -> None:
    key = test_capability_key(track=track)
    if factory is None:
        registry.register(key, FakeSubjectHarness)
    else:
        registry.register(key, factory)
