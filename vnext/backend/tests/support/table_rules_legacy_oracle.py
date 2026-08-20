"""Legacy TableRuleRegistry oracle. Test support only; not a production import."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

_LEGACY_ROOT = Path(__file__).resolve().parents[4] / "legacy" / "backend_vnext"
_PACKAGE = "gateway_backend_tests_legacy_oracle"


@dataclass(frozen=True, slots=True)
class LegacyOracleDecision:
    static_role: str
    compare_key_mode: str | None
    compare_key_columns: tuple[str, ...]
    ignored_columns: frozenset[str]
    artifact_scope: str | None
    position_column: str | None
    stable_key_candidates: tuple[str, ...]


def legacy_oracle_decision(
    table_name: str,
    *,
    primary_key_columns: tuple[str, ...] = (),
) -> LegacyOracleDecision:
    registry = _legacy_registry()
    role = registry.classify_static_role(table_name)
    key_rule = registry.key_rule_for_table(table_name, primary_key_columns=primary_key_columns)
    if key_rule is None:
        return LegacyOracleDecision(
            static_role=str(role),
            compare_key_mode=None,
            compare_key_columns=(),
            ignored_columns=frozenset(),
            artifact_scope=None,
            position_column=None,
            stable_key_candidates=(),
        )
    return LegacyOracleDecision(
        static_role=str(role),
        compare_key_mode=str(key_rule.compare_key_mode),
        compare_key_columns=tuple(key_rule.compare_key_columns),
        ignored_columns=frozenset(key_rule.ignored_columns),
        artifact_scope=str(key_rule.artifact_scope),
        position_column=key_rule.position_column,
        stable_key_candidates=tuple(key_rule.stable_key_candidates),
    )


@cache
def _legacy_registry() -> Any:
    _namespace(_PACKAGE)
    _namespace(f"{_PACKAGE}.contracts")
    _namespace(f"{_PACKAGE}.core")
    _namespace(f"{_PACKAGE}.capabilities")
    _namespace(f"{_PACKAGE}.capabilities.table_rules")
    _load(f"{_PACKAGE}.contracts.versions", _LEGACY_ROOT / "contracts" / "versions.py")
    _load(f"{_PACKAGE}.core.identifiers", _LEGACY_ROOT / "core" / "identifiers.py")
    _load(
        f"{_PACKAGE}.capabilities.table_rules.models",
        _LEGACY_ROOT / "capabilities" / "table_rules" / "models.py",
    )
    _load(
        f"{_PACKAGE}.capabilities.table_rules.semantic",
        _LEGACY_ROOT / "capabilities" / "table_rules" / "semantic.py",
    )
    registry_module = _load(
        f"{_PACKAGE}.capabilities.table_rules.registry",
        _LEGACY_ROOT / "capabilities" / "table_rules" / "registry.py",
    )
    return registry_module.default_table_rule_registry()


def _namespace(name: str) -> None:
    if name in sys.modules:
        return
    module = ModuleType(name)
    module.__path__ = []
    sys.modules[name] = module


def _load(name: str, path: Path) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load legacy oracle module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
