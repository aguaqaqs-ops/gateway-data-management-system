"""Public contracts owned by the Table Rules capability.

Owner: Table Rules capability
Authority: docs/backend-vnext/refactoring/formal/plans/p3-r4-storage-projection-handoff.md

This module owns the immutable TableRulesetSnapshot injection surface used by
source materialization and the R4 two-layer rule document. Projection and
package publication remain later R4 steps. Downstream consumers may import
this module only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from gateway_shared_kernel import DigestRef, canonicalize_identifier
from gateway_shared_kernel.jcs import canonicalize_json_value

TABLE_RULESET_VERSION = 1
RULESET_ID = "backend-vnext/table-ruleset"
RULESET_VERSION = "v3"
TABLE_RULESET_CONTRACT_VERSION = "gateway-vnext.table-ruleset:v1"
STORAGE_PROJECTION_VERSION = "3"
FALLBACK_SELECTOR_VALUE = "*"
ORDERED_POSITION_COLUMN = "no"
ORDERED_IDENTITY_COLUMN = "gid"
_PAIRED_QUOTES = frozenset({"'", '"', "`"})
_DOCUMENT_TOP_LEVEL_KEYS = frozenset(
    {
        "contract_version",
        "rules",
        "ruleset_id",
        "ruleset_version",
        "storage_projection_version",
        "table_ruleset_version",
    }
)
_SELECTOR_KEYS = frozenset({"kind", "value"})
_DROPPED_COLUMN_KEYS = frozenset({"name", "reason"})
_RULE_RECORD_KEYS = frozenset(
    {
        "artifact_scope",
        "canonical_key_policy",
        "compare_key_columns",
        "compare_key_mode",
        "compare_excluded_columns",
        "dropped_columns",
        "ignored_columns",
        "ordered_policy",
        "position_column",
        "precedence_class",
        "selector",
        "stable_key_candidates",
        "static_role",
        "structural_columns",
        "table_storage",
    }
)


class TableRuleSelectorKind(StrEnum):
    EXACT = "EXACT"
    REGEX = "REGEX"
    FALLBACK = "FALLBACK"


class TableStaticRole(StrEnum):
    SKIP = "SKIP"
    SNAPSHOT_ONLY = "SNAPSHOT_ONLY"
    BROWSE_ONLY = "BROWSE_ONLY"
    STANDARD_DIFF = "STANDARD_DIFF"
    ORDERED_DIFF = "ORDERED_DIFF"


class TableCompareKeyMode(StrEnum):
    RAW_PRIMARY_KEY = "RAW_PRIMARY_KEY"
    EXPLICIT_KEY = "EXPLICIT_KEY"
    ORDERED_STABLE_KEY = "ORDERED_STABLE_KEY"


class TableArtifactScope(StrEnum):
    ALL_CHANGES = "ALL_CHANGES"
    UPDATE_ONLY = "UPDATE_ONLY"
    ORDERED_SEMANTIC = "ORDERED_SEMANTIC"


class SelectorPrecedenceClass(StrEnum):
    SKIP = "SKIP"
    SNAPSHOT_ONLY = "SNAPSHOT_ONLY"
    BROWSE_ONLY = "BROWSE_ONLY"
    ORDERED_DIFF = "ORDERED_DIFF"
    STANDARD_EXACT = "STANDARD_EXACT"
    STANDARD_DEVICE_CFG = "STANDARD_DEVICE_CFG"
    STANDARD_PROTOCOL_OPTION = "STANDARD_PROTOCOL_OPTION"
    STANDARD_PROTOCOL_DEVICE = "STANDARD_PROTOCOL_DEVICE"
    STANDARD_RAW_PK_FALLBACK = "STANDARD_RAW_PK_FALLBACK"


class StorageColumnPolicy(StrEnum):
    PERSIST_BUSINESS = "PERSIST_BUSINESS"
    RETAIN_FOR_STRUCTURE = "RETAIN_FOR_STRUCTURE"
    DROP_FROM_STORAGE = "DROP_FROM_STORAGE"


class CanonicalKeyPolicy(StrEnum):
    NONE = "NONE"
    EXPLICIT = "EXPLICIT"
    DDL_PRIMARY_KEY = "DDL_PRIMARY_KEY"
    DDL_PRIMARY_KEY_OR_KEYLESS = "DDL_PRIMARY_KEY_OR_KEYLESS"
    EXPLICIT_KEYLESS = "EXPLICIT_KEYLESS"


class OrderedPolicy(StrEnum):
    NONE = "NONE"
    GID_NO_V1 = "GID_NO_V1"


class TableStorageDisposition(StrEnum):
    OMIT = "OMIT"
    PROJECT = "PROJECT"


class ComparisonRole(StrEnum):
    STANDARD = "STANDARD"
    ORDERED = "ORDERED"
    BROWSE_ONLY = "BROWSE_ONLY"
    SNAPSHOT_ONLY = "SNAPSHOT_ONLY"


_PRECEDENCE_ROLES: dict[SelectorPrecedenceClass, TableStaticRole] = {
    SelectorPrecedenceClass.SKIP: TableStaticRole.SKIP,
    SelectorPrecedenceClass.SNAPSHOT_ONLY: TableStaticRole.SNAPSHOT_ONLY,
    SelectorPrecedenceClass.BROWSE_ONLY: TableStaticRole.BROWSE_ONLY,
    SelectorPrecedenceClass.ORDERED_DIFF: TableStaticRole.ORDERED_DIFF,
    SelectorPrecedenceClass.STANDARD_EXACT: TableStaticRole.STANDARD_DIFF,
    SelectorPrecedenceClass.STANDARD_DEVICE_CFG: TableStaticRole.STANDARD_DIFF,
    SelectorPrecedenceClass.STANDARD_PROTOCOL_OPTION: TableStaticRole.STANDARD_DIFF,
    SelectorPrecedenceClass.STANDARD_PROTOCOL_DEVICE: TableStaticRole.STANDARD_DIFF,
    SelectorPrecedenceClass.STANDARD_RAW_PK_FALLBACK: TableStaticRole.STANDARD_DIFF,
}


def canonicalize_rule_identifier(identifier: str) -> str:
    if type(identifier) is not str:
        raise ValueError("identifier must be a string")
    stripped = identifier.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in _PAIRED_QUOTES:
        stripped = stripped[1:-1].strip()
    if stripped == "":
        raise ValueError("identifier must not be empty")
    return canonicalize_identifier(stripped)


def legacy_ignored_column_reason(selector: TableRuleSelector) -> str:
    return f"legacy_ignored_column:{selector.identity_value}"


@dataclass(frozen=True, slots=True)
class TableRuleSelector:
    kind: TableRuleSelectorKind
    value: str

    def __post_init__(self) -> None:
        if type(self.kind) is not TableRuleSelectorKind:
            raise ValueError("kind must be TableRuleSelectorKind")
        if type(self.value) is not str or self.value == "":
            raise ValueError("selector value must be a non-empty string")
        _reject_path_shaped(self.value, "selector")
        if self.kind is TableRuleSelectorKind.EXACT:
            object.__setattr__(self, "value", canonicalize_rule_identifier(self.value))
            return
        if self.kind is TableRuleSelectorKind.REGEX:
            return
        if self.value != FALLBACK_SELECTOR_VALUE:
            raise ValueError("fallback selector value must be *")

    @property
    def identity_value(self) -> str:
        return self.value

    def canonical_serialization(self) -> str:
        if self.kind is TableRuleSelectorKind.EXACT:
            return f"exact:{self.value}"
        if self.kind is TableRuleSelectorKind.REGEX:
            return f"regex:{self.value}"
        return f"fallback:{FALLBACK_SELECTOR_VALUE}"


@dataclass(frozen=True, slots=True)
class DroppedColumn:
    name: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", canonicalize_rule_identifier(self.name))
        if type(self.reason) is not str or self.reason == "":
            raise ValueError("dropped column reason must be a non-empty string")
        _reject_path_shaped(self.reason, "dropped column reason")


@dataclass(frozen=True, slots=True)
class TableCompareKey:
    canonical_table: str
    key_columns: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_table", canonicalize_rule_identifier(self.canonical_table))
        if type(self.key_columns) is not tuple:
            raise ValueError("key_columns must be a tuple")
        if not self.key_columns:
            raise ValueError("key_columns must not be empty")
        canonical_columns = tuple(canonicalize_rule_identifier(column) for column in self.key_columns)
        _reject_duplicate_names(canonical_columns, "key_columns")
        object.__setattr__(self, "key_columns", canonical_columns)


@dataclass(frozen=True, slots=True)
class LegacyRuleDecision:
    selector: TableRuleSelector
    static_role: TableStaticRole
    compare_key_mode: TableCompareKeyMode | None = None
    compare_key_columns: tuple[str, ...] = ()
    ignored_columns: tuple[str, ...] = ()
    compare_excluded_columns: tuple[str, ...] = ()
    artifact_scope: TableArtifactScope | None = None
    position_column: str | None = None
    stable_key_candidates: tuple[str, ...] = ()
    pseudo_key_start: int = 2_000_000_000

    def __post_init__(self) -> None:
        if type(self.selector) is not TableRuleSelector:
            raise ValueError("selector must be TableRuleSelector")
        if type(self.static_role) is not TableStaticRole:
            raise ValueError("static_role must be TableStaticRole")
        object.__setattr__(self, "compare_key_columns", _canonical_name_tuple(self.compare_key_columns, "compare_key_columns"))
        object.__setattr__(self, "ignored_columns", _canonical_name_tuple(self.ignored_columns, "ignored_columns"))
        object.__setattr__(
            self,
            "compare_excluded_columns",
            _canonical_name_tuple(self.compare_excluded_columns, "compare_excluded_columns"),
        )
        object.__setattr__(
            self,
            "stable_key_candidates",
            _canonical_name_tuple(self.stable_key_candidates, "stable_key_candidates"),
        )
        if self.position_column is not None:
            object.__setattr__(self, "position_column", canonicalize_rule_identifier(self.position_column))
        if self.compare_key_mode is not None and type(self.compare_key_mode) is not TableCompareKeyMode:
            raise ValueError("compare_key_mode must be TableCompareKeyMode or None")
        if self.artifact_scope is not None and type(self.artifact_scope) is not TableArtifactScope:
            raise ValueError("artifact_scope must be TableArtifactScope or None")
        if type(self.pseudo_key_start) is not int or isinstance(self.pseudo_key_start, bool):
            raise ValueError("pseudo_key_start must be an int")
        _reject_ignored_key_conflict(self.compare_key_columns, self.ignored_columns)
        _validate_compare_excluded_columns(
            compare_excluded_columns=self.compare_excluded_columns,
            ignored_columns=self.ignored_columns,
            compare_key_columns=self.compare_key_columns,
            position_column=self.position_column,
            structural_columns=(),
        )
        if self.static_role is TableStaticRole.ORDERED_DIFF:
            _reject_ignored_identity_conflict(self.ignored_columns)


@dataclass(frozen=True, slots=True)
class ResolvedTableRule:
    canonical_table: str
    decision: LegacyRuleDecision
    record: TableRuleRecord

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_table", canonicalize_rule_identifier(self.canonical_table))
        if type(self.decision) is not LegacyRuleDecision:
            raise ValueError("decision must be LegacyRuleDecision")
        if type(self.record) is not TableRuleRecord:
            raise ValueError("record must be TableRuleRecord")


@dataclass(frozen=True, slots=True)
class StorageRuleView:
    canonical_table: str
    canonical_key_policy: CanonicalKeyPolicy
    ordered_policy: OrderedPolicy
    dropped_columns: tuple[DroppedColumn, ...] = ()
    structural_columns: tuple[str, ...] = ()
    retained_columns: tuple[str, ...] = ()
    canonical_key_columns: tuple[str, ...] = ()
    storage_rule_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_table", canonicalize_rule_identifier(self.canonical_table))
        if type(self.canonical_key_policy) is not CanonicalKeyPolicy:
            raise ValueError("canonical_key_policy must be CanonicalKeyPolicy")
        if type(self.ordered_policy) is not OrderedPolicy:
            raise ValueError("ordered_policy must be OrderedPolicy")
        if type(self.dropped_columns) is not tuple:
            raise ValueError("dropped_columns must be a tuple")
        for item in self.dropped_columns:
            if type(item) is not DroppedColumn:
                raise ValueError("dropped_columns must contain DroppedColumn")
        object.__setattr__(
            self,
            "structural_columns",
            _canonical_name_tuple(self.structural_columns, "structural_columns"),
        )
        object.__setattr__(
            self,
            "retained_columns",
            _canonical_name_tuple(self.retained_columns, "retained_columns"),
        )
        object.__setattr__(
            self,
            "canonical_key_columns",
            _canonical_name_tuple(self.canonical_key_columns, "canonical_key_columns"),
        )
        if self.storage_rule_digest is not None and type(self.storage_rule_digest) is not DigestRef:
            raise ValueError("storage_rule_digest must be DigestRef or None")
        _validate_storage_column_sets(
            dropped_columns=self.dropped_columns,
            structural_columns=self.structural_columns,
            retained_columns=self.retained_columns,
            canonical_key_columns=self.canonical_key_columns,
            ordered_policy=self.ordered_policy,
        )


@dataclass(frozen=True, slots=True)
class TableRuleRecord:
    selector: TableRuleSelector
    precedence_class: SelectorPrecedenceClass
    static_role: TableStaticRole
    table_storage: TableStorageDisposition
    canonical_key_policy: CanonicalKeyPolicy
    ordered_policy: OrderedPolicy
    compare_key_mode: TableCompareKeyMode | None = None
    compare_key_columns: tuple[str, ...] = ()
    ignored_columns: tuple[str, ...] = ()
    compare_excluded_columns: tuple[str, ...] = ()
    artifact_scope: TableArtifactScope | None = None
    position_column: str | None = None
    stable_key_candidates: tuple[str, ...] = ()
    dropped_columns: tuple[DroppedColumn, ...] = ()
    structural_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.selector) is not TableRuleSelector:
            raise ValueError("selector must be TableRuleSelector")
        if type(self.precedence_class) is not SelectorPrecedenceClass:
            raise ValueError("precedence_class must be SelectorPrecedenceClass")
        if type(self.static_role) is not TableStaticRole:
            raise ValueError("static_role must be TableStaticRole")
        if type(self.table_storage) is not TableStorageDisposition:
            raise ValueError("table_storage must be TableStorageDisposition")
        if type(self.canonical_key_policy) is not CanonicalKeyPolicy:
            raise ValueError("canonical_key_policy must be CanonicalKeyPolicy")
        if type(self.ordered_policy) is not OrderedPolicy:
            raise ValueError("ordered_policy must be OrderedPolicy")
        if _PRECEDENCE_ROLES[self.precedence_class] is not self.static_role:
            raise ValueError("precedence_class does not match static_role")
        object.__setattr__(self, "compare_key_columns", _canonical_name_tuple(self.compare_key_columns, "compare_key_columns"))
        object.__setattr__(self, "ignored_columns", _canonical_name_tuple(self.ignored_columns, "ignored_columns"))
        object.__setattr__(
            self,
            "compare_excluded_columns",
            _canonical_name_tuple(self.compare_excluded_columns, "compare_excluded_columns"),
        )
        object.__setattr__(
            self,
            "stable_key_candidates",
            _canonical_name_tuple(self.stable_key_candidates, "stable_key_candidates"),
        )
        object.__setattr__(
            self,
            "structural_columns",
            _canonical_name_tuple(self.structural_columns, "structural_columns"),
        )
        if self.position_column is not None:
            object.__setattr__(self, "position_column", canonicalize_rule_identifier(self.position_column))
        if type(self.dropped_columns) is not tuple:
            raise ValueError("dropped_columns must be a tuple")
        for item in self.dropped_columns:
            if type(item) is not DroppedColumn:
                raise ValueError("dropped_columns must contain DroppedColumn")
        if self.compare_key_mode is not None and type(self.compare_key_mode) is not TableCompareKeyMode:
            raise ValueError("compare_key_mode must be TableCompareKeyMode or None")
        if self.artifact_scope is not None and type(self.artifact_scope) is not TableArtifactScope:
            raise ValueError("artifact_scope must be TableArtifactScope or None")
        _validate_rule_record(self)

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_scope": None if self.artifact_scope is None else self.artifact_scope.value,
            "canonical_key_policy": self.canonical_key_policy.value,
            "compare_key_columns": list(self.compare_key_columns),
            "compare_key_mode": None if self.compare_key_mode is None else self.compare_key_mode.value,
            "compare_excluded_columns": list(self.compare_excluded_columns),
            "dropped_columns": [
                {"name": item.name, "reason": item.reason} for item in self.dropped_columns
            ],
            "ignored_columns": list(self.ignored_columns),
            "ordered_policy": self.ordered_policy.value,
            "position_column": self.position_column,
            "precedence_class": self.precedence_class.value,
            "selector": {"kind": self.selector.kind.value, "value": self.selector.value},
            "stable_key_candidates": list(self.stable_key_candidates),
            "static_role": self.static_role.value,
            "structural_columns": list(self.structural_columns),
            "table_storage": self.table_storage.value,
        }


@dataclass(frozen=True, slots=True)
class TableRulesetSnapshot:
    """Immutable ruleset view injected into materialization. No hidden global."""

    table_ruleset_version: int
    compare_keys: tuple[TableCompareKey, ...] = ()
    ruleset_id: str = RULESET_ID
    ruleset_version: str = RULESET_VERSION
    contract_version: str = TABLE_RULESET_CONTRACT_VERSION
    storage_projection_version: str = STORAGE_PROJECTION_VERSION
    rules: tuple[TableRuleRecord, ...] = ()
    ruleset_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if type(self.compare_keys) is not tuple:
            raise ValueError("compare_keys must be a tuple")
        seen_tables: set[str] = set()
        for item in self.compare_keys:
            if type(item) is not TableCompareKey:
                raise ValueError("compare_keys must contain TableCompareKey")
            if item.canonical_table in seen_tables:
                raise ValueError("compare_keys must not repeat canonical_table")
            seen_tables.add(item.canonical_table)
        if self.ruleset_id != RULESET_ID:
            raise ValueError("ruleset_id must be backend-vnext/table-ruleset")
        if self.ruleset_version != RULESET_VERSION:
            raise ValueError(f"ruleset_version must be {RULESET_VERSION}")
        if self.contract_version != TABLE_RULESET_CONTRACT_VERSION:
            raise ValueError("contract_version must be gateway-vnext.table-ruleset:v1")
        if self.storage_projection_version != STORAGE_PROJECTION_VERSION:
            raise ValueError(f"storage_projection_version must be {STORAGE_PROJECTION_VERSION}")
        if type(self.rules) is not tuple:
            raise ValueError("rules must be a tuple")
        seen_selectors: set[str] = set()
        for rule in self.rules:
            if type(rule) is not TableRuleRecord:
                raise ValueError("rules must contain TableRuleRecord")
            serialized = rule.selector.canonical_serialization()
            if serialized in seen_selectors:
                raise ValueError("duplicate selectors are forbidden")
            seen_selectors.add(serialized)
        if self.ruleset_digest is not None and type(self.ruleset_digest) is not DigestRef:
            raise ValueError("ruleset_digest must be DigestRef or None")
        if self.rules:
            if self.ruleset_digest is None:
                raise ValueError("non-empty rules require ruleset_digest")
            expected = compute_ruleset_digest(table_ruleset_document(self))
            if self.ruleset_digest != expected:
                raise ValueError("ruleset_digest does not match the canonical document")
        elif self.ruleset_digest is not None:
            expected = compute_ruleset_digest(table_ruleset_document(self))
            if self.ruleset_digest != expected:
                raise ValueError("ruleset_digest does not match the canonical document")


@dataclass(frozen=True, slots=True)
class OrderedComparisonRule:
    position_column: str
    stable_key_candidates: tuple[str, ...]
    row_identity_key: tuple[str, ...]
    blank_row_policy: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "position_column", canonicalize_rule_identifier(self.position_column))
        object.__setattr__(
            self,
            "stable_key_candidates",
            _canonical_name_tuple(self.stable_key_candidates, "stable_key_candidates"),
        )
        object.__setattr__(
            self,
            "row_identity_key",
            _canonical_name_tuple(self.row_identity_key, "row_identity_key"),
        )
        if type(self.blank_row_policy) is not str or self.blank_row_policy == "":
            raise ValueError("blank_row_policy must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ComparisonRuleView:
    canonical_table: str
    comparison_role: ComparisonRole
    artifact_scope: TableArtifactScope
    compare_key_mode: TableCompareKeyMode | None
    effective_key_columns: tuple[str, ...]
    compare_excluded_columns: tuple[str, ...]
    ordered: OrderedComparisonRule | None
    comparison_rule_digest: DigestRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_table", canonicalize_rule_identifier(self.canonical_table))
        if type(self.comparison_role) is not ComparisonRole:
            raise ValueError("comparison_role must be ComparisonRole")
        if type(self.artifact_scope) is not TableArtifactScope:
            raise ValueError("artifact_scope must be TableArtifactScope")
        if self.compare_key_mode is not None and type(self.compare_key_mode) is not TableCompareKeyMode:
            raise ValueError("compare_key_mode must be TableCompareKeyMode or None")
        object.__setattr__(
            self,
            "effective_key_columns",
            _canonical_name_tuple(self.effective_key_columns, "effective_key_columns"),
        )
        object.__setattr__(
            self,
            "compare_excluded_columns",
            _canonical_name_tuple(self.compare_excluded_columns, "compare_excluded_columns"),
        )
        if self.ordered is not None and type(self.ordered) is not OrderedComparisonRule:
            raise ValueError("ordered must be OrderedComparisonRule or None")
        if type(self.comparison_rule_digest) is not DigestRef:
            raise ValueError("comparison_rule_digest must be DigestRef")
        _validate_compare_excluded_columns(
            compare_excluded_columns=self.compare_excluded_columns,
            ignored_columns=(),
            compare_key_columns=self.effective_key_columns,
            position_column=None if self.ordered is None else self.ordered.position_column,
            structural_columns=(),
        )
        if self.comparison_role is ComparisonRole.ORDERED:
            if self.ordered is None or self.artifact_scope is not TableArtifactScope.ORDERED_SEMANTIC:
                raise ValueError("ORDERED comparison rules require ordered semantics")
        elif self.ordered is not None or self.artifact_scope is TableArtifactScope.ORDERED_SEMANTIC:
            raise ValueError("only ORDERED comparison rules may carry ordered semantics")


@dataclass(frozen=True, slots=True)
class ComparisonRuleSet:
    snapshot: TableRulesetSnapshot

    def __post_init__(self) -> None:
        if type(self.snapshot) is not TableRulesetSnapshot:
            raise ValueError("snapshot must be TableRulesetSnapshot")

    @property
    def ruleset_digest(self) -> DigestRef | None:
        return self.snapshot.ruleset_digest


def table_ruleset_document(snapshot: TableRulesetSnapshot) -> dict[str, object]:
    if type(snapshot) is not TableRulesetSnapshot:
        raise ValueError("snapshot must be TableRulesetSnapshot")
    return {
        "contract_version": snapshot.contract_version,
        "rules": [rule.to_document() for rule in snapshot.rules],
        "ruleset_id": snapshot.ruleset_id,
        "ruleset_version": snapshot.ruleset_version,
        "storage_projection_version": snapshot.storage_projection_version,
        "table_ruleset_version": snapshot.table_ruleset_version,
    }


def compute_ruleset_digest(document: Mapping[str, object]) -> DigestRef:
    if type(document) is not dict:
        raise ValueError("ruleset document must be a dict")
    _reject_unknown_keys(document, _DOCUMENT_TOP_LEVEL_KEYS, "ruleset document")
    payload = canonicalize_json_value(dict(document))
    return DigestRef.from_raw_digest(hashlib.sha256(payload).digest())


def table_ruleset_from_document(document: Mapping[str, object]) -> TableRulesetSnapshot:
    if type(document) is not dict:
        raise ValueError("ruleset document must be a dict")
    _reject_unknown_keys(document, _DOCUMENT_TOP_LEVEL_KEYS, "ruleset document")
    rules_payload = document.get("rules")
    if type(rules_payload) is not list:
        raise ValueError("rules must be a list")
    rules = tuple(_rule_record_from_document(item) for item in rules_payload)
    snapshot = TableRulesetSnapshot(
        table_ruleset_version=_require_positive_int(document.get("table_ruleset_version"), "table_ruleset_version"),
        ruleset_id=_require_string(document.get("ruleset_id"), "ruleset_id"),
        ruleset_version=_require_string(document.get("ruleset_version"), "ruleset_version"),
        contract_version=_require_string(document.get("contract_version"), "contract_version"),
        storage_projection_version=_require_string(
            document.get("storage_projection_version"),
            "storage_projection_version",
        ),
        rules=rules,
        ruleset_digest=compute_ruleset_digest(dict(document)),
    )
    return snapshot


def _rule_record_from_document(payload: object) -> TableRuleRecord:
    if type(payload) is not dict:
        raise ValueError("rule record must be an object")
    _reject_unknown_keys(payload, _RULE_RECORD_KEYS, "rule record")
    selector_payload = payload.get("selector")
    if type(selector_payload) is not dict:
        raise ValueError("selector must be an object")
    _reject_unknown_keys(selector_payload, _SELECTOR_KEYS, "selector")
    dropped_payload = payload.get("dropped_columns")
    if type(dropped_payload) is not list:
        raise ValueError("dropped_columns must be a list")
    return TableRuleRecord(
        selector=TableRuleSelector(
            kind=TableRuleSelectorKind(_require_string(selector_payload.get("kind"), "selector.kind")),
            value=_require_string(selector_payload.get("value"), "selector.value"),
        ),
        precedence_class=SelectorPrecedenceClass(
            _require_string(payload.get("precedence_class"), "precedence_class")
        ),
        static_role=TableStaticRole(_require_string(payload.get("static_role"), "static_role")),
        table_storage=TableStorageDisposition(_require_string(payload.get("table_storage"), "table_storage")),
        canonical_key_policy=CanonicalKeyPolicy(
            _require_string(payload.get("canonical_key_policy"), "canonical_key_policy")
        ),
        ordered_policy=OrderedPolicy(_require_string(payload.get("ordered_policy"), "ordered_policy")),
        compare_key_mode=_optional_enum(payload.get("compare_key_mode"), TableCompareKeyMode, "compare_key_mode"),
        compare_key_columns=_string_tuple(payload.get("compare_key_columns"), "compare_key_columns"),
        ignored_columns=_string_tuple(payload.get("ignored_columns"), "ignored_columns"),
        compare_excluded_columns=_string_tuple(
            payload.get("compare_excluded_columns"), "compare_excluded_columns"
        ),
        artifact_scope=_optional_enum(payload.get("artifact_scope"), TableArtifactScope, "artifact_scope"),
        position_column=_optional_string(payload.get("position_column"), "position_column"),
        stable_key_candidates=_string_tuple(payload.get("stable_key_candidates"), "stable_key_candidates"),
        dropped_columns=tuple(_dropped_column_from_document(item) for item in dropped_payload),
        structural_columns=_string_tuple(payload.get("structural_columns"), "structural_columns"),
    )


def _dropped_column_from_document(payload: object) -> DroppedColumn:
    if type(payload) is not dict:
        raise ValueError("dropped column must be an object")
    _reject_unknown_keys(payload, _DROPPED_COLUMN_KEYS, "dropped column")
    return DroppedColumn(
        name=_require_string(payload.get("name"), "dropped column name"),
        reason=_require_string(payload.get("reason"), "dropped column reason"),
    )


def _validate_rule_record(record: TableRuleRecord) -> None:
    _validate_compare_excluded_columns(
        compare_excluded_columns=record.compare_excluded_columns,
        ignored_columns=record.ignored_columns,
        compare_key_columns=record.compare_key_columns,
        position_column=record.position_column,
        structural_columns=record.structural_columns,
    )
    if set(record.compare_excluded_columns) & {item.name for item in record.dropped_columns}:
        raise ValueError("compare-excluded columns must be retained in storage")
    if record.static_role is TableStaticRole.SKIP:
        if record.table_storage is not TableStorageDisposition.OMIT:
            raise ValueError("SKIP tables must be omitted from storage")
        if record.canonical_key_policy is not CanonicalKeyPolicy.NONE:
            raise ValueError("SKIP tables forbid a canonical key")
        if record.compare_key_mode is not None or record.compare_key_columns:
            raise ValueError("SKIP tables forbid compare keys")
        if record.ignored_columns or record.compare_excluded_columns or record.dropped_columns or record.structural_columns:
            raise ValueError("SKIP tables forbid ignored or dropped columns")
        if record.ordered_policy is not OrderedPolicy.NONE:
            raise ValueError("SKIP tables forbid ordered policy")
        if record.selector.kind is not TableRuleSelectorKind.EXACT:
            raise ValueError("SKIP selectors must be exact")
        return
    if record.table_storage is not TableStorageDisposition.PROJECT:
        raise ValueError("non-SKIP tables must be projected")
    if record.static_role in {TableStaticRole.SNAPSHOT_ONLY, TableStaticRole.BROWSE_ONLY}:
        if record.compare_key_mode is not None or record.compare_key_columns:
            raise ValueError("snapshot-only and browse-only rules forbid compare keys")
        if record.canonical_key_policy is not CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS:
            raise ValueError("snapshot-only and browse-only storage key is DDL primary key or keyless")
        if record.ordered_policy is not OrderedPolicy.NONE:
            raise ValueError("snapshot-only and browse-only forbid ordered policy")
        if record.static_role is TableStaticRole.SNAPSHOT_ONLY:
            if record.selector.kind is not TableRuleSelectorKind.REGEX:
                raise ValueError("snapshot-only selectors must be regex")
        elif record.selector.kind is not TableRuleSelectorKind.EXACT:
            raise ValueError("browse-only selectors must be exact")
        _validate_ignored_drop_mapping(record)
        return
    if record.static_role is TableStaticRole.ORDERED_DIFF:
        if record.selector.kind is not TableRuleSelectorKind.REGEX:
            raise ValueError("ordered selectors must be regex")
        if record.compare_key_mode is not TableCompareKeyMode.ORDERED_STABLE_KEY:
            raise ValueError("ordered rules require ORDERED_STABLE_KEY")
        if record.compare_key_columns != (ORDERED_IDENTITY_COLUMN,):
            raise ValueError("ordered rules require key column gid")
        if record.canonical_key_policy is not CanonicalKeyPolicy.EXPLICIT:
            raise ValueError("ordered storage key must be explicit")
        if record.ordered_policy is not OrderedPolicy.GID_NO_V1:
            raise ValueError("ordered rules require gid_no_v1")
        if record.position_column != ORDERED_POSITION_COLUMN:
            raise ValueError("ordered position_column must be no")
        if record.artifact_scope is not TableArtifactScope.ORDERED_SEMANTIC:
            raise ValueError("ordered artifact_scope must be ORDERED_SEMANTIC")
        if ORDERED_POSITION_COLUMN not in record.structural_columns:
            raise ValueError("ordered no must be RETAIN_FOR_STRUCTURE")
        if any(item.name == ORDERED_POSITION_COLUMN for item in record.dropped_columns):
            raise ValueError("ordered no must not be DROP_FROM_STORAGE")
        _reject_ignored_identity_conflict(record.ignored_columns)
        _validate_ignored_drop_mapping(record)
        _validate_storage_column_sets(
            dropped_columns=record.dropped_columns,
            structural_columns=record.structural_columns,
            retained_columns=(),
            canonical_key_columns=record.compare_key_columns,
            ordered_policy=record.ordered_policy,
        )
        return
    if record.precedence_class is SelectorPrecedenceClass.STANDARD_RAW_PK_FALLBACK:
        if record.selector.kind is not TableRuleSelectorKind.FALLBACK:
            raise ValueError("raw-PK fallback selector must be FALLBACK")
        if record.compare_key_mode is not TableCompareKeyMode.RAW_PRIMARY_KEY:
            raise ValueError("raw-PK fallback requires RAW_PRIMARY_KEY")
        if record.canonical_key_policy is not CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS:
            raise ValueError("raw-PK fallback storage key is DDL primary key or keyless")
    elif record.precedence_class is SelectorPrecedenceClass.STANDARD_DEVICE_CFG:
        if record.selector.kind is not TableRuleSelectorKind.EXACT:
            raise ValueError("device_cfg selector must be exact")
        if record.compare_key_mode is not TableCompareKeyMode.RAW_PRIMARY_KEY:
            raise ValueError("device_cfg requires RAW_PRIMARY_KEY")
        if record.canonical_key_policy is not CanonicalKeyPolicy.DDL_PRIMARY_KEY:
            raise ValueError("device_cfg storage key is DDL primary key")
        if record.artifact_scope is not TableArtifactScope.UPDATE_ONLY:
            raise ValueError("device_cfg artifact_scope must be UPDATE_ONLY")
    elif record.selector.kind is TableRuleSelectorKind.REGEX:
        if record.precedence_class not in {
            SelectorPrecedenceClass.STANDARD_PROTOCOL_OPTION,
            SelectorPrecedenceClass.STANDARD_PROTOCOL_DEVICE,
        }:
            raise ValueError("unexpected regex selector for STANDARD_DIFF")
    elif record.selector.kind is not TableRuleSelectorKind.EXACT:
        raise ValueError("STANDARD_DIFF exact rules require exact selectors")
    if (
        record.canonical_key_policy is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS
        and record.precedence_class is not SelectorPrecedenceClass.STANDARD_RAW_PK_FALLBACK
    ):
        raise ValueError(
            "DDL_PRIMARY_KEY_OR_KEYLESS is restricted to snapshot-only, browse-only, and raw-PK fallback rules"
        )
    if record.ordered_policy is not OrderedPolicy.NONE:
        raise ValueError("STANDARD_DIFF forbids ordered policy")
    if record.canonical_key_policy is CanonicalKeyPolicy.NONE:
        raise ValueError("STANDARD_DIFF requires a canonical key policy")
    _reject_ignored_key_conflict(record.compare_key_columns, record.ignored_columns)
    _validate_ignored_drop_mapping(record)
    _validate_storage_column_sets(
        dropped_columns=record.dropped_columns,
        structural_columns=record.structural_columns,
        retained_columns=(),
        canonical_key_columns=record.compare_key_columns,
        ordered_policy=record.ordered_policy,
    )


def _validate_ignored_drop_mapping(record: TableRuleRecord) -> None:
    dropped_by_name = {item.name: item for item in record.dropped_columns}
    if len(dropped_by_name) != len(record.dropped_columns):
        raise ValueError("dropped_columns must not repeat names")
    expected_reason = legacy_ignored_column_reason(record.selector)
    for name in record.ignored_columns:
        dropped = dropped_by_name.get(name)
        if dropped is None:
            raise ValueError("ignored columns must map to DROP_FROM_STORAGE")
        if dropped.reason != expected_reason:
            raise ValueError("ignored drop reason must be legacy_ignored_column:<selector>")
    for name, dropped in dropped_by_name.items():
        if name in record.ignored_columns:
            continue
        if dropped.reason.startswith("legacy_ignored_column:"):
            raise ValueError("legacy ignored drop reason requires an ignored column")


def _validate_storage_column_sets(
    *,
    dropped_columns: tuple[DroppedColumn, ...],
    structural_columns: tuple[str, ...],
    retained_columns: tuple[str, ...],
    canonical_key_columns: tuple[str, ...],
    ordered_policy: OrderedPolicy,
) -> None:
    dropped_names = tuple(item.name for item in dropped_columns)
    _reject_duplicate_names(dropped_names, "dropped_columns")
    dropped = set(dropped_names)
    structural = set(structural_columns)
    retained = set(retained_columns)
    if dropped & structural:
        raise ValueError("dropped columns must not be structural")
    if dropped & retained:
        raise ValueError("dropped columns must not be retained")
    if dropped & set(canonical_key_columns):
        raise ValueError("dropped columns must not be canonical key columns")
    if ORDERED_IDENTITY_COLUMN in dropped:
        raise ValueError("ordered identity gid must not be dropped")
    if ordered_policy is OrderedPolicy.GID_NO_V1:
        if ORDERED_POSITION_COLUMN not in structural:
            raise ValueError("ordered no must be RETAIN_FOR_STRUCTURE")
        if ORDERED_POSITION_COLUMN in dropped:
            raise ValueError("ordered no must not be DROP_FROM_STORAGE")


def _reject_ignored_key_conflict(key_columns: tuple[str, ...], ignored_columns: tuple[str, ...]) -> None:
    if set(key_columns) & set(ignored_columns):
        raise ValueError("ignored columns must not be effective key columns")


def _reject_ignored_identity_conflict(ignored_columns: tuple[str, ...]) -> None:
    if ORDERED_IDENTITY_COLUMN in set(ignored_columns):
        raise ValueError("ignored columns must not include ordered identity gid")


def _validate_compare_excluded_columns(
    *,
    compare_excluded_columns: tuple[str, ...],
    ignored_columns: tuple[str, ...],
    compare_key_columns: tuple[str, ...],
    position_column: str | None,
    structural_columns: tuple[str, ...],
) -> None:
    if set(compare_excluded_columns) & set(ignored_columns):
        raise ValueError("ignored and compare-excluded columns must not overlap")
    protected = set(compare_key_columns) | set(structural_columns) | {ORDERED_IDENTITY_COLUMN}
    if position_column is not None:
        protected.add(position_column)
    if set(compare_excluded_columns) & protected:
        raise ValueError("compare-excluded columns must not include keys or structural columns")


def _canonical_name_tuple(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    canonical = tuple(canonicalize_rule_identifier(item) for item in values)
    _reject_duplicate_names(canonical, label)
    return canonical


def _reject_duplicate_names(values: tuple[str, ...], label: str) -> None:
    seen: set[str] = set()
    for item in values:
        if item in seen:
            raise ValueError(f"{label} must not contain duplicates")
        seen.add(item)


def _reject_path_shaped(value: str, label: str) -> None:
    lowered = value.casefold()
    windows_drive = len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}
    if (
        "\x00" in value
        or value.startswith("/")
        or value.startswith("\\\\")
        or windows_drive
        or lowered.startswith("file:")
    ):
        raise ValueError(f"{label} must not be a filesystem path")


def _reject_unknown_keys(payload: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{label} contains unknown fields")


def _require_string(value: object, label: str) -> str:
    if type(value) is not str or value == "":
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, label)


def _require_positive_int(value: object, label: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive int")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise ValueError(f"{label} must be a list")
    names: list[str] = []
    for item in value:
        names.append(_require_string(item, label))
    return tuple(names)


def _optional_enum(value: object, enum_type: type[Any], label: str) -> Any:
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"{label} must be a string or null")
    return enum_type(value)
