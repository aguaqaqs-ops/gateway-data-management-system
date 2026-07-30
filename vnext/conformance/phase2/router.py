"""Versioned affected-scope router for Phase 2 gate selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.strict_yaml import loads_strict_yaml_bytes

INVENTORY_SCHEMA_ID = "gateway-vnext.affected-scope.v1"
INVENTORY_SCHEMA_VERSION = 1
INVENTORY_FILE_NAME = "affected-scope-v1.yaml"

KNOWN_GATES: frozenset[str] = frozenset(
    {
        "P2-PR-STATIC",
        "P2-PR-CONTRACT",
        "P2-PR-RECOVERY",
        "P2-PHASE-EXIT-CONTAINER",
        "PR-CORRECTNESS",
        "PR-NATIVE",
    }
)

EXPECTED_GATE_ACTIVATION: dict[str, str] = {
    "P2-PR-STATIC": "active",
    "P2-PR-CONTRACT": "inactive",
    "P2-PR-RECOVERY": "inactive",
    "P2-PHASE-EXIT-CONTAINER": "inactive",
    "PR-CORRECTNESS": "external",
    "PR-NATIVE": "external",
}

EXPECTED_GATE_OWNERS: dict[str, str] = {
    "P2-PR-STATIC": "phase2-conformance",
    "P2-PR-CONTRACT": "phase2-conformance",
    "P2-PR-RECOVERY": "phase2-conformance",
    "P2-PHASE-EXIT-CONTAINER": "phase2-deploy",
    "PR-CORRECTNESS": "phase1-correctness",
    "PR-NATIVE": "phase1-native",
}

EXTERNAL_GATES: frozenset[str] = frozenset({"PR-CORRECTNESS", "PR-NATIVE"})
INACTIVE_PHASE2_GATES: frozenset[str] = frozenset(
    {"P2-PR-CONTRACT", "P2-PR-RECOVERY", "P2-PHASE-EXIT-CONTAINER"}
)

ChangeStatus = Literal[
    "added",
    "modified",
    "deleted",
    "renamed",
    "copied",
    "type_changed",
]

_ACTIVATION_VALUES = frozenset({"active", "inactive", "external"})
_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_id",
        "schema_version",
        "gates",
        "rules",
        "unknown_path_gates",
        "empty_change_set_policy",
    }
)
_RULE_KEYS = frozenset({"id", "paths", "gates", "narrow"})
_GATE_KEYS = frozenset({"activation", "owner"})
_EMPTY_POLICY_VALUES = frozenset({"fail"})
_PATH_CHANGE_STATUSES = frozenset(
    {"added", "modified", "deleted", "renamed", "copied", "type_changed"}
)
_OLD_PATH_STATUSES = frozenset({"renamed", "copied"})


class RouterErrorCode(StrEnum):
    ABSOLUTE_PATH = "ABSOLUTE_PATH"
    CONFLICTING_RULE_PREFIX = "CONFLICTING_RULE_PREFIX"
    DUPLICATE_GATE = "DUPLICATE_GATE"
    DUPLICATE_RULE_ID = "DUPLICATE_RULE_ID"
    DUPLICATE_RULE_PATH = "DUPLICATE_RULE_PATH"
    EMPTY_CHANGE_SET = "EMPTY_CHANGE_SET"
    EMPTY_PATH = "EMPTY_PATH"
    INVALID_INVENTORY = "INVALID_INVENTORY"
    MALFORMED_COPY = "MALFORMED_COPY"
    MALFORMED_RENAME = "MALFORMED_RENAME"
    NONCANONICAL_PATH = "NONCANONICAL_PATH"
    PARENT_TRAVERSAL = "PARENT_TRAVERSAL"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    UNKNOWN_CHANGE_STATUS = "UNKNOWN_CHANGE_STATUS"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    UNKNOWN_GATE = "UNKNOWN_GATE"
    UNKNOWN_INVENTORY_FIELD = "UNKNOWN_INVENTORY_FIELD"
    UNSUPPORTED_SEPARATOR = "UNSUPPORTED_SEPARATOR"


class RouterError(ConformanceValidationError):
    """Routing failed with a stable closed error code."""

    def __init__(self, code: RouterErrorCode, *, detail: str = "") -> None:
        self.code = code
        message = code.value if not detail else f"{code.value}: {detail}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PathChange:
    path: str
    status: ChangeStatus
    old_path: str | None = None


@dataclass(frozen=True, slots=True)
class RoutingRule:
    rule_id: str
    paths: tuple[str, ...]
    gates: tuple[str, ...]
    narrow: bool


@dataclass(frozen=True, slots=True)
class Inventory:
    schema_id: str
    schema_version: int
    gates: tuple[tuple[str, str], ...]
    rules: tuple[RoutingRule, ...]
    unknown_path_gates: tuple[str, ...]
    empty_change_set_policy: str

    def gate_activation(self, gate: str) -> str:
        for gate_name, activation in self.gates:
            if gate_name == gate:
                return activation
        raise KeyError(gate)


@dataclass(frozen=True, slots=True)
class RoutingResult:
    schema_version: int
    selected_gates: tuple[str, ...]
    gate_activation: tuple[tuple[str, str], ...]
    diagnostics: tuple[str, ...]
    fail_closed: bool
    narrow_scope: bool
    pending_external_gates: tuple[str, ...]
    pending_inactive_gates: tuple[str, ...]


def default_inventory_path() -> Path:
    return Path(__file__).resolve().parent / INVENTORY_FILE_NAME


def load_inventory(path: Path | None = None) -> Inventory:
    inventory_path = path or default_inventory_path()
    raw = loads_strict_yaml_bytes(inventory_path.read_bytes())
    return parse_inventory(raw)


def _canonicalize_inventory_path(path: str) -> str:
    if path == "":
        raise RouterError(RouterErrorCode.EMPTY_PATH)
    if len(path) >= 3 and path[0].isalpha() and path[1] == ":" and path[2] == "/":
        raise RouterError(RouterErrorCode.ABSOLUTE_PATH)
    if path.startswith("/"):
        raise RouterError(RouterErrorCode.ABSOLUTE_PATH)
    if "\\" in path:
        raise RouterError(RouterErrorCode.UNSUPPORTED_SEPARATOR)
    if "\0" in path:
        raise RouterError(RouterErrorCode.NONCANONICAL_PATH, detail="nul")
    if path != path.strip():
        raise RouterError(RouterErrorCode.NONCANONICAL_PATH, detail="whitespace")
    if "//" in path:
        raise RouterError(RouterErrorCode.NONCANONICAL_PATH, detail="duplicate_slash")

    parts = [part for part in path.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise RouterError(RouterErrorCode.PARENT_TRAVERSAL)
    if not parts:
        raise RouterError(RouterErrorCode.EMPTY_PATH)
    return "/".join(parts)


def validate_repo_relative_path(path: str) -> str:
    canonical = _canonicalize_inventory_path(path)
    if path != canonical:
        raise RouterError(RouterErrorCode.NONCANONICAL_PATH, detail="not_canonical")
    return canonical


def validate_inventory_rule_prefix(path: str) -> str:
    if not isinstance(path, str):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="rule_path_type")
    trailing_slash = path.endswith("/")
    body = path[:-1] if trailing_slash else path
    if body == "":
        raise RouterError(RouterErrorCode.EMPTY_PATH)
    if body.startswith("./") or "/./" in body or body.endswith("/.") or body == ".":
        raise RouterError(RouterErrorCode.NONCANONICAL_PATH, detail="not_canonical")
    canonical_body = validate_repo_relative_path(body)
    if trailing_slash:
        return f"{canonical_body}/"
    return canonical_body


def _inventory_prefix_key(prefix: str) -> str:
    return prefix.rstrip("/")


def normalize_repo_relative_path(path: str) -> str:
    return _canonicalize_inventory_path(path)


def _parse_gate_list(
    value: object,
    *,
    label: str,
    known_gates: set[str],
    allow_empty: bool = False,
    allow_duplicates: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=label)
    if not value and not allow_empty:
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=label)

    gates: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=label)
        if item not in known_gates:
            raise RouterError(RouterErrorCode.UNKNOWN_GATE, detail=item)
        if not allow_duplicates and item in seen:
            raise RouterError(RouterErrorCode.DUPLICATE_GATE, detail=f"{label}:{item}")
        seen.add(item)
        gates.append(item)
    return tuple(sorted(gates))


def _validate_rule_prefixes(rules: tuple[RoutingRule, ...]) -> None:
    path_owner: dict[str, str] = {}
    for rule in rules:
        for prefix in rule.paths:
            prefix_key = _inventory_prefix_key(prefix)
            if prefix_key in path_owner:
                raise RouterError(
                    RouterErrorCode.DUPLICATE_RULE_PATH,
                    detail=f"{path_owner[prefix_key]}:{rule.rule_id}:{prefix}",
                )
            path_owner[prefix_key] = rule.rule_id


def _validate_prefix_gate_monotonicity(rules: tuple[RoutingRule, ...]) -> None:
    indexed: list[tuple[str, frozenset[str], str]] = [
        (_inventory_prefix_key(prefix), frozenset(rule.gates), rule.rule_id)
        for rule in rules
        for prefix in rule.paths
    ]
    for left_prefix, left_gates, left_rule_id in indexed:
        for right_prefix, right_gates, right_rule_id in indexed:
            if left_prefix == right_prefix:
                continue
            if right_prefix.startswith(f"{left_prefix}/"):
                if not left_gates <= right_gates:
                    raise RouterError(
                        RouterErrorCode.CONFLICTING_RULE_PREFIX,
                        detail=f"{left_rule_id}:{right_rule_id}:{left_prefix}:{right_prefix}",
                    )
            elif left_prefix.startswith(f"{right_prefix}/"):
                if not right_gates <= left_gates:
                    raise RouterError(
                        RouterErrorCode.CONFLICTING_RULE_PREFIX,
                        detail=f"{right_rule_id}:{left_rule_id}:{right_prefix}:{left_prefix}",
                    )


def parse_inventory(raw: Any) -> Inventory:
    if not isinstance(raw, dict):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="root")
    unknown_top = set(raw) - _TOP_LEVEL_KEYS
    if unknown_top:
        raise RouterError(
            RouterErrorCode.UNKNOWN_INVENTORY_FIELD,
            detail=",".join(sorted(unknown_top)),
        )

    schema_id = raw.get("schema_id")
    if schema_id != INVENTORY_SCHEMA_ID:
        raise RouterError(RouterErrorCode.SCHEMA_MISMATCH, detail="schema_id")

    schema_version = raw.get("schema_version")
    if schema_version != INVENTORY_SCHEMA_VERSION:
        raise RouterError(RouterErrorCode.SCHEMA_MISMATCH, detail="schema_version")

    gates_raw = raw.get("gates")
    if not isinstance(gates_raw, dict) or not gates_raw:
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="gates")

    if set(gates_raw) != set(KNOWN_GATES):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="gate_registry")

    gate_items: list[tuple[str, str]] = []
    for gate_name in sorted(gates_raw):
        gate_entry = gates_raw[gate_name]
        if not isinstance(gate_entry, dict):
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=f"gate:{gate_name}")
        unknown_gate_fields = set(gate_entry) - _GATE_KEYS
        if unknown_gate_fields:
            raise RouterError(
                RouterErrorCode.UNKNOWN_INVENTORY_FIELD,
                detail=",".join(sorted(unknown_gate_fields)),
            )
        activation = gate_entry.get("activation")
        if activation not in _ACTIVATION_VALUES:
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=f"activation:{gate_name}")
        expected_activation = EXPECTED_GATE_ACTIVATION[gate_name]
        if activation != expected_activation:
            raise RouterError(
                RouterErrorCode.INVALID_INVENTORY,
                detail=f"activation_mismatch:{gate_name}",
            )
        owner = gate_entry.get("owner")
        if not isinstance(owner, str) or not owner:
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=f"owner:{gate_name}")
        expected_owner = EXPECTED_GATE_OWNERS[gate_name]
        if owner != expected_owner:
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=f"owner_mismatch:{gate_name}")
        gate_items.append((gate_name, str(activation)))

    unknown_path_gates = _parse_gate_list(
        raw.get("unknown_path_gates"),
        label="unknown_path_gates",
        known_gates=set(KNOWN_GATES),
    )
    if set(unknown_path_gates) != set(KNOWN_GATES):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="unknown_path_gates")

    empty_policy = raw.get("empty_change_set_policy")
    if empty_policy not in _EMPTY_POLICY_VALUES:
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="empty_change_set_policy")

    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="rules")

    rules: list[RoutingRule] = []
    seen_rule_ids: set[str] = set()
    for entry in rules_raw:
        if not isinstance(entry, dict):
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="rule")
        unknown_rule_fields = set(entry) - _RULE_KEYS
        if unknown_rule_fields:
            raise RouterError(
                RouterErrorCode.UNKNOWN_INVENTORY_FIELD,
                detail=",".join(sorted(unknown_rule_fields)),
            )
        rule_id = entry.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="rule.id")
        if rule_id in seen_rule_ids:
            raise RouterError(RouterErrorCode.DUPLICATE_RULE_ID, detail=rule_id)
        seen_rule_ids.add(rule_id)

        paths_raw = entry.get("paths")
        if not isinstance(paths_raw, list) or not paths_raw:
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=f"paths:{rule_id}")
        normalized_paths: list[str] = []
        for path in paths_raw:
            if not isinstance(path, str):
                raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=f"paths:{rule_id}")
            normalized_paths.append(validate_inventory_rule_prefix(path))
        paths = tuple(sorted(normalized_paths))

        gates_list = _parse_gate_list(
            entry.get("gates"),
            label=f"rule:{rule_id}",
            known_gates=set(KNOWN_GATES),
            allow_empty=True,
        )

        if "narrow" not in entry:
            narrow = False
        elif not isinstance(entry["narrow"], bool):
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail=f"narrow:{rule_id}")
        else:
            narrow = entry["narrow"]

        rules.append(
            RoutingRule(
                rule_id=rule_id,
                paths=paths,
                gates=gates_list,
                narrow=narrow,
            )
        )

    rules_sorted = tuple(sorted(rules, key=lambda rule: rule.rule_id))
    _validate_rule_prefixes(rules_sorted)
    _validate_prefix_gate_monotonicity(rules_sorted)
    return Inventory(
        schema_id=INVENTORY_SCHEMA_ID,
        schema_version=INVENTORY_SCHEMA_VERSION,
        gates=tuple(gate_items),
        rules=rules_sorted,
        unknown_path_gates=unknown_path_gates,
        empty_change_set_policy=str(empty_policy),
    )


def _validate_change_status(status: str) -> ChangeStatus:
    if status not in _PATH_CHANGE_STATUSES:
        raise RouterError(RouterErrorCode.UNKNOWN_CHANGE_STATUS, detail=status)
    return status  # type: ignore[return-value]


def _normalize_changes(changes: list[PathChange]) -> tuple[PathChange, ...]:
    deduped: dict[tuple[str, str, str], PathChange] = {}
    for change in changes:
        status = _validate_change_status(change.status)
        path = validate_repo_relative_path(change.path)
        old_path = change.old_path

        if status in _OLD_PATH_STATUSES:
            if old_path is None:
                code = (
                    RouterErrorCode.MALFORMED_COPY
                    if status == "copied"
                    else RouterErrorCode.MALFORMED_RENAME
                )
                raise RouterError(code, detail="missing_old_path")
            normalized_old = validate_repo_relative_path(old_path)
            if normalized_old == path:
                raise RouterError(
                    RouterErrorCode.MALFORMED_RENAME
                    if status == "renamed"
                    else RouterErrorCode.MALFORMED_COPY,
                    detail="same_path",
                )
            old_key = normalized_old
        else:
            if old_path is not None:
                raise RouterError(RouterErrorCode.MALFORMED_RENAME, detail="unexpected_old_path")
            old_key = ""

        key = (status, path, old_key)
        deduped[key] = PathChange(path=path, status=status, old_path=old_key or None)

    return tuple(
        sorted(
            deduped.values(),
            key=lambda item: (item.path, item.status, item.old_path or ""),
        )
    )


def _paths_for_change(change: PathChange) -> tuple[str, ...]:
    if change.status in _OLD_PATH_STATUSES:
        assert change.old_path is not None
        return (change.old_path, change.path)
    return (change.path,)


def _longest_prefix_match(path: str, rule: RoutingRule) -> int:
    best = 0
    for prefix in rule.paths:
        normalized_prefix = _inventory_prefix_key(prefix)
        if path == normalized_prefix or path.startswith(f"{normalized_prefix}/"):
            best = max(best, len(normalized_prefix))
    return best


def _matching_rules(path: str, rules: tuple[RoutingRule, ...]) -> tuple[RoutingRule, ...]:
    scored: list[tuple[int, RoutingRule]] = []
    for rule in rules:
        match_len = _longest_prefix_match(path, rule)
        if match_len > 0:
            scored.append((match_len, rule))
    if not scored:
        return ()
    best_len = max(match_len for match_len, _ in scored)
    return tuple(
        sorted(
            (rule for match_len, rule in scored if match_len == best_len),
            key=lambda rule: rule.rule_id,
        )
    )


def _gates_for_path(
    path: str,
    inventory: Inventory,
) -> tuple[tuple[str, ...], bool, str]:
    matches = _matching_rules(path, inventory.rules)
    if not matches:
        return inventory.unknown_path_gates, True, f"unknown_path:{path}"
    if any(rule.narrow for rule in matches):
        narrow_rules = tuple(rule for rule in matches if rule.narrow)
        narrow_rule_ids = ",".join(rule.rule_id for rule in narrow_rules)
        narrow_gates: set[str] = set()
        for rule in narrow_rules:
            narrow_gates.update(rule.gates)
        return tuple(sorted(narrow_gates)), False, f"narrow_rule:{narrow_rule_ids}:{path}"
    matched_gates: set[str] = set()
    matched_rule_ids: list[str] = []
    for rule in matches:
        matched_rule_ids.append(rule.rule_id)
        matched_gates.update(rule.gates)
    return tuple(sorted(matched_gates)), False, f"rule:{','.join(matched_rule_ids)}:{path}"


def _activation_map(inventory: Inventory) -> dict[str, str]:
    return dict(inventory.gates)


def _pending_gates(
    selected_gates: tuple[str, ...],
    activation_map: dict[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    external = tuple(
        sorted(gate for gate in selected_gates if activation_map.get(gate) == "external")
    )
    inactive = tuple(
        sorted(gate for gate in selected_gates if activation_map.get(gate) == "inactive")
    )
    return external, inactive


def route_changes(
    changes: list[PathChange],
    inventory: Inventory | None = None,
) -> RoutingResult:
    inv = inventory or load_inventory()
    activation_map = _activation_map(inv)

    if not changes:
        if inv.empty_change_set_policy == "fail":
            raise RouterError(RouterErrorCode.EMPTY_CHANGE_SET)
        return RoutingResult(
            schema_version=inv.schema_version,
            selected_gates=(),
            gate_activation=(),
            diagnostics=("empty_change_set",),
            fail_closed=False,
            narrow_scope=False,
            pending_external_gates=(),
            pending_inactive_gates=(),
        )

    normalized = _normalize_changes(changes)
    selected: set[str] = set()
    diagnostics: list[str] = []
    fail_closed = False
    narrow_hits = 0
    non_narrow_hits = 0

    for change in normalized:
        for path in _paths_for_change(change):
            gates, path_fail_closed, diagnostic = _gates_for_path(path, inv)
            diagnostics.append(diagnostic)
            if path_fail_closed:
                fail_closed = True
            if gates:
                non_narrow_hits += 1
                selected.update(gates)
            else:
                narrow_hits += 1

    narrow_scope = narrow_hits > 0 and non_narrow_hits == 0 and not fail_closed
    selected_sorted = tuple(sorted(selected))
    gate_activation = tuple(
        sorted((gate, activation_map[gate]) for gate in selected_sorted if gate in activation_map)
    )
    pending_external, pending_inactive = _pending_gates(selected_sorted, activation_map)
    return RoutingResult(
        schema_version=inv.schema_version,
        selected_gates=selected_sorted,
        gate_activation=gate_activation,
        diagnostics=tuple(sorted(diagnostics)),
        fail_closed=fail_closed,
        narrow_scope=narrow_scope,
        pending_external_gates=pending_external,
        pending_inactive_gates=pending_inactive,
    )


def routing_view_to_dict(routing: RoutingResult) -> dict[str, Any]:
    return {
        "schema_version": routing.schema_version,
        "selected_gates": list(routing.selected_gates),
        "gate_activation": dict(routing.gate_activation),
        "diagnostics": list(routing.diagnostics),
        "fail_closed": routing.fail_closed,
        "narrow_scope": routing.narrow_scope,
        "pending_external_gates": list(routing.pending_external_gates),
        "pending_inactive_gates": list(routing.pending_inactive_gates),
    }
