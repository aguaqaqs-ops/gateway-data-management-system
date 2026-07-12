from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ....core.digests import DigestRef
from ....core.identifiers import canonical_identifier


@dataclass(frozen=True, slots=True)
class OrderedTablePolicy:
    policy_id: str
    policy_version: str
    payload: Mapping[str, object] = field(default_factory=dict)
    policy_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", _mapping_payload(self.payload))
        if self.policy_digest is not None:
            object.__setattr__(self, "policy_digest", DigestRef.parse(str(self.policy_digest)))

    def to_payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "payload": _mapping_payload(self.payload),
            "policy_digest": self.policy_digest.to_payload() if self.policy_digest is not None else None,
        }


def build_ordered_table_policy(
    *,
    table_name: str,
    row_identity_key: str | None,
    stable_key_candidates: Sequence[str],
    order_key: str,
    ignored_columns: Sequence[str],
    value_columns: Sequence[str],
    blank_row_policy: str,
    pseudo_key_start: int,
    move_policy: str,
    policy_version: str = "v1",
) -> OrderedTablePolicy:
    canonical_table_name = canonical_identifier(table_name)
    payload = {
        "table_name": canonical_table_name,
        "row_identity_key": None if row_identity_key is None else canonical_identifier(row_identity_key),
        "stable_key_candidates": _normalized_identifier_tuple(stable_key_candidates),
        "order_key": canonical_identifier(order_key),
        "ignored_columns": _normalized_identifier_tuple(ignored_columns),
        "value_columns": _normalized_identifier_tuple(value_columns),
        "blank_row_policy": blank_row_policy,
        "pseudo_key_start": pseudo_key_start,
        "move_policy": move_policy,
    }
    return OrderedTablePolicy(
        policy_id=f"{canonical_table_name}:ordered-policy",
        policy_version=policy_version,
        payload=payload,
        policy_digest=DigestRef.from_payload(payload),
    )


def ordered_policy_value(policy: OrderedTablePolicy | None, key: str, default: object | None = None) -> object | None:
    if policy is None:
        return default
    return policy.payload.get(key, default)


def ordered_policy_payload(policy: OrderedTablePolicy | None) -> dict[str, object]:
    if policy is None:
        return {}
    return dict(policy.payload)


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("policy payload keys must be strings")
        normalized[key] = value
    return normalized


def _normalized_identifier_tuple(values: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("identifier values must be non-empty strings")
        normalized_value = canonical_identifier(value)
        if normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized.append(normalized_value)
    return tuple(sorted(normalized))
