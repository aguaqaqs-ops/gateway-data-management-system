"""Runner-owned runtime context and harness capability dispatch.

SubjectHarness is a trusted in-process adapter. Public DTOs expose minimal
capability APIs (fault consume, clock now_iso). Module-private token tables
are runner dispatch only — not a security sandbox against reflection or imports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from typing import Any, Protocol

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.scenario.closure import ResolvedAsset, ScenarioClosure

_TOKEN_COUNTER = count(1)
_FAULT_BY_TOKEN: dict[int, Any] = {}
_CLOCK_BY_TOKEN: dict[int, Any] = {}


def _allocate_token() -> int:
    return next(_TOKEN_COUNTER)


def register_logical_clock(clock: LogicalClock) -> int:
    token = _allocate_token()
    _CLOCK_BY_TOKEN[token] = clock
    return token


def register_fault_channel(channel: FaultSideChannel) -> int:
    token = _allocate_token()
    _FAULT_BY_TOKEN[token] = channel
    return token


def unregister_run_tokens(
    *,
    clock_token: int | None,
    fault_token: int | None,
) -> None:
    if clock_token is not None:
        _CLOCK_BY_TOKEN.pop(clock_token, None)
    if fault_token is not None:
        _FAULT_BY_TOKEN.pop(fault_token, None)


def capability_token_registry_sizes() -> tuple[int, int]:
    """Test/diagnostic probe: (fault_entries, clock_entries). Not a security API."""
    return len(_FAULT_BY_TOKEN), len(_CLOCK_BY_TOKEN)


@dataclass(frozen=True, slots=True)
class RunCapabilityTokens:
    clock_token: int
    fault_token: int | None


@dataclass
class LogicalClock:
    """Injectable logical clock for deterministic runs."""

    _iso: str
    _ticks: int = 0

    def now_iso(self) -> str:
        return self._iso

    def tick(self) -> int:
        self._ticks += 1
        return self._ticks

    def advance_iso(self, iso: str) -> None:
        self._iso = iso


class ClockView:
    """Harness-visible clock: frozen ISO snapshot from run start (public API: now_iso only)."""

    __slots__ = ("__iso",)

    def __init__(self, iso: str) -> None:
        object.__setattr__(self, "_ClockView__iso", iso)

    def now_iso(self) -> str:
        return str(object.__getattribute__(self, "_ClockView__iso"))


@dataclass(frozen=True, slots=True)
class RunIdentity:
    run_id: str
    deterministic_seed: str


@dataclass(frozen=True, slots=True)
class ProfileView:
    profile: str
    provider_id: str | None


@dataclass
class ProfileHandle:
    """Runner-owned profile lifecycle controller."""

    profile: str
    provider_id: str | None
    provision_count: int = 0
    teardown_count: int = 0

    def provision(self) -> None:
        if self.provision_count > 0:
            raise ConformanceValidationError("profile already provisioned")
        self.provision_count += 1

    def teardown(self) -> None:
        if self.teardown_count > 0:
            raise ConformanceValidationError("profile teardown already executed")
        self.teardown_count += 1

    def view(self) -> ProfileView:
        return ProfileView(profile=self.profile, provider_id=self.provider_id)


class FaultSideChannel:
    """Runner-owned fault arm/consume state (not exposed on HarnessRuntimeContext)."""

    __slots__ = (
        "_FaultSideChannel__armed",
        "_FaultSideChannel__consumed",
        "_FaultSideChannel__arm_count",
        "_FaultSideChannel__consume_count",
    )

    def __init__(self) -> None:
        object.__setattr__(self, "_FaultSideChannel__armed", False)
        object.__setattr__(self, "_FaultSideChannel__consumed", False)
        object.__setattr__(self, "_FaultSideChannel__arm_count", 0)
        object.__setattr__(self, "_FaultSideChannel__consume_count", 0)

    @property
    def armed(self) -> bool:
        return bool(object.__getattribute__(self, "_FaultSideChannel__armed"))

    @property
    def consumed(self) -> bool:
        return bool(object.__getattribute__(self, "_FaultSideChannel__consumed"))

    @property
    def arm_count(self) -> int:
        return int(object.__getattribute__(self, "_FaultSideChannel__arm_count"))

    @property
    def consume_count(self) -> int:
        return int(object.__getattribute__(self, "_FaultSideChannel__consume_count"))

    def arm(self) -> None:
        if self.armed:
            raise ConformanceValidationError("fault already armed")
        object.__setattr__(self, "_FaultSideChannel__armed", True)
        object.__setattr__(
            self,
            "_FaultSideChannel__arm_count",
            self.arm_count + 1,
        )

    def consume(self) -> None:
        if not self.armed:
            raise ConformanceValidationError("fault not armed")
        if self.consumed:
            raise ConformanceValidationError("fault already consumed")
        object.__setattr__(self, "_FaultSideChannel__consumed", True)
        object.__setattr__(
            self,
            "_FaultSideChannel__consume_count",
            self.consume_count + 1,
        )

    def disarm(self) -> None:
        object.__setattr__(self, "_FaultSideChannel__armed", False)

    def receipt(self) -> dict[str, Any]:
        return {
            "armed": self.arm_count > 0,
            "consumed": self.consume_count > 0,
            "diagnostics": [],
        }


class FaultConsumeChannel(Protocol):
    def consume(self) -> None: ...


class FaultConsumeFacade:
    """Harness-visible fault API: consume() only (runner dispatch via internal token)."""

    __slots__ = ("__token",)

    def __init__(self, fault_token: int) -> None:
        object.__setattr__(self, "_FaultConsumeFacade__token", fault_token)

    def consume(self) -> None:
        token: int = object.__getattribute__(self, "_FaultConsumeFacade__token")
        channel = _FAULT_BY_TOKEN.get(token)
        if channel is None:
            raise ConformanceValidationError("fault channel unavailable")
        channel.consume()


class VerifiedAssetResolver:
    """Read-only resolver for declared closure assets only."""

    def __init__(self, assets: dict[str, ResolvedAsset]) -> None:
        self._assets = dict(assets)

    def read_bytes(self, logical_name: str) -> bytes:
        asset = self._assets.get(logical_name)
        if asset is None:
            raise ConformanceValidationError(f"unknown verified asset: {logical_name}")
        return asset.raw

    def metadata(self, logical_name: str) -> ResolvedAsset:
        asset = self._assets.get(logical_name)
        if asset is None:
            raise ConformanceValidationError(f"unknown verified asset: {logical_name}")
        return asset


@dataclass(frozen=True, slots=True)
class HarnessRuntimeContext:
    """Non-serializable per-run harness context."""

    identity: RunIdentity
    clock: ClockView
    profile: ProfileView
    resolver: VerifiedAssetResolver
    fault: FaultConsumeFacade | None
    _stable_read_barrier: Callable[[], None]

    def stable_read_barrier(self) -> None:
        self._stable_read_barrier()


def build_harness_context(
    *,
    identity: RunIdentity,
    clock: LogicalClock,
    profile: ProfileView,
    resolver: VerifiedAssetResolver,
    fault: FaultSideChannel | None,
    deadline_tick: int = 10_000,
) -> tuple[HarnessRuntimeContext, RunCapabilityTokens]:
    clock_token = register_logical_clock(clock)
    fault_token: int | None = None
    fault_facade: FaultConsumeFacade | None = None
    if fault is not None:
        fault_token = register_fault_channel(fault)
        fault_facade = FaultConsumeFacade(fault_token)

    def stable_read_barrier() -> None:
        logical = _CLOCK_BY_TOKEN.get(clock_token)
        if logical is None:
            raise ConformanceValidationError("logical clock unavailable")
        if logical.tick() > deadline_tick:
            raise ConformanceValidationError("stable-read deadline exceeded")

    context = HarnessRuntimeContext(
        identity=identity,
        clock=ClockView(clock.now_iso()),
        profile=profile,
        resolver=resolver,
        fault=fault_facade,
        _stable_read_barrier=stable_read_barrier,
    )
    tokens = RunCapabilityTokens(clock_token=clock_token, fault_token=fault_token)
    return context, tokens


def build_resolver(closure: ScenarioClosure) -> VerifiedAssetResolver:
    return VerifiedAssetResolver(closure.assets)
